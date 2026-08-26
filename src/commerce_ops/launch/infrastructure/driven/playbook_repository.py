"""Driven adapter: the live launch playbook, served from Postgres.

`move-playbook-steps-to-postgres` made the database the source of truth
for the *step set*; the framework — the eight gates, their opening modes,
their metric conditions, every coherence rule — stays code-owned in
`launch.domain.launch_playbook`, and this adapter joins the two on every
read: every stored definition over `framework_gates()`, constructed through `LaunchPlaybook` so nothing an
accepted write persisted can fail to load.

The playbook is **live**: `get(version)` deliberately ignores the version
it is passed. A launch's recorded version identifier is an audit stamp
("which definition era did this start under"), never a selector — the
served version identifier derives from the step-set version that
serializes writes, so it moves with every accepted write.

The same class doubles as the `StepSetStore` the `playbook-authoring`
use cases take: `load()` yields every stored row — retired included —
with the current set-version, and `save()` persists a full replacement
set conditionally on that version, raising `StaleStepSetError` when a
concurrent write got there first. Callers own the `AsyncSession`; each
write commits its own work, the convention `launch_repository` records.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.application import (
    StaleStepSetError,
    StepRecord,
    authored_definitions,
)
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    Cadence,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    OpenEndedAnchor,
    PlaybookNotReadyError,
    RecurringAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
    TimingAnchor,
    WindowAnchor,
    framework_gates,
)
from commerce_ops.launch.infrastructure.driven.models import (
    PlaybookStep,
    PlaybookStepSet,
)
from commerce_ops.shared.domain.discipline import Discipline

_SET_ROW_ID = 1


def _anchor_to_json(anchor: TimingAnchor) -> dict[str, Any]:
    if isinstance(anchor, OffsetAnchor):
        return {"kind": "offset", "days": anchor.days}
    if isinstance(anchor, WindowAnchor):
        return {"kind": "window", "start": anchor.start, "end": anchor.end}
    if isinstance(anchor, OpenEndedAnchor):
        return {"kind": "open-ended", "start": anchor.start}
    return {"kind": "recurring", "cadence": anchor.cadence.value}


def _anchor_from_json(raw: dict[str, Any]) -> TimingAnchor:
    kind = raw["kind"]
    if kind == "offset":
        return OffsetAnchor(days=int(raw["days"]))
    if kind == "window":
        return WindowAnchor(start=int(raw["start"]), end=int(raw["end"]))
    if kind == "open-ended":
        return OpenEndedAnchor(start=int(raw["start"]))
    if kind == "recurring":
        return RecurringAnchor(cadence=Cadence(raw["cadence"]))
    raise ValueError(f"stored timing anchor has unknown kind '{kind}'")


def _definition_from_row(row: PlaybookStep) -> StepDefinition:
    return StepDefinition(
        identifier=row.identifier,
        name=row.name,
        description=row.description,
        gate=row.gate,
        discipline=Discipline(row.discipline),
        scope=Scope(row.scope),
        timing_anchor=_anchor_from_json(row.timing_anchor),
        blocking=row.blocking,
        kind=StepKind(row.kind),
        needs_confirmation=row.needs_confirmation,
        status=StepStatus(row.status),
        hazard=Hazard(row.hazard),
        assignees=tuple(row.assignees or ()),
        automation_brief=row.automation_brief,
        handler=row.handler,
        provenance=row.provenance,
    )


def _record_from_row(row: PlaybookStep) -> StepRecord:
    return StepRecord(
        definition=_definition_from_row(row),
        display_order=row.display_order,
        created_by=row.created_by,
        created_on=row.created_on,
        updated_by=row.updated_by,
        updated_on=row.updated_on,
        retired_by=row.retired_by,
        retired_on=row.retired_on,
        unretired_by=row.unretired_by,
        unretired_on=row.unretired_on,
    )


def _row_from_record(record: Any) -> PlaybookStep:
    definition: StepDefinition = record.definition
    return PlaybookStep(
        identifier=definition.identifier,
        name=definition.name,
        description=definition.description,
        gate=definition.gate,
        discipline=definition.discipline.value,
        scope=definition.scope.value,
        timing_anchor=_anchor_to_json(definition.timing_anchor),
        blocking=definition.blocking,
        kind=definition.kind.value,
        needs_confirmation=definition.needs_confirmation,
        status=definition.status.value,
        hazard=definition.hazard.value,
        assignees=list(definition.assignees),
        automation_brief=definition.automation_brief,
        handler=definition.handler,
        provenance=definition.provenance,
        display_order=getattr(record, "display_order", 0),
        created_by=record.created_by,
        created_on=record.created_on,
        updated_by=record.updated_by,
        updated_on=record.updated_on,
        retired_by=record.retired_by,
        retired_on=record.retired_on,
        unretired_by=record.unretired_by,
        unretired_on=record.unretired_on,
    )


class ServedPlaybooks:
    """The sync `Playbooks` port over one pre-loaded served playbook.

    The port's `get` is synchronous while a Postgres read is not, so a
    driving adapter loads the playbook once per pass
    (`await PlaybookRepository(session).get(...)`) and hands the use
    cases this wrapper — which is also what keeps "the playbook is read
    per pass, never cached at import" true by construction."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


