"""The recurring pass: when it stands down, when it asks, and how often.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers, from the ADDED requirements, the scenarios stated over *the pass
as a whole* rather than over one launch's cascade:

- *The pass stands down while the playbook cannot hold a launch* — both
  scenarios. The stand-down is additionally driven over a step set that
  has not yet become ready, at the integration tier, in
  `tests/integration/launch/test_gate_progression_stand_down_live.py`
  (`tasks.md` 7.9).
- *A gate awaiting only confirmation is asked about in Slack* — all four
  scenarios. What the message *says* is the ask adapter's and is in
  `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py`.
- *A gate is asked about at most once a day* — *A gate asked about is not
  asked about again on the next pass*, *An unanswered gate is asked about
  again the next day*, *A rejected gate is not re-proposed the same day*
  and *A restart does not resume asking*. Its remaining scenario, *A
  rejection and its cool-off refresh land together or not at all*, is
  stated over a decision rather than over the pass and is in
  `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`
  and `tests/integration/launch/test_gate_progression_atomicity_live.py`.

The containment scenarios of *One launch's failure does not stop the other
launches being advanced* are in
`tests/unit/launch/infrastructure/driving/test_gate_progression_containment.py`;
the cascade's own scenarios are in
`tests/unit/launch/application/test_progress_launch.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The pass body over in-memory doubles. Every scenario here is stated over
what the pass does across launches — whether it advanced any, whether it
posted, how often it posted — and nothing below the pass can observe any
of them: the cascade does not know an ask exists, and the ask adapter does
not know a previous pass happened. It is the level
`test_automation_pass.py` and `test_clickup_sync_job_stand_down.py`
already hold for this module's other recurring walks.

## Reading the outcome clauses

"Recorded as having succeeded" is read as *the pass body returns
normally*, and "reported as a failed run" as *it raises*. The same reading
`test_clickup_sync_job_stand_down.py` and
`test_clickup_sync_job_containment.py` record for the same words, and for
the same reason: a job body's only outcome signal is whether it raises.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `launch/infrastructure/driving/gate_progression_job.py` as the pass's
  home (`tasks.md` 4.1).
- Readiness determined once, above the walk, and a stand-down recorded as
  a **succeeded** run with the unheld gates logged (`tasks.md` 4.2; delta
  R2).
- The walk over `LaunchRepository.list_active` (`tasks.md` 4.3).
- The ask posted only where no suppression record younger than 24 hours
  exists, the delivery recorded only after it succeeds (`tasks.md` 4.7).
- A failed ask delivery reported without failing the run, leaving the gate
  eligible for the next pass (`tasks.md` 4.8).
- The final-gate exclusion enforced in the ask itself rather than left to
  which launches the pass is handed (`tasks.md` 5.8; delta R4).

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The pass's entry-point name. `_entry()` probes and fails loudly.
- The names its collaborators are reachable under — as keyword parameters
  or as module attributes. `_Harness.install` places each under whichever
  spelling the module carries and **fails loudly when it can place none**,
  so no test here can run against an unsubstituted real collaborator.
  Correction points: the `_*_NAMES` tuples.
- The suppression store's read and write method names (`_FakeSuppression`)
  and the row's attributes. `tasks.md` 2.1 and 2.3 fix the operations, not
  their spellings.
- What the cascade hands back to say a gate is awaiting confirmation
  (`_Progressed`). Deliberately paired with a launch that is *genuinely*
  awaiting confirmation in the store, so a pass that re-reads the launch
  instead of trusting the return value observes the same thing.
- That the ask is delivered through a substitutable module-level
  collaborator rather than by the pass composing a message itself.

What must survive any correction is what each test asserts: which launches
were advanced, how many asks were posted and for which gates, what the
suppression store holds afterwards, and whether the pass raised.

## Expected first-run state

`gate_progression_job.py` does not exist (`tasks.md` 4.1), so every test
here is expected to fail on an absent target — `_module()`'s loud failure.
Per `ai-toolkit:testing` that establishes absence only: none of the
assertions below has been exercised.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed. `uv run pytest tests/integration` — 3 passed, 112
skipped (no `DATABASE_URL` is configured here).
"""

from __future__ import annotations

import importlib
import inspect
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from typing import Any, Final

import pytest

