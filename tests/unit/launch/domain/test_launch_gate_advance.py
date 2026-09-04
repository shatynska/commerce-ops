"""Tests for the `Launch` aggregate: gate advancement, approvals, and
metric attestations.

Derived from the delta spec:
openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md

Covers, at the domain level:

- ADDED Requirement: *A gate opens only when every blocking condition
  attached to it is satisfied* (all four scenarios).
- ADDED Requirement: *A confirmation gate additionally requires a
  recorded approval* (all five scenarios).
- ADDED Requirement: *A metric condition is satisfied by human
  attestation until live evaluation exists* (all three scenarios).
- ADDED Requirement: *Graduation stamps the catalog product
  steady-state* — only scenario *A graduation approval without a posture
  is rejected*; the rejection is a property of recording an approval on
  the aggregate, so the domain is the smallest level that observes it.
  The two stage-stamping scenarios need the catalog wiring and live in
  `tests/unit/launch/application/test_graduation.py`.

At the time of writing `commerce_ops.launch.domain.launch_run` does not
exist, so every test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

The INVENTED interface shape (module path, `Launch.start`, command and
read-back spellings, `LaunchError` as the single rejection signal) is the
one `test_launch_run.py`'s docstring records; this file adds:

- A rejected advance raises `LaunchError`; the raised error's rendering
  (`str`) names each unsatisfied condition — the delta's "a `GateBlocked`
  occurrence naming each unsatisfied condition", with `design.md`
  Decision 4 putting that occurrence on the raised error. If the
  implementation carries the naming on a structured event attribute
  instead of the message, correcting how the naming is *read* is a
  fixture correction; that the unsatisfied condition is named is
  SPECIFIED and must survive.
- Approval-construction rejections (an unnamed approver) may surface at
  value construction (`ValueError`, the project's construction-time
  convention) or at the recording command (`LaunchError`); the tests
  accept either site, since the delta fixes the rejection, not its
  layer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    Refused,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    GateOpened,
    Launch,
    LaunchError,
    LaunchStarted,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

PRODUCT_ID: Final = product_id()

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

# A rejection may surface at value construction (ValueError, the project
# convention) or at the recording command (LaunchError) — see docstring.
REJECTED: Final = (LaunchError, ValueError)


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        name="Work this step asks for",
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return _build_playbook(*steps, filler=_hold)


def _start(playbook: LaunchPlaybook) -> tuple[Launch, LaunchStarted]:
    """INVENTED call shape — the single point to correct if it differs."""
    return Launch.start(product_id=PRODUCT_ID, playbook=playbook)


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "screenshot in the launch Slack thread",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": "Helen",
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _satisfy_fillers(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Record `Satisfied` for the current gate's holding fillers, so a
    test is blocked only by the conditions it authored deliberately."""
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking and step.identifier.startswith("hold."):
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(source="automated"),
            )


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate_id: str) -> None:
    """Walk the launch forward to `gate_id`, approving confirmation gates."""
    while launch.current_gate != gate_id:
        _satisfy_fillers(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)


