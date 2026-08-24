"""Deriving attention items from launches, and collapsing them by cause.

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/briefing/spec.md

Covers two ADDED requirements and all nine of their scenarios:

- *Attention items are derived from every active launch* (6 scenarios)
- *Findings collapse by cause and the causal item leads* (3 scenarios)

## Why the application tier, and why real launch reports

Every scenario here is stated about what *the briefing* contains ("the
briefing SHALL contain an item ...", "exactly one at-risk item ..."), and
a `Briefing` first exists at the point of assembly -- `tasks.md` 4.3's
`assemble_daily_briefing`. That is the smallest unit that can observe any
of these outcomes (`ai-toolkit:testing`'s level rule), so the domain-level
collapse function (`tasks.md` 3.3) is exercised through it rather than
against a raw-findings shape no artifact fixes.

The launch reports fed in are built by running launch's own
`read_launches` over real `Launch` aggregates and a real `LaunchPlaybook`,
not by hand-rolling report look-alikes. Two reasons: `design.md` Decision
1 makes the report "the whole of what briefing may know", so a mismatch
between what launch publishes and what briefing consumes is precisely the
defect worth catching; and a stub report would encode this file's guess at
the report's field names a second time, independently of
`tests/unit/launch/application/test_launch_reports.py`. Nothing here
touches I/O -- both stores are fakes -- so the level does not rise.

## The interface under test does not exist yet, and its shape is INVENTED

`commerce_ops.briefing` is created by this change, so every test here is
expected to fail on an absent target (`ModuleNotFoundError`) until tasks
3.1-4.5 land. Per `ai-toolkit:testing`, that failure establishes only
absence.

Fixed by the artifacts, not invented: `assemble_daily_briefing(...,
*, audience, as_of) -> Briefing` and its export from
`briefing/application/__init__.py` (`tasks.md` 4.3, 4.5); the ports being
a launch-reports reader and a product reader answering name, SKU and
lifecycle stage (`tasks.md` 4.1); the severity grading -- at-risk
CRITICAL, awaiting-confirmation DIAGNOSE, overdue non-blocking step
MONITOR (`spec` scenarios plus `design.md` Decision 3); the cause order
(`design.md` Decision 2).

INVENTED, and recorded as unresolved project questions in
`test-manifest.md` at the change root:

- `assemble_daily_briefing`'s keyword names for its two readers
  (`_assemble` below is the single place to correct).
- `Briefing.items`, and `AttentionItem`'s `product_id`, `severity`,
  `discipline` and `evidence` attributes. `tasks.md` 3.2 names the
  concepts; nothing fixes the spellings.
- That an unresolvable product is signalled to the product reader's
  caller by `None`. `design.md` Decision 5 says the catalog "cannot
  resolve" it without saying how that is reported.
- Evidence is read as text (`_evidence_text`) so that an evidence value
  carrying a step identifier as a field and one rendering it in a string
  both satisfy "evidence naming the launch facts it summarizes". What is
  asserted is that the fact is named.

Correcting any of those is a fixture correction. What must survive
unweakened: which items each launch condition yields, at which severity,
with which evidence; that inactive launches yield none; that an
unresolvable product's launch still does; and the three collapse
outcomes.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.briefing.application import assemble_daily_briefing
from commerce_ops.launch.application import read_launches
from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Launching,
    Posture,
    Retired,
    SteadyState,
)
from commerce_ops.shared.domain.severity import Severity

pytestmark = pytest.mark.anyio

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

APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"

# DERIVED: dates chosen so a -30-day offset is already fully past on the
# evaluation date, and a step on the "healthy" launch is not yet due.
LAUNCH_DATE: Final = date(2027, 4, 15)  # -30 days => 2027-03-16
HEALTHY_LAUNCH_DATE: Final = date(2027, 8, 1)  # -30 days => 2027-07-02
AS_OF: Final = date(2027, 4, 1)
# SPECIFIED literal for "-30 days" before 2027-04-15.
OVERDUE_STEP_DUE: Final = date(2027, 3, 16)

# DERIVED: `assemble_daily_briefing` takes the audience as a parameter even
# though slice 5 only ever passes one channel (`design.md` Decision 4).
AUDIENCE: Final = "monitoring-channel"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Launch-side builders -- the shapes `test_launch_dates.py` and
# `test_graduation.py` already record for this aggregate.
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "gate": "live",
        "discipline": Discipline("listing"),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "binding": Binding.FRAMEWORK,
        "blocking": False,
        "execution": ExecutionMode.HUMAN_ATTESTED,
        "hazard": Hazard.NONE,
        "rule_policy": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver=APPROVER,
        when=APPROVED_AT,
        posture=None,
    )


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _launch(
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = LAUNCH_DATE,
    at_gate: str = "commit",
) -> Launch:
    """A launch standing at `at_gate`, walked there along the ordinary
    path (approving each confirmation gate on the way).

    `listable` is the gate used wherever a test needs a launch that is
    *not* awaiting confirmation: it is the first automatic gate, so no
    human decision is due on it.
    """
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    while launch.current_gate != at_gate:
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


class _FakeLaunchStore:
    """In-memory `LaunchStore` with the enumeration `tasks.md` 2.2 adds.

    Answers to three spellings of the enumeration because no artifact
    fixes one -- see `test_launch_reports.py`'s docstring.
    """

    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    async def all(self) -> tuple[Launch, ...]:
        return await self.list_all()

    async def list_launches(self) -> tuple[Launch, ...]:
        return await self.list_all()


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# Briefing-side test doubles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    """What the product reader answers with: name, SKU and stage.

    The three facts `tasks.md` 4.1 names for the port; shaped like the
    catalog product `test_clickup_sync_projection.py`'s own double is,
    plus the stage the activeness filter reads.
    """

    name: str
    sku: Sku
    # Annotated `Any` rather than a stage union type: no artifact fixes a
    # name for the union, and importing a guessed one would fail this file
    # for a reason unrelated to anything it asserts.
    stage: Any


class _FakeCatalog:
    """Stands in for `catalog.application.get_product_by_id`, closed over
    a per-product answer. An absent entry is reported as `None` -- the
    INVENTED reading of "the catalog cannot resolve it"."""

    def __init__(self, products: dict[ProductId, _CatalogProduct]) -> None:
        self._products = products
        self.calls: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct | None:
        self.calls.append(product_id)
        return self._products.get(product_id)


class _ScriptedLaunchReports:
    """Stands in for the launch-reports reader port, handing back reports
    produced by launch's own `read_launches`."""

    def __init__(self, reports: tuple[Any, ...]) -> None:
        self._reports = reports
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls += 1
        return self._reports


