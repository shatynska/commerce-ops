"""Driven adapter: creates and updates ClickUp tasks via ClickUp's REST API.

Lazily constructs its `httpx.AsyncClient` (mirroring
`omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache`
pattern for `WebClient`/`SignatureVerifier`) so importing this module never
requires `CLICKUP_API_TOKEN` to be set. A non-2xx response, or a transport
failure that never produces a response at all, propagates uncaught -- see
`add-clickup-task-client`'s design.md, Decisions.
"""

from __future__ import annotations

import asyncio
import functools
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import quote

import httpx

from commerce_ops.shared.domain.clickup import (
    ClickUpFieldDefinition,
    ClickUpFieldOption,
    ClickUpListState,
    ClickUpTask,
    ClickUpTaskState,
)

_BASE_URL = "https://api.clickup.com"

# ClickUp reports a status's kind in its `type` field; only this value means
# the task is finished. Judging by the status *name* instead would break the
# moment the ops team renamed one.
_CLOSED_STATUS_TYPE = "closed"


@functools.lru_cache
def get_client() -> httpx.AsyncClient:
    token = os.environ["CLICKUP_API_TOKEN"]
    return httpx.AsyncClient(headers={"Authorization": token})


# DERIVED in `retry-clickup-rate-limits`' design.md, "Bounded backoff, Retry-
# After honored and capped" -- the clickup-task-client spec delta states only
# "a bounded number of attempts" / "a fixed maximum wait"; these are the
# concrete values chosen.
_MAX_ATTEMPTS = 4  # up to 3 retries
_MAX_RETRY_WAIT_SECONDS = 10.0
_BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)


async def _wait_before_retry(response: httpx.Response, attempt: int) -> None:
    """The wait before the next attempt on a `429`.

    `Retry-After` is honored when present and parseable as a plain count of
    seconds, capped at `_MAX_RETRY_WAIT_SECONDS`. Absent or unparseable are
    treated identically -- both fall back to the client's own backoff,
    indexed by `attempt` (the number of retries already made).
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after is not None:
        try:
            seconds = float(retry_after)
        except ValueError:
            pass
        else:
            await asyncio.sleep(min(seconds, _MAX_RETRY_WAIT_SECONDS))
            return
    await asyncio.sleep(_BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)])


async def _send(method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send one request, retrying a `429` with backoff before surfacing it.

    Implements `clickup-task-client`'s *A rate-limited request is retried
    before it is surfaced* (`retry-clickup-rate-limits`). Every other non-
    success status, and a connection failure, propagate on the first
    attempt -- only `429` is retried, and only up to `_MAX_ATTEMPTS`.

    The single choke point every operation below routes through, replacing
    each one's own direct `get_client().<verb>(...)` + `raise_for_status()`
    pair -- see design.md, "One shared low-level send helper".
    """
    client = get_client()
    for attempt in range(_MAX_ATTEMPTS):
        response = await client.request(method, url, **kwargs)
        if response.status_code == 429 and attempt < _MAX_ATTEMPTS - 1:
            await _wait_before_retry(response, attempt)
            continue
        response.raise_for_status()
        return response
    raise AssertionError("unreachable: the loop above always returns or raises")


def _task_from_response(response: httpx.Response) -> ClickUpTask:
    data = response.json()
    return ClickUpTask(id=data["id"], url=data["url"])


async def create_task(
    list_id: str,
    name: str,
    description: str | None = None,
    assignees: Sequence[str] | None = None,
    tags: Sequence[str] | None = None,
) -> ClickUpTask:
    body: dict[str, object] = {"name": name}
    if description is not None:
        body["description"] = description
    # Omitted rather than sent empty: a create carrying `"assignees": []`
    # is a claim about who owns the work, and a step naming nobody makes
    # no such claim.
    if assignees:
        body["assignees"] = list(assignees)
    # Omitted when empty for the same reason, and because ClickUp accepts
    # tags on a create but not on an update -- this is the one call that
    # can set them without a second request per tag.
    if tags:
        body["tags"] = list(tags)

    response = await _send("POST", f"{_BASE_URL}/api/v2/list/{list_id}/task", json=body)
    return _task_from_response(response)


