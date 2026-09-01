"""A launch is not started against a playbook that cannot hold one.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-entry/spec.md`

Covers, from the ADDED requirement *A launch is not started against a
playbook that cannot hold one*, both scenarios:

- *A start against an unready playbook is refused*
- *A start against a ready playbook is unaffected*

## Level

The Slack route, as every other file in this directory establishes for this
capability. The requirement is stated over "the modal is submitted", and
what it fixes is *where* the rejection surfaces — "to the submitting user
... It SHALL NOT be reported as a malformed field" — which only the route
can exhibit. Nothing below it can tell a DM from a `response_action:
errors` envelope.

## What "neither the product nor a launch is persisted" is read as here

As *the collaborators that would persist them were never called*. A mocked
registrar can only satisfy "nothing is persisted" vacuously, so this file
asserts the stronger, observable thing instead: the refusal happens before
either collaborator is reached. That is the same division
`test_slack_entry_ack_and_failure_visibility.py` records, and the real
persistence assertion for this capability lives in
`tests/integration/launch/test_slack_entry_start.py`.

## What is fixed, and what is INVENTED

Fixed by the artifacts: that `slack_entry` refuses the start, reports to the
submitting user with the unheld gates named, and persists neither product
nor launch (`tasks.md` 4.1); and `PlaybookNotReadyError` as the refusal's
type.

INVENTED, and transcribed from
`test_slack_entry_ack_and_failure_visibility.py` rather than re-derived so a
correction there is the correction here: the route path, the env var names,
the callback id, the DM being a `chat.postMessage` whose `channel` is the
submitting user's id, and the collaborator names substituted.
Additionally INVENTED here: `PlaybookNotReadyError`'s constructor keywords,
probed by `_build_not_ready()`.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import importlib
import inspect
import json
import time
import urllib.parse
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from commerce_ops.launch.domain import launch_playbook as playbook_module
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

SLACK_ENTRY_PATH: Final = "/product_agent/slack/events"
SIGNING_SECRET: Final = "test-product-agent-signing-secret"
BOT_TOKEN: Final = "xoxb-test-product-agent-not-a-real-token"

SIGNING_SECRET_VAR: Final = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR: Final = "PRODUCT_AGENT_SLACK_BOT_TOKEN"

CALLBACK_ID: Final = "start_launch_modal"
SUBMITTER_ID: Final = "U0SUBMITTER"

SLACK_ENTRY_MODULE: Final = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES: Final = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
    # `ensure_launch_thread` posts the anchor through its own `lru_cache`d
    # `AsyncWebClient`, built while `AsyncWebClient.api_call` is patched.
    "commerce_ops.launch.application.thread_establishment",
)

LAUNCHES_CHANNEL_VAR: Final = "PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"
LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"  # not a real channel
THREAD_TS: Final = "1700000000.000100"

REGISTRAR_ATTRIBUTES: Final = (
    "register_catalog_product",
    "catalog_registrar",
    "register_product",
)

SPECIFIED_GATE_ORDER: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

# Two, not one: the requirement says the message "names those gates",
# plural, and a message naming only the first would pass a single-gate
# fixture.
UNHELD_GATES: Final = ("ignition", "graduated")


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=0),
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "handler": "fixture.holding_check",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _ready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


def _unready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=tuple(
            _hold(
                gate,
                status=StepStatus.DRAFT if gate in UNHELD_GATES else StepStatus.ACTIVE,
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
    )


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": UNHELD_GATES}),
        ((), {"playbook": playbook, "unheld_gates": UNHELD_GATES}),
        ((UNHELD_GATES, playbook), {}),
        ((playbook, UNHELD_GATES), {}),
    )
    for args, kwargs in attempts:
        try:
            return error(*args, **kwargs)  # type: ignore[no-any-return]
        except TypeError:
            continue
    pytest.fail(
        "could not construct PlaybookNotReadyError under any probed "
        "signature; correct `_build_not_ready` to the implemented one"
    )


# ---------------------------------------------------------------------------
# Test doubles — transcribed from
# `test_slack_entry_ack_and_failure_visibility.py`
# ---------------------------------------------------------------------------


class _FakeSlackResponse(dict[str, Any]):
    @property
    def data(self) -> dict[str, Any]:
        return dict(self)


class _RecordingSlackApi:
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
        # `ts` because `ensure_launch_thread` reads `response["ts"]`; without
        # it the `KeyError` is swallowed into the fallback DM and this file's
        # `assert slack_api.posts` passes without the thread ever existing.
        return _FakeSlackResponse({"ok": True, "ts": THREAD_TS})


class _RecordingCall:
    def __init__(self) -> None:
        self.calls: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return None


@asynccontextmanager
async def _fake_transaction() -> AsyncIterator[None]:
    yield None


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


def _reset_slack_caches() -> None:
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        try:
            module = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        for value in list(vars(module).values()):
            cache_clear = getattr(value, "cache_clear", None)
            if callable(cache_clear):
                cache_clear()
            elif _looks_like_a_reset_hook(value):
                value()


def _entry_module() -> Any:
    return importlib.import_module(SLACK_ENTRY_MODULE)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _ThreadlessLaunch:
    """The launch `ensure_launch_thread` reads: no thread established yet."""

    def __init__(self) -> None:
        self.slack_thread_id: str | None = None
        self.launch_date = None
        self.submitter = SUBMITTER_ID


class _FakeLaunchStore:
    """`LaunchRepository`, for the thread-establishment read and write.

    Read twice per establishment -- once inside `ensure_launch_thread`, once
    for `resolve_mention_target` -- so the thread reference written by the
    first must be visible to the second. `product_id` is ignored: the
    registrar double returns `None`, so there is no identity to key on.
    """

    launch: _ThreadlessLaunch

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    async def get_by_product_id(self, product_id: Any) -> Any:
        return type(self).launch

    async def save(self, launch: Any) -> None:
        """Persists the thread reference; absent, the `AttributeError` is
        swallowed and the fallback DM answers this file's assertion."""


