"""Enumerating launch positions, and what a launch report carries.

Derived from the delta spec:
openspec/changes/introduce-launch-briefing/specs/launch-instance/spec.md

Covers all three ADDED requirements and all eight of their scenarios:

- *Launch positions are enumerable with their reports* (2 scenarios)
- *The launch report carries each step's discipline and names the steps
  behind an at-risk date* (2 scenarios)
- *The launch report states whether the current gate awaits confirmation*
  (4 scenarios)

## Why every scenario is observed here rather than at the domain level

Each of the three requirements is stated about *the launch report* -- what
is enumerated, what a report entry carries, what the report states. The
report is produced by the application layer (`read_launches`), so the
application unit tier is the smallest level that can observe any of them
(`ai-toolkit:testing`'s level rule). The collaborators are fakes, per this
project's fast mocked unit tier; no session and no Postgres.

The `awaiting_confirmation` scenarios are deliberately *not* asserted
against `Launch.awaiting_confirmation(playbook)` (`tasks.md` 2.1) even
though that is where the rule is computed: the requirement says "the
launch report SHALL state", and a domain method that is correct but never
reaches the report satisfies no scenario here.

## The interface under test does not exist yet, and its shape is INVENTED

`read_launches` and the report's new fields are introduced by this change,
so every test here is expected to fail on an absent target
(`ImportError`, then `AttributeError` once the export lands) until tasks
2.1-2.5 land. Per `ai-toolkit:testing`, that failure establishes only
absence -- it says nothing about whether the assertions below are any
good.

Fixed by the artifacts, not invented: `read_launches(launches, playbooks,
*, as_of) -> tuple[LaunchReport, ...]` and its export from
`launch/application/__init__.py` (`tasks.md` 2.4, 2.5); the
`awaiting_confirmation: bool` field on `LaunchReport` and each step
entry's owning `Discipline` (`tasks.md` 2.3); `LaunchDateAtRisk`'s
`overdue_steps` (`design.md` Decision 1).

INVENTED, and recorded as unresolved project questions in
`test-manifest.md` at the change root:

- The `LaunchStore`'s enumeration method name. `tasks.md` 2.2 fixes that
  the protocol grows one, not what it is called. `_FakeLaunchStore` below
  answers to three plausible spellings so that a mismatch is a one-line
  fixture correction rather than a rewrite.
- The report's own attribute spellings: `product_id`, `steps`, and
  `at_risk`. `design.md` fixes the report's *content* ("steps with due
  periods and progress, plus the at-risk evaluation"), not its field
  names.
- Each step entry's attribute spellings: `identifier`, `discipline`,
  `due_period`, `outcome`. `_entry_for` and `_ATTRIBUTE_ALIASES` below are
  the single place to correct.

Correcting any of those is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: that every persisted position is reported, that an empty store is
not an error, which discipline each entry carries, which steps the at-risk
evaluation names, and in which four situations the report does or does not
say the gate awaits confirmation.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import read_launches
from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

pytestmark = pytest.mark.anyio

# SPECIFIED (launch-playbook spec, unchanged): the eight gates, in order.
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

# SPECIFIED (launch-instance spec, unchanged): the four confirmation gates.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
APPROVER: Final = "Helen"

# DERIVED: no artifact fixes a launch date. Chosen, with `AS_OF`, so that a
# -30-day offset is already fully past on the evaluation date for the
# at-risk launches and comfortably in the future for the healthy one --
# the same construction `test_launch_dates.py` uses.
AT_RISK_LAUNCH_DATE: Final = date(2027, 4, 15)  # -30 days => 2027-03-16
HEALTHY_LAUNCH_DATE: Final = date(2027, 8, 1)  # -30 days => 2027-07-02
AS_OF: Final = date(2027, 4, 1)

# SPECIFIED literal for "-30 days" from 2027-04-15, written out rather than
# recomputed with `timedelta` so the test does not reuse the arithmetic it
# checks (the convention `test_timing_anchor.py` records).
AT_RISK_STEP_DUE: Final = date(2027, 3, 16)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here: no trio
    # dependency is installed.
    return "asyncio"


# ---------------------------------------------------------------------------
# Builders -- the shapes `test_launch_dates.py` and `test_graduation.py`
# already record for this aggregate.
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


def _provenance() -> Provenance:
    return Provenance(
        source="attestation",
        who=APPROVER,
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _start(
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = None,
) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=launch_date
    )
    return launch


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    """Walk a launch to `gate` along the ordinary path, approving each
    confirmation gate on the way (the walk `test_graduation.py` records)."""
    while launch.current_gate != gate:
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


class _FakeLaunchStore:
    """In-memory `LaunchStore`, including the enumeration `tasks.md` 2.2
    adds.

    The enumeration answers to three spellings because no artifact fixes
    one (see the module docstring). This is fixture-level accommodation of
    an unfixed name, not a weakened assertion: every assertion is made on
    what `read_launches` returns.
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
    """Playbook port returning the one version every launch here pinned."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# Reading a report -- the single correction point for the report's own
# attribute spellings.
# ---------------------------------------------------------------------------

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    "product_id": ("product_id",),
    "steps": ("steps", "step_statuses"),
    "at_risk": ("at_risk", "date_at_risk", "launch_date_at_risk"),
    "identifier": ("identifier", "step_id"),
    "discipline": ("discipline",),
    "due_period": ("due_period", "due"),
    "outcome": ("outcome", "recorded_outcome", "progress"),
}


def _read(subject: object, field: str) -> Any:
    """Read `field` off a report or step entry, trying the spellings no
    artifact fixes.

    Fails the test loudly when none is present, rather than returning a
    default that would leave an assertion vacuously true.
    """
    for name in _ATTRIBUTE_ALIASES[field]:
        if hasattr(subject, name):
            return getattr(subject, name)
    pytest.fail(
        f"{type(subject).__name__} exposes none of "
        f"{_ATTRIBUTE_ALIASES[field]} for '{field}'; the launch report must "
        "carry it (see the module docstring's INVENTED shapes)"
    )


def _reports_by_product(reports: Any) -> dict[ProductId, Any]:
    return {_read(report, "product_id"): report for report in reports}


def _entry_for(report: Any, step_id: str) -> Any:
    entries = [
        entry
        for entry in _read(report, "steps")
        if str(_read(entry, "identifier")) == step_id
    ]
    assert len(entries) == 1, (
        f"expected exactly one report entry for step {step_id!r}, got {len(entries)}"
    )
    return entries[0]


def _awaiting_confirmation(report: Any) -> bool:
    """`awaiting_confirmation` is fixed by `tasks.md` 2.3, so this reads it
    by name and fails loudly rather than accommodating alternatives."""
    assert hasattr(report, "awaiting_confirmation"), (
        "the launch report carries no `awaiting_confirmation` field, so it "
        "cannot state whether the current gate awaits confirmation"
    )
    return bool(report.awaiting_confirmation)


# ---------------------------------------------------------------------------
# Requirement: Launch positions are enumerable with their reports
# ---------------------------------------------------------------------------


async def test_all_launch_positions_are_reported() -> None:
    """Scenario: All launch positions are reported.

    WHEN several launch positions exist and the launches are enumerated as
    of a date
    THEN every persisted launch position SHALL be reported, each with its
    steps' due periods, recorded progress, and at-risk evaluation as of
    that date.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready", discipline=Discipline("inventory")
            ),
        )
    )
    at_risk_id, healthy_id, resolved_id = (
        _new_product_id(),
        _new_product_id(),
        _new_product_id(),
    )
    at_risk = _start(playbook, product_id=at_risk_id, launch_date=AT_RISK_LAUNCH_DATE)
    healthy = _start(playbook, product_id=healthy_id, launch_date=HEALTHY_LAUNCH_DATE)
    resolved = _start(playbook, product_id=resolved_id, launch_date=AT_RISK_LAUNCH_DATE)
    resolved.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(),
    )

    reports = await read_launches(
        _FakeLaunchStore(at_risk, healthy, resolved),
        _FakePlaybooks(playbook),
        as_of=AS_OF,
    )

    by_product = _reports_by_product(reports)
    # SPECIFIED: every persisted launch position is reported -- all three,
    # and no more (a report for a position that is not persisted would be
    # invented).
    assert set(by_product) == {at_risk_id, healthy_id, resolved_id}
    assert len(tuple(reports)) == 3

    # SPECIFIED: each with its steps' due periods. The -30-day offset from
    # 2027-04-15 is the single day 2027-03-16.
    due = _read(
        _entry_for(by_product[at_risk_id], "listing.title-conforms"), "due_period"
    )
    assert due is not None
    assert due.start == AT_RISK_STEP_DUE
    assert due.end == AT_RISK_STEP_DUE

    # SPECIFIED: each with its recorded progress -- the outcome recorded on
    # one launch is visible on that launch's report and absent from the
    # others', so the report carries per-launch progress rather than a
    # playbook-shaped blank.
    recorded = _read(
        _entry_for(by_product[resolved_id], "listing.title-conforms"), "outcome"
    )
    untouched = _read(
        _entry_for(by_product[at_risk_id], "listing.title-conforms"), "outcome"
    )
    assert recorded is not None
    assert recorded != untouched

    # SPECIFIED: each with its at-risk evaluation *as of that date* -- the
    # launch whose blocking step is overdue on 2027-04-01 is at risk, the
    # one whose step is not yet due is not, and the one whose overdue step
    # is satisfied is not.
    assert _read(by_product[at_risk_id], "at_risk")
    assert not _read(by_product[healthy_id], "at_risk")
    assert not _read(by_product[resolved_id], "at_risk")


