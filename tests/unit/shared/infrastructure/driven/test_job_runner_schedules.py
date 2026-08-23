"""What the job runner has, and has not, been given a schedule for.

Derived strictly from the delta specs of the OpenSpec change
`replace-cron-with-job-runner`:

- `specs/scheduled-jobs/spec.md`
  - "Recurring Work Runs On Its Declared Schedule" / Scenario: Work with
    no declared schedule does not run
  - "A Window Missed While No Worker Was Available Is Run Once On Return"
    / Scenarios: A single missed window is run on return; Several missed
    windows produce one run
- `specs/product-monitoring/spec.md`
  - ADDED "The Daily Cadence Runs On A Schedule": "The weekly, biweekly,
    monthly and quarterly cadences SHALL NOT be scheduled while they have
    no reporting content"

See `test-manifest.md` at the change root for the full accounting.

## What is invented here

`RUNNER_MODULE`/`RUNNER_APP_ATTRIBUTE` -- design.md fixes the directory
for the runner's application object but no artifact fixes a module or
attribute name. This is the single correction point.
`commerce_ops.worker` is not invented (tasks.md 2.8), and is imported for
the reason that task gives: importing it is what registers the job
definitions, so a worker that registers nothing fails here.

## The missed-window seam

The two missed-window scenarios are about what happens when a worker
starts and finds due moments already passed. That is the periodic
deferrer's job, and this file drives the deferrer directly -- built from
the runner application object's own registry and periodic defaults,
exactly as `procrastinate`'s worker builds it (verified against
procrastinate 3.9.0, `worker.py`) -- rather than starting a real worker
and waiting for wall-clock time to pass.

This makes the runner's `max_delay` configuration load-bearing on
behaviour rather than on timing alone: with the runner's default
(10 minutes), a due moment missed by longer than that is dropped, which
is what "rather than skipping it silently" forbids. tasks.md 2.5
anticipates exactly this ("determine whether the runner performs a missed
window once on return by default or requires configuration ... If it
turns out neither configurable nor defaulted this way, stop and report").
These tests are not to be weakened to fit whatever the default happens to
be.

At the time this pass was written the runner is not a dependency of this
project, so every test here is expected to fail on an absent target
(`ModuleNotFoundError`) until tasks 1.1, 2.1, 2.2 and 2.8 land.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from procrastinate import periodic

import commerce_ops.worker  # noqa: F401  -- registers the job definitions
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

RUNNER_MODULE = "commerce_ops.shared.infrastructure.driven.job_runner"
RUNNER_APP_ATTRIBUTE = "app"

# The four cadences this change takes off the schedule. Transcribed from
# the delta spec's own wording ("The weekly, biweekly, monthly and
# quarterly cadences SHALL NOT be scheduled").
UNSCHEDULED_CADENCES = ("weekly", "biweekly", "monthly", "quarterly")

# A moment at which the daily schedule is already past for the day: the
# schedule is due at 06:00, so a worker returning at 08:00 has missed that
# day's window by two hours.
_MISSED_BY_TWO_HOURS = datetime.datetime(
    2026, 3, 10, 8, 0, tzinfo=datetime.UTC
).timestamp()

# The same, after a three-day absence: the 11th, 12th and 13th of March
# each had a 06:00 due moment pass with no worker available, of which
# exactly one run is owed on return.
_MISSED_FOR_THREE_DAYS = datetime.datetime(
    2026, 3, 13, 8, 0, tzinfo=datetime.UTC
).timestamp()


def _registered_periodics() -> list[Any]:
    return list(runner_app.periodic_registry.periodic_tasks.values())


def _fresh_deferrer() -> periodic.PeriodicDeferrer:
    """A deferrer as a just-started worker has one: no record of any
    previous defer, and configured the way the application configures it.
    """
    return periodic.PeriodicDeferrer(
        registry=runner_app.periodic_registry, **runner_app.periodic_defaults
    )


# The piece of work the catch-up scenarios below are stated about. They say
# "that work" and "the same piece of recurring work", not "the system in
# total" -- so the runs owed are counted for one piece of work, not summed
# across the registry. Enumerating every periodic was equivalent only while
# exactly one existed; `report-overdue-scheduled-runs` adds the hourly
# overdue check, and each piece of work catching up once would otherwise read
# as the catch-up firing twice.
#
# Retargeted by `introduce-launch-briefing`: the daily slot's occupant is
# now the launch briefing, the retired product-name digest having given up
# its schedule. The scenarios are about *a* daily piece of work catching
# up, not about which one — but the name must name something registered,
# or every filter below silently matches nothing and the assertions go
# vacuous rather than red.
_CATCH_UP_WORK = "briefing.daily"


def _runs_owed_at(
    moment: float, task_name: str = _CATCH_UP_WORK
) -> list[tuple[str, int]]:
    """The runs a worker becoming available at `moment` owes `task_name`."""
    return [
        (entry.task.name, timestamp)
        for entry, timestamp in _fresh_deferrer().get_previous_tasks(at=moment)
        if entry.task.name == task_name
    ]


# --------------------------------------------------------------------------
# Requirement: Recurring Work Runs On Its Declared Schedule
# --------------------------------------------------------------------------


def test_exactly_the_declared_pieces_of_recurring_work_are_scheduled() -> None:
    """Scenario: Work with no declared schedule does not run.

    WHEN a piece of work exists but has no declared schedule
    THEN the system SHALL NOT run it on a schedule.

    SPECIFIED, from `product-monitoring`'s ADDED requirement: the daily
    cadence is scheduled and the other four are not. Asserted as an exact
    count as well as by name, so that scheduling some *other* recurring
    work without a spec to declare it also fails here.
    """
    registered = _registered_periodics()

    names = [entry.task.name.lower() for entry in registered]
    assert len(registered) == 3, (
        "expected exactly three scheduled pieces of recurring work -- the "
        "daily cadence, `report-overdue-scheduled-runs`' hourly overdue "
        "check, and `add-clickup-completion-loop`' ClickUp completion pass "
        f"-- got {names}"
    )
    assert any("daily" in name for name in names), (
        f"the daily cadence is not among the scheduled work: {names}"
    )
    assert any("overdue" in name for name in names), (
        f"the overdue check is not among the scheduled work: {names}"
    )
    assert any("clickup" in name for name in names), (
        f"the ClickUp completion pass is not among the scheduled work: {names}"
    )


@pytest.mark.parametrize("cadence", UNSCHEDULED_CADENCES)
def test_an_unimplemented_cadence_has_no_declared_schedule(cadence: str) -> None:
    """Scenario: Work with no declared schedule does not run.

    Each of the four cadences whose reporting content is deferred must
    have no schedule at all -- not a schedule pointing at a no-op.
    """
    scheduled = [entry.task.name.lower() for entry in _registered_periodics()]

    assert not any(cadence in name for name in scheduled), (
        f"the {cadence} cadence is scheduled, although it has no reporting "
        f"content; scheduled work: {scheduled}"
    )


# --------------------------------------------------------------------------
# Requirement: A Window Missed While No Worker Was Available Is Run Once On
# Return
# --------------------------------------------------------------------------


def test_a_single_missed_window_is_run_on_return() -> None:
    """Scenario: A single missed window is run on return.

    WHEN a piece of recurring work's due moment passes with no process
    available, and a process then becomes available
    THEN the system SHALL run that work.

    SPECIFIED: the work runs, rather than being skipped silently. The
    moment used is two hours past the due moment -- longer than the
    runner's own default tolerance, deliberately: a test inside that
    default would pass without the deliberate decision this requirement
    exists to force.
    """
    owed = _runs_owed_at(_MISSED_BY_TWO_HOURS)

    assert len(owed) == 1, (
        "a due moment that passed while no worker was available produced "
        f"{len(owed)} runs on the worker's return, expected 1: {owed}"
    )
    ran_for = datetime.datetime.fromtimestamp(owed[0][1], datetime.UTC)
    assert ran_for.hour == 6, (
        f"the run performed on return is not the missed 06:00 window: {ran_for}"
    )


def test_several_missed_windows_produce_one_run() -> None:
    """Scenario: Several missed windows produce one run.

    WHEN more than one due moment for the same piece of recurring work
    passes with no process available, and a process then becomes available
    THEN the system SHALL run that work exactly once, not once per missed
    moment.
    """
    owed = _runs_owed_at(_MISSED_FOR_THREE_DAYS)

    assert len(owed) == 1, (
        "three days of missed due moments produced "
        f"{len(owed)} runs on the worker's return, expected exactly 1: {owed}"
    )


def test_the_run_performed_on_return_is_the_most_recent_missed_window() -> None:
    """Scenario: Several missed windows produce one run.

    DERIVED from the requirement's own reason clause -- "a report is a
    statement about the present, and replaying a backlog of them produces
    a burst of stale reports rather than one useful one". The scenario
    fixes the count at one; this fixes *which* one, since a single run
    replaying the oldest missed window would satisfy the count while
    producing exactly the stale report the requirement rejects.
    """
    owed = _runs_owed_at(_MISSED_FOR_THREE_DAYS)

    assert owed, "no run was owed at all"
    ran_for = datetime.datetime.fromtimestamp(owed[0][1], datetime.UTC)
    assert ran_for.date() == datetime.date(2026, 3, 13), (
        "the run performed on return replays an older missed window rather "
        f"than the most recent one: {ran_for}"
    )


def test_a_worker_that_never_went_away_defers_nothing_extra() -> None:
    """DERIVED guard, from the same requirement's "not silently skipped
    and not replayed once per missed window".

    A deferrer that has already handled a window must not hand the same
    window out again on its next pass -- otherwise "run once" would hold
    only for the first worker to return, and a running worker would
    re-run the day's digest on every loop.
    """
    deferrer = _fresh_deferrer()

    first = [
        entry
        for entry in deferrer.get_previous_tasks(at=_MISSED_BY_TWO_HOURS)
        if entry[0].task.name == _CATCH_UP_WORK
    ]
    second = [
        entry
        for entry in deferrer.get_previous_tasks(at=_MISSED_BY_TWO_HOURS + 60)
        if entry[0].task.name == _CATCH_UP_WORK
    ]

    assert len(first) == 1
    assert second == [], (
        "the same due moment was handed out twice by one deferrer, so a "
        "running worker would re-run the same window"
    )
