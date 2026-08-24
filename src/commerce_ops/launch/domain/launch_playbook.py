"""The launch-playbook domain model: gates, step definitions, timing anchors.

Pure domain code — no I/O, no framework, no YAML. `LaunchPlaybook` enforces
its own coherence at construction; a driven adapter (see
`launch.infrastructure.driven.playbook_loader`) is responsible for turning
a file into the values this module's constructors expect, not for
re-implementing any of the rules below.

**Timing-anchor convention.** Every offset is relative to the marketing
launch date, which is offset zero: the launch day itself is offset 0, the
day before it is offset -1, the day after it is offset 1.

This convention is **zero-based**, and that is the whole hazard. Source
material for launch plans is conventionally one-based — a "Day 1" that
means the launch day, not the day after it — so a plan transcribed here
without adjusting shifts every post-launch anchor by one day. The drift is
uniform, so nothing looks obviously wrong; it is invisible by inspection
and shows up only as work scheduled a day late, forever.

The full mapping, so it need not be reconstructed:

    a "T-N" (countdown) value  ->  offset -N        (T-90 -> -90)
    the launch day itself      ->  offset 0
    a one-based "Day N" value  ->  offset N - 1     (Day 1 -> 0, Day 7 -> 6)

Countdown values transcribe directly because they are already relative to
the launch day; only the one-based forward count needs the -1.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum

from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId


class InvalidPlaybookError(ValueError):
    """A playbook (or a step definition within one) fails coherence.

    Carries every fault found in one load attempt, not just the first, so a
    large playbook does not have to be corrected one error at a time.
    """

    def __init__(self, faults: Sequence[str]) -> None:
        self.faults: tuple[str, ...] = tuple(faults)
        super().__init__("; ".join(self.faults))


class Scope(Enum):
    """Whether a step concerns the product itself, or one marketplace."""

    PRODUCT = "product"
    MARKET = "market"


class Binding(Enum):
    """Whether a step is a rule the launch is held to, or advice."""

    FRAMEWORK = "framework"
    LESSON = "lesson"


class ExecutionMode(Enum):
    """How a step is resolved."""

    AUTOMATED = "automated"
    AI_ASSISTED = "ai-assisted"
    HUMAN_ATTESTED = "human-attested"


class Hazard(Enum):
    """Terms-of-service exposure a step carries.

    `PROHIBITED_TACTIC`'s only terminal state is refusal, so it can never
    be satisfied and therefore can never be marked as blocking a gate.
    `COMPLIANCE_OBLIGATION` can be satisfied and may block freely.
    """

    NONE = "none"
    PROHIBITED_TACTIC = "prohibited-tactic"
    COMPLIANCE_OBLIGATION = "compliance-obligation"


class GateOpening(Enum):
    """Whether a gate opens automatically or requires human confirmation."""

    AUTOMATIC = "automatic"
    REQUIRES_CONFIRMATION = "requires-confirmation"


@dataclass(frozen=True, slots=True)
class NotStarted:
    """The step has not been taken up."""


@dataclass(frozen=True, slots=True)
class InProgress:
    """The step is being worked."""


@dataclass(frozen=True, slots=True)
class Satisfied:
    """The step's acceptance criterion holds."""


@dataclass(frozen=True, slots=True)
class Blocked:
    """The step awaits something outside itself. Not a resolution."""

    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("a Blocked outcome requires a non-empty reason")


@dataclass(frozen=True, slots=True)
class Refused:
    """The step was recognised as a prohibited tactic and refused."""


@dataclass(frozen=True, slots=True)
class NotApplicable:
    """The step does not apply here — absent and inapplicable differ."""

    reason: str

    def __post_init__(self) -> None:
        if not self.reason:
            raise ValueError("a NotApplicable outcome requires a non-empty reason")


StepOutcome = NotStarted | InProgress | Satisfied | Blocked | Refused | NotApplicable
"""The vocabulary a step's resolution is expressed in — an outcome, not a
boolean, because "missing is not fine". Recording and transitioning
outcomes at runtime belongs to the launch-instance capability (domain-map
slice 3); this module only defines what the outcomes are and which are
permitted as terminal."""


def permissible_terminal_outcomes(hazard: Hazard) -> frozenset[type[StepOutcome]]:
    """Which outcomes are permitted as terminal for a step with `hazard`.

    Complete over all six outcomes: a `prohibited-tactic` step can only
    terminate in `Refused`; any other step terminates in `Satisfied` or
    `NotApplicable` and can never be `Refused`. `NotStarted`, `InProgress`
    and `Blocked` are never terminal — a blocked step awaits resolution,
    it has not reached one.
    """
    if hazard is Hazard.PROHIBITED_TACTIC:
        return frozenset({Refused})
    return frozenset({Satisfied, NotApplicable})


