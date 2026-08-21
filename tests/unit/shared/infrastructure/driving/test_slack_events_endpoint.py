"""Tests for the `slack-trigger` capability's Slack Events API endpoint.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/trigger-omni-agent-via-slack/specs/slack-trigger/spec.md`:

- "Slack App Mention Triggers Omni" / Scenario: Mention receives an answer in
  the same channel
- "Slack Request Authenticity Is Verified" / Scenario: Unsigned or forged
  request is rejected
- "Endpoint Responds to Slack's URL Verification Challenge" / Scenario:
  Challenge request is echoed back
- "Slack Events Are Acknowledged Within Slack's Timeout" / Scenario: Slow
  answer generation does not delay the acknowledgement
- "Answer Generation Failure Is Visible in Slack" / Scenario: Omni-agent
  invocation fails
- "No Sender Identity Restriction (Deferred)" / Scenario: Any member in the
  channel can trigger Omni

At the time these tests were written,
`src/commerce_ops/shared/infrastructure/driving/slack.py` does not exist --
so this whole module is expected to fail at collection with
`ModuleNotFoundError` until it lands. That failure establishes only that the
target is absent; it says nothing about whether the assertions below are
correct. See `test-manifest.md` at the change root for the full accounting,
including every assertion's specified/derived classification and the
unresolved project questions these tests assume answers to.

Seams used, all fixed by design.md rather than invented here:

- `get_signature_verifier()` / `get_slack_client()` are lazy,
  `functools.lru_cache`-wrapped factories reading `OMNI_AGENT_SLACK_SIGNING_SECRET` /
  `OMNI_AGENT_SLACK_BOT_TOKEN` from the ambient environment. Signature verification is
  exercised against a REAL `slack_sdk.signature.SignatureVerifier` built from
  a test signing secret -- no fake verifier -- so these tests constrain the
  endpoint's verification behaviour rather than a stub of it. Only the
  `WebClient` is replaced, because posting is a live network call.
- `handle_app_mention(event)` invokes
  `omni_agent.application.graph.build_production_graph()`; a recording fake
  graph is substituted for it, per `add-omni-agent`'s
  `graph.invoke({"messages": [HumanMessage(...)]})` contract.
"""

from __future__ import annotations

import importlib
import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from slack_sdk.signature import SignatureVerifier

from commerce_ops.main import app
from commerce_ops.shared.infrastructure.driving import slack as slack_adapter

# Imported dynamically rather than with `from ... import graph`: the package's
# `__init__` does not re-export the submodule, and only the module object (not
# the symbol) can be monkeypatched.
omni_graph_module = importlib.import_module("commerce_ops.omni_agent.application.graph")

