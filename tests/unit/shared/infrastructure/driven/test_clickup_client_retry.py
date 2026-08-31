"""Bounded 429-retry-with-backoff on the shared ClickUp adapter.

Derived strictly from the delta spec of the OpenSpec change
`retry-clickup-rate-limits`:
`openspec/changes/retry-clickup-rate-limits/specs/clickup-task-client/spec.md`

Covers, from the ADDED requirement *A rate-limited request is retried before
it is surfaced* -- all six scenarios:

- A rate-limited request succeeds on retry
- A `Retry-After` header is honored
- No `Retry-After` header falls back to the client's own backoff
- An unparseable `Retry-After` header falls back to the client's own backoff
- A request exhausts its retry budget and still fails
- A non-429 failure is not retried

And, from the MODIFIED requirement *A failed ClickUp request is surfaced to
the caller*, new coverage for the requirement **as revised** ("a non-success
status other than `429`") across all eight operations it enumerates. That
revision is, word for word, the ADDED requirement's own "A non-429 failure is
not retried" scenario applied to every operation the failure requirement
names, so one parametrised test below (`test_a_non_429_failure_is_not_retried`)
serves both: it is new coverage derived from this change's own delta, and it
is also what makes each of the MODIFIED requirement's eight rejection
scenarios hold **as revised**, not merely as before.

## What this file does NOT (re)cover, and why that is not an omission

- The MODIFIED requirement's ninth scenario, *ClickUp is unreachable*, is
  carried into this delta **verbatim** -- its WHEN/THEN text is byte-for-byte
  identical to the predecessor spec (confirmed by diffing the delta against
  `openspec/specs/clickup-task-client/spec.md`). A connection failure carries
  no status code at all, so this change's 429-specific carve-out cannot touch
  it, and it is not revised behavior. It stays covered, untouched, by the
  `..._when_clickup_is_unreachable_raises` tests already in
  `test_clickup_client.py`, `test_clickup_client_list_and_read.py`,
  `test_clickup_client_list_state.py`, `test_clickup_client_tags.py` and
  `test_clickup_client_custom_fields.py`.
- The MODIFIED requirement's other eight rejection scenarios' pre-existing
  tests (using statuses 400/401/404/422/500) are untouched here and remain
  valid: none of them asserts anything this delta contradicts, since a
  non-429 status is unaffected. See `test-manifest.md` at this change's root
  for why none of them is superseded.
- "Authentication is configured independently of any one caller" is untouched
  by this delta and is not restated here, matching every sibling file's own
  reasoning for the operations it does not extend.

## What is fixed by this change's own artifacts, and what is INVENTED

Fixed by `tasks.md` (this change's own), so SPECIFIED/pinned for these tests:

- `create_task`, `update_task`, `create_list`, `list_tasks`,
  `read_list_state`, `add_task_tag`, `folder_fields`, `set_task_field` are
  the eight operations the retry behavior covers identically (tasks.md
  section 2 enumerates exactly these eight names).
- Up to 3 retries, 4 attempts total (`design.md` -- Decisions). The spec
  delta itself states only "a bounded number of attempts"; the number is
  DERIVED from design.md and asserted exactly, so tests below flag a budget
  that silently grew, shrank, or never terminated.
- A `Retry-After` wait is capped at 10 seconds per attempt, and the
  no-header fallback is a short exponential backoff (`design.md` --
  Decisions: "1s, 2s, 4s"). Also DERIVED, for the same reason.

INVENTED, and recorded in the manifest as an unresolved project question:

- **That the retry wait is issued via `asyncio.sleep(...)`, reached through
  the `asyncio` module attribute** (`design.md` -- Decisions: "Implemented
  with `asyncio.sleep` and a small loop"). `capture_sleep` below monkeypatches
  `asyncio.sleep` globally to record wait durations without any real delay
  (`tasks.md` 3.8). If the implementation calls a differently-imported alias
  (`from asyncio import sleep as _sleep`) that isn't reached by patching the
  module attribute, correcting the patch target is a fixture correction, not
  a change to what is asserted.
- `read_list_state`'s exact exported name. No artifact before this change
  pins one spelling over the others it could plausibly have landed as (see
  `test_clickup_client_list_state.py`'s own `_CANDIDATE_NAMES`); this
  change's own `tasks.md` 2.5 spells it `read_list_state`, which is included
  first among the candidates tried here, exactly as the sibling file does.
- The exact call shape (positional vs. keyword arguments) for each of the
  eight operations, copied from the shape each sibling test file already
  established for it.
- `create_task`'s trailing "Retry probe" copy passed as its `name`; no
  artifact fixes fixture task/list/field names, and none of this file's
  assertions turn on them.

## `pytest.raises(Exception)` is deliberate

As in every sibling file: no artifact names a specific exception type for any
of these scenarios (design.md's Risks section names `httpx.HTTPStatusError`
only as an expected *mechanism*, not a requirement). Each block is scoped to
the single call under test, per `ai-toolkit:testing`'s `pytest.raises`
scoping rule.

## At the time this pass was written, none of this behavior exists

`clickup_client.py` today, per `proposal.md`, "propagates every non-success
response immediately, with no distinction for a transient `429`" -- there is
no retry loop and no backoff at all. Every test below is expected to fail,
on first run, for one of two reasons: a `429` is surfaced immediately instead
of retried (a wrong value, not an absent target -- the eight operations and
`get_client()` already exist from earlier changes), or (for
`read_list_state`) the name-resolution helper fails outright if none of the
candidate names is exported. Per `ai-toolkit:testing`'s failure-state
taxonomy, a currently-passing test in this file would itself be the alarm
(state 4), not evidence of coverage.

Baseline recorded before these tests were written, at the worktree root:
`uv run pytest tests/unit tests/agents` -- 1727 passed, 0 failed.
`grep -rn "429" tests/` -- no hits anywhere in the existing suite, confirmed
by also reading every failure-scenario test in this module's five existing
files in full: none scripts a `429` response. See `test-manifest.md`'s
obsolete-tests section for what that establishes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Sequence
from typing import Any, Final

import httpx
import pytest

from commerce_ops.shared.infrastructure.driven import clickup_client
from commerce_ops.shared.infrastructure.driven.clickup_client import (
    add_task_tag,
    create_list,
    create_task,
    folder_fields,
    list_tasks,
    set_task_field,
    update_task,
)

pytestmark = pytest.mark.anyio

TOKEN: Final = "test-clickup-api-token-not-a-real-credential"

FOLDER_ID: Final = "90110042424"
LIST_ID: Final = "901234002"
TASK_ID: Final = "86a1b2c3d"
FIELD_ID: Final = "4bd1f0f9-6f2a-4f0e-9d5d-0f4a1c6b2e11"

# DERIVED from design.md's Decisions -- the spec delta itself states only
# "a bounded number of attempts" / "a fixed maximum wait", not these numbers.
MAX_ATTEMPTS: Final = 4  # "up to 3 retries (4 attempts total)"
MAX_WAIT_SECONDS: Final = 10  # Retry-After capped "at 10 seconds per attempt"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


# ---------------------------------------------------------------------------
# Fixtures / test doubles -- the seam every sibling file documents
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
        "`shared/infrastructure/driven/clickup_client.py` -- the seam every "
        "sibling test file already substitutes through"
    )
    monkeypatch.setattr(
        clickup_client,
        "get_client",
        lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture()
def capture_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Records every wait the retry loop issues, without any real delay.

    `tasks.md` 3.8: "Mock or monkeypatch the retry wait ... so the suite
    adds no real wall-clock delay." INVENTED patch target -- see the module
    docstring's "What is fixed ... and what is INVENTED" section.
    """
    durations: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        durations.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return durations


