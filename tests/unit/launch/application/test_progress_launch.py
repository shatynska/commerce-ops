"""What advances a launch: the cascade `progress_launch` runs under the lock.

Derived strictly from the delta spec of the OpenSpec change
`advance-gates-and-confirm-in-slack`:
`openspec/changes/advance-gates-and-confirm-in-slack/specs/launch-gate-progression/spec.md`

Covers, from the ADDED requirements:

- *A recurring pass advances every launch whose gate may open* — *An
  automatic gate opens once its conditions are satisfied*, *Consecutive
  open gates are crossed in one pass*, *A launch with an unsatisfied
  condition is left where it is, silently*, and *A launch is not advanced
  past the final gate*. Its fifth scenario, *Recording an outcome does
  not itself advance a launch*, is stated over `record_step_outcome` and
  is in
  `tests/unit/launch/application/test_recording_does_not_advance_a_launch.py`
  — deliberately its own file, because it is a regression guard expected
  to pass on its first run and would never run at all from a module whose
  import of `progress_launch` fails.
- *One launch's failure does not stop the other launches being advanced*
  — *A gate declining mid-cascade stops it without undoing what it
  crossed*, and the use-case half of *A cascade failing part-way leaves
  the launch where it started*: that the failure **propagates** out of
  the cascade rather than being committed. Its other half — that the
  launch is then found at the gate it started from — is a property of the
  transaction the driving adapter opens (`design.md` — Decision 6) and is
  in `tests/integration/launch/test_gate_progression_atomicity_live.py`.

Every other scenario of those requirements is stated over *the pass*, and
is in `tests/unit/launch/infrastructure/driving/`.

See `test-manifest.md` at the change root for the full accounting.

## Level

The use case over in-memory doubles. The subject of each scenario here is
what one launch's cascade does — which gates it crosses, what it leaves
in the journal, and whether it raises — and `progress_launch` is the
smallest unit that can observe any of them: the pass above it does not
know a cascade happened, and the `Launch` below it crosses one gate at a
time and cannot observe a cascade at all. It is the level
`tests/unit/launch/application/test_launch_journal_appends.py` already
holds for this module's other write-side rules.

## What is fixed, and what is INVENTED

Fixed by this change's artifacts:

- `progress_launch` in `launch/application/use_cases.py`, exported from
  `launch/application/__init__.py` (`tasks.md` 3.2, 3.6).
- That it takes the **product identifier** and reads the launch itself,
  never one the caller loaded before it (`tasks.md` 3.2).
- That it asks the launch whether the gate may open **before** commanding
  the advance, and commands nothing for a gate that read says may not
  open — so no `advance-refused` entry is journaled for it (delta R1;
  `design.md` — Decision 3).
- That it repeats while gates keep opening and stops at the final gate
  (`tasks.md` 3.2; `design.md` — Decision 4).
- That a gate declining to open is the cascade's **stop**, committing the
  crossings already made and the refusal `advance_gate` journaled, while
  any other exception unwinds (`tasks.md` 3.3; `design.md` — Decision 6).
- That an absent launch record is a no-op rather than a contained failure
  (`tasks.md` 3.2).
- The journal kinds `gate-opened` and `advance-refused`, which
  `tests/unit/launch/application/test_launch_journal_appends.py` records.

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- `progress_launch`'s exported name. `_use_case()` probes
  `commerce_ops.launch.application` and fails loudly rather than
  defaulting, so no test here can pass against something that is not the
  cascade.
- Its call shape — collaborators as keyword arguments, mirroring
  `advance_gate(launches=..., playbooks=..., stamp_steady_state=...,
  product_id=..., journal=...)` which this module's journal tests record.
  `_progress` is the single correction point. It supplies a superset and
  filters by the implemented signature, so a collaborator this change
  drops is not a failure here; what it *asserts* is that `product_id` is
  accepted, since `tasks.md` 3.2 fixes it.
- The shape of what the cascade returns. `tasks.md` 3.5 fixes that it
  reports whether the launch is now awaiting confirmation and on which
  gate; nothing fixes how. `_awaiting` reads several plausible shapes and
  is the correction point.
- How a *race* is provoked. A condition regressing between the cascade's
  read and its command cannot be produced from outside the use case —
  the read and the command are the same computation over the same launch
  (`design.md` — Decision 3), so no state exists in which one says yes
  and the other says no. The two tests that need one substitute the
  module-level `advance_gate` the cascade calls, found through
  `progress_launch.__module__`. Correction point: `_declining_advance` /
  `_failing_advance`. The substitute for the declining case journals the
  refusal itself, because the real `advance_gate` does (`launch-journal`,
  already implemented and covered) and what is under test here is that
  the cascade does not discard it.

What must survive any correction is what each test asserts: which gate
the launch ends at, how many crossings were journaled, whether an
`advance-refused` entry exists, and whether the cascade raised.

## Expected first-run state

`progress_launch` does not exist (`tasks.md` 3.2), so every test here is
expected to fail on an absent target — `_use_case()`'s loud failure. Per
`ai-toolkit:testing` that establishes absence only: the assertions below
have not been exercised.

Baseline recorded before these tests were written, at the worktree root,
commit `656f1c4`, clean tree: `uv run pytest tests/unit tests/agents` —
1472 passed, 0 failed. `uv run pytest tests/integration` — 3 passed, 112
skipped (no `DATABASE_URL` is configured here).
"""

