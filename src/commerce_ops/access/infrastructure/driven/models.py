"""SQLAlchemy models mapping the `admin-session` state to Postgres.

Two small tables (`add-playbook-admin-ui`, design Decision 5): the
single-use link tokens a Slack command mints, and the browser sessions
they exchange for. Both store SHA-256 hashes, never the raw values — the
raw token rides the minted link and the raw session identifier rides the
cookie, so a database read yields nothing a browser could present.

Rows are kept simple on purpose: expiry is a stored instant compared at
read time, revocation is the principals directory re-resolved per
request, and spent tokens stay as rows so a second use is a conditional
no-match rather than a distinguishable error.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from commerce_ops.shared.infrastructure.driven.orm import Base


class MemberRow(Base):
    """One member on the membership: identity data plus the attribution trail.

    Replaces the repo-owned `principals.yaml` (`move-principals-to-roster`).
    Rows are never deleted — deactivation is a flag, so the history of who
    was granted what, by whom, survives.

    `slack_identity` is unique across every row, deactivated ones
    included: an identity names exactly one human, and a generated
    identifier must never be re-pointed at a different one.
    """

    __tablename__ = "members"

    identifier: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    slack_identity: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    clickup_user_id: Mapped[str | None] = mapped_column(String, nullable=True)
    admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deactivated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    deactivated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reactivated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    reactivated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Who conferred the admin flag, kept apart from `updated_by` so a
    # later edit that confers nothing cannot erase the startup seed's
    # signal (see `access.application.members.MemberRecord`).
    admin_conferred_by: Mapped[str | None] = mapped_column(String, nullable=True)


class RoleRow(Base):
    """One role: the position, its lifecycle and its attribution trail.

    The slug is the primary key — there is no generated identifier. A step will
    store the slug and a vendored file must be able to name it in advance, so
    it is chosen once and never changes; that inverts `MemberRow`, whose
    identifier is generated precisely so it can never be re-pointed at a
    different human, and it inverts it for the inverse reason.

    Rows are never deleted — retirement is a status, so the history of which
    positions the company has staffed survives.
    """

    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_roles_status",
        ),
    )

    slug: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")

    created_by: Mapped[str | None] = mapped_column(String, nullable=True)
    created_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_by: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retired_by: Mapped[str | None] = mapped_column(String, nullable=True)
    retired_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unretired_by: Mapped[str | None] = mapped_column(String, nullable=True)
    unretired_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RoleHolderRow(Base):
    """One member holding one role, and whether they are its default.

    The partial unique index is the point: it makes "at most one default per
    role" a storage guarantee rather than only a rule the application checks,
    in the same spirit as `members.slack_identity`'s uniqueness constraint. A
    write that got past the domain could still not persist a second default.
    """

    __tablename__ = "role_holders"
    __table_args__ = (
        Index(
            "uq_role_holders_one_default",
            "role_slug",
            unique=True,
            postgresql_where=text("is_default"),
        ),
    )

    # Deferrable, checked at commit: both collections are written by full
    # replacement, so a delete-then-reinsert momentarily orphans these rows
    # inside a transaction that puts them back. See the migration for the
    # reasoning in full.
    role_slug: Mapped[str] = mapped_column(
        String,
        ForeignKey("roles.slug", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    member_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("members.identifier", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    added_by: Mapped[str | None] = mapped_column(String, nullable=True)
    added_on: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MembersSet(Base):
    """The single optimistic set-version serializing every write in `access`.

    One row, ever — the shape `playbook_step_set` established: each
    accepted write persists conditionally on the version it loaded and
    bumps it, so two concurrent writes cannot both believe they held the
    last active admin.

    It serializes the **roles** as well as the membership, which its name no
    longer says (`rebuild-the-member-directory`, design Decision 8). The
    member/role invariant spans both collections — a member may not be
    deactivated while they are an active role's default holder — so the two are
    one write-serialization boundary. Two version cells would let a
    deactivation and a default move each win their own race and together leave
    an active role holding a deactivated default. The table was renamed from
    `roster_set` one change earlier, so it is not renamed again here; recorded
    as naming debt for whoever adds a third collection.
    """

    __tablename__ = "members_set"
    __table_args__ = (CheckConstraint("id = 1", name="ck_members_set_singleton"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class AdminLinkToken(Base):
    """One minted admin link token, stored hashed, spent at most once."""

    __tablename__ = "admin_link_tokens"

    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    principal: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    spent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AdminSession(Base):
    """One browser session established by a token exchange, stored hashed."""

    __tablename__ = "admin_sessions"

    session_hash: Mapped[str] = mapped_column(String, primary_key=True)
    principal: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
