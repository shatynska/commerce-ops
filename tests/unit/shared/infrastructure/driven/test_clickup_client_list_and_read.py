"""Tests for the `clickup-task-client` capability's read and list-creation
operations, added by `add-clickup-completion-loop`.

Derived strictly from that change's delta spec:
`openspec/changes/add-clickup-completion-loop/specs/clickup-task-client/spec.md`

- ADDED "A list can be created in a given folder" / Scenario: List created
  in a folder
- ADDED "The tasks of a list can be read" / Scenario: Tasks returned with
  status and due date
- ADDED "The tasks of a list can be read" / Scenario: An empty list reads
  as empty
- ADDED "The tasks of a list can be read" / Scenario: A multi-page list is
  read completely
- MODIFIED "A failed ClickUp request is surfaced to the caller" / Scenario:
  ClickUp rejects a create-list request
- MODIFIED "A failed ClickUp request is surfaced to the caller" / Scenario:
  ClickUp rejects a read of a list's tasks
- MODIFIED "A failed ClickUp request is surfaced to the caller" / Scenario:
  ClickUp is unreachable -- the two *new* operations only

This file is additive. The MODIFIED requirement's other two scenarios
("ClickUp rejects a create request", "ClickUp rejects an update request")
are carried over into the delta **verbatim**, so the existing tests in
`test_clickup_client.py` still cover them unchanged and are not touched,
duplicated, or superseded here. The same file already covers the
unreachable scenario on the create-task and update-task paths; only the
two paths the delta newly names are covered below. See
`openspec/changes/add-clickup-completion-loop/test-manifest.md` for the
full accounting.

## Names and shapes used here: what is fixed, and what is INVENTED

Fixed by this change's `tasks.md`, so SPECIFIED for the purposes of these
tests:

- `create_list(folder_id, name)` on
  `shared/infrastructure/driven/clickup_client.py` (task 1.2).
- `list_tasks(list_id)` on the same module, which "includes closed tasks
  (`include_closed`), follows ClickUp's pagination until exhausted, maps
  each task to the read-side value object with the closed judgement taken
  from the status `type` field and the due date parsed from ClickUp's
  epoch-millisecond field (`None` when unset)" (task 1.3).

INVENTED, and recorded in the manifest as unresolved project questions:

- The read-side value object's attribute spellings: `.id`, `.status`,
  `.closed`, `.due_date`. Task 1.1 fixes the four *facts* it carries
  (identifier, status name, closed-type flag, due date or `None`) and no
  artifact fixes the names. Correcting them is a fixture correction.
- ClickUp's own URL shapes -- `POST /api/v2/folder/{folder_id}/list` and
  `GET /api/v2/list/{list_id}/task` -- follow the existing adapter's
  `/api/v2/...` convention that `test_clickup_client.py` already pins for
  create/update. The scenarios say only "ClickUp receives a create-list
  request for that folder"; the path is how that is observed.
- The `get_client()` cached factory used as the substitution seam, exactly
  as `test_clickup_client.py` documents it.

Tolerated deliberately rather than invented:

- `create_list`'s return **shape**. The delta says it returns "the created
  list's identifier"; task 1.1 says a "list-creation result carrying the
  new list's identifier". The two artifacts agree on the content and
  disagree on the shape, so `_list_identifier()` below accepts either a
  bare string or an object carrying it, and the assertion is on the
  identifier -- which is what the scenario states.
- How a due date is typed once parsed. `_as_date()` normalises a `date`,
  a `datetime`, or an epoch-millisecond number to the calendar day, so
  the assertion is on the day ClickUp reported rather than on a wire
  encoding no artifact pins.

## `pytest.raises(Exception)` is deliberate

As in `test_clickup_client.py`: the requirement says only that the caller
"receives an error", and no artifact names a type. Each block is scoped to
the single call under test, per `ai-toolkit:testing`.

## At the time this pass was written, neither operation exists

`create_list` and `list_tasks` are added by tasks 1.1-1.3. Every test here
is expected to fail on an absent target (`ImportError`) until they land.
Per `ai-toolkit:testing`, that failure establishes only absence -- nothing
about whether the assertions below are well-formed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import (
    create_list,
    list_tasks,
)

pytestmark = pytest.mark.anyio

TOKEN = "test-clickup-api-token-not-a-real-credential"

FOLDER_ID = "90110042424"
LIST_ID = "901234002"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixtures / test doubles -- the seam `test_clickup_client.py` documents
# ---------------------------------------------------------------------------


def _clear_client_cache() -> None:
    factory = getattr(clickup_client, "get_client", None)
    cache_clear = getattr(factory, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


@pytest.fixture(autouse=True)
def _reset_client_cache() -> Iterator[None]:
    _clear_client_cache()
    yield
    _clear_client_cache()


@pytest.fixture()
def configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
    """Substitutes the cached client factory with a `MockTransport`-backed
    one, so no request reaches the network."""
    original = getattr(clickup_client, "get_client", None)
    assert original is not None, (
        "expected a `get_client()` cached factory in "
        "`shared/infrastructure/driven/clickup_client.py` -- the seam "
        "`test_clickup_client.py` already substitutes through"
    )
    monkeypatch.setattr(
        clickup_client,
        "get_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


def recording_handler(
    response: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response

    return handler, captured


def paging_handler(
    pages: list[httpx.Response],
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Serves `pages` in order, one per request, repeating the last one if
    the client asks for more than were scripted.

    The pages are served in request order rather than keyed off a `page`
    query parameter: the delta says only that a multi-page list is
    returned completely, and no artifact fixes ClickUp's paging parameter
    name, so keying on it would assert a contract nobody stated.
    """
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        index = min(len(captured) - 1, len(pages) - 1)
        return pages[index]

    return handler, captured


