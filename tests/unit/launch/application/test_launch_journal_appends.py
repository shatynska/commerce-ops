"""Tests for what the launch journal appends, and what each entry carries.

Derived from the delta spec:
openspec/changes/add-launch-journal/specs/launch-journal/spec.md

Covers, of that spec's ADDED requirements:

- *Every accepted launch command appends exactly one journal entry* — all
  ten scenarios.
- *A refused advance is journaled with the conditions that blocked it* —
  all three scenarios.
- *An entry carries the labels the occurrence concerned, captured when it
  happened* — all four scenarios.
- *Entries are appended, never replaced or deleted* — both scenarios.
- *A launch's journal is retained for the life of the launch record* —
  scenario *The journal outlives the state it records*. Its sibling,
  *Removing the launch record removes its journal*, is a database cascade
  and is driven in
  `tests/integration/launch/test_launch_journal_live.py`.

The remaining requirements are in two sibling files:
`test_launch_journal_read.py` (the read, and that an entry stores facts
rather than prose) and `test_launch_journal_containment.py` (a failed
append).

## Level

The application layer, fast mocked unit tier. Every scenario here is
stated over *what a command appends*, and the append site is the use
case (`design.md` Decision 2). Nothing below the use case can observe
"one entry was appended for this command"; nothing above it observes
anything more.

Setup that is not the command under test drives the **aggregate**
directly rather than the use cases, so that each test's journal holds
exactly the entries the command under test produced.

## The interface under test does not exist yet, and its shape is INVENTED

At the time of writing no journal exists, so every test here is expected
to fail on an absent target (a `TypeError` for the unexpected `journal`
argument). Per `ai-toolkit:testing`, that failure establishes only
absence.

Fixed by this change's artifacts, and asserted as such:

- The six commands take a **required keyword-only** `journal`
  (`design.md` Decision 1, `tasks.md` 4.1).
- The `kind` vocabulary — `launch-started`, `step-outcome-recorded`,
  `metric-attested`, `gate-approval-recorded`, `gate-opened`,
  `launch-graduated`, `launch-date-moved`, `advance-refused`
  (`design.md` Decision 4, `tasks.md` 2.2).
- The entry's fact fields: `product_id`, `occurred_at`, `kind`, `actor`,
  `source`, `subject_id`, `subject_label`, `details` (`design.md`
  Decision 4's table, `tasks.md` 3.1).
- Which identifier is the *subject* of each kind (`design.md` Decision 4,
  "The subject, per kind").
- That a refused advance stores `GateBlocked.unsatisfied` as a list of
  the domain's own condition strings, in `details` (`design.md`
  Decision 7).

INVENTED, each with a correction point named here:

- The port's methods are **async** (`append`, `read`, `rollback` —
  `tasks.md` 3.2), on `LaunchStore`'s precedent. Correction point:
  `FakeJournal`.
- The **key names inside `details`** are fixed nowhere, so nothing here
  asserts one. Where a scenario says an entry *names* something, the
  test asks whether that thing appears among the facts the entry carries
  (`_names`), comparing on alphanumerics only so that a spelling choice
  — `InProgress` / `in-progress` / `in_progress` — is not silently
  required. Correction point: `_facts` / `_names`.
- That the appended entry's `product_id` may be a `ProductId` or its
  string value. Correction point: `_is_product`.

Correcting any of those is a fixture correction (failure state 3 in
`ai-toolkit:testing`). What must survive unweakened is what each test
asserts: how many entries a command appends, of what kind, against which
launch, and which facts each entry names.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    advance_gate,
    approve_gate,
    move_launch_date,
    record_step_outcome,
    start_launch,
)
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    Hazard,
    InProgress,
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
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

# SPECIFIED (design.md Decision 4 / tasks.md 2.2): the kind vocabulary.
KIND_LAUNCH_STARTED: Final = "launch-started"
KIND_STEP_OUTCOME_RECORDED: Final = "step-outcome-recorded"
KIND_METRIC_ATTESTED: Final = "metric-attested"
KIND_GATE_APPROVAL_RECORDED: Final = "gate-approval-recorded"
KIND_GATE_OPENED: Final = "gate-opened"
KIND_LAUNCH_GRADUATED: Final = "launch-graduated"
KIND_LAUNCH_DATE_MOVED: Final = "launch-date-moved"
KIND_ADVANCE_REFUSED: Final = "advance-refused"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
OTHER_PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

RECORDED_AT: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
LATER_AT: Final = datetime(2027, 5, 4, 9, 15, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 5, 5, 11, 0, tzinfo=UTC)
ATTESTED_AT: Final = datetime(2027, 5, 6, 8, 45, tzinfo=UTC)

APPROVER: Final = "Helen"
RECORDER: Final = "Dana"
ATTESTER: Final = "Mira"

LAUNCH_DATE: Final = date(2027, 9, 1)
MOVED_DATE: Final = date(2027, 10, 15)

STOCK_METRIC: Final = MetricId("units-fulfillable")
STOCK_THRESHOLD: Final = "60-80 fulfillable units"

TRACKED_STEP: Final = "listing.title-conforms"
TRACKED_STEP_NAME: Final = "Write the listing title to the conformance rules"
TRACKED_STEP_RENAMED: Final = "Write a listing title that conforms"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Reading an entry without inventing a `details` key
# ---------------------------------------------------------------------------


def _normalised(value: object) -> str:
    """Alphanumerics only, lowercased — so that a vocabulary spelling the
    change never fixed (`InProgress` vs `in-progress`) is not demanded."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())


