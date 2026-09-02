"""The periodic gate-progression pass triggers an eager convergence too.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A launch is converged eagerly at start
and at a gate crossing*, the scenarios stated over this call site:

- *A gate crossing's newly released steps get tasks immediately, however
  the gate opened* — the pass half: "regardless of which path crossed it
  — a recorded decision, **the periodic gate-progression pass**, or the
  ClickUp webhook's own advance-and-ask trigger". A gate the pass itself
  crosses during its own walk triggers the eager helper for that launch,
  inline, the same run.
- *A failed eager run does not fail the action that triggered it* — this
  call site's own half: one launch's failed eager convergence does not
  fail the pass's own run, and does not stop the walk reaching the
  launches after it — the same containment shape
  `test_gate_progression_containment.py` already establishes for
  `progress_launch` itself.
- *The eager run stands down exactly as the pass does* — inherited: the
  pass already stands down above its walk on `PlaybookNotReadyError`
  (`test_gate_progression_pass.py`), before this change adds anything
  after a crossing, so the eager helper is never reached during a
  stand-down.

`tasks.md` 2.1's own worker-wiring obligation (`gate_progression_job.py`
gaining its own `read_product`/`read_members` module globals) is a
composition-root detail with no scenario of its own; this file asserts the
one thing it exists to serve — that the eager helper, once reached, is
reachable from this module at all — and does not otherwise test wiring
`main.py`/`worker.py` do not own.

See `test-manifest.md` at the change root for the full accounting.

## Level

The pass body over in-memory doubles — the level
`test_gate_progression_pass.py` and `test_gate_progression_containment.py`
already hold for this module's walk. Nothing below the pass can observe
"a gate crossing during the walk triggered the eager helper" or "a launch
left unchanged did not".

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the pass calls the eager helper,
inline and awaited, immediately after a launch's gate actually crosses
during its own per-launch loop (`tasks.md` 2.2), and that a launch left
unchanged by an unsatisfied condition does not trigger one (`tasks.md`
2.3).

INVENTED: the eager helper's name (`_HELPER_NAMES`, kept in step with
`test_eager_convergence_helper.py`); every domain fixture, collaborator
name and the entry-point probe are transcribed from
`test_gate_progression_pass.py` and `test_gate_progression_containment.py`,
which record the provenance of each.

## Expected first-run state

The pass calls no eager helper yet (`tasks.md` 2.2), so every test here is
expected to fail on an **absent target**. Per `ai-toolkit:testing` that
establishes absence only.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest

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
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_progression_job"

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
FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

CROSSING: Final = ProductId(str(uuid.uuid4()))
UNCHANGED: Final = ProductId(str(uuid.uuid4()))

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

#: Kept in step with `test_eager_convergence_helper.py`'s own
#: `_HELPER_NAMES`, which is the correction point for the name itself.
_HELPER_NAMES: Final = (
    "converge_launch_eagerly",
    "eager_converge_launch",
    "converge_launch_now",
    "converge_one_launch_eagerly",
    "eagerly_converge_launch",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_gate_progression_pass.py`
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


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


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _ready_playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="progression-v1",
        gates=_gates(),
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
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


# ---------------------------------------------------------------------------
# Test doubles — transcribed from `test_gate_progression_pass.py`
# ---------------------------------------------------------------------------


def _find(args: tuple[Any, ...], kwargs: dict[str, Any], predicate: Any) -> Any:
    for candidate in (*args, *kwargs.values()):
        if predicate(candidate):
            return candidate
    return None


def _product_of(args: tuple[Any, ...], kwargs: dict[str, Any]) -> ProductId:
    found = _find(args, kwargs, lambda c: isinstance(c, ProductId))
    if isinstance(found, ProductId):
        return found
    launch = _find(args, kwargs, lambda c: isinstance(c, Launch))
    if isinstance(launch, Launch):
        return launch.product_id
    text = _find(
        args,
        kwargs,
        lambda c: isinstance(c, str) and c in {CROSSING.value, UNCHANGED.value},
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
        return tuple(self._launches.values())

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    async def get(self, version: str = "") -> LaunchPlaybook:
        return self.playbook

    async def __call__(self, *args: Any, **kwargs: Any) -> LaunchPlaybook:
        return self.playbook


@dataclass
class _Progressed:
    awaiting_confirmation: bool = False
    awaiting_gate: str | None = None
    events: tuple[Any, ...] = ()
    #: The real `LaunchProgressed.crossed` field (`use_cases.py`) — what
    #: `gate_progression_job.py`'s own `_crossed` helper reads to decide
    #: whether to trigger eager convergence. `events` alone does not stand
    #: in for it: `_crossed` reads `crossed` specifically, tolerating its
    #: *absence* (a fake that predates this field) via `getattr(...,
    #: None)`, not a differently-named field standing in for it.
    crossed: tuple[str, ...] = ()

    @property
    def awaiting(self) -> bool:
        return self.awaiting_confirmation

    @property
    def gate_id(self) -> str | None:
        return self.awaiting_gate


class _FakeProgress:
    """Stands in for `progress_launch`.

    Crosses the launch's gate when told to (`crossing={product_id, ...}`),
    and leaves it exactly where it stands otherwise — which is the "left
    unchanged" half this file's own negative test needs.
    """

    def __init__(self, launches: _FakeLaunches, crossing: set[ProductId]) -> None:
        self._launches = launches
        self._crossing = crossing
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
        if product_id in self._crossing:
            gate_before = launch.current_gate
            launch.advance_gate(_ready_playbook())
            await self._launches.save(launch)
            return _Progressed(events=("crossed",), crossed=(gate_before,))
        return _Progressed()


class _FakeSuppression:
    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    get = read
    latest = read
    last_for = read
    record_for = read
    read_for = read

    async def is_suppressed(self, *args: Any, **kwargs: Any) -> bool:
        return False

    suppressed = is_suppressed

    async def record_delivery(self, *args: Any, **kwargs: Any) -> None:
        return None

    record_delivered = record_delivery
    note_delivery = record_delivery
    record = record_delivery
    mark_delivered = record_delivery

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        return None

    refresh = record_rejection


class _FakeAsk:
    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        return None


class _FakeSession:
    async def rollback(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return None


class _RecordingHelper:
    def __init__(self, *, failing_for: set[ProductId] | None = None) -> None:
        self.calls: list[Any] = []
        self._failing_for = failing_for or set()

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        product_id = _product_of(args, kwargs)
        self.calls.append(product_id)
        if product_id in self._failing_for:
            raise RuntimeError("simulated eager-convergence failure")

    @property
    def seen(self) -> list[ProductId]:
        return self.calls


# ---------------------------------------------------------------------------
# Reaching the pass — transcribed from `test_gate_progression_pass.py`
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
            f"{MODULE_PATH} does not exist ({error}); this test's target is absent."
        )


def _entry(module: ModuleType) -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {module.__name__} under any of "
        f"{_ENTRY_NAMES} — correct this file's probe to the implemented name"
    )


def _helper_name(module: ModuleType) -> str:
    for name in _HELPER_NAMES:
        if callable(getattr(module, name, None)):
            return name
    pytest.fail(
        f"{module.__name__} exposes no eager-convergence helper under any of "
        f"{_HELPER_NAMES}; `tasks.md` 2.2 adds a call to one. This is the "
        "absent-target state, not a defect in this file — do not add the "
        "attribute to make this pass."
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
    helper: _RecordingHelper
    placed: dict[str, list[str]] = field(default_factory=dict)

    def install(self) -> None:
        self._place("launches", _LAUNCHES_NAMES, self.launches)
        self._place("playbooks", _PLAYBOOKS_NAMES, self.playbooks)
        self._place("progress", _PROGRESS_NAMES, self.progress)
        self._place("suppression", _SUPPRESSION_NAMES, self.suppression)
        self._place("ask", _ASK_NAMES, self.ask)
        self._place_session()
        self.monkeypatch.setattr(self.module, _helper_name(self.module), self.helper)

    def _place(self, role: str, names: tuple[str, ...], value: Any) -> None:
        placed: list[str] = []
        for name in names:
            if not hasattr(self.module, name):
                continue
            target: Any = value
            if isinstance(getattr(self.module, name), type):

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


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *launches: Launch,
    crossing: set[ProductId] | None = None,
    failing_helper_for: set[ProductId] | None = None,
) -> _Harness:
    module = _module()
    store = _FakeLaunches(*launches)
    harness = _Harness(
        module=module,
        monkeypatch=monkeypatch,
        launches=store,
        playbooks=_FakePlaybooks(_ready_playbook()),
        progress=_FakeProgress(store, crossing or set()),
        suppression=_FakeSuppression(),
        ask=_FakeAsk(),
        session=_FakeSession(),
        helper=_RecordingHelper(failing_for=failing_helper_for),
    )
    harness.install()
    return harness


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# Scenario: A gate crossing's newly released steps get tasks immediately,
# however the gate opened — the periodic-pass half
# ---------------------------------------------------------------------------


async def test_a_gate_the_pass_itself_crosses_triggers_the_eager_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate crossing's newly released steps get tasks
    immediately, however the gate opened.

    WHEN a launch's gate crosses through the periodic gate-progression
    pass's own advance
    THEN the eager helper is triggered for that launch, on the same run.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(CROSSING, "listable"),
        crossing={CROSSING},
    )

    await harness.run()

    # SPECIFIED-BY-TASKS: the eager helper is triggered for the launch
    # whose gate crossed.
    assert harness.helper.seen == [CROSSING], (
        "the pass's own gate crossing did not trigger the eager-convergence "
        f"helper for that launch: {harness.helper.seen!r}"
    )


async def test_a_launch_left_unchanged_does_not_trigger_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario (`tasks.md` 2.3): "a launch left unchanged (unsatisfied
    condition) does not trigger one".

    Paired with a launch that *does* cross, on the same run, so the
    absence is attributable to the condition rather than to a pass that
    never triggers the helper at all.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(CROSSING, "listable"),
        _launch_at(UNCHANGED, "commit", satisfy_steps=False),
        crossing={CROSSING},
    )

    await harness.run()

    assert UNCHANGED not in harness.helper.seen, (
        "the pass triggered the eager-convergence helper for a launch its "
        f"own advance left unchanged: {harness.helper.seen!r}"
    )
    # Guard: the control launch was in fact triggered on the same run.
    assert CROSSING in harness.helper.seen, (
        f"the control launch was not triggered either: {harness.helper.seen!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A failed eager run does not fail the action that triggered it
# ---------------------------------------------------------------------------


async def test_a_failing_eager_run_does_not_fail_the_passs_own_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: A failed eager run does not fail the action that
    triggered it.

    WHEN the eager run raises while converging a launch whose gate the
    pass itself just crossed
    THEN the pass's own run completes and is reported exactly as it would
    have been had the eager run succeeded — and the walk still reaches the
    launches after it, the same containment shape
    `test_gate_progression_containment.py` establishes for
    `progress_launch` itself.
    """
    second = ProductId(str(uuid.uuid4()))
    harness = _harness(
        monkeypatch,
        _launch_at(CROSSING, "listable"),
        _launch_at(second, "listable"),
        crossing={CROSSING, second},
        failing_helper_for={CROSSING},
    )

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED-BY-TASKS: the run is not failed by it.
        await harness.run()

    assert CROSSING in harness.helper.seen, (
        "the failing eager helper was never reached, so this test exercised nothing"
    )
    # SPECIFIED: the walk still reaches the launch after the one whose
    # eager convergence failed.
    assert second in harness.helper.seen, (
        "a launch after the one whose eager convergence failed was never "
        f"reached: {harness.helper.seen!r}"
    )
    assert second in harness.progress.seen


