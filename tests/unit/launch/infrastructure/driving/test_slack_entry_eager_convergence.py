"""`start_launch` triggers an eager convergence, and a failed one costs it
nothing.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A launch is converged eagerly at start
and at a gate crossing*, the three scenarios stated over this call site:

- *A newly started launch's first tasks appear without waiting for the
  pass* — the wiring half: that a successful `start_launch` triggers the
  eager helper for the launch it started. What the helper itself then does
  with a real `converge_launch` is `test_eager_convergence_helper.py`'s.
- *A failed eager run does not fail the action that triggered it* — this
  call site's own half: the Slack confirmation and its acknowledgement are
  unaffected by a raising helper.
- *The eager run stands down exactly as the pass does* — inherited rather
  than re-implemented (`design.md`): `start_launch` already refuses while
  the served playbook cannot hold a launch, before this change adds
  anything after it, so the eager helper is never reached in that case.

`tasks.md` 5.1's cadence-string fix is covered separately, in
`test_slack_entry_cadence_wording.py`.

The integration-tier realization — that tasks actually exist in ClickUp
without the periodic pass having run — is
`tests/integration/launch/test_eager_convergence_live.py`'s.

See `test-manifest.md` at the change root for the full accounting.

## Level

The Slack route, over in-memory doubles for `start_launch`, the catalog
registrar and the eager helper — the level every other file in this
directory already holds for this surface
(`test_slack_entry_no_clickup_projection.py`,
`test_slack_entry_unready_playbook.py`). Nothing below the route can
observe "a submission triggered the helper" or "a failed helper did not
touch the confirmation", both of which are properties of what the route
does after `start_launch` returns.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that `slack_entry.py` calls the eager
helper after `start_launch` commits, following `ack()` (`tasks.md` 3.3;
`design.md` — Decision: dispatch differs by call site, Bolt listeners
"call the helper by awaiting it directly after `ack()`").

INVENTED, and recorded in the manifest as unresolved project questions:

- The eager helper's name on `slack_entry.py` (`_HELPER_NAMES`) — kept in
  step with `test_eager_convergence_helper.py`'s own `_HELPER_NAMES`,
  which is the correction point for the name itself; this file's own
  correction point is only which attribute on *this* module carries it.
- Every route mechanic — the path, env vars, callback id, the cache-reset
  convention, the fake transaction and served-playbook fixtures — is
  transcribed from `test_slack_entry_no_clickup_projection.py`, which
  records the provenance of each; correcting any of it is a fixture
  correction there as much as here.

## Expected first-run state

`slack_entry.py` calls no eager helper yet (`tasks.md` 3.3), so every test
here is expected to fail on an **absent target** — `_helper_name`'s loud
failure. Per `ai-toolkit:testing` that establishes absence only: none of
the assertions below has been exercised.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import importlib
import inspect
import json
import time
import urllib.parse
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Final

import pytest
from fastapi.testclient import TestClient
from slack_sdk.signature import SignatureVerifier

from tests.support.fakes import FakeSlackResponse as _FakeSlackResponse

SLACK_ENTRY_PATH: Final = "/product_agent/slack/events"
SIGNING_SECRET: Final = "test-product-agent-signing-secret"
BOT_TOKEN: Final = "xoxb-test-product-agent-not-a-real-token"

SIGNING_SECRET_VAR: Final = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR: Final = "PRODUCT_AGENT_SLACK_BOT_TOKEN"

CALLBACK_ID: Final = "start_launch_modal"

SLACK_ENTRY_MODULE: Final = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES: Final = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

REGISTRAR_ATTRIBUTES: Final = (
    "register_catalog_product",
    "catalog_registrar",
    "register_product",
)

#: Kept in step with `test_eager_convergence_helper.py`'s own
#: `_HELPER_NAMES`, which is the correction point for the name itself.
_HELPER_NAMES: Final = (
    "converge_launch_eagerly",
    "eager_converge_launch",
    "converge_launch_now",
    "converge_one_launch_eagerly",
    "eagerly_converge_launch",
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _RecordingSlackApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

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


@dataclass
class _Timeline:
    events: list[str] = field(default_factory=list)

    def note(self, event: str) -> None:
        self.events.append(event)


class _RecordingStartLaunch:
    def __init__(self, timeline: _Timeline) -> None:
        self.calls: list[Any] = []
        self._timeline = timeline

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        self._timeline.note("start_launch")
        return None


class _RecordingHelper:
    def __init__(self, timeline: _Timeline, *, failing: bool = False) -> None:
        self.calls: list[Any] = []
        self._timeline = timeline
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        self._timeline.note("eager")
        if self.failing:
            raise RuntimeError("simulated eager-convergence failure")


# ---------------------------------------------------------------------------
# Cache-reset discovery — transcribed from
# `test_slack_entry_no_clickup_projection.py`
# ---------------------------------------------------------------------------


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
            f"{SLACK_ENTRY_MODULE} does not exist ({exc}); this test's target "
            "is absent."
        )


def _helper_name(module: Any) -> str:
    for name in _HELPER_NAMES:
        if callable(getattr(module, name, None)):
            return name
    pytest.fail(
        f"{module.__name__} exposes no eager-convergence helper under any of "
        f"{_HELPER_NAMES}; `tasks.md` 3.3 adds it. This is the absent-target "
        "state, not a defect in this file — do not add the attribute to make "
        "this pass."
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _fake_transaction() -> AsyncIterator[None]:
    """Stands in for the adapter's `transaction()` provider — transcribed
    from `test_slack_entry_no_clickup_projection.py`."""
    yield None


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    module = importlib.import_module(SLACK_ENTRY_MODULE)
    monkeypatch.setattr(module, "transaction", _fake_transaction)


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> Any:
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


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.import_module(SLACK_ENTRY_MODULE),
        "PlaybookRepository",
        _FakePlaybookRepository,
    )


class _StubLaunch:
    """The minimum the eager-convergence call site needs to see a launch:
    truthy, and carrying a `product_id` its own error-logging can read.

    Not a real `Launch` domain object — nothing downstream inspects it,
    since the eager helper itself is substituted by `_RecordingHelper`,
    which records whatever it is called with rather than acting on it.
    """

    product_id: Any = None


class _FakeLaunchRepository:
    """Stands in for `LaunchRepository`, so the eager-convergence call
    site's own `get_by_product_id` read succeeds regardless of the
    (fake, `None`-yielding) session `transaction()`/`session()` hand it —
    this file does not otherwise model launch persistence at all, since
    `_RecordingStartLaunch`/`_RecordingRegistrar` return `None` throughout.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    async def get_by_product_id(self, product_id: Any) -> Any:
        return _StubLaunch()