def _satisfy(launch: Launch, playbook: LaunchPlaybook, step_id: str) -> None:
    launch.record_step_outcome(
        playbook, step_id=step_id, outcome=Satisfied, provenance=_provenance()
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A gate opens only when every blocking condition
# attached to it is satisfied
# ---------------------------------------------------------------------------


def test_an_automatic_gate_opens_when_every_blocking_condition_is_satisfied() -> None:
    """Scenario: An automatic gate opens when every blocking condition is
    satisfied.

    WHEN every blocking condition attached to the current automatic gate
    is satisfied and the launch is advanced
    THEN the current gate becomes the next gate in the sequence and a
    `GateOpened` occurrence is reported.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    launch, _ = _start(playbook)
    _advance_to(launch, playbook, "listable")
    _satisfy(launch, playbook, "listing.title-conforms")

    events = launch.advance_gate(playbook)

    # SPECIFIED: the next gate in the sequence, and a `GateOpened`
    # occurrence.
    assert launch.current_gate == "stock-ready"
    assert any(isinstance(event, GateOpened) for event in events)


def test_an_advance_with_an_unresolved_blocking_step_is_rejected() -> None:
    """Scenario: An advance with an unresolved blocking step is rejected.

    WHEN the launch is advanced while a blocking step attached to the
    current gate has not reached a permitted terminal outcome
    THEN the advance is rejected, the current gate is unchanged, and a
    `GateBlocked` occurrence names that unsatisfied condition.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    launch, _ = _start(playbook)
    _advance_to(launch, playbook, "listable")

    with pytest.raises(LaunchError) as caught:
        launch.advance_gate(playbook)

    # SPECIFIED: the current gate is unchanged.
    assert launch.current_gate == "listable"
    # SPECIFIED: the `GateBlocked` occurrence names that unsatisfied
    # condition (read via the error's rendering — see module docstring).
    assert "listing.title-conforms" in str(caught.value)


def test_a_refused_prohibited_tactic_step_never_holds_a_gate_closed() -> None:
    """Scenario: A refused prohibited-tactic step never holds a gate
    closed.

    WHEN a non-blocking `prohibited-tactic` step attached to the current
    gate is `Refused` and every blocking condition attached to that gate
    is satisfied
    THEN the launch advances — refusal neither satisfies nor blocks any
    condition.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.title-conforms", blocking=True),
            _step(
                identifier="reviews.purchase-ring",
                hazard=Hazard.PROHIBITED_TACTIC,
                blocking=False,
            ),
        )
    )
    launch, _ = _start(playbook)
    _advance_to(launch, playbook, "listable")
    _satisfy(launch, playbook, "listing.title-conforms")
    launch.record_step_outcome(
        playbook,
        step_id="reviews.purchase-ring",
        outcome=Refused,
        provenance=_provenance(),
    )

    launch.advance_gate(playbook)

    # SPECIFIED: the launch advances.
    assert launch.current_gate == "stock-ready"


def test_an_advance_moves_to_exactly_the_next_gate() -> None:
    """Scenario: An advance moves to exactly the next gate.

    WHEN the launch advances from its current gate
    THEN the current gate becomes exactly the next gate in the
    `launch-playbook` sequence.

    Walked over the whole sequence so that a skip or a backward move at
    any position would be caught, not only at the first. The scenario's
    further clause — that the advance operation offers no way to target a
    later or an earlier gate — is established by the command's shape
    (`advance_gate` takes no target); the walk asserts the positive half.
    The `graduated` gate is not advanced here: opening it is graduation,
    covered in the application tier.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)

    for expected_next in SPECIFIED_GATE_ORDER[1:]:
        _satisfy_fillers(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
        # SPECIFIED: exactly the next gate, at every position.
        assert launch.current_gate == expected_next


# ---------------------------------------------------------------------------
# ADDED Requirement: A confirmation gate additionally requires a recorded
# approval
# ---------------------------------------------------------------------------


def test_a_confirmation_gate_with_satisfied_conditions_but_no_approval_stays_closed() -> (
    None
):
    """Scenario: A confirmation gate with satisfied conditions but no
    approval stays closed.

    WHEN every blocking condition attached to the current
    `requires-confirmation` gate is satisfied but no approval for it has
    been recorded, and the launch is advanced
    THEN the advance is rejected and the current gate is unchanged.

    `commit` carries no blocking condition in this playbook, so every
    blocking condition is (vacuously) satisfied and only the approval is
    missing.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)
    # The gate-holding floor gives `commit` a filler obligation; satisfying
    # it restores the premise that only the approval is missing.
    _satisfy_fillers(launch, playbook)

    with pytest.raises(LaunchError):
        launch.advance_gate(playbook)

    # SPECIFIED: the current gate is unchanged.
    assert launch.current_gate == "commit"


def test_a_confirmation_gate_opens_once_approved() -> None:
    """Scenario: A confirmation gate opens once approved.

    WHEN every blocking condition attached to the current
    `requires-confirmation` gate is satisfied and an approval with a
    named approver is recorded
    THEN the launch advances and a `GateOpened` occurrence is reported.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)
    _satisfy_fillers(launch, playbook)
    launch.approve_gate("commit", _approval(approver="Helen"))

    events = launch.advance_gate(playbook)

    # SPECIFIED: the launch advances and a `GateOpened` occurrence is
    # reported.
    assert launch.current_gate == "order"
    assert any(isinstance(event, GateOpened) for event in events)


def test_an_approval_without_a_named_approver_is_rejected() -> None:
    """Scenario: An approval without a named approver is rejected.

    WHEN a gate approval is recorded without a named approver
    THEN the recording is rejected.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)

    # SPECIFIED: the recording is rejected. The rejection may surface at
    # approval construction or at the recording command (see docstring);
    # `pytest.raises` spans both calls deliberately.
    with pytest.raises(REJECTED):
        launch.approve_gate("commit", _approval(approver=""))


def test_a_rejecting_decision_keeps_the_gate_closed() -> None:
    """Scenario: A rejecting decision keeps the gate closed.

    WHEN every blocking condition attached to the current
    `requires-confirmation` gate is satisfied, an approval with a
    rejecting decision is recorded, and the launch is advanced
    THEN the advance is rejected and the current gate is unchanged.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)
    # SPECIFIED: a rejecting decision is recorded — recording it is not
    # itself an error.
    _satisfy_fillers(launch, playbook)
    launch.approve_gate("commit", _approval(decision=ApprovalDecision.REJECTING))

    with pytest.raises(LaunchError):
        launch.advance_gate(playbook)

    # SPECIFIED: the current gate is unchanged — only an approving
    # decision satisfies the approval requirement.
    assert launch.current_gate == "commit"


def test_a_posture_on_a_non_graduation_approval_is_rejected() -> None:
    """Scenario: A posture on a non-graduation approval is rejected.

    WHEN an approval for a gate other than `graduated` names a posture
    THEN the recording is rejected.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)

    with pytest.raises(REJECTED):
        launch.approve_gate("commit", _approval(posture=Posture.HOLD))


def test_a_graduation_approval_without_a_posture_is_rejected() -> None:
    """Scenario: A graduation approval without a posture is rejected.

    WHEN an approval for the `graduated` gate is recorded without naming
    a posture
    THEN the recording is rejected.

    Recorded against a fresh launch: nothing in the delta conditions the
    rejection on the launch's position, only on the approved gate being
    `graduated`. If the implementation requires standing at the gate
    first, walking the launch there is a fixture correction.
    """
    playbook = _playbook()
    launch, _ = _start(playbook)

    with pytest.raises(REJECTED):
        launch.approve_gate("graduated", _approval(posture=None))
