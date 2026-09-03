"""The recurring pass that invokes an `automated` step's handler.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirements, every scenario stated over *a pass
running*:

- *An automated step's handler is invoked by recurring work* — all four
  scenarios.
- *A handler receives the step, the launch and the product, and
  attributes nothing* — all three scenarios. *A handler cannot claim
  another source* is covered here in the half a recording is needed to
  observe (the constructed provenance standing); its other half — that
  the contract type has no place to put provenance — is asserted in
  `tests/unit/launch/application/test_step_handler_contract.py`.
- *A non-terminal outcome is recorded directly and never held for a
  decision* — its recording scenario in full, and the *first* half of
  *A step reporting no progress is reconsidered on the next pass*, which
  `cool-off-a-repeatedly-blocked-step` narrowed to the changed-outcome
  case. The repeat case, and the cool-off that now follows it, are in
  `test_automation_pass_repeat_backoff.py`.
- *A terminal outcome the step's hazard forbids is a handler fault, not a
  recording* — its one scenario.
- *An unregistered handler is reported and skipped, never fatal* — its
  one scenario.
- *A handler failure resolves nothing and does not stop the pass* — all
  three scenarios.
- *A result needing no confirmation is recorded at once* — its one
  scenario.
- *A result needing confirmation is held until a member decides* — *A
  confirmable terminal result is held rather than recorded* and *A
  pending result suppresses re-invocation*. Its third scenario (two
  overlapping passes) is a concurrency guarantee of the store's partial
  unique index and is integration-tier:
  `tests/integration/launch/test_automated_result_store_live.py`.
- *A pending result is delivered for a decision, and delivery failure
  does not lose it* — *Undelivered is not undone* and *An undelivered
  result is delivered again later*. Its first scenario (what the Slack
  message names) is about the message and lives in
  `tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py`.
- *A rejected step is not re-proposed immediately* — both scenarios.

The requirement statement's two clauses that no scenario carries — that
the pass declares a schedule and a tolerance, and that invocation is not
reachable from outside the deployment — are covered in
`tests/unit/launch/infrastructure/driving/test_automation_pass_schedule.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

Every scenario above is stated over *a pass* — what it invokes, what it
records, what it stores, what it reports. The pass function over
in-memory doubles is the smallest unit that can observe those, and it is
the level `tests/unit/launch/infrastructure/driven/test_clickup_sync_*.py`
already establishes for this module's other recurring walk.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `launch/infrastructure/driving/automation_pass.py` as the pass's home
  (`design.md`, "The invoker is a scheduled job module"; `tasks.md` 4.1).
- The walk: non-graduated launches via `list_active()`, and within each,
  served steps whose kind is `automated`, whose recorded outcome is not
  terminal for their hazard, and which carry no pending result
  (`tasks.md` 4.2).
- The branch on **terminality**, not on the confirmation flag alone
  (`tasks.md` 2.5) and the hazard check before storing or recording
  (`tasks.md` 2.6).
- Delivery of undelivered pending results at the start of each pass,
  stamping delivery only on success (`tasks.md` 4.6).
- A 24-hour post-rejection cool-off as a module constant, never
  configuration (`design.md`, "A cool-off after rejection").
- "Reported" as a warning-level application log record — the reading
  `tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py`
  already records for this module's other pass.
- "Recorded as a successful run" as *the pass body returns normally* —
  the only outcome signal a job body has, and the reading
  `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`
  records for the same words.

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The pass's entry point name. `_pass_entry()` probes the module's public
  surface for it and fails loudly rather than defaulting.
- Its call shape — collaborators as keyword arguments, mirroring
  `converge_launch(...)`/`reconcile_launch(...)` in this module's driven
  layer. `_run_pass` below is the single correction point.
- That a handler is **awaited**. The whole module is async and the one
  handler this change writes makes a network call, so the contract is
  assumed async. Correction point: `_ScriptedHandler.__call__`.
- The pending-result repository's method names (`_FakeResults`), and the
  pending row's attribute names (`_PendingRow`). `tasks.md` 1.4 fixes the
  operations, not their spellings.
- `now=` as how the pass is told the moment it is running as of. The spec
  fixes that a handler receives "the moment the pass is running as of",
  not how the pass obtains it; injecting it is what makes the cool-off
  observable without freezing a clock.

What must survive any correction is what each test asserts: which
handlers are invoked, what is recorded, what is stored, what is
delivered, and — for the several requirements stated in the negative —
what is *not*.

## Expected first-run state

Nothing under test exists: `automation_pass.py`, `StepContext` and
`StepResolution` are created by tasks 4.1 and 2.1. Every test here is
expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing` that establishes absence only — the assertions have
not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
`uv run pytest tests/integration` — 3 passed, 81 skipped (no database is
configured here).
"""

from __future__ import annotations

import inspect
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    Hazard,
    InProgress,
    LaunchPlaybook,
    NotApplicable,
    NotStarted,
    OffsetAnchor,
    Refused,
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
from commerce_ops.launch.infrastructure.driving import automation_pass
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
OTHER_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

AUTOMATED_STEP_ID: Final = "listing.sub-category"
HUMAN_STEP_ID: Final = "listing.title-conforms"
HANDLER_NAME: Final = "listing.subcategory_advisor"
UNREGISTERED_HANDLER: Final = "listing.nothing_registers_this"

ALICE: Final = "prs_01HQ8Z6M4A"

LAUNCH_DATE: Final = date(2027, 3, 2)
NOW: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 5, 9, 30, tzinfo=UTC)