@pytest.fixture(autouse=True)
def launch_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        importlib.import_module(SLACK_ENTRY_MODULE),
        "LaunchRepository",
        _FakeLaunchRepository,
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
def timeline() -> _Timeline:
    return _Timeline()


@pytest.fixture()
def start_launch(
    monkeypatch: pytest.MonkeyPatch, timeline: _Timeline
) -> _RecordingStartLaunch:
    fake = _RecordingStartLaunch(timeline)
    module = _require_slack_entry_module()
    if hasattr(module, "start_launch"):
        monkeypatch.setattr(module, "start_launch", fake)
    return fake


def _install_helper(
    monkeypatch: pytest.MonkeyPatch, timeline: _Timeline, *, failing: bool = False
) -> _RecordingHelper:
    module = _require_slack_entry_module()
    fake = _RecordingHelper(timeline, failing=failing)
    monkeypatch.setattr(module, _helper_name(module), fake)
    return fake


@pytest.fixture()
def helper(monkeypatch: pytest.MonkeyPatch, timeline: _Timeline) -> _RecordingHelper:
    return _install_helper(monkeypatch, timeline)


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
        "user": {"id": "U0SUBMITTER", "username": "submitter"},
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
    return {"payload": json.dumps(payload)}


def _post_view_submission(client: TestClient) -> Any:
    body = urllib.parse.urlencode(_view_submission_form()).encode("utf-8")
    return client.post(SLACK_ENTRY_PATH, content=body, headers=_signed_headers(body))


def _drain(client: TestClient) -> None:
    client.get("/health")


# ---------------------------------------------------------------------------
# Scenario: A newly started launch's first tasks appear without waiting for
# the pass — the wiring half
# ---------------------------------------------------------------------------