async def test_no_launches_yields_an_empty_enumeration() -> None:
    """Scenario: No launches yields an empty enumeration.

    WHEN no launch position exists and the launches are enumerated
    THEN the system SHALL report an empty result, not an error.
    """
    playbook = _playbook()

    reports = await read_launches(
        _FakeLaunchStore(), _FakePlaybooks(playbook), as_of=AS_OF
    )

    # SPECIFIED: an empty result, not an error -- reaching this assertion
    # at all is half of what the scenario states.
    assert tuple(reports) == ()


async def test_enumeration_does_not_filter_by_lifecycle() -> None:
    """Requirement statement: "Enumeration SHALL NOT filter by lifecycle
    ... whoever consumes the enumeration filters by the catalog's stage
    stamp."

    SPECIFIED. A launch standing at the final gate with its graduation
    approval recorded is exactly the position `design.md` Decision 1 says
    the persisted shape cannot distinguish from a graduated one; it is
    still reported. Without this, an implementation that quietly dropped
    end-of-line launches would pass both scenarios above.
    """
    playbook = _playbook()
    product_id = _new_product_id()
    launch = _advance_to(
        _start(playbook, product_id=product_id, launch_date=AT_RISK_LAUNCH_DATE),
        playbook,
        "graduated",
    )

    reports = await read_launches(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), as_of=AS_OF
    )

    assert set(_reports_by_product(reports)) == {product_id}