# `design.md`: "24 hours, as a module constant."
COOL_OFF: Final = timedelta(hours=24)

RECOMMENDATION: Final = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home & Kitchen > "
    "Home Decor, which carries no food-contact obligation and would "
    "understate the compliance surface."
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": AUTOMATED_STEP_ID,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (ALICE,),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _automated(**overrides: Any) -> StepDefinition:
    """The step under test: `active`, `automated`, naming a handler."""
    attributes: dict[str, Any] = {
        "kind": StepKind.AUTOMATED,
        "handler": HANDLER_NAME,
        "assignees": (),
    }
    attributes.update(overrides)
    return _step(**attributes)


def _hold(gate: str) -> StepDefinition:
    """One blocking step per gate, satisfying the gate-holding floor.

    `human`, deliberately: an `automated` filler would itself be a
    candidate for invocation and would contaminate every assertion below
    about which handlers the pass reached.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _launch(playbook: LaunchPlaybook, product_id: ProductId = PRODUCT_ID) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _graduate(launch: Launch, playbook: LaunchPlaybook) -> Launch:
    """Walk a launch to `graduated` by satisfying only its blocking work.

    The automated step under test stays unresolved throughout, which is
    exactly the shape *A graduated launch is left alone* needs: a step the
    pass would invoke on any launch that had not graduated.
    """
    while launch.current_gate != "graduated":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and step.identifier.startswith("hold."):
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="clickup",
                        who="Helen",
                        when=APPROVED_AT,
                        evidence="blocking work signed off",
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


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
    """The catalog read the pass injects, per `tasks.md` 4.8."""

    def __init__(self) -> None:
        self.reads: list[ProductId] = []

    async def __call__(self, product_id: ProductId) -> _CatalogProduct:
        self.reads.append(product_id)
        return _CatalogProduct(name=PRODUCT_NAME, sku=PRODUCT_SKU)


class _FakeLaunches:
    def __init__(self, *launches: Launch) -> None:
        self._launches = list(launches)

    async def list_active(self) -> list[Launch]:
        return list(self._launches)

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        for launch in self._launches:
            if launch.product_id == product_id:
                return launch
        return None


class _ScriptedHandler:
    """A registered handler returning a scripted resolution.

    INVENTED: that a handler is awaited (see the module docstring). The
    single correction point for a synchronous contract.
    """

    def __init__(self, resolution: StepResolution | None = None) -> None:
        self.resolution = resolution
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        assert self.resolution is not None
        return self.resolution

    @property
    def invoked(self) -> bool:
        return bool(self.contexts)


class _RaisingHandler:
    """A handler whose invocation fails — the crash case."""

    def __init__(self) -> None:
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        raise RuntimeError("simulated handler failure")

    @property
    def invoked(self) -> bool:
        return bool(self.contexts)


class _FakeHandlers:
    """The step-handler registry, in the both-shapes form
    `tests/unit/launch/application/test_step_activation.py` records: a
    container answering `__contains__` and `names()`, plus a `resolve`."""

    def __init__(self, **handlers: Any) -> None:
        self._handlers = dict(handlers)

    def __contains__(self, name: object) -> bool:
        return name in self._handlers

    def names(self) -> tuple[str, ...]:
        return tuple(self._handlers)

    def resolve(self, name: str) -> Any:
        return self._handlers[name]

    def get(self, name: str, default: Any = None) -> Any:
        return self._handlers.get(name, default)


@dataclass
class _PendingRow:
    product_id: ProductId
    step_id: str
    handler: str
    proposed_outcome: Any
    result_text: str
    produced_at: datetime
    state: str = "pending"
    delivered_at: datetime | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None


class _FakeResults:
    """In-memory stand-in for `AutomatedResultRepository` (`tasks.md` 1.4)."""

    def __init__(self) -> None:
        self.rows: list[_PendingRow] = []

    async def pending_for(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        for row in self.rows:
            if (
                row.product_id == product_id
                and row.step_id == step_id
                and row.state == "pending"
            ):
                return row
        return None

    async def store(
        self,
        *,
        product_id: ProductId,
        step_id: str,
        handler: str,
        proposed_outcome: Any,
        result_text: str,
        produced_at: datetime,
        finding: Any = None,
    ) -> _PendingRow:
        row = _PendingRow(
            product_id=product_id,
            step_id=step_id,
            handler=handler,
            proposed_outcome=proposed_outcome,
            result_text=result_text,
            produced_at=produced_at,
        )
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[_PendingRow]:
        return [
            row
            for row in self.rows
            if row.state == "pending" and row.delivered_at is None
        ]

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        target = self._row_of(row)
        target.delivered_at = when or NOW

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> _PendingRow | None:
        rejected = [
            row
            for row in self.rows
            if row.product_id == product_id
            and row.step_id == step_id
            and row.state == "rejected"
        ]
        if not rejected:
            return None
        return max(rejected, key=lambda row: row.decided_at or row.produced_at)

    def _row_of(self, row: object) -> _PendingRow:
        if isinstance(row, _PendingRow):
            return row
        for candidate in self.rows:
            if candidate is row or getattr(row, "id", None) is candidate:
                return candidate
        raise AssertionError(f"unknown pending row {row!r}")

    # -- seeding helpers, used by the tests themselves ---------------------

    def seed_pending(
        self,
        *,
        product_id: ProductId = PRODUCT_ID,
        step_id: str = AUTOMATED_STEP_ID,
        delivered: bool = True,
    ) -> _PendingRow:
        row = _PendingRow(
            product_id=product_id,
            step_id=step_id,
            handler=HANDLER_NAME,
            proposed_outcome=Satisfied,
            result_text=RECOMMENDATION,
            produced_at=NOW - timedelta(hours=1),
            delivered_at=NOW - timedelta(hours=1) if delivered else None,
        )
        self.rows.append(row)
        return row

    def seed_rejection(self, *, decided_at: datetime) -> _PendingRow:
        row = _PendingRow(
            product_id=PRODUCT_ID,
            step_id=AUTOMATED_STEP_ID,
            handler=HANDLER_NAME,
            proposed_outcome=Satisfied,
            result_text=RECOMMENDATION,
            produced_at=decided_at - timedelta(minutes=5),
            state="rejected",
            delivered_at=decided_at - timedelta(minutes=4),
            decided_by=ALICE,
            decided_at=decided_at,
        )
        self.rows.append(row)
        return row

    @property
    def pending_rows(self) -> list[_PendingRow]:
        return [row for row in self.rows if row.state == "pending"]


class _RecordingOutcomes:
    """Stands in for `record_step_outcome`; only the keywords are read."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    @property
    def outcomes(self) -> list[Any]:
        return [call.get("outcome") for call in self.calls]

    def for_step(self, step_id: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("step_id") == step_id]


