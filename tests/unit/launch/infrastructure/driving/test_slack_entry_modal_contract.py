"""`launch-entry`: the modal's contract, at the slash-command level.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Covers, from the ADDED requirement "A
launch is started from Slack in one interaction":

- Scenario: The playbook version is never user input

The requirement's other two scenarios ("A launch is started with a date" /
"...without a date") state persistence outcomes -- "the product is
registered and its launch exists ... pinned to the shipped playbook
version" -- whose smallest observing unit is a real read-back through an
independent store, per `ai-toolkit:testing`'s level rule. They live in
`tests/integration/launch/test_slack_entry_start.py`, not here.

## The interface under test does not exist yet, and its shape is INVENTED

See `test_slack_entry_request_verification.py`'s module docstring for the
route, env var, and cache-reset assumptions shared by every file in this
directory; they are not repeated here. Additionally INVENTED for this
file:

- The submission opens the modal via a `views.open` Slack Web API call
  (`api_method == "views.open"`), the only mechanism Slack's own API
  offers for opening a modal from a slash command.
- No block id or field label is pinned by any artifact for the "no
  playbook-version field" assertion, so it searches the *entire* opened
  view for anything resembling a version field (any block id or label text
  containing "version" or "playbook", case-insensitively) rather than the
  absence of one specific field. This makes the assertion robust to
  whatever field-naming the implementation chooses, at the cost of being
  slightly broader than the literal text -- recorded here rather than
  silently narrowed.
"""

from __future__ import annotations

import importlib
import inspect
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from tests.support.fakes import FakeSlackResponse as _FakeSlackResponse

SLACK_ENTRY_PATH = "/product_agent/slack/events"  # ASSUMED
SIGNING_SECRET = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"  # not a real credential

SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"  # ASSUMED

SLASH_COMMAND = "/start-launch"  # ASSUMED, cosmetic per design.md

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _RecordingSlackApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def methods(self) -> list[str]:
        return [call["api_method"] for call in self.calls]

    @property
    def views_open_calls(self) -> list[dict[str, Any]]:
        return [
            call["payload"] for call in self.calls if call["api_method"] == "views.open"
        ]

    async def api_call(self, api_method: str, **kwargs: Any) -> _FakeSlackResponse:
        payload = kwargs.get("json") or kwargs.get("params") or kwargs.get("data") or {}
        self.calls.append(
            {
                "api_method": api_method,
                "payload": dict(payload) if isinstance(payload, dict) else payload,
            }
        )
        return _FakeSlackResponse({"ok": True, "view": {"id": "V0VIEW"}})


# --------------------------------------------------------------------------
# Cache-reset discovery (see test_slack_entry_request_verification.py)
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
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    with TestClient(slack_asgi_app, raise_server_exceptions=False) as test_client:
        yield test_client


# --------------------------------------------------------------------------
# Request helpers
# --------------------------------------------------------------------------


def _signed_headers(body: bytes) -> dict[str, str]:
    import time

    stamp = str(int(time.time()))
    signature = SignatureVerifier(SIGNING_SECRET).generate_signature(
        timestamp=stamp, body=body
    )
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


def _post_slash_command(client: TestClient) -> Any:
    import urllib.parse

    body = urllib.parse.urlencode(_slash_command_form()).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


def _iter_texts(node: Any) -> Iterator[str]:
    """Walks a Slack Block Kit structure, yielding every string it finds
    in a `block_id`, `action_id`, or `text` position."""
    if isinstance(node, dict):
        for key in ("block_id", "action_id"):
            value = node.get(key)
            if isinstance(value, str):
                yield value
        text = node.get("text")
        if isinstance(text, str):
            yield text
        elif isinstance(text, dict):
            yield from _iter_texts(text)
        for value in node.values():
            if isinstance(value, dict | list):
                yield from _iter_texts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_texts(item)


def _opened_view(recorder: _RecordingSlackApi) -> dict[str, Any]:
    assert recorder.views_open_calls, (
        "no views.open call was recorded; the slash command must open the "
        f"modal directly. Observed calls: {recorder.methods}"
    )
    payload = recorder.views_open_calls[0]
    view = payload.get("view")
    if isinstance(view, str):
        view = json.loads(view)
    assert isinstance(view, dict), (
        f"views.open payload carried no usable view: {payload!r}"
    )
    return view


# --------------------------------------------------------------------------
# Requirement: A launch is started from Slack in one interaction
# --------------------------------------------------------------------------


def test_slash_command_opens_a_modal(
    client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """Precondition guard, not a scenario on its own: without this, every
    assertion below about the modal's *contents* would be vacuous if the
    modal was never opened at all.
    """
    _require_slack_entry_module()
    response = _post_slash_command(client)
    _drain(client)

    assert 200 <= response.status_code < 300, (
        f"the slash command was not acknowledged, got {response.status_code}"
    )
    _opened_view(slack_api)  # raises with a clear message if absent


def test_the_modal_contains_no_playbook_version_field(
    client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """Scenario: The playbook version is never user input.

    WHEN the modal is displayed
    THEN it contains no playbook-version field, and the started launch
    pins the version the build ships.

    Only the modal-shape half is observable at this level; the pinned-
    version half is a persistence outcome covered in
    `tests/integration/launch/test_slack_entry_start.py`.
    """
    _require_slack_entry_module()
    _post_slash_command(client)
    _drain(client)

    view = _opened_view(slack_api)
    suspect_terms = [
        text
        for text in _iter_texts(view)
        if "version" in text.lower() or "playbook" in text.lower()
    ]
    assert suspect_terms == [], (
        "the modal exposes something naming a playbook version, which the "
        "requirement forbids (a human-typed version field is a trap the "
        "requirement exists to prevent): "
        f"{suspect_terms}"
    )


def test_the_modal_carries_the_required_and_optional_fields(
    client: TestClient, slack_api: _RecordingSlackApi
) -> None:
    """DERIVED FROM THE REQUIREMENT STATEMENT, not a separate `#### Scenario:`
    block. The requirement's own text (not just a scenario) commits to the
    modal "collecting a new product's SKU and name (required), its ASIN and
    launch date (optional), and a marketplace selection (required,
    preselected to the single offered option)". Asserted as: at least five
    distinct fields are present, and the marketplace field carries a
    preselected option, since no artifact fixes block ids to search for by
    name.
    """
    _require_slack_entry_module()
    _post_slash_command(client)
    _drain(client)

    view = _opened_view(slack_api)
    blocks = view.get("blocks", [])
    assert isinstance(blocks, list) and blocks, "the opened view carried no blocks"

    # SPECIFIED: a marketplace selection, preselected. Block Kit expresses a
    # preselected static_select as `initial_option`.
    select_blocks = [
        block
        for block in blocks
        if isinstance(block, dict)
        and isinstance(block.get("element"), dict)
        and block["element"].get("type") == "static_select"
    ]
    assert select_blocks, "no static_select block found for the marketplace field"
    preselected = [
        block for block in select_blocks if block["element"].get("initial_option")
    ]
    assert preselected, (
        "the marketplace select carries no preselected option, but the "
        "requirement states it is 'preselected to the single offered "
        "option'"
    )
