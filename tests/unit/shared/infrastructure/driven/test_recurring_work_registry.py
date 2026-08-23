"""Each piece of recurring work declares its schedule and tolerance once.

Derived strictly from the delta spec of the OpenSpec change
`report-overdue-scheduled-runs`
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`):

- "Each Piece Of Recurring Work Declares Its Schedule And Tolerance In One
  Place" / Scenarios: Every piece of work the runner will run has a
  tolerance; The schedule run and the schedule checked are the same value;
  A tolerance exceeds its work's longest scheduling gap
- "The Process Running Scheduled Work Is Itself Monitored Work" /
  Scenarios: The worker's own liveness is monitored work; An absent worker
  becomes visible well before the work it runs is overdue

See `test-manifest.md` at the change root for the full
specified/derived/deliberately-untested accounting and for the unresolved
project questions this file's assumptions are recorded under.

## The registry is enumerated from the runner, not from itself

tasks.md 1.6b is load-bearing on how the first test below is written. The
set enumerated is **the job runner's registered periodics**, and the
registry is what each of them is looked up in. Enumerating the registry
instead makes the assertion circular: it can only find what is already
there, so a periodic the runner will actually run but that never reached
the registry passes unnoticed while being invisible to both the overdue
check and the freshness endpoint. `test_a_periodic_missing_from_the_
registry_is_caught` exists to show the enumeration used here would in fact
catch that.

## The single correction point

`REGISTRY_MODULE` / `REGISTRY_ACCESSOR` below. No artifact fixes a module
or attribute name for the registry -- tasks.md 1.1 says only "a registry in
`shared`", and design.md only that `shared` owns it. `shared.application`
may not import `shared.infrastructure` (`.importlinter`'s `module-layers`)
while the single registration helper of tasks.md 1.1a must apply the
runner's periodic decorator, which lives in
`shared/infrastructure/driven/job_runner.py` -- so the registry is assumed
to live beside it in `shared/infrastructure/driven/`. If it lands elsewhere
or under another name, this pair of constants is the only thing to correct.

`commerce_ops.registrations.register_all` is **not** invented: tasks.md 1.3
fixes both the module path and the function name, and it is called at
import here for the reason that task gives -- it is what populates the
registry, and tasks.md 6.15 requires tests to read the registry
`registrations.py` populates rather than an ad-hoc one built in the test.
It is called rather than merely imported because tasks.md 1.4b requires it
to be idempotent per identifier, so a second call in a process where
another test file already called it is well defined.

Task placement is not invented either: tasks.md 4.1 fixes the overdue
check's home as `shared/infrastructure/driving/`, which is how
`_worker_liveness_periodic` identifies it without transcribing a task name.

## Assumed registry shape, and how much of it is load-bearing

`registered_work()` returns either a mapping of identifier to entry or an
iterable of entries; an entry carries `schedule` (the cron expression) and
`tolerance` (a `timedelta`, or a number of seconds). The helpers below
accommodate both representations of each -- that is fixture-level
accommodation of a shape no artifact fixes, not a weakening of any
assertion, since every assertion is made on the normalized value.

Whether a registry identifier is the runner's own task name is left open:
design.md's illustrative JSON shows `product-daily-digest` where the
runner's task is named `products.monitoring.daily`, so `_names` treats both
`identifier` and an optional `task_name` as names a piece of work answers
to. What is asserted is that the runner's task name is among them.

At the time this pass was written none of the target exists: the registry,
`registrations.py` and the overdue-check job are all introduced by this
change. Every test here is expected to fail on an absent target
(`ModuleNotFoundError`) until tasks 1.1, 1.1a, 1.3 and 4.1 land. That
failure establishes absence and nothing about whether the assertions below
are any good.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from croniter import croniter

from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app
from commerce_ops.shared.infrastructure.driven.recurring_work import registered_work

# The single correction point -- recorded as constants as well as imported,
# so a failure message can name what was looked for.
REGISTRY_MODULE = "commerce_ops.shared.infrastructure.driven.recurring_work"
REGISTRY_ACCESSOR = "registered_work"

# tasks.md 4.1: the overdue check is a driving adapter of `shared`. This is
# how the worker-liveness registration is identified below without
# transcribing a task name no artifact fixes.
OVERDUE_CHECK_PACKAGE = "commerce_ops.shared.infrastructure.driving"

# How far ahead the longest-gap computation looks. Long enough to contain a
# full quarterly cycle and both ends of a month-length swing, since the
# requirement's own reason clause names "weekdays only, or monthly" as the
# schedules a uniform-gap assumption gets wrong.
HORIZON_DAYS = 400
_MAX_OCCURRENCES = 60_000

# Populating the registry is the point of importing this: see the module
# docstring.
register_all()


# --------------------------------------------------------------------------
# Reaching the registrations and the runner's periodics
# --------------------------------------------------------------------------


def _registrations() -> list[Any]:
    """Every registered piece of recurring work, however the registry is
    shaped."""
    declared = registered_work()
    if hasattr(declared, "values"):
        entries = list(declared.values())
        if entries and not any(hasattr(entry, "identifier") for entry in entries):
            # A mapping whose entries carry no identifier of their own: the
            # key is the identifier, so carry it alongside.
            return [_KeyedEntry(key, entry) for key, entry in declared.items()]
        return entries
    return list(declared)


class _KeyedEntry:
    """A registry entry whose identifier is its mapping key."""

    def __init__(self, key: str, entry: Any) -> None:
        self.identifier = key
        self._entry = entry

    def __getattr__(self, name: str) -> Any:
        return getattr(self._entry, name)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return f"_KeyedEntry({self.identifier!r}, {self._entry!r})"


def _names(entry: Any) -> set[str]:
    """Every name a registered piece of work answers to.

    Both `identifier` and `task_name` are accepted because no artifact
    fixes whether they are the same string -- see the module docstring.
    """
    names = {
        str(getattr(entry, attribute))
        for attribute in ("identifier", "id", "task_name", "name")
        if getattr(entry, attribute, None) is not None
    }
    if not names:
        pytest.fail(
            f"a registry entry carries no identifier of any kind: {entry!r}. "
            "The overdue check and the freshness endpoint both have to name "
            "the work they report on."
        )
    return names


def _identifier(entry: Any) -> str:
    for attribute in ("identifier", "id", "task_name", "name"):
        value = getattr(entry, attribute, None)
        if value is not None:
            return str(value)
    return repr(entry)


def _schedule(entry: Any) -> str:
    for attribute in ("schedule", "cron"):
        value = getattr(entry, attribute, None)
        if value is not None:
            return str(value)
    pytest.fail(
        f"the registration for {_identifier(entry)!r} carries no schedule. "
        "tasks.md 1.1 requires the registry to hold each piece of work's "
        "schedule as well as its tolerance, and the longest-gap check has "
        "nothing to compute from without it."
    )


def _tolerance_seconds(entry: Any) -> float:
    for attribute in ("tolerance", "tolerance_seconds"):
        value = getattr(entry, attribute, None)
        if value is None:
            continue
        if isinstance(value, datetime.timedelta):
            return value.total_seconds()
        if isinstance(value, (int, float)):
            return float(value)
        pytest.fail(
            f"the tolerance registered for {_identifier(entry)!r} is neither "
            f"a timedelta nor a number of seconds: {value!r}"
        )
    pytest.fail(
        f"no tolerance is registered for {_identifier(entry)!r}; every piece "
        "of recurring work SHALL have a declared tolerance."
    )


def _registered_periodics() -> list[Any]:
    return list(runner_app.periodic_registry.periodic_tasks.values())


def _worker_liveness_registration() -> Any:
    """The registration standing for the worker process's own liveness.

    Identified through tasks.md 4.1's fixed placement -- the overdue check
    is the one scheduled job in `shared/infrastructure/driving/`, and
    tasks.md 4.7 enrols its own successful runs as the liveness evidence.
    """
    check_periodics = [
        entry
        for entry in _registered_periodics()
        if entry.task.func.__module__.startswith(OVERDUE_CHECK_PACKAGE)
    ]
    assert len(check_periodics) == 1, (
        "expected exactly one scheduled job under "
        f"{OVERDUE_CHECK_PACKAGE!r} (the overdue check, tasks.md 4.1); "
        f"found {[entry.task.name for entry in check_periodics]}"
    )
    task_name = check_periodics[0].task.name
    matching = [entry for entry in _registrations() if task_name in _names(entry)]
    assert len(matching) == 1, (
        f"the overdue check runs as periodic {task_name!r} but has "
        f"{len(matching)} registration(s) declaring a tolerance for it; its "
        "own successful runs are the worker's liveness evidence, so it has "
        "to be monitored work like any other"
    )
    return matching[0]


# --------------------------------------------------------------------------
# The longest gap between consecutive scheduled runs
# --------------------------------------------------------------------------


def _longest_gap_seconds(schedule: str) -> float:
    """The longest gap between consecutive runs of `schedule` over a
    bounded horizon.

    Computed rather than assumed uniform: the requirement's own reason
    clause is that a schedule with unequal gaps -- weekdays only, or
    monthly -- must not report itself overdue across its longest gap.

    The horizon starts at a fixed instant so this is deterministic; the
    start is a Thursday in a 31-day month, so a weekday-only schedule's
    weekend gap and a month-boundary gap both fall inside it well before
    the horizon ends.
    """
    start = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    end = start + datetime.timedelta(days=HORIZON_DAYS)
    cursor = croniter(schedule, start)
    previous = cursor.get_next(datetime.datetime)
    longest = 0.0
    occurrences = 0
    while previous < end:
        following = cursor.get_next(datetime.datetime)
        longest = max(longest, (following - previous).total_seconds())
        previous = following
        occurrences += 1
        if occurrences > _MAX_OCCURRENCES:
            pytest.fail(
                f"schedule {schedule!r} produced more than {_MAX_OCCURRENCES} "
                f"occurrences within {HORIZON_DAYS} days; the horizon or the "
                "schedule is not what this computation assumes"
            )
    if longest == 0.0:
        pytest.fail(
            f"schedule {schedule!r} produced no consecutive pair of runs "
            f"within {HORIZON_DAYS} days, so it has no computable gap"
        )
    return longest


# --------------------------------------------------------------------------
# Requirement: Each Piece Of Recurring Work Declares Its Schedule And
# Tolerance In One Place
# --------------------------------------------------------------------------


def _periodics_without_a_tolerance(
    periodic_names: list[str], registrations: list[Any]
) -> list[str]:
    """Which of `periodic_names` no registration declares a tolerance for.

    Written as a pure function over both enumerations so that
    `test_a_periodic_missing_from_the_registry_is_caught` can exercise it
    against a periodic that is deliberately absent, without touching the
    process-global runner registry.
    """
    declared: set[str] = set()
    for entry in registrations:
        _tolerance_seconds(entry)
        declared |= _names(entry)
    return [name for name in periodic_names if name not in declared]


def test_every_piece_of_work_the_runner_will_run_has_a_tolerance() -> None:
    """Scenario: Every piece of work the runner will run has a tolerance.

    WHEN the pieces of recurring work the job runner will actually run on a
    schedule are enumerated
    THEN each SHALL have a declared tolerance
    AND none SHALL be absent from the declaration the overdue check and the
    freshness interface read.

    SPECIFIED. Enumerated from the runner's own periodic registry, per
    tasks.md 1.6b -- see the module docstring.
    """
    periodic_names = [entry.task.name for entry in _registered_periodics()]
    assert periodic_names, (
        "the job runner has no registered periodics at all after "
        "register_all(), so this assertion would hold vacuously"
    )

    missing = _periodics_without_a_tolerance(periodic_names, _registrations())

    assert missing == [], (
        f"the runner will run {missing} on a schedule, but no tolerance is "
        "declared for them; they are invisible to both the overdue check "
        "and the freshness endpoint"
    )


def test_a_periodic_missing_from_the_registry_is_caught() -> None:
    """DERIVED guard on the test above, required by tasks.md 6.20.

    Not itself a `#### Scenario:` block. It exists because the assertion
    above is only worth anything if enumerating from the runner would in
    fact catch a periodic the registry never received -- the circularity
    tasks.md 1.6b names. Exercised against the real registrations plus one
    synthetic periodic name, so nothing process-global is mutated.
    """
    stray = "commerce_ops.tests.a_periodic_nobody_declared_a_tolerance_for"
    periodic_names = [entry.task.name for entry in _registered_periodics()] + [stray]

    missing = _periodics_without_a_tolerance(periodic_names, _registrations())

    assert missing == [stray], (
        "the enumeration used by "
        "test_every_piece_of_work_the_runner_will_run_has_a_tolerance does "
        "not notice a periodic that is absent from the registry, so that "
        "test cannot distinguish a complete registry from an empty one"
    )


def test_the_schedule_run_and_the_schedule_checked_are_the_same_value() -> None:
    """Scenario: The schedule run and the schedule checked are the same
    value.

    WHEN a piece of work's schedule as given to the job runner is compared
    to the schedule its tolerance was checked against
    THEN they SHALL be the same value.

    SPECIFIED. This is the verification tasks.md 1.1a's single-registration
    mechanism is meant to make unnecessary -- and which, until now, nothing
    performed: a job module that declared the cron expression to the runner
    and passed a copy to the registry would satisfy every other assertion
    in this file while the two values drifted.
    """
    registrations = _registrations()
    mismatches: list[str] = []
    for entry in _registered_periodics():
        declared = [
            registration
            for registration in registrations
            if entry.task.name in _names(registration)
        ]
        assert len(declared) == 1, (
            f"periodic {entry.task.name!r} has {len(declared)} registrations; "
            "the previous test covers absence, so this is a duplicate"
        )
        registered_schedule = _schedule(declared[0]).strip()
        runner_schedule = str(entry.cron).strip()
        if registered_schedule != runner_schedule:
            mismatches.append(
                f"{entry.task.name}: runner runs {runner_schedule!r}, "
                f"registry checks {registered_schedule!r}"
            )

    assert mismatches == [], (
        "the schedule a piece of work is run on and the schedule its "
        "tolerance was checked against are different values: "
        f"{mismatches}"
    )


def test_each_tolerance_exceeds_its_works_longest_scheduling_gap() -> None:
    """Scenario: A tolerance exceeds its work's longest scheduling gap.

    WHEN a piece of recurring work's tolerance is compared to the longest
    gap between consecutive scheduled runs over a bounded horizon
    THEN the tolerance SHALL be the longer of the two.

    SPECIFIED. The gap is computed from the schedule expression over a
    bounded horizon rather than assumed uniform (tasks.md 1.6): a
    weekday-only schedule gaps 72 hours over a weekend and a monthly one
    28-31 days, and a tolerance shorter than that reports the work overdue
    across a gap it was always going to have.
    """
    registrations = _registrations()
    assert registrations, "no recurring work is registered at all"

    too_short: list[str] = []
    for entry in registrations:
        schedule = _schedule(entry)
        tolerance = _tolerance_seconds(entry)
        longest_gap = _longest_gap_seconds(schedule)
        if tolerance <= longest_gap:
            too_short.append(
                f"{_identifier(entry)}: schedule {schedule!r} gaps up to "
                f"{longest_gap:.0f}s, tolerance is {tolerance:.0f}s"
            )

    assert too_short == [], (
        "a tolerance does not exceed the longest gap between consecutive "
        f"runs of its own schedule, so the work reports itself overdue "
        f"across a gap its schedule always had: {too_short}"
    )


# --------------------------------------------------------------------------
# Requirement: The Process Running Scheduled Work Is Itself Monitored Work
# --------------------------------------------------------------------------


def test_the_workers_own_liveness_is_monitored_work() -> None:
    """Scenario: The worker's own liveness is monitored work.

    WHEN the pieces of recurring work subject to overdue determination are
    enumerated
    THEN they SHALL include evidence of the worker process's own liveness.

    SPECIFIED. The evidence is the overdue check's own successful runs
    (tasks.md 4.7): it runs inside the worker and records a run each time,
    so a registration declaring a tolerance for it is what makes the
    worker's absence subject to the same overdue determination as anything
    else.
    """
    registration = _worker_liveness_registration()

    assert _tolerance_seconds(registration) > 0, (
        "the worker's liveness evidence is registered with a "
        "non-positive tolerance, so it would be overdue immediately"
    )


def test_an_absent_worker_becomes_visible_before_the_work_it_runs() -> None:
    """Scenario: An absent worker becomes visible well before the work it
    runs is overdue.

    WHEN the process running scheduled work becomes unavailable
    THEN its liveness evidence SHALL become overdue before any work it runs
    on a longer schedule does.

    SPECIFIED as a comparison between tolerances rather than against a
    figure: design.md's Open Questions record the hourly interval, the
    liveness tolerance and the digest's 30 hours as initial figures, so
    what the scenario fixes is the ordering, not the numbers.
    """
    liveness = _worker_liveness_registration()
    liveness_tolerance = _tolerance_seconds(liveness)
    liveness_names = _names(liveness)

    others = {
        _identifier(entry): _tolerance_seconds(entry)
        for entry in _registrations()
        if not (_names(entry) & liveness_names)
    }
    assert others, (
        "the worker's liveness is the only registered work, so this "
        "comparison would hold vacuously; the daily digest is registered "
        "too (tasks.md 1.2)"
    )

    not_later = {
        identifier: tolerance
        for identifier, tolerance in others.items()
        if tolerance <= liveness_tolerance
    }
    assert not_later == {}, (
        f"the worker's own liveness tolerance is {liveness_tolerance:.0f}s, "
        "which is not shorter than the tolerance of work it runs "
        f"({not_later}); an absent worker would become visible no sooner "
        "than the work it failed to run, which is what enrolling its "
        "liveness exists to avoid"
    )
