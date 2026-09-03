"""A handler is invoked only once its launch has released the step
(`launch-step-automation`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-step-automation/spec.md`:

- MODIFIED *An automated step's handler is invoked by recurring work* —
  only its five new scenarios: *A step whose start gate the launch has
  not reached is not invoked*, *A step naming no start gate keeps running
  from the first pass*, *A step is invoked on the pass after the launch
  releases it*, *An unreleased step is not reported as stuck*, and *An
  unregistered handler on an unreleased step is not reported by the
  pass*.
- MODIFIED *An unregistered handler is reported and skipped, never fatal*
  — only its one new scenario, *A step naming an unregistered handler is
  not reported before its launch releases it*.

Both requirements' remaining scenarios are reproduced from the served
spec — one with "carries an `active` `automated` step" reworded to
"carries a **released** `active` `automated` step" — and are covered by
`test_automation_pass.py` in this directory, whose fixtures declare no
start gate and are therefore released from a launch's first gate. They
are accounted for against those tests in the manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`.

## Level

The pass over in-memory collaborators, the level and the harness
`test_automation_pass.py` establishes — the smallest unit that can
observe which handlers a pass reached and what it reported.

## INVENTED, with correction points

Inherited from `test_automation_pass.py`, whose docstring records them:
the pass's entry point (found by probing `_ENTRY_NAMES`), its
collaborator keywords, the handler contract, and the registry's shape.
Correction points: `_pass_entry`, `_run_pass`.

Added by this file:

- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition`. Correction point: `_automated`.
- That the backoff record is *read* per candidate step, so "costs no
  read" is observable. `tasks.md` 4.3 asks for the skip to happen
  "before the backoff read **and before the handler is resolved**".
  Correction point: `_RecordingBackoff`.
- That a stuck-step report reaches the monitoring notifier, per
  `test_automation_pass_repeat_backoff.py`. Correction point:
  `_RecordingNotifier`.

## Expected first-run state

`starts_at_gate` does not exist, so every test here is expected to fail
on an **absent target** (`TypeError` from the constructor) — except the
two *negative* scenarios below, which assert that nothing was invoked or
reported and would pass vacuously against today's ungated pass. Each of
those therefore carries a positive control in the same test: the same
pass, over the same collaborators, must reach a step it *has* released.
Without that control a green result would establish nothing.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

import importlib
import inspect
import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
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
from commerce_ops.shared.domain.identity import ProductId, Sku
from tests.support.fixtures import HANDLER_NAME, PRODUCT_NAME, PRODUCT_SKU, product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

pytestmark = pytest.mark.anyio

#: Resolved by name rather than imported, matching
#: `test_launch_admin_detail.py`: the module is a driving adapter this
#: file only reaches through its entry point.
automation_pass: ModuleType = importlib.import_module(
    "commerce_ops.launch.infrastructure.driving.automation_pass"
)

PRODUCT_ID: Final = product_id()
A_DISCIPLINE: Final = next(iter(Discipline))

WAITING_STEP: Final = "listing.waits-for-listable"
RUNNING_STEP: Final = "listing.runs-from-the-first-pass"
OTHER_HANDLER_NAME: Final = "listing.other_advisor"
UNREGISTERED_HANDLER: Final = "listing.nobody_registers_this"

RECOMMENDATION: Final = "the proposed sub-category node"
NOW: Final = datetime(2027, 2, 1, 9, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 4, 15)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": WAITING_STEP,
        "name": "Choose the sub-category node",
        "description": None,
        "gate": "listable",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _automated(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "kind": StepKind.AUTOMATED,
        "handler": HANDLER_NAME,
    }
    attributes.update(overrides)
    return _step(**attributes)


def _hold(gate: str) -> StepDefinition:
    """One blocking `human` filler per gate. `human` deliberately: an
    `automated` filler would itself be a candidate for invocation and
    would contaminate every assertion about which handlers the pass
    reached."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="release-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _launch(playbook: LaunchPlaybook, product_id: ProductId = PRODUCT_ID) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and launch.progress_for(step.identifier) is None:
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
    return launch


