"""A recorded decision that crosses a gate triggers an eager convergence.

Derived strictly from the delta spec of the OpenSpec change
`trigger-clickup-projection-on-launch-events`:
`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`

Covers, from the ADDED requirement *A launch is converged eagerly at start
and at a gate crossing*, the scenarios stated over this call site:

- *A gate crossing's newly released steps get tasks immediately, however
  the gate opened* — the decision half: a decision that actually crosses a
  gate triggers the eager helper for that launch.
- *A failed eager run does not fail the action that triggered it* — this
  call site's own half: the decider's reply is unaffected by a raising
  helper, and — per `design.md`'s own ordering decision — the helper runs
  *after* `respond(message)` has already sent the decider their reply, so
  a slow or failing convergence cannot hold that reply up either.
- *The eager run stands down exactly as the pass does* — inherited: a
  decision that never crosses a gate (rejected, or approved but blocked)
  never reaches the eager helper at all, because there is nothing to
  converge.

`tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`
already covers this same adapter's other scenarios (the reply's wording,
acknowledgement-before-work, the failed-cascade-does-not-discard-the-
approval guarantee); this file adds only the eager-convergence trigger and
does not restate them.

See `test-manifest.md` at the change root for the full accounting.

## Level

The decision adapter over in-memory doubles, the level
`test_gate_decision_wiring.py` already holds for this surface. Nothing
below the adapter can observe whether the eager helper was reached, or in
what order relative to `respond()`.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that the adapter calls the eager helper
once `progress_launch`'s cascade actually crosses a gate, and that it does
so *after* `respond(message)` has sent the decider their reply (`tasks.md`
3.4; `design.md` — "in `gate_confirmation.py`'s decision path, the eager
helper is awaited *after* `respond(message)` sends the decider their
reply").

INVENTED: the eager helper's name (`_HELPER_NAMES`, kept in step with
`test_eager_convergence_helper.py`); every other collaborator name, the
entry point's call shape (`_press`), and the transaction seam that models a
real transaction are transcribed wholesale from `test_gate_decision_wiring.py`,
which records the provenance of each.

## Expected first-run state

`gate_confirmation.py` calls no eager helper yet (`tasks.md` 3.4), so every
test here is expected to fail on an **absent target**. Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e`, clean tree: `uv run pytest tests/unit tests/agents` —
1743 passed, 0 failed, 72 skipped.
"""

from __future__ import annotations

import copy
import importlib
import inspect
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final, cast

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
    StepKind,
)
from commerce_ops.launch.domain.launch_run import (
    GateBlockedError,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fakes import AsyncFakePlaybooks as _FakePlaybooks
from tests.support.fakes import FakeLaunches
from tests.support.fixtures import ALICE, product_id
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.values import MemberValue as _Member

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_confirmation"

PRODUCT_ID: Final = product_id()
GATE_ID: Final = "commit"

ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Ordinary"

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 5, 3, 10, 0, tzinfo=UTC)

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
# Domain fixtures — transcribed from `test_gate_decision_wiring.py`
# ---------------------------------------------------------------------------


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        handler="fixture.holding_check",
        kind=StepKind.AUTOMATED,
        timing_anchor=OffsetAnchor(days=0),
    )


def _playbook() -> LaunchPlaybook:
    return _build_playbook(
        version="progression-v1",
        filler=_hold,
    )


def _launch_at_commit(*, satisfy: bool = True) -> Launch:
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    if satisfy:
        launch.record_step_outcome(
            playbook,
            step_id="hold.commit",
            outcome=Satisfied,
            provenance=Provenance(
                source="automated",
                who="hold-filler",
                when=NOW,
                evidence="the blocking check reported green",
            ),
        )
    return launch


# ---------------------------------------------------------------------------
# Test doubles — transcribed from `test_gate_decision_wiring.py`
# ---------------------------------------------------------------------------


class _ReaderMembers:
    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


