"""What the launch report carries about a step that has not started
(`launch-instance`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-instance/spec.md`:

- ADDED *The launch report states whether each step has started, and what
  it waits for* — all four scenarios.
- MODIFIED *The launch report states whether each step is overdue* — only
  its three new scenarios: *A step whose start gate is not reached is not
  overdue though its due period passed*, *A step held only by a
  dependency is still overdue*, and *A step becomes overdue once the
  launch releases it*. Its other five are reproduced from the served spec
  — one with "a non-blocking step" reworded to "a released non-blocking
  step" — and are covered by `test_launch_report_step_facts.py`, whose
  fixtures declare no start gate and are therefore released from the
  first gate.

The at-risk half of the same delta is domain-level and lives in
`tests/unit/launch/domain/test_launch_dates_release.py`. The manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
accounts for every scenario in the change.

## Level

`read_launch` over fakes — the application unit tier, because every
requirement here is stated about *the launch report*, which the
application layer produces. Same level, same doubles and the same
`_read`/`_entry_for` accessors as `test_launch_report_step_facts.py`,
duplicated rather than imported because this project shares no
test-helper module between test files.

## INVENTED, with correction points

- The attribute spellings of the three new facts on a step entry —
  whether the launch has released it, the gate it starts at where the
  launch has not reached it, and the identifiers of its unresolved
  dependencies. No artifact fixes a field name. `_ATTRIBUTE_ALIASES` and
  `_read` are the single correction point, and they **fail loudly**
  rather than returning a default, so no assertion can pass vacuously on
  a missing field.
- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition`. Correction point: `_step`.
- The dates, offsets and gates, chosen so each overdue judgement is
  unambiguous and written as literals rather than recomputed.

What must survive unweakened is what each test asserts: which entries
report a step as started, what an unstarted entry names, and which
entries are overdue.

## Expected first-run state

Neither field exists and the report carries neither fact, so every test
here is expected to fail on an **absent target** — a `TypeError` from
the constructor, or `_read`'s loud failure. That establishes absence and
nothing about these assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import read_launch
from commerce_ops.launch.domain.launch_playbook import (
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    StepDefinition,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step

pytestmark = pytest.mark.anyio

A_DISCIPLINE: Final = next(iter(Discipline))

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)

# DERIVED dates, taken from `test_launch_report_step_facts.py`: a -30-day
# offset from 2027-04-15 is the single day 2027-03-16, fully past on the
# evaluation date; a +365-day offset is comfortably in the future.
LAUNCH_DATE: Final = date(2027, 4, 15)
AS_OF: Final = date(2027, 4, 1)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**{"timing_anchor": OffsetAnchor(days=-30), **overrides})


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, anchored a year after the launch
    so it is never overdue, and declaring neither start field so it is
    released from the first gate."""
    return _build_hold(
        gate,
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="report-v1", gates=_gates(), steps=(*steps, *fillers))


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who="Helen",
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=APPROVED_AT,
        posture=None,
    )


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=ProductId(str(uuid.uuid4())),
        playbook=playbook,
        launch_date=LAUNCH_DATE,
    )
    return launch


def _satisfy(launch: Launch, playbook: LaunchPlaybook, step_id: str) -> None:
    launch.record_step_outcome(
        playbook, step_id=step_id, outcome=Satisfied, provenance=_provenance()
    )


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and launch.progress_for(step.identifier) is None:
                _satisfy(launch, playbook, step.identifier)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class _FakeLaunchStore:
    def __init__(self, *launches: Launch) -> None:
        self._launches = {launch.product_id: launch for launch in launches}

    async def get_by_product_id(
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Launch | None:
        return self._launches.get(product_id)

    async def save(self, launch: Launch) -> None:
        self._launches[launch.product_id] = launch

    async def list_all(self, *_args: Any, **_kwargs: Any) -> tuple[Launch, ...]:
        return tuple(self._launches.values())

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)

    async def list_launches(self, *args: Any, **kwargs: Any) -> tuple[Launch, ...]:
        return await self.list_all(*args, **kwargs)


class _FakePlaybooks:
    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# Reading the report — the single correction point for every spelling
# ---------------------------------------------------------------------------

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    # Existing, taken from `test_launch_report_step_facts.py`.
    "steps": ("steps", "step_statuses"),
    "at_risk": ("at_risk", "date_at_risk", "launch_date_at_risk"),
    "identifier": ("identifier", "step_id"),
    "due_period": ("due_period", "due"),
    "overdue": ("overdue", "is_overdue"),
    # Added by this change. INVENTED spellings.
    "released": ("released", "is_released", "started", "has_started"),
    "starts_at_gate": (
        "starts_at_gate",
        "start_gate",
        "awaiting_gate",
        "waiting_for_gate",
    ),
    "unresolved_dependencies": (
        "unresolved_dependencies",
        "unresolved_after_steps",
        "waiting_on",
        "awaiting_steps",
        "unresolved_dependency_ids",
    ),
}