# ---------------------------------------------------------------------------
# Requirement: The launch report carries each step's discipline and names
# the steps behind an at-risk date
# ---------------------------------------------------------------------------


async def test_a_step_entry_carries_its_owning_discipline() -> None:
    """Scenario: A step entry carries its owning discipline.

    WHEN a launch is read back or enumerated
    THEN every step entry in the report SHALL carry the discipline the
    playbook assigns to that step.

    Two steps with *different* disciplines, because a single-discipline
    playbook cannot tell "carries the assigned discipline" apart from
    "carries some constant discipline".
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

    reports = await read_launches(
        _FakeLaunchStore(
            _start(playbook, product_id=product_id, launch_date=AT_RISK_LAUNCH_DATE)
        ),
        _FakePlaybooks(playbook),
        as_of=AS_OF,
    )

    (report,) = tuple(reports)
    entries = _read(report, "steps")
    # SPECIFIED: *every* step entry carries one, not merely the first.
    assert len(tuple(entries)) == 2
    assert _read(_entry_for(report, "listing.title-conforms"), "discipline") == (
        Discipline("listing")
    )
    assert _read(_entry_for(report, "inventory.units-ready"), "discipline") == (
        Discipline("inventory")
    )


async def test_the_at_risk_evaluation_names_its_overdue_blocking_steps() -> None:
    """Scenario: The at-risk evaluation names its overdue blocking steps.

    WHEN a launch's report states the launch date is at risk
    THEN the at-risk evaluation SHALL name each overdue blocking step that
    produced it.

    SPECIFIED: *each* -- two overdue blocking steps, so an implementation
    naming only the first fails. DERIVED: the naming is read through
    `LaunchDateAtRisk.overdue_steps` (`design.md` Decision 1) rendered to
    text, so that a tuple of step identifiers and a tuple of richer step
    objects both satisfy it; what is asserted is that both steps are
    named.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="inventory.units-ready",
                blocking=True,
                discipline=Discipline("inventory"),
            ),
            _step(identifier="price.buy-box-check", discipline=Discipline("price")),
        )
    )
    product_id = _new_product_id()

    reports = await read_launches(
        _FakeLaunchStore(
            _start(playbook, product_id=product_id, launch_date=AT_RISK_LAUNCH_DATE)
        ),
        _FakePlaybooks(playbook),
        as_of=AS_OF,
    )

    (report,) = tuple(reports)
    at_risk = _read(report, "at_risk")
    assert at_risk, (
        "the launch date is not reported at risk, so the scenario's WHEN does not hold"
    )
    assert hasattr(at_risk, "overdue_steps"), (
        "the at-risk evaluation exposes no `overdue_steps`, so it names no "
        "step (design.md Decision 1)"
    )
    named = " ".join(str(step) for step in at_risk.overdue_steps)
    # SPECIFIED: each overdue blocking step that produced it.
    assert "listing.title-conforms" in named
    assert "inventory.units-ready" in named
    # SPECIFIED by "that produced it": the overdue *non-blocking* step did
    # not produce the at-risk verdict and is not named by it.
    assert "price.buy-box-check" not in named