class _FakeLaunches(FakeLaunches):
    """The shared launch store, adapted: this file reads it through its
    own helper. The helpers are rewritten against the shared list, since
    every local kept its launches in a dict keyed by identifier."""

    def __init__(self, launch: Launch) -> None:
        super().__init__(launch)

    @property
    def only(self) -> Launch:
        return cast(Launch, self.launches[0])


class _FakeJournal:
    def __init__(self) -> None:
        self.appended: list[Any] = []

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        return None


class _FakeSuppression:
    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    get = read
    latest = read
    last_for = read

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        return None

    refresh = record_rejection
    note_rejection = record_rejection
    record = record_rejection

    async def record_delivery(self, *args: Any, **kwargs: Any) -> None:
        return None

    mark_delivered = record_delivery


@dataclass
class _Progressed:
    """The real `LaunchProgressed.crossed` field (`use_cases.py`) —
    transcribed from `test_gate_progression_pass_eager_convergence.py`,
    which records the same provenance: `test_gate_decision_wiring.py`'s own
    fake predates this field and returns a bare tuple of events instead,
    which `_advance_after_approval`'s `getattr(progressed, "crossed",
    None)` tolerates as "no crossing" — fine there, since none of that
    file's tests exercise eager convergence, but wrong here, where
    triggering it is exactly what this file tests."""

    crossed: tuple[str, ...] = ()


class _FakeProgress:
    """Stands in for the cascade the adapter runs under the lock —
    transcribed from `test_gate_decision_wiring.py`, minus the racing-pass
    variant this file does not need."""

    def __init__(self, launches: _FakeLaunches, order: list[str]) -> None:
        self._launches = launches
        self._order = order
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        self._order.append("progress")
        launch = self._launches.only
        playbook = _playbook()
        gate_before = launch.current_gate
        try:
            events = launch.advance_gate(playbook)
        except GateBlockedError:
            return _Progressed()
        await self._launches.save(launch)
        crossed = (gate_before,) if events else ()
        return _Progressed(crossed=crossed)


class _CapturingRespond:
    def __init__(self, order: list[str]) -> None:
        self.replies: list[Any] = []
        self._order = order

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self._order.append("respond")
        self.replies.append({"args": args, "kwargs": kwargs})


class _RecordingAck:
    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self._order = order

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        self._order.append("ack")


class _RecordingHelper:
    def __init__(self, order: list[str], *, failing: bool = False) -> None:
        self.calls: list[Any] = []
        self._order = order
        self.failing = failing

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))
        self._order.append("eager")
        if self.failing:
            raise RuntimeError("simulated eager-convergence failure")


# ---------------------------------------------------------------------------
# Reaching the adapter — transcribed from `test_gate_decision_wiring.py`
# ---------------------------------------------------------------------------

_ENTRY_NAMES: Final = (
    "_handle_gate_decision",
    "handle_gate_decision",
    "_handle_decision",
    "handle_decision",
    "_decide",
    "handle_gate_decision_action",
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
_MEMBERS_NAMES: Final = ("read_members", "members", "MembersReader", "members_reader")
_JOURNAL_NAMES: Final = ("journal", "LaunchJournalRepository", "launch_journal")
_SESSION_SEAM_NAMES: Final = ("transaction", "session")
_LOCK_NAMES: Final = (
    "hold_launch_advance_lock",
    "advance_lock",
    "hold_advance_lock",
)


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
        f"the gate confirmation adapter exposes no decision entry point on "
        f"{module.__name__} under any of {_ENTRY_NAMES} — correct this "
        "file's probe to the implemented name"
    )


def _helper_name(module: ModuleType) -> str:
    for name in _HELPER_NAMES:
        if callable(getattr(module, name, None)):
            return name
    pytest.fail(
        f"{module.__name__} exposes no eager-convergence helper under any of "
        f"{_HELPER_NAMES}; `tasks.md` 3.4 adds it. This is the absent-target "
        "state, not a defect in this file — do not add the attribute to make "
        "this pass."
    )


