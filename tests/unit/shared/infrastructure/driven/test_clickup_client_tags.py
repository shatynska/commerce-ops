"""Tests for the `clickup-task-client` capability's tag operations, added
by `tag-tasks-with-gate-and-discipline`.

Derived from that change's delta spec:
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/clickup-task-client/spec.md`

- ADDED "A task can be created carrying tags" / both scenarios
- ADDED "A tag can be added to an existing task" / both scenarios
- ADDED "A tag can be created in a space" / both scenarios
- ADDED "The tags of a space can be read" / both scenarios
- ADDED "The space containing a folder can be resolved" / its scenario
- MODIFIED "The tasks of a list can be read" / Scenario: Tasks returned
  with their tags -- the one scenario that requirement gained. Its three
  carried-forward scenarios stay covered by
  `test_clickup_client_list_and_read.py`, which is not touched here.

This file is additive: no existing test is edited, weakened or superseded.

## Harness

The `get_client()` substitution seam, the `MockTransport` handlers and the
token fixture are transcribed from `test_clickup_client_list_and_read.py`
in this directory, so no request reaches the network.

`pytest.raises(Exception)` where a failure is asserted, for the reason
that file records: the requirement says only that the caller "receives an
error" and no artifact names a type.

## What is INVENTED here

- The operation spellings `add_task_tag`, `create_space_tag`, `space_tags`
  and `space_id_for_folder`, and the `tags=` keyword on `create_task`,
  are fixed by this change's `tasks.md` (1.3-1.7), so SPECIFIED for these
  tests.
- ClickUp's own URL shapes -- `POST /api/v2/task/{id}/tag/{name}`,
  `POST|GET /api/v2/space/{id}/tag`, `GET /api/v2/folder/{id}` -- follow
  the adapter's existing `/api/v2/...` convention. The scenarios say only
  that "ClickUp receives" the request; the path is how that is observed.
  These four shapes were exercised against the live API on 2026-08-26 and
  are recorded in the change's design.md.
- That `space_tags` yields tag *names*. The requirement says it reports
  "the tag names a space holds", so the content is specified; that they
  arrive as plain strings is the shape this file assumes.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator

import httpx
import pytest

from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import (
    add_task_tag,
    create_space_tag,
    create_task,
    list_tasks,
    space_id_for_folder,
    space_tags,
)

pytestmark = pytest.mark.anyio

TOKEN = "test-clickup-api-token-not-a-real-credential"

FOLDER_ID = "90110042424"
SPACE_ID = "90110099999"
LIST_ID = "901234002"
TASK_ID = "86abc1234"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
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


@pytest.fixture(autouse=True)
def configured_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLICKUP_API_TOKEN", TOKEN)


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> None:
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


def _created_task_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={"id": TASK_ID, "url": f"https://app.clickup.com/t/{TASK_ID}"},
    )


def _body_of(request: httpx.Request) -> dict[str, object]:
    payload = json.loads(request.content.decode() or "{}")
    assert isinstance(payload, dict)
    return payload


# ---------------------------------------------------------------------------
# Requirement: A task can be created carrying tags
# ---------------------------------------------------------------------------


async def test_task_created_with_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Task created with tags.

    WHEN a task is created with a list identifier, a name, and two tag
    names
    THEN ClickUp receives a create-task request for that list containing
    both tag names
    AND the caller receives the created task's identifier and URL.
    """
    handler, captured = recording_handler(_created_task_response())
    install_transport(monkeypatch, handler)

    created = await create_task(
        list_id=LIST_ID,
        name="Conform the title",
        tags=["gate:listable", "discipline:listing"],
    )

    assert len(captured) == 1
    assert LIST_ID in str(captured[0].url)
    # SPECIFIED: the request contains both tag names.
    sent = _body_of(captured[0])
    assert sent["tags"] == ["gate:listable", "discipline:listing"]
    # SPECIFIED: the caller receives the created task's identifier and URL.
    assert created.id == TASK_ID
    assert created.url.endswith(TASK_ID)


async def test_task_created_without_tags_sends_no_tags_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Task created without tags.

    WHEN a task is created with no tags supplied
    THEN the create-task request carries no tags field.

    SPECIFIED in the strong form -- **no** tags key, not an empty one:
    "A create with no tags supplied SHALL send no tag claim at all, rather
    than a claim that the task carries none." An implementation sending
    `"tags": []` passes a weaker assertion and fails this one.
    """
    handler, captured = recording_handler(_created_task_response())
    install_transport(monkeypatch, handler)

    await create_task(list_id=LIST_ID, name="Conform the title")

    assert "tags" not in _body_of(captured[0])


# ---------------------------------------------------------------------------
# Requirement: A tag can be added to an existing task
# ---------------------------------------------------------------------------


async def test_a_tag_is_added_to_a_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A tag is added to a task.

    WHEN a tag is added to a task by the task's identifier and the tag's
    name
    THEN ClickUp receives an add-tag request for that task and that tag.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await add_task_tag(TASK_ID, "gate:listable")

    assert len(captured) == 1
    url = str(captured[0].url)
    # SPECIFIED: the request names that task and that tag. The tag is
    # percent-encoded, since `gate:listable` carries a colon.
    assert TASK_ID in url
    assert "gate%3Alistable" in url or "gate:listable" in url


async def test_adding_a_tag_twice_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Adding a tag twice is not an error.

    WHEN a tag is added to a task that already carries it
    THEN the caller receives no error.

    ClickUp answers a repeat add with a success, so the assertion is that
    the client does not manufacture a failure of its own -- returning
    normally *is* the assertion.
    """
    handler, _ = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await add_task_tag(TASK_ID, "gate:listable")
    await add_task_tag(TASK_ID, "gate:listable")


