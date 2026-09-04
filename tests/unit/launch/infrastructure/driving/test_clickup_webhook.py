"""Webhook intake for `launch-clickup-sync`: verification, then translation.

Derived strictly from the delta spec:
`openspec/changes/add-clickup-completion-loop/specs/launch-clickup-sync/spec.md`

Covers, as ADDED requirements:

- *Webhook deliveries are verified before anything is recorded* -- all
  five scenarios.
- *Completion flows from ClickUp to the launch as a recorded outcome* --
  the four scenarios stated over a received status change (*A closed task
  records Satisfied*, *A reopened task records InProgress*, *A reopening
  without an observed closing records nothing*, *A repeated delivery
  changes nothing*). The requirement's fifth scenario, *The system never
  closes a task*, is a property of the sync passes and is covered in
  `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`.

Every scenario here is stated over an HTTP delivery arriving at an
endpoint -- acknowledged, rejected, or ignored -- so the route itself is
the smallest level that can observe them. Signature verification is
exercised against real HMAC-SHA256 computation, not a stubbed verifier,
so these tests constrain the endpoint's verification rather than a stub of
it -- the discipline `tests/unit/omni_agent/infrastructure/driving/
test_slack_events_endpoint.py` already applies to the Slack adapter.

See `openspec/changes/add-clickup-completion-loop/test-manifest.md` for the
full accounting.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- The module `launch/infrastructure/driving/clickup_webhook.py`
  (`tasks.md` 5.1) and that it is mounted in `main.py` (`tasks.md` 5.3).
- The verification scheme: "HMAC-SHA256 of the raw request body with
  `CLICKUP_WEBHOOK_SECRET`, constant-time compare against the
  `X-Signature` header" (`design.md`).
- `taskStatusUpdated` as the event handled, its status change carried in
  the delivery's history items with the acting ClickUp user, and the
  closed judgement taken from the status `type` field rather than its name
  (`design.md`).

INVENTED, and recorded in the manifest as unresolved project questions:

- The route's URL. Never transcribed here: `_webhook_path()` reads it off
  the module's own `router`, so nothing in this file pins a path. Only
  the mounting guard at the end assumes `main.py` includes the router
  without an extra prefix -- the pattern
  `omni_agent/infrastructure/driving/slack.py` already follows.
- The four module-level collaborator names this file substitutes:
  `session`, `ClickUpMappingRepository`, `LaunchRepository` and
  `record_step_outcome`. `monkeypatch.setattr` is used at its default
  `raising=True`, so a differently-named collaborator fails loudly here
  rather than leaving a test green against an unpatched real one --
  the convention `tests/unit/catalog/infrastructure/driving/
  test_daily_digest_job.py` records. Correcting a name is a fixture
  correction (failure state 3 in `ai-toolkit:testing`).

What must survive unweakened is what each test asserts: which deliveries
are rejected, which are acknowledged, and exactly what is -- and is not --
recorded as a result.

## At the time this pass was written, nothing under test exists

`commerce_ops.launch.infrastructure.driving.clickup_webhook` is created by
task 5.1. Every test here is expected to fail on an absent target
(`ModuleNotFoundError`) until it lands; per `ai-toolkit:testing`, that
failure establishes only absence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, Final

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_ops.launch.domain.launch_playbook import (
    InProgress,
    LaunchPlaybook,
    Satisfied,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.launch.infrastructure.driving import clickup_webhook as webhook_module
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import LAUNCH_DATE, product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step
from tests.support.values import TaskMapping as _TaskMapping

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"

PRODUCT_ID: Final = product_id()
STEP_ID: Final = "listing.title-conforms"
TASK_ID: Final = "8x2mapped"
UNMAPPED_TASK_ID: Final = "8x2unknown"

APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

CLICKUP_SOURCE: Final = "clickup"
ACTOR_USERNAME: Final = "helen.shatynska"
#: The delivery's `user.id` — preferred over `username`/`email` since
#: it's the field a member's `clickup_user_id` can resolve
#: against (`raw-out-the-journal-columns`'s ClickUp actor fix).
ACTOR_ID: Final = "183"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"identifier": STEP_ID, **overrides})


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        name="Work this step asks for",
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        *_fill((_step(),)),
        filler=_hold,
    )


def _active_launch() -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=_playbook(), launch_date=LAUNCH_DATE
    )
    return launch


def _graduated_launch() -> Launch:
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=APPROVED_AT,
                        evidence="filler obligations satisfied by the walk",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=APPROVED_AT,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    assert launch.current_gate == "graduated"
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeMapping:
    """In-memory stand-in for the two mapping tables (`tasks.md` 3.1)."""

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
    """Stands in for `LaunchRepository`; hands back one launch."""

    def __init__(self, launch: Launch) -> None:
        self._launch = launch

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        if product_id == self._launch.product_id:
            return self._launch
        return None


class _RecordingOutcomes:
    """Stands in for `launch.application.record_step_outcome`.

    Accepts anything: the route may hand the use case stores and a
    playbook alongside the recording itself, and none of that is what
    these tests assert on. Only the keyword arguments are inspected.
    """

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
    """Stands in for the process-wide session provider's `session()`.

    Yields `None`: the route passes it to repositories that are themselves
    substituted below, so nothing ever issues a query. This keeps the file
    unit-tier -- no `DATABASE_URL`, no Postgres.
    """
    yield None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _clear_caches() -> None:
    """Drops anything an `lru_cache`-wrapped factory in the route module or
    in the settings module memoised, so one test's secret cannot leak into
    the next through a cache."""
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


class _FakePlaybookRepository:
    """The served-playbook read (`move-playbook-steps-to-postgres`),
    substituted like every other collaborator global: serves the fixture
    playbook, which defines the mapped step."""

    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> LaunchPlaybook:
        return _playbook()


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook_module, "PlaybookRepository", _FakePlaybookRepository)


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
    """The route's own path, read off the router rather than transcribed."""
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
    """The router mounted on a bare app.

    Mounted here rather than reached through `commerce_ops.main` so these
    tests constrain the route's own behaviour and not `main.py`'s
    composition; that `main.py` mounts it is asserted separately at the end
    of this file.
    """
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def _sign(body: bytes, *, secret: str = WEBHOOK_SECRET) -> str:
    """ClickUp's own scheme, as design.md fixes it: HMAC-SHA256 of the raw
    request body, hex-encoded."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _signed_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)}


def _unsigned_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _foreign_secret_headers(body: bytes) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: _sign(body, secret="an-attackers-own-secret"),
    }


def _tampered_body_headers(body: bytes) -> dict[str, str]:
    # Correctly signed -- for a different body than the one being sent.
    return {
        "Content-Type": "application/json",
        SIGNATURE_HEADER: _sign(b'{"event":"something_else"}'),
    }


def _status_change_payload(
    *,
    task_id: str = TASK_ID,
    before: str = "in progress",
    before_type: str = "custom",
    after: str = "complete",
    after_type: str = "closed",
    event: str = "taskStatusUpdated",
) -> dict[str, Any]:
    """A minimal but realistically shaped ClickUp `taskStatusUpdated`
    delivery. The closed judgement lives in each status's `type` field,
    never in its name (`design.md`)."""
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
                    "username": ACTOR_USERNAME,
                    "email": "ops@example.invalid",
                },
            }
        ],
    }


def _deliver(
    client: TestClient,
    payload: dict[str, Any],
    headers_for: Any = _signed_headers,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(_webhook_path(), content=body, headers=headers_for(body))


def _seeded_row(mapping: _FakeMapping) -> _TaskMapping:
    """The one seeded mapping row, read directly rather than awaited --
    these route tests are synchronous (`TestClient` drives the event loop
    itself), so the fake's async readers cannot be called from here."""
    return mapping.tasks[(PRODUCT_ID, STEP_ID)]


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
# Requirement: Webhook deliveries are verified before anything is recorded
# ---------------------------------------------------------------------------