# ---------------------------------------------------------------------------
# Test doubles, as `test_automation_pass.py` records them
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _CatalogProduct:
    name: str
    sku: Sku


class _FakeCatalog:
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
    def __init__(self, resolution: StepResolution | None = None) -> None:
        self.resolution = resolution or StepResolution(
            outcome=Satisfied, result=RECOMMENDATION
        )
        self.contexts: list[Any] = []

    async def __call__(self, context: Any) -> StepResolution:
        self.contexts.append(context)
        return self.resolution

    @property
    def invoked(self) -> bool:
        return bool(self.contexts)


class _FakeHandlers:
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


class _FakeResults:
    def __init__(self) -> None:
        self.rows: list[Any] = []

    async def pending_for(self, product_id: ProductId, step_id: str) -> Any:
        return None

    async def store(self, **fields: Any) -> Any:
        row = dict(fields)
        self.rows.append(row)
        return row

    async def undelivered(self) -> list[Any]:
        return []

    async def mark_delivered(self, row: object, when: datetime | None = None) -> None:
        return None

    async def latest_rejection(self, product_id: ProductId, step_id: str) -> Any:
        return None


class _RecordingOutcomes:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
        self.calls.append(kwargs)
        return ()

    def for_step(self, step_id: str) -> list[dict[str, Any]]:
        return [call for call in self.calls if call.get("step_id") == step_id]


class _FakeDelivery:
    def __init__(self) -> None:
        self.delivered: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.delivered.append(kwargs or args)


