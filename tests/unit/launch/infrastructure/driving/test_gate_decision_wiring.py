"""Pressing a gate control: what the decider is told, and what survives.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers the scenarios of *A decision records the approval and reports what
it did* that are stated over the Slack exchange rather than over the
decision, plus two clauses whose subject is the adapter:

- *An approving decision opens the gate and says so* — its reply half
- *A rejecting decision keeps the gate closed* — its reply half
- *A decision whose gate the pass crossed first still reports it opened*
- *A decision on a condition that has since regressed reports why* — its
  reply half
- *A decision is acknowledged before its work completes*
- *A failed cascade does not discard the approval that triggered it*
  (from *One launch's failure does not stop the other launches being
  advanced*)
- *A rejection and its cool-off refresh land together or not at all*
  (from *A gate is asked about at most once a day*), in the half a
  substituted transaction can observe; over a real transaction it is in
  `tests/integration/launch/test_gate_progression_atomicity_live.py`
- the decider-facing half of *An unreadable members collaborator is refused
  by name*: told their decision was not processed, without being told
  anything about their own members entry, and the fault reported where
  operators see it

The recording halves of all of these are in
`tests/unit/launch/application/test_gate_decision.py`. The remaining
scenario of the requirement, *A decision and the pass do not cross the
same gate twice*, is a mutual exclusion held by a Postgres advisory lock
and is integration-tier.

See `test-manifest.md` at the change root for the full accounting.

## Level

The decision adapter over in-memory doubles. Every scenario here is about
what the *press* produces — an acknowledgement, a reply, a surviving
approval — and none of it exists below the adapter: the use case returns a
`Decision` and never sees a Slack request, and the cascade never sees a
decider.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `launch/infrastructure/driving/gate_confirmation.py` as the adapter's
  home, its listeners registered through `contribute_listeners`, and the
  acknowledgement made independently of the work the press triggers
  (`tasks.md` 5.1, 5.2).
- That the reply is derived from the launch **as it stands once the
  cascade has finished**, not from that path's own advance (`tasks.md`
  5.3; delta R7).
- That the approval is recorded in its own transaction and the advance
  then run from the adapter, so a failed cascade cannot discard a decision
  a member actually made (`tasks.md` 3.7, 5.6; `design.md` — Decision 6).
- That the **rejecting** path is wrapped in one `transaction()` so the
  rejecting approval and the cool-off refresh land together (`tasks.md`
  5.5; delta R5).
- That `UnreadableMembersError` is handled by its own type (`tasks.md` 5.7).

INVENTED, each recorded in `test-manifest.md` with its correction point:

- The listener's entry-point name (`_ENTRY_NAMES`) and its call shape
  (`_press`), which supplies a pool of plausible Bolt arguments and
  filters it by the implemented signature — the shape
  `test_automated_decision_wiring.py` established.
- The seam the adapter obtains its transaction through
  (`_SESSION_SEAM_NAMES`), substituted with a provider that **models a
  transaction**: it snapshots the launch store on entry and restores it
  if the block raises. That is what makes the torn-write scenario
  observable at this tier, and it is discriminating rather than
  permissive — an adapter that committed the approval outside the
  transaction leaves it standing and fails that test.
- The names its collaborators are reachable under, transcribed from
  `test_gate_progression_pass.py`.
- The wordings a reply is read through (`_SAYS_OPENED`, `_SAYS_CLOSED`,
  `_SAYS_NOT_PROCESSED`, `_BLAMES_THE_IDENTITY`). None is asserted blind:
  every negative assertion is paired with a positive one in the same file
  that establishes the marker set matches something.

## Expected first-run state

`gate_confirmation.py` does not exist (`tasks.md` 5.1), so every test here
is expected to fail on an absent target. Per `ai-toolkit:testing` that
establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed.
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
from typing import Any, Final

import pytest

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
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    GateBlockedError,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.fixtures import ALICE, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_confirmation"

PRODUCT_ID: Final = product_id()
GATE_ID: Final = "commit"

ALICE_SLACK: Final = "U01ALICE"
ALICE_NAME: Final = "Alice Ordinary"

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
DECIDED_AT: Final = datetime(2027, 5, 3, 10, 0, tzinfo=UTC)

_SAYS_OPENED: Final = ("opened", "is open", "has opened", "advanced", "moved on")
_SAYS_CLOSED: Final = (
    "closed",
    "stays closed",
    "not opened",
    "did not open",
    "rejected",
    "declined",
)
_SAYS_NOT_PROCESSED: Final = (
    "not processed",
    "could not be processed",
    "couldn't be processed",
    "not be processed",
    "not recorded",
    "went wrong",
    "failed",
)
_BLAMES_THE_IDENTITY: Final = (
    "does not know",
    "doesn't know",
    "not on the membership",
    "unknown",
    "unrecognised",
    "unrecognized",
    "no such member",
    "not known",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _hold(gate: str) -> StepDefinition:
    return StepDefinition(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        discipline=next(iter(Discipline)),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=0),
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        hazard=Hazard.NONE,
        assignees=(),
        handler="fixture.holding_check",
        provenance=None,
    )


def _playbook() -> LaunchPlaybook:
    gates = tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(
        version="progression-v1",
        gates=gates,
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
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
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _Member:
    id: str
    display_name: str
    slack_identity: str
    active: bool = True
    clickup_user_id: str | None = None
    admin: bool = False


class _ReaderMembers:
    def __init__(self, *members: _Member) -> None:
        self._members = list(members)

    async def list_members(self) -> tuple[_Member, ...]:
        return tuple(self._members)


class _StoreShapedMembers:
    """The collaborator production once supplied by mistake: a store, not
    a reader."""

    async def load(self) -> Any:
        raise AssertionError("the store was read; nothing here should reach it")

    async def save(self, members: Any) -> None:
        raise AssertionError("the store was written; nothing here writes a membership")


class _FakeLaunches:
    def __init__(self, launch: Launch) -> None:
        self.launches = {launch.product_id: launch}

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self.launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self.launches[launch.product_id] = launch

    async def list_active(self) -> tuple[Launch, ...]:
        return tuple(self.launches.values())

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self.launches.values())

    @property
    def only(self) -> Launch:
        return next(iter(self.launches.values()))


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    async def get(self, version: str = "") -> LaunchPlaybook:
        return self.playbook

    async def __call__(self, *args: Any, **kwargs: Any) -> LaunchPlaybook:
        return self.playbook


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
    def __init__(self, *, failing_refresh: bool = False) -> None:
        self.failing_refresh = failing_refresh
        self.writes: list[str] = []

    async def read(self, *args: Any, **kwargs: Any) -> None:
        return None

    get = read
    latest = read
    last_for = read

    async def record_rejection(self, *args: Any, **kwargs: Any) -> None:
        if self.failing_refresh:
            raise RuntimeError("simulated cool-off refresh failure")
        self.writes.append("rejection")

    refresh = record_rejection
    note_rejection = record_rejection
    record = record_rejection

    async def record_delivery(self, *args: Any, **kwargs: Any) -> None:
        self.writes.append("delivery")

    mark_delivered = record_delivery


class _FakeProgress:
    """Stands in for the cascade the adapter runs under the lock.

    By default it does what the cascade does: cross whatever gates the
    launch's own conditions permit. `crossed_by_the_pass` models the race
    the delta names — the recurring pass having crossed the approved gate
    just before the lock was acquired, so this path's own advance opens
    nothing while the launch has nonetheless moved.
    """

    def __init__(
        self,
        launches: _FakeLaunches,
        order: list[str],
        *,
        crossed_by_the_pass: bool = False,
        failing: bool = False,
    ) -> None:
        self._launches = launches
        self._order = order
        self.crossed_by_the_pass = crossed_by_the_pass
        self.failing = failing
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        self._order.append("progress")
        if self.failing:
            raise RuntimeError("simulated cascade failure")
        launch = self._launches.only
        playbook = _playbook()
        if self.crossed_by_the_pass:
            # The recurring pass crossed the approved gate first. This
            # path's own advance therefore opens nothing.
            launch.advance_gate(playbook)
            await self._launches.save(launch)
            return ()
        try:
            events = launch.advance_gate(playbook)
        except GateBlockedError:
            return ()
        await self._launches.save(launch)
        return events


class _CapturingRespond:
    def __init__(self, order: list[str]) -> None:
        self.replies: list[Any] = []
        self._order = order

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self._order.append("respond")
        self.replies.append({"args": args, "kwargs": kwargs})

    @property
    def rendered(self) -> str:
        return json.dumps(self.replies, default=str)


class _RecordingAck:
    def __init__(self, order: list[str]) -> None:
        self.calls = 0
        self._order = order

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.calls += 1
        self._order.append("ack")


# ---------------------------------------------------------------------------
# Reaching the adapter
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
# The product advisory lock. Substituted rather than exercised: it is a real
# Postgres lock and holds nothing without a database, so what it guarantees
# is asserted in `tests/integration/launch/test_gate_progression_atomicity_live.py`.
# Placed here only so the adapter can be driven at all — the harness's
# transaction provider yields no session for a real lock to be taken on.
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
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` 5.1 creates "
            "it. This is the absent-target state, not a defect in this file."
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
        self._require("launches", "progress", "members", "transaction")

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
        """A provider that *models* a transaction.

        It snapshots the launch store on entry and restores it if the
        block raises, which is what makes "the rejecting approval and the
        refresh land together or not at all" observable here. It is
        discriminating rather than permissive: an adapter that committed
        the approval outside this block leaves it standing.
        """
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

    def _require(self, *roles: str) -> None:
        parameters = set(inspect.signature(_entry(self.module)).parameters)
        role_names = {
            "launches": _LAUNCHES_NAMES,
            "playbooks": _PLAYBOOKS_NAMES,
            "progress": _PROGRESS_NAMES,
            "suppression": _SUPPRESSION_NAMES,
            "journal": _JOURNAL_NAMES,
            "members": _MEMBERS_NAMES,
            "transaction": _SESSION_SEAM_NAMES,
        }
        for role in roles:
            names = role_names[role]
            if self.placed.get(role) or (parameters & set(names)):
                continue
            pytest.fail(
                f"the decision adapter exposes no {role} collaborator under "
                f"any of {names} — correct this file's probe rather than "
                "letting the adapter reach a real one. Its parameters are "
                f"{sorted(parameters)}"
            )


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    launch: Launch | None = None,
    members: Any | None = None,
    crossed_by_the_pass: bool = False,
    failing_cascade: bool = False,
    failing_refresh: bool = False,
) -> _Harness:
    module = _module()
    order: list[str] = []
    launches = _FakeLaunches(launch or _launch_at_commit())
    harness = _Harness(
        module=module,
        monkeypatch=monkeypatch,
        launches=launches,
        playbooks=_FakePlaybooks(_playbook()),
        progress=_FakeProgress(
            launches,
            order,
            crossed_by_the_pass=crossed_by_the_pass,
            failing=failing_cascade,
        ),
        suppression=_FakeSuppression(failing_refresh=failing_refresh),
        journal=_FakeJournal(),
        members=members
        if members is not None
        else _ReaderMembers(
            _Member(id=ALICE, display_name=ALICE_NAME, slack_identity=ALICE_SLACK)
        ),
        order=order,
        respond=_CapturingRespond(order),
        ack=_RecordingAck(order),
    )
    harness.install()
    return harness


def _body(*, approve: bool, gate_id: str = GATE_ID) -> dict[str, Any]:
    """A Slack `block_actions` payload for one of the two gate controls.

    The value carries `{product_id, gate_id}`, which `design.md` —
    Decision 9 fixes; the encoding is INVENTED and part of `_press`'s
    correction point.
    """
    # CORRECTED fixture: the control carries the identifier's *value*, which
    # is what `post_gate_ask` writes. `str(ProductId(...))` renders the
    # dataclass repr, so a body built from it names a product nothing can
    # find — and every assertion below would then be met by "no launch
    # record" rather than by the behaviour under test.
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


@dataclass
class _Answer:
    returned: Any
    respond: _CapturingRespond
    escaped: BaseException | None

    @property
    def text(self) -> str:
        parts = [self.respond.rendered]
        if self.returned is not None:
            parts.append(str(self.returned))
        return "\n".join(parts).lower()

    @property
    def answered(self) -> bool:
        return bool(self.respond.replies) or bool(str(self.returned or "").strip())


async def _press(
    harness: _Harness, *, approve: bool = True, gate_id: str = GATE_ID
) -> _Answer:
    """INVENTED call shape — the single correction point."""
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
    assert supplied, (
        "none of this file's supplied arguments matched the decision entry "
        f"point's signature ({sorted(accepted)}); correct `_press`"
    )
    try:
        returned = entry(**supplied)
        if inspect.isawaitable(returned):
            returned = await returned
    except Exception as error:  # noqa: BLE001 -- an escaping fault is the finding
        return _Answer(returned=None, respond=harness.respond, escaped=error)
    return _Answer(returned=returned, respond=harness.respond, escaped=None)


def _matches(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _approval(harness: _Harness, gate: str = GATE_ID) -> GateApproval | None:
    return harness.launches.only.approval_for(gate)


# ---------------------------------------------------------------------------
# Requirement: A decision records the approval and reports what it did
# ---------------------------------------------------------------------------


async def test_an_approving_decision_replies_that_the_gate_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An approving decision opens the gate and says so — its
    reply half.

    THEN ... the gate opens, and the reply states that it opened.

    This test also establishes that `_SAYS_OPENED` matches something, which
    is what stops the negative assertions in the tests below from passing
    vacuously.
    """
    harness = _harness(monkeypatch)

    answer = await _press(harness, approve=True)

    assert answer.escaped is None, (
        f"the decision escaped the listener: {answer.escaped!r}"
    )
    # SPECIFIED: the gate opens.
    assert harness.launches.only.current_gate != GATE_ID, (
        "the approved gate did not open; the launch stands at "
        f"{harness.launches.only.current_gate}"
    )
    # SPECIFIED: the reply states that it opened.
    assert answer.answered, "the decider got nothing back at all"
    assert _matches(answer.text, _SAYS_OPENED), (
        f"the reply does not state that the gate opened: {answer.text!r}"
    )


