"""The undecided-rule-policies report, run over the *shipped* playbook.

Derived from the delta spec:
openspec/changes/author-playbook-steps/specs/launch-playbook/spec.md

Covers the one scenario of *The authored set exercises the full step
vocabulary* that is observed through the application-layer report rather
than through the loaded file: *Outstanding rule-policy decisions stay
visible*. Every other scenario of that requirement, and of the change's
two other requirements, lives in
`tests/unit/launch/infrastructure/test_shipped_playbook_steps.py`.

The report's own behaviour is specified by the existing `launch-playbook`
requirement *Undecided rule policies are reported* and covered by
`test_report_undecided_rule_policies.py` against purpose-built fixtures.
What is new here — and what this file asserts — is that the *shipped*
playbook is in the authoring-in-progress state the delta describes, and
that the report shows exactly that state.

At the time of writing the shipped file carries `steps: []`, so the report
returns nothing and the tests below fail on a wrong value, not on an
absent target (failure state 1 in `ai-toolkit:testing`).

Baseline recorded before these tests were written:
`uv run pytest tests/unit/launch tests/unit/shared/domain/test_discipline.py`
— 178 passed, 0 failed.

**This file is scheduled to be superseded, deliberately.** The delta's own
closing note: "This scenario describes the authoring-in-progress state
this change ships; once every rule policy is decided, a follow-up change
amends it rather than a fully decided playbook counting as a violation."
When that change lands, the non-emptiness assertion below is superseded
and should be removed *with* that change — not weakened to fit a playbook
that has since been fully decided.
"""

from __future__ import annotations

from typing import Final

from commerce_ops.launch.application import report_undecided_rule_policies
from commerce_ops.launch.domain.launch_playbook import ExecutionMode, StepDefinition
from commerce_ops.launch.infrastructure.driven.playbook_loader import (
    load_shipped_playbook,
)

# SPECIFIED: "human-attested steps MAY ship without one, appearing in the
# undecided-rule-policies report" — the only mode that may lack a policy.
POLICY_OPTIONAL_MODE: Final = ExecutionMode.HUMAN_ATTESTED


def _shipped_steps() -> tuple[StepDefinition, ...]:
    steps = tuple(load_shipped_playbook().steps)
    assert steps, "the shipped playbook carries no steps"
    return steps


def test_the_report_lists_exactly_the_shipped_steps_without_a_rule_policy() -> None:
    """Scenario: Outstanding rule-policy decisions stay visible.

    WHEN the undecided-rule-policies report runs over the shipped
    playbook while any human-attested step lacks a decided rule policy
    THEN it lists exactly those steps.
    """
    playbook = load_shipped_playbook()
    undecided = {
        step.identifier for step in _shipped_steps() if step.rule_policy is None
    }

    # The scenario's WHEN clause is itself a condition on the shipped
    # data: this change ships with rule policies outstanding (design.md
    # Decision 7 — two steps carry a policy, the rest deliberately do
    # not). Asserted, so the test cannot pass by both sides being empty.
    assert undecided != set()

    reported = {row.identifier for row in report_undecided_rule_policies(playbook)}

    # SPECIFIED: *exactly* those steps — neither a subset nor a superset.
    assert reported == undecided


def test_every_reported_step_is_human_attested() -> None:
    """Requirement statement: which steps may ship without a policy.

    "Steps whose execution mode requires a rule policy SHALL carry one;
    human-attested steps MAY ship without one, appearing in the
    undecided-rule-policies report."

    So every row the report returns for the shipped playbook must be a
    human-attested step. The infrastructure-tier counterpart asserts the
    other half — that automated and AI-assisted steps carry a policy.
    """
    playbook = load_shipped_playbook()

    rows = list(report_undecided_rule_policies(playbook))

    # Guard against a vacuous pass: the assertion below quantifies over
    # the reported rows, which the scenario above establishes are present.
    assert rows != []
    assert [
        row.identifier for row in rows if row.execution is not POLICY_OPTIONAL_MODE
    ] == []


def test_reported_rows_identify_the_shipped_steps_they_stand_for() -> None:
    """Scenario: Outstanding rule-policy decisions stay visible (identity).

    "it lists exactly those steps" — a row identifies a step by more than
    its identifier (the existing requirement *Undecided rule policies are
    reported* fixes the four fields). This checks each row's gate,
    discipline and execution agree with the shipped step it names, so a
    report that listed the right identifiers against the wrong steps
    would not pass.
    """
    playbook = load_shipped_playbook()
    steps = {step.identifier: step for step in _shipped_steps()}

    disagreements = [
        row.identifier
        for row in report_undecided_rule_policies(playbook)
        if (row.gate, row.discipline, row.execution)
        != (
            steps[row.identifier].gate,
            steps[row.identifier].discipline,
            steps[row.identifier].execution,
        )
    ]

    assert disagreements == []


# DELIBERATELY UNTESTED, recorded rather than omitted:
#
# - The number of undecided steps (design.md puts it at 95 of 97). The
#   delta requires the report to list *exactly* the policy-less steps,
#   which is asserted as a set equality against the shipped data — a
#   count would additionally freeze a curation decision the delta does
#   not state.
# - The two authored rule-policy strings themselves (design.md Decision
#   7). The delta requires only that steps needing a policy carry one;
#   their wording is the design's, and design.md names it a conservative
#   statement of current practice rather than a specified value.
