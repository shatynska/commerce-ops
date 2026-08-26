"""The launch-playbook domain model: gates, step definitions, timing anchors.

Pure domain code — no I/O, no framework, no YAML. `LaunchPlaybook` enforces
its own coherence at construction; a driven adapter (see
`launch.infrastructure.driven.playbook_repository`) is responsible for
turning stored rows into the values this module's constructors expect,
not for re-implementing any of the rules below.

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

from collections.abc import Collection, Sequence
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


class PlaybookNotReadyError(RuntimeError):
    """The playbook is coherent but cannot hold a launch: some gate has no
    `active` blocking step.

    Deliberately **not** an `InvalidPlaybookError`. A consumer has to be
    able to tell "this playbook is broken and someone should be paged"
    from "this playbook is still being written and will serve once it is
    finished" — the first is a defect, the second is an expected stage of
    a system being set up, and collapsing them makes a bootstrap look like
    an outage.

    It carries the playbook as well as the gates. A consumer that is
    declining to act may still owe an obligation that turns on what the
    set contains — `launch-clickup-sync`'s webhook intake owes opposite
    treatments to a served and a non-served step's task — and a refusal
    carrying only gate names would force it to take a second read or to
    guess. The carried playbook is for **classifying** the set only: it
    must never be used to advance, project or report on a launch, which is
    the very thing the refusal withheld it from.
    """

    def __init__(self, *, playbook: LaunchPlaybook, gates: Sequence[str]) -> None:
        # Taken as `gates` and read back as `unheld_gates`: inside an error
        # whose whole subject is the unheld ones the shorter name is
        # unambiguous, while at a read site far from here it is not.
        self.playbook = playbook
        self.unheld_gates: tuple[str, ...] = tuple(gates)
        super().__init__(
            "the playbook cannot hold a launch: "
            + ", ".join(unheld_gate_fault(gate) for gate in self.unheld_gates)
        )


class Scope(Enum):
    """Whether a step concerns the product itself, or one marketplace."""

    PRODUCT = "product"
    MARKET = "market"


class StepKind(Enum):
    """Who does a step's work: a person, or code.

    Deliberately not a record of *how* the code works. Whether the
    resolving code calls a language model is an implementation detail of
    that code and no rule in this system reacts to it; what the launch
    reacts to is whether a person must accept the result, which
    `StepDefinition.needs_confirmation` carries as a separate fact.
    """

    HUMAN = "human"
    AUTOMATED = "automated"


class StepStatus(Enum):
    """How far a step has been carried, and therefore what may be done
    with it.

    Only `ACTIVE` steps are served to a launch, hold a gate, or reach a
    task tracker; the rest are visible to whoever authors the step set
    and to nobody else. This is what lets an author write work down
    before its automation exists, rather than inventing a description of
    code nobody has written.

    Any status may move to any other: each move is a write validated by
    the rules of the status it moves *to*, so there is no transition
    table and no ordering a step must climb.
    """

    DRAFT = "draft"
    IN_DEVELOPMENT = "in-development"
    ACTIVE = "active"
    RETIRED = "retired"


BEYOND_DRAFT: frozenset[StepStatus] = frozenset(
    {StepStatus.IN_DEVELOPMENT, StepStatus.ACTIVE}
)
"""What "beyond `draft`" means, and deliberately not "any status other
than `draft`": a step abandoned before its automation was ever specified
is retired without ever owing a brief. Reading the phrase the other way
would make such a step unretirable and its playbook unloadable."""


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
    """A single unit of launch work, resolved before a gate opens.

    `name` and `description` answer to two audiences and are two fields
    for that reason: the name is what a person scans in a list of work
    and is composed into a task's name, so it is required and occupies a
    single line; the description is what they read once they have
    decided to do it, so it is optional and may span lines.

    `assignees` reference roster people by the roster's own generated
    identifier, never by name or Slack identity, so that correcting a
    person's details never rewrites the steps pointing at them. That an
    assignee exists and is active is a *write-time* precondition and
    never a load-time rule — see `assignee_faults`.
    """

    identifier: str
    name: str
    gate: str
    discipline: Discipline
    scope: Scope
    timing_anchor: TimingAnchor
    blocking: bool
    kind: StepKind
    description: str | None = None
    needs_confirmation: bool = False
    status: StepStatus = StepStatus.DRAFT
    hazard: Hazard = Hazard.NONE
    assignees: tuple[str, ...] = ()
    automation_brief: str | None = None
    handler: str | None = None
    provenance: str | None = None

    def __post_init__(self) -> None:
        # Normalised so a caller handing a list gets value semantics: the
        # definition is frozen and compared by value, and a mutable
        # member would defeat both.
        object.__setattr__(self, "assignees", tuple(self.assignees))
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

# The metric conditions each gate authors — framework data, code-owned like
# the sequence and the opening modes. `move-playbook-steps-to-postgres`
# moved the *steps* into the database and deliberately left the gates here:
# a manager edits steps, never the framework.
_AUTHORED_METRIC_CONDITIONS: dict[str, tuple[MetricCondition, ...]] = {
    "stock-ready": (
        MetricCondition(
            MetricId("units-fulfillable"),
            "60–80 fulfillable units, excluding Vine",
        ),
    ),
    "phase-one-complete": (
        MetricCondition(MetricId("sales-velocity"), "~10 units/day sustained"),
        MetricCondition(MetricId("organic-share"), "organic share above 40%"),
    ),
    "graduated": (
        MetricCondition(MetricId("tacos"), "TACOS falling"),
        MetricCondition(MetricId("review-rating"), "rating stable at 4.5"),
    ),
}


def framework_gates() -> tuple[Gate, ...]:
    """The eight gates exactly as this specification fixes them — sequence,
    opening modes, and authored metric conditions.

    The one construction every served playbook and every write validation
    uses, so "code-owned framework" is a single definition rather than a
    convention."""
    return tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=opening,
            metric_conditions=_AUTHORED_METRIC_CONDITIONS.get(identifier, ()),
        )
        for position, (identifier, opening) in enumerate(_SPECIFIED_GATES, start=1)
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
        if not step.name or not step.name.strip():
            faults.append(
                f"step '{step.identifier}' has an empty name — a step whose "
                f"work cannot be read from the step itself is "
                f"indistinguishable from one nobody wrote down"
            )
        elif "\n" in step.name or "\r" in step.name:
            faults.append(
                f"step '{step.identifier}' has a name spanning more than one "
                f"line — a name is composed into a task's name, and a name "
                f"is a single line"
            )
        faults.extend(_automation_faults(step))
        if step.hazard is Hazard.PROHIBITED_TACTIC and step.blocking:
            faults.append(
                f"step '{step.identifier}' is classified 'prohibited-tactic' "
                f"and cannot block its gate"
            )
    return faults


def _automation_faults(step: StepDefinition) -> list[str]:
    """What a step's kind and status oblige it to carry, or to leave off.

    The brief is owed on leaving `draft` — a step nobody can state the
    acceptance criterion for is not ready to be built — and the handler
    on becoming `active`. That a handler is *present* is a property of
    the step set and belongs here; that the deployed code **registers**
    it is a property of the deployment, checked at activation and never
    at load, so a rename in the registry reports a deployment fault
    rather than making every stored playbook unloadable.
    """
    faults: list[str] = []
    if step.kind is StepKind.AUTOMATED:
        if step.status in BEYOND_DRAFT and step.automation_brief is None:
            faults.append(
                f"step '{step.identifier}' is automated and beyond draft "
                f"(status '{step.status.value}') but carries no automation "
                f"brief"
            )
        if step.status is StepStatus.ACTIVE and step.handler is None:
            faults.append(
                f"step '{step.identifier}' is automated and active but names "
                f"no handler — nothing would resolve it"
            )
        return faults
    if step.automation_brief is not None:
        faults.append(
            f"step '{step.identifier}' is a human step and cannot carry an "
            f"automation brief"
        )
    if step.handler is not None:
        faults.append(
            f"step '{step.identifier}' is a human step and cannot name a handler"
        )
    return faults


def _unheld_gates(
    gates: tuple[Gate, ...], steps: tuple[StepDefinition, ...]
) -> tuple[str, ...]:
    """The gates holding no `active` blocking step, in gate-sequence order.

    The gate-holding floor was a construction rule until
    `serve-only-a-ready-playbook`, which found it to be the wrong kind of
    rule for the place it sat in. Its subject is not whether the step set
    is internally consistent — every other rule in the constructor answers
    that — but whether the set is *complete enough to hold a launch*. As a
    construction rule it made an all-`draft` set unrepresentable, and
    unrepresentable in a way no sequence of writes could climb out of,
    since write validation reconstructs the whole candidate set.

    So it is a computation now rather than a fault, and the two places
    that care ask it directly: the serving read refuses a set that leaves
    a gate unheld, and the write path refuses a write that would leave one
    unheld *in a set that is already ready*.
    """
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    return tuple(gate.identifier for gate in gates if gate.identifier not in held)


def unheld_gates_of(steps: Sequence[StepDefinition]) -> tuple[str, ...]:
    """The framework gates that `steps` leaves without an `active` blocking
    step.

    Public so the write path can ask the question without constructing an
    aggregate purely to ask it — which matters because the candidate set a
    write is judging may not be constructible at all, and the ratchet's
    answer is wanted alongside whatever coherence faults it carries rather
    than instead of them.
    """
    return _unheld_gates(framework_gates(), tuple(steps))


def unheld_gate_fault(gate_identifier: str) -> str:
    """The wording a gate-holding refusal carries, in one place.

    Kept verbatim from when this was a construction fault, deliberately:
    the admin surface matches it by substring to attribute the refusal to
    a field (`playbook_admin._CROSSINGS`), so rewording it would silently
    turn an attributed fault into an unattributed one.
    """
    return (
        f"gate '{gate_identifier}' has no active blocking step attached — a "
        f"gate whose step obligations are an empty set opens for free"
    )


def gate_holding_faults(
    prior: tuple[str, ...], candidate: tuple[str, ...]
) -> list[str]:
    """The one-directional gate-holding rule, over a prior and a candidate
    set's unheld gates.

    It is always permitted to move a set toward being served, and never to
    move a served set away from it in one write. So a write is refused for
    leaving a gate unheld **only when the set it started from was itself
    ready** — which is what protects a running launch from losing its
    playbook to a single authoring action, while still letting a set that
    is being built reach readiness one activation at a time.

    Stated here rather than in the application layer so the ratchet is a
    domain rule: the layer above supplies the two sets and reports what
    comes back.
    """
    if prior:
        return []
    return [unheld_gate_fault(gate) for gate in candidate]


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

    @property
    def authored_steps(self) -> tuple[StepDefinition, ...]:
        """Every step the set holds, whatever its status — the read an
        authoring surface uses. Named rather than left to `steps` so a
        caller has to say which set it means."""
        return self.steps

    @property
    def served_steps(self) -> tuple[StepDefinition, ...]:
        """The steps a launch is actually held to: the `active` ones.

        Every query below answers this set, so nothing that advances a
        launch can be handed a draft by accident."""
        return tuple(step for step in self.steps if step.status is StepStatus.ACTIVE)

    @property
    def unheld_gates(self) -> tuple[str, ...]:
        """The gates holding no `active` blocking step, in sequence order.

        Derived on every read and never stored: a stored flag would need
        maintaining on every write and could disagree with the steps it
        summarises, while this is eight set-membership tests over a
        collection already in memory."""
        return _unheld_gates(self.gates, self.steps)

    @property
    def is_ready(self) -> bool:
        """Whether this playbook can hold a launch — that every gate has at
        least one `active` blocking step. Exactly the emptiness of
        `unheld_gates`, which is what the requirement defines readiness
        as."""
        return not self.unheld_gates

    def steps_for_gate(self, gate_identifier: str) -> tuple[StepDefinition, ...]:
        return tuple(step for step in self.served_steps if step.gate == gate_identifier)

    def conditions_for_gate(self, gate_identifier: str) -> tuple[GateCondition, ...]:
        """Everything the gate waits on, as one collection of two kinds.

        Step obligations are derived — one per blocking step attached to
        the gate, never authored a second time on the gate itself — and
        the gate's authored metric conditions follow them.
        """
        obligations = tuple(
            StepObligation(step_id=step.identifier)
            for step in self.served_steps
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
        return tuple(step for step in self.served_steps if step.scope is scope)


def assignee_faults(
    steps: Sequence[StepDefinition],
    *,
    known: Collection[str],
    active: Collection[str],
) -> tuple[str, ...]:
    """The two assignee rules, over the steps a write touches.

    Kept out of `LaunchPlaybook`'s construction deliberately. Every
    load-time coherence rule is a function of the step set alone, which
    is what lets one predicate guard a load and a write alike; whether an
    assignee exists and is active is a function of the *roster*, which
    changes without the step set changing. Were these load-time rules,
    deactivating a person would retroactively make a stored playbook
    unloadable — a write in another module breaking a capability that
    accepted no write.

    The domain cannot read the roster, so the caller supplies the two
    identifier sets and the application layer is what fetches them.
    """
    faults: list[str] = []
    known_ids = set(known)
    active_ids = set(active)
    for step in steps:
        for identifier in step.assignees:
            if identifier not in known_ids:
                faults.append(
                    f"step '{step.identifier}' names assignee '{identifier}', "
                    f"whom the roster does not carry"
                )
        if (
            step.kind is StepKind.HUMAN
            and step.status is StepStatus.ACTIVE
            and not any(identifier in active_ids for identifier in step.assignees)
        ):
            faults.append(
                f"step '{step.identifier}' is an active human step and names "
                f"no assignee who is active on the roster — human work "
                f"nobody is responsible for is work that will not happen"
            )
    return tuple(faults)
