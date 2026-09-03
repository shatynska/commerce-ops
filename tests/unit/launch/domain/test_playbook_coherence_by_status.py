"""The coherence rules as this change restates them, against each step's status.

Derived strictly from the delta spec:
`openspec/changes/redesign-step-fields/specs/launch-playbook/spec.md`

Covers, from the ADDED requirement *An incoherent playbook is rejected
against each step's status*, the scenarios whose **rule changed** —

- *A step with no name is rejected by identifier* (the emptiness rule
  moved from description to name),
- *A name spanning several lines is rejected* (the single-line rule moved
  with it),
- *A description spanning several lines is accepted* (its inverse, and a
  new rule: the description may now span lines),
- *A gate with no active blocking step is rejected* (the floor counts
  only `active` steps),
- *Multiple violations are reported together* (re-established over the
  rules this change introduces, since the pair the existing test uses —
  a lesson-bound blocking step — ceases to exist),
- *A coherent playbook loads* (what "coherent" now means),

together with the MODIFIED requirement *Every gate is held by at least
one blocking step* and its scenario *No gate opens for free*, restated as
counting only active steps.

**Scenarios of this requirement whose rule is unchanged are not
re-covered here**, and are accounted for in `test-manifest.md` against
the existing tests that cover them — gate-sequence deviations, opening
modes, duplicate identifiers, unknown gates, the prohibited-tactic rule,
the malformed metric condition, and the malformed-step aggregation. Those
tests need their fixtures migrated to the new field set (`tasks.md` 6.3);
that is a fixture correction and not a licence to weaken what they
assert.

*Automation past draft without a brief* is covered in
`test_step_automation_brief_and_handler.py`, which owns the requirement
that states the rule.

**Level.** `LaunchPlaybook` construction (`tasks.md` 1.3), the placement
every existing coherence rule already has.

## Expected first-run state

`StepKind`/`StepStatus` do not exist, so every test here fails on an
absent target (`ImportError`) — absence, and nothing more.

Baseline recorded before these tests were written: `uv run pytest` at
the worktree root — 729 passed, 68 skipped, 0 failed.
"""

from __future__ import annotations

from typing import Any

import pytest

from commerce_ops.launch.domain.launch_playbook import (
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
from tests.support.steps import step as _build_step


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _step(**overrides: Any) -> StepDefinition:
    return _build_step(**overrides)


def _hold(gate: str, **overrides: Any) -> StepDefinition:
    """An `active` blocking filler holding `gate` — the floor's minimum."""
    attributes: dict[str, Any] = {
        "identifier": f"hold.{gate}",
        "name": f"Blocking work holding the {gate} gate",
        "gate": gate,
        "blocking": True,
        "status": StepStatus.ACTIVE,
    }
    attributes.update(overrides)
    return _step(**attributes)


def _holding_steps(
    *, except_gates: frozenset[str] = frozenset()
) -> tuple[StepDefinition, ...]:
    return tuple(
        _hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in except_gates
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    """Constructs with the given steps, filling every gate the steps
    leave without an **active** blocking step."""
    held = {
        step.gate
        for step in steps
        if step.blocking and step.status is StepStatus.ACTIVE
    }
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _raw(steps: tuple[StepDefinition, ...]) -> LaunchPlaybook:
    """Constructs with exactly these steps and no fillers — for the tests
    that are about which gates end up held."""
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


# ---------------------------------------------------------------------------
# The name rules — moved here from the description
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("", id="empty"),
        pytest.param("   ", id="spaces"),
        pytest.param("\t\n ", id="whitespace-only"),
    ],
)
def test_a_step_with_no_name_is_rejected_by_identifier(name: str) -> None:
    """Scenario: A step with no name is rejected by identifier.

    WHEN a playbook declares a step whose name is empty, consists only of
    whitespace, or omits the name entirely
    THEN loading fails with an error naming that step, in the same
    aggregated report as any other fault.

    SPECIFIED: "a name consisting only of whitespace SHALL be treated as
    empty", which is why the whitespace cases sit here rather than being
    left to be inferred. The *omitted* case is the test below, since
    omitting a required constructor argument is a different event from
    passing an empty one.
    """
    step = _step(identifier="listing.nameless", name=name)

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step. The identifier is what names
    # it — the name is exactly what the step does not have.
    assert "listing.nameless" in str(caught.value)


