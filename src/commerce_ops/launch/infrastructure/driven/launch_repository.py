"""Driven adapter: persists and rehydrates the `Launch` aggregate.

Implements `launch-instance`'s persistence requirements as reshaped by
`introduce-launch-aggregate` (design.md Decision 7): whole-aggregate
`save` / `get_by_product_id` over the `launch_positions` spine plus the
three child tables. The former free-form `update_current_gate` path is
retired — the stored gate changes only through aggregate behavior.

Callers own the `AsyncSession`; each method commits its own work, the
convention this module's predecessor (`launch_position_repository`)
recorded.

`save` distinguishes a newly started launch from a loaded one by object
identity: an aggregate this repository handed out (or already saved) is
updated in place; any other aggregate is an insert, and an insert that
collides — an unknown product (foreign key) or a product that already has
a launch (primary key) — is rejected. The update path replaces the child
rows wholesale from the aggregate's state; at slice-3 scale (one launch,
~150 step rows) that is simpler than diffing and equally correct.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    InProgress,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    MetricAttestation,
    Provenance,
    StepOutcomeValue,
    StepProgress,
)
from commerce_ops.launch.infrastructure.driven.models import (
    GATE_IDS,
    LaunchGateApproval,
    LaunchMetricAttestation,
    LaunchPosition,
    LaunchStepProgress,
)
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture


class LaunchRepositoryError(Exception):
    """A save was rejected: an unknown product, a second launch for the
    same product, or a record the schema's constraints refuse."""


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    """The row key for a product identifier, or None when the opaque value
    cannot be a row key at all — read as an unknown product."""
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


# The outcome value convention (see `launch_run`'s module docstring):
# reason-less outcomes are stored as a kind alone and rehydrated to the
# outcome type itself; reason-carrying ones round-trip kind + reason.
_KIND_BY_TYPE: dict[type, str] = {
    NotStarted: "not-started",
    InProgress: "in-progress",
    Satisfied: "satisfied",
    Blocked: "blocked",
    Refused: "refused",
    NotApplicable: "not-applicable",
}
_BARE_TYPE_BY_KIND: dict[str, StepOutcomeValue] = {
    "not-started": NotStarted,
    "in-progress": InProgress,
    "satisfied": Satisfied,
    "refused": Refused,
}


def _outcome_to_row(outcome: StepOutcomeValue) -> tuple[str, str | None]:
    if isinstance(outcome, Blocked | NotApplicable):
        return _KIND_BY_TYPE[type(outcome)], outcome.reason
    kind_type = outcome if isinstance(outcome, type) else type(outcome)
    return _KIND_BY_TYPE[kind_type], None


def _outcome_from_row(kind: str, reason: str | None) -> StepOutcomeValue:
    if kind == "blocked":
        return Blocked(reason or "")
    if kind == "not-applicable":
        return NotApplicable(reason or "")
    return _BARE_TYPE_BY_KIND[kind]


class LaunchRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Aggregates this repository handed out or saved, by row key —
        # how `save` tells an update from a colliding second start.
        self._managed: dict[uuid.UUID, Launch] = {}

    async def save(self, launch: Launch) -> None:
        row_id = _row_id(launch.product_id)
        if row_id is None:
            raise LaunchRepositoryError(
                f"no catalog product with id '{launch.product_id.value}'"
            )
        if launch.current_gate not in GATE_IDS:
            raise LaunchRepositoryError(f"unrecognized gate '{launch.current_gate}'")

        if self._managed.get(row_id) is launch:
            await self._update(row_id, launch)
        else:
            await self._insert(row_id, launch)
        self._managed[row_id] = launch

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        position = await self._session.get(LaunchPosition, row_id)
        if position is None:
            return None

        progress_rows = await self._session.scalars(
            select(LaunchStepProgress).where(LaunchStepProgress.product_id == row_id)
        )
        approval_rows = await self._session.scalars(
            select(LaunchGateApproval).where(LaunchGateApproval.product_id == row_id)
        )
        attestation_rows = await self._session.scalars(
            select(LaunchMetricAttestation).where(
                LaunchMetricAttestation.product_id == row_id
            )
        )

        launch = Launch(
            product_id=ProductId(str(position.product_id)),
            playbook_version=position.playbook_version,
            current_gate=position.current_gate,
            launch_date=position.launch_date,
            step_progress={
                row.step_id: StepProgress(
                    outcome=_outcome_from_row(row.outcome_kind, row.outcome_reason),
                    provenance=Provenance(
                        source=row.source,
                        who=row.who,
                        when=row.recorded_at,
                        evidence=row.evidence,
                    ),
                )
                for row in progress_rows
            },
            approvals={
                row.gate_id: GateApproval(
                    decision=ApprovalDecision(row.decision),
                    approver=row.approver,
                    when=row.approved_at,
                    posture=Posture(row.posture) if row.posture else None,
                )
                for row in approval_rows
            },
            attestations=tuple(
                MetricAttestation(
                    gate_id=row.gate_id,
                    metric_id=MetricId(row.metric_id),
                    attester=row.attester,
                    when=row.attested_at,
                    evidence=row.evidence,
                )
                for row in attestation_rows
            ),
        )
        self._managed[row_id] = launch
        return launch

    async def _insert(self, row_id: uuid.UUID, launch: Launch) -> None:
        self._session.add(
            LaunchPosition(
                product_id=row_id,
                playbook_version=launch.playbook_version,
                current_gate=launch.current_gate,
                launch_date=launch.launch_date,
            )
        )
        try:
            # Flush the spine row before the child rows: no ORM
            # relationships link these mappers, so without the flush the
            # unit of work may emit a child insert first and trip its own
            # foreign key.
            await self._session.flush()
            self._add_children(row_id, launch)
            await self._session.commit()
        except IntegrityError as exc:
            # Either the product does not exist (foreign key) or it
            # already has a launch (primary key) — both are rejections.
            await self._session.rollback()
            raise LaunchRepositoryError(
                f"could not persist a launch for product "
                f"'{launch.product_id.value}': the product is unknown or "
                f"already has one"
            ) from exc

    async def _update(self, row_id: uuid.UUID, launch: Launch) -> None:
        position = await self._session.get(LaunchPosition, row_id)
        if position is None:
            raise LaunchRepositoryError(
                f"product '{launch.product_id.value}' has no launch record"
            )
        position.playbook_version = launch.playbook_version
        position.current_gate = launch.current_gate
        position.launch_date = launch.launch_date
        for model in (
            LaunchStepProgress,
            LaunchGateApproval,
            LaunchMetricAttestation,
        ):
            await self._session.execute(delete(model).where(model.product_id == row_id))
        self._add_children(row_id, launch)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise LaunchRepositoryError(
                f"could not persist the launch for product '{launch.product_id.value}'"
            ) from exc

    def _add_children(self, row_id: uuid.UUID, launch: Launch) -> None:
        for step_id in launch.recorded_step_ids:
            progress = launch.progress_for(step_id)
            assert progress is not None
            kind, reason = _outcome_to_row(progress.outcome)
            self._session.add(
                LaunchStepProgress(
                    product_id=row_id,
                    step_id=step_id,
                    outcome_kind=kind,
                    outcome_reason=reason,
                    source=progress.provenance.source,
                    who=progress.provenance.who,
                    recorded_at=progress.provenance.when,
                    evidence=progress.provenance.evidence,
                )
            )
        for gate_id in launch.approved_gate_ids:
            approval = launch.approval_for(gate_id)
            assert approval is not None
            self._session.add(
                LaunchGateApproval(
                    product_id=row_id,
                    gate_id=gate_id,
                    decision=approval.decision.value,
                    approver=approval.approver,
                    approved_at=approval.when,
                    posture=approval.posture.value if approval.posture else None,
                )
            )
        for attestation in launch.attestations:
            self._session.add(
                LaunchMetricAttestation(
                    product_id=row_id,
                    gate_id=attestation.gate_id,
                    metric_id=attestation.metric_id.value,
                    attester=attestation.attester,
                    attested_at=attestation.when,
                    evidence=attestation.evidence,
                )
            )
