"""drop the metric attestation table

Revision ID: c04d95ba6e31
Revises: b8e402cf17a9
Create Date: 2026-09-01

The last of `replace-metric-conditions-with-steps`. Nothing reads or
writes `launch_metric_attestations` after the preceding revisions: the
aggregate no longer carries attestations, the repository no longer
persists or rehydrates them, and `MetricAttestation` is gone.

Ordered last on purpose. This is the one irreversible step of the change,
and it belongs after the additive work has demonstrably landed.

**On what this discards.** design.md Decision 7 gated the drop on the
table being empty in production, on the reasoning that a stored row would
be an attestation the change has no account of. That gate was lifted
deliberately: the production database currently holds test data, recorded
by the person who owns it, so a row here preserves nothing. Every row
observed while implementing this change was fixture residue -- evidence
text reading "attested for this fixture", dated 2027 -- written by the
integration tier and never by the application, no driving adapter having
ever called `record_metric_attestation`.

Downgrade recreates the table empty, with its original columns,
constraint and cascade. It cannot restore rows, which is what makes this
the irreversible step rather than merely the last one.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c04d95ba6e31"
down_revision: str | Sequence[str] | None = "b8e402cf17a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_GATE_IDS = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)
_GATE_LIST = ", ".join(f"'{gate}'" for gate in _GATE_IDS)


def upgrade() -> None:
    op.drop_table("launch_metric_attestations")


def downgrade() -> None:
    op.create_table(
        "launch_metric_attestations",
        sa.Column(
            "product_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "launch_positions.product_id",
                name="fk_launch_metric_attestations_product_id",
                ondelete="CASCADE",
            ),
            primary_key=True,
        ),
        sa.Column("gate_id", sa.String(), primary_key=True),
        sa.Column("metric_id", sa.String(), primary_key=True),
        sa.Column("attester", sa.String(), nullable=False),
        sa.Column("attested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", sa.String(), nullable=False),
        sa.CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_metric_attestations_gate_id_valid",
        ),
    )
