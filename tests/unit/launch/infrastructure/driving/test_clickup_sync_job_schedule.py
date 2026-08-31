"""The reconciliation pass is scheduled work, not something anyone triggers.

Derived strictly from the delta spec:
`openspec/changes/add-clickup-completion-loop/specs/launch-clickup-sync/spec.md`

Covers the opening clause of the ADDED requirement *The reconciliation pass
records completions and reopenings the webhook missed*:

    The system SHALL **periodically, on a declared schedule and without
    any request from outside the deployment**, read the ClickUp state of
    every active launch's mapped tasks ...

That clause is part of the requirement's statement rather than of any one
`#### Scenario:` block, so the four scenarios it also carries are covered
elsewhere -- in
`tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`,
which asserts what the pass records. This file asserts only that the pass
is reached on a schedule and by nothing else.

The job is never addressed by name here. It is found through its fixed
placement -- `tasks.md` 6.1 puts it in
`launch/infrastructure/driving/` -- so nothing in this file pins a task
name or a module path, following
`tests/unit/catalog/infrastructure/driving/test_daily_digest_job.py`'s own
"one correction point" convention.

## What is INVENTED

Only the assumption that importing a composition root registers the job,
which is how `commerce_ops.worker` already works and what
`tests/unit/test_registrations_across_processes.py` records. The runner
application object's location (`RUNNER_MODULE`/`RUNNER_APP_ATTRIBUTE`) is
transcribed from that existing file rather than invented afresh.

## At the time this pass was written, the job does not exist

`launch/infrastructure/driving/clickup_sync_job.py` is created by task
6.1 and added to `registrations.py` by task 6.2. Until then the lookup
below finds nothing and every test here fails on an absent target. Per
`ai-toolkit:testing`, that failure establishes only absence.
"""

from __future__ import annotations

import datetime
from typing import Any

import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app
from commerce_ops.shared.infrastructure.driven.recurring_work import registered_work

# `tasks.md` 6.1's fixed placement -- the reconciliation job is the one
# scheduled job this change adds, and it lives in the launch module's
# driving layer.
JOB_PACKAGE = "commerce_ops.launch.infrastructure.driving"

# `design.md`: "Cadence: every 30 minutes, tolerance sized per the
# `scheduled-jobs` overdue conventions", lowered to 10 on 2026-08-24, then
# to twice daily on 2026-08-31 (see `SYNC_SCHEDULE`'s own note). DERIVED
# from design.md, not from a scenario -- the spec fixes only that a
# schedule is declared. If the cadence is revised again, this figure is
# the thing to correct.
EXPECTED_INTERVAL_SECONDS = 12 * 60 * 60


def _reconciliation_periodic() -> Any:
    """The ClickUp reconciliation job, found by placement and subject."""
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "clickup" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the ClickUp reconciliation "
        f"pass under {JOB_PACKAGE!r}; registered periodics are "
        f"{[entry.task.name for entry in registered]}"
    )
    return matching[0]


def _tolerance_seconds(entry: Any) -> float | None:
    for attribute in ("tolerance", "tolerance_seconds"):
        value = getattr(entry, attribute, None)
        if isinstance(value, datetime.timedelta):
            return value.total_seconds()
        if isinstance(value, int | float):
            return float(value)
    return None


def _registrations() -> list[Any]:
    declared = registered_work()
    if hasattr(declared, "values"):
        return list(declared.values())
    return list(declared)


def test_the_reconciliation_pass_runs_on_a_declared_schedule() -> None:
    """Requirement clause: "periodically, on a declared schedule".

    SPECIFIED: the pass is declared as recurring work with a schedule, so
    a due moment causes a run. What that schedule is, is asserted
    separately below.
    """
    entry = _reconciliation_periodic()

    assert entry.cron, "the ClickUp reconciliation pass has an empty schedule"


def test_the_declared_schedule_becomes_due_every_twelve_hours() -> None:
    """Requirement clause: "periodically".

    SPECIFIED: consecutive due moments exist, so the pass is periodic
    rather than declared once and never due again. DERIVED (`design.md`,
    "Cadence: every 30 minutes", revised to 10, then to twice daily on
    2026-08-31): the interval itself. If the cadence is revised again,
    this figure is the thing to correct -- the periodicity it guards is
    not.
    """
    entry = _reconciliation_periodic()
    reference = datetime.datetime(2027, 3, 10, 12, 0, tzinfo=datetime.UTC).timestamp()

    first = entry.croniter.get_next(ret_type=float, start_time=reference)
    second = entry.croniter.get_next(ret_type=float, start_time=first)

    assert second - first == EXPECTED_INTERVAL_SECONDS, (
        "expected consecutive due moments 12 hours apart, got "
        f"{(second - first) / 60:.1f} minutes"
    )


def test_the_reconciliation_pass_declares_a_tolerance() -> None:
    """DERIVED from `tasks.md` 6.1 ("tolerance per `scheduled-jobs`
    conventions"), guarding the `scheduled-jobs` capability's own
    "Each Piece Of Recurring Work Declares Its Schedule And Tolerance In
    One Place" against this change's addition.

    Not a `#### Scenario:` block of this change's delta spec: it is a
    published requirement of another capability that adding a job could
    break, recorded here rather than left to surface as an unexplained
    failure in `test_recurring_work_registry.py`.
    """
    entry = _reconciliation_periodic()
    task_name = entry.task.name

    declaring = [
        registration
        for registration in _registrations()
        if task_name
        in {
            str(getattr(registration, attribute, ""))
            for attribute in ("identifier", "id", "task_name", "name")
        }
    ]
    assert len(declaring) == 1, (
        f"the reconciliation pass runs as periodic {task_name!r} but has "
        f"{len(declaring)} registration(s) declaring a tolerance for it"
    )
    tolerance = _tolerance_seconds(declaring[0])
    assert tolerance is not None and tolerance > 0, (
        "the reconciliation pass is registered with no usable tolerance, so "
        "a run it silently stopped making would never be reported overdue"
    )


def test_no_externally_reachable_route_starts_the_reconciliation_pass() -> None:
    """Requirement clause: "without any request from outside the
    deployment".

    SPECIFIED. Read the same way
    `tests/unit/test_no_external_cadence_trigger.py` reads the equivalent
    `scheduled-jobs` clause: this application's one externally reachable
    surface is the FastAPI app in `commerce_ops.main`, so enumerating its
    OpenAPI paths is the enumeration the clause asks for. The webhook this
    change *does* mount is a completion delivery, not a way to start the
    pass, so a path naming reconciliation or synchronisation is what would
    violate this.
    """
    from commerce_ops.main import app

    paths = sorted(app.openapi().get("paths", {}))
    assert paths, "the application exposes no paths at all, which cannot be right"

    offending = [
        path
        for path in paths
        if any(word in path.lower() for word in ("reconcil", "sync"))
    ]
    assert offending == [], (
        "these externally reachable routes name the reconciliation pass, so "
        f"it has an external trigger surface: {offending}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - The job body's own behaviour: that it runs the convergence pass and
#   then the pull half over `list_active()`. What each pass does is
#   asserted directly against those passes in
#   `tests/unit/launch/infrastructure/driven/`, at a level that needs no
#   runner; asserting the job's internal call order would pin a wiring no
#   scenario states.
# - Retry behaviour on a failed run. `scheduled-jobs` already requires and
#   tests it (`test_daily_digest_job.py`), and this change's delta adds no
#   scenario about it.
# ---------------------------------------------------------------------------
