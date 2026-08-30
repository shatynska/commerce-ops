"""The ClickUp webhook subscription's pre-serving registration step
(`launch-clickup-sync`).

Implements the capability's *The webhook subscription is registered as an
idempotent, non-blocking deploy step*
(`openspec/changes/shift-clickup-completions-to-webhook/specs/launch-clickup-sync/spec.md`).

Runs as its own process in the container's start chain, between
`alembic upgrade head` and the server, the same positioning `seed_admin.py`
takes and for the analogous reason: its one piece of work is a call to an
external system (ClickUp), and an external call that can fail or hang must
not gate the first request the server would otherwise serve.

Unlike `seed_admin.py`, a failure here is deliberately never fatal: this
capability already has a fallback independent of the webhook -- the
reconciliation pass -- so a registration failure degrades to that fallback
rather than to a broken deployment. Every fault (an ambiguous workspace, a
missing public endpoint, any ClickUp API failure) is logged as a warning and
`main()` still returns `0`.

Idempotent: the existing-subscription check matches on both `endpoint` and
`folder_id`, never on the endpoint alone -- a subscription left over from a
since-changed `CLICKUP_LAUNCH_FOLDER_ID` must not be read as covering the
*current* folder, or that folder would go silently unregistered.

ClickUp generates each subscription's signing secret itself and returns it
in the creation response; this step never supplies one. Every create --
first-ever or a recreation after a prior subscription was removed, which
this step has no way to tell apart -- logs that secret at warning level,
naming that this deployment's `CLICKUP_WEBHOOK_SECRET` must be set or
updated to match it before any delivery will verify.

Settings are read directly from `os.environ` rather than through
`get_settings()`, matching `clickup_webhook.py` -- this step's own sibling,
handling the other half of this same capability -- for the same reason:
`runtime-configuration` permits a direct read "where per-request tolerance
of absence is itself required behavior", and taking no action on an absent
value rather than raising is that case.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from commerce_ops.launch.infrastructure.driving.clickup_webhook import WEBHOOK_PATH
from commerce_ops.shared.infrastructure.logging import configure_logging

__all__ = ["main"]

_logger = logging.getLogger(__name__)

_BASE_URL = "https://api.clickup.com"
_TEAM_PATH = "/api/v2/team"
_EVENTS = ["taskStatusUpdated"]


def _webhook_path(team_id: str) -> str:
    return f"/api/v2/team/{team_id}/webhook"


def _ensure_ok(response: httpx.Response) -> None:
    # Not `response.raise_for_status()`: it requires the response's
    # `request` attribute, which only a full `Client.send` pipeline sets --
    # a bare status check needs nothing from the transport that produced
    # the response.
    if response.status_code >= 400:
        raise RuntimeError(
            f"ClickUp API call failed with status {response.status_code}: "
            f"{response.text}"
        )


async def _resolve_team(client: httpx.AsyncClient) -> str | None:
    response = await client.get(_TEAM_PATH)
    _ensure_ok(response)
    teams = response.json().get("teams", [])
    if len(teams) != 1:
        _logger.warning(
            "clickup webhook registration: expected exactly one accessible "
            "ClickUp workspace for CLICKUP_API_TOKEN, found %d; not "
            "registering, since which workspace to register against is "
            "ambiguous",
            len(teams),
        )
        return None
    return str(teams[0]["id"])


async def _matching_subscription_exists(
    client: httpx.AsyncClient, team_id: str, endpoint: str, folder_id: str
) -> bool:
    response = await client.get(_webhook_path(team_id))
    _ensure_ok(response)
    webhooks = response.json().get("webhooks", [])
    return any(
        webhook.get("endpoint") == endpoint and webhook.get("folder_id") == folder_id
        for webhook in webhooks
    )


async def _create_subscription(
    client: httpx.AsyncClient, team_id: str, endpoint: str, folder_id: str
) -> None:
    body: dict[str, Any] = {
        "endpoint": endpoint,
        "events": _EVENTS,
        "folder_id": folder_id,
    }
    response = await client.post(_webhook_path(team_id), json=body)
    _ensure_ok(response)
    data = response.json()
    secret = data.get("secret") or data.get("webhook", {}).get("secret")
    _logger.warning(
        "clickup webhook registration: created a subscription for %s "
        "(folder %s); ClickUp generated its own signing secret (%s) -- set "
        "or update this deployment's CLICKUP_WEBHOOK_SECRET to match it, or "
        "every delivery against this subscription will be silently "
        "rejected by signature verification",
        endpoint,
        folder_id,
        secret,
    )


async def _register() -> None:
    # Literal names throughout: the environment-drift check parses source
    # for `os.environ`/`.get(...)` with a constant argument, so a read
    # through a shared constant would make this module's consumption
    # invisible to it.
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        _logger.warning(
            "clickup webhook registration: CLICKUP_API_TOKEN is not "
            "configured; nothing to register with"
        )
        return

    async with httpx.AsyncClient(
        base_url=_BASE_URL, headers={"Authorization": token}
    ) as client:
        team_id = await _resolve_team(client)
        if team_id is None:
            return

        admin_base_url = os.environ.get("ADMIN_BASE_URL")
        if not admin_base_url:
            _logger.warning(
                "clickup webhook registration: ADMIN_BASE_URL is not "
                "configured; this deployment's public endpoint is unknown, "
                "so no subscription can be registered"
            )
            return

        folder_id = os.environ.get("CLICKUP_LAUNCH_FOLDER_ID")
        if not folder_id:
            _logger.warning(
                "clickup webhook registration: CLICKUP_LAUNCH_FOLDER_ID is "
                "not configured; a subscription would have nothing to be "
                "scoped to, so none is registered"
            )
            return

        endpoint = f"{admin_base_url}{WEBHOOK_PATH}"

        if await _matching_subscription_exists(client, team_id, endpoint, folder_id):
            _logger.info(
                "clickup webhook registration: a subscription already "
                "targets %s for folder %s; nothing to do",
                endpoint,
                folder_id,
            )
            return

        await _create_subscription(client, team_id, endpoint, folder_id)


def main() -> int:
    """Register this deployment's ClickUp webhook subscription.

    Always returns `0`: a registration failure degrades to the
    reconciliation pass's fallback, never to a blocked deployment. See the
    module docstring.
    """
    configure_logging()
    try:
        asyncio.run(_register())
    except Exception as failure:  # best-effort by design
        _logger.warning(
            "clickup webhook registration failed and is being skipped for "
            "this deploy; the reconciliation pass remains the fallback: %s",
            failure,
            exc_info=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