def test_the_name_is_required_rather_than_defaulted() -> None:
    """Scenario: A step with no name is rejected by identifier (the
    omitted case).

    SPECIFIED: "The name is required" — a step that omits it is not a
    step with a blank name, and an implementation defaulting it to the
    identifier, to the description, or to the empty string would satisfy
    neither this nor the rule above.

    DERIVED: that omission surfaces as a construction failure (`TypeError`
    for a missing argument) or as the same aggregated fault. Either is
    accepted; what is not accepted is a playbook that loads.
    """
    with pytest.raises((TypeError, InvalidPlaybookError, ValueError)):
        nameless = StepDefinition(  # type: ignore[call-arg]
            identifier="listing.nameless",
            gate="listable",
            discipline=_any_discipline(),
            scope=Scope.PRODUCT,
            timing_anchor=OffsetAnchor(days=-7),
            blocking=False,
            kind=StepKind.HUMAN,
            status=StepStatus.ACTIVE,
        )
        _playbook(steps=(nameless,))


def test_a_name_spanning_several_lines_is_rejected() -> None:
    """Scenario: A name spanning several lines is rejected.

    WHEN a playbook declares a step whose name contains a line break
    THEN loading fails with an error naming that step.

    SPECIFIED reason, which is why the rule moved rather than being
    dropped: "a name is composed into a task's name, and a name is a
    single line".
    """
    step = _step(
        identifier="listing.two-line-name",
        name="Conform the title to the style guide\nand check it renders",
    )

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    assert "listing.two-line-name" in str(caught.value)


def test_a_description_spanning_several_lines_is_accepted() -> None:
    """Scenario: A description spanning several lines is accepted.

    WHEN a playbook declares a step whose description contains line breaks
    THEN the playbook loads, and the description is carried unaltered.

    This is the inverse of the rule above and the reason the two fields
    are two fields. "Unaltered" is asserted exactly: an implementation
    that normalised the line breaks, collapsed the whitespace or trimmed
    the body would put a different text into the ClickUp task than the
    author wrote.
    """
    body = (
        "Check the title against the style guide.\n"
        "\n"
        "  Then check it renders on mobile, where the truncation differs."
    )
    step = _step(identifier="listing.title-conforms", description=body)

    playbook = _playbook(steps=(step,))

    (read_back,) = [
        candidate
        for candidate in playbook.steps_for_gate("listable")
        if candidate.identifier == "listing.title-conforms"
    ]
    assert read_back.description == body


def test_a_description_is_optional() -> None:
    """Requirement statement (*A step definition declares how it is to be
    resolved*): the description "MAY be absent when the name says
    everything".

    The seeded set depends on this: a seeded step carries the reference
    row's text as its **name** and "MAY carry no description at all".
    """
    playbook = _playbook(steps=(_step(identifier="listing.title-conforms"),))

    (read_back,) = [
        candidate
        for candidate in playbook.steps_for_gate("listable")
        if candidate.identifier == "listing.title-conforms"
    ]
    assert read_back.description is None


# ---------------------------------------------------------------------------
# The gate-holding floor, counting only active steps
# ---------------------------------------------------------------------------


def test_a_gate_whose_only_blocking_step_is_a_draft_leaves_it_unheld() -> None:
    """Scenario: A gate with no active blocking step is not served.

    WHEN a playbook's steps leave any gate with no active step whose
    blocking flag is true
    THEN the set constructs, and the readiness read names that gate.

    SPECIFIED reason: "a gate whose only blocking step is a draft is a
    gate that *would* open for free, and the floor exists to make that
    state unservable". `serve-only-a-ready-playbook` moved the refusal
    from construction to the serving read; what stays load-bearing here is
    that a `draft` blocking step does not count, which an implementation
    carrying the pre-change rule forward — counting any blocking step —
    would get wrong.
    """
    draft_blocker = _hold("ignition", status=StepStatus.DRAFT)
    steps = (*_holding_steps(except_gates=frozenset({"ignition"})), draft_blocker)

    playbook = _raw(steps)

    # SPECIFIED: the read names the gate the draft does not hold.
    assert playbook.unheld_gates == ("ignition",)
    assert not playbook.is_ready


