"""Replacing a launch's list and discarding its task mappings, as one
commit, against a real Postgres.

Derived strictly from the delta spec of the OpenSpec change
`heal-a-launchs-deleted-list`:
`openspec/changes/heal-a-launchs-deleted-list/specs/launch-clickup-sync/spec.md`

Covers, from the MODIFIED requirement *Each launch is projected into its
own ClickUp list*, the halves of two scenarios that only a database can
observe:

- *The replacement and the discard cannot come apart* — "as one
  indivisible act: either the launch is left recorded against its old list
  with its mappings intact, or it is recorded against the new list with
  the discard applied". Indivisibility across two tables is a transaction
  property; no in-memory double can establish it, so this is the smallest
  level that can. The *caller's* half — that the pass performs one act
  rather than ordering two — is asserted at the unit level in
  `tests/unit/launch/infrastructure/driven/test_clickup_sync_list_healing.py`.
- *A launch whose list was deleted gets a new one* — that the replacement
  association and the discard are both **recorded**, i.e. readable back by
  a later pass in a later process, and that the exempt mapping is what
  survives.

This file is additive. It touches, duplicates and supersedes nothing in
`tests/integration/launch/test_launch_clickup_mapping.py`, which covers
the store's pre-existing operations and is not modified here. See
`openspec/changes/heal-a-launchs-deleted-list/test-manifest.md` for the
full accounting.

## What decides the exemption is **not** tested here

`design.md` — Decision 2b is explicit that the store must not judge
terminality: "The store cannot decide this, and the task list must not
offer it as an option ... The caller evaluates terminality and hands the
store the mappings to spare." So these tests hand the store a spared set
directly and assert it is honoured. *Which* mappings belong in that set —
authored-set range, hazard-independent judgement — is the caller's
behaviour and is asserted at the unit level.

## INVENTED shapes

`tasks.md` 2.1 fixes that this is **one** operation on
`ClickUpMappingRepository` committing once; 2.2 fixes that the caller
hands it the mappings to spare. Nothing names the operation or its
parameters. `_replace_operation()` resolves the first of several plausible
spellings the store actually offers, and `_call_replace()` binds the three
arguments by inspecting the real signature, so a differing parameter
spelling is absorbed rather than being a false failure. Both are the
single correction point; teaching them the real names is a fixture
correction (`ai-toolkit:testing` failure state 3), never a reason to
weaken what these tests assert.

## The commit seam, and its one fragility

Both tests substitute `AsyncSession.commit` on the session they hand the
store — the same construction seam
`test_launch_clickup_mapping.py` already uses (`ClickUpMappingRepository(session)`).
A store that committed through `session.begin()` instead would bypass that
substitution, so **each test guards for it**: the counter must have been
reached before any conclusion is drawn from it, and the guard's message
says so. That way a differing commit style surfaces as a fixture
correction rather than as a misleading claim that the store is not atomic.

## Test-database lifecycle

Same convention as the rest of this directory: unique SKUs per test, no
truncate fixture, `alembic upgrade head` assumed applied, and a skip when
`DATABASE_URL` is unset.

## Expected first-run state

`ClickUpMappingRepository` has no combined replace-and-discard; `tasks.md`
2.1 adds it. Both tests are expected to fail on an absent target — the
resolver fails naming the spellings it looked for. Per `ai-toolkit:testing`
that establishes only absence.

Baseline recorded before these tests were written, at the worktree root:
`uv run pytest tests/unit tests/agents` — 1130 passed, 0 failed;
`uv run pytest tests/integration` — 3 passed, 94 skipped. **No database is
configured here**, so this tier's database-backed tests — these two
included — were not executed at all. Their first real run belongs to
whoever implements the change, against a migrated database.
"""

from __future__ import annotations

import contextlib
import inspect
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
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
    Gate,
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
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import LAUNCH_DATE, MARKETPLACE
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

