"""`slack-trigger`: a request needing an absent credential is rejected.

Derived strictly from the delta specs at
`openspec/changes/migrate-slack-to-bolt/specs/slack-trigger/spec.md`, without
reading the implementation. Scenarios covered here, all from the ADDED
requirement "A Request That Cannot Be Handled With Available Credentials Is
Rejected":

- Scenario: The signing secret is absent or empty
- Scenario: The credential needed to reply is absent or empty
- Scenario: A request needing no reply credential is unaffected
- Scenario: An event that is only acknowledged is unaffected
- Scenario: An event that is deliberately not answered is unaffected

The last three are what stop this requirement contradicting two others in the
same delta, so each is asserted rather than inferred from another. The seven
cases below reach their outcomes by different routes -- the secret's absence
via the adapter's own `KeyError` catch, its emptiness via Bolt's request
verification, the token's absence or emptiness via the `before_authorize`
middleware (design.md, Verified Finding 9) -- which is why they are seven
named tests rather than one parametrized sweep.

Each case starts from a cold Bolt-app cache (`tasks.md` 2.6a and 7.8). Without
that, a case that changes the environment would observe an app built from the
previous case's environment and pass vacuously; `_require_cold_cache` refuses
to let that happen silently.

`raise_server_exceptions=False` is used throughout on purpose. The requirement
forbids a server-error response as explicitly as it forbids an acknowledgement,
and with the default client a 500 would be re-raised into the test as the
underlying exception rather than observed as the response Slack would see.

Level and seams: as in `test_slack_event_dispatch_under_bolt.py`.
"""

from __future__ import annotations

import importlib
import inspect
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.omni_agent.infrastructure.driving import slack as slack_adapter

SLACK_EVENTS_PATH = "/omni_agent/slack/events"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-not-a-real-token"  # not a real credential
BOT_ID = "U0BOTID"
CHANNEL = "C0FFEECHANNEL"

SIGNING_SECRET_VAR = "OMNI_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "OMNI_AGENT_SLACK_BOT_TOKEN"

FORBIDDEN_GENERIC_ENV_VARS = ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET")

_MODULES_WITH_CACHED_FACTORIES = (
    "commerce_ops.omni_agent.infrastructure.driving.slack",
    "commerce_ops.shared.infrastructure.driving.slack_app",
)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _FakeSlackResponse(dict[str, Any]):
    """Minimal stand-in for `AsyncSlackResponse`, which is dict-like."""

    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class _RecordingSlackApi:
    """Records every Slack Web API method the app calls, in call order."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def methods(self) -> list[str]:
        return [call["api_method"] for call in self.calls]

    @property
    def posts(self) -> list[dict[str, Any]]:
        return [
            call["payload"]
            for call in self.calls
            if call["api_method"] == "chat.postMessage"
        ]

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        self.calls.append(
            {
                "api_method": api_method,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )
        return _FakeSlackResponse({"ok": True})


class _RecordingAnswerQuestion:
    """Stands in for `omni_agent.application.answer_question` (a coroutine)."""

    def __init__(self, answer: str = "Paris is the capital of France.") -> None:
        self.answer = answer
        self.calls: list[str] = []

    async def __call__(self, question: str) -> str:
        self.calls.append(question)
        return self.answer


# --------------------------------------------------------------------------
# Cache-reset discovery (tasks.md 2.6a)
# --------------------------------------------------------------------------


def _looks_like_a_reset_hook(value: Any) -> bool:
    if not callable(value):
        return False
    name = getattr(value, "__name__", "")
    if not name.startswith(("reset_", "clear_")):
        return False
    try:
        signature = inspect.signature(value)
    except (TypeError, ValueError):
        return False
    return all(
        parameter.default is not inspect.Parameter.empty
        or parameter.kind
        in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for parameter in signature.parameters.values()
    )


def _reset_slack_caches() -> int:
    reset = 0
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        module = importlib.import_module(module_name)
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
                reset += 1
            elif _looks_like_a_reset_hook(value):
                value()
                reset += 1
    return reset


def _require_cold_cache() -> None:
    """Refuses to proceed unless a cached Bolt app was actually discarded."""
    assert _reset_slack_caches(), (
        "no cache-reset seam was found on the Slack app factory. tasks.md 2.6a"
        " requires the cached factory to expose one; without it this test "
        "could observe an app built from an earlier environment state and pass"
        " for a reason that has nothing to do with what it asserts"
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The healthy baseline each test below then breaks in exactly one way."""
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    for name in FORBIDDEN_GENERIC_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    _reset_slack_caches()
    yield
    _reset_slack_caches()