def test_a_validly_signed_delivery_is_processed(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A validly signed delivery is processed.

    WHEN a delivery arrives whose signature matches the configured secret
    THEN it is acknowledged and its status change is processed against the
    mapping.
    """
    mapping = install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload())

    # SPECIFIED: it is acknowledged. DERIVED: "acknowledged" is read as a
    # 2xx, the only acknowledgement an HTTP endpoint has.
    assert 200 <= response.status_code < 300, (
        f"a validly signed delivery was not acknowledged: {response.status_code}"
    )
    # SPECIFIED: its status change is processed against the mapping -- the
    # mapped step, and no other, is what the recording names.
    assert len(recorder.calls) == 1, (
        f"the delivery was not processed against the mapping: {recorder.calls}"
    )
    assert recorder.calls[0].get("step_id") == STEP_ID
    # SPECIFIED by the reconciliation requirement: the retained
    # observed state is updated by every observation, webhook
    # deliveries included.
    assert _seeded_row(mapping).last_observed_closed is True


@pytest.mark.parametrize(
    "headers_for",
    [
        pytest.param(_unsigned_headers, id="no-signature-header"),
        pytest.param(_foreign_secret_headers, id="signed-with-wrong-secret"),
        pytest.param(_tampered_body_headers, id="body-tampered-after-signing"),
    ],
)
def test_a_delivery_failing_signature_verification_is_rejected(
    headers_for: Any,
    client: TestClient,
    recorder: _RecordingOutcomes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An invalid signature is rejected.

    WHEN a delivery arrives whose signature does not match the configured
    secret, or carries no signature
    THEN it is rejected and no outcome is recorded.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload(), headers_for=headers_for)

    # SPECIFIED: it is rejected. DERIVED: "rejected" is read as a 4xx --
    # no artifact pins a status code, so 400/401/403 all satisfy this and
    # a 2xx does not. (The same reading `test_slack_events_endpoint.py`
    # records for the Slack adapter's own verification scenario.)
    assert 400 <= response.status_code < 500, (
        f"an unverifiable delivery was not rejected: {response.status_code}"
    )
    # SPECIFIED: no outcome is recorded.
    assert recorder.calls == []


def test_no_configured_secret_rejects_all_deliveries(
    client: TestClient,
    recorder: _RecordingOutcomes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No configured secret rejects all deliveries.

    WHEN a delivery arrives while no webhook secret is configured
    THEN it is rejected and no outcome is recorded.

    The delivery used is signed with what *would* be the right secret, so
    the rejection can only come from there being no configured secret to
    compare against -- an implementation that treated an absent secret as
    "nothing to check" would acknowledge this and fail here, which is the
    failure mode `design.md` names ("no secret configured means everything
    is rejected, not accepted").
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())
    monkeypatch.delenv("CLICKUP_WEBHOOK_SECRET", raising=False)
    _clear_caches()

    response = _deliver(client, _status_change_payload())

    # SPECIFIED: it is rejected, and nothing is recorded.
    assert 400 <= response.status_code < 500, (
        "a delivery was accepted although no webhook secret is configured: "
        f"{response.status_code}"
    )
    assert recorder.calls == []


def test_an_unmapped_task_is_acknowledged_and_ignored(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An unmapped task is acknowledged and ignored.

    WHEN a verified delivery concerns a task no mapping records
    THEN it is acknowledged and no outcome is recorded.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload(task_id=UNMAPPED_TASK_ID))

    # SPECIFIED: acknowledged -- not rejected, and not an error.
    assert 200 <= response.status_code < 300, (
        f"a delivery for an unmapped task was not acknowledged: {response.status_code}"
    )
    # SPECIFIED: no outcome is recorded.
    assert recorder.calls == []


def test_a_graduated_launchs_task_is_acknowledged_and_ignored(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A graduated launch's task is acknowledged and ignored.

    WHEN a verified delivery concerns a task mapped to a launch that has
    reached `graduated`
    THEN it is acknowledged and no outcome is recorded.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _graduated_launch())

    response = _deliver(client, _status_change_payload())

    # SPECIFIED: acknowledged.
    assert 200 <= response.status_code < 300, (
        "a delivery for a graduated launch's task was not acknowledged: "
        f"{response.status_code}"
    )
    # SPECIFIED: no outcome is recorded.
    assert recorder.calls == []


def test_an_event_other_than_a_status_change_is_acknowledged_and_ignored(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requirement clause, not itself a `#### Scenario:` block.

    The requirement's final sentence names three things a verified
    delivery may be that must be acknowledged without recording: an
    unmapped task, a graduated launch's task, and "an event other than a
    task status change". Two have their own scenarios; this one does not,
    and is covered here rather than left as the one unasserted third of a
    stated requirement.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload(event="taskCommentPosted"))

    # SPECIFIED: acknowledged, nothing recorded.
    assert 200 <= response.status_code < 300, (
        f"an unrelated event was not acknowledged: {response.status_code}"
    )
    assert recorder.calls == []


# ---------------------------------------------------------------------------
# Requirement: Completion flows from ClickUp to the launch as a recorded
# outcome -- the scenarios stated over a received status change
# ---------------------------------------------------------------------------


def test_a_closed_task_records_satisfied(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A closed task records Satisfied.

    WHEN a mapped task's status change to a closed status is received
    THEN a `Satisfied` outcome is recorded for the mapped step with
    provenance source `clickup` and the task as evidence.

    The closed status is deliberately *named* something a name-based
    implementation would not recognise ("shipped"), while carrying
    `type: closed`: `design.md` requires the judgement to come from the
    type field so the team can rename statuses freely.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(
        client, _status_change_payload(after="shipped", after_type="closed")
    )

    assert 200 <= response.status_code < 300
    # SPECIFIED: a `Satisfied` outcome for the mapped step.
    assert len(recorder.calls) == 1, f"expected one recording, got {recorder.calls}"
    recorded = recorder.calls[0]
    assert recorded.get("step_id") == STEP_ID
    assert recorded.get("outcome") is Satisfied

    provenance = recorded.get("provenance")
    assert provenance is not None, "the recording carried no provenance"
    # SPECIFIED: provenance source `clickup`.
    assert provenance.source == CLICKUP_SOURCE
    # SPECIFIED: the ClickUp actor, where the delivery identifies one.
    # DERIVED: `user.id` specifically, not `username` -- the spec's own
    # text ("the ClickUp actor where the delivery identifies one") does
    # not fix a field, but `id` is what a member's
    # `clickup_user_id` can resolve against later, which `username`
    # cannot.
    assert ACTOR_ID in str(provenance.who), (
        f"the delivery's acting ClickUp user is not recorded by id: {provenance.who!r}"
    )
    assert ACTOR_USERNAME not in str(provenance.who), (
        f"the delivery's acting ClickUp user is recorded by username, not id: "
        f"{provenance.who!r}"
    )
    # SPECIFIED: the task as evidence.
    assert TASK_ID in str(provenance.evidence), (
        f"the task is not identifiable in the evidence: {provenance.evidence!r}"
    )


def test_a_reopened_task_records_in_progress(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A reopened task records InProgress.

    WHEN a status change to an open status is received for a mapped task
    whose retained observed state is closed
    THEN an `InProgress` outcome is recorded for the mapped step with
    provenance source `clickup`.
    """
    mapping = install_mapping(monkeypatch, _mapped(closed=True))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(
        client,
        _status_change_payload(
            before="complete",
            before_type="closed",
            after="in progress",
            after_type="custom",
        ),
    )

    assert 200 <= response.status_code < 300
    # SPECIFIED: an `InProgress` outcome with provenance source `clickup`.
    assert len(recorder.calls) == 1, f"expected one recording, got {recorder.calls}"
    assert recorder.calls[0].get("step_id") == STEP_ID
    assert recorder.calls[0].get("outcome") is InProgress
    reopened_provenance = recorder.calls[0].get("provenance")
    assert reopened_provenance is not None, "the recording carried no provenance"
    assert reopened_provenance.source == CLICKUP_SOURCE
    # SPECIFIED by the reconciliation requirement: every observation --
    # webhook and reconciliation alike -- updates the retained state.
    assert _seeded_row(mapping).last_observed_closed is False


def test_a_reopening_without_an_observed_closing_records_nothing(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A reopening without an observed closing records nothing.

    WHEN a status change to an open status is received for a mapped task
    that was never observed closed
    THEN no outcome is recorded for the mapped step.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(
        client,
        _status_change_payload(
            before="to do",
            before_type="open",
            after="in progress",
            after_type="custom",
        ),
    )

    # SPECIFIED: not an error -- the delivery is still acknowledged.
    assert 200 <= response.status_code < 300
    # SPECIFIED: no outcome is recorded for the mapped step.
    assert recorder.calls == [], (
        "an outcome was recorded for an open-to-open change against a task "
        "that was never observed closed"
    )


def test_a_repeated_delivery_changes_nothing(
    client: TestClient, recorder: _RecordingOutcomes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A repeated delivery changes nothing.

    WHEN the same status change for a mapped task is received more than
    once
    THEN the step's recorded outcome after the repeat is the same as after
    the first delivery
    AND the repeat is not an error.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    first = _deliver(client, _status_change_payload())
    after_first = list(recorder.outcomes)
    repeat = _deliver(client, _status_change_payload())

    # SPECIFIED: the repeat is not an error.
    assert 200 <= first.status_code < 300
    assert 200 <= repeat.status_code < 300, (
        f"a re-delivered webhook was treated as an error: {repeat.status_code}"
    )
    # SPECIFIED: the step's recorded outcome after the repeat is the same
    # as after the first delivery.
    assert after_first == [Satisfied]
    assert recorder.outcomes[: len(after_first)] == after_first
    assert set(recorder.outcomes) == {Satisfied}, (
        f"the repeat changed the step's recorded outcome: {recorder.outcomes}"
    )
    # DERIVED (`design.md`: "a re-delivered webhook shows no transition
    # against the already-updated observed state and records nothing").
    # The scenario above is satisfied by an idempotent re-recording too;
    # this asserts the mechanism the design chose, so a regression to
    # recording-on-every-delivery is visible rather than silent.
    assert len(recorder.calls) == 1, (
        f"the repeat produced a second recording: {recorder.calls}"
    )


# ---------------------------------------------------------------------------
# Wiring guard -- DERIVED from `tasks.md` 5.3, not a `#### Scenario:`
# ---------------------------------------------------------------------------


def test_the_webhook_route_is_mounted_in_the_application() -> None:
    """`tasks.md` 5.3: "Mount the webhook router in `main.py`".

    Asserted behaviourally, exactly as
    `tests/unit/launch/infrastructure/driving/test_main_monitoring_wiring.py`
    records: a request that would 404 if nothing were mounted at the path.
    An unsigned delivery is used so nothing downstream runs -- the route
    must reject it before any payload-dependent behaviour -- which also
    means this guard needs no collaborators substituted.

    If `main.py` mounts the router under a prefix, this test's use of the
    router's own path is the thing to correct, not what it asserts.
    """
    from commerce_ops.main import app

    with TestClient(app) as test_client:
        response = test_client.post(
            _webhook_path(),
            content=b'{"event":"taskStatusUpdated"}',
            headers={"Content-Type": "application/json"},
        )

    assert response.status_code != 404, (
        f"nothing is mounted at {_webhook_path()!r}; the ClickUp webhook "
        "router is not included in commerce_ops.main"
    )
    assert response.status_code != 405, (
        f"{_webhook_path()!r} exists but does not accept POST"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Replay protection by timestamp. ClickUp's scheme, as `design.md`
#   states it, signs the body alone -- there is no timestamp header to
#   check, unlike Slack's -- so no stale-delivery case is asserted.
# - Whether verification uses a constant-time comparison (`design.md`
#   requires it). Timing behaviour is not observable from a functional
#   test; a wrong-signature rejection passes either way. This stays a
#   review obligation on the implementation.
# - The acknowledgement body's shape, and whether processing happens
#   before or after the acknowledgement. No scenario states either;
#   `design.md` gives the route "exactly one thing: translate a verified
#   status change into the same recording call, sooner", with no
#   acknowledgement-window requirement of the kind `slack-trigger`
#   carries.
# - A delivery whose history items name no acting user. The requirement
#   says "the ClickUp actor where the delivery identifies one", which
#   leaves the other case open rather than stating it.
# ---------------------------------------------------------------------------
