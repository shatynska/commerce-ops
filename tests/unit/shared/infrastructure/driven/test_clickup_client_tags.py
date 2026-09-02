"""Tags on the shared ClickUp adapter: creation, attachment, and reading.

Derived strictly from the delta spec of the OpenSpec change
`tag-tasks-with-gate-and-discipline`:
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/clickup-task-client/spec.md`

Covers, as ADDED requirements:

- *A task can be created carrying tags* — both scenarios.
- *A tag can be added to an existing task* — both scenarios.

And, from the MODIFIED requirements, only the scenarios this change adds or
whose rule it broadens:

- *The tasks of a list can be read* / Scenario: **Tasks returned with their
  tags** (new).
- *A failed ClickUp request is surfaced to the caller* / Scenario: **ClickUp
  rejects a tag write** (new), and *Scenario: ClickUp is unreachable* over
  the one operation this change adds.

The other scenarios of both MODIFIED requirements are carried into the delta
**verbatim** — "Tasks returned with status and due date", "An empty list
reads as empty", "A multi-page list is read completely", and the four
existing rejection scenarios. They stay covered by
`test_clickup_client.py` and `test_clickup_client_list_and_read.py`, which
this file neither touches nor duplicates. See
`openspec/changes/tag-tasks-with-gate-and-discipline/test-manifest.md` for
the full accounting.

## The premise this change turns on, and how it is asserted

`design.md` measured against the live API on 2026-08-26 that **a tag needs
no prior existence**: attaching an unknown tag name answers `200` and
creates it in the task's space. Six earlier drafts assumed the opposite and
built a seeding subsystem on it. Both tag scenarios below therefore assert
the *negative* — that **no space-level request is sent** — because that is
what distinguishes this change's shape from the deleted one, and an
implementation that resurrected a vocabulary read would otherwise pass
every positive assertion here.

## Names and shapes: what is fixed, and what is INVENTED

Fixed by this change's `tasks.md`, so treated as SPECIFIED for these tests:

- `tags: tuple[str, ...] = ()` on the read-side value object in
  `shared/domain/clickup.py`, defaulting empty (task 1.1) — so `.tags` is
  the attribute read below.
- `tags` as a keyword on `clickup_client.create_task`, "sent only when
  non-empty — omitted rather than sent as `[]`" (task 1.3).
- `add_task_tag(task_id, tag_name)` over
  `POST /api/v2/task/{task_id}/tag/{tag_name}` (task 1.4).

INVENTED, and recorded in the manifest as unresolved project questions:

- The `get_client()` cached factory used as the substitution seam, exactly
  as `test_clickup_client.py` documents it.
- That `add_task_tag`'s two arguments are passed positionally below. Only
  the names are fixed; the call shape is not. `_add_tag()` is the single
  correction point.
- Whether the tag names in a create body are a JSON list. The scenario says
  only that the request "contain[s] both tag names", so the assertion is
  membership in whatever the `tags` key carries, not the container's type.

## `pytest.raises(Exception)` is deliberate

As in the two sibling files: the requirement says only that the caller
"receives an error", and no artifact names a type. Each block is scoped to
the single call under test, per `ai-toolkit:testing`.

## Expected first-run state

`add_task_tag` does not exist, and neither `create_task`'s `tags` keyword
nor the read-side object's `tags` attribute does. Every test here is
expected to fail on an absent target — `ImportError` for the import,
`TypeError`/`AttributeError` for the other two. Per `ai-toolkit:testing`
that failure establishes only absence, and nothing about whether these
assertions are well-formed.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` at the worktree root —
1064 passed, 0 failed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any, Final
from urllib.parse import unquote

import httpx
import pytest

from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import (
    add_task_tag,
    create_task,
    list_tasks,
)

pytestmark = pytest.mark.anyio

TOKEN: Final = "test-clickup-api-token-not-a-real-credential"

LIST_ID: Final = "901234002"
TASK_ID: Final = "86a1b2c3d"

# The two owned prefixes the launch projection composes. The `:` is the
# character `design.md` measured surviving both the create body and the
# percent-encoded path segment, so it is deliberately kept in the fixtures
# rather than simplified away.
GATE_TAG: Final = "gate:listable"
DISCIPLINE_TAG: Final = "discipline:listing"


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


def raising_handler(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


async def _add_tag(task_id: str, tag_name: str) -> Any:
    """INVENTED call shape -- the single correction point for
    `add_task_tag`'s signature (task 1.4 fixes only the two argument
    names)."""
    return await add_task_tag(task_id, tag_name)


def _tags_claimed(body: dict[str, Any]) -> Any:
    """The create body's tag claim, under whichever key carries it.

    Task 1.3 names the field `tags`; matched case-insensitively so a
    `camelCase` spelling would not read as "no claim at all", which is the
    other thing this file has to be able to tell apart.
    """
    for key, value in body.items():
        if key.lower() == "tags":
            return value
    return None


def _tag_names(claimed: Any) -> set[str]:
    """The names inside a create body's tag claim, whatever container it
    arrived in — a list of names, or a list of objects carrying them."""
    if claimed is None:
        return set()
    if isinstance(claimed, str):
        return {claimed}
    names: set[str] = set()
    for item in claimed:
        if isinstance(item, dict):
            name = item.get("name")
            if name is not None:
                names.add(str(name))
        else:
            names.add(str(item))
    return names


def _clickup_task_json(
    identifier: str,
    *,
    tags: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """One task as ClickUp's own list-tasks response carries it.

    `tags=None` omits the key entirely, which is how a payload from before
    tags were read looks and what the existing read tests already send.
    """
    payload: dict[str, Any] = {
        "id": identifier,
        "name": f"task {identifier}",
        "status": {
            "status": "to do",
            "type": "open",
            "color": "#6bc950",
            "orderindex": 0,
        },
        "due_date": None,
    }
    if tags is not None:
        payload["tags"] = tags
    return payload


def _clickup_tag_json(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "tag_fg": "#000000",
        "tag_bg": "#ffffff",
        "creator": 183,
    }


def _created_task_json(identifier: str) -> dict[str, Any]:
    return {
        "id": identifier,
        "url": f"https://app.clickup.com/t/{identifier}",
        "name": "Conform the title to the style guide",
    }


def _identifier_of(created: Any) -> str:
    """The created task's identifier, however `create_task` returns it."""
    if isinstance(created, str):
        return created
    for attribute in ("id", "task_id", "identifier"):
        value = getattr(created, attribute, None)
        if value is not None:
            return str(value)
    pytest.fail(f"create_task returned no task identifier: {created!r}")