class _FakeDelivery:
    """Stands in for posting a pending result to Slack."""

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)
        if self.failing:
            raise RuntimeError("simulated Slack delivery failure")


@dataclass
class _Collaborators:
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    handlers: _FakeHandlers
    results: _FakeResults = field(default_factory=_FakeResults)
    recorder: _RecordingOutcomes = field(default_factory=_RecordingOutcomes)
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    delivery: _FakeDelivery = field(default_factory=_FakeDelivery)


# ---------------------------------------------------------------------------
# The pass, reached through one correction point
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)


def _pass_entry() -> Any:
    """The pass's own callable, found by probing rather than assumed.

    Fails loudly rather than defaulting, so no test below can pass
    against an entry point that is not the pass.
    """
    for name in _ENTRY_NAMES:
        found = getattr(automation_pass, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no pass entry point found on "
        f"{automation_pass.__name__} under any of {_ENTRY_NAMES} — correct "
        "this file's probe to the implemented name"
    )


class _InertBackoff:
    """A backoff record that holds nothing and fails at nothing."""

    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def note(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _InertNotifier:
    """A monitoring notifier nothing in this file exercises."""

    async def post_monitoring_message(self, message: str) -> None:
        return None


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    """Thread-establishment nothing in this file exercises.

    Added by `thread-launch-slack-notifications`, which made it a required
    collaborator like `backoff` and `notifier` above -- inert here for the
    same reason: nothing below asserts on threading or tagging, that has
    its own file.
    """
    return "FAKE_THREAD_TS", None


async def _run_pass(collaborators: _Collaborators, *, now: datetime = NOW) -> Any:
    """INVENTED call shape — the single correction point."""
    entry = _pass_entry()
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbook": collaborators.playbook,
        "handlers": collaborators.handlers,
        "results": collaborators.results,
        "record_outcome": collaborators.recorder,
        "read_product": collaborators.catalog,
        "deliver": collaborators.delivery,
        # Added by `cool-off-a-repeatedly-blocked-step`, which made both
        # required. Inert on purpose: `read` finding no row is the
        # pre-change world, so every assertion in this file still
        # observes what it observed before. The repeat cool-off has its
        # own file.
        "backoff": _InertBackoff(),
        "notifier": _InertNotifier(),
        "establish_thread": _inert_establish_thread,
        "now": now,
    }
    accepted = set(inspect.signature(entry).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct "
        "`_run_pass` to the implemented collaborator names"
    )
    return await entry(**supplied)


def _setup(
    *steps: StepDefinition,
    handler: Any | None = None,
    launches: tuple[Launch, ...] | None = None,
    registry: _FakeHandlers | None = None,
) -> _Collaborators:
    playbook = _playbook(*steps)
    return _Collaborators(
        launches=_FakeLaunches(*(launches or (_launch(playbook),))),
        playbook=playbook,
        handlers=registry
        or _FakeHandlers(**{HANDLER_NAME: handler or _ScriptedHandler()}),
    )


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# Requirement: An automated step's handler is invoked by recurring work
# ---------------------------------------------------------------------------


