"""When a step may start, and when a launch has released it
(`launch-playbook`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-playbook/spec.md`:

- ADDED *A step declares when it may start* — all nine scenarios.
- ADDED *A dependency nobody is still owed is satisfied vacuously* — all
  four scenarios.
- ADDED *The stored step set declares when its steps start* — only its
  scenario *An activated draft does not become eligible everywhere*,
  which is a statement about the predicate rather than about the
  backfill; the backfill's own scenarios live in
  `tests/integration/launch/test_step_start_gate_backfill.py` and the
  vendored-delivery ones in
  `tests/unit/launch/test_playbook_reference_set_start_gates.py`.
- MODIFIED *A step definition declares how it is to be resolved* — only
  its one new clause, "the gate it starts at and the steps it waits on
  are read back as declared". The rest of that scenario is reproduced
  unchanged and is covered by
  `tests/unit/launch/domain/test_launch_playbook.py`.

The manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`
records every scenario, every assertion's classification and every
project question this file answered by assumption.

## Level

`Launch` and `LaunchPlaybook` values, with no I/O and no clock. The
delta puts the predicate on the aggregate ("Release SHALL consult no
clock and perform no I/O"), so the domain is the smallest unit that can
observe any of these — `ai-toolkit:testing`'s level rule.

## The interface under test does not exist yet, and its shape is INVENTED

`tasks.md` 1.1 and 3.1 fix the concepts and the field names but not the
predicate's spelling or call shape. Assumed here, each with its
correction point named:

- `StepDefinition(..., starts_at_gate=..., after_steps=...)` — the field
  names are SPECIFIED by the delta and by `tasks.md` 1.1; that they are
  constructor keywords on the existing frozen dataclass is INVENTED.
  Correction point: `_step`.
- The predicate is a method on `Launch` found by probing
  `_PREDICATE_NAMES`, called with the playbook and the step (or the
  step's identifier). Correction point: `_released`. It **fails loudly**
  rather than defaulting, so no assertion below can pass vacuously
  against a predicate that is not there.
- `after_steps` accepting a list and normalising to a tuple, per
  `tasks.md` 1.1 ("normalising ... exactly as `assignees` is").

Correcting a spelling or a call shape is a fixture correction (failure
state 3 in `ai-toolkit:testing`). What must survive unweakened is what
each test asserts: which launch/step pairs are released and which are
not.

## Expected first-run state

`StepDefinition` carries neither field and `Launch` carries no
predicate, so every test here is expected to fail on an **absent
target** — `TypeError` from the constructor, or `_released`'s loud
failure. Per `ai-toolkit:testing` that establishes absence and nothing
about whether these assertions are any good.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
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
    LaunchError,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER

FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

A_DISCIPLINE: Final = next(iter(Discipline))

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 4, 15)


# ---------------------------------------------------------------------------
# Builders
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
    """A valid step definition, overriding named attributes.

    INVENTED: `starts_at_gate` and `after_steps` as constructor keywords.
    Both are omitted from the baseline deliberately, so that the "author
    said nothing" case exercises the defaults rather than restating them.
    """
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
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


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, satisfying the gate-holding floor.

    It declares neither start field, so a filler is released from the
    first gate and can never be the reason a test's own step is held.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="release-v1", gates=_gates(), steps=(*steps, *fillers)
    )


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
    """Walk the launch to `gate`, satisfying only the fillers holding it.

    Deliberately satisfies `hold.` fillers alone: a test's own steps stay
    unresolved, which is what nearly every scenario here needs.
    """
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if (
                step.blocking
                and step.identifier.startswith("hold.")
                and launch.progress_for(step.identifier) is None
            ):
                _satisfy(launch, playbook, step.identifier)
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# The predicate, reached through one correction point
# ---------------------------------------------------------------------------

#: INVENTED spellings. `design.md` names the concept `released(launch,
#: step)` and puts it on `Launch`; no artifact fixes the method name.
_PREDICATE_NAMES: Final = (
    "has_released",
    "released",
    "is_released",
    "releases",
    "has_started",
    "step_released",
)


def _released(launch: Launch, playbook: LaunchPlaybook, step: StepDefinition) -> bool:
    """Whether `launch` has released `step`.

    Probes the method name and the call shape rather than assuming one,
    and fails loudly when neither is found — an assertion that silently
    read a default would establish nothing.
    """
    found = None
    name_found = None
    for name in _PREDICATE_NAMES:
        candidate = getattr(launch, name, None)
        if callable(candidate):
            found = candidate
            name_found = name
            break
    if found is None:
        pytest.fail(
            "`Launch` exposes no release predicate under any of "
            f"{_PREDICATE_NAMES} — correct this file's probe to the "
            "implemented name"
        )
    attempts: tuple[tuple[tuple[Any, ...], dict[str, Any]], ...] = (
        ((playbook, step), {}),
        ((playbook,), {"step": step}),
        ((playbook,), {"step_id": step.identifier}),
        ((playbook, step.identifier), {}),
        ((step,), {"playbook": playbook}),
    )
    failures: list[str] = []
    for args, kwargs in attempts:
        try:
            answer = found(*args, **kwargs)
        except TypeError as mismatch:  # the call shape, not the predicate
            failures.append(f"{args!r}/{kwargs!r}: {mismatch}")
            continue
        return bool(answer)
    pytest.fail(
        f"`Launch.{name_found}` accepted none of the call shapes this file "
        f"tries ({failures}) — correct `_released` to the implemented "
        "signature"
    )


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A step definition declares how it is to be resolved
# (only the clause this change adds)
# ---------------------------------------------------------------------------


def test_a_step_reads_back_the_gate_it_starts_at_and_the_steps_it_waits_on() -> None:
    """Scenario: A step definition is read back with every declared attribute.

    ...AND the gate it starts at and the steps it waits on are read back
    as declared.

    Only that clause is asserted here; the rest of the scenario is
    reproduced unchanged from the served spec and is covered by
    `test_launch_playbook.py`.
    """
    declared = _step(
        identifier="listing.needs-both",
        starts_at_gate="listable",
        after_steps=("listing.photos-approved",),
    )
    dependency = _step(identifier="listing.photos-approved", gate="listable")

    playbook = _playbook(declared, dependency)
    (read_back,) = [
        step
        for step in playbook.authored_steps
        if step.identifier == "listing.needs-both"
    ]

    # SPECIFIED: read back as declared.
    assert read_back.starts_at_gate == "listable"
    assert tuple(read_back.after_steps) == ("listing.photos-approved",)


def test_a_step_declaring_neither_reads_back_as_declaring_neither() -> None:
    """Requirement statement: "Absent means the step is eligible from the
    launch's first gate", and "Empty means the step waits on no other
    step."

    SPECIFIED: the two absences are values, not a third state. DERIVED:
    that absence is spelled `None` for the gate and an empty tuple for
    the set — `design.md` fixes both ("`starts_at_gate: str | None`",
    "`after_steps: tuple[str, ...] = ()`"), `tasks.md` 1.1 repeats them.
    """
    step = _step(identifier="listing.says-nothing")

    assert step.starts_at_gate is None
    assert tuple(step.after_steps) == ()


def test_the_steps_a_step_waits_on_normalise_to_a_tuple() -> None:
    """`tasks.md` 1.1: `after_steps` is normalised "exactly as `assignees`
    is, so a caller handing a list still gets value semantics on a frozen
    dataclass".

    DERIVED assertion: this is a task rather than a scenario, and the
    spelling of the normalised type is not stated in the spec. It is
    asserted because a list stored unnormalised on a frozen dataclass is
    a mutable value shared between every reader of the definition.
    """
    step = _step(
        identifier="listing.normalises",
        after_steps=["listing.first", "listing.second"],
    )

    assert isinstance(step.after_steps, tuple)
    assert tuple(step.after_steps) == ("listing.first", "listing.second")


# ---------------------------------------------------------------------------
# ADDED Requirement: A step declares when it may start
# ---------------------------------------------------------------------------


def test_a_step_naming_neither_field_starts_immediately() -> None:
    """Scenario: A step naming neither field starts immediately.

    WHEN a launch begins at the first gate and its served playbook
    carries a step declaring no `starts_at_gate` and no `after_steps`
    THEN the launch has released that step, whatever gate the step
    belongs to.
    """
    # Deliberately at the *last* gate before the final one, so "whatever
    # gate the step belongs to" is actually exercised rather than
    # coincidentally satisfied by a step at the launch's own gate.
    step = _step(identifier="strategy.says-nothing", gate="phase-one-complete")
    playbook = _playbook(step)
    launch = _start(playbook)

    assert launch.current_gate == SPECIFIED_GATE_ORDER[0]
    # SPECIFIED: released, whatever gate it belongs to.
    assert _released(launch, playbook, step)


def test_a_step_is_not_released_before_its_start_gate() -> None:
    """Scenario: A step is not released before its start gate.

    WHEN a launch stands at `commit` and a step declares
    `starts_at_gate` of `listable`
    THEN the launch has not released that step.
    """
    step = _step(identifier="listing.waits-for-listable", starts_at_gate="listable")
    playbook = _playbook(step)
    launch = _start(playbook)

    assert launch.current_gate == "commit"
    assert not _released(launch, playbook, step)


def test_a_step_is_released_at_its_start_gate() -> None:
    """Scenario: A step is released at its start gate.

    WHEN a launch stands at `listable` and a step declares
    `starts_at_gate` of `listable`
    THEN the launch has released that step.
    """
    step = _step(identifier="listing.waits-for-listable", starts_at_gate="listable")
    playbook = _playbook(step)
    launch = _advance_to(_start(playbook), playbook, "listable")

    assert _released(launch, playbook, step)


def test_a_step_stays_released_once_its_gate_is_passed() -> None:
    """Scenario: A step stays released once its gate is passed.

    WHEN a launch stands at `stock-ready`, and an unresolved step
    declares `starts_at_gate` of `listable`
    THEN the launch has released that step, and it does not cease to be
    released by the launch moving on.

    This is the `>=`-not-`==` rule `design.md` singles out as "a
    one-character difference with a per-launch blast radius": under
    equality the 64 `listable` steps go dark the moment a launch reaches
    `stock-ready`.
    """
    step = _step(identifier="listing.waits-for-listable", starts_at_gate="listable")
    playbook = _playbook(step)
    launch = _advance_to(_start(playbook), playbook, "stock-ready")

    # SPECIFIED: the step is still unresolved — which is the whole point.
    assert launch.progress_for(step.identifier) is None
    assert _released(launch, playbook, step)


def test_a_step_may_start_before_the_gate_it_belongs_to() -> None:
    """Scenario: A step may start before the gate it belongs to.

    WHEN a launch stands at `listable` and a step belonging to gate
    `live` declares `starts_at_gate` of `listable`
    THEN the launch has released that step.

    SPECIFIED reason: `starts_at_gate` "SHALL name a gate, not a flag, so
    that a step may start at a gate earlier than the one it belongs to".
    """
    step = _step(
        identifier="ppc.keyword-buckets", gate="live", starts_at_gate="listable"
    )
    playbook = _playbook(step)
    launch = _advance_to(_start(playbook), playbook, "listable")

    assert _released(launch, playbook, step)


def test_every_named_dependency_must_be_resolved() -> None:
    """Scenario: Every named dependency must be resolved.

    WHEN a step names three steps in `after_steps`, and two of them are
    resolved
    THEN the launch has not released that step
    AND when the third is resolved, the launch has released it.

    SPECIFIED: `after_steps` is conjunctive — "the step is eligible only
    once **every** step it names is resolved".
    """
    first = _step(identifier="listing.first", gate="listable")
    second = _step(identifier="listing.second", gate="listable")
    third = _step(identifier="listing.third", gate="listable")
    depending = _step(
        identifier="listing.founded-on-three",
        gate="listable",
        after_steps=("listing.first", "listing.second", "listing.third"),
    )
    playbook = _playbook(first, second, third, depending)
    launch = _start(playbook)

    _satisfy(launch, playbook, "listing.first")
    _satisfy(launch, playbook, "listing.second")

    # SPECIFIED: two of three is not enough.
    assert not _released(launch, playbook, depending)

    _satisfy(launch, playbook, "listing.third")

    # SPECIFIED: and the third releases it.
    assert _released(launch, playbook, depending)


def test_both_fields_must_be_satisfied() -> None:
    """Scenario: Both fields must be satisfied.

    WHEN a step declares `starts_at_gate` of `listable` and an
    `after_steps` dependency that is resolved, and the launch stands at
    `commit`
    THEN the launch has not released that step.
    """
    dependency = _step(identifier="strategy.brief-signed", gate="commit")
    depending = _step(
        identifier="listing.needs-both",
        starts_at_gate="listable",
        after_steps=("strategy.brief-signed",),
    )
    playbook = _playbook(dependency, depending)
    launch = _start(playbook)

    _satisfy(launch, playbook, "strategy.brief-signed")

    assert launch.current_gate == "commit"
    # SPECIFIED: the satisfied dependency does not excuse the start gate.
    assert not _released(launch, playbook, depending)


def test_gate_opening_is_not_gated_on_release() -> None:
    """Scenario: Gate opening is not gated on release.

    WHEN a gate's blocking step is unresolved and the launch has not
    released it
    THEN the gate's condition is unsatisfied, exactly as if the step were
    released and unresolved.

    SPECIFIED reason: "gating a blocking condition on release would open
    a gate over work that had merely not been asked for yet". Asserted as
    the advance being refused, which is how the aggregate expresses an
    unsatisfied condition.

    The blocking step here belongs to `commit` and starts at `order`,
    which the load rules refuse — a start gate later than the step's own
    gate. So the shape the scenario needs is reached the other way: the
    launch stands at the *first* gate while a blocking step of that gate
    waits on an unresolved dependency at the same gate.
    """
    dependency = _step(identifier="strategy.brief-signed", gate="commit")
    blocking = _step(
        identifier="strategy.commitment-agreed",
        gate="commit",
        blocking=True,
        after_steps=("strategy.brief-signed",),
    )
    playbook = _playbook(dependency, blocking)
    launch = _start(playbook)
    launch.approve_gate("commit", _approval())

    # SPECIFIED (premise): the launch has not released the blocking step.
    assert not _released(launch, playbook, blocking)

    with pytest.raises(LaunchError) as refused:
        launch.advance_gate(playbook)

    # DERIVED: `LaunchError` as the rejection signal, taken from
    # `test_launch_gate_advance.py`. The scenario fixes only that the
    # condition is unsatisfied; the step being named in the refusal is
    # what makes this assertion about the blocking condition rather than
    # about any refusal at all.
    assert "strategy.commitment-agreed" in str(refused.value)
    assert launch.current_gate == "commit"


def test_release_does_not_consult_the_date() -> None:
    """Scenario: Release does not consult the date.

    WHEN the same launch and step are evaluated on two different dates
    with no change to the launch's gate or recorded outcomes
    THEN the step's release is the same on both.

    Asserted structurally rather than by moving a clock: the predicate is
    called twice with no date supplied at all, and its signature is
    checked to accept none. `tasks.md` 3.4 asks for exactly this — "verify
    by inspection that the predicate takes no `date`, `datetime` or clock
    argument and performs no I/O".

    DERIVED: the parameter-name probe. What is SPECIFIED is that the
    answer cannot differ between two passes differing only in when they
    ran; a predicate with no way to learn the date cannot.
    """
    import inspect

    step = _step(identifier="listing.waits-for-listable", starts_at_gate="listable")
    playbook = _playbook(step)
    launch = _advance_to(_start(playbook), playbook, "listable")

    first = _released(launch, playbook, step)
    second = _released(launch, playbook, step)
    assert first == second

    predicate = next(
        getattr(launch, name)
        for name in _PREDICATE_NAMES
        if callable(getattr(launch, name, None))
    )
    parameters = inspect.signature(predicate).parameters
    clocklike = [
        name
        for name in parameters
        if any(
            word in name.lower() for word in ("date", "now", "today", "clock", "as_of")
        )
    ]
    # SPECIFIED: release consults no clock.
    assert not clocklike, (
        f"the release predicate takes {clocklike}, so its answer can differ "
        "between two passes that differ only in when they ran"
    )


# ---------------------------------------------------------------------------
# ADDED Requirement: A dependency nobody is still owed is satisfied vacuously
# ---------------------------------------------------------------------------


def test_retiring_a_step_releases_what_waited_on_it() -> None:
    """Scenario: Retiring a step releases what waited on it.

    WHEN a step's only `after_steps` dependency is retired, and the
    launch has reached that step's start gate
    THEN the launch has released the step.

    SPECIFIED reason: a step that is not `active` "is not part of the
    launch's obligations at all", and "the alternative would freeze every
    dependent step of every launch in flight as the consequence of a
    routine authoring action".
    """
    retired = _step(
        identifier="listing.photos-approved",
        gate="listable",
        status=StepStatus.RETIRED,
    )
    depending = _step(
        identifier="listing.copy-written",
        gate="listable",
        after_steps=("listing.photos-approved",),
    )
    playbook = _playbook(retired, depending)
    launch = _start(playbook)

    # SPECIFIED (premise): nothing was ever recorded for the retired step.
    assert launch.progress_for("listing.photos-approved") is None
    assert _released(launch, playbook, depending)


def test_a_dependency_re_classified_prohibited_tactic_holds_nothing_back() -> None:
    """Scenario: A dependency re-classified prohibited-tactic holds nothing
    back.

    WHEN a step named in another's `after_steps` is re-authored to the
    `prohibited-tactic` hazard, and the launch has reached the depending
    step's start gate
    THEN the launch has released the depending step, without waiting for
    an outcome the classification means the system will decline to
    produce.

    `design.md` calls this "the case that would be missed": an
    implementation judging it by the hazard's permitted terminal outcomes
    would wait for a `Refused` that, for a `human` step, no surface
    produces.
    """
    prohibited = _step(
        identifier="reviews.purchase-ring",
        gate="listable",
        hazard=Hazard.PROHIBITED_TACTIC,
    )
    depending = _step(
        identifier="listing.copy-written",
        gate="listable",
        after_steps=("reviews.purchase-ring",),
    )
    playbook = _playbook(prohibited, depending)
    launch = _start(playbook)

    assert launch.progress_for("reviews.purchase-ring") is None
    assert _released(launch, playbook, depending)


def test_an_identifier_naming_no_step_holds_nothing_back() -> None:
    """Scenario: An identifier naming no step holds nothing back.

    WHEN a step's `after_steps` names an identifier no step in the set
    carries, and the launch has reached that step's start gate
    THEN the launch has released the step.
    """
    depending = _step(
        identifier="listing.copy-written",
        gate="listable",
        after_steps=("listing.no-such-step",),
    )
    playbook = _playbook(depending)
    launch = _start(playbook)

    assert _released(launch, playbook, depending)


def test_a_mix_of_active_and_retired_dependencies_still_holds() -> None:
    """Scenario: A mix of active and retired dependencies.

    WHEN a step names two dependencies, one retired and one `active` and
    unresolved
    THEN the launch has not released the step, the `active` one still
    holding it.

    The discriminating case: an implementation excusing the whole set
    once any member is excused passes every scenario above and fails
    here.
    """
    retired = _step(
        identifier="listing.photos-approved",
        gate="listable",
        status=StepStatus.RETIRED,
    )
    still_owed = _step(identifier="listing.copy-approved", gate="listable")
    depending = _step(
        identifier="listing.copy-written",
        gate="listable",
        after_steps=("listing.photos-approved", "listing.copy-approved"),
    )
    playbook = _playbook(retired, still_owed, depending)
    launch = _start(playbook)

    assert not _released(launch, playbook, depending)

    _satisfy(launch, playbook, "listing.copy-approved")

    assert _released(launch, playbook, depending)


# ---------------------------------------------------------------------------
# ADDED Requirement: The stored step set declares when its steps start
# (only the scenario stated about the predicate)
# ---------------------------------------------------------------------------


def test_an_activated_draft_does_not_become_eligible_everywhere() -> None:
    """Scenario: An activated draft does not become eligible everywhere.

    WHEN a `draft` step carrying a start gate is activated while launches
    stand at earlier gates
    THEN those launches have not released it.

    SPECIFIED reason: this is why the obligation covers the authored set
    and not merely the served one — "a draft left declaring nothing
    becomes, on the day it is activated, a step eligible in every launch
    at once".

    The activation is modelled as the step set the launch is served
    changing status, which is what an authoring write produces; the write
    path itself is covered in
    `tests/unit/launch/application/test_step_dependency_preconditions.py`.
    """
    as_draft = _step(
        identifier="ppc.never-keywords",
        gate="live",
        status=StepStatus.DRAFT,
        starts_at_gate="order",
    )
    drafted = _playbook(as_draft)
    launch = _start(drafted)

    activated = _step(
        identifier="ppc.never-keywords",
        gate="live",
        status=StepStatus.ACTIVE,
        starts_at_gate="order",
    )
    served = _playbook(activated)

    assert launch.current_gate == "commit"
    # SPECIFIED: activation does not make it eligible in a launch that has
    # not reached its start gate.
    assert not _released(launch, served, activated)
