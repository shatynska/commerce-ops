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

from typing import Any

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    InvalidPlaybookError,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
    WindowAnchor,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for
from tests.support.steps import step as _build_step


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def specified_gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires; `hold.` namespace so assertions can tell fillers
    from the steps under test."""
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


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="test-v1", gates=specified_gates(), steps=(*steps, *fillers)
    )


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
        step = _step(
            identifier=f"step.{member.value}-example",
            discipline=member,
            blocking=True,
        )

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
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        hazard=Hazard.COMPLIANCE_OBLIGATION,
        provenance="lp.inventory.040",
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("stock-ready")

    # SPECIFIED: each mandatory attribute is present and is
    # what was declared — the ownership attribute under its one name,
    # `discipline`.
    assert read_back.identifier == "inventory.fulfillable-units"
    assert read_back.gate == "stock-ready"
    assert read_back.discipline is discipline
    assert read_back.scope is Scope.MARKET
    assert read_back.timing_anchor == anchor
    assert read_back.blocking is True
    assert read_back.kind is StepKind.HUMAN
    assert read_back.status is StepStatus.ACTIVE
    assert read_back.hazard is Hazard.COMPLIANCE_OBLIGATION
    # SPECIFIED: provenance is present when authored.
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
        name="Work this step asks for",
        gate="commit",
        discipline=_any_discipline(),
        scope=Scope.PRODUCT,
        timing_anchor=OffsetAnchor(days=-90),
        blocking=True,
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
    )

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("commit")

    # SPECIFIED: present only if authored.
    assert read_back.confirmer is None
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

    steps = (product_listable, market_listable, market_live)
    playbook = _playbook(steps=steps)

    # SPECIFIED: exactly the steps declaring that gate — no more, no fewer.
    assert {step.identifier for step in playbook.steps_for_gate("listable")} == {
        "sourcing.unit-economics",
        "listing.a-plus-content",
    }
    assert {step.identifier for step in playbook.steps_for_gate("live")} == {
        "rank.indexation-confirmed"
    }
    # The gate-holding floor forbids a stepless gate in a coherent
    # playbook, so an undeclared gate returns exactly its holding filler.
    assert {step.identifier for step in playbook.steps_for_gate("graduated")} == {
        "hold.graduated"
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
