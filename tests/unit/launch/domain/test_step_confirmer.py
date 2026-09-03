"""`confirmer` replaces `needs_confirmation`: the field itself, and kind's
independence from it.

Derived strictly from the delta specs:
`openspec/changes/add-step-confirmer/specs/launch-playbook/spec.md`

Covers:

- MODIFIED requirement *A step definition declares how it is to be
  resolved* — the scenario *A step definition is read back with every
  declared attribute*, restated: `confirmer` (like `assignees` and
  `handler`) is present only if authored, and the old always-present
  "confirmation flag" is gone. *Steps can be selected by gate and by
  scope* is unaffected by this delta (its WHEN/THEN mention neither field)
  and stays covered by the existing
  `tests/unit/launch/domain/test_launch_playbook.py::
  test_steps_can_be_selected_by_gate_and_by_scope` — recorded as such in
  `test-manifest.md` rather than duplicated here.
- MODIFIED requirement *A step names who does the work and whether a
  member accepts it* — all four scenarios: *An automated step declares
  whether its result is accepted*, *The playbook records no automation
  detail beyond the kind*, *Kind and confirmation are independent*, and
  *A human step's confirmer is accepted, not rejected*.
- ADDED requirement *A step names who confirms an automated result* — the
  read-back half observable with no members in reach: *An automated step
  names its confirmer*. The membership-dependent scenarios (unknown/deactivated
  confirmer, the sole-assignee case, correcting a member) are write-time
  preconditions and are covered in
  `tests/unit/launch/application/test_step_confirmer_preconditions.py`.
- MODIFIED requirement *A step names the membership responsible for it* — the
  one substantive change to this requirement's own text: "An `automated`
  step MAY name assignees or none; naming them no longer says who is
  asked to confirm a result — that is the confirmer's question alone."
  No scenario states this in the affirmative (the requirement's four
  scenarios are otherwise unchanged and are covered by the existing
  `test_step_assignee_preconditions.py` /
  `test_step_assignees_are_not_a_load_rule.py`), so it is asserted here as
  the requirement-statement test the change most directly motivates: an
  automated step's assignees and its confirmer are independent, and an
  assignee is never implicitly the confirmer just by being named.

**Level.** `StepDefinition`/`LaunchPlaybook` construction — no members in
reach, matching the placement `test_step_kind_and_confirmation.py` and
`test_step_assignees_are_not_a_load_rule.py` already use for the same
kind of rule.

## Names are DERIVED

The field name `confirmer` is fixed by the delta spec and `tasks.md` 1.1;
that it is typed `str | None` is also fixed. The Python member spellings
(`StepKind.HUMAN`) are DERIVED, matching every other file in this
directory.

## Expected first-run state

`StepDefinition` carries `needs_confirmation` and `automation_brief`, not
`confirmer` — every test here that constructs a step with `confirmer=...`
fails on a `TypeError` (unexpected keyword argument), which establishes
absence and nothing more.

Baseline: run this pass's baseline separately per `test-manifest.md`
(not re-recorded per file, per this repository's own convention change
partway through the suite's history — see the manifest for the one
baseline this pass took).
"""

from __future__ import annotations

from typing import Any, Final

from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.shared.domain.discipline import Discipline
from tests.support.fixtures import ALICE, BOHDAN
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

HANDLER_NAME: Final = "price.buy_box_check"


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
# Requirement (MODIFIED): A step definition declares how it is to be
# resolved
# ---------------------------------------------------------------------------


def test_a_step_definition_is_read_back_with_every_declared_attribute() -> None:
    """Scenario: A step definition is read back with every declared
    attribute (restated).

    WHEN a step definition is read from a loaded playbook
    THEN its identifier, name, gate, discipline, scope, timing anchor,
    blocking flag, kind, status, and hazard classification are all present
    AND its description, assignees, handler, confirmer and provenance
    reference are present only if authored
    AND the gate it starts at and the steps it waits on are read back as
    declared.

    SPECIFIED, and the point of this restatement: `confirmer` is now among
    the *optional* attributes, present only if authored — there is no
    longer an always-present "confirmation flag" the old scenario listed
    alongside `kind`.
    """
    authored = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        confirmer=ALICE,
        handler=HANDLER_NAME,
        description="The full statement of the work.",
    )
    unauthored = _step(identifier="listing.bare")

    playbook = _playbook(steps=(authored, unauthored))

    with_confirmer = _read_back(playbook, "price.buy-box-check")
    # SPECIFIED: always-present attributes.
    for attribute in (
        "identifier",
        "name",
        "gate",
        "discipline",
        "scope",
        "timing_anchor",
        "blocking",
        "kind",
        "status",
        "hazard",
    ):
        assert getattr(with_confirmer, attribute) is not None or attribute in (
            "blocking",
        )
    # SPECIFIED: present because authored.
    assert with_confirmer.confirmer == ALICE
    assert with_confirmer.handler == HANDLER_NAME
    assert with_confirmer.description == "The full statement of the work."

    bare = _read_back(playbook, "listing.bare")
    # SPECIFIED: absent because not authored.
    assert bare.confirmer is None
    assert bare.handler is None
    assert bare.description is None
    assert tuple(bare.assignees) == ()


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step names who does the work and whether a
# member accepts it
# ---------------------------------------------------------------------------


