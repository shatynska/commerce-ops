"""What a step definition declares, after the redesign.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers the MODIFIED requirement *A step definition declares how it is to
be resolved* — both scenarios:

- *A step definition is read back with every declared attribute*, whose
  attribute list this change rewrites (`name`, `kind`, confirmation and
  `status` are required; `description`, `assignees`, brief, handler and
  provenance are present only if authored; `binding` and `execution` are
  gone),
- *Steps can be selected by gate and by scope*, which now answers the
  **served** set.

`test_step_lifecycle_status.py` covers the served/authored split itself;
what this file adds is that the by-scope query answers it too, which the
lifecycle requirement states but no scenario of it exercises.

**Level.** `LaunchPlaybook` construction and its queries.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from typing import Any, Final

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    GateOpening,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
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

PERSON_A: Final = "prs_01HQ8Z6M4A"


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


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
        "gate": "listable",
        "discipline": _any_discipline(),
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
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        status=StepStatus.ACTIVE,
    )


def _hold_ids(steps: tuple[StepDefinition, ...]) -> set[str]:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    return {f"hold.{gate}" for gate in SPECIFIED_GATE_ORDER if gate not in held}


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    fillers = tuple(_hold(gate.removeprefix("hold.")) for gate in _hold_ids(steps))
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step definition declares how it is to be resolved
# ---------------------------------------------------------------------------


def test_a_step_definition_is_read_back_with_every_declared_attribute() -> None:
    """Scenario: A step definition is read back with every declared
    attribute.

    WHEN a step definition is read from a loaded playbook
    THEN its identifier, name, gate, discipline, scope, timing anchor,
    blocking flag, kind, confirmation flag, status, and hazard
    classification are all present.
    """
    step = _step(
        identifier="listing.title-conforms",
        name="Conform the title to the style guide",
        gate="listable",
        scope=Scope.MARKET,
        timing_anchor=OffsetAnchor(days=-7),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        hazard=Hazard.COMPLIANCE_OBLIGATION,
    )

    (read_back,) = [
        candidate
        for candidate in _playbook(steps=(step,)).steps_for_gate("listable")
        if candidate.identifier == "listing.title-conforms"
    ]

    # SPECIFIED: every one of the ten required attributes is present.
    assert read_back.identifier == "listing.title-conforms"
    assert read_back.name == "Conform the title to the style guide"
    assert read_back.gate == "listable"
    assert read_back.discipline is _any_discipline()
    assert read_back.scope is Scope.MARKET
    assert read_back.timing_anchor == OffsetAnchor(days=-7)
    assert read_back.blocking is True
    assert read_back.kind is StepKind.HUMAN
    assert read_back.status is StepStatus.ACTIVE
    assert read_back.hazard is Hazard.COMPLIANCE_OBLIGATION


def test_unauthored_optional_attributes_are_absent() -> None:
    """Scenario: A step definition is read back with every declared
    attribute — the second half.

    ...AND its description, assignees, handler, confirmer and
    provenance reference are present only if authored.

    Constructed omitting each of the five, so the test exercises the
    defaults rather than restating them. The hazard default is asserted
    alongside, since the same construction omits it and the requirement
    says it is `none` when the author declares nothing.
    """
    step = StepDefinition(
        identifier="strategy.phase-one-criteria",
        name="Write the phase-one exit criteria down",
        gate="commit",
        discipline=_any_discipline(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-90),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
    )

    (read_back,) = [
        candidate
        for candidate in _playbook(steps=(step,)).steps_for_gate("commit")
        if candidate.identifier == "strategy.phase-one-criteria"
    ]

    # SPECIFIED: present only if authored.
    assert read_back.description is None
    assert tuple(read_back.assignees) == ()
    assert read_back.confirmer is None
    assert read_back.handler is None
    assert read_back.provenance is None
    # SPECIFIED: hazard defaults to `none`.
    assert read_back.hazard is Hazard.NONE


def test_the_removed_fields_are_gone_from_the_step() -> None:
    """Requirement statement, by way of `proposal.md`'s Impact: the step
    "loses `binding` and `execution`", and `Binding` and `ExecutionMode`
    are deleted.

    A field left in place "for compatibility" would leave the admin form,
    the repository mapping and the seed free to keep writing it, and the
    lesson-cannot-block rule free to come back — which is the state this
    change removes rather than deprecates.
    """
    step = _step(assignees=(PERSON_A,))

    assert not hasattr(step, "binding")
    assert not hasattr(step, "execution")

    import commerce_ops.launch.domain.launch_playbook as module

    assert not hasattr(module, "Binding"), (
        "Binding still exists: `proposal.md` removes it, and its one rule with it"
    )
    assert not hasattr(module, "ExecutionMode"), (
        "ExecutionMode still exists: it is replaced by `StepKind` plus an "
        "independent confirmation flag"
    )


def test_steps_can_be_selected_by_gate_and_by_scope() -> None:
    """Scenario: Steps can be selected by gate and by scope.

    WHEN the playbook is queried for the steps attached to a given gate
    THEN exactly the step definitions declaring that gate are returned
    AND the same holds when querying by scope.

    Both queries answer the **served** set (the lifecycle requirement),
    so the draft below is returned by neither.
    """
    product_listable = _step(
        identifier="sourcing.unit-economics",
        gate="listable",
        scope=Scope.PRODUCT,
        blocking=True,
    )
    market_listable = _step(
        identifier="listing.a-plus-content", gate="listable", scope=Scope.MARKET
    )
    market_live = _step(
        identifier="rank.indexation-confirmed",
        gate="live",
        scope=Scope.MARKET,
        blocking=True,
    )
    market_draft = _step(
        identifier="listing.draft-work",
        gate="listable",
        scope=Scope.MARKET,
        status=StepStatus.DRAFT,
    )

    steps = (product_listable, market_listable, market_live, market_draft)
    playbook = _playbook(steps=steps)

    # SPECIFIED: exactly the served steps declaring that gate.
    assert {step.identifier for step in playbook.steps_for_gate("listable")} == {
        "sourcing.unit-economics",
        "listing.a-plus-content",
    }
    assert {step.identifier for step in playbook.steps_for_gate("live")} == {
        "rank.indexation-confirmed"
    }

    # SPECIFIED: the same holds when querying by scope.
    assert {step.identifier for step in playbook.steps_with_scope(Scope.MARKET)} == {
        "listing.a-plus-content",
        "rank.indexation-confirmed",
    }
    assert {step.identifier for step in playbook.steps_with_scope(Scope.PRODUCT)} == {
        "sourcing.unit-economics",
        *_hold_ids(steps),
    }
