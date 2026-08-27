"""Reading a list's *own* state from ClickUp, as distinct from its tasks.

Derived strictly from the delta spec of the OpenSpec change
`heal-a-launchs-deleted-list`:
`openspec/changes/heal-a-launchs-deleted-list/specs/clickup-task-client/spec.md`

Covers:

- ADDED *A list's own state can be read* — both scenarios (*A deleted list
  reports itself deleted*, *A live list reports itself not deleted*).
- MODIFIED *A failed ClickUp request is surfaced to the caller* — the one
  scenario the delta adds, *ClickUp rejects a read of a list's own state*,
  and *ClickUp is unreachable* on that same new path.

This file is additive. The MODIFIED requirement's other five scenarios are
carried into the delta **verbatim**; *ClickUp rejects a create request* and
*ClickUp rejects an update request* stay covered by
`tests/unit/shared/infrastructure/driven/test_clickup_client.py`, and
*ClickUp rejects a create-list request*, *ClickUp rejects a read of a
list's tasks* and the create-list/list-tasks halves of *ClickUp is
unreachable* stay covered by
`tests/unit/shared/infrastructure/driven/test_clickup_client_list_and_read.py`.
None of those is touched, duplicated or superseded here. See
`openspec/changes/heal-a-launchs-deleted-list/test-manifest.md` for the
full accounting.

## What this operation exists to discriminate

`design.md` measures that `list_tasks(list_id)` **cannot** tell a deleted
list from a live empty one: a deleted list answers that read successfully
and empty. So the two scenarios below are not a formality — the whole
point of the operation is that its answer differs where the task read's
does not. The live case is therefore scripted with *no tasks at all* in
mind: nothing about the tasks is consulted, and the assertion is on what
the list itself reports.

## Names and shapes used here: what is fixed, and what is INVENTED

Fixed by this change's `tasks.md` 1.1-1.2, so SPECIFIED for these tests:

- the operation lives on
  `shared/infrastructure/driven/clickup_client.py`, alongside
  `create_list` and `list_tasks`, and returns "whether ClickUp reports the
  list as deleted";
- a non-successful response and an unreachable ClickUp both propagate —
  "so a `404` is never returned as 'deleted'".

INVENTED, and recorded in the manifest as unresolved project questions:

- **The operation's name.** No artifact names it. `_read_list_state()`
  below resolves the first of several plausible spellings that the module
  actually exports, and fails with a message naming them all where none
  is present. That resolver is the single correction point for the name.
- **How the answer is carried** — an object with `.deleted`, a mapping
  with a `"deleted"` key, or a bare bool. `_deleted_flag()` accepts any of
  those and asserts on the *fact*, which is what the requirement states.
- **ClickUp's URL shape**, `GET /api/v2/list/{list_id}`, following the
  `/api/v2/...` convention `test_clickup_client.py` already pins. The
  scenarios say only that the state "of a list" is read; the path is how
  that is observed to name the right list.
- The `get_client()` cached factory used as the substitution seam, exactly
  as `test_clickup_client.py` documents it.

## `pytest.raises(Exception)` is deliberate

As in the two sibling client files: the requirement says only that the
caller "receives an error", and no artifact names a type. Each block is
scoped to the single call under test, per `ai-toolkit:testing`.

## At the time this pass was written, the operation does not exist

`clickup_client.py` has no read of a single list; `tasks.md` 1.1 adds it.
Every test here is expected to fail on an absent target — the resolver
below fails naming the spellings it looked for. Per `ai-toolkit:testing`
that failure establishes only absence, and nothing about whether these
assertions are well-formed.

Baseline recorded before these tests were written, at the worktree root:
`uv run pytest tests/unit tests/agents` — 1130 passed, 0 failed;
`uv run pytest tests/integration` — 3 passed, 94 skipped (no database is
configured here, so that tier's database-backed tests skip).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

# Both forms, deliberately: the `from` import is what binds the name used
# below, and the plain submodule import is what makes `mypy .` resolve it
# as an attribute of its package. The sibling
# `test_clickup_client_list_and_read.py` gets the second for free by also
# importing two names out of the module; this file imports none, because
# the operation it covers has no name yet.
import commerce_ops.shared.infrastructure.driven.clickup_client  # noqa: F401
from commerce_ops.shared.infrastructure.driven import clickup_client

pytestmark = pytest.mark.anyio

TOKEN = "test-clickup-api-token-not-a-real-credential"

# The list the production fault was observed on (`proposal.md` — Why):
# `GET /list/901220624358` answered `200` with `"deleted": true`.
DELETED_LIST_ID = "901220624358"
LIVE_LIST_ID = "901234002"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# The single correction point: how the new operation is named and read
# ---------------------------------------------------------------------------

#: Plausible spellings, in preference order. INVENTED — no artifact names
#: the operation. Adding the real one here (or renaming the implementation)
#: is a fixture correction, `ai-toolkit:testing` failure state 3.
_CANDIDATE_NAMES = (
    "get_list",
    "read_list",
    "get_list_state",
    "read_list_state",
    "list_state",
)


def _read_list_state() -> Any:
    """The client's read of a single list's own state, however it is named."""
    for name in _CANDIDATE_NAMES:
        operation = getattr(clickup_client, name, None)
        if operation is not None:
            return operation
    pytest.fail(
        "`shared/infrastructure/driven/clickup_client.py` exports no read of "
        "a single list's own state. `tasks.md` 1.1 adds one; none of the "
        f"spellings this test looked for is present: {_CANDIDATE_NAMES}. If "
        "the operation exists under another name, add it to "
        "`_CANDIDATE_NAMES` — that is a fixture correction, not a change to "
        "what these tests assert."
    )


def _deleted_flag(result: Any) -> bool:
    """Whether the result reports the list as deleted, however it is carried.

    The requirement states the *fact* the caller receives, not a shape:
    "returning at least whether ClickUp reports that list as deleted".
    """
    if isinstance(result, bool):
        return result
    if isinstance(result, dict):
        for key in ("deleted", "is_deleted"):
            if key in result:
                return bool(result[key])
    for attribute in ("deleted", "is_deleted"):
        value = getattr(result, attribute, None)
        if value is not None:
            return bool(value)
    pytest.fail(
        "the list-state read returned something that reports nothing about "
        f"deletion: {result!r}. The requirement obliges it to return at "
        "least whether ClickUp reports the list as deleted."
    )


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


# ---------------------------------------------------------------------------
# ADDED Requirement: A list's own state can be read
# ---------------------------------------------------------------------------


async def test_a_deleted_list_reports_itself_deleted(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A deleted list reports itself deleted.

    WHEN the state of a list ClickUp has deleted is read
    THEN the caller receives a result reporting the list as deleted.

    The scripted body is the one `proposal.md` records from the live API on
    2026-08-27 for list 901220624358: a `200` carrying `"deleted": true`.
    That the *status* is a success is load-bearing — Decision 4 turns on a
    deletion being ClickUp stating a fact, never a failed request.
    """
    response = httpx.Response(
        200,
        json={
            "id": DELETED_LIST_ID,
            "name": "TestProductName0 (TESTSKU0)",
            "deleted": True,
        },
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    result = await _read_list_state()(list_id=DELETED_LIST_ID)

    # SPECIFIED: the request is a read of *that* list. DERIVED: the method
    # and the `/api/v2/list/{id}` path shape (see the module docstring).
    assert len(captured) == 1, f"expected exactly one request, got {captured}"
    assert captured[0].method == "GET"
    assert DELETED_LIST_ID in captured[0].url.path

    # SPECIFIED: the caller receives a result reporting the list as deleted.
    assert _deleted_flag(result) is True


async def test_a_live_list_reports_itself_not_deleted(
    configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A live list reports itself not deleted.

    WHEN the state of a list ClickUp still holds is read
    THEN the caller receives a result reporting the list as not deleted.

    Scripted with `task_count` zero deliberately: the requirement's own
    reason for this operation existing is that "a list ClickUp reports as
    deleted still answers a read of its tasks, and answers it as empty".
    An empty live list is exactly the state the task read cannot tell from
    a deleted one, so this is where the two answers must differ.
    """
    response = httpx.Response(
        200,
        json={
            "id": LIVE_LIST_ID,
            "name": "Bamboo Cutting Board (BCB-2027-01)",
            "task_count": 0,
            "deleted": False,
        },
    )
    handler, captured = recording_handler(response)
    install_transport(monkeypatch, handler)

    result = await _read_list_state()(list_id=LIVE_LIST_ID)

    assert len(captured) == 1
    assert LIVE_LIST_ID in captured[0].url.path

    # SPECIFIED: a result reporting the list as *not* deleted.
    assert _deleted_flag(result) is False


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A failed ClickUp request is surfaced to the caller
#
# Only what this delta adds: the list-state read. The other four operations
# stay covered by test_clickup_client.py and
# test_clickup_client_list_and_read.py, untouched.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "body"),
    [
        pytest.param(
            404, {"err": "List not found", "ECODE": "CAT_001"}, id="not-found"
        ),
        pytest.param(
            401, {"err": "Team not authorized", "ECODE": "OAUTH_017"}, id="unauthorized"
        ),
        pytest.param(500, {"err": "Internal error"}, id="server-error"),
    ],
)
async def test_a_rejected_read_of_a_lists_own_state_raises(
    status: int,
    body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: ClickUp rejects a read of a list's own state.

    WHEN ClickUp responds to a request for a list's own state with a
    non-success status
    THEN the caller receives an error and no state.

    SPECIFIED: the error, and that no state reaches the caller. The `404`
    case is parametrised in alongside the others rather than left implicit
    because it is the one this change's `design.md` — Decision 4 settles
    explicitly: a `404` is "equally what a withdrawn permission or a
    mistaken identifier produces", so it must raise like any other
    non-success and must never be returned as a deletion. A client that
    answered `deleted=True` here would satisfy the healing scenarios by
    accident while healing lists nobody deleted.
    """
    handler, captured = recording_handler(httpx.Response(status, json=body))
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _read_list_state()(list_id=DELETED_LIST_ID)

    # SPECIFIED precondition: the request was actually attempted, so the
    # failure traces to ClickUp's rejection and not to an earlier problem.
    assert len(captured) == 1


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(httpx.ConnectError("simulated ClickUp outage"), id="connect"),
        pytest.param(httpx.TimeoutException("simulated ClickUp timeout"), id="timeout"),
    ],
)
async def test_reading_a_lists_state_when_clickup_is_unreachable_raises(
    failure: Exception, configured_token: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: ClickUp is unreachable (list-state path).

    WHEN any of the client's requests cannot reach ClickUp at all (a
    connection failure or timeout, with no response received)
    THEN the caller receives an error and no result.

    The revised requirement's enumeration now names this read, so the
    already-general "any of the client's requests" reaches it. The other
    four paths stay covered by the two sibling files.
    """
    install_transport(monkeypatch, raising_handler(failure))

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await _read_list_state()(list_id=LIVE_LIST_ID)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - A `200` response that carries no `deleted` key at all. ClickUp's own
#   behaviour for a live list was observed only through the *deleted* case
#   (`design.md` — Risks: "`"deleted": true` is a single observed ClickUp
#   behaviour"), and no scenario states what the absence of the key means.
#   Asserting a reading of it -- absent means live, or absent means
#   unanswerable -- would invent a wire contract nobody stated. Recorded
#   here so that if the implementation has to choose, the choice is visible
#   as a choice.
# - Whether the read asks ClickUp for anything beyond the list itself
#   (a folder listing, a space read). `design.md` — Decision 4 names the
#   folder-listing alternative as belonging to a *different* change, so
#   there is nothing here to forbid yet.
# - "Authentication is configured independently of any one caller" over
#   this new operation. That requirement is unmodified by this delta and
#   its scenarios name "a task is created or updated"; the same reasoning
#   `test_clickup_client_list_and_read.py` records for `create_list` and
#   `list_tasks` applies unchanged.
# ---------------------------------------------------------------------------
