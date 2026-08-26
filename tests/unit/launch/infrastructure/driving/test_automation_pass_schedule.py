"""The automation pass is scheduled work, and nothing outside starts it.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/launch-step-automation/spec.md`

Covers the two clauses of the ADDED requirement *An automated step's
handler is invoked by recurring work* that its four scenarios do not
carry:

    The system SHALL invoke registered step handlers from **recurring
    work that runs inside the deployment, declaring its schedule and
    tolerance** as `scheduled-jobs` requires of every piece of recurring
    work.

    **Invocation SHALL NOT be reachable from outside the deployment.**

The four scenarios themselves — what a pass invokes, records and holds —
are covered in
`tests/unit/launch/infrastructure/driving/test_automation_pass.py`, at a
level needing no runner.

This file follows
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py`,
which reads the same two clauses for this module's other recurring walk:
the job is never addressed by module path or task name, only found
through the runner's own periodic registry by placement and subject, so
nothing here pins a name the implementation is free to choose.

## What is INVENTED

Only that importing a composition root registers the job, which is how
`commerce_ops.worker` already works
(`tests/unit/test_registrations_across_processes.py`), and the
identifying assumption that the registered task's module or name contains
"automation" (`_automation_periodic` below). `tasks.md` 4.1 fixes that
the module is `automation_pass.py` under this package and that it is
registered through `@register_scheduled`; 4.7 adds it to
`registrations.py`'s one list.

`AUTOMATION_SCHEDULE = "*/15 * * * *"` and a six-hour tolerance are fixed
by `tasks.md` 4.1 and `design.md`, but they are DERIVED with respect to
the *spec*, which requires only that a schedule and a tolerance be
declared. If the cadence is revised, `EXPECTED_INTERVAL_SECONDS` is the
figure to correct — the periodicity it guards is not.

## Expected first-run state

`launch/infrastructure/driving/automation_pass.py` does not exist, so the
selector below finds no matching periodic and fails loudly rather than
passing vacuously. Per `ai-toolkit:testing`, that failure establishes
absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
"""

from __future__ import annotations

import datetime
from typing import Any, Final

import commerce_ops.worker  # noqa: F401 -- importing a root registers its work
from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app
from commerce_ops.shared.infrastructure.driven.recurring_work import registered_work

JOB_PACKAGE: Final = "commerce_ops.launch.infrastructure.driving"

# `tasks.md` 4.1: `AUTOMATION_SCHEDULE = "*/15 * * * *"`.
EXPECTED_INTERVAL_SECONDS: Final = 15 * 60


def _automation_periodic() -> Any:
    """The automation pass, found by placement and subject."""
    registered = list(runner_app.periodic_registry.periodic_tasks.values())
    matching = [
        entry
        for entry in registered
        if entry.task.func.__module__.startswith(JOB_PACKAGE)
        and "automation" in (entry.task.func.__module__ + entry.task.name).lower()
    ]
    assert len(matching) == 1, (
        "expected exactly one scheduled job for the step-automation pass "
        f"under {JOB_PACKAGE!r}; registered periodics are "
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


def test_handlers_are_invoked_from_work_that_runs_on_a_declared_schedule() -> None:
    """Requirement clause: "from recurring work that runs inside the
    deployment, declaring its schedule".

    SPECIFIED: the invocation path is declared recurring work with a
    schedule, so a due moment causes a pass. What that schedule is, is
    asserted separately below.
    """
    entry = _automation_periodic()

    assert entry.cron, "the step-automation pass has an empty schedule"


def test_the_declared_schedule_becomes_due_every_fifteen_minutes() -> None:
    """Requirement clause: recurring work.

    SPECIFIED: consecutive due moments exist, so the pass is periodic
    rather than declared once and never due again — which is what makes a
    handler's "not resolved yet" answerable, the reason `design.md` gives
    for choosing a pass over event-driven invocation. DERIVED
    (`tasks.md` 4.1): the fifteen-minute interval itself.
    """
    entry = _automation_periodic()
    reference = datetime.datetime(2027, 3, 10, 12, 0, tzinfo=datetime.UTC).timestamp()

    first = entry.croniter.get_next(ret_type=float, start_time=reference)
    second = entry.croniter.get_next(ret_type=float, start_time=first)

    assert second - first == EXPECTED_INTERVAL_SECONDS, (
        "expected consecutive due moments 15 minutes apart, got "
        f"{(second - first) / 60:.1f} minutes"
    )


def test_the_automation_pass_declares_a_tolerance() -> None:
    """Requirement clause: "declaring its schedule **and tolerance** as
    `scheduled-jobs` requires of every piece of recurring work".

    SPECIFIED by the requirement statement, and simultaneously the
    `scheduled-jobs` capability's own "Each Piece Of Recurring Work
    Declares Its Schedule And Tolerance In One Place" — a pass registered
    with no tolerance would never be reported overdue, so a worker that
    silently stopped running it would be invisible.
    """
    entry = _automation_periodic()
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
        f"the automation pass runs as periodic {task_name!r} but has "
        f"{len(declaring)} registration(s) declaring a tolerance for it"
    )
    tolerance = _tolerance_seconds(declaring[0])
    assert tolerance is not None and tolerance > 0, (
        "the automation pass is registered with no usable tolerance, so a "
        "run it silently stopped making would never be reported overdue"
    )


def test_no_externally_reachable_route_invokes_a_handler() -> None:
    """Requirement clause: "Invocation SHALL NOT be reachable from
    outside the deployment."

    SPECIFIED. Read the same way
    `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py`
    and `tests/unit/test_no_external_cadence_trigger.py` read the
    equivalent clauses: this application's one externally reachable
    surface is the FastAPI app in `commerce_ops.main`, so enumerating its
    OpenAPI paths is the enumeration the clause asks for.

    The Slack decision surface this change *does* add is a decision on a
    result a pass already produced, not a way to invoke a handler, so a
    path naming automation, a handler or a resolution is what would
    violate this.
    """
    from commerce_ops.main import app

    paths = sorted(app.openapi().get("paths", {}))
    assert paths, "the application exposes no paths at all, which cannot be right"

    offending = [
        path
        for path in paths
        if any(word in path.lower() for word in ("automation", "handler", "resolve"))
    ]
    assert offending == [], (
        "these externally reachable routes name handler invocation, so it "
        f"has an external trigger surface: {offending}"
    )