def _flatten(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [text for held in value.values() for text in _flatten(held)]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [text for held in value for text in _flatten(held)]
    return [str(value)]


def _facts(entry: object) -> list[str]:
    """Every fact the entry carries, `kind` excluded — `kind` is asserted
    on its own, and folding it in here would let a kind string satisfy a
    "names X" assertion about something else."""
    values: list[str] = []
    for name in ("subject_id", "subject_label", "actor", "source"):
        held = getattr(entry, name, None)
        if held is not None:
            values.append(str(held))
    values.extend(_flatten(getattr(entry, "details", None)))
    return values


def _names(entry: object, token: object) -> bool:
    needle = _normalised(token)
    return any(needle in _normalised(fact) for fact in _facts(entry))


def _assert_names(entry: object, token: object, why: str) -> None:
    assert _names(entry, token), (
        f"the entry does not name {token!r} ({why}); "
        f"the facts it carries are {_facts(entry)!r}"
    )


def _is_product(value: object, product_id: ProductId) -> bool:
    return value == product_id or value == product_id.value


def _only(journal: FakeJournal) -> Any:
    """The single appended entry — the *exactly one* half of R1."""
    assert len(journal.appended) == 1, (
        f"expected exactly one appended entry, got {len(journal.appended)}: "
        f"{[getattr(entry, 'kind', entry) for entry in journal.appended]}"
    )
    return journal.appended[0]


def _kinds(journal: FakeJournal) -> list[str | None]:
    return [getattr(entry, "kind", None) for entry in journal.appended]


# ---------------------------------------------------------------------------
# Playbook and launch fixtures
# ---------------------------------------------------------------------------


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": TRACKED_STEP,
        "name": TRACKED_STEP_NAME,
        "gate": "listable",
        "discipline": _any_discipline(),
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


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor forbids a
    coherent playbook with unheld gates."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        handler="fixture.holding_check",
    )


def _playbook(
    *,
    tracked_name: str = TRACKED_STEP_NAME,
    tracked_status: StepStatus = StepStatus.ACTIVE,
) -> LaunchPlaybook:
    """The eight gates, a metric condition on `stock-ready`, a blocking
    filler per gate, and one non-blocking tracked step whose name and
    lifecycle the label scenarios move."""
    gates = tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )
    steps = (
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER),
        _step(name=tracked_name, status=tracked_status),
    )
    return LaunchPlaybook(version="journal-v1", gates=gates, steps=steps)


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": RECORDER,
        "when": RECORDED_AT,
        "evidence": "ClickUp task closed with its checklist complete",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _started(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _satisfy_gate(launch: Launch, playbook: LaunchPlaybook) -> None:
    """Everything the current gate waits on, driven on the aggregate so
    that none of it reaches the journal under test."""
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking:
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(source="automated", who="hold-filler"),
            )
    if launch.current_gate in CONFIRMATION_GATES:
        posture = Posture.SCALE if launch.current_gate == "graduated" else None
        launch.approve_gate(launch.current_gate, _approval(posture=posture))


