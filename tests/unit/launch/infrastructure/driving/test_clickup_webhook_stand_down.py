"""Webhook intake while the served playbook cannot hold a launch.

Derived strictly from the delta spec of the OpenSpec change
`serve-only-a-ready-playbook`:
`openspec/changes/serve-only-a-ready-playbook/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *Projection and intake stand down while
the playbook cannot hold a launch*:

- *A served step's task is not observed during a stand-down*
- *A non-served step's closure during a stand-down is still consumed*
- *A served step's completion arriving during a stand-down is not lost*

The two step cases are the requirement's own pair, and it says in as many
words that they "SHALL NOT be collapsed". They are written as separate
tests over the *same* delivery, differing only in whether the carried
playbook serves the step, so that an implementation applying one treatment
to both fails exactly one of them.

Also covers, from the MODIFIED requirement *Completion flows from ClickUp
to the launch as a recorded outcome*, the clause this change adds to its
statement — "intake during a stand-down records no outcome whatever the
task's status". That clause names no `#### Scenario:` of its own; the
requirement's five scenarios are stated outside a stand-down and keep their
existing tests in `test_clickup_webhook.py`.

## Level

The route, as `test_clickup_webhook.py` already establishes for this
capability: every scenario here is stated over an HTTP delivery arriving at
an endpoint, and what makes the served/non-served split load-bearing is
where the readiness check sits **relative to `mapping.observe(...)`** — an
ordering only the route can exhibit.

The retained observed state is asserted on the mapping row rather than on
the response, per `tasks.md` 5.7. That row is the in-memory `_FakeMapping`,
which is what the project's own tier rule puts at this level: `tests/unit`
is for tests that touch no real I/O, and the behaviour under test is the
route's ordering, not the repository's commit. The repository's own commit
is covered at the integration tier by
`tests/integration/launch/test_launch_clickup_mapping.py`, unchanged by this
change.

## Reading "the delivery is acknowledged"

As a 2xx, the only acknowledgement an HTTP endpoint has — the reading
`test_clickup_webhook.py` already recorded. The requirement's reason clause
depends on it: "Failing the delivery instead of acknowledging it would make
ClickUp retry against a condition that retrying cannot resolve."

## What is fixed, and what is INVENTED

Fixed by the artifacts: that the readiness check moves ahead of
`mapping.observe(...)` while the membership check stays after it
(`tasks.md` 4.3); that the served set comes from the playbook the refusal
carries, with no second read (`design.md`); and `PlaybookNotReadyError` as
the refusal's type (`tasks.md` 1.3).

INVENTED, and transcribed from `test_clickup_webhook.py` rather than
re-derived so a correction there is the correction here: the four
module-level collaborator names substituted below, the route's URL (read
off the router, never transcribed), and the payload shape.
Additionally INVENTED here: `PlaybookNotReadyError`'s constructor keywords,
probed by `_raise_not_ready()` below.

## Expected first-run state

`PlaybookNotReadyError` does not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed;
`uv run pytest tests/integration` — 84 passed, 0 failed.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
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
from commerce_ops.launch.infrastructure.driven.clickup_sync import reconcile_launch
from commerce_ops.launch.infrastructure.driving import clickup_webhook as webhook_module
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
SERVED_STEP_ID: Final = "listing.title-conforms"
SERVED_TASK_ID: Final = "8x2served"
DRAFT_STEP_ID: Final = "listing.copy-review"
DRAFT_TASK_ID: Final = "8x2drafted"
UNKNOWN_STEP_ID: Final = "listing.never-authored"
UNKNOWN_TASK_ID: Final = "8x2unknown"

LIST_ID: Final = "list-001"
LAUNCH_DATE: Final = date(2027, 3, 2)
ACTOR_USERNAME: Final = "helen.shatynska"

# SPECIFIED (main spec): the gate the served fixture step hangs off.
UNHELD_GATE: Final = "graduated"


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


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": SERVED_STEP_ID,
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


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "gate": gate,
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "handler": "fixture.holding_check",
    }
    attributes.update(overrides)
    return _step(**attributes)


def _authored_steps() -> tuple[StepDefinition, ...]:
    """The authored set every fixture playbook below carries.

    `SERVED_STEP_ID` is `active`, `DRAFT_STEP_ID` is a draft — so the two
    are authored alike and differ only in whether the playbook *serves*
    them, which is exactly the distinction the requirement's pair turns on.
    """
    return (
        _step(identifier=SERVED_STEP_ID, status=StepStatus.ACTIVE),
        _step(identifier=DRAFT_STEP_ID, status=StepStatus.DRAFT),
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


def _ready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=_authored_steps())


def _unready_playbook() -> LaunchPlaybook:
    """The same authored set, with `UNHELD_GATE`'s only blocking step
    demoted to a draft — so exactly one gate holds no active blocking step
    and the playbook is coherent but unservable."""
    steps = tuple(
        _hold(UNHELD_GATE, status=StepStatus.DRAFT)
        if step.identifier == f"hold.{UNHELD_GATE}"
        else step
        for step in _authored_steps()
    )
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


def _active_launch(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


# ---------------------------------------------------------------------------
# The refusal — INVENTED constructor keywords, one correction point
# ---------------------------------------------------------------------------


def _not_ready_error() -> type[Exception]:
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError` (`tasks.md` 1.3)"
        )
    return error  # type: ignore[no-any-return]


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    """The refusal the serving read raises, carrying the unheld gates and
    the playbook (`tasks.md` 1.3).

    Several constructor shapes are tried so that a correction to the
    error's signature is a change here alone; what every test below relies
    on is only that the raised error carries the playbook.
    """
    error = _not_ready_error()
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": (UNHELD_GATE,)}),
        ((), {"playbook": playbook, "unheld_gates": (UNHELD_GATE,)}),
        (((UNHELD_GATE,), playbook), {}),
        ((playbook, (UNHELD_GATE,)), {}),
    )
    for args, kwargs in attempts:
        try:
            return error(*args, **kwargs)
        except TypeError:
            continue
    pytest.fail(
        "could not construct PlaybookNotReadyError carrying both the "
        "unheld gates and the playbook under any probed signature; correct "
        "`_build_not_ready` to the implemented one"
    )


# ---------------------------------------------------------------------------
# Test doubles — transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False


@dataclass
class _FakeTask:
    id: str
    name: str
    list_id: str
    status: str = "to do"
    closed: bool = False
    due_date: Any = None


class _FakeMapping:
    """In-memory stand-in for the two mapping tables.

    Records every `observe` call as well as applying it, so a test can
    distinguish "the retained state happens to be unchanged" from "the
    observation was never made" — which is what the requirement is about.
    """

    def __init__(self, mappings: list[_TaskMapping] | None = None) -> None:
        self.tasks: dict[tuple[ProductId, str], _TaskMapping] = {
            (mapping.product_id, mapping.step_id): mapping
            for mapping in (mappings or [])
        }
        self.lists: dict[ProductId, str] = {}
        self.observations: list[tuple[str, bool]] = []

    async def resolve_task(self, task_id: str) -> _TaskMapping | None:
        for mapping in self.tasks.values():
            if mapping.task_id == task_id:
                return mapping
        return None

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> _TaskMapping | None:
        return self.tasks.get((product_id, step_id))

    async def tasks_for(self, product_id: ProductId) -> list[_TaskMapping]:
        return [
            mapping
            for (mapped_product, _), mapping in self.tasks.items()
            if mapped_product == product_id
        ]

    async def list_id_for(self, product_id: ProductId) -> str | None:
        return self.lists.get(product_id)

    async def replace_list_discarding_tasks(
        self,
        product_id: ProductId,
        list_id: str,
        *,
        spare: Sequence[str] = (),
    ) -> None:
        """Present so this double still stands in for the whole
        `MappingStore` port, which `heal-a-launchs-deleted-list` widened.
        No scenario in this file replaces a list; the behaviour is
        exercised in `test_clickup_sync_list_healing.py`."""
        spared = {str(step_id) for step_id in spare}
        self.tasks = {
            key: mapped
            for key, mapped in self.tasks.items()
            if key[0] != product_id or key[1] in spared
        }
        self.lists[product_id] = list_id

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
        """Present so this double satisfies `MappingStore` whole. The
        reconciliation paths under test here never project, so recording a
        list is not exercised — but a double that silently omits half a
        protocol is a double that can drift from it."""
        self.lists[product_id] = list_id

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None:
        """Present for the same reason as `record_list`."""
        self.tasks[(product_id, step_id)] = _TaskMapping(
            product_id=product_id, step_id=step_id, task_id=task_id
        )

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        self.observations.append((step_id, closed))
        self.tasks[(product_id, step_id)].last_observed_closed = closed

    async def record_composition(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeClickUp:
    """Only the reads reconciliation takes."""

    def __init__(self, tasks: tuple[_FakeTask, ...] = ()) -> None:
        self.tasks = {task.id: task for task in tasks}

    async def list_tasks(self, list_id: str) -> Sequence[_FakeTask]:
        return [task for task in self.tasks.values() if task.list_id == list_id]


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


@asynccontextmanager
async def _fake_session() -> AsyncIterator[None]:
    yield None


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


def install_playbook_read(
    monkeypatch: pytest.MonkeyPatch, *, refusing_with: LaunchPlaybook | None
) -> None:
    """Substitute the served-playbook read.

    `refusing_with` is the playbook the refusal carries; `None` installs a
    read that succeeds with a ready playbook, which is the control.
    """

    class _Repository:
        def __init__(self, *args: object, **kwargs: object) -> None: ...

        async def get(self, version: str) -> LaunchPlaybook:
            if refusing_with is not None:
                raise _build_not_ready(refusing_with)
            return _ready_playbook()

    monkeypatch.setattr(webhook_module, "PlaybookRepository", _Repository)


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch) -> _RecordingOutcomes:
    fake = _RecordingOutcomes()
    monkeypatch.setattr(webhook_module, "record_step_outcome", fake)
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


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Request helpers — transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


def _sign(body: bytes) -> str:
    return hmac.new(WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _signed_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)}


def _closure_payload(task_id: str) -> dict[str, Any]:
    """A verified `taskStatusUpdated` delivery moving a task to a status of
    the closed type. The closed judgement lives in the status's `type`
    field, never in its name."""
    return {
        "event": "taskStatusUpdated",
        "task_id": task_id,
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
    return client.post(_webhook_path(), content=body, headers=_signed_headers(body))


def _row(mapping: _FakeMapping, step_id: str) -> _TaskMapping:
    """The stored mapping row, read directly — these route tests are
    synchronous, so the fake's async readers cannot be awaited here."""
    return mapping.tasks[(PRODUCT_ID, step_id)]


