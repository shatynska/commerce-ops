"""Tests for the `Launch` aggregate: starting, and step-outcome recording.

Derived from the delta spec:
openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md

Covers, at the domain level:

- MODIFIED Requirement: *A launch position is persisted for a catalog
  product* — only the `LaunchStarted`-occurrence half of scenario *A
  launch position is created for an existing product* (the persistence
  halves of that requirement live in
  `tests/integration/launch/test_launch_repository.py`).
- MODIFIED Requirement: *A product's current gate is restricted to the
  launch-playbook gate sequence* — scenario *A new product defaults to
  the first gate* (the persistence-rejection scenario lives in the
  integration file).
- ADDED Requirement: *A step outcome is recorded with provenance* (all
  six scenarios).

Every outcome these scenarios state is observable on the aggregate alone,
with no I/O, so the domain unit tier is the smallest level that can
observe them.

At the time of writing `commerce_ops.launch.domain.launch_run` does not
exist (`tasks.md` 1.1 creates it), so every test here is expected to fail
on an absent target (`ModuleNotFoundError`). Per `ai-toolkit:testing`,
that failure establishes only absence.

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 1.1-1.4 and `design.md` Decisions 2-4 fix the concepts but not
the spellings. Assumed, and recorded in the manifest as unresolved
project questions:

- `commerce_ops.launch.domain.launch_run` exporting `Launch`,
  `Provenance`, `GateApproval`, `ApprovalDecision` (members `APPROVING` /
  `REJECTING`), the event objects (`LaunchStarted`, `StepSatisfied`,
  `StepRefused`, ...), and `LaunchError` as the single domain rejection
  signal (this project's one-exception-per-rejected-family precedent).
- `Launch.start(product_id=..., playbook=..., launch_date=None)`
  returning `(launch, LaunchStarted)`; the alternative shape (a
  `playbook_version` string instead of the playbook) is recorded in the
  manifest.
- Commands mutate in place and return the tuple of events they produced
  (`design.md` Decision 3):
  `launch.record_step_outcome(playbook, step_id=..., outcome=...,
  provenance=...)`, `launch.approve_gate(gate_id, approval)`,
  `launch.advance_gate(playbook)`.
- Read-back via `launch.progress_for(step_id)` returning an object with
  `.outcome` and `.provenance` (with `.source`, `.who`, `.when`,
  `.evidence`), or `None` where nothing was ever recorded; `.current_gate`
  as the gate-id string (the spelling the previous launch-instance pass
  used); `.launch_date`; `.playbook_version`.
- Outcomes are referred to by the designators `test_step_outcome.py`
  already records: `Satisfied` / `Refused` bare, `Blocked(reason)` /
  `NotApplicable(reason)` constructed.
- Provenance `source` spelled as the spec's wire strings (`"clickup"`,
  `"automated"`); an enum instead is a fixture
  correction.

Correcting any name, path, or call shape above is a fixture correction
(failure state 3 in `ai-toolkit:testing`); what must survive unweakened
is what each test asserts: which recordings are accepted or rejected,
what the stored outcome and provenance are afterwards, and which
occurrences are reported.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    InProgress,
    LaunchPlaybook,
    OffsetAnchor,
    Refused,
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
    LaunchStarted,
    Provenance,
    StepRefused,
    StepSatisfied,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

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

# SPECIFIED (launch-playbook spec, unchanged): the four confirmation gates.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)


def _any_discipline() -> Discipline:
    """Return some `Discipline` member, asserting nothing about which."""
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
    """Build a valid `StepDefinition`, overriding named attributes."""
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
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires; the `hold.` namespace tells fillers apart."""
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


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
    """Record `Satisfied` for the current gate's holding fillers, so the
    walk is blocked only by the steps a test authored deliberately."""
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


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A product's current gate is restricted to the
# launch-playbook gate sequence
# ---------------------------------------------------------------------------


