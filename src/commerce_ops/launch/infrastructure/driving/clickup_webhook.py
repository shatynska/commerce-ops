"""Driving adapter: ClickUp webhook deliveries for `launch-clickup-sync`.

Implements the capability's "Webhook deliveries are verified before
anything is recorded" and the completion scenarios stated over a received
status change.

This is the *fast* path only. Everything it does, the reconciliation pass
does too — the webhook merely does it sooner. That is why an unverifiable
delivery can be rejected outright and an unrecognised one acknowledged and
dropped: nothing is lost that the next pass would not pick up.

Verification comes first, before the body is parsed and before any
collaborator is touched, because the endpoint is internet-facing. An absent
secret rejects everything rather than waving it through: "no secret
configured" is not "nothing to check".

The secret is read directly from `os.environ` rather than through
`get_settings()`, exactly as the Slack adapter reads its own:
`runtime-configuration` permits a direct read "where per-request tolerance
of absence is itself required behavior", and rejecting an unverifiable
request rather than raising is that case. It stays declared in the settings
model, so the startup check still reports it by name.

Collaborators (`session`, `ClickUpMappingRepository`, `LaunchRepository`,
`record_step_outcome`) are imported by name into this module's namespace and
referenced as bare globals, keeping `daily_digest_job.py`'s pattern — which
is what lets tests substitute fakes with `monkeypatch.setattr`.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any, Final

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import JSONResponse

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.domain.launch_run import Provenance
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import transition_outcome
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.shipped_playbooks import (
    ShippedPlaybooks,
)
from commerce_ops.shared.infrastructure.driven.database import session

__all__ = [
    "ClickUpMappingRepository",
    "LaunchRepository",
    "record_step_outcome",
    "router",
    "session",
]

_logger = logging.getLogger(__name__)

router = APIRouter()

# Deliberately free of any cadence word: `scheduled-jobs` forbids an
# externally reachable route that starts recurring work, and this path is a
# completion delivery, not a way to trigger the reconciliation pass.
WEBHOOK_PATH: Final = "/webhooks/clickup/tasks"

SIGNATURE_HEADER: Final = "X-Signature"
STATUS_CHANGE_EVENT: Final = "taskStatusUpdated"
_CLOSED_STATUS_TYPE: Final = "closed"
_CLICKUP_SOURCE: Final = "clickup"
_GRADUATED_GATE: Final = "graduated"

_playbooks = ShippedPlaybooks()


def _webhook_secret() -> str | None:
    # The variable name is a literal here on purpose: the environment-drift
    # check parses the source for `os.environ`/`.get(...)` with a *constant*
    # argument, so a module constant would make this read invisible to it.
    return os.environ.get("CLICKUP_WEBHOOK_SECRET")


def _is_authentic(body: bytes, signature: str | None, secret: str) -> bool:
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    # Constant-time: a byte-by-byte comparison leaks how much of a forged
    # signature was right, which is enough to forge the rest.
    return hmac.compare_digest(expected, signature)


def _acknowledged() -> Response:
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "ok"})


def _rejected(reason: str) -> Response:
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": reason}
    )


def _status_change(payload: Any) -> tuple[bool, str | None] | None:
    """The delivery's new closed state and acting user, or None when it
    carries no status change at all.

    The closed judgement is taken from the status `type` field rather than
    its name, so the ops team can rename statuses freely.
    """
    items = payload.get("history_items") or []
    for item in items:
        if item.get("field") != "status":
            continue
        after = item.get("after") or {}
        user = item.get("user") or {}
        actor = user.get("username") or user.get("email") or user.get("id")
        return after.get("type") == _CLOSED_STATUS_TYPE, (
            str(actor) if actor is not None else None
        )
    return None


@router.post(WEBHOOK_PATH)
async def receive_clickup_event(request: Request) -> Response:
    """Record what a ClickUp status change means for the mapped step."""
    body = await request.body()

    secret = _webhook_secret()
    if not secret:
        _logger.warning(
            "a ClickUp webhook delivery arrived but no CLICKUP_WEBHOOK_SECRET "
            "is configured; it cannot be verified and is rejected"
        )
        return _rejected("no webhook secret is configured")
    if not _is_authentic(body, request.headers.get(SIGNATURE_HEADER), secret):
        return _rejected("signature verification failed")

    try:
        payload = json.loads(body)
    except ValueError:
        return _rejected("body is not JSON")

    if payload.get("event") != STATUS_CHANGE_EVENT:
        return _acknowledged()

    change = _status_change(payload)
    if change is None:
        return _acknowledged()
    now_closed, actor = change

    task_id = payload.get("task_id")
    if not task_id:
        return _acknowledged()

    async with session() as db_session:
        mapping = ClickUpMappingRepository(db_session)
        mapped = await mapping.resolve_task(str(task_id))
        if mapped is None:
            # A task this deployment never projected — someone else's work
            # in the same workspace.
            return _acknowledged()

        launches = LaunchRepository(db_session)
        launch = await launches.get_by_product_id(mapped.product_id)
        if launch is None or launch.current_gate == _GRADUATED_GATE:
            return _acknowledged()

        outcome = transition_outcome(mapped.last_observed_closed, now_closed)
        if outcome is None:
            # No transition: a repeat delivery, or a change between two
            # open statuses. Nothing happened that the launch records.
            return _acknowledged()

        await mapping.observe(mapped.product_id, mapped.step_id, now_closed)
        await record_step_outcome(
            launches,
            _playbooks,
            product_id=mapped.product_id,
            step_id=mapped.step_id,
            outcome=outcome,
            provenance=Provenance(
                source=_CLICKUP_SOURCE,
                who=actor or "clickup-webhook",
                when=datetime.now(UTC),
                evidence=f"ClickUp task {task_id}",
            ),
        )

    return _acknowledged()
