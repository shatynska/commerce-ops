"""add admin session tables

Revision ID: f4c8b1d97a25
Revises: e7f2a9c31b64
Create Date: 2026-08-24

The session half of `add-playbook-admin-ui`'s Migration Plan:
`admin_link_tokens` (the single-use tokens the Slack command mints,
stored hashed, with expiry and a spent flag) and `admin_sessions` (the
browser sessions they exchange for, stored hashed, with expiry). Both
land empty; nothing backfills.

Downgrade drops both. Lost are any live admin sessions and unspent
links — every admin simply mints a fresh link, so the loss costs one
Slack command per person.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4c8b1d97a25"
down_revision: str | Sequence[str] | None = "e7f2a9c31b64"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_link_tokens",
        sa.Column("token_hash", sa.String(), primary_key=True),
        sa.Column("principal", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spent", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("session_hash", sa.String(), primary_key=True),
        sa.Column("principal", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("admin_sessions")
    op.drop_table("admin_link_tokens")