#: An unfinished step's mapping: discarded with the dead list.
OPEN_STEP_ID: Final = "listing.title-conforms"
#: A second one, so the discard is asserted over more than a single row.
OTHER_OPEN_STEP_ID: Final = "listing.images-approved"
#: A mapping the caller names as exempt: it stands.
SPARED_STEP_ID: Final = "finance.unit-economics"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# The single correction point: how the new store operation is reached
# ---------------------------------------------------------------------------

#: Plausible spellings, in preference order. INVENTED -- no artifact names
#: the operation.
_CANDIDATE_NAMES: Final = (
    "replace_list",
    "replace_list_discarding_tasks",
    "replace_list_and_discard_tasks",
    "record_list_discarding_tasks",
    "record_replacement_list",
    "replace_launch_list",
)

#: Parameter-name fragments naming the set of mappings to *spare*.
_SPARE_WORDS: Final = ("keep", "spare", "exempt", "retain", "preserve", "except")


def _replace_operation(store: ClickUpMappingRepository) -> Any:
    """The store's combined replace-and-discard, however it is named."""
    for name in _CANDIDATE_NAMES:
        operation = getattr(store, name, None)
        if operation is not None:
            return operation
    pytest.fail(
        "`ClickUpMappingRepository` offers no operation that records a "
        "replacement list and discards the launch's task mappings together. "
        "`tasks.md` 2.1 adds one; none of the spellings this test looked for "
        f"is present: {_CANDIDATE_NAMES}. If it exists under another name, "
        "add it to `_CANDIDATE_NAMES` -- a fixture correction, not a change "
        "to what these tests assert."
    )


async def _call_replace(
    store: ClickUpMappingRepository,
    *,
    product_id: ProductId,
    list_id: str,
    spare: tuple[str, ...],
) -> None:
    """Invoke it, binding the three arguments to whatever it calls them.

    `tasks.md` 2.1-2.2 fix the three facts the operation needs -- which
    launch, which new list, which mappings to spare -- and fix none of the
    names. Binding by inspection keeps a differing spelling from reading as
    a failure of the behaviour.
    """
    operation = _replace_operation(store)
    parameters = inspect.signature(operation).parameters

    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for name, parameter in parameters.items():
        if parameter.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        lowered = name.lower()
        if "product" in lowered or "launch" in lowered:
            value: Any = product_id
        elif "list" in lowered:
            value = list_id
        elif any(word in lowered for word in _SPARE_WORDS):
            value = spare
        elif parameter.default is not inspect.Parameter.empty:
            continue
        else:
            pytest.fail(
                f"the store's replace-and-discard takes a required parameter "
                f"{name!r} this test cannot supply. It is expected to need "
                "only the launch, the new list identifier, and the mappings "
                "to spare (`tasks.md` 2.1-2.2). Teaching `_call_replace` the "
                "real signature is a fixture correction."
            )
        if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[name] = value

    await operation(*positional, **keywords)