def _walked_to(playbook: LaunchPlaybook, gate: str) -> Launch:
    """A launch standing at `gate` with everything that gate waits on
    already satisfied, so the next advance opens it."""
    launch = _started(playbook)
    while launch.current_gate != gate:
        _satisfy_gate(launch, playbook)
        launch.advance_gate(playbook)
    _satisfy_gate(launch, playbook)
    return launch


# ---------------------------------------------------------------------------
# Collaborators
# ---------------------------------------------------------------------------


class FakeLaunchStore:
    """In-memory `LaunchStore`, recording save order in a shared log."""

    def __init__(self, *launches: Launch, log: list[str] | None = None) -> None:
        self._launches = {launch.product_id: launch for launch in launches}
        self._log = log if log is not None else []

    async def get_by_product_id(self, product_id: ProductId) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._log.append("save")
        self._launches[launch.product_id] = launch

    async def list_all(self) -> tuple[Launch, ...]:
        return tuple(self._launches.values())


class FakePlaybooks:
    """Playbook port. Mutable, so a rename or a retirement after an append
    can be modelled by swapping what the port serves."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self.playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self.playbook


class FakeJournal:
    """In-memory `LaunchJournal`, keeping every entry exactly as handed to
    the port — the journal is append-only, so this list only ever grows."""

    def __init__(self, log: list[str] | None = None) -> None:
        self.appended: list[Any] = []
        self.rollbacks = 0
        self._log = log if log is not None else []

    async def append(self, entry: Any) -> None:
        self._log.append("append")
        self.appended.append(entry)

    async def read(self, product_id: ProductId) -> tuple[Any, ...]:
        return tuple(
            entry
            for entry in reversed(self.appended)
            if _is_product(getattr(entry, "product_id", None), product_id)
        )

    async def rollback(self) -> None:
        self.rollbacks += 1


class FakeStamper:
    """The graduation's catalog stamp; records its calls."""

    def __init__(self, log: list[str] | None = None) -> None:
        self.calls: list[tuple[ProductId, object, str]] = []
        self._log = log if log is not None else []

    async def __call__(
        self, product_id: ProductId, stage: object, *, confirmed_by: str
    ) -> None:
        self._log.append("stamp")
        self.calls.append((product_id, stage, confirmed_by))


# ---------------------------------------------------------------------------
# R1: Every accepted launch command appends exactly one journal entry
# ---------------------------------------------------------------------------


async def test_a_started_launch_is_journaled() -> None:
    """Scenario: A started launch is journaled.

    WHEN a launch is started
    THEN one entry is appended against that launch, naming the start.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await start_launch(
        FakeLaunchStore(),
        playbook,
        product_id=PRODUCT_ID,
        launch_date=LAUNCH_DATE,
        journal=journal,
    )

    entry = _only(journal)
    # SPECIFIED: against that launch.
    assert _is_product(entry.product_id, PRODUCT_ID)
    # SPECIFIED: naming the start. The kind string is fixed by design.md
    # Decision 4.
    assert entry.kind == KIND_LAUNCH_STARTED


async def test_a_recorded_step_outcome_is_journaled() -> None:
    """Scenario: A recorded step outcome is journaled.

    WHEN a terminal outcome is recorded for a step
    THEN one entry is appended naming the step and the outcome recorded.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )

    entry = _only(journal)
    assert entry.kind == KIND_STEP_OUTCOME_RECORDED
    assert _is_product(entry.product_id, PRODUCT_ID)
    # SPECIFIED: naming the step. The step is this kind's subject
    # (design.md Decision 4).
    assert entry.subject_id == TRACKED_STEP
    # SPECIFIED: naming the outcome recorded.
    _assert_names(entry, "Satisfied", "the outcome recorded")


