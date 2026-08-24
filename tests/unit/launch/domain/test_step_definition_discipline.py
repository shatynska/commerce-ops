"""Tests for the discipline-carrying `StepDefinition` (`launch-playbook`).

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the ADDED requirement *Discipline is drawn from the shared
vocabulary* and the MODIFIED requirement *A step definition declares how
it is to be resolved* — the ownership attribute is now `discipline`,
drawn from the shared vocabulary, where it was `track` with a locally
defined value set. The predecessor tests asserting `.track` and importing
`Track` (`tests/unit/products/domain/test_launch_playbook.py`) are
recorded as obsolete-candidates in the manifest; per the delta, "there
SHALL be exactly one name for it", so `track` must not survive anywhere.

At the time of writing `commerce_ops.launch` does not exist, so every
test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

DERIVED: module path and constructor keywords, per the manifest. The
unrecognised-discipline scenario is checked at `StepDefinition`
construction, mirroring where the predecessor pass placed the
unrecognised-track check (`tasks.md` 3.1: the same fault, with its
message renamed) — an unrecognised discipline needs no playbook context.
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
    OffsetAnchor,
    Scope,
    StepDefinition,
    WindowAnchor,
)
from commerce_ops.shared.domain.discipline import Discipline

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


def specified_gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


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


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    return LaunchPlaybook(version="test-v1", gates=specified_gates(), steps=steps)


# ---------------------------------------------------------------------------
# Requirement: Discipline is drawn from the shared vocabulary
# ---------------------------------------------------------------------------


def test_a_discipline_outside_the_shared_vocabulary_is_rejected() -> None:
    """Scenario: Discipline is restricted to the shared vocabulary.

    WHEN a step definition declares a discipline outside the shared
    vocabulary's set
    THEN loading fails with an error naming the step and the unrecognised
    discipline.
    """
    with pytest.raises(InvalidPlaybookError) as caught:
        _step(
            identifier="listing.mystery-discipline",
            discipline="not-a-recognised-discipline",
        )

    # SPECIFIED: the error names the step and the unrecognised discipline.
    message = str(caught.value)
    assert "listing.mystery-discipline" in message
    assert "not-a-recognised-discipline" in message


def test_each_shared_discipline_is_accepted_on_a_step() -> None:
    """Scenario: Discipline is restricted to the shared vocabulary
    (permitted side).

    The named scenario only forbids a discipline outside the shared set;
    this checks the permitted complement — an implementation rejecting
    every discipline would still pass the rejection test alone. Iterates
    the shared vocabulary itself so this test tracks the shared set
    rather than restating it (the set's content is covered in
    `tests/unit/shared/domain/test_discipline.py`).
    """
    for member in Discipline:
        step = _step(identifier=f"step.{member.value}-example", discipline=member)

        (read_back,) = _playbook(steps=(step,)).steps_for_gate(step.gate)

        # SPECIFIED: the owning discipline is one the shared vocabulary
        # defines, and reads back as declared.
        assert read_back.discipline is member


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step definition declares how it is to be resolved
# ---------------------------------------------------------------------------


def test_step_definition_is_read_back_with_every_declared_attribute() -> None:
    """Scenario: A step definition is read back with every declared
    attribute.

    WHEN a step definition is read from a loaded playbook
    THEN its identifier, gate, discipline, scope, timing anchor, binding,
    blocking flag, execution mode, and hazard classification are all
    present
    AND its rule policy and provenance reference are present only if
    authored.
    """
    discipline = _any_discipline()
    anchor = WindowAnchor(start=28, end=55)
    step = _step(
        identifier="inventory.fulfillable-units",
        gate="stock-ready",
        discipline=discipline,
        scope=Scope.MARKET,
        timing_anchor=anchor,
        binding=Binding.FRAMEWORK,
        blocking=True,
        execution=ExecutionMode.HUMAN_ATTESTED,
        hazard=Hazard.COMPLIANCE_OBLIGATION,
        rule_policy="At least 60 fulfillable units checked in.",
        provenance="lp.inventory.040",
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("stock-ready")

    # SPECIFIED: each of the nine mandatory attributes is present and is
    # what was declared — the ownership attribute under its one name,
    # `discipline`.
    assert read_back.identifier == "inventory.fulfillable-units"
    assert read_back.gate == "stock-ready"
    assert read_back.discipline is discipline
    assert read_back.scope is Scope.MARKET
    assert read_back.timing_anchor == anchor
    assert read_back.binding is Binding.FRAMEWORK
    assert read_back.blocking is True
    assert read_back.execution is ExecutionMode.HUMAN_ATTESTED
    assert read_back.hazard is Hazard.COMPLIANCE_OBLIGATION
    # SPECIFIED: rule policy and provenance are present when authored.
    assert read_back.rule_policy == "At least 60 fulfillable units checked in."
    assert read_back.provenance == "lp.inventory.040"
    # SPECIFIED ("there SHALL be exactly one name for it"): the former
    # name does not survive on the loaded form.
    assert not hasattr(read_back, "track")


def test_unauthored_optional_attributes_are_absent() -> None:
    """Scenario: A step definition is read back with every declared
    attribute (unauthored optionals).

    ...AND its rule policy and provenance reference are present only if
    authored — constructed here without either, and without a hazard, so
    the defaults are exercised rather than restated.
    """
    step = StepDefinition(
        identifier="strategy.undecided",
        description="Work this step asks for",
        gate="commit",
        discipline=_any_discipline(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-90),
        binding=Binding.FRAMEWORK,
        blocking=False,
        execution=ExecutionMode.HUMAN_ATTESTED,
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("commit")

    # SPECIFIED: present only if authored.
    assert read_back.rule_policy is None
    assert read_back.provenance is None
    # SPECIFIED (main spec, unchanged): hazard defaults to `none`.
    assert read_back.hazard is Hazard.NONE


def test_steps_can_be_selected_by_gate_and_by_scope() -> None:
    """Scenario: Steps can be selected by gate and by scope.

    WHEN the playbook is queried for the steps attached to a given gate
    THEN exactly the step definitions declaring that gate are returned
    AND the same holds when querying by scope.

    Re-derived here against the renamed module; the predecessor test
    covers the same behaviour through the pre-rename module path and
    `track` fixtures.
    """
    product_listable = _step(
        identifier="sourcing.unit-economics", gate="listable", scope=Scope.PRODUCT
    )
    market_listable = _step(
        identifier="listing.a-plus-content", gate="listable", scope=Scope.MARKET
    )
    market_live = _step(
        identifier="rank.indexation-confirmed", gate="live", scope=Scope.MARKET
    )

    playbook = _playbook(steps=(product_listable, market_listable, market_live))

    # SPECIFIED: exactly the steps declaring that gate — no more, no fewer.
    assert {step.identifier for step in playbook.steps_for_gate("listable")} == {
        "sourcing.unit-economics",
        "listing.a-plus-content",
    }
    assert {step.identifier for step in playbook.steps_for_gate("live")} == {
        "rank.indexation-confirmed"
    }
    assert list(playbook.steps_for_gate("graduated")) == []

    # SPECIFIED: the same holds when querying by scope.
    assert {step.identifier for step in playbook.steps_with_scope(Scope.MARKET)} == {
        "listing.a-plus-content",
        "rank.indexation-confirmed",
    }
    assert {step.identifier for step in playbook.steps_with_scope(Scope.PRODUCT)} == {
        "sourcing.unit-economics"
    }
