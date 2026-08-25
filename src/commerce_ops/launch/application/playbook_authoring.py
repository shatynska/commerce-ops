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
    Binding,
    ExecutionMode,
    Hazard,
    LaunchPlaybook,
    Scope,
    StepDefinition,
    TimingAnchor,
    framework_gates,
)

AUTHORED_NAMESPACE = "mg"
"""The generated-identifier namespace, distinct from the seeded `lp.*`."""

_WRITE_ATTEMPTS = 3
"""How many times a write retries after losing the set-version race."""


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
        return self.retired_by is not None and self.unretired_by is None


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


def _is_retired(row: Any) -> bool:
    return row.retired_by is not None and row.unretired_by is None


def live_definitions(records: Sequence[Any]) -> tuple[StepDefinition, ...]:
    """The definitions the served playbook carries: everything not retired."""
    return tuple(row.definition for row in records if not _is_retired(row))


def _validate(records: Sequence[Any], version: int) -> None:
    """Construct the playbook the write would produce; `InvalidPlaybookError`
    propagates with every fault, exactly as a load would report them."""
    LaunchPlaybook(
        version=f"set-v{version}",
        gates=framework_gates(),
        steps=live_definitions(records),
    )


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
    """The slot after every live step of `gate` — where a created,
    un-retired, or gate-changed step appends."""
    highest = 0
    for row in records:
        if row.definition.gate != gate or _is_retired(row):
            continue
        if row.definition.identifier == excluding:
            continue
        highest = max(highest, _slot_of(row))
    return highest + 1


async def create_step(
    *,
    steps: StepSetStore,
    principal: str,
    description: str,
    gate: str,
    discipline: Any,
    scope: Scope,
    timing_anchor: TimingAnchor,
    binding: Binding,
    blocking: bool,
    execution: ExecutionMode,
    hazard: Hazard = Hazard.NONE,
    rule_policy: str | None = None,
) -> StepRecord:
    """Create a step with a generated `mg.*` identifier, attributed to
    `principal`. Validated as the whole playbook it would produce."""
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        definition = StepDefinition(
            identifier=_generate_identifier(records, discipline),
            description=description,
            gate=gate,
            discipline=discipline,
            scope=scope,
            timing_anchor=timing_anchor,
            binding=binding,
            blocking=blocking,
            execution=execution,
            hazard=hazard,
            rule_policy=rule_policy,
        )
        record = StepRecord(
            definition=definition,
            display_order=_last_slot_of_gate(records, gate),
            created_by=principal,
            created_on=datetime.now(UTC),
        )
        candidate = (*records, record)
        _validate(candidate, version + 1)
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(
        f"create_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def update_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    **fields: Any,
) -> StepRecord:
    """Update a step's authorable fields — never its identifier and never
    its discipline (the identifier's second segment must keep telling the
    truth; retire and create a successor to move a step's discipline)."""
    if "identifier" in fields:
        raise ValueError("a step's identifier is not updatable")
    if "discipline" in fields:
        raise ValueError(
            f"a step's discipline is not updatable: '{step_id}' keeps its "
            f"discipline because the identifier's second segment carries it; "
            f"retire the step and create its successor instead"
        )
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        index = _find(records, step_id)
        record = _as_record(records[index])
        gate_before = record.definition.gate
        record.definition = replace(record.definition, **fields)
        if record.definition.gate != gate_before:
            # A gate change appends to the new gate's order.
            record.display_order = _last_slot_of_gate(
                records, record.definition.gate, excluding=step_id
            )
        record.updated_by = principal
        record.updated_on = datetime.now(UTC)
        candidate = (*records[:index], record, *records[index + 1 :])
        _validate(candidate, version + 1)
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(
        f"update_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def retire_step(
    *, steps: StepSetStore, principal: str, step_id: str
) -> StepRecord:
    """Retire a step: excluded from the served set, never deleted. Rejected
    whole when the remaining set is incoherent — retiring a gate's last
    blocking step included."""
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        index = _find(records, step_id)
        record = _as_record(records[index])
        record.retired_by = principal
        record.retired_on = datetime.now(UTC)
        record.unretired_by = None
        record.unretired_on = None
        candidate = (*records[:index], record, *records[index + 1 :])
        _validate(candidate, version + 1)
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(
        f"retire_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )


async def reorder_step(
    *,
    steps: StepSetStore,
    principal: str,
    step_id: str,
    target_index: int,
    expected_version: int | None = None,
) -> StepRecord:
    """Move a live step to `target_index` (0-based) among its own gate's
    live steps, renumbering the gate's slots as one atomic write. The
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
        if _is_retired(records[index]):
            raise ValueError(f"step '{step_id}' is retired and holds no slot to move")
        gate = records[index].definition.gate
        gate_live = sorted(
            (
                position
                for position, row in enumerate(records)
                if row.definition.gate == gate and not _is_retired(row)
            ),
            key=lambda position: (
                _slot_of(records[position]),
                records[position].definition.identifier,
            ),
        )
        if not 0 <= target_index < len(gate_live):
            raise ValueError(
                f"target index {target_index} is outside gate '{gate}', "
                f"which holds {len(gate_live)} live steps"
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
    *, steps: StepSetStore, principal: str, step_id: str
) -> StepRecord:
    """Restore a retired step to the served set under its original
    identifier, attributing the reversal like the retirement was."""
    for _ in range(_WRITE_ATTEMPTS):
        records, version = await steps.load()
        index = _find(records, step_id)
        record = _as_record(records[index])
        # Rejoin at the end of the gate's order, not the remembered slot.
        record.display_order = _last_slot_of_gate(
            records, record.definition.gate, excluding=step_id
        )
        record.unretired_by = principal
        record.unretired_on = datetime.now(UTC)
        candidate = (*records[:index], record, *records[index + 1 :])
        _validate(candidate, version + 1)
        try:
            await steps.save(candidate, expected_version=version)
        except StaleStepSetError:
            continue
        return record
    raise StaleStepSetError(
        f"unretire_step lost the set-version race {_WRITE_ATTEMPTS} times"
    )
