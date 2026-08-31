"""add the product sub-category column

Revision ID: e6c1a92d7f04
Revises: d5f83b1e04a7
Create Date: 2026-08-31

`write-the-advisors-finding-to-the-product`'s Migration Plan: `products`
gains `sub_category`, nullable, no backfill — every existing product
simply has no sub-category recorded until the advisor next resolves
`lp.listing.007` for it.

Downgrade drops the column; nothing else reads it yet, so this is safe in
both directions.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c1a92d7f04"
down_revision: str | Sequence[str] | None = "d5f83b1e04a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("products", sa.Column("sub_category", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "sub_category")
