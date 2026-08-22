"""Event-dispatch behaviour `slack-trigger` gains under `migrate-slack-to-bolt`.

Derived strictly from the delta specs at
`openspec/changes/migrate-slack-to-bolt/specs/slack-trigger/spec.md`, without
reading the implementation. Scenarios covered here:

- ADDED "An Event With No Registered Handler Is Still Acknowledged"
  / Scenario: An event type with no handler is acknowledged
  / Scenario: A handled event type still reaches its handler
- ADDED "Bot-Authored Events Do Not Trigger A Reply"
  / Scenario: A bot-authored mention receives no reply
  / Scenario: A person's mention is unaffected by the bot-authorship check
- MODIFIED "Slack App Mention Triggers Omni"
  / Scenario: Mention receives an answer in the same channel (narrowed to a
    person-authored mention)
- MODIFIED "No Sender Identity Restriction (Deferred)"
  / Scenario: Any member in the channel can trigger Omni
  / Scenario: No member is privileged over another

One further test in this file covers no scenario at all: the `@app.error`
logging guard of `tasks.md` 7.11 / 2.4a. It is marked DERIVED FROM TASKS
below and is recorded as such in `test-manifest.md`.

Level: the endpoint, through `TestClient`. Every scenario here is about what
the system answers Slack and what reaches (or does not reach) omni-agent, and
neither is observable below the HTTP boundary.

Seams, all fixed by the change's own artifacts rather than invented here:

- `slack_adapter.answer_question` -- the use-case seam the existing endpoint
  tests already substitute through, and which `tasks.md` section 6 leaves in
  place (only its double's sync/async shape changes). It is a coroutine after
  this change, so the double here is awaitable.
- `slack_sdk.web.async_client.AsyncWebClient.api_call` -- every Slack Web API
  call funnels through it (`auth_test` and `chat_postMessage` both do), so
  patching it both records what was called and guarantees this tier makes no
  outbound Slack call, as `AGENTS.md`'s testing strategy requires. Patching
  `app.client` would NOT do: design.md's Verified Finding 6 records that Bolt
  builds the injected client from the `AuthorizeResult`, so the injected one
  would stay real and attempt live HTTP.
- The cached Bolt-app factory's reset seam (`tasks.md` 2.6a). Its name is not
  pinned anywhere, so it is discovered rather than named -- see
  `_reset_slack_caches` and `test-manifest.md`'s unresolved project questions.
"""

from __future__ import annotations

import importlib
import inspect
import json
import logging
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.main import app
from commerce_ops.omni_agent.infrastructure.driving import slack as slack_adapter

SLACK_EVENTS_PATH = "/omni_agent/slack/events"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-not-a-real-token"  # not a real credential
BOT_ID = "U0BOTID"
CHANNEL = "C0FFEECHANNEL"

