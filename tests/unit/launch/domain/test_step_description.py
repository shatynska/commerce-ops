"""A step definition's required `description`, and the rules on it.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-playbook/spec.md`

Both requirements this file touches are `MODIFIED`:

- *A step definition declares how it is to be resolved* — the declared
  attribute list gains "a description: the work the step asks for,
  readable without consulting the source material, and occupying a single
  line", required and non-empty.
- *An incoherent playbook is rejected at load time* — two new rejection
  rules: an empty or absent description, and a description spanning more
  than one line.

**Level.** `design.md` Decision 1 places the emptiness rule "with the
other playbook coherence rules (rejected at load, naming the step), not
as a constructor rule on `StepDefinition`", matching how
`MetricCondition`'s empty-threshold rule is already handled. Playbook
construction is therefore the smallest unit that can observe these
rejections, exactly as in
`test_playbook_coherence_completion.py`. The one case construction cannot
observe — a description key *absent from the authored file*, which a
required dataclass field cannot express — lives at the loader boundary in
`tests/unit/launch/infrastructure/test_playbook_loader_description.py`,
per `tasks.md` 2.2.

**At the time of writing, `StepDefinition` has no `description` field.**
Every test here is therefore expected to fail on an absent target — a
`TypeError` from the unexpected keyword argument, not a wrong value. Per
`ai-toolkit:testing` that failure establishes only that the field is
absent; it establishes nothing about whether these assertions are any
good, because they never executed.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 584 passed, 0 failed. The
`tests/integration` tier was not run: it needs a live Postgres, which is
not available here.

DERIVED, and recorded rather than left implicit: the field is named
`description` and is passed to `StepDefinition` as a keyword argument.
`proposal.md` ("`StepDefinition` gains a required `description`") and
`tasks.md` 2.1 fix the name; nothing fixes the constructor's parameter
order, so every construction below is by keyword. See
`openspec/changes/describe-playbook-steps/test-manifest.md`.
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
)
from commerce_ops.shared.domain.discipline import Discipline

# SPECIFIED (main spec, Requirement: Gate sequence orders the launch).
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

# A description in the shape the shipped set uses: one line, stating the
# work. Its wording asserts nothing — only its shape matters here.
A_DESCRIPTION: Final = (
    "Main image designed to be scroll-stopping and explicitly different "
    "from competitors, not blending in"
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
    """A coherent step, overriding named attributes.

    Same factory shape as the other launch-domain test files, with the
    `description` this change adds carrying a valid default so that a
    test changing one attribute knows the failure it provokes is the one
    it intended.
    """
    attributes: dict[str, Any] = {
        "identifier": "lp.creative.008",
        "description": A_DESCRIPTION,
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


def _playbook(
    *,
    gates: tuple[Gate, ...] | None = None,
    steps: tuple[StepDefinition, ...] = (),
) -> LaunchPlaybook:
    return LaunchPlaybook(
        version="test-v1",
        gates=specified_gates() if gates is None else gates,
        steps=steps,
    )


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): A step definition declares how it is to be resolved
# ---------------------------------------------------------------------------


def test_a_step_definition_reads_back_its_description() -> None:
    """Scenario: A step definition is read back with every declared attribute.

    WHEN a step definition is read from a loaded playbook
    THEN its identifier, description, gate, discipline, scope, timing
    anchor, binding, blocking flag, execution mode, and hazard
    classification are all present.

    Asserted over the whole declared list rather than the description
    alone, because the scenario states one conjunction: a model that
    carried a description while dropping another declared attribute would
    not satisfy it.
    """
    step = _step(identifier="lp.creative.008", description=A_DESCRIPTION)

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("listable")

    # SPECIFIED: the description is present, and is the work the step
    # asks for rather than a restatement of the identifier.
    assert read_back.description == A_DESCRIPTION
    # SPECIFIED: every other declared attribute is present too.
    assert read_back.identifier == "lp.creative.008"
    assert read_back.gate == "listable"
    assert read_back.discipline is not None
    assert read_back.scope is Scope.PRODUCT
    assert read_back.timing_anchor is not None
    assert read_back.binding is Binding.FRAMEWORK
    assert read_back.blocking is False
    assert read_back.execution is ExecutionMode.HUMAN_ATTESTED
    assert read_back.hazard is Hazard.NONE


def test_the_description_is_not_the_identifier() -> None:
    """Requirement statement: the description states the work.

    "readable without consulting the source material" — and `design.md`
    Decision 1 rejects, by name, an implementation defaulting the
    description to the identifier: "a description that falls back to
    `lp.creative.008` reproduces exactly the task name this change exists
    to eliminate, while making the failure invisible".

    Without this, an implementation deriving the description from the
    identifier would satisfy every other test in this file.
    """
    step = _step(identifier="lp.creative.008", description=A_DESCRIPTION)

    (read_back,) = _playbook(steps=(step,)).steps_for_gate("listable")

    # SPECIFIED: the description is the authored work statement, not a
    # value derived from the identifier.
    assert read_back.description != read_back.identifier
    assert read_back.identifier not in read_back.description


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


def test_a_step_with_an_empty_description_is_rejected_by_name() -> None:
    """Scenario: A step with no description is rejected by name (empty).

    WHEN a playbook declares a step whose description is empty
    THEN loading fails with an error naming that step.

    The *omitted entirely* half of this scenario cannot be observed
    below the file boundary — a required dataclass field cannot be
    missing (`tasks.md` 2.1) — and is covered at the loader in
    `tests/unit/launch/infrastructure/test_playbook_loader_description.py`.
    """
    step = _step(identifier="lp.listing.019", description="")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "lp.listing.019" in str(caught.value)


def test_an_empty_description_is_rejected_by_the_playbook_not_the_step() -> None:
    """Scenario: A step with no description is rejected by name (placement).

    `design.md` Decision 1: the emptiness rule "lives with the other
    playbook coherence rules (rejected at load, naming the step), not as
    a constructor rule on `StepDefinition`", so that "a malformed
    authored value reports *where it was authored*".

    Constructing the step alone must therefore not raise; the fault
    surfaces when the playbook is assembled, which is what lets it be
    aggregated with every other fault rather than aborting on the first.
    """
    # SPECIFIED (design.md Decision 1): construction is not where this
    # rule lives, so this line raising would put the fault outside the
    # aggregated report.
    step = _step(identifier="lp.listing.019", description="")

    assert step.description == ""


@pytest.mark.parametrize(
    ("label", "description"),
    [
        (
            "embedded newline",
            "A+ modules built to confirm what the product has\nand why it wins",
        ),
        (
            "embedded carriage-return newline",
            "A+ modules built to confirm what the product has\r\nand why it wins",
        ),
    ],
)
def test_a_description_spanning_several_lines_is_rejected(
    label: str, description: str
) -> None:
    """Scenario: A description spanning several lines is rejected.

    WHEN a playbook declares a step whose description contains a line
    break
    THEN loading fails with an error naming that step.

    Both line-break spellings are exercised because the rule is stated on
    the description containing a line break, not on a particular
    encoding of one; an implementation splitting on `\\n` alone still
    catches the second case, while one comparing against a single
    hard-coded separator might not.
    """
    step = _step(identifier="lp.listing.019", description=description)

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "lp.listing.019" in str(caught.value), label


def test_a_single_line_description_is_accepted() -> None:
    """Scenario: A coherent playbook loads (as revised — permitted side).

    The two rules above forbid an *empty* description and one spanning
    *more than one line*. A valid single-line description must load, or
    the rules would outlaw the field they exist to guarantee — and
    without this, an implementation rejecting every description would
    pass both rejection tests. Same permitted-side pattern the earlier
    passes applied to the prohibited-tactic and lesson rules.
    """
    steps = (
        _step(identifier="lp.creative.008", description=A_DESCRIPTION),
        _step(
            identifier="lp.strategy.001",
            gate="commit",
            description="Product is VISIBLY BETTER on the search results page",
        ),
    )

    playbook = _playbook(steps=steps)

    # SPECIFIED: it loads successfully and exposes its step definitions,
    # each carrying its own description.
    assert {step.identifier: step.description for step in playbook.steps} == {
        "lp.creative.008": A_DESCRIPTION,
        "lp.strategy.001": "Product is VISIBLY BETTER on the search results page",
    }


def test_a_description_fault_is_aggregated_with_another_fault() -> None:
    """Scenario: A step with no description is rejected by name (aggregation).

    "...in the same aggregated report as any other fault" — and Scenario:
    *Multiple violations are reported together*, exercised over the fault
    this change adds.

    A description fault implemented as an early exit would leave the
    other fault undiscovered, which is the experience the aggregation
    requirement exists to prevent.
    """
    no_description = _step(identifier="lp.listing.019", description="")
    unknown_gate = _step(identifier="lp.ppc.048", gate="pre-launch")

    # SPECIFIED: loading fails *once* — a single raised error carrying
    # both faults, not one error per fault.
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(no_description, unknown_gate))

    message = str(caught.value)
    # SPECIFIED: the failure names both.
    assert "lp.listing.019" in message
    assert "lp.ppc.048" in message


def test_a_multi_line_description_fault_is_aggregated_with_another_fault() -> None:
    """Scenario: Multiple violations are reported together (multi-line).

    Covered separately from the empty case because the delta states two
    distinct rules, and an implementation that aggregated one while
    early-exiting on the other would pass the test above.
    """
    multi_line = _step(identifier="lp.listing.019", description="first\nsecond")
    unknown_gate = _step(identifier="lp.ppc.048", gate="pre-launch")

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(multi_line, unknown_gate))

    message = str(caught.value)
    # SPECIFIED: the failure names both.
    assert "lp.listing.019" in message
    assert "lp.ppc.048" in message


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - A whitespace-only description (`"   "`). The delta says the
#   description "SHALL NOT be empty"; whether whitespace-only counts as
#   empty is not stated anywhere in the change's artifacts, and asserting
#   either answer here would impose a constraint nobody agreed to. Raised
#   as an unresolved project question in the manifest instead.
# - A description ending in a trailing newline but otherwise one line.
#   "Spans more than one line" is unambiguous for an embedded break and
#   ambiguous for a trailing one; same reason as above.
# - Any maximum length on the description at the domain level. The delta
#   places the length concern on the *composed task name*, in
#   `launch-clickup-sync`, and states no bound on the description itself.
# - The exact wording of any error message — only that it names the
#   offending step, which is what the delta requires.
