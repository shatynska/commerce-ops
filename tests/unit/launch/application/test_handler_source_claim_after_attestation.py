"""A handler still cannot claim another source, once `attestation` is not
one of them.

Derived strictly from the delta spec:
`openspec/changes/replace-metric-conditions-with-steps/specs/launch-step-automation/spec.md`

Covers the MODIFIED requirement *A handler receives the step, the launch
and the product, and attributes nothing* — its scenario *A handler cannot
claim another source*, whose words this delta leaves unchanged while
striking `attestation` from the sources the requirement's own sentence
names ("A handler therefore cannot record work as having come from a
person or from ClickUp").

Its three other scenarios are untouched by this delta and stay covered by
`tests/unit/launch/application/test_step_handler_contract.py` and
`tests/unit/launch/infrastructure/driving/test_automation_pass.py`.

## Why this file exists at all

The scenario is already covered, in the contract half, by
`test_step_handler_contract.py::test_a_resolution_has_no_place_to_put_provenance`
— which smuggles a `Provenance(source="attestation", ...)`. Its
assertion survives this change; its **fixture** names a source the change
retires, and `tasks.md` 5.7 revises it. This file re-derives the same
scenario over a source that survives (`clickup`), so the coverage does
not depend on a value the change removes. It is additive: nothing here
edits that file, which `test-manifest.md` records as needing a fixture
correction rather than as superseded.

## Level

`StepResolution` construction. The refusal is the contract simply not
declaring the field, so constructing one is the smallest unit that
observes it — the level `test_step_handler_contract.py` records.

## What is fixed, and what is INVENTED

Fixed: the two-field `StepResolution(outcome, result)` shape, and that a
handler supplies no provenance of its own. INVENTED: `TypeError` as what
a dataclass raises for an argument it does not declare — Python's own
behaviour, named because it is what the assertion reads.

## Expected first-run state

`StepResolution` already refuses a `provenance` argument, so this test is
expected to **pass on its first run**. Its subject is unchanged by this
delta; what changes is only which source the fixture names. Per
`ai-toolkit:testing` a pass where the implementation exists is the
expected result, not the alarm state — the alarm is a pass where nothing
implements the behaviour.

Baseline recorded before these tests were written, at the worktree root,
branch `add-metric-attestation-surface`, clean tree: `uv run pytest` —
1982 passed, 176 skipped, 0 failed (the integration tier skipped
throughout: no database is configured here).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.launch.domain.launch_run import Provenance

AS_OF: Final = datetime(2027, 5, 3, 9, 15, tzinfo=UTC)
RESULT: Final = "72 fulfillable units reported by the inventory read"


def test_a_handler_cannot_claim_a_surviving_source() -> None:
    """Scenario: A handler cannot claim another source.

    WHEN a handler attempts to supply provenance of its own
    THEN the system rejects it and the provenance the system constructed
    stands.

    The smuggled source is `clickup` — one of the two the requirement
    still names — so the refusal is asserted over a value that outlives
    this change. A handler claiming `clickup` is the concrete harm the
    rule prevents: a completion the system would then report as a
    person's own, arriving through a channel nobody used.
    """
    smuggled = Provenance(
        source="clickup",
        who="a person who never saw this",
        when=AS_OF,
        evidence=RESULT,
    )

    # Called through an untyped alias: what this asserts is the runtime
    # refusal, the type checker's being a separate obligation.
    constructor: Any = StepResolution

    with pytest.raises(TypeError):
        constructor(outcome=Satisfied, result=RESULT, provenance=smuggled)

    # SPECIFIED: a resolution carries an outcome and the produced result,
    # and nothing that could stand in for provenance — asserted so the
    # rejection above cannot be satisfied by a contract that refuses
    # every keyword argument.
    accepted = StepResolution(outcome=Satisfied, result=RESULT)
    assert accepted.outcome is Satisfied
    assert accepted.result == RESULT