async def _reports_for(
    playbook: LaunchPlaybook, *launches: Launch, as_of: date = AS_OF
) -> tuple[Any, ...]:
    return tuple(
        await read_launches(
            _FakeLaunchStore(*launches),
            _FakePlaybooks(playbook),
            as_of=as_of,
            scope=AccessScope.unrestricted(),
        )
    )


async def _assemble(
    reports: tuple[Any, ...],
    products: dict[ProductId, _CatalogProduct],
    *,
    as_of: date = AS_OF,
) -> Any:
    """The one place to correct if `assemble_daily_briefing`'s call shape
    differs from what `tasks.md` 4.1/4.3 imply."""
    return await assemble_daily_briefing(
        read_launch_reports=_ScriptedLaunchReports(reports),
        read_product=_FakeCatalog(products),
        audience=AUDIENCE,
        as_of=as_of,
    )


# ---------------------------------------------------------------------------
# Reading a briefing
# ---------------------------------------------------------------------------


def _items(briefing: Any) -> tuple[Any, ...]:
    assert hasattr(briefing, "items"), (
        "the assembled briefing exposes no `items`, so nothing it contains "
        "can be observed"
    )
    return tuple(briefing.items)


def _items_for(briefing: Any, product_id: ProductId) -> tuple[Any, ...]:
    return tuple(item for item in _items(briefing) if item.product_id == product_id)


def _severity(item: Any) -> Severity:
    assert hasattr(item, "severity"), "an attention item carries no severity"
    severity = item.severity
    # The item is read as `Any` (its type is the interface under test), so
    # the narrowing is asserted rather than assumed: a severity that is not
    # the shared vocabulary's fails here instead of comparing unequal to
    # every tier and reading as a grading bug.
    assert isinstance(severity, Severity), (
        f"an attention item's severity is not the shared vocabulary's: {severity!r}"
    )
    return severity