# ---------------------------------------------------------------------------
# Requirement: The launch report states whether the current gate awaits
# confirmation
# ---------------------------------------------------------------------------


async def _report_for(launch: Launch, playbook: LaunchPlaybook) -> Any:
    reports = await read_launches(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), as_of=AS_OF
    )
    (report,) = tuple(reports)
    return report


async def test_a_satisfied_confirmation_gate_without_an_approval_awaits() -> None:
    """Scenario: A satisfied confirmation gate without an approval awaits
    confirmation.

    WHEN the current gate requires confirmation, every blocking condition
    attached to it is satisfied, and no approving approval is recorded for
    it
    THEN the launch report SHALL state the gate awaits confirmation.

    A freshly started launch stands at `commit`, a confirmation gate; the
    playbook attaches no blocking condition to it, so every one of them is
    (vacuously) satisfied -- the same construction `test_graduation.py`
    uses for its conditionless playbook.
    """
    playbook = _playbook()
    launch = _start(
        playbook, product_id=_new_product_id(), launch_date=AT_RISK_LAUNCH_DATE
    )
    assert launch.current_gate == "commit"

    report = await _report_for(launch, playbook)

    # SPECIFIED: the report states the gate awaits confirmation.
    assert _awaiting_confirmation(report) is True


async def test_unsatisfied_blocking_conditions_mean_not_awaiting() -> None:
    """Scenario: Unsatisfied blocking conditions mean the gate is not
    awaiting confirmation.

    WHEN the current gate requires confirmation and at least one blocking
    condition attached to it is unsatisfied
    THEN the launch report SHALL state the gate does not await
    confirmation.

    The blocking condition used is an unresolved blocking step attached to
    `commit` -- the condition kind `launch-instance`'s standing scenario
    *An advance with an unresolved blocking step is rejected* already
    establishes holds a gate closed.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="strategy.phase-one-criteria", gate="commit", blocking=True
            ),
        )
    )
    launch = _start(
        playbook, product_id=_new_product_id(), launch_date=AT_RISK_LAUNCH_DATE
    )

    report = await _report_for(launch, playbook)

    # SPECIFIED: not awaiting confirmation -- nothing is waiting on a human
    # while the gate's own conditions are unmet.
    assert _awaiting_confirmation(report) is False


async def test_a_recorded_approving_approval_ends_the_wait() -> None:
    """Scenario: A recorded approving approval ends the wait.

    WHEN the current gate requires confirmation, its blocking conditions
    are satisfied, and an approving approval is recorded for it
    THEN the launch report SHALL state the gate does not await
    confirmation.
    """
    playbook = _playbook()
    launch = _start(
        playbook, product_id=_new_product_id(), launch_date=AT_RISK_LAUNCH_DATE
    )
    launch.approve_gate("commit", _approval())

    report = await _report_for(launch, playbook)

    # SPECIFIED: the wait is over once the approval is recorded.
    assert _awaiting_confirmation(report) is False


async def test_an_automatic_gate_never_awaits_confirmation() -> None:
    """Scenario: An automatic gate never awaits confirmation.

    WHEN the current gate opens automatically
    THEN the launch report SHALL state the gate does not await
    confirmation, whatever its conditions' state.

    "Whatever its conditions' state" is exercised by attaching an
    unresolved blocking step to the automatic gate the launch stands at:
    the gate is held closed, and it still awaits no confirmation, because
    no human decision is due on an automatic gate.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", gate="listable", blocking=True),
        )
    )
    launch = _advance_to(
        _start(playbook, product_id=_new_product_id(), launch_date=AT_RISK_LAUNCH_DATE),
        playbook,
        "listable",
    )

    report = await _report_for(launch, playbook)

    # SPECIFIED: an automatic gate never awaits confirmation.
    assert _awaiting_confirmation(report) is False