def _mapped_rows() -> _FakeMapping:
    """Both steps mapped to tasks, neither yet observed closed."""
    mapping = _FakeMapping(
        [
            _TaskMapping(PRODUCT_ID, SERVED_STEP_ID, SERVED_TASK_ID),
            _TaskMapping(PRODUCT_ID, DRAFT_STEP_ID, DRAFT_TASK_ID),
            _TaskMapping(PRODUCT_ID, UNKNOWN_STEP_ID, UNKNOWN_TASK_ID),
        ]
    )
    mapping.lists[PRODUCT_ID] = LIST_ID
    return mapping


def _clickup_with(*closed_task_ids: str) -> _FakeClickUp:
    """Every mapped task, present in ClickUp, with the named ones closed.

    Seeding *all three* rather than only the task under test keeps
    reconciliation off the "mapped task ClickUp does not answer for" path,
    which no scenario of this change is about.
    """
    return _FakeClickUp(
        tuple(
            _FakeTask(
                id=task_id,
                name=f"task {task_id}",
                list_id=LIST_ID,
                status="complete" if task_id in closed_task_ids else "in progress",
                closed=task_id in closed_task_ids,
            )
            for task_id in (SERVED_TASK_ID, DRAFT_TASK_ID, UNKNOWN_TASK_ID)
        )
    )


