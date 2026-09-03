"""Tests for gate conditions on the `LaunchPlaybook` domain model.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the ADDED requirements *A gate carries authored metric conditions*
and *Gate conditions unify step obligations and metric conditions*, at the
domain level — construction of `Gate`/`LaunchPlaybook` is the smallest
unit that can observe them, matching where the earlier pass placed the
coherence scenarios. The same two metric-condition scenarios are also
exercised through the real loader and the shipped `v1` file in
`tests/unit/launch/infrastructure/test_playbook_loader_completion.py`.

At the time of writing `commerce_ops.launch` does not exist (the change
renames `products` to `launch` as its first commit — `design.md`
Decision 6), so every test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

DERIVED / unresolved project questions (see the manifest at the change
root):

- `commerce_ops.launch.domain.launch_playbook` as the module (the renamed
  `products` module), re-exporting the names the earlier pass already
  used, plus `StepObligation`.
- `StepObligation(step_id)` with attribute `step_id`, per `proposal.md`.
  Since `replace-metric-conditions-with-steps` it is the *only* kind of
  gate condition: a gate carries no authored conditions of its own, so
  the tests that read them back retired with the type.
- `LaunchPlaybook.conditions_for_gate(gate_id)` returning an iterable of
  `GateCondition`, per `tasks.md` 4.2; "each identifiable as its kind" is
  read as an `isinstance` check against the two condition types.
"""

from __future__ import annotations

from typing import Any, Final

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepObligation,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import step as _build_step


def _any_discipline() -> Discipline:
    """Return some `Discipline` member, asserting nothing about which.

    Constructing a `StepDefinition` needs a discipline value; nothing in
    this file depends on which one (the discipline set itself is covered
    in `tests/unit/shared/domain/test_discipline.py`).
    """
    return next(iter(Discipline))


def specified_gates() -> tuple[Gate, ...]:
    """The eight gates in the specified order.

    A gate carries its identifier, position and opening mode and nothing
    else — `replace-metric-conditions-with-steps` removed the authored
    metric conditions it used to carry, so there is no longer anything to
    author onto one.
    """
    return tuple(
        Gate(
            identifier=identifier,
            position=position,
            opening=_opening_for(identifier),
        )
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(
        **{
            "identifier": "inventory.fulfillable-units",
            "gate": "stock-ready",
            **overrides,
        }
    )


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires; the `hold.` namespace tells fillers apart."""
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
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


def _playbook(
    *,
    gates: tuple[Gate, ...] | None = None,
    steps: tuple[StepDefinition, ...] = (),
) -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=specified_gates() if gates is None else gates,
        steps=_fill(steps),
    )


# SPECIFIED example threshold description, taken from `design.md`
# Decision 2's own worked example.
STOCK_THRESHOLD: Final = "60-80 fulfillable units, excluding Vine"


# ---------------------------------------------------------------------------
# Requirement: A gate carries authored metric conditions
# ---------------------------------------------------------------------------


def test_a_blocking_step_appears_as_a_step_obligation() -> None:
    """Scenario: A blocking step appears as a step obligation.

    WHEN a step definition declares gate `listable` and is marked
    blocking, and the `listable` gate's conditions are read
    THEN the conditions include a step obligation naming that step's
    identifier.
    """
    step = _step(
        identifier="listing.a-plus-content",
        gate="listable",
        blocking=True,
    )
    playbook = _playbook(steps=(step,))

    conditions = list(playbook.conditions_for_gate("listable"))

    # SPECIFIED: one step obligation per blocking step at the gate,
    # naming that step's identifier.
    obligations = [c for c in conditions if isinstance(c, StepObligation)]
    assert [obligation.step_id for obligation in obligations] == [
        "listing.a-plus-content"
    ]


def test_a_non_blocking_step_produces_no_condition() -> None:
    """Scenario: A non-blocking step produces no condition.

    WHEN a step definition declares gate `listable` and is not marked
    blocking
    THEN the `listable` gate's conditions include no obligation for that
    step.
    """
    step = _step(
        identifier="listing.a-plus-content",
        gate="listable",
        blocking=False,
    )
    playbook = _playbook(steps=(step,))

    conditions = list(playbook.conditions_for_gate("listable"))

    # SPECIFIED: "A non-blocking step SHALL NOT appear among a gate's
    # conditions" — the gate waits on nothing beyond the holding filler
    # the gate-holding floor requires, and never on the step under test.
    obligations = [c for c in conditions if isinstance(c, StepObligation)]
    assert [obligation.step_id for obligation in obligations] == ["hold.listable"]
    assert len(conditions) == 1


def test_conditions_are_scoped_to_the_asked_gate() -> None:
    """Requirement statement: obligations are derived from "the blocking
    step definitions attached to the gate".

    DERIVED from the requirement statement rather than a named scenario:
    a blocking step at one gate must not surface as a condition of
    another — without this, `conditions_for_gate` returning every
    condition in the playbook would pass the scenarios above.
    """
    listable_step = _step(
        identifier="listing.a-plus-content",
        gate="listable",
        blocking=True,
    )
    playbook = _playbook(
        gates=specified_gates(),
        steps=(listable_step,),
    )

    live_conditions = list(playbook.conditions_for_gate("live"))
    listable_conditions = list(playbook.conditions_for_gate("listable"))

    # `live` carries exactly its holding filler's obligation — never the
    # listable step's obligation.
    assert [c.step_id for c in live_conditions if isinstance(c, StepObligation)] == [
        "hold.live"
    ]
    assert len(live_conditions) == 1
    assert len(listable_conditions) == 1
    assert isinstance(listable_conditions[0], StepObligation)
    assert listable_conditions[0].step_id == "listing.a-plus-content"