async def test_an_unresolved_automated_step_is_invoked() -> None:
    """Scenario: An unresolved automated step is invoked.

    WHEN a pass runs over a launch whose served playbook carries an
    `active` `automated` step with no recorded outcome, no pending result
    and no recent rejection
    THEN that step's named handler is invoked.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    # SPECIFIED: the step's named handler is invoked.
    assert handler.invoked, "the unresolved automated step's handler was not invoked"


async def test_a_human_step_is_never_invoked() -> None:
    """Scenario: A human step is never invoked.

    WHEN a pass runs over a launch whose served playbook carries an
    `active` `human` step
    THEN no handler is invoked for it, whether or not it needs
    confirmation.

    Both confirmation flags are exercised, because the scenario says
    "whether or not it needs confirmation" and an implementation keying
    on the flag rather than on kind would pass on one of them alone.
    """
    plain = _step(identifier=HUMAN_STEP_ID, handler=None)
    confirming = _step(
        identifier="listing.needs-a-nod",
        assignees=(),
        confirmer=ALICE,
        handler=None,
    )
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(plain, confirming, handler=handler)

    await _run_pass(collaborators)

    # SPECIFIED: no handler is invoked for a `human` step.
    assert not handler.invoked
    # SPECIFIED (the recording half of "no handler is invoked for it"):
    # nothing is recorded and nothing is held for either step.
    assert collaborators.recorder.calls == []
    assert collaborators.results.rows == []


async def test_a_resolved_step_is_not_invoked_again() -> None:
    """Scenario: A resolved step is not invoked again.

    WHEN a pass runs over an `automated` step whose recorded outcome is
    one its hazard permits as terminal
    THEN its handler is not invoked and its recorded outcome is left
    unchanged.
    """
    step = _automated()
    playbook = _playbook(step)
    launch = _launch(playbook)
    launch.record_step_outcome(
        playbook,
        step_id=AUTOMATED_STEP_ID,
        outcome=Satisfied,
        provenance=Provenance(
            source="automated",
            who=HANDLER_NAME,
            when=APPROVED_AT,
            evidence=RECOMMENDATION,
        ),
    )

    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked("would overwrite"), result="not this")
    )
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    await _run_pass(collaborators)

    # SPECIFIED: the handler is not invoked.
    assert not handler.invoked
    # SPECIFIED: the recorded outcome is left unchanged.
    progress = launch.progress_for(AUTOMATED_STEP_ID)
    assert progress is not None
    assert progress.outcome is Satisfied
    assert collaborators.recorder.calls == []


async def test_a_terminal_not_applicable_also_stops_re_invocation() -> None:
    """Scenario: A resolved step is not invoked again — the second
    outcome `Hazard.NONE` permits as terminal.

    SPECIFIED by the requirement statement ("the step's recorded outcome
    is not one the step's hazard permits as terminal"), which is a
    property of the hazard's whole permitted set rather than of
    `Satisfied` alone. An implementation testing `outcome is Satisfied`
    passes the scenario above and fails here.
    """
    step = _automated()
    playbook = _playbook(step)
    launch = _launch(playbook)
    launch.record_step_outcome(
        playbook,
        step_id=AUTOMATED_STEP_ID,
        outcome=NotApplicable("single-marketplace product; the node is EU-only"),
        provenance=Provenance(
            source="automated",
            who=HANDLER_NAME,
            when=APPROVED_AT,
            evidence=RECOMMENDATION,
        ),
    )

    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    await _run_pass(collaborators)

    assert not handler.invoked
    assert collaborators.recorder.calls == []


async def test_a_graduated_launch_is_left_alone() -> None:
    """Scenario: A graduated launch is left alone.

    WHEN a pass runs and a launch has reached `graduated`
    THEN no handler is invoked for any of its steps.
    """
    step = _automated()
    playbook = _playbook(step)
    launch = _graduate(_launch(playbook), playbook)

    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    await _run_pass(collaborators)

    # SPECIFIED: no handler is invoked for any of its steps.
    assert not handler.invoked
    assert collaborators.recorder.for_step(AUTOMATED_STEP_ID) == []
    assert collaborators.results.rows == []


# ---------------------------------------------------------------------------
# Requirement: A handler receives the step, the launch and the product,
# and attributes nothing
# ---------------------------------------------------------------------------


async def test_the_product_is_supplied_not_fetched() -> None:
    """Scenario: The product is supplied, not fetched.

    WHEN a handler is invoked for a step on a launch
    THEN its context carries the catalog product that launch is for,
    resolved before the handler ran.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    assert handler.contexts, "the handler was never invoked, so nothing was supplied"
    context = handler.contexts[0]

    # SPECIFIED: the context carries the catalog product that launch is
    # for, and the pass — not the handler — resolved it.
    assert getattr(context, "product", None) is not None
    assert context.product.name == PRODUCT_NAME
    assert collaborators.catalog.reads == [PRODUCT_ID]

    # SPECIFIED: the context also carries the step it is resolving, the
    # launch it is resolving against, and the moment the pass runs as of.
    assert context.step.identifier == AUTOMATED_STEP_ID
    assert getattr(context, "launch", None) is not None
    assert context.as_of == NOW


async def test_a_produced_outcome_is_attributed_to_the_handler() -> None:
    """Scenario: A produced outcome is attributed to the handler.

    WHEN a handler returns a resolution and its outcome is recorded
    THEN the recorded provenance has source `automated`, names the
    handler, carries the moment of the run, and carries the produced
    result as its evidence.

    Recorded here through the no-confirmation branch, which is the one
    that records without a member; the accepted-result branch names the
    accepter instead and is asserted in
    `tests/unit/launch/application/test_automated_result_decisions.py`.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1, f"expected exactly one recording, got {calls}"
    provenance = calls[0]["provenance"]

    # SPECIFIED, all four.
    assert provenance.source == "automated"
    assert HANDLER_NAME in str(provenance.who)
    assert provenance.when == NOW
    assert RECOMMENDATION in str(provenance.evidence)


async def test_a_smuggled_provenance_does_not_displace_the_constructed_one() -> None:
    """Scenario: A handler cannot claim another source — the half a
    recording is needed to observe.

    WHEN a handler attempts to supply provenance of its own
    THEN the system rejects it and the provenance the system constructed
    stands.

    The contract half — that a `StepResolution` has no place to put
    provenance — is asserted in
    `tests/unit/launch/application/test_step_handler_contract.py`. This
    is the half that matters if a handler routes round the contract with
    a duck-typed return: the requirement says the system SHALL construct
    the provenance for **every** outcome a handler produces, so what is
    recorded must be the constructed one whatever the handler attached.
    """

    class _SmugglingResolution:
        """A resolution-shaped object carrying an attribution of its own."""

        outcome = Satisfied
        result = RECOMMENDATION
        provenance = Provenance(
            source="clickup",
            who="a member who never saw this",
            when=APPROVED_AT,
            evidence="signed off by hand",
        )

    class _SmugglingHandler:
        async def __call__(self, context: Any) -> Any:
            return _SmugglingResolution()

    collaborators = _setup(_automated(), handler=_SmugglingHandler())

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    if calls:
        # SPECIFIED: the provenance the system constructed stands — source
        # `automated`, the handler as what did the work, the moment of the
        # run, the produced text as evidence.
        provenance = calls[0]["provenance"]
        assert provenance.source == "automated"
        assert HANDLER_NAME in str(provenance.who)
        assert provenance.when == NOW
        assert "signed off by hand" not in str(provenance.evidence)
    else:
        # SPECIFIED, the other permissible reading of "the system rejects
        # it": refusing the smuggled resolution outright. What must not
        # happen is a recording carrying the handler's own attribution,
        # and neither branch here permits one.
        assert collaborators.results.rows == []


# ---------------------------------------------------------------------------
# Requirement: A non-terminal outcome is recorded directly and never held
# for a decision
# ---------------------------------------------------------------------------


async def test_a_non_terminal_outcome_on_a_confirmable_step_is_recorded_not_held() -> (
    None
):
    """Scenario: A non-terminal outcome on a confirmable step is
    recorded, not held.

    WHEN a handler proposes `Blocked` with a reason for a step whose
    confirmation flag is true
    THEN the outcome is recorded against the launch with `automated`
    provenance, no pending result is stored, and no decision is
    requested.

    This is the trap `design.md` records the confirmation branch being
    moved to close: an implementation branching on the confirmation flag
    alone holds "please accept: Blocked" and fails all three halves.
    """
    reason = "the marketplace's category tree gave no confident answer"
    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked(reason), result=f"No node chosen: {reason}")
    )
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    # SPECIFIED: recorded against the launch, with `automated` provenance.
    assert len(calls) == 1, f"expected the non-terminal outcome recorded, got {calls}"
    assert isinstance(calls[0]["outcome"], Blocked)
    assert calls[0]["outcome"].reason == reason
    assert calls[0]["provenance"].source == "automated"
    # SPECIFIED: no pending result is stored.
    assert collaborators.results.rows == []
    # SPECIFIED: no decision is requested.
    assert collaborators.delivery.delivered == []


@pytest.mark.parametrize(
    ("outcome", "produced"),
    [
        pytest.param(
            NotStarted, "nothing has begun on this node choice yet", id="not-started"
        ),
        pytest.param(
            InProgress, "the category tree read is still running", id="in-progress"
        ),
    ],
)
async def test_a_reasonless_non_terminal_outcome_is_recorded_directly_too(
    outcome: Any, produced: str
) -> None:
    """Requirement statement: "Where the outcome a handler proposes is not
    terminal — `NotStarted`, `InProgress` or `Blocked` ... the system
    SHALL record it against the launch immediately ... **whatever the
    step's confirmation flag says**".

    Stated in no scenario for the two outcomes that cannot carry a
    reason, and covered here because those are the two an implementation
    branching on "is this a `Blocked`?" would treat differently. The
    requirement additionally says the produced text states the reason
    where the outcome cannot, which is what makes the stalled step
    legible — asserted through the evidence.
    """
    handler = _ScriptedHandler(StepResolution(outcome=outcome, result=produced))
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    assert len(calls) == 1
    assert calls[0]["outcome"] is outcome
    assert produced in str(calls[0]["provenance"].evidence)
    assert collaborators.results.rows == []


async def test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass() -> None:
    """Scenario: A step reporting no progress is reconsidered on the next
    pass — the case where nothing was recorded to repeat against.

    WHEN a handler proposes a non-terminal outcome that differs from the
    one the step already carries, and a later pass runs
    THEN the handler is invoked again for that step.

    Re-attributed by `cool-off-a-repeatedly-blocked-step`, which narrowed
    this scenario: a handler *repeating* the outcome the step carries now
    cools the step off instead. Nothing here changed, because nothing
    here was ever the repeat case — this file's recorder never writes to
    the launch, so the step carries no outcome on either pass and both
    are the first-outcome case the scenario still covers. The repeat and
    its cool-off live in `test_automation_pass_repeat_backoff.py`.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Blocked("no confident node"), result="still nothing")
    )
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)

    await _run_pass(collaborators)
    assert len(handler.contexts) == 1

    await _run_pass(collaborators, now=NOW + timedelta(minutes=15))

    # SPECIFIED: the handler is invoked again — a non-terminal outcome
    # leaves the step eligible for the next pass.
    assert len(handler.contexts) == 2


