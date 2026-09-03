"""What the launch report carries about each served step
(`launch-instance`).

Derived strictly from the delta spec
`openspec/changes/add-launch-tracking-pages/specs/launch-instance/spec.md`
— all five ADDED requirements and all twelve of their scenarios:

- *The launch report names each step* (2 scenarios)
- *The launch report states whether each step blocks* (1 scenario)
- *The launch report states whether each step is overdue* (5 scenarios)
- *The launch report places each step in its gate and names the gate
  sequence* (2 scenarios)
- *The launch report carries one entry per served step, in the served
  order* (2 scenarios)

The manifest at
`openspec/changes/add-launch-tracking-pages/test-manifest.md` records
every scenario, every assertion's classification and every unresolved
project question this file answered by assumption.

## Why the application level

Every requirement is stated about *the launch report* — what each entry
carries, what the report names. The report is produced by the
application layer (`read_launch` / `read_launches`), so the application
unit tier is the smallest unit that can observe any of them
(`ai-toolkit:testing`'s level rule). Fakes over real `Launch` and
`LaunchPlaybook` values, matching
`tests/unit/launch/application/test_launch_reports.py` and
`test_scope_aware_launch_reads.py`, whose builders this file duplicates
rather than imports — this project shares no test-helper module between
test files, and `tests/**/test_*.py` is the only path a test may be
written to here.

## Expected first-run state — two halves, and they differ

`tasks.md` 1.4 states that `blocking`, `overdue`, per-served-step
coverage and entry order are **already carried** by the report, their
requirements closing spec gaps rather than producing behaviour. So:

- **Expected to PASS on first run**: the eight scenarios of *states
  whether each step blocks*, *states whether each step is overdue* and
  *carries one entry per served step, in the served order*. Per
  `ai-toolkit:testing`, a first-run pass in the target-exists situation
  is the expected result, not an alarm. A **failure** here is a
  significant finding, not a test to adjust: it falsifies `tasks.md`
  1.4's premise, and that task says to stop rather than implement.
- **Expected to FAIL on an absent target**: the four scenarios of *names
  each step* and *places each step in its gate and names the gate
  sequence*. `ReportedStep` carries neither `name` nor `gate` today and
  the report names no gate sequence (`tasks.md` 1.1, 1.2). That failure
  establishes absence and nothing about the assertions themselves.

Which half a given failure falls in is readable from the section
heading each test sits under.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- That each step entry carries the step's **name**, the **gate** the
  playbook attaches it to, whether it **blocks**, and whether it is
  **overdue as of the evaluation date**; that the report **names the
  gate sequence in its order**; that it carries **one entry per served
  step** whether or not an outcome was recorded, in **gate-sequence
  order and, within a gate, that gate's authored order** (the delta's
  own requirement statements).
- That the name is the served playbook's name "at the time the report is
  produced", not a historical one (same).
- That overdue means the due period has fully passed without the step
  reaching a terminal outcome **its hazard permits** — so a
  `prohibited-tactic` step at `Refused` is not overdue (same).
- `read_launch` / `read_launches`, their `as_of` and `scope` parameters,
  and `LaunchDateAtRisk.overdue_steps`, all of which exist today and are
  read here exactly as the two files named above read them.

INVENTED, each recorded in the manifest with its correction point:

- The attribute spellings of the four new facts — `name`, `gate`,
  `blocking`, `overdue` on a step entry, and the gate sequence on the
  report. No artifact fixes a field name. `_ATTRIBUTE_ALIASES` and
  `_read` below are the single correction point, and they **fail
  loudly** rather than returning a default, so no assertion can pass
  vacuously on a missing field.
- The report's own `product_id` / `steps` spellings and each entry's
  `identifier` — taken unchanged from `test_launch_reports.py`.
- The evaluation dates, launch dates and offsets. No artifact fixes any;
  they are chosen so each overdue judgement is unambiguous, and written
  as literals rather than recomputed with `timedelta`, the convention
  `test_timing_anchor.py` records.
- That *The name follows the served playbook* is exercised by driving
  the real `update_step` and rebuilding the served playbook from the
  store — the same `LaunchPlaybook(version=..., gates=..., steps=
  _live_definitions(store))` composition `test_playbook_authoring.py`
  already uses. The scenario says "through the authoring writes"; the
  serving repository that turns records into a playbook is
  infrastructure and is not reachable at this tier, so the composition
  stands in for it. Recorded in the manifest as a deviation.

Correcting a spelling or a fixture is a fixture correction (failure
state 3 in `ai-toolkit:testing`). What must survive unweakened is what
each test asserts: which name, gate, blocking flag and overdue judgement
each entry carries, which gates the report names and in what order, that
an untouched step still gets an entry, and in what order the entries
arrive.

Baseline recorded before these tests were written: `uv run pytest` at
`/home/shatynska/projects/commerce-ops-launch-pages` — 1133 passed, 0
failed, 94 skipped (the whole integration tier, no database configured)
on 2026-08-27.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import (
    read_launch,
    read_launches,
    update_step,
)
from commerce_ops.launch.domain.launch_playbook import (
    Cadence,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    NotStarted,
    OffsetAnchor,
    RecurringAnchor,
    Refused,
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
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER

pytestmark = pytest.mark.anyio

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

A_DISCIPLINE: Final = Discipline("listing")
ANOTHER_DISCIPLINE: Final = Discipline("inventory")

PRINCIPAL: Final = "helen"
APPROVER: Final = "Helen"
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)

# DERIVED dates. A -30-day offset from 2027-04-15 is the single day
# 2027-03-16, fully past on the evaluation date; a +365-day offset is
# comfortably in the future. Written as literals, not recomputed.
LAUNCH_DATE: Final = date(2027, 4, 15)
AS_OF: Final = date(2027, 4, 1)
OVERDUE_STEP_DUE: Final = date(2027, 3, 16)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here: no trio
    # dependency is installed.
    return "asyncio"


# ---------------------------------------------------------------------------
# Builders — the shapes `test_launch_reports.py` records for this aggregate
# ---------------------------------------------------------------------------


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "description": None,
        "gate": "live",
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
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


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`.

    The gate-holding floor forbids a coherent playbook with an unheld
    gate, so `_playbook` fills whichever gates a test's own steps leave
    unheld. Automated with a decided rule so no other coherence rule
    fires, and anchored a year *after* launch so a filler can never be
    the overdue step an assertion is about.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        timing_anchor=OffsetAnchor(days=365),
    )


def _fillers(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1", gates=_gates(), steps=(*steps, *_fillers(steps))
    )


def _served_shaped_playbook(
    steps: tuple[StepDefinition, ...] = (),
) -> LaunchPlaybook:
    """A playbook composed the way the serving layer composes one.

    The serving repository reads the stored set gate-first and, within a
    gate, in the authored slot order, so `served_steps` arrives already
    grouped. `_playbook` above deliberately does not reorder — it hands
    the aggregate exactly what a test authored — so this is the shape to
    use wherever the *served order* is what a test is about.
    """
    authored = (*steps, *_fillers(steps))
    ordered = tuple(
        step for gate in SPECIFIED_GATE_ORDER for step in authored if step.gate == gate
    )
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=ordered)


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who=APPROVER,
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval(**overrides: Any) -> GateApproval:
    attributes: dict[str, Any] = {
        "decision": ApprovalDecision.APPROVING,
        "approver": APPROVER,
        "when": APPROVED_AT,
        "posture": None,
    }
    attributes.update(overrides)
    return GateApproval(**attributes)


def _new_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


def _start(
    playbook: LaunchPlaybook,
    *,
    product_id: ProductId | None = None,
    launch_date: date | None = LAUNCH_DATE,
) -> Launch:
    launch, _ = Launch.start(
        product_id=product_id or _new_product_id(),
        playbook=playbook,
        launch_date=launch_date,
    )
    return launch


def _satisfy_fillers(launch: Launch, playbook: LaunchPlaybook) -> None:
    for step in playbook.steps_for_gate(launch.current_gate):
        if step.blocking and step.identifier.startswith("hold."):
            launch.record_step_outcome(
                playbook,
                step_id=step.identifier,
                outcome=Satisfied,
                provenance=_provenance(),
            )


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    while launch.current_gate != gate:
        _satisfy_fillers(launch, playbook)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class _FakeLaunchStore:
    """In-memory `LaunchStore`. Answers to the three enumeration spellings
    `test_launch_reports.py` records, since no artifact fixes one."""

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
    """Playbook port returning the one version every launch here pinned."""

    def __init__(self, playbook: LaunchPlaybook) -> None:
        self._playbook = playbook

    def get(self, version: str) -> LaunchPlaybook:
        return self._playbook


# ---------------------------------------------------------------------------
# The step-store double, for the authoring write (see the docstring)
# ---------------------------------------------------------------------------


class _Record:
    def __init__(self, definition: StepDefinition) -> None:
        self.definition = definition
        self.created_by: str | None = None
        self.created_on: Any = None
        self.updated_by: str | None = None
        self.updated_on: Any = None
        self.retired_by: str | None = None
        self.retired_on: Any = None
        self.unretired_by: str | None = None
        self.unretired_on: Any = None


class _FakeStepStore:
    def __init__(self, definitions: tuple[StepDefinition, ...]) -> None:
        self.records: tuple[Any, ...] = tuple(
            _Record(definition) for definition in definitions
        )
        self.version = 41

    async def load(self) -> tuple[tuple[Any, ...], int]:
        return self.records, self.version

    async def save(self, records: Any, *, expected_version: int) -> None:
        assert expected_version == self.version, (
            "conditional persistence violated: save() called with a stale "
            f"expected_version {expected_version} against {self.version}"
        )
        self.records = tuple(records)
        self.version += 1


def _served_playbook_of(store: _FakeStepStore) -> LaunchPlaybook:
    """The playbook the serving layer would build from the stored set.

    Only `active` steps are served (`redesign-step-fields`), and the
    stored order is the authored order. The same composition
    `test_playbook_authoring.py` uses to read a store back as a playbook.
    """
    return LaunchPlaybook(
        version=f"set-v{store.version}",
        gates=_gates(),
        steps=tuple(
            record.definition
            for record in store.records
            if record.definition.status is StepStatus.ACTIVE
        ),
    )


# ---------------------------------------------------------------------------
# Reading a report — the single correction point for field spellings
# ---------------------------------------------------------------------------

_ATTRIBUTE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    # Existing, taken from `test_launch_reports.py`.
    "product_id": ("product_id",),
    "steps": ("steps", "step_statuses"),
    "at_risk": ("at_risk", "date_at_risk", "launch_date_at_risk"),
    "identifier": ("identifier", "step_id"),
    "outcome": ("outcome", "recorded_outcome", "progress"),
    "due_period": ("due_period", "due"),
    # Added by this change. INVENTED spellings.
    "name": ("name", "step_name"),
    "gate": ("gate", "gate_id", "gate_identifier"),
    "blocking": ("blocking", "is_blocking", "blocks", "blocks_gate"),
    "overdue": ("overdue", "is_overdue"),
    "gate_sequence": ("gate_sequence", "gates", "gate_order", "sequence"),
}


def _read(subject: object, field: str) -> Any:
    """Read `field` off a report or step entry, trying the spellings no
    artifact fixes.

    Fails the test loudly when none is present, rather than returning a
    default that would leave an assertion vacuously true.
    """
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
        f"expected exactly one report entry for step {step_id!r}, got "
        f"{len(found)} (entries: "
        f"{[str(_read(e, 'identifier')) for e in _entries(report)]})"
    )
    return found[0]


def _identifiers(report: Any) -> tuple[str, ...]:
    return tuple(str(_read(entry, "identifier")) for entry in _entries(report))


async def _read_one(
    store: _FakeLaunchStore,
    playbooks: _FakePlaybooks,
    product_id: ProductId,
    *,
    as_of: date = AS_OF,
) -> Any:
    """The one place to correct if `read_launch`'s call shape differs.

    Assembled from the signature rather than guessed, exactly as
    `test_scope_aware_launch_reads.py` assembles it.
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