async def add_task_tag(task_id: str, tag_name: str) -> None:
    """Attach a tag to a task, creating it in the task's space if it does
    not already exist there.

    Its own endpoint rather than a field on `update_task`: ClickUp's task
    update accepts no `tags` key, so a tag added after creation costs one
    request per tag. Returns nothing -- the response carries no task body
    to hand back.

    The tag needs no prior existence. Measured against the live API on
    2026-08-26: attaching `discipline:listing` to a task in a space
    holding no tags answered `200` and left that name in the space. This
    is why the projection seeds no vocabulary.
    """
    await _send(
        "POST", f"{_BASE_URL}/api/v2/task/{task_id}/tag/{quote(tag_name, safe='')}"
    )


async def update_task(task_id: str, fields: Mapping[str, object]) -> ClickUpTask:
    response = await _send(
        "PUT", f"{_BASE_URL}/api/v2/task/{task_id}", json=dict(fields)
    )
    return _task_from_response(response)


async def create_list(folder_id: str, name: str) -> str:
    """Create a list in a folder, returning the created list's identifier.

    Returns the identifier itself rather than a wrapper: the
    `clickup-task-client` delta states the operation "SHALL return the
    created list's identifier", and nothing downstream needs more of the
    created list than that.
    """
    response = await _send(
        "POST", f"{_BASE_URL}/api/v2/folder/{folder_id}/list", json={"name": name}
    )
    return str(response.json()["id"])


async def read_list_state(list_id: str) -> ClickUpListState:
    """A list's own state — whether ClickUp reports it deleted.

    Distinct from `list_tasks`, which reads what a list *holds*: ClickUp
    answers a deleted list's task read with `200` and no tasks, so the
    tasks cannot say whether the list is still there. Reading the list
    itself can: ClickUp answers `200` with `"deleted": true`, observed
    against list `901220624358` on 2026-08-27.

    A non-2xx response and an unreachable ClickUp both propagate, as they
    do from every other operation here. That is deliberate rather than
    incidental: a failed read is not evidence of a deletion — it is
    equally what a withdrawn permission or a mistaken identifier
    produces — so this returns the fact or nothing at all. See
    `heal-a-launchs-deleted-list`'s design.md, Decision 4.
    """
    response = await _send("GET", f"{_BASE_URL}/api/v2/list/{list_id}")
    # Absent is read as "not deleted": ClickUp sends the flag on a
    # deleted list, and a live list is under no obligation to carry it.
    return ClickUpListState(deleted=bool(response.json().get("deleted", False)))


# The field types this adapter knows how to read an option set from. A type
# outside this set is reported as uninterpretable rather than guessed at.
_OPTION_BEARING_FIELD_TYPES = frozenset({"drop_down", "labels"})


def _field_definition(raw: Mapping[str, object]) -> ClickUpFieldDefinition:
    """One Custom Field, or a marker that it could not be interpreted.

    Total by construction: a folder holds whatever anyone added to it, at
    any type this adapter does not anticipate, and a read that raised on one
    unrelated field would raise on every subsequent read too -- nothing here
    can remove the field that causes it. So an unreadable field is reported
    with what it does carry and marked `uninterpretable`.

    That mark is deliberately not the same as declaring no options, though
    every uninterpretable field trivially declares none: a caller told a
    field "declares no options" is told to add some, which is the wrong
    instruction for a field that already has eight and merely could not be
    parsed.
    """
    identifier = str(raw.get("id", ""))
    name = str(raw.get("name", ""))
    field_type = str(raw.get("type", ""))
    if field_type not in _OPTION_BEARING_FIELD_TYPES:
        # A type this adapter does not anticipate -- a formula, a
        # relationship, a plain text field. Marked uninterpretable rather
        # than reported as declaring no options: it declares none, but so
        # does every uninterpretable field, and a caller told "declares no
        # options" is told to add some, which is the wrong instruction here.
        # Harmless for a field nobody configured; decisive for one somebody
        # pointed a field identifier at.
        return ClickUpFieldDefinition(
            id=identifier, name=name, type=field_type, uninterpretable=True
        )

    config = raw.get("type_config")
    options = config.get("options") if isinstance(config, Mapping) else None
    if not isinstance(options, Sequence):
        return ClickUpFieldDefinition(
            id=identifier, name=name, type=field_type, uninterpretable=True
        )

    collected: list[tuple[int, ClickUpFieldOption]] = []
    for position, option in enumerate(options):
        if not isinstance(option, Mapping) or "id" not in option:
            return ClickUpFieldDefinition(
                id=identifier, name=name, type=field_type, uninterpretable=True
            )
        order = option.get("orderindex")
        collected.append(
            (
                order if isinstance(order, int) else position,
                ClickUpFieldOption(
                    id=str(option["id"]), name=str(option.get("name", ""))
                ),
            )
        )
    return ClickUpFieldDefinition(
        id=identifier,
        name=name,
        type=field_type,
        # In the order the field declares them: the order is load-bearing,
        # not incidental, and `orderindex` is what carries it.
        options=tuple(option for _, option in sorted(collected, key=lambda o: o[0])),
    )