from commerce_ops.launch.domain import launch_playbook as playbook_module
from commerce_ops.launch.domain.launch_playbook import (
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
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_progression_job"

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

UNHELD_GATE: Final = "ignition"

FIRST: Final = ProductId(str(uuid.uuid4()))
SECOND: Final = ProductId(str(uuid.uuid4()))
THIRD: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FIRST, SECOND, THIRD)

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)

#: `design.md` — Decision 5, and `tasks.md` 4.9: 24 hours, a module
#: constant rather than configuration.
COOL_OFF: Final = timedelta(hours=24)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "description": None,
        "gate": gate,
        "discipline": next(iter(Discipline)),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=0),
        "blocking": True,
        "kind": StepKind.AUTOMATED,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": "fixture.holding_check",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _ready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="progression-v1",
        gates=_gates(),
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


def _unready_playbook() -> LaunchPlaybook:
    """A served set in which one gate holds no *active* blocking step —
    the condition R2 stands the pass down for."""
    return LaunchPlaybook(
        version="progression-v1",
        gates=_gates(),
        steps=tuple(
            _hold(
                gate,
                status=StepStatus.DRAFT if gate == UNHELD_GATE else StepStatus.ACTIVE,
            )
            for gate in SPECIFIED_GATE_ORDER
        ),
    )


def _provenance() -> Provenance:
    return Provenance(
        source="automated",
        who="hold-filler",
        when=NOW,
        evidence="the blocking check reported green",
    )


def _satisfy_everything(launch: Launch, playbook: LaunchPlaybook) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )
    if launch.current_gate in CONFIRMATION_GATES:
        launch.approve_gate(
            launch.current_gate,
            GateApproval(
                decision=ApprovalDecision.APPROVING,
                approver="Helen",
                when=NOW,
                posture=Posture.SCALE if launch.current_gate == FINAL_GATE else None,
            ),
        )


def _launch_at(
    product_id: ProductId, gate: str, *, satisfy_steps: bool = True
) -> Launch:
    """A launch standing at `gate`; by default with that gate's blocking
    steps satisfied, so a confirmation gate there is *awaiting only
    confirmation* in exactly the sense `launch-instance` defines."""
    playbook = _ready_playbook()
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != gate:
        _satisfy_everything(launch, playbook)
        launch.advance_gate(playbook)
    if satisfy_steps:
        for step in playbook.steps_for_gate(gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(),
                )
    return launch


def _build_not_ready(playbook: LaunchPlaybook) -> Exception:
    """`PlaybookNotReadyError`, under whichever signature it carries —
    transcribed from `test_clickup_sync_job_stand_down.py`."""
    error = getattr(playbook_module, "PlaybookNotReadyError", None)
    if error is None:
        pytest.fail(
            "commerce_ops.launch.domain.launch_playbook exports no "
            "`PlaybookNotReadyError`, so a stand-down cannot be provoked here"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((), {"playbook": playbook, "gates": (UNHELD_GATE,)}),
        ((), {"playbook": playbook, "unheld_gates": (UNHELD_GATE,)}),
        (((UNHELD_GATE,), playbook), {}),
        ((playbook, (UNHELD_GATE,)), {}),
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
# Test doubles
# ---------------------------------------------------------------------------


def _find(args: tuple[Any, ...], kwargs: dict[str, Any], predicate: Any) -> Any:
    for candidate in (*args, *kwargs.values()):
        if predicate(candidate):
            return candidate
    return None


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    """The launch a call is for, found rather than read off a parameter
    name, so a call this file cannot attribute never attributes wrongly."""
    found = _find(args, kwargs, lambda c: isinstance(c, ProductId))
    if isinstance(found, ProductId):
        return found
    launch = _find(args, kwargs, lambda c: isinstance(c, Launch))
    if isinstance(launch, Launch):
        return launch.product_id
    text = _find(
        args, kwargs, lambda c: isinstance(c, str) and c in {p.value for p in WALK}
    )
    if text is not None:
        return ProductId(text)
    pytest.fail(
        "a call carried neither a launch nor a product identifier among its "
        f"arguments (args={args!r}, kwargs={kwargs!r}); correct `_product_of`"
    )


class _FakeLaunches:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def list_active(self) -> tuple[Launch, ...]:
        """Every launch handed to the fixture, the final gate **included**.

        Deliberately not filtering: `design.md` — Decision 8 leans on the
        real `list_active` excluding the final gate, and `tasks.md` 5.8
        requires the exclusion hold anyway. A double that filtered would
        make the final-gate scenario unfalsifiable here.
        """
        return tuple(self._launches.values())

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook, refusal: Exception | None) -> None:
        self.playbook = playbook
        self.refusal = refusal
        self.reads = 0

    async def get(self, version: str = "") -> LaunchPlaybook:
        self.reads += 1
        if self.refusal is not None:
            raise self.refusal
        return self.playbook

    #: Some callers in this repository read a playbook through a bare
    #: call rather than through `get`.
    async def __call__(self, *args: Any, **kwargs: Any) -> LaunchPlaybook:
        return await self.get()