async def _read_all(
    store: _FakeLaunchStore,
    playbooks: _FakePlaybooks,
    *,
    as_of: date = AS_OF,
) -> tuple[Any, ...]:
    return tuple(
        await read_launches(
            store, playbooks, as_of=as_of, scope=AccessScope.unrestricted()
        )
    )


# ===========================================================================
# Requirement: The launch report names each step
#
# EXPECTED TO FAIL on an absent target until `tasks.md` 1.1 lands:
# `ReportedStep` carries no `name` today.
# ===========================================================================


async def test_every_step_entry_carries_the_served_playbooks_name() -> None:
    """Scenario: A step entry carries its name.

    WHEN a launch is read back or enumerated
    THEN every step entry in the report SHALL carry the name the served
    playbook gives that step.
    """
    named = _step(identifier="listing.title-conforms", name="Title conforms to policy")
    other = _step(
        identifier="inventory.units-ready",
        name="Units are ready in the warehouse",
        gate="stock-ready",
        discipline=ANOTHER_DISCIPLINE,
    )
    playbook = _playbook(steps=(named, other))
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    read_back = await _read_one(store, playbooks, launch.product_id)
    (enumerated,) = await _read_all(store, playbooks)

    by_identifier = {step.identifier: step.name for step in playbook.served_steps}
    for report, how in ((read_back, "read back"), (enumerated, "enumerated")):
        # SPECIFIED: *every* entry carries the name the served playbook
        # gives it — not only the ones a test named, and not the
        # identifier standing in for a name.
        for entry in _entries(report):
            identifier = str(_read(entry, "identifier"))
            assert _read(entry, "name") == by_identifier[identifier], (
                f"the entry for {identifier!r} in the {how} report carries "
                f"{_read(entry, 'name')!r} rather than the served playbook's "
                f"{by_identifier[identifier]!r}"
            )