class _RecordingBackoff:
    """A backoff record that holds nothing and *records every read*.

    Holding nothing reproduces the pre-change world, so nothing here is
    suppressed by a cool-off. Recording the reads is what makes
    `tasks.md` 4.3's "an unreleased step costs no read" observable.
    """

    def __init__(self) -> None:
        self.reads: list[str] = []

    async def read(self, *args: Any, **kwargs: Any) -> None:
        self.reads.extend(
            str(value) for value in (*args, *kwargs.values()) if isinstance(value, str)
        )

    async def note(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def mark_reported(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def rollback(self) -> None:
        return None


class _RecordingNotifier:
    """The monitoring notifier the stuck-step report is delivered through —
    a `ThreadReplyNotifier` (`launch.application.ports`), not the
    message-only `MonitoringNotifier`: `fix-stuck-step-report-notifier`
    narrowed `run_automation_pass`'s `notifier` parameter to the shape
    this collaborator actually stands in for. Every scenario in this file
    asserts on *absence* (no message naming a given step), so nothing here
    exercises delivery, but an old, incompatible call shape would still
    have masked a real mismatch had one been introduced."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def post_monitoring_message(
        self, *, channel: str, text: str, thread_ts: str | None = None
    ) -> None:
        self.messages.append(text)


async def _inert_establish_thread(*args: Any, **kwargs: Any) -> tuple[str, None]:
    """Thread-establishment nothing in this file exercises.

    Added by `thread-launch-slack-notifications`, which made it a required
    collaborator like `backoff` and `notifier` above — inert here for the
    same reason: nothing below asserts on threading or tagging.
    """
    return "FAKE_THREAD_TS", None


@dataclass
class _Collaborators:
    launches: _FakeLaunches
    playbook: LaunchPlaybook
    handlers: _FakeHandlers
    results: _FakeResults = field(default_factory=_FakeResults)
    recorder: _RecordingOutcomes = field(default_factory=_RecordingOutcomes)
    catalog: _FakeCatalog = field(default_factory=_FakeCatalog)
    delivery: _FakeDelivery = field(default_factory=_FakeDelivery)
    backoff: _RecordingBackoff = field(default_factory=_RecordingBackoff)
    notifier: _RecordingNotifier = field(default_factory=_RecordingNotifier)


_ENTRY_NAMES: Final = (
    "run_automation_pass",
    "run_pass",
    "resolve_automated_steps",
    "run_automation",
)


def _pass_entry() -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(automation_pass, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {automation_pass.__name__} under any "
        f"of {_ENTRY_NAMES} — correct this file's probe to the implemented name"
    )


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
        "backoff": collaborators.backoff,
        "notifier": collaborators.notifier,
        "establish_thread": _inert_establish_thread,
        "now": now,
    }
    accepted = set(inspect.signature(entry).parameters)
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the pass entry point does not accept {unknown}; correct `_run_pass` "
        "to the implemented collaborator names"
    )
    return await entry(**supplied)


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: An automated step's handler is invoked by recurring
# work (the five new scenarios)
# ---------------------------------------------------------------------------


async def test_a_step_whose_start_gate_is_not_reached_is_not_invoked() -> None:
    """Scenario: A step whose start gate the launch has not reached is not
    invoked.

    WHEN a pass runs over a launch standing at `commit` and the served
    playbook carries an `active` `automated` step whose start gate is
    `listable`
    THEN its handler is not invoked, and nothing is recorded against the
    step.

    A **positive control** rides in the same pass: a second automated
    step that names no start gate must still be invoked. Without it this
    test would pass against a pass that invoked nothing at all, which
    would establish nothing about the release rule.
    """
    waiting = _automated(identifier=WAITING_STEP, starts_at_gate="listable")
    running = _automated(
        identifier=RUNNING_STEP,
        name="Work whose author said nothing about starting",
        handler=OTHER_HANDLER_NAME,
    )
    playbook = _playbook(waiting, running)

    held_back = _ScriptedHandler()
    control = _ScriptedHandler()
    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(
            **{HANDLER_NAME: held_back, OTHER_HANDLER_NAME: control}
        ),
    )

    await _run_pass(collaborators)

    # SPECIFIED: its handler is not invoked.
    assert not held_back.invoked
    # SPECIFIED: and nothing is recorded against the step.
    assert collaborators.recorder.for_step(WAITING_STEP) == []
    # Positive control: the pass did run, and did reach a released step.
    assert control.invoked, (
        "the pass invoked nothing at all, so the assertion above says "
        "nothing about the release rule"
    )
    # `tasks.md` 4.3: an unreleased step "costs no read".
    assert WAITING_STEP not in collaborators.backoff.reads, (
        "the pass read the backoff record for a step it had not released; "
        "the skip belongs before that read"
    )


async def test_a_step_naming_no_start_gate_keeps_running_from_the_first_pass() -> None:
    """Scenario: A step naming no start gate keeps running from the first
    pass.

    WHEN a pass runs over a launch standing at `commit` and the served
    playbook carries an `active` `automated` step naming no start gate
    and no dependencies
    THEN its handler is invoked, whatever gate the step itself belongs
    to.

    SPECIFIED: "Gating invocation therefore withholds nothing by itself"
    — the step below belongs to `live`, five gates ahead of where the
    launch stands, and still runs.

    **Expected to PASS on its first run**, and recorded as such in the
    manifest rather than counted as coverage of new behaviour: today's
    pass is ungated, so it already invokes this handler. This is a
    regression guard on what the change must *not* take away — the whole
    argument that gating invocation withholds nothing rests on it.
    """
    running = _automated(identifier=RUNNING_STEP, gate="live")
    playbook = _playbook(running)

    handler = _ScriptedHandler()
    launch = _launch(playbook)
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    assert launch.current_gate == "commit"

    await _run_pass(collaborators)

    assert handler.invoked


async def test_a_step_is_invoked_on_the_pass_after_the_launch_releases_it() -> None:
    """Scenario: A step is invoked on the pass after the launch releases
    it.

    WHEN a launch that stood at `commit` advances to the start gate of an
    unresolved `active` `automated` step, and the next pass runs
    THEN that step's handler is invoked.

    Read across two passes, so the *change* is what is observed.
    """
    waiting = _automated(identifier=WAITING_STEP, starts_at_gate="listable")
    playbook = _playbook(waiting)

    handler = _ScriptedHandler()
    launch = _launch(playbook)
    collaborators = _Collaborators(
        launches=_FakeLaunches(launch),
        playbook=playbook,
        handlers=_FakeHandlers(**{HANDLER_NAME: handler}),
    )

    await _run_pass(collaborators)
    assert not handler.invoked

    _advance_to(launch, playbook, "listable")

    await _run_pass(collaborators)

    assert handler.invoked


async def test_an_unreleased_step_is_not_reported_as_stuck(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: An unreleased step is not reported as stuck.

    WHEN a pass runs over a launch that has not released an `active`
    `automated` step
    THEN no stuck-step report is produced for it and no application log
    record names it as making no progress.

    SPECIFIED reason: "It has not failed to make progress — it has not
    been asked to."

    The positive control here is the second step, whose handler runs: a
    pass that did nothing at all would satisfy both negatives.
    """
    waiting = _automated(identifier=WAITING_STEP, starts_at_gate="listable")
    running = _automated(
        identifier=RUNNING_STEP,
        name="Work whose author said nothing about starting",
        handler=OTHER_HANDLER_NAME,
    )
    playbook = _playbook(waiting, running)

    control = _ScriptedHandler()
    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(
            **{HANDLER_NAME: _ScriptedHandler(), OTHER_HANDLER_NAME: control}
        ),
    )

    with caplog.at_level(logging.INFO):
        await _run_pass(collaborators)

    assert control.invoked, "the pass did not run, so neither negative below holds"

    # SPECIFIED: no stuck-step report is produced for it.
    assert not [
        message
        for message in collaborators.notifier.messages
        if WAITING_STEP in message
    ]
    # SPECIFIED: and no application log record names it as making no
    # progress. DERIVED reading: the step's identifier appearing in any
    # record the pass emitted about it.
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert WAITING_STEP not in logged


async def test_an_unregistered_handler_on_an_unreleased_step_is_not_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scenario: An unregistered handler on an unreleased step is not
    reported by the pass.

    Also covers the MODIFIED requirement *An unregistered handler is
    reported and skipped, never fatal*'s new scenario *A step naming an
    unregistered handler is not reported before its launch releases it*
    — the two are the same observation stated from the two requirements
    that share it.

    WHEN a pass runs over a launch that has not released a step whose
    named handler no registered use case answers to
    THEN the pass reports nothing for it, the startup registration report
    being where that fault is named.

    SPECIFIED reason: "reporting it every pass until its gate arrives
    would bury the steps that are actually stuck".

    The positive control is a *released* step naming the same
    unregistered handler on a second launch: the pass must still report
    that one, which is what makes the silence above about release rather
    than about the report having been removed.
    """
    unreleased = _automated(
        identifier=WAITING_STEP,
        handler=UNREGISTERED_HANDLER,
        starts_at_gate="listable",
    )
    released = _automated(
        identifier=RUNNING_STEP,
        name="Released work naming a handler nobody registers",
        handler=UNREGISTERED_HANDLER,
    )
    playbook = _playbook(unreleased, released)

    collaborators = _Collaborators(
        launches=_FakeLaunches(_launch(playbook)),
        playbook=playbook,
        handlers=_FakeHandlers(),
    )

    with caplog.at_level(logging.INFO):
        await _run_pass(collaborators)

    reported = " ".join(record.getMessage() for record in caplog.records)

    # Positive control: the released step naming the same unregistered
    # handler *is* reported, exactly as it always was.
    assert RUNNING_STEP in reported, (
        "the pass reported nothing for a released step naming an "
        "unregistered handler, so the silence asserted below is not about "
        "release"
    )
    # SPECIFIED: the pass reports nothing for the unreleased one.
    assert WAITING_STEP not in reported
    assert not [
        message
        for message in collaborators.notifier.messages
        if WAITING_STEP in message
    ]
    # `tasks.md` 4.3: the skip happens "before the handler is resolved".
    assert collaborators.recorder.for_step(WAITING_STEP) == []
