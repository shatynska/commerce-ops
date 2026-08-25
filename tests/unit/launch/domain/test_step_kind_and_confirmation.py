"""Kind and confirmation as two independent facts, replacing `ExecutionMode`.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers the ADDED requirement *A step names who does the work and whether
a person accepts it* — all three scenarios — plus its paragraph on a
`human` step's confirmation flag being "ignored rather than rejected",
which is a rule no scenario states in the affirmative and which a write
that refused it would violate.

**Level.** Construction of `StepDefinition` and `LaunchPlaybook`, the
placement `tasks.md` 1.1–1.3 gives the field set and its rules.

## Names are DERIVED

`tasks.md` 1.1 fixes `StepKind` with members `human` and `automated`,
and 1.2 fixes the field names `kind` and `needs_confirmation`; the Python
member spellings (`StepKind.HUMAN`) are DERIVED, as is the module — the
one `ExecutionMode` is deleted from.

`_NO_AUTOMATION_DETAIL` below is a DERIVED probe, not an exhaustive one:
the spec says the playbook "SHALL NOT record" how the automation works,
and a probe can only look for the spellings that recording would
plausibly take. It is recorded in `test-manifest.md` as derived so that
its list is reviewable rather than mistaken for a stated requirement.

## Expected first-run state

`StepKind` does not exist, so every test here fails on an absent target
(`ImportError`) — which establishes absence and nothing more.

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

A_BRIEF: Final = "Buy Box share is at or above 90% over a rolling week."


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
        "needs_confirmation": False,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "automation_brief": None,
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
# Requirement: A step names who does the work and whether a person accepts it
# ---------------------------------------------------------------------------


def test_an_automated_step_declares_whether_its_result_is_accepted() -> None:
    """Scenario: An automated step declares whether its result is accepted.

    WHEN an automated step is read back
    THEN it carries its kind and, separately, whether its result needs a
    person's confirmation.
    """
    step = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        needs_confirmation=True,
        status=StepStatus.ACTIVE,
        automation_brief=A_BRIEF,
        handler="price.buy_box_check",
    )

    read_back = _read_back(_playbook(steps=(step,)), "price.buy-box-check")

    # SPECIFIED: the kind, and — separately — the confirmation flag.
    assert read_back.kind is StepKind.AUTOMATED
    assert read_back.needs_confirmation is True


_NO_AUTOMATION_DETAIL: Final = (
    # The vocabulary this change removes, which must not survive under
    # its own name...
    "execution",
    "execution_mode",
    "binding",
    # ...nor return as a record of *how* the automation works, which the
    # spec says the playbook does not record.
    "ai_assisted",
    "assisted_by",
    "model",
    "model_name",
    "llm",
    "agent",
    "uses_model",
)


def test_the_playbook_records_no_automation_detail_beyond_the_kind() -> None:
    """Scenario: The playbook records no automation detail beyond the kind.

    WHEN a step's declared fields are read
    THEN nothing states how the automation works — only that code
    resolves it, and whether a person accepts the result.

    The automation *brief* is not such a detail and is deliberately not
    probed: it states what the code must establish, in prose, for whoever
    builds it — the acceptance criterion, not the mechanism. What the
    spec forbids is the playbook recording "whether the code that
    resolves a step calls a language model", which is what the removed
    `ai-assisted` mode recorded.
    """
    step = _step(
        identifier="creative.image-brief",
        kind=StepKind.AUTOMATED,
        needs_confirmation=True,
        automation_brief="A hero image brief exists and reads coherently.",
        handler="creative.image_brief",
    )

    for name in _NO_AUTOMATION_DETAIL:
        assert not hasattr(step, name), (
            f"StepDefinition exposes {name!r}: the playbook records who "
            "does the work and whether a person accepts the result, and "
            "nothing about how the automation is implemented"
        )

    # SPECIFIED: what it *does* state — code resolves it, and whether a
    # person accepts the result. Asserted alongside the absences so this
    # test cannot pass against a step model that records neither.
    assert step.kind is StepKind.AUTOMATED
    assert step.needs_confirmation is True


def test_kind_and_confirmation_are_independent() -> None:
    """Scenario: Kind and confirmation are independent.

    WHEN the step vocabulary is read
    THEN an automated step may either need confirmation or not, and
    neither combination is rejected.
    """
    confirmed = _step(
        identifier="price.buy-box-check",
        kind=StepKind.AUTOMATED,
        needs_confirmation=True,
        automation_brief=A_BRIEF,
        handler="price.buy_box_check",
    )
    unconfirmed = _step(
        identifier="rank.indexation-confirmed",
        kind=StepKind.AUTOMATED,
        needs_confirmation=False,
        automation_brief="Every listed ASIN is indexed for its main keyword.",
        handler="rank.indexation_confirmed",
    )

    playbook = _playbook(steps=(confirmed, unconfirmed))

    # SPECIFIED: neither combination is rejected — both load.
    assert _read_back(playbook, "price.buy-box-check").needs_confirmation is True
    assert _read_back(playbook, "rank.indexation-confirmed").needs_confirmation is False
    # SPECIFIED: the two axes are two fields, not one collapsed value.
    assert len(set(StepKind)) == 2
    assert {StepKind.HUMAN, StepKind.AUTOMATED} == set(StepKind)


def test_a_human_steps_confirmation_flag_is_ignored_rather_than_rejected() -> None:
    """Requirement statement: "A `human` step's confirmation flag SHALL
    carry no meaning ... and SHALL be ignored rather than rejected, so
    that flipping a step's kind does not require clearing an unrelated
    field".

    No scenario states this in the affirmative, and it is exactly the
    rule an implementation that validated the field set field-by-field
    would get wrong: rejecting the flag would make flipping `automated`
    → `human` fail on a field the author never touched.

    SPECIFIED: the construction is accepted. DELIBERATELY UNTESTED:
    whether the stored value is normalised to false or carried as
    written — "ignored" fixes that nothing reads it, not what it reads
    back as, so asserting either spelling would invent a rule.
    """
    step = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        needs_confirmation=True,
        status=StepStatus.ACTIVE,
    )

    # SPECIFIED: accepted, not rejected — the playbook constructs.
    playbook = _playbook(steps=(step,))

    assert _read_back(playbook, "listing.title-conforms").kind is StepKind.HUMAN
