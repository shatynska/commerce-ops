"""`launch-entry`: a missing required field keeps the modal open.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Covers, from the ADDED requirement
"Rejections are surfaced where the user is":

- Scenario: A missing required field keeps the modal open

The requirement's other scenario -- "A duplicate SKU is rejected with
nothing persisted" -- is a domain rejection established only at persistence
time (design.md Decision 4), and both halves of what it states ("the user
is told the SKU is already registered" and "no second product and no
launch is persisted") are only faithfully observable against the real
`DuplicateSkuError` `product-catalog` raises and a real store; guessing
that exception's constructor shape to raise it from a mock here would risk
a test that passes for the wrong reason. It lives in
`tests/integration/launch/test_slack_entry_start.py` instead, exercised
against real collaborators.

## The interface under test does not exist yet, and its shape is INVENTED

See `test_slack_entry_request_verification.py`'s module docstring for the
route, env vars, and cache-reset assumptions shared by every file in this
directory. Additionally INVENTED here:

- A missing plain-text field arrives in the view-submission payload as
  `"value": None` on its `plain_text_input` element -- the shape Slack's
  own API sends for an untouched text input, and the only way "missing" is
  distinguishable from "submitted empty" in a view-submission payload.
- Bolt's own `response_action: errors` envelope shape (`{"response_action":
  "errors", "errors": {<block_id>: <message>}}"`) is Slack's documented
  contract, not invented by this file, but the block id it error-blames is
  not named by any artifact, so the assertion below checks that at least
  one error is attached rather than which key it is attached to.
"""

from __future__ import annotations

import importlib
import inspect
import json
import time
import urllib.parse
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

SLACK_ENTRY_PATH = "/product_agent/slack/events"  # ASSUMED
SIGNING_SECRET = "test-product-agent-signing-secret"  # not a real credential
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"  # not a real credential

SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"  # ASSUMED

CALLBACK_ID = "start_launch_modal"  # ASSUMED

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

REGISTRAR_ATTRIBUTES: tuple[str, ...] = (
    "register_catalog_product",
    "catalog_registrar",
    "register_product",
)


# --------------------------------------------------------------------------
# Test doubles
# --------------------------------------------------------------------------


class _FakeSlackResponse(dict[str, Any]):
    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class _RecordingSlackApi:
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


class _RecordingRegistrar:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return None


class _RecordingStartLaunch:
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


@asynccontextmanager
async def _fake_transaction() -> AsyncIterator[None]:
    """Stands in for the adapter's `transaction()` provider.

    Yields `None`: the collaborators that would use the session -- the
    catalog registrar and `start_launch` -- are themselves substituted in
    every test here, so nothing issues a query. This keeps the file
    unit-tier: no `DATABASE_URL`, no Postgres.

    Fixture correction made while implementing tasks.md 2.2, following the
    convention `test_clickup_webhook.py` records for the same seam. It adds
    a substitute for a real collaborator; it weakens no assertion.
    """
    yield None


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module(SLACK_ENTRY_MODULE)
    monkeypatch.setattr(module, "transaction", _fake_transaction)


class _FakePlaybookRepository:
    """The served-playbook read (`move-playbook-steps-to-postgres`),
    substituted like the other collaborator globals: serves a minimal
    coherent playbook (every gate held, as the gate-holding floor
    requires) without touching any database."""

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> Any:
        from commerce_ops.launch.domain.launch_playbook import (
            Binding,
            ExecutionMode,
            Gate,
            GateOpening,
            Hazard,
            LaunchPlaybook,
            OffsetAnchor,
            Scope,
            StepDefinition,
        )
        from commerce_ops.shared.domain.discipline import Discipline

        gate_order = (
            "commit",
            "order",
            "listable",
            "stock-ready",
            "live",
            "ignition",
            "phase-one-complete",
            "graduated",
        )
        confirmation = {"commit", "order", "phase-one-complete", "graduated"}
        gates = tuple(
            Gate(
                identifier=identifier,
                position=position,
                opening=(
                    GateOpening.REQUIRES_CONFIRMATION
                    if identifier in confirmation
                    else GateOpening.AUTOMATIC
                ),
            )
            for position, identifier in enumerate(gate_order, start=1)
        )
        steps = tuple(
            StepDefinition(
                identifier=f"hold.{gate}",
                description=f"Blocking work holding the {gate} gate",
                gate=gate,
                discipline=next(iter(Discipline)),
                scope=Scope.PRODUCT,
                timing_anchor=OffsetAnchor(days=0),
                binding=Binding.FRAMEWORK,
                blocking=True,
                execution=ExecutionMode.AUTOMATED,
                hazard=Hazard.NONE,
                rule_policy="Held until the automated check reports green.",
                provenance=None,
            )
            for gate in gate_order
        )
        return LaunchPlaybook(version="test-v1", gates=gates, steps=steps)


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.import_module(SLACK_ENTRY_MODULE),
        "PlaybookRepository",
        _FakePlaybookRepository,
    )


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
    fake = _RecordingRegistrar()
    module = _require_slack_entry_module()
    for name in REGISTRAR_ATTRIBUTES:
        if hasattr(module, name):
            monkeypatch.setattr(module, name, fake)
    return fake


