"""Webhook intake is unaffected by the completion pass's fate.

Derived strictly from the delta spec of the OpenSpec change
`contain-a-failing-launch`:
`openspec/changes/contain-a-failing-launch/specs/launch-clickup-sync/spec.md`

Covers exactly one scenario of the ADDED requirement *One launch's failure
does not stop the other launches being converged*:

- *A webhook delivery still records for a launch whose projection is
  failing*

It is in its own file rather than beside the walk's own tests
(`test_clickup_sync_job_containment.py`) because it is the only scenario of
that requirement stated over an HTTP delivery: the requirement's claim is
that intake reaches the same launch **independently**, and a test that
drove the recording through anything but the route would be asserting the
independence of two things it had wired together itself.

See `openspec/changes/contain-a-failing-launch/test-manifest.md` for the
full accounting.

## Level

The route, over a run of the completion pass. The scenario's WHEN has two
halves -- a launch whose projection raised on the most recent run, and a
verified delivery arriving for its mapped task -- and only the route can
observe the second. The first is *made true* rather than assumed: the
completion pass is really run, with that launch's projection really
raising, before the delivery is posted. Asserting intake against a launch
merely described as failing would establish nothing about the pass.

## What is fixed, and what is INVENTED

The webhook harness -- the verification scheme, the delivery shape, the
route read off the router rather than transcribed, and the four
collaborator names substituted on the route module -- is transcribed from
`test_clickup_webhook.py`, which records the provenance of each. The job
harness is transcribed from `test_clickup_sync_job_containment.py`. Neither
is re-argued here; correcting either is a fixture correction in the file it
came from as much as in this one.

INVENTED here, and nowhere else: that the mapping the failing pass leaves
behind and the mapping intake reads are the same store. They are one
`_FakeMapping` instance, which is what makes "the same launch" mean
anything across the two halves.

## Expected first-run state

Expected to **pass** before the implementation lands, and that is not the
alarm `ai-toolkit:testing` describes for a test written ahead of its
implementation. This scenario states what the change must **preserve** --
"webhook intake is unaffected by any of this" -- so the current code
already satisfies it. Its job is to catch a containment implementation that
reached into the intake path, which the delta explicitly forbids.

Baseline recorded before this test was written:
`uv run pytest tests/unit tests/agents` -- 1114 passed, 0 failed;
`uv run pytest tests/integration` -- 93 passed, 2 skipped (both skips
pre-existing and unrelated).
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import hashlib
import hmac
import inspect
import json
import sys
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from types import ModuleType
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from procrastinate import job_context, jobs

import commerce_ops.launch.infrastructure.driving.clickup_webhook as webhook_module
import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.launch.infrastructure.driven.clickup_sync import ClickUpSyncError
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"
CLICKUP_SOURCE: Final = "clickup"
ACTOR_USERNAME: Final = "helen.shatynska"

#: The launch whose projection raises on the run below, and whose mapped
#: task the delivery then concerns.
FAILING: Final = ProductId(str(uuid.uuid4()))
#: A second launch, so the run is a walk rather than a single attempt.
HEALTHY: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FAILING, HEALTHY)

STEP_ID: Final = "listing.title-conforms"
TASK_ID: Final = "8x2mapped"
LAUNCH_DATE: Final = datetime.date(2027, 3, 2)


# ---------------------------------------------------------------------------
# Domain fixtures -- transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (_step(),)
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(*steps, *fillers))


def _launch_for(product_id: ProductId) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=_playbook(), launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# Test doubles shared by the two halves
# ---------------------------------------------------------------------------


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False


class _FakeMapping:
    """The two mapping tables, in memory -- one instance, reached by both
    the pass and the route, which is what makes them the same launch."""

    def __init__(self, mappings: list[_TaskMapping]) -> None:
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {
            (mapping.product_id, mapping.step_id): mapping for mapping in mappings
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


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()


class _FakeWebhookLaunches:
    def __init__(self, launches: tuple[Launch, ...]) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)


class _FakeJobLaunches:
    def __init__(self, launches: tuple[Launch, ...]) -> None:
        self._launches = launches

    async def list_active(self) -> tuple[Launch, ...]:
        return self._launches

    active = list_active
    all_active = list_active

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return self._launches


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str = "") -> LaunchPlaybook:
        return _playbook()


class _FakeSession:
    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> None:
        # `hold_launch_advance_lock` (`trigger-clickup-projection-on-
        # launch-events`) issues `SELECT pg_advisory_xact_lock(...)` and
        # discards the result; a no-op is all this fake needs to support.
        return None


@asynccontextmanager
async def _session_provider(*args: Any, **kwargs: Any) -> AsyncIterator[_FakeSession]:
    yield _FakeSession()


class _FailingConverge:
    """`converge_launch`, raising for exactly one launch."""

    def __init__(self, failing: ProductId) -> None:
        self.failing = failing
        self.seen: list[ProductId] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        self.seen.append(product_id)
        if product_id == self.failing:
            raise ClickUpSyncError("create_task -> 404 Not Found")


class _RecordingReconcile:
    def __init__(self) -> None:
        self.seen: list[ProductId] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.seen.append(_product_of(args, kwargs))


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    for candidate in (*args, *kwargs.values()):
        if isinstance(candidate, Launch):
            return candidate.product_id
        if isinstance(candidate, ProductId) and candidate in WALK:
            return candidate
    pytest.fail(
        "a pass was called with no launch among its arguments "
        f"(args={args!r}, kwargs={kwargs!r})"
    )


# ---------------------------------------------------------------------------
# Reaching the job -- transcribed from the containment tests
# ---------------------------------------------------------------------------


def _runner_app() -> Any:
    from commerce_ops.shared.infrastructure.driven.job_runner import app

    return app


def _completion_periodic() -> Any:
    registered = list(_runner_app().periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "clickup" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the ClickUp completion pass; "
        f"registered periodics are {[entry.task.name for entry in registered]}"
    )
    return matching[0]


def _job_module() -> ModuleType:
    return sys.modules[_completion_periodic().task.func.__module__]


async def _run_job_body() -> Any:
    task = _completion_periodic().task
    parameters = inspect.signature(task.func).parameters
    args: list[Any] = []
    if task.pass_context:
        args.append(
            job_context.JobContext(
                app=_runner_app(),
                job=jobs.Job(
                    id=1,
                    queue=task.queue,
                    lock=task.lock,
                    queueing_lock=task.queueing_lock,
                    task_name=task.name,
                    task_kwargs={},
                    attempts=0,
                ),
                start_timestamp=time.time(),
                abort_reason=lambda: None,
            )
        )
    kwargs: dict[str, Any] = {}
    if "timestamp" in parameters:
        kwargs["timestamp"] = int(time.time())
    return await task.func(*args, **kwargs)


# ---------------------------------------------------------------------------
# Webhook request helpers -- transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _status_change_payload() -> dict[str, Any]:
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


def _webhook_path() -> str:
    posts = [
        route
        for route in webhook_module.router.routes
        if "POST" in getattr(route, "methods", set())
    ]
    assert len(posts) == 1, (
        "expected the ClickUp webhook router to declare exactly one POST "
        f"route; found {[getattr(r, 'path', r) for r in posts]}"
    )
    return str(getattr(posts[0], "path", ""))


def _clear_caches() -> None:
    from commerce_ops.shared.application.settings import get_settings

    get_settings.cache_clear()
    for value in list(vars(webhook_module).values()):
        cache_clear = getattr(value, "cache_clear", None)
        if callable(cache_clear):
            cache_clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mapping() -> _FakeMapping:
    """One mapped task, on the launch whose projection is about to fail --
    projected by some earlier, successful run."""
    return _FakeMapping(
        [_TaskMapping(product_id=FAILING, step_id=STEP_ID, task_id=TASK_ID)]
    )


@pytest.fixture(autouse=True)
def configured_secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("CLICKUP_WEBHOOK_SECRET", WEBHOOK_SECRET)
    _clear_caches()
    yield
    _clear_caches()


@pytest.fixture()
def intake(
    monkeypatch: pytest.MonkeyPatch, mapping: _FakeMapping
) -> _RecordingOutcomes:
    """The route's collaborators, substituted at their default
    `raising=True`, so a renamed collaborator fails loudly here."""
    recorder = _RecordingOutcomes()
    monkeypatch.setattr(webhook_module, "session", _session_provider)
    monkeypatch.setattr(webhook_module, "PlaybookRepository", _FakePlaybookRepository)
    monkeypatch.setattr(webhook_module, "record_step_outcome", recorder)
    monkeypatch.setattr(
        webhook_module, "ClickUpMappingRepository", lambda *a, **k: mapping
    )
    launches = _FakeWebhookLaunches(tuple(_launch_for(product) for product in WALK))
    monkeypatch.setattr(webhook_module, "LaunchRepository", lambda *a, **k: launches)
    return recorder


@pytest.fixture()
def failing_pass(monkeypatch: pytest.MonkeyPatch) -> _FailingConverge:
    """The completion pass, wired so that `FAILING`'s projection raises."""
    job_module = _job_module()
    converge = _FailingConverge(FAILING)
    monkeypatch.setattr(job_module, "converge_launch", converge)
    monkeypatch.setattr(job_module, "reconcile_launch", _RecordingReconcile())
    monkeypatch.setattr(job_module, "PlaybookRepository", _FakePlaybookRepository)
    monkeypatch.setattr(
        job_module,
        "LaunchRepository",
        lambda *a, **k: _FakeJobLaunches(
            tuple(_launch_for(product) for product in WALK)
        ),
        raising=False,
    )
    for name in ("session", "transaction"):
        if hasattr(job_module, name):
            monkeypatch.setattr(job_module, name, _session_provider)
    return converge


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# converged
# ---------------------------------------------------------------------------