async def test_a_step_entry_carries_the_name_the_authoring_write_left() -> None:
    """Scenario: The name follows the served playbook.

    WHEN a step's name is changed through the authoring writes and a
    launch is then read back
    THEN the step entry SHALL carry the changed name.

    The write is the real `update_step`; the served playbook is rebuilt
    from the stored set afterwards, which is what the serving repository
    does and what this tier cannot reach. See the module docstring.
    """
    edited = _step(identifier="listing.title-conforms", name="The original wording")
    store = _FakeStepStore((edited, *_fillers((edited,))))
    before = _served_playbook_of(store)
    launch = _start(before)
    launches = _FakeLaunchStore(launch)

    # DERIVED guard: the report really carried the original name first, so
    # the assertion below observes a change rather than a coincidence.
    original = await _read_one(launches, _FakePlaybooks(before), launch.product_id)
    assert _read(_entry_for(original, "listing.title-conforms"), "name") == (
        "The original wording"
    )

    await update_step(
        steps=store,
        principal=PRINCIPAL,
        step_id="listing.title-conforms",
        name="The reworded wording",
    )

    after = await _read_one(
        launches, _FakePlaybooks(_served_playbook_of(store)), launch.product_id
    )

    # SPECIFIED: the entry carries the changed name — the report names the
    # step as the served playbook now calls it, not as it was called when
    # the launch started.
    assert _read(_entry_for(after, "listing.title-conforms"), "name") == (
        "The reworded wording"
    )


