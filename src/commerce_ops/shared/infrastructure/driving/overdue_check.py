"""Driving adapter: the scheduled check that reports work which has stopped.

Implements the `scheduled-jobs` capability's "Overdue Work Is Reported To
Slack From Inside The Deployment", "The Process Running Scheduled Work Is
Itself Monitored Work" and "A Continuing Outage Is Reported Once, Not
Repeatedly"
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`).

Lives in `shared/infrastructure/driving/` rather than in `application/`: a
scheduled job is a driving adapter, and that layer may import
`shared.infrastructure.driven`, where the last-success accessor and both
repositories live -- which `shared.application` could not. It must not import
`products`; `.importlinter`'s `shared-boundary` enforces that, which is why
the notifier arrives through a port rather than by import (design.md, "The
check lives in `shared/infrastructure/driving/`").

Collaborators are imported by name into this module's namespace and referenced
as bare globals, keeping `daily_digest_job.py`'s own pattern -- which is what
lets tests substitute fakes with `monkeypatch.setattr`.
"""

from __future__ import annotations

import datetime
import logging

from commerce_ops.shared.application.ports import MonitoringNotifier
from commerce_ops.shared.infrastructure.driven.job_history import last_successful_run
from commerce_ops.shared.infrastructure.driven.known_work import (
    first_known_times,
    record_first_known,
)
from commerce_ops.shared.infrastructure.driven.recurring_work import (
    register_scheduled,
    registered_work,
)
from commerce_ops.shared.infrastructure.driven.report_suppression import (
    clear_report_suppression,
    record_report_delivered,
    suppressed_identifiers,
)

__all__ = [
    "CHECK_SCHEDULE",
    "CHECK_TOLERANCE",
    "TASK_NAME",
    "check_for_overdue_work",
    "clear_report_suppression",
    "first_known_times",
    "last_successful_run",
    "notifier",
    "record_first_known",
    "record_report_delivered",
    "registered_work",
    "suppressed_identifiers",
]

_logger = logging.getLogger(__name__)

TASK_NAME = "shared.scheduled_runs.overdue_check"

# Hourly. The reporting delay a piece of work suffers is bounded by this, not
# by its own schedule, so it wants to be well inside the shortest tolerance
# being watched.
CHECK_SCHEDULE = "0 * * * *"

# The check's own tolerance, and therefore how quickly an absent worker
# becomes visible through the freshness endpoint. Deliberately far shorter
# than the digest's 30 hours: without enrolling the check itself, the
# endpoint's dead-worker latency would be bounded below by the shortest
# tolerance it watches, which is roughly when a human would notice the digest
# missing anyway -- and the endpoint would have bought nothing. An initial
# figure, better chosen after a few weeks of real run history (design.md,
# Open Questions).
CHECK_TOLERANCE = datetime.timedelta(hours=4)

# Injected by `worker.py` after `register_all()`, never at import and never as
# a job argument. `shared` may not import `products`, and the runner passes
# only serializable values to a job, so the notifier cannot travel either way.
# It is `None` in the HTTP process, which registers the same job module but
# never runs it. See design.md, "The overdue check reports through a
# `Protocol` port, injected by `worker.py`".
notifier: MonitoringNotifier | None = None


def _describe(identifier: str, last_success: datetime.datetime | None) -> str:
    if last_success is None:
        return f"Scheduled work {identifier!r} has never succeeded and is now overdue."
    return (
        f"Scheduled work {identifier!r} is overdue; it last succeeded at "
        f"{last_success.isoformat()}."
    )


async def _deliver(message: str) -> bool:
    """Post the report, saying whether it actually arrived.

    The return value is what decides whether suppression is written, so a
    failed delivery leaves the work eligible to be reported again next hour
    rather than being silently suppressed (tasks.md 3.5).
    """
    if notifier is None:
        _logger.error(
            "overdue work was found but no monitoring notifier is configured; "
            "the report was not delivered"
        )
        return False
    try:
        await notifier.post_monitoring_message(message)
    except Exception:
        _logger.exception("failed to deliver an overdue-work report")
        return False
    return True


@register_scheduled(
    name=TASK_NAME,
    schedule=CHECK_SCHEDULE,
    tolerance=CHECK_TOLERANCE,
)
async def check_for_overdue_work(timestamp: int) -> None:
    """Report each piece of recurring work that has stopped happening.

    Completing this evaluation is what counts as a successful run, whether or
    not any report could be delivered. Failing the run on a delivery failure
    would make this job's own liveness evidence stale during a Slack outage,
    so the freshness endpoint would report an absent worker while the worker
    was running normally -- a false page, and it would make the deliberately
    Slack-independent endpoint Slack-dependent (tasks.md 4.8).
    """
    work = registered_work()
    await record_first_known(sorted(work))
    anchors = await first_known_times()
    suppressed = await suppressed_identifiers()
    now = datetime.datetime.now(datetime.UTC)

    for identifier in sorted(work):
        entry = work[identifier]
        last_success = await last_successful_run(identifier)
        # Measured from the last success, or -- where there has never been one
        # -- from when the work was first known. A work with neither cannot be
        # judged at all, so it is left alone rather than reported from the
        # epoch.
        reference = last_success or anchors.get(identifier)
        if reference is None:
            continue

        if now - reference <= entry.tolerance:
            if identifier in suppressed:
                # The work has succeeded since it was reported, which ends
                # that period of overdueness and makes a recurrence
                # reportable again.
                await clear_report_suppression(identifier)
            continue

        if identifier in suppressed:
            continue

        if await _deliver(_describe(identifier, last_success)):
            await record_report_delivered(identifier)
