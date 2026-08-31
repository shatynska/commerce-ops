"""Launch use cases: the module's public behavior over its ports.

Implements `launch-instance`'s driving surface for slice 3 (see
`openspec/changes/introduce-launch-aggregate/`): application use cases
only — no HTTP or Slack adapter exists yet (those arrive with the ClickUp
loop and briefing slices). Each command loads the aggregate, loads the
playbook version the launch pinned, invokes the domain command, persists,
and returns the events the domain produced.

Graduation is the one cross-module write: when `advance_gate` opens
`graduated`, the advanced launch is persisted first, then the catalog
product is stamped steady-state through the stamping port — carrying the
posture the graduation approver chose and the approver as the human
confirmer. A stamp the catalog rejects leaves the advance standing and
surfaces as `GraduationStampError` naming the manual catalog correction.

Unknown-product and duplicate-launch rejections on `start_launch` are the
store's own (`launch-instance`'s persistence requirements): the catalog
reference is enforced where the record is kept.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

from commerce_ops.catalog.application import StageTransitionError
from commerce_ops.launch.application.errors import (
    GraduationStampError,
    LaunchNotFoundError,
)
from commerce_ops.launch.application.journal import (
    KIND_ADVANCE_REFUSED,
    KIND_GATE_APPROVAL_RECORDED,
    KIND_GATE_OPENED,
    KIND_LAUNCH_DATE_MOVED,
    KIND_LAUNCH_GRADUATED,
    KIND_LAUNCH_STARTED,
    KIND_METRIC_ATTESTED,
    KIND_STEP_OUTCOME_RECORDED,
    JournalEntry,
    JournalOccurrence,
    compose,
)
from commerce_ops.launch.application.ports import (
    LaunchJournal,
    LaunchStore,
    Playbooks,
    SteadyStateStamper,
)
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    AnchorPeriod,
    Hazard,
    LaunchPlaybook,
    StepDefinition,
    StepStatus,
    gate_position,
    permissible_terminal_outcomes,
    start_position_of,
)
from commerce_ops.launch.domain.launch_run import (
    GateApproval,
    GateBlockedError,
    GateOpened,
    Launch,
    LaunchDateAtRisk,
    LaunchError,
    LaunchEvent,
    LaunchGraduated,
    MetricAttestation,
    Provenance,
    StepOutcomeValue,
    StepProgress,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.domain.lifecycle_stage import SteadyState

_logger = logging.getLogger(__name__)

# The gate whose opening is graduation. Spelled here rather than imported
# from the aggregate's private constant; `launch_run` keeps its own.
_GRADUATION_GATE = "graduated"


async def _journal(journal: LaunchJournal, occurrence: JournalOccurrence) -> None:
    """Append one occurrence, and never let its failure reach the caller.

    Containment is two things, not one (`launch-journal`, "A failed
    append never fails the command it records, nor disturbs its work").
    Catching the exception is the easy half. The half that is easy to
    omit and impossible to do without is the **rollback**: a failed
    INSERT leaves the session refusing every later statement, so a
    command whose work continues past the append — most sharply the
    catalog stamp a graduating advance performs — would fail on a
    session the journal poisoned. That would be the journal breaking a
    graduation: the exact outage this guarantee forbids, caused by the
    mechanism meant to prevent it.

    A rollback that itself raises is caught too. There is nothing
    further this layer can do, and a journal must never be why a launch
    command fails.
    """
    try:
        await journal.append(occurrence)
    except Exception:
        _logger.exception(
            "the launch journal could not record a '%s' occurrence for "
            "product '%s'%s; the command stands, the occurrence is "
            "unrecorded",
            occurrence.kind,
            occurrence.product_id.value,
            f" (subject '{occurrence.subject_id}')" if occurrence.subject_id else "",
        )
        try:
            await journal.rollback()
        except Exception:
            _logger.exception(
                "rolling back after the failed journal append for product "
                "'%s' failed as well; the work following this command may "
                "fail on the same session",
                occurrence.product_id.value,
            )


async def start_launch(
    launches: LaunchStore,
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId,
    launch_date: date | None = None,
    submitter: str | None = None,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    """Start a launch for a catalog product, pinning the given playbook's
    version. The store rejects an unknown product or a second launch."""
    launch, started = Launch.start(
        product_id=product_id,
        playbook=playbook,
        launch_date=launch_date,
        submitter=submitter,
    )
    await launches.save(launch)
    await _journal(
        journal,
        JournalOccurrence(
            product_id=product_id,
            kind=KIND_LAUNCH_STARTED,
            details={"playbook_version": playbook.version},
        ),
    )
    return (started,)


async def record_step_outcome(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    step_id: str,
    outcome: StepOutcomeValue,
    provenance: Provenance,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    events = launch.record_step_outcome(
        playbook, step_id=step_id, outcome=outcome, provenance=provenance
    )
    await launches.save(launch)
    await _journal(
        journal,
        JournalOccurrence(
            product_id=product_id,
            kind=KIND_STEP_OUTCOME_RECORDED,
            occurred_at=provenance.when,
            actor=provenance.who,
            source=provenance.source,
            subject_id=step_id,
            # Captured now, never re-resolved: the entry must stay
            # readable after the step is renamed or retired.
            subject_label=_step_name(playbook, step_id),
            details={
                "outcome": _outcome_name(outcome),
                "reason": getattr(outcome, "reason", None),
                "evidence": provenance.evidence,
            },
        ),
    )
    return events


async def record_metric_attestation(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    attestation: MetricAttestation,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    events = launch.record_metric_attestation(playbook, attestation)
    await launches.save(launch)
    await _journal(
        journal,
        JournalOccurrence(
            product_id=product_id,
            kind=KIND_METRIC_ATTESTED,
            occurred_at=attestation.when,
            actor=attestation.attester,
            # The condition is the subject; the gate it was attested
            # against travels in `details` (design.md Decision 4).
            subject_id=attestation.metric_id.value,
            subject_label=_threshold_for(playbook, attestation),
            details={
                "gate_id": attestation.gate_id,
                "evidence": attestation.evidence,
            },
        ),
    )
    return events


async def approve_gate(
    launches: LaunchStore,
    *,
    product_id: ProductId,
    gate_id: str,
    approval: GateApproval,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    events = launch.approve_gate(gate_id, approval)
    await launches.save(launch)
    await _journal(
        journal,
        JournalOccurrence(
            product_id=product_id,
            kind=KIND_GATE_APPROVAL_RECORDED,
            occurred_at=approval.when,
            actor=approval.approver,
            # A gate's identifier is the whole of its label.
            subject_id=gate_id,
            subject_label=gate_id,
            details={
                "decision": approval.decision.value,
                "posture": approval.posture.value if approval.posture else None,
            },
        ),
    )
    return events


async def advance_gate(
    *,
    launches: LaunchStore,
    playbooks: Playbooks,
    stamp_steady_state: SteadyStateStamper,
    product_id: ProductId,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    """Advance the launch past its current gate. Opening `graduated`
    additionally stamps the catalog product steady-state — after the
    advanced launch is persisted, so a rejected stamp leaves the advance
    standing.

    The journal append sits between the two, deliberately: appending
    after the save means a contained failure can discard nothing of the
    command's own work, and appending before the stamp is what makes the
    guarantee "a failed append does not prevent the graduation stamp"
    something a test can observe at all (design.md Decision 2).
    """
    launch = await _existing(launches, product_id)
    playbook = playbooks.get(launch.playbook_version)
    try:
        events = launch.advance_gate(playbook)
    except GateBlockedError as refused:
        # The most diagnostic thing a launch produces, and the only
        # record of it: unsatisfied conditions are recomputed from
        # current state, so once satisfied nothing can establish that
        # they ever blocked an advance, or when.
        await _journal(
            journal,
            JournalOccurrence(
                product_id=product_id,
                kind=KIND_ADVANCE_REFUSED,
                subject_id=refused.blocked.gate_id,
                subject_label=refused.blocked.gate_id,
                # Stored as the domain composes them — condition names,
                # in a list, identifying a step by identifier. The one
                # stated exception to labels-not-identifiers
                # (design.md Decision 7).
                details={"unsatisfied": list(refused.blocked.unsatisfied)},
            ),
        )
        raise
    await launches.save(launch)

    graduated = next(
        (event for event in events if isinstance(event, LaunchGraduated)), None
    )
    if graduated is not None:
        await _journal(
            journal,
            JournalOccurrence(
                product_id=product_id,
                kind=KIND_LAUNCH_GRADUATED,
                actor=graduated.approver,
                subject_id=_GRADUATION_GATE,
                subject_label=_GRADUATION_GATE,
                details={"posture": graduated.posture.value},
            ),
        )
    else:
        opened = next(
            event.gate_id for event in events if isinstance(event, GateOpened)
        )
        await _journal(
            journal,
            JournalOccurrence(
                product_id=product_id,
                kind=KIND_GATE_OPENED,
                subject_id=opened,
                subject_label=opened,
                details={"standing_at": launch.current_gate},
            ),
        )

    if graduated is not None:
        try:
            await stamp_steady_state(
                launch.product_id,
                SteadyState(posture=graduated.posture),
                confirmed_by=graduated.approver,
            )
        except StageTransitionError as exc:
            raise GraduationStampError(
                f"product '{product_id.value}' ({product_id}) graduated, "
                f"but the catalog rejected the steady-state stamp ({exc}); "
                f"the launch stands at 'graduated' — correct the product's "
                f"stage in the catalog by hand"
            ) from exc
    return events


async def move_launch_date(
    launches: LaunchStore,
    *,
    product_id: ProductId,
    new_date: date,
    journal: LaunchJournal,
) -> tuple[LaunchEvent, ...]:
    launch = await _existing(launches, product_id)
    previous = launch.launch_date
    events = launch.move_launch_date(new_date)
    await launches.save(launch)
    await _journal(
        journal,
        JournalOccurrence(
            product_id=product_id,
            kind=KIND_LAUNCH_DATE_MOVED,
            details={
                "previous": previous.isoformat() if previous else None,
                "new": new_date.isoformat(),
            },
        ),
    )
    return events


@dataclass(frozen=True, slots=True)
class ReportedStep:
    """One step as a launch report carries it: what was recorded, when it
    is due, and the two judgements only the launch context can make.

    Named for the report rather than for "status" since
    `redesign-step-fields`: a step's `status` is now its lifecycle
    (`StepStatus` in the domain), and two things called the same on one
    module's surface is one more than the word can carry.

    `name` and `gate` come from the served step definition, so a consumer
    can render a step and group it under its gate without obtaining the
    playbook — the arrangement `launch-instance`'s governing principle
    exists to preserve, and the one `add-launch-tracking-pages` would
    otherwise have had to break for the detail page's grouping alone.

    `discipline` and `blocking` come from the playbook; `overdue` folds
    "the due period has fully passed" together with "the step has not
    reached a terminal outcome its hazard permits". A reader outside this
    module has neither the playbook nor the hazard rules, so each of these
    travels on the report rather than being re-derived (`launch-instance`,
    "The launch report carries each step's discipline").

    `released` and the two fields beside it say whether the launch has
    asked for this work yet, and where it has not, what it is waiting for
    — the gate it starts at while the launch has not reached it, and the
    dependencies still unresolved. They travel here for the same reason
    everything else does: release turns on gate *positions* and on which
    outcomes each named step's hazard permits, so a consumer computing it
    would need the framework and the whole step set.

    `starts_at_gate` is present only while the launch has not reached it,
    and `unresolved_dependencies` holds only the ones still outstanding:
    the report states what a step is waiting *for*, not what it declares.
    A released step carries neither, so a consumer can render "what is
    this waiting on" without a second judgement of its own.

    All three default so that constructing a report without them is still
    possible for a caller that predates them — and default to *released*,
    which is what a step declaring nothing is.
    """

    step_id: str
    name: str
    gate: str
    discipline: Discipline
    due_period: AnchorPeriod | None
    progress: StepProgress | None
    blocking: bool
    overdue: bool
    released: bool = True
    starts_at_gate: str | None = None
    unresolved_dependencies: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LaunchReport:
    """The launch's full state plus its derived schedule, as of a date.

    `gate_sequence` names the gates in order. It travels here rather than
    being looked up because a consumer that had to find it would need the
    gate *framework* — a heavier dependency than the step set it is
    already spared, and one carrying the order as well as the names.

    `steps` holds one entry per served step, recorded or not, in the
    served playbook's own order: gate sequence order, then each gate's
    authored order. Both are properties of the set `served_steps` hands
    over, relied on by every consumer that lists a gate's steps.
    """

    product_id: ProductId
    playbook_version: str
    current_gate: str
    launch_date: date | None
    steps: tuple[ReportedStep, ...]
    gate_sequence: tuple[str, ...]
    at_risk: LaunchDateAtRisk | None
    awaiting_confirmation: bool


def _awaited_gate(launch: Launch, step: StepDefinition) -> str | None:
    """The gate the step starts at, while the launch has not reached it.

    `None` once it has, so a consumer renders "waiting for `listable`"
    only while that is true and never as a restatement of what the step
    declares.
    """
    standing = gate_position(launch.current_gate)
    if standing is None or standing >= start_position_of(step):
        return None
    return step.starts_at_gate


def _unresolved_dependencies(
    launch: Launch, playbook: LaunchPlaybook, step: StepDefinition
) -> tuple[str, ...]:
    """The steps this one waits on that are not yet resolved.

    Only the outstanding ones, and only the ones that count: a dependency
    naming no step, one no longer `active`, or one classified
    `prohibited-tactic` holds nothing back, so naming it here would tell a
    reader to chase something that is not holding anything.
    """
    defined = {held.identifier: held for held in playbook.authored_steps}
    return tuple(
        named
        for named in step.after_steps
        if (held := defined.get(named)) is not None
        and held.status is StepStatus.ACTIVE
        and held.hazard is not Hazard.PROHIBITED_TACTIC
        and not _is_resolved(launch, held)
    )


def _is_resolved(launch: Launch, step: StepDefinition) -> bool:
    """Whether `step` has reached an outcome its own hazard permits as
    terminal — the reading every consumer of "resolved" uses."""
    progress = launch.progress_for(step.identifier)
    if progress is None:
        return False
    recorded = progress.outcome
    kind = recorded if isinstance(recorded, type) else type(recorded)
    return kind in permissible_terminal_outcomes(step.hazard)


def _report_for(launch: Launch, playbook: LaunchPlaybook, as_of: date) -> LaunchReport:
    """One launch's report — the single construction both reads share, so
    an enumerated report can never drift from a singly-read one."""
    overdue = set(launch.overdue_step_ids(playbook, as_of))
    return LaunchReport(
        product_id=launch.product_id,
        playbook_version=launch.playbook_version,
        current_gate=launch.current_gate,
        launch_date=launch.launch_date,
        steps=tuple(
            ReportedStep(
                step_id=step.identifier,
                name=step.name,
                gate=step.gate,
                discipline=step.discipline,
                due_period=launch.due_period_for(playbook, step.identifier),
                progress=launch.progress_for(step.identifier),
                blocking=step.blocking,
                overdue=step.identifier in overdue,
                released=launch.has_released(playbook, step),
                starts_at_gate=_awaited_gate(launch, step),
                unresolved_dependencies=_unresolved_dependencies(
                    launch, playbook, step
                ),
            )
            for step in playbook.served_steps
        ),
        gate_sequence=tuple(gate.identifier for gate in playbook.gates),
        at_risk=launch.date_at_risk(playbook, as_of),
        awaiting_confirmation=launch.awaiting_confirmation(playbook),
    )


async def read_launch(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    product_id: ProductId,
    as_of: date,
    scope: AccessScope,
) -> LaunchReport | None:
    """The launch with every step's due period and the at-risk evaluation
    as of `as_of`; absence is reported as None, not an error.

    A launch the caller's scope does not permit reports the same absence as
    a product with no launch record — telling them apart would confirm the
    existence of a launch the caller may not see.
    """
    if not scope.permits(product_id):
        return None
    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        return None
    return _report_for(launch, playbooks.get(launch.playbook_version), as_of)


async def read_launches(
    launches: LaunchStore,
    playbooks: Playbooks,
    *,
    as_of: date,
    scope: AccessScope,
) -> tuple[LaunchReport, ...]:
    """Every persisted launch position the caller's scope permits, reported
    as of `as_of`.

    Never filtered by lifecycle: this context does not own a product's
    stage, and its persisted shape does not distinguish a graduated launch
    from one standing at the final gate. A caller wanting only live
    launches asks the catalog for the stage stamp (`launch-instance`,
    "Launch positions are enumerable with their reports").

    Scope filtering is a different question from that one, and does not
    reopen it: it decides whose launches the caller may see at all, never
    which stage of launch is worth reporting. An empty store — and a scope
    permitting nothing — is an empty result, not an error.
    """
    return tuple(
        _report_for(launch, playbooks.get(launch.playbook_version), as_of)
        for launch in await launches.list_all()
        if scope.permits(launch.product_id)
    )


async def read_launch_journal(
    journal: LaunchJournal,
    *,
    product_id: ProductId,
    scope: AccessScope,
) -> tuple[JournalEntry, ...]:
    """One launch's journal, most recent first, worded at read time.

    Three cases report the same empty journal, and they must stay
    indistinguishable: a scope that does not permit the product, a
    launch with nothing recorded — which every launch predating the
    journal is in, for ever — and a product with no launch record at
    all. Telling them apart would confirm the existence of a launch the
    caller may not see, which is why `read_launch` reports absence the
    same way.
    """
    if not scope.permits(product_id):
        return ()
    return tuple(compose(occurrence) for occurrence in await journal.read(product_id))


def _step_name(playbook: LaunchPlaybook, step_id: str) -> str | None:
    """The served playbook's name for a step, captured at the append.

    `None` where the playbook no longer serves it — unreachable through
    a recording, which the domain rejects for an unserved step, but the
    journal must not be the thing that raises if it ever becomes
    reachable.
    """
    for step in playbook.served_steps:
        if step.identifier == step_id:
            return step.name
    return None


def _threshold_for(
    playbook: LaunchPlaybook, attestation: MetricAttestation
) -> str | None:
    """A metric condition's threshold text — its label, captured at the
    append for the same reason a step's name is."""
    for gate in playbook.gates:
        if gate.identifier != attestation.gate_id:
            continue
        for condition in gate.metric_conditions:
            if condition.metric_id == attestation.metric_id:
                return condition.threshold
    return None


def _outcome_name(outcome: StepOutcomeValue) -> str:
    """The outcome's own name — the type for the reason-less outcomes, the
    instance's type for the reason-carrying ones (the domain's outcome
    value convention)."""
    return outcome.__name__ if isinstance(outcome, type) else type(outcome).__name__


async def _existing(launches: LaunchStore, product_id: ProductId) -> Launch:
    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        raise LaunchNotFoundError(f"product '{product_id.value}' has no launch record")
    return launch


# ---------------------------------------------------------------------------
# The cascade — `launch-gate-progression`
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _PinnedPlaybook:
    """The `Playbooks` port over one already-loaded definition.

    `progress_launch` is handed the served playbook rather than a resolver
    (`tasks.md` 3.4), so that the readiness the pass established once,
    before its walk, is the readiness every launch in that walk is judged
    against. `advance_gate` still wants the port, so the definition is
    wrapped rather than the port re-plumbed.
    """

    playbook: LaunchPlaybook

    def get(self, version: str) -> LaunchPlaybook:
        # The version selects nothing, exactly as the live repository's own
        # read documents: it is a launch's audit stamp, not a key.
        return self.playbook


@dataclass(frozen=True, slots=True)
class LaunchProgressed:
    """What one launch's cascade did, and what it left behind.

    `awaiting_confirmation` and `current_gate` travel together so a caller
    can decide whether an ask is owed without re-reading the launch — the
    pass asks that of every launch it walks, and a second read per launch
    would double the cost of the cheapest thing it does.
    """

    product_id: ProductId
    events: tuple[LaunchEvent, ...]
    current_gate: str
    awaiting_confirmation: bool
    crossed: tuple[str, ...]


async def _graduation_is_out_of_scope(
    product_id: ProductId, stage: object, *, confirmed_by: str
) -> None:
    """The stamper a caller gets when it supplies none.

    Reaching it would mean the cascade crossed the final gate, which it
    stops before doing. So this is a guard rather than a behaviour: it
    fails loudly rather than stamping a catalog product under a change
    that deliberately carries no graduation.
    """
    raise LaunchError(
        f"the gate-progression cascade attempted to graduate product "
        f"'{product_id.value}', which it stops short of by construction — "
        f"see `advance-gates-and-confirm-in-slack` design.md, Decision 8"
    )


async def progress_launch(
    *,
    launches: LaunchStore,
    playbook: LaunchPlaybook,
    product_id: ProductId,
    journal: LaunchJournal,
    stamp_steady_state: SteadyStateStamper | None = None,
) -> LaunchProgressed:
    """Advance one launch as far as its recorded state permits.

    Reads the launch itself, by identifier, rather than taking one a caller
    loaded: the caller holds the product's advisory lock, and a launch
    loaded before that lock could have been advanced by a decision in the
    meantime — judging readiness from that copy would command a crossing
    nobody judged.

    **Asks before it commands.** A refused advance is journaled, and
    unconditionally so; a cascade that commanded an advance for every
    launch on every run would bury the launch journal under its own
    refusals within days. So each iteration asks the launch whether its
    current gate may open — the same computation `advance_gate` decides on,
    so the two cannot disagree — and commands only where it says yes.

    **Stops at the final gate.** The walk's launch set already excludes a
    launch standing there, but a launch can *arrive* there mid-cascade,
    which no filter applied before the walk can govern. Crossing it is
    graduation, which this capability does not carry.

    **A gate declining is the stop, not a failure.** The race the ask above
    knowingly leaves open — a condition regressing between the read and the
    command — surfaces as `GateBlockedError`. The crossings already made
    were valid and stand, and the refusal `advance_gate` journaled on its
    way out is the only record that the condition ever blocked an advance.
    Any other exception propagates, to be contained by the caller.
    """
    playbooks = _PinnedPlaybook(playbook)
    stamper = stamp_steady_state or _graduation_is_out_of_scope
    final_gate = GATE_SEQUENCE[-1]

    events: list[LaunchEvent] = []
    crossed: list[str] = []

    launch = await launches.get_by_product_id(product_id)
    if launch is None:
        # A launch deleted between the walk's read and the lock. A no-op
        # rather than a contained failure: this deployment deletes launches
        # by hand, and a run failed by one is a run retried and reported
        # overdue for something already resolved.
        _logger.info(
            "gate progression: product %s has no launch record; nothing to advance",
            product_id.value,
        )
        return LaunchProgressed(
            product_id=product_id,
            events=(),
            current_gate="",
            awaiting_confirmation=False,
            crossed=(),
        )

    while True:
        if launch.current_gate == final_gate:
            break
        if launch.unsatisfied_conditions(playbook):
            break
        try:
            events.extend(
                await advance_gate(
                    launches=launches,
                    playbooks=playbooks,
                    stamp_steady_state=stamper,
                    product_id=product_id,
                    journal=journal,
                )
            )
        except GateBlockedError:
            # The read said the gate could open and the command found it
            # could not. Everything crossed before this stands, and the
            # refusal is already journaled.
            break
        crossed.append(launch.current_gate)
        launch = await _existing(launches, product_id)

    return LaunchProgressed(
        product_id=product_id,
        events=tuple(events),
        current_gate=launch.current_gate,
        awaiting_confirmation=launch.awaiting_confirmation(playbook),
        crossed=tuple(crossed),
    )