# ---------------------------------------------------------------------------
# Scenario: The eager run stands down exactly as the pass does — inherited
# ---------------------------------------------------------------------------


async def test_a_stood_down_pass_never_reaches_the_eager_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The eager run stands down exactly as the pass does.

    WHEN the pass runs while the served playbook cannot hold a launch
    THEN the eager helper is never reached for any launch — inherited from
    the pass's own existing stand-down
    (`test_gate_progression_pass.py`'s own scenario), not re-implemented.
    """
    from commerce_ops.launch.domain import launch_playbook as playbook_module

    class _RefusingPlaybooks:
        async def get(self, version: str = "") -> LaunchPlaybook:
            error = getattr(playbook_module, "PlaybookNotReadyError", None)
            if error is None:
                pytest.fail(
                    "commerce_ops.launch.domain.launch_playbook exports no "
                    "`PlaybookNotReadyError`"
                )
            playbook = _ready_playbook()
            for args, kwargs in (
                ((), {"playbook": playbook, "gates": ("ignition",)}),
                ((), {"playbook": playbook, "unheld_gates": ("ignition",)}),
            ):
                try:
                    raise error(*args, **kwargs)
                except TypeError:
                    continue
            raise RuntimeError("could not construct PlaybookNotReadyError")

        def __call__(self, *args: Any, **kwargs: Any) -> _RefusingPlaybooks:
            # Synchronous, matching `PlaybookRepository(db_session)`'s own
            # real shape: construction itself is never awaited, only the
            # `.get(...)` call the caller makes on its result. An async
            # `__call__` here would make `PlaybookRepository(db_session)`
            # return an unawaited coroutine instead of this fake.
            return self

    harness = _harness(
        monkeypatch, _launch_at(CROSSING, "listable"), crossing={CROSSING}
    )
    monkeypatch.setattr(
        harness.module, "playbooks", _RefusingPlaybooks(), raising=False
    )
    for name in _PLAYBOOKS_NAMES:
        if hasattr(harness.module, name):
            monkeypatch.setattr(harness.module, name, _RefusingPlaybooks())

    await harness.run()

    assert harness.helper.seen == [], (
        "the eager-convergence helper was reached although the served "
        f"playbook could not hold a launch: {harness.helper.seen!r}"
    )
    assert harness.progress.seen == [], (
        "the pass advanced a launch during a stand-down, so this test does "
        f"not exercise the stand-down at all: {harness.progress.seen!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - `tasks.md` 2.1's own worker-process wiring (`gate_progression_job.py`
#   gaining its own `read_product`/`read_members` module globals, injected
#   by `worker.py`). A composition-root detail with no scenario of its
#   own; the eager helper being reachable from this module at all is what
#   the tests above already require in order to pass.
# - What the eager helper itself does with a real `converge_launch`. That
#   is `test_eager_convergence_helper.py`'s.
# - Every existing scenario of *A recurring pass advances every launch
#   whose gate may open* and its containment requirement. Unaffected by
#   this change and already covered by `test_gate_progression_pass.py`
#   and `test_gate_progression_containment.py`, which this change leaves
#   untouched.
# ---------------------------------------------------------------------------
