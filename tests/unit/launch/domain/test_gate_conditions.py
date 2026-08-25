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
  used, plus `MetricCondition`, `StepObligation`, and
  `Gate.metric_conditions` per `tasks.md` 4.1-4.2.
- `MetricCondition(metric_id, threshold)` with attributes `metric_id` and
  `threshold` — `proposal.md` writes the constructor exactly so; the spec
  calls the second element a "threshold description", so
  `threshold_description` is the recorded alternative spelling.
- `StepObligation(step_id)` with attribute `step_id`, per `proposal.md`.
- `LaunchPlaybook.conditions_for_gate(gate_id)` returning an iterable of
  `GateCondition`, per `tasks.md` 4.2; "each identifiable as its kind" is
  read as an `isinstance` check against the two condition types.
"""

from __future__ import annotations

from typing import Any, Final

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    MetricCondition,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepObligation,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MetricId

# SPECIFIED (main spec, unchanged): the eight gates, in this order.
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

# SPECIFIED (main spec, unchanged): the four confirmation gates.
CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


def _any_discipline() -> Discipline:
    """Return some `Discipline` member, asserting nothing about which.

    Constructing a `StepDefinition` needs a discipline value; nothing in
    this file depends on which one (the discipline set itself is covered
    in `tests/unit/shared/domain/test_discipline.py`).
    """
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def specified_gates(
    metric_conditions: dict[str, tuple[MetricCondition, ...]] | None = None,
) -> tuple[Gate, ...]:
    """The eight gates in the specified order, optionally carrying authored
    metric conditions on named gates.

    DERIVED: `metric_conditions` as a keyword on `Gate` defaulting to
    empty, per `tasks.md` 4.1 ("give `Gate` an authored `metric_conditions`
    tuple defaulting to empty"). Gates not named in the mapping are built
    without the keyword at all, so the default itself is exercised.
    """
    authored = metric_conditions or {}
    gates = []
    for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1):
        if identifier in authored:
            gates.append(
                Gate(
                    identifier=identifier,
                    position=position,
                    opening=_opening_for(identifier),
                    metric_conditions=authored[identifier],
                )
            )
        else:
            gates.append(
                Gate(
                    identifier=identifier,
                    position=position,
                    opening=_opening_for(identifier),
                )
            )
    return tuple(gates)


def _step(**overrides: Any) -> StepDefinition:
    """Build a valid `StepDefinition`, overriding named attributes."""
    attributes: dict[str, Any] = {
        "identifier": "inventory.fulfillable-units",
        "name": "Work this step asks for",
        "gate": "stock-ready",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "needs_confirmation": False,
        "hazard": Hazard.NONE,
        "automation_brief": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


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
        automation_brief="Held until the automated check reports green.",
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


def test_a_gates_metric_conditions_are_read_back() -> None:
    """Scenario: A gate's metric conditions are read back.

    WHEN a gate authored with a metric condition is read from a loaded
    playbook
    THEN the condition reports its metric identifier and its threshold
    description.
    """
    condition = MetricCondition(MetricId("units-fulfillable"), STOCK_THRESHOLD)
    playbook = _playbook(
        gates=specified_gates({"stock-ready": (condition,)}),
    )

    gates = {gate.identifier: gate for gate in playbook.gates}
    (read_back,) = gates["stock-ready"].metric_conditions

    # SPECIFIED: the condition reports its metric identifier and its
    # threshold description.
    assert read_back.metric_id == MetricId("units-fulfillable")
    assert read_back.threshold == STOCK_THRESHOLD


def test_a_gate_with_no_metric_conditions_is_valid() -> None:
    """Scenario: A gate with no metric conditions is valid.

    WHEN a gate authored with no metric conditions is read
    THEN it reports an empty set of metric conditions.
    """
    playbook = _playbook()

    for gate in playbook.gates:
        # SPECIFIED: zero authored conditions is valid, and reads back as
        # an empty collection — not as an error and not as an absent
        # attribute.
        assert list(gate.metric_conditions) == []


def test_a_gate_may_carry_more_than_one_metric_condition() -> None:
    """Requirement statement: "zero or more authored metric conditions".

    DERIVED from the requirement statement rather than a named scenario:
    the two scenarios cover one and zero; "or more" is the remaining
    clause, without which an implementation capping conditions at one
    would pass both.
    """
    conditions = (
        MetricCondition(MetricId("sales-velocity"), "~10 units/day sustained"),
        MetricCondition(MetricId("organic-share"), "organic share above 40%"),
    )
    playbook = _playbook(
        gates=specified_gates({"phase-one-complete": conditions}),
    )

    gates = {gate.identifier: gate for gate in playbook.gates}
    assert len(gates["phase-one-complete"].metric_conditions) == 2


# ---------------------------------------------------------------------------
# Requirement: Gate conditions unify step obligations and metric conditions
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


def test_authored_metric_conditions_appear_alongside_derived_obligations() -> None:
    """Scenario: Authored metric conditions appear alongside derived
    obligations.

    WHEN a gate has both a blocking step attached and an authored metric
    condition
    THEN reading its conditions returns both, each identifiable as its
    kind.
    """
    condition = MetricCondition(MetricId("units-fulfillable"), STOCK_THRESHOLD)
    step = _step(
        identifier="inventory.stock-checked-in",
        gate="stock-ready",
        blocking=True,
    )
    playbook = _playbook(
        gates=specified_gates({"stock-ready": (condition,)}),
        steps=(step,),
    )

    conditions = list(playbook.conditions_for_gate("stock-ready"))

    # SPECIFIED: both kinds are returned, each identifiable as its kind.
    obligations = [c for c in conditions if isinstance(c, StepObligation)]
    metrics = [c for c in conditions if isinstance(c, MetricCondition)]
    assert len(conditions) == 2
    assert [o.step_id for o in obligations] == ["inventory.stock-checked-in"]
    assert [m.metric_id for m in metrics] == [MetricId("units-fulfillable")]


def test_conditions_are_scoped_to_the_asked_gate() -> None:
    """Requirement statement: obligations are derived from "the blocking
    step definitions attached to the gate".

    DERIVED from the requirement statement rather than a named scenario:
    a blocking step at one gate must not surface as a condition of
    another, and an authored condition on one gate must not surface on
    another — without this, `conditions_for_gate` returning every
    condition in the playbook would pass the three scenarios above.
    """
    condition = MetricCondition(MetricId("units-fulfillable"), STOCK_THRESHOLD)
    listable_step = _step(
        identifier="listing.a-plus-content",
        gate="listable",
        blocking=True,
    )
    playbook = _playbook(
        gates=specified_gates({"stock-ready": (condition,)}),
        steps=(listable_step,),
    )

    live_conditions = list(playbook.conditions_for_gate("live"))
    listable_conditions = list(playbook.conditions_for_gate("listable"))

    # `live` carries exactly its holding filler's obligation — never the
    # listable step's obligation or the stock-ready metric condition.
    assert [c.step_id for c in live_conditions if isinstance(c, StepObligation)] == [
        "hold.live"
    ]
    assert len(live_conditions) == 1
    assert len(listable_conditions) == 1
    assert isinstance(listable_conditions[0], StepObligation)
    assert listable_conditions[0].step_id == "listing.a-plus-content"
