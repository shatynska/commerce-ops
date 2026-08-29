"""add the columns saying when a step may start

Revision ID: b4e21f9a76c8
Revises: f7a3c81b25d9
Create Date: 2026-08-29

Step 1 of `let-a-step-say-when-it-starts`'s Migration Plan: `playbook_steps`
gains the two authored fields that say when a step becomes eligible.

**This revision is inert on its own, and that is the whole of its design.**
Both defaults reproduce today's behaviour exactly — a null `starts_at_gate`
means "from the launch's first gate" and an empty `after_steps` means "waits
on nothing" — so every step stays released from a launch's first pass and all
three consumers behave as they did before. What changes behaviour is the
backfill revision that follows, which is deliberately a separate step: this
one can be deployed, observed and rolled back without any launch moving.

The two columns are shaped unlike each other on purpose. `starts_at_gate` is
nullable because absent is a *meaningful authored value* — "starts
immediately" — and the column must be able to hold it; the backfill's
`WHERE ... IS NULL` guard also depends on null being distinguishable from a
written value, which is what lets the backfill be re-run without overwriting
an author's decision. `after_steps` is NOT NULL defaulting to `[]`, mirroring
`assignees`, because empty and "no dependency" are one fact and a nullable
array would give one fact two spellings.

Downgrade drops both columns, losing whatever the backfill and any authoring
since then wrote. That is not a hazard in the way the seed's rollback is: a
step with no `starts_at_gate` is a step that starts immediately, so a
downgraded deployment resolves and projects everything from gate one — the
behaviour that stood before this change, and never a stranded launch.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b4e21f9a76c8"
down_revision: str | Sequence[str] | None = "f7a3c81b25d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "playbook_steps",
        sa.Column("starts_at_gate", sa.String(), nullable=True),
    )
    # `server_default` and not merely the model's `default=list`: existing
    # rows need a value at the moment the NOT NULL is applied, and a column
    # default written by the database is what gives them one without a
    # separate UPDATE. The model keeps its own default for rows the
    # application inserts.
    op.add_column(
        "playbook_steps",
        sa.Column(
            "after_steps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("playbook_steps", "after_steps")
    op.drop_column("playbook_steps", "starts_at_gate")