@dataclass
class _Harness:
    module: ModuleType
    monkeypatch: pytest.MonkeyPatch
    launches: _FakeLaunches
    playbooks: _FakePlaybooks
    progress: _FakeProgress
    suppression: _FakeSuppression
    journal: _FakeJournal
    members: Any
    order: list[str]
    respond: _CapturingRespond
    ack: _RecordingAck
    helper: _RecordingHelper
    placed: dict[str, list[str]] = field(default_factory=dict)

    def install(self) -> None:
        self._place("launches", _LAUNCHES_NAMES, self.launches)
        self._place("playbooks", _PLAYBOOKS_NAMES, self.playbooks)
        self._place("progress", _PROGRESS_NAMES, self.progress)
        self._place("suppression", _SUPPRESSION_NAMES, self.suppression)
        self._place("journal", _JOURNAL_NAMES, self.journal)
        self._place("members", _MEMBERS_NAMES, self.members)
        self._place_lock()
        self._place_transaction()
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

    def _place_lock(self) -> None:
        async def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        for name in _LOCK_NAMES:
            if hasattr(self.module, name):
                self.monkeypatch.setattr(self.module, name, _noop)

    def _place_transaction(self) -> None:
        """A provider that *models* a transaction — transcribed from
        `test_gate_decision_wiring.py`."""
        placed: list[str] = []
        store = self.launches
        for name in _SESSION_SEAM_NAMES:
            if not hasattr(self.module, name):
                continue

            @asynccontextmanager
            async def _provider(
                *args: Any, _store: _FakeLaunches = store, **kwargs: Any
            ) -> AsyncIterator[Any]:
                snapshot = copy.deepcopy(_store.launches)
                try:
                    yield None
                except BaseException:
                    _store.launches = snapshot
                    raise

            self.monkeypatch.setattr(self.module, name, _provider)
            placed.append(name)
        self.placed["transaction"] = placed


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launch: Launch | None = None,
    failing_helper: bool = False,
) -> _Harness:
    module = _module()
    order: list[str] = []
    launches = _FakeLaunches(launch or _launch_at_commit())
    harness = _Harness(
        module=module,
        monkeypatch=monkeypatch,
        launches=launches,
        playbooks=_FakePlaybooks(_playbook()),
        progress=_FakeProgress(launches, order),
        suppression=_FakeSuppression(),
        journal=_FakeJournal(),
        members=_ReaderMembers(
            _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
        ),
        order=order,
        respond=_CapturingRespond(order),
        ack=_RecordingAck(order),
        helper=_RecordingHelper(order, failing=failing_helper),
    )
    harness.install()
    return harness


def _body(*, approve: bool, gate_id: str = GATE_ID) -> dict[str, Any]:
    value = json.dumps({"product_id": PRODUCT_ID.value, "gate_id": gate_id})
    action = {
        "action_id": "approve_launch_gate" if approve else "reject_launch_gate",
        "type": "button",
        "value": value,
    }
    return {
        "type": "block_actions",
        "user": {"id": ALICE_SLACK},
        "channel": {"id": "C0MONITORING"},
        "actions": [action],
        "response_url": "https://slack.example/respond",
    }


async def _press(
    harness: _Harness, *, approve: bool = True, gate_id: str = GATE_ID
) -> None:
    entry = _entry(harness.module)
    body = _body(approve=approve, gate_id=gate_id)
    pool: dict[str, Any] = {
        "ack": harness.ack,
        "body": body,
        "payload": body["actions"][0],
        "action": body["actions"][0],
        "respond": harness.respond,
        "say": harness.respond,
        "client": None,
        "context": {},
        "logger": logging.getLogger("commerce_ops.launch.gate_confirmation"),
        "approve": approve,
        "approving": approve,
        "product_id": PRODUCT_ID,
        "gate_id": gate_id,
        "slack_identity": ALICE_SLACK,
        "when": DECIDED_AT,
    }
    accepted = set(inspect.signature(entry).parameters)
    supplied = {key: value for key, value in pool.items() if key in accepted}
    returned = entry(**supplied)
    if inspect.isawaitable(returned):
        await returned


