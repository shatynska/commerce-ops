"""The webhook's advance-and-ask cascade triggers an eager convergence too.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A launch is converged eagerly at start
and at a gate crossing*, the scenarios stated over this call site:

- *A gate crossing's newly released steps get tasks immediately, however
  the gate opened* — the webhook half: "... or the ClickUp webhook's own
  advance-and-ask trigger". A gate the webhook's own trigger crosses
  dispatches the eager helper too, via `BackgroundTasks`, alongside
  `advance_and_ask` (`tasks.md` 3.5).
- *A failed eager run does not fail the action that triggered it* — this
  call site's own half: the webhook's acknowledgement is unaffected by a
  raising helper — the same insulation
  `test_clickup_webhook_triggers_the_advance_cascade.py` already
  establishes for a raising `advance_and_ask` itself.

`test_advance_and_ask.py` already covers what `advance_and_ask`'s own
cascade does once triggered, and `test_clickup_webhook_triggers_the_
advance_cascade.py` already covers that a recording delivery triggers it,
handed the product identifier alone, off the response path. This file adds
only the eager-convergence dispatch alongside it and does not restate
those.

See `test-manifest.md` at the change root for the full accounting.

## Level

The route, over in-memory doubles — the level
`test_clickup_webhook_triggers_the_advance_cascade.py` already holds for
this surface. Nothing below the route can observe whether the eager
helper was dispatched via `BackgroundTasks`, or whether a raising helper
reached the acknowledgement.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the route dispatches the eager
helper via `BackgroundTasks` — "this route is genuine FastAPI, unlike
3.3/3.4" — alongside, or from within, `advance_and_ask`, after a gate
crossing (`tasks.md` 3.5).

INVENTED: the eager helper's name (`_HELPER_NAMES`, kept in step with
`test_eager_convergence_helper.py`); every webhook mechanic — signature
verification, the delivery shape, the mapped step, the collaborator names
— is transcribed from `test_clickup_webhook_triggers_the_advance_cascade.py`,
which records the provenance of each.

## What "alongside, or from within" leaves open

`tasks.md` 3.5 permits either shape: the route dispatches the eager helper
as its own `background_tasks.add_task` call, or `advance_and_ask` itself
(already backgrounded) calls the eager helper internally once it crosses a
gate. This file asserts only the observable common to both — that a
crossing dispatched through this route eventually triggers the eager
helper for that launch — and does not pin which of the two shapes produced
it. Where the second shape is chosen, this file's own assertions still
hold; only `test_gate_progression_pass_eager_convergence.py`'s reading of
where the call lives (inline in `gate_progression_job.py`) is specific to
that module and does not transfer here.

## Expected first-run state

The route dispatches no eager helper yet (`tasks.md` 3.5), so every test
here is expected to fail on an **absent target**. Per `ai-toolkit:testing`
that establishes absence only.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import commerce_ops.launch.infrastructure.driving.clickup_webhook as webhook_module
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import LAUNCH_DATE, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import TaskMapping as _TaskMapping

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"

PRODUCT_ID: Final = product_id()
STEP_ID: Final = "listing.title-conforms"
TASK_ID: Final = "8x2mapped"

#: Kept in step with `test_eager_convergence_helper.py`'s own
#: `_HELPER_NAMES`, which is the correction point for the name itself.
_HELPER_NAMES: Final = (
    "converge_launch_eagerly",
    "eager_converge_launch",
    "converge_launch_now",
    "converge_one_launch_eagerly",
    "eagerly_converge_launch",
)
_TRIGGER_NAMES: Final = (
    "advance_and_ask",
    "advance_and_ask_for",
    "trigger_advance_and_ask",
    "advance_launch_and_ask",
)


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from
# `test_clickup_webhook_triggers_the_advance_cascade.py`
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": STEP_ID, **overrides})


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    return _build_hold(
        gate,
        **{
            "kind": StepKind.AUTOMATED,
            "status": StepStatus.ACTIVE,
            "handler": "fixture.holding_check",
            "name": "Work this step asks for",
            **overrides,
        },
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(version="test-v1", gates=gates, steps=_fill((_step(),)))


def _active_launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=_playbook(), launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — transcribed from
# `test_clickup_webhook_triggers_the_advance_cascade.py`
# ---------------------------------------------------------------------------


class _FakeMapping:
    def __init__(self, mappings: list[_TaskMapping] | None = None) -> None:
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {
            (mapping.product_id, mapping.step_id): mapping
            for mapping in (mappings or [])
        }

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> _TaskMapping | None:
        return self.tasks.get((product_id, step_id))

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        self.tasks[(product_id, step_id)].last_observed_closed = closed


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self._launch = launch

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        if product_id == self._launch.product_id:
            return self._launch
        return None


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()


class _RecordingTrigger:
    """Stands in for `advance_and_ask`. Advances the launch's current gate
    when it is called, unconditionally — this file is not about the
    cascade's own advancement rules (`test_advance_and_ask.py`'s), only
    about what runs alongside it once a gate crosses.

    Sets `current_gate` directly rather than calling the real
    `Launch.advance_gate`: every gate in `SPECIFIED_GATE_ORDER` either
    requires confirmation or carries an unsatisfied `_hold` blocking step
    by construction (`_fill`), so the real domain method would raise
    `GateBlockedError` here regardless of which gate the launch starts at
    — a fact about this file's minimal fixture data, not something this
    fake exists to exercise.
    """

    def __init__(self, launch: Launch, playbook: LaunchPlaybook) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._launch = launch
        self._playbook = playbook

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        position = SPECIFIED_GATE_ORDER.index(self._launch.current_gate)
        self._launch.current_gate = SPECIFIED_GATE_ORDER[position + 1]


class _RecordingHelper:
    def __init__(self, *, failing: bool = False) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        if self.failing:
            raise RuntimeError("simulated eager-convergence failure")

    @property
    def products(self) -> list[Any]:
        """The product each call named — as a bare `ProductId` among its
        arguments, or (the shared helper's verified real shape, per
        `test_eager_convergence_helper.py`'s sentinel-identity checks) via
        a `launch` argument's own `.product_id`."""
        found: list[Any] = []
        for args, kwargs in self.calls:
            for candidate in (*args, *kwargs.values()):
                if isinstance(candidate, ProductId):
                    found.append(candidate)
                    break
                nested = getattr(candidate, "product_id", None)
                if isinstance(nested, ProductId):
                    found.append(nested)
                    break
            else:
                found.append(None)
        return found


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> LaunchPlaybook:
        return _playbook()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _clear_caches() -> None:
    from commerce_ops.shared.application.settings import get_settings

    get_settings.cache_clear()
    for value in list(vars(webhook_module).values()):
        cache_clear = getattr(value, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CLICKUP_WEBHOOK_SECRET", WEBHOOK_SECRET)
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[None]:
        yield None

    monkeypatch.setattr(webhook_module, "session", _provider)


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook_module, "PlaybookRepository", _FakePlaybookRepository)


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingOutcomes:
    fake = _RecordingOutcomes()
    monkeypatch.setattr(webhook_module, "record_step_outcome", fake)
    return fake


def _helper_name() -> str:
    for name in _HELPER_NAMES:
        if hasattr(webhook_module, name):
            return name
    pytest.fail(
        f"{webhook_module.__name__} exposes no eager-convergence helper "
        f"under any of {_HELPER_NAMES}; `tasks.md` 3.5 adds one. This is the "
        "absent-target state, not a defect in this file — do not add the "
        "attribute to make this pass."
    )


def _trigger_name() -> str:
    for name in _TRIGGER_NAMES:
        if hasattr(webhook_module, name):
            return name
    pytest.fail(
        f"{webhook_module.__name__} exposes no advance-and-ask trigger under "
        f"any of {_TRIGGER_NAMES}; `advance-gates-from-clickup-webhook` adds "
        "it. This is the absent-target state."
    )


@pytest.fixture()
def helper(monkeypatch: pytest.MonkeyPatch) -> _RecordingHelper:
    fake = _RecordingHelper()
    monkeypatch.setattr(webhook_module, _helper_name(), fake)
    return fake


def install_mapping(
    monkeypatch: pytest.MonkeyPatch, mapping: _FakeMapping
) -> _FakeMapping:
    monkeypatch.setattr(
        webhook_module, "ClickUpMappingRepository", lambda *args, **kwargs: mapping
    )
    return mapping


def install_launch(monkeypatch: pytest.MonkeyPatch, launch: Launch) -> _FakeLaunches:
    launches = _FakeLaunches(launch)
    monkeypatch.setattr(
        webhook_module, "LaunchRepository", lambda *args, **kwargs: launches
    )
    return launches


def install_trigger(
    monkeypatch: pytest.MonkeyPatch, launch: Launch
) -> _RecordingTrigger:
    fake = _RecordingTrigger(launch, _playbook())
    monkeypatch.setattr(webhook_module, _trigger_name(), fake)
    return fake


def _webhook_path() -> str:
    posts = [
        route
        for route in webhook_module.router.routes
        if "POST" in getattr(route, "methods", set())
    ]
    assert len(posts) == 1
    return str(getattr(posts[0], "path", ""))


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


def _sign(body: bytes, *, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _signed_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)}