@dataclass
class _Progressed:
    """What the cascade hands back (INVENTED shape — see the docstring).

    Every plausible spelling of the same two facts, so a pass reading any
    one of them observes what the fixture set up.

    `crossed` defaults empty: this file exercises the ask mechanism, not
    `trigger-clickup-projection-on-launch-events`'s eager convergence
    (`test_gate_progression_pass_eager_convergence.py`'s job), so the fake
    never reports a crossing and the pass's own `if progressed.crossed:`
    branch is simply never taken here.
    """

    awaiting_confirmation: bool = False
    awaiting_gate: str | None = None
    events: tuple[Any, ...] = ()
    crossed: tuple[str, ...] = ()

    @property
    def awaiting(self) -> bool:
        return self.awaiting_confirmation

    @property
    def gate_id(self) -> str | None:
        return self.awaiting_gate

    @property
    def gate(self) -> str | None:
        return self.awaiting_gate

    @property
    def current_gate(self) -> str | None:
        return self.awaiting_gate


class _FakeProgress:
    """Stands in for `progress_launch`.

    Reports, for each product, whatever the test scripted — and by default
    what the launch in the store actually is, so a pass that re-reads the
    launch rather than trusting the return value sees the same thing.
    """

    def __init__(self, launches: _FakeLaunches) -> None:
        self._launches = launches
        self.seen: list[ProductId] = []
        self.failures: dict[ProductId, Any] = {}

    def fail_for(self, product_id: ProductId, build: Any) -> None:
        self.failures[product_id] = build

    async def __call__(self, *args: Any, **kwargs: Any) -> _Progressed:
        product_id = _product_of(args, kwargs)
        self.seen.append(product_id)
        build = self.failures.get(product_id)
        if build is not None:
            raise build()
        launch = await self._launches.get_by_product_id(product_id)
        if launch is None:
            return _Progressed()
        gate = launch.current_gate
        # `Launch.awaiting_confirmation` is `launch-instance`'s own read,
        # and the delta requires the ask be made "in exactly the sense
        # `launch-instance` defines" — so the fixture judges it the same
        # way rather than reimplementing the rule beside it.
        awaiting = launch.awaiting_confirmation(_ready_playbook())
        return _Progressed(
            awaiting_confirmation=awaiting, awaiting_gate=gate if awaiting else None
        )


@dataclass
class _SuppressionRow:
    product_id: ProductId
    gate_id: str
    delivered_at: datetime
    reason: str = "delivery"


