"""What release does, and does not, do to the at-risk judgement
(`launch-instance`).

Derived strictly from the delta spec
`openspec/changes/let-a-step-say-when-it-starts/specs/launch-instance/spec.md`
— MODIFIED *The launch date is reported at risk when a blocking
unresolved step is overdue*, and only the three scenarios that requirement
adds:

- *A blocking step whose start gate is not reached does not put the date
  at risk*
- *A blocking step held by a dependency puts the date at risk*
- *The gate the launch stands at still puts the date at risk*

Its other four scenarios are reproduced from the served spec — one of
them with "a blocking step" reworded to "a released blocking step" — and
are covered by `test_launch_dates.py` in this directory, whose fixtures
declare no start gate and are therefore released from the first gate.
They are accounted for against those tests in the manifest at
`openspec/changes/let-a-step-say-when-it-starts/test-manifest.md`.

## Level

`Launch.date_at_risk(playbook, as_of)` — the same level and the same
call shape `test_launch_dates.py` records, which is the smallest unit
that can observe the occurrence.

## INVENTED, with correction points

- `starts_at_gate` / `after_steps` as constructor keywords on
  `StepDefinition`. Correction point: `_step`.
- That the occurrence "names" a step is read as the identifier appearing
  in the report's rendering — taken unchanged from `test_launch_dates.py`,
  which records why.

## Expected first-run state

Neither field exists, so every test here is expected to fail on an
**absent target** (`TypeError` from the constructor). That establishes
absence and nothing about these assertions.

Baseline recorded before these tests were written: `uv run pytest
tests/unit tests/agents` — 1556 passed, 0 failed; `uv run pytest
tests/integration` — 118 passed, 1 skipped — at the worktree root on
2026-08-29.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any, Final

from commerce_ops.launch.domain.launch_playbook import (
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import (
    ApprovalDecision,
    GateApproval,
    Launch,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import CONFIRMATION_GATES, SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

A_DISCIPLINE: Final = next(iter(Discipline))

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)
APPROVED_AT: Final = datetime(2027, 1, 6, 9, 0, tzinfo=UTC)

# DERIVED dates, taken from `test_launch_dates.py`: a -30-day offset from
# 2027-04-15 is the single day 2027-03-16, fully past on 2027-04-01,
# which is itself before the launch date.
LAUNCH_DATE: Final = date(2027, 4, 15)
AS_OF: Final = date(2027, 4, 1)


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
        "discipline": A_DISCIPLINE,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": None,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate`, anchored a year *after* the
    launch so a filler can never be the overdue step an assertion is
    about, and declaring neither start field so it is never the reason a
    launch is or is not at risk."""
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        gate=gate,
        blocking=True,
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook(*steps: StepDefinition) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(
        version="at-risk-v1", gates=_gates(), steps=(*steps, *fillers)
    )


def _provenance() -> Provenance:
    return Provenance(
        source="clickup",
        who="Helen",
        when=RECORDED_AT,
        evidence="screenshot in the launch Slack thread",
    )


def _approval() -> GateApproval:
    return GateApproval(
        decision=ApprovalDecision.APPROVING,
        approver="Helen",
        when=APPROVED_AT,
        posture=None,
    )


def _start(playbook: LaunchPlaybook) -> Launch:
    launch, _ = Launch.start(
        product_id=ProductId(str(uuid.uuid4())),
        playbook=playbook,
        launch_date=LAUNCH_DATE,
    )
    return launch


def _advance_to(launch: Launch, playbook: LaunchPlaybook, gate: str) -> Launch:
    while launch.current_gate != gate:
        for step in playbook.steps_for_gate(launch.current_gate):
            if step.blocking and launch.progress_for(step.identifier) is None:
                launch.record_step_outcome(
                    playbook,
                    step_id=step.identifier,
                    outcome=Satisfied,
                    provenance=_provenance(),
                )
        if launch.current_gate in CONFIRMATION_GATES:
            launch.approve_gate(launch.current_gate, _approval())
        launch.advance_gate(playbook)
    return launch


# ---------------------------------------------------------------------------
# MODIFIED Requirement: The launch date is reported at risk when a blocking
# unresolved step is overdue (the three new scenarios)
# ---------------------------------------------------------------------------


def test_a_blocking_step_whose_start_gate_is_not_reached_does_not_put_the_date_at_risk() -> (
    None
):
    """Scenario: A blocking step whose start gate is not reached does not
    put the date at risk.

    WHEN a launch standing at `commit` holds an unresolved blocking step
    that starts at `live` and whose due period has fully passed
    THEN no `LaunchDateAtRisk` occurrence is reported naming that step.

    SPECIFIED reason: "work nobody has been asked for is not work anyone
    is late with".
    """
    unreached = _step(
        identifier="ppc.late-blocking-work",
        gate="live",
        blocking=True,
        starts_at_gate="live",
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(unreached)
    launch = _start(playbook)

    assert launch.current_gate == "commit"

    report = launch.date_at_risk(playbook, AS_OF)

    # SPECIFIED: no occurrence naming that step. Written as "not named"
    # rather than "no occurrence at all", because the requirement excludes
    # this step, not every step.
    assert "ppc.late-blocking-work" not in str(report or "")


def test_a_blocking_step_held_by_a_dependency_puts_the_date_at_risk() -> None:
    """Scenario: A blocking step held by a dependency puts the date at
    risk.

    WHEN a launch has reached a blocking step's start gate, that step
    waits on an unresolved dependency which is not itself overdue, and
    the blocking step's due period has fully passed
    THEN a `LaunchDateAtRisk` occurrence is reported naming that blocking
    step.

    SPECIFIED: "This is the case in which the at-risk signal matters most,
    and an exclusion drawn any wider than the start gate would remove
    it." The dependency is anchored a year after the launch precisely so
    that it is *not* itself overdue — otherwise the occurrence could be
    raised for the dependency and this assertion would establish nothing
    about the blocking step.
    """
    dependency = _step(
        identifier="listing.photos-approved",
        gate="listable",
        timing_anchor=OffsetAnchor(days=365),
    )
    blocking = _step(
        identifier="listing.holds-listable",
        gate="listable",
        blocking=True,
        starts_at_gate="commit",
        after_steps=("listing.photos-approved",),
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(dependency, blocking)
    launch = _start(playbook)

    assert launch.current_gate == "commit"
    assert launch.progress_for("listing.photos-approved") is None

    report = launch.date_at_risk(playbook, AS_OF)

    assert report
    assert "listing.holds-listable" in str(report)


def test_the_gate_the_launch_stands_at_still_puts_the_date_at_risk() -> None:
    """Scenario: The gate the launch stands at still puts the date at risk.

    WHEN a launch standing at `listable` has an unresolved blocking
    `listable`-gate step whose due period has fully passed
    THEN a `LaunchDateAtRisk` occurrence is reported naming that step.

    SPECIFIED: "What is excluded is only the work of the gates ahead of
    the launch. Whatever is holding the launch up at the gate it actually
    stands at is still reported." `tasks.md` 6.3 asks for this as the
    guard against an exclusion that hides a real delay.
    """
    blocking = _step(
        identifier="listing.holds-listable",
        gate="listable",
        blocking=True,
        starts_at_gate="listable",
        timing_anchor=OffsetAnchor(days=-30),
    )
    playbook = _playbook(blocking)
    launch = _advance_to(_start(playbook), playbook, "listable")

    assert launch.progress_for("listing.holds-listable") is None

    report = launch.date_at_risk(playbook, AS_OF)

    assert report
    assert "listing.holds-listable" in str(report)