class PlaybookRepository:
    """The `Playbooks` read over the live step set, and the `StepSetStore`
    the authoring use cases write through."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _version(self) -> int:
        version = await self._session.scalar(
            select(PlaybookStepSet.version).where(PlaybookStepSet.id == _SET_ROW_ID)
        )
        if version is None:
            raise RuntimeError(
                "the playbook step set has no version row — has "
                "`alembic upgrade head` (schema + seed) been applied?"
            )
        return int(version)

    async def get(self, version: str) -> LaunchPlaybook:
        """The live playbook. The passed version selects nothing — it is
        a launch's audit stamp, not a key — so a launch started under an
        earlier definition still reads the current set.

        Constructed over **every** stored definition, whatever its
        status: the status-dependent coherence rules can only be
        evaluated over steps that carry a status, and the playbook's own
        queries answer the served (`active`) subset while
        `authored_steps` answers the whole authored set the admin
        surface reads.

        This is the **serving** read: a read taken on a launch's behalf,
        to advance one, project one, or report on one. It refuses a
        playbook that cannot hold a launch — one leaving a gate with no
        `active` blocking step — with `PlaybookNotReadyError` naming those
        gates. The authoring read (`load`) is deliberately not refused, so
        a set under construction stays visible and editable throughout.

        An *absent* playbook stays a different failure: `_version` raises
        before this point, because nothing to serve and nothing built yet
        are not the same problem."""
        records, set_version = await self.load()
        playbook = LaunchPlaybook(
            version=f"v{set_version}",
            gates=framework_gates(),
            steps=authored_definitions(records),
        )
        if not playbook.is_ready:
            raise PlaybookNotReadyError(playbook=playbook, gates=playbook.unheld_gates)
        return playbook

    # -- the StepSetStore half ------------------------------------------

    async def load(self) -> tuple[Sequence[StepRecord], int]:
        version = await self._version()
        rows = await self._session.scalars(
            select(PlaybookStep).order_by(PlaybookStep.identifier)
        )
        # Serving order: gate position in the framework's sequence, then
        # the authored slot, then the identifier as a deterministic
        # backstop (`add-playbook-admin-ui`). A gate the framework does
        # not know cannot be persisted by an accepted write; sorting it
        # last keeps the read from crashing on a hand-edited row.
        gate_positions = {gate: index for index, gate in enumerate(GATE_SEQUENCE)}
        records = sorted(
            (_record_from_row(row) for row in rows),
            key=lambda record: (
                gate_positions.get(record.definition.gate, len(gate_positions)),
                record.display_order,
                record.definition.identifier,
            ),
        )
        return tuple(records), version

    async def save(self, records: Sequence[Any], *, expected_version: int) -> None:
        """Persist the full replacement set, conditionally on the version
        it was loaded at — the optimistic serialization every write rides."""
        bumped = await self._session.execute(
            update(PlaybookStepSet)
            .where(
                PlaybookStepSet.id == _SET_ROW_ID,
                PlaybookStepSet.version == expected_version,
            )
            .values(version=expected_version + 1)
            .returning(PlaybookStepSet.version)
        )
        if bumped.scalar() is None:
            await self._session.rollback()
            raise StaleStepSetError(
                f"the step set moved past version {expected_version} while "
                f"this write was validating; reload and revalidate"
            )
        await self._session.execute(delete(PlaybookStep))
        self._session.add_all(_row_from_record(record) for record in records)
        await self._session.commit()