def test_an_automated_step_declares_whether_its_result_is_accepted() -> None:
    """Scenario: An automated step declares whether its result is accepted.

    WHEN an automated step is read back
    THEN it carries its kind and, separately, its confirmer, present only
    if one is named.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        confirmer=ALICE,
        handler=HANDLER_NAME,
    )

    read_back = _read_back(_playbook(steps=(step,)), "price.buy-box-check")

    assert read_back.kind is StepKind.AUTOMATED
    assert read_back.confirmer == ALICE


_NO_AUTOMATION_DETAIL: Final = (
    "execution",
    "execution_mode",
    "binding",
    "ai_assisted",
    "assisted_by",
    "model",
    "model_name",
    "llm",
    "agent",
    "uses_model",
    # Removed by this change specifically — must not survive as a boolean
    # flag beside, or in place of, `confirmer`.
    "needs_confirmation",
    "confirmation",
    "confirmation_flag",
)


def test_the_playbook_records_no_automation_detail_beyond_the_kind() -> None:
    """Scenario: The playbook records no automation detail beyond the kind.

    WHEN a step's declared fields are read
    THEN nothing states how the automation works — only that code
    resolves it, and who, if anyone, must accept the result.

    `handler` is deliberately not probed: it names the use case that
    resolves the step, which is exactly what the requirement says the
    playbook SHALL be able to declare, not a detail of "how" beyond that.
    """
    step = _step(
        identifier="creative.image-brief",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        confirmer=ALICE,
        handler="creative.image_brief",
    )

    for name in _NO_AUTOMATION_DETAIL:
        assert not hasattr(step, name), (
            f"StepDefinition exposes {name!r}: the playbook records who does "
            "the work and who, if anyone, must accept the result, and "
            "nothing about how the automation is implemented, and no "
            "boolean flag survives beside `confirmer`"
        )

    assert step.kind is StepKind.AUTOMATED
    assert step.confirmer == ALICE


def test_kind_and_confirmation_are_independent() -> None:
    """Scenario: Kind and confirmation are independent.

    WHEN the step vocabulary is read
    THEN an automated step may name a confirmer or none, and neither is
    rejected.
    """
    confirmed = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        confirmer=ALICE,
        handler=HANDLER_NAME,
    )
    unconfirmed = _step(
        identifier="rank.indexation-confirmed",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        confirmer=None,
        handler="rank.indexation_confirmed",
    )

    playbook = _playbook(steps=(confirmed, unconfirmed))

    assert _read_back(playbook, "price.buy-box-check").confirmer == ALICE
    assert _read_back(playbook, "rank.indexation-confirmed").confirmer is None
    assert len(set(StepKind)) == 2
    assert {StepKind.HUMAN, StepKind.AUTOMATED} == set(StepKind)


def test_a_human_steps_confirmer_is_accepted_not_rejected() -> None:
    """Scenario: A human step's confirmer is accepted, not rejected.

    WHEN a `human` step is written naming a confirmer
    THEN the write is accepted, and the step's kind is unaffected.

    SPECIFIED reason: "the member doing the work is the member attesting
    it ... so that flipping a step's kind does not require clearing an
    unrelated field" — the same treatment `needs_confirmation` received on
    a `human` step, now carried by `confirmer`.
    """
    step = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        status=StepStatus.ACTIVE,
        assignees=(ALICE,),
        confirmer=BOHDAN,
    )

    # SPECIFIED: accepted, not rejected — the playbook constructs.
    playbook = _playbook(steps=(step,))

    read_back = _read_back(playbook, "listing.title-conforms")
    assert read_back.kind is StepKind.HUMAN
    assert read_back.confirmer == BOHDAN


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step names the membership responsible for it —
# the one substantive change to its own text
# ---------------------------------------------------------------------------


def test_an_automated_steps_assignees_no_longer_imply_who_confirms() -> None:
    """Requirement statement (*A step names the membership responsible for
    it*): "An `automated` step MAY name assignees or none; naming them no
    longer says who is asked to confirm a result — that is the
    confirmer's question alone."

    No scenario states this in the affirmative. It is the one change this
    delta actually makes to this requirement's normative text (the old
    spec read "where it needs confirmation they are who is asked"), so it
    is asserted directly: an automated step may name assignees who are
    entirely distinct from its confirmer, and the confirmer need not be
    drawn from the assignee set at all.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(ALICE, BOHDAN),
        confirmer=None,
        handler=HANDLER_NAME,
    )

    read_back = _read_back(_playbook(steps=(step,)), "price.buy-box-check")

    # SPECIFIED: assignees carry no confirmation authority of their own —
    # naming them says nothing about who, if anyone, confirms.
    assert tuple(read_back.assignees) == (ALICE, BOHDAN)
    assert read_back.confirmer is None
