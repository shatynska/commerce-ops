"""Write use cases of the `playbook-authoring` capability.

The step set lives in a store behind the `StepSetStore` port; these five
operations are the only way it changes. Every write is validated by
constructing the **entire** `LaunchPlaybook` the write would produce —
the live definitions after the mutation, over the code-owned
`framework_gates()` — so the same coherence rulebook guards load and
write alike, and a rejected write reports every fault at once
(`InvalidPlaybookError`) while persisting nothing.

Writes are serialized by the store's optimistic set-version: each
operation loads the set with its version and persists conditionally on
that version being unchanged. A lost race (`StaleStepSetError`) is
retried against the fresh set, re-validating — the retry may now be
rightly rejected (the second of two retirements that together would
leave a gate unheld).

Identifiers are generated, never chosen: `mg.<discipline>.<seq>`, the
`mg.` namespace keeping a step's origin legible next to the seeded
`lp.*` rows, the discipline segment keeping the identifier truthful —
which is also why `update_step` refuses to change a step's discipline
(retire the step and create its successor instead).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
    TimingAnchor,
    assignee_faults,
    confirmer_faults,
    dependency_faults,
    framework_gates,
    gate_holding_faults,
    unheld_gates_of,
)

AUTHORED_NAMESPACE = "mg"
"""The generated-identifier namespace, distinct from the seeded `lp.*`."""

_WRITE_ATTEMPTS = 3
"""How many times a write retries after losing the set-version race."""


class RosterReader(Protocol):
    """The one shape a roster collaborator answers to.

    The write-side preconditions need to know who the roster carries; the
    module boundary forbids `launch` resolving that itself, so a caller
    supplies a reader. It used to be addressed by guessing among several
    shapes, and the shape production actually supplied — the `RosterStore`
    the composition root holds, which answers `load()` and `save()` — was
    not among them. Every write from the admin page therefore died on a
    `TypeError` raised from inside the write.

    One member, and it is a `Protocol` so that `mypy` sees a store handed
    over where a reader belongs, at the call site, which is where the
    mistake was made and where nothing was watching.
    """

    async def list_people(self) -> Sequence[Any]: ...


class UnreadableRosterError(TypeError):
    """A roster collaborator that does not answer `RosterReader`.

    A defect of *wiring*, and deliberately not an `InvalidPlaybookError`:
    that type carries a rejected write's fault list, which the admin page
    renders as a judgement about what the author submitted. Presenting a
    mis-wired deployment that way would show an operator's mistake in an
    author's form, at 200, where nothing but the browser could tell a
    broken deployment from a refused edit.

    A `TypeError` subclass because that is what it is, and because the
    production fault was one — a caller that already handles the old
    failure keeps handling this one, better named.
    """


class StaleStepSetError(RuntimeError):
    """A conditional persist lost the race: the step set changed between
    load and save.

    A write that computed its own change from the set it just read
    retries against the fresh set. A write given a caller's view of the
    set — `reorder_step`'s `expected_version` — does not: its change was
    computed against a view the caller has since lost, and reapplying it
    to a newer set would move a step somewhere nobody asked for."""


@dataclass(slots=True)
class StepRecord:
    """One stored step: its definition plus the attribution trail.

    `definition.provenance` carries the seed citation (for `lp.*` rows)
    or nothing; who created, updated, retired, or un-retired the step is
    recorded here, on the row, not in the definition.

    `display_order` is the authored within-gate slot
    (`add-playbook-admin-ui`): presentation truth only — the domain's
    commitment machinery never sees it. Serving reads gate position,
    then slot, then identifier.
    """

    definition: StepDefinition
    display_order: int = 0
    created_by: str | None = None
    created_on: datetime | None = None
    updated_by: str | None = None
    updated_on: datetime | None = None
    retired_by: str | None = None
    retired_on: datetime | None = None
    unretired_by: str | None = None
    unretired_on: datetime | None = None

    @property
    def retired(self) -> bool:
        """Read off the *status*, not the attribution.

        `redesign-step-fields` made the status the single answer to "is
        this step in play"; the attribution columns stay, recording who
        moved the step and when, which the status itself cannot say.
        """
        return self.definition.status is StepStatus.RETIRED


class StepSetStore(Protocol):
    """The step-set persistence port.

    `load` returns every stored record — retired included — with the
    current set-version; `save` persists a full replacement set
    conditionally on that version, raising `StaleStepSetError` when it
    has moved.
    """

    async def load(self) -> tuple[Sequence[Any], int]: ...

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None: ...


def _as_record(row: Any) -> StepRecord:
    """A loaded row as a `StepRecord`, whatever concrete type the store
    yielded — the attribute spellings are the port's contract."""
    if isinstance(row, StepRecord):
        return row
    return StepRecord(
        definition=row.definition,
        display_order=getattr(row, "display_order", 0),
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        retired_by=row.retired_by,
        retired_on=row.retired_on,
        unretired_by=row.unretired_by,
        unretired_on=row.unretired_on,
    )


