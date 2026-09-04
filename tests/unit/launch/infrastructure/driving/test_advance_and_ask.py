"""The cascade the webhook triggers decides and acts like the pass's own.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-from-clickup-webhook`:
`openspec/changes/advance-gates-from-clickup-webhook/specs/launch-gate-progression/spec.md`

Covers the second half of the MODIFIED requirement *A recurring pass
advances every launch whose gate may open*'s new scenario:

    #### Scenario: A ClickUp webhook delivery may trigger an
    advance-and-ask cascade for the launch it completes
    - **THEN** the same advance-and-ask cascade the pass runs for that
      launch MAY be triggered immediately ... **and every rule this
      requirement and the requirements below state about how a gate may
      open, how a decision is asked for, and how often, apply to that
      cascade exactly as they apply to the pass's own**

That clause is what this file is for. The requirement's amended text says
the same twice over — *"A launch the webhook's trigger reaches is still
judged, advanced and journaled by the same rules this requirement states
throughout — read-before-command, one gate at a time, silent on an
unsatisfied condition"* — so each test below names the rule it is
carrying over and where that rule is already asserted for the pass, in
`tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py`.

The other half of the scenario — that a webhook delivery triggers this at
all — is stated over the route and is in
`tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The trigger callable over in-memory doubles, exactly the level
`test_gate_progression_pass.py` holds for the walk. Each rule below is
observable in what the trigger did to its collaborators — which launch it
progressed, whether it posted, what the cool-off store holds afterwards,
whether it raised — and nothing smaller sees any of it, because the
cascade does not know an ask exists and the ask adapter does not know a
previous pass happened.

Deliberately **not** driven through the route. The route's job is to
trigger this; this file's job is what it then does. Driving both through
one HTTP delivery would make every failure here ambiguous between the two.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `advance_and_ask(product_id, *, now=None) -> None` on
  `gate_progression_job.py`, exported from its `__all__` (`tasks.md`
  1.1, 1.3; `design.md` — Decision 1).
- That it reads the served playbook in its own session, stands down for
  that one product on `PlaybookNotReadyError`, then runs `_advance_one`,
  `_awaiting_gate` and — outside the lock — `_ask_if_owed` (`tasks.md`
  1.1).
- That its whole body is wrapped in a broad catch, so no failure inside
  it ever reaches a caller (`tasks.md` 1.2; `design.md` — Decision 3).
- The 24-hour ask cool-off and the final-gate exclusion, which this
  change reuses unchanged (`design.md` — Decision 4, naming the archived
  Decisions 4, 5 and 6 as still in force).

INVENTED, and recorded in the manifest as unresolved project questions:

- The trigger's name. `_ENTRY_NAMES` probes and `_entry` fails loudly.
- How it is called — positionally or by keyword, with or without `now`.
  `_invoke` reads the implemented signature rather than assuming one.
- The collaborator names, the suppression store's read/write spellings
  and the shape the cascade hands back (`_Progressed`) — all transcribed
  from `test_gate_progression_pass.py`, which is the correction point for
  each and records the provenance of each.

What must survive any correction is what each test asserts: which launch
was progressed, how many asks were posted and for which gate, what the
cool-off store holds afterwards, and whether the trigger raised.

## Expected first-run state

`gate_progression_job.py` carries no `advance_and_ask` (`tasks.md` 1.1),
so every test here is expected to fail on an **absent target** — `_entry`'s
loud failure. Per `ai-toolkit:testing` that establishes absence only: none
of the assertions below has been exercised. Do not resolve it by adding
the function; that is `tasks.md` section 1's to add.

Baseline recorded before these tests were written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `96303a7`: `uv run pytest tests/unit tests/agents` — 1727 passed,
0 failed. `uv run pytest tests/integration` — 3 passed, 124 skipped (no
`DATABASE_URL` is configured here, so that tier did not in fact run).
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

#: The launch the webhook's delivery completed, and a bystander that must
#: be left entirely alone.
COMPLETED: Final = ProductId(str(uuid.uuid4()))
BYSTANDER: Final = ProductId(str(uuid.uuid4()))

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

#: The names the single-launch trigger may carry. Correction point.
_ENTRY_NAMES: Final = (
    "advance_and_ask",
    "advance_and_ask_for",
    "advance_one_and_ask",
    "advance_launch_and_ask",
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


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures — transcribed from `test_gate_progression_pass.py`
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
        source="clickup",
        who="183",
        when=NOW,
        evidence="the mapped ClickUp task was closed",
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
    steps satisfied, which is the state a webhook delivery leaves behind —
    a confirmation gate there is *awaiting only confirmation* in exactly
    the sense `launch-instance` defines."""
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
    transcribed from `test_gate_progression_pass.py`."""
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
        lambda c: isinstance(c, str) and c in {COMPLETED.value, BYSTANDER.value},
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
    def __init__(self, playbook: LaunchPlaybook, refusal: Exception | None) -> None:
        self.playbook = playbook
        self.refusal = refusal
        self.reads = 0

    async def get(self, version: str = "") -> LaunchPlaybook:
        self.reads += 1
        if self.refusal is not None:
            raise self.refusal
        return self.playbook

    async def __call__(self, *args: Any, **kwargs: Any) -> LaunchPlaybook:
        return await self.get()


@dataclass
class _Progressed:
    """What the cascade hands back (INVENTED shape — transcribed from
    `test_gate_progression_pass.py`, which records the provenance).

    `crossed` defaults empty: this file exercises the ask mechanism, not
    `trigger-clickup-projection-on-launch-events`'s eager convergence
    (`test_gate_progression_pass_eager_convergence.py`'s job), so the fake
    never reports a crossing and `advance_and_ask`'s own
    `if progressed.crossed:` branch is simply never taken here.
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
    """Stands in for `progress_launch`."""

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
    """In-memory stand-in for the ask cool-off store."""

    def __init__(self, now: datetime = NOW) -> None:
        self.rows: dict[tuple[ProductId, str], _SuppressionRow] = {}
        self.reads: list[tuple[ProductId, str]] = []
        self.writes: list[_SuppressionRow] = []
        self.now = now

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
        return moment - row.delivered_at < _cool_off()

    suppressed = is_suppressed

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
            "*and* gate"
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
    def __init__(self) -> None:
        self.rollbacks = 0
        self.commits = 0

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def commit(self) -> None:
        self.commits += 1

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        return None


# ---------------------------------------------------------------------------
# Reaching the trigger, through one correction point
# ---------------------------------------------------------------------------


def _module() -> ModuleType:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:  # pragma: no cover — the module ships today
        pytest.fail(f"{MODULE_PATH} does not exist ({error})")


def _entry(module: ModuleType) -> Any:
    for name in _ENTRY_NAMES:
        found = getattr(module, name, None)
        if callable(found):
            return found
    pytest.fail(
        f"{module.__name__} exposes no single-launch advance-and-ask trigger "
        f"under any of {_ENTRY_NAMES}; `tasks.md` 1.1 adds it. This is the "
        "absent-target state, not a defect in this file — do not add the "
        "function to make this pass."
    )


def _entry_name(module: ModuleType) -> str:
    for name in _ENTRY_NAMES:
        if callable(getattr(module, name, None)):
            return name
    return _ENTRY_NAMES[0]


def _cool_off() -> timedelta:
    """The ask cool-off, read off the module rather than transcribed.

    `design.md` — Decision 4 keeps the archived Decision 5's 24 hours; the
    constant is the module's, so a change to it must not silently make
    this file assert a window the system no longer uses.
    """
    module = importlib.import_module(MODULE_PATH)
    for name in ("ASK_COOL_OFF", "COOL_OFF", "ASK_COOL_OFF_WINDOW"):
        found = getattr(module, name, None)
        if isinstance(found, timedelta):
            return found
    return timedelta(hours=24)


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
        """Fail loudly where a collaborator a test depends on could be
        placed neither as a module attribute nor as a parameter, so no
        test here runs green against an unsubstituted real one."""
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
                f"the trigger exposes no {role} collaborator under any of "
                f"{names}, as a module attribute or as a parameter — correct "
                "this file's probe, rather than letting it reach a real one. "
                f"Its parameters are {sorted(parameters)}"
            )

    async def run(self, product_id: ProductId, *, now: datetime = NOW) -> Any:
        """Invoke the trigger for one launch, under whichever signature it
        carries: the product identifier is the one thing `tasks.md` 1.1
        fixes, and `now` is passed only where it is accepted."""
        entry = _entry(self.module)
        signature = inspect.signature(entry)
        parameters = signature.parameters
        kwargs: dict[str, Any] = {}
        if "now" in parameters:
            kwargs["now"] = now
        for name in ("product_id", "product", "launch_id"):
            if (
                name in parameters
                and parameters[name].kind is not inspect.Parameter.POSITIONAL_ONLY
            ):
                kwargs[name] = product_id
                return await entry(**kwargs)
        return await entry(product_id, **kwargs)


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *launches: Launch,
    refusal: Exception | None = None,
    failing_ask: bool = False,
    suppression: _FakeSuppression | None = None,
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
        session=_FakeSession(),
    )
    harness.install()
    return harness