def sequenced_handler(
    responses: Sequence[httpx.Response],
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Serves `responses` one per request, in order, repeating the last one
    if more requests are made than were scripted -- so a script of
    `[429, 200]` answers the first attempt with `429` and every attempt
    after that with `200`, and a script of all-`429` never runs out."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        index = min(len(captured), len(responses) - 1)
        captured.append(request)
        return responses[index]

    return handler, captured


def recording_handler(
    response: httpx.Response,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return response

    return handler, captured


# ---------------------------------------------------------------------------
# The eight operations this capability's failure/retry requirements cover
# identically -- resolved and invoked the same way each sibling file already
# does for its own tests.
# ---------------------------------------------------------------------------

#: INVENTED spellings, in preference order -- see the module docstring.
#: `read_list_state` (this change's own `tasks.md` 2.5) is tried first.
_LIST_STATE_CANDIDATE_NAMES: Final = (
    "read_list_state",
    "get_list_state",
    "get_list",
    "read_list",
    "list_state",
)


def _list_state_operation() -> Callable[..., Awaitable[Any]]:
    for name in _LIST_STATE_CANDIDATE_NAMES:
        operation = getattr(clickup_client, name, None)
        if operation is not None:
            return operation  # type: ignore[no-any-return]
    pytest.fail(
        "`shared/infrastructure/driven/clickup_client.py` exports no read of "
        "a single list's own state under any of "
        f"{_LIST_STATE_CANDIDATE_NAMES}. If it exists under another name, add "
        "it to this list -- a fixture correction, not a change to what these "
        "tests assert."
    )


async def _call_create_task() -> Any:
    return await create_task(list_id=LIST_ID, name="Retry probe")


async def _call_update_task() -> Any:
    return await update_task(task_id=TASK_ID, fields={"status": "in progress"})


async def _call_create_list() -> Any:
    return await create_list(folder_id=FOLDER_ID, name="Retry probe list")


async def _call_list_tasks() -> Any:
    return await list_tasks(list_id=LIST_ID)


async def _call_read_list_state() -> Any:
    return await _list_state_operation()(list_id=LIST_ID)


async def _call_add_task_tag() -> Any:
    return await add_task_tag(TASK_ID, "gate:listable")


async def _call_folder_fields() -> Any:
    return await folder_fields(folder_id=FOLDER_ID)


async def _call_set_task_field() -> Any:
    return await set_task_field(task_id=TASK_ID, field_id=FIELD_ID, value="opt-1")


#: (operation name, invoker, a success body it can parse without erroring)
#: SPECIFIED which eight operations these are (tasks.md section 2); the
#: success bodies are DERIVED, following each sibling file's own fixtures.
OPERATIONS: Final[list[tuple[str, Callable[[], Awaitable[Any]], dict[str, Any]]]] = [
    (
        "create_task",
        _call_create_task,
        {"id": "9hz-retried", "url": "https://app.clickup.com/t/9hz-retried"},
    ),
    (
        "update_task",
        _call_update_task,
        {"id": TASK_ID, "url": f"https://app.clickup.com/t/{TASK_ID}"},
    ),
    ("create_list", _call_create_list, {"id": LIST_ID, "name": "Retry probe list"}),
    ("list_tasks", _call_list_tasks, {"tasks": [], "last_page": True}),
    ("read_list_state", _call_read_list_state, {"id": LIST_ID, "deleted": False}),
    ("add_task_tag", _call_add_task_tag, {}),
    ("folder_fields", _call_folder_fields, {"fields": [], "last_page": True}),
    ("set_task_field", _call_set_task_field, {}),
]

_OPERATION_IDS = [op[0] for op in OPERATIONS]

#: Two representative operations (one write, one read) for the Retry-After
#: timing scenarios -- see the module docstring's scoping note above
#: `test_a_retry_after_header_is_honored`.
_REPRESENTATIVE_OPERATIONS = [
    op for op in OPERATIONS if op[0] in {"create_task", "list_tasks"}
]
_REPRESENTATIVE_IDS = [op[0] for op in _REPRESENTATIVE_OPERATIONS]


def _rate_limited(headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        429, json={"err": "Rate limit reached"}, headers=headers or {}
    )


# ---------------------------------------------------------------------------
# Scenario: A rate-limited request succeeds on retry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "call", "success_body"), OPERATIONS, ids=_OPERATION_IDS
)
async def test_a_rate_limited_request_succeeds_on_retry(
    name: str,
    call: Callable[[], Awaitable[Any]],
    success_body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: A rate-limited request succeeds on retry.

    WHEN ClickUp responds to a request with 429 and then, on a subsequent
    attempt, with a success response
    THEN the caller receives the successful result, with no error raised for
    the intervening 429.

    "Every operation this capability offers is covered identically" (the
    ADDED requirement's own text) is why this is parametrised across all
    eight, rather than asserted once on a representative operation.
    """
    handler, captured = sequenced_handler(
        [_rate_limited(), httpx.Response(200, json=success_body)]
    )
    install_transport(monkeypatch, handler)

    # SPECIFIED: no error raised for the intervening 429 -- reaching this
    # line at all establishes that.
    await call()

    # SPECIFIED: the request was retried after the 429, and succeeded on the
    # next attempt.
    assert len(captured) == 2, (
        f"{name}: expected exactly one failed attempt and one retry that "
        f"succeeded, got {len(captured)} request(s)"
    )


# ---------------------------------------------------------------------------
# Scenario: A request exhausts its retry budget and still fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "call", "success_body"), OPERATIONS, ids=_OPERATION_IDS
)
async def test_a_request_exhausts_its_retry_budget_and_still_fails(
    name: str,
    call: Callable[[], Awaitable[Any]],
    success_body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: A request exhausts its retry budget and still fails.

    WHEN ClickUp responds with 429 on every attempt up to the retry budget
    THEN the caller receives an error and no result, exactly as for any
    other non-successful response.
    """
    handler, captured = sequenced_handler([_rate_limited()])
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await call()

    # DERIVED (design.md: "up to 3 retries (4 attempts total)"): asserted
    # exactly, so a budget that silently grew, shrank, or never terminated
    # both fail here -- the spec delta itself only requires "bounded".
    assert len(captured) == MAX_ATTEMPTS, (
        f"{name}: expected exactly {MAX_ATTEMPTS} attempt(s) against a "
        f"persistent 429, got {len(captured)}"
    )


# ---------------------------------------------------------------------------
# Scenario: A non-429 failure is not retried
#
# Also what makes the MODIFIED requirement's eight rejection scenarios hold
# AS REVISED ("... other than 429") -- see the module docstring.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "call", "success_body"), OPERATIONS, ids=_OPERATION_IDS
)
async def test_a_non_429_failure_is_not_retried(
    name: str,
    call: Callable[[], Awaitable[Any]],
    success_body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: A non-429 failure is not retried.

    WHEN ClickUp responds to a request with a non-success status other than
    429
    THEN the system does not retry, and the caller receives an error on the
    first attempt.

    This is also new coverage for each of the MODIFIED requirement's eight
    rejection scenarios ("ClickUp rejects a create request" and its seven
    siblings) as revised by this delta: their WHEN clause now reads "a
    non-success status other than 429", and this test asserts exactly that,
    over every operation the requirement enumerates.
    """
    handler, captured = recording_handler(
        httpx.Response(400, json={"err": "Rejected", "ECODE": "CAT_001"})
    )
    install_transport(monkeypatch, handler)

    with pytest.raises(Exception):  # noqa: B017 -- no type is specified; see docstring
        await call()

    # SPECIFIED: the system does not retry -- one attempt, not more.
    assert len(captured) == 1, (
        f"{name}: a non-429 failure was retried ({len(captured)} attempts "
        "made); only 429 is retried"
    )
    # SPECIFIED (by implication of "does not retry"): no wait was issued
    # either, since a wait is only ever a prelude to a retry that never
    # happens here.
    assert not capture_sleep, (
        f"{name}: a wait was issued for a non-429 failure ({capture_sleep!r})"
    )


# ---------------------------------------------------------------------------
# Scenario: A `Retry-After` header is honored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "call", "success_body"),
    _REPRESENTATIVE_OPERATIONS,
    ids=_REPRESENTATIVE_IDS,
)
async def test_a_retry_after_header_is_honored(
    name: str,
    call: Callable[[], Awaitable[Any]],
    success_body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: A `Retry-After` header is honored.

    WHEN ClickUp responds with 429 carrying a Retry-After header
    THEN the system waits at least that long, and no longer than the fixed
    maximum wait, before retrying.

    Tested on two representative operations (one write, `create_task`, one
    read, `list_tasks`) rather than all eight: this scenario and the two
    below exercise the shared wait/backoff mechanism design.md describes as
    one internal helper every operation routes through, not per-operation
    behavior -- unlike the retry-outcome scenarios above, which
    `test_a_rate_limited_request_succeeds_on_retry` and its siblings
    parametrise across all eight because the ADDED requirement's text makes
    that an explicit obligation ("a caller cannot tell them apart"). This
    scoping is recorded in the manifest as a deliberate choice, not a gap.
    """
    handler, _ = sequenced_handler(
        [
            _rate_limited(headers={"Retry-After": "3"}),
            httpx.Response(200, json=success_body),
        ]
    )
    install_transport(monkeypatch, handler)

    await call()

    assert capture_sleep, f"{name}: no wait was recorded before the retry"
    # SPECIFIED: waits at least that long ...
    assert capture_sleep[0] >= 3, (
        f"{name}: waited {capture_sleep[0]!r}s, less than the 3s Retry-After"
    )
    # DERIVED (design.md: capped "at 10 seconds") ... and no longer than the
    # fixed maximum wait.
    assert capture_sleep[0] <= MAX_WAIT_SECONDS


@pytest.mark.parametrize(
    ("name", "call", "success_body"),
    _REPRESENTATIVE_OPERATIONS,
    ids=_REPRESENTATIVE_IDS,
)
async def test_a_retry_after_header_larger_than_the_cap_is_capped(
    name: str,
    call: Callable[[], Awaitable[Any]],
    success_body: dict[str, Any],
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: A `Retry-After` header is honored -- the "no longer than the
    fixed maximum wait" half, specifically.

    A large Retry-After (600s) is scripted so this test can tell "happened
    to wait less than 600s" from "the cap was actually applied" -- the
    distinction the scenario's own second clause exists to state.
    """
    handler, _ = sequenced_handler(
        [
            _rate_limited(headers={"Retry-After": "600"}),
            httpx.Response(200, json=success_body),
        ]
    )
    install_transport(monkeypatch, handler)

    await call()

    assert capture_sleep, f"{name}: no wait was recorded before the retry"
    # SPECIFIED: no longer than the fixed maximum wait.
    assert capture_sleep[0] <= MAX_WAIT_SECONDS
    # DERIVED (design.md: the cap is exactly 10s): the cap actually took
    # effect, not merely "some value under 600" by coincidence.
    assert capture_sleep[0] == MAX_WAIT_SECONDS, (
        f"{name}: a 600s Retry-After produced a {capture_sleep[0]!r}s wait, "
        f"not the {MAX_WAIT_SECONDS}s cap"
    )


# ---------------------------------------------------------------------------
# Scenarios: No `Retry-After` header falls back to the client's own backoff /
# An unparseable `Retry-After` header falls back to the client's own backoff
# ---------------------------------------------------------------------------


async def test_no_retry_after_header_falls_back_to_the_clients_own_backoff(
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: No `Retry-After` header falls back to the client's own
    backoff.

    WHEN ClickUp responds with 429 carrying no Retry-After header
    THEN the system waits according to its own backoff before retrying.
    """
    handler, _ = sequenced_handler(
        [
            _rate_limited(),
            httpx.Response(
                200,
                json={
                    "id": "9hz-fallback",
                    "url": "https://app.clickup.com/t/9hz-fallback",
                },
            ),
        ]
    )
    install_transport(monkeypatch, handler)

    await create_task(list_id=LIST_ID, name="Retry probe (no header)")

    # SPECIFIED: the system waits according to its own backoff -- some
    # positive wait occurred, with no header to have driven it.
    assert capture_sleep, "no wait was recorded for a 429 with no Retry-After header"
    assert capture_sleep[0] > 0


async def test_an_unparseable_retry_after_header_falls_back_identically_to_no_header(
    configured_token: None,
    monkeypatch: pytest.MonkeyPatch,
    capture_sleep: list[float],
) -> None:
    """Scenario: An unparseable `Retry-After` header falls back to the
    client's own backoff.

    WHEN ClickUp responds with 429 carrying a Retry-After header that cannot
    be interpreted as a plain count of seconds
    THEN the system waits according to its own backoff before retrying,
    exactly as it does when the header is absent
    AND no error is raised for the unparseable header itself.

    Asserted as an equality against the no-header wait recorded in the same
    test (rather than against a hardcoded number) so this test states
    exactly what the scenario states -- "exactly as it does when the header
    is absent" -- without additionally pinning design.md's specific backoff
    value, which this scenario's own text does not name.
    """
    no_header_handler, _ = sequenced_handler(
        [
            _rate_limited(),
            httpx.Response(
                200,
                json={
                    "id": "9hz-no-header",
                    "url": "https://app.clickup.com/t/9hz-no-header",
                },
            ),
        ]
    )
    install_transport(monkeypatch, no_header_handler)
    await create_task(list_id=LIST_ID, name="Retry probe (no header, for comparison)")
    assert capture_sleep, "no wait was recorded for the no-header comparison call"
    no_header_wait = capture_sleep[0]
    capture_sleep.clear()

    unparseable_handler, _ = sequenced_handler(
        [
            _rate_limited(headers={"Retry-After": "N/A"}),
            httpx.Response(
                200,
                json={
                    "id": "9hz-unparseable",
                    "url": "https://app.clickup.com/t/9hz-unparseable",
                },
            ),
        ]
    )
    install_transport(monkeypatch, unparseable_handler)

    # SPECIFIED: no error is raised for the unparseable header itself --
    # reaching the assertions below at all establishes that.
    await create_task(list_id=LIST_ID, name="Retry probe (unparseable header)")

    assert capture_sleep, "no wait was recorded for the unparseable-header call"
    # SPECIFIED: falls back to the client's own backoff, "exactly as it does
    # when the header is absent."
    assert capture_sleep[0] == no_header_wait, (
        f"an unparseable Retry-After produced a {capture_sleep[0]!r}s wait, "
        f"which differs from the {no_header_wait!r}s wait used when the "
        "header is absent entirely"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The exact wait durations design.md pins for the no-header exponential
#   backoff (1s, 2s, 4s) across a multi-retry sequence. The two scenarios
#   above state the *fallback rule* ("its own backoff" / "exactly as ...
#   absent"), not a specific sequence of numbers; asserting that sequence
#   here would pin a design decision the spec delta itself leaves open,
#   beyond what "DERIVED, asserted where the spec is abstract" already does
#   for the attempt count and the Retry-After cap above.
# - What `add_task_tag` and `set_task_field` return on a retried success.
#   Every sibling file already records this as deliberately untested for
#   these two operations' ordinary (non-retried) path; retrying does not
#   change what either operation's own requirement commits to returning.
# ---------------------------------------------------------------------------