# ---------------------------------------------------------------------------
# Requirement: A terminal outcome the step's hazard forbids is a handler
# fault, not a recording
# ---------------------------------------------------------------------------


async def test_an_impermissible_proposal_is_refused_before_it_is_stored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: An impermissible proposal is refused before it is stored.

    WHEN a handler proposes a terminal outcome the step's hazard does not
    permit
    THEN no outcome is recorded, no pending result is stored, and the
    fault is reported naming the launch, step, handler and outcome.

    `Refused` on a `compliance-obligation` step: `launch-playbook` allows
    `Refused` only where the hazard is `prohibited-tactic`. The step
    needs confirmation, which is the shape the requirement's own
    reasoning names — checking at recording time instead would store it,
    deliver it, and fail on every press of accept.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Refused, result="declining this listing tactic")
    )
    collaborators = _setup(
        _automated(hazard=Hazard.COMPLIANCE_OBLIGATION, confirmer=ALICE),
        handler=handler,
    )

    with caplog.at_level(logging.WARNING):
        await _run_pass(collaborators)

    # SPECIFIED: no outcome is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: no pending result is stored.
    assert collaborators.results.rows == []
    # SPECIFIED: the fault is reported naming launch, step, handler and
    # outcome.
    reported = _warnings(caplog)
    assert reported, "an impermissible proposal was refused without a report"
    assert str(PRODUCT_ID) in reported
    assert AUTOMATED_STEP_ID in reported
    assert HANDLER_NAME in reported
    assert "refused" in reported.lower()