async def test_a_rejecting_decision_replies_that_the_gate_stays_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejecting decision keeps the gate closed — its reply half.

    THEN ... no advance is attempted, the gate is unchanged, and the reply
    states that the gate stays closed.
    """
    harness = _harness(monkeypatch)

    answer = await _press(harness, approve=False)

    # SPECIFIED: no advance is attempted.
    assert harness.progress.calls == 0, (
        "a rejecting decision ran the cascade, so an advance was attempted"
    )
    # SPECIFIED: the gate is unchanged.
    assert harness.launches.only.current_gate == GATE_ID
    # SPECIFIED: the reply states that the gate stays closed.
    assert _matches(answer.text, _SAYS_CLOSED), (
        f"the reply does not state that the gate stays closed: {answer.text!r}"
    )


async def test_a_decision_whose_gate_the_pass_crossed_first_still_reports_it_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A decision whose gate the pass crossed first still reports
    it opened.

    WHEN an approving decision is recorded and the recurring pass crosses
    that gate before the decision path acquires the lock
    THEN the reply states that the gate opened, rather than reporting the
    decision's own advance as having opened nothing.

    The cascade substitute reports opening nothing while the launch has
    nonetheless moved past the approved gate — which is exactly the state
    the race leaves. A reply derived from "what my advance did" says
    nothing opened; a reply derived from the launch as it stands says it
    opened, and only the second is right.
    """
    harness = _harness(monkeypatch, crossed_by_the_pass=True)

    answer = await _press(harness, approve=True)

    # Premise: the launch really did move past the approved gate, and this
    # path's own advance reported nothing.
    assert harness.launches.only.current_gate != GATE_ID

    # SPECIFIED: the reply states that the gate opened.
    assert _matches(answer.text, _SAYS_OPENED), (
        "the reply did not tell the decider their gate opened, although it "
        f"had: {answer.text!r}"
    )
    # SPECIFIED: "rather than reporting the decision's own advance as having
    # opened nothing" — the reply must not read as a refusal or a failure.
    assert not _matches(answer.text, _SAYS_NOT_PROCESSED), (
        "the decider was told their decision failed when the gate they "
        f"approved had in fact opened: {answer.text!r}"
    )