async def test_a_failed_add_tag_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client suppresses no ClickUp failure, as
    `clickup-task-client`'s standing requirement demands of every
    operation."""
    handler, _ = recording_handler(httpx.Response(500, json={"err": "boom"}))
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await add_task_tag(TASK_ID, "gate:listable")


# ---------------------------------------------------------------------------
# Requirement: A tag can be created in a space
# ---------------------------------------------------------------------------


async def test_a_tag_is_created_in_a_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A tag is created in a space.

    WHEN a tag is created with a space identifier and a name
    THEN ClickUp receives a create-tag request for that space containing
    the name.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await create_space_tag(SPACE_ID, "gate:listable")

    assert len(captured) == 1
    assert SPACE_ID in str(captured[0].url)
    # SPECIFIED: the request contains the name. ClickUp nests it under a
    # `tag` object, which is the wire shape the live API accepts.
    assert "gate:listable" in captured[0].content.decode()


async def test_creating_an_existing_tag_is_not_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Creating an existing tag leaves it as it stands.

    WHEN a tag is created in a space that already holds a tag of that name
    THEN the caller receives no error and the existing tag is unaltered.

    Measured against the live API on 2026-08-26: a repeat create answers
    `200` and creates no duplicate (see the change's design.md). What this
    test pins is the client's half -- it manufactures no failure of its
    own on the repeat.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await create_space_tag(SPACE_ID, "gate:listable")
    await create_space_tag(SPACE_ID, "gate:listable")

    assert len(captured) == 2


# ---------------------------------------------------------------------------
# Requirement: The tags of a space can be read
# ---------------------------------------------------------------------------


async def test_a_spaces_tags_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A space's tags are read.

    WHEN the tags of a space are read
    THEN the caller receives the name of every tag the space holds.
    """
    handler, captured = recording_handler(
        httpx.Response(
            200,
            json={
                "tags": [
                    {"name": "gate:listable", "tag_bg": "#000", "tag_fg": "#fff"},
                    {"name": "discipline:listing", "tag_bg": "#000", "tag_fg": "#fff"},
                ]
            },
        )
    )
    install_transport(monkeypatch, handler)

    names = await space_tags(SPACE_ID)

    assert SPACE_ID in str(captured[0].url)
    assert set(names) == {"gate:listable", "discipline:listing"}


async def test_a_space_with_no_tags_reads_as_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A space with no tags reads as empty.

    WHEN the tags of a space holding no tags are read
    THEN the caller receives an empty result, not an error.

    The launch space held exactly this when the change was written, so
    this is the state the first pass after deploy actually meets.
    """
    handler, _ = recording_handler(httpx.Response(200, json={"tags": []}))
    install_transport(monkeypatch, handler)

    assert await space_tags(SPACE_ID) == ()


# ---------------------------------------------------------------------------
# Requirement: The space containing a folder can be resolved
# ---------------------------------------------------------------------------


async def test_a_folder_resolves_to_its_space(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A folder resolves to its space.

    WHEN the space of a folder is resolved by the folder's identifier
    THEN the caller receives the identifier of the space that folder
    belongs to.

    This is what lets the projection reach the space without a second
    configured value -- design.md, Decision 1. The payload shape is the
    one the live API returned on 2026-08-26.
    """
    handler, captured = recording_handler(
        httpx.Response(
            200,
            json={
                "id": FOLDER_ID,
                "name": "Launches",
                "space": {"id": SPACE_ID, "name": "Product Launch", "access": True},
            },
        )
    )
    install_transport(monkeypatch, handler)

    resolved = await space_id_for_folder(FOLDER_ID)

    assert FOLDER_ID in str(captured[0].url)
    assert resolved == SPACE_ID


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The tasks of a list can be read
# ---------------------------------------------------------------------------


async def test_tasks_are_returned_with_their_tags(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Tasks returned with their tags.

    WHEN the tasks of a list are read and a task carries tags
    THEN that task's tag names are reported with it
    AND a task carrying no tags is reported with an empty set of tags, not
    an error.

    Both clauses in one test, because the discriminating case is the pair:
    a reader that dropped tags entirely, and one that failed on a task
    carrying none, are different faults and both are caught here.
    """
    handler, _ = recording_handler(
        httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "id": "task-tagged",
                        "status": {"status": "to do", "type": "open"},
                        "due_date": None,
                        "tags": [
                            {"name": "gate:listable"},
                            {"name": "discipline:listing"},
                        ],
                    },
                    {
                        "id": "task-bare",
                        "status": {"status": "to do", "type": "open"},
                        "due_date": None,
                    },
                ],
                "last_page": True,
            },
        )
    )
    install_transport(monkeypatch, handler)

    tasks = {task.id: task for task in await list_tasks(LIST_ID)}

    # SPECIFIED: the tag names are reported with the task.
    assert set(tasks["task-tagged"].tags) == {"gate:listable", "discipline:listing"}
    # SPECIFIED: a task carrying none reads as empty, not as an error.
    assert tasks["task-bare"].tags == ()
