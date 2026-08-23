"""Driven adapter: creates and updates ClickUp tasks via ClickUp's REST API.

Lazily constructs its `httpx.AsyncClient` (mirroring
`omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache`
pattern for `WebClient`/`SignatureVerifier`) so importing this module never
requires `CLICKUP_API_TOKEN` to be set. A non-2xx response, or a transport
failure that never produces a response at all, propagates uncaught -- see
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime

import httpx

from commerce_ops.shared.domain.clickup import ClickUpTask, ClickUpTaskState

_BASE_URL = "https://api.clickup.com"

# ClickUp reports a status's kind in its `type` field; only this value means
# the task is finished. Judging by the status *name* instead would break the
# moment the ops team renamed one.
_CLOSED_STATUS_TYPE = "closed"


@functools.lru_cache
def get_client() -> httpx.AsyncClient:
    token = os.environ["CLICKUP_API_TOKEN"]
    return httpx.AsyncClient(headers={"Authorization": token})


def _task_from_response(response: httpx.Response) -> ClickUpTask:
    data = response.json()
    return ClickUpTask(id=data["id"], url=data["url"])


async def create_task(
    list_id: str, name: str, description: str | None = None
) -> ClickUpTask:
    body: dict[str, object] = {"name": name}
    if description is not None:
        body["description"] = description

    response = await get_client().post(
        f"{_BASE_URL}/api/v2/list/{list_id}/task", json=body
    )
    response.raise_for_status()
    return _task_from_response(response)


async def update_task(task_id: str, fields: Mapping[str, object]) -> ClickUpTask:
    response = await get_client().put(
        f"{_BASE_URL}/api/v2/task/{task_id}", json=dict(fields)
    )
    response.raise_for_status()
    return _task_from_response(response)


async def create_list(folder_id: str, name: str) -> str:
    """Create a list in a folder, returning the created list's identifier.

    Returns the identifier itself rather than a wrapper: the
    `clickup-task-client` delta states the operation "SHALL return the
    created list's identifier", and nothing downstream needs more of the
    created list than that.
    """
    response = await get_client().post(
        f"{_BASE_URL}/api/v2/folder/{folder_id}/list", json={"name": name}
    )
    response.raise_for_status()
    return str(response.json()["id"])


def _due_date_from(raw: object) -> date | None:
    """ClickUp's epoch-millisecond due date as the calendar day it names.

    Absent, null and empty all mean "no due date"; ClickUp sends the value
    as a string of digits, but tolerates a number here too.
    """
    if raw is None or raw == "" or not isinstance(raw, str | int | float):
        return None
    return datetime.fromtimestamp(int(raw) / 1000, tz=UTC).date()


def _task_state(raw: Mapping[str, object]) -> ClickUpTaskState:
    status = raw.get("status") or {}
    assert isinstance(status, Mapping)
    return ClickUpTaskState(
        id=str(raw["id"]),
        status=str(status.get("status", "")),
        closed=status.get("type") == _CLOSED_STATUS_TYPE,
        due_date=_due_date_from(raw.get("due_date")),
    )


async def list_tasks(list_id: str) -> tuple[ClickUpTaskState, ...]:
    """Every task in a list, closed ones included, across every page.

    ClickUp omits closed tasks unless asked for them, and pages at 100
    tasks; a launch list holds more than that, so stopping at the first
    page would silently under-report the launch's own work.
    """
    collected: list[ClickUpTaskState] = []
    page = 0
    while True:
        response = await get_client().get(
            f"{_BASE_URL}/api/v2/list/{list_id}/task",
            params={"include_closed": "true", "page": page},
        )
        response.raise_for_status()
        payload = response.json()
        tasks = payload.get("tasks") or []
        collected.extend(_task_state(raw) for raw in tasks)
        # `last_page` absent is read as "this was the last": an unpaged
        # response must terminate the loop rather than spin forever.
        if payload.get("last_page", True) or not tasks:
            return tuple(collected)
        page += 1
