"""add roster tables

Revision ID: a3d7e9f2c481
Revises: f4c8b1d97a25
Create Date: 2026-08-25

The persistence half of `move-principals-to-roster`: `roster_people`
(one row per known human, with identity data, the admin and active
flags, and the attribution trail that replaces the deleted
`principals.yaml`'s git history) and `roster_set` (the singleton
optimistic version serializing every roster write, the shape
`playbook_step_set` established).

Both land empty, and the version singleton is seeded at 0 — the store
treats its absence as "the migration has not run" rather than as an
empty roster. Nothing backfills: the YAML's sole admin entry is
reproduced at startup by the bootstrap seed reading
`BOOTSTRAP_ADMIN_IDENTITY`.

Downgrade drops both tables. Lost is the whole roster, which is every
declared person and their attribution — after a downgrade, the next
start seeds the bootstrap admin again from the environment, and every
other person must be re-entered from the roster page.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3d7e9f2c481"
down_revision: str | Sequence[str] | None = "f4c8b1d97a25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roster_people",
        sa.Column("identifier", sa.String(), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("slack_identity", sa.String(), nullable=False, unique=True),
        sa.Column("clickup_user_id", sa.String(), nullable=True),
        sa.Column("admin", sa.Boolean(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_by", sa.String(), nullable=True),
        sa.Column("deactivated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reactivated_by", sa.String(), nullable=True),
        sa.Column("reactivated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admin_conferred_by", sa.String(), nullable=True),
    )
    op.create_table(
        "roster_set",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_roster_set_singleton"),
    )
    # The singleton every write serializes on. Created here, never by the
    # application, so a missing row means the migration has not run.
    op.execute("INSERT INTO roster_set (id, version) VALUES (1, 0)")


def downgrade() -> None:
    op.drop_table("roster_set")
    op.drop_table("roster_people")