# The generic names design.md's Verified Finding 7 records as forbidden in the
# runtime: Bolt's constructor falls back to both, and an ambient
# `SLACK_BOT_TOKEN` would silently restore the `auth.test` call. Cleared here so
# that no developer's ambient shell can make these tests pass for a reason the
# deployment does not share.
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
    """Records every Slack Web API method the app calls, in call order.

    Substituted for `AsyncWebClient.api_call`, the single funnel every Slack
    Web API method goes through, so this records the answer post *and* any
    identity call an implementation makes on the way to it.
    """

    def __init__(self, failure: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.failure = failure

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
        if self.failure is not None:
            raise self.failure
        if api_method == "auth.test":
            # Shaped like a real `auth.test` result on purpose: an
            # implementation that wrongly makes this call should fail on the
            # assertion that says so, not on a downstream KeyError.
            return _FakeSlackResponse(
                {
                    "ok": True,
                    "url": "https://example.slack.com/",
                    "team": "test-team",
                    "user": "test-bot",
                    "team_id": "T0TEAM",
                    "user_id": "U0BOTUSERID",
                    "bot_id": "B0BOTID",
                }
            )
        return _FakeSlackResponse({"ok": True})


class _RecordingAnswerQuestion:
    """Stands in for `omni_agent.application.answer_question`.

    A coroutine after this change (tasks.md 4.1), so `__call__` is `async def`.
    """

    def __init__(
        self,
        answer: str = "Paris is the capital of France.",
        failure: Exception | None = None,
    ) -> None:
        self.answer = answer
        self.failure = failure
        self.calls: list[str] = []

    async def __call__(self, question: str) -> str:
        self.calls.append(question)
        if self.failure is not None:
            raise self.failure
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
    """Drops whatever the lazily-cached Bolt-app factories memoised.

    `tasks.md` 2.6a requires a reset seam but pins no name for it, so the seam
    is discovered: anything exposing `cache_clear()` (an `lru_cache`-wrapped
    factory) or named `reset_*`/`clear_*` and callable with no arguments.
    Returns how many seams were reset, so a caller that depends on a cold
    cache can refuse to run vacuously.
    """
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


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ambient environment the adapter reads its credentials from."""
    monkeypatch.setenv("OMNI_AGENT_SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("OMNI_AGENT_SLACK_BOT_TOKEN", BOT_TOKEN)
    for name in FORBIDDEN_GENERIC_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    _reset_slack_caches()
    yield
    _reset_slack_caches()


@pytest.fixture()
def slack_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingSlackApi:
    """Records outbound Slack Web API calls and makes them non-networked."""
    async_client = importlib.import_module("slack_sdk.web.async_client")
    recorder = _RecordingSlackApi()
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", recorder.api_call)
    return recorder


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def install_answer_question(
    monkeypatch: pytest.MonkeyPatch, fake: _RecordingAnswerQuestion
) -> _RecordingAnswerQuestion:
    """Points the adapter's call to `answer_question` at the double.

    The adapter imports the name into its own module namespace, so that
    binding is what gets patched -- the same seam the existing endpoint tests
    use, which `tasks.md` section 6 leaves in place.
    """
    monkeypatch.setattr(slack_adapter, "answer_question", fake)
    return fake


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
    """Gives work Bolt scheduled a chance to run before a negative assertion.

    Bolt schedules its listener as an asyncio task during dispatch rather than
    awaiting it (design.md, Verified Finding 3), so "nothing was posted"
    asserted the instant `client.post(...)` returns could hold because the
    listener has not run *yet* rather than because it ran and declined to act
    -- a silent pass. A further round-trip through the same client forces the
    loop to make progress first.

    This is a best-effort barrier, not a proof. Where a positive control is
    available, the test below sequences one after the event under test and
    asserts on that instead, which is what actually makes the negative
    non-vacuous.
    """
    client.get("/health")


def _app_mention_payload(
    *,
    text: str = f"<@{BOT_ID}> what is the capital of France?",
    user: str | None = "U0MEMBER",
    channel: str = CHANNEL,
    bot_id: str | None = None,
    subtype: str | None = None,
    event_id: str = "Ev0EVENT",
) -> dict[str, Any]:
    """A minimal but realistically shaped Slack `app_mention` envelope."""
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
        "event_id": event_id,
        "event_time": 1700000000,
        "event": event,
    }


def _unhandled_event_payload() -> dict[str, Any]:
    """An authentic `event_callback` of a type nothing subscribes to.

    DERIVED: `reaction_added` is a stand-in. The requirement says "whose event
    type has no registered handler" and names none, and only `app_mention` is
    subscribed today (proposal.md), so any other type serves. What is asserted
    is the response to an unhandled type, never this particular type.
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


# --------------------------------------------------------------------------
# Requirement: An Event With No Registered Handler Is Still Acknowledged
# --------------------------------------------------------------------------


def test_event_type_with_no_handler_is_acknowledged(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An event type with no handler is acknowledged.

    WHEN Slack delivers an authentic `event_callback` whose event type has no
    registered handler
    THEN the system SHALL respond with a success status
    AND SHALL NOT invoke omni-agent.
    """
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion())

    response = _post(client, _unhandled_event_payload())

    # Specified: a success status, so Slack does not treat the delivery as
    # failed and retry it. Bolt's own default here is 404, which is what this
    # requirement exists to displace.
    assert 200 <= response.status_code < 300, (
        "an authentic event with no registered handler must be acknowledged "
        f"with a success status, got {response.status_code}; Bolt's default "
        "404 would make Slack retry a delivery nothing was ever going to "
        "answer"
    )

    _drain(client)

    # Specified: omni-agent is not invoked.
    assert fake.calls == []
    # Derived: an event nothing handles produces no channel traffic either.
    assert slack_api.posts == []


def test_handled_event_type_still_reaches_its_handler(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A handled event type still reaches its handler.

    WHEN Slack delivers an authentic `app_mention`, for which a handler is
    registered
    THEN that handler SHALL run, rather than the event being absorbed by the
    acknowledgement of unhandled events.

    The unhandled event is delivered first, deliberately: it puts the
    unhandled-request acknowledgement in play before the mention arrives, so
    an implementation that absorbed everything would be caught here rather
    than only in a hand-inspection of listener registration order. It also
    makes the preceding test's negative assertions non-vacuous -- by the time
    the mention's own post is observable, the loop has run past the point at
    which the unhandled event's work would have been scheduled.
    """
    answer = "Paris is the capital of France."
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion(answer=answer))
    question = "what is the capital of France?"

    unhandled = _post(client, _unhandled_event_payload())
    mention = _post(client, _app_mention_payload(text=f"<@{BOT_ID}> {question}"))

    assert 200 <= unhandled.status_code < 300
    assert 200 <= mention.status_code < 300

    # Specified: the registered handler ran -- exactly once, for the mention
    # and not for the unhandled event.
    assert len(fake.calls) == 1, (
        "expected the `app_mention` handler to run exactly once; the "
        "unhandled-request acknowledgement must not shadow a registered "
        f"listener (observed invocations: {fake.calls})"
    )
    assert fake.calls[0].strip() == question
    assert len(slack_api.posts) == 1
    assert slack_api.posts[0]["channel"] == CHANNEL


# --------------------------------------------------------------------------
# Requirement: Bot-Authored Events Do Not Trigger A Reply
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bot_id", "subtype", "user"),
    [
        pytest.param("B0OTHERBOT", None, "U0BOTUSER", id="carries-bot-id"),
        pytest.param(None, "bot_message", None, id="carries-bot-message-subtype"),
        pytest.param("B0OTHERBOT", "bot_message", None, id="carries-both"),
    ],
)
def test_bot_authored_mention_is_acknowledged_and_receives_no_reply(
    bot_id: str | None,
    subtype: str | None,
    user: str | None,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A bot-authored mention receives no reply.

    WHEN an authentic `app_mention` carrying a `bot_id`, or a bot-authored
    `subtype`, is delivered
    THEN the system SHALL acknowledge it with a success status
    AND SHALL NOT invoke omni-agent
    AND SHALL NOT post any message to the originating channel.

    The `user` field is never the bot's own configured identity in any of
    these cases, and in two of them is absent entirely: the requirement keys
    on how the message was authored, so `bot_id`/`subtype` must be the only
    signal an implementation can be passing on. An implementation that
    suppressed by sender identity instead would fail these.
    """
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion())

    response = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> are you there?",
            user=user,
            bot_id=bot_id,
            subtype=subtype,
        ),
    )

    # Specified: acknowledged with a success status, so Slack does not retry.
    assert 200 <= response.status_code < 300, (
        "a bot-authored mention must still be acknowledged so Slack does not "
        f"retry it, got {response.status_code}"
    )

    _drain(client)

    # Specified: omni-agent is not invoked.
    assert fake.calls == [], (
        "a bot-authored mention reached omni-agent; with Bolt's own self-event"
        " filter disabled by the fixed AuthorizeResult (design.md, Verified "
        "Finding 4), this guard is the only thing preventing a reply loop"
    )
    # Specified: nothing is posted to the originating channel.
    assert slack_api.posts == []


def test_person_authored_mention_is_unaffected_by_the_bot_authorship_check(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A person's mention is unaffected by the bot-authorship check.

    WHEN an authentic `app_mention` authored by a person, carrying no `bot_id`
    and no bot-authored `subtype`, is delivered
    THEN the system SHALL process it normally and post omni-agent's answer to
    the originating channel.

    A bot-authored mention is delivered first so this doubles as the positive
    control for the test above: the suppressed event is dispatched before the
    one whose post is observed, so if the guard were letting bot-authored
    mentions through, two invocations and two posts would be visible here.
    """
    answer = "Yes, I am here."
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion(answer=answer))
    question = "are you there?"

    suppressed = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> {question}",
            user=None,
            bot_id="B0OTHERBOT",
            subtype="bot_message",
            event_id="Ev0BOTAUTHORED",
        ),
    )
    person = _post(client, _app_mention_payload(text=f"<@{BOT_ID}> {question}"))

    assert 200 <= suppressed.status_code < 300
    assert 200 <= person.status_code < 300

    # Specified: the person's mention is processed normally.
    assert len(fake.calls) == 1, (
        "expected exactly one invocation -- the person's. More than one means "
        "the bot-authored mention was answered too; none means the guard is "
        f"over-broad and suppressed a person's mention (observed: {fake.calls})"
    )
    assert fake.calls[0].strip() == question

    # Specified: omni-agent's answer is posted to the originating channel.
    assert len(slack_api.posts) == 1
    posted = slack_api.posts[0]
    assert posted["channel"] == CHANNEL
    # Derived: containment rather than equality, so an implementation adding
    # surrounding formatting is not failed for it. What is specified is that
    # the generated answer reaches the channel.
    assert answer in (posted.get("text") or "")


