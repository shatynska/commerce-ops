"""One launch's failure is contained to that launch, and the run still fails.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers, from the ADDED requirement *One launch's failure does not stop the
other launches being advanced*, the three scenarios stated over the walk:

- *A failing launch does not stop the others*
- *An unrestorable store ends the walk*
- *A shutdown stops the walk*

Its other three scenarios are not stated over the walk and are elsewhere:

- *A gate declining mid-cascade stops it without undoing what it crossed*
  and *A cascade failing part-way leaves the launch where it started* are
  the cascade's, in
  `tests/unit/launch/application/test_progress_launch.py` — the second in
  the half a fake transaction can observe, its other half at the
  integration tier.
- *A failed cascade does not discard the approval that triggered it* is
  the decision path's, in
  `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The pass body over in-memory doubles. The subject of every scenario here
is the *walk* across launches, which lives only in the job: the cascade
below it takes one product identifier and does not know other launches
exist, and the run's outcome has no signal below the job either.

## Reading the outcome clauses

"Reported as a failed run" is read as *the job body raises*; "not failed"
as *it returns normally*. The reading
`test_clickup_sync_job_containment.py` records for the same words.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts: that containment lives in the job's loop
around `progress_launch` (`tasks.md` 4.5); that the catch is `Exception`
and lets a cancellation propagate (same, and delta R3's last paragraph);
that the shared store is restored between launches and that a restore
which cannot be performed ends the walk (`tasks.md` 4.6); and that the
aggregate error names each failed launch by **product identifier** (delta
R3).

INVENTED, each recorded in `test-manifest.md` with its correction point:

- The pass's entry point, its collaborator names and how they are placed.
  Transcribed from
  `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`,
  which is the single correction point for all of it; the tuples are
  repeated here rather than imported because this repository's test files
  carry their own fixtures (`tests/` holds no importable package).
- That the restore is observable as a `rollback()` on the session the walk
  shares. `tasks.md` 4.6 names `clickup_sync_job.py`'s
  `_restore_after_store_fault` as the shape, and that is what it does.
  *The unrestorable-store test guards on the restore having been
  attempted*, so a pass restoring by some other means fails loudly with an
  instruction rather than silently asserting nothing.
- That the contained failure is reported through the standard library's
  logging, which is the only report the artifacts name.

What must survive any correction is what each test asserts: which launches
were attempted, in what order the reports appeared, whether the job
raised, and which product identifiers its error names.

## Expected first-run state

`gate_progression_job.py` does not exist (`tasks.md` 4.1), so every test
here is expected to fail on an absent target. Per `ai-toolkit:testing`
that establishes absence only.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed. `uv run pytest tests/integration` — 3 passed, 112
skipped (no `DATABASE_URL` is configured here).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import logging
import uuid
from collections.abc import AsyncIterator, Iterator
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
from commerce_ops.shared.domain.identity import ProductId

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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

#: Three launches, so "the walk continued" is distinguishable from "the
#: walk did one more thing": a failure in the middle has both a launch
#: before it and a launch after it.
FIRST: Final = ProductId(str(uuid.uuid4()))
SECOND: Final = ProductId(str(uuid.uuid4()))
THIRD: Final = ProductId(str(uuid.uuid4()))
WALK: Final = (FIRST, SECOND, THIRD)

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


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


def _launch_for(product_id: ProductId) -> Launch:
    """A launch standing at `listable` with nothing satisfied — nothing
    here turns on what any launch's gate is, only on which of them the
    walk attempted."""
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=product_id, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != "listable":
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=Provenance(
                        source="automated",
                        who="hold-filler",
                        when=NOW,
                        evidence="the blocking check reported green",
                    ),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(
                launch.current_gate,
                GateApproval(
                    decision=ApprovalDecision.APPROVING,
                    approver="Helen",
                    when=NOW,
                    posture=None,
                ),
            )
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# The timeline: log records and cascade calls in one sequence
# ---------------------------------------------------------------------------


@dataclass
class _Timeline:
    """What happened, in the order it happened.

    One sequence, which is what makes "reported *as it happens*"
    assertable: a report that only appeared after the walk finished would
    satisfy a per-launch count while failing the requirement.
    """

    events: list[tuple[str, str]] = field(default_factory=list)

    def note(self, kind: str, detail: str) -> None:
        self.events.append((kind, detail))

    def index_of(self, kind: str, detail: str) -> int | None:
        for position, event in enumerate(self.events):
            if event == (kind, detail):
                return position
        return None

    @property
    def rendered(self) -> str:
        return "\n".join(f"{kind}: {detail}" for kind, detail in self.events)


class _TimelineHandler(logging.Handler):
    def __init__(self, timeline: _Timeline) -> None:
        super().__init__(level=logging.NOTSET)
        self._timeline = timeline
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)
        rendered = record.getMessage()
        if record.exc_info is not None and record.exc_info[1] is not None:
            rendered = f"{rendered} || {record.exc_info[1]!r}"
        self._timeline.note("log", rendered)


@pytest.fixture()
def timeline() -> Iterator[_Timeline]:
    line = _Timeline()
    handler = _TimelineHandler(line)
    root = logging.getLogger()
    previous = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield line
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)


@pytest.fixture()
def log_records(timeline: _Timeline) -> list[logging.LogRecord]:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, _TimelineHandler):
            return handler.records
    pytest.fail("the timeline handler was not installed")


def _identifier_text(product_id: ProductId) -> str:
    """The bare value, so the assertion holds whichever of value or repr
    an implementation formats — the value is a substring of both."""
    return product_id.value


def _reports_naming(
    records: list[logging.LogRecord], product_id: ProductId
) -> list[logging.LogRecord]:
    identifier = _identifier_text(product_id)
    return [
        record
        for record in records
        if identifier in record.getMessage()
        or identifier in str(getattr(record, "args", ""))
    ]


def _carries_what_was_raised(record: logging.LogRecord, marker: str) -> bool:
    if marker in record.getMessage():
        return True
    info = record.exc_info
    return info is not None and info[1] is not None and marker in repr(info[1])


# ---------------------------------------------------------------------------
# Test doubles
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
        args, kwargs, lambda c: isinstance(c, str) and c in {p.value for p in WALK}
    )
    if text is not None:
        return ProductId(text)
    pytest.fail(
        "the cascade was called with neither a launch nor a product "
        f"identifier (args={args!r}, kwargs={kwargs!r}); correct `_product_of`"
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


class _FakeProgress:
    """Stands in for `progress_launch`, raising for whichever launches the
    test told it to fail on and noting every attempt on the timeline."""

    def __init__(self, timeline: _Timeline) -> None:
        self.timeline = timeline
        self.failures: dict[ProductId, Any] = {}
        self.seen: list[ProductId] = []

    def fail_for(self, product_id: ProductId, build: Any) -> None:
        self.failures[product_id] = build

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        product_id = _product_of(args, kwargs)
        self.seen.append(product_id)
        self.timeline.note("progress", str(product_id))
        build = self.failures.get(product_id)
        if build is not None:
            raise build()
        return None


class _FakeSuppression:
    """Inert: nothing in this file turns on the cool-off, and every launch
    here stands at an automatic gate, so no ask is ever owed."""

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
    def __init__(self) -> None:
        self.posted: list[Any] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> None:
        self.posted.append((args, kwargs))


class _FakeSession:
    """The store the walk shares, with only what the walk uses.

    `rollback()` is counted and optionally raises, which is what the
    *unrestorable store* scenario needs.
    """

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
# Reaching the pass — transcribed from test_gate_progression_pass.py
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


def _entry(module: ModuleType) -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"no pass entry point found on {module.__name__} under any of "
        f"{_ENTRY_NAMES} — correct this file's probe to the implemented name"
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
        self.require("launches", "playbooks", "progress", "session")

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

    def require(self, *roles: str) -> None:
        parameters = set(inspect.signature(_entry(self.module)).parameters)
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
                f"{names} — correct this file's probe rather than letting the "
                f"pass reach a real one. Its parameters are {sorted(parameters)}"
            )

    async def run(self) -> Any:
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
            "now": NOW,
        }
        accepted = set(inspect.signature(entry).parameters)
        return await entry(**{k: v for k, v in pool.items() if k in accepted})


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    timeline: _Timeline,
    *,
    session: _FakeSession | None = None,
) -> _Harness:
    module = _module()
    harness = _Harness(
        module=module,
        monkeypatch=monkeypatch,
        launches=_FakeLaunches(*(_launch_for(product) for product in WALK)),
        playbooks=_FakePlaybooks(_playbook()),
        progress=_FakeProgress(timeline),
        suppression=_FakeSuppression(),
        ask=_FakeAsk(),
        session=session or _FakeSession(),
    )
    harness.install()
    return harness


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# advanced
# ---------------------------------------------------------------------------


async def test_a_failing_launch_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
    timeline: _Timeline,
    log_records: list[logging.LogRecord],
) -> None:
    """Scenario: A failing launch does not stop the others.

    WHEN advancing one launch raises an error and other launches remain to
    be walked
    THEN the remaining launches are still attempted, the failure is
    reported naming that launch's product, and the run is reported as
    failed.

    The failing launch is the middle one, so it has both a launch before it
    and a launch after it; "as it happens" is asserted on the timeline
    rather than by a count, because a report summarised after the walk
    would satisfy a count while failing the requirement.
    """
    harness = _harness(monkeypatch, timeline)
    marker = "second-launch-fault"
    harness.progress.fail_for(SECOND, lambda: RuntimeError(marker))

    # SPECIFIED: the run is reported as failed.
    with pytest.raises(Exception) as raised:
        await harness.run()

    # SPECIFIED: the remaining launches are still attempted.
    assert harness.progress.seen == list(WALK), (
        f"the walk did not attempt every launch; it attempted {harness.progress.seen}"
    )
    # SPECIFIED: the failure is reported naming that launch's product...
    naming = _reports_naming(log_records, SECOND)
    assert naming, (
        f"no report named the product {SECOND} whose launch failed; the "
        f"timeline was:\n{timeline.rendered}"
    )
    # ...and carrying what was raised.
    assert any(_carries_what_was_raised(record, marker) for record in naming), (
        f"the report for {SECOND} carried nothing of what was raised "
        f"({marker!r}); the timeline was:\n{timeline.rendered}"
    )
    # SPECIFIED: "as it happens" — reported before the next launch is
    # attempted, rather than summarised after the walk.
    first_report = next(
        position
        for position, (kind, detail) in enumerate(timeline.events)
        if kind == "log" and _identifier_text(SECOND) in detail
    )
    third_attempt = timeline.index_of("progress", str(THIRD))
    assert third_attempt is not None
    assert first_report < third_attempt, (
        "the failure was not reported until after the walk had moved on; "
        f"the timeline was:\n{timeline.rendered}"
    )
    # SPECIFIED: the error that fails the run names every launch that
    # failed, by the identifier of the product each launch is for.
    message = str(raised.value)
    assert _identifier_text(SECOND) in message, (
        f"the run's error did not name the failed launch {SECOND}: {message!r}"
    )
    # DERIVED, from "naming every launch that failed": an error naming a
    # launch that succeeded would satisfy the clause while telling the
    # reader nothing. No scenario states it.
    assert _identifier_text(FIRST) not in message, (
        f"the run's error named {FIRST}, whose launch did not fail: {message!r}"
    )
    assert _identifier_text(THIRD) not in message


async def test_an_unrestorable_store_ends_the_walk(
    monkeypatch: pytest.MonkeyPatch,
    timeline: _Timeline,
) -> None:
    """Scenario: An unrestorable store ends the walk.

    WHEN a contained failure leaves the shared store in a state that cannot
    be restored
    THEN the walk ends rather than continuing against it, the run is
    reported as failed, and the error names the launches contained up to
    that point.

    "Cannot be restored" is a restore that itself raises — the shape
    `tasks.md` 4.6 names. The guard below establishes that a restore was
    attempted at all, so a pass restoring by some other means fails here
    with an instruction rather than leaving this test asserting nothing.
    """
    unusable = RuntimeError("the connection is gone; rollback failed")
    harness = _harness(monkeypatch, timeline, session=_FakeSession(unusable))
    harness.progress.fail_for(FIRST, lambda: RuntimeError("first-launch-fault"))

    with pytest.raises(Exception) as raised:
        await harness.run()

    # Guard: the restore really was attempted, so "the walk ended" is not
    # simply a walk that never recovered from anything.
    assert harness.session.rollbacks >= 1, (
        "no restore was attempted after the contained failure, so this test "
        "exercised nothing; correct this file's reading of how the pass "
        "restores the shared store (`tasks.md` 4.6)"
    )
    # SPECIFIED: the walk ends rather than continuing against it.
    assert harness.progress.seen == [FIRST], (
        "the walk carried on past a restore it could not perform, and "
        f"attempted {harness.progress.seen}"
    )
    message = str(raised.value)
    # SPECIFIED: the error names the launches contained up to that point.
    assert _identifier_text(FIRST) in message, (
        "the run's error did not name the launch contained before the "
        f"restore failed: {message!r}"
    )
    # SPECIFIED: "up to that point" — the launches never attempted are not
    # named.
    assert (
        _identifier_text(SECOND) not in message
        and _identifier_text(THIRD) not in message
    ), f"the run's error named a launch that was never attempted: {message!r}"


async def test_a_shutdown_stops_the_walk(
    monkeypatch: pytest.MonkeyPatch,
    timeline: _Timeline,
    log_records: list[logging.LogRecord],
) -> None:
    """Scenario: A shutdown stops the walk.

    WHEN the process running the pass is cancelled part-way through the
    walk
    THEN the walk stops rather than recording the cancellation against a
    product and continuing.

    `asyncio.CancelledError` is a `BaseException`, which is the distinction
    the requirement rests on: "Containment covers errors raised by the work
    itself. It SHALL NOT contain a cancellation or a shutdown". The launch
    before the cancellation fails first, so the test also establishes that
    a launch contained before it keeps its own report.
    """
    harness = _harness(monkeypatch, timeline)
    harness.progress.fail_for(FIRST, lambda: RuntimeError("first-launch-fault"))
    harness.progress.fail_for(SECOND, asyncio.CancelledError)

    # SPECIFIED: the cancellation is left to propagate.
    with pytest.raises(asyncio.CancelledError):
        await harness.run()

    # SPECIFIED: the walk stops rather than continuing.
    assert THIRD not in harness.progress.seen, (
        f"the walk continued past a cancellation, and attempted {harness.progress.seen}"
    )
    # SPECIFIED: rather than recording the cancellation against a product.
    assert not _reports_naming(log_records, SECOND), (
        "the cancellation was reported against the product whose launch was "
        "being walked when the process was stopped"
    )
    # SPECIFIED, from the same requirement read at the launch before it: a
    # launch contained before the cancellation keeps its own report.
    assert _reports_naming(log_records, FIRST), (
        "the launch contained before the cancellation lost its own report"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the catch is literally `except Exception` rather than a curated
#   list. `tasks.md` 4.5 decides it and no scenario states it; the tests
#   above provoke a bare `RuntimeError` and a `CancelledError` between
#   them, which is what the distinction actually turns on.
# - What `scheduled-jobs` records for a run whose process was cancelled.
#   Another capability's, and this delta states nothing about it.
# - Whether the restore runs after *every* contained failure or only after
#   a store fault. No scenario states it, and an integration-tier test
#   over a real session is what would establish it either way.
# ---------------------------------------------------------------------------