def _is_active(row: Any) -> bool:
    return row.definition.status is StepStatus.ACTIVE


def _is_retired(row: Any) -> bool:
    return row.definition.status is StepStatus.RETIRED


def authored_definitions(records: Sequence[Any]) -> tuple[StepDefinition, ...]:
    """Every stored definition, whatever its status — what a load
    constructs and what a write validates, since the status-dependent
    rules can only be evaluated over the steps that carry a status."""
    return tuple(row.definition for row in records)


def live_definitions(records: Sequence[Any]) -> tuple[StepDefinition, ...]:
    """The definitions a launch is held to: the `active` ones."""
    return tuple(row.definition for row in records if _is_active(row))


def _validate(records: Sequence[Any], version: int) -> None:
    """Construct the playbook the write would produce; `InvalidPlaybookError`
    propagates with every fault, exactly as a load would report them."""
    LaunchPlaybook(
        version=f"set-v{version}",
        gates=framework_gates(),
        steps=authored_definitions(records),
    )


async def _roster_identifiers(roster: RosterReader) -> tuple[set[str], set[str]]:
    """(everyone the roster carries, everyone active on it), by identifier.

    The reader is a collaborator the composition root supplies across the
    module boundary — `.importlinter` forbids `launch` reaching into
    `access`'s internals — so it is addressed by shape rather than by
    type, and a person's identifier is read under either spelling the
    roster's own rows use.
    """
    people = await _read_people(roster)
    known: set[str] = set()
    active: set[str] = set()
    for person in people:
        identifier = person_identifier(person)
        known.add(identifier)
        if getattr(person, "active", True):
            active.add(identifier)
    return known, active


async def _read_people(roster: RosterReader) -> tuple[Any, ...]:
    """Everyone the roster carries, read through the one stated shape.

    It once accepted three — a `list_people()` reader, a callable, or a
    plain iterable — and fell through to `tuple(roster)` for anything
    else, which is how a `RosterStore` produced `'PostgresRoster' object
    is not iterable` from the middle of a write. One shape now, and
    anything else is refused by name before the write is attempted.
    """
    lister = getattr(roster, "list_people", None)
    if lister is None:
        raise UnreadableRosterError(
            f"the roster collaborator is a {type(roster).__name__!r}, which "
            f"cannot answer who the roster carries: a roster reader must "
            f"provide `list_people()`, and this one does not. Pass a reader "
            f"rather than a roster store, or pass no roster at all to leave "
            f"the two roster preconditions unevaluated"
        )
    return tuple(await lister())


def person_identifier(person: Any) -> str:
    """One roster person's generated identifier.

    `access`'s own `Person` spells it `identifier`; a reader that answers
    rows of its own may spell it `id`. Both are read here so the seam is
    a shape rather than a type."""
    for name in ("identifier", "id", "person_id"):
        value = getattr(person, name, None)
        if value is not None:
            return str(value)
    raise ValueError(f"a roster person exposes no identifier: {person!r}")


