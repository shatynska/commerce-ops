"""add the Custom Field configuration-gap suppression record

Revision ID: c9f2a4d7b613
Revises: e4b91c73a2d5

One table, holding at most one row.

`record-gate-and-discipline-as-fields` reports a Custom Field configuration
gap to Slack, and reports a *continuing* gap once rather than on every pass
-- a misconfiguration left in place over days must produce one message, not
a wall of identical ones that trains the team to ignore the channel. This is
where "already reported" is remembered.

It is a table rather than process state for the reason `scheduled-jobs`
already gives for the equivalent record: a restart must not resume the
flood, and a crash-looping worker would otherwise report on every restart.

It is **separate from `scheduled_run_report_suppression`** despite the
similar shape, because the two lifecycles are incompatible. That row is
keyed by a piece of recurring *work* and is lifted when the work succeeds;
this pass succeeds precisely *while* the gap stands, so lifting on success
would clear the row on the very passes it exists to suppress. The rule that
suppression is written only after a delivered report is borrowed; the
storage is not. See design.md, "Suppression gets its own table".

`identity` holds the gap's whole content -- per field, the set of gap kinds
found, the missing option names, the duplicated names and the gate-option
order observed. Content rather than mere existence: a gap that *changes*
names a repair nobody has been asked for yet and must be reported again,
while an unchanged one must not. Storing only "a gap exists" would make a
wrong-typed field and a wrongly-ordered one indistinguishable, so repairing
one into the other would meet silence -- which is the failure the report
exists to prevent.

Create Date: 2026-08-27 16:20:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9f2a4d7b613"
down_revision: str | Sequence[str] | None = "e4b91c73a2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "clickup_field_gap_suppression",
        # At most one row ever. The gap is a property of the deployment's
        # configuration rather than of any launch, so there is nothing to key
        # it by; a fixed primary key makes "one row" a schema guarantee
        # rather than a convention the writer has to keep.
        sa.Column(
            "id",
            sa.Boolean(),
            primary_key=True,
            server_default=sa.true(),
        ),
        sa.Column("identity", sa.Text(), nullable=False),
        sa.Column(
            "reported_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.CheckConstraint("id IS TRUE", name="clickup_field_gap_suppression_single"),
    )


def downgrade() -> None:
    op.drop_table("clickup_field_gap_suppression")
