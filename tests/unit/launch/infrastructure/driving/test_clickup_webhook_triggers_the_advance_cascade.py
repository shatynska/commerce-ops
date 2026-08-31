"""A webhook delivery that records an outcome triggers the cascade.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-from-clickup-webhook`:
`openspec/changes/advance-gates-from-clickup-webhook/specs/launch-gate-progression/spec.md`

Covers, from the MODIFIED requirement *A recurring pass advances every
launch whose gate may open*, the half of the new exception that is stated
over **the call site**:

    #### Scenario: A ClickUp webhook delivery may trigger an
    advance-and-ask cascade for the launch it completes

and, from the same requirement's MODIFIED scenario:

    #### Scenario: Recording an outcome does not itself advance a launch
    - **THEN** ... unless it was recorded through the ClickUp webhook,
      which may also trigger the cascade immediately

The scenario's second half — that *"every rule this requirement and the
requirements below state about how a gate may open, how a decision is
asked for, and how often, apply to that cascade exactly as they apply to
the pass's own"* — is stated over the cascade, not over the route, and is
in `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py`.

The exclusivity half of the amendment — that the carve-out reaches this
call site and no other — is in
`tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The route, over in-memory doubles. Every assertion here is about what an
HTTP delivery causes — which deliveries trigger the cascade, which do
not, and whether the acknowledgement survives a cascade that explodes —
and nothing below the route can observe any of it: the recording use case
does not know a webhook exists, and the cascade does not know what
invoked it. The webhook harness (verification scheme, delivery shape, the
path read off the router rather than transcribed, the substituted
collaborator names) is transcribed from `test_clickup_webhook.py`, which
records the provenance of each; correcting any of it is a fixture
correction there as much as here.

## Reading the `MAY`

The scenario's THEN says the cascade **MAY** be triggered. Read on its own
that permits an implementation that never triggers anything, which no test
could falsify. It is read as definite here because this change's own
artifacts make it so: `tasks.md` 2.3 requires the call
(`background_tasks.add_task(advance_and_ask, mapped.product_id)`) on the
recording path, and `design.md` — Decision 2 fixes its mechanism. So the
positive assertions below are marked SPECIFIED-BY-TASKS rather than
SPECIFIED, and are the one place a reader should look if the change's
intent about the `MAY` is ever revisited.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- That the trigger is reached as a **bare module global** on
  `clickup_webhook.py` and named in its `__all__` (`tasks.md` 2.1,
  `proposal.md` — Impact), which is what makes `monkeypatch.setattr`
  substitution here legitimate rather than a trick.
- That it is dispatched through FastAPI `BackgroundTasks` (`tasks.md`
  2.2, `design.md` — Decision 2).
- That it is passed the `ProductId` value alone — never the request's
  session, never a loaded entity (`tasks.md` 2.3, `design.md` —
  Decision 2).
- That it fires only on the path that actually recorded a step outcome
  (`tasks.md` 2.4).

INVENTED, and recorded in the manifest as unresolved project questions:

- The trigger's name on the route module. `_TRIGGER_NAMES` probes, and
  `_install_trigger` fails loudly when it can place none, so no test here
  can run green against an unsubstituted real cascade. Correction point:
  `_TRIGGER_NAMES`.

## Expected first-run state

`clickup_webhook.py` carries no cascade trigger (`tasks.md` 2.1-2.3), so
every test in this file except the two negative-path ones is expected to
fail on an **absent target** — `_install_trigger`'s loud failure. Per
`ai-toolkit:testing` that establishes absence only: none of the
assertions below has been exercised. Never resolve it by adding the
attribute; it is `tasks.md` section 2's to add.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `96303a7`: `uv run pytest tests/unit tests/agents` — 1727 passed,
0 failed. `uv run pytest tests/integration` — 3 passed, 124 skipped (no
`DATABASE_URL` is configured here, so that tier did not in fact run).
"""

from __future__ import annotations

import hashlib
import hmac
import inspect
import json
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient

import commerce_ops.launch.infrastructure.driving.clickup_webhook as webhook_module
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
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId

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