SLACK_EVENTS_PATH = "/slack/events"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-not-a-real-token"  # not a real credential
BOT_ID = "U0BOTID"
CHANNEL = "C0FFEECHANNEL"


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingSlackClient:
    """Stands in for `slack_sdk.WebClient`, recording what was posted.

    Only `chat_postMessage` is implemented -- design.md fixes it as the one
    Slack Web API call this adapter makes. `channel`/`text` are accepted
    positionally as well as by keyword because `WebClient.chat_postMessage`
    accepts both and design.md does not pin the call style.
    """

    def __init__(self) -> None:
        self.posted: list[dict[str, Any]] = []

    # Named to mirror `slack_sdk.WebClient`'s own method exactly.
    def chat_postMessage(
        self,
        channel: str | None = None,
        text: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.posted.append({"channel": channel, "text": text, **kwargs})
        return {"ok": True}


class _RecordingGraph:
    """Stands in for omni-agent's compiled graph.

    Records each `invoke` payload, and either returns a scripted answer in
    the `MessagesState` shape `add-omni-agent` fixed, or raises.
    """

    def __init__(
        self,
        answer: str = "Paris is the capital of France.",
        failure: Exception | None = None,
        journal: list[str] | None = None,
    ) -> None:
        self.answer = answer
        self.failure = failure
        self.journal = journal
        self.calls: list[Any] = []

    def invoke(self, payload: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        if self.journal is not None:
            self.journal.append("omni_invoked")
        self.calls.append(payload)
        if self.failure is not None:
            raise self.failure
        return {
            "messages": [
                HumanMessage(content=_question_from(payload)),
                AIMessage(content=self.answer),
            ]
        }


class _ResponseStartRecorder:
    """ASGI wrapper noting when the HTTP response headers are sent.

    Used to establish acknowledgement ordering: FastAPI runs
    `BackgroundTasks` only after the response has been sent, so a route that
    schedules the omni-agent call as a background task records
    "response_started" strictly before "omni_invoked", while a route that
    awaits the answer inline records them the other way round.
    """

    def __init__(self, inner: Any, journal: list[str]) -> None:
        self.inner = inner
        self.journal = journal

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        async def recording_send(message: Any) -> None:
            if message.get("type") == "http.response.start":
                self.journal.append("response_started")
            await send(message)

        await self.inner(scope, receive, recording_send)


def _question_from(payload: Any) -> str:
    """Extracts the question the adapter handed to omni-agent.

    `add-omni-agent`'s design fixed the invocation as
    `graph.invoke({"messages": [HumanMessage(question)]})`; a bare string is
    accepted too so this helper reports a clear mismatch rather than an
    obscure `TypeError` if the adapter passes something else.
    """
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        messages = payload.get("messages")
        if messages:
            last = messages[-1]
            content = getattr(last, "content", last)
            if isinstance(content, str):
                return content
    raise AssertionError(
        "expected omni-agent to be invoked as "
        '`graph.invoke({"messages": [HumanMessage(question)]})`, got: '
        f"{payload!r}"
    )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _clear_factory_caches() -> None:
    """Drops anything the `lru_cache`-wrapped factories memoised.

    Without this, a verifier built from one test's signing secret would leak
    into the next test through the cache.
    """
    for name in ("get_signature_verifier", "get_slack_client"):
        factory = getattr(slack_adapter, name, None)
        cache_clear = getattr(factory, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ambient environment the adapter reads its credentials from."""
    monkeypatch.setenv("OMNI_AGENT_SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("OMNI_AGENT_SLACK_BOT_TOKEN", BOT_TOKEN)
    _clear_factory_caches()
    yield
    _clear_factory_caches()


@pytest.fixture()
def slack_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[_RecordingSlackClient]:
    """Substitutes the recording client for the real `WebClient`.

    Both substitution points are covered on purpose: design.md fixes the
    cached factory as the seam but does not say whether the route resolves it
    by calling it directly or through FastAPI's `Depends`, and either
    satisfies the design.
    """
    fake = _RecordingSlackClient()
    original = getattr(slack_adapter, "get_slack_client", None)
    assert original is not None, (
        "expected a `get_slack_client()` factory in the Slack adapter "
        "(design.md: lazy, lru_cache-wrapped factories are the seam tests "
        "substitute fakes through)"
    )
    monkeypatch.setattr(slack_adapter, "get_slack_client", lambda: fake)
    app.dependency_overrides[original] = lambda: fake
    yield fake
    app.dependency_overrides.pop(original, None)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


def install_graph(
    monkeypatch: pytest.MonkeyPatch, graph: _RecordingGraph
) -> _RecordingGraph:
    """Points `build_production_graph()` at the recording fake.

    Patched in both modules because design.md does not fix whether the
    adapter imports the name directly (`from ... import
    build_production_graph`) or reaches it through the module.
    """

    def factory(*args: Any, **kwargs: Any) -> _RecordingGraph:
        return graph

    patched = False
    for module in (slack_adapter, omni_graph_module):
        if hasattr(module, "build_production_graph"):
            monkeypatch.setattr(module, "build_production_graph", factory)
            patched = True
    assert patched, (
        "expected `build_production_graph` to be reachable on the Slack "
        "adapter or on commerce_ops.omni_agent.application.graph"
    )
    return graph


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------


def _signed_headers(body: bytes, *, timestamp: str | None = None) -> dict[str, str]:
    stamp = timestamp if timestamp is not None else str(int(time.time()))
    signature = SignatureVerifier(SIGNING_SECRET).generate_signature(
        timestamp=stamp, body=body
    )
    assert signature is not None
    return {
        "Content-Type": "application/json",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _post(
    client: TestClient,
    payload: dict[str, Any],
    headers_for: Callable[[bytes], dict[str, str]] = _signed_headers,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(SLACK_EVENTS_PATH, content=body, headers=headers_for(body))


def _app_mention_payload(
    text: str = f"<@{BOT_ID}> what is the capital of France?",
    user: str = "U0MEMBER",
    channel: str = CHANNEL,
) -> dict[str, Any]:
    """A minimal but realistically shaped Slack `app_mention` envelope."""
    return {
        "type": "event_callback",
        "token": "verification-token",
        "team_id": "T0TEAM",
        "api_app_id": "A0APP",
        "event_id": "Ev0EVENT",
        "event_time": 1700000000,
        "event": {
            "type": "app_mention",
            "user": user,
            "text": text,
            "ts": "1700000000.000100",
            "channel": channel,
            "event_ts": "1700000000.000100",
        },
    }


# --------------------------------------------------------------------------
# Requirement: Endpoint Responds to Slack's URL Verification Challenge
# --------------------------------------------------------------------------


def test_url_verification_challenge_is_echoed_back(
    client: TestClient,
    slack_client: _RecordingSlackClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Challenge request is echoed back.

    WHEN Slack sends a `url_verification` challenge request to the events
    endpoint
    THEN the system SHALL respond with the same challenge value it received.
    """
    graph = install_graph(monkeypatch, _RecordingGraph())
    challenge = "3eZbrw1aB1cCcQ2S1nZ7jHqWvXyZ0challenge"

    response = _post(
        client,
        {
            "type": "url_verification",
            "token": "verification-token",
            "challenge": challenge,
        },
    )

    # Specified: respond with the same challenge value.
    assert response.status_code == 200
    # Derived from design.md, which fixes the response body as
    # `{"challenge": ...}`; the spec itself only requires that the value come
    # back. The containment check keeps the weaker, spec-level guarantee
    # readable on its own.
    assert challenge in response.text
    assert response.json()["challenge"] == challenge

    # Derived: a handshake is not an event, so nothing downstream should run.
    assert graph.calls == []
    assert slack_client.posted == []


# --------------------------------------------------------------------------
# Requirement: Slack Request Authenticity Is Verified
# --------------------------------------------------------------------------


def _unsigned_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _foreign_secret_headers(body: bytes) -> dict[str, str]:
    stamp = str(int(time.time()))
    signature = SignatureVerifier("an-attackers-own-secret").generate_signature(
        timestamp=stamp, body=body
    )
    assert signature is not None
    return {
        "Content-Type": "application/json",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _tampered_body_headers(body: bytes) -> dict[str, str]:
    # Correctly signed -- but for a different body than the one being sent.
    return _signed_headers(b'{"type":"something_else"}')


def _stale_timestamp_headers(body: bytes) -> dict[str, str]:
    # Correctly signed for a timestamp well outside Slack's replay window.
    return _signed_headers(body, timestamp=str(int(time.time()) - 60 * 60))


@pytest.mark.parametrize(
    "headers_for",
    [
        pytest.param(_unsigned_headers, id="no-signature-headers"),
        pytest.param(_foreign_secret_headers, id="signed-with-wrong-secret"),
        pytest.param(_tampered_body_headers, id="body-tampered-after-signing"),
        pytest.param(_stale_timestamp_headers, id="replayed-stale-timestamp"),
    ],
)
def test_request_failing_signature_verification_is_rejected(
    headers_for: Callable[[bytes], dict[str, str]],
    client: TestClient,
    slack_client: _RecordingSlackClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Unsigned or forged request is rejected.

    WHEN an incoming request to the Slack events endpoint fails Slack's
    signature verification
    THEN the system SHALL reject the request and SHALL NOT invoke
    omni-agent.
    """
    graph = install_graph(monkeypatch, _RecordingGraph())

    response = _post(client, _app_mention_payload(), headers_for=headers_for)

    # Specified: the request is rejected. Derived: "rejected" is read as a
    # 4xx client error -- neither the spec nor design.md pins an exact status
    # code, so any of 400/401/403 satisfies this, but a 2xx does not.
    assert 400 <= response.status_code < 500, (
        f"expected the request to be rejected, got {response.status_code}"
    )

    # Specified: omni-agent SHALL NOT be invoked.
    assert graph.calls == []
    # Derived: nothing is posted back either -- a rejected request must not
    # produce channel traffic an attacker could induce.
    assert slack_client.posted == []


# --------------------------------------------------------------------------
# Requirement: Slack Events Are Acknowledged Within Slack's Timeout
# --------------------------------------------------------------------------


def test_app_mention_is_acknowledged_before_answer_generation(
    slack_client: _RecordingSlackClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: Slow answer generation does not delay the acknowledgement.

    WHEN the bot is mentioned and generating the answer takes longer than
    Slack's acknowledgement window
    THEN the system SHALL still have acknowledged the event within that
    window, and SHALL post the answer separately once it is ready.

    Asserted as strict ordering rather than as elapsed time: a wall-clock
    assertion would be both flaky and unable to distinguish "fast enough
    today" from "acknowledged independently of the answer". If the answer is
    generated only after the response has been sent, the acknowledgement
    cannot be delayed by generation however long it takes -- which is exactly
    what the requirement asks for. A deliberate sleep is therefore not used;
    it would add runtime without adding evidence.
    """
    journal: list[str] = []
    graph = install_graph(monkeypatch, _RecordingGraph(journal=journal))

    with TestClient(_ResponseStartRecorder(app, journal)) as recording_client:
        response = _post(recording_client, _app_mention_payload())

    # Derived: acknowledgement is a 2xx; design.md says the route "returns
    # 200 immediately".
    assert 200 <= response.status_code < 300

    # Specified: the event was acknowledged before the answer existed.
    assert "response_started" in journal, "the endpoint never sent a response"
    assert "omni_invoked" in journal, "omni-agent was never invoked"
    assert journal.index("response_started") < journal.index("omni_invoked"), (
        "omni-agent was invoked before the event was acknowledged; the "
        "generation must be scheduled as a background task, not awaited "
        f"inline (observed order: {journal})"
    )

    # Specified: the answer is posted separately, once it is ready.
    assert len(graph.calls) == 1
    assert len(slack_client.posted) == 1


# --------------------------------------------------------------------------
# Requirement: Slack App Mention Triggers Omni
# --------------------------------------------------------------------------


def test_mention_receives_an_answer_in_the_same_channel(
    client: TestClient,
    slack_client: _RecordingSlackClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Mention receives an answer in the same channel.

    WHEN the bot is `@mentioned` in a Slack channel with a question
    THEN the system SHALL post omni-agent's generated answer as a message in
    that same channel.
    """
    answer = "Paris is the capital of France."
    graph = install_graph(monkeypatch, _RecordingGraph(answer=answer))
    question = "what is the capital of France?"

    response = _post(
        client, _app_mention_payload(text=f"<@{BOT_ID}> {question}", channel=CHANNEL)
    )

    assert 200 <= response.status_code < 300

    # Specified: omni-agent is invoked with the text of the mention as the
    # question.
    assert len(graph.calls) == 1, "expected omni-agent to be invoked exactly once"
    asked = _question_from(graph.calls[0])
    # Specified (design.md, "The mention's bot-ID token is stripped from the
    # event text before it's passed to omni_agent"). `.strip()` on the
    # observed value is deliberate: whether stripping the token leaves a
    # leading space is not pinned anywhere, and is not what this asserts.
    assert "<@" not in asked, (
        f"the bot-mention token was not stripped from the question: {asked!r}"
    )
    assert asked.strip() == question

    # Specified: the answer is posted as a message in that same channel.
    assert len(slack_client.posted) == 1, "expected exactly one message posted back"
    posted = slack_client.posted[0]
    assert posted["channel"] == CHANNEL
    # Derived: containment rather than equality, so an implementation that
    # adds surrounding formatting is not failed for it. What is specified is
    # that omni-agent's generated answer reaches the channel.
    assert answer in (posted["text"] or "")


# --------------------------------------------------------------------------
# Requirement: Answer Generation Failure Is Visible in Slack
# --------------------------------------------------------------------------


def test_omni_agent_invocation_failure_posts_a_message_to_the_channel(
    client: TestClient,
    slack_client: _RecordingSlackClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Omni-agent invocation fails.

    WHEN omni-agent's invocation fails while processing an `app_mention`
    THEN the system SHALL post a message to the originating channel
    indicating the request failed, rather than posting nothing.

    DELIBERATELY UNTESTED: the wording of the failure message. Neither the
    spec nor design.md pins any phrasing ("a short failure message"), and
    asserting particular words here would impose a contract nobody agreed
    to. What is asserted is that a message reaches the originating channel
    at all -- the thing the requirement exists to guarantee -- and that the
    background task does not propagate the failure instead. See
    test-manifest.md.
    """
    graph = install_graph(
        monkeypatch,
        _RecordingGraph(failure=RuntimeError("simulated omni-agent failure")),
    )

    response = _post(client, _app_mention_payload(channel=CHANNEL))

    # Specified precondition: the invocation was actually attempted and did
    # fail -- otherwise this test would pass for the wrong reason.
    assert len(graph.calls) == 1

    # Derived: the acknowledgement is unaffected; the failure happens after
    # the response has already been sent.
    assert 200 <= response.status_code < 300

    # Specified: a message is posted to the originating channel rather than
    # nothing.
    assert slack_client.posted, (
        "omni-agent failed and nothing was posted back to the channel; the "
        "mention was left silently unanswered"
    )
    assert len(slack_client.posted) == 1
    posted = slack_client.posted[0]
    assert posted["channel"] == CHANNEL
    assert posted["text"], "the failure message posted to the channel was empty"


# --------------------------------------------------------------------------
# Requirement: No Sender Identity Restriction (Deferred)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sender",
    [
        pytest.param("U0ARBITRARYMEMBER", id="arbitrary-member"),
        pytest.param("W0ANOTHERMEMBER", id="another-arbitrary-member"),
    ],
)
def test_any_workspace_member_can_trigger_omni(
    sender: str,
    client: TestClient,
    slack_client: _RecordingSlackClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Any member in the channel can trigger Omni.

    WHEN any member of the Slack workspace mentions the bot in a channel it
    is in
    THEN the system SHALL process that mention the same as any other,
    without checking the sender's identity or role.

    The "without checking the sender's identity or role" half is asserted in
    the only form observable from outside: two unrelated, arbitrary senders
    -- neither of them configured, allow-listed, or otherwise known to the
    system -- are both processed identically. A negative assertion that no
    identity check ran anywhere would require reading the implementation,
    which these tests deliberately do not do.
    """
    answer = "Yes, any member can ask."
    graph = install_graph(monkeypatch, _RecordingGraph(answer=answer))

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
    assert len(graph.calls) == 1
    assert len(slack_client.posted) == 1
    assert slack_client.posted[0]["channel"] == CHANNEL
    assert answer in (slack_client.posted[0]["text"] or "")
