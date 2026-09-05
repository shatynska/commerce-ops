"""What a real advisory lock and a real, separate transaction hold for the
eager-convergence helper.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers exactly the two claims of the ADDED requirement *A launch is
converged eagerly at start and at a gate crossing* that no in-memory
double can establish:

- *The eager run and the pass do not duplicate each other's work* — the
  concurrency half. `design.md` names "two eager calls — e.g., a
  webhook-triggered one and a Slack-decision one racing the same gate
  crossing" as one of the cases the shared advisory lock exists to close,
  alongside an eager call racing the periodic pass; this file drives that
  exact case — two genuinely concurrent eager calls for the same
  brand-new launch — because it needs no periodic-pass machinery to set
  up and exercises the identical lock. `tasks.md` 6.3.
- The unstated half of `tasks.md` 1.2's partial-failure test: that a
  failure partway through convergence leaves what was written *on a real
  Postgres session* standing, because the lock's own transaction — a
  genuinely different connection — is what could otherwise roll it back
  were `converge_launch`'s collaborators ever rebound to it. The unit-tier
  version of this same claim, against fakes with no transactional
  semantics, is `test_eager_convergence_helper.py`'s; this is what makes
  it real.

See `test-manifest.md` at the change root for the full accounting.

## Why these two are here and not at the unit tier

`design.md` — "The lock acquisition and `converge_launch`'s own writes
deliberately do not share a transaction": the whole point of that decision
is a fact about two different Postgres connections and what
`join_transaction_mode="create_savepoint"` would do to one of them if the
decision were reversed. A fake session has no such semantics — it cannot
demonstrate that a real savepoint rollback around the lock's own
transaction leaves work on a *different* session's connection untouched,
and it cannot demonstrate that a real `pg_advisory_xact_lock` excludes a
genuinely concurrent second caller. Both claims exist only against a real
database.

## Level

The eager-convergence helper over a real Postgres session, with a real
catalog product, a real launch record and a fake ClickUp client (an
in-memory double stands in for the external API in every tier this
repository has, including its other live-Postgres files — see
`test_clickup_sync_job_containment_live.py`'s own precedent of
substituting `converge_launch`'s ClickUp-facing side while keeping the
mapping store real).

## Test-database lifecycle

The tier's own convention: a unique SKU per test, no truncate fixture,
`alembic upgrade head` assumed applied, and the `database_url` fixture
gating on a configured database.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the helper opens its own
`transaction()` solely to hold `hold_launch_advance_lock`, and that
`converge_launch`'s own collaborators (`mapping` above all) stay bound to
the caller's own session rather than being rebound to that lock-only
transaction (`tasks.md` 1.1; `design.md`).

INVENTED, each with a correction point:

- **Where** the helper lives and its name — `_MODULE_CANDIDATES` and
  `_HELPER_NAMES`, kept in step with `test_eager_convergence_helper.py`,
  which is the correction point for both.
- The helper's call shape (`_invoke`), probed and filtered by its
  implemented signature.
- `converge_launch`'s own collaborator keywords (`launch`, `playbook`,
  `clickup`, `mapping`, `read_product`, `members`, `folder_id`) —
  transcribed from `test_clickup_sync_projection.py`, which records them
  as invented there.
- `ClickUpMappingRepository`'s method names, transcribed from
  `test_launch_clickup_mapping.py` and `test_clickup_sync_job_containment_live.py`.

## Expected first-run state

Neither candidate module carries this helper yet (`tasks.md` 1.1), so
every test here is expected to fail on an **absent target** where a
database is configured, and to skip where one is not. Per
`ai-toolkit:testing` that establishes absence only.

**This file has never been executed.** The environment it was written in
configures no `DATABASE_URL`, so the tier skipped rather than ran.
Whoever implements the change should run
`uv run pytest tests/integration/launch/test_eager_convergence_atomicity_live.py`
against a real database *before* trusting a green result from it.

Baseline recorded before this file was written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/integration` — 3
passed, 125 skipped (no `DATABASE_URL` is configured here).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import uuid
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from types import ModuleType
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.shared.domain.clickup import ClickUpListState
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fakes import FakeProductReader as _FakeCatalog
from tests.support.fixtures import LAUNCH_DATE, MARKETPLACE
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import CatalogProduct as _CatalogProduct
from tests.support.values import CreatedTask as _CreatedTask
from tests.support.values import FakeTask as _FakeTask

pytestmark = pytest.mark.anyio

STEP_ID: Final = "listing.title-conforms"
SECOND_STEP_ID: Final = "listing.images-conform"
FOLDER_ID: Final = "90110042424"

_MODULE_CANDIDATES: Final = (
    "commerce_ops.launch.infrastructure.driven.clickup_sync",
    "commerce_ops.launch.infrastructure.driving.gate_progression_job",
)
_HELPER_NAMES: Final = (
    "converge_launch_eagerly",
    "eager_converge_launch",
    "converge_launch_now",
    "converge_one_launch_eagerly",
    "eagerly_converge_launch",
)
_LOCK_NAMES: Final = ("hold_launch_advance_lock", "advance_lock", "hold_advance_lock")
_SESSION_NAMES: Final = ("transaction", "session")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"EC-{uuid.uuid4().hex[:12].upper()}")


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": STEP_ID, **overrides})


def _second_step() -> StepDefinition:
    return _step(identifier=SECOND_STEP_ID, name="Second piece of work")


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        name="Work this step asks for",
    )


def _playbook(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    return _build_playbook(
        *steps,
        filler=_hold,
    )


def _launch(product_id: ProductId, playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# A real catalog product with a launch, and a fake catalog reader wrapping
# it (`converge_launch` only reads `.name`/`.sku` off what `read_product`
# returns).
# ---------------------------------------------------------------------------


async def _new_product(engine: AsyncEngine) -> ProductId:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        product = await register_product(
            CatalogProductRepository(session),
            sku=_unique_sku(),
            marketplace_id=MARKETPLACE,
            name="Bamboo Cutting Board",
        )
    return product.id


async def _persist_launch(engine: AsyncEngine, launch: Launch) -> None:
    """Writes a `launch_positions` row for `launch.product_id` — a real
    launch record, matching `test_webhook_advance_atomicity_live.py`'s own
    `_launch_standing_at` precedent. Required: `launch_clickup_lists` and
    `launch_clickup_tasks` both carry a foreign key to `launch_positions`,
    so `converge_launch`'s own writes (through `ClickUpMappingRepository`)
    fail without one — `converge_launch` itself never reads this row back,
    since it takes the `Launch` it converges as an argument, but the row
    still has to exist for its writes to be accepted.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        await LaunchRepository(session).save(launch)