async def _precondition_faults(
    touched: Sequence[StepDefinition],
    *,
    candidate: Sequence[StepDefinition],
    roster: RosterReader | None,
    handlers: Any,
) -> list[str]:
    """The checks a load cannot make, over the steps a write touches.

    Scoped to the touched steps and never to the whole resulting set:
    set-wide evaluation would mean the migrated step set — 95 `active`
    steps deliberately left unowned — refuses every subsequent write
    until all 95 are assigned, which is the backfill the migration
    declined to invent.

    The dependency rules are evaluated **whatever the caller supplies as
    a roster, and whether or not one is supplied at all**. Only the
    assignee and confirmer rules turn on the roster; a dependency is a
    function of the step set alone, and skipping it because no roster
    arrived would leave a step-set rule unevaluated for a reason having
    nothing to do with it. They read the whole candidate set — that is
    where a named step's status and hazard live — while still being
    *reported* only for the steps the write touched.
    """
    faults: list[str] = []
    if roster is not None:
        known, active = await _roster_identifiers(roster)
        faults.extend(assignee_faults(touched, known=known, active=active))
        faults.extend(confirmer_faults(touched, known=known, active=active))
    faults.extend(dependency_faults(touched, defined=candidate))
    faults.extend(_registration_faults(touched, handlers))
    return faults


async def _accept(
    candidate: Sequence[Any],
    version: int,
    touched: Sequence[StepDefinition],
    *,
    prior_unheld: Sequence[str],
    roster: RosterReader | None,
    handlers: Any,
) -> None:
    """Judge the write whole, and report every fault it carries at once.

    The load-side rules are evaluated over the entire set the write would
    produce; the two the roster and the registry decide are evaluated
    over the steps the write touches. Both are gathered before either is
    raised, so a rejection does not have to be corrected one fault at a
    time — the shape `InvalidPlaybookError` has carried since the load
    path.

    The gate-holding rule is a third kind, and the only one that reads the
    set as it stood *before* the write. It is one-directional: a write is
    refused for leaving a gate unheld only when the set it started from was
    itself ready, so a served playbook cannot be taken from a running
    launch by one authoring action, while a set still being built reaches
    readiness one activation at a time.

    The prior set arrives already reduced to its unheld gates, and must:
    `_write_fields` mutates the loaded record **in place** (`_as_record`
    returns the stored object, not a copy), so by the time this runs the
    caller's `records` already reflects the write. Sampling the prior set
    here would read the candidate twice and the ratchet would never fire.
    """
    faults: list[str] = []
    try:
        _validate(candidate, version + 1)
    except InvalidPlaybookError as rejected:
        faults.extend(rejected.faults)
    faults.extend(
        gate_holding_faults(
            tuple(prior_unheld),
            unheld_gates_of(authored_definitions(candidate)),
        )
    )
    faults.extend(
        await _precondition_faults(
            touched,
            candidate=authored_definitions(candidate),
            roster=roster,
            handlers=handlers,
        )
    )
    if faults:
        raise InvalidPlaybookError(faults)


def _registration_faults(touched: Sequence[StepDefinition], handlers: Any) -> list[str]:
    """That the deployed code answers for an activated step's handler.

    Checked here and never at load: the registry is a property of the
    deployment, which changes without the step set changing, so a rename
    must fail a deployment rather than take down every launch."""
    if handlers is None:
        return []
    registered = _registered_names(handlers)
    return [
        (
            f"step '{step.identifier}' names handler '{step.handler}', which "
            f"no registered use case answers to"
        )
        for step in touched
        if step.status is StepStatus.ACTIVE
        and step.kind is StepKind.AUTOMATED
        and step.handler is not None
        and step.handler not in registered
    ]


def _registered_names(handlers: Any) -> frozenset[str]:
    names = getattr(handlers, "names", None)
    if callable(names):
        return frozenset(str(name) for name in names())
    return frozenset(str(name) for name in handlers)


def _generate_identifier(records: Sequence[Any], discipline: Any) -> str:
    """The next `mg.<discipline>.<seq>` — counted over every stored row,
    retired ones included, so a generated identifier never collides."""
    pattern = re.compile(
        rf"{AUTHORED_NAMESPACE}\.{re.escape(discipline.value)}\.(\d+)$"
    )
    highest = 0
    for row in records:
        matched = pattern.fullmatch(row.definition.identifier)
        if matched:
            highest = max(highest, int(matched.group(1)))
    return f"{AUTHORED_NAMESPACE}.{discipline.value}.{highest + 1:03d}"


