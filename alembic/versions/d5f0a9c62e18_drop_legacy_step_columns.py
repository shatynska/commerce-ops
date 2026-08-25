"""drop the step columns the redesign replaced

Revision ID: d5f0a9c62e18
Revises: b8e5c04a1d39
Create Date: 2026-08-25

Step 4 of `redesign-step-fields`'s Migration Plan: `binding`, `execution`
and `rule_policy` go, now that nothing reads them. `binding` had exactly
one enforced effect — a `lesson` may not block its gate — which was a
statement about `blocking` expressed on a second field; `execution`'s
three values are replaced by a kind plus an independent confirmation
flag; and `rule_policy` is carried forward as `automation_brief`, owed
only once a step leaves `draft`.

**Sequencing note.** The Migration Plan puts this after the deploy that
stops reading those columns, and Alembic runs every pending revision in
one `alembic upgrade head` — so landing this revision alongside the
backfill closes the rollback window the plan describes between its steps
2 and 3. Holding it back for a follow-up pull request is what restores
that window.

Downgrade restores the columns and re-derives each from the fields that
replaced it, which is lossy in exactly one place: `binding` cannot be
re-derived (nothing records it any more) and comes back as `framework`
for every row.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5f0a9c62e18"
down_revision: str | Sequence[str] | None = "b8e5c04a1d39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("playbook_steps", "rule_policy")
    op.drop_column("playbook_steps", "execution")
    op.drop_column("playbook_steps", "binding")


def downgrade() -> None:
    op.add_column("playbook_steps", sa.Column("binding", sa.String(), nullable=True))
    op.add_column("playbook_steps", sa.Column("execution", sa.String(), nullable=True))
    op.add_column("playbook_steps", sa.Column("rule_policy", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE playbook_steps
        SET binding = 'framework',
            execution = CASE
                WHEN kind = 'human' THEN 'human-attested'
                WHEN needs_confirmation THEN 'ai-assisted'
                ELSE 'automated'
            END,
            rule_policy = automation_brief
        """
    )
    op.alter_column("playbook_steps", "binding", nullable=False)
    op.alter_column("playbook_steps", "execution", nullable=False)