def _evidence_text(item: Any) -> str:
    """Every fact an item's evidence names, as one searchable string.

    Read as text so that evidence carrying a step identifier in a field
    and evidence rendering it into a string both satisfy the requirement's
    "evidence naming the launch facts it summarizes". What each test
    asserts is that the fact *is* named -- and, where it matters, that
    another fact is not.
    """
    assert hasattr(item, "evidence"), "an attention item carries no evidence"
    entries = tuple(item.evidence)
    assert entries, (
        "an attention item carries empty evidence, which `tasks.md` 3.2 "
        "makes an invariant violation (at least one piece of evidence)"
    )
    return " | ".join(repr(entry) for entry in entries)


def _active(name: str, sku: str) -> _CatalogProduct:
    return _CatalogProduct(name=name, sku=Sku(sku), stage=Launching(phase=1))


# ---------------------------------------------------------------------------
# Requirement: Attention items are derived from every active launch
# ---------------------------------------------------------------------------


async def test_an_at_risk_launch_date_yields_a_critical_item() -> None:
    """Scenario: An at-risk launch date yields a critical item.

    WHEN the briefing is assembled and an active launch's date is at risk
    THEN the briefing SHALL contain an item for that product with severity
    critical
    AND the item's evidence SHALL name the overdue blocking steps that put
    the date at risk.

    The launch stands at `listable`, an automatic gate, so the only
    condition holding is the at-risk one -- otherwise a launch parked at
    `commit` would also yield an awaiting-confirmation item and the
    critical item could not be isolated.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: an item for that product, with severity critical.
    (item,) = _items_for(briefing, product_id)
    assert _severity(item) == Severity("critical")
    # SPECIFIED: its evidence names the overdue blocking steps.
    assert "listing.title-conforms" in _evidence_text(item)


async def test_a_gate_awaiting_confirmation_yields_a_diagnose_item() -> None:
    """Scenario: A gate awaiting confirmation yields a diagnose item.

    WHEN the briefing is assembled and an active launch's current gate
    awaits confirmation
    THEN the briefing SHALL contain an item for that product with severity
    diagnose, naming the gate awaiting approval.

    A freshly started launch stands at `commit`, a confirmation gate with
    no blocking condition attached and no approval recorded -- the
    situation `launch-instance`'s *A satisfied confirmation gate without an
    approval awaits confirmation* fixes.
    """
    playbook = _playbook()
    product_id = _new_product_id()
    reports = await _reports_for(playbook, _launch(playbook, product_id=product_id))

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: one item for that product, severity diagnose.
    (item,) = _items_for(briefing, product_id)
    assert _severity(item) == Severity("diagnose")
    # SPECIFIED: naming the gate awaiting approval.
    assert "commit" in _evidence_text(item)


async def test_an_overdue_non_blocking_step_yields_a_monitor_item() -> None:
    """Scenario: An overdue non-blocking step yields a monitor item.

    WHEN the briefing is assembled and an active launch has an overdue
    step that is not blocking and has not reached a permitted terminal
    outcome
    THEN the briefing SHALL contain an item for that product with severity
    monitor, whose evidence names the step and its due period.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=False),)
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: one item for that product, severity monitor.
    (item,) = _items_for(briefing, product_id)
    assert _severity(item) == Severity("monitor")
    # SPECIFIED: evidence names the step and its due period. The due period
    # is the single day 2027-03-16 (-30 days from 2027-04-15).
    evidence = _evidence_text(item)
    assert "listing.title-conforms" in evidence
    assert str(OVERDUE_STEP_DUE) in evidence, (
        f"the item's evidence does not name the step's due period; got {evidence}"
    )


