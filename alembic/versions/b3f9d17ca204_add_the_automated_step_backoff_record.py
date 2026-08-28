"""add the repeat-backoff record for the automation pass

Revision ID: b3f9d17ca204
Revises: a7c2e5b81f43
Create Date: 2026-08-28

`cool-off-a-repeatedly-blocked-step`'s only schema change: where an
automated step's handler repeats the non-terminal outcome the step
already carries, that fact is kept here, and the step is neither asked
again for a cool-off nor reported more than once.

**One row carries both decisions** — the cool-off and the report
suppression. They key on the same launch and step and are lifted by the
same event, so two tables would need the same writes and could disagree.

`noted_kind` holds the outcome's *kind* and never the outcome: `Blocked`
carries a reason, an LLM-backed handler rewords it on every call, and a
value comparison would find no two blocks alike — the cool-off would
engage never while the rule appeared to work.

Nothing lifts a row explicitly. A row whose kind is not that of the
step's currently recorded outcome governs nothing, which is what lets
every other surface that records an outcome stay untouched.

Downgrade drops the table. Every step then returns to the fifteen-minute
cadence — the behaviour before this change, which is a cost problem
rather than an outage — and any report already delivered stays delivered.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f9d17ca204"
down_revision: str | Sequence[str] | None = "a7c2e5b81f43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# The `launch-playbook` outcome vocabulary, as `models.OUTCOME_KINDS`
# spells it. A standalone copy for the reason every other constraint in
# these migrations keeps one.
_OUTCOME_KINDS = (
    "not-started",
    "in-progress",
    "satisfied",
    "blocked",
    "refused",
    "not-applicable",
)


def upgrade() -> None:
    op.create_table(
        "automated_step_backoff",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("step_id", sa.String(), nullable=False),
        sa.Column("noted_kind", sa.String(), nullable=False),
        sa.Column("noted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint(
            "product_id", "step_id", name="pk_automated_step_backoff"
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["launch_positions.product_id"],
            name="fk_automated_step_backoff_product_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "noted_kind IN (" + ", ".join(f"'{kind}'" for kind in _OUTCOME_KINDS) + ")",
            name="ck_automated_step_backoff_noted_kind_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("automated_step_backoff")