def test_a_successful_submission_triggers_the_eager_helper(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
    helper: _RecordingHelper,
    timeline: _Timeline,
) -> None:
    """Scenario: A newly started launch's first tasks appear without
    waiting for the pass.

    WHEN `start_launch` succeeds for a product
    THEN the eager helper is triggered for it, after `start_launch` has
    committed (`tasks.md` 3.3).
    """
    response = _post_view_submission(client)
    _drain(client)

    assert response.status_code == 200
    # Premise: the submission really did succeed.
    assert len(start_launch.calls) == 1, (
        "start_launch was not called; this test cannot establish anything "
        "about a successful start"
    )
    # SPECIFIED-BY-TASKS: the eager helper is triggered.
    assert len(helper.calls) == 1, (
        "a successful start_launch did not trigger the eager-convergence "
        f"helper: {helper.calls!r}"
    )
    # SPECIFIED-BY-TASKS: after start_launch has committed.
    assert timeline.events.index("start_launch") < timeline.events.index("eager"), (
        f"the eager helper ran before start_launch, not after: {timeline.events!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A failed eager run does not fail the action that triggered it
# ---------------------------------------------------------------------------


def test_a_failing_eager_run_does_not_fail_the_submission(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    start_launch: _RecordingStartLaunch,
    timeline: _Timeline,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed eager run does not fail the action that
    triggered it.

    WHEN the eager run raises while converging a launch just started
    THEN the launch start completes and is reported exactly as it would
    have been had the eager run succeeded.

    The helper substituted here raises *past* its own documented
    containment (`tasks.md` 1.1) — the same defence-in-depth this
    repository already applies at `test_advance_and_ask.py`'s sibling
    route test — so what is asserted is that this call site does not rely
    solely on the helper's own catch.
    """
    exploding = _install_helper(monkeypatch, timeline, failing=True)

    response = _post_view_submission(client)
    _drain(client)

    # Premise: the exploding helper really was reached.
    assert len(exploding.calls) == 1, (
        f"the exploding helper was never reached: {exploding.calls!r}"
    )
    # SPECIFIED: the submission is reported exactly as it would have been
    # had the eager run succeeded.
    assert response.status_code == 200, (
        "a failing eager-convergence helper affected the HTTP response to "
        f"the submission: {response.status_code}"
    )
    assert len(start_launch.calls) == 1, (
        "a failing eager-convergence helper cost the submission its "
        f"start_launch call: {start_launch.calls!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: The eager run stands down exactly as the pass does — inherited
# rather than re-implemented
# ---------------------------------------------------------------------------


def test_a_stood_down_start_never_reaches_the_eager_helper(
    client: TestClient,
    slack_api: _RecordingSlackApi,
    registrar: _RecordingRegistrar,
    helper: _RecordingHelper,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The eager run stands down exactly as the pass does.

    WHEN a launch starts while the served playbook cannot hold a launch
    THEN the eager run creates no list and writes no task for that launch
    — asserted here as "the helper is never reached at all", which is what
    `design.md` means by "inherited rather than re-implemented": the
    stand-down happens inside `start_launch` itself, before this call site
    has anything to trigger.
    """

    class _RefusingPlaybookRepository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str) -> Any:
            from commerce_ops.launch.domain import (
                launch_playbook as playbook_module,
            )

            error = getattr(playbook_module, "PlaybookNotReadyError", None)
            if error is None:
                pytest.fail(
                    "commerce_ops.launch.domain.launch_playbook exports no "
                    "`PlaybookNotReadyError`"
                )
            for args, kwargs in (
                ((), {"playbook": None, "gates": ("ignition",)}),
                ((), {"playbook": None, "unheld_gates": ("ignition",)}),
            ):
                try:
                    raise error(*args, **kwargs)
                except TypeError:
                    continue
            raise RuntimeError(
                "could not construct PlaybookNotReadyError under any probed signature"
            )

    monkeypatch.setattr(
        importlib.import_module(SLACK_ENTRY_MODULE),
        "PlaybookRepository",
        _RefusingPlaybookRepository,
    )

    _post_view_submission(client)
    _drain(client)

    # SPECIFIED: the eager helper is never reached during a stand-down.
    assert helper.calls == [], (
        "the eager-convergence helper was reached although the served "
        f"playbook could not hold a launch: {helper.calls!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - What the eager helper itself does with a real `converge_launch`
#   (eligibility, the lock, containment internals). That is
#   `test_eager_convergence_helper.py`'s; repeating it here would make this
#   file fail for reasons it does not state.
# - That tasks actually exist in ClickUp after a real start, without the
#   periodic pass running. That needs a real session and is
#   `test_eager_convergence_live.py`'s (`tasks.md` 6.1).
# - The precise ordering of `ack()` relative to the eager helper. Bolt's
#   `process_before_response=False` default is what already lets
#   `gate_confirmation.py` continue after `ack()`
#   (`test_gate_decision_wiring.py`'s own convention); this file asserts
#   only that the helper runs after `start_launch`, which is what
#   `tasks.md` 3.3 states.
# ---------------------------------------------------------------------------
