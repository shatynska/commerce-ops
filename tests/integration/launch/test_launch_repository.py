"""Tests for the `Launch` aggregate's repository (`launch-instance`, as
reshaped by `introduce-launch-aggregate`), against a real Postgres.

Derived from the delta spec:
openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md

Covers the persistence halves of the MODIFIED requirements:

- *A launch position is persisted for a catalog product* — all three
  scenarios' persistence outcomes (the `LaunchStarted`-occurrence half of
  the first scenario is domain behavior, covered in
  `tests/unit/launch/domain/test_launch_run.py`).
- *A product's current gate is restricted to the launch-playbook gate
  sequence* — scenario *An unrecognized gate is rejected* (the
  defaults-to-`commit` scenario is domain behavior, covered in the same
  domain file).
- *A launch position can be read back by product identifier* — both
  scenarios, including full-state rehydration (step progress with
  provenance, a gate approval).

Every scenario here states persistence outcomes ("persisted", "nothing
is persisted", "the record is returned", real FK existence against the
catalog), so the integration tier is the smallest level that can observe
them.

This is a **new** file. `test_launch_position_repository.py` in this
directory keeps running against the pre-change repository until
implementation lands; nothing here touches it. Its `update_current_gate`
tests are recorded in this change's manifest as obsolete-test candidates
(the delta REMOVES *A product's current gate can be updated*).

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 2.3 evolves the repository into the aggregate's but fixes no
names. Assumed, and recorded in the manifest as unresolved project
questions:

- `commerce_ops.launch.infrastructure.driven.launch_repository` exporting
  `LaunchRepository(session: AsyncSession)` (the name `design.md`
  Decision 7 uses) and a single `LaunchRepositoryError` for the
  rejections this delta describes — the one-exception-per-family
  precedent `test_launch_position_repository.py` records. If the
  repository instead evolves in place under its old module and names,
  correcting the import is a fixture correction.
- Methods `save(launch)` and `get_by_product_id(product_id)` (the two
  `tasks.md` 2.3 names), each async and committing its own work;
  `get_by_product_id` rehydrates a domain `Launch` or returns `None`.
- The aggregate shape (`Launch.start`, commands, `progress_for`,
  `approval_for(gate_id)`) as recorded in
  `tests/unit/launch/domain/test_launch_run.py`'s docstring; plus a
  direct `Launch(...)` construction used only by the unrecognized-gate
  test, which accepts the rejection surfacing at construction instead of
  at persistence (the delta fixes the rejection, not its layer).

Correcting any path, name, or signature above is a fixture correction
(failure state 3 in `ai-toolkit:testing`); what must survive unweakened
are the postconditions each test asserts — what was persisted, what was
not, and what a re-read through an independent session reports.

## Test-database lifecycle

Same convention as the rest of this directory: unique SKUs per test, no
truncate fixture, `alembic upgrade head` (including this change's three
new child tables) assumed applied, and a skip when `DATABASE_URL` is
unset.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    LaunchError,
    Provenance,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
    LaunchRepositoryError,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import (
    MarketplaceId,
    MetricId,
    ProductId,
    Sku,
)
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

NOT_A_GATE: Final = "not-a-real-gate"

MARKETPLACE = MarketplaceId("ATVPDKIKX0DER")

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")

# A rejection may surface at aggregate construction (domain validation)
# or at persistence — see the module docstring.
REJECTED: Final = (LaunchRepositoryError, LaunchError, ValueError)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _unique_sku() -> Sku:
    return Sku(f"LR-{uuid.uuid4().hex[:12].upper()}")


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": _any_discipline(),
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


def _playbook(
    version: str = "v1", steps: tuple[StepDefinition, ...] = ()
) -> LaunchPlaybook:
    gates = tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version=version, gates=gates, steps=(*steps, *fillers))


def _start(
    product_id: ProductId,
    playbook: LaunchPlaybook,
    *,
    launch_date: date | None = None,
) -> Launch:
    """INVENTED call shape — the single point to correct if it differs."""
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    return launch


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "ClickUp task closed with checklist complete",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def launches(engine: AsyncEngine) -> AsyncIterator[LaunchRepository]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield LaunchRepository(session)


@pytest.fixture()
def new_launches(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[LaunchRepository]]:
    """An independent session/repository factory, so reads prove the
    write reached Postgres rather than a session identity map."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[LaunchRepository]:
        async with maker() as session:
            yield LaunchRepository(session)

    return _open