async def test_a_decision_on_a_regressed_condition_names_what_blocks_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A decision on a condition that has since regressed reports
    why — its reply half.

    WHEN an approving decision arrives after a blocking condition on that
    gate has stopped being satisfied
    THEN the approval is recorded, the gate does not open, and the reply
    names the condition that now blocks it.

    "Including the case where the approval was recorded but a condition
    became unsatisfied between the ask and the decision" — so the reply
    must say more than "it did not open".
    """
    harness = _harness(monkeypatch, launch=_launch_at_commit(satisfy=False))

    answer = await _press(harness, approve=True)

    # SPECIFIED: the gate does not open.
    assert harness.launches.only.current_gate == GATE_ID
    # SPECIFIED: the reply names the condition that now blocks it. The
    # blocking step's identifier is what `Launch`'s own unsatisfied-
    # conditions read names, so it is what a reply derived from the launch
    # would carry.
    assert "hold.commit" in answer.text or "blocking step" in answer.text, (
        "the reply does not name the condition that blocks the gate, so the "
        f"decider cannot tell why their approval opened nothing: {answer.text!r}"
    )


async def test_a_decision_is_acknowledged_before_its_work_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A decision is acknowledged before its work completes.

    WHEN a decision arrives and the recording and advance it triggers have
    not yet completed
    THEN it is acknowledged within Slack's timeout, and the reply reporting
    what it did follows separately.

    Asserted as ordering rather than as elapsed time: Slack's three-second
    budget is met by acknowledging first, and a listener that acknowledged
    only after its work would be racing the timeout however fast the work
    happened to be. Both halves are asserted — the ack came first, and the
    reply is a separate thing that followed.
    """
    harness = _harness(monkeypatch)

    await _press(harness, approve=True)

    assert harness.ack.calls >= 1, (
        "the decision was never acknowledged, so Slack shows the presser an "
        "error whatever the work did"
    )
    assert harness.order, "nothing was recorded on the ordering timeline"
    assert harness.order[0] == "ack", (
        "the decision was acknowledged only after its work; the order was "
        f"{harness.order}"
    )
    # SPECIFIED: the reply reporting what it did follows separately.
    assert "respond" in harness.order, (
        f"no reply followed the acknowledgement; the order was {harness.order}"
    )
    assert harness.order.index("ack") < harness.order.index("respond")


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# advanced
# ---------------------------------------------------------------------------


