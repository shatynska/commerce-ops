"""Containment across a real transaction: what a failed launch leaves, and
what the launch behind it can still write.

Derived strictly from the delta spec of the OpenSpec change
`contain-a-failing-launch`:
`openspec/changes/contain-a-failing-launch/specs/launch-clickup-sync/spec.md`

Covers exactly two scenarios of the ADDED requirement *One launch's failure
does not stop the other launches being converged*:

- *A partially projected launch keeps what its failed attempt achieved*
- *A launch attempted after one that failed on the database is unaffected
  by it*

Every other scenario of that requirement is unit-tier, in
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_containment.py`.

## Why these two are here and not there

`tasks.md` 1.2 states it, and it is the whole reason this file exists: an
in-memory mapping store models no transaction, so it passes both of these
whether or not the rollback (`tasks.md` 2.3) was implemented.

- *A partially projected launch keeps what its failed attempt achieved*
  asserts that work **committed** before a failure survives a rollback the
  pass performs afterwards. A fake store keeps its dictionary entries
  through any exception, so it cannot tell a committed write from a
  pending one -- and "nothing is pending when the rollback runs" is
  precisely the property `design.md` says makes the unconditional rollback
  safe.
- *A launch attempted after one that failed on the database is unaffected
  by it* needs a genuinely failed transaction, not merely an exception. A
  fake that raises leaves its next write perfectly able to succeed, so the
  test would be green with no rollback at all. Here the first launch's
  attempt runs a statement the database rejects, which leaves the shared
  `AsyncSession` in the failed state a rollback exists to clear; the
  second launch's write then succeeds only if the pass recovered.

`tasks.md` 1.2 offers an alternative -- a fake refusing every write until
`rollback()` has been called. It was **not** taken. It would establish that
the implementation calls a method named `rollback`, which is a fact about
the code's shape; a real session establishes that the *next launch's write
lands*, which is what the scenario states, and it costs no more here
because this tier already has a database and the mapping store to write
through.

## Level

The job body, over a real Postgres session. The walk is the subject and
lives only in the job; the transaction is the mechanism and exists only
against a real database. Nothing smaller has both.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the walk shares one `AsyncSession`
(`design.md` -- Context), that every write in it is committed as it is made
(same), and that a contained failure rolls that session back before the next
launch (*A contained failure rolls the session back*).

INVENTED, with correction points:

- The collaborator names substituted on the job module -- `session`,
  `converge_launch`, `reconcile_launch`, `LaunchRepository`,
  `PlaybookRepository`. Correction point: `driven_job`.
- `ClickUpMappingRepository`'s method names, transcribed from
  `test_launch_clickup_mapping.py`, which records them as invented there.
- That the failing launch's projection writes through the *shared* session
  rather than one of its own. `design.md` names the mapping store as one of
  the walk's two writing paths on that session, so a projection writing
  anywhere else would make the rollback question moot -- and this file's
  fake projection is what stands in for the real one either way.

## Test-database lifecycle

The tier's own convention: unique SKUs and unique ClickUp identifiers per
test, no truncate fixture, `alembic upgrade head` assumed applied, and the
`database_url` fixture gating on a configured database.

## Expected first-run state

`reconcile_clickup_completions` has no containment yet, so both tests are
expected to fail on a wrong value -- the second launch never attempted --
rather than on an absent target.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` -- 1114 passed, 0 failed;
`uv run pytest tests/integration` -- 93 passed, 2 skipped (both skips
pre-existing and unrelated).
"""

from __future__ import annotations

import inspect
import sys
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import date
from types import ModuleType
from typing import Any, Final

import pytest
from procrastinate import job_context, jobs
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import ClickUpSyncError
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

