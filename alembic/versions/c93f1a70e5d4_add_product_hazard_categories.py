"""Record what a compliance screening found against a product.

A nullable `text[]` on `products`, holding three states rather than two:
`NULL` is "never screened", `{}` is "screened and nothing found", and a
non-empty array is what the screening flagged. The first two are opposite
facts -- an open question and an answered one -- and every consumer of
this field branches on telling them apart.

**No default, and that is the point of the column rather than an
omission.** A `server_default` of `'{}'` would declare every product in
the catalog screened and found clear, at migration time, on the strength
of nothing having screened them. `NULL` is the correct value for every
existing row, so there is no backfill either.

An array rather than `jsonb`: `jsonb` admits `null`, `[]`, `{}`, `""` and
`0` as five spellings of roughly the same thing, and `launch-instance`
had to write a requirement forbidding the second spelling precisely
because its own storage could not. A `text[]` cannot express the
confusion, so the distinction is structural rather than asserted.

Adding a nullable column with no default is metadata-only in Postgres --
no table rewrite, no lock held for the length of a scan -- so this is safe
against the running container, and the previous image is compatible with
the new schema.

Revision ID: c93f1a70e5d4
Revises: b62d05f1ae37
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "c93f1a70e5d4"
down_revision = "b62d05f1ae37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("hazard_categories", sa.ARRAY(sa.String()), nullable=True),
    )


def downgrade() -> None:
    # Lossy by nature: the screenings recorded into it are gone. Acceptable
    # for a field nothing yet consumes and no other table references.
    op.drop_column("products", "hazard_categories")
