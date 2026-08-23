"""split products into catalog and launch positions

Revision ID: e8a3c5f19d42
Revises: 7c1a4f2b9e30
Create Date: 2026-08-23

The table split `introduce-catalog-and-shared-vocabulary` mandates
(design.md Decisions 7-8, Migration Plan): `products` becomes the
catalog-owned identity + stage record; `playbook_version`, `current_gate`
and `launch_date` move to a `launch_positions` table keyed by product.

Backfill (design.md Decision 8): existing rows are launch-in-progress
records by construction, so they get the Amazon US marketplace, the
`Launching` phase-1 stage entered at migration time, and a migration-named
confirmer so the guess is auditable. Every added column goes
nullable -> backfill -> non-null, except `stage_confirmed_by`, which stays
nullable (absent until a product's first stage change).

Downgrade re-fuses the columns from `launch_positions`. A product with no
`launch_positions` row (registered catalog-only after the upgrade) is
DROPPED by the downgrade -- the pre-split schema cannot represent a product
without launch fields, and inventing them would be worse (design.md,
Migration Plan step 3).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from commerce_ops.products.infrastructure.driven.models import GATE_IDS

# revision identifiers, used by Alembic.
revision: str = "e8a3c5f19d42"
down_revision: str | Sequence[str] | None = "7c1a4f2b9e30"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GATE_LIST = ", ".join(f"'{gate}'" for gate in GATE_IDS)
_STAGE_LIST = ", ".join(
    f"'{kind}'" for kind in ("development", "launching", "steady-state", "retired")
)

BACKFILL_MARKETPLACE = "ATVPDKIKX0DER"
BACKFILL_CONFIRMER = "migration:introduce-catalog-and-shared-vocabulary"


def upgrade() -> None:
    # 1. Catalog columns, nullable first so existing rows survive the ADD.
    op.add_column("products", sa.Column("marketplace_id", sa.String(), nullable=True))
    op.add_column("products", sa.Column("stage", sa.String(), nullable=True))
    op.add_column(
        "products", sa.Column("launching_phase", sa.SmallInteger(), nullable=True)
    )
    op.add_column("products", sa.Column("posture", sa.String(), nullable=True))
    op.add_column(
        "products",
        sa.Column("stage_entered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "products", sa.Column("stage_confirmed_by", sa.String(), nullable=True)
    )

    # 2. Backfill: every existing row is a launch-in-progress record.
    op.execute(
        "UPDATE products SET "
        f"marketplace_id = '{BACKFILL_MARKETPLACE}', "
        "stage = 'launching', "
        "launching_phase = 1, "
        "stage_entered_at = now(), "
        f"stage_confirmed_by = '{BACKFILL_CONFIRMER}'"
    )

    # 3. Non-null where the model requires it; `stage_confirmed_by` stays
    #    nullable per the registration-provenance rule.
    op.alter_column("products", "marketplace_id", nullable=False)
    op.alter_column("products", "stage", nullable=False)
    op.alter_column("products", "stage_entered_at", nullable=False)
    op.create_check_constraint(
        "ck_products_stage_valid", "products", f"stage IN ({_STAGE_LIST})"
    )

    # 4. The launch-position record.
    op.create_table(
        "launch_positions",
        sa.Column(
            "product_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("products.id", name="fk_launch_positions_product_id"),
            primary_key=True,
        ),
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
            f"current_gate IN ({_GATE_LIST})",
            name="ck_launch_positions_current_gate_valid",
        ),
    )
    op.execute(
        "INSERT INTO launch_positions "
        "(product_id, playbook_version, current_gate, launch_date) "
        "SELECT id, playbook_version, current_gate, launch_date FROM products"
    )

    # 5. The launch fields leave the catalog record.
    op.drop_constraint("ck_products_current_gate_valid", "products")
    op.drop_column("products", "playbook_version")
    op.drop_column("products", "current_gate")
    op.drop_column("products", "launch_date")


def downgrade() -> None:
    # 1. The launch fields return, nullable while they are re-fused.
    op.add_column("products", sa.Column("playbook_version", sa.String(), nullable=True))
    op.add_column("products", sa.Column("current_gate", sa.String(), nullable=True))
    op.add_column("products", sa.Column("launch_date", sa.Date(), nullable=True))
    op.execute(
        "UPDATE products SET "
        "playbook_version = lp.playbook_version, "
        "current_gate = lp.current_gate, "
        "launch_date = lp.launch_date "
        "FROM launch_positions AS lp WHERE products.id = lp.product_id"
    )

    # 2. Catalog-only products cannot exist in the pre-split schema: dropped,
    #    per design.md Migration Plan step 3.
    op.execute("DELETE FROM products WHERE playbook_version IS NULL")

    op.alter_column("products", "playbook_version", nullable=False)
    op.alter_column("products", "current_gate", nullable=False)
    op.create_check_constraint(
        "ck_products_current_gate_valid", "products", f"current_gate IN ({_GATE_LIST})"
    )

    # 3. The split artifacts leave.
    op.drop_table("launch_positions")
    op.drop_constraint("ck_products_stage_valid", "products")
    op.drop_column("products", "stage_confirmed_by")
    op.drop_column("products", "stage_entered_at")
    op.drop_column("products", "posture")
    op.drop_column("products", "launching_phase")
    op.drop_column("products", "stage")
    op.drop_column("products", "marketplace_id")