@pytest.fixture()
def registered_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A factory registering a fresh catalog product and returning its
    identifier — every launch record needs an existing catalog product to
    reference."""

    async def _register() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Launch Aggregate Test Widget",
            )
        return product.id

    return _register


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A launch position is persisted for a catalog
# product
# ---------------------------------------------------------------------------


async def test_a_started_launch_is_persisted_for_an_existing_product(
    launches: LaunchRepository,
    new_launches: Callable[[], AbstractAsyncContextManager[LaunchRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A launch position is created for an existing product
    (persistence half; the `LaunchStarted`-occurrence half is domain
    behavior, covered in `test_launch_run.py`).

    WHEN a launch is started for a registered catalog product against a
    playbook version, with no launch date
    THEN the record is persisted referencing that product with that
    version pinned, the launch date is reported as absent ...
    """
    product_id = await registered_product_id()
    playbook = _playbook(version="v1")

    await launches.save(_start(product_id, playbook))

    async with new_launches() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    # SPECIFIED: persisted referencing that product with that version
    # pinned.
    assert reread.product_id == product_id
    assert reread.playbook_version == "v1"
    # SPECIFIED: the launch date is reported as absent.
    assert reread.launch_date is None


async def test_a_launch_for_an_unknown_product_is_rejected(
    launches: LaunchRepository,
) -> None:
    """Scenario: A launch position for an unknown product is rejected.

    WHEN a launch is started for a product identifier no catalog product
    has
    THEN the start is rejected and nothing is persisted.
    """
    # ProductId is opaque (generated, never parsed), so a fresh value no
    # registration produced is a valid unknown identifier.
    unknown_id = ProductId(str(uuid.uuid4()))
    playbook = _playbook(version="v1")

    with pytest.raises(LaunchRepositoryError):
        await launches.save(_start(unknown_id, playbook))

    # SPECIFIED: nothing is persisted.
    assert await launches.get_by_product_id(unknown_id) is None


