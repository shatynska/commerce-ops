"""DERIVED FROM TASKS, no delta-spec scenario of its own: tasks.md 2.1.

design.md's Migration Plan step 4: "Confirm slack.py needs no change -- its
existing except Exception already covers the new exception; add a test
asserting this rather than assuming it." This file is that test -- it
confirms `slack.py`'s existing broad catch covers `NonStringAnswerError`
specifically, rather than assuming a general `Exception` test already
proves it (the assumption proposal.md itself flags as needing confirmation,
not as settled: "Possibly modified: slack.py... confirmed, not assumed,
during design").

`NonStringAnswerError` does not exist yet (design.md, "Where the exception
lives" -- it is to be added to `use_cases.py`, alongside its only raiser and
its only caller's module boundary). Importing it here is expected to fail
collection until the implementation lands, per this project's
test-design-before-implementation workflow (AGENTS.md); that is the
intended, reportable state for this file, not a defect in it.

Fixtures and helpers below are deliberately duplicated, trimmed to only what
this one test needs, rather than imported from a sibling test module in
this directory (`test_slack_event_dispatch_under_bolt.py`,
`test_slack_events_endpoint.py`) -- matching this directory's own
established convention of each file carrying its own self-contained
harness rather than importing another file's private names.

Level: the endpoint, through `TestClient`. What design.md's step 4 asks to
confirm is what `slack.py`'s existing `except Exception` does with this
specific exception type once it propagates out of `answer_question`, and
that is only observable from outside, at the same level the rest of this
directory's Slack-adapter tests already use for the equivalent generic-
failure case (`test_slack_events_endpoint.py`'s
`test_omni_agent_invocation_failure_posts_a_message_to_the_channel`).

DELIBERATELY UNTESTED: the exact wording of the failure message posted back
to the channel. This directory's own equivalent test for a generic failure
already leaves this unpinned, for the reason recorded there -- neither the
spec nor design.md pins any phrasing -- and this file follows the same
convention rather than asserting a value found only by reading `slack.py`.
"""

from __future__ import annotations

import importlib
import json
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.omni_agent.application.use_cases import NonStringAnswerError
from commerce_ops.omni_agent.infrastructure.driving import slack as slack_adapter

SLACK_EVENTS_PATH = "/omni_agent/slack/events"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-not-a-real-token"  # not a real credential
BOT_ID = "U0BOTID"
CHANNEL = "C0FFEECHANNEL"

# Cleared so no developer's ambient shell can make this test pass for a
# reason the deployment does not share -- matching this directory's
# existing convention (test_slack_event_dispatch_under_bolt.py).
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
    Web API method goes through, so this records the failure post *and* any
    identity call an implementation makes on the way to it.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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
        if api_method == "auth.test":
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
    """Stands in for `omni_agent.application.answer_question` (a coroutine).

    Only the failure path is exercised in this file, so no scripted-answer
    branch is offered -- unlike the sibling test modules' equivalents.
    """

    def __init__(self, failure: Exception) -> None:
        self.failure = failure
        self.calls: list[str] = []

    async def __call__(self, question: str) -> str:
        self.calls.append(question)
        raise self.failure


# --------------------------------------------------------------------------
# Cache reset
# --------------------------------------------------------------------------


def _reset_slack_caches() -> None:
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        module = importlib.import_module(module_name)
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()


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
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    # `slack_asgi_app` comes from this directory's conftest.py -- Bolt runs
    # the listener as a task scheduled after the acknowledgement, so
    # asserting on what a listener did straight after `_post` returns would
    # be racing that task.
    with TestClient(slack_asgi_app) as test_client:
        yield test_client


def install_answer_question(
    monkeypatch: pytest.MonkeyPatch, fake: _RecordingAnswerQuestion
) -> _RecordingAnswerQuestion:
    """Points the adapter's call to `answer_question` at the double."""
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
    """Gives work Bolt scheduled a chance to run before an assertion on it.

    Matches this directory's established convention
    (`test_slack_event_dispatch_under_bolt.py`'s own `_drain`): a further
    round-trip through the same client forces the loop to make progress
    past whatever task the listener spawned.
    """
    client.get("/health")


def _app_mention_payload(*, channel: str = CHANNEL) -> dict[str, Any]:
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
            "user": "U0MEMBER",
            "text": f"<@{BOT_ID}> what is the capital of France?",
            "ts": "1700000000.000100",
            "channel": channel,
            "event_ts": "1700000000.000100",
        },
    }


# --------------------------------------------------------------------------
# tasks.md 2.1
# --------------------------------------------------------------------------


def test_non_string_answer_error_is_caught_by_the_existing_broad_handler(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tasks.md 2.1 (DERIVED FROM TASKS -- no delta-spec scenario of its own).

    WHEN `answer_question` raises `NonStringAnswerError` specifically while
    handling an `app_mention`
    THEN `slack.py`'s existing broad `except Exception` / `_FAILURE_MESSAGE`
    path SHALL still catch it and post a failure message to the originating
    channel -- confirming the existing handler needs no change for this new
    exception type, rather than assuming it (design.md, Migration Plan
    step 4).
    """
    fake = install_answer_question(
        monkeypatch,
        _RecordingAnswerQuestion(
            failure=NonStringAnswerError(
                "language model response content was not a plain string"
            )
        ),
    )

    response = _post(client, _app_mention_payload(channel=CHANNEL))

    # Derived: the acknowledgement is unaffected -- Bolt's acknowledgement is
    # decided before the listener (and this exception) runs at all.
    assert 200 <= response.status_code < 300

    _drain(client)

    # Precondition, so this cannot pass for the wrong reason: the invocation
    # was actually attempted and did raise `NonStringAnswerError`
    # specifically.
    assert len(fake.calls) == 1, (
        "expected the app_mention handler to invoke answer_question exactly "
        f"once (observed: {fake.calls})"
    )

    # Specified (tasks.md 2.1 / design.md Migration Plan step 4): a message
    # is still posted to the originating channel, exactly as for any other
    # answer_question failure -- the existing broad catch needs no change
    # for this exception type.
    assert len(slack_api.posts) == 1, (
        "NonStringAnswerError propagating out of answer_question was not "
        "caught by slack.py's existing broad `except Exception`; no "
        f"failure message reached the channel (calls observed: {slack_api.calls})"
    )
    posted = slack_api.posts[0]
    # Derived: same channel the mention came from, matching this directory's
    # equivalent generic-failure test's assertions.
    assert posted["channel"] == CHANNEL
    # Derived: some message reached the channel; its wording is deliberately
    # untested, per this file's module docstring.
    assert posted.get("text"), "the failure message posted to the channel was empty"