def _url_of(created: Any) -> str:
    for attribute in ("url", "task_url"):
        value = getattr(created, attribute, None)
        if value is not None:
            return str(value)
    pytest.fail(f"create_task returned no task URL: {created!r}")


def _assert_no_space_request(captured: list[httpx.Request]) -> None:
    """SPECIFIED, in both tag scenarios: "no space-level tag request — no
    tag creation, and no read of a space's tags — is sent".

    Asserted on every request the client made, in either direction, which
    is what "before or after" requires.
    """
    space_requests = [
        f"{request.method} {request.url}"
        for request in captured
        if "/space" in unquote(str(request.url)).lower()
    ]
    assert space_requests == [], (
        "a space-level request was sent; this change reaches nothing but the "
        f"tasks themselves — a tag needs no prior existence. Sent: "
        f"{space_requests}"
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A task can be created carrying tags
# ---------------------------------------------------------------------------


async def test_a_task_is_created_carrying_the_supplied_tags(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task created with tags.

    WHEN a task is created with a list identifier, a name, and two tag names
    THEN ClickUp receives a create-task request for that list containing
    both tag names
    AND the caller receives the created task's identifier and URL.
    """
    handler, captured = recording_handler(
        httpx.Response(200, json=_created_task_json(TASK_ID))
    )
    install_transport(monkeypatch, handler)

    created = await create_task(
        list_id=LIST_ID,
        name="Conform the title to the style guide",
        tags=(GATE_TAG, DISCIPLINE_TAG),
    )

    # SPECIFIED: ClickUp receives a create-task request for that list.
    assert len(captured) == 1, f"expected exactly one request, got {captured}"
    request = captured[0]
    assert request.method == "POST"
    # DERIVED: the endpoint path; what is SPECIFIED is that the request is
    # a create for that list.
    assert LIST_ID in request.url.path

    # SPECIFIED: containing both tag names. Asserted as an exact set, so an
    # implementation dropping one, or adding a third of its own, fails.
    body = json.loads(request.content)
    assert _tag_names(_tags_claimed(body)) == {GATE_TAG, DISCIPLINE_TAG}, (
        f"the create body did not claim exactly both tags: {body!r}"
    )

    # SPECIFIED: the caller receives the created task's identifier and URL.
    assert _identifier_of(created) == TASK_ID
    assert _url_of(created) == f"https://app.clickup.com/t/{TASK_ID}"

    # SPECIFIED (the ADDED tag requirement, and the projection's own
    # scenario): a create needs no tag to exist first.
    _assert_no_space_request(captured)


async def test_a_create_without_tags_sends_no_tags_field_at_all(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Task created without tags.

    WHEN a task is created with no tags supplied
    THEN the create-task request carries no tags field.

    SPECIFIED, and the reason this is its own scenario: "A create with no
    tags supplied SHALL send no tag claim at all, rather than a claim that
    the task carries none." An empty list is a *claim* — it is exactly what
    an implementation sending `"tags": []` would produce, and asserting
    only "no tag names are claimed" would let it through. So the assertion
    is on the key's absence.
    """
    handler, captured = recording_handler(
        httpx.Response(200, json=_created_task_json(TASK_ID))
    )
    install_transport(monkeypatch, handler)

    await create_task(list_id=LIST_ID, name="Conform the title to the style guide")

    assert len(captured) == 1
    body = json.loads(captured[0].content)
    assert _tags_claimed(body) is None, (
        "a create with no tags supplied sent a tag claim anyway: "
        f"{_tags_claimed(body)!r} — the field is to be omitted, not sent empty"
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A tag can be added to an existing task
# ---------------------------------------------------------------------------


async def test_a_tag_is_added_to_a_task_with_no_space_request_first(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A tag is added to a task.

    WHEN a tag is added to a task by the task's identifier and the tag's
    name
    THEN ClickUp receives an add-tag request for that task and that tag
    AND no space-level tag request — no tag creation, and no read of a
    space's tags — is sent first.

    The second clause is the whole point of the change's final shape, and
    it is asserted twice over: no request names a space, **and** exactly
    one request was sent at all.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await _add_tag(TASK_ID, GATE_TAG)

    # SPECIFIED: no space-level request is sent first — so the add is the
    # only request there is.
    assert len(captured) == 1, (
        "the add-tag path sent more than the one request it needs; a tag "
        f"needs no prior existence. Sent: "
        f"{[f'{r.method} {r.url}' for r in captured]}"
    )
    _assert_no_space_request(captured)

    # SPECIFIED: an add-tag request for that task and that tag. The URL is
    # read decoded, because `design.md` measured the `:` surviving
    # percent-encoded in the path segment — how it is encoded is not the
    # assertion, that the request names the tag is.
    request = captured[0]
    assert request.method == "POST"
    decoded = unquote(str(request.url))
    assert TASK_ID in decoded, f"the add-tag request does not name the task: {decoded}"
    assert GATE_TAG in decoded, f"the add-tag request does not name the tag: {decoded}"


async def test_adding_a_tag_the_task_already_carries_is_not_an_error(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Adding a tag twice is not an error.

    WHEN a tag is added to a task that already carries it
    THEN the caller receives no error.

    `design.md` measured the repeated add answering `200` with the task
    still carrying the tag once. What this test constrains is the *client*:
    it must not read a repeat as a fault of its own, because the
    projection's add-if-missing rule is convergent and a pass that
    re-attempted an add must survive it.
    """
    handler, captured = recording_handler(httpx.Response(200, json={}))
    install_transport(monkeypatch, handler)

    await _add_tag(TASK_ID, GATE_TAG)
    # SPECIFIED: the second add — against a task that now carries it — is
    # not an error. Deliberately outside a `pytest.raises`: returning
    # normally is the assertion.
    await _add_tag(TASK_ID, GATE_TAG)

    assert len(captured) == 2, (
        "the second add was not sent; the client suppressed a repeat "
        "rather than letting ClickUp answer it"
    )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The tasks of a list can be read
#
# Only the scenario this change adds. The other three are carried into the
# delta verbatim and stay covered by `test_clickup_client_list_and_read.py`.
# ---------------------------------------------------------------------------


async def test_tasks_are_returned_with_their_tag_names(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Tasks returned with their tags.

    WHEN the tasks of a list are read and a task carries tags
    THEN that task's tag names are reported with it
    AND a task carrying no tags is reported with an empty set of tags, not
    an error.

    The tagged task below carries a **foreign** tag alongside the two owned
    ones, because the projection's rule turns on telling them apart: a read
    that reported only recognised names would leave the projection unable
    to see that a member's tag is there, and its "never touched" rule
    unverifiable.
    """
    response = httpx.Response(
        200,
        json={
            "tasks": [
                _clickup_task_json(
                    "task-tagged",
                    tags=[
                        _clickup_tag_json(GATE_TAG),
                        _clickup_tag_json(DISCIPLINE_TAG),
                        _clickup_tag_json("waiting-on-supplier"),
                    ],
                ),
                _clickup_task_json("task-untagged", tags=[]),
            ],
            "last_page": True,
        },
    )
    handler, _ = recording_handler(response)
    install_transport(monkeypatch, handler)

    tasks = await list_tasks(list_id=LIST_ID)

    by_id = {task.id: task for task in tasks}
    assert set(by_id) == {"task-tagged", "task-untagged"}

    # SPECIFIED: that task's tag names are reported with it -- the names,
    # not ClickUp's tag objects, and every one of them.
    assert set(by_id["task-tagged"].tags) == {
        GATE_TAG,
        DISCIPLINE_TAG,
        "waiting-on-supplier",
    }

    # SPECIFIED: a task carrying no tags is reported with an empty set of
    # tags, not an error.
    assert list(by_id["task-untagged"].tags) == []


async def test_a_task_payload_without_a_tags_key_reads_without_erroring(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Tasks returned with their tags -- the tolerance half.

    DERIVED, not SPECIFIED: no scenario states what a payload *omitting*
    the `tags` key does. It is asserted because the read-side value object
    defaults `tags` to empty (task 1.1) precisely so that "existing
    constructions stay valid", and because a task ClickUp answers without
    the key must not become an error on a pass that used to work. A tag
    object carrying no `name` is tolerated in the same spirit (task 1.2).

    What is *not* asserted here is what a nameless tag object becomes --
    no artifact says, so pinning it would invent behaviour.
    """
    response = httpx.Response(
        200,
        json={
            "tasks": [
                _clickup_task_json("task-legacy", tags=None),
                _clickup_task_json(
                    "task-odd",
                    tags=[{"tag_bg": "#ffffff"}, _clickup_tag_json(GATE_TAG)],
                ),
            ],
            "last_page": True,
        },
    )
    handler, _ = recording_handler(response)
    install_transport(monkeypatch, handler)

    tasks = await list_tasks(list_id=LIST_ID)

    by_id = {task.id: task for task in tasks}
    # DERIVED: a payload with no `tags` key reads as carrying none.
    assert list(by_id["task-legacy"].tags) == []
    # DERIVED: a nameless tag object does not cost the task its named ones.
    assert GATE_TAG in set(by_id["task-odd"].tags)


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A failed ClickUp request is surfaced to the caller
#
# The enumeration is extended to name a fifth operation. Only the scenarios
# bearing on that operation are written here; the other four stay covered by
# the two existing files, untouched.
# ---------------------------------------------------------------------------


async def test_a_rejected_tag_write_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp rejects a tag write.

    WHEN ClickUp responds to an add-tag request with a non-success status
    THEN the caller receives an error and no result.

    `tasks.md` 1.5 states why this matters more than the shape suggests:
    the *projection* is what survives a tag fault, by catching it per task.
    The client must therefore raise, or the projection has nothing to catch
    and a tagging gap becomes silent instead of a warning record.
    """
    handler, captured = recording_handler(
        httpx.Response(401, json={"err": "Team not authorized", "ECODE": "OAUTH_017"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _add_tag(TASK_ID, GATE_TAG)

    # SPECIFIED precondition: the request was actually attempted, so the
    # failure traces to ClickUp's rejection and not to an earlier problem.
    assert len(captured) == 1


async def test_add_task_tag_when_clickup_is_unreachable_raises(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable -- the add-tag path.

    WHEN any of the client's requests cannot reach ClickUp at all (a
    connection failure or timeout, with no response received)
    THEN the caller receives an error and no result.

    The scenario is carried into the delta verbatim, but its requirement's
    enumeration now names a fifth operation, and "any of the client's
    requests" reaches it. The other four paths stay covered by the two
    existing files.
    """
    install_transport(
        monkeypatch, raising_handler(httpx.ConnectError("simulated ClickUp outage"))
    )

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _add_tag(TASK_ID, GATE_TAG)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether `add_task_tag` returns anything. The requirement states only
#   that the tag is added; the failure scenario says "no result", which
#   constrains the failing path and not the succeeding one.
# - The tag's colour or ordering. `design.md` puts both out of scope
#   ("ClickUp assigns colours, a member may change them, and the system
#   leaves them alone"), and no scenario states either.
# - "Authentication is configured independently of any one caller" over
#   `add_task_tag`. That requirement is unmodified by this delta and its
#   scenarios name "a task is created or updated"; the same reading
#   `test_clickup_client_list_and_read.py` already recorded for the two
#   operations it added.
# - Removing a tag from a task. The client is given no removal operation:
#   the projection never removes one, and `design.md` names the absence of
#   a removal path as a Non-Goal.
# ---------------------------------------------------------------------------