async def folder_fields(folder_id: str) -> tuple[ClickUpFieldDefinition, ...]:
    """Every Custom Field available to a folder, in declared option order.

    **Folder scope, not list scope**, and that is the point: a field
    configured on a folder is available to every list within it, so one read
    answers for all of them -- and answers even for a folder holding no
    lists at all, which is precisely when a fresh misconfiguration should
    still be found. A list-scoped read would answer once per launch instead
    of once per pass, and could not answer when no launch is active.

    Measured 2026-08-27: this endpoint answers `{"fields": [...]}` with no
    pagination affordance whatsoever -- no cursor, no `last_page` -- where
    `GET /list/{id}/task` answers with `last_page`, and a `page` parameter
    is ignored rather than honoured. One read returns every field the folder
    declares. **So this loop makes exactly one request in production**, and
    is written anyway for the reason `list_tasks` gives for the same shape:
    an absent `last_page` is read as "this was the last", so an unpaged
    response terminates rather than spinning, while a paged one would be
    followed if the task system ever grew pages here. A configured field
    missing from the result would be reported as *absent*, which withholds
    its writes and sends someone looking for a field that is there -- which
    is why completeness is worth defending even against a contract that does
    not page today.
    """
    collected: list[ClickUpFieldDefinition] = []
    page = 0
    while True:
        response = await _send(
            "GET", f"{_BASE_URL}/api/v2/folder/{folder_id}/field", params={"page": page}
        )
        payload = response.json()
        fields = payload.get("fields") or []
        collected.extend(
            _field_definition(raw) for raw in fields if isinstance(raw, Mapping)
        )
        if payload.get("last_page", True) or not fields:
            return tuple(collected)
        page += 1


async def set_task_field(task_id: str, field_id: str, value: object) -> None:
    """Sets one Custom Field's value on an existing task.

    A value drawn from a field's option set is named by **that option's
    identifier**, which is the other end of the contract `list_tasks` holds
    up from the read side: the two must speak the same representation, or a
    caller comparing what a task carries against what it would write finds
    them different forever.

    **A Custom Field, unlike a tag, is not created by being used**, and this
    adapter creates none -- no field, no type, no option. That is a measured
    property rather than an assumption, and the whole shape of
    `record-gate-and-discipline-as-fields` turns on it. Measured 2026-08-27
    against the live workspace:

        POST   /api/v2/list/{id}/field    {} -> 400 FIELD_002 "Field type is required"
        POST   /api/v2/folder/{id}/field  {} -> 400 FIELD_002
        OPTIONS /api/v2/field/{id}           -> 405, `allow: PATCH`
        PATCH  /api/v2/field/{id}         {} -> 403 FIELD_262 "Access denied for
                                                 updating field api"
        POST   /api/v2/field/{id}/option     -> 404
        POST   /api/v3/list/{id}/field       -> 404

    So an undocumented create endpoint exists and validates, and an
    undocumented update endpoint exists but refuses this token. Neither is
    used. Beyond being unsupported, an option appended through them lands
    *last* in the declared order -- so repairing a missing option that way
    would clear the reported gap and silently destroy the ordering that is
    the entire reason a field is preferred to a tag.
    """
    await _send(
        "POST",
        f"{_BASE_URL}/api/v2/task/{task_id}/field/{field_id}",
        json={"value": value},
    )


def _due_date_from(raw: object) -> date | None:
    """ClickUp's epoch-millisecond due date as the calendar day it names.

    Absent, null and empty all mean "no due date"; ClickUp sends the value
    as a string of digits, but tolerates a number here too.
    """
    if raw is None or raw == "" or not isinstance(raw, str | int | float):
        return None
    return datetime.fromtimestamp(int(raw) / 1000, tz=UTC).date()


def _option_ids_by_orderindex(field: Mapping[str, object]) -> Mapping[int, str]:
    """A field's options, indexed by the number a task's value reports.

    Built from what the task payload itself carries: each entry of a task's
    `custom_fields` embeds its own `type_config.options`, so no field
    definition has to be obtained separately and no second request is made.
    """
    config = field.get("type_config")
    options = config.get("options") if isinstance(config, Mapping) else None
    if not isinstance(options, Sequence):
        return {}
    indexed: dict[int, str] = {}
    for option in options:
        if not isinstance(option, Mapping):
            continue
        order, identifier = option.get("orderindex"), option.get("id")
        if isinstance(order, int) and identifier is not None:
            indexed[order] = str(identifier)
    return indexed


