"""Within-gate order never reaches the commitment machinery
(`launch-playbook`, MODIFIED *Gate sequence orders the launch*).

Derived strictly from the delta spec:
`openspec/changes/add-playbook-admin-ui/specs/launch-playbook/spec.md`

Covers the retained scenario *Steps at the same gate are unordered*, as
the delta redefines it: "unordered" now means unordered **to the
commitment machinery** — an authored order exists, and this scenario
pins down that it never reaches an evaluation. Reordering a gate's
steps changes how they are listed, and nothing else: never when a gate
opens, which steps block it, or how step completion is evaluated.

## Level

At the domain level a reorder is a change in the sequence the same-gate
step definitions reach `LaunchPlaybook` in — the design keeps the slot
in the serving layer (`design.md` Decision 1), so the playbook object
receives its steps already ordered, and a reorder reaches the aggregate
only as a permutation of that tuple. The `Launch` aggregate's
evaluations over two permutations of the same steps are therefore the
smallest unit that can observe the invariant. Fixtures follow
`test_launch_gate_advance.py` in this directory.

## Expected first-run state

The target — gate advancement, blocking evaluation, step completion —
**already exists**; what this change adds is the authored order these
evaluations must ignore. These tests are expected to PASS on first run:
they pin the pre-change indifference to step sequence so that
implementing the ordering cannot silently break it. Per
`ai-toolkit:testing`, a first-run pass in the target-exists situation is
the expected result, not an alarm.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 621 passed, 0 failed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

import pytest

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
    LaunchError,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

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

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


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
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _provenance() -> Provenance:
    return Provenance(
        source="attestation",
        who="Helen",
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=APPROVED_AT,
        posture=None,
    )


# The gate under evaluation carries two blocking steps whose authored
# listing order this test permutes. Fillers hold every other gate.
FIRST = _step(identifier="listing.first-authored", blocking=True)
SECOND = _step(identifier="listing.second-authored", blocking=True)


def _playbook(listable_steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate != "listable")
    return LaunchPlaybook(
        version="test-v1", gates=_gates(), steps=(*listable_steps, *fillers)
    )


def _launch_at_listable(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(product_id=ProductId(str(uuid.uuid4())), playbook=playbook)
    while launch.current_gate != "listable":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


@pytest.mark.parametrize(
    "listable_steps",
    [
        pytest.param((FIRST, SECOND), id="authored-order"),
        pytest.param((SECOND, FIRST), id="reordered"),
    ],
)
def test_blocking_evaluation_is_identical_under_any_step_order(
    listable_steps: tuple[StepDefinition, ...],
) -> None:
    """Scenario: Steps at the same gate are unordered (retained; revised
    meaning) — the blocking half.

    WHEN a gate's steps are reordered and the gate's advancement and
    blocking evaluation are then evaluated
    THEN the commitment machinery treats the gate's steps as an
    unordered set: each evaluation comes out exactly as it did before
    the reorder.

    Both permutations run the same evaluations; the parametrisation is
    the reorder. With only the *later-listed* step satisfied, an
    evaluation that consulted listing order (for example, one that
    checked only the first-listed step, or short-circuited on it) would
    diverge between the two permutations.
    """
    playbook = _playbook(listable_steps)
    launch = _launch_at_listable(playbook)

    # Satisfy exactly one of the two blocking steps — the same *step*
    # (by identity, not by position) in both permutations.
    launch.record_step_outcome(
        playbook,
        step_id=SECOND.identifier,
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # SPECIFIED: an unresolved blocking step blocks the gate — in both
    # permutations, naming the same step.
    with pytest.raises(LaunchError) as caught:
        launch.advance_gate(playbook)
    assert launch.current_gate == "listable"
    assert FIRST.identifier in str(caught.value)

    # SPECIFIED: once every blocking step is satisfied the gate opens —
    # in both permutations alike.
    launch.record_step_outcome(
        playbook,
        step_id=FIRST.identifier,
        outcome=Satisfied,
        provenance=_provenance(),
    )
    launch.advance_gate(playbook)
    assert launch.current_gate == "stock-ready"


@pytest.mark.parametrize(
    "listable_steps",
    [
        pytest.param((FIRST, SECOND), id="authored-order"),
        pytest.param((SECOND, FIRST), id="reordered"),
    ],
)
def test_step_completion_is_identical_under_any_step_order(
    listable_steps: tuple[StepDefinition, ...],
) -> None:
    """Scenario: Steps at the same gate are unordered (retained; revised
    meaning) — the step-completion half.

    WHEN a gate's steps are reordered and step completion is then
    evaluated
    THEN recording an outcome addresses the step by identifier exactly
    as before the reorder — a step's recorded outcome does not depend on
    its slot.
    """
    playbook = _playbook(listable_steps)
    launch = _launch_at_listable(playbook)

    launch.record_step_outcome(
        playbook,
        step_id=FIRST.identifier,
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # SPECIFIED: completion is evaluated per step identity, untouched by
    # the permutation — the same step remains the unsatisfied one.
    with pytest.raises(LaunchError) as caught:
        launch.advance_gate(playbook)
    assert SECOND.identifier in str(caught.value)
    assert FIRST.identifier not in str(caught.value)