# ---------------------------------------------------------------------------
# A fake ClickUp — in-memory, transcribed from `test_clickup_sync_projection.py`
# ---------------------------------------------------------------------------


class _FakeClickUp:
    def __init__(self, *, fail_after_tasks: int | None = None) -> None:
        self.lists: dict[str, str] = {}
        self.tasks: dict[str, _FakeTask] = {}
        self.calls: list[tuple[str, Any]] = []
        self._next = 0
        self._fail_after_tasks = fail_after_tasks

    def _identifier(self, prefix: str) -> str:
        self._next += 1
        return f"{prefix}-{uuid.uuid4().hex[:8]}-{self._next:03d}"

    async def read_list_state(self, list_id: str) -> ClickUpListState:
        return ClickUpListState(deleted=False)

    async def create_list(self, folder_id: str, name: str) -> str:
        self.calls.append(("create_list", {"folder_id": folder_id, "name": name}))
        list_id = self._identifier("list")
        self.lists[list_id] = name
        return list_id

    async def create_task(
        self, list_id: str, name: str, description: str | None = None, **fields: Any
    ) -> _CreatedTask:
        if (
            self._fail_after_tasks is not None
            and len(self.tasks) >= self._fail_after_tasks
        ):
            raise RuntimeError("simulated ClickUp fault partway through projection")
        self.calls.append(("create_task", {"list_id": list_id, "name": name, **fields}))
        task_id = self._identifier("task")
        self.tasks[task_id] = _FakeTask(id=task_id, name=name, list_id=list_id)
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def update_task(self, task_id: str, fields: dict[str, Any]) -> _CreatedTask:
        self.calls.append(("update_task", {"task_id": task_id, "fields": dict(fields)}))
        return _CreatedTask(id=task_id, url=f"https://app.clickup.com/t/{task_id}")

    async def add_task_tag(self, task_id: str, tag_name: str) -> None:
        self.calls.append(("add_task_tag", {"task_id": task_id, "tag": tag_name}))

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        return [task for task in self.tasks.values() if task.list_id == list_id]

    def calls_named(self, name: str) -> list[Any]:
        return [payload for called, payload in self.calls if called == name]


# ---------------------------------------------------------------------------
# Reaching the helper — transcribed from `test_eager_convergence_helper.py`
# ---------------------------------------------------------------------------


def _locate_helper() -> tuple[ModuleType, str]:
    for path in _MODULE_CANDIDATES:
        try:
            module = importlib.import_module(path)
        except ImportError:
            continue
        for name in _HELPER_NAMES:
            if callable(getattr(module, name, None)):
                return module, name
    pytest.fail(
        f"neither of {_MODULE_CANDIDATES} exposes an eager-convergence helper "
        f"under any of {_HELPER_NAMES}; `tasks.md` 1.1 adds it to one of "
        "them. This is the absent-target state, not a defect in this file."
    )


