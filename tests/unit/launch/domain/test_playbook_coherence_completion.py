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
coherence rule. The rule that once rejected an empty metric-condition
threshold retired with metric conditions themselves; what remains here
is exercised through the same construction.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


def specified_gates() -> tuple[Gate, ...]:
    """The eight gates in the specified order.

    A gate carries its identifier, position and opening mode and nothing
    else — `replace-metric-conditions-with-steps` removed the authored
    conditions it used to carry, so there is nothing to author onto one.
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
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
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


# ---------------------------------------------------------------------------
# New rule: a malformed metric condition is rejected
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): the new faults participate in the aggregated
# all-faults error
# ---------------------------------------------------------------------------


def test_two_distinct_faults_are_reported_together() -> None:
    """Scenario: Multiple violations are reported together (as revised).

    WHEN a playbook contains two distinct coherence violations
    THEN loading fails once, and the failure names both.

    The two faults have been re-derived twice, and for the same reason
    each time: what this test is about is the *aggregation*, not either
    fault, so a rule's removal costs it a fixture and never its subject.
    A blocking `lesson` step went with `binding` in `redesign-step-fields`;
    an empty metric-condition threshold went with metric conditions
    themselves in `replace-metric-conditions-with-steps`. Both are now
    surviving step rules — a `prohibited-tactic` step marked as blocking,
    and a `human` step carrying a handler — chosen because they are
    independent of each other, which is what makes reporting *both*
    evidence of aggregation rather than of one check running.
    """
    prohibited_blocking = _step(
        identifier="ppc.consider-exact-match-first",
        hazard=Hazard.PROHIBITED_TACTIC,
        blocking=True,
    )
    human_with_handler = _step(
        identifier="listing.write-the-title",
        kind=StepKind.HUMAN,
        handler="listing.subcategory_advisor",
    )

    # SPECIFIED: it fails *once* — a single raised error carrying both
    # faults, not one error per fault.
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(prohibited_blocking, human_with_handler))

    message = str(caught.value)
    # SPECIFIED: the failure names both offending steps.
    assert "ppc.consider-exact-match-first" in message
    assert "listing.write-the-title" in message


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): a coherent playbook loads — over the completed
# surface
# ---------------------------------------------------------------------------


def test_a_coherent_playbook_with_the_completed_surface_loads() -> None:
    """Scenario: A coherent playbook loads (as revised).

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    Exercised over the surface this change completes: a blocking step and
    a non-blocking one, each the permitted side of a rule this delta
    touches. The authored metric condition that stood alongside them went
    with metric conditions themselves; a blocking step on `stock-ready`
    now *is* how that gate's threshold is held.
    """
    steps = (
        _step(
            identifier="inventory.stock-checked-in",
            gate="stock-ready",
            blocking=True,
        ),
        _step(
            identifier="ppc.consider-exact-match-first",
            gate="ignition",
            blocking=False,
        ),
    )

    playbook = _playbook(steps=steps)

    # SPECIFIED: it loads successfully and exposes its gates and step
    # definitions.
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)
    assert {step.identifier for step in playbook.steps} == {
        "inventory.stock-checked-in",
        "ppc.consider-exact-match-first",
        *_hold_ids(steps),
    }
