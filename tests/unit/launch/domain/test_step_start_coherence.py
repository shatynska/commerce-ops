"""Load-time coherence for the two start declarations (`launch-playbook`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-playbook/spec.md`:

- ADDED *A step cannot start after the gate it belongs to* — all six
  scenarios.
- ADDED *Step dependencies form an acyclic graph that cannot deadlock a
  gate* — all eight scenarios.

The MODIFIED requirement *An incoherent playbook is rejected against each
step's status* adds four bullets to its rule list and reproduces every
one of its fourteen scenarios unchanged; those are covered by the
existing files in this directory and are accounted for as such in the
manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`. The
two new rules' own aggregation is asserted here instead, since it is the
new rules that could be reported one at a time.

## Level

`LaunchPlaybook` construction. Both requirements say these are
**load-time** rules — "a function of the step set and the code-owned
framework gates alone" — and construction is the smallest unit that can
observe a rejection, matching where every existing coherence test in
this directory sits.

## INVENTED, with correction points

- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition` (field names SPECIFIED; keyword form INVENTED).
  Correction point: `_step`.
- `InvalidPlaybookError` as the rejection, taken unchanged from every
  other coherence test here.
- That a fault "names" a step, a gate or a value is read as that string
  appearing in the rendered error. Correction point: `_message`.

## Expected first-run state

Neither field exists, so every test here is expected to fail on an
**absent target** — a `TypeError` from the constructor — which
establishes absence and nothing about these assertions. The three
*accepted* scenarios would additionally pass vacuously if the fields
existed and no rule did; each therefore also asserts that the step it
built is actually in the loaded set, so "loads" cannot be satisfied by a
playbook that dropped it.

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
    InvalidPlaybookError,
    LaunchPlaybook,
    StepDefinition,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates
from tests.support.steps import step as _build_step

#: SPECIFIED: "the final gate", the one every consumer stands down at.
FINAL_GATE: Final = SPECIFIED_GATE_ORDER[-1]

A_DISCIPLINE: Final = next(iter(Discipline))
LAUNCH_DATE: Final = date(2027, 4, 15)
RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, declaring neither start field.

    Fillers must never be the reason a rule fires: they name no
    dependency, and their start gate is absent, which every rule here
    accepts.
    """
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="coherence-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _message(caught: pytest.ExceptionInfo[InvalidPlaybookError]) -> str:
    """Everything a rejection says, however it carries it.

    INVENTED: faults may be a tuple on the error rather than only text in
    its rendering, so both are folded into one haystack.
    """
    rendered = str(caught.value)
    faults = getattr(caught.value, "faults", None)
    if faults is not None:
        rendered = " ".join([rendered, *(str(fault) for fault in faults)])
    return rendered


def _identifiers(playbook: LaunchPlaybook) -> set[str]:
    return {step.identifier for step in playbook.authored_steps}


# ---------------------------------------------------------------------------
# ADDED Requirement: A step cannot start after the gate it belongs to
# ---------------------------------------------------------------------------


def test_a_start_gate_of_the_final_gate_is_rejected() -> None:
    """Scenario: A start gate of the final gate is rejected.

    WHEN a playbook carries a step whose `starts_at_gate` is `graduated`
    THEN the playbook is rejected, with a fault naming the step.

    SPECIFIED reason: "Every consumer that acts on a step stands down
    once a launch reaches the final gate ... so a step released only
    there is released into a state in which nothing will ever act on it."
    """
    step = _step(identifier="listing.starts-at-the-end", starts_at_gate=FINAL_GATE)

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    reported = _message(caught)
    # SPECIFIED: the fault names the step.
    assert "listing.starts-at-the-end" in reported
    # SPECIFIED: it says the final gate is not a gate at which work
    # begins, "so that an author correcting it is not left to infer the
    # rule from a refusal". DERIVED: read as the gate being named.
    assert FINAL_GATE in reported


