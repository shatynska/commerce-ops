"""The launch-playbook domain model: gates, step definitions, timing anchors.

Pure domain code — no I/O, no framework, no YAML. `LaunchPlaybook` enforces
its own coherence at construction; a driven adapter (see
`products.infrastructure.driven.playbook_loader`) is responsible for turning
a file into the values this module's constructors expect, not for
re-implementing any of the rules below.

**Timing-anchor convention.** Every offset is relative to the marketing
launch date, which is offset zero: the launch day itself is offset 0, the
day before it is offset -1, the day after it is offset 1. This is
zero-based, whereas the external reference material this playbook is built
from numbers days from one (its "Day 1" is our offset 0). A reference
`T-N` value transcribes directly to offset -N; a reference `Day N` value
transcribes to offset N-1. Getting this shift wrong produces a uniform
one-day drift across every post-launch anchor that is invisible by
inspection — see `design.md`'s transcription table for the full mapping.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum


class InvalidPlaybookError(ValueError):
    """A playbook (or a step definition within one) fails coherence.

    Carries every fault found in one load attempt, not just the first, so a
    large playbook does not have to be corrected one error at a time.
    """

    def __init__(self, faults: Sequence[str]) -> None:
        self.faults: tuple[str, ...] = tuple(faults)
        super().__init__("; ".join(self.faults))


class Track(Enum):
    """The discipline whose expertise a step belongs to.

    A closed set of twelve, taken from the reference material's own AGENT
    column. Deliberately a weaker closure than the gate sequence: adding a
    thirteenth discipline later costs one member, not a structural change.
    """

    STRATEGY = "strategy"
    FINANCE = "finance"
    SETUP = "setup"
    INVENTORY = "inventory"
    CREATIVE = "creative"
    LISTING = "listing"
    RANK = "rank"
    PRICE = "price"
    PPC = "ppc"
    CUSTOMER = "customer"
    EXTERNAL = "external"
    TRAFFIC = "traffic"


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
class Gate:
    """A commitment point in the launch's ordering spine."""

    identifier: str
    position: int
    opening: GateOpening


@dataclass(frozen=True, slots=True)
class StepDefinition:
    """A single unit of launch work, resolved before a gate opens."""

    identifier: str
    gate: str
    track: Track
    scope: Scope
    timing_anchor: TimingAnchor
    binding: Binding
    blocking: bool
    execution: ExecutionMode
    hazard: Hazard = Hazard.NONE
    rule_policy: str | None = None
    provenance: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.track, Track):
            raise InvalidPlaybookError(
                [f"step '{self.identifier}' declares unrecognised track '{self.track}'"]
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
        if step.hazard is Hazard.PROHIBITED_TACTIC and step.blocking:
            faults.append(
                f"step '{step.identifier}' is classified 'prohibited-tactic' "
                f"and cannot block its gate"
            )
    return faults


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

    def steps_with_scope(self, scope: Scope) -> tuple[StepDefinition, ...]:
        return tuple(step for step in self.steps if step.scope is scope)