def raising_handler(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


# ---------------------------------------------------------------------------
# Tolerant readers -- see the module docstring for why each is tolerant
# ---------------------------------------------------------------------------


def _list_identifier(result: Any) -> str:
    """The created list's identifier, however `create_list` returns it."""
    if isinstance(result, str):
        return result
    for attribute in ("id", "list_id", "identifier"):
        value = getattr(result, attribute, None)
        if value is not None:
            return str(value)
    pytest.fail(
        "create_list returned something that carries no list identifier: "
        f"{result!r}. The delta requires the created list's identifier to "
        "reach the caller."
    )


def _as_date(value: Any) -> date | None:
    """Normalises a parsed due date to the calendar day it names."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(UTC).date()
    if isinstance(value, date):
        return value
    if isinstance(value, int | float):
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    if isinstance(value, str) and value.isdigit():
        return datetime.fromtimestamp(float(value) / 1000.0, tz=UTC).date()
    pytest.fail(f"cannot read {value!r} as a due date")


def _clickup_task_json(
    identifier: str,
    *,
    status: str,
    status_type: str,
    due_date_ms: str | None,
) -> dict[str, Any]:
    """One task as ClickUp's own list-tasks response carries it.

    The `status.type` field is the closed judgement the delta requires and
    design.md names ("ClickUp statuses are compared by their `type` field
    (`closed` vs anything else), never by status name").
    """
    return {
        "id": identifier,
        "name": f"task {identifier}",
        "status": {
            "status": status,
            "type": status_type,
            "color": "#6bc950",
            "orderindex": 3,
        },
        "due_date": due_date_ms,
    }


# ---------------------------------------------------------------------------
# Requirement: A list can be created in a given folder
# ---------------------------------------------------------------------------


async def test_a_list_is_created_in_the_given_folder(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: List created in a folder.

    WHEN a list is created with a folder identifier and a name
    THEN ClickUp receives a create-list request for that folder containing
    the name
    AND the caller receives the created list's identifier.
    """
    response = httpx.Response(200, json={"id": LIST_ID, "name": "Widget A (SKU-1)"})
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    created = await create_list(folder_id=FOLDER_ID, name="Widget A (SKU-1)")

    # SPECIFIED: ClickUp receives a create-list request for that folder.
    assert len(captured) == 1
    request = captured[0]
    assert request.method == "POST"
    # DERIVED: the endpoint path (see the module docstring); what is
    # SPECIFIED is that the request names the folder.
    assert FOLDER_ID in request.url.path
    # SPECIFIED: containing the name.
    body = json.loads(request.content)
    assert body["name"] == "Widget A (SKU-1)"

    # SPECIFIED: the caller receives the created list's identifier.
    assert _list_identifier(created) == LIST_ID


# ---------------------------------------------------------------------------
# Requirement: The tasks of a list can be read
# ---------------------------------------------------------------------------


async def test_tasks_are_returned_with_status_closed_judgement_and_due_date(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Tasks returned with status and due date.

    WHEN the tasks of a list are read
    THEN the caller receives every task in the list -- closed ones
    included -- each with its identifier, its status, whether that status
    is of the closed type, and its due date where one is set.
    """
    # 2027-03-02T00:00:00Z, chosen so the date is unambiguous in UTC.
    due_ms = str(int(datetime(2027, 3, 2, tzinfo=UTC).timestamp() * 1000))
    response = httpx.Response(
        200,
        json={
            "tasks": [
                _clickup_task_json(
                    "task-open",
                    status="in progress",
                    status_type="custom",
                    due_date_ms=due_ms,
                ),
                _clickup_task_json(
                    "task-closed",
                    status="complete",
                    status_type="closed",
                    due_date_ms=None,
                ),
            ],
            "last_page": True,
        },
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    tasks = await list_tasks(list_id=LIST_ID)

    # SPECIFIED: the request is a read of that list's tasks.
    assert captured, "no request was sent to ClickUp"
    assert captured[0].method == "GET"
    assert LIST_ID in captured[0].url.path

    # SPECIFIED: "Closed tasks SHALL be included in the result." Asserted
    # on the *request* as well as the result, because a MockTransport
    # returns whatever it is scripted to return: whether real ClickUp would
    # have included closed tasks depends on the request asking for them,
    # which task 1.3 names (`include_closed`). Without this, the result
    # assertion below would establish nothing about the live behaviour.
    query = captured[0].url.params
    assert any(
        str(value).lower() in {"true", "1"}
        for key, value in query.multi_items()
        if "closed" in key.lower()
    ), (
        "the list-tasks request did not ask ClickUp to include closed "
        f"tasks; query was {dict(query)}"
    )

    by_id = {task.id: task for task in tasks}
    # SPECIFIED: every task in the list, closed ones included.
    assert set(by_id) == {"task-open", "task-closed"}

    # SPECIFIED: its status, and whether that status is of the closed type.
    assert by_id["task-open"].status == "in progress"
    assert by_id["task-open"].closed is False
    assert by_id["task-closed"].status == "complete"
    assert by_id["task-closed"].closed is True

    # SPECIFIED: its due date where one is set, and absent where none is.
    assert _as_date(by_id["task-open"].due_date) == date(2027, 3, 2)
    assert by_id["task-closed"].due_date is None


async def test_an_empty_list_reads_as_empty_rather_than_erroring(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An empty list reads as empty.

    WHEN the tasks of a list holding no tasks are read
    THEN the caller receives an empty result, not an error.
    """
    handler, _ = recording_handler(
        httpx.Response(200, json={"tasks": [], "last_page": True})
    )
    install_transport(monkeypatch, handler)

    tasks = await list_tasks(list_id=LIST_ID)

    # SPECIFIED: an empty result, not an error.
    assert list(tasks) == []


async def test_a_multi_page_list_is_read_completely(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A multi-page list is read completely.

    WHEN the tasks of a list holding more tasks than one ClickUp page are
    read
    THEN the caller receives all of them.

    Two pages are scripted, the first marked as not the last. A client
    that stops after the first page returns 100 tasks and fails here;
    one that follows pagination to exhaustion returns 102.
    """
    first_page = [
        _clickup_task_json(
            f"task-{index:03d}", status="to do", status_type="open", due_date_ms=None
        )
        for index in range(100)
    ]
    second_page = [
        _clickup_task_json(
            f"task-{index:03d}",
            status="complete",
            status_type="closed",
            due_date_ms=None,
        )
        for index in (100, 101)
    ]
    handler, captured = paging_handler(
        [
            httpx.Response(200, json={"tasks": first_page, "last_page": False}),
            httpx.Response(200, json={"tasks": second_page, "last_page": True}),
        ]
    )
    install_transport(monkeypatch, handler)

    tasks = await list_tasks(list_id=LIST_ID)

    # SPECIFIED: the caller receives all of them.
    identifiers = [task.id for task in tasks]
    assert len(identifiers) == 102, (
        "the list was read incompletely -- pagination was not followed to "
        f"exhaustion (got {len(identifiers)} of 102, over "
        f"{len(captured)} request(s))"
    )
    assert set(identifiers) == {f"task-{index:03d}" for index in range(102)}


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A failed ClickUp request is surfaced to the caller
#
# Only the scenarios this change adds or broadens. "ClickUp rejects a
# create request" and "ClickUp rejects an update request" are carried over
# verbatim and stay covered by test_clickup_client.py, untouched.
# ---------------------------------------------------------------------------


async def test_a_rejected_create_list_request_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a create-list request.

    WHEN ClickUp responds to a create-list request with a non-success
    status
    THEN the caller receives an error and no list identifier.
    """
    handler, captured = recording_handler(
        httpx.Response(400, json={"err": "Folder not found", "ECODE": "CAT_001"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await create_list(folder_id="no-such-folder", name="Rejected list")

    # SPECIFIED precondition: the request was actually attempted, so the
    # failure traces to ClickUp's rejection and not to an earlier problem.
    assert len(captured) == 1


async def test_a_rejected_read_of_a_lists_tasks_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a read of a list's tasks.

    WHEN ClickUp responds to a request for a list's tasks with a
    non-success status
    THEN the caller receives an error and no tasks.
    """
    handler, captured = recording_handler(
        httpx.Response(401, json={"err": "Team not authorized", "ECODE": "OAUTH_017"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await list_tasks(list_id=LIST_ID)

    assert len(captured) == 1


async def test_create_list_when_clickup_is_unreachable_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable (create-list path).

    WHEN any of the client's requests cannot reach ClickUp at all (a
    connection failure or timeout, with no response received)
    THEN the caller receives an error and no result.

    The revised requirement broadens this scenario from "a create-task or
    update-task request" to "any of the client's requests"; the create-task
    and update-task paths stay covered by `test_clickup_client.py`.
    """
    install_transport(
        monkeypatch, raising_handler(httpx.ConnectError("simulated ClickUp outage"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await create_list(folder_id=FOLDER_ID, name="Unreachable list")


async def test_list_tasks_when_clickup_is_unreachable_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable (list-tasks path)."""
    install_transport(
        monkeypatch,
        raising_handler(httpx.TimeoutException("simulated ClickUp timeout")),
    )

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await list_tasks(list_id=LIST_ID)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - "Authentication is configured independently of any one caller" is an
#   existing, unmodified requirement of this capability. Its two scenarios
#   name "a task is created or updated"; the delta does not restate them
#   over the two new operations, so no credential-absence test is written
#   for `create_list`/`list_tasks` here. If that requirement is later
#   broadened the same way the failure requirement was, this is where the
#   coverage belongs.
# - Which concrete type `list_tasks` returns (sequence, list, iterator) and
#   what the read-side value object is called. The delta states only what
#   each task carries.
# ---------------------------------------------------------------------------