def test_a_final_gate_step_may_not_start_at_its_own_gate() -> None:
    """Scenario: A final-gate step may not start at its own gate.

    WHEN a playbook carries a step whose gate is `graduated` and whose
    `starts_at_gate` is `graduated`
    THEN the playbook is rejected, notwithstanding that the start gate is
    not later than the step's own gate.

    The discriminating case for an implementation that checked only the
    position comparison: `pos(graduated) <= pos(graduated)` passes it.
    """
    step = _step(
        identifier="strategy.graduation-review",
        gate=FINAL_GATE,
        starts_at_gate=FINAL_GATE,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    assert "strategy.graduation-review" in _message(caught)


def test_a_final_gate_step_starting_earlier_is_accepted() -> None:
    """Scenario: A final-gate step starting earlier is accepted.

    WHEN a playbook carries a step whose gate is `graduated` and whose
    `starts_at_gate` is `phase-one-complete`
    THEN the playbook loads, the two-gate rule binding the default rather
    than the load.

    SPECIFIED: "The two-gate rule is a **default and not a refusal**" —
    an author who names a one-gate window "is taken to have meant it".
    """
    step = _step(
        identifier="strategy.graduation-review",
        gate=FINAL_GATE,
        starts_at_gate="phase-one-complete",
    )

    playbook = _playbook(step)

    # SPECIFIED: it loads — and the step is in the set, so "loads" cannot
    # be satisfied by a playbook that quietly dropped it.
    assert "strategy.graduation-review" in _identifiers(playbook)


def test_a_start_gate_later_than_the_steps_own_gate_is_rejected() -> None:
    """Scenario: A start gate later than the step's own gate is rejected.

    WHEN a playbook carries a step whose gate is `listable` and whose
    `starts_at_gate` is `live`
    THEN the playbook is rejected, with a fault naming the step, its gate
    and its start gate.
    """
    step = _step(
        identifier="listing.starts-too-late", gate="listable", starts_at_gate="live"
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    reported = _message(caught)
    # SPECIFIED: the fault names the step, its gate and its start gate.
    assert "listing.starts-too-late" in reported
    assert "listable" in reported
    assert "live" in reported


def test_a_start_gate_equal_to_the_steps_own_gate_is_accepted() -> None:
    """Scenario: A start gate equal to the step's own gate is accepted.

    WHEN a playbook carries a step whose gate is `listable` and whose
    `starts_at_gate` is `listable`
    THEN the playbook loads.

    This is the backfill's own default, so a rule stated as a strict
    inequality would refuse the whole stored set.
    """
    step = _step(
        identifier="listing.starts-at-its-own-gate",
        gate="listable",
        starts_at_gate="listable",
    )

    playbook = _playbook(step)

    assert "listing.starts-at-its-own-gate" in _identifiers(playbook)


def test_an_unknown_start_gate_is_rejected() -> None:
    """Scenario: An unknown start gate is rejected.

    WHEN a playbook carries a step whose `starts_at_gate` names no gate
    in the framework's sequence
    THEN the playbook is rejected, with a fault naming the step and the
    unknown value.
    """
    step = _step(identifier="listing.starts-nowhere", starts_at_gate="no-such-gate")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    reported = _message(caught)
    assert "listing.starts-nowhere" in reported
    assert "no-such-gate" in reported


def test_a_non_blocking_step_with_a_late_start_gate_is_refused_too() -> None:
    """Requirement statement: the rule is stated "for a step that does not
    block" as well — "it is merely incoherent ... so it is overdue from
    the moment it appears. Both are refused, because a state with no
    sensible reading is better made unrepresentable than documented."

    Stated in the requirement's prose rather than in a scenario of its
    own, and asserted because an implementation reading the deadlock
    argument alone would naturally scope this rule to `blocking` steps.
    """
    step = _step(
        identifier="listing.not-blocking-but-late",
        gate="listable",
        blocking=False,
        starts_at_gate="live",
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    assert "listing.not-blocking-but-late" in _message(caught)


# ---------------------------------------------------------------------------
# ADDED Requirement: Step dependencies form an acyclic graph that cannot
# deadlock a gate
# ---------------------------------------------------------------------------


def test_a_cycle_is_rejected() -> None:
    """Scenario: A cycle is rejected.

    WHEN a playbook carries step A naming B in `after_steps`, B naming C,
    and C naming A
    THEN the playbook is rejected, with a fault naming the steps forming
    the cycle.
    """
    a = _step(identifier="listing.a", gate="listable", after_steps=("listing.b",))
    b = _step(identifier="listing.b", gate="listable", after_steps=("listing.c",))
    c = _step(identifier="listing.c", gate="listable", after_steps=("listing.a",))

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(a, b, c)

    reported = _message(caught)
    # SPECIFIED: the fault names the steps forming it — all three.
    assert "listing.a" in reported
    assert "listing.b" in reported
    assert "listing.c" in reported


def test_a_step_naming_itself_is_rejected() -> None:
    """Scenario: A step naming itself is rejected.

    WHEN a playbook carries a step naming its own identifier in
    `after_steps`
    THEN the playbook is rejected.

    SPECIFIED: "A step naming itself SHALL be rejected as the cycle it
    is" — a one-length cycle, not a separate rule.
    """
    step = _step(
        identifier="listing.waits-on-itself",
        gate="listable",
        after_steps=("listing.waits-on-itself",),
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(step)

    assert "listing.waits-on-itself" in _message(caught)


def test_a_blocking_step_depending_on_a_later_starting_step_is_rejected() -> None:
    """Scenario: A blocking step depending on a later-starting step is
    rejected.

    WHEN a `blocking` step at gate `listable` names a step whose
    `starts_at_gate` is `live`
    THEN the playbook is rejected, with a fault naming both steps and the
    two gates.
    """
    depended_on = _step(identifier="ppc.late-input", gate="live", starts_at_gate="live")
    blocking = _step(
        identifier="listing.holds-listable",
        gate="listable",
        blocking=True,
        after_steps=("ppc.late-input",),
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(depended_on, blocking)

    reported = _message(caught)
    # SPECIFIED: the fault names the blocking step, the depended-on step
    # and the two gates.
    assert "listing.holds-listable" in reported
    assert "ppc.late-input" in reported
    assert "listable" in reported
    assert "live" in reported


def test_a_blocking_step_may_depend_on_a_later_gates_step_that_starts_early() -> None:
    """Scenario: A blocking step may depend on a later gate's step that
    starts early.

    WHEN a `blocking` step at gate `listable` names a step belonging to
    gate `live` that declares no `starts_at_gate`
    THEN the playbook loads, the dependency being resolvable before
    `listable` closes.

    This is the case `design.md` says a rule stated over the depended-on
    step's *own* gate would wrongly forbid: "Same `B.gate`, opposite
    outcomes."
    """
    depended_on = _step(identifier="ppc.early-input", gate="live")
    blocking = _step(
        identifier="listing.holds-listable",
        gate="listable",
        blocking=True,
        after_steps=("ppc.early-input",),
    )

    playbook = _playbook(depended_on, blocking)

    assert {"ppc.early-input", "listing.holds-listable"} <= _identifiers(playbook)


def test_a_deadlock_two_hops_away_is_rejected() -> None:
    """Scenario: A deadlock two hops away is rejected.

    WHEN a `blocking` step at gate `listable` names a step belonging to
    `graduated` that starts at `commit`, and that step names a third
    whose `starts_at_gate` is `live`
    THEN the playbook is rejected, notwithstanding that each link
    satisfies the rule against its immediate successor.

    The discriminating case for a pairwise implementation: both pairwise
    checks pass, and the launch still strands at `listable`.
    """
    middle = _step(
        identifier="strategy.middle",
        gate=FINAL_GATE,
        starts_at_gate="commit",
        after_steps=("ppc.last",),
    )
    last = _step(identifier="ppc.last", gate="live", starts_at_gate="live")
    blocking = _step(
        identifier="listing.holds-listable",
        gate="listable",
        blocking=True,
        after_steps=("strategy.middle",),
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(middle, last, blocking)

    reported = _message(caught)
    assert "listing.holds-listable" in reported
    assert "ppc.last" in reported


def test_the_traversal_does_not_stop_at_a_step_that_is_not_active() -> None:
    """Scenario: The traversal does not stop at a step that is not active.

    WHEN a cycle among three steps includes one that is `retired`
    THEN the playbook is rejected, the retired step's edges being
    followed like any other's.

    SPECIFIED reason: skipping such edges "would make these rules
    disagree with themselves across a status change: a cycle ... that a
    set was refused for would become loadable by retiring one step in
    it".
    """
    a = _step(identifier="listing.a", gate="listable", after_steps=("listing.b",))
    b = _step(
        identifier="listing.b",
        gate="listable",
        status=StepStatus.RETIRED,
        after_steps=("listing.c",),
    )
    c = _step(identifier="listing.c", gate="listable", after_steps=("listing.a",))

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(a, b, c)

    reported = _message(caught)
    assert "listing.a" in reported
    assert "listing.b" in reported
    assert "listing.c" in reported


def test_a_non_blocking_step_is_not_held_to_the_deadlock_rule() -> None:
    """Scenario: A non-blocking step is not held to the deadlock rule.

    WHEN a step that does not block its gate depends on a step whose
    start gate is later than its own gate
    THEN the playbook loads, no gate being held by the depending step.
    """
    depended_on = _step(identifier="ppc.late-input", gate="live", starts_at_gate="live")
    depending = _step(
        identifier="listing.does-not-block",
        gate="listable",
        blocking=False,
        after_steps=("ppc.late-input",),
    )

    playbook = _playbook(depended_on, depending)

    assert {"ppc.late-input", "listing.does-not-block"} <= _identifiers(playbook)


def test_a_step_may_depend_on_one_starting_later_than_the_launch_has_reached() -> None:
    """Scenario: A step may depend on one starting later than the launch
    has reached.

    WHEN a non-blocking step whose start gate the launch has reached
    names a dependency whose start gate the launch has not reached
    THEN the playbook loads, and the depending step is unreleased while
    its due period may pass.

    SPECIFIED: this is "accepted rather than prevented" — the overdue
    mark it produces "is true on its own terms ... What it signals is an
    authored schedule that does not hang together".

    The release half is asserted through the predicate's own probe rather
    than duplicated: `test_step_start_release.py` owns the predicate's
    call shape, and this file needs only the answer.
    """
    depended_on = _step(identifier="ppc.late-input", gate="live", starts_at_gate="live")
    depending = _step(
        identifier="listing.starts-now-waits-later",
        gate="listable",
        blocking=False,
        starts_at_gate="commit",
        after_steps=("ppc.late-input",),
    )

    playbook = _playbook(depended_on, depending)

    # SPECIFIED: it loads.
    assert "listing.starts-now-waits-later" in _identifiers(playbook)

    launch, _ = Launch.start(
        product_id=ProductId(str(uuid.uuid4())),
        playbook=playbook,
        launch_date=LAUNCH_DATE,
    )
    predicate = next(
        (
            getattr(launch, name)
            for name in (
                "has_released",
                "released",
                "is_released",
                "releases",
                "has_started",
                "step_released",
            )
            if callable(getattr(launch, name, None))
        ),
        None,
    )
    if predicate is None:
        pytest.fail(
            "`Launch` exposes no release predicate, so the second half of "
            "this scenario — that the depending step is unreleased — cannot "
            "be observed"
        )
    # SPECIFIED: and the depending step is unreleased.
    assert not predicate(playbook, depending)


def test_the_two_new_rules_are_reported_alongside_every_other_fault() -> None:
    """MODIFIED Requirement: An incoherent playbook is rejected against each
    step's status — "The failure SHALL report **every** fault found".

    `tasks.md` 2.6 asks for this specifically: the new rules must be
    "reported alongside every other fault of one load attempt, never one
    at a time". The scenario *Multiple violations are reported together*
    is reproduced unchanged and covered elsewhere; what is new is that
    the start rules join that aggregation, which no existing test can
    observe.
    """
    unknown_gate = _step(
        identifier="listing.starts-nowhere", starts_at_gate="no-such-gate"
    )
    nameless = _step(identifier="listing.nameless", name="   ")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(unknown_gate, nameless)

    reported = _message(caught)
    # SPECIFIED: one failure names both.
    assert "listing.starts-nowhere" in reported
    assert "listing.nameless" in reported
