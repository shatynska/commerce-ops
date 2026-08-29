"""The `Launch` aggregate: one product's run against a pinned playbook.

Implements `launch-instance` as reshaped by `introduce-launch-aggregate`.
Pure domain code — no I/O, no framework, no clock. The playbook definition
never lives inside the aggregate: every command that needs definitions
takes the loaded `LaunchPlaybook` as an argument and rejects one whose
version differs from the version this launch pinned at start, so a caller
cannot evaluate a launch against the wrong definition.

The rules here are the launch process itself, readable in one place:

- Gates advance monotonically, one at a time, never skipped, never
  backwards — `advance_gate` takes no target, so no other move exists.
- A gate opens only when every blocking condition attached to it is
  satisfied: every blocking step has reached a permitted terminal outcome
  (`Satisfied` or `NotApplicable`), and every authored metric condition
  has a recorded human attestation (until live evaluation exists,
  domain-map slice 7). A `Refused` outcome never satisfies anything.
- A `requires-confirmation` gate additionally requires a recorded
  approval whose decision is approving; a rejecting decision is recorded
  but keeps the gate closed.
- Opening `graduated` — the last gate — is graduation: the launch stays
  at `graduated` and reports `LaunchGraduated` carrying the posture the
  graduation approver chose (the system never chooses a posture itself).
- Every recorded step outcome carries recording provenance; completion is
  always recorded, never inferred. A later recording replaces the stored
  outcome, and never reverses a gate that has already opened.
- Due periods derive from `LaunchDate + TimingAnchor`; with no launch
  date there are none. Moving the date re-resolves every anchor at once.
  The date is at risk exactly when a blocking step's due period has fully
  passed without the step reaching a permitted terminal outcome.

**Events are returned, not collected** (the catalog's `StageChanged`
precedent): each command returns the tuple of event objects it produced,
and no dispatch infrastructure exists yet.

**Outcome value convention.** The reason-less outcomes (`NotStarted`,
`InProgress`, `Satisfied`, `Refused`) are recorded as the outcome *type*
itself; the reason-carrying ones (`Blocked`, `NotApplicable`) as
instances. `StepProgress.outcome` holds exactly what was recorded, so
``progress.outcome is Satisfied`` and ``progress.outcome ==
Blocked(reason)`` both read the way the rule is stated.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import ClassVar

from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    AnchorPeriod,
    GateOpening,
    Hazard,
    InProgress,
    LaunchPlaybook,
    MetricCondition,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
    StepDefinition,
    StepObligation,
    StepOutcome,
    StepStatus,
    gate_position,
    permissible_terminal_outcomes,
    start_position_of,
)
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture

PROVENANCE_SOURCES: tuple[str, ...] = ("clickup", "automated", "attestation")

StepOutcomeValue = (
    StepOutcome | type[NotStarted] | type[InProgress] | type[Satisfied] | type[Refused]
)
"""What a recording supplies and `StepProgress` stores: the outcome type
itself for the reason-less outcomes, an instance for the reason-carrying
ones (see the module docstring's outcome value convention)."""


class LaunchError(Exception):
    """A launch command was rejected: an unknown step or gate, an outcome
    the step's hazard forbids, an unauthored metric condition, a
    misplaced or missing posture, a mismatched playbook version, or an
    advance whose gate is not open."""


def _outcome_type(outcome: StepOutcomeValue) -> type[StepOutcome]:
    return outcome if isinstance(outcome, type) else type(outcome)


@dataclass(frozen=True, slots=True)
class Provenance:
    """Where a recorded outcome came from: completion is always recorded,
    never inferred, so every recording names its source, recorder, time
    and evidence — non-terminal outcomes included."""

    source: str
    who: str
    when: datetime
    evidence: str

    def __post_init__(self) -> None:
        if self.source not in PROVENANCE_SOURCES:
            raise ValueError(
                f"provenance source must be one of {PROVENANCE_SOURCES}: "
                f"'{self.source}'"
            )
        if not self.who:
            raise ValueError("provenance requires a named recorder")
        if not self.evidence:
            raise ValueError("provenance requires evidence")


@dataclass(frozen=True, slots=True)
class StepProgress:
    """A step's recorded outcome together with its recording provenance."""

    outcome: StepOutcomeValue
    provenance: Provenance


class ApprovalDecision(Enum):
    """A confirmation gate's recorded decision. Only an approving decision
    satisfies the gate's approval requirement — a rejecting one is
    recorded but keeps the gate closed."""

    APPROVING = "approving"
    REJECTING = "rejecting"


@dataclass(frozen=True, slots=True)
class GateApproval:
    """A human's recorded decision on a confirmation gate. The posture is
    meaningful exactly for `graduated` — the graduation approver chooses
    the steady-state posture, because the system never does."""

    decision: ApprovalDecision
    approver: str
    when: datetime
    posture: Posture | None = None

    def __post_init__(self) -> None:
        if not self.approver:
            raise ValueError("a gate approval requires a named approver")


@dataclass(frozen=True, slots=True)
class MetricAttestation:
    """A human's recorded satisfaction of a gate's authored metric
    condition, with evidence — the interim satisfaction path until live
    evaluation exists (domain-map slice 7)."""

    gate_id: str
    metric_id: MetricId
    attester: str
    when: datetime
    evidence: str

    def __post_init__(self) -> None:
        if not self.attester:
            raise ValueError("a metric attestation requires a named attester")
        if not self.evidence:
            raise ValueError("a metric attestation requires evidence")


# ---------------------------------------------------------------------------
# Events — returned domain objects, one per occurrence the spec names.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LaunchStarted:
    product_id: ProductId
    playbook_version: str


@dataclass(frozen=True, slots=True)
class StepSatisfied:
    product_id: ProductId
    step_id: str


@dataclass(frozen=True, slots=True)
class StepRefused:
    product_id: ProductId
    step_id: str


@dataclass(frozen=True, slots=True)
class GateOpened:
    product_id: ProductId
    gate_id: str


@dataclass(frozen=True, slots=True)
class GateBlocked:
    """An advance was attempted while conditions were unsatisfied; names
    each unsatisfied condition."""

    product_id: ProductId
    gate_id: str
    unsatisfied: tuple[str, ...]

    def __str__(self) -> str:
        named = ", ".join(self.unsatisfied)
        return (
            f"gate '{self.gate_id}' is blocked for product "
            f"'{self.product_id.value}': unsatisfied conditions: {named}"
        )


@dataclass(frozen=True, slots=True)
class LaunchDateMoved:
    """The launch date moved — every timing anchor re-resolves at once."""

    product_id: ProductId
    previous: date | None
    new: date


@dataclass(frozen=True, slots=True)
class LaunchDateAtRisk:
    """Blocking steps whose due periods have fully passed unresolved."""

    product_id: ProductId
    launch_date: date
    overdue_steps: tuple[str, ...]

    def __str__(self) -> str:
        named = ", ".join(self.overdue_steps)
        return (
            f"launch date {self.launch_date.isoformat()} is at risk for "
            f"product '{self.product_id.value}': overdue blocking steps: "
            f"{named}"
        )


@dataclass(frozen=True, slots=True)
class LaunchGraduated:
    """The `graduated` gate opened. Carries what the catalog stamp needs:
    the posture the graduation approver chose, and the approver as the
    stage change's human confirmer."""

    product_id: ProductId
    posture: Posture
    approver: str


LaunchEvent = (
    LaunchStarted
    | StepSatisfied
    | StepRefused
    | GateOpened
    | GateBlocked
    | LaunchDateMoved
    | LaunchDateAtRisk
    | LaunchGraduated
)


class GateBlockedError(LaunchError):
    """An advance was rejected; carries the `GateBlocked` occurrence."""

    def __init__(self, blocked: GateBlocked) -> None:
        self.blocked = blocked
        super().__init__(str(blocked))


_GRADUATION_GATE = "graduated"


class Launch:
    """Aggregate root: one product's launch run. `start` is the only
    creation path for a new launch; the repository reconstitutes persisted
    ones via `__init__`.

    A rehydrated launch standing at `graduated` cannot be distinguished
    from one whose `graduated` gate already opened — the persisted shape
    carries no flag (an accepted slice-3 limit; the graduation stamp's
    idempotence is guarded by the catalog's own transition rules).
    """

    GATE_IDS: ClassVar[tuple[str, ...]] = GATE_SEQUENCE

    def __init__(
        self,
        *,
        product_id: ProductId,
        playbook_version: str,
        current_gate: str,
        launch_date: date | None,
        step_progress: Mapping[str, StepProgress] | None = None,
        approvals: Mapping[str, GateApproval] | None = None,
        attestations: Iterable[MetricAttestation] = (),
    ) -> None:
        if current_gate not in GATE_SEQUENCE:
            raise LaunchError(
                f"'{current_gate}' is not one of the launch-playbook gate ids"
            )
        self.product_id = product_id
        self.playbook_version = playbook_version
        self.current_gate = current_gate
        self.launch_date = launch_date
        self._step_progress: dict[str, StepProgress] = dict(step_progress or {})
        self._approvals: dict[str, GateApproval] = dict(approvals or {})
        self._attestations: list[MetricAttestation] = list(attestations)
        self._graduated = False

    @classmethod
    def start(
        cls,
        *,
        product_id: ProductId,
        playbook: LaunchPlaybook,
        launch_date: date | None = None,
    ) -> tuple[Launch, LaunchStarted]:
        """A new launch begins at `commit`, the first gate — the start
        path offers no way to begin anywhere else — with the playbook
        version pinned for the life of the launch."""
        launch = cls(
            product_id=product_id,
            playbook_version=playbook.version,
            current_gate=GATE_SEQUENCE[0],
            launch_date=launch_date,
        )
        return launch, LaunchStarted(
            product_id=product_id, playbook_version=playbook.version
        )

    # -- read surface -------------------------------------------------------

    def progress_for(self, step_id: str) -> StepProgress | None:
        return self._step_progress.get(step_id)

    def approval_for(self, gate_id: str) -> GateApproval | None:
        return self._approvals.get(gate_id)

    @property
    def attestations(self) -> tuple[MetricAttestation, ...]:
        return tuple(self._attestations)

    @property
    def recorded_step_ids(self) -> tuple[str, ...]:
        return tuple(self._step_progress)

    @property
    def approved_gate_ids(self) -> tuple[str, ...]:
        return tuple(self._approvals)

    # -- commands -----------------------------------------------------------

    def record_step_outcome(
        self,
        playbook: LaunchPlaybook,
        *,
        step_id: str,
        outcome: StepOutcomeValue,
        provenance: Provenance,
    ) -> tuple[LaunchEvent, ...]:
        """Record an outcome for a step the pinned playbook defines.

        Terminal outcomes are restricted by the step's hazard: a
        `prohibited-tactic` step can only terminate in `Refused`; any
        other step terminates in `Satisfied` or `NotApplicable` and can
        never be `Refused`. The restrictions apply to every recording —
        a later recording replaces the stored outcome and provenance, and
        never reverses a gate that has already opened.
        """
        step = self._defined_step(playbook, step_id)

        kind = _outcome_type(outcome)
        if kind in (Satisfied, NotApplicable, Refused):
            permitted = permissible_terminal_outcomes(step.hazard)
            if kind not in permitted:
                raise LaunchError(
                    f"step '{step_id}' (hazard '{step.hazard.value}') does "
                    f"not permit the terminal outcome '{kind.__name__}'"
                )

        self._step_progress[step_id] = StepProgress(
            outcome=outcome, provenance=provenance
        )

        if kind is Satisfied:
            return (StepSatisfied(product_id=self.product_id, step_id=step_id),)
        if kind is Refused:
            return (StepRefused(product_id=self.product_id, step_id=step_id),)
        return ()

    def record_metric_attestation(
        self, playbook: LaunchPlaybook, attestation: MetricAttestation
    ) -> tuple[LaunchEvent, ...]:
        """Record a human's satisfaction of a metric condition the pinned
        playbook authors on the named gate; any other (gate, metric)
        pairing is rejected."""
        authored = any(
            condition.metric_id == attestation.metric_id
            for condition in self._authored_conditions(playbook, attestation.gate_id)
        )
        if not authored:
            raise LaunchError(
                f"the pinned playbook does not author metric condition "
                f"'{attestation.metric_id.value}' on gate "
                f"'{attestation.gate_id}'"
            )
        self._attestations.append(attestation)
        return ()

    def approve_gate(
        self, gate_id: str, approval: GateApproval
    ) -> tuple[LaunchEvent, ...]:
        """Record a confirmation decision for a gate. The graduation
        approval must name the steady-state posture the approver chose;
        a posture on any other gate's approval is rejected."""
        if gate_id not in GATE_SEQUENCE:
            raise LaunchError(f"'{gate_id}' is not one of the launch-playbook gate ids")
        if gate_id == _GRADUATION_GATE and approval.posture is None:
            raise LaunchError(
                "a graduation approval must name the steady-state posture "
                "the approver chose — the system never chooses one"
            )
        if gate_id != _GRADUATION_GATE and approval.posture is not None:
            raise LaunchError(
                f"an approval for gate '{gate_id}' cannot name a posture — "
                f"a posture belongs to the graduation approval only"
            )
        self._approvals[gate_id] = approval
        return ()

    def advance_gate(self, playbook: LaunchPlaybook) -> tuple[LaunchEvent, ...]:
        """Advance past the current gate — to exactly the next gate in the
        sequence; there is no way to target any other.

        The gate opens only when every blocking condition attached to it
        is satisfied, and — for a `requires-confirmation` gate — an
        approving approval is recorded. Opening `graduated` is
        graduation: the launch stays at `graduated` and the returned
        events include `LaunchGraduated`.
        """
        if self._graduated:
            raise LaunchError(
                f"product '{self.product_id.value}' has already graduated"
            )

        unsatisfied = self.unsatisfied_conditions(playbook)
        if unsatisfied:
            raise GateBlockedError(
                GateBlocked(
                    product_id=self.product_id,
                    gate_id=self.current_gate,
                    unsatisfied=tuple(unsatisfied),
                )
            )

        opened = self.current_gate
        events: list[LaunchEvent] = [
            GateOpened(product_id=self.product_id, gate_id=opened)
        ]
        if opened == _GRADUATION_GATE:
            self._graduated = True
            approval = self._approvals[_GRADUATION_GATE]
            assert approval.posture is not None  # enforced by approve_gate
            events.append(
                LaunchGraduated(
                    product_id=self.product_id,
                    posture=approval.posture,
                    approver=approval.approver,
                )
            )
        else:
            position = GATE_SEQUENCE.index(opened)
            self.current_gate = GATE_SEQUENCE[position + 1]
        return tuple(events)

    def move_launch_date(self, new_date: date) -> tuple[LaunchEvent, ...]:
        """Move the launch date. Every timing anchor re-resolves at once
        from the new date — due periods are always derived, never stored,
        so the move itself is the whole cascade."""
        previous = self.launch_date
        self.launch_date = new_date
        return (
            LaunchDateMoved(
                product_id=self.product_id, previous=previous, new=new_date
            ),
        )

    # -- derivations --------------------------------------------------------

    def due_period_for(
        self, playbook: LaunchPlaybook, step_id: str
    ) -> AnchorPeriod | None:
        """The step's due period, derived from the launch date and the
        step's timing anchor — absent when the launch has no date, and
        absent for recurring anchors, which carry a cadence rather than a
        due date."""
        step = self._defined_step(playbook, step_id)
        if self.launch_date is None:
            return None
        return step.timing_anchor.resolve(self.launch_date)

    def date_at_risk(
        self, playbook: LaunchPlaybook, as_of: date
    ) -> LaunchDateAtRisk | None:
        """Evaluated as of `as_of` (the clock never lives here): the date
        is at risk exactly when a blocking step's due period has fully
        passed and the step has not reached a permitted terminal
        outcome."""
        if self.launch_date is None:
            return None
        blocking = {step.identifier for step in playbook.served_steps if step.blocking}
        overdue = tuple(
            step_id
            for step_id in self.overdue_step_ids(playbook, as_of)
            if step_id in blocking
        )
        if not overdue:
            return None
        return LaunchDateAtRisk(
            product_id=self.product_id,
            launch_date=self.launch_date,
            overdue_steps=overdue,
        )

    def overdue_step_ids(
        self, playbook: LaunchPlaybook, as_of: date
    ) -> tuple[str, ...]:
        """Every step whose due period has fully passed as of `as_of`
        without the step reaching a permitted terminal outcome — blocking
        and non-blocking alike.

        Which outcomes are *permitted* depends on the step's hazard (a
        `prohibited-tactic` step terminates in `Refused` and is resolved
        by it), so this judgement can only be made where the playbook is
        — which is why it is answered here rather than left to whoever
        reads a report. `date_at_risk` is this, narrowed to blocking
        steps.

        **A step whose start gate the launch has not reached is not
        overdue**, whatever its due period says. Nobody has been asked for
        the work — it is not projected as a task and its handler is not
        invoked — so there is nothing anyone has failed to do, and a
        launch delayed at an early gate would otherwise accrue overdue
        marks against the whole plan ahead of it.

        **The exclusion turns on the start gate alone, and never on
        `has_released`.** A step the launch has reached but which waits on
        an unresolved dependency stays overdue: it is a delay *within*
        work the launch has arrived at, the dependency holding it may not
        itself be overdue or even blocking, and nothing else in the report
        would say so. Excluding it would mean the later a dependency ran,
        the quieter the report became — and a launch stalled behind one
        would report healthy.
        """
        if self.launch_date is None:
            return ()
        standing = gate_position(self.current_gate)
        return tuple(
            step.identifier
            for step in playbook.served_steps
            if (standing is None or standing >= start_position_of(step))
            and self._fully_passed(step, as_of)
            and not self._resolved(step)
        )

    def awaiting_confirmation(self, playbook: LaunchPlaybook) -> bool:
        """Whether the current gate is held open only by a human decision.

        True exactly when the gate requires confirmation, every blocking
        condition attached to it is already satisfied, and no *approving*
        approval is recorded — a rejecting decision leaves the gate still
        waiting on a confirmation, which is what makes it reportable.

        A graduated launch is never awaiting anything: `graduated` is the
        last gate, and the launch stays there once it opens.
        """
        if self._graduated or not self._requires_confirmation(playbook):
            return False
        if self._unsatisfied_gate_conditions(playbook):
            return False
        approval = self._approvals.get(self.current_gate)
        return approval is None or approval.decision is not ApprovalDecision.APPROVING

    # -- internals ----------------------------------------------------------

    # No pinned-version guard exists any more, on purpose
    # (`move-playbook-steps-to-postgres`): the playbook is live and the
    # recorded version identifier is an audit stamp — "no subsequent read
    # of the playbook branches on it" — so a launch stamped under an
    # earlier definition is evaluated against whatever set is served now.

    def _defined_step(self, playbook: LaunchPlaybook, step_id: str) -> StepDefinition:
        for step in playbook.served_steps:
            if step.identifier == step_id:
                return step
        raise LaunchError(
            f"the pinned playbook version '{self.playbook_version}' defines "
            f"no step '{step_id}'"
        )

    def _authored_conditions(
        self, playbook: LaunchPlaybook, gate_id: str
    ) -> tuple[MetricCondition, ...]:
        return tuple(
            condition
            for gate in playbook.gates
            if gate.identifier == gate_id
            for condition in gate.metric_conditions
        )

    def unsatisfied_conditions(self, playbook: LaunchPlaybook) -> list[str]:
        """Names of the current gate's unsatisfied conditions, the missing
        approval included — empty exactly when the gate may open.

        Public, and `advance-gates-and-confirm-in-slack` is the only reason
        it is: a pass that advances launches must be able to ask whether a
        gate may open *before* commanding the advance, because a refused
        advance is journaled and a pass that commanded blindly would bury
        the launch journal under its own refusals.

        Deliberately the same computation `advance_gate` decides on, rather
        than a second one alongside it. Two computations of "may this gate
        open" are two things to keep in agreement, and the one place they
        could disagree is the one place it matters.

        A read: it inspects nothing a caller could not already reach
        through the recorded outcomes, attestations and approvals, and it
        changes nothing."""
        unsatisfied = self._unsatisfied_gate_conditions(playbook)

        if self._requires_confirmation(playbook):
            approval = self._approvals.get(self.current_gate)
            if approval is None:
                unsatisfied.append("a recorded approval")
            elif approval.decision is not ApprovalDecision.APPROVING:
                unsatisfied.append("an approving approval (decision is rejecting)")
        return unsatisfied

    def _unsatisfied_gate_conditions(self, playbook: LaunchPlaybook) -> list[str]:
        """The same names, approval excluded — the gate's own conditions.

        Separate from `unsatisfied_conditions` because
        `awaiting_confirmation` asks precisely the question this answers:
        is everything *except* the human decision already satisfied?
        """
        unsatisfied: list[str] = []
        for condition in playbook.conditions_for_gate(self.current_gate):
            if isinstance(condition, StepObligation):
                progress = self._step_progress.get(condition.step_id)
                resolved = progress is not None and _outcome_type(progress.outcome) in (
                    Satisfied,
                    NotApplicable,
                )
                if not resolved:
                    unsatisfied.append(f"blocking step '{condition.step_id}'")
            else:
                attested = any(
                    attestation.gate_id == self.current_gate
                    and attestation.metric_id == condition.metric_id
                    for attestation in self._attestations
                )
                if not attested:
                    unsatisfied.append(
                        f"metric condition '{condition.metric_id.value}'"
                    )
        return unsatisfied

    def _requires_confirmation(self, playbook: LaunchPlaybook) -> bool:
        for gate in playbook.gates:
            if gate.identifier == self.current_gate:
                return gate.opening is GateOpening.REQUIRES_CONFIRMATION
        return False

    def _fully_passed(self, step: StepDefinition, as_of: date) -> bool:
        assert self.launch_date is not None  # guarded by date_at_risk
        period = step.timing_anchor.resolve(self.launch_date)
        # A recurring anchor has no due period; an open-ended one never
        # fully passes.
        return period is not None and period.end is not None and period.end < as_of

    def has_released(self, playbook: LaunchPlaybook, step: StepDefinition) -> bool:
        """Whether this launch has released `step` — whether the work may
        begin, which is a different question from whether the step's gate
        may open.

        Two authored facts decide it: the launch must have reached the
        step's start gate, and every step it waits on must be resolved.
        A step declaring neither is released from the first gate, which is
        every step until an author says otherwise.

        **Compared by position, at or beyond, and never by equality.** A
        step whose gate the launch has already passed and which is not yet
        resolved stays released, because work left unfinished at a gate the
        launch has left is exactly the work that must still be done.
        Equality here would abandon every unfinished step the moment its
        gate was left — which for the `listable` gate is most of the
        playbook.

        **No clock, and no timing anchor.** An anchor states when work is
        *due*; whether it may *begin* is this. A rule reading the date
        would make a step's eligibility differ between two passes that
        differ only in when they ran.

        This governs what the system **asks for** — the projection into a
        task tracker and the invocation of a handler — and never what it
        accepts or evaluates. Recording an outcome is outside it: work a
        person completed early is work done. Gate opening is outside it
        too, and that one matters more: `unsatisfied_conditions` turns on
        recorded outcomes alone, and gating a blocking condition on
        release would open a gate over work that had merely not been asked
        for yet.
        """
        standing = gate_position(self.current_gate)
        if standing is None:  # pragma: no cover - constructor forbids it
            return False
        if standing < start_position_of(step):
            return False
        defined = {held.identifier: held for held in playbook.authored_steps}
        return all(
            self._counts_against_release(defined.get(named))
            is not True  # a dependency that does not count cannot hold
            or self._resolved(defined[named])
            for named in step.after_steps
        )

    def _counts_against_release(self, named: StepDefinition | None) -> bool:
        """Whether a named dependency is something this launch is still
        owed, and so may hold its dependent back.

        Three cases fall the same way and are stated together because a
        release predicate must excuse all three or none: a name no step
        answers to, a step no longer `active`, and a step classified
        `prohibited-tactic`. None is something anybody is waiting for — the
        first was never a step, the second is not part of the launch's
        obligations at all, and the third the system has undertaken to
        decline.

        The alternative — holding a dependent until such a step reaches an
        outcome — freezes it for ever, on every launch in flight, as the
        consequence of one routine authoring action.
        """
        if named is None:
            return False
        if named.status is not StepStatus.ACTIVE:
            return False
        return named.hazard is not Hazard.PROHIBITED_TACTIC

    def _resolved(self, step: StepDefinition) -> bool:
        progress = self._step_progress.get(step.identifier)
        if progress is None:
            return False
        return _outcome_type(progress.outcome) in permissible_terminal_outcomes(
            step.hazard
        )