async def test_a_failed_cascade_does_not_discard_the_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failed cascade does not discard the approval that
    triggered it.

    WHEN an approving decision is recorded and the cascade it triggers then
    fails
    THEN the approval stands, and the gate it approves is crossed by a
    later pass rather than being asked about again.

    The approval is written in its own transaction, before the lock is
    taken (`design.md` — Decision 6), so the cascade's failure must not
    reach it. "A decision is a fact about what a member did; discarding it
    would leave that member believing they had approved."
    """
    harness = _harness(monkeypatch, failing_cascade=True)

    answer = await _press(harness, approve=True)

    # Premise: the cascade really did fail.
    assert harness.progress.calls == 1, (
        "the cascade was never run, so this test exercised nothing"
    )
    # SPECIFIED: the approval stands.
    approval = _approval(harness)
    assert approval is not None, (
        "the approval was discarded by the failure of the cascade it "
        "triggered, so the member who pressed believes they approved and "
        "nothing records it"
    )
    assert approval.decision is ApprovalDecision.APPROVING
    # SPECIFIED: "rather than being asked about again" — the decision path
    # posts no fresh ask, and writes no delivery record that would claim
    # one was sent.
    assert "delivery" not in harness.suppression.writes, (
        "the decision path recorded an ask delivery for a gate nobody was "
        "asked about again"
    )
    # DERIVED, from `tasks.md` 5.7's shape for the sibling fault: a press
    # whose work failed still answers the decider rather than falling
    # silent after `ack()`. No scenario states it for this fault.
    assert answer.answered, (
        "the decider got nothing back after a cascade failure, which after "
        "`ack()` is a button that silently does nothing"
    )


# ---------------------------------------------------------------------------
# Requirement: A gate is asked about at most once a day
# ---------------------------------------------------------------------------


async def test_a_rejection_and_its_cool_off_refresh_land_together_or_not_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A rejection and its cool-off refresh land together or not
    at all.

    WHEN a rejecting decision is recorded and the cool-off refresh fails
    THEN neither the rejecting approval nor the refresh stands, and the
    decider is told the decision was not recorded.

    "Unlike a delivery, where a lost write costs one duplicate message, a
    lost refresh here re-proposes a gate a member has just declined." The
    transaction seam this file installs restores the launch store when the
    block raises, so an adapter that wrote the approval outside the
    transaction that carries the refresh leaves it standing and fails here.
    Over a real transaction, the same scenario is in
    `tests/integration/launch/test_gate_progression_atomicity_live.py`.
    """
    harness = _harness(monkeypatch, failing_refresh=True)

    answer = await _press(harness, approve=False)

    # SPECIFIED: neither the rejecting approval...
    assert _approval(harness) is None, (
        "the rejecting approval stands although its cool-off refresh failed, "
        "so the gate a member has just declined is proposed again tomorrow "
        "with no record of why it was not"
    )
    # ...nor the refresh stands.
    assert harness.suppression.writes == []
    # SPECIFIED: the decider is told the decision was not recorded.
    assert _matches(answer.text, _SAYS_NOT_PROCESSED), (
        f"the decider was not told their decision went unrecorded: {answer.text!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: Only a known, active member may approve a gate
# ---------------------------------------------------------------------------


async def test_a_wiring_fault_answers_the_decider_without_blaming_them(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: An unreadable members collaborator is refused by name — its
    decider-facing half.

    THEN ... the decider is told their decision was not processed without
    being told anything about their own members entry.

    And, from the requirement's statement: the refusal "SHALL be reported
    where operators see faults". `tasks.md` 5.7 places both in the adapter,
    keyed on `UnreadableMembersError`'s own type.
    """
    harness = _harness(monkeypatch, members=_StoreShapedMembers())

    with caplog.at_level(logging.DEBUG):
        answer = await _press(harness, approve=True)

    # SPECIFIED: the decider is answered rather than met with silence.
    assert answer.escaped is None, (
        "the wiring fault escaped the listener after `ack()`, so the decider "
        f"sees a button that silently does nothing: {answer.escaped!r}"
    )
    assert answer.answered, "the decider got nothing back at all"
    # SPECIFIED: told their decision was not processed...
    assert _matches(answer.text, _SAYS_NOT_PROCESSED), (
        f"the reply does not say the decision was not processed: {answer.text!r}"
    )
    # ...without being told anything about their own members entry.
    assert not _matches(answer.text, _BLAMES_THE_IDENTITY), (
        "a mis-wiring was reported to the decider as a fact about their "
        f"identity: {answer.text!r}"
    )
    # SPECIFIED: reported where operators see faults.
    reported = " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )
    assert reported.strip(), (
        "the wiring fault was answered to the decider and reported nowhere, "
        "so it survives as a sentence in one Slack thread"
    )
    # SPECIFIED: no approval is recorded.
    assert _approval(harness) is None


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the two listeners keep their `ack()`-first ordering under Bolt's
#   own dispatch. The ordering is asserted here against the listener
#   itself; how Bolt schedules it is `automation_confirmation`'s
#   established shape and is not restated by this delta.
# - The wording of any reply beyond the facts each scenario names.
#   Asserting a phrasing would impose a contract nobody agreed to.
# - That the listeners are registered through `contribute_listeners` in
#   the HTTP process and not the worker (`tasks.md` 5.2, 6.2). That is a
#   wiring obligation of `scheduled-jobs` and the composition root, with
#   no scenario in this delta;
#   `tests/unit/test_registrations_across_processes.py` is where it would
#   be asserted.
# - The lock the advance runs under. It is a Postgres advisory lock and
#   holds nothing in a test with no Postgres; see
#   `tests/integration/launch/test_gate_progression_atomicity_live.py`.
# ---------------------------------------------------------------------------