def _find(records: Sequence[Any], step_id: str) -> int:
    for index, row in enumerate(records):
        if row.definition.identifier == step_id:
            return index
    raise ValueError(f"no stored step carries identifier '{step_id}'")


def _copy_record(row: Any) -> StepRecord:
    """A fresh `StepRecord` for `row`, never the loaded object itself —
    so a write that loses the save race has mutated nothing."""
    record = _as_record(row)
    if record is row:
        copied: StepRecord = replace(record)
        return copied
    return record


def _slot_of(row: Any) -> int:
    return int(getattr(row, "display_order", 0))


def _last_slot_of_gate(
    records: Sequence[Any], gate: str, *, excluding: str | None = None
) -> int:
    """The slot after every **active** step of `gate` — where a step
    entering `active`, or an active step changing gate, appends.

    Slots belong to the served order, so a `draft` or `in-development`
    step holds none: there is one order, and it is the order a launch is
    held to."""
    highest = 0
    for row in records:
        if row.definition.gate != gate or not _is_active(row):
            continue
        if row.definition.identifier == excluding:
            continue
        highest = max(highest, _slot_of(row))
    return highest + 1


def _crossing_retired(
    before: StepDefinition, after: StepDefinition
) -> tuple[StepDefinition, str | None]:
    """A move into or out of `retired` **is** the retire / un-retire write.

    Whatever surface asks for the change — the admin page's status
    control included — crossing `retired` carries that write's
    attribution, and a move out arrives at `in-development`: a step
    retired months ago may name an assignee who has since left, so
    restoring it straight to the served set would either fail the write
    or serve a step nobody can resolve. Activating it is the separate
    deliberate act it is for any other step.

    Returns the definition to persist and which attribution to stamp.
    """
    if after.status is StepStatus.RETIRED and before.status is not StepStatus.RETIRED:
        return after, "retired"
    if before.status is StepStatus.RETIRED and after.status is not StepStatus.RETIRED:
        return replace(after, status=StepStatus.IN_DEVELOPMENT), "unretired"
    return after, None


def _stamp(
    record: StepRecord, crossing: str | None, principal: str, now: datetime
) -> None:
    if crossing == "retired":
        record.retired_by = principal
        record.retired_on = now
        record.unretired_by = None
        record.unretired_on = None
    elif crossing == "unretired":
        record.unretired_by = principal
        record.unretired_on = now


def _place(record: StepRecord, records: Sequence[Any], before: StepDefinition) -> None:
    """Where the written step now stands in its gate's served order.

    A step entering `active` takes the last slot of its gate rather than
    reclaiming a remembered position, and an active step changing gate
    appends to the new one. A step leaving `active` by any route — a
    retirement or any other status change — is removed from the order
    without disturbing the steps that remain.
    """
    definition = record.definition
    if definition.status is not StepStatus.ACTIVE:
        record.display_order = 0
        return
    if before.status is not StepStatus.ACTIVE or definition.gate != before.gate:
        record.display_order = _last_slot_of_gate(
            records, definition.gate, excluding=definition.identifier
        )


