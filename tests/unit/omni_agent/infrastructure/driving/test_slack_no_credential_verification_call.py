"""`slack-trigger`: handling an event makes no credential-verification call.

Derived strictly from the delta specs at
`openspec/changes/migrate-slack-to-bolt/specs/slack-trigger/spec.md`, without
reading the implementation. Scenarios covered here:

- ADDED "Handling An Event Requires No Credential Verification Call To Slack"
  / Scenario: Handling a mention makes no credential-verification call
  / Scenario: No credential-verification call at startup
  / Scenario: Inbound handling is unaffected by Slack being unreachable

One further test covers no scenario: the forbidden-environment guard of
`tasks.md` 7.9 / 2.2a. It is marked DERIVED FROM TASKS below. It belongs in
this file because what it protects is this requirement -- Bolt's constructor
falls back to `os.environ["SLACK_BOT_TOKEN"]`, and an ambient value would
silently reinstate the `auth.test` call the requirement forbids (design.md,
Verified Finding 7). Without it the guarantee is green in a clean environment
and false in one carrying that name.

This is the test design.md's Migration Plan names as the one that carries the
rollout risk: "verified by an explicit test asserting no outbound HTTP is
attempted ... not by inspection, since the whole reason this decision exists is
that inspection of the documentation gave the wrong answer once already."

Level and seams: as in `test_slack_event_dispatch_under_bolt.py`. The
interception point is `AsyncWebClient.api_call`, through which every Slack Web
API method funnels -- `auth_test` does `api_call("auth.test", ...)` and
`chat_postMessage` does `api_call("chat.postMessage", ...)`, so one patch
records both and no call reaches the network.
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

from commerce_ops.main import app
from commerce_ops.omni_agent.infrastructure.driving import slack as slack_adapter

SLACK_EVENTS_PATH = "/omni_agent/slack/events"
SIGNING_SECRET = "test-slack-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-not-a-real-token"  # not a real credential
BOT_ID = "U0BOTID"
CHANNEL = "C0FFEECHANNEL"

FORBIDDEN_GENERIC_ENV_VARS = ("SLACK_BOT_TOKEN", "SLACK_SIGNING_SECRET")

_MODULES_WITH_CACHED_FACTORIES = (
    "commerce_ops.omni_agent.infrastructure.driving.slack",
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

# Slack Web API methods whose purpose is to establish or validate the caller's
# own identity or credentials. `auth.test` is the one this change exists to
# remove -- Bolt's `AsyncSingleTeamAuthorization` calls it on the first request
# that reaches the middleware (design.md, Verified Finding 1). The others are
# listed because the requirement is stated about the *purpose* of the call, not
# about one method name, so an implementation that swapped `auth.test` for
# `bots.info` or `users.identity` would satisfy a single-name check while
# breaking the requirement.
IDENTITY_VERIFICATION_METHODS = frozenset(
    {
        "auth.test",
        "auth.teams.list",
        "apps.connections.open",
        "bots.info",
        "users.identity",
        "openid.connect.userInfo",
        "team.info",
    }
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
            # Shaped like a real result, so an implementation that wrongly
            # makes this call fails on the assertion that says so rather than
            # on a downstream KeyError.
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
    """Drops whatever the lazily-cached Bolt-app factories memoised.

    The seam's name is not pinned by any artifact, so it is discovered rather
    than named. See `test-manifest.md`'s unresolved project questions.
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


def _require_cold_cache() -> None:
    """Refuses to proceed unless a cached Bolt app was actually discarded.

    A test that changes the environment and then observes an app built from
    the *previous* environment passes vacuously. That silent pass is exactly
    the failure mode `tasks.md` 2.6a exists to prevent, so its absence is
    asserted rather than hoped for.
    """
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
    monkeypatch.setenv("OMNI_AGENT_SLACK_SIGNING_SECRET", SIGNING_SECRET)
    monkeypatch.setenv("OMNI_AGENT_SLACK_BOT_TOKEN", BOT_TOKEN)
    for name in FORBIDDEN_GENERIC_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    _reset_slack_caches()
    yield
    _reset_slack_caches()


def _install_recorder(
    monkeypatch: pytest.MonkeyPatch, recorder: _RecordingSlackApi
) -> _RecordingSlackApi:
    async_client = importlib.import_module("slack_sdk.web.async_client")
    monkeypatch.setattr(async_client.AsyncWebClient, "api_call", recorder.api_call)
    return recorder


@pytest.fixture()
def slack_api(monkeypatch: pytest.MonkeyPatch) -> _RecordingSlackApi:
    return _install_recorder(monkeypatch, _RecordingSlackApi())


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    with TestClient(slack_asgi_app) as test_client:
        yield test_client