def _acknowledged(response: Any) -> None:
    assert 200 <= response.status_code < 300, (
        "a verified delivery arriving during a stand-down must be "
        "acknowledged, not failed — failing it would make ClickUp retry "
        f"against a condition retrying cannot resolve; got "
        f"{response.status_code}"
    )


# ---------------------------------------------------------------------------
# Requirement: Projection and intake stand down while the playbook cannot
# hold a launch
# ---------------------------------------------------------------------------


def test_a_served_steps_task_is_not_observed_during_a_stand_down(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A served step's task is not observed during a stand-down.

    WHEN a verified webhook delivery arrives during a stand-down for a task
    whose step the playbook serves
    THEN the delivery is acknowledged, nothing is recorded, and the task's
    retained observed state is left exactly as it was.

    The non-observation is "the whole of what makes the completion
    recoverable": reconciliation detects a missed completion only as a
    *transition* of the retained state, so an ordinary observation here
    would lose the completion silently. Asserted twice over — the row's
    value, and that `observe` was never called for the step at all — so
    that an implementation observing and then restoring still fails.
    """
    unready = _unready_playbook()
    install_playbook_read(monkeypatch, refusing_with=unready)
    mapping = install_mapping(monkeypatch, _mapped_rows())
    install_launch(monkeypatch, _active_launch(_ready_playbook()))

    response = _deliver(client, _closure_payload(SERVED_TASK_ID))

    # SPECIFIED: the delivery is acknowledged.
    _acknowledged(response)
    # SPECIFIED: nothing is recorded.
    assert recorder.calls == [], (
        f"an outcome was recorded during a stand-down: {recorder.calls}"
    )
    # SPECIFIED: the retained observed state is left exactly as it was.
    assert _row(mapping, SERVED_STEP_ID).last_observed_closed is False
    assert [step for step, _ in mapping.observations if step == SERVED_STEP_ID] == [], (
        "the served step's task was observed during a stand-down; the "
        "readiness check must precede `mapping.observe(...)`, not follow it"
    )


def test_a_non_served_steps_closure_during_a_stand_down_is_still_consumed(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A non-served step's closure during a stand-down is still
    consumed.

    WHEN a verified webhook delivery arrives during a stand-down for a task
    whose step the playbook does **not** serve
    THEN the delivery is acknowledged, nothing is recorded, and the task's
    retained observed state is advanced.

    The opposite treatment to the test above, over the same delivery shape
    and the same stand-down — only the step differs. "A closure that
    happened while the step was out of the served set must be consumed, so
    it is never replayed as a transition after the step returns."

    The second AND of the scenario — "when the playbook becomes ready and
    that step is active again, no outcome is recorded for that closure" —
    is asserted at the end, by reconciling against a ready playbook that
    serves the step and finding no transition left to record.
    """
    unready = _unready_playbook()
    install_playbook_read(monkeypatch, refusing_with=unready)
    mapping = install_mapping(monkeypatch, _mapped_rows())
    install_launch(monkeypatch, _active_launch(_ready_playbook()))

    response = _deliver(client, _closure_payload(DRAFT_TASK_ID))

    # SPECIFIED: acknowledged, and nothing recorded.
    _acknowledged(response)
    assert recorder.calls == [], (
        f"an outcome was recorded during a stand-down: {recorder.calls}"
    )
    # SPECIFIED: the retained observed state is advanced.
    assert _row(mapping, DRAFT_STEP_ID).last_observed_closed is True, (
        "a non-served step's closure was not consumed during the stand-down, "
        "so it will be replayed as a transition once the step returns to "
        "the served set"
    )

    # SPECIFIED (the scenario's second AND): once the playbook is ready and
    # the step is active again, that closure records nothing.
    returned = _ready_playbook()
    served_again = tuple(
        step for step in returned.served_steps if step.identifier == DRAFT_STEP_ID
    )
    outcomes = _RecordingOutcomes()
    clickup = _clickup_with(DRAFT_TASK_ID)
    with_step_active = LaunchPlaybook(
        version="test-v2",
        gates=_gates(),
        steps=tuple(
            _step(identifier=DRAFT_STEP_ID, status=StepStatus.ACTIVE)
            if step.identifier == DRAFT_STEP_ID
            else step
            for step in _authored_steps()
        ),
    )
    assert not served_again, (
        "fixture precondition: the draft step must not be served before it "
        "is re-activated, or this test's premise does not hold"
    )

    asyncio.run(
        reconcile_launch(
            launch=_active_launch(with_step_active),
            playbook=with_step_active,
            clickup=clickup,
            mapping=mapping,
            record_outcome=outcomes,
        )
    )

    assert [
        call for call in outcomes.calls if call.get("step_id") == DRAFT_STEP_ID
    ] == [], (
        "the stand-down closure was replayed as a completion once the step "
        "returned to the served set; consuming it during the stand-down is "
        "what prevents that"
    )


def test_a_served_steps_completion_arriving_during_a_stand_down_is_not_lost(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A served step's completion arriving during a stand-down is
    not lost.

    WHEN a served step's mapped task is closed in ClickUp while the
    playbook is not ready
    AND the playbook later becomes ready and the reconciliation pass runs
    THEN the completion is recorded then, from the transition between the
    task's unchanged retained state and its closed state in ClickUp.

    Written as one test rather than three because the scenario's claim is
    about a **sequence**: each step of it is satisfiable in isolation by an
    implementation that loses the completion. This is the test `design.md`
    names as the guard on the webhook's ordering ("A completion is lost if
    the readiness check lands after the observation").
    """
    install_playbook_read(monkeypatch, refusing_with=_unready_playbook())
    mapping = install_mapping(monkeypatch, _mapped_rows())
    install_launch(monkeypatch, _active_launch(_ready_playbook()))

    # 1. The task is closed in ClickUp while the playbook is not ready, and
    #    its delivery arrives.
    response = _deliver(client, _closure_payload(SERVED_TASK_ID))

    _acknowledged(response)
    assert recorder.calls == [], "the stand-down recorded an outcome"
    assert _row(mapping, SERVED_STEP_ID).last_observed_closed is False, (
        "the retained observed state was advanced during the stand-down, so "
        "the transition reconciliation needs no longer exists"
    )

    # 2. The playbook becomes ready and the reconciliation pass runs. The
    #    task is still closed in ClickUp — nothing about it changed; only
    #    the playbook did.
    ready = _ready_playbook()
    outcomes = _RecordingOutcomes()
    clickup = _clickup_with(SERVED_TASK_ID)

    asyncio.run(
        reconcile_launch(
            launch=_active_launch(ready),
            playbook=ready,
            clickup=clickup,
            mapping=mapping,
            record_outcome=outcomes,
        )
    )

    # SPECIFIED: the completion is recorded then.
    recorded = [
        call for call in outcomes.calls if call.get("step_id") == SERVED_STEP_ID
    ]
    assert len(recorded) == 1, (
        "the completion that arrived during the stand-down was not recovered "
        f"by the first reconciliation after the playbook became ready: "
        f"{outcomes.calls}"
    )
    assert recorded[0].get("outcome") is Satisfied
    # SPECIFIED: from the transition — so the retained state is now closed.
    assert _row(mapping, SERVED_STEP_ID).last_observed_closed is True


def test_a_delivery_for_a_step_outside_the_authored_set_still_advances_the_row(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DERIVED ordering guard, from `tasks.md` 4.3 and 5.11.

    No `#### Scenario:` covers this. `tasks.md` 4.3 requires that the
    membership check following the playbook read **stay after** the
    observation, so that a delivery for a step outside the launch's
    obligations is still observed and never replayed later. Moving the
    readiness check above `mapping.observe(...)` is exactly the edit that
    could drag the membership check up with it.

    The step used is absent from the authored set entirely, per `tasks.md`
    5.11: a *retired* step passes the membership check and is refused
    downstream by `_defined_step` instead, which is a different path and
    out of scope here.

    Stated outside a stand-down: the serving read succeeds, so what this
    isolates is the membership check's position alone.
    """
    install_playbook_read(monkeypatch, refusing_with=None)
    mapping = install_mapping(monkeypatch, _mapped_rows())
    install_launch(monkeypatch, _active_launch(_ready_playbook()))

    response = _deliver(client, _closure_payload(UNKNOWN_TASK_ID))

    _acknowledged(response)
    assert recorder.calls == [], (
        "an outcome was recorded for a step the playbook does not carry: "
        f"{recorder.calls}"
    )
    assert _row(mapping, UNKNOWN_STEP_ID).last_observed_closed is True, (
        "the delivery for a step outside the authored set was not observed, "
        "so its closure can be replayed as a transition later"
    )


def test_a_ready_playbook_leaves_intake_recording_exactly_as_before(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A ready playbook restores the passes — the intake half.

    WHEN every gate holds at least one active blocking step
    THEN the projection and reconciliation passes run exactly as they do
    today.

    The control for every test above: without it, an implementation that
    stood down unconditionally would satisfy the two stand-down tests and
    the ordering guard alike.
    """
    install_playbook_read(monkeypatch, refusing_with=None)
    mapping = install_mapping(monkeypatch, _mapped_rows())
    install_launch(monkeypatch, _active_launch(_ready_playbook()))

    response = _deliver(client, _closure_payload(SERVED_TASK_ID))

    _acknowledged(response)
    # SPECIFIED by *A closed task records Satisfied*, unchanged outside a
    # stand-down.
    assert len(recorder.calls) == 1, (
        f"a ready playbook did not record the completion: {recorder.calls}"
    )
    assert recorder.calls[0].get("step_id") == SERVED_STEP_ID
    assert _row(mapping, SERVED_STEP_ID).last_observed_closed is True
