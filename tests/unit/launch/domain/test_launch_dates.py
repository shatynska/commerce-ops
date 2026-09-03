"""Tests for the `Launch` aggregate: due-period derivation, launch-date
movement, and at-risk evaluation.

Derived from the delta spec:
openspec/changes/introduce-launch-aggregate/specs/launch-instance/spec.md

Covers, at the domain level:

- ADDED Requirement: *Step due dates derive from the launch date and
  re-resolve when it moves* (all three scenarios).
- ADDED Requirement: *The launch date is reported at risk when a
  blocking unresolved step is overdue* (all four scenarios).

Both are pure functions of the aggregate, the pinned playbook, and — for
at-risk — an `as_of` date passed in (`design.md` Decision 6: the clock
never lives in the domain), so the domain unit tier is the smallest
level that can observe them.

At the time of writing `commerce_ops.launch.domain.launch_run` does not
exist, so every test here is expected to fail on an absent target
(`ModuleNotFoundError`). Per `ai-toolkit:testing`, that failure
establishes only absence.

The INVENTED interface shape shared with the other launch-run files is
recorded in `test_launch_run.py`'s docstring; this file adds:

- `launch.due_period_for(playbook, step_id)` returning the resolved
  range (with `.start` / `.end`, the spellings the timing-anchor tests
  already use) or `None` where no due period exists.
- `launch.move_launch_date(new_date)` returning events including
  `LaunchDateMoved` with `.previous` and `.new`.
- `launch.date_at_risk(playbook, as_of)` returning a falsy value when
  not at risk, and otherwise a `LaunchDateAtRisk` report whose rendering
  (`str`) names each overdue blocking step. If the implementation names
  the steps on a structured attribute instead, correcting how the naming
  is read is a fixture correction; that the step is named is SPECIFIED.

Expected dates are written as literals rather than recomputed with
`timedelta`, so the tests do not reuse the arithmetic they check
(the convention `test_timing_anchor.py` records).
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
    WindowAnchor,
)
from commerce_ops.launch.domain.launch_run import (
    Launch,
    LaunchDateMoved,
    LaunchStarted,
    Provenance,
)
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import ProductId
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

RECORDED_AT: Final = datetime(2027, 1, 5, 12, 0, tzinfo=UTC)

# DERIVED: the delta fixes no particular launch date. Chosen so that the
# -30-day offset under test crosses a month boundary, which a naive
# day-of-month implementation would get wrong.
LAUNCH_DATE: Final = date(2027, 4, 15)
# SPECIFIED literal for the scenario's "-30 days": the single day 30 days
# before 2027-04-15.
THIRTY_DAYS_BEFORE: Final = date(2027, 3, 16)
# Scenario: "moved to a date 14 days later".
MOVED_LAUNCH_DATE: Final = date(2027, 4, 29)
THIRTY_DAYS_BEFORE_MOVED: Final = date(2027, 3, 30)


def _any_discipline() -> Discipline:
    return next(iter(Discipline))


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": "listing.title-conforms",
        "name": "Work this step asks for",
        "gate": "listable",
        "discipline": _any_discipline(),
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-30),
        "blocking": False,
        "kind": StepKind.HUMAN,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    """A blocking filler holding `gate` — the gate-holding floor
    (`move-playbook-steps-to-postgres`) forbids coherent playbooks with
    unheld gates, so `_playbook` fills whichever gates the test's own
    steps leave unheld. Automated with a decided rule so no other
    coherence rule fires, and anchored a year *after* the launch so a
    filler can never be the overdue step an at-risk assertion is about."""
    return _step(
        identifier=f"hold.{gate}",
        gate=gate,
        blocking=True,
        kind=StepKind.AUTOMATED,
        status=StepStatus.ACTIVE,
        handler="fixture.holding_check",
        timing_anchor=OffsetAnchor(days=365),
    )


def _playbook(steps: tuple[StepDefinition, ...] = ()) -> LaunchPlaybook:
    held = {step.gate for step in steps if step.blocking}
    fillers = tuple(_hold(gate) for gate in SPECIFIED_GATE_ORDER if gate not in held)
    return LaunchPlaybook(version="test-v1", gates=_gates(), steps=(*steps, *fillers))


def _start(
    playbook: LaunchPlaybook, *, launch_date: date | None = None
) -> tuple[Launch, LaunchStarted]:
    """INVENTED call shape — the single point to correct if it differs."""
    return Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=launch_date
    )


def _provenance(**overrides: Any) -> Provenance:
    attributes: dict[str, Any] = {
        "source": "clickup",
        "who": "Helen",
        "when": RECORDED_AT,
        "evidence": "screenshot in the launch Slack thread",
    }
    attributes.update(overrides)
    return Provenance(**attributes)


# ---------------------------------------------------------------------------
# ADDED Requirement: Step due dates derive from the launch date and
# re-resolve when it moves
# ---------------------------------------------------------------------------


def test_a_steps_due_period_derives_from_the_launch_date() -> None:
    """Scenario: A step's due period derives from the launch date.

    WHEN a launch has a launch date and a step's timing anchor is an
    offset of -30 days
    THEN that step's due period is reported as the single day 30 days
    before the launch date.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                timing_anchor=OffsetAnchor(days=-30),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=LAUNCH_DATE)

    period = launch.due_period_for(playbook, "listing.title-conforms")

    # SPECIFIED: the single day 30 days before the launch date.
    assert period is not None
    assert period.start == THIRTY_DAYS_BEFORE
    assert period.end == THIRTY_DAYS_BEFORE