# --------------------------------------------------------------------------
# Requirement: Slack App Mention Triggers Omni (MODIFIED)
# --------------------------------------------------------------------------


def test_person_mention_receives_an_answer_in_the_same_channel(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Mention receives an answer in the same channel.

    WHEN a person `@mentions` the bot in a Slack channel with a question
    THEN the system SHALL post omni-agent's generated answer as a message in
    that same channel.

    The requirement is narrowed by this change to person-authored mentions, so
    the payload carries neither `bot_id` nor a bot-authored `subtype`. This
    asserts the same postconditions as the pre-existing endpoint test of the
    unnarrowed requirement, at the seam Bolt actually uses to post
    (design.md, Verified Finding 6).
    """
    answer = "Paris is the capital of France."
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion(answer=answer))
    question = "what is the capital of France?"

    response = _post(
        client, _app_mention_payload(text=f"<@{BOT_ID}> {question}", channel=CHANNEL)
    )

    assert 200 <= response.status_code < 300

    # Specified: omni-agent is invoked with the text of the mention as the
    # question, with the bot-mention token stripped.
    assert len(fake.calls) == 1
    asked = fake.calls[0]
    assert "<@" not in asked, (
        f"the bot-mention token was not stripped from the question: {asked!r}"
    )
    assert asked.strip() == question

    # Specified: the answer is posted back to that same channel.
    assert len(slack_api.posts) == 1, (
        "expected exactly one message posted back to Slack, observed "
        f"{slack_api.methods}"
    )
    posted = slack_api.posts[0]
    assert posted["channel"] == CHANNEL
    # Derived: containment, for the reason given above.
    assert answer in (posted.get("text") or "")


# --------------------------------------------------------------------------
# Requirement: No Sender Identity Restriction (Deferred) (MODIFIED)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sender",
    [
        pytest.param("U0ARBITRARYMEMBER", id="arbitrary-member"),
        pytest.param("W0ANOTHERMEMBER", id="another-arbitrary-member"),
    ],
)
def test_any_human_member_can_trigger_omni(
    sender: str,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Any member in the channel can trigger Omni.

    WHEN any human member of the Slack workspace mentions the bot in a channel
    it is in
    THEN the system SHALL process that mention the same as any other, without
    checking the sender's identity or role.

    "Without checking the sender's identity" is asserted in the only form
    observable from outside: unrelated, arbitrary senders -- none configured,
    allow-listed or otherwise known to the system -- are each processed. A
    negative assertion that no identity check ran anywhere would require
    reading the implementation, which these tests deliberately do not do.
    """
    answer = "Yes, any member can ask."
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion(answer=answer))

    response = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> can I ask you something?",
            user=sender,
            channel=CHANNEL,
        ),
    )

    assert 200 <= response.status_code < 300
    # Specified: the mention is processed the same as any other.
    assert len(fake.calls) == 1
    assert len(slack_api.posts) == 1
    assert slack_api.posts[0]["channel"] == CHANNEL
    assert answer in (slack_api.posts[0].get("text") or "")


