"""`launch-entry`: requests are verified before anything is acted on.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Scenarios covered here, all from the
ADDED requirement "Requests are verified before anything is acted on":

- Scenario: An unverifiable request is rejected
- Scenario: No configured secret rejects everything
- Scenario: An absent reply credential rejects rather than strands

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 2.1/2.2 name the module (`launch/infrastructure/driving/
slack_entry.py`), the app identity (`product_agent`, via the shared
`slack_app` registry), and the env var
`PRODUCT_AGENT_SLACK_SIGNING_SECRET` (moved to required by `proposal.md`'s
Impact section). Nothing in any artifact fixes:

- The route path. ASSUMED as `/product_agent/slack/events`, mirroring the
  one existing precedent for this exact shared registry
  (`omni_agent`'s `/omni_agent/slack/events`, see
  `tests/unit/omni_agent/infrastructure/driving/test_slack_event_dispatch_under_bolt.py`)
  generalized by app identity, since design.md explicitly says this
  adapter is registered "via the shared `slack_app` registry" -- the same
  composition mechanism.
- The bot-token env var name. ASSUMED as `PRODUCT_AGENT_SLACK_BOT_TOKEN`,
  by the same `<IDENTITY>_SLACK_<KIND>` convention `OMNI_AGENT_SLACK_BOT_TOKEN`
  establishes, and consistent with `tasks.md` 1.2's "the existing
  `product_agent` bot token".
- The slash command's name. ASSUMED as `/start-launch` -- design.md's own
  Open Questions section states this is "cosmetic, decided at
  implementation with the team", so no test here depends on the exact
  string; it is a placeholder for "the registered slash command".
- The modal's `callback_id`. ASSUMED as `start_launch_modal`.
- The reset seam for the shared registry's cached Bolt-app factories.
  Discovered the same way `test_slack_credential_absence_rejection.py`
  discovers it (`cache_clear()` or a `reset_*`/`clear_*` no-arg callable),
  rather than named.

Correcting any of the above is a fixture correction (failure state 3 in
`ai-toolkit:testing`); the postconditions each test asserts -- rejected vs.
accepted, and that no collaborator was ever touched -- are what trace to
the spec and must survive unweakened.

## Why 401

The `slack-trigger` capability spec (read for context, not modified by this
change) states the same family of rejection as "an unauthorized response",
and design.md Decision 5 says this adapter's credential gate follows "the
registry's established predicate pattern" -- the same mechanism
`test_slack_credential_absence_rejection.py` observes returning 401 for
exactly these two failure kinds (bad/missing signature, absent reply
token). Asserted here on that basis, not invented fresh.
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

from tests.support.fakes import FakeSlackResponse as _FakeSlackResponse

SLACK_ENTRY_PATH = "/product_agent/slack/events"  # ASSUMED, see module docstring
SIGNING_SECRET = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"  # not a real credential

SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"  # ASSUMED, see module docstring

SLASH_COMMAND = "/start-launch"  # ASSUMED, cosmetic per design.md
CALLBACK_ID = "start_launch_modal"  # ASSUMED

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

# The multiple candidate names the injected catalog-registrar attribute
# might carry. design.md Decision 2 / tasks.md 2.3 fix that a module-global
# injection point exists ("on daily_briefing_job.py's pattern") but not its
# spelling.
REGISTRAR_ATTRIBUTES: tuple[str, ...] = (
    "register_catalog_product",
    "catalog_registrar",
    "register_product",
)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingSlackApi:
    """Records every Slack Web API method the app calls, in call order."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def methods(self) -> list[str]:
        return [call["api_method"] for call in self.calls]

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        self.calls.append(
            {
                "api_method": api_method,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )
        return _FakeSlackResponse({"ok": True, "id": "V0VIEW"})


class _RecordingRegistrar:
    """Stands in for the injected catalog-registrar callable."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return None


class _RecordingStartLaunch:
    """Stands in for `launch.application.start_launch`."""

    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return None


# --------------------------------------------------------------------------
# Cache-reset discovery
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
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            # Expected until tasks 2.1-2.3 land: see module docstring.
            continue
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
                reset += 1
            elif _looks_like_a_reset_hook(value):
                value()
                reset += 1
    return reset


def _require_slack_entry_module() -> Any:
    """Imports the adapter module, failing with the absent-target message
    `ai-toolkit:testing` calls for rather than a bare `ModuleNotFoundError`.
    """
    try:
        return importlib.import_module(SLACK_ENTRY_MODULE)
    except ModuleNotFoundError as exc:
        pytest.fail(
            f"{SLACK_ENTRY_MODULE} does not exist yet (tasks.md 2.1); this "
            f"test's target is absent. Underlying error: {exc}"
        )


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
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
def registrar(monkeypatch: pytest.MonkeyPatch) -> _RecordingRegistrar:
    """Installs the recording registrar over whichever candidate attribute
    the adapter module exposes. Does NOT fail if none is found yet -- the
    module itself may not exist, which `_require_slack_entry_module` in
    each test reports clearly.
    """
    fake = _RecordingRegistrar()
    try:
        module = importlib.import_module(SLACK_ENTRY_MODULE)
    except ModuleNotFoundError:
        return fake
    for name in REGISTRAR_ATTRIBUTES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, fake)
    return fake


@pytest.fixture()
def start_launch(monkeypatch: pytest.MonkeyPatch) -> _RecordingStartLaunch:
    fake = _RecordingStartLaunch()
    try:
        module = importlib.import_module(SLACK_ENTRY_MODULE)
    except ModuleNotFoundError:
        return fake
    if hasattr(module, "start_launch"):
        monkeypatch.setattr(module, "start_launch", fake)
    return fake


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    # raise_server_exceptions=False: the requirement forbids a server-error
    # response as explicitly as it forbids an acknowledgement (slack-trigger
    # spec, read for context), so a 500 must be observable as a response.
    with TestClient(slack_asgi_app, raise_server_exceptions=False) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------


def _signed_headers(body: bytes, *, secret: str) -> dict[str, str]:
    stamp = str(int(time.time()))
    signature = SignatureVerifier(secret).generate_signature(timestamp=stamp, body=body)
    assert signature is not None
    return {
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _slash_command_form() -> dict[str, str]:
    return {
        "token": "verification-token",
        "team_id": "T0TEAM",
        "team_domain": "test-team",
        "channel_id": "C0FFEECHANNEL",
        "channel_name": "general",
        "user_id": "U0SUBMITTER",
        "user_name": "submitter",
        "command": SLASH_COMMAND,
        "text": "",
        "api_app_id": "A0PRODUCTAGENT",
        "response_url": "https://hooks.slack.test/commands/1234",
        "trigger_id": "1234.5678.abcdef",
    }


def _view_submission_form(
    *,
    sku: str = "SKU-0001",
    name: str = "Widget",
) -> dict[str, str]:
    view_submission_payload = {
        "type": "view_submission",
        "team": {"id": "T0TEAM", "domain": "test-team"},
        "user": {"id": "U0SUBMITTER", "username": "submitter"},
        "api_app_id": "A0PRODUCTAGENT",
        "token": "verification-token",
        "trigger_id": "1234.5678.abcdef",
        "view": {
            "id": "V0VIEW",
            # Slack's own view object always carries this; Bolt reads
            # `body["view"]["type"]` unconditionally (payload_utils'
            # `is_workflow_step_save`), so omitting it is a 500 rather than
            # anything this change's spec is about. Fixture correction made
            # while implementing tasks.md 2.2.
            "type": "modal",
            "callback_id": CALLBACK_ID,
            "private_metadata": "",
            "hash": "156772938.1827394",
            "state": {
                "values": {
                    "sku": {"sku": {"type": "plain_text_input", "value": sku}},
                    "name": {"name": {"type": "plain_text_input", "value": name}},
                    "asin": {"asin": {"type": "plain_text_input", "value": None}},
                    "launch_date": {
                        "launch_date": {
                            "type": "datepicker",
                            "selected_date": None,
                        }
                    },
                    "marketplace": {
                        "marketplace": {
                            "type": "static_select",
                            "selected_option": {
                                "value": "ATVPDKIKX0DER",
                                "text": {"type": "plain_text", "text": "Amazon US"},
                            },
                        }
                    },
                }
            },
        },
    }
    return {"payload": json.dumps(view_submission_payload)}


def _urlencode(form: dict[str, str]) -> bytes:
    import urllib.parse

    return urllib.parse.urlencode(form).encode("utf-8")


def _post_form(
    client: TestClient,
    form: dict[str, str],
    *,
    secret: str | None = SIGNING_SECRET,
) -> Any:
    body = _urlencode(form)
    if secret is not None:
        headers = _signed_headers(body, secret=secret)
    else:
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
    return client.post(SLACK_ENTRY_PATH, content=body, headers=headers)


def _drain(client: TestClient) -> None:
    client.get("/health")


def _assert_unauthorized(response: Any, *, because: str) -> None:
    assert response.status_code == 401, (
        f"{because}: expected 401, got {response.status_code}. The "
        "requirement forbids both an acknowledgement and a server error -- "
        "see the slack-trigger capability spec's analogous requirement, "
        "which design.md Decision 5 says this adapter's credential gate "
        "follows"
    )


# --------------------------------------------------------------------------
# Scenario: An unverifiable request is rejected
# --------------------------------------------------------------------------


def test_an_unverifiable_slash_command_is_rejected(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: An unverifiable request is rejected.

    WHEN a request arrives whose signature does not verify
    THEN it is rejected and nothing is persisted.
    """
    _require_slack_entry_module()
    body = _urlencode(_slash_command_form())
    bad_headers = _signed_headers(body, secret="a-completely-different-secret")

    response = client.post(SLACK_ENTRY_PATH, content=body, headers=bad_headers)
    _drain(client)

    _assert_unauthorized(response, because="the request's signature does not verify")
    # SPECIFIED: nothing is persisted -- no collaborator is even reached.
    assert registrar.calls == []
    assert start_launch.calls == []
    assert slack_api.methods == [], (
        "an unverifiable request reached far enough to call Slack's Web "
        f"API: {slack_api.methods}"
    )


def test_an_unverifiable_view_submission_is_rejected(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: An unverifiable request is rejected (view-submission half).

    Same scenario, exercised on the submission path rather than the
    slash-command path, since both are requests to this surface and neither
    is named as exempt.
    """
    _require_slack_entry_module()
    body = _urlencode(_view_submission_form())
    bad_headers = _signed_headers(body, secret="a-completely-different-secret")

    response = client.post(SLACK_ENTRY_PATH, content=body, headers=bad_headers)
    _drain(client)

    _assert_unauthorized(response, because="the submission's signature does not verify")
    assert registrar.calls == []
    assert start_launch.calls == []


# --------------------------------------------------------------------------
# Scenario: No configured secret rejects everything
# --------------------------------------------------------------------------


def test_no_configured_secret_rejects_a_slash_command(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: No configured secret rejects everything (slash-command half).

    WHEN the signing secret is absent from the environment and any request
    arrives
    THEN the request is rejected.
    """
    _require_slack_entry_module()
    monkeypatch.delenv(SIGNING_SECRET_VAR, raising=False)
    _reset_slack_caches()

    # Signed with a secret the running app does not have -- there is no
    # secret this request could carry that would verify once the app has
    # none configured.
    response = _post_form(client, _slash_command_form())
    _drain(client)

    _assert_unauthorized(
        response, because="the signing secret is absent from the environment"
    )
    assert registrar.calls == []
    assert start_launch.calls == []
    assert slack_api.methods == []


def test_no_configured_secret_rejects_a_view_submission(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: No configured secret rejects everything (submission half)."""
    _require_slack_entry_module()
    monkeypatch.delenv(SIGNING_SECRET_VAR, raising=False)
    _reset_slack_caches()

    response = _post_form(client, _view_submission_form())
    _drain(client)

    _assert_unauthorized(
        response, because="the signing secret is absent from the environment"
    )
    assert registrar.calls == []
    assert start_launch.calls == []
    assert slack_api.methods == []


# --------------------------------------------------------------------------
# Scenario: An absent reply credential rejects rather than strands
# --------------------------------------------------------------------------


def test_slash_command_is_rejected_when_the_bot_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: An absent reply credential rejects rather than strands
    (slash-command half).

    WHEN a request whose handling would need the bot's reply credential
    arrives and no bot token is configured
    THEN the request is rejected rather than acknowledged and left
    undeliverable.

    Opening the modal is itself a reply (a `views.open` call needing the
    bot token), so the slash command is a request "whose handling would
    require the bot's reply credential" -- unlike `omni_agent`'s
    `url_verification`, this surface has no request type that can be
    answered without it.
    """
    _require_slack_entry_module()
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _reset_slack_caches()

    response = _post_form(client, _slash_command_form())
    _drain(client)

    _assert_unauthorized(
        response, because="the bot token needed to open the modal is absent"
    )
    assert registrar.calls == []
    assert start_launch.calls == []
    assert slack_api.methods == [], (
        "a slash command was rejected for lack of a reply token, yet a "
        f"Slack Web API call was still made: {slack_api.methods}"
    )


def test_view_submission_is_rejected_when_the_bot_token_is_absent(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: An absent reply credential rejects rather than strands
    (view-submission half).

    Submitting the modal needs the bot token too -- the outcome, success or
    rejection, is always delivered as a message (design.md Decision 6), so
    there is no submission this surface could acknowledge and then strand.
    """
    _require_slack_entry_module()
    monkeypatch.delenv(BOT_TOKEN_VAR, raising=False)
    _reset_slack_caches()

    response = _post_form(client, _view_submission_form())
    _drain(client)

    _assert_unauthorized(
        response,
        because="the bot token needed to deliver the outcome message is absent",
    )
    # SPECIFIED: rejected rather than persisted.
    assert registrar.calls == []
    assert start_launch.calls == []