def test_a_started_launch_begins_at_the_first_gate() -> None:
    """Scenario: A new product defaults to the first gate (as revised).

    WHEN a launch is started
    THEN its current gate is reported as `commit`.
    """
    launch, _ = _start(_playbook())

    # SPECIFIED: a newly started launch begins at `commit`; the start path
    # offers no way to begin anywhere else (the revised requirement drops
    # the old explicit-gate creation parameter).
    assert launch.current_gate == "commit"


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A launch position is persisted for a catalog
# product — the `LaunchStarted`-occurrence half; persistence halves live in
# tests/integration/launch/test_launch_repository.py
# ---------------------------------------------------------------------------


def test_starting_reports_a_launch_started_occurrence() -> None:
    """Scenario: A launch position is created for an existing product
    (occurrence half).

    WHEN a launch is started ... against a playbook version, with no
    launch date
    THEN ... the launch date is reported as absent, and a `LaunchStarted`
    occurrence is reported.
    """
    launch, started = _start(_playbook())

    # SPECIFIED: a `LaunchStarted` occurrence carrying the product
    # identifier and the pinned playbook version. DERIVED: the attribute
    # spellings `product_id` / `playbook_version`.
    assert isinstance(started, LaunchStarted)
    assert started.product_id == PRODUCT_ID
    assert started.playbook_version == "test-v1"
    # SPECIFIED: the version is pinned at start.
    assert launch.playbook_version == "test-v1"
    # SPECIFIED: the launch date is reported as absent.
    assert launch.launch_date is None


# ---------------------------------------------------------------------------
# ADDED Requirement: A step outcome is recorded with provenance
# ---------------------------------------------------------------------------


def test_a_satisfied_step_is_recorded_with_its_provenance() -> None:
    """Scenario: A satisfied step is recorded with its provenance.

    WHEN a `Satisfied` outcome is recorded for a defined step with source
    `clickup`, a named recorder, a timestamp, and evidence
    THEN reading the launch back reports that step's outcome as
    `Satisfied` with exactly that provenance, and a `StepSatisfied`
    occurrence is reported.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    launch, _ = _start(playbook)
    provenance = _provenance(source="clickup")

    events = launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=provenance,
    )

    # SPECIFIED: a `StepSatisfied` occurrence is reported.
    assert any(isinstance(event, StepSatisfied) for event in events)
    progress = launch.progress_for("listing.title-conforms")
    assert progress is not None
    # SPECIFIED: the outcome is `Satisfied` with exactly that provenance.
    assert progress.outcome is Satisfied
    assert progress.provenance.source == "clickup"
    assert progress.provenance.who == "Helen"
    assert progress.provenance.when == RECORDED_AT
    assert progress.provenance.evidence == "screenshot in the launch Slack thread"


def test_a_re_recorded_outcome_replaces_the_stored_one_without_reopening_gates() -> (
    None
):
    """Scenario: A re-recorded outcome replaces the stored one without
    reopening gates.

    WHEN a step recorded as `Satisfied` is later re-recorded as `Blocked`
    with a reason, after the gate it is attached to has already opened
    THEN the stored outcome and provenance are replaced, and the launch's
    current gate is unchanged.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", blocking=True),)
    )
    launch, _ = _start(playbook)
    _advance_to(launch, playbook, "listable")
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(who="Helen"),
    )
    launch.advance_gate(playbook)
    assert launch.current_gate == "stock-ready"  # precondition: gate opened

    later = datetime(2027, 2, 1, 8, 0, tzinfo=UTC)
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Blocked("listing suppressed by the marketplace"),
        provenance=_provenance(source="clickup", who="Anton", when=later),
    )

    progress = launch.progress_for("listing.title-conforms")
    assert progress is not None
    # SPECIFIED: the stored outcome and provenance are replaced.
    assert progress.outcome == Blocked("listing suppressed by the marketplace")
    assert progress.provenance.who == "Anton"
    assert progress.provenance.source == "clickup"
    assert progress.provenance.when == later
    # SPECIFIED: the launch's current gate is unchanged — a re-recording
    # never reverses a gate that has already opened.
    assert launch.current_gate == "stock-ready"