async def create_step(
    *,
    steps: StepSetStore,
    principal: str,
    name: str,
    gate: str,
    discipline: Any,
    scope: Scope,
    timing_anchor: TimingAnchor,
    blocking: bool,
    kind: StepKind,
    roster: RosterReader | None = None,
    handlers: Any = None,
    description: str | None = None,
    status: StepStatus = StepStatus.DRAFT,
    hazard: Hazard = Hazard.NONE,
    assignees: Sequence[str] = (),
    starts_at_gate: str | None = None,
    after_steps: Sequence[str] = (),
    handler: str | None = None,
    confirmer: str | None = None,
) -> StepRecord:
    """Create a step with a generated `mg.*` identifier, attributed to
    `principal`. Validated as the whole playbook it would produce, plus
    the two preconditions a load cannot check."""
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        prior_unheld = unheld_gates_of(authored_definitions(records))
        now = datetime.now(UTC)
        definition = StepDefinition(
            identifier=_generate_identifier(records, discipline),
            name=name,
            gate=gate,
            discipline=discipline,
            scope=scope,
            timing_anchor=timing_anchor,
            blocking=blocking,
            kind=kind,
            description=description,
            status=status,
            hazard=hazard,
            assignees=tuple(assignees),
            starts_at_gate=starts_at_gate,
            after_steps=tuple(after_steps),
            handler=handler,
            confirmer=confirmer,
        )
        record = StepRecord(
            definition=definition,
            display_order=(
                _last_slot_of_gate(records, gate) if status is StepStatus.ACTIVE else 0
            ),
            created_by=principal,
            created_on=now,
        )
        if status is StepStatus.RETIRED:
            _stamp(record, "retired", principal, now)
        candidate = (*records, record)
        await _accept(
            candidate,
            version,
            (definition,),
            prior_unheld=prior_unheld,
            roster=roster,
            handlers=handlers,
        )
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(
        f"create_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def _write_fields(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    roster: RosterReader | None,
    handlers: Any,
    attribute_as_update: bool,
    what: str,
    fields: dict[str, Any],
) -> StepRecord:
    """The one write behind `update_step`, `retire_step` and
    `unretire_step`: replace a step's authorable fields, resolve what
    crossing `retired` means, place it in its gate's order, and judge the
    whole set the write would produce."""
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        # Sampled before the record below is mutated in place, which is
        # what makes the ratchet able to see the set as it stood.
        prior_unheld = unheld_gates_of(authored_definitions(records))
        index = _find(records, step_id)
        record = _as_record(records[index])
        before = record.definition
        now = datetime.now(UTC)
        definition, crossing = _crossing_retired(before, replace(before, **fields))
        record.definition = definition
        _stamp(record, crossing, principal, now)
        _place(record, records, before)
        if attribute_as_update:
            record.updated_by = principal
            record.updated_on = now
        candidate = (*records[:index], record, *records[index + 1 :])
        await _accept(
            candidate,
            version,
            (definition,),
            prior_unheld=prior_unheld,
            roster=roster,
            handlers=handlers,
        )
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(f"{what} lost the set-version race {_WRITE_ATTEMPTS} times")


async def update_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    roster: RosterReader | None = None,
    handlers: Any = None,
    **fields: Any,
) -> StepRecord:
    """Update a step's authorable fields — never its identifier and never
    its discipline (the identifier's second segment must keep telling the
    truth; retire and create a successor to move a step's discipline).

    An update that changes the status is validated as the transition it
    is, so the same rules apply however the status moves."""
    if "identifier" in fields:
        raise ValueError("a step's identifier is not updatable")
    if "discipline" in fields:
        raise ValueError(
            f"a step's discipline is not updatable: '{step_id}' keeps its "
            f"discipline because the identifier's second segment carries it; "
            f"retire the step and create its successor instead"
        )
    if "assignees" in fields:
        fields["assignees"] = tuple(fields["assignees"])
    # Same normalisation and for the same reason: the surface submits a
    # list, the definition compares by value, and a list member would
    # defeat both.
    if "after_steps" in fields:
        fields["after_steps"] = tuple(fields["after_steps"])
    return await _write_fields(
        steps=steps,
        principal=principal,
        step_id=step_id,
        roster=roster,
        handlers=handlers,
        attribute_as_update=True,
        what="update_step",
        fields=fields,
    )


async def retire_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    roster: RosterReader | None = None,
    handlers: Any = None,
) -> StepRecord:
    """Retire a step: its status becomes `retired`, which excludes it
    from the served set while the stored definition, the identifier and
    every outcome recorded against it persist. Rejected whole when the
    remaining set is incoherent — retiring a gate's last active blocking
    step included."""
    return await _write_fields(
        steps=steps,
        principal=principal,
        step_id=step_id,
        roster=roster,
        handlers=handlers,
        attribute_as_update=False,
        what="retire_step",
        fields={"status": StepStatus.RETIRED},
    )