async def test_a_healthy_launch_contributes_nothing() -> None:
    """Scenario: A healthy launch contributes nothing.

    WHEN the briefing is assembled and an active launch has no at-risk
    date, no gate awaiting confirmation, and no overdue steps
    THEN the briefing SHALL contain no item for that product.

    All three conditions are arranged away at once: the launch stands at an
    automatic gate, and its only step is not yet due on the evaluation
    date (due 2027-07-02, evaluated 2027-04-01).
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook,
        _launch(
            playbook,
            product_id=product_id,
            launch_date=HEALTHY_LAUNCH_DATE,
            at_gate="listable",
        ),
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: no item for that product.
    assert _items_for(briefing, product_id) == ()


async def test_a_graduated_products_launch_is_not_briefed() -> None:
    """Scenario: A graduated product's launch is not briefed.

    WHEN the briefing is assembled and a launch's catalog product is in a
    steady-state stage
    THEN the briefing SHALL contain no item derived from that launch,
    whatever its recorded step outcomes.

    "Whatever its recorded step outcomes" is what makes this discriminate:
    the launch used is the same at-risk one that yields a critical item in
    the first test above, so the only thing suppressing it is the stage
    stamp.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(
        reports,
        {
            product_id: _CatalogProduct(
                name="Widget A",
                sku=Sku("WIDGET-001"),
                stage=SteadyState(posture=Posture.SCALE),
            )
        },
    )

    # SPECIFIED: no item derived from that launch.
    assert _items_for(briefing, product_id) == ()


async def test_a_retired_products_launch_is_not_briefed() -> None:
    """Requirement statement: "A launch is active when its catalog
    product's lifecycle stage is neither steady-state nor retired".

    SPECIFIED by the requirement statement; no scenario of its own names
    the retired half, and an implementation filtering only on steady-state
    would pass every scenario while briefing retired products forever.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(
        reports,
        {
            product_id: _CatalogProduct(
                name="Widget A", sku=Sku("WIDGET-001"), stage=Retired()
            )
        },
    )

    assert _items_for(briefing, product_id) == ()


async def test_an_unresolvable_products_launch_is_still_derived_from() -> None:
    """Scenario: An unresolvable product's launch is still derived from.

    WHEN the briefing is assembled and a launch's product cannot be
    resolved by the catalog
    THEN that launch SHALL be treated as active and its conditions SHALL
    yield items as for any other launch.

    "As for any other launch" is asserted by comparing against the
    resolvable case directly: the same launch, the same conditions, the
    same item at the same severity -- the filter fails toward reporting,
    never toward silence.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {})

    # SPECIFIED: treated as active -- items are yielded at all.
    (item,) = _items_for(briefing, product_id)
    # SPECIFIED: its conditions yield items as for any other launch.
    assert _severity(item) == Severity("critical")
    assert "listing.title-conforms" in _evidence_text(item)


async def test_every_active_launch_is_derived_from_not_merely_the_first() -> None:
    """Requirement statement: "derive attention items from *every* active
    launch".

    SPECIFIED by the requirement statement rather than by a scenario of its
    own: each scenario above uses a single launch, which an implementation
    deriving from only the first enumerated launch would satisfy. Three
    launches, one inactive, so the assertion also confirms the filter is
    applied per launch rather than to the batch.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    first, second, graduated = (
        _new_product_id(),
        _new_product_id(),
        _new_product_id(),
    )
    reports = await _reports_for(
        playbook,
        _launch(playbook, product_id=first, at_gate="listable"),
        _launch(playbook, product_id=second, at_gate="listable"),
        _launch(playbook, product_id=graduated, at_gate="listable"),
    )

    briefing = await _assemble(
        reports,
        {
            first: _active("Widget A", "WIDGET-001"),
            second: _active("Widget B", "WIDGET-002"),
            graduated: _CatalogProduct(
                name="Widget C",
                sku=Sku("WIDGET-003"),
                stage=SteadyState(posture=Posture.SCALE),
            ),
        },
    )

    assert len(_items_for(briefing, first)) == 1
    assert len(_items_for(briefing, second)) == 1
    assert _items_for(briefing, graduated) == ()


# ---------------------------------------------------------------------------
# Requirement: Findings collapse by cause and the causal item leads
# ---------------------------------------------------------------------------


async def test_overdue_blocking_steps_are_absorbed_by_the_at_risk_item() -> None:
    """Scenario: Overdue blocking steps are absorbed by the at-risk item.

    WHEN a launch's date is at risk because two blocking steps are overdue
    THEN the briefing SHALL contain exactly one at-risk item for that
    product carrying both steps as evidence
    AND no separate item SHALL exist for either blocking step.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready",
                blocking=True,
                discipline=Discipline("inventory"),
            ),
        )
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: exactly one item for that product -- which is also "no
    # separate item exists for either blocking step", since a separate item
    # would be a second one.
    (item,) = _items_for(briefing, product_id)
    assert _severity(item) == Severity("critical")
    # SPECIFIED: carrying both steps as evidence.
    evidence = _evidence_text(item)
    assert "listing.title-conforms" in evidence
    assert "inventory.units-ready" in evidence


