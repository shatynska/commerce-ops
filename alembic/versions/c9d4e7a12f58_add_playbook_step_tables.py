"""add playbook step tables

Revision ID: c9d4e7a12f58
Revises: a5d93f107b28
Create Date: 2026-08-24

The schema half of `move-playbook-steps-to-postgres`'s Migration Plan,
step 1: the step tables land empty — `playbook_steps` (one row per step
definition, with the attribution trail authoring writes) and the
`playbook_step_set` singleton carrying the optimistic set-version that
serializes every write — and `launch_clickup_tasks` gains the two
nullable retained-composition columns conditional wording-healing keys
on (null on rows predating this change: adopt-if-matching on first
observation, per the delta).

The set-version row is created at 0; the seed migration that follows
populates the steps and performs the first bump, so an unseeded database
is distinguishable from a seeded-then-emptied one.

Downgrade drops the two step tables and the retained columns. Lost with
the tables is every authored edit made since the seed — the recorded,
accepted data-loss of the change's rollback plan; lost with the columns
is only healing eligibility, which legacy adoption re-establishes for
unedited tasks.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9d4e7a12f58"
down_revision: str | Sequence[str] | None = "a5d93f107b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playbook_steps",
        sa.Column("identifier", sa.String(), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("gate", sa.String(), nullable=False),
        sa.Column("discipline", sa.String(), nullable=False),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("timing_anchor", postgresql.JSONB(), nullable=False),
        sa.Column("binding", sa.String(), nullable=False),
        sa.Column("blocking", sa.Boolean(), nullable=False),
        sa.Column("execution", sa.String(), nullable=False),
        sa.Column("hazard", sa.String(), nullable=False),
        sa.Column("rule_policy", sa.Text(), nullable=True),
        sa.Column("provenance", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(), nullable=True),
        sa.Column("retired_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unretired_by", sa.String(), nullable=True),
        sa.Column("unretired_on", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "playbook_step_set",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_playbook_step_set_singleton"),
    )
    op.execute("INSERT INTO playbook_step_set (id, version) VALUES (1, 0)")
    op.add_column(
        "launch_clickup_tasks",
        sa.Column("retained_name", sa.Text(), nullable=True),
    )
    op.add_column(
        "launch_clickup_tasks",
        sa.Column("retained_body", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("launch_clickup_tasks", "retained_body")
    op.drop_column("launch_clickup_tasks", "retained_name")
    op.drop_table("playbook_step_set")
    op.drop_table("playbook_steps")
