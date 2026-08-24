"""Driven adapters: the Postgres `LinkTokenStore` and `AdminSessionStore`.

Each store opens its own session per operation through the shared
factory — the stores are module-level collaborators of a driving adapter
that outlives any one request, so no request-scoped session can be owned
here. The optimistic serialization the ports require is carried by the
rows themselves: `claim` spends a token with one conditional UPDATE, so
two concurrent exchanges of one token cannot both succeed.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, update

from commerce_ops.access.infrastructure.driven.models import (
    AdminLinkToken,
    AdminSession,
)
from commerce_ops.shared.infrastructure.driven.database import session


class PostgresLinkTokens:
    """The `LinkTokenStore` port over `admin_link_tokens`."""

    async def save(
        self, *, token_hash: str, principal: str, expires_at: datetime
    ) -> None:
        async with session() as db:
            db.add(
                AdminLinkToken(
                    token_hash=token_hash,
                    principal=principal,
                    expires_at=expires_at,
                )
            )
            await db.commit()

    async def claim(self, token_hash: str, *, now: datetime) -> str | None:
        async with session() as db:
            claimed = await db.execute(
                update(AdminLinkToken)
                .where(
                    AdminLinkToken.token_hash == token_hash,
                    AdminLinkToken.spent.is_(False),
                    AdminLinkToken.expires_at > now,
                )
                .values(spent=True)
                .returning(AdminLinkToken.principal)
            )
            principal: str | None = claimed.scalar()
            await db.commit()
            return principal


class PostgresAdminSessions:
    """The `AdminSessionStore` port over `admin_sessions`."""

    async def save(
        self, *, session_hash: str, principal: str, expires_at: datetime
    ) -> None:
        async with session() as db:
            db.add(
                AdminSession(
                    session_hash=session_hash,
                    principal=principal,
                    expires_at=expires_at,
                )
            )
            await db.commit()

    async def find(self, session_hash: str, *, now: datetime) -> str | None:
        async with session() as db:
            principal: str | None = await db.scalar(
                select(AdminSession.principal).where(
                    AdminSession.session_hash == session_hash,
                    AdminSession.expires_at > now,
                )
            )
            return principal