def test_no_member_is_privileged_over_another(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No member is privileged over another.

    WHEN two different workspace members each mention the bot in a channel it
    is in
    THEN the system SHALL process both mentions identically, without
    consulting either sender's identity, role or permissions.

    Both mentions carry identical text, so the sender is the only thing that
    differs between them. "Identically" is therefore asserted as: same status,
    same question reaching omni-agent, same answer reaching the same channel.
    An implementation that consulted identity at all -- to allow, deny, route
    or annotate -- would have to make one of those differ.
    """
    answer = "Yes, any member can ask."
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion(answer=answer))
    question = "can I ask you something?"

    first = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> {question}",
            user="U0FIRSTMEMBER",
            event_id="Ev0FIRST",
        ),
    )
    second = _post(
        client,
        _app_mention_payload(
            text=f"<@{BOT_ID}> {question}",
            user="W0SECONDMEMBER",
            event_id="Ev0SECOND",
        ),
    )

    # Specified: both are processed identically.
    assert first.status_code == second.status_code
    assert 200 <= first.status_code < 300

    assert len(fake.calls) == 2, (
        "expected both members' mentions to reach omni-agent; a differing "
        f"count means one sender was treated differently (observed: {fake.calls})"
    )
    assert fake.calls[0] == fake.calls[1]

    assert len(slack_api.posts) == 2, (
        f"expected both members to receive an answer, observed posts: {slack_api.posts}"
    )
    assert slack_api.posts[0]["channel"] == slack_api.posts[1]["channel"] == CHANNEL
    assert slack_api.posts[0].get("text") == slack_api.posts[1].get("text")


# --------------------------------------------------------------------------
# DERIVED FROM TASKS (no delta-spec scenario): tasks.md 7.11 / 2.4a
# --------------------------------------------------------------------------


def test_listener_error_other_than_unhandled_request_is_logged(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """DERIVED FROM TASKS, not from a delta-spec scenario. tasks.md 7.11.

    Registering `@app.error` displaces Bolt's default error handler, whose
    contribution is the log entry (design.md, Verified Finding 5). A handler
    that recognised only `BoltUnhandledRequestError` and returned silently for
    everything else would delete the only remaining trace of a failed answer
    post.

    Asserted on the log record rather than on the HTTP status -- with
    `process_before_response` at its default, the acknowledgement is already
    decided by the time a listener error arrives, so status cannot distinguish
    the cases. The error used is the one design.md argues from: the
    failure-message post itself failing, which escapes the listener's own
    `except` rather than being handled by it.

    This test asserts a constraint no `slack-trigger` scenario states. It is
    recorded as derived in `test-manifest.md`; if the project decides the log
    is not required, this test is the thing to revisit, not the requirement.
    """
    async_client = importlib.import_module("slack_sdk.web.async_client")
    unreachable = _RecordingSlackApi(failure=ConnectionError("Slack is unreachable"))
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", unreachable.api_call)
    install_answer_question(
        monkeypatch,
        _RecordingAnswerQuestion(failure=RuntimeError("simulated omni-agent failure")),
    )

    with caplog.at_level(logging.ERROR):
        response = _post(client, _app_mention_payload())
        _drain(client)

    # Derived: the acknowledgement is unaffected -- it was decided before the
    # listener ran at all.
    assert 200 <= response.status_code < 300

    # Precondition, so this cannot pass for the wrong reason: the listener got
    # as far as attempting the failure-message post, and that attempt failed.
    assert "chat.postMessage" in unreachable.methods, (
        "the listener never attempted to post, so no error escaped it and this"
        " test would prove nothing about the error handler"
    )

    assert any(record.levelno >= logging.ERROR for record in caplog.records), (
        "a listener error that is not a BoltUnhandledRequestError left no log "
        "record; the `@app.error` handler must log every error it does not "
        "recognise (tasks.md 2.4a), since it displaces the default handler "
        "that would otherwise have done so"
    )