WEBHOOK_SECRET: Final = "test-clickup-webhook-secret-not-a-real-credential"
SIGNATURE_HEADER: Final = "X-Signature"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
STEP_ID: Final = "listing.title-conforms"
TASK_ID: Final = "8x2mapped"
UNMAPPED_TASK_ID: Final = "8x2unknown"

LAUNCH_DATE: Final = date(2027, 3, 2)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

#: The names the cascade trigger may carry on the route module. The
#: correction point for this file, per the docstring.
_TRIGGER_NAMES: Final = (
    "advance_and_ask",
    "advance_and_ask_for",
    "trigger_advance_and_ask",
    "advance_launch_and_ask",
)


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


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


def _unready_playbook() -> LaunchPlaybook:
    """A served set in which one gate holds no *active* blocking step —
    the condition `launch-clickup-sync` stands webhook intake down for."""
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = tuple(
        _hold(
            gate, status=StepStatus.DRAFT if gate == "ignition" else StepStatus.ACTIVE
        )
        for gate in SPECIFIED_GATE_ORDER
    )
    return LaunchPlaybook(version="test-v1", gates=gates, steps=(_step(), *steps))


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    """`PlaybookNotReadyError`, under whichever signature it carries —
    transcribed from `test_clickup_webhook_stand_down.py`."""
    from commerce_ops.launch.domain import launch_playbook as playbook_module

    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError`, so a stand-down cannot be provoked here"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": ("ignition",)}),
        ((), {"playbook": playbook, "unheld_gates": ("ignition",)}),
        ((("ignition",), playbook), {}),
        ((playbook, ("ignition",)), {}),
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
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _TaskMapping:
    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool = False


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


@dataclass
class _Journal:
    """What happened, in the order it happened.

    One list shared by the session provider, the recorder and the cascade
    trigger, because the only way to observe *when* the trigger fires
    relative to the recording transaction is to observe both against one
    clock.
    """

    events: list[str] = field(default_factory=list)
    #: How many session scopes were open when each event was appended.
    depth_at: list[int] = field(default_factory=list)
    open_sessions: int = 0

    def note(self, event: str) -> None:
        self.events.append(event)
        self.depth_at.append(self.open_sessions)

    def depth_when(self, event: str) -> int:
        return self.depth_at[self.events.index(event)]


class _RecordingOutcomes:
    """Stands in for `launch.application.record_step_outcome`."""

    def __init__(self, journal: _Journal) -> None:
        self.calls: list[dict[str, Any]] = []
        self._journal = journal

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        self._journal.note("record")
        return ()


class _RecordingTrigger:
    """Stands in for the advance-and-ask cascade the route triggers.

    Records the whole call — positional and keyword — so the tests can
    assert not only *that* it ran but *what it was handed*: `tasks.md` 2.3
    requires the `ProductId` value alone, never the request's session and
    never a loaded entity.
    """

    def __init__(self, journal: _Journal, *, failing: bool = False) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.failing = failing
        self._journal = journal

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        self._journal.note("cascade")
        if self.failing:
            raise RuntimeError("simulated advance-and-ask failure")

    @property
    def products(self) -> list[Any]:
        found: list[Any] = []
        for args, kwargs in self.calls:
            for candidate in (*args, *kwargs.values()):
                if isinstance(candidate, ProductId):
                    found.append(candidate)
                    break
            else:
                found.append(None)
        return found

    @property
    def carried(self) -> list[Any]:
        return [
            candidate
            for args, kwargs in self.calls
            for candidate in (*args, *kwargs.values())
        ]


class _FakePlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> LaunchPlaybook:
        return _playbook()


class _RefusingPlaybookRepository:
    def __init__(self, *args: object, **kwargs: object) -> None: ...

    async def get(self, version: str) -> LaunchPlaybook:
        raise _build_not_ready(_unready_playbook())


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


@pytest.fixture()
def journal() -> _Journal:
    return _Journal()


@pytest.fixture(autouse=True)
def sessionless(monkeypatch: pytest.MonkeyPatch, journal: _Journal) -> None:
    """The route's session provider, counting open scopes.

    Yields `None`: every repository the route builds from it is itself
    substituted, so nothing issues a query and this file stays unit-tier.
    The counting is what lets `test_the_cascade_is_triggered_after_the_
    recording_transaction_has_closed` observe the ordering `tasks.md` 2.3
    fixes.
    """

    @asynccontextmanager
    async def _provider(*args: Any, **kwargs: Any) -> AsyncIterator[None]:
        journal.open_sessions += 1
        try:
            yield None
        finally:
            journal.open_sessions -= 1

    monkeypatch.setattr(webhook_module, "session", _provider)


@pytest.fixture(autouse=True)
def served_playbook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(webhook_module, "PlaybookRepository", _FakePlaybookRepository)


@pytest.fixture()
def recorder(monkeypatch: pytest.MonkeyPatch, journal: _Journal) -> _RecordingOutcomes:
    fake = _RecordingOutcomes(journal)
    monkeypatch.setattr(webhook_module, "record_step_outcome", fake)
    return fake


def _trigger_name() -> str:
    for name in _TRIGGER_NAMES:
        if hasattr(webhook_module, name):
            return name
    pytest.fail(
        f"{webhook_module.__name__} exposes no advance-and-ask trigger under "
        f"any of {_TRIGGER_NAMES}; `tasks.md` 2.1 adds it as a bare module "
        "global. This is the absent-target state, not a defect in this file "
        "— do not add the attribute to make this pass."
    )


def _install_trigger(
    monkeypatch: pytest.MonkeyPatch, journal: _Journal, *, failing: bool = False
) -> _RecordingTrigger:
    fake = _RecordingTrigger(journal, failing=failing)
    monkeypatch.setattr(webhook_module, _trigger_name(), fake)
    return fake


@pytest.fixture()
def trigger(monkeypatch: pytest.MonkeyPatch, journal: _Journal) -> _RecordingTrigger:
    return _install_trigger(monkeypatch, journal)


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


def _endpoint() -> Any:
    posts = [
        route
        for route in webhook_module.router.routes
        if "POST" in getattr(route, "methods", set())
    ]
    assert len(posts) == 1
    return getattr(posts[0], "endpoint", None)


@pytest.fixture()
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(webhook_module.router)
    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Request helpers — transcribed from `test_clickup_webhook.py`
# ---------------------------------------------------------------------------


def _sign(body: bytes, *, secret: str = WEBHOOK_SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _signed_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json", SIGNATURE_HEADER: _sign(body)}


def _unsigned_headers(body: bytes) -> dict[str, str]:
    return {"Content-Type": "application/json"}


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


def _deliver(
    client: TestClient,
    payload: dict[str, Any],
    headers_for: Any = _signed_headers,
) -> Any:
    body = json.dumps(payload).encode("utf-8")
    return client.post(_webhook_path(), content=body, headers=headers_for(body))


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
# Requirement: A recurring pass advances every launch whose gate may open
# Scenario: A ClickUp webhook delivery may trigger an advance-and-ask
# cascade for the launch it completes
# ---------------------------------------------------------------------------


def test_a_delivery_that_records_an_outcome_triggers_the_cascade_for_that_launch(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A ClickUp webhook delivery may trigger an advance-and-ask
    cascade for the launch it completes.

    WHEN a step outcome recorded through the ClickUp webhook satisfies the
    last outstanding condition on a launch's current gate
    THEN the same advance-and-ask cascade the pass runs for that launch MAY
    be triggered immediately, rather than waiting for the next pass.

    The mapped step holds the launch's current gate (`listable`) and is the
    only thing outstanding on it, so the recording this delivery causes is
    exactly the WHEN — not a recording that leaves the gate blocked for
    some other reason.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload())

    _acknowledged(response)
    # Premise: the delivery really did record an outcome, so what follows
    # is a statement about the recording path and not about some other one.
    assert len(recorder.calls) == 1, (
        f"the delivery recorded no outcome, so this test exercised nothing: "
        f"{recorder.calls}"
    )
    # SPECIFIED-BY-TASKS (`tasks.md` 2.3; the scenario's own `MAY` is read
    # as definite — see this module's docstring): the cascade is triggered
    # for the launch the delivery completes.
    assert len(trigger.calls) == 1, (
        "a delivery that recorded a step outcome triggered no advance-and-ask "
        f"cascade: {trigger.calls}"
    )
    assert trigger.products == [PRODUCT_ID], (
        f"the cascade was triggered for the wrong launch, or for none: {trigger.calls}"
    )


def test_the_cascade_is_handed_the_product_identifier_and_nothing_else(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from `tasks.md` 2.3 and `design.md` — Decision 2: "passing
    only the `ProductId` value, never the request's `db_session` or any
    loaded entity".

    No `#### Scenario:` states it. It is asserted because the mechanism the
    design chose depends on it: Starlette runs a background task *after*
    the request's session scope has closed, so a task holding that session
    or an entity loaded through it would touch a closed session at a point
    no test of the happy path would notice.
    """
    mapping = install_mapping(monkeypatch, _mapped(closed=False))
    launch = _active_launch()
    install_launch(monkeypatch, launch)

    _acknowledged(_deliver(client, _status_change_payload()))

    assert len(trigger.calls) == 1, f"no cascade was triggered: {trigger.calls}"
    carried = trigger.carried
    # DERIVED: the identifier is carried.
    assert any(isinstance(value, ProductId) for value in carried), (
        f"the cascade was triggered without naming a product: {trigger.calls}"
    )
    # DERIVED: and no loaded entity or store travels with it.
    forbidden = [
        value
        for value in carried
        if isinstance(value, Launch | LaunchPlaybook | _FakeMapping | _TaskMapping)
    ]
    assert forbidden == [], (
        "the cascade was handed a loaded entity or a store belonging to the "
        f"request rather than the product identifier alone: {forbidden!r}"
    )
    assert launch is not None and mapping is not None  # fixtures really used


def test_the_cascade_is_triggered_after_the_recording_transaction_has_closed(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    journal: _Journal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from `tasks.md` 2.3: the call is made "after the `async with
    session()` block that calls `record_step_outcome` exits (i.e. after
    that transition is committed)".

    No `#### Scenario:` states the ordering, but the cascade's correctness
    turns on it: `advance_and_ask` re-reads the launch in its own session,
    so a trigger firing while the recording transaction is still open would
    judge the gate against a launch that does not yet carry the outcome
    that just satisfied it — the fast path would then routinely do nothing,
    and the defect would be invisible because the periodic pass would
    quietly cover for it ten minutes later.

    Asserted two ways: the cascade runs after the recording, and it runs
    with no session scope open.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    _acknowledged(_deliver(client, _status_change_payload()))

    assert "record" in journal.events, "nothing was recorded"
    assert "cascade" in journal.events, "no cascade was triggered"
    # DERIVED: after the recording.
    assert journal.events.index("cascade") > journal.events.index("record"), (
        f"the cascade ran before the outcome was recorded: {journal.events}"
    )
    # DERIVED: and outside the recording's session scope.
    assert journal.depth_when("cascade") == 0, (
        "the cascade ran while a request session scope was still open, so it "
        "cannot have been dispatched off the response path "
        f"(open scopes: {journal.depth_when('cascade')})"
    )


def test_the_route_defers_the_cascade_rather_than_awaiting_it_inline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from `tasks.md` 2.2 and `design.md` — Decision 2: the
    handler "gains a `BackgroundTasks` parameter" and dispatches through
    it.

    Structural, and deliberately so. The behaviour this pins —
    the acknowledgement is flushed before the cascade runs — is not
    observable through `TestClient`, which drives the response and its
    background tasks within one blocking call. What *is* observable is that
    the route asks FastAPI for the deferral mechanism at all, and that is
    what this asserts. Its companion is
    `test_a_delivery_is_acknowledged_although_the_cascade_explodes`, which
    covers the consequence a reader actually cares about.

    Correction point if the change ever chooses a different deferral
    mechanism: this test, and `design.md` — Decision 2 with it.
    """
    _trigger_name()  # absent-target guard, so this reads as absence not shape
    endpoint = _endpoint()
    assert endpoint is not None, "the webhook router declares no POST endpoint"
    annotations = [
        parameter.annotation
        for parameter in inspect.signature(endpoint).parameters.values()
    ]
    assert any(
        annotation is BackgroundTasks
        or getattr(annotation, "__name__", "") == "BackgroundTasks"
        or "BackgroundTasks" in str(annotation)
        for annotation in annotations
    ), (
        "the webhook handler declares no `BackgroundTasks` parameter, so the "
        "cascade cannot be running off the response path "
        f"(its parameters are {annotations!r})"
    )


