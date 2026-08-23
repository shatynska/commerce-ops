"""add launch aggregate child tables

Revision ID: f1b6d842a7c3
Revises: b4e7d21c8a90
Create Date: 2026-08-23

The additive migration `introduce-launch-aggregate` mandates (design.md
Decision 7, Migration Plan): three child tables holding the `Launch`
aggregate's recorded state — step progress with recording provenance,
gate approvals, metric attestations — each keyed by
`launch_positions.product_id` with cascade delete. `launch_positions`
itself is untouched; existing rows remain valid as launches with no
recorded progress.

Downgrade drops only the three child tables, losing any recorded
progress, approvals and attestations (stated plainly in the change's
migration plan).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from commerce_ops.launch.infrastructure.driven.models import (
    APPROVAL_DECISIONS,
    GATE_IDS,
    OUTCOME_KINDS,
    PROVENANCE_SOURCES,
)

# revision identifiers, used by Alembic.
revision: str = "f1b6d842a7c3"
down_revision: str | Sequence[str] | None = "b4e7d21c8a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GATE_LIST = ", ".join(f"'{gate}'" for gate in GATE_IDS)
_OUTCOME_LIST = ", ".join(f"'{kind}'" for kind in OUTCOME_KINDS)
_SOURCE_LIST = ", ".join(f"'{source}'" for source in PROVENANCE_SOURCES)
_DECISION_LIST = ", ".join(f"'{decision}'" for decision in APPROVAL_DECISIONS)


def upgrade() -> None:
    op.create_table(
        "launch_step_progress",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("outcome_kind", sa.String(), nullable=False),
        sa.Column("outcome_reason", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("who", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "step_id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_step_progress_product_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"outcome_kind IN ({_OUTCOME_LIST})",
            name="ck_launch_step_progress_outcome_kind_valid",
        ),
        sa.CheckConstraint(
            f"source IN ({_SOURCE_LIST})",
            name="ck_launch_step_progress_source_valid",
        ),
    )
    op.create_table(
        "launch_gate_approvals",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_id", sa.String(), nullable=False),
        sa.Column("decision", sa.String(), nullable=False),
        sa.Column("approver", sa.String(), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("posture", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("product_id", "gate_id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_gate_approvals_product_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"decision IN ({_DECISION_LIST})",
            name="ck_launch_gate_approvals_decision_valid",
        ),
        sa.CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_gate_approvals_gate_id_valid",
        ),
    )
    op.create_table(
        "launch_metric_attestations",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("gate_id", sa.String(), nullable=False),
        sa.Column("metric_id", sa.String(), nullable=False),
        sa.Column("attester", sa.String(), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "gate_id", "metric_id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_metric_attestations_product_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_metric_attestations_gate_id_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("launch_metric_attestations")
    op.drop_table("launch_gate_approvals")
    op.drop_table("launch_step_progress")