def _bind_lock_transaction(module: ModuleType, engine: AsyncEngine) -> None:
    """Point the helper's own lock-only `transaction()`/`session` seam at
    this test's engine, on a *separate* connection each time it is
    entered — transcribed from `test_webhook_advance_atomicity_live.py`'s
    `_bind_session_providers`, which records why `transaction` is rebuilt
    with savepoint semantics rather than aliased to a shared session."""

    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[AsyncSession]:
        async with engine.connect() as connection, connection.begin():
            db_session = AsyncSession(
                bind=connection,
                join_transaction_mode="create_savepoint",
                expire_on_commit=False,
            )
            try:
                yield db_session
            finally:
                await db_session.close()

    for name in _SESSION_NAMES:
        if hasattr(module, name):
            setattr(module, name, _provider)


async def _invoke(
    module: ModuleType,
    name: str,
    *,
    launch: Launch,
    playbook: LaunchPlaybook,
    clickup: Any,
    mapping: ClickUpMappingRepository,
    read_product: Any,
) -> None:
    """INVENTED call shape — kept in step with
    `test_eager_convergence_helper.py`'s own `_invoke`, the correction
    point for both."""
    entry = getattr(module, name)
    parameters = inspect.signature(entry).parameters
    pool: dict[str, Any] = {
        "product_id": launch.product_id,
        "product": launch.product_id,
        "launch": launch,
        "playbook": playbook,
        "clickup": clickup,
        "mapping": mapping,
        "read_product": read_product,
        "members": None,
        "folder_id": FOLDER_ID,
    }
    supplied = {key: value for key, value in pool.items() if key in parameters}
    await entry(**supplied)


@pytest.fixture(autouse=True)
def _restore_module_globals() -> Any:
    """Undo every substitution this module makes on the helper's own
    module — transcribed from `test_webhook_advance_atomicity_live.py`'s
    identically-purposed fixture, which records why: left in place, a
    `session`/`transaction` bound to this test's own event loop outlives
    this file and breaks the next module to touch it."""
    _MISSING: Any = object()
    names = (*_SESSION_NAMES, *_LOCK_NAMES, *_HELPER_NAMES)
    modules = []
    for path in _MODULE_CANDIDATES:
        try:
            modules.append(importlib.import_module(path))
        except ImportError:
            continue
    saved = [
        (
            module,
            {
                name: getattr(module, name)
                for name in names
                if getattr(module, name, _MISSING) is not _MISSING
            },
        )
        for module in modules
    ]
    try:
        yield
    finally:
        for module, values in saved:
            for name, value in values.items():
                setattr(module, name, value)


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@asynccontextmanager
async def _mapping_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


# ---------------------------------------------------------------------------
# Scenario: The eager run and the pass do not duplicate each other's work
# — the concurrency half
# ---------------------------------------------------------------------------


async def test_two_concurrent_eager_calls_for_a_brand_new_launch_produce_one_list(
    engine: AsyncEngine,
) -> None:
    """Scenario: The eager run and the pass do not duplicate each other's
    work.

    WHEN two eager calls race the same brand-new launch's first
    convergence — the case `design.md` names explicitly ("two eager calls
    — e.g., a webhook-triggered one and a Slack-decision one racing the
    same gate crossing")
    THEN neither creates a second list for it: the launch's first list has
    no recorded mapping yet for either concurrent caller to check against,
    so the advisory lock — taken by both — is what serializes them rather
    than the mapping read they would otherwise race.

    Driven as two genuinely concurrent tasks, each with its **own**
    collaborators — a separate `_FakeClickUp`, and its own
    `ClickUpMappingRepository` bound to its own session — because the real
    thing this test establishes is that two independent callers, exactly
    as the eager helper's four real call sites would be, do not each
    decide unilaterally that no list exists yet.
    """
    module, name = _locate_helper()
    _bind_lock_transaction(module, engine)
    product_id = await _new_product(engine)
    playbook = _playbook((_step(),))
    launch_a = _launch(product_id, playbook)
    launch_b = _launch(product_id, playbook)
    # A real `launch_positions` row: `launch_clickup_lists` carries a
    # foreign key to it, so either concurrent caller's `converge_launch`
    # write would otherwise fail before the lock is even reached.
    await _persist_launch(engine, _launch(product_id, playbook))
    catalog = _FakeCatalog(
        _CatalogProduct(name="Bamboo Cutting Board", sku=_unique_sku())
    )
    clickup_a = _FakeClickUp()
    clickup_b = _FakeClickUp()

    async def _call(launch: Launch, clickup: _FakeClickUp) -> None:
        async with _mapping_session(engine) as session:
            mapping = ClickUpMappingRepository(session)
            await _invoke(
                module,
                name,
                launch=launch,
                playbook=playbook,
                clickup=clickup,
                mapping=mapping,
                read_product=catalog,
            )

    await asyncio.gather(
        _call(launch_a, clickup_a), _call(launch_b, clickup_b), return_exceptions=True
    )

    total_lists_created = len(clickup_a.calls_named("create_list")) + len(
        clickup_b.calls_named("create_list")
    )
    # SPECIFIED: neither SHALL create a second list — across both callers,
    # exactly one `create_list` call was made, however they interleaved.
    assert total_lists_created <= 1, (
        "two concurrent eager calls for the same brand-new launch created "
        f"more than one ClickUp list between them ({total_lists_created} "
        f"`create_list` calls); the advisory lock did not serialize them"
    )
    async with _mapping_session(engine) as session:
        recorded = await ClickUpMappingRepository(session).list_id_for(product_id)
    # Premise: at least one of the two callers actually converged the
    # launch, so a green result above is not simply both having silently
    # failed.
    assert recorded is not None, (
        "neither concurrent eager call recorded a list for the launch, so "
        "this test exercised no convergence at all"
    )


