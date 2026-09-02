"""Driving adapter: the Slack-to-browser bridge (`admin-session`).

Two doors into one hallway: a Slack slash command that mints a
short-lived, single-use admin link for a caller the principals directory
declares admin-capable, and the browser route that exchanges the link's
token for the hardened session cookie.

The refusal grammar is absence: every failed exchange — spent, expired,
never minted, no token at all — raises the app's own 404, produced
nowhere else than here so the shape cannot drift from FastAPI's
unregistered-route response. The Slack side refuses with one generic
ephemeral message for unknown and visibility-only callers alike; the
mint use case answers both with the same `None`, so this handler could
not distinguish them if it tried.

This adapter rides the same physical Slack app as `slack_entry`'s
`product_agent` — one workspace app can point each slash command at its
own request URL, and the signing secret and bot token are app-level, so
the same environment variables verify and reply here. It registers its
own Bolt instance under its own identity all the same: each module owns
its listeners, and neither module imports the other.

Collaborators (`link_tokens`, `admin_sessions`) are module-level names
referenced as bare globals, keeping `clickup_webhook.py`'s pattern —
which is what lets tests substitute fakes with `monkeypatch.setattr`.
`deployed` is derived from `ADMIN_BASE_URL`'s scheme at import: the
Secure cookie flag follows where the admin surface actually lives, and
the variable stays declared in the settings model so the startup check
reports it by name.
"""

from __future__ import annotations

import functools
import json
import logging
import os
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler

from commerce_ops.access.application import (
    exchange_link_token,
    mint_admin_link,
)
from commerce_ops.access.infrastructure.driven.admin_session_store import (
    PostgresAdminSessions,
    PostgresLinkTokens,
)
from commerce_ops.access.infrastructure.driven.members_repository import (
    PostgresMembers,
)
from commerce_ops.shared.infrastructure.driving.slack_app import (
    SlackAppSpec,
    get_slack_app,
    register_slack_app,
)

__all__ = [
    "SESSION_LIFETIME_SECONDS",
    "admin_sessions",
    "deployed",
    "link_tokens",
    "members",
    "reset_handler_cache",
    "router",
]

logger = logging.getLogger(__name__)

router = APIRouter()

SLACK_APP_IDENTITY: Final = "admin_link"

SLASH_COMMAND: Final = "/playbook-admin"

SESSION_COOKIE: Final = "admin_session"

SESSION_LIFETIME_SECONDS: Final = 12 * 60 * 60

ADMIN_HOME_PATH: Final = "/admin/playbook"

REFUSAL_TEXT: Final = (
    "This command is not available to you. If you believe it should be, "
    "ask the workspace owner."
)
"""One and the same ephemeral refusal for every non-admin caller: no
URL, no confirmation that any admin surface exists, and no distinction
between a caller the directory does not know and one it knows without
the admin declaration."""

# The stores, referenced as bare globals so tests can substitute fakes.
link_tokens = PostgresLinkTokens()
members = PostgresMembers()
admin_sessions = PostgresAdminSessions()


def _base_url() -> str | None:
    return os.environ.get("ADMIN_BASE_URL")


def _read_deployed() -> bool:
    """Secure-cookie environments are the ones serving the admin surface
    over https — the scheme of its own public URL is the evidence."""
    url = _base_url()
    return url is not None and url.lower().startswith("https")


deployed: bool = _read_deployed()


# --------------------------------------------------------------------------
# The Slack door: minting a link
# --------------------------------------------------------------------------


def _signing_secret() -> str | None:
    # Literal reads, here and below: the environment-drift check parses the
    # source for constant `os.environ` arguments (see `slack_entry.py`).
    return os.environ.get("PRODUCT_AGENT_SLACK_SIGNING_SECRET")


def _bot_token() -> str | None:
    return os.environ.get("PRODUCT_AGENT_SLACK_BOT_TOKEN")


def will_reply(body: Mapping[str, Any]) -> bool:
    """Every request class this adapter serves replies — the slash
    command answers ephemerally either way — so anything unrecognized is
    treated as replying too and fails closed on absent credentials."""
    return True


register_slack_app(
    SLACK_APP_IDENTITY,
    SlackAppSpec(
        signing_secret_provider=_signing_secret,
        bot_token_provider=_bot_token,
        will_reply=will_reply,
    ),
)


@functools.cache
def _get_handler() -> AsyncSlackRequestHandler:
    app = get_slack_app(SLACK_APP_IDENTITY)

    @app.command(SLASH_COMMAND)
    async def handle_admin_command(
        ack: Callable[..., Awaitable[None]],
        respond: Callable[..., Awaitable[None]],
        body: Mapping[str, Any],
    ) -> None:
        await ack()
        identity = str(body.get("user_id") or "")
        base_url = _base_url()
        link: str | None = None
        if base_url:
            # The membership is read per invocation, not cached at import:
            # deactivating a member is the whole of revocation.
            link = await mint_admin_link(
                members,
                link_tokens,
                identity=identity,
                base_url=base_url.rstrip("/"),
                now=datetime.now(UTC),
            )
        elif identity:
            logger.warning(
                "ADMIN_BASE_URL is not set; the admin link command cannot "
                "mint a usable link and refuses"
            )
        # `respond` posts ephemerally by default for a slash command: the
        # link — or the refusal — is visible only to the caller.
        if link is None:
            await respond(text=REFUSAL_TEXT)
        else:
            await respond(
                text=(
                    f"Your playbook admin link (single use, expires in 10 "
                    f"minutes): {link}"
                )
            )

    return AsyncSlackRequestHandler(app)


def reset_handler_cache() -> None:
    """Drops the cached Bolt handler, for tests that change the
    environment between requests."""
    _get_handler.cache_clear()


@router.post("/admin_link/slack/events")
async def admin_link_slack_events(request: Request) -> Response:
    try:
        secret = os.environ["PRODUCT_AGENT_SLACK_SIGNING_SECRET"]
    except KeyError:
        secret = ""

    if not secret:
        # Absent or empty verifies nothing either way: fail closed, as
        # `slack_entry.py` does and for the same reason.
        return Response(
            status_code=401,
            media_type="application/json",
            content=json.dumps({"error": "slack signing secret is not configured"}),
        )

    return await _get_handler().handle(request)


# --------------------------------------------------------------------------
# The browser door: exchanging the token
# --------------------------------------------------------------------------


@router.get("/admin/session")
async def exchange(token: str | None = None) -> Response:
    """Opening the minted link: the one path that establishes a session.

    A missing, spent, expired or never-minted token raises the app's own
    404 — indistinguishable from requesting a route that does not exist.
    """
    session_id = None
    if token:
        session_id = await exchange_link_token(
            link_tokens, admin_sessions, token=token, now=datetime.now(UTC)
        )
    if session_id is None:
        raise HTTPException(status_code=404)
    response: Response = RedirectResponse(ADMIN_HOME_PATH, status_code=303)
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=deployed,
        samesite="lax",
    )
    return response