def _logged(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(record.getMessage() for record in caplog.records)


def _warnings(caplog: pytest.LogCaptureFixture) -> str:
    return " ".join(
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING
    )


# ---------------------------------------------------------------------------
# "the same advance-and-ask cascade the pass runs for that launch"
# ---------------------------------------------------------------------------


async def test_the_trigger_runs_the_cascade_for_the_launch_it_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A ClickUp webhook delivery may trigger an advance-and-ask
    cascade for the launch it completes — "the **same** advance-and-ask
    cascade the pass runs for that launch".

    Sameness is asserted where it is observable: the cascade the pass uses
    (`progress_launch`, the collaborator
    `test_gate_progression_pass.py` substitutes under the same name) is
    what the trigger reaches, for the product it was handed and no other.
    A trigger that reimplemented advancement beside it would leave that
    collaborator untouched and fail here.
    """
    harness = _harness(monkeypatch, _launch_at(COMPLETED, "listable"))
    harness.require("launches", "playbooks", "progress")

    await harness.run(COMPLETED)

    # SPECIFIED: the cascade runs, for that launch.
    assert harness.progress.seen == [COMPLETED], (
        "the trigger did not run the pass's own cascade for the launch it "
        f"was given: {harness.progress.seen}"
    )


async def test_the_trigger_leaves_every_other_launch_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED by the same clause, read for what it excludes: the
    cascade is run "for **that** launch", the one the delivery completes.

    The bystander is deliberately reachable — it is in the same store, and
    `list_active` would hand it over — so a trigger that walked every
    active launch rather than the one it was named would fail here rather
    than passing for want of a second launch to touch.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(COMPLETED, "listable"),
        _launch_at(BYSTANDER, "listable"),
    )
    harness.require("launches", "playbooks", "progress")

    await harness.run(COMPLETED)

    # SPECIFIED: one launch, not a walk.
    assert harness.progress.seen == [COMPLETED], (
        "the trigger reached a launch other than the one the delivery "
        f"completed: {harness.progress.seen}"
    )
    assert harness.ask.gates_for(BYSTANDER) == [], (
        f"the trigger posted an ask for a bystander launch: {harness.ask.posted}"
    )


# ---------------------------------------------------------------------------
# "every rule ... about how a decision is asked for, and how often, apply
# to that cascade exactly as they apply to the pass's own"
# ---------------------------------------------------------------------------


async def test_a_gate_awaiting_only_confirmation_is_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule carried over: *A gate awaiting only confirmation is asked
    about in Slack* — asserted for the pass in
    `test_gate_progression_pass.py`, and required of this cascade by the
    new scenario's "apply to that cascade exactly as they apply to the
    pass's own".

    This is the whole point of the change: the ask arrives on the webhook's
    latency rather than the pass's, so a trigger that advanced but never
    asked would deliver none of what `proposal.md` says it is for.
    """
    harness = _harness(monkeypatch, _launch_at(COMPLETED, "commit"))
    harness.require("launches", "playbooks", "progress", "suppression", "ask")

    await harness.run(COMPLETED)

    # SPECIFIED: the ask is posted, for the gate awaiting confirmation.
    assert harness.ask.gates_for(COMPLETED) == ["commit"], (
        "the trigger posted no ask for a gate awaiting only confirmation: "
        f"{harness.ask.posted}"
    )
    # SPECIFIED (*A gate is asked about at most once a day*): the delivery
    # is recorded, or the pass ten minutes later asks a second time — which
    # is the double-post `proposal.md` says the cool-off prevents.
    assert [(row.product_id, row.gate_id) for row in harness.suppression.writes] == [
        (COMPLETED, "commit")
    ], (
        "the ask was posted without recording its delivery in the cool-off "
        f"store, so the next pass would ask again: {harness.suppression.writes}"
    )


async def test_a_gate_asked_about_within_the_cool_off_is_not_asked_about_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule carried over: *A gate is asked about at most once a day*.

    `proposal.md` leans on this rule by name — the webhook-triggered ask
    and the periodic-pass ask "for the same gate cannot double-post; the
    cool-off already makes repeats within a day a no-op" — so a trigger
    that bypassed the cool-off would break the argument the change rests
    on rather than merely being noisy.

    The seeded row is an hour old, well inside whichever window the module
    itself carries (`_cool_off`).
    """
    suppression = _FakeSuppression()
    suppression.seed(COMPLETED, "commit", age=timedelta(hours=1), reason="delivery")
    harness = _harness(
        monkeypatch, _launch_at(COMPLETED, "commit"), suppression=suppression
    )
    harness.require("launches", "playbooks", "progress", "suppression", "ask")

    await harness.run(COMPLETED)

    # SPECIFIED: nothing is posted inside the cool-off.
    assert harness.ask.posted == [], (
        "the trigger asked about a gate already asked about within the "
        f"cool-off: {harness.ask.posted}"
    )
    # Guard: the store really was consulted, so the silence above is the
    # cool-off's doing and not a trigger that never got as far as asking.
    assert harness.suppression.reads != [], (
        "the cool-off store was never read, so this test cannot tell a "
        "respected cool-off from a trigger that never reached the ask"
    )


async def test_a_gate_asked_about_more_than_a_day_ago_is_asked_about_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same rule: *An unanswered gate is asked about
    again the next day*.

    Its companion above is satisfiable by a trigger that never asks at
    all; this one is not, so the pair together establish that the cool-off
    is being applied rather than the ask being absent.
    """
    suppression = _FakeSuppression()
    suppression.seed(
        COMPLETED, "commit", age=_cool_off() + timedelta(minutes=5), reason="delivery"
    )
    harness = _harness(
        monkeypatch, _launch_at(COMPLETED, "commit"), suppression=suppression
    )
    harness.require("launches", "playbooks", "progress", "suppression", "ask")

    await harness.run(COMPLETED)

    # SPECIFIED: a cool-off that has expired no longer suppresses.
    assert harness.ask.gates_for(COMPLETED) == ["commit"], (
        "the trigger stayed silent although the previous ask is older than "
        f"the cool-off: {harness.ask.posted}"
    )


async def test_the_final_gate_is_not_asked_about(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule carried over: *The final gate is not asked about* (and,
    from the same requirement, *A launch is not advanced past the final
    gate*).

    Reached here through the trigger rather than the walk: the pass gets
    the exclusion partly for free from which launches `list_active` hands
    it, and a single-launch trigger is handed a product identifier by an
    HTTP delivery instead — so the exclusion has to hold in the cascade
    itself, exactly as `tasks.md` 5.8 of the archived change already
    required of the ask.
    """
    harness = _harness(monkeypatch, _launch_at(COMPLETED, FINAL_GATE))
    harness.require("launches", "playbooks", "progress", "ask")

    await harness.run(COMPLETED)

    # SPECIFIED: the final gate is not asked about.
    assert harness.ask.posted == [], (
        f"the trigger asked for confirmation of the final gate: {harness.ask.posted}"
    )


async def test_a_gate_with_an_unsatisfied_condition_is_left_alone_and_silently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The rule carried over: *A gate with unsatisfied conditions is not
    asked about*, and *A launch with an unsatisfied condition is left where
    it is, silently* — the requirement's own words for the trigger are
    "silent on an unsatisfied condition".

    The launch stands at a confirmation gate whose blocking step is *not*
    satisfied, so it is not awaiting only confirmation, and a webhook
    delivery for some other step of the same launch would land it in
    exactly this state.
    """
    harness = _harness(
        monkeypatch, _launch_at(COMPLETED, "commit", satisfy_steps=False)
    )
    harness.require("launches", "playbooks", "progress", "ask")

    # SPECIFIED: not a failure — returning normally is part of the
    # assertion, so there is no `pytest.raises` here.
    await harness.run(COMPLETED)

    # SPECIFIED: no ask.
    assert harness.ask.posted == [], (
        "the trigger asked about a gate with an unsatisfied blocking "
        f"condition: {harness.ask.posted}"
    )


async def test_an_unready_playbook_stands_the_trigger_down_for_that_launch(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The rule carried over: *The pass stands down while the playbook
    cannot hold a launch* (`tasks.md` 1.1: `PlaybookNotReadyError` "is
    caught here and stands the trigger down for this one product —
    logged, not raised"; `design.md` — Risks: "the periodic pass is still
    the thing that recovers once the playbook is ready").

    Asserted three ways, because a stand-down that raised would still
    satisfy "no advance, no ask" — the response has already been sent by
    then, so an exception here goes nowhere a member will read it.
    """
    harness = _harness(
        monkeypatch,
        _launch_at(COMPLETED, "listable"),
        refusal=_build_not_ready(_unready_playbook()),
    )
    harness.require("launches", "playbooks", "progress", "ask")

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED: logged, not raised.
        await harness.run(COMPLETED)

    # SPECIFIED: no launch is advanced.
    assert harness.progress.seen == [], (
        f"a launch was advanced during a stand-down: {harness.progress.seen}"
    )
    # SPECIFIED: no ask is posted.
    assert harness.ask.posted == [], (
        f"an ask was posted during a stand-down: {harness.ask.posted}"
    )
    # SPECIFIED: the stand-down is logged.
    assert _logged(caplog) != "", (
        "the stand-down left no log entry at all, so a launch the webhook "
        "silently did nothing for is unattributable"
    )


# ---------------------------------------------------------------------------
# "no failure inside it ever propagates to a caller" — `tasks.md` 1.2
# ---------------------------------------------------------------------------


async def test_a_failing_cascade_never_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """SPECIFIED-BY-TASKS (`tasks.md` 1.2; `design.md` — Decision 3): the
    whole body is wrapped in a broad catch "that logs a warning naming the
    product and returns, so no failure inside it ever propagates to a
    caller".

    No `#### Scenario:` states it — it is this change's own containment
    decision rather than a rule carried over — and it is asserted because
    the caller is a Starlette background task with no client left to
    report to, which is the failure mode `design.md` names.
    """
    harness = _harness(monkeypatch, _launch_at(COMPLETED, "listable"))
    harness.require("launches", "playbooks", "progress")
    harness.progress.fail_for(
        COMPLETED, lambda: RuntimeError("simulated cascade failure")
    )

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED-BY-TASKS: it returns rather than raising.
        await harness.run(COMPLETED)

    # Premise: the failure really happened.
    assert harness.progress.seen == [COMPLETED], (
        "the failing cascade was never reached, so this test exercised nothing"
    )
    # SPECIFIED-BY-TASKS: a warning naming the product.
    assert COMPLETED.value in _warnings(caplog), (
        "the contained failure logged no warning naming the product, so it is "
        f"unattributable: {_warnings(caplog)!r}"
    )


async def test_a_failing_ask_delivery_never_reaches_the_caller(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The rule carried over: *An undelivered ask is reported, retried,
    and does not fail the run* — which `tasks.md` 1.2 makes absolute for
    this trigger, since it has no run to fail.

    Kept separate from the test above because the two failures arrive
    through different collaborators and an implementation can contain one
    without containing the other: the archived design already absorbs an
    ask failure inside `_ask_if_owed`, so only the advance half depends on
    the new broad catch.
    """
    harness = _harness(monkeypatch, _launch_at(COMPLETED, "commit"), failing_ask=True)
    harness.require("launches", "playbooks", "progress", "suppression", "ask")

    with caplog.at_level(logging.DEBUG):
        # SPECIFIED: it returns rather than raising.
        await harness.run(COMPLETED)

    # Premise: the delivery really was attempted and really did fail.
    assert harness.ask.posted != [], (
        "the failing ask was never attempted, so this test exercised nothing"
    )
    # SPECIFIED (*An undelivered ask ... leaves the gate eligible*): the
    # failed delivery is not recorded as one, or the cool-off would
    # suppress the retry the next pass owes.
    assert harness.suppression.writes == [], (
        "a failed ask delivery was recorded in the cool-off store, so the "
        f"gate is suppressed although nobody was asked: {harness.suppression.writes}"
    )


# ---------------------------------------------------------------------------
# Convention guard — DERIVED from `tasks.md` 1.3, not a `#### Scenario:`
# ---------------------------------------------------------------------------


def test_the_trigger_is_exported_from_the_jobs_public_surface() -> None:
    """`tasks.md` 1.3: "Export `advance_and_ask` from
    `gate_progression_job.py`'s `__all__`".

    Asserted because the webhook reaches it by import (`design.md` —
    Decision 1), and this module's `__all__` is what the repository treats
    as the surface a sibling adapter may import from.
    """
    module = _module()
    name = _entry_name(module)
    assert callable(getattr(module, name, None)), (
        f"{module.__name__} exposes no trigger under any of {_ENTRY_NAMES}; "
        "`tasks.md` 1.1 adds it. This is the absent-target state."
    )
    exported = getattr(module, "__all__", None)
    assert exported is not None, f"{module.__name__} declares no `__all__`"
    assert name in exported, (
        f"{name!r} is not named in {module.__name__}'s `__all__` ({sorted(exported)})"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the periodic pass's own behaviour is unchanged (`tasks.md` 1.4).
#   It is already covered by `test_gate_progression_pass.py` and
#   `test_gate_progression_containment.py`, which this change must leave
#   green; re-asserting it here would duplicate rather than add.
# - That the trigger reads the served playbook in its own session rather
#   than being handed one (`tasks.md` 1.1, `design.md` — Decision 1). The
#   session provider is substituted here, so a fresh read and a shared one
#   are indistinguishable; what depends on it — that the background task
#   holds nothing belonging to the request — is asserted at the route in
#   `test_clickup_webhook_triggers_the_advance_cascade.py`.
# - That the advance is serialized against the pass and against a button
#   press by the advisory lock. Mutual exclusion is a claim about two
#   concurrent callers against a real Postgres lock and holds nothing in a
#   single-process test with no database; it is at the integration tier in
#   `tests/integration/launch/test_webhook_advance_atomicity_live.py`.
# - Which gates the cascade crosses, and that it crosses them one at a
#   time. That is `progress_launch`'s own requirement, asserted in
#   `tests/unit/launch/application/test_progress_launch.py`; the cascade is
#   substituted here precisely so these tests fail for reasons they state.
# ---------------------------------------------------------------------------
