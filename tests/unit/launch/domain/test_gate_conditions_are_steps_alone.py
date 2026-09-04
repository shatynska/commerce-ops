"""A gate's conditions, once metric conditions are gone.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-playbook/spec.md`

Covers the ADDED requirement *A gate's conditions are the obligations of
its blocking steps* — all three scenarios:

- *A blocking step appears as a step obligation*,
- *A non-blocking step produces no condition*,
- *A gate waits on nothing but its steps* (new with this change).

The first two carry the same words as two scenarios of the REMOVED
requirement *Gate conditions unify step obligations and metric
conditions*, and are covered today by
`tests/unit/launch/domain/test_gate_conditions.py`. They are re-derived
here rather than accounted against that file because it imports
`MetricCondition` at module scope: once `tasks.md` 4.1 deletes the type,
every test in it fails at import, including the two whose subject
survives. Nothing here edits that file — it is recorded in
`test-manifest.md` as an obsolete-test candidate for the scenarios whose
subject the change removes, and the two surviving scenarios are covered
by this file instead.

## Level

`LaunchPlaybook` construction and `conditions_for_gate`. A gate's
conditions are computed from the step set with no I/O, so the domain is
the smallest unit that observes them — the level
`test_gate_conditions.py` already holds for the same requirement.

## What is fixed, and what is INVENTED

Fixed by the artifacts:

- `StepObligation(step_id)` with attribute `step_id`, and
  `LaunchPlaybook.conditions_for_gate(gate_id)` — both already
  implemented and read the same way by `test_gate_conditions.py`.
- That `MetricCondition`, `_AUTHORED_METRIC_CONDITIONS` and the
  `GateCondition` union are deleted from `launch_playbook.py`
  (`tasks.md` 4.1), and that `conditions_for_gate` returns step
  obligations only (`tasks.md` 4.2).
- That `Gate` no longer carries authored conditions: the REMOVED
  requirement *A gate carries authored metric conditions*.

INVENTED: nothing beyond the fixture shapes this directory's sibling
files already use (the eight gates, the confirmation set, and a blocking
`hold.<gate>` filler per gate so the gate-holding floor is satisfied).

## Expected first-run state

`framework_gates()` still authors metric conditions on three gates and
`MetricCondition` still exists, so
`test_a_gate_carries_no_condition_of_any_other_kind` and
`test_the_removed_condition_types_are_gone` are expected to **fail on a
wrong value** — the code is there and behaves as it did before the
change. The two obligation scenarios are expected to **pass on their
first run**: their subject is unchanged by this delta and already
implemented. Per `ai-toolkit:testing` that is not the alarm state — the
alarm is a pass where no implementation exists, and here one does.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

from typing import Any

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepObligation,
    StepStatus,
    framework_gates,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.playbook import playbook as _build_playbook
from tests.support.steps import hold as _build_hold
from tests.support.steps import step as _build_step


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _gates() -> tuple[Gate, ...]:
    """The **framework's own** gates, not a fixture standing in for them.

    Deliberate: `launch_playbook.py` authors metric conditions on three
    real gates today (`stock-ready`, `phase-one-complete`, `graduated`),
    so a fixture that built its own gates from `Gate(identifier=...,
    position=..., opening=...)` would carry none and the scenario below
    would pass against a framework that still authors them. Reading the
    framework's gates is what makes "a gate waits on nothing but its
    steps" a claim about what ships.

    A locally-built gate is still constructed once, in
    `test_the_removed_condition_types_are_gone`, to assert what a gate's
    own declaration is: its sequence position and its opening mode, and
    nothing else.
    """
    return tuple(framework_gates())


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": "inventory.fulfillable-units",
            "gate": "stock-ready",
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    return _build_hold(
        gate,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
    )


def _fill(steps: tuple[StepDefinition, ...]) -> tuple[StepDefinition, ...]:
    held = {step.gate for step in steps if step.blocking}
    return (
        *steps,
        *(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return _build_playbook(
        *_fill(steps),
        version="steps-alone-v1",
        filler=_hold,
    )


# ---------------------------------------------------------------------------
# Requirement (ADDED): A gate's conditions are the obligations of its
# blocking steps
# ---------------------------------------------------------------------------


def test_a_blocking_step_appears_as_a_step_obligation() -> None:
    """Scenario: A blocking step appears as a step obligation.

    WHEN a step definition declares gate `listable` and is marked
    blocking, and the `listable` gate's conditions are read
    THEN the conditions include a step obligation naming that step's
    identifier.
    """
    step = _step(identifier="listing.a-plus-content", gate="listable", blocking=True)

    conditions = list(_playbook(steps=(step,)).conditions_for_gate("listable"))

    # SPECIFIED: one obligation per blocking step definition attached to
    # the gate, naming that step's identifier.
    assert [condition.step_id for condition in conditions] == ["listing.a-plus-content"]


def test_a_non_blocking_step_produces_no_condition() -> None:
    """Scenario: A non-blocking step produces no condition.

    WHEN a step definition declares gate `listable` and is not marked
    blocking
    THEN the `listable` gate's conditions include no obligation for that
    step.
    """
    step = _step(identifier="listing.a-plus-content", gate="listable", blocking=False)

    conditions = list(_playbook(steps=(step,)).conditions_for_gate("listable"))

    # SPECIFIED: the non-blocking step raises no obligation. The gate
    # waits on the holding filler alone, which the floor requires.
    assert [condition.step_id for condition in conditions] == ["hold.listable"]


def test_a_gate_carries_no_condition_of_any_other_kind() -> None:
    """Scenario: A gate waits on nothing but its steps.

    WHEN any gate's conditions are read
    THEN every condition returned is a step obligation naming a blocking
    step of that gate.

    Read over all eight gates rather than one, because the requirement is
    stated over "any gate" and because `launch_playbook.py` today authors
    conditions on three of them (`stock-ready`, `phase-one-complete`,
    `graduated`) and on no other — a check confined to one gate could
    pass against a set that still authors conditions elsewhere.
    """
    step = _step(identifier="inventory.stock-checked-in", blocking=True)
    playbook = _playbook(steps=(step,))

    for gate in SPECIFIED_GATE_ORDER:
        conditions = list(playbook.conditions_for_gate(gate))
        blocking_here = {
            definition.identifier
            for definition in playbook.steps_for_gate(gate)
            if definition.blocking
        }
        # SPECIFIED: every condition returned is a step obligation...
        for condition in conditions:
            assert isinstance(condition, StepObligation), (
                f"the {gate} gate carries a condition that is not a step "
                f"obligation: {condition!r}"
            )
            # SPECIFIED: ...naming a blocking step of that gate.
            assert condition.step_id in blocking_here, (
                f"the {gate} gate carries an obligation naming "
                f"{condition.step_id!r}, which is not a blocking step of it"
            )
        # SPECIFIED: one obligation per blocking step, so the collection
        # is exactly the gate's blocking steps and nothing besides.
        assert {condition.step_id for condition in conditions} == blocking_here


def test_the_removed_condition_types_are_gone() -> None:
    """Requirement statement: "A gate SHALL carry no condition of any
    other kind", and the REMOVED requirement *A gate carries authored
    metric conditions*.

    `tasks.md` 4.1 deletes `MetricCondition`, `_AUTHORED_METRIC_CONDITIONS`
    and the `GateCondition` union. Asserted as absence rather than left
    implicit because a type left in place "for compatibility" leaves the
    repository mapping, the admin surface and `framework_gates()` free to
    keep constructing one — which is the state this change removes rather
    than deprecates, and which the scenario above would not detect while
    no gate happened to author one.
    """
    import commerce_ops.launch.domain.launch_playbook as module

    for name in ("MetricCondition", "GateCondition", "_AUTHORED_METRIC_CONDITIONS"):
        assert not hasattr(module, name), (
            f"`{name}` still exists in launch_playbook.py: the delta removes "
            "the authored metric condition rather than deprecating it "
            "(`tasks.md` 4.1)"
        )

    # SPECIFIED: a gate declares its position and its opening mode, and
    # nothing a step could state instead — asserted over the framework's
    # own gates and over one built here, so neither a shipped gate nor
    # the type itself keeps the field.
    built = Gate(identifier="listable", position=3, opening=_opening_for("listable"))
    for gate in (*_gates(), built):
        assert not hasattr(gate, "metric_conditions"), (
            "`Gate` still carries `metric_conditions`; the REMOVED "
            "requirement takes authored conditions off the gate"
        )