pytestmark = pytest.mark.anyio

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
STEP_ID: Final = "listing.title-conforms"
LAUNCH_DATE: Final = date(2027, 3, 2)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_launch_clickup_mapping.py`
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"CC-{uuid.uuid4().hex[:12].upper()}")


def _unique_clickup_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (_step(),)
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(*steps, *fillers))


def _start(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=_playbook(), launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# The walk, driven over a real session
# ---------------------------------------------------------------------------


def _runner_app() -> Any:
    from commerce_ops.shared.infrastructure.driven.job_runner import app

    return app


def _completion_periodic() -> Any:
    registered = list(_runner_app().periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "clickup" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the ClickUp completion pass; "
        f"registered periodics are {[entry.task.name for entry in registered]}"
    )
    return matching[0]


def _job_module() -> ModuleType:
    return sys.modules[_completion_periodic().task.func.__module__]


async def _run_job() -> Any:
    task = _completion_periodic().task
    parameters = inspect.signature(task.func).parameters
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=_runner_app(),
                job=jobs.Job(
                    id=1,
                    queue=task.queue,
                    lock=task.lock,
                    queueing_lock=task.queueing_lock,
                    task_name=task.name,
                    task_kwargs={},
                    attempts=0,
                ),
                start_timestamp=time.time(),
                abort_reason=lambda: None,
            )
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


@dataclass
class _Walk:
    """What the fake passes did, and the session they were handed."""

    session: AsyncSession | None = None
    converged: list[ProductId] = field(default_factory=list)
    reconciled: list[ProductId] = field(default_factory=list)
    observed_lists: dict[ProductId, str | None] = field(default_factory=dict)


class _FakeJobLaunches:
    def __init__(self, launches: tuple[Launch, ...]) -> None:
        self._launches = launches

    async def list_active(self) -> tuple[Launch, ...]:
        return self._launches

    active = list_active
    all_active = list_active

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return self._launches


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str = "") -> LaunchPlaybook:
        return _playbook()


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    for candidate in (*args, *kwargs.values()):
        if isinstance(candidate, Launch):
            return candidate.product_id
        if isinstance(candidate, ProductId):
            return candidate
    pytest.fail(
        "a pass was called with no launch among its arguments "
        f"(args={args!r}, kwargs={kwargs!r})"
    )


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
def new_mapping(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]]:
    """An independent session, so a read proves the write reached Postgres
    rather than the walk's own identity map."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[ClickUpMappingRepository]:
        async with maker() as session:
            yield ClickUpMappingRepository(session)

    return _open


@pytest.fixture()
def launched_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product with a launch record.

    The mapping rows key to the launch, so a product alone is not a state
    they can exist in.
    """

    async def _launch() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        async with maker() as session:
            await LaunchRepository(session).save(_start(product.id))
        return product.id

    return _launch


@pytest.fixture()
def driven_job(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> Callable[..., _Walk]:
    """Install the walk's collaborators over a real session, and hand back
    the recorder they write through.

    The session the job is given is a real `AsyncSession` from this test's
    engine, so the two passes below write, fail and recover exactly where
    the implementation does.
    """
    job_module = _job_module()
    maker = async_sessionmaker(engine, expire_on_commit=False)

    def _install(
        launches: tuple[ProductId, ...],
        converge: Any,
        reconcile: Any | None = None,
    ) -> _Walk:
        walk = _Walk()

        @asynccontextmanager
        async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[AsyncSession]:
            async with maker() as session:
                walk.session = session
                yield session

        assert hasattr(job_module, "session"), (
            f"{job_module.__name__} exposes no `session`; correct this "
            "fixture to the provider it does use"
        )
        monkeypatch.setattr(job_module, "session", _provider)

        if hasattr(job_module, "transaction"):
            # `trigger-clickup-projection-on-launch-events`: the pass now
            # also opens `transaction()` per launch, solely to hold
            # `hold_launch_advance_lock`. Left unpatched, that call falls
            # through to the real application engine singleton — a second,
            # long-lived connection pool this test's own `engine` fixture
            # does not own or dispose, whose connections can outlive this
            # test's event loop and get handed to a *later* test's, on a
            # *different* loop, once pytest-asyncio/anyio tears this one
            # down. A genuinely separate connection from `walk.session`
            # (never bound to `walk.session` itself), still from this
            # test's own `engine`, so the property under test — the lock
            # and `converge_launch`'s writes living on different
            # connections — still holds.
            @asynccontextmanager
            async def _lock_provider(
                *args: Any, **kwargs: Any
            ) -> AsyncIterator[AsyncSession]:
                async with maker() as lock_session:
                    yield lock_session

            monkeypatch.setattr(job_module, "transaction", _lock_provider)

        monkeypatch.setattr(job_module, "PlaybookRepository", _FakePlaybookRepository)
        monkeypatch.setattr(
            job_module,
            "LaunchRepository",
            lambda *a, **k: _FakeJobLaunches(
                tuple(_start(product) for product in launches)
            ),
        )

        async def _converge(*args: Any, **kwargs: Any) -> None:
            product_id = _product_of(args, kwargs)
            walk.converged.append(product_id)
            await converge(walk, product_id)

        async def _reconcile(*args: Any, **kwargs: Any) -> None:
            product_id = _product_of(args, kwargs)
            walk.reconciled.append(product_id)
            if reconcile is not None:
                await reconcile(walk, product_id)

        monkeypatch.setattr(job_module, "converge_launch", _converge)
        monkeypatch.setattr(job_module, "reconcile_launch", _reconcile)
        return walk

    return _install


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# converged
# ---------------------------------------------------------------------------


async def test_a_partially_projected_launch_keeps_what_its_failed_attempt_achieved(
    driven_job: Callable[..., _Walk],
    launched_product_id: Callable[[], Awaitable[ProductId]],
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
) -> None:
    """Scenario: A partially projected launch keeps what its failed attempt
    achieved.

    WHEN a launch's projection raises after its list and some of its tasks
    were created and recorded
    THEN the list and task associations recorded before the failure survive
    it
    AND the next run's projection continues from them rather than starting
    the launch again.

    Two launches, not one: the run has to be a *contained* run for the
    rollback that follows the failure to happen at all, and a single-launch
    walk would never reach it.
    """
    failing = await launched_product_id()
    behind = await launched_product_id()
    list_id = _unique_clickup_id("list")
    task_id = _unique_clickup_id("task")
    behind_list_id = _unique_clickup_id("list-behind")

    async def _partial_projection(walk: _Walk, product_id: ProductId) -> None:
        assert walk.session is not None
        mapping = ClickUpMappingRepository(walk.session)
        if product_id == failing:
            # The list was created in ClickUp and recorded, and so was one
            # task -- and then the projection raised, exactly as the
            # production fault did on its next `create_task`.
            await mapping.record_list(product_id, list_id)
            await mapping.record_task(product_id, STEP_ID, task_id)
            raise ClickUpSyncError("create_task -> 404 Not Found")
        await mapping.record_list(product_id, behind_list_id)

    driven_job((failing, behind), _partial_projection)

    with pytest.raises(Exception):  # noqa: B017 -- the run's outcome is
        await _run_job()  # asserted in the unit-tier containment file.

    async with new_mapping() as other:
        # SPECIFIED: the list and task associations recorded before the
        # failure survive it -- read back through an independent session,
        # after the walk's own session has been rolled back and closed.
        assert await other.list_id_for(failing) == list_id, (
            "the list recorded before the failure did not survive it, so a "
            "later run would create a second list for this launch"
        )
        recorded_task = await other.task_for(failing, STEP_ID)
        assert recorded_task is not None and recorded_task.task_id == task_id, (
            "the task association recorded before the failure did not survive it"
        )
        # Guard: the launch behind the failing one was attempted at all,
        # so the assertions above are about a contained failure rather than
        # an abandoned walk.
        assert await other.list_id_for(behind) == behind_list_id, (
            "the launch behind the failing one never recorded its list, so "
            "the walk did not continue past the failure"
        )

    # The next run: its projection reads what is already recorded.
    async def _resuming_projection(walk: _Walk, product_id: ProductId) -> None:
        assert walk.session is not None
        mapping = ClickUpMappingRepository(walk.session)
        walk.observed_lists[product_id] = await mapping.list_id_for(product_id)

    second = driven_job((failing, behind), _resuming_projection)
    await _run_job()

    # SPECIFIED: the next run's projection continues from them rather than
    # starting the launch again.
    assert second.observed_lists.get(failing) == list_id, (
        "the next run's projection did not find the list its failed "
        f"predecessor recorded; it found {second.observed_lists.get(failing)!r}"
    )


async def test_a_launch_after_one_that_failed_on_the_database_is_unaffected_by_it(
    driven_job: Callable[..., _Walk],
    launched_product_id: Callable[[], Awaitable[ProductId]],
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
) -> None:
    """Scenario: A launch attempted after one that failed on the database is
    unaffected by it.

    WHEN attempting one launch fails with a database error the pass recovers
    from, and a later launch is then attempted
    THEN the later launch is projected and reconciled exactly as it would
    have been had the earlier launch succeeded
    AND the writes it makes are recorded.

    The database error is a real one -- a statement Postgres rejects, which
    leaves the shared session's transaction in the failed state every
    subsequent write raises against until it is rolled back. That is what a
    fake cannot produce and what the rollback exists for.
    """
    failing = await launched_product_id()
    behind = await launched_product_id()
    behind_list_id = _unique_clickup_id("list-behind")
    behind_task_id = _unique_clickup_id("task-behind")

    async def _projection(walk: _Walk, product_id: ProductId) -> None:
        assert walk.session is not None
        if product_id == failing:
            # A database fault, not a ClickUp one: the transaction is left
            # in a failed state, so every later write on this session
            # raises until the pass rolls it back.
            await walk.session.execute(text("SELECT 1 / 0"))
            pytest.fail("the database accepted a statement it must reject")
        mapping = ClickUpMappingRepository(walk.session)
        await mapping.record_list(product_id, behind_list_id)

    async def _reconciliation(walk: _Walk, product_id: ProductId) -> None:
        assert walk.session is not None
        mapping = ClickUpMappingRepository(walk.session)
        await mapping.record_task(product_id, STEP_ID, behind_task_id)

    walk = driven_job((failing, behind), _projection, _reconciliation)

    with pytest.raises(Exception) as raised:
        await _run_job()

    # SPECIFIED: the later launch is projected and reconciled exactly as it
    # would have been had the earlier launch succeeded.
    assert walk.converged == [failing, behind], (
        "the launch after the database fault was never converged; the walk "
        f"converged {walk.converged}"
    )
    assert walk.reconciled == [behind], (
        "the launch after the database fault was not reconciled as it would "
        f"have been otherwise; the walk reconciled {walk.reconciled}"
    )

    async with new_mapping() as other:
        # SPECIFIED: the writes it makes are recorded -- read back through
        # an independent session, which is the only way to tell a write
        # that landed from one that raised into a poisoned transaction.
        assert await other.list_id_for(behind) == behind_list_id, (
            "the launch after the database fault could not record its list, "
            "so the failed transaction reached it"
        )
        recorded = await other.task_for(behind, STEP_ID)
        assert recorded is not None and recorded.task_id == behind_task_id, (
            "the launch after the database fault could not record its task"
        )
        # SPECIFIED: "no state left by one launch's attempt affects
        # another's" -- the failing launch recorded nothing, and nothing
        # was recorded for it by accident either.
        assert await other.list_id_for(failing) is None

    # SPECIFIED, by the run-outcome clause of the same requirement: the run
    # names the launch that failed. Asserted here rather than left to the
    # unit tier because this is the only place a *database* failure is the
    # one being named.
    message = str(raised.value)
    assert failing.value in message, (
        f"the run's error did not name the launch that failed: {message!r}"
    )
    assert behind.value not in message, (
        f"the run's error named the launch that succeeded: {message!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the recovery is a `rollback()` specifically, as opposed to any
#   other means of restoring the session. The scenario states the effect --
#   the later launch's writes are recorded -- and the effect is what is
#   asserted; `design.md` chooses the means.
# - A database that accepts rollbacks while refusing writes (a read-only
#   failover, a full disk). `design.md` -- Risks names it as accepted
#   unmitigated, so there is no stated behaviour to assert.
# - Recovery from a fault raised by `reconcile_launch` rather than by
#   `converge_launch`. The requirement contains both halves as one unit and
#   states no difference between them; the unit tier drives the
#   reconciliation half.
# ---------------------------------------------------------------------------