async def test_a_non_terminal_step_outcome_is_journaled_too() -> None:
    """Scenario: A non-terminal step outcome is journaled too.

    WHEN an outcome that produces no event — `InProgress` — is recorded
    for a step
    THEN one entry is appended naming the step and that outcome.

    The requirement states this in its own words: coverage does not
    depend on the occurrence having produced an event.
    """
    playbook = _playbook()
    journal = FakeJournal()

    events = await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=InProgress,
        provenance=_provenance(),
        journal=journal,
    )

    # SPECIFIED by the scenario's own wording: this outcome produces no
    # event, which is the premise the entry must not depend on.
    assert events == ()
    entry = _only(journal)
    assert entry.kind == KIND_STEP_OUTCOME_RECORDED
    assert entry.subject_id == TRACKED_STEP
    _assert_names(entry, "InProgress", "the non-terminal outcome recorded")


async def test_an_outcome_recorded_from_any_source_is_journaled_alike() -> None:
    """Scenario: An outcome recorded from any source is journaled alike.

    WHEN a step outcome is recorded with source `clickup`, and another
    with source `automated`
    THEN an entry is appended for each, naming the source that recorded
    it.
    """
    playbook = _playbook()
    launches = FakeLaunchStore(_started(playbook))
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()

    for source in ("clickup", "automated"):
        await record_step_outcome(
            launches,
            playbooks,
            product_id=PRODUCT_ID,
            step_id=TRACKED_STEP,
            outcome=InProgress,
            provenance=_provenance(source=source),
            journal=journal,
        )

    # SPECIFIED: an entry for each.
    assert _kinds(journal) == [
        KIND_STEP_OUTCOME_RECORDED,
        KIND_STEP_OUTCOME_RECORDED,
    ]
    # SPECIFIED: each naming the source that recorded it. `source` is a
    # column of its own (design.md Decision 4).
    first, second = journal.appended
    assert first.source == "clickup"
    assert second.source == "automated"


async def test_a_recorded_approval_is_journaled() -> None:
    """Scenario: A recorded approval is journaled.

    WHEN an approving decision is recorded on a gate
    THEN one entry is appended naming the gate, the decision and the
    approver.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await approve_gate(
        FakeLaunchStore(_started(playbook)),
        product_id=PRODUCT_ID,
        gate_id="commit",
        approval=_approval(),
        journal=journal,
    )

    entry = _only(journal)
    assert entry.kind == KIND_GATE_APPROVAL_RECORDED
    # SPECIFIED: naming the gate — the gate is this kind's subject, and
    # its identifier is the whole of its label (R3).
    assert entry.subject_id == "commit"
    # SPECIFIED: naming the approver. The approver is the actor
    # (design.md Decision 4, "Which kinds carry an actor").
    assert entry.actor == APPROVER
    # SPECIFIED: naming the decision.
    _assert_names(entry, "approving", "the decision recorded")


async def test_a_rejecting_approval_is_journaled_too() -> None:
    """Scenario: A rejecting approval is journaled too.

    WHEN a rejecting decision is recorded on a gate
    THEN one entry is appended naming that the decision was rejecting.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await approve_gate(
        FakeLaunchStore(_started(playbook)),
        product_id=PRODUCT_ID,
        gate_id="commit",
        approval=_approval(decision=ApprovalDecision.REJECTING),
        journal=journal,
    )

    entry = _only(journal)
    assert entry.kind == KIND_GATE_APPROVAL_RECORDED
    # SPECIFIED: naming that the decision was rejecting — the whole point
    # of the scenario is that a rejection is journaled as a rejection,
    # not merely journaled.
    _assert_names(entry, "rejecting", "the decision recorded")
    assert not _names(entry, "approving"), (
        "a rejecting decision must not be journaled as approving; "
        f"the facts the entry carries are {_facts(entry)!r}"
    )


