"""add the pending-result store for the automation runtime

Revision ID: e4b91c73a2d5
Revises: d5f0a9c62e18
Create Date: 2026-08-26

`introduce-automation-runtime`'s only schema change: where an automated
step's handler proposes a terminal outcome and the step needs
confirmation, the result waits here instead of being recorded.

**The partial unique index is the point of this revision**, not an
optimisation on it. "At most one pending result per launch and step" has
to hold against two overlapping passes, and a read-then-write in
application code cannot promise that — only the database can. `state` is
in the predicate rather than the key because settled rows are kept
forever: a step may accumulate any number of accepted, rejected and
voided rows over its life, and exactly one pending one at a time.

Downgrade drops the table, losing any *undecided* pending results with
it. Recorded outcomes are unaffected — those live on the launch, not
here — so a rollback degrades to "the proposals nobody had answered yet
are gone", and the next pass produces fresh ones.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e4b91c73a2d5"
down_revision: str | Sequence[str] | None = "d5f0a9c62e18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "automated_step_results",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("handler", sa.String(), nullable=False),
        sa.Column("proposed_outcome", sa.String(), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=False),
        sa.Column("produced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "state", sa.String(), nullable=False, server_default=sa.text("'pending'")
        ),
        sa.Column("decided_by", sa.String(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_automated_step_results_product_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "uq_automated_step_results_one_pending",
        "automated_step_results",
        ["product_id", "step_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending'"),
    )
    # The reads the pass makes every cycle: what is undelivered, and the
    # most recent rejection for a step. Neither is unique.
    op.create_index(
        "ix_automated_step_results_step",
        "automated_step_results",
        ["product_id", "step_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("ix_automated_step_results_step", table_name="automated_step_results")
    op.drop_index(
        "uq_automated_step_results_one_pending",
        table_name="automated_step_results",
    )
    op.drop_table("automated_step_results")
