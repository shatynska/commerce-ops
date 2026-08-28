"""add the gate-ask suppression record

Revision ID: f7a3c81b25d9
Revises: b3f9d17ca204

One table, at most one row per (launch, gate).

`advance-gates-and-confirm-in-slack` asks a person to approve a gate whose
every other condition is met, and asks at most once a day. This is where
"already put to someone" is remembered.

A table rather than process state, for the reason `clickup_field_gap_suppression`
already records for its own row: a restart must not resume the flood the record
exists to prevent.

Keyed by (product, gate) rather than holding a single row, because the question
it answers is per launch and per gate: two launches standing at `commit` are two
separate asks, and the same launch reaching `order` tomorrow is a third.

`asked_at` is named for the moment rather than for a delivery because it has
**two** writers. An ask writes it, only after the message reaches Slack. A
*rejecting decision* also writes it, having delivered nothing at all -- the day
must run from the decision rather than from the ask that prompted it, or a
person who declines a gate at hour 23 is asked again an hour later.

No foreign key to `launch_positions`, deliberately. A launch deleted by hand --
this deployment does that, and keeps the scripts for it -- would otherwise
either block the deletion or have this table silently rewritten beneath it. The
orphan row is unreachable instead: every read is keyed by a product the walk
found, and a deleted launch is never walked.

Create Date: 2026-08-28 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7a3c81b25d9"
down_revision: str | Sequence[str] | None = "b3f9d17ca204"
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
    op.create_table(
        "launch_gate_ask_suppression",
        sa.Column("product_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gate_id", sa.String(), primary_key=True),
        sa.Column("asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            f"gate_id IN ({_GATE_LIST})",
            name="ck_launch_gate_ask_suppression_gate_valid",
        ),
    )


def downgrade() -> None:
    op.drop_table("launch_gate_ask_suppression")