async def test_an_impermissible_proposal_is_refused_on_an_unconfirmed_step_too() -> (
    None
):
    """Requirement statement: "Before storing **or recording** anything".

    Stated in no scenario: the named scenario turns on storing, which
    only a confirmable step does. A step needing no confirmation takes
    the record-immediately branch, and an implementation that checks the
    hazard only on the store path records straight through it.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Refused, result="declining this listing tactic")
    )
    collaborators = _setup(
        _automated(hazard=Hazard.COMPLIANCE_OBLIGATION),
        handler=handler,
    )

    await _run_pass(collaborators)

    assert collaborators.recorder.calls == []
    assert collaborators.results.rows == []


# ---------------------------------------------------------------------------
# Requirement: An unregistered handler is reported and skipped, never fatal
# ---------------------------------------------------------------------------


async def test_a_step_naming_an_unregistered_handler_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A step naming an unregistered handler is skipped.

    WHEN a pass reaches an `active` `automated` step whose named handler
    is not registered in this deployment
    THEN no outcome is recorded for it, the step and the handler name are
    reported, and the pass continues.

    "The pass continues" is asserted through a second launch carrying a
    resolvable step: an implementation that raises never reaches it.
    """
    unresolvable = _automated(handler=UNREGISTERED_HANDLER)
    playbook = _playbook(unresolvable)
    first = _launch(playbook, PRODUCT_ID)
    second = _launch(playbook, OTHER_PRODUCT_ID)

    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _Collaborators(
        launches=_FakeLaunches(first, second),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    with caplog.at_level(logging.WARNING):
        await _run_pass(collaborators)

    # SPECIFIED: no outcome is recorded for it.
    assert collaborators.recorder.calls == []
    assert collaborators.results.rows == []
    # SPECIFIED: the step and the handler name are reported.
    reported = _warnings(caplog)
    assert reported, "an unresolvable handler was skipped without a report"
    assert AUTOMATED_STEP_ID in reported
    assert UNREGISTERED_HANDLER in reported
    # SPECIFIED: the pass continues — it reached the second launch too,
    # which it could only report on having walked it.
    assert (
        reported.count(UNREGISTERED_HANDLER) >= 2 or str(OTHER_PRODUCT_ID) in reported
    ), (
        "the pass stopped at the first unresolvable step rather than "
        "continuing to the next launch"
    )


# ---------------------------------------------------------------------------
# Requirement: A handler failure resolves nothing and does not stop the pass
# ---------------------------------------------------------------------------


async def test_a_failing_handler_leaves_the_step_untouched(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: A failing handler leaves the step untouched.

    WHEN a handler raises while resolving a step
    THEN the step's recorded outcome is unchanged, the failure is
    reported naming the launch, step and handler, and the pass continues
    to the next step.

    The negative half is the one this requirement exists for: "A failure
    SHALL NOT be recorded as any outcome, `Blocked` included", so the
    assertion is over the recorder's whole call list rather than over the
    absence of a terminal outcome.
    """
    failing = _RaisingHandler()
    second_handler = _ScriptedHandler(
        StepResolution(outcome=Satisfied, result="the second step's own result")
    )
    crashing_step = _automated()
    healthy_step = _automated(
        identifier="listing.other-automated", handler="listing.other_handler"
    )
    playbook = _playbook(crashing_step, healthy_step)
    launch = _launch(playbook)
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(
            **{HANDLER_NAME: failing, "listing.other_handler": second_handler}
        ),
    )

    with caplog.at_level(logging.WARNING):
        await _run_pass(collaborators)

    # SPECIFIED: the step's recorded outcome is unchanged — nothing at
    # all is recorded for it, `Blocked` included.
    assert collaborators.recorder.for_step(AUTOMATED_STEP_ID) == []
    assert launch.progress_for(AUTOMATED_STEP_ID) is None
    assert [
        row for row in collaborators.results.rows if row.step_id == AUTOMATED_STEP_ID
    ] == []
    # SPECIFIED: the failure is reported naming launch, step and handler.
    reported = _warnings(caplog)
    assert str(PRODUCT_ID) in reported
    assert AUTOMATED_STEP_ID in reported
    assert HANDLER_NAME in reported
    # SPECIFIED: the pass continues to the next step.
    assert second_handler.invoked


async def test_one_failure_does_not_abandon_the_remaining_launches() -> None:
    """Scenario: One failure does not abandon the remaining launches.

    WHEN a handler fails for one launch and other launches have
    unresolved automated steps
    THEN those other launches are still walked in the same pass.
    """
    playbook = _playbook(_automated())
    failing_launch = _launch(playbook, PRODUCT_ID)
    healthy_launch = _launch(playbook, OTHER_PRODUCT_ID)

    class _FailsForTheFirstLaunch:
        def __init__(self) -> None:
            self.seen: list[ProductId] = []

        async def __call__(self, context: Any) -> StepResolution:
            product_id = context.launch.product_id
            self.seen.append(product_id)
            if product_id == PRODUCT_ID:
                raise RuntimeError("simulated handler failure")
            return StepResolution(outcome=Satisfied, result=RECOMMENDATION)

    handler = _FailsForTheFirstLaunch()
    collaborators = _Collaborators(
        launches=_FakeLaunches(failing_launch, healthy_launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    await _run_pass(collaborators)

    # SPECIFIED: the other launch is still walked.
    assert OTHER_PRODUCT_ID in handler.seen
    recorded = [
        call
        for call in collaborators.recorder.calls
        if call.get("product_id") == OTHER_PRODUCT_ID
    ]
    assert recorded, "the second launch was walked but its resolution went nowhere"
    # SPECIFIED (from the sibling scenario): nothing was recorded for the
    # launch whose handler failed.
    assert [
        call
        for call in collaborators.recorder.calls
        if call.get("product_id") == PRODUCT_ID
    ] == []


async def test_a_completed_walk_is_a_successful_run() -> None:
    """Scenario: A completed walk is a successful run.

    WHEN a pass walks every launch to completion while one handler failed
    and one delivery failed
    THEN the run is recorded as successful.

    Read as *the pass body returns normally* — the only outcome signal a
    job body has, and the reading
    `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py`
    records for the same words. The runner's own recording of that
    outcome is integration-tier.
    """
    playbook = _playbook(_automated())
    failing_launch = _launch(playbook, PRODUCT_ID)
    healthy_launch = _launch(playbook, OTHER_PRODUCT_ID)

    class _FailsForTheFirstLaunch:
        async def __call__(self, context: Any) -> StepResolution:
            if context.launch.product_id == PRODUCT_ID:
                raise RuntimeError("simulated handler failure")
            return StepResolution(outcome=Satisfied, result=RECOMMENDATION)

    collaborators = _Collaborators(
        launches=_FakeLaunches(failing_launch, healthy_launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: _FailsForTheFirstLaunch()}),
        delivery=_FakeDelivery(failing=True),
    )
    collaborators.results.seed_pending(delivered=False)

    # SPECIFIED: the run is successful — no exception escapes the pass,
    # though both a handler and a delivery failed inside it.
    await _run_pass(collaborators)


# ---------------------------------------------------------------------------
# Requirement: A result needing no confirmation is recorded at once
# ---------------------------------------------------------------------------


async def test_an_unconfirmed_result_is_recorded_directly() -> None:
    """Scenario: An unconfirmed result is recorded directly.

    WHEN a handler resolves a step whose confirmation flag is false
    THEN the outcome is recorded against the launch with `automated`
    provenance, and no decision is requested.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(), handler=handler)

    await _run_pass(collaborators)

    calls = collaborators.recorder.for_step(AUTOMATED_STEP_ID)
    # SPECIFIED: recorded immediately, with `automated` provenance.
    assert len(calls) == 1
    assert calls[0]["outcome"] is Satisfied
    assert calls[0]["provenance"].source == "automated"
    # SPECIFIED: nothing is held and no decision is sought.
    assert collaborators.results.rows == []
    assert collaborators.delivery.delivered == []


# ---------------------------------------------------------------------------
# Requirement: A result needing confirmation is held until a member decides
# ---------------------------------------------------------------------------


async def test_a_confirmable_terminal_result_is_held_rather_than_recorded() -> None:
    """Scenario: A confirmable terminal result is held rather than
    recorded.

    WHEN a handler proposes a terminal outcome for a step whose
    confirmation flag is true
    THEN no outcome is recorded against the launch, and a pending result
    is stored carrying the proposed outcome, the produced text, the
    handler and the moment it was produced.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)

    await _run_pass(collaborators)

    # SPECIFIED: no outcome is recorded against the launch.
    assert collaborators.recorder.calls == []
    # SPECIFIED: a pending result is stored carrying all four facts.
    pending = collaborators.results.pending_rows
    assert len(pending) == 1, f"expected one pending result, got {pending}"
    row = pending[0]
    assert row.product_id == PRODUCT_ID
    assert row.step_id == AUTOMATED_STEP_ID
    assert row.proposed_outcome is Satisfied
    assert row.result_text == RECOMMENDATION
    assert row.handler == HANDLER_NAME
    assert row.produced_at == NOW


async def test_a_pending_result_suppresses_re_invocation() -> None:
    """Scenario: A pending result suppresses re-invocation.

    WHEN a pass runs while a pending result stands for a launch and step
    THEN that step's handler is not invoked and the pending result is
    left as it is.
    """
    handler = _ScriptedHandler(
        StepResolution(outcome=Satisfied, result="a second, competing proposal")
    )
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)
    standing = collaborators.results.seed_pending()

    await _run_pass(collaborators, now=NOW + timedelta(hours=2))

    # SPECIFIED: the handler is not invoked.
    assert not handler.invoked
    # SPECIFIED: the pending result is left as it is — one row, unchanged.
    assert collaborators.results.pending_rows == [standing]
    assert standing.result_text == RECOMMENDATION
    assert standing.state == "pending"
    assert collaborators.recorder.calls == []


# ---------------------------------------------------------------------------
# Requirement: A pending result is delivered for a decision, and delivery
# failure does not lose it
# ---------------------------------------------------------------------------


async def test_undelivered_is_not_undone(caplog: pytest.LogCaptureFixture) -> None:
    """Scenario: Undelivered is not undone.

    WHEN delivering a pending result to Slack fails
    THEN the pending result still stands, no outcome is recorded, and the
    delivery failure is reported.
    """
    collaborators = _setup(_automated(confirmer=ALICE))
    collaborators.delivery = _FakeDelivery(failing=True)
    standing = collaborators.results.seed_pending(delivered=False)

    with caplog.at_level(logging.WARNING):
        await _run_pass(collaborators)

    # SPECIFIED: the pending result still stands.
    assert collaborators.results.pending_rows == [standing]
    assert standing.state == "pending"
    # SPECIFIED: and is still undelivered, so a later pass can retry it.
    assert standing.delivered_at is None
    # SPECIFIED: no outcome is recorded.
    assert collaborators.recorder.calls == []
    # SPECIFIED: the failure is reported.
    reported = _warnings(caplog)
    assert reported, "a failed delivery was swallowed without a report"
    assert AUTOMATED_STEP_ID in reported


async def test_an_undelivered_result_is_delivered_again_later() -> None:
    """Scenario: An undelivered result is delivered again later.

    WHEN a delivery failed and a later pass runs
    THEN delivery of that pending result is attempted again.
    """
    collaborators = _setup(_automated(confirmer=ALICE))
    failing = _FakeDelivery(failing=True)
    collaborators.delivery = failing
    standing = collaborators.results.seed_pending(delivered=False)

    await _run_pass(collaborators)
    assert len(failing.delivered) == 1
    assert standing.delivered_at is None

    succeeding = _FakeDelivery()
    collaborators.delivery = succeeding
    await _run_pass(collaborators, now=NOW + timedelta(minutes=15))

    # SPECIFIED: delivery is attempted again.
    assert len(succeeding.delivered) == 1
    # And a successful post stamps delivery, so it is not offered a third
    # time (`design.md`, "Delivery is retried by the next pass").
    assert standing.delivered_at is not None


async def test_an_already_delivered_result_is_not_delivered_again() -> None:
    """`design.md`: "Each pass begins by delivering every pending result
    whose `delivered_at` is null ... A successful post stamps
    `delivered_at`."

    DERIVED, from design rather than from a scenario: the spec requires
    that an undelivered result be deliverable again, and says nothing
    about a delivered one. Recorded as derived because a re-delivering
    implementation would post the same proposal every fifteen minutes,
    which the requirement's own reasoning about bounding the cost of a
    decision argues against without stating.
    """
    collaborators = _setup(_automated(confirmer=ALICE))
    collaborators.results.seed_pending(delivered=True)

    await _run_pass(collaborators)

    assert collaborators.delivery.delivered == []


# ---------------------------------------------------------------------------
# Requirement: A rejected step is not re-proposed immediately
# ---------------------------------------------------------------------------


async def test_a_rejected_step_is_skipped_within_the_cool_off() -> None:
    """Scenario: A rejected step is skipped within the cool-off.

    WHEN a pass runs while a step's most recent settled result was
    rejected within the cool-off
    THEN that step's handler is not invoked.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)
    collaborators.results.seed_rejection(decided_at=NOW - timedelta(hours=1))

    await _run_pass(collaborators)

    # SPECIFIED: the handler is not invoked.
    assert not handler.invoked
    assert collaborators.recorder.calls == []
    assert collaborators.results.pending_rows == []


async def test_a_rejected_step_is_offered_again_once_the_cool_off_elapses() -> None:
    """Scenario: A rejected step is offered to the handler again once the
    cool-off elapses.

    WHEN a pass runs after the cool-off has elapsed since a step's
    rejection, and no pending result stands for it
    THEN that step's handler is invoked again.

    The window itself (24 hours) is DERIVED from `design.md`; what is
    SPECIFIED is that some fixed cool-off both suppresses and then
    expires. If the constant is revised, `COOL_OFF` is the figure to
    correct — the two-sided behaviour it guards is not.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)
    rejected_at = NOW - COOL_OFF - timedelta(minutes=1)
    collaborators.results.seed_rejection(decided_at=rejected_at)

    await _run_pass(collaborators)

    # SPECIFIED: the handler is invoked again.
    assert handler.invoked


async def test_a_voided_result_is_not_a_rejection_for_the_cool_off() -> None:
    """`design.md`: "`voided` is a fourth state, not a flavour of
    `rejected` ... Only `rejected` counts as a rejection for the
    cool-off", and `tasks.md` 4.3 repeats it.

    DERIVED, recorded as such: no scenario of the delta states it, and
    the two states are indistinguishable to a pass that keys on "settled
    and not accepted". A voided row parking the step for 24 hours after
    it returned to the served set is the failure this pins.
    """
    handler = _ScriptedHandler(StepResolution(outcome=Satisfied, result=RECOMMENDATION))
    collaborators = _setup(_automated(confirmer=ALICE), handler=handler)
    voided = collaborators.results.seed_rejection(decided_at=NOW - timedelta(hours=1))
    voided.state = "voided"
    voided.decided_by = None

    await _run_pass(collaborators)

    assert handler.invoked


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Which collaborators the *job wrapper* hands the pass. The pass's own
#   behaviour is asserted above at a level needing no runner; asserting
#   the wiring would pin a composition no scenario states. That both
#   composition roots register the same handler names is `tasks.md`
#   8.6a's guard and belongs with the existing registry-divergence test.
# - The pass's ordering between delivering undelivered results and
#   resolving handlers. `design.md` fixes it ("Each pass begins by
#   delivering..."), but no scenario turns on it, and the two are
#   observable independently above.
# ---------------------------------------------------------------------------