def test_a_delivery_is_acknowledged_although_the_cascade_explodes(
    client: TestClient,
    recorder: _RecordingOutcomes,
    journal: _Journal,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED-BY-PROPOSAL (`proposal.md`: it "runs off the webhook's
    response path ... so a slow advance cascade or a slow Slack delivery
    never delays the webhook's acknowledgement back to ClickUp";
    `design.md` — Decision 3: it "never raises into Starlette").

    The cascade substituted here raises. `advance_and_ask`'s own broad
    catch (`tasks.md` 1.2) is not what this test exercises — that is
    `test_advance_and_ask.py`'s — so the fake deliberately raises past it:
    what is asserted is that the *route* is insulated, which is the
    property that still holds if that catch is ever loosened.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())
    exploding = _install_trigger(monkeypatch, journal, failing=True)

    response = _deliver(client, _status_change_payload())

    # Premise: it really did run and really did raise.
    assert len(exploding.calls) == 1, (
        f"the exploding cascade was never reached: {exploding.calls}"
    )
    # SPECIFIED-BY-PROPOSAL: the acknowledgement is unaffected.
    _acknowledged(response)
    # SPECIFIED-BY-PROPOSAL: and the recording it acknowledged stands.
    assert len(recorder.calls) == 1, (
        f"the failing cascade cost the delivery its recording: {recorder.calls}"
    )


