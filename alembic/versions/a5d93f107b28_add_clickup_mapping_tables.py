"""add clickup mapping tables

Revision ID: a5d93f107b28
Revises: f1b6d842a7c3
Create Date: 2026-08-23

The additive migration `add-clickup-completion-loop` mandates (design.md,
"Mapping lives in two launch-infrastructure tables"): the per-launch
ClickUp list association, and the per-step task association carrying the
closed state last observed for that task. Both are keyed by
`launch_positions.product_id` with cascade delete, following the three
child tables `f1b6d842a7c3` added.

`launch_clickup_tasks` is unique on both sides: its primary key gives a
step one task, and the unique constraint on `task_id` gives a task one
step — webhook intake resolves a delivery by task identifier alone.

Downgrade drops both tables. What is lost is the mapping and the retained
observed state, not any launch progress: the next pass re-projects the
lists and tasks, and the loop resumes with nothing observed, so an
already-closed task records its completion again.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5d93f107b28"
down_revision: str | Sequence[str] | None = "f1b6d842a7c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "launch_clickup_lists",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("list_id", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("product_id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_clickup_lists_product_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("list_id", name="uq_launch_clickup_lists_list_id"),
    )
    op.create_table(
        "launch_clickup_tasks",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("last_observed_closed", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("product_id", "step_id"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_clickup_tasks_product_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("task_id", name="uq_launch_clickup_tasks_task_id"),
    )


def downgrade() -> None:
    op.drop_table("launch_clickup_tasks")
    op.drop_table("launch_clickup_lists")
