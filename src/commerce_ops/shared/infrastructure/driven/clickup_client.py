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

import httpx

from commerce_ops.shared.domain.clickup import ClickUpTask

_BASE_URL = "https://api.clickup.com"


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
