"""The step-to-task mapping, and the enumeration the pass runs over,
against a real Postgres.

Derived strictly from the delta spec:
`openspec/changes/add-clickup-completion-loop/specs/launch-clickup-sync/spec.md`

Covers the persistence halves of two ADDED requirements, and the
enumeration half of a third:

- *Each launch is projected into its own ClickUp list* -- "SHALL record
  the association between the launch and its list", and the enumeration
  half of scenario *A graduated launch is left alone* (`design.md` puts
  the filter in `LaunchRepository.list_active()`, so this is where "the
  pass never sees a graduated launch" is observable at all; the
  behavioural half is asserted in
  `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py`).
- *Human-attested steps are projected as tasks* -- "SHALL record the
  association between each step and its task", and the mapping
  *replacement* scenario *A deleted task for unfinished work is
  re-projected* states ("the mapping is replaced with the new task").
- *The reconciliation pass ...* -- "the system SHALL retain, per mapped
  task, the closed state it last observed", which is a persisted column
  (`tasks.md` 3.1) and therefore only observable here.

Each of those states an outcome that survives a process boundary --
"recorded", "retained" -- so the integration tier is the smallest level
that can observe them. What is *done* with the associations and the
retained state is asserted in the unit tier, against fakes.

See `openspec/changes/add-clickup-completion-loop/test-manifest.md` for the
full accounting.

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 3.1 fixes the two tables (`launch_clickup_lists`,
`launch_clickup_tasks`), their keys and the last-observed-closed column;
3.3 fixes `list_active()` on `LaunchRepository`. Nothing names a store
over the two tables. Assumed here, and recorded in the manifest as
unresolved project questions:

- `commerce_ops.launch.infrastructure.driven.clickup_mapping` exporting
  `ClickUpMappingRepository(session)`, mirroring `LaunchRepository`'s own
  shape, with the method names the unit-tier fakes also use:
  `record_list` / `list_id_for`, `record_task` / `task_for` /
  `tasks_for` / `resolve_task`, and `observe`.
- `LaunchRepository.list_active()` returning hydrated `Launch`
  aggregates.

Correcting any name or signature above is a fixture correction; what must
survive unweakened is what each test asserts: what an independent session
reads back, and which launches the enumeration does and does not include.

## Test-database lifecycle

Same convention as the rest of this directory: unique SKUs per test, no
truncate fixture, `alembic upgrade head` (including this change's two new
mapping tables) assumed applied, and a skip when `DATABASE_URL` is unset.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import LAUNCH_DATE, MARKETPLACE
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

STEP_ID: Final = "listing.title-conforms"
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _unique_sku() -> Sku:
    return Sku(f"CU-{uuid.uuid4().hex[:12].upper()}")


def _unique_clickup_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": STEP_ID, **overrides})


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates; automated with a decided rule so no other rule fires."""
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