def test_a_prohibited_tactic_step_is_refused() -> None:
    """Scenario: A prohibited-tactic step is refused.

    WHEN a `Refused` outcome is recorded for a step classified
    `prohibited-tactic`
    THEN the outcome is recorded and a `StepRefused` occurrence is
    reported.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="reviews.purchase-ring",
                hazard=Hazard.PROHIBITED_TACTIC,
                blocking=False,
            ),
        )
    )
    launch, _ = _start(playbook)

    events = launch.record_step_outcome(
        playbook,
        step_id="reviews.purchase-ring",
        outcome=Refused,
        provenance=_provenance(),
    )

    # SPECIFIED: the outcome is recorded and a `StepRefused` occurrence is
    # reported.
    assert any(isinstance(event, StepRefused) for event in events)
    progress = launch.progress_for("reviews.purchase-ring")
    assert progress is not None
    assert progress.outcome is Refused


def test_satisfying_a_prohibited_tactic_step_is_rejected() -> None:
    """Scenario: Satisfying a prohibited-tactic step is rejected.

    WHEN a `Satisfied` outcome is recorded for a step classified
    `prohibited-tactic`
    THEN the recording is rejected and the step's stored outcome is
    unchanged.

    The step carries a prior non-terminal `InProgress` recording so that
    "unchanged" is observable as a concrete stored value — the requirement
    says the hazard restrictions apply to every recording, not only the
    first.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="reviews.purchase-ring",
                hazard=Hazard.PROHIBITED_TACTIC,
                blocking=False,
            ),
        )
    )
    launch, _ = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id="reviews.purchase-ring",
        outcome=InProgress,
        provenance=_provenance(),
    )

    # SPECIFIED: the recording is rejected. DERIVED mechanism: the single
    # domain rejection error (see module docstring).
    with pytest.raises(LaunchError):
        launch.record_step_outcome(
            playbook,
            step_id="reviews.purchase-ring",
            outcome=Satisfied,
            provenance=_provenance(),
        )

    # SPECIFIED: the step's stored outcome is unchanged.
    progress = launch.progress_for("reviews.purchase-ring")
    assert progress is not None
    assert progress.outcome is InProgress


def test_refusing_an_ordinary_step_is_rejected() -> None:
    """Scenario: Refusing an ordinary step is rejected.

    WHEN a `Refused` outcome is recorded for a step not classified
    `prohibited-tactic`
    THEN the recording is rejected and the step's stored outcome is
    unchanged.
    """
    playbook = _playbook(
        steps=(_step(identifier="listing.title-conforms", hazard=Hazard.NONE),)
    )
    launch, _ = _start(playbook)

    with pytest.raises(LaunchError):
        launch.record_step_outcome(
            playbook,
            step_id="listing.title-conforms",
            outcome=Refused,
            provenance=_provenance(),
        )

    # SPECIFIED: the stored outcome is unchanged — nothing was ever
    # recorded for this step, so no `Refused` recording may be stored.
    # DERIVED reading: an unrecorded step reports no progress.
    progress = launch.progress_for("listing.title-conforms")
    assert progress is None or progress.outcome is not Refused


def test_an_unknown_step_identifier_is_rejected() -> None:
    """Scenario: An unknown step identifier is rejected.

    WHEN an outcome is recorded for a step identifier the pinned playbook
    version does not define
    THEN the recording is rejected.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    launch, _ = _start(playbook)

    with pytest.raises(LaunchError):
        launch.record_step_outcome(
            playbook,
            step_id="no.such-step",
            outcome=Satisfied,
            provenance=_provenance(),
        )
