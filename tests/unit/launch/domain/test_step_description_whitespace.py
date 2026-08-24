"""A description consisting only of whitespace is empty.

Derived strictly from the delta spec:
`openspec/changes/describe-playbook-steps/specs/launch-playbook/spec.md`

This file exists because of a clause the delta gained after the first
test-writing pass. That pass recorded "does a whitespace-only description
count as empty?" as an *unresolved project question* and left the case
deliberately untested, because no artifact answered it. The delta now
answers it, in three places:

- the attribute paragraph — "The description is required and SHALL NOT be
  empty, and a description consisting only of whitespace SHALL be treated
  as empty";
- the coherence bullet — "a step definition's description is empty,
  consists only of whitespace, or is not declared at all";
- *Scenario: A step with no description is rejected by name* — "a step
  whose description is empty, consists only of whitespace, or omits the
  description entirely".

`tasks.md` 2.1 names the consequence for the implementation directly: "the
delta defines [empty] to include one consisting only of whitespace, so a
bare `if not description` is not enough".

**Level.** `design.md` Decision 1 places the emptiness rule with the
playbook's other coherence rules — "rejected at load, naming the step" —
not on `StepDefinition`'s constructor. Playbook construction is therefore
the smallest unit that can observe the rejection, the same level the first
pass used for the empty-string case in
`tests/unit/launch/domain/test_step_description.py`.

**At the time of writing `StepDefinition` has no `description` field**, so
every test here is expected to fail on an absent target — a `TypeError`
from the unexpected keyword argument, not a wrong value. Per
`ai-toolkit:testing` that establishes only that the field is absent; it
establishes nothing about whether these assertions are any good, because
they never execute.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 585 passed, 23 failed. All 23
failures are the first pass's own tests, failing on the same absent field.
`tests/integration` was not run: it needs a live Postgres, unavailable
here.
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

A_DESCRIPTION: Final = (
    "Main image designed to be scroll-stopping and explicitly different "
    "from competitors, not blending in"
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
        "identifier": "lp.creative.008",
        "description": A_DESCRIPTION,
        "gate": "listable",
        "discipline": Discipline("creative"),
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
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=steps)


# ---------------------------------------------------------------------------
# Requirement (MODIFIED): An incoherent playbook is rejected at load time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "description"),
    [
        ("a single space", " "),
        ("several spaces", "   "),
        ("a tab", "\t"),
        ("mixed horizontal whitespace", " \t \t "),
    ],
    ids=["single-space", "several-spaces", "tab", "mixed-horizontal"],
)
def test_a_whitespace_only_description_is_rejected_by_name(
    label: str, description: str
) -> None:
    """Scenario: A step with no description is rejected by name (whitespace).

    WHEN a playbook declares a step whose description consists only of
    whitespace
    THEN loading fails with an error naming that step.

    Four spellings of "only whitespace" are exercised because the delta
    states the rule on the *property* — "consisting only of whitespace" —
    not on a particular character. An implementation testing
    `description != " "`, or one stripping only spaces, satisfies some of
    these and not others; one implementing the stated property satisfies
    all four.

    Vertical whitespace is deliberately excluded: a description of `"\\n"`
    is both whitespace-only and spanning more than one line, so which of
    the two faults reported it would be ambiguous, and this test would
    stop discriminating. See the foot of this file.
    """
    step = _step(identifier="lp.listing.019", description=description)

    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(step,))

    # SPECIFIED: the error names that step.
    assert "lp.listing.019" in str(caught.value), label


def test_a_whitespace_only_description_is_rejected_by_the_playbook_not_the_step() -> (
    None
):
    """Scenario: A step with no description is rejected by name (placement).

    `design.md` Decision 1 puts this rule with the playbook's coherence
    rules rather than on `StepDefinition`'s constructor, "so that a
    malformed authored value reports *where it was authored*". Asserted
    for the whitespace-only case as well as the empty-string case (which
    `test_step_description.py` covers), because an implementation could
    place one rule in each spot — and a fault raised at construction
    cannot be aggregated with the others.
    """
    # SPECIFIED (design.md Decision 1): construction is not where this rule
    # lives, so this line raising would put the fault outside the
    # aggregated report.
    step = _step(identifier="lp.listing.019", description="   ")

    assert step.description == "   "


def test_a_whitespace_only_description_fault_is_aggregated_with_another_fault() -> None:
    """Scenario: A step with no description is rejected by name (aggregation).

    "...in the same aggregated report as any other fault", and Scenario:
    *Multiple violations are reported together*, exercised over the
    whitespace spelling of the empty-description fault.

    Covered separately from the empty-string case because an
    implementation could reach the two by different routes — an early
    `raise` on one and an accumulated fault on the other — and the
    empty-string aggregation test would still pass.
    """
    whitespace_only = _step(identifier="lp.listing.019", description="   ")
    unknown_gate = _step(identifier="lp.ppc.048", gate="pre-launch")

    # SPECIFIED: loading fails *once*, carrying both faults.
    with pytest.raises(InvalidPlaybookError) as caught:
        _playbook(steps=(whitespace_only, unknown_gate))

    message = str(caught.value)
    # SPECIFIED: the failure names both.
    assert "lp.listing.019" in message
    assert "lp.ppc.048" in message


def test_a_description_that_merely_contains_whitespace_is_accepted() -> None:
    """Scenario: A coherent playbook loads (permitted side of the rule).

    The delta treats as empty a description "consisting **only** of
    whitespace". A description carrying real words — including one padded
    with leading and trailing spaces — is not that, and must load.

    Without this, an implementation rejecting any description that
    contains whitespace at all, or any that is not already stripped, would
    pass every rejection test above while outlawing all 97 shipped
    descriptions.
    """
    padded = f"  {A_DESCRIPTION}  "
    steps = (_step(identifier="lp.creative.008", description=padded),)

    playbook = _playbook(steps=steps)

    # SPECIFIED: it loads, and the step is exposed.
    assert [step.identifier for step in playbook.steps] == ["lp.creative.008"]
    # SPECIFIED: the description is not empty — the words survive. Whether
    # the loaded value is stored padded or stripped is NOT asserted: no
    # artifact says, and asserting either would fix a behaviour nobody
    # stated. See the foot of this file.
    (loaded,) = playbook.steps
    assert loaded.description.strip() == A_DESCRIPTION


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - A description of only vertical whitespace (`"\n"`, `"\r\n"`). It
#   satisfies two rejection rules at once — whitespace-only and spanning
#   more than one line — and the delta does not say which reports it. Both
#   name the step, so an assertion would hold either way and would
#   therefore discriminate nothing that the tests above do not already.
# - Whether the loader stores a padded description as authored or strips
#   it. The delta constrains only which descriptions are *rejected*; the
#   shipped-set transcription rule (trailing whitespace removed) is a rule
#   on authoring, in `tasks.md` 3.1, not on the loader.
# - A whitespace-only description supplied through the *file* boundary
#   rather than through playbook construction. The rule lives in the
#   domain (`tasks.md` 2.1) and the loader passes the authored value
#   through, so a loader-level test would re-observe the same rule one
#   layer out. The loader-specific case — a description key absent
#   entirely — is covered by
#   `tests/unit/launch/infrastructure/test_playbook_loader_description.py`.
# - Unicode whitespace outside the ASCII set (a non-breaking space, say).
#   The delta says "whitespace" without fixing a repertoire, and Python's
#   own answer (`str.isspace()`, `str.strip()`) would be the assertion's
#   real source rather than any artifact.