# ---------------------------------------------------------------------------
# Scenario: A gate crossing's newly released steps get tasks immediately,
# however the gate opened — the decision half
# ---------------------------------------------------------------------------


async def test_a_decision_that_crosses_a_gate_triggers_the_eager_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate crossing's newly released steps get tasks
    immediately, however the gate opened.

    WHEN a launch's gate crosses through a recorded decision
    THEN the eager helper is triggered for that launch.
    """
    harness = _harness(monkeypatch)

    await _press(harness, approve=True)

    assert harness.launches.only.current_gate != GATE_ID, (
        "the gate never crossed, so this test does not exercise a crossing at all"
    )
    # SPECIFIED-BY-TASKS: the eager helper is triggered.
    assert len(harness.helper.calls) == 1, (
        "a decision that crossed a gate did not trigger the eager-"
        f"convergence helper: {harness.helper.calls!r}"
    )


async def test_a_rejecting_decision_never_triggers_the_eager_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A rejecting decision crosses no gate, so there is nothing new to
    converge — the eager run is not stated to fire on a decision that
    changes nothing. Paired with the test above so "triggered" is not
    trivially true of every press."""
    harness = _harness(monkeypatch)

    await _press(harness, approve=False)

    assert harness.launches.only.current_gate == GATE_ID
    assert harness.helper.calls == [], (
        "a rejecting decision, which crosses no gate, triggered the "
        f"eager-convergence helper anyway: {harness.helper.calls!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A failed eager run does not fail the action that triggered it
# ---------------------------------------------------------------------------


async def test_a_failing_eager_run_does_not_affect_the_deciders_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed eager run does not fail the action that
    triggered it.

    WHEN the eager run raises while converging a launch that just crossed
    a gate through a recorded decision
    THEN the decision completes and is reported exactly as it would have
    been had the eager run succeeded.

    The helper substituted here raises past its own documented
    containment, mirroring the defence-in-depth
    `test_advance_and_ask.py`'s sibling route test already applies.
    """
    harness = _harness(monkeypatch, failing_helper=True)

    await _press(harness, approve=True)

    assert harness.helper.calls, (
        "the failing eager helper was never reached, so this test exercised nothing"
    )
    assert harness.respond.replies, (
        "a failing eager-convergence helper cost the decider their reply"
    )


async def test_the_eager_helper_runs_after_the_decider_has_already_been_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED-BY-DESIGN (`design.md`: the eager helper "is awaited
    *after* `respond(message)` sends the decider their reply — the decider
    is told what their decision did ... without waiting on ClickUp
    latency").

    So a slow or failing convergence cannot delay, and cannot be blamed
    for delaying, the reply the decider already has.
    """
    harness = _harness(monkeypatch)

    await _press(harness, approve=True)

    assert "eager" in harness.order and "respond" in harness.order, (
        f"the ordering timeline is missing an expected event: {harness.order!r}"
    )
    assert harness.order.index("respond") < harness.order.index("eager"), (
        "the eager helper ran before the decider's reply was sent, so a "
        f"slow convergence could hold the reply up: {harness.order!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Every other scenario of *A decision records the approval and reports
#   what it did* — the reply's wording, acknowledgement-before-work, the
#   failed-cascade-does-not-discard-the-approval guarantee. Unaffected by
#   this change and already covered by `test_gate_decision_wiring.py`,
#   which this change leaves untouched.
# - What the eager helper itself does with a real `converge_launch`. That
#   is `test_eager_convergence_helper.py`'s.
# - A decision whose approval is recorded but whose advance is blocked by
#   a since-regressed condition (`GateBlockedError`). No gate crosses
#   there either, so the same "nothing new to converge" reasoning as the
#   rejecting-decision test applies; a dedicated test would duplicate
#   rather than add.
# ---------------------------------------------------------------------------