@pytest.fixture()
def start_launch(monkeypatch: pytest.MonkeyPatch) -> _RecordingStartLaunch:
    fake = _RecordingStartLaunch()
    module = _require_slack_entry_module()
    if hasattr(module, "start_launch"):
        monkeypatch.setattr(module, "start_launch", fake)
    return fake


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
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
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Slack-Request-Timestamp": stamp,
        "X-Slack-Signature": signature,
    }


def _view_submission_form(
    *,
    sku: str | None = "SKU-0001",
    name: str | None = "Widget",
    asin: str | None = None,
    launch_date: str | None = None,
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
                    "asin": {"asin": {"type": "plain_text_input", "value": asin}},
                    "launch_date": {
                        "launch_date": {
                            "type": "datepicker",
                            "selected_date": launch_date,
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


def _post_view_submission(client: TestClient, **field_overrides: Any) -> Any:
    form = _view_submission_form(**field_overrides)
    body = urllib.parse.urlencode(form).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# --------------------------------------------------------------------------
# Requirement: Rejections are surfaced where the user is
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing_field",
    [
        pytest.param({"sku": None}, id="missing-sku"),
        pytest.param({"name": None}, id="missing-name"),
    ],
)
def test_a_missing_required_field_keeps_the_modal_open(
    missing_field: dict[str, None],
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: A missing required field keeps the modal open.

    WHEN the modal is submitted without a SKU or without a name
    THEN the modal stays open showing the error on that field, and nothing
    is persisted.
    """
    response = _post_view_submission(client, **missing_field)
    _drain(client)

    # SPECIFIED: the modal stays open. Bolt's `response_action: errors`
    # envelope is how a Bolt listener keeps a modal open in reply to a
    # view_submission -- returning any other `response_action` (or none)
    # closes it.
    assert response.status_code == 200, (
        f"expected the request to be acknowledged with 200, got {response.status_code}"
    )
    body = response.json()
    assert body.get("response_action") == "errors", (
        "expected a response_action of 'errors' to keep the modal open for "
        f"a missing required field, got: {body}"
    )
    errors = body.get("errors")
    assert isinstance(errors, dict) and errors, (
        f"expected at least one field-level error attached, got: {errors!r}"
    )

    # SPECIFIED: nothing is persisted -- validation is checked before any
    # collaborator is touched (design.md Decision 4).
    assert registrar.calls == [], (
        "the catalog registrar was called despite a missing required field"
    )
    assert start_launch.calls == [], (
        "start_launch was called despite a missing required field"
    )
    # DERIVED: no outcome message either -- there is no outcome yet, the
    # modal is still open waiting for a corrected resubmission.
    assert slack_api.posts == []


def test_a_complete_submission_is_not_rejected_inline(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """DERIVED positive control for the test above: without it, an
    implementation that always returns `response_action: errors` -- or
    never calls the collaborators at all -- would pass every test in this
    file for the wrong reason.
    """
    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200
    body: Any = None
    if response.content:
        try:
            body = response.json()
        except ValueError:
            body = None
    assert not (isinstance(body, dict) and body.get("response_action") == "errors"), (
        f"a submission with every required field present was rejected inline: {body}"
    )

    # SPECIFIED (requirement statement): submitting the modal registers the
    # product and starts its launch.
    assert len(registrar.calls) == 1, (
        "expected the catalog registrar to be called exactly once for a "
        f"complete submission, observed {len(registrar.calls)} call(s)"
    )
    assert len(start_launch.calls) == 1, (
        "expected start_launch to be called exactly once for a complete "
        f"submission, observed {len(start_launch.calls)} call(s)"
    )
