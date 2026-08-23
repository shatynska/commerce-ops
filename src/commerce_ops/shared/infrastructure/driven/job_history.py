"""Driven adapter: reading the job runner's own run history.

Implements the `scheduled-jobs` capability's "Every Run's Outcome Is Recorded
And Can Be Asked About Afterwards"
(`openspec/changes/replace-cron-with-job-runner/specs/scheduled-jobs/spec.md`).

Lives beside the queue it reads. `report-overdue-scheduled-runs` consumes
this from both the worker and the HTTP process; it is implemented here rather
than there because this change specifies and tests the behaviour, and
`proposal.md` claims queryability as its own deliverable.

**Read through the application's session provider, not the runner's own
connector.** The sibling change's freshness endpoint calls this from the HTTP
process, which would otherwise acquire the queue's psycopg pool for a read
that is not queue work -- widening to the HTTP process a two-driver footprint
design.md scopes to the worker. The cost, stated plainly: this means raw SQL
against the runner's physical tables rather than its supported job-manager
API, which is a tighter coupling than "the runner is swappable" would admit.
See design.md, "The accessor queries through the session provider".
"""

from __future__ import annotations

import datetime

from sqlalchemy import text

from commerce_ops.shared.infrastructure.driven.database import session

# A run spans its retries: one job, whose end is the moment of the outcome
# that stopped it. The `succeeded` event carries that moment, so the most
# recent successful run is the latest such event for the named work -- see
# the requirement's "A run spans its retries" clause.
_LAST_SUCCESS = text(
    """
    SELECT max(events.at) AS at
    FROM procrastinate_events AS events
    JOIN procrastinate_jobs AS jobs ON jobs.id = events.job_id
    WHERE jobs.task_name = :task_name
      AND events.type = 'succeeded'
    """
)


async def last_successful_run(task_name: str) -> datetime.datetime | None:
    """When the named recurring work most recently succeeded.

    Returns `None` when it has never succeeded -- distinct from a time, so
    "never succeeded" cannot be mistaken for "succeeded long ago", which is
    the distinction an overdue check has to make.
    """
    async with session() as db_session:
        result = await db_session.execute(_LAST_SUCCESS, {"task_name": task_name})
        return result.scalar_one_or_none()