class _FakeSuppression:
    """In-memory stand-in for the ask cool-off store (`tasks.md` 2.3).

    At most one row per `(product_id, gate_id)`, which is the primary key
    `tasks.md` 2.1 fixes. Answers several read and write spellings — the
    operations are fixed by the artifacts, the names are not — and records
    which it was reached through, so a test can assert the store was
    consulted at all.
    """

    def __init__(self, now: datetime = NOW) -> None:
        self.rows: dict[tuple[ProductId, str], _SuppressionRow] = {}
        self.reads: list[tuple[ProductId, str]] = []
        self.writes: list[_SuppressionRow] = []
        self.now = now

    # -- reads -----------------------------------------------------------

    async def read(self, *args: Any, **kwargs: Any) -> _SuppressionRow | None:
        key = self._key(args, kwargs)
        self.reads.append(key)
        return self.rows.get(key)

    get = read
    latest = read
    last_for = read
    record_for = read
    read_for = read

    async def is_suppressed(self, *args: Any, **kwargs: Any) -> bool:
        row = await self.read(*args, **kwargs)
        if row is None:
            return False
        moment = _find(args, kwargs, lambda c: isinstance(c, datetime)) or self.now
        return moment - row.delivered_at < COOL_OFF

    suppressed = is_suppressed

    # -- writes ----------------------------------------------------------

    async def record_delivery(self, *args: Any, **kwargs: Any) -> None:
        await self._write(args, kwargs, reason="delivery")

    record_delivered = record_delivery
    note_delivery = record_delivery
    record = record_delivery
    mark_delivered = record_delivery

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        await self._write(args, kwargs, reason="rejection")

    refresh = record_rejection
    note_rejection = record_rejection

    async def _write(
        self, args: tuple[Any, ...], kwargs: dict[str, Any], *, reason: str
    ) -> None:
        key = self._key(args, kwargs)
        when = _find(args, kwargs, lambda c: isinstance(c, datetime)) or self.now
        row = _SuppressionRow(
            product_id=key[0], gate_id=key[1], delivered_at=when, reason=reason
        )
        self.rows[key] = row
        self.writes.append(row)

    def _key(
        self, args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> tuple[ProductId, str]:
        product_id = _product_of(args, kwargs)
        gate = _find(
            args, kwargs, lambda c: isinstance(c, str) and c in SPECIFIED_GATE_ORDER
        )
        assert gate is not None, (
            "the suppression store was reached without naming a gate "
            f"(args={args!r}, kwargs={kwargs!r}); the record is per launch "
            "*and* gate (`tasks.md` 2.1)"
        )
        return (product_id, gate)

    def seed(
        self, product_id: ProductId, gate: str, *, age: timedelta, reason: str
    ) -> _SuppressionRow:
        row = _SuppressionRow(
            product_id=product_id,
            gate_id=gate,
            delivered_at=self.now - age,
            reason=reason,
        )
        self.rows[(product_id, gate)] = row
        return row


class _FakeAsk:
    """Stands in for posting the gate ask to Slack."""

    def __init__(self, *, failing: bool = False) -> None:
        self.failing = failing
        self.posted: list[tuple[ProductId, str]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        gate = _find(
            args, kwargs, lambda c: isinstance(c, str) and c in SPECIFIED_GATE_ORDER
        )
        self.posted.append((product_id, gate or "?"))
        if self.failing:
            raise RuntimeError("simulated Slack delivery failure")

    def gates_for(self, product_id: ProductId) -> list[str]:
        return [gate for product, gate in self.posted if product == product_id]


class _FakeSession:
    def __init__(self, rollback_error: BaseException | None = None) -> None:
        self.rollbacks = 0
        self.commits = 0
        self._rollback_error = rollback_error

    async def rollback(self) -> None:
        self.rollbacks += 1
        if self._rollback_error is not None:
            raise self._rollback_error

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return None


# ---------------------------------------------------------------------------
# Reaching the pass, through one correction point
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "run_gate_progression_pass",
    "run_gate_progression",
    "advance_launch_gates",
    "progress_gates",
    "run_pass",
)

_LAUNCHES_NAMES: Final = ("launches", "LaunchRepository", "launch_repository")
_PLAYBOOKS_NAMES: Final = (
    "playbooks",
    "PlaybookRepository",
    "playbook_repository",
    "read_playbook",
)
_PROGRESS_NAMES: Final = ("progress_launch", "progress", "advance_launch")
_SUPPRESSION_NAMES: Final = (
    "suppression",
    "GateAskSuppressionRepository",
    "gate_ask_suppression",
    "ask_suppression",
    "asks",
)
_ASK_NAMES: Final = (
    "post_gate_ask",
    "deliver_gate_ask",
    "ask_for_confirmation",
    "request_confirmation",
    "post_ask",
    "deliver",
)
_SESSION_NAMES: Final = ("transaction", "session")


def _module() -> ModuleType:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` 4.1 creates "
            "it. This is the absent-target state, not a defect in this file."
        )


@dataclass
class _Harness:
    module: ModuleType
    monkeypatch: pytest.MonkeyPatch
    launches: _FakeLaunches
    playbooks: _FakePlaybooks
    progress: _FakeProgress
    suppression: _FakeSuppression
    ask: _FakeAsk
    session: _FakeSession
    placed: dict[str, list[str]] = field(default_factory=dict)

    def install(self) -> None:
        self._place("launches", _LAUNCHES_NAMES, self.launches)
        self._place("playbooks", _PLAYBOOKS_NAMES, self.playbooks)
        self._place("progress", _PROGRESS_NAMES, self.progress)
        self._place("suppression", _SUPPRESSION_NAMES, self.suppression)
        self._place("ask", _ASK_NAMES, self.ask)
        self._place_session()

    def _place(self, role: str, names: tuple[str, ...], value: Any) -> None:
        placed: list[str] = []
        for name in names:
            if not hasattr(self.module, name):
                continue
            existing = getattr(self.module, name)
            target: Any = value
            if isinstance(existing, type):

                def target(*args: Any, _value: Any = value, **kwargs: Any) -> Any:
                    return _value

            self.monkeypatch.setattr(self.module, name, target)
            placed.append(name)
        self.placed[role] = placed

    def _place_session(self) -> None:
        placed: list[str] = []
        for name in _SESSION_NAMES:
            if not hasattr(self.module, name):
                continue

            @asynccontextmanager
            async def _provider(
                *args: Any, _session: _FakeSession = self.session, **kwargs: Any
            ) -> AsyncIterator[_FakeSession]:
                yield _session

            self.monkeypatch.setattr(self.module, name, _provider)
            placed.append(name)
        self.placed["session"] = placed

    def require(self, *roles: str) -> None:
        """Fail loudly where a collaborator this test depends on could be
        placed neither as a module attribute nor as a parameter."""
        entry = _entry(self.module)
        parameters = set(inspect.signature(entry).parameters)
        role_names = {
            "launches": _LAUNCHES_NAMES,
            "playbooks": _PLAYBOOKS_NAMES,
            "progress": _PROGRESS_NAMES,
            "suppression": _SUPPRESSION_NAMES,
            "ask": _ASK_NAMES,
            "session": _SESSION_NAMES,
        }
        for role in roles:
            names = role_names[role]
            if self.placed.get(role) or (parameters & set(names)):
                continue
            pytest.fail(
                f"the pass exposes no {role} collaborator under any of "
                f"{names}, as a module attribute or as a parameter — correct "
                "this file's probe, rather than letting the pass reach a real "
                f"one. Its parameters are {sorted(parameters)}"
            )

    async def run(self, *, now: datetime = NOW) -> Any:
        entry = _entry(self.module)
        pool: dict[str, Any] = {
            "launches": self.launches,
            "playbooks": self.playbooks,
            "progress_launch": self.progress,
            "progress": self.progress,
            "suppression": self.suppression,
            "ask_suppression": self.suppression,
            "post_gate_ask": self.ask,
            "deliver": self.ask,
            "now": now,
        }
        accepted = set(inspect.signature(entry).parameters)
        return await entry(**{k: v for k, v in pool.items() if k in accepted})


def _drop_registration(module: ModuleType) -> None:
    """Let the pass's module be reloaded.

    `register_scheduled` runs at import and the runner rejects a duplicate
    name; making it idempotent would be a change to shared infrastructure
    every job depends on, which is not this change's to make.
    """
    name = getattr(module, "TASK_NAME", None)
    if name is None:
        return
    # Imported dynamically rather than named: the runner app is deliberately
    # not in that module's `__all__`, and widening a shared module's public
    # surface for a test's sake is not this change's to do.
    runner: Any = importlib.import_module(
        "commerce_ops.shared.infrastructure.driven.recurring_work"
    )
    app: Any = runner.app
    app.tasks.pop(name, None)
    # The periodic registration is separate from the task registration and
    # rejects a duplicate `(task, periodic_id)` of its own, so both have to
    # go before the module can be imported a second time.
    periodic = getattr(app, "periodic_registry", None)
    registry = getattr(periodic, "periodic_tasks", None)
    if isinstance(registry, dict):
        for key in [k for k in registry if getattr(k, "__len__", None) and name in k]:
            registry.pop(key, None)


def _entry(module: ModuleType) -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {module.__name__} under any of "
        f"{_ENTRY_NAMES} — correct this file's probe to the implemented name"
    )


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *launches: Launch,
    refusal: Exception | None = None,
    failing_ask: bool = False,
    suppression: _FakeSuppression | None = None,
    session: _FakeSession | None = None,
) -> _Harness:
    module = _module()
    store = _FakeLaunches(*launches)
    harness = _Harness(
        module=module,
        monkeypatch=monkeypatch,
        launches=store,
        playbooks=_FakePlaybooks(_ready_playbook(), refusal),
        progress=_FakeProgress(store),
        suppression=suppression or _FakeSuppression(),
        ask=_FakeAsk(failing=failing_ask),
        session=session or _FakeSession(),
    )
    harness.install()
    return harness


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(record.getMessage() for record in caplog.records)


# ---------------------------------------------------------------------------
# Requirement: The pass stands down while the playbook cannot hold a launch
# ---------------------------------------------------------------------------


async def test_an_unready_playbook_stands_the_pass_down_without_failing_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: An unready playbook stands the pass down without failing it.

    WHEN the pass runs while a gate holds no active blocking step
    THEN no launch is advanced and no ask is posted
    AND the run is recorded as succeeded, with the stand-down and the
    unheld gates logged.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, "listable"),
        _launch_at(SECOND, "commit"),
        refusal=_build_not_ready(_unready_playbook()),
    )
    harness.require("launches", "playbooks", "progress", "ask")

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED: the run is recorded as succeeded — returning normally
        # is the assertion, so there is no `pytest.raises` here.
        await harness.run()

    # SPECIFIED: no launch is advanced.
    assert harness.progress.seen == [], (
        f"a launch was advanced during a stand-down: {harness.progress.seen}"
    )
    # SPECIFIED: no ask is posted.
    assert harness.ask.posted == [], (
        f"an ask was posted during a stand-down: {harness.ask.posted}"
    )
    # SPECIFIED: the stand-down and the unheld gates are logged.
    logged = _logged(caplog)
    assert UNHELD_GATE in logged, (
        "the stand-down did not log the gate holding no active blocking "
        f"step; what was logged was: {logged!r}"
    )
    # SPECIFIED (R2): readiness is determined once, before the walk begins,
    # rather than per launch — two launches, one playbook read.
    assert harness.playbooks.reads == 1, (
        "the served playbook was read more than once, so readiness was "
        f"judged per launch rather than once above the walk ({harness.playbooks.reads} reads)"
    )


async def test_a_ready_playbook_is_served_normally(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A ready playbook is served normally.

    WHEN the pass runs while every gate holds at least one active blocking
    step
    THEN launches are advanced as the requirements above describe.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, "listable"),
        _launch_at(SECOND, "listable"),
        _launch_at(THIRD, "listable"),
    )
    harness.require("launches", "playbooks", "progress")

    await harness.run()

    # SPECIFIED: launches are advanced — every one of them, since the walk
    # is over `list_active` and the requirement is a convergence pass.
    assert sorted(harness.progress.seen, key=WALK.index) == list(WALK), (
        f"the pass did not attempt every active launch: {harness.progress.seen}"
    )


# ---------------------------------------------------------------------------
# Requirement: A gate awaiting only confirmation is asked about in Slack
# ---------------------------------------------------------------------------


async def test_a_satisfied_confirmation_gate_is_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A satisfied confirmation gate is asked about.

    WHEN the pass runs against a launch whose current gate requires
    confirmation, has every blocking condition satisfied, and has no
    approving approval recorded
    THEN a message naming the product and the gate is posted, carrying the
    decision controls.

    What the message *says* is the ask adapter's and is asserted in
    `test_gate_ask_message.py`; what is asserted here is that the pass
    posts one at all, for that launch and that gate.
    """
    harness = _harness(monkeypatch, _launch_at(FIRST, "commit"))
    harness.require("ask", "suppression")

    await harness.run()

    # SPECIFIED: an ask is posted, for that product and that gate.
    assert harness.ask.posted == [(FIRST, "commit")], (
        f"the pass posted {harness.ask.posted!r} rather than one ask for the "
        "launch standing at a satisfied confirmation gate"
    )
    # SPECIFIED (R5): the delivery is recorded — but only after it
    # succeeded, which is what makes the next pass silent.
    assert harness.suppression.writes, (
        "the delivered ask left no cool-off record, so the gate will be "
        "asked about again on the next pass"
    )


async def test_the_final_gate_is_not_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The final gate is not asked about.

    WHEN the pass runs against a launch standing at the final gate of the
    sequence with every blocking condition satisfied and no approval
    recorded
    THEN no ask is posted, although that gate requires confirmation.

    The launch is handed to the pass deliberately, rather than filtered out
    of its set: the delta states the exclusion "so that it is a property of
    the capability and not of a collaborator's filtering", and `tasks.md`
    5.8 requires it enforced in the ask itself. A second launch, at
    `commit`, is asked about on the same run, so "no ask" is not the pass
    having posted nothing at all.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, FINAL_GATE),
        _launch_at(SECOND, "commit"),
    )
    harness.require("ask")

    await harness.run()

    # SPECIFIED: no ask is posted for the final gate.
    assert harness.ask.gates_for(FIRST) == [], (
        "an ask was posted for a launch standing at the final gate: "
        f"{harness.ask.posted!r}"
    )
    # Guard: the run did post, so the assertion above is not vacuous.
    assert harness.ask.gates_for(SECOND) == ["commit"], (
        f"the control launch was not asked about either: {harness.ask.posted!r}"
    )


async def test_a_gate_with_unsatisfied_conditions_is_not_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate with unsatisfied conditions is not asked about.

    WHEN the pass runs against a launch whose current gate requires
    confirmation but has an unsatisfied blocking condition
    THEN no ask is posted for that gate.

    Again paired with a control launch that *is* asked about, so the
    absence is attributable to the unsatisfied condition.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, "commit", satisfy_steps=False),
        _launch_at(SECOND, "commit"),
    )
    harness.require("ask")

    await harness.run()

    # SPECIFIED: no ask for the gate whose condition is unsatisfied.
    assert harness.ask.gates_for(FIRST) == [], (
        "an ask was posted for a gate with an unsatisfied blocking "
        f"condition: {harness.ask.posted!r}"
    )
    # Guard.
    assert harness.ask.gates_for(SECOND) == ["commit"]


async def test_an_undelivered_ask_is_reported_retried_and_does_not_fail_the_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: An undelivered ask is reported, retried, and does not fail
    the run.

    WHEN posting the ask fails
    THEN the failure is reported, no delivery is recorded, the run is not
    failed by it, and the ask is attempted again on the next pass while the
    gate is still awaiting confirmation.

    Driven over two runs, because "attempted again on the next pass" is a
    statement about the second run and no property of the first can stand
    in for it.
    """
    suppression = _FakeSuppression()
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, "commit"),
        failing_ask=True,
        suppression=suppression,
    )
    harness.require("ask", "suppression")

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED: the run is not failed by it.
        await harness.run()

    # SPECIFIED: the failure is reported.
    assert FIRST.value in _warnings(caplog) or FIRST.value in _logged(caplog), (
        "the failed ask delivery was not reported against its product; what "
        f"was logged was: {_logged(caplog)!r}"
    )
    # SPECIFIED: no delivery is recorded.
    assert suppression.writes == [], (
        "a cool-off record was written for an ask that was never delivered, "
        "which silences the gate for a day with nobody having been asked"
    )
    assert harness.ask.posted == [(FIRST, "commit")]

    # SPECIFIED: the ask is attempted again on the next pass.
    harness.ask.failing = False
    await harness.run()

    assert harness.ask.gates_for(FIRST) == ["commit", "commit"], (
        "the gate was not asked about again on the next pass, so a failed "
        f"delivery lost the ask: {harness.ask.posted!r}"
    )
    assert suppression.writes, "the ask that did succeed left no cool-off record"


# ---------------------------------------------------------------------------
# Requirement: A gate is asked about at most once a day
# ---------------------------------------------------------------------------


async def test_a_gate_asked_about_is_not_asked_about_again_on_the_next_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate asked about is not asked about again on the next
    pass.

    WHEN an ask for a gate was delivered and the pass runs again within
    twenty-four hours while the gate is still awaiting confirmation
    THEN no second ask is posted.
    """
    suppression = _FakeSuppression()
    harness = _harness(
        monkeypatch, _launch_at(FIRST, "commit"), suppression=suppression
    )
    harness.require("ask", "suppression")

    await harness.run()
    # Guard: the first pass really did ask, so silence on the second is the
    # cool-off and not a pass that never asks.
    assert harness.ask.gates_for(FIRST) == ["commit"]

    await harness.run(now=NOW + timedelta(hours=23))

    # SPECIFIED: no second ask.
    assert harness.ask.gates_for(FIRST) == ["commit"], (
        "the gate was asked about twice within twenty-four hours: "
        f"{harness.ask.posted!r}"
    )


async def test_an_unanswered_gate_is_asked_about_again_the_next_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unanswered gate is asked about again the next day.

    WHEN an ask for a gate was delivered more than twenty-four hours ago
    and the gate is still awaiting confirmation
    THEN the ask is posted again.
    """
    suppression = _FakeSuppression()
    suppression.seed(
        FIRST, "commit", age=COOL_OFF + timedelta(minutes=1), reason="delivery"
    )
    harness = _harness(
        monkeypatch, _launch_at(FIRST, "commit"), suppression=suppression
    )
    harness.require("ask", "suppression")

    await harness.run()

    # SPECIFIED: the ask is posted again.
    assert harness.ask.gates_for(FIRST) == ["commit"], (
        "a gate whose ask went unanswered for more than a day was not asked "
        f"about again: {harness.ask.posted!r}"
    )


async def test_a_rejected_gate_is_not_re_proposed_the_same_day(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejected gate is not re-proposed the same day.

    WHEN a rejecting decision is recorded for a gate and the pass runs
    again within twenty-four hours
    THEN no ask is posted for that gate.

    The rejection's own record is seeded, since recording it is the
    decision path's work and is covered in
    `test_gate_decision_wiring.py`; what is asserted here is that the pass
    honours it exactly as it honours a delivery — one rule, three cases
    (delta R5).
    """
    suppression = _FakeSuppression()
    suppression.seed(FIRST, "commit", age=timedelta(hours=2), reason="rejection")
    harness = _harness(
        monkeypatch,
        _launch_at(FIRST, "commit"),
        _launch_at(SECOND, "commit"),
        suppression=suppression,
    )
    harness.require("ask", "suppression")

    await harness.run()

    # SPECIFIED: no ask for the rejected gate.
    assert harness.ask.gates_for(FIRST) == [], (
        f"a gate rejected two hours ago was proposed again: {harness.ask.posted!r}"
    )
    # Guard: a launch with no record is asked about on the same run.
    assert harness.ask.gates_for(SECOND) == ["commit"]


async def test_a_restart_does_not_resume_asking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A restart does not resume asking.

    WHEN the process running the pass restarts and runs a pass while a
    delivered ask is less than twenty-four hours old
    THEN no second ask is posted.

    The restart is modelled by reloading the pass's module between runs,
    which discards any module-level state the process was holding while
    leaving the store exactly where it was. That is the distinction the
    requirement draws — "held in storage rather than in the memory of the
    process running the pass" — and a pass memoising its asks in a module
    global would pass the cool-off test above and fail this one.
    """
    suppression = _FakeSuppression()
    harness = _harness(
        monkeypatch, _launch_at(FIRST, "commit"), suppression=suppression
    )
    harness.require("ask", "suppression")

    await harness.run()
    assert harness.ask.gates_for(FIRST) == ["commit"]

    monkeypatch.undo()
    # CORRECTED mechanism: the pass registers its scheduled task at module
    # scope, and the runner refuses a second registration of the same name,
    # so a bare reload raises `TaskAlreadyRegistered` before any of this
    # test's substance is reached. Dropping the registration first lets the
    # reload do what the scenario actually needs — discard the module's own
    # state — without asserting anything about the scheduler.
    _drop_registration(_module())
    importlib.reload(_module())
    restarted = _harness(
        monkeypatch, _launch_at(FIRST, "commit"), suppression=suppression
    )

    await restarted.run(now=NOW + timedelta(hours=1))

    # SPECIFIED: no second ask.
    assert restarted.ask.posted == [], (
        "a restarted process asked again about a gate whose ask is an hour "
        f"old, so the record is process state rather than storage: {restarted.ask.posted!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The schedule and tolerance the pass declares (`tasks.md` 4.1, 6.3).
#   `scheduled-jobs` owns that requirement and no scenario of this delta
#   states it; `test_automation_pass_schedule.py` is the shape it would
#   take when someone writes it.
# - Which channel the ask lands in. `design.md` — Open Questions leaves it
#   as configuration and states explicitly that it changes no requirement
#   here; the ask adapter's own file asserts the channel it was given.
# - The order the walk visits launches in. No requirement states one; the
#   fixtures fix an order only so that "which launches were attempted" is
#   sayable.
# - That the first pass against a real deployment asks about every ready
#   launch at once (`design.md` — Risks; `tasks.md` 7.5). It is accepted
#   behaviour with no cap stated, so there is no rule to assert.
# ---------------------------------------------------------------------------
