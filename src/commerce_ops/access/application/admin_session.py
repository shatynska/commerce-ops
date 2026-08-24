"""The Slack-to-browser bridge's use cases (`admin-session`).

Three operations carry a Slack identity into a browser session: `mint`
binds a short-lived single-use token to an admin-capable principal,
`exchange` spends that token for a bounded session, and `verify` answers
a session's principal — re-resolving admin capability against the
directory on every call, so editing the repo-owned file is the whole of
revocation.

Every refusal is `None`, deliberately shapeless: a caller rendering a
refusal cannot distinguish an unknown asker from a visibility-only one,
a spent token from one that never existed, or an expired session from an
absent one — the indistinguishability the capability's absence-shaped
requirements build on.

Raw tokens and session identifiers exist only in flight; the stores see
SHA-256 hashes, so a database read yields nothing a browser could
present.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Final

from commerce_ops.access.application.ports import AdminSessionStore, LinkTokenStore
from commerce_ops.access.application.use_cases import resolve_admin_capability
from commerce_ops.access.domain.principals import PrincipalsDirectory

TOKEN_LIFETIME: Final = timedelta(minutes=10)
"""The spec's bound exactly: a link token expires no more than ten
minutes after minting."""

SESSION_LIFETIME: Final = timedelta(hours=12)
"""The spec's bound exactly: a session expires no more than twelve hours
after it was established."""


def _hashed(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def mint_admin_link(
    directory: PrincipalsDirectory,
    tokens: LinkTokenStore,
    *,
    identity: str,
    base_url: str,
    now: datetime,
) -> str | None:
    """A browser link into the admin surface for `identity`, or `None`.

    Minted only for an identity that resolves admin-capable — directory
    membership and visibility grants alone never suffice — and both
    refusal kinds are one and the same `None`, so nothing downstream can
    leak which one occurred.
    """
    if not resolve_admin_capability(directory, identity=identity):
        return None
    raw = secrets.token_urlsafe(32)
    await tokens.save(
        token_hash=_hashed(raw),
        principal=identity,
        expires_at=now + TOKEN_LIFETIME,
    )
    return f"{base_url}/admin/session?token={raw}"


async def exchange_link_token(
    tokens: LinkTokenStore,
    sessions: AdminSessionStore,
    *,
    token: str,
    now: datetime,
) -> str | None:
    """The session identifier a valid token exchanges for, or `None`.

    The claim spends the token atomically before the session exists, so
    a token exchanges exactly once; spent, expired and never-minted
    tokens refuse identically.
    """
    principal = await tokens.claim(_hashed(token), now=now)
    if principal is None:
        return None
    session_id = secrets.token_urlsafe(32)
    await sessions.save(
        session_hash=_hashed(session_id),
        principal=principal,
        expires_at=now + SESSION_LIFETIME,
    )
    return session_id


async def verify_admin_session(
    directory: PrincipalsDirectory,
    sessions: AdminSessionStore,
    *,
    session_id: str,
    now: datetime,
) -> str | None:
    """The principal behind a live session, or `None`.

    Admin capability is re-resolved against `directory` on every call:
    a principal removed from the directory, or one whose entry lost its
    admin declaration, stops verifying on the next request even while
    the stored session is unexpired.
    """
    principal = await sessions.find(_hashed(session_id), now=now)
    if principal is None:
        return None
    if not resolve_admin_capability(directory, identity=principal):
        return None
    return principal