async def _no_lock(*args: Any, **kwargs: Any) -> None:
    """`hold_launch_thread_establishment_lock`, which needs a real session."""


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_entry_module(), "transaction", _fake_transaction)

    # Substituting `slack_entry.transaction` above does not reach
    # `establish_thread_and_resolve_mention`, which opens its own
    # `transaction()` in its own module. Until this was added, that call
    # raised `RuntimeError: DATABASE_URL is not set` on every run of this
    # file, `slack_entry` swallowed it, and the fallback direct message
    # satisfied `assert slack_api.posts` -- so this file's tests passed
    # while observing none of the threaded delivery they are about.
    #
    # The seam substituted is the one beneath the preamble, not
    # `establish_thread_and_resolve_mention` itself: substituting the
    # preamble would make these tests observe a double where the delivery
    # should be, which is the deficiency being removed rather than a fix
    # for it.
    delivery = importlib.import_module(
        "commerce_ops.launch.infrastructure.driven.launch_thread_delivery"
    )
    _FakeLaunchStore.launch = _ThreadlessLaunch()
    monkeypatch.setattr(delivery, "transaction", _fake_transaction)
    monkeypatch.setattr(delivery, "LaunchRepository", _FakeLaunchStore)
    monkeypatch.setattr(delivery, "hold_launch_thread_establishment_lock", _no_lock)


@pytest.fixture(autouse=True)
def slack_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    # The anchor and the confirmation reply both land in the launches
    # channel; `launches_channel()` reads this variable directly.
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)
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
def registrar(monkeypatch: pytest.MonkeyPatch) -> _RecordingCall:
    module = _entry_module()
    fake = _RecordingCall()
    installed = [name for name in REGISTRAR_ATTRIBUTES if hasattr(module, name)]
    assert installed, (
        f"{module.__name__} exposes none of {REGISTRAR_ATTRIBUTES}, so this "
        "file cannot tell a product that was registered from one that was not"
    )
    for name in installed:
        monkeypatch.setattr(module, name, fake)
    return fake


@pytest.fixture()
def start_launch(monkeypatch: pytest.MonkeyPatch) -> _RecordingCall:
    module = _entry_module()
    fake = _RecordingCall()
    monkeypatch.setattr(module, "start_launch", fake)
    return fake


def install_playbook_read(
    monkeypatch: pytest.MonkeyPatch, *, refusing_with: LaunchPlaybook | None
) -> None:
    class _Repository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str = "") -> LaunchPlaybook:
            if refusing_with is not None:
                raise _build_not_ready(refusing_with)
            return _ready_playbook()

    monkeypatch.setattr(_entry_module(), "PlaybookRepository", _Repository)