def test_a_gate_whose_only_blocking_step_is_in_development_leaves_it_unheld() -> None:
    """Scenario: A gate with no active blocking step is not served
    (`in-development` case).

    Covered separately from the draft case because `in-development` is
    the status the seeded automated steps land in, and an implementation
    that excluded only `draft` from the count would pass the test above
    while leaving a gate held by something the launch is never served.
    """
    steps = (
        *_holding_steps(except_gates=frozenset({"live"})),
        _hold("live", status=StepStatus.IN_DEVELOPMENT),
    )

    playbook = _raw(steps)

    assert playbook.unheld_gates == ("live",)
    assert not playbook.is_ready


def test_no_gate_opens_for_free() -> None:
    """Scenario (MODIFIED requirement *Every gate is held by at least one
    blocking step*): No gate opens for free.

    WHEN the served step set is grouped by gate, at any point in the
    set's life
    THEN every gate has at least one active step with a true blocking
    flag.

    Asserted over the constructed playbook's **served** steps, which is
    what the requirement is about — the same set a launch is held to.
    """
    playbook = _playbook(
        steps=(
            _step(identifier="listing.draft-work", status=StepStatus.DRAFT),
            _step(
                identifier="ignition.retired-work",
                gate="ignition",
                status=StepStatus.RETIRED,
                blocking=True,
            ),
        )
    )

    unheld = [
        gate
        for gate in SPECIFIED_GATE_ORDER
        if not any(
            step.blocking and step.status is StepStatus.ACTIVE
            for step in playbook.steps_for_gate(gate)
        )
    ]
    assert unheld == []


# ---------------------------------------------------------------------------
# Aggregation, and the coherent case
# ---------------------------------------------------------------------------


def test_two_violations_of_the_new_rules_are_reported_together() -> None:
    """Scenario: Multiple violations are reported together.

    WHEN a playbook contains two distinct coherence violations
    THEN loading fails once, and the failure names both.

    Exercised with two faults this change introduces — a `human` step
    carrying a handler, and an `automated`, `active` step with no
    handler — so the new rules are established as participants in the
    aggregated error rather than as early-exit checks. The pre-change
    test of this scenario pairs an empty description with a lesson-bound
    blocking step, and **neither of those faults exists after this
    change** (`tasks.md` 6.2).
    """
    human_with_handler = _step(
        identifier="listing.title-conforms",
        kind=StepKind.HUMAN,
        handler="listing.title_conforms",
    )
    automated_without_handler = _step(
        identifier="price.buy-box-check",
        gate="live",
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        assignees=(),
        handler=None,
    )

    # A single raised error is what establishes "fails once".
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(human_with_handler, automated_without_handler))

    message = str(caught.value)
    # SPECIFIED: the failure names both.
    assert "listing.title-conforms" in message
    assert "price.buy-box-check" in message


def test_a_coherent_playbook_loads() -> None:
    """Scenario: A coherent playbook loads.

    WHEN a playbook satisfies every coherence rule
    THEN it loads successfully and exposes its gates and step definitions.

    "Coherent" as this change defines it: statuses across the range, an
    active human step naming nobody (a write-time matter, never a load-
    time one), an automated step naming a confirmer, an active
    automated step with a handler nothing here registers, and a
    multi-line description.
    """
    steps = (
        _step(
            identifier="sourcing.unit-economics",
            gate="commit",
            blocking=True,
            status=StepStatus.ACTIVE,
        ),
        _step(
            identifier="listing.a-plus-content",
            scope=Scope.MARKET,
            description="The full statement of the work.\nOn several lines.",
            status=StepStatus.DRAFT,
        ),
        _step(
            identifier="creative.image-brief",
            gate="ignition",
            kind=StepKind.AUTOMATED,
            confirmer="prs_confirmer",
            status=StepStatus.IN_DEVELOPMENT,
        ),
        _step(
            identifier="price.buy-box-check",
            gate="live",
            kind=StepKind.AUTOMATED,
            status=StepStatus.ACTIVE,
            handler="price.buy_box_check",
        ),
        _step(
            identifier="listing.superseded",
            status=StepStatus.RETIRED,
        ),
    )

    playbook = _playbook(steps=steps)

    # SPECIFIED: it exposes its gates...
    assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)
    # ...and its step definitions, the served ones under the served
    # queries.
    served = {
        step.identifier
        for gate in SPECIFIED_GATE_ORDER
        for step in playbook.steps_for_gate(gate)
    }
    assert {"sourcing.unit-economics", "price.buy-box-check"} <= served
    assert {"listing.a-plus-content", "creative.image-brief", "listing.superseded"} & (
        served
    ) == set()
