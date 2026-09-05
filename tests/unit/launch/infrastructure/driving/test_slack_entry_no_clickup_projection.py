"""`launch-entry`: entry never projects work into ClickUp.

Derived strictly from the delta spec at
`openspec/changes/start-launch-from-slack/specs/launch-entry/spec.md`,
without reading the implementation. Covers, from the ADDED requirement
"Entry never projects work":

- Scenario: A started launch touches no external tracker

The second half of that scenario -- "the launch is picked up by the
completion loop's next pass with no involvement from this surface" -- is a
statement about a different capability's (`launch-clickup-sync`) own
convergence behaviour, already specified and tested there; nothing this
surface does or does not do can make that pass involve it, so there is
nothing further to assert about it here beyond the first half: that this
surface itself makes no ClickUp call.

## The interface under test does not exist yet, and its shape is INVENTED

See `test_slack_entry_request_verification.py`'s module docstring for the
route, env vars, and cache-reset assumptions shared by every file in this
directory. Additionally INVENTED here:

- The real ClickUp client is `commerce_ops.shared.infrastructure.driven
  .clickup_client`, exposing `create_task`/`update_task`
  (`tests/unit/shared/infrastructure/driven/test_clickup_client.py`'s own
  module docstring names these as `tasks.md`/`design.md`-fixed, from
  `add-clickup-task-client`, not invented by this file). Patching both to
  fail loudly if called is a stronger guarantee than only recording calls:
  a call this surface should never make is caught even if it would have
  raised for an unrelated reason (e.g. a missing credential) before this
  test could observe it as "called".
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

from commerce_ops.launch.domain.launch_playbook import LaunchPlaybook
from commerce_ops.shared.infrastructure.driven import clickup_client
from tests.support.fakes import FakePlaybookRepository
from tests.support.fakes import FakeSlackResponse as _FakeSlackResponse

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


class _RecordingSlackApi:
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


class _ForbiddenClickUpCall(AssertionError):
    """Raised by the patched ClickUp client functions if entry ever calls
    them -- a distinct type so a failure here cannot be confused with any
    other assertion failure in the same test."""


async def _forbidden_create_task(*args: Any, **kwargs: Any) -> Any:
    raise _ForbiddenClickUpCall(
        f"launch-entry called clickup_client.create_task{args!r}{kwargs!r}; "
        "'Entry never projects work' forbids this surface from creating, "
        "updating, or deleting anything in ClickUp"
    )


async def _forbidden_update_task(*args: Any, **kwargs: Any) -> Any:
    raise _ForbiddenClickUpCall(
        f"launch-entry called clickup_client.update_task{args!r}{kwargs!r}; "
        "'Entry never projects work' forbids this surface from creating, "
        "updating, or deleting anything in ClickUp"
    )


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


def _served_playbook() -> LaunchPlaybook:
    """The playbook this file serves, lifted out of the double it used to
    be built inside. `serving` reads it at call time."""
    from commerce_ops.launch.domain.launch_playbook import (
        Gate,
        GateOpening,
        Hazard,
        LaunchPlaybook,
        OffsetAnchor,
        Scope,
        StepDefinition,
        StepKind,
        StepStatus,
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
            name=f"Blocking work holding the {gate} gate",
            gate=gate,
            discipline=next(iter(Discipline)),
            scope=Scope.PRODUCT,
            timing_anchor=OffsetAnchor(days=0),
            blocking=True,
            kind=StepKind.AUTOMATED,
            status=StepStatus.ACTIVE,
            hazard=Hazard.NONE,
            handler="fixture.holding_check",
            provenance=None,
        )
        for gate in gate_order
    )
    return LaunchPlaybook(version="test-v1", gates=gates, steps=steps)


_FakePlaybookRepository = FakePlaybookRepository.serving(_served_playbook)


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


@pytest.fixture(autouse=True)
def forbid_clickup_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clickup_client, "create_task", _forbidden_create_task)
    monkeypatch.setattr(clickup_client, "update_task", _forbidden_update_task)


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


def _view_submission_form() -> dict[str, str]:
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
                    "sku": {"sku": {"type": "plain_text_input", "value": "SKU-0003"}},
                    "name": {"name": {"type": "plain_text_input", "value": "Widget"}},
                    "asin": {"asin": {"type": "plain_text_input", "value": None}},
                    "launch_date": {
                        "launch_date": {"type": "datepicker", "selected_date": None}
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


def _post_view_submission(client: TestClient) -> Any:
    body = urllib.parse.urlencode(_view_submission_form()).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# --------------------------------------------------------------------------
# Scenario: A started launch touches no external tracker
# --------------------------------------------------------------------------


def test_a_successful_submission_makes_no_clickup_call(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
) -> None:
    """Scenario: A started launch touches no external tracker.

    WHEN a submission succeeds
    THEN no ClickUp call was made by the entry surface.

    (The second AND clause -- that the completion loop's next pass picks
    the launch up -- is `launch-clickup-sync`'s own specified and tested
    behaviour, not observable from this surface; see the module docstring.)
    """
    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200

    # Precondition: the submission really did succeed, so "no ClickUp
    # call" is not vacuously true of a request that never got that far.
    assert len(registrar.calls) == 1, (
        "the catalog registrar was not called; this test cannot establish "
        "anything about a successful submission if the submission itself "
        "never succeeded"
    )
    assert len(start_launch.calls) == 1, (
        "start_launch was not called; this test cannot establish anything "
        "about a successful submission if the submission itself never "
        "succeeded"
    )

    # SPECIFIED: no ClickUp call was made. The `forbid_clickup_calls`
    # fixture (autouse) replaces `clickup_client.create_task` and
    # `.update_task` with functions that raise `_ForbiddenClickUpCall`
    # synchronously if either is ever invoked. A submission that reaches
    # this assertion without that exception having propagated through the
    # request -- observable as the 200 already asserted above, since an
    # unhandled exception in the listener would not leave a clean
    # acknowledgement -- has therefore made no ClickUp call.
    assert response.status_code == 200, (
        "if a ClickUp call had been made, the forbid_clickup_calls fixture "
        "would have raised _ForbiddenClickUpCall inside the listener"
    )
