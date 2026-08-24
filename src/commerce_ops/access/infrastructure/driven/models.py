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

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from commerce_ops.shared.infrastructure.driven.orm import Base


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