async def test_overdue_non_blocking_steps_in_one_discipline_collapse() -> None:
    """Scenario: Overdue non-blocking steps in one discipline collapse
    into one item.

    WHEN two non-blocking steps of the same discipline on one launch are
    overdue
    THEN the briefing SHALL contain exactly one monitor item for that
    product and discipline, with both steps as evidence.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms", discipline=Discipline("listing")
            ),
            _step(
                identifier="listing.images-uploaded", discipline=Discipline("listing")
            ),
        )
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    # SPECIFIED: exactly one monitor item for that product and discipline.
    (item,) = _items_for(briefing, product_id)
    assert _severity(item) == Severity("monitor")
    assert item.discipline == Discipline("listing"), (
        "the collapsed monitor item does not name the discipline it "
        "collapsed, so 'one item per discipline' cannot be read off it"
    )
    # SPECIFIED: with both steps as evidence.
    evidence = _evidence_text(item)
    assert "listing.title-conforms" in evidence
    assert "listing.images-uploaded" in evidence


async def test_overdue_non_blocking_steps_in_two_disciplines_do_not_collapse() -> None:
    """Requirement statement: "overdue non-blocking steps on one product
    SHALL collapse into one item *per discipline*".

    SPECIFIED by the requirement statement. The named scenario uses one
    discipline, which an implementation collapsing every overdue step on a
    product into a single item would also satisfy -- losing the
    per-discipline split the statement fixes.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms", discipline=Discipline("listing")
            ),
            _step(
                identifier="inventory.units-ready", discipline=Discipline("inventory")
            ),
        )
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    items = _items_for(briefing, product_id)
    assert len(items) == 2, (
        "expected one monitor item per discipline, got "
        f"{[(str(i.discipline), str(_severity(i))) for i in items]}"
    )
    assert {item.discipline for item in items} == {
        Discipline("listing"),
        Discipline("inventory"),
    }


async def test_the_causal_item_precedes_the_rest() -> None:
    """Scenario: The causal item precedes the rest.

    WHEN one product has both an at-risk date and an overdue non-blocking
    step
    THEN that product's at-risk item SHALL precede its monitor item in the
    briefing.

    Asserted on the product's own items in the order the briefing reports
    them: ordering *across* products is presentation and not a domain rule
    (`design.md` Decision 2), so nothing here asserts one.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready",
                blocking=False,
                discipline=Discipline("inventory"),
            ),
        )
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="listable")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    severities = [_severity(item) for item in _items_for(briefing, product_id)]
    assert Severity("critical") in severities and Severity("monitor") in severities, (
        "the arrangement did not produce both an at-risk and a monitor "
        f"item, so the ordering cannot be observed; got {severities}"
    )
    # SPECIFIED: the at-risk item precedes the monitor item.
    assert severities.index(Severity("critical")) < severities.index(
        Severity("monitor")
    )


async def test_the_awaiting_confirmation_item_ranks_between_the_other_two() -> None:
    """Requirement statement: "The launch-side cause order SHALL rank an
    at-risk launch date first, then a gate awaiting confirmation, then
    overdue non-blocking steps."

    SPECIFIED by the requirement statement. The named scenario exercises
    only the first-versus-third pair, so the middle rank is otherwise
    unconstrained -- an implementation ordering the confirmation gate last
    would pass every scenario.

    The launch stands at `commit` (a confirmation gate with no blocking
    condition attached), and carries one overdue blocking step and one
    overdue non-blocking step, so all three causes are present at once.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready",
                blocking=False,
                discipline=Discipline("inventory"),
            ),
        )
    )
    product_id = _new_product_id()
    reports = await _reports_for(
        playbook, _launch(playbook, product_id=product_id, at_gate="commit")
    )

    briefing = await _assemble(reports, {product_id: _active("Widget A", "WIDGET-001")})

    severities = [_severity(item) for item in _items_for(briefing, product_id)]
    assert severities == [
        Severity("critical"),
        Severity("diagnose"),
        Severity("monitor"),
    ], f"cause order not respected within one product's items; got {severities}"