def _custom_field_value(field: Mapping[str, object]) -> object | None:
    """One Custom Field's value, in the representation a write of it sends.

    Measured 2026-08-27: ClickUp reports a drop-down's value as the option's
    integer `orderindex`, while a write of that value sends the option's
    identifier. Reporting the difference to the caller would make every task
    differ from what the caller would write, on every pass, forever -- two
    writes per task per pass, each succeeding and changing nothing, and
    invisible to a mocked test. So the difference is settled here.

    An unset field omits the `value` key entirely rather than reporting `0`,
    and that is preserved: `0` is a legitimate value -- it is the first
    option -- so reading absence as `0` would report every unvalued task as
    carrying the first option of its field.

    Total by construction: a value of any shape this function cannot
    interpret as a single option is returned as the payload carries it,
    stringified, rather than raising or being reported absent. This read
    gates a launch's projection and its completion intake, so a value nobody
    can make sense of must not be able to stop either, and absence would
    discard the difference between "nothing set" and "not recognised".
    """
    if "value" not in field:
        return None
    value = field["value"]
    if value is None:
        return None
    # A bool is an `int` in Python and is not an orderindex; check it first
    # so `True` is never read as option 1.
    if isinstance(value, bool):
        return value
    order = _as_orderindex(value)
    if order is not None:
        resolved = _option_ids_by_orderindex(field).get(order)
        if resolved is not None:
            return resolved
    # Anything else -- an identifier already, a list of them, a mapping, a
    # shape nothing anticipates -- is carried through **exactly as the
    # payload holds it**. Altering it would destroy the caller's ability to
    # tell what is actually there, and reporting it absent would discard the
    # difference between "nothing set" and "not recognised".
    return value


def _as_orderindex(value: object) -> int | None:
    """The option position a value names, if it names one.

    ClickUp reported an integer when measured, but a numeric *string* names
    the same position and must normalise identically -- an option identifier
    is a uuid and never all digits, so the two cannot be confused.
    """
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _custom_field_values(raw: Mapping[str, object]) -> Mapping[str, object]:
    fields = raw.get("custom_fields") or ()
    if not isinstance(fields, Sequence):
        return {}
    values: dict[str, object] = {}
    for field in fields:
        if not isinstance(field, Mapping) or "id" not in field:
            continue
        value = _custom_field_value(field)
        if value is not None:
            values[str(field["id"])] = value
    return values


def _task_state(raw: Mapping[str, object]) -> ClickUpTaskState:
    status = raw.get("status") or {}
    assert isinstance(status, Mapping)
    description = raw.get("description")
    assignees = raw.get("assignees") or ()
    assert isinstance(assignees, Sequence)
    tags = raw.get("tags") or ()
    assert isinstance(tags, Sequence)
    return ClickUpTaskState(
        id=str(raw["id"]),
        status=str(status.get("status", "")),
        closed=status.get("type") == _CLOSED_STATUS_TYPE,
        due_date=_due_date_from(raw.get("due_date")),
        name=str(raw.get("name", "")),
        description=str(description) if description else None,
        # ClickUp reports an assignee as an object carrying the user's
        # own id; the loop compares ids, never display names.
        assignees=tuple(
            str(member["id"])
            for member in assignees
            if isinstance(member, Mapping) and "id" in member
        ),
        # ClickUp reports a tag as an object carrying its name and its
        # colours; only the name is judged, so a tag object without one
        # is skipped rather than read as an empty tag.
        tags=tuple(
            str(tag["name"])
            for tag in tags
            if isinstance(tag, Mapping) and "name" in tag
        ),
        custom_field_values=_custom_field_values(raw),
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
        response = await _send(
            "GET",
            f"{_BASE_URL}/api/v2/list/{list_id}/task",
            params={"include_closed": "true", "page": page},
        )
        payload = response.json()
        tasks = payload.get("tasks") or []
        collected.extend(_task_state(raw) for raw in tasks)
        # `last_page` absent is read as "this was the last": an unpaged
        # response must terminate the loop rather than spin forever.
        if payload.get("last_page", True) or not tasks:
            return tuple(collected)
        page += 1
