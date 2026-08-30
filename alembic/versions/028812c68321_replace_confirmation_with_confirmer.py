"""replace needs_confirmation and automation_brief with confirmer

Revision ID: 028812c68321
Revises: d5f83b1e04a7
Create Date: 2026-08-30

`add-step-confirmer`'s field-set change: `needs_confirmation` (bool) and
`automation_brief` (text) go, and `confirmer` (a nullable roster
identifier, unconstrained at the database level like `assignees` and
`handler`) replaces them both. A named confirmer now carries the whole
of what the boolean used to mean — a step naming one requires
confirmation, a step naming none does not — and `automation_brief` had
no remaining reader once a step's `handler` existed.

No backfill: confirmed with the project that every row this deployment
holds is test data, so nothing here needs to survive.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "028812c68321"
down_revision: str | Sequence[str] | None = "d5f83b1e04a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("playbook_steps", sa.Column("confirmer", sa.String(), nullable=True))
    op.drop_column("playbook_steps", "needs_confirmation")
    op.drop_column("playbook_steps", "automation_brief")


def downgrade() -> None:
    op.add_column(
        "playbook_steps",
        sa.Column("needs_confirmation", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "playbook_steps", sa.Column("automation_brief", sa.Text(), nullable=True)
    )
    # `automation_brief` cannot be re-derived and comes back NULL for every
    # row. `needs_confirmation` is recovered exactly, since a named
    # confirmer is precisely the successor state to it being true.
    op.execute(
        """
        UPDATE playbook_steps
        SET needs_confirmation = (confirmer IS NOT NULL)
        """
    )
    op.alter_column("playbook_steps", "needs_confirmation", nullable=False)
    op.drop_column("playbook_steps", "confirmer")
