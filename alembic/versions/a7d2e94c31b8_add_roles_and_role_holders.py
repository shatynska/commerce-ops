"""Add the roles collection and its holders.

Two new tables; no existing table is altered. `roles` is keyed by the slug
itself — a step will store it and a vendored file must be able to name it in
advance, so there is no generated identifier to key on — and `role_holders`
carries the many-to-many with the one flag that says which holder is the
default.

The partial unique index is the point of the second table: it makes "at most
one default holder per role" a storage guarantee rather than only a rule the
application checks, in the same spirit as `members.slack_identity`'s
uniqueness constraint.

No version table is created. The roles serialize on `members_set`, the row the
membership already uses: the member/role invariant spans both collections, so
they are one write-serialization boundary
(`rebuild-the-member-directory`, design Decision 8).

Revision ID: a7d2e94c31b8
Revises: f4b7c1e09d52
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "a7d2e94c31b8"
down_revision = "f4b7c1e09d52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(), nullable=True),
        sa.Column("updated_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retired_by", sa.String(), nullable=True),
        sa.Column("retired_on", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unretired_by", sa.String(), nullable=True),
        sa.Column("unretired_on", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("slug"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_roles_status",
        ),
    )

    op.create_table(
        "role_holders",
        sa.Column("role_slug", sa.String(), nullable=False),
        sa.Column("member_id", sa.String(), nullable=False),
        sa.Column(
            "is_default", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("added_by", sa.String(), nullable=True),
        sa.Column("added_on", sa.DateTime(timezone=True), nullable=True),
        # Both deferrable, checked at COMMIT rather than per statement.
        #
        # Every collection in this module is written by full replacement — the
        # membership and the roles alike delete their rows and re-insert the
        # set, which is what makes one validated write atomic. Checked per
        # statement, that pattern trips its own foreign keys: clearing
        # `members` momentarily orphans every holder row, and clearing `roles`
        # does the same, even though the transaction puts them all back before
        # it ends. Deferring moves the check to the only moment at which the
        # answer is meaningful.
        sa.ForeignKeyConstraint(
            ["role_slug"],
            ["roles.slug"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["members.identifier"],
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.PrimaryKeyConstraint("role_slug", "member_id"),
    )

    # At most one default per role, enforced by the database rather than only
    # by the write use cases.
    op.create_index(
        "uq_role_holders_one_default",
        "role_holders",
        ["role_slug"],
        unique=True,
        postgresql_where=sa.text("is_default"),
    )


def downgrade() -> None:
    op.drop_index("uq_role_holders_one_default", table_name="role_holders")
    op.drop_table("role_holders")
    op.drop_table("roles")
