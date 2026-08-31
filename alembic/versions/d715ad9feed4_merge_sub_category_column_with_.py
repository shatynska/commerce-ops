"""merge sub-category column with confirmer redesign

Revision ID: d715ad9feed4
Revises: e6c1a92d7f04, 1a2b3c4d5e6f
Create Date: 2026-08-31

Two branches grew independently off `d5f83b1e04a7`: this repo's
`write-the-advisors-finding-to-the-product` (`e6c1a92d7f04`, adding
`products.sub_category`) and `main`'s `add-step-confirmer` /
`thread-launch-slack-notifications` (`...` -> `1a2b3c4d5e6f`, replacing
`needs_confirmation`/`automation_brief` with `confirmer` and adding the
Slack-thread fields). Neither depends on the other's columns, so this
merge revision is a pure convergence point -- no schema change of its
own.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d715ad9feed4"
down_revision: str | Sequence[str] | None = ("e6c1a92d7f04", "1a2b3c4d5e6f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
