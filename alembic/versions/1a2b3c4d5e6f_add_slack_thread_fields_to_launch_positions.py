"""add slack thread fields to launch positions

Revision ID: 1a2b3c4d5e6f
Revises: 028812c68321

Two nullable columns for thread-launch-slack-notifications:
- submitter: the Slack identity of whoever submitted the launch, recorded
  once at start and never mutated afterward
- slack_thread_id: the `ts` of the anchor message in the launches channel,
  absent until the first per-product message is delivered

Both columns are nullable with no default, and no backfill is performed:
every launch predating this migration simply has both absent, and the
lazy-establishment mechanism creates a thread the first time any per-product
message needs to be sent for it.

Create Date: 2026-08-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1a2b3c4d5e6f"
down_revision: str | Sequence[str] | None = "028812c68321"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "launch_positions",
        sa.Column("submitter", sa.String(), nullable=True),
    )
    op.add_column(
        "launch_positions",
        sa.Column("slack_thread_id", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_positions", "slack_thread_id")
    op.drop_column("launch_positions", "submitter")