def test_without_a_launch_date_there_are_no_due_periods() -> None:
    """Scenario: Without a launch date there are no due periods.

    WHEN a launch has no launch date
    THEN every step's due period is reported as absent.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                timing_anchor=OffsetAnchor(days=-30),
            ),
            _step(
                identifier="rank.review-velocity",
                gate="ignition",
                timing_anchor=WindowAnchor(start=28, end=55),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=None)

    # SPECIFIED: reported as absent rather than invented — for every step.
    assert launch.due_period_for(playbook, "listing.title-conforms") is None
    assert launch.due_period_for(playbook, "rank.review-velocity") is None


def test_moving_the_launch_date_re_resolves_every_due_period() -> None:
    """Scenario: Moving the launch date re-resolves every due period.

    WHEN the launch date is moved to a date 14 days later
    THEN every step's due period is reported re-resolved from the new
    date, and a `LaunchDateMoved` occurrence carries the previous and new
    dates.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                timing_anchor=OffsetAnchor(days=-30),
            ),
            _step(
                identifier="rank.review-velocity",
                gate="ignition",
                timing_anchor=WindowAnchor(start=28, end=55),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=LAUNCH_DATE)

    events = launch.move_launch_date(MOVED_LAUNCH_DATE)

    # SPECIFIED: a `LaunchDateMoved` occurrence carrying the previous and
    # new dates. DERIVED: the attribute spellings `previous` / `new`.
    moved = [event for event in events if isinstance(event, LaunchDateMoved)]
    assert len(moved) == 1
    assert moved[0].previous == LAUNCH_DATE
    assert moved[0].new == MOVED_LAUNCH_DATE

    # SPECIFIED: every step's due period re-resolves at once from the new
    # date. Literals: 2027-04-29 - 30 days = 2027-03-30; offsets 28..55
    # after 2027-04-29 are 2027-05-27 .. 2027-06-23.
    offset_period = launch.due_period_for(playbook, "listing.title-conforms")
    assert offset_period is not None
    assert offset_period.start == THIRTY_DAYS_BEFORE_MOVED
    assert offset_period.end == THIRTY_DAYS_BEFORE_MOVED
    window_period = launch.due_period_for(playbook, "rank.review-velocity")
    assert window_period is not None
    assert window_period.start == date(2027, 5, 27)
    assert window_period.end == date(2027, 6, 23)


# ---------------------------------------------------------------------------
# ADDED Requirement: The launch date is reported at risk when a blocking
# unresolved step is overdue
# ---------------------------------------------------------------------------

# DERIVED: an evaluation date after the -30-day step's due period
# (2027-03-16) has fully passed, while still before the launch date.
AS_OF: Final = date(2027, 4, 1)


def test_an_overdue_unresolved_blocking_step_puts_the_date_at_risk() -> None:
    """Scenario: An overdue unresolved blocking step puts the date at
    risk.

    WHEN the launch is evaluated on a date after a blocking step's due
    period has fully passed and that step has not reached a permitted
    terminal outcome
    THEN a `LaunchDateAtRisk` occurrence is reported naming that step.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                blocking=True,
                timing_anchor=OffsetAnchor(days=-30),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=LAUNCH_DATE)

    report = launch.date_at_risk(playbook, AS_OF)

    # SPECIFIED: a `LaunchDateAtRisk` occurrence naming that step (naming
    # read via the report's rendering — see module docstring).
    assert report
    assert "listing.title-conforms" in str(report)


def test_an_overdue_non_blocking_step_does_not_put_the_date_at_risk() -> None:
    """Scenario: An overdue non-blocking step does not put the date at
    risk.

    WHEN the only steps whose due periods have passed unresolved are
    non-blocking
    THEN no `LaunchDateAtRisk` occurrence is reported.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                blocking=False,
                timing_anchor=OffsetAnchor(days=-30),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=LAUNCH_DATE)

    # SPECIFIED: not reported at risk.
    assert not launch.date_at_risk(playbook, AS_OF)


def test_a_resolved_overdue_step_does_not_put_the_date_at_risk() -> None:
    """Scenario: A resolved overdue step does not put the date at risk.

    WHEN every blocking step whose due period has passed has reached a
    permitted terminal outcome
    THEN no `LaunchDateAtRisk` occurrence is reported.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                blocking=True,
                timing_anchor=OffsetAnchor(days=-30),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=LAUNCH_DATE)
    launch.record_step_outcome(
        playbook,
        step_id="listing.title-conforms",
        outcome=Satisfied,
        provenance=_provenance(),
    )

    # SPECIFIED: not reported at risk.
    assert not launch.date_at_risk(playbook, AS_OF)


def test_a_launch_without_a_launch_date_is_never_at_risk() -> None:
    """Scenario: A launch without a launch date is never at risk.

    WHEN a launch with no launch date is evaluated
    THEN no `LaunchDateAtRisk` occurrence is reported.

    The playbook still carries a blocking step, so the outcome turns on
    the absent launch date rather than on there being nothing to be
    overdue.
    """
    playbook = _playbook(
        steps=(
            _step(
                identifier="listing.title-conforms",
                blocking=True,
                timing_anchor=OffsetAnchor(days=-30),
            ),
        )
    )
    launch, _ = _start(playbook, launch_date=None)

    # SPECIFIED: not reported at risk.
    assert not launch.date_at_risk(playbook, AS_OF)
