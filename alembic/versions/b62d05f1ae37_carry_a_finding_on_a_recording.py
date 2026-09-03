"""Carry a finding on a recording, and across the wait for a confirmer.

A recording may now carry the finding that produced it -- the field the
value was written to, how that field reads, the value, and the comment.
One `jsonb` column per store rather than four columns: the shape moves
when a second sink writes an array where the first wrote a string, and
`NULL` is then the whole of "carries nothing" with an empty *value*
living inside a finding that exists.

`automated_step_results` gets the same column because a terminal outcome
on a step naming a confirmer is *held*, and its recording is made when a
member accepts. A finding kept only on the recording the pass makes would
never reach such a step at all -- which is every step this is for.

No backfill. Absent is the correct reading for every existing row in
either table, and every one of them was written before a finding could be
carried.

Revision ID: b62d05f1ae37
Revises: f4b7c1e09d52
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "b62d05f1ae37"
down_revision = "f4b7c1e09d52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("launch_step_progress", "automated_step_results"):
        op.add_column(
            table,
            sa.Column("finding", postgresql.JSONB(), nullable=True),
        )


def downgrade() -> None:
    for table in ("launch_step_progress", "automated_step_results"):
        op.drop_column(table, "finding")