def _start(product_id: ProductId, playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _walk_to_graduated(launch: Launch, playbook: LaunchPlaybook) -> Launch:
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=APPROVED_AT,
                        evidence="filler obligations satisfied by the walk",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=APPROVED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    return launch


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
def new_launches(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[LaunchRepository]]:
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[LaunchRepository]:
        async with maker() as session:
            yield LaunchRepository(session)

    return _open


@pytest.fixture()
def registered_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A fresh catalog product per call -- every launch record references
    one."""

    async def _register() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Bamboo Cutting Board",
            )
        return product.id

    return _register


@pytest.fixture()
def launched_product_id(
    engine: AsyncEngine, registered_product_id: Callable[[], Awaitable[ProductId]]
) -> Callable[[], Awaitable[ProductId]]:
    """A fresh product that also has a launch record.

    The mapping is per *launch* -- what it records is "the association
    between the launch and its list" -- and the two tables key to
    `launch_positions` with cascade delete, as every table
    `introduce-launch-aggregate` added does: deleting a launch must take
    its ClickUp mapping with it, and a mapping for a product that is not
    launching stands for nothing. So a product alone is not a state these
    rows can exist in, and this fixture puts one in the state they can.

    Kept separate from `registered_product_id`, which the enumeration test
    below uses: that test saves its own launches, and a fixture that had
    already saved one would collide with it.
    """

    async def _launch() -> ProductId:
        product_id = await registered_product_id()
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            await LaunchRepository(session).save(_start(product_id, _playbook()))
        return product_id

    return _launch


# ---------------------------------------------------------------------------
# Requirement: Each launch is projected into its own ClickUp list --
# "SHALL record the association between the launch and its list"
# ---------------------------------------------------------------------------


async def test_the_launch_to_list_association_survives_the_session(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """SPECIFIED: "SHALL record the association between the launch and its
    list", and "A launch whose list already exists SHALL NOT get a second
    one" -- which only holds if the association is readable back by a
    later pass, in a later process.
    """
    product_id = await launched_product_id()
    list_id = _unique_clickup_id("list")

    async with new_mapping() as mapping:
        await mapping.record_list(product_id, list_id)

    async with new_mapping() as other:
        # SPECIFIED: the association is recorded.
        assert await other.list_id_for(product_id) == list_id


async def test_a_launch_with_no_recorded_list_reports_absence(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """SPECIFIED, as the precondition scenario *A launch without a list
    gets one* rests on: a launch with no recorded list must read as having
    none, rather than erroring -- otherwise "has no recorded ClickUp list"
    is not a state the pass can observe.
    """
    product_id = await launched_product_id()

    async with new_mapping() as mapping:
        assert await mapping.list_id_for(product_id) is None


# ---------------------------------------------------------------------------
# Requirement: Human-attested steps are projected as tasks --
# "SHALL record the association between each step and its task"
# ---------------------------------------------------------------------------


async def test_the_step_to_task_association_survives_the_session(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """SPECIFIED: the association between each step and its task is
    recorded, and is resolvable from either side -- by (launch, step) for
    the projection pass, and by task identifier for webhook intake, which
    is what `tasks.md` 3.1's "unique on both sides" is for.
    """
    product_id = await launched_product_id()
    task_id = _unique_clickup_id("task")

    async with new_mapping() as mapping:
        await mapping.record_task(product_id, STEP_ID, task_id)

    async with new_mapping() as other:
        # SPECIFIED: resolvable from the step side.
        by_step = await other.task_for(product_id, STEP_ID)
        assert by_step is not None
        assert by_step.task_id == task_id
        # SPECIFIED: resolvable from the task side -- webhook intake has
        # only the task identifier to go on.
        by_task = await other.resolve_task(task_id)
        assert by_task is not None
        assert by_task.product_id == product_id
        assert by_task.step_id == STEP_ID
        # SPECIFIED (completion requirement): a newly projected task's
        # retained observed state starts as not closed.
        assert by_task.last_observed_closed is False


async def test_re_projecting_a_step_replaces_its_mapping(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A deleted task for unfinished work is re-projected --
    the persistence half of "the mapping is replaced with the new task".

    A step keeps exactly one task: after re-projection the old task
    identifier must resolve to nothing, or a late webhook delivery for the
    deleted task would still record against the step.
    """
    product_id = await launched_product_id()
    old_task = _unique_clickup_id("task-old")
    new_task = _unique_clickup_id("task-new")

    async with new_mapping() as mapping:
        await mapping.record_task(product_id, STEP_ID, old_task)
    async with new_mapping() as mapping:
        await mapping.record_task(product_id, STEP_ID, new_task)

    async with new_mapping() as other:
        # SPECIFIED: the mapping is replaced with the new task.
        current = await other.task_for(product_id, STEP_ID)
        assert current is not None
        assert current.task_id == new_task
        # SPECIFIED corollary of "unique on both sides": the step has one
        # task, not two.
        assert [entry.task_id for entry in await other.tasks_for(product_id)] == [
            new_task
        ]
        assert await other.resolve_task(old_task) is None
        # SPECIFIED: the observed state is reset with the new task -- it
        # has never been observed closed.
        assert current.last_observed_closed is False


# ---------------------------------------------------------------------------
# Requirement: The reconciliation pass ... -- "SHALL retain, per mapped
# task, the closed state it last observed"
# ---------------------------------------------------------------------------


async def test_the_retained_observed_state_survives_the_session(
    new_mapping: Callable[[], AbstractAsyncContextManager[ClickUpMappingRepository]],
    launched_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """SPECIFIED: the closed state last observed is *retained* -- it is
    what one pass leaves behind for the next to compare against, so it has
    to outlive the process that observed it. Both directions are exercised,
    because a reopening is detected by the state going back to not-closed.
    """
    product_id = await launched_product_id()
    task_id = _unique_clickup_id("task")

    async with new_mapping() as mapping:
        await mapping.record_task(product_id, STEP_ID, task_id)
    async with new_mapping() as mapping:
        await mapping.observe(product_id, STEP_ID, True)

    async with new_mapping() as other:
        observed = await other.task_for(product_id, STEP_ID)
        assert observed is not None
        assert observed.last_observed_closed is True

    async with new_mapping() as mapping:
        await mapping.observe(product_id, STEP_ID, False)

    async with new_mapping() as other:
        observed = await other.task_for(product_id, STEP_ID)
        assert observed is not None
        assert observed.last_observed_closed is False


# ---------------------------------------------------------------------------
# Requirement: Each launch is projected into its own ClickUp list --
# scenario *A graduated launch is left alone*, enumeration half
# ---------------------------------------------------------------------------


async def test_the_enumeration_the_pass_runs_over_excludes_graduated_launches(
    new_launches: Callable[[], AbstractAsyncContextManager[LaunchRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A graduated launch is left alone (enumeration half).

    WHEN the reconciliation pass runs and a launch has reached `graduated`
    THEN no list or task is created or updated for it and no outcome is
    recorded from it.

    `design.md` discharges this by never handing the pass a graduated
    launch: `list_active()` is "every launch whose current gate is short
    of `graduated`" (`tasks.md` 3.3). Two launches are persisted -- one
    active, one graduated -- so the assertion cannot pass by the
    enumeration returning nothing at all.
    """
    playbook = _playbook()
    active_id = await registered_product_id()
    graduated_id = await registered_product_id()

    async with new_launches() as launches:
        await launches.save(_start(active_id, playbook))
    async with new_launches() as launches:
        await launches.save(
            _walk_to_graduated(_start(graduated_id, playbook), playbook)
        )

    async with new_launches() as other:
        active = await other.list_active()

    enumerated = {launch.product_id for launch in active}
    # SPECIFIED: a graduated launch is never handed to the pass.
    assert graduated_id not in enumerated, (
        "list_active() enumerated a launch that has reached `graduated`; "
        "the pass would then project and reconcile it"
    )
    # Guard: the enumeration is not simply empty, which would make the
    # assertion above hold for the wrong reason.
    assert active_id in enumerated, (
        "list_active() omitted an active launch, so the exclusion above "
        "establishes nothing"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the two mapping tables carry a foreign key to the launch or
#   catalog tables, and what happens on a cascade. `tasks.md` 3.1 names
#   the columns and the uniqueness constraints; no scenario states
#   referential behaviour.
# - The Alembic migration's own up/down round-trip. `tasks.md` 7.2 makes
#   it a verification step run against a scratch database, and this
#   project has no precedent for asserting a migration from a test.
# - Whether `list_active()` hydrates full aggregates (`tasks.md` 3.3) as
#   opposed to identifiers. The scenario turns on which launches are
#   enumerated; the assertions above read `.product_id`, which either
#   shape carries.
# ---------------------------------------------------------------------------
