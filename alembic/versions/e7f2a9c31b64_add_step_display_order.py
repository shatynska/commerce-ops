"""add step display order

Revision ID: e7f2a9c31b64
Revises: d2f8b3c64e17
Create Date: 2026-08-24

The ordering half of `add-playbook-admin-ui`'s Migration Plan, step 1:
`playbook_steps` gains `display_order`, the authored within-gate slot the
reorder write renumbers. The backfill assigns each gate's steps their
position in the order the set was being served in until now — identifier
sort within the gate — so the first ordered read serves exactly what the
last unordered read did (the delta's "SHALL keep the order it was being
served in").

Downgrade drops the column: authored order is lost and serving falls
back to identifier order — the recorded, accepted loss of the change's
rollback plan.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f2a9c31b64"
down_revision: str | Sequence[str] | None = "d2f8b3c64e17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "playbook_steps",
        sa.Column("display_order", sa.Integer(), nullable=True),
    )
    op.execute(
        """
        UPDATE playbook_steps
        SET display_order = numbered.slot
        FROM (
            SELECT identifier,
                   ROW_NUMBER() OVER (
                       PARTITION BY gate ORDER BY identifier
                   ) AS slot
            FROM playbook_steps
        ) AS numbered
        WHERE playbook_steps.identifier = numbered.identifier
        """
    )
    op.alter_column("playbook_steps", "display_order", nullable=False)


def downgrade() -> None:
    op.drop_column("playbook_steps", "display_order")