async def test_an_opened_gate_is_journaled() -> None:
    """Scenario: An opened gate is journaled.

    WHEN an advance opens a gate short of `graduated`
    THEN one entry is appended naming the gate that opened.
    """
    playbook = _playbook()
    journal = FakeJournal()
    launch = _walked_to(playbook, "commit")

    await advance_gate(
        launches=FakeLaunchStore(launch),
        playbooks=FakePlaybooks(playbook),
        stamp_steady_state=FakeStamper(),
        product_id=PRODUCT_ID,
        journal=journal,
    )

    entry = _only(journal)
    assert entry.kind == KIND_GATE_OPENED
    # SPECIFIED: the gate that opened — `commit`, the gate the launch
    # stood at, not the one it moved on to.
    assert entry.subject_id == "commit"


async def test_a_graduation_is_journaled_as_a_graduation() -> None:
    """Scenario: A graduation is journaled as a graduation.

    WHEN an advance opens `graduated`
    THEN one entry is appended naming the graduation, the posture the
    approver chose and the approver.
    """
    playbook = _playbook()
    journal = FakeJournal()
    launch = _walked_to(playbook, "graduated")

    await advance_gate(
        launches=FakeLaunchStore(launch),
        playbooks=FakePlaybooks(playbook),
        stamp_steady_state=FakeStamper(),
        product_id=PRODUCT_ID,
        journal=journal,
    )

    # SPECIFIED, and the requirement states it twice: *one* entry, and it
    # names the graduation rather than only the gate that opened.
    entry = _only(journal)
    assert entry.kind == KIND_LAUNCH_GRADUATED
    # SPECIFIED: naming the posture the approver chose.
    _assert_names(entry, Posture.SCALE.value, "the posture the approver chose")
    # SPECIFIED: naming the approver.
    assert entry.actor == APPROVER