# ---------------------------------------------------------------------------
# Requirement: A recurring pass advances every launch whose gate may open
# Scenario: Recording an outcome does not itself advance a launch — the
# amended THEN, whose exception reaches *the recording path only*
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        pytest.param(
            _status_change_payload(task_id=UNMAPPED_TASK_ID),
            "a task no mapping records",
            id="unmapped-task",
        ),
        pytest.param(
            _status_change_payload(event="taskCommentPosted"),
            "an event that is not a status change",
            id="not-a-status-change",
        ),
        pytest.param(
            _status_change_payload(
                before="to do",
                before_type="open",
                after="in progress",
                after_type="custom",
            ),
            "a reopening with no observed closing behind it",
            id="reopening-without-observed-closing",
        ),
    ],
)
def test_a_delivery_that_records_nothing_triggers_no_cascade(
    payload: dict[str, Any],
    why: str,
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED by the MODIFIED requirement's amended sentence.

    The exception it carves is for "the ClickUp webhook's own **recording
    of a step outcome**"; the unqualified SHALL NOT — "this capability
    SHALL NOT advance a launch as part of recording a step outcome" — is
    what remains in force everywhere it does not reach. A delivery that
    records nothing has recorded no step outcome, so nothing licenses it to
    advance a launch. `tasks.md` 2.4 requires the same, call site by call
    site.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, payload)

    _acknowledged(response)
    # Premise: this really is the no-recording path the parameter names.
    assert recorder.calls == [], (
        f"a delivery for {why} recorded an outcome, so this case no longer "
        f"exercises the no-recording path: {recorder.calls}"
    )
    # SPECIFIED: no advance follows a delivery that recorded nothing.
    assert trigger.calls == [], (
        f"a delivery for {why} triggered an advance-and-ask cascade although "
        f"it recorded no step outcome: {trigger.calls}"
    )