def _read(subject: object, field: str) -> Any:
    for name in _ATTRIBUTE_ALIASES[field]:
        if hasattr(subject, name):
            return getattr(subject, name)
    pytest.fail(
        f"{type(subject).__name__} exposes none of {_ATTRIBUTE_ALIASES[field]} "
        f"for {field!r}; the launch report must carry it (see this file's "
        "docstring for the INVENTED spellings and their correction point)"
    )


def _entries(report: Any) -> tuple[Any, ...]:
    return tuple(_read(report, "steps"))


def _entry_for(report: Any, step_id: str) -> Any:
    found = [
        entry
        for entry in _entries(report)
        if str(_read(entry, "identifier")) == step_id
    ]
    assert len(found) == 1, (
        f"expected exactly one report entry for step {step_id!r}, got {len(found)}"
    )
    return found[0]


def _waiting_on(entry: Any) -> tuple[str, ...]:
    named = _read(entry, "unresolved_dependencies")
    return tuple(str(item) for item in (named or ()))


async def _read_one(
    store: _FakeLaunchStore,
    playbooks: _FakePlaybooks,
    product_id: ProductId,
    *,
    as_of: date = AS_OF,
) -> Any:
    """The one place to correct if `read_launch`'s call shape differs.

    Assembled from the signature rather than guessed, exactly as
    `test_launch_report_step_facts.py` assembles it.
    """
    parameters = inspect.signature(read_launch).parameters
    arguments: dict[str, Any] = {}
    for name in list(parameters)[1:]:
        if "playbook" in name:
            arguments[name] = playbooks
        elif "product" in name or name in ("identifier", "launch_id"):
            arguments[name] = product_id
        elif "scope" in name:
            arguments[name] = AccessScope.unrestricted()
        elif name == "as_of":
            arguments[name] = as_of
    return await read_launch(store, **arguments)


# ---------------------------------------------------------------------------
# ADDED Requirement: The launch report states whether each step has
# started, and what it waits for
# ---------------------------------------------------------------------------


async def test_a_released_step_is_reported_as_released() -> None:
    """Scenario: A released step is reported as released.

    WHEN a launch's report is produced and the launch has released a step
    THEN that step's entry states that it has started, and names nothing
    it waits for.
    """
    released = _step(identifier="listing.starts-now", starts_at_gate="commit")
    playbook = _playbook(released)
    launch = _start(playbook)

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.starts-now")

    # SPECIFIED: it has started.
    assert bool(_read(entry, "released"))
    # SPECIFIED: and names nothing it waits for.
    assert _read(entry, "starts_at_gate") is None
    assert _waiting_on(entry) == ()


async def test_an_unreleased_step_names_the_gate_it_starts_at() -> None:
    """Scenario: An unreleased step names the gate it starts at.

    WHEN a launch standing at `commit` holds a step whose start gate is
    `listable`
    THEN that step's entry states that it has not started, and names
    `listable` as the gate it starts at.

    SPECIFIED reason for it travelling on the report at all: release
    "cannot be re-derived by a consumer" — it depends on the gate
    sequence's positions and on which terminal outcomes each named step's
    hazard permits.
    """
    waiting = _step(identifier="listing.waits-for-listable", starts_at_gate="listable")
    playbook = _playbook(waiting)
    launch = _start(playbook)

    assert launch.current_gate == "commit"

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.waits-for-listable")

    assert not bool(_read(entry, "released"))
    assert str(_read(entry, "starts_at_gate")) == "listable"


async def test_an_unreleased_step_names_its_unresolved_dependencies() -> None:
    """Scenario: An unreleased step names its unresolved dependencies.

    WHEN a step the launch has reached the start gate of names two
    `after_steps` dependencies, one resolved and one not
    THEN that step's entry names only the unresolved one.

    SPECIFIED: "The unresolved dependencies SHALL be named by identifier,
    so that a consumer can state what a step waits for without a second
    read."
    """
    resolved = _step(identifier="listing.photos-approved", gate="commit")
    unresolved = _step(identifier="listing.copy-approved", gate="commit")
    depending = _step(
        identifier="listing.copy-written",
        starts_at_gate="commit",
        after_steps=("listing.photos-approved", "listing.copy-approved"),
    )
    playbook = _playbook(resolved, unresolved, depending)
    launch = _start(playbook)
    _satisfy(launch, playbook, "listing.photos-approved")

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.copy-written")

    assert not bool(_read(entry, "released"))
    # SPECIFIED: only the unresolved one.
    assert _waiting_on(entry) == ("listing.copy-approved",)
    # SPECIFIED (by the same clause): the start gate is reached, so it is
    # not what the entry names.
    assert _read(entry, "starts_at_gate") is None