class Cadence(Enum):
    """How often a recurring timing anchor's obligation repeats."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


@dataclass(frozen=True, slots=True)
class AnchorPeriod:
    """A resolved timing anchor: a start date, and an end date if bounded."""

    start: date
    end: date | None


@dataclass(frozen=True, slots=True)
class OffsetAnchor:
    """A single day, relative to the launch date."""

    days: int

    def resolve(self, launch_date: date) -> AnchorPeriod:
        day = launch_date + timedelta(days=self.days)
        return AnchorPeriod(start=day, end=day)


@dataclass(frozen=True, slots=True)
class WindowAnchor:
    """A bounded span between two offsets, relative to the launch date."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(
                f"window anchor end offset {self.end} precedes its start "
                f"offset {self.start}"
            )

    def resolve(self, launch_date: date) -> AnchorPeriod:
        return AnchorPeriod(
            start=launch_date + timedelta(days=self.start),
            end=launch_date + timedelta(days=self.end),
        )


@dataclass(frozen=True, slots=True)
class OpenEndedAnchor:
    """A start offset with no end: an obligation that does not expire."""

    start: int

    def resolve(self, launch_date: date) -> AnchorPeriod:
        return AnchorPeriod(start=launch_date + timedelta(days=self.start), end=None)


@dataclass(frozen=True, slots=True)
class RecurringAnchor:
    """A fixed cadence rather than a due date."""

    cadence: Cadence

    def resolve(self, launch_date: date) -> AnchorPeriod | None:
        return None


TimingAnchor = OffsetAnchor | WindowAnchor | OpenEndedAnchor | RecurringAnchor


@dataclass(frozen=True, slots=True)
class MetricCondition:
    """An authored gate condition: an observation must satisfy a threshold.

    The `MetricId` is a reference only — no metric registry exists yet
    (domain-map slice 7), and until one does, whether the condition holds
    is established by human attestation recorded against a launch (a
    launch-instance concern). The threshold is a human-readable
    description; that it is non-empty is a playbook coherence rule
    (enforced at load, naming the gate), not a constructor rule, so that
    a malformed authored condition reports where it was authored.
    """

    metric_id: MetricId
    threshold: str


@dataclass(frozen=True, slots=True)
class StepObligation:
    """A derived gate condition: a blocking step must be resolved.

    Never authored — derived from a step definition's own gate and
    blocking declarations, so a blocking fact exists in exactly one place.
    """

    step_id: str


GateCondition = StepObligation | MetricCondition
"""One thing a gate waits on: a blocking step's resolution, or a metric
observation satisfying a threshold."""


@dataclass(frozen=True, slots=True)
class Gate:
    """A commitment point in the launch's ordering spine."""

    identifier: str
    position: int
    opening: GateOpening
    metric_conditions: tuple[MetricCondition, ...] = ()


@dataclass(frozen=True, slots=True)
class StepDefinition:
    """A single unit of launch work, resolved before a gate opens."""

    identifier: str
    description: str
    gate: str
    discipline: Discipline
    scope: Scope
    timing_anchor: TimingAnchor
    binding: Binding
    blocking: bool
    execution: ExecutionMode
    hazard: Hazard = Hazard.NONE
    rule_policy: str | None = None
    provenance: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.discipline, Discipline):
            raise InvalidPlaybookError(
                [
                    (
                        f"step '{self.identifier}' declares unrecognised "
                        f"discipline '{self.discipline}'"
                    )
                ]
            )


# The gate sequence this specification fixes: identifier, position (1-based,
# matching the numbered list in the spec) and required opening mode. This is
# the target every loaded playbook's gate sequence is checked against.
_SPECIFIED_GATES: tuple[tuple[str, GateOpening], ...] = (
    ("commit", GateOpening.REQUIRES_CONFIRMATION),
    ("order", GateOpening.REQUIRES_CONFIRMATION),
    ("listable", GateOpening.AUTOMATIC),
    ("stock-ready", GateOpening.AUTOMATIC),
    ("live", GateOpening.AUTOMATIC),
    ("ignition", GateOpening.AUTOMATIC),
    ("phase-one-complete", GateOpening.REQUIRES_CONFIRMATION),
    ("graduated", GateOpening.REQUIRES_CONFIRMATION),
)
_SPECIFIED_GATE_IDS: tuple[str, ...] = tuple(
    identifier for identifier, _ in _SPECIFIED_GATES
)

GATE_SEQUENCE: tuple[str, ...] = _SPECIFIED_GATE_IDS
"""The eight gate identifiers in their fixed order — public, because the
launch-instance side (`launch_run`) validates and advances against the
same sequence this specification fixes."""


