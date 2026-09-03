"""A sole assignee cannot also be the step's confirmer — a load-time rule.

Derived strictly from the delta spec:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`

Covers the new bullet and scenario the ADDED requirement *An incoherent
playbook is rejected against its steps' status and shape* adds over its
predecessor *...against each step's status*:

- bullet: "a step definition names exactly one assignee who is also its
  confirmer"
- Scenario: *A sole assignee who is also the confirmer fails to load*

and the corresponding paragraph of the ADDED requirement *A step names
who confirms an automated result*: "Unlike the two [members] preconditions
above, this is a **load-time coherence rule**: it is a pure function of
the step set's own `assignees` and `confirmer` fields, needs no members to
evaluate ... a playbook already carrying this shape SHALL fail to load,
not merely fail its next write."

Every other bullet and scenario of *An incoherent playbook is rejected
against its steps' status and shape* carries over from its predecessor
requirement unchanged in substance (the automation-brief bullet and its
scenario are dropped, and this is the one bullet added in their place);
those are accounted for in `test-manifest.md` against the existing
coverage in `tests/unit/launch/domain/test_launch_playbook.py` and
`tests/unit/launch/domain/test_playbook_coherence_by_status.py`, which
this file does not duplicate.

The write-time expression of the same rule — *A sole assignee cannot also
be the confirmer* (write) and *A confirmer among several assignees is not
rejected* — is covered at the application level in
`tests/unit/launch/application/test_step_confirmer_preconditions.py`,
matching the precedent `test_step_automation_brief_and_handler.py` /
`test_step_status_transitions.py` already set for a rule tested at both
load and write.

**Level.** `LaunchPlaybook` construction — the placement every load-time
coherence rule in this domain module already has.

## Expected first-run state

`StepDefinition` carries no `confirmer` field yet, so every test here
fails on a `TypeError` (unexpected keyword argument) — absence, and
nothing more.
"""

from __future__ import annotations

from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import (
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
from tests.support.playbook import gates as _gates

ALICE: Final = "prs_01HQ8Z6M4A"
BOHDAN: Final = "prs_01HQ8Z6M4B"


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


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
        "confirmer": None,
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
        assignees=(ALICE,),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _read_back(playbook: LaunchPlaybook, identifier: str) -> StepDefinition:
    for step in playbook.steps_for_gate("listable"):
        if step.identifier == identifier:
            return step
    raise AssertionError(f"{identifier!r} is not served at `listable`")


# ---------------------------------------------------------------------------
# The new bullet, and its scenario
# ---------------------------------------------------------------------------


def test_a_sole_assignee_who_is_also_the_confirmer_fails_to_load() -> None:
    """Scenario: A sole assignee who is also the confirmer fails to load.

    WHEN a playbook contains a step naming exactly one assignee and naming
    that same member as its confirmer
    THEN loading fails with an error naming that step.

    SPECIFIED reason: "a single actor confirming their own work is not a
    second opinion, and the shape can never produce one no matter how
    many times it is pressed." Constructed with `kind=HUMAN` deliberately
    — the requirement states the rule "holds regardless of `kind`", and a
    load rule that checked only `automated` steps would pass this test if
    it were written against an automated step alone.
    """
    step = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
        confirmer=ALICE,
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "listing.title-conforms" in str(caught.value)


def test_the_rule_holds_regardless_of_kind() -> None:
    """Requirement statement: "This holds regardless of `kind`, including
    on a `human` step, where a named confirmer otherwise carries no
    meaning today."

    Covered separately from the scenario above with `kind=AUTOMATED`, so
    an implementation that keyed the rule to `human` alone (mistaking it
    for a corollary of "a human step's confirmer carries no meaning") is
    caught here.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(BOHDAN,),
        confirmer=BOHDAN,
        handler="price.buy_box_check",
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    assert "price.buy-box-check" in str(caught.value)


def test_two_or_more_assignees_including_the_confirmer_load_fine() -> None:
    """Requirement statement: "Two or more assignees naming the confirmer
    among them ... [is] unaffected by this rule — only the case where the
    confirmer is the step's *only* named assignee is incoherent."

    The permitted side, without which an implementation rejecting every
    step whose confirmer is also an assignee (rather than only the
    sole-assignee shape) would pass the two rejection tests above.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(ALICE, BOHDAN),
        confirmer=BOHDAN,
        handler="price.buy_box_check",
    )

    playbook = _playbook(steps=(step,))

    read_back = _read_back(playbook, "price.buy-box-check")
    assert tuple(read_back.assignees) == (ALICE, BOHDAN)
    assert read_back.confirmer == BOHDAN


def test_no_assignees_at_all_loads_fine() -> None:
    """Requirement statement: "...or no assignees at all, are both
    unaffected by this rule."

    A confirmer with an empty `assignees` tuple is not the sole-assignee
    shape and loads without incident.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        confirmer=ALICE,
        handler="price.buy_box_check",
    )

    playbook = _playbook(steps=(step,))

    read_back = _read_back(playbook, "price.buy-box-check")
    assert tuple(read_back.assignees) == ()
    assert read_back.confirmer == ALICE