class _CommitRefused(RuntimeError):
    """A commit that does not complete, as a database refusing the write
    would present it."""


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_launch_clickup_mapping.py`
# ---------------------------------------------------------------------------


def _unique_sku() -> Sku:
    return Sku(f"CU-{uuid.uuid4().hex[:12].upper()}")


def _unique_clickup_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": OPEN_STEP_ID,
        "name": "Work this step asks for",
        "description": None,
        "gate": "listable",
        "discipline": Discipline.LISTING,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking automated filler holding `gate`, for the gate-holding
    floor."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler=f"hold.{gate.replace('-', '_')}",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (
        _step(identifier=OPEN_STEP_ID),
        _step(identifier=OTHER_OPEN_STEP_ID),
        _step(identifier=SPARED_STEP_ID, gate="commit", discipline=Discipline.FINANCE),
    )
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(*steps, *fillers))


def _start(product_id: ProductId, playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Session fixtures -- transcribed from `test_launch_clickup_mapping.py`
# ---------------------------------------------------------------------------


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
    """An independent session/store factory, so a read proves the write
    reached Postgres rather than a session identity map."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[ClickUpMappingRepository]:
        async with maker() as session:
            yield ClickUpMappingRepository(session)

    return _open


@pytest.fixture()
def new_session(engine: AsyncEngine) -> Callable[[], AbstractAsyncContextManager[Any]]:
    """A session handed out raw, so a test can substitute its `commit`
    before building a store on it."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    return _open


@pytest.fixture()
def launched_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product that also has a launch record -- the two
    mapping tables key to `launch_positions` with cascade delete, so a
    product alone is not a state their rows can exist in."""

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
            await LaunchRepository(session).save(_start(product.id, _playbook()))
        return product.id

    return _launch


async def _seed_dead_list(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    product_id: ProductId,
) -> tuple[str, dict[str, str]]:
    """The launch recorded against a list, holding three task mappings.

    Returns the dead list's identifier and the step-to-task map, both
    committed before anything under test runs.
    """
    dead_list = _unique_clickup_id("list-dead")
    tasks = {
        OPEN_STEP_ID: _unique_clickup_id("task-open"),
        OTHER_OPEN_STEP_ID: _unique_clickup_id("task-other"),
        SPARED_STEP_ID: _unique_clickup_id("task-done"),
    }
    async with new_mapping() as mapping:
        await mapping.record_list(product_id, dead_list)
    for step_id, task_id in tasks.items():
        async with new_mapping() as mapping:
            await mapping.record_task(product_id, step_id, task_id)
    # The spared mapping carries an observed state, so the exemption is
    # asserted to leave the *row* alone and not merely to re-create it:
    # "task identifiers, retained compositions, retained observed states"
    # are what the discard takes with it.
    async with new_mapping() as mapping:
        await mapping.observe(product_id, SPARED_STEP_ID, True)
    return dead_list, tasks


# ---------------------------------------------------------------------------
# Scenario: The replacement and the discard cannot come apart --
# the "recorded against the new list with the discard applied" side
# ---------------------------------------------------------------------------


async def test_the_replacement_and_the_discard_land_in_one_commit(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    new_session: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED: the launch "is recorded against the new list with the
    discard applied" -- both, together, as one indivisible act.

    Two things are asserted, and they are different claims. That both
    effects are *readable back through an independent session* is what
    makes them recorded rather than merely done. That the store issued
    exactly **one** commit is what makes them indivisible: `design.md` —
    Decision 3 records that two commits leave a window in which a crash
    strands the record in the half-state the requirement forbids, and
    `tasks.md` 2.1 says outright "Do not build it as two calls".
    """
    product_id = await launched_product_id()
    dead_list, tasks = await _seed_dead_list(new_mapping, product_id)
    replacement = _unique_clickup_id("list-new")

    commits: list[None] = []
    async with new_session() as session:
        real_commit = session.commit

        async def counting_commit() -> None:
            commits.append(None)
            await real_commit()

        monkeypatch.setattr(session, "commit", counting_commit)
        await _call_replace(
            ClickUpMappingRepository(session),
            product_id=product_id,
            list_id=replacement,
            spare=(SPARED_STEP_ID,),
        )

    # SPECIFIED: one act, one commit. A store that ordered `record_list`
    # and a discard would count two.
    assert len(commits) == 1, (
        f"the replacement and the discard were committed {len(commits)} "
        "time(s); `tasks.md` 2.1 requires a single commit. If the store "
        "commits through `session.begin()` rather than `session.commit()`, "
        "this counter never fires and the right response is to move the "
        "substitution -- a fixture correction, not a weaker assertion."
    )

    async with new_mapping() as other:
        # SPECIFIED: the launch is recorded against the new list.
        assert await other.list_id_for(product_id) == replacement
        # SPECIFIED: the discard is applied -- to everything but the
        # mapping the caller named as exempt.
        remaining = {
            entry.step_id: entry for entry in await other.tasks_for(product_id)
        }
        assert set(remaining) == {SPARED_STEP_ID}, (
            f"the discard left {sorted(remaining)}; only the spared step's "
            "mapping was to stand"
        )
        # SPECIFIED: the spared mapping *stands* -- the row itself, with the
        # task it named and the observed state it retained. Re-creating it
        # would reset the observed state and is not what "stands" means.
        spared = remaining[SPARED_STEP_ID]
        assert spared.task_id == tasks[SPARED_STEP_ID]
        assert spared.last_observed_closed is True
        # SPECIFIED corollary: the discarded mappings resolve to nothing, so
        # a late webhook for one of those dead tasks records against no step.
        for step_id in (OPEN_STEP_ID, OTHER_OPEN_STEP_ID):
            assert await other.task_for(product_id, step_id) is None
            assert await other.resolve_task(tasks[step_id]) is None
        # And the dead list is not still recorded anywhere for this launch.
        assert await other.list_id_for(product_id) != dead_list


# ---------------------------------------------------------------------------
# Scenario: The replacement and the discard cannot come apart --
# the "left recorded against its old list with its mappings intact" side
# ---------------------------------------------------------------------------


async def test_a_replacement_that_does_not_commit_leaves_the_old_list_and_mappings(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    new_session: Callable[[], AbstractAsyncContextManager[Any]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The replacement and the discard cannot come apart.

    WHEN the reconciliation pass replaces a launch's deleted list and the
    write of that replacement does not complete
    THEN the launch is left recorded against its old list with its task
    mappings intact.

    The commit is refused, standing in for a transaction that does not
    complete. What must not be observable afterwards is *either* half on
    its own: not the new list association without the discard, and not the
    discard without the new list. Both are read back through an
    independent session, which is the only place the distinction between
    "written" and "committed" exists at all.
    """
    product_id = await launched_product_id()
    dead_list, tasks = await _seed_dead_list(new_mapping, product_id)
    replacement = _unique_clickup_id("list-new")

    attempted: list[None] = []
    async with new_session() as session:

        async def refusing_commit() -> None:
            attempted.append(None)
            raise _CommitRefused("the replace-and-discard transaction did not commit")

        monkeypatch.setattr(session, "commit", refusing_commit)
        with contextlib.suppress(Exception):
            await _call_replace(
                ClickUpMappingRepository(session),
                product_id=product_id,
                list_id=replacement,
                spare=(SPARED_STEP_ID,),
            )

    # Guard against a vacuous pass: the refusal must actually have been
    # reached, or the assertions below hold for the wrong reason.
    assert attempted, (
        "the store never committed through the substituted `session.commit`, "
        "so this test observed nothing about what an incomplete write leaves "
        "behind. If the store commits through `session.begin()`, move the "
        "substitution -- a fixture correction."
    )

    async with new_mapping() as other:
        # SPECIFIED: the launch is left recorded against its old list.
        assert await other.list_id_for(product_id) == dead_list
        # SPECIFIED: with its task mappings intact -- all three, each still
        # naming the task it named, with its retained observed state.
        remaining = {
            entry.step_id: entry for entry in await other.tasks_for(product_id)
        }
        assert set(remaining) == set(tasks), (
            f"an incomplete replacement left {sorted(remaining)} of "
            f"{sorted(tasks)}; the discard applied without the replacement "
            "is exactly the half-state the requirement forbids"
        )
        for step_id, task_id in tasks.items():
            assert remaining[step_id].task_id == task_id
        assert remaining[SPARED_STEP_ID].last_observed_closed is True


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - **Which mappings belong in the spared set.** `design.md` — Decision 2b
#   puts that judgement in the caller and forbids the store from making it
#   ("giving it one would drag the domain vocabulary across a boundary the
#   module's layering exists to keep"). Asserted at the unit level instead.
# - **A concurrent pass replacing the same launch's list.** No scenario
#   states an isolation level or a concurrency guarantee, and `design.md`
#   frames the pass as convergent rather than serialized.
# - **The orphan list a crash between `create_list` and this commit
#   leaves.** `design.md` — Risks accepts it explicitly, and the
#   requirement says the same: "a replacement list created in ClickUp
#   before the record is written may be left with nothing naming it, and
#   reclaiming such a list is not undertaken here." There is no behaviour
#   to assert.
# - **Whether the discard uses one statement or several inside the one
#   transaction.** The requirement states indivisibility, not a statement
#   count; the commit count is what makes indivisibility observable.
# ---------------------------------------------------------------------------
