"""add the redesigned step-field columns

Revision ID: c3a1f74d8b26
Revises: a3d7e9f2c481
Create Date: 2026-08-25

Step 1 of `redesign-step-fields`'s Migration Plan: `playbook_steps`
gains the new columns, all nullable, and keeps `binding`, `execution`
and `rule_policy` — so this revision alone changes nothing about what
the deployed code reads and can be rolled back by redeploying the
previous image.

`description` becomes nullable in the same breath, because the backfill
that follows sets it null: the row's text becomes the step's `name`, and
a description is what an author adds when the name is not enough.

`launch_clickup_tasks` gains `retained_assignees` here too, for the same
reason it carries `retained_name` and `retained_body`: the projection
respects a person's own assignment change, which it can only tell by
comparing what a task carries against what the system last set.

Downgrade drops every column this adds and restores `description`'s NOT
NULL — safe only while nothing has been backfilled, which is exactly the
window this revision opens.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3a1f74d8b26"
down_revision: str | Sequence[str] | None = "a3d7e9f2c481"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ADDED = (
    ("name", sa.Text()),
    ("kind", sa.String()),
    ("needs_confirmation", sa.Boolean()),
    ("status", sa.String()),
    ("assignees", postgresql.JSONB(astext_type=sa.Text())),
    ("automation_brief", sa.Text()),
    ("handler", sa.Text()),
)


def upgrade() -> None:
    for column, kind in _ADDED:
        op.add_column("playbook_steps", sa.Column(column, kind, nullable=True))
    op.alter_column("playbook_steps", "description", nullable=True)
    op.add_column(
        "launch_clickup_tasks",
        sa.Column(
            "retained_assignees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("launch_clickup_tasks", "retained_assignees")
    op.execute("UPDATE playbook_steps SET description = '' WHERE description IS NULL")
    op.alter_column("playbook_steps", "description", nullable=False)
    for column, _ in reversed(_ADDED):
        op.drop_column("playbook_steps", column)
