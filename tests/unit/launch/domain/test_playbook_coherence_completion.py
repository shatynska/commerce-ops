"""Tests for the two coherence faults this change adds at load time.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the two rules the MODIFIED requirement *An incoherent playbook is
rejected at load time* adds — a `lesson`-binding step marked blocking, and
a gate's authored metric condition with an empty threshold description —
plus their participation in the all-faults aggregated error and the
coherent-playbook scenario over the completed surface. The requirement's
pre-existing rules (gate sequence, opening modes, duplicate identifiers,
unknown gates, automation without a rule, prohibited-tactic blocking) are
unchanged by this delta and remain covered by
`tests/unit/products/domain/test_launch_playbook.py`, which task 1.2
relocates mechanically.

At the time of writing `commerce_ops.launch` does not exist, so every
test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

DERIVED level choice: both new faults are exercised through
`LaunchPlaybook` construction, where `tasks.md` 4.3 places them
("extend load-time coherence ... both reported in the aggregated
all-faults error") and where the earlier pass placed every other
coherence rule. This assumes `MetricCondition` itself admits an empty
threshold description so that the playbook-level fault naming the *gate*
is reachable — the reading the scenario's "an error naming the gate
carrying it" fixes. If the implementation instead rejects the empty
description at `MetricCondition` construction, these fixtures error
before the assertion runs (failure state 3 in `ai-toolkit:testing`) and
the divergence between that design and the scenario's gate-naming clause
must be reported, not absorbed.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    MetricCondition,
    OffsetAnchor,
    Scope,
    StepDefinition,
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

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def specified_gates(
    metric_conditions: dict[str, tuple[MetricCondition, ...]] | None = None,
) -> tuple[Gate, ...]:
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
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "description": "Work this step asks for",
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-7),
        "binding": Binding.FRAMEWORK,
        "blocking": False,
        "execution": ExecutionMode.HUMAN_ATTESTED,
        "hazard": Hazard.NONE,
        "rule_policy": None,
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
        execution=ExecutionMode.AUTOMATED,
        rule_policy="Held until the automated check reports green.",
    )


def _hold_ids(steps: tuple[StepDefinition, ...]) -> set[str]:
    held = {step.gate for step in steps if step.blocking}
    return {f"hold.{gate}" for gate in SPECIFIED_GATE_ORDER if gate not in held}


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


# ---------------------------------------------------------------------------
# New rule: a lesson cannot block a gate
# ---------------------------------------------------------------------------


def test_a_lesson_step_marked_blocking_is_rejected() -> None:
    """Scenario: A lesson cannot block a gate.

    WHEN a step definition's binding is `lesson` and it is marked as
    blocking its gate
    THEN loading fails with an error naming that step.
    """
    step = _step(
        identifier="ppc.consider-exact-match-first",
        binding=Binding.LESSON,
        blocking=True,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "ppc.consider-exact-match-first" in str(caught.value)


def test_a_non_blocking_lesson_step_is_accepted() -> None:
    """Scenario: A lesson cannot block a gate (permitted side).

    The rule forbids the *combination* — advice that blocks a gate. A
    lesson that does not block must load, or the rule would outlaw advice
    itself; without this, an implementation rejecting every lesson step
    would pass the rejection test alone. Same permitted-side pattern the
    earlier pass applied to the prohibited-tactic rule.
    """
    step = _step(
        identifier="ppc.consider-exact-match-first",
        binding=Binding.LESSON,
        blocking=False,
    )

    # A lesson can never block, so `listable` also carries its holding
    # filler; the read-back targets the step under test.
    read_back = next(
        candidate
        for candidate in _playbook(steps=(step,)).steps_for_gate("listable")
        if candidate.identifier == "ppc.consider-exact-match-first"
    )

    assert read_back.binding is Binding.LESSON
    assert read_back.blocking is False


# ---------------------------------------------------------------------------
# New rule: a malformed metric condition is rejected
# ---------------------------------------------------------------------------


def test_a_metric_condition_with_an_empty_threshold_is_rejected() -> None:
    """Scenario: A malformed metric condition is rejected.

    WHEN a playbook authors a metric condition whose threshold description
    is empty
    THEN loading fails with an error naming the gate carrying it.
    """
    empty_threshold = MetricCondition(MetricId("units-fulfillable"), "")
    gates = specified_gates({"stock-ready": (empty_threshold,)})

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=gates)

    # SPECIFIED: the error names the gate carrying the condition.
    assert "stock-ready" in str(caught.value)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): the new faults participate in the aggregated
# all-faults error
# ---------------------------------------------------------------------------


def test_the_two_new_faults_are_reported_together() -> None:
    """Scenario: Multiple violations are reported together (as revised).

    WHEN a playbook contains two distinct coherence violations
    THEN loading fails once, and the failure names both.

    Exercised with the two violations this change adds — a blocking
    lesson step and an empty metric-condition threshold — so that the new
    rules are established as participants in the aggregation, not
    early-exit checks; the earlier pass already covers aggregation of the
    pre-existing rules.
    """
    lesson_blocking = _step(
        identifier="ppc.consider-exact-match-first",
        binding=Binding.LESSON,
        blocking=True,
    )
    empty_threshold = MetricCondition(MetricId("units-fulfillable"), "")
    gates = specified_gates({"stock-ready": (empty_threshold,)})

    # SPECIFIED: it fails *once* — a single raised error carrying both
    # faults, not one error per fault.
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(gates=gates, steps=(lesson_blocking,))

    message = str(caught.value)
    # SPECIFIED: the failure names both — the offending step and the
    # offending gate.
    assert "ppc.consider-exact-match-first" in message
    assert "stock-ready" in message


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): a coherent playbook loads — over the completed
# surface
# ---------------------------------------------------------------------------


def test_a_coherent_playbook_with_the_completed_surface_loads() -> None:
    """Scenario: A coherent playbook loads (as revised).

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    Exercised over the surface this change completes: an authored metric
    condition with a non-empty threshold, a non-blocking lesson step, and
    a blocking framework step — each the permitted side of a rule this
    delta touches.
    """
    condition = MetricCondition(
        MetricId("units-fulfillable"), "60-80 fulfillable units, excluding Vine"
    )
    steps = (
        _step(
            identifier="inventory.stock-checked-in",
            gate="stock-ready",
            binding=Binding.FRAMEWORK,
            blocking=True,
        ),
        _step(
            identifier="ppc.consider-exact-match-first",
            gate="ignition",
            binding=Binding.LESSON,
            blocking=False,
        ),
    )

    playbook = _playbook(
        gates=specified_gates({"stock-ready": (condition,)}),
        steps=steps,
    )

    # SPECIFIED: it loads successfully and exposes its gates and step
    # definitions.
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)
    assert {step.identifier for step in playbook.steps} == {
        "inventory.stock-checked-in",
        "ppc.consider-exact-match-first",
        *_hold_ids(steps),
    }