from __future__ import annotations

import inspect
import sys
import uuid
from datetime import UTC, date, datetime
from types import ModuleType
from typing import Any, Final

import pytest

import commerce_ops.launch.application as launch_application
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
from commerce_ops.shared.domain.identity import MetricId, ProductId
from commerce_ops.shared.domain.lifecycle_stage import Posture
from tests.support.fixtures import product_id
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

pytestmark = pytest.mark.anyio

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

#: The journal kinds this change wires for the first time
#: (`proposal.md` — Impact), spelled as
#: `tests/unit/launch/application/test_launch_journal_appends.py` records.
KIND_GATE_OPENED: Final = "gate-opened"
KIND_ADVANCE_REFUSED: Final = "advance-refused"

PRODUCT_ID: Final = product_id()
ABSENT_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

LAUNCH_DATE: Final = date(2027, 9, 1)
NOW: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

APPROVER: Final = "Helen"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------


def _hold(gate: str) -> StepDefinition:
    """One blocking step per gate, satisfying the gate-holding floor.

    `automated` with a handler name, which is the shape
    `test_launch_journal_appends.py` uses for the same filler: it needs no
    assignee and so does not drag this file into the assignee
    preconditions, which are another capability's rules.
    """
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
    """The eight gates, one blocking step each, one metric condition.

    The metric condition sits on `stock-ready` because that is where
    `launch_playbook.py` authors one and where `design.md` — Risks says
    every launch will in fact come to rest. It is what makes *a gate
    blocked only by a metric condition* sayable at all, which is the case
    the launch report cannot answer (delta R1) — and so the case a pass
    judging readiness from the report would flood the journal at.
    """
    gates = tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    return LaunchPlaybook(
        version="progression-v1",
        gates=gates,
        steps=tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
    )


def _provenance() -> Provenance:
    return Provenance(
        source="automated",
        who="hold-filler",
        when=NOW,
        evidence="the blocking check reported green",
    )


def _approval(*, gate: str) -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver=APPROVER,
        when=NOW,
        posture=Posture.SCALE if gate == FINAL_GATE else None,
    )


def _satisfy_steps(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Every blocking step of the launch's current gate, and nothing else."""
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _satisfy_everything(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Everything the launch's current gate waits on — its blocking steps
    and, where the gate asks for one, its approval — driven on the
    aggregate so none of it reaches the journal the use case under test
    writes to."""
    _satisfy_steps(launch, playbook)
    if launch.current_gate in CONFIRMATION_GATES:
        launch.approve_gate(launch.current_gate, _approval(gate=launch.current_gate))


def _standing_at(gate: str, playbook: LaunchPlaybook) -> Launch:
    """A launch standing at `gate` with nothing that gate waits on done."""
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    while launch.current_gate != gate:
        _satisfy_everything(launch, playbook)
        launch.advance_gate(playbook)
    assert launch.current_gate == gate
    return launch


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeLaunches:
    """In-memory `LaunchStore`, counting reads so that "reads the launch
    itself under the lock" is observable."""

    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}
        self.reads: list[ProductId] = []
        self.saves: list[ProductId] = []

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        self.reads.append(product_id)
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self.saves.append(launch.product_id)
        self._launches[launch.product_id] = launch

    async def list_active(self) -> tuple[Launch, ...]:
        return tuple(
            launch
            for launch in self._launches.values()
            if launch.current_gate != FINAL_GATE
        )

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    def stored(self, product_id: ProductId = PRODUCT_ID) -> Launch:
        return self._launches[product_id]


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str = "") -> LaunchPlaybook:
        return self.playbook