@pytest.fixture()
def slack_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingSlackApi:
    async_client = importlib.import_module("slack_sdk.web.async_client")
    recorder = _RecordingSlackApi()
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", recorder.api_call)
    return recorder


@pytest.fixture()
def answer_question(monkeypatch: pytest.MonkeyPatch) -> _RecordingAnswerQuestion:
    fake = _RecordingAnswerQuestion()
    monkeypatch.setattr(slack_adapter, "answer_question", fake)
    return fake


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    # See the module docstring: a 500 must be observable as a response, since
    # the requirement forbids one as explicitly as it forbids a 2xx.
    #
    # `slack_asgi_app` (conftest.py) rather than `app`: every assertion here
    # that omni-agent was NOT invoked is only worth making once whatever the
    # request scheduled has actually run.
    with TestClient(slack_asgi_app, raise_server_exceptions=False) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------


def _signed_headers(body: bytes) -> dict[str, str]:
    stamp = str(int(time.time()))
    signature = SignatureVerifier(SIGNING_SECRET).generate_signature(
        timestamp=stamp, body=body
    )
    assert signature is not None
    return {
        "Content-Type": "application/json",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _post(client: TestClient, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(SLACK_EVENTS_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    """Lets work Bolt scheduled run before an assertion about what it did."""
    client.get("/health")


def _app_mention_payload(
    *,
    text: str = f"<@{BOT_ID}> what is the capital of France?",
    user: str | None = "U0MEMBER",
    channel: str = CHANNEL,
    bot_id: str | None = None,
    subtype: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": "app_mention",
        "text": text,
        "ts": "1700000000.000100",
        "channel": channel,
        "event_ts": "1700000000.000100",
    }
    if user is not None:
        event["user"] = user
    if bot_id is not None:
        event["bot_id"] = bot_id
    if subtype is not None:
        event["subtype"] = subtype
    return {
        "type": "event_callback",
        "token": "verification-token",
        "team_id": "T0TEAM",
        "api_app_id": "A0APP",
        "event_id": "Ev0EVENT",
        "event_time": 1700000000,
        "event": event,
    }


def _unhandled_event_payload() -> dict[str, Any]:
    """An authentic `event_callback` of a type nothing subscribes to.

    DERIVED: `reaction_added` is a stand-in; the requirement names no
    particular type and only `app_mention` is subscribed today.
    """
    return {
        "type": "event_callback",
        "token": "verification-token",
        "team_id": "T0TEAM",
        "api_app_id": "A0APP",
        "event_id": "Ev0UNHANDLED",
        "event_time": 1700000000,
        "event": {
            "type": "reaction_added",
            "user": "U0MEMBER",
            "reaction": "tada",
            "item": {"type": "message", "channel": CHANNEL, "ts": "1700000000.000200"},
            "event_ts": "1700000000.000300",
        },
    }


def _challenge_payload(challenge: str) -> dict[str, Any]:
    return {
        "type": "url_verification",
        "token": "verification-token",
        "challenge": challenge,
    }


def _assert_unauthorized(response: Any, *, because: str) -> None:
    """Asserts the response is 401, naming both forbidden alternatives.

    The requirement rules out an acknowledgement and a server error by name,
    so a bare status comparison would lose most of what it is asserting when
    it fails.
    """
    assert response.status_code == 401, (
        f"{because}: expected 401, got {response.status_code}. The requirement"
        " forbids both alternatives explicitly -- a 2xx would tell Slack the "
        "work is done when nothing was delivered, and a 5xx is what returning"
        " None or raising inside `authorize` produces (design.md, Verified "
        "Finding 9); the response must be emitted by a `before_authorize` "
        "middleware, ahead of authorization"
    )


# --------------------------------------------------------------------------
# Scenario: The signing secret is absent or empty
# --------------------------------------------------------------------------


def test_request_is_rejected_when_the_signing_secret_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: The signing secret is absent or empty (absent half).

    WHEN an inbound request arrives and the signing secret needed to verify it
    is absent or empty
    THEN the system SHALL respond as unauthorized
    AND SHALL NOT invoke omni-agent.

    Absence and emptiness are separate tests because they are reached by
    different routes: absence raises `KeyError` at the adapter's own
    environment read, which the adapter catches; emptiness builds an app whose
    verification then fails inside Bolt (design.md).
    """
    monkeypatch.delenv(SIGNING_SECRET_VAR, raising=False)
    _require_cold_cache()

    response = _post(client, _app_mention_payload())
    _drain(client)

    _assert_unauthorized(
        response, because="the signing secret needed to verify the request is absent"
    )
    # Specified: omni-agent is not invoked.
    assert answer_question.calls == []
    # Derived: an unverifiable request produces no channel traffic either.
    assert slack_api.posts == []


def test_request_is_rejected_when_the_signing_secret_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: The signing secret is absent or empty (empty half).

    WHEN an inbound request arrives and the signing secret needed to verify it
    is absent or empty
    THEN the system SHALL respond as unauthorized
    AND SHALL NOT invoke omni-agent.
    """
    monkeypatch.setenv(SIGNING_SECRET_VAR, "")
    _require_cold_cache()

    response = _post(client, _app_mention_payload())
    _drain(client)

    _assert_unauthorized(response, because="the signing secret is present but empty")
    assert answer_question.calls == []
    assert slack_api.posts == []


# --------------------------------------------------------------------------
# Scenario: The credential needed to reply is absent or empty
# --------------------------------------------------------------------------


def test_member_authored_mention_is_rejected_when_the_bot_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: The credential needed to reply is absent or empty (absent).

    WHEN an authentic member-authored `app_mention` arrives and the token
    needed to post a reply is absent, or present but empty
    THEN the system SHALL respond as unauthorized rather than acknowledging an
    event it cannot answer.

    This is a genuine behaviour difference from the adapter being replaced,
    which acknowledges first and then fails silently inside a background task
    (proposal.md), so an absent token produced a 200 and silence.
    """
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _require_cold_cache()

    response = _post(client, _app_mention_payload())
    _drain(client)

    _assert_unauthorized(
        response, because="the token needed to post the reply is absent"
    )
    # Derived: rejecting rather than acknowledging means the event is not
    # processed -- an acknowledged-then-dropped mention is the outcome this
    # scenario exists to prevent.
    assert answer_question.calls == []
    assert slack_api.posts == []


def test_member_authored_mention_is_rejected_when_the_bot_token_is_empty(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: The credential needed to reply is absent or empty (empty).

    WHEN an authentic member-authored `app_mention` arrives and the token
    needed to post a reply is absent, or present but empty
    THEN the system SHALL respond as unauthorized rather than acknowledging an
    event it cannot answer.

    The empty half is asserted separately because it is the half a single
    truthiness check covers only by accident -- the requirement covers absence
    and emptiness together, deliberately.
    """
    monkeypatch.setenv(BOT_TOKEN_VAR, "")
    _require_cold_cache()

    response = _post(client, _app_mention_payload())
    _drain(client)

    _assert_unauthorized(
        response, because="the token needed to post the reply is present but empty"
    )
    assert answer_question.calls == []
    assert slack_api.posts == []


# --------------------------------------------------------------------------
# Scenario: A request needing no reply credential is unaffected
# --------------------------------------------------------------------------


def test_url_verification_challenge_is_answered_when_the_bot_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: A request needing no reply credential is unaffected.

    WHEN a `url_verification` challenge arrives while the token needed to post
    a reply is absent
    THEN the system SHALL answer the challenge normally, since answering it
    requires no such token.

    Also covers the pre-existing requirement "Endpoint Responds to Slack's URL
    Verification Challenge" under this condition: without this carve-out, any
    token rotation would take the challenge down with it.
    """
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _require_cold_cache()
    challenge = "3eZbrw1aB1cCcQ2S1nZ7jHqWvXyZ0challenge"

    response = _post(client, _challenge_payload(challenge))

    # Specified: the challenge is answered normally, not rejected.
    assert response.status_code != 401, (
        "a url_verification challenge was rejected for lack of a reply token "
        "it never needed; the before_authorize middleware must pass it "
        "through, because Bolt's own AsyncUrlVerification runs *after* "
        "authorization (design.md, Verified Finding 9)"
    )
    assert response.status_code == 200
    # Specified by "Endpoint Responds to Slack's URL Verification Challenge":
    # the same challenge value comes back.
    assert challenge in response.text
    assert response.json()["challenge"] == challenge

    # Derived: a handshake is not an event, so nothing downstream runs.
    assert answer_question.calls == []
    assert slack_api.posts == []


# --------------------------------------------------------------------------
# Scenario: An event that is only acknowledged is unaffected
# --------------------------------------------------------------------------


def test_unhandled_event_is_acknowledged_when_the_bot_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: An event that is only acknowledged is unaffected.

    WHEN an authentic `event_callback` whose event type has no registered
    handler arrives while the token needed to post a reply is absent
    THEN the system SHALL acknowledge it with a success status, as "An Event
    With No Registered Handler Is Still Acknowledged" requires
    AND SHALL NOT reject it, since acknowledging it requires no such token.

    This is one of the two cases that stop this requirement contradicting
    another in the same delta, so it is asserted directly rather than inferred
    from the unhandled-event tests, which run with the token present.
    """
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _require_cold_cache()

    response = _post(client, _unhandled_event_payload())
    _drain(client)

    # Specified: not rejected.
    assert response.status_code != 401, (
        "an event that was only ever going to be acknowledged was rejected "
        "for lack of a reply token; the reply credential must be required "
        "exactly when the module's will_reply predicate is true (tasks.md "
        "2.2b(ii)), and rejecting here would also make Slack retry an event "
        "nothing was going to answer"
    )
    # Specified: acknowledged with a success status.
    assert 200 <= response.status_code < 300, (
        f"expected a success status, got {response.status_code}"
    )
    assert answer_question.calls == []
    assert slack_api.posts == []


# --------------------------------------------------------------------------
# Scenario: An event that is deliberately not answered is unaffected
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bot_id", "subtype", "user"),
    [
        pytest.param("B0OTHERBOT", None, "U0BOTUSER", id="carries-bot-id"),
        pytest.param(None, "bot_message", None, id="carries-bot-message-subtype"),
    ],
)
def test_bot_authored_mention_is_acknowledged_when_the_bot_token_is_absent(
    bot_id: str | None,
    subtype: str | None,
    user: str | None,
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    answer_question: _RecordingAnswerQuestion,
) -> None:
    """Scenario: An event that is deliberately not answered is unaffected.

    WHEN an authentic bot-authored `app_mention` arrives while the token
    needed to post a reply is absent
    THEN the system SHALL acknowledge it with a success status, as
    "Bot-Authored Events Do Not Trigger A Reply" requires
    AND SHALL NOT reject it, since the system was never going to reply to it.

    Parametrized over both authorship signals because the predicate deciding
    whether a reply is owed must recognise the same two the listener guard
    does -- design.md accepts that duplication explicitly, and a drift between
    the two layers would show up here as a 401.
    """
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _require_cold_cache()

    response = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> are you there?",
            user=user,
            bot_id=bot_id,
            subtype=subtype,
        ),
    )
    _drain(client)

    # Specified: not rejected.
    assert response.status_code != 401, (
        "a bot-authored mention was rejected for lack of a reply token the "
        "system was never going to use; the will_reply predicate and the "
        "listener guard must agree on what counts as bot-authored (design.md)"
    )
    # Specified: acknowledged with a success status.
    assert 200 <= response.status_code < 300, (
        f"expected a success status, got {response.status_code}"
    )
    # Specified by "Bot-Authored Events Do Not Trigger A Reply", restated here
    # because this scenario's premise is that no reply was ever owed.
    assert answer_question.calls == []
    assert slack_api.posts == []