def test_a_webhook_delivery_still_records_for_a_launch_whose_projection_is_failing(
    failing_pass: _FailingConverge,
    intake: _RecordingOutcomes,
    mapping: _FakeMapping,
    client: TestClient,
) -> None:
    """Scenario: A webhook delivery still records for a launch whose
    projection is failing.

    WHEN a verified webhook delivery arrives for a mapped task of a launch
    whose projection raised on the most recent run
    THEN the outcome is recorded exactly as it would be for any other
    launch, the completion pass's fate notwithstanding.

    "The most recent run" is made true rather than described: the pass is
    run first, with this launch's projection raising, and the run is
    asserted to have actually reached it before the delivery is posted.
    """
    # The most recent run: this launch's projection raised on it. The run
    # itself fails, which is what the containment requirement demands and
    # is asserted in `test_clickup_sync_job_containment.py`; what matters
    # here is only that it happened.
    # The run's own outcome -- that it fails -- is not this scenario's
    # subject and is asserted in `test_clickup_sync_job_containment.py`;
    # what this test needs from it is only that it happened.
    with contextlib.suppress(Exception):
        asyncio.run(_run_job_body())

    # Guard: the pass really did attempt -- and fail on -- this launch, so
    # "whose projection raised on the most recent run" is a fact about
    # this test rather than a description in its docstring.
    assert failing_pass.seen[:1] == [FAILING], (
        "the completion pass never reached the launch this scenario is "
        f"about; it converged {failing_pass.seen}"
    )

    body = json.dumps(_status_change_payload()).encode("utf-8")
    response = client.post(
        _webhook_path(),
        content=body,
        headers={"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)},
    )

    # SPECIFIED: the outcome is recorded exactly as it would be for any
    # other launch -- the delivery is acknowledged...
    assert 200 <= response.status_code < 300, (
        "a verified delivery for a launch whose projection is failing was "
        f"not acknowledged: {response.status_code} {response.text!r}"
    )
    # ...and one outcome is recorded, for the mapped step.
    assert len(intake.calls) == 1, (
        "the delivery recorded no outcome for a launch whose projection is "
        f"failing: {intake.calls}"
    )
    recorded = intake.calls[0]
    assert recorded.get("step_id") == STEP_ID
    # SPECIFIED, by the intake requirements this scenario says still
    # govern: a closed task records `Satisfied` with provenance source
    # `clickup`.
    assert recorded.get("outcome") is Satisfied, (
        f"the delivery recorded {recorded.get('outcome')!r} rather than Satisfied"
    )
    provenance = recorded.get("provenance")
    assert provenance is not None, "the recording carried no provenance"
    assert provenance.source == CLICKUP_SOURCE
    # SPECIFIED, by the reconciliation requirement: the retained observed
    # state is updated by every observation, webhook deliveries included --
    # so intake, unlike the skipped reconciliation, does consume the
    # transition.
    assert mapping.tasks[(FAILING, STEP_ID)].last_observed_closed is True


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Every other condition intake imposes -- signature verification, an
#   unmapped task, a graduated launch, a repeated delivery. The scenario
#   says intake is gated on "the conditions the intake requirements already
#   impose", and those requirements are unmodified by this change; their
#   tests stand in `test_clickup_webhook.py`.
# - Whether a delivery arriving *during* a run is recorded. No scenario
#   states an ordering between the pass and a delivery, and this change
#   introduces no shared state between them.
# ---------------------------------------------------------------------------
