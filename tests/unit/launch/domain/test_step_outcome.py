"""Tests for the `StepOutcome` vocabulary.

Derived from the delta spec:
openspec/changes/complete-playbook-definition/specs/launch-playbook/spec.md

Covers the ADDED requirement *Step outcome vocabulary*. The vocabulary
ships without a runtime consumer (`design.md` Decision 4): recording and
transitioning outcomes belongs to slice 3's launch-instance capability and
is deliberately not tested here.

At the time of writing `commerce_ops.launch` does not exist, so every test
here is expected to fail on an absent target (`ModuleNotFoundError`). Per
`ai-toolkit:testing`, that failure establishes only absence.

DERIVED / unresolved project questions (see the manifest at the change
root):

- The vocabulary lives in `commerce_ops.launch.domain.launch_playbook`
  "next to `Hazard`" (`design.md` Decision 4), exporting `NotStarted`,
  `InProgress`, `Satisfied`, `Blocked`, `Refused`, `NotApplicable`, and
  `permissible_terminal_outcomes`.
- Per Decision 4, `Blocked`/`NotApplicable` are small frozen classes
  constructed with a reason, and the reasonless states are singletons. The
  tests below refer to each outcome by its exported name and assume
  `permissible_terminal_outcomes(hazard)` returns a collection supporting
  membership (`in`) against exactly those six designators — the natural
  reading of "answer which outcomes are permitted as terminal ... complete
  over all six outcomes". If the implemented answering surface differs (a
  predicate, say), correcting how the answer is *asked* is a fixture
  correction; which outcomes it must contain is SPECIFIED and must
  survive unchanged.
- `ValueError` as the empty-reason rejection signal, matching the
  construction-time validation convention of the shared vocabulary.
"""

from __future__ import annotations

import pytest

from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Hazard,
    InProgress,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
    permissible_terminal_outcomes,
)

# The two hazard classifications the spec calls "any other step" — every
# classification that is not `prohibited-tactic`.
ORDINARY_HAZARDS = (Hazard.NONE, Hazard.COMPLIANCE_OBLIGATION)


# ---------------------------------------------------------------------------
# Reasons
# ---------------------------------------------------------------------------


def test_a_blocked_outcome_carries_its_reason() -> None:
    """Scenario: A blocked outcome carries its reason.

    WHEN a `Blocked` outcome is constructed with a reason
    THEN it reports that reason.
    """
    blocked = Blocked("supplier shipment delayed at customs")

    # SPECIFIED: it reports that reason. DERIVED: `reason` as the
    # attribute name — the spec says only that the outcome carries one.
    assert blocked.reason == "supplier shipment delayed at customs"


def test_a_not_applicable_outcome_carries_its_reason() -> None:
    """Scenario: A blocked outcome carries its reason (NotApplicable
    counterpart).

    Not itself a named scenario — the requirement statement gives
    `NotApplicable` the same carrying-a-reason shape as `Blocked`
    ("`NotApplicable` carrying a reason"), and the rejection scenario
    below names both, so the read-back side is asserted for both too.
    """
    outcome = NotApplicable("product is single-marketplace; step is EU-only")

    assert outcome.reason == "product is single-marketplace; step is EU-only"


@pytest.mark.parametrize(
    "construct",
    [
        pytest.param(lambda: Blocked(""), id="blocked"),
        pytest.param(lambda: NotApplicable(""), id="not-applicable"),
    ],
)
def test_an_outcome_requiring_a_reason_rejects_an_empty_one(
    construct: object,
) -> None:
    """Scenario: An outcome requiring a reason rejects an empty one.

    WHEN a `Blocked` or `NotApplicable` outcome is constructed with an
    empty reason
    THEN construction fails.
    """
    # SPECIFIED: construction fails. DERIVED: the mechanism is a raised
    # ValueError (see module docstring).
    with pytest.raises(ValueError):
        construct()  # type: ignore[operator]


# ---------------------------------------------------------------------------
# Permissible terminal outcomes
# ---------------------------------------------------------------------------


def test_a_prohibited_tactic_can_only_terminate_in_refusal() -> None:
    """Scenario: A prohibited tactic can only terminate in refusal.

    WHEN the vocabulary is asked whether `Satisfied` is a permissible
    terminal outcome for a step classified `prohibited-tactic`
    THEN it answers no
    AND it answers yes for `Refused`.
    """
    permitted = permissible_terminal_outcomes(Hazard.PROHIBITED_TACTIC)

    # SPECIFIED: `Satisfied` no, `Refused` yes.
    assert Satisfied not in permitted
    assert Refused in permitted


def test_refusal_is_the_only_terminal_outcome_for_a_prohibited_tactic() -> None:
    """Scenario: A prohibited tactic can only terminate in refusal
    (completeness half).

    SPECIFIED by the requirement statement: "for a `prohibited-tactic`
    step the only permissible terminal outcome is `Refused`", and the
    answer is complete over all six outcomes — so the other five are all
    excluded, not just `Satisfied`.
    """
    permitted = permissible_terminal_outcomes(Hazard.PROHIBITED_TACTIC)

    for outcome in (Satisfied, NotApplicable, Blocked, NotStarted, InProgress):
        assert outcome not in permitted


@pytest.mark.parametrize("hazard", ORDINARY_HAZARDS)
def test_an_ordinary_step_cannot_be_refused(hazard: Hazard) -> None:
    """Scenario: An ordinary step cannot be refused.

    WHEN the vocabulary is asked whether `Refused` is a permissible
    terminal outcome for a step whose hazard classification is `none` or
    `compliance-obligation`
    THEN it answers no.
    """
    permitted = permissible_terminal_outcomes(hazard)

    # SPECIFIED: `Refused` is not permissible for an ordinary step.
    assert Refused not in permitted
    # SPECIFIED by the requirement statement: "the permissible terminal
    # outcomes are `Satisfied` and `NotApplicable`" — the yes half, so
    # that a vocabulary answering no to everything cannot pass.
    assert Satisfied in permitted


@pytest.mark.parametrize("hazard", ORDINARY_HAZARDS)
def test_blocked_is_never_terminal_and_inapplicability_is(hazard: Hazard) -> None:
    """Scenario: Blocked is never terminal, inapplicability is.

    WHEN the vocabulary is asked about the remaining outcomes for a step
    whose hazard classification is `none` or `compliance-obligation`
    THEN it answers yes for `NotApplicable`
    AND it answers no for `Blocked`, `NotStarted`, and `InProgress`.
    """
    permitted = permissible_terminal_outcomes(hazard)

    # SPECIFIED: inapplicability is a terminal resolution.
    assert NotApplicable in permitted
    # SPECIFIED: a blocked step awaits resolution; it has not reached one.
    assert Blocked not in permitted
    assert NotStarted not in permitted
    assert InProgress not in permitted