async def test_a_moved_launch_date_is_journaled() -> None:
    """Scenario: A moved launch date is journaled.

    WHEN a launch date is moved
    THEN one entry is appended naming the previous date and the new one.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await move_launch_date(
        FakeLaunchStore(_started(playbook)),
        product_id=PRODUCT_ID,
        new_date=MOVED_DATE,
        journal=journal,
    )

    entry = _only(journal)
    assert entry.kind == KIND_LAUNCH_DATE_MOVED
    # SPECIFIED: naming the previous date and the new one — both, so that
    # a reader learns what the move was, not only where it landed.
    _assert_names(entry, LAUNCH_DATE.isoformat(), "the previous launch date")
    _assert_names(entry, MOVED_DATE.isoformat(), "the new launch date")


# ---------------------------------------------------------------------------
# R2: A refused advance is journaled with the conditions that blocked it
# ---------------------------------------------------------------------------


def _condition_list(entry: object) -> list[str]:
    """The one list-of-strings the entry carries in `details` — the shape
    design.md Decision 7 fixes, without fixing the key it sits under."""
    details = getattr(entry, "details", None)
    assert isinstance(details, Mapping), (
        f"a refused advance's entry must carry its conditions in a details "
        f"mapping; it carries {details!r}"
    )
    candidates = [
        list(value)
        for value in details.values()
        if isinstance(value, (list, tuple))
        and value
        and all(isinstance(item, str) for item in value)
    ]
    assert len(candidates) == 1, (
        f"expected exactly one list of condition names among the entry's "
        f"details; found {len(candidates)} in {details!r}"
    )
    return candidates[0]


async def test_a_refused_advance_is_journaled_with_its_unsatisfied_conditions() -> None:
    """Scenario: A refused advance is journaled with its unsatisfied
    conditions.

    WHEN an advance is attempted on a gate holding two unsatisfied
    conditions
    THEN one entry is appended naming that gate and both conditions.
    """
    playbook = _playbook()
    journal = FakeJournal()
    # `commit` is a confirmation gate held by a blocking filler: with
    # neither done, exactly two conditions are unsatisfied.
    launch = _started(playbook)

    with pytest.raises(GateBlockedError) as caught:
        await advance_gate(
            launches=FakeLaunchStore(launch),
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=FakeStamper(),
            product_id=PRODUCT_ID,
            journal=journal,
        )

    unsatisfied = caught.value.blocked.unsatisfied
    assert len(unsatisfied) == 2, (
        f"fixture premise: the gate must hold two unsatisfied conditions; "
        f"it holds {unsatisfied!r}"
    )
    entry = _only(journal)
    assert entry.kind == KIND_ADVANCE_REFUSED
    # SPECIFIED: naming that gate.
    assert entry.subject_id == "commit"
    # SPECIFIED: and both conditions — every condition that was
    # unsatisfied at that moment, not the first of them.
    assert _condition_list(entry) == list(unsatisfied)


async def test_a_refused_advance_still_fails() -> None:
    """Scenario: A refused advance still fails.

    WHEN an advance is refused and its entry is appended
    THEN the command fails with the same rejection, naming the same
    unsatisfied conditions, and the launch's current gate is unchanged.
    """
    playbook = _playbook()
    journal = FakeJournal()
    launch = _started(playbook)
    # What the refusal carries with no journal in the picture — the
    # comparison the requirement's "the same rejection" is against.
    with pytest.raises(GateBlockedError) as unjournaled:
        launch.advance_gate(playbook)

    with pytest.raises(GateBlockedError) as caught:
        await advance_gate(
            launches=FakeLaunchStore(launch),
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=FakeStamper(),
            product_id=PRODUCT_ID,
            journal=journal,
        )

    # SPECIFIED: the same rejection, naming the same unsatisfied
    # conditions.
    assert caught.value.blocked.gate_id == unjournaled.value.blocked.gate_id
    assert caught.value.blocked.unsatisfied == unjournaled.value.blocked.unsatisfied
    assert str(caught.value) == str(unjournaled.value)
    # SPECIFIED: the launch's current gate is unchanged.
    assert launch.current_gate == "commit"
    # The entry was appended all the same — the scenario's premise.
    assert _kinds(journal) == [KIND_ADVANCE_REFUSED]


async def test_a_condition_satisfied_later_leaves_the_entry_standing() -> None:
    """Scenario: A condition satisfied later leaves the entry standing.

    WHEN a condition that blocked an earlier advance is satisfied and the
    gate later opens
    THEN the entry recording the refusal still names that condition as
    having blocked the advance.

    This is the requirement's whole reason for existing: unsatisfied
    conditions are recomputed from current state, so once satisfied they
    are unrecoverable, and the entry is the only record that they ever
    blocked an advance.
    """
    playbook = _playbook()
    journal = FakeJournal()
    launch = _started(playbook)
    launches = FakeLaunchStore(launch)
    playbooks = FakePlaybooks(playbook)

    with pytest.raises(GateBlockedError):
        await advance_gate(
            launches=launches,
            playbooks=playbooks,
            stamp_steady_state=FakeStamper(),
            product_id=PRODUCT_ID,
            journal=journal,
        )
    blocked_by = _condition_list(_only(journal))

    _satisfy_gate(launch, playbook)
    await advance_gate(
        launches=launches,
        playbooks=playbooks,
        stamp_steady_state=FakeStamper(),
        product_id=PRODUCT_ID,
        journal=journal,
    )

    # The gate did later open — the scenario's premise.
    assert launch.current_gate == "order"
    # SPECIFIED: the refusal entry still names the condition that blocked
    # the advance, unchanged by the later satisfaction.
    refusals = [
        entry for entry in journal.appended if entry.kind == KIND_ADVANCE_REFUSED
    ]
    assert len(refusals) == 1
    assert _condition_list(refusals[0]) == blocked_by
    assert any("hold.commit" in condition for condition in blocked_by), (
        f"fixture premise: the blocking step was among the conditions; "
        f"they were {blocked_by!r}"
    )


# ---------------------------------------------------------------------------
# R3: An entry carries the labels the occurrence concerned
# ---------------------------------------------------------------------------


async def test_an_entry_names_the_step_as_well_as_identifying_it() -> None:
    """Scenario: An entry names the step as well as identifying it.

    WHEN a step outcome is recorded
    THEN the entry carries both the step's identifier and the name the
    served playbook gave that step.
    """
    playbook = _playbook()
    journal = FakeJournal()

    await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        FakePlaybooks(playbook),
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )

    entry = _only(journal)
    # SPECIFIED: both — the identifier and the label, separately.
    assert entry.subject_id == TRACKED_STEP
    assert entry.subject_label == TRACKED_STEP_NAME


async def test_a_step_renamed_later_does_not_change_an_appended_entry() -> None:
    """Scenario: A step renamed later does not change an appended entry.

    WHEN a step is renamed after an entry naming it was appended
    THEN the entry still carries the name the step bore when the entry
    was appended.
    """
    playbook = _playbook()
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()

    await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )
    # The playbook moves on: the same step, a different name.
    playbooks.playbook = _playbook(tracked_name=TRACKED_STEP_RENAMED)

    entry = _only(journal)
    # SPECIFIED: the name it bore when the entry was appended — captured
    # at the append and never re-resolved at read time.
    assert entry.subject_label == TRACKED_STEP_NAME
    assert entry.subject_label != TRACKED_STEP_RENAMED


async def test_a_step_retired_later_still_reads_by_name() -> None:
    """Scenario: A step retired later still reads by name.

    WHEN a step is retired after an entry naming it was appended
    THEN the entry still names that step, rather than reporting only its
    identifier.
    """
    playbook = _playbook()
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()

    await record_step_outcome(
        FakeLaunchStore(_started(playbook)),
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )
    retired = _playbook(tracked_status=StepStatus.RETIRED)
    playbooks.playbook = retired

    # The served playbook really has moved on — the scenario's premise.
    assert TRACKED_STEP not in {step.identifier for step in retired.served_steps}
    entry = _only(journal)
    # SPECIFIED: still names that step, rather than only identifying it.
    assert entry.subject_label == TRACKED_STEP_NAME


async def test_a_refused_advances_conditions_are_stored_as_the_domain_names_them() -> (
    None
):
    """Scenario: A refused advance's conditions are stored as the domain
    names them.

    WHEN an advance is refused because a blocking step is unresolved, and
    its entry is inspected as stored
    THEN the entry carries that condition as the domain's own condition
    name, which identifies the step by identifier, and carries it as one
    item of a list rather than as a sentence.

    This is the requirement's one stated exception to labels-not-
    identifiers (design.md Decision 7). The test therefore asserts the
    exception as written — an identifier, in a list — rather than
    demanding the step's name here.
    """
    playbook = _playbook()
    journal = FakeJournal()
    # `order` is a confirmation gate too, so satisfy its approval and
    # leave only the blocking step unresolved: one condition, and it is a
    # step obligation.
    launch = _started(playbook)
    _satisfy_gate(launch, playbook)
    launch.advance_gate(playbook)
    launch.approve_gate("order", _approval())

    with pytest.raises(GateBlockedError) as caught:
        await advance_gate(
            launches=FakeLaunchStore(launch),
            playbooks=FakePlaybooks(playbook),
            stamp_steady_state=FakeStamper(),
            product_id=PRODUCT_ID,
            journal=journal,
        )

    unsatisfied = caught.value.blocked.unsatisfied
    assert unsatisfied == ("blocking step 'hold.order'",), (
        f"fixture premise: exactly the blocking step is unresolved; the "
        f"domain named {unsatisfied!r}"
    )
    stored = _condition_list(_only(journal))
    # SPECIFIED: the domain's own condition name, identifying the step by
    # identifier.
    assert stored == ["blocking step 'hold.order'"]
    # SPECIFIED: one item of a list, never a sentence about them. A
    # single joined string would satisfy "names the condition" and is
    # exactly what this asserts against.
    assert len(stored) == 1


# ---------------------------------------------------------------------------
# R5: Entries are appended, never replaced or deleted
# ---------------------------------------------------------------------------


async def test_a_second_recording_on_the_same_step_appends_rather_than_replaces() -> (
    None
):
    """Scenario: A second recording on the same step appends rather than
    replaces.

    WHEN a step recorded once is recorded again
    THEN the journal holds two entries for that step, both readable, and
    neither one altered by the other.
    """
    playbook = _playbook()
    launches = FakeLaunchStore(_started(playbook))
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()

    await record_step_outcome(
        launches,
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=InProgress,
        provenance=_provenance(who=RECORDER, when=RECORDED_AT),
        journal=journal,
    )
    await record_step_outcome(
        launches,
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(who=APPROVER, when=LATER_AT),
        journal=journal,
    )

    # SPECIFIED: two entries for that step.
    first, second = journal.appended
    assert first.subject_id == TRACKED_STEP
    assert second.subject_id == TRACKED_STEP
    # SPECIFIED: neither one altered by the other — the earlier entry
    # still carries what it carried when it was appended.
    _assert_names(first, "InProgress", "the first recording's outcome")
    assert first.actor == RECORDER
    assert first.occurred_at == RECORDED_AT
    _assert_names(second, "Satisfied", "the second recording's outcome")
    assert second.actor == APPROVER
    assert second.occurred_at == LATER_AT


async def test_a_replaced_step_outcome_leaves_the_earlier_entry_standing() -> None:
    """Scenario: A replaced step outcome leaves the earlier entry
    standing.

    WHEN a step recorded `Satisfied` is later recorded `Blocked`,
    replacing the stored outcome
    THEN the journal still reports the earlier entry naming the
    `Satisfied` recording.
    """
    playbook = _playbook()
    launch = _started(playbook)
    launches = FakeLaunchStore(launch)
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()

    await record_step_outcome(
        launches,
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Satisfied,
        provenance=_provenance(),
        journal=journal,
    )
    await record_step_outcome(
        launches,
        playbooks,
        product_id=PRODUCT_ID,
        step_id=TRACKED_STEP,
        outcome=Blocked(reason="the photography is not back"),
        provenance=_provenance(when=LATER_AT),
        journal=journal,
    )

    # The state really was replaced — the scenario's premise, and the
    # whole difference between the journal and the state it records.
    progress = launch.progress_for(TRACKED_STEP)
    assert progress is not None
    assert isinstance(progress.outcome, Blocked)
    # SPECIFIED: the journal still reports the earlier entry naming the
    # `Satisfied` recording.
    assert len(journal.appended) == 2
    _assert_names(journal.appended[0], "Satisfied", "the recording it replaced")
    _assert_names(journal.appended[1], "Blocked", "the recording that replaced it")


# ---------------------------------------------------------------------------
# R8: A launch's journal is retained for the life of the launch record
# ---------------------------------------------------------------------------


async def test_the_journal_outlives_the_state_it_records() -> None:
    """Scenario: The journal outlives the state it records.

    WHEN every recorded step outcome of a launch has been replaced by a
    later recording
    THEN the journal still reports an entry for each of the earlier
    recordings.
    """
    playbook = _playbook()
    launch = _started(playbook)
    launches = FakeLaunchStore(launch)
    playbooks = FakePlaybooks(playbook)
    journal = FakeJournal()
    recorded = (TRACKED_STEP, "hold.commit", "hold.order")

    for step_id in recorded:
        await record_step_outcome(
            launches,
            playbooks,
            product_id=PRODUCT_ID,
            step_id=step_id,
            outcome=InProgress,
            provenance=_provenance(when=RECORDED_AT),
            journal=journal,
        )
    for step_id in recorded:
        await record_step_outcome(
            launches,
            playbooks,
            product_id=PRODUCT_ID,
            step_id=step_id,
            outcome=Satisfied,
            provenance=_provenance(when=LATER_AT),
            journal=journal,
        )

    # Every stored outcome really has been replaced — the premise.
    for step_id in recorded:
        progress = launch.progress_for(step_id)
        assert progress is not None
        assert progress.outcome is Satisfied

    # SPECIFIED: an entry for each of the earlier recordings survives.
    earlier = [
        entry
        for entry in journal.appended
        if entry.occurred_at == RECORDED_AT and _names(entry, "InProgress")
    ]
    assert {entry.subject_id for entry in earlier} == set(recorded)
    assert len(journal.appended) == 2 * len(recorded)
