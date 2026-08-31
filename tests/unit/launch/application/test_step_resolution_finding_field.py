"""`StepResolution.finding` — the contract-level half of the typed-finding
requirements (`launch-step-automation`).

Derived from the change `write-the-advisors-finding-to-the-product`'s delta
spec:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/launch-step-automation/spec.md`

Covers, at construction level (no pass, no I/O):

- MODIFIED requirement *A handler receives the step, the launch and the
  product, and attributes nothing* — the contract-level half of scenario
  *A finding changes nothing about the outcome or the result*: adding a
  `finding` changes nothing about what `outcome`/`result` already mean.
  The full scenario ("the outcome is recorded, and the result is stored as
  evidence, exactly as they would be for a handler reporting no finding")
  is a pass-level claim and is covered in full in
  `tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py`;
  this file supplies the half observable on the dataclass alone.
- ADDED requirement *A handler MAY report a typed finding alongside its
  outcome* — the construction-level half of *A handler reports no finding
  by default*: `finding` defaults to `None`, so every pre-existing
  `StepResolution(outcome=..., result=...)` call (as in
  `tests/unit/launch/application/test_step_handler_contract.py`, still
  unedited by this pass) keeps constructing without change. The full
  scenario ("no finding is recorded anywhere on its behalf") is a
  pass-level claim, covered in `test_automation_pass_finding.py` above.

Existing coverage this file does not re-derive: every scenario `outcome`
and `result` already carried before this change — `test_step_handler_contract.py`
covers those, is unedited, and is unaffected by an additive, defaulted
field.

## Level

`StepResolution` is a frozen dataclass with no I/O; construction is the
smallest unit that can observe `finding`'s own contract.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 1's own code sample:

    StepResolution:  outcome, result, finding: Result[Any, Any] | None = None

INVENTED: none beyond what `test_step_handler_contract.py` already
records for `StepResolution` itself (`ValueError` for empty `result`,
`TypeError` for an unknown keyword) — this file adds only the new field.

## Expected first-run state

`finding` does not exist on `StepResolution` yet (`tasks.md` 2.1), so
every test here is expected to fail: either on a `TypeError` (the field is
rejected as an unknown keyword) or — for the two tests that pass no
`finding` at all — on `AttributeError` when reading `.finding` back. Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

import dataclasses

import pytest

from commerce_ops.launch.application import StepResolution
from commerce_ops.launch.domain.launch_playbook import Blocked, Satisfied
from commerce_ops.shared.domain.result import Failure, Success

RESULT_TEXT = (
    "Home & Kitchen > Kitchen & Dining > Cutting Boards. Demands: FDA "
    "food-contact declaration. Rejected alternative: Home & Kitchen > "
    "Home Decor."
)


def test_finding_defaults_to_none() -> None:
    """Scenario: A handler reports no finding by default (construction
    half).

    SPECIFIED: "A handler that has nothing for another part of the system
    to consume beyond its outcome and result text SHALL simply not report
    one" — expressed on the contract as a default, so a pre-existing
    caller supplying no `finding` keyword still constructs.
    """
    resolution = StepResolution(outcome=Satisfied, result=RESULT_TEXT)

    assert resolution.finding is None


def test_a_success_finding_is_accepted() -> None:
    """SPECIFIED: `finding` may carry "a success carrying a value"."""
    finding = Success(value="Home & Kitchen > Cutting Boards", comment="demands")

    resolution = StepResolution(outcome=Satisfied, result=RESULT_TEXT, finding=finding)

    assert resolution.finding is finding


def test_a_failure_finding_is_accepted() -> None:
    """SPECIFIED: `finding` may carry "a failure carrying an error"."""
    finding: Failure[str] = Failure(error="no verdict could be read")

    resolution = StepResolution(
        outcome=Blocked("no verdict could be read"), result=RESULT_TEXT, finding=finding
    )

    assert resolution.finding is finding


def test_a_finding_does_not_change_the_outcome_or_the_result_carried() -> None:
    """Scenario: A finding changes nothing about the outcome or the result
    (contract-level half).

    SPECIFIED: "The two SHALL be reported independently" — adding a
    `finding` leaves `outcome`/`result` exactly what they were constructed
    with.
    """
    finding = Success(value="node", comment="demands")

    with_finding = StepResolution(
        outcome=Satisfied, result=RESULT_TEXT, finding=finding
    )
    without_finding = StepResolution(outcome=Satisfied, result=RESULT_TEXT)

    assert with_finding.outcome is without_finding.outcome
    assert with_finding.result == without_finding.result


def test_the_resolution_stays_frozen_with_a_finding_carried() -> None:
    """DERIVED, mirroring `test_step_handler_contract.py`'s existing
    frozen-ness assertion for `result` — the new field should not weaken
    the type's existing immutability contract."""
    resolution = StepResolution(
        outcome=Satisfied, result=RESULT_TEXT, finding=Success(value="node")
    )

    assert dataclasses.is_dataclass(type(resolution))
    # Through a non-literal attribute name, per this project's convention
    # (`test_step_handler_contract.py`): the assertion is about
    # frozen-ness, not a spelling `mypy --strict` would reject outright.
    frozen_field = "finding"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(resolution, frozen_field, None)
