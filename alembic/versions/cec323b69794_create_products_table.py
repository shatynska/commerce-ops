"""create products table

Revision ID: cec323b69794
Revises:
Create Date: 2026-08-21 16:03:10.483981

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from commerce_ops.products.infrastructure.driven.models import GATE_IDS

# revision identifiers, used by Alembic.
revision: str = "cec323b69794"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    gate_list = ", ".join(f"'{gate}'" for gate in GATE_IDS)
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sku", sa.String(), nullable=False, unique=True),
        sa.Column("asin", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("playbook_version", sa.String(), nullable=False),
        sa.Column("current_gate", sa.String(), nullable=False),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            f"current_gate IN ({gate_list})",
            name="ck_products_current_gate_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("products")