def install_answer_question(
    monkeypatch: pytest.MonkeyPatch, fake: _RecordingAnswerQuestion
) -> _RecordingAnswerQuestion:
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


def _unsigned_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _post(
    client: TestClient,
    payload: dict[str, Any],
    *,
    signed: bool = True,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    headers = _signed_headers(body) if signed else _unsigned_headers(body)
    return client.post(SLACK_EVENTS_PATH, content=body, headers=headers)


def _app_mention_payload(
    *,
    text: str = f"<@{BOT_ID}> what is the capital of France?",
    user: str = "U0MEMBER",
    channel: str = CHANNEL,
) -> dict[str, Any]:
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
# Requirement: Handling An Event Requires No Credential Verification Call
# --------------------------------------------------------------------------


def test_handling_a_mention_makes_no_credential_verification_call(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Handling a mention makes no credential-verification call.

    WHEN an authentic `app_mention` is received and handled
    THEN the system SHALL make no outbound Slack call to establish or validate
    its own identity or credentials
    AND the call posting its answer SHALL NOT be preceded by any such call.

    Asserted by intercepting outbound calls, not by inspecting how the app is
    constructed (tasks.md 7.2). Construction was inspected once already and
    gave the wrong answer -- `token_verification_enabled` does not exist on
    `AsyncApp` at all (design.md, Verified Finding 1).
    """
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion())

    response = _post(client, _app_mention_payload())

    assert 200 <= response.status_code < 300

    # Precondition, so the assertions below cannot pass for the wrong reason:
    # the mention really was handled. "No outbound call" is trivially true of
    # a request that was rejected or never dispatched.
    assert len(fake.calls) == 1, (
        "the mention was never handled, so this test would establish nothing "
        "about what handling it calls out to"
    )

    # Specified: no outbound Slack call to establish or validate the system's
    # own identity or credentials.
    called_identity_methods = IDENTITY_VERIFICATION_METHODS.intersection(
        slack_api.methods
    )
    assert not called_identity_methods, (
        "handling a mention made an identity/credential-verification call to "
        f"Slack: {sorted(called_identity_methods)}. The Bolt app must be "
        "constructed with a custom `authorize` and NO `token`; passing a "
        "token makes Bolt install AsyncSingleTeamAuthorization, which calls "
        "auth.test and silently ignores the `authorize` (design.md, Verified "
        f"Finding 1). Observed call order: {slack_api.methods}"
    )

    # Specified: the answer post is not preceded by any such call. Asserted as
    # "the answer post is the first outbound call", which forbids a preceding
    # call without forbidding later ones -- the requirement explicitly does
    # not restrict outbound calls a capability makes to do its work.
    assert slack_api.methods, (
        "no outbound call at all was made; the answer was never posted"
    )
    assert slack_api.methods[0] == "chat.postMessage", (
        "something preceded the answer post on the way out: observed call "
        f"order {slack_api.methods}"
    )
    assert len(slack_api.posts) == 1
    assert slack_api.posts[0]["channel"] == CHANNEL


def test_startup_makes_no_credential_verification_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No credential-verification call at startup.

    WHEN the application starts and its Slack handling is initialized
    THEN the system SHALL make no outbound Slack call to establish or validate
    its own identity or credentials.

    Run with the Slack credentials present (the autouse fixture supplies them)
    so the assertion is not satisfied merely by there being nothing to
    authenticate with. Startup here is the app's lifespan, which `TestClient`
    runs on entering its context; `test_main_slack_wiring.py` separately
    covers import time in a fresh interpreter and is not modified.
    """
    recorder = _install_recorder(monkeypatch, _RecordingSlackApi())
    _require_cold_cache()

    with TestClient(app) as started:
        # Precondition: the application really did come up, so an empty call
        # log means "made no call", not "never started".
        assert started.get("/health").status_code == 200

    # Specified: no outbound Slack call at all during startup -- which
    # includes, and is stronger than, no identity call.
    assert recorder.calls == [], (
        "the application made an outbound Slack call while starting up: "
        f"{recorder.methods}. Bolt app construction must stay lazy and must "
        "not verify credentials at startup"
    )


def test_inbound_handling_is_unaffected_by_slack_being_unreachable(
    slack_asgi_app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Inbound handling is unaffected by Slack being unreachable.

    WHEN an authentic inbound request is received while Slack's API is
    unreachable
    THEN the system SHALL still verify, accept and acknowledge that request,
    and SHALL fail only at the point of delivering an outbound message.

    "Verify" is asserted in both directions inside the one test, because a
    system that had stopped verifying would also accept and acknowledge: an
    authentic request is accepted, and an unsigned one delivered under the
    same unreachable condition is still rejected.
    """
    unreachable = _install_recorder(
        monkeypatch, _RecordingSlackApi(failure=ConnectionError("Slack is unreachable"))
    )
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion())
    _require_cold_cache()

    with TestClient(slack_asgi_app) as client:
        authentic = _post(client, _app_mention_payload())
        forged = _post(client, _app_mention_payload(), signed=False)

    # Specified: the authentic request is accepted and acknowledged.
    assert 200 <= authentic.status_code < 300, (
        "an authentic request was not acknowledged while Slack was "
        f"unreachable, got {authentic.status_code}; inbound handling must not "
        "depend on Slack's API being reachable"
    )
    # Specified: it was accepted, i.e. it reached the handler.
    assert len(fake.calls) == 1

    # Specified: verification still happened -- an unsigned request is
    # rejected even while Slack is unreachable.
    assert 400 <= forged.status_code < 500, (
        "an unsigned request was not rejected while Slack was unreachable, "
        f"got {forged.status_code}"
    )

    # Specified: the failure occurs only at the point of delivering an
    # outbound message. Every attempted call was a delivery, and none was an
    # identity call made earlier in the request path.
    assert unreachable.methods, (
        "nothing was ever sent outbound, so the request did not get as far as "
        "delivery and this test cannot say where it failed"
    )
    assert IDENTITY_VERIFICATION_METHODS.isdisjoint(unreachable.methods), (
        "an identity/credential-verification call was attempted while Slack "
        f"was unreachable: {unreachable.methods}"
    )
    assert set(unreachable.methods) == {"chat.postMessage"}, (
        "the only outbound call attempted should have been the delivery, "
        f"observed: {unreachable.methods}"
    )


# --------------------------------------------------------------------------
# DERIVED FROM TASKS (no delta-spec scenario): tasks.md 7.9 / 2.2a
# --------------------------------------------------------------------------


def test_ambient_generic_bot_token_cannot_reinstate_the_credential_call(
    slack_asgi_app: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED FROM TASKS, not from a delta-spec scenario. tasks.md 7.9.

    The requirement above is what this protects; the mechanism is not stated
    in the spec. `AsyncApp.__init__` does `token = token or
    os.environ.get("SLACK_BOT_TOKEN")` (design.md, Verified Finding 7), so
    omitting the `token` argument is necessary but not sufficient: an ambient
    value makes `self._token` truthy, Bolt installs single-team authorization,
    the custom `authorize` is silently ignored, and the `auth.test` call comes
    back. Without this test the guarantee is green in a clean environment and
    false in one carrying that name.

    Two assertions, in order of what they trace to:

    - the requirement's own guarantee, which must hold in this environment
      too: no identity/credential-verification call is made;
    - DERIVED from design.md and tasks.md 2.2a: the guard's own response is a
      500. Construction is lazy, so the guard fires on the first Slack
      request, and a deployment carrying this name is misconfigured in a way
      no per-request status can express -- a 401 would misreport it as an
      authenticity problem.

    `raise_server_exceptions=False` on this client is what lets the 500 be
    observed as a response rather than re-raised into the test.
    """
    recorder = _install_recorder(monkeypatch, _RecordingSlackApi())
    fake = install_answer_question(monkeypatch, _RecordingAnswerQuestion())
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-ambient-not-a-real-token")
    _require_cold_cache()

    with TestClient(slack_asgi_app, raise_server_exceptions=False) as client:
        response = _post(client, _app_mention_payload())

    # Specified (the requirement this guard protects): no identity call, even
    # with the generic name present.
    called_identity_methods = IDENTITY_VERIFICATION_METHODS.intersection(
        recorder.methods
    )
    assert not called_identity_methods, (
        "an ambient SLACK_BOT_TOKEN reinstated Bolt's credential-verification "
        f"call: {sorted(called_identity_methods)}. The construction helper "
        'must refuse to build while "SLACK_BOT_TOKEN" is in os.environ -- a '
        "membership test, never a value read (tasks.md 2.2a(i))"
    )

    # Derived (design.md / tasks.md 2.2a): the guard fails loudly rather than
    # silently, and does so on presence rather than on a truthy value.
    assert response.status_code == 500, (
        "a runtime carrying SLACK_BOT_TOKEN is one this change declares "
        "invalid; the helper must refuse to build, which surfaces as a 500 on "
        f"the first Slack request. Got {response.status_code}"
    )
    # Derived: refusing to build means nothing reached omni-agent or Slack.
    assert fake.calls == []
    assert recorder.calls == []
