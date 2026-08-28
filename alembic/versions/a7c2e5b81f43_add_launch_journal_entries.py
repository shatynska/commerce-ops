"""add the append-only launch journal

Revision ID: a7c2e5b81f43
Revises: e4b91c73a2d5
Create Date: 2026-08-28

`add-launch-journal`'s only schema change: one table recording what
happened to a launch, kept independently of the state that produced it.
Additive — no existing table is altered and no row changes.

**There is nothing to backfill from.** The occurrences this table records
were discarded as they were raised, which is the change's whole premise.
Launches that predate this revision therefore have empty journals for
ever, and the read reports that as an empty journal rather than an error.

`sequence` is the primary key because this table is about order: two
entries routinely name the same `occurred_at` — one reconciliation pass
recording several steps — so "most recent first" needs a total order, and
a bigint identity gives one.

`occurred_at` defaults to `now()` so that the five kinds whose command
carries no timestamp are stamped by the database; the three that carry
one supply it and the default is not reached.

Downgrade drops the table, losing the history recorded since the upgrade.
Nothing else depends on it: no launch state is derived from a journal
entry, and every command behaves identically with the table absent, since
a failed append is contained.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c2e5b81f43"
down_revision: str | Sequence[str] | None = "e4b91c73a2d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_KINDS = (
    "launch-started",
    "step-outcome-recorded",
    "metric-attested",
    "gate-approval-recorded",
    "gate-opened",
    "launch-graduated",
    "launch-date-moved",
    "advance-refused",
)


def upgrade() -> None:
    op.create_table(
        "launch_journal_entries",
        sa.Column("sequence", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("actor", sa.String(), nullable=True),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("subject_id", sa.String(), nullable=True),
        sa.Column("subject_label", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("sequence", name="pk_launch_journal_entries"),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_launch_journal_entries_product_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "kind IN (" + ", ".join(f"'{kind}'" for kind in _KINDS) + ")",
            name="ck_launch_journal_entries_kind_valid",
        ),
    )
    op.create_index(
        "ix_launch_journal_entries_product_id",
        "launch_journal_entries",
        ["product_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_launch_journal_entries_product_id",
        table_name="launch_journal_entries",
    )
    op.drop_table("launch_journal_entries")