def _gate_sequence_faults(gates: tuple[Gate, ...]) -> list[str]:
    faults: list[str] = []
    actual_ids = {gate.identifier for gate in gates}
    specified_ids = set(_SPECIFIED_GATE_IDS)

    extra = actual_ids - specified_ids
    missing = specified_ids - actual_ids
    for identifier in sorted(extra):
        faults.append(f"gate sequence: unexpected gate '{identifier}'")
    for identifier in sorted(missing):
        faults.append(f"gate sequence: missing gate '{identifier}'")
    if extra or missing:
        return faults

    by_identifier = {gate.identifier: gate for gate in gates}
    for position, (identifier, expected_opening) in enumerate(
        _SPECIFIED_GATES, start=1
    ):
        gate = by_identifier[identifier]
        if gate.position != position:
            faults.append(
                f"gate sequence: '{identifier}' is at position {gate.position}, "
                f"expected position {position}"
            )
        if gate.opening is not expected_opening:
            faults.append(
                f"gate '{identifier}' opening mode is '{gate.opening.value}', "
                f"expected '{expected_opening.value}'"
            )
    return faults


def _step_faults(
    gates: tuple[Gate, ...], steps: tuple[StepDefinition, ...]
) -> list[str]:
    faults: list[str] = []
    gate_ids = {gate.identifier for gate in gates}

    seen: dict[str, int] = {}
    for step in steps:
        seen[step.identifier] = seen.get(step.identifier, 0) + 1
    for identifier, count in seen.items():
        if count > 1:
            faults.append(f"duplicate step identifier '{identifier}'")

    for step in steps:
        if step.gate not in gate_ids:
            faults.append(
                f"step '{step.identifier}' declares unknown gate '{step.gate}'"
            )
        if (
            step.execution in (ExecutionMode.AUTOMATED, ExecutionMode.AI_ASSISTED)
            and step.rule_policy is None
        ):
            faults.append(
                f"step '{step.identifier}' has execution mode "
                f"'{step.execution.value}' but no rule policy"
            )
        if not step.description.strip():
            faults.append(
                f"step '{step.identifier}' has an empty description — a step "
                f"whose work cannot be read from the step itself is "
                f"indistinguishable from one nobody wrote down"
            )
        elif "\n" in step.description or "\r" in step.description:
            faults.append(
                f"step '{step.identifier}' has a description spanning more "
                f"than one line — a description is composed into a task's "
                f"name, and a name is a single line"
            )
        if step.hazard is Hazard.PROHIBITED_TACTIC and step.blocking:
            faults.append(
                f"step '{step.identifier}' is classified 'prohibited-tactic' "
                f"and cannot block its gate"
            )
        if step.binding is Binding.LESSON and step.blocking:
            faults.append(
                f"step '{step.identifier}' has binding 'lesson' and cannot "
                f"block its gate — advice that blocks a gate the way a "
                f"framework rule does is a category error"
            )
    return faults


def _gate_condition_faults(gates: tuple[Gate, ...]) -> list[str]:
    return [
        f"gate '{gate.identifier}' authors a metric condition "
        f"('{condition.metric_id.value}') with an empty threshold description"
        for gate in gates
        for condition in gate.metric_conditions
        if not condition.threshold
    ]


@dataclass(frozen=True, slots=True)
class LaunchPlaybook:
    """The definition of an Amazon product launch: gates and step definitions.

    Aggregate root. Coherence is enforced here, at construction — not by the
    loader that builds one from a file — because these are domain
    invariants that hold regardless of where a playbook came from.
    """

    version: str
    gates: tuple[Gate, ...]
    steps: tuple[StepDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        faults = [
            *_gate_sequence_faults(self.gates),
            *_gate_condition_faults(self.gates),
            *_step_faults(self.gates, self.steps),
        ]
        if faults:
            raise InvalidPlaybookError(faults)
        # A coherent playbook's gates are exactly the eight specified
        # identifiers each at their specified position, so sorting here is
        # equivalent to already being in spec order — done anyway so the
        # order read back does not depend on the order a caller supplied.
        object.__setattr__(
            self, "gates", tuple(sorted(self.gates, key=lambda gate: gate.position))
        )

    def steps_for_gate(self, gate_identifier: str) -> tuple[StepDefinition, ...]:
        return tuple(step for step in self.steps if step.gate == gate_identifier)

    def conditions_for_gate(self, gate_identifier: str) -> tuple[GateCondition, ...]:
        """Everything the gate waits on, as one collection of two kinds.

        Step obligations are derived — one per blocking step attached to
        the gate, never authored a second time on the gate itself — and
        the gate's authored metric conditions follow them.
        """
        obligations = tuple(
            StepObligation(step_id=step.identifier)
            for step in self.steps
            if step.gate == gate_identifier and step.blocking
        )
        authored = tuple(
            condition
            for gate in self.gates
            if gate.identifier == gate_identifier
            for condition in gate.metric_conditions
        )
        return obligations + authored

    def steps_with_scope(self, scope: Scope) -> tuple[StepDefinition, ...]:
        return tuple(step for step in self.steps if step.scope is scope)