class _FakeJournal:
    """In-memory `LaunchJournal`. Append-only, so this list only grows."""

    def __init__(self) -> None:
        self.appended: list[Any] = []
        self.rollbacks = 0

    async def append(self, entry: Any) -> None:
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(reversed(self.appended))

    async def rollback(self) -> None:
        self.rollbacks += 1

    def kinds(self) -> list[Any]:
        return [getattr(entry, "kind", None) for entry in self.appended]

    def count(self, kind: str) -> int:
        return self.kinds().count(kind)


class _FakeStamper:
    """The graduation's catalog stamp. Recorded, never expected here."""

    def __init__(self) -> None:
        self.calls: list[tuple[ProductId, object, str]] = []

    async def __call__(
        self, product_id: ProductId, stage: object, *, confirmed_by: str
    ) -> None:
        self.calls.append((product_id, stage, confirmed_by))


class _Collaborators:
    def __init__(self, launch: Launch | None, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook
        self.playbooks = _FakePlaybooks(playbook)
        self.launches = _FakeLaunches(*((launch,) if launch is not None else ()))
        self.journal = _FakeJournal()
        self.stamper = _FakeStamper()


def _setup(gate: str, *, satisfy: bool = False) -> _Collaborators:
    playbook = _playbook()
    launch = _standing_at(gate, playbook)
    if satisfy:
        _satisfy_steps(launch, playbook)
    return _Collaborators(launch, playbook)


# ---------------------------------------------------------------------------
# The use case, reached through one correction point
# ---------------------------------------------------------------------------

_USE_CASE_NAMES: Final = ("progress_launch", "progress", "advance_launch")


def _use_case() -> Any:
    for name in _USE_CASE_NAMES:
        found = getattr(launch_application, name, None)
        if callable(found):
            return found
    pytest.fail(
        "`commerce_ops.launch.application` exports no cascade use case under "
        f"any of {_USE_CASE_NAMES} — correct this file's probe to the "
        "implemented name (`tasks.md` 3.2, 3.6)"
    )


def _use_case_module() -> ModuleType:
    """The module the cascade is defined in, so its `advance_gate` can be
    substituted. Found through the use case rather than by module path."""
    return sys.modules[_use_case().__module__]


async def _progress(collaborators: _Collaborators, **overrides: Any) -> Any:
    """INVENTED call shape — the single correction point."""
    entry = _use_case()
    supplied: dict[str, Any] = {
        "launches": collaborators.launches,
        "playbooks": collaborators.playbooks,
        "playbook": collaborators.playbook,
        "stamp_steady_state": collaborators.stamper,
        "journal": collaborators.journal,
        "product_id": PRODUCT_ID,
        "now": NOW,
    }
    supplied.update(overrides)
    accepted = set(inspect.signature(entry).parameters)
    # SPECIFIED by `tasks.md` 3.2: it takes the product identifier, not a
    # launch the caller loaded. A cascade that took a `Launch` could not
    # re-read it under the lock, which is the whole point of the argument.
    assert "product_id" in accepted, (
        "the cascade does not accept `product_id`; `tasks.md` 3.2 fixes that "
        "it takes the product identifier and reads the launch itself under "
        f"the lock. Its parameters are {sorted(accepted)}"
    )
    assert accepted & {"playbook", "playbooks"}, (
        "the cascade takes no playbook; `tasks.md` 3.4 fixes that the "
        "readiness the pass determined once is passed in. Its parameters "
        f"are {sorted(accepted)}"
    )
    return await entry(**{k: v for k, v in supplied.items() if k in accepted})


# ---------------------------------------------------------------------------
# Reading what the cascade reports back (INVENTED shape)
# ---------------------------------------------------------------------------


def _awaiting(returned: Any) -> tuple[bool, Any]:
    """Whether the cascade reported the launch awaiting confirmation, and
    on which gate. `tasks.md` 3.5 fixes the substance, not the shape."""
    candidates: list[Any] = [returned]
    if isinstance(returned, (tuple, list)):
        candidates.extend(returned)
    for candidate in candidates:
        for flag in ("awaiting_confirmation", "awaiting", "is_awaiting_confirmation"):
            value = getattr(candidate, flag, None)
            if isinstance(value, bool):
                gate = None
                for name in ("awaiting_gate", "gate_id", "gate", "current_gate"):
                    held = getattr(candidate, name, None)
                    if isinstance(held, str):
                        gate = held
                        break
                return value, gate
    return False, None


# ---------------------------------------------------------------------------
# Substituting the advance, for the two race scenarios only
# ---------------------------------------------------------------------------


def _install_advance(monkeypatch: pytest.MonkeyPatch, replacement: Any) -> None:
    module = _use_case_module()
    assert hasattr(module, "advance_gate"), (
        f"{module.__name__} holds no module-level `advance_gate` for the "
        "cascade to call, so this file cannot provoke a gate declining "
        "between the cascade's read and its command; correct "
        "`_install_advance` to the implemented seam"
    )
    monkeypatch.setattr(module, "advance_gate", replacement)


class _Entry:
    """A journal entry, modelled to the two facts asserted here: its kind
    and the launch it is for."""

    def __init__(self, kind: str, product_id: ProductId) -> None:
        self.kind = kind
        self.product_id = product_id
        self.subject_id = "the gate"
        self.details = {"unsatisfied": ("a blocking condition regressed",)}


def _a_real_gate_blocked_error() -> GateBlockedError:
    """A genuine `GateBlockedError`, raised by the domain rather than
    constructed here.

    `GateBlockedError`'s constructor signature is fixed by no artifact of
    this change and carries a `blocked` payload
    (`test_launch_journal_appends.py` reads `.blocked.unsatisfied`), so
    building one by hand would pin a shape this change does not own. A
    launch standing at an unsatisfied gate produces the real thing.
    """
    playbook = _playbook()
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    try:
        launch.advance_gate(playbook)
    except GateBlockedError as error:
        return error
    pytest.fail(
        "a launch at an unsatisfied gate did not refuse to advance, so this "
        "file cannot obtain a real `GateBlockedError` to script a decline with"
    )


def _find(args: tuple[Any, ...], kwargs: dict[str, Any], predicate: Any) -> Any:
    for candidate in (*args, *kwargs.values()):
        if predicate(candidate):
            return candidate
    return None


class _ScriptedAdvance:
    """`advance_gate`, crossing `crossings` gates and then doing whatever
    the test scripted for the next call.

    Each crossing is performed on the real launch through the real domain
    operation, so "the crossing stands" means here what it means in
    production: the launch's own gate moved and the store was told. Its
    collaborators are *found* among the call's arguments rather than read
    off a parameter name, so a differently shaped call is not silently
    mis-driven.
    """

    def __init__(self, *, crossings: int, then: BaseException) -> None:
        self.crossings = crossings
        self.then = then
        self.calls = 0

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        launches = _find(args, kwargs, lambda c: hasattr(c, "get_by_product_id"))
        journal = _find(args, kwargs, lambda c: hasattr(c, "append"))
        product_id = _find(args, kwargs, lambda c: isinstance(c, ProductId))
        playbook = _find(args, kwargs, lambda c: isinstance(c, LaunchPlaybook))
        if playbook is None:
            # CORRECTED probe: `advance_gate` takes the `Playbooks` *port*,
            # not a loaded definition, so the cascade wraps whatever it was
            # handed. Resolve through the port rather than naming any one
            # implementation of it.
            playbooks = _find(
                args,
                kwargs,
                lambda c: (
                    callable(getattr(c, "get", None)) and not isinstance(c, (dict, str))
                ),
            )
            if playbooks is not None:
                resolved = playbooks.get("live")
                playbook = resolved if isinstance(resolved, LaunchPlaybook) else None
        assert launches is not None and product_id is not None, (
            "the cascade called `advance_gate` with neither a launch store "
            f"nor a product identifier among its arguments: {args!r} {kwargs!r}"
        )
        assert playbook is not None, (
            "the cascade called `advance_gate` with no playbook among its "
            f"arguments: {args!r} {kwargs!r}"
        )
        if self.calls > self.crossings:
            if journal is not None and isinstance(self.then, GateBlockedError):
                await journal.append(_Entry(KIND_ADVANCE_REFUSED, product_id))
            raise self.then
        launch = await launches.get_by_product_id(product_id)
        events = launch.advance_gate(playbook)
        await launches.save(launch)
        if journal is not None:
            await journal.append(_Entry(KIND_GATE_OPENED, product_id))
        return events


# ---------------------------------------------------------------------------
# Requirement: A recurring pass advances every launch whose gate may open
# ---------------------------------------------------------------------------


async def test_an_automatic_gate_opens_once_its_conditions_are_satisfied() -> None:
    """Scenario: An automatic gate opens once its conditions are satisfied.

    WHEN the pass runs against a launch whose current gate opens
    automatically and every blocking condition attached to it is satisfied
    THEN the gate opens and the launch's current gate becomes the next gate
    in the sequence.

    `listable` is the gate: it opens automatically and, unlike
    `stock-ready` after it, authors no metric condition — so the launch
    comes to rest one gate on, which is what "becomes the next gate" (and
    not "runs to the end") asserts.
    """
    collaborators = _setup("listable", satisfy=True)

    await _progress(collaborators)

    # SPECIFIED: the gate opens and the current gate becomes the next one.
    assert collaborators.launches.stored().current_gate == "stock-ready", (
        "the automatic gate did not open; the launch stands at "
        f"{collaborators.launches.stored().current_gate}"
    )
    # SPECIFIED (R1, "every gate crossed ... emitted its own GateOpened"):
    # exactly one crossing, journaled.
    assert collaborators.journal.count(KIND_GATE_OPENED) == 1, (
        f"expected one crossing, journal holds {collaborators.journal.kinds()}"
    )


async def test_consecutive_open_gates_are_crossed_in_one_pass() -> None:
    """Scenario: Consecutive open gates are crossed in one pass.

    WHEN the pass runs against a launch for which the conditions of its
    current gate and of the gate after it are both satisfied and neither
    requires confirmation
    THEN both gates open on that pass and the launch's current gate becomes
    the gate after them.

    `listable` then `stock-ready`, both automatic; `stock-ready`'s metric
    condition is attested here so that the second gate really is satisfied
    rather than merely unblocked on its steps. The launch then stops at
    `live`, whose blocking step is untouched — which is what makes "the
    gate after them" distinguishable from "the end of the sequence".
    """
    collaborators = _setup("listable", satisfy=True)
    launch = collaborators.launches.stored()
    # `stock-ready`'s own blocking step, satisfied ahead of the cascade:
    # the scenario is stated over two gates whose conditions are already
    # met when the pass reaches the launch.
    launch.record_step_outcome(
        collaborators.playbook,
        step_id="hold.stock-ready",
        outcome=Satisfied,
        provenance=_provenance(),
    )

    await _progress(collaborators)

    # SPECIFIED: the current gate becomes the gate after both of them.
    assert collaborators.launches.stored().current_gate == "live", (
        "the cascade did not cross both open gates in one pass; the launch "
        f"stands at {collaborators.launches.stored().current_gate}"
    )
    # SPECIFIED: *both* gates opened — two crossings, not one advance that
    # skipped a gate. `launch-instance` forbids a skipped gate, and a
    # cascade is the only reason two entries appear on one pass.
    assert collaborators.journal.count(KIND_GATE_OPENED) == 2, (
        "the cascade did not journal one crossing per gate; the journal "
        f"holds {collaborators.journal.kinds()}"
    )
    # SPECIFIED (R1): the cascade stopped rather than commanding an advance
    # it expected to be refused.
    assert collaborators.journal.count(KIND_ADVANCE_REFUSED) == 0


async def test_a_launch_with_an_unsatisfied_condition_is_left_where_it_is() -> None:
    """Scenario: A launch with an unsatisfied condition is left where it is,
    silently.

    WHEN the pass runs against a launch whose current gate has an
    unsatisfied blocking condition
    THEN the launch's current gate is unchanged, no advance is commanded,
    no refused-advance entry is journaled, and the pass is not failed by it.
    """
    collaborators = _setup("listable")

    # SPECIFIED: the pass is not failed by it — returning is the assertion.
    await _progress(collaborators)

    # SPECIFIED: the current gate is unchanged.
    assert collaborators.launches.stored().current_gate == "listable"
    # SPECIFIED: no advance is commanded, and no refused-advance entry is
    # journaled. Both halves: an implementation that commanded and caught
    # the refusal would still have journaled it.
    assert collaborators.journal.appended == [], (
        "a launch the cascade could not advance left entries in the journal "
        f"kept for members to read: {collaborators.journal.kinds()}"
    )
    # Guard: the cascade really did read the launch, so the assertions
    # above cannot hold because nothing ran at all.
    assert collaborators.launches.reads, "the cascade never read the launch"


async def test_a_launch_is_not_advanced_past_the_final_gate() -> None:
    """Scenario: A launch is not advanced past the final gate.

    WHEN the pass runs while a launch stands at the final gate of the
    sequence
    THEN no advance is commanded for that launch.

    Driven with the final gate's conditions *all* satisfied — its blocking
    step, and the approving approval naming a posture — so that the reason
    nothing is commanded is the stop at the final gate and not an
    unsatisfied condition, which the scenario above already covers.
    """
    playbook = _playbook()
    launch = _standing_at(FINAL_GATE, playbook)
    _satisfy_everything(launch, playbook)
    collaborators = _Collaborators(launch, playbook)

    await _progress(collaborators)

    # SPECIFIED: no advance is commanded.
    assert collaborators.launches.stored().current_gate == FINAL_GATE
    assert collaborators.journal.appended == [], (
        "an advance was commanded for a launch standing at the final gate; "
        f"the journal holds {collaborators.journal.kinds()}"
    )
    # SPECIFIED, from the same clause read at its consequence: the catalog
    # steady-state stamp is what an opened final gate produces, and this
    # change obtains none (delta R4; `design.md` — Decision 8).
    assert collaborators.stamper.calls == [], (
        "the cascade stamped the catalog for a launch at the final gate, "
        "which is behaviour this change explicitly does not carry"
    )


async def test_an_absent_launch_record_is_a_no_op() -> None:
    """`tasks.md` 3.2: an absent launch record is "a no-op for that product
    rather than a contained failure, since a launch may be deleted by hand
    between the walk's read and the lock".

    DERIVED with respect to the delta, which states no scenario for it.
    Recorded as derived in `test-manifest.md`.
    """
    collaborators = _Collaborators(None, _playbook())

    await _progress(collaborators, product_id=ABSENT_PRODUCT_ID)

    assert collaborators.journal.appended == []
    assert collaborators.launches.saves == []


async def test_a_gate_awaiting_only_confirmation_is_reported_back() -> None:
    """`tasks.md` 3.5: the cascade reports, alongside the events, "whether
    the launch is now awaiting confirmation and on which gate, so a caller
    can decide whether an ask is owed without re-reading the launch".

    DERIVED with respect to the delta, which fixes when an ask is owed
    (R4) but not how the pass learns it. Recorded as derived in
    `test-manifest.md`; the correction point for the shape is `_awaiting`.

    The half that *is* specified is asserted too: a confirmation gate whose
    approval is outstanding is a gate whose conditions are unsatisfied, so
    R1 forbids a command and forbids a journal entry for it.
    """
    collaborators = _setup("commit", satisfy=True)

    returned = await _progress(collaborators)

    # SPECIFIED (R1): no command, no entry.
    assert collaborators.launches.stored().current_gate == "commit"
    assert collaborators.journal.appended == []
    # DERIVED (`tasks.md` 3.5): the caller is told, and told which gate.
    awaiting, gate = _awaiting(returned)
    assert awaiting, (
        "the cascade did not report the launch as awaiting confirmation, so "
        "the pass cannot decide whether an ask is owed without re-reading "
        f"the launch; it returned {returned!r}"
    )
    assert gate == "commit", (
        f"the cascade reported the wrong gate as awaiting confirmation: {gate!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: One launch's failure does not stop the other launches being
# advanced
# ---------------------------------------------------------------------------


async def test_a_gate_declining_mid_cascade_stops_it_without_undoing_the_crossing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A gate declining mid-cascade stops it without undoing what
    it crossed.

    WHEN a launch crosses one gate and the next declines to open, a
    condition having stopped being satisfied since the pass read it
    THEN the crossing already made stands, the refusal is journaled with
    the conditions that blocked it, and the run is not failed.

    The race cannot be produced from outside the use case (see the module
    docstring), so `advance_gate` is substituted: it crosses once for real
    and then declines, journaling the refusal as the real one does. What is
    under test is what the *cascade* does with that — commit and stop, not
    unwind and not re-raise.
    """
    collaborators = _setup("listable", satisfy=True)
    launch = collaborators.launches.stored()
    launch.record_step_outcome(
        collaborators.playbook,
        step_id="hold.stock-ready",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    advance = _ScriptedAdvance(crossings=1, then=_a_real_gate_blocked_error())
    _install_advance(monkeypatch, advance)

    # SPECIFIED: the run is not failed by it — the cascade returns.
    await _progress(collaborators)

    # SPECIFIED: the crossing already made stands.
    assert collaborators.launches.stored().current_gate == "stock-ready", (
        "the crossing made before the refusal was undone; the launch stands "
        f"at {collaborators.launches.stored().current_gate}"
    )
    assert collaborators.journal.count(KIND_GATE_OPENED) == 1
    # SPECIFIED: the refusal is journaled — and, crucially, still there.
    # `design.md` — Decision 3 rests its whole argument on this entry being
    # the one record no later pass can reconstruct.
    assert collaborators.journal.count(KIND_ADVANCE_REFUSED) == 1, (
        "the refusal the declining gate journaled was discarded by the "
        f"cascade; the journal holds {collaborators.journal.kinds()}"
    )
    assert collaborators.journal.rollbacks == 0, (
        "the cascade rolled the journal back over a gate declining to open, "
        "which is its stopping condition and not a failure"
    )
    # Guard: the decline really was reached, so "the crossing stands" is
    # not simply a cascade that stopped after one gate on its own.
    assert advance.calls == 2, (
        f"the cascade did not reach the declining gate ({advance.calls} calls)"
    )


async def test_a_cascade_failing_part_way_propagates_rather_than_committing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A cascade failing part-way leaves the launch where it
    started — its use-case half.

    WHEN a launch crosses one gate and the attempt at the next raises
    THEN the launch stands at the gate it was at when the pass reached it,
    the crossing already made having been undone.

    The undoing is the driving adapter's transaction (`design.md` —
    Decision 6), and is asserted against a real one in
    `tests/integration/launch/test_gate_progression_atomicity_live.py`.
    What is assertable here — and what that undoing depends on — is that a
    failure which is *not* a gate declining leaves the cascade rather than
    being caught and committed alongside the crossings. A cascade that
    swallowed it would commit the partial advance the scenario forbids,
    and no transaction could undo what was never unwound.
    """
    collaborators = _setup("listable", satisfy=True)
    # CORRECTED setup: `_satisfy_steps` satisfies only the *current* gate,
    # so without this the cascade reads `stock-ready` as unsatisfied, stops
    # before commanding, and the scenario's "attempt at the next" never
    # happens. The cascade asks before it commands (`design.md` — Decision
    # 3), so a second attempt has to be earned by a second ready gate —
    # the same preparation `test_consecutive_open_gates_are_crossed_in_one_pass`
    # already makes.
    collaborators.launches.stored().record_step_outcome(
        collaborators.playbook,
        step_id="hold.stock-ready",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    failure = RuntimeError("the store went away mid-cascade")
    advance = _ScriptedAdvance(crossings=1, then=failure)
    _install_advance(monkeypatch, advance)

    # SPECIFIED: it is a failure, not a stop — so it reaches the caller,
    # whose transaction is what undoes the crossing.
    with pytest.raises(RuntimeError) as raised:
        await _progress(collaborators)

    assert raised.value is failure, (
        "the cascade replaced the failure with one of its own, so the pass "
        "above it cannot report what was raised"
    )
    # Guard: one gate really was crossed before the failure, so this test
    # exercises a cascade failing *part-way* rather than at its first step.
    assert advance.calls == 2


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That the cascade terminates without a counter (`design.md` —
#   Decision 4). It is a property of the gate sequence being finite and
#   strictly forward, which `launch-instance` already fixes and this
#   change does not touch; a test could only re-assert the sequence.
# - Which lock the cascade runs under. `design.md` — Decision 6 places the
#   lock in the two driving adapters and explicitly not in the use case,
#   so there is nothing here to observe; the mutual exclusion it buys is
#   `tests/integration/launch/test_gate_progression_atomicity_live.py`'s.
# - The `GateOpened` events the cascade returns. `launch-instance` fixes
#   them and `tests/unit/launch/domain/test_launch_gate_advance.py`
#   already covers them; this change states nothing new about them.
# ---------------------------------------------------------------------------