@pytest.fixture()
def client(slack_asgi_app: Any) -> Iterator[TestClient]:
    with TestClient(slack_asgi_app, raise_server_exceptions=False) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


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
    payload = {
        "type": "view_submission",
        "team": {"id": "T0TEAM", "domain": "test-team"},
        "user": {"id": SUBMITTER_ID, "username": "submitter"},
        "api_app_id": "A0PRODUCTAGENT",
        "token": "verification-token",
        "trigger_id": "1234.5678.abcdef",
        "view": {
            "id": "V0VIEW",
            "type": "modal",
            "callback_id": CALLBACK_ID,
            "private_metadata": "",
            "hash": "156772938.1827394",
            "state": {
                "values": {
                    "sku": {"sku": {"type": "plain_text_input", "value": "SKU-0002"}},
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
    return {"payload": json.dumps(payload)}


def _post_view_submission(client: TestClient) -> Any:
    body = urllib.parse.urlencode(_view_submission_form()).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# ---------------------------------------------------------------------------
# Requirement: A launch is not started against a playbook that cannot hold
# one
# ---------------------------------------------------------------------------


def test_a_start_against_an_unready_playbook_is_refused(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingCall,
    start_launch: _RecordingCall,
) -> None:
    """Scenario: A start against an unready playbook is refused.

    WHEN the modal is submitted while one or more gates hold no active
    blocking step
    THEN the user is told the playbook cannot yet hold a launch, and the
    message names those gates
    AND neither the product nor a launch is persisted.

    "Neither is persisted" is asserted as *neither collaborator was
    reached* — see the module docstring. That is the stronger observable
    claim at this level, and it is what makes the refusal happen before
    persistence rather than being rolled back after it.
    """
    install_playbook_read(monkeypatch, refusing_with=_unready_playbook())

    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200, (
        f"the submission was not acknowledged: {response.status_code}"
    )

    # SPECIFIED: the user is told — to the submitting user, the way other
    # domain rejections established at persistence time are surfaced.
    assert len(slack_api.posts) == 1, (
        "expected exactly one message delivered to the submitting user, "
        f"observed: {slack_api.posts}"
    )
    posted = slack_api.posts[0]
    assert posted.get("channel") == SUBMITTER_ID, (
        "the refusal must reach the submitting user directly, got "
        f"channel={posted.get('channel')!r}"
    )

    # SPECIFIED: the message names those gates.
    text = str(posted.get("text") or "") + json.dumps(posted.get("blocks") or [])
    for gate in UNHELD_GATES:
        assert gate in text, (
            f"the refusal message does not name the unheld gate {gate!r}, so "
            "it reports an internal failure rather than the work needed; "
            f"message was: {text!r}"
        )

    # SPECIFIED: neither the product nor a launch is persisted.
    assert registrar.calls == [], (
        "the product was registered despite the playbook being unable to hold a launch"
    )
    assert start_launch.calls == [], "a launch was started against an unready playbook"


def test_the_refusal_is_not_reported_as_a_malformed_field(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingCall,
    start_launch: _RecordingCall,
) -> None:
    """Requirement statement: "It SHALL NOT be reported as a malformed
    field, because no field the user filled in caused it."

    SPECIFIED by the requirement's own second paragraph, which states this
    as a prohibition rather than in a scenario. Bolt's `response_action:
    errors` envelope is how this adapter reports a malformed field
    (`test_slack_entry_field_validation.py`), so its *absence* is what the
    prohibition amounts to here.

    Recorded as its own test so that a refusal routed to the field-error
    envelope fails visibly, rather than inside the DM assertion above.
    """
    install_playbook_read(monkeypatch, refusing_with=_unready_playbook())

    response = _post_view_submission(client)
    _drain(client)

    body: Any
    try:
        body = response.json()
    except ValueError:
        body = None

    assert not (isinstance(body, dict) and body.get("response_action") == "errors"), (
        "the unready-playbook refusal was reported as a malformed field; no "
        f"field the user filled in caused it. Response body: {body!r}"
    )


def test_a_start_against_a_ready_playbook_is_unaffected(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingCall,
    start_launch: _RecordingCall,
) -> None:
    """Scenario: A start against a ready playbook is unaffected.

    WHEN the modal is submitted while every gate holds at least one active
    blocking step
    THEN the launch starts exactly as it does today, recording the served
    playbook's version identifier.

    The control for the refusal above: without it, an adapter that refused
    every submission would satisfy both tests there. The version identifier
    is asserted as what `start_launch` was handed, since recording it is
    the use case's own doing and is covered against a real database in
    `tests/integration/launch/test_slack_entry_start.py`.
    """
    install_playbook_read(monkeypatch, refusing_with=None)

    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200
    # SPECIFIED: the launch starts exactly as it does today.
    assert len(start_launch.calls) == 1, (
        "a submission against a ready playbook did not start a launch: "
        f"{start_launch.calls}"
    )
    assert registrar.calls, "the product was not registered against a ready playbook"
    # SPECIFIED: the user is told nothing that reads as a refusal — a
    # started launch's own confirmation is this capability's existing
    # behaviour and is not re-asserted here.
    assert slack_api.posts, "the submitting user heard nothing at all"

    # DELIBERATELY UNTESTED at this level: "recording the served playbook's
    # version identifier". The recording is `start_launch`'s, over a
    # collaborator this file substitutes, so asserting it here would assert
    # the double. It is observable against real persistence and is covered
    # in `tests/integration/launch/test_slack_entry_start.py`, which reads
    # the stored version back out of `playbook_step_set`.