def test_a_graduated_launchs_delivery_triggers_no_cascade(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same clause, over the fourth no-recording path.

    Kept out of the parametrization above because it differs in its
    fixture (the launch, not the payload) rather than in its delivery, and
    because it carries a second reason of its own: a graduated launch
    stands at the final gate, which *A launch is not advanced past the
    final gate* forbids advancing in any case.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _graduated_launch())

    response = _deliver(client, _status_change_payload())

    _acknowledged(response)
    assert recorder.calls == [], (
        f"a graduated launch's delivery recorded an outcome: {recorder.calls}"
    )
    # SPECIFIED: no advance for a delivery that recorded nothing.
    assert trigger.calls == [], (
        "a graduated launch's delivery triggered an advance-and-ask cascade: "
        f"{trigger.calls}"
    )


def test_a_delivery_arriving_during_a_stand_down_triggers_no_cascade(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same clause, over the stand-down path `tasks.md` 2.4 names.

    `launch-clickup-sync` already requires that a delivery arriving while
    the served playbook cannot hold a launch records nothing; nothing
    recorded means nothing licensed to advance. The trigger firing here
    would also reach a cascade that must stand down anyway (`design.md` —
    Decision 1, step 2), which is a waste rather than a fault — but the
    requirement's own reason is the one asserted.
    """
    monkeypatch.setattr(
        webhook_module, "PlaybookRepository", _RefusingPlaybookRepository
    )
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload())

    _acknowledged(response)
    assert recorder.calls == [], (
        f"an outcome was recorded during a stand-down: {recorder.calls}"
    )
    # SPECIFIED: no advance for a delivery that recorded nothing.
    assert trigger.calls == [], (
        f"a delivery arriving during a stand-down triggered a cascade: {trigger.calls}"
    )


def test_an_unverifiable_delivery_triggers_no_cascade(
    client: TestClient,
    recorder: _RecordingOutcomes,
    trigger: _RecordingTrigger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same clause, over the path that never gets as far as a mapping.

    `launch-clickup-sync` requires an unverifiable delivery to be rejected
    with nothing recorded. It is asserted here rather than left to that
    capability's own file because the thing being guarded is new: an
    unauthenticated request must not be able to make the system do work
    for a launch of the sender's choosing, which is a property of the
    trigger this change adds and of no test written before it.
    """
    install_mapping(monkeypatch, _mapped(closed=False))
    install_launch(monkeypatch, _active_launch())

    response = _deliver(client, _status_change_payload(), headers_for=_unsigned_headers)

    assert 400 <= response.status_code < 500, (
        f"an unsigned delivery was not rejected: {response.status_code}"
    )
    assert recorder.calls == []
    # SPECIFIED (by `launch-clickup-sync`'s verification requirement, read
    # through this change's amendment): nothing follows a rejected delivery.
    assert trigger.calls == [], (
        "an unverifiable delivery triggered an advance-and-ask cascade: "
        f"{trigger.calls}"
    )


# ---------------------------------------------------------------------------
# Convention guard — DERIVED from `tasks.md` 2.1, not a `#### Scenario:`
# ---------------------------------------------------------------------------


def test_the_trigger_is_a_named_part_of_the_modules_public_surface() -> None:
    """`tasks.md` 2.1: add the trigger "to `clickup_webhook.py`'s bare-global
    imports and `__all__`, following the module's own documented convention
    for testability via `monkeypatch.setattr`".

    Asserted because every other test in this file depends on it: a trigger
    reached through a nested import or a locally-bound name cannot be
    substituted, and the tests above would then be exercising the real
    cascade against fake stores without saying so.
    """
    name = _trigger_name()
    exported = getattr(webhook_module, "__all__", None)
    assert exported is not None, (
        f"{webhook_module.__name__} declares no `__all__`; `tasks.md` 2.1 "
        "requires the trigger to be named in it"
    )
    assert name in exported, (
        f"{name!r} is not named in {webhook_module.__name__}'s `__all__` "
        f"({sorted(exported)}), so it is not part of the module's documented "
        "substitutable surface"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the acknowledgement is *flushed* before the cascade begins.
#   `TestClient` runs a request and its background tasks inside one
#   blocking call, so no assertion available here distinguishes "deferred
#   until after the response" from "awaited inline". The two tests above
#   cover the mechanism (a `BackgroundTasks` parameter) and the
#   consequence (a failing cascade costs neither the acknowledgement nor
#   the recording); the flush itself stays a review obligation on
#   `design.md` — Decision 2.
# - Whether a *slow* cascade delays the acknowledgement. Same reason: the
#   latency the proposal cares about is a property of the deployed ASGI
#   server, not of `TestClient`.
# - Ordering of the background task relative to other requests.
#   `design.md` names this as explicitly unguaranteed and immaterial, so
#   asserting one would impose a rule nobody agreed to.
# - What the cascade then does. That is the cascade's own, and is in
#   `test_advance_and_ask.py`; repeating it here would make these route
#   tests fail for reasons they do not state.
# ---------------------------------------------------------------------------
