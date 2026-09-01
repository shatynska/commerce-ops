"""add the step metric identifier

Revision ID: f3a71c58b0d2
Revises: d715ad9feed4
Create Date: 2026-09-01

`replace-metric-conditions-with-steps` moves the metric identifier off the
gate and onto the step that establishes the quantity. Nullable, because
almost every step declares none: the column records where a named quantity
is established for a launch, so an observation of the same quantity can
later be related to it, and it changes no rule in the meantime.

This migration adds the column and nothing else. The six reference rows
that carry a value arrive through the **preparation step**, not here --
`launch-playbook`'s *The step set is seeded before the application serves*
assigns a reference row added later to that step and states that the
migration machinery cannot express it, a migration running exactly once per
environment. The ordering matters in one direction only: this column must
exist before the preparation step next runs, which it does, the step
running between migration and server.

Downgrade drops the column. A step's identifier is inert, so nothing else
reads it and dropping it loses only the values themselves.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a71c58b0d2"
down_revision: str | Sequence[str] | None = "d715ad9feed4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("playbook_steps", sa.Column("metric_id", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("playbook_steps", "metric_id")