async def reorder_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    target_index: int,
    expected_version: int | None = None,
) -> StepRecord:
    """Move an active step to `target_index` (0-based) among its own
    gate's active steps, renumbering the gate's slots as one atomic write. The
    unmoved steps keep their relative order; the step's definition — its
    gate included — is untouched; the move is attributed to `principal`
    on the moved step, as an update is. Validated and serialized exactly
    like every other write.

    `expected_version` is the caller's view of the set: the version
    `target_index` was computed against. Supplied, the write is refused
    with `StaleStepSetError` unless it is the version the write itself
    reads — refused whichever way it differs, so a version the caller
    cannot hold a view of is not taken for one — and it is never retried
    past, because retrying would reapply a position computed against a
    view that no longer describes the set. Absent, the position is
    understood to be computed against whatever the write reads, and a
    concurrent write is resolved by re-reading and recomputing.
    """
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        if expected_version is not None and version != expected_version:
            raise StaleStepSetError(
                f"reorder_step was given version {expected_version} as the view "
                f"its position was computed against, but the set reads "
                f"{version}; the position is not recomputed"
            )
        index = _find(records, step_id)
        if not _is_active(records[index]):
            raise ValueError(
                f"step '{step_id}' is "
                f"'{records[index].definition.status.value}' and holds no "
                f"slot to move"
            )
        gate = records[index].definition.gate
        gate_live = sorted(
            (
                position
                for position, row in enumerate(records)
                if row.definition.gate == gate and _is_active(row)
            ),
            key=lambda position: (
                _slot_of(records[position]),
                records[position].definition.identifier,
            ),
        )
        if not 0 <= target_index < len(gate_live):
            raise ValueError(
                f"target index {target_index} is outside gate '{gate}', "
                f"which holds {len(gate_live)} active steps"
            )
        sequence = [position for position in gate_live if position != index]
        sequence.insert(target_index, index)
        now = datetime.now(UTC)
        moved: StepRecord | None = None
        renumbered: dict[int, StepRecord] = {}
        for slot, position in enumerate(sequence, start=1):
            copy = _copy_record(records[position])
            copy.display_order = slot
            if position == index:
                copy.updated_by = principal
                copy.updated_on = now
                moved = copy
            renumbered[position] = copy
        candidate = tuple(
            renumbered.get(position, row) for position, row in enumerate(records)
        )
        # Deliberately `_validate` and not `_accept`, which is where every
        # other write goes. A reorder rewrites `display_order` and nothing
        # else — it carries each definition across unchanged — so it can
        # neither break a coherence rule nor move a ready set to not-ready,
        # and the ratchet has nothing to say about it. Routing it through
        # `_accept` would additionally subject the moved step to
        # `_precondition_faults`, refusing reorders of the migrated
        # `active` `human` steps that name no assignee — which is a
        # refusal `playbook-authoring`'s reorder requirement does not
        # contemplate and nobody asked for.
        _validate(candidate, version + 1)
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            if expected_version is not None:
                raise
            continue
        assert moved is not None
        return moved
    raise StaleStepSetError(
        f"reorder_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def unretire_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    roster: RosterReader | None = None,
    handlers: Any = None,
) -> StepRecord:
    """Return a retired step to `in-development` under its original
    identifier, attributing the reversal like the retirement was.

    Not to `active`: retirement is no longer the inverse of
    un-retirement, and this is the honest consequence of activation
    being validated. Returning it to `in-development` always succeeds,
    and activating it is the separate act it is for any other step."""
    return await _write_fields(
        steps=steps,
        principal=principal,
        step_id=step_id,
        roster=roster,
        handlers=handlers,
        attribute_as_update=False,
        what="unretire_step",
        fields={"status": StepStatus.IN_DEVELOPMENT},
    )


async def change_step_status(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    status: StepStatus,
    roster: RosterReader | None = None,
    handlers: Any = None,
) -> StepRecord:
    """Move a step to `status`, validated by the rules of the status it
    moves **to** plus the whole-set rules every write obeys.

    A move into or out of `retired` is the retirement or un-retirement
    write itself, wherever it was asked for — so a status control cannot
    become a second way out of `retired` that lands somewhere else and
    records nobody."""
    return await update_step(
        steps=steps,
        principal=principal,
        step_id=step_id,
        roster=roster,
        handlers=handlers,
        status=status,
    )