# ---------------------------------------------------------------------------
# `tasks.md` 1.2's partial-failure claim, made real: prior writes on the
# real session are not undone by the lock's own (different) transaction
# ---------------------------------------------------------------------------


async def test_a_failure_partway_through_the_eager_run_leaves_real_prior_writes_standing(
    engine: AsyncEngine,
) -> None:
    """`tasks.md` 1.2: "a failure partway through `converge_launch` (e.g.
    after the list is created but before a task write) leaves the list and
    any completed writes standing rather than rolled back."

    The list and the first task's mapping row are written through a real
    `ClickUpMappingRepository` on its own session; the eager helper's lock
    is taken on a *different* connection, whose own transaction rolls back
    around the raised failure. Read back through a third, independent
    session, so what is asserted is what Postgres actually holds — not
    what the failing call's own identity map still remembers.
    """
    module, name = _locate_helper()
    _bind_lock_transaction(module, engine)
    product_id = await _new_product(engine)
    playbook = _playbook((_step(), _second_step()))
    launch = _launch(product_id, playbook)
    await _persist_launch(engine, _launch(product_id, playbook))
    catalog = _FakeCatalog(
        _CatalogProduct(name="Bamboo Cutting Board", sku=_unique_sku())
    )
    clickup = _FakeClickUp(fail_after_tasks=1)

    async with _mapping_session(engine) as session:
        mapping = ClickUpMappingRepository(session)
        # SPECIFIED-BY-TASKS: the helper does not re-raise.
        await _invoke(
            module,
            name,
            launch=launch,
            playbook=playbook,
            clickup=clickup,
            mapping=mapping,
            read_product=catalog,
        )

    # Premise: the attempt really did get partway before failing.
    assert clickup.calls_named("create_list"), (
        "the attempt never created a list, so this test does not exercise "
        "a partial failure at all"
    )
    assert len(clickup.tasks) == 1, (
        "the attempt did not stop after its first task, so this test does "
        f"not exercise the shape `tasks.md` 1.2 asks for: {clickup.tasks!r}"
    )

    async with _mapping_session(engine) as other:
        other_repo = ClickUpMappingRepository(other)
        # SPECIFIED: the list recorded before the failure survives it —
        # read back through an independent session, after the lock's own
        # (different) transaction has rolled back around the raised
        # failure.
        recorded_list = await other_repo.list_id_for(product_id)
        assert recorded_list is not None, (
            "the list recorded before the failure did not survive it, so a "
            "later attempt would create a second list for this launch — "
            "this is exactly the defect `design.md` warns a rebound "
            "collaborator would reintroduce"
        )
        recorded_task = await other_repo.task_for(product_id, STEP_ID)
        assert recorded_task is not None, (
            "the task association recorded before the failure did not survive it"
        )
    # SPECIFIED: the second step's task was not created — the failure
    # really did stop the launch partway, and nothing here silently
    # completed it by some other means.
    async with _mapping_session(engine) as other:
        assert (
            await ClickUpMappingRepository(other).task_for(product_id, SECOND_STEP_ID)
            is None
        )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The specific pairing "an eager call racing `clickup_sync_job`'s own
#   periodic pass". The lock it would exercise is the identical one this
#   file's own two-eager-calls test already drives against a real
#   database, and `design.md` states no different behaviour for that
#   pairing — the same reasoning
#   `test_webhook_advance_atomicity_live.py` already records for leaving
#   an analogous unstated third pairing untested.
# - Which of the two concurrent callers wins. Neither the requirement nor
#   `design.md` states an order.
# - Every eligibility rule `converge_launch` itself applies. Unaffected by
#   this change; covered by the existing driven-tier suite.
# ---------------------------------------------------------------------------