async def test_a_second_launch_for_the_same_product_is_rejected(
    launches: LaunchRepository,
    new_launches: Callable[[], AbstractAsyncContextManager[LaunchRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A second launch position for the same product is
    rejected.

    WHEN a launch is started for a product that already has a launch
    record
    THEN the start is rejected and the existing record is unchanged.

    The second start pins a different playbook version, so "unchanged" is
    observable as the first version surviving the rejected second start.
    """
    product_id = await registered_product_id()
    await launches.save(_start(product_id, _playbook(version="v1")))

    with pytest.raises(LaunchRepositoryError):
        await launches.save(_start(product_id, _playbook(version="v2")))

    # SPECIFIED: the existing record is unchanged.
    async with new_launches() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    assert reread.playbook_version == "v1"


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A product's current gate is restricted to the
# launch-playbook gate sequence
# ---------------------------------------------------------------------------


async def test_persisting_an_unrecognized_gate_is_rejected(
    launches: LaunchRepository,
    new_launches: Callable[[], AbstractAsyncContextManager[LaunchRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: An unrecognized gate is rejected.

    WHEN an attempt is made to persist a launch record whose current gate
    is not one of the eight `launch-playbook` gate ids
    THEN the operation is rejected and the stored gate is unchanged.

    The aggregate's own commands cannot reach a gate outside the eight,
    so the attempt constructs a `Launch` directly (the rehydration path's
    constructor). The rejection may surface at that construction or at
    `save` — the delta fixes the rejection, not its layer — and either
    way the stored gate must be unchanged.
    """
    product_id = await registered_product_id()
    playbook = _playbook(version="v1")
    await launches.save(_start(product_id, playbook))

    with pytest.raises(REJECTED):
        rogue = Launch(
            product_id=product_id,
            playbook_version="v1",
            current_gate=NOT_A_GATE,
            launch_date=None,
        )
        await launches.save(rogue)

    # SPECIFIED: the stored gate is unchanged.
    async with new_launches() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    assert reread.current_gate == "commit"


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A launch position can be read back by product
# identifier
# ---------------------------------------------------------------------------


async def test_a_launch_is_retrieved_with_its_full_recorded_state(
    launches: LaunchRepository,
    new_launches: Callable[[], AbstractAsyncContextManager[LaunchRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A launch position is retrieved.

    WHEN a launch that has recorded step outcomes and a gate approval is
    read using its product identifier
    THEN the record is returned with the pinned version, current gate,
    launch date, each step's outcome and provenance, and each approval it
    was persisted with.
    """
    product_id = await registered_product_id()
    playbook = _playbook(
        version="v1",
        steps=(
            _step(identifier="listing.title-conforms", gate="listable"),
            _step(identifier="inventory.stock-checked-in", gate="stock-ready"),
        ),
    )
    launch = _start(product_id, playbook, launch_date=date(2027, 6, 1))
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(source="clickup", who="Helen"),
    )
    launch.record_step_outcome(
        playbook,
        step_id="inventory.stock-checked-in",
        outcome=Blocked("supplier shipment delayed at customs"),
        provenance=_provenance(source="automated", who="system", evidence="3PL feed"),
    )
    launch.approve_gate(
        "commit",
        GateApproval(
            decision=ApprovalDecision.APPROVING,
            approver="Helen",
            when=APPROVED_AT,
            posture=None,
        ),
    )
    await launches.save(launch)

    async with new_launches() as other:
        reread = await other.get_by_product_id(product_id)

    assert reread is not None
    # SPECIFIED: the pinned version, current gate, launch date.
    assert reread.product_id == product_id
    assert reread.playbook_version == "v1"
    assert reread.current_gate == "commit"
    assert reread.launch_date == date(2027, 6, 1)

    # SPECIFIED: each step's outcome and provenance.
    satisfied = reread.progress_for("listing.title-conforms")
    assert satisfied is not None
    assert satisfied.outcome is Satisfied
    assert satisfied.provenance.source == "clickup"
    assert satisfied.provenance.who == "Helen"
    assert satisfied.provenance.when == RECORDED_AT
    assert satisfied.provenance.evidence == (
        "ClickUp task closed with checklist complete"
    )
    blocked = reread.progress_for("inventory.stock-checked-in")
    assert blocked is not None
    assert blocked.outcome == Blocked("supplier shipment delayed at customs")
    assert blocked.provenance.source == "automated"
    assert blocked.provenance.who == "system"
    assert blocked.provenance.evidence == "3PL feed"

    # SPECIFIED: each approval. DERIVED read surface: `approval_for`.
    approval = reread.approval_for("commit")
    assert approval is not None
    assert approval.decision is ApprovalDecision.APPROVING
    assert approval.approver == "Helen"
    assert approval.when == APPROVED_AT


async def test_a_product_without_a_launch_reports_absence(
    launches: LaunchRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A product without a launch position reports absence.

    WHEN a launch record is read for a product identifier that has none
    THEN the system reports that none exists, rather than an error.

    The product is a real, registered catalog product, so the absence is
    of the launch record specifically, not of the product.
    """
    product_id = await registered_product_id()

    result = await launches.get_by_product_id(product_id)

    # SPECIFIED: absence (`None`), not an error.
    assert result is None