async def test_a_step_waiting_on_both_names_both() -> None:
    """Scenario: A step waiting on both names both.

    WHEN a step is held back by its start gate and by an unresolved
    dependency
    THEN its entry names the gate and the dependency.
    """
    dependency = _step(identifier="listing.photos-approved", gate="commit")
    depending = _step(
        identifier="listing.copy-written",
        starts_at_gate="listable",
        after_steps=("listing.photos-approved",),
    )
    playbook = _playbook(dependency, depending)
    launch = _start(playbook)

    assert launch.current_gate == "commit"

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.copy-written")

    assert not bool(_read(entry, "released"))
    # SPECIFIED: both, not whichever the implementation checked first.
    assert str(_read(entry, "starts_at_gate")) == "listable"
    assert _waiting_on(entry) == ("listing.photos-approved",)


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The launch report states whether each step is
# overdue (the three new scenarios)
# ---------------------------------------------------------------------------


async def test_a_step_whose_start_gate_is_not_reached_is_not_overdue() -> None:
    """Scenario: A step whose start gate is not reached is not overdue
    though its due period passed.

    WHEN a launch standing at `commit` holds an unresolved step that
    starts at `listable` and whose due period has fully passed
    THEN that step's entry SHALL NOT state that it is overdue.

    SPECIFIED reason: "Nobody has been asked for the work, so there is
    nothing anyone has failed to do, and a launch delayed at an early
    gate would otherwise accumulate overdue marks against the whole of
    the plan ahead of it."
    """
    unreached = _step(
        identifier="listing.waits-for-listable",
        starts_at_gate="listable",
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(unreached)
    launch = _start(playbook)

    assert launch.current_gate == "commit"

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.waits-for-listable")

    # DERIVED guard on the WHEN: the due period really has fully passed,
    # so the exclusion is what suppresses the mark rather than the dates.
    due = _read(entry, "due_period")
    assert due is not None and due.end is not None and due.end < AS_OF, (
        f"the step's due period {due!r} has not fully passed before {AS_OF}, "
        "so this test does not reach the case the scenario is about"
    )

    assert not bool(_read(entry, "overdue"))


async def test_a_step_held_only_by_a_dependency_is_still_overdue() -> None:
    """Scenario: A step held only by a dependency is still overdue.

    WHEN a launch has reached a step's start gate, the step is held only
    by an unresolved `after_steps` dependency, and its due period has
    fully passed
    THEN that step's entry SHALL state that it is overdue, and SHALL
    still name the dependency it waits on.

    SPECIFIED: "The exclusion SHALL turn on the start gate alone, and not
    on the step's dependencies" — otherwise "the later a dependency ran,
    the quieter the report became". This is the discriminating case for
    an implementation that suppressed the mark on any unreleased step.
    """
    dependency = _step(
        identifier="listing.photos-approved",
        gate="commit",
        timing_anchor=OffsetAnchor(days=365),
    )
    depending = _step(
        identifier="listing.copy-written",
        starts_at_gate="commit",
        after_steps=("listing.photos-approved",),
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(dependency, depending)
    launch = _start(playbook)

    report = await _read_one(
        _FakeLaunchStore(launch), _FakePlaybooks(playbook), launch.product_id
    )
    entry = _entry_for(report, "listing.copy-written")

    # DERIVED guard: the step is unreleased, and unreleased by the
    # dependency alone.
    assert not bool(_read(entry, "released"))
    assert _read(entry, "starts_at_gate") is None

    # SPECIFIED: still overdue.
    assert bool(_read(entry, "overdue"))
    # SPECIFIED: and still names the dependency it waits on.
    assert _waiting_on(entry) == ("listing.photos-approved",)


async def test_a_step_becomes_overdue_once_the_launch_releases_it() -> None:
    """Scenario: A step becomes overdue once the launch releases it.

    WHEN a launch advances to the start gate of an unresolved step whose
    due period has already fully passed
    THEN that step's entry SHALL state that it is overdue from that
    point.

    Asserted as the same step read twice across one advance, so the
    change of judgement is what is observed rather than the judgement
    alone.
    """
    waiting = _step(
        identifier="listing.waits-for-listable",
        starts_at_gate="listable",
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(waiting)
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    before = await _read_one(store, playbooks, launch.product_id)
    assert not bool(_read(_entry_for(before, "listing.waits-for-listable"), "overdue"))

    _advance_to(launch, playbook, "listable")

    after = await _read_one(store, playbooks, launch.product_id)
    entry = _entry_for(after, "listing.waits-for-listable")

    # DERIVED guard: still unresolved, so the mark is about lateness and
    # not about a recorded outcome.
    assert launch.progress_for("listing.waits-for-listable") is None
    # SPECIFIED: overdue from that point.
    assert bool(_read(entry, "overdue"))
    assert bool(_read(entry, "released"))
