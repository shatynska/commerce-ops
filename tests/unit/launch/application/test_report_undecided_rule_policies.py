"""Tests for the undecided-rule-policy report use case.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the ADDED requirement *Undecided rule policies are reported*.

DERIVED / unresolved project questions (see the manifest at the change
root):

- `report_undecided_rule_policies` imported from
  `commerce_ops.launch.application` — its public-surface placement is
  fixed by `tasks.md` 5.2; the *call shape* is not. **Q7 resolved during
  implementation**: the use case takes a loaded `LaunchPlaybook`, not a
  path, so the caller loads.
- Report rows expose `identifier`, `gate`, `discipline`, and `execution`
  — the four fields `tasks.md` 5.1 names, with `execution` spelled as
  `StepDefinition` already spells it.

**Fixtures repaired by `move-playbook-steps-to-postgres`** (I-3 in that
change's test manifest): the playbooks these tests feed the report were
originally loaded from YAML files through the retired `playbook_loader`;
they are now constructed directly through the domain — the use case
under test never cared where its playbook came from, and no assertion
changed. Every gate carries a blocking holding filler (the gate-holding
floor that change promotes to a construction rule), each automated with
a decided rule policy so no filler can appear in the report.
"""

from __future__ import annotations

from typing import Any, Final

from commerce_ops.launch.application import report_undecided_rule_policies
from commerce_ops.launch.domain.launch_playbook import (
    Binding,
    ExecutionMode,
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
)
from commerce_ops.shared.domain.discipline import Discipline

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
        "description": "Work this step asks for",
        "gate": "listable",
        "discipline": next(iter(Discipline)),
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
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        execution=ExecutionMode.AUTOMATED,
        rule_policy="Held until the automated check reports green.",
    )


def _playbook(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


_DECIDED: Final = _step(
    identifier="price.buy-box-check",
    gate="live",
    discipline=Discipline("price"),
    scope=Scope.MARKET,
    timing_anchor=OffsetAnchor(days=0),
    execution=ExecutionMode.AUTOMATED,
    rule_policy="Buy Box share is at or above 90% over a rolling week.",
)

_UNDECIDED: Final = _step(
    identifier="strategy.phase-one-criteria",
    gate="commit",
    discipline=Discipline("strategy"),
    timing_anchor=OffsetAnchor(days=-90),
    execution=ExecutionMode.HUMAN_ATTESTED,
    rule_policy=None,
)


def test_steps_without_a_rule_policy_are_listed() -> None:
    """Scenario: Steps without a rule policy are listed.

    WHEN the report is requested against a playbook containing one step
    with a rule policy and one without
    THEN exactly the step without a rule policy is reported, with its
    identifier, gate, discipline, and execution mode.
    """
    playbook = _playbook(steps=(_DECIDED, _UNDECIDED))

    rows = list(report_undecided_rule_policies(playbook))

    (row,) = rows
    assert row.identifier == "strategy.phase-one-criteria"
    assert row.gate == "commit"
    assert row.discipline is Discipline("strategy")
    assert row.execution is ExecutionMode.HUMAN_ATTESTED


def test_a_fully_decided_playbook_reports_nothing() -> None:
    """Scenario: A fully decided playbook reports nothing.

    WHEN the report is requested against a playbook in which every step
    carries a rule policy
    THEN the report is empty.
    """
    decided_everywhere = _step(
        identifier="strategy.phase-one-criteria",
        gate="commit",
        discipline=Discipline("strategy"),
        timing_anchor=OffsetAnchor(days=-90),
        execution=ExecutionMode.HUMAN_ATTESTED,
        rule_policy="Phase-one exit criteria are written down and agreed.",
    )
    playbook = _playbook(steps=(_DECIDED, decided_everywhere))

    assert list(report_undecided_rule_policies(playbook)) == []