# ===========================================================================
# Requirement: The launch report states whether each step blocks
#
# EXPECTED TO PASS on first run (`tasks.md` 1.4). A failure falsifies that
# task's premise and is a finding, not a test to adjust.
# ===========================================================================


async def test_every_step_entry_states_whether_it_blocks_its_gate() -> None:
    """Scenario: A step entry states whether it blocks.

    WHEN a launch is read back or enumerated
    THEN every step entry in the report SHALL state whether that step
    blocks its gate.
    """
    blocking = _step(identifier="listing.blocking", blocking=True)
    passive = _step(identifier="listing.passive", blocking=False)
    playbook = _playbook(steps=(blocking, passive))
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    read_back = await _read_one(store, playbooks, launch.product_id)
    (enumerated,) = await _read_all(store, playbooks)

    expected = {step.identifier: step.blocking for step in playbook.served_steps}
    for report, how in ((read_back, "read back"), (enumerated, "enumerated")):
        # SPECIFIED: every entry states it, and states it correctly — a
        # field that were always `False` would satisfy "carries a flag"
        # while answering the question wrongly, so both a blocking and a
        # non-blocking step are asserted.
        for entry in _entries(report):
            identifier = str(_read(entry, "identifier"))
            assert bool(_read(entry, "blocking")) is expected[identifier], (
                f"the entry for {identifier!r} in the {how} report reports "
                f"blocking={_read(entry, 'blocking')!r} where the playbook "
                f"attaches it as blocking={expected[identifier]!r}"
            )
    # DERIVED guard: the fixture really holds one of each, so neither
    # assertion above is vacuous.
    assert set(expected.values()) == {True, False}


