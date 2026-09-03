"""A gate held by an unresolved metric step is left where it is.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-gate-progression/spec.md`

Covers the MODIFIED requirement *A recurring pass advances every launch
whose gate may open* — its new scenario *A gate held by an unresolved
metric step is left where it is*, and the two clauses this delta rewrites
to stop naming metric attestations among the facts a gate is judged on
("every condition the served playbook attaches to the gate, weighed
against the launch's own recorded step outcomes and approvals").

Its six other scenarios are unchanged by this delta and stay covered by
`tests/unit/launch/application/test_progress_launch.py`,
`tests/unit/launch/application/test_recording_does_not_advance_a_launch.py`
and this module's siblings in
`tests/unit/launch/infrastructure/driving/`. Nothing here edits them; the
first of those constructs `MetricCondition` and records an attestation in
its fixtures, and is recorded in `test-manifest.md` as needing fixture
migration, its `test_a_gate_blocked_only_by_a_metric_condition_is_left_silently`
as an obsolete-test candidate.

## Level, and why it is the cascade rather than the pass

The scenario reads "the pass runs against a launch...", but the
requirement fixes where the judgement is made: "That judgement ... SHALL
be made by the launch, so that the pass and the advance cannot disagree
about whether a gate may open." The cascade is the smallest unit that can
observe *all three* of the scenario's clauses together — the gate
unchanged, no advance commanded, and no refused-advance entry journaled —
because the pass above it only counts launches and the `Launch` below it
does not know a journal exists.

It is also where this project already put the superseded analogue: the
metric-condition scenario of the same requirement lives in
`test_progress_launch.py`, not in the pass's own file.

## What is fixed, and what is INVENTED

Fixed by the artifacts and by the existing implementation: `progress_launch`
exported from `commerce_ops.launch.application`; that it takes the product
identifier and reads the launch itself; the journal kinds `gate-opened`
and `advance-refused`.

INVENTED, with correction points, following what
`test_progress_launch.py`'s own docstring records: the cascade's exported
name (`_use_case()` probes and fails loudly) and its call shape
(`_progress` supplies a superset and filters by the implemented
signature).

## Expected first-run state

`StepDefinition` takes no `metric_id`, so both tests here are expected to
fail on an absent target (`TypeError` in the fixture). Per
`ai-toolkit:testing` that establishes absence only: neither test's
assertions has been exercised.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
from commerce_ops.launch.domain.launch_playbook import (
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
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

KIND_GATE_OPENED: Final = "gate-opened"
KIND_ADVANCE_REFUSED: Final = "advance-refused"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
APPROVER: Final = "Helen"

STOCK_METRIC: Final = MetricId("units-fulfillable")
METRIC_STEP: Final = "lp.inventory.040"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _hold(gate: str) -> StepDefinition:
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=0),
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(),
        handler="fixture.holding_check",
        provenance=None,
    )


def _metric_step() -> StepDefinition:
    """The blocking metric step, on `stock-ready`.

    Placed there because that is where `launch_playbook.py` authors a
    condition today and where `design.md` — Risks says every launch comes
    to rest, so the scenario is exercised at the gate the change is
    actually about.
    """
    return StepDefinition(
        identifier=METRIC_STEP,
        name="INVENTORY GATE: 60-80+ units fulfillable before going live",
        description=(
            "INVENTORY GATE: do not make the listing live until 60-80, and "
            "hopefully 100+, units are FULFILLABLE - not in transfer, not "
            "reserved, not inbound"
        ),
        gate="stock-ready",
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-7),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(),
        handler=None,
        provenance=None,
        metric_id=STOCK_METRIC,
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(
        version="progression-metric-v1",
        gates=gates,
        steps=(*(_hold(gate) for gate in SPECIFIED_GATE_ORDER), _metric_step()),
    )


def _provenance() -> Provenance:
    return Provenance(
        source="automated",
        who="hold-filler",
        when=NOW,
        evidence="the blocking check reported green",
    )


def _approval(*, gate: str) -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver=APPROVER,
        when=NOW,
        posture=Posture.SCALE if gate == FINAL_GATE else None,
    )


def _satisfy_steps(launch: Launch, playbook: LaunchPlaybook) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _standing_at(gate: str, playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != gate:
        _satisfy_steps(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate, _approval(gate=launch.current_gate)
            )
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeLaunches:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}
        self.saves: list[ProductId] = []

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self.saves.append(launch.product_id)
        self._launches[launch.product_id] = launch

    async def list_active(self) -> tuple[Launch, ...]:
        return tuple(
            launch
            for launch in self._launches.values()
            if launch.current_gate != FINAL_GATE
        )

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    def stored(self) -> Launch:
        return self._launches[PRODUCT_ID]


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str = "") -> LaunchPlaybook:
        return self.playbook


class _FakeJournal:
    def __init__(self) -> None:
        self.appended: list[Any] = []
        self.rollbacks = 0

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        self.rollbacks += 1

    def count(self, kind: str) -> int:
        return [getattr(entry, "kind", None) for entry in self.appended].count(kind)


class _FakeStamper:
    def __init__(self) -> None:
        self.calls: list[tuple[ProductId, object, str]] = []

    async def __call__(
        self, product_id: ProductId, stage: object, *, confirmed_by: str
    ) -> None:
        self.calls.append((product_id, stage, confirmed_by))


class _Collaborators:
    def __init__(self, launch: Launch, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook
        self.playbooks = _FakePlaybooks(playbook)
        self.launches = _FakeLaunches(launch)
        self.journal = _FakeJournal()
        self.stamper = _FakeStamper()


# ---------------------------------------------------------------------------
# The use case, reached through one correction point
# ---------------------------------------------------------------------------

_USE_CASE_NAMES: Final = ("progress_launch", "progress", "advance_launch")


def _use_case() -> Any:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "`commerce_ops.launch.application` exports no cascade use case under "
        f"any of {_USE_CASE_NAMES} — correct this file's probe to the "
        "implemented name"
    )


async def _progress(collaborators: _Collaborators) -> Any:
    """INVENTED call shape — the single correction point."""
    entry = _use_case()
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbooks": collaborators.playbooks,
        "playbook": collaborators.playbook,
        "stamp_steady_state": collaborators.stamper,
        "journal": collaborators.journal,
        "product_id": PRODUCT_ID,
        "now": NOW,
    }
    accepted = set(inspect.signature(entry).parameters)
    return await entry(**{k: v for k, v in supplied.items() if k in accepted})


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A recurring pass advances every launch whose
# gate may open
# ---------------------------------------------------------------------------


async def test_a_gate_held_by_an_unresolved_metric_step_is_left_where_it_is() -> None:
    """Scenario: A gate held by an unresolved metric step is left where it
    is.

    WHEN the pass runs against a launch whose current gate carries a
    blocking step declaring a metric identifier, and that step has no
    satisfying outcome recorded
    THEN the launch's current gate is unchanged, exactly as for any other
    unresolved blocking step.

    The gate's other blocking obligation is satisfied first, so the metric
    step alone holds it. The silence half of the sibling scenario is
    asserted alongside — no advance commanded and no refused-advance
    entry — because that is what the requirement's read-before-command
    rule buys, and "exactly as for any other unresolved blocking step"
    means it must hold here too: a cascade that commanded the advance and
    read the refusal would append that entry hundreds of times a day per
    parked launch, which is the flooding the rule exists to prevent, and
    the three parked launches are parked at exactly this gate.
    """
    playbook = _playbook()
    launch = _standing_at("stock-ready", playbook)
    launch.record_step_outcome(
        playbook,
        step_id="hold.stock-ready",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    collaborators = _Collaborators(launch, playbook)

    await _progress(collaborators)

    # SPECIFIED: the launch's current gate is unchanged.
    assert collaborators.launches.stored().current_gate == "stock-ready"
    # SPECIFIED: no advance is commanded, and no refused-advance entry is
    # journaled.
    assert collaborators.journal.count(KIND_ADVANCE_REFUSED) == 0
    assert collaborators.journal.count(KIND_GATE_OPENED) == 0


async def test_a_resolved_metric_step_lets_the_pass_carry_the_launch_on() -> None:
    """Requirement statement: "A gate therefore opens no later than one
    pass interval after its last condition is met."

    DERIVED from the requirement statement rather than a named scenario,
    and paired with the test above: without it, a cascade that never
    opened a gate carrying a metric step would satisfy the holding
    scenario and reproduce, through the step, exactly the stall the metric
    condition caused.
    """
    playbook = _playbook()
    launch = _standing_at("stock-ready", playbook)
    _satisfy_steps(launch, playbook)
    collaborators = _Collaborators(launch, playbook)

    await _progress(collaborators)

    # The gate opened. The cascade continues while gates keep opening, so
    # what is asserted is that it moved past `stock-ready`, not the exact
    # gate it came to rest at — that depends on the fixture's later gates
    # and is the subject of *Consecutive open gates are crossed in one
    # pass*, which this file does not cover.
    stored = collaborators.launches.stored()
    assert stored.current_gate != "stock-ready"
    assert SPECIFIED_GATE_ORDER.index(stored.current_gate) > (
        SPECIFIED_GATE_ORDER.index("stock-ready")
    )
    assert collaborators.journal.count(KIND_GATE_OPENED) >= 1
