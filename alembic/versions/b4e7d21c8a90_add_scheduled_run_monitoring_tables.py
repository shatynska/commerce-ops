"""add the scheduled-run monitoring tables

Revision ID: b4e7d21c8a90
Revises: e8a3c5f19d42

Chained onto the catalog/launch-position split rather than onto the job
runner schema directly: both were written against `7c1a4f2b9e30` as their
parent, which made two heads and left `upgrade head` refusing to run. These
two changes are independent of each other, so the order between them is
arbitrary -- what matters is that there is one.
Create Date: 2026-08-23 12:10:00.000000

Two tables, deliberately separate from each other and from the job runner's
own schema.

`scheduled_run_known_work` records when the system first knew of a piece of
recurring work. `scheduled_run_report_suppression` records that an overdue
report has been delivered for one. They cannot be one table: first-known has
to exist *before* any report and persist *across* successes, while the
suppression row is written only *after* a delivered report and cleared *on*
success. One row cannot carry both lifecycles -- folding them either erases
the anchor when work recovers, or breaks the write-after-delivery rule for
the row that carries the anchor. See design.md, "First-known is its own
table".

Neither is folded into the runner's tables, which a runner schema upgrade
could replace (tasks.md 3.1).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e7d21c8a90"
down_revision: str | Sequence[str] | None = "e8a3c5f19d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The identifier is the runner's own task name, which the runner's schema
# declares as `character varying(128)`. Matched here so a name the runner
# accepts cannot fail to be recorded against.
_IDENTIFIER = sa.String(length=128)


def upgrade() -> None:
    op.create_table(
        "known_work",
        sa.Column("identifier", _IDENTIFIER, primary_key=True),
        # The first time this work was observed, and never advanced
        # afterwards. Not a "last seen": the whole point is that it is the
        # earliest moment from which a never-succeeded piece of work can be
        # measured as overdue.
        sa.Column("first_known_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "report_suppression",
        sa.Column("identifier", _IDENTIFIER, primary_key=True),
        # Written only after a report has been delivered successfully, and
        # deleted when the work next succeeds. Its presence is what makes a
        # continuing outage report once rather than every hour.
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_suppression")
    op.drop_table("known_work")