# ===========================================================================
# Requirement: The launch report states whether each step is overdue
#
# EXPECTED TO PASS on first run (`tasks.md` 1.4), as above.
# ===========================================================================


async def test_an_overdue_non_blocking_step_on_a_healthy_launch_is_reported_overdue() -> (
    None
):
    """Scenario: An overdue non-blocking step is reported overdue.

    WHEN a launch that is not reported at risk holds a non-blocking step
    whose due period has fully passed unresolved
    THEN that step's entry SHALL state that it is overdue.
    """
    passed = _step(
        identifier="listing.passed",
        blocking=False,
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(steps=(passed,))
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    # DERIVED guard on the WHEN: the launch is *not* at risk, which is the
    # whole point — the existing at-risk requirement would say nothing
    # about this step.
    assert not _read(report, "at_risk"), (
        "the fixture launch is reported at risk, so this test does not reach "
        "the case the scenario is about (a healthy launch with an overdue "
        "non-blocking step)"
    )
    # DERIVED guard: the due period really has fully passed as of AS_OF.
    due = _read(_entry_for(report, "listing.passed"), "due_period")
    assert due is not None and due.end is not None and due.end < AS_OF, (
        f"the step's due period {due!r} has not fully passed before {AS_OF}"
    )

    # SPECIFIED: the entry states that it is overdue.
    assert bool(_read(_entry_for(report, "listing.passed"), "overdue")), (
        "a non-blocking step whose due period has fully passed unresolved is "
        "not reported overdue, so the fact `briefing` already derives a "
        "monitor item from is absent from the report"
    )


async def test_the_overdue_blocking_step_the_at_risk_evaluation_names_is_marked() -> (
    None
):
    """Scenario: An overdue blocking step is reported overdue on its own
    entry.

    WHEN a launch is reported at risk, its at-risk evaluation naming an
    overdue blocking step
    THEN the entry for the step the at-risk evaluation names SHALL state
    that it is overdue.
    """
    blocking = _step(
        identifier="listing.blocking-passed",
        blocking=True,
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(steps=(blocking,))
    launch = _start(playbook)
    _advance_to(launch, playbook, "live")
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    at_risk = _read(report, "at_risk")
    # DERIVED guard on the WHEN: the launch is at risk and its evaluation
    # names a step, so the assertion below is about the named one.
    assert at_risk, "the fixture launch is not reported at risk"
    assert hasattr(at_risk, "overdue_steps"), (
        "the at-risk evaluation exposes no `overdue_steps`, so it names no "
        "step and this scenario cannot be reached"
    )
    named = tuple(str(step) for step in at_risk.overdue_steps)
    assert named, "the at-risk evaluation names no overdue step"

    # SPECIFIED: each step the evaluation names says so on its *own*
    # entry — the fact travels per step, not only inside the evaluation.
    for identifier in named:
        assert bool(_read(_entry_for(report, identifier), "overdue")), (
            f"the at-risk evaluation names {identifier!r} as overdue while "
            "that step's own entry does not state it, so a consumer reading "
            "entries would miss it"
        )


async def test_a_step_resolved_under_its_own_hazard_is_not_overdue() -> None:
    """Scenario: A step resolved under its own hazard is not overdue.

    WHEN a step whose hazard permits only `Refused` has reached `Refused`
    and its due period has fully passed
    THEN that step's entry SHALL NOT state that it is overdue.
    """
    prohibited = _step(
        identifier="listing.prohibited",
        blocking=False,
        hazard=Hazard.PROHIBITED_TACTIC,
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(steps=(prohibited,))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id="listing.prohibited",
        outcome=Refused,
        provenance=_provenance(),
    )
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    entry = _entry_for(report, "listing.prohibited")
    # DERIVED guard: the due period has fully passed, so a page deriving
    # overdue from the due period and the outcome alone would say yes.
    due = _read(entry, "due_period")
    assert due is not None and due.end is not None and due.end < AS_OF

    # SPECIFIED: not overdue — `Refused` is the terminal outcome this
    # step's hazard permits, which is exactly the judgement no consumer
    # can make from the due period and the outcome alone.
    assert not bool(_read(entry, "overdue")), (
        "a prohibited-tactic step that has reached `Refused` is reported "
        "overdue, so the report is making the judgement a consumer computing "
        "it from the due period would make — and it would stay overdue forever"
    )


async def test_no_step_is_overdue_on_a_launch_with_no_date() -> None:
    """Scenario: A step with no due period is not overdue.

    WHEN a launch has no launch date, so no step's due period resolves
    THEN no step entry SHALL state that it is overdue.
    """
    passed = _step(identifier="listing.passed", timing_anchor=OffsetAnchor(days=-30))
    playbook = _playbook(steps=(passed,))
    launch = _start(playbook, launch_date=None)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    # DERIVED guard: the report really holds entries, so "no entry states
    # overdue" is not satisfied by there being no entries.
    assert _entries(report), "the report carries no step entries at all"
    # DERIVED guard: no due period resolves, which is the WHEN's premise.
    for entry in _entries(report):
        assert _read(entry, "due_period") is None, (
            f"the entry for {_read(entry, 'identifier')!r} resolves a due "
            "period on an undated launch"
        )

    # SPECIFIED: no entry states that it is overdue.
    overdue = [
        str(_read(entry, "identifier"))
        for entry in _entries(report)
        if bool(_read(entry, "overdue"))
    ]
    assert overdue == [], (
        f"{overdue} are reported overdue on a launch with no date, so no due "
        "period could have passed"
    )


async def test_a_recurring_anchor_step_on_a_dated_launch_is_not_overdue() -> None:
    """Scenario: A recurring-anchor step on a dated launch is not overdue.

    WHEN a launch has a launch date and holds a step whose timing anchor
    is recurring, so it resolves to no due period
    THEN that step's entry SHALL NOT state that it is overdue.
    """
    recurring = _step(
        identifier="listing.recurring",
        blocking=False,
        timing_anchor=RecurringAnchor(cadence=Cadence.WEEKLY),
    )
    passed = _step(identifier="listing.passed", timing_anchor=OffsetAnchor(days=-30))
    playbook = _playbook(steps=(recurring, passed))
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    # DERIVED guard: the launch *is* dated and another step on it really
    # is overdue, so this test is about the anchor and not about a report
    # that marks nothing overdue at all.
    assert launch.launch_date == LAUNCH_DATE
    assert bool(_read(_entry_for(report, "listing.passed"), "overdue"))

    entry = _entry_for(report, "listing.recurring")
    # DERIVED guard: the anchor really resolves to no due period.
    assert _read(entry, "due_period") is None

    # SPECIFIED: the recurring step's entry does not state overdue.
    assert not bool(_read(entry, "overdue")), (
        "a recurring-anchor step, which resolves to no due period at all, is "
        "reported overdue on a dated launch"
    )


# ===========================================================================
# Requirement: The launch report places each step in its gate and names the
# gate sequence
#
# EXPECTED TO FAIL on an absent target until `tasks.md` 1.1 and 1.2 land.
# ===========================================================================


async def test_every_step_entry_carries_the_gate_the_playbook_attaches_it_to() -> None:
    """Scenario: A step entry carries its gate.

    WHEN a launch is read back or enumerated
    THEN every step entry in the report SHALL carry the gate the playbook
    attaches that step to.
    """
    early = _step(identifier="listing.early", gate="commit")
    late = _step(identifier="listing.late", gate="ignition")
    playbook = _playbook(steps=(early, late))
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    read_back = await _read_one(store, playbooks, launch.product_id)
    (enumerated,) = await _read_all(store, playbooks)

    expected = {step.identifier: step.gate for step in playbook.served_steps}
    for report, how in ((read_back, "read back"), (enumerated, "enumerated")):
        # SPECIFIED: every entry carries its own gate, so a consumer can
        # group without obtaining the playbook.
        for entry in _entries(report):
            identifier = str(_read(entry, "identifier"))
            assert str(_read(entry, "gate")) == expected[identifier], (
                f"the entry for {identifier!r} in the {how} report carries "
                f"gate {_read(entry, 'gate')!r} rather than the playbook's "
                f"{expected[identifier]!r}"
            )
    # DERIVED guard: the fixture spans more than one gate, so a report
    # stamping every entry with the current gate would fail above.
    assert len(set(expected.values())) > 1


async def test_the_report_names_the_gate_sequence_in_order() -> None:
    """Scenario: The report names the gates in order.

    WHEN a launch is read back or enumerated
    THEN the report SHALL name the gate sequence in its order, and the
    launch's current gate SHALL be one of them.
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))
    launch = _start(playbook)
    _advance_to(launch, playbook, "listable")
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    read_back = await _read_one(store, playbooks, launch.product_id)
    (enumerated,) = await _read_all(store, playbooks)

    for report, how in ((read_back, "read back"), (enumerated, "enumerated")):
        named = tuple(str(gate) for gate in _read(report, "gate_sequence"))
        # SPECIFIED: the gates, in the sequence's order. Compared as a
        # sequence, not a set — the order is the half a consumer cannot
        # recover, and it is why the sequence travels at all.
        assert named == SPECIFIED_GATE_ORDER, (
            f"the {how} report names {named} rather than the gate sequence "
            f"{SPECIFIED_GATE_ORDER} in its order"
        )
        # SPECIFIED: the launch's current gate is one of them.
        assert launch.current_gate in named, (
            f"the launch stands at {launch.current_gate!r}, which the {how} "
            f"report's gate sequence {named} does not name"
        )


# ===========================================================================
# Requirement: The launch report carries one entry per served step, in the
# served order
#
# EXPECTED TO PASS on first run (`tasks.md` 1.4).
# ===========================================================================


async def test_a_served_step_with_no_recorded_outcome_still_gets_an_entry() -> None:
    """Scenario: The report carries an entry for a step with no recorded
    outcome.

    WHEN a launch is read back and a served step has no recorded outcome
    THEN the report SHALL carry an entry for that step.
    """
    touched = _step(identifier="listing.touched")
    untouched = _step(identifier="listing.untouched")
    playbook = _playbook(steps=(touched, untouched))
    launch = _start(playbook)
    launch.record_step_outcome(
        playbook,
        step_id="listing.touched",
        outcome=Satisfied,
        provenance=_provenance(),
    )
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    report = await _read_one(store, playbooks, launch.product_id)

    # SPECIFIED: one entry per served step, whether or not an outcome was
    # recorded — asserted over the whole served set, so a report holding
    # only the recorded steps fails here.
    assert set(_identifiers(report)) == {
        step.identifier for step in playbook.served_steps
    }, (
        "the report does not carry one entry per served step: it holds "
        f"{sorted(_identifiers(report))} against a served set of "
        f"{sorted(step.identifier for step in playbook.served_steps)}"
    )
    # SPECIFIED: and the untouched step's entry is present with nothing
    # recorded, which is the fact that makes it distinguishable from one
    # recorded `NotStarted`.
    assert _read(_entry_for(report, "listing.untouched"), "outcome") in (
        None,
        NotStarted,
    ), (
        "the untouched step's entry carries a recorded outcome, so nothing "
        "having been recorded is indistinguishable from a recording"
    )


async def test_step_entries_arrive_in_the_served_playbooks_order() -> None:
    """Scenario: Step entries arrive in the served playbook's order.

    WHEN a launch is read back or enumerated
    THEN the report's step entries SHALL be ordered by gate in the gate
    sequence's order, and within each gate by that gate's authored step
    order.

    The fixture playbook is composed the way the serving layer composes
    one — gate-sequence order, and within a gate the authored slot order
    — because the requirement is about "the served playbook's **own**
    order" and a playbook assembled any other way is not a served one.

    A NOTE THAT IS NOT A WEAKENING, and is recorded in the manifest and
    in this pass's report as a finding for whoever revises the change:
    the report was observed to hand entries over in exactly the order
    the `LaunchPlaybook` was constructed in, so the gate grouping this
    scenario names is a property of how the served playbook is composed,
    not something the report imposes. Handed a playbook whose steps
    arrive out of gate order, the entries came out ungrouped. Nothing in
    `openspec/specs/` requires the serving layer to hand `served_steps`
    over gate-first, so the obligation rests on an unstated premise.
    That is a specification gap to close in the artifacts, not an
    assertion to invent here — so this test asserts both halves against
    a served-shaped playbook and does not manufacture a stricter
    obligation nobody agreed to.
    """
    # Two steps at one gate and two gates in play, composed gate-first
    # (`commit` before `ignition`) as the serving layer composes them, so
    # the within-gate half has something to be wrong about.
    authored = (
        _step(identifier="listing.early-first", gate="commit"),
        _step(identifier="listing.early-second", gate="commit"),
        _step(identifier="listing.late", gate="ignition"),
    )
    playbook = _served_shaped_playbook(authored)
    launch = _start(playbook)
    store, playbooks = _FakeLaunchStore(launch), _FakePlaybooks(playbook)

    read_back = await _read_one(store, playbooks, launch.product_id)
    (enumerated,) = await _read_all(store, playbooks)

    served_order = tuple(step.identifier for step in playbook.served_steps)
    for report, how in ((read_back, "read back"), (enumerated, "enumerated")):
        arrived = _identifiers(report)
        # SPECIFIED: one entry per served step, in the served playbook's
        # own order — compared as a sequence, so both the coverage and
        # the order are asserted at once.
        assert arrived == served_order, (
            f"the {how} report hands entries over as {list(arrived)} where "
            f"the served playbook's order is {list(served_order)}"
        )

        gates = [_gate_of(identifier, playbook) for identifier in arrived]
        positions = [SPECIFIED_GATE_ORDER.index(gate) for gate in gates]
        # SPECIFIED: ordered by gate in the gate sequence's order — the
        # gate positions never decrease as the entries arrive.
        assert positions == sorted(positions), (
            f"the {how} report's entries are not grouped in gate-sequence "
            f"order: {list(zip(arrived, gates, strict=True))}"
        )
        # SPECIFIED: and within each gate, in that gate's authored order.
        for gate in SPECIFIED_GATE_ORDER:
            authored_here = [step.identifier for step in playbook.steps_for_gate(gate)]
            arrived_here = [
                identifier
                for identifier, entry_gate in zip(arrived, gates, strict=True)
                if entry_gate == gate
            ]
            assert arrived_here == authored_here, (
                f"at gate {gate!r} the {how} report hands over "
                f"{arrived_here} where the served playbook's authored order "
                f"is {authored_here}"
            )
    # DERIVED guard: the fixture really spans more than one gate and puts
    # two steps at one of them, so neither half above is vacuous.
    assert len({step.gate for step in playbook.served_steps}) > 1
    assert len(playbook.steps_for_gate("commit")) > 1


def _gate_of(identifier: str, playbook: LaunchPlaybook) -> str:
    for step in playbook.served_steps:
        if step.identifier == identifier:
            return str(step.gate)
    pytest.fail(f"{identifier!r} is not a served step of the fixture playbook")
