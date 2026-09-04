"""The webhook half: closing an automated step's orphaned task records nothing.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-clickup-sync/spec.md`

Covers the webhook half of the MODIFIED requirement *A step that is not
active leaves the loop*'s new scenario:

    #### Scenario: Closing the orphaned task of an automated step records
    nothing
    - **WHEN** the mapped task of an `active` `automated` step is closed
      in ClickUp, and that closure reaches the system **by webhook** or by
      the reconciliation pass
    - **THEN** no outcome is recorded for that step, and its retained
      observed state is updated so the closure is never replayed

The reconciliation half of the same scenario, and the requirement's other
new scenario (*A step that becomes automated leaves the loop while staying
active*), are covered in
`tests/unit/launch/infrastructure/driven/test_clickup_automated_steps_leave_loop.py`.

`tasks.md` 4a.2 is the task this file guards: "Apply the same exclusion on
the webhook path." Without it, the webhook keeps the older, status-only
notion of which steps are defined, and a member closing the orphaned task
in ClickUp records a `clickup`-sourced `Satisfied` — terminal for hazard
`none`, and so permanently suppressing the automation the flip to
`automated` was performed to enable.

See `test-manifest.md` at the change root for the full accounting.

## Level

The scenario is stated over a delivery arriving at an endpoint, so the
route is the smallest level that can observe it — the level
`tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`
already establishes for this path, whose harness this file follows.

## INVENTED

Nothing new. The four substituted module globals (`session`,
`ClickUpMappingRepository`, `LaunchRepository`, `record_step_outcome`),
the `PlaybookRepository` substitution, the signing scheme and the
route-by-router lookup are all transcribed from that file, which is not
edited by this pass. `monkeypatch.setattr` runs at its default
`raising=True`, so a renamed collaborator fails loudly here rather than
leaving a test green against an unpatched real one.

## Expected first-run state

Expected to **fail** rather than to be absent: the route exists and,
per `design.md`, its notion of a defined step keys on status alone today,
so the closure below records `Satisfied`. Per `ai-toolkit:testing` that
is the wrong-value state — the test executed and discriminated — not an
absent target.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
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

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driving import clickup_webhook as webhook_module
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import ALICE, HANDLER_NAME, LAUNCH_DATE, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import TaskMapping as _TaskMapping

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"

PRODUCT_ID: Final = product_id()
STEP_ID: Final = "lp.listing.007"
TASK_ID: Final = "8x2mapped"
ACTOR_USERNAME: Final = "helen.shatynska"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": STEP_ID,
            "name": "Choose the sub-category node",
            "assignees": (ALICE,),
            **overrides,
        }
    )


def _automated_step() -> StepDefinition:
    """The step after the flip: `automated`, and still `active`."""
    return _step(
        kind=StepKind.AUTOMATED,
        assignees=(),
        confirmer=ALICE,
        handler=HANDLER_NAME,
    )


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        handler=f"hold.{gate.replace('-', '_')}",
        kind=StepKind.AUTOMATED,
        name="Choose the sub-category node",
    )


def _playbook_with(step: StepDefinition) -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(step, *fillers))


# The served set this file's route reads. Rebound per test.
_SERVED: list[LaunchPlaybook] = [_playbook_with(_automated_step())]


def _active_launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=_SERVED[0], launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles (transcribed from `test_clickup_webhook.py`)
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
        return self._launch if product_id == self._launch.product_id else None


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    @property
    def outcomes(self) -> list[Any]:
        return [call.get("outcome") for call in self.calls]


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> LaunchPlaybook:
        return _SERVED[0]


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
    monkeypatch.setattr(webhook_module, "session", _fake_session)


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook_module, "PlaybookRepository", _FakePlaybookRepository)


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingOutcomes:
    fake = _RecordingOutcomes()
    monkeypatch.setattr(webhook_module, "record_step_outcome", fake)
    return fake


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


def _install_mapping(
    monkeypatch: pytest.MonkeyPatch, mapping: _FakeMapping
) -> _FakeMapping:
    monkeypatch.setattr(
        webhook_module, "ClickUpMappingRepository", lambda *args, **kwargs: mapping
    )
    return mapping


def _install_launch(monkeypatch: pytest.MonkeyPatch, launch: Launch) -> None:
    launches = _FakeLaunches(launch)
    monkeypatch.setattr(
        webhook_module, "LaunchRepository", lambda *args, **kwargs: launches
    )


def _webhook_path() -> str:
    posts = [
        route
        for route in webhook_module.router.routes
        if "POST" in getattr(route, "methods", set())
    ]
    assert len(posts) == 1
    return str(getattr(posts[0], "path", ""))


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _closure_payload() -> dict[str, Any]:
    return {
        "event": "taskStatusUpdated",
        "task_id": TASK_ID,
        "webhook_id": "4b67ac88-e506-4a29-9d42-26e504e3435e",
        "history_items": [
            {
                "id": "2800763136717140857",
                "type": 1,
                "date": "1700000000000",
                "field": "status",
                "before": {"status": "in progress", "type": "custom", "orderindex": 1},
                "after": {"status": "complete", "type": "closed", "orderindex": 3},
                "user": {
                    "id": 183,
                    "username": ACTOR_USERNAME,
                    "email": "ops@example.invalid",
                },
            }
        ],
    }


def _deliver(client: TestClient, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(
        _webhook_path(),
        content=body,
        headers={"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)},
    )


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


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step that is not active leaves the loop
# ---------------------------------------------------------------------------


def test_closing_the_orphaned_task_of_an_automated_step_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    recorder: _RecordingOutcomes,
) -> None:
    """Scenario: Closing the orphaned task of an automated step records
    nothing — the webhook half.

    WHEN the mapped task of an `active` `automated` step is closed in
    ClickUp, and that closure reaches the system by webhook
    THEN no outcome is recorded for that step, and its retained observed
    state is updated so the closure is never replayed.
    """
    _SERVED[0] = _playbook_with(_automated_step())
    mapping = _install_mapping(monkeypatch, _mapped(closed=False))
    _install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _closure_payload())

    # The delivery is well-formed and verified, so it is acknowledged —
    # this is a step leaving the loop, not a rejected request.
    assert response.status_code < 400
    # SPECIFIED: no outcome is recorded for that step.
    assert recorder.calls == [], (
        "closing the orphaned task of an `active` `automated` step "
        f"recorded {recorder.outcomes} — terminal for hazard `none`, which "
        "permanently suppresses the automation the flip enables"
    )
    # SPECIFIED: its retained observed state is updated, so the closure
    # is never replayed as a transition later.
    assert mapping.tasks[(PRODUCT_ID, STEP_ID)].last_observed_closed is True


def test_the_same_closure_on_a_human_step_still_records(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
    recorder: _RecordingOutcomes,
) -> None:
    """The discrimination check for the test above.

    Carried forward from the MODIFIED requirement *Completion flows from
    ClickUp to the launch as a recorded outcome* — scenario *A closed
    task records Satisfied*, whose statement this delta re-scopes from
    "a step the served playbook defines" to "a step the loop still
    projects" without changing what it records for a step still in the
    projection.

    Without this, an implementation that recorded nothing at all — a
    broken webhook rather than a corrected exclusion — would pass the
    test above. Same delivery, same mapping, same launch; only the step's
    kind differs.
    """
    _SERVED[0] = _playbook_with(_step())
    _install_mapping(monkeypatch, _mapped(closed=False))
    _install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _closure_payload())

    assert response.status_code < 400
    assert len(recorder.calls) == 1, (
        "a closed task on an `active` `human` step recorded nothing, so the "
        "test above would pass for the wrong reason"
    )
    assert recorder.calls[0]["provenance"].source == "clickup"