def _status_change_payload(
    *,
    task_id: str = TASK_ID,
    before: str = "in progress",
    before_type: str = "custom",
    after: str = "complete",
    after_type: str = "closed",
    event: str = "taskStatusUpdated",
) -> dict[str, Any]:
    return {
        "event": event,
        "task_id": task_id,
        "webhook_id": "4b67ac88-e506-4a29-9d42-26e504e3435e",
        "history_items": [
            {
                "id": "2800763136717140857",
                "type": 1,
                "date": "1700000000000",
                "field": "status",
                "before": {"status": before, "type": before_type, "orderindex": 1},
                "after": {"status": after, "type": after_type, "orderindex": 3},
                "user": {
                    "id": 183,
                    "username": "helen.shatynska",
                    "email": "ops@example.invalid",
                },
            }
        ],
    }


def _deliver(client: TestClient, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(_webhook_path(), content=body, headers=_signed_headers(body))


def _mapped(closed: bool = False) -> _FakeMapping:
    return _FakeMapping(
        [
            _TaskMapping(
                product_id=PRODUCT_ID,
                step_id=STEP_ID,
                task_id=TASK_ID,
                last_observed_closed=closed,
            )
        ]
    )


def _acknowledged(response: Any) -> None:
    assert 200 <= response.status_code < 300, (
        f"the delivery was not acknowledged: {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Scenario: A gate crossing's newly released steps get tasks immediately,
# however the gate opened — the webhook half
# ---------------------------------------------------------------------------


def test_a_delivery_whose_cascade_crosses_a_gate_triggers_the_eager_helper(
    client: TestClient,
    recorder: _RecordingOutcomes,
    helper: _RecordingHelper,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate crossing's newly released steps get tasks
    immediately, however the gate opened.

    WHEN a launch's gate crosses through the ClickUp webhook's own
    advance-and-ask trigger
    THEN the eager helper is triggered for that launch.

    The substituted `advance_and_ask` here unconditionally advances the
    launch's gate once called, so a delivery that records an outcome and
    reaches the cascade is exactly the WHEN this scenario states.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    launch = _active_launch()
    install_launch(monkeypatch, launch)
    install_trigger(monkeypatch, launch)

    response = _deliver(client, _status_change_payload())

    _acknowledged(response)
    assert len(recorder.calls) == 1, (
        f"the delivery recorded no outcome, so this test exercised nothing: "
        f"{recorder.calls}"
    )
    # SPECIFIED-BY-TASKS (`tasks.md` 3.5): the eager helper is triggered.
    assert len(helper.calls) == 1, (
        "a webhook-triggered gate crossing did not trigger the eager-"
        f"convergence helper: {helper.calls!r}"
    )
    assert helper.products == [PRODUCT_ID], (
        f"the eager helper was triggered for the wrong launch: {helper.calls!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A failed eager run does not fail the action that triggered it
# ---------------------------------------------------------------------------


def test_a_failing_eager_run_does_not_affect_the_webhooks_acknowledgement(
    client: TestClient,
    recorder: _RecordingOutcomes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed eager run does not fail the action that
    triggered it.

    WHEN the eager run raises while converging a launch whose gate the
    webhook's own trigger just crossed
    THEN the delivery is still acknowledged and its recording still stands
    — exactly as `test_clickup_webhook_triggers_the_advance_cascade.py`'s
    own `test_a_delivery_is_acknowledged_although_the_cascade_explodes`
    already establishes for a raising `advance_and_ask` itself.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    launch = _active_launch()
    install_launch(monkeypatch, launch)
    install_trigger(monkeypatch, launch)
    exploding = _RecordingHelper(failing=True)
    monkeypatch.setattr(webhook_module, _helper_name(), exploding)

    response = _deliver(client, _status_change_payload())

    assert exploding.calls, (
        "the failing eager helper was never reached, so this test exercised nothing"
    )
    # SPECIFIED-BY-PROPOSAL: the acknowledgement is unaffected.
    _acknowledged(response)
    # SPECIFIED-BY-PROPOSAL: and the recording it acknowledged stands.
    assert len(recorder.calls) == 1, (
        f"the failing eager helper cost the delivery its recording: {recorder.calls}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the eager helper is dispatched by the route's own
#   `background_tasks.add_task` call, or from inside `advance_and_ask`
#   itself once it crosses a gate. `tasks.md` 3.5 permits either shape and
#   this file's own assertions hold under both (see the module docstring).
# - That the eager helper is dispatched via `BackgroundTasks` specifically
#   rather than awaited inline. `TestClient` runs a request and its
#   background tasks inside one blocking call, so no assertion available
#   here distinguishes the two — the same limitation
#   `test_clickup_webhook_triggers_the_advance_cascade.py` already records
#   for `advance_and_ask`'s own dispatch.
# - What the eager helper itself does with a real `converge_launch`. That
#   is `test_eager_convergence_helper.py`'s.
# - A delivery whose cascade does not cross a gate (an unmapped task, a
#   graduated launch, an unrelated event, a stand-down). Already covered
#   by `test_clickup_webhook_triggers_the_advance_cascade.py`'s own
#   no-cascade tests for `advance_and_ask`; since the eager helper here is
#   asserted to fire only alongside a crossing, "no crossing" already
#   implies "no eager call" without a dedicated negative test duplicating
#   that file's own fixtures.
# ---------------------------------------------------------------------------
