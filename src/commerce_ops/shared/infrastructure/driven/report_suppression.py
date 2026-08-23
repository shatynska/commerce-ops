"""Driven adapter: which overdue reports have already been delivered.

Implements the `scheduled-jobs` capability's "A Continuing Outage Is Reported
Once, Not Repeatedly"
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`).

A row here means "an overdue report for this work has been delivered, and the
work has not succeeded since". The check reports only work that has no row, so
a continuing outage produces one message rather than one an hour.

**Written only after a delivery succeeds**, never before. Recording first and
then failing to deliver loses that period's only alarm permanently, since
suppression lifts when the work succeeds and not when Slack recovers. If the
write itself fails after a successful delivery, the next check reports again:
a duplicate message is the accepted outcome, consistent with preferring a
duplicate to a miss for the alarm itself (tasks.md 3.5, 3.7).

It is a table rather than process state because a restart must not resume the
flood, and it is separate from `known_work` because the two lifecycles are
incompatible -- see that module and design.md, "First-known is its own table".
"""

from __future__ import annotations

import datetime

from sqlalchemy import text

from commerce_ops.shared.infrastructure.driven.database import session

__all__ = [
    "clear_report_suppression",
    "record_report_delivered",
    "suppressed_identifiers",
]

_RECORD_DELIVERED = text(
    """
    INSERT INTO report_suppression (identifier, reported_at)
    VALUES (:identifier, :reported_at)
    ON CONFLICT (identifier) DO UPDATE SET reported_at = EXCLUDED.reported_at
    """
)

_CLEAR = text("DELETE FROM report_suppression WHERE identifier = :identifier")

_SUPPRESSED = text("SELECT identifier FROM report_suppression")


async def record_report_delivered(identifier: str) -> None:
    """Record that an overdue report for this work has been delivered."""
    async with session() as db_session:
        await db_session.execute(
            _RECORD_DELIVERED,
            {
                "identifier": identifier,
                "reported_at": datetime.datetime.now(datetime.UTC),
            },
        )
        await db_session.commit()


async def clear_report_suppression(identifier: str) -> None:
    """Lift suppression, because the work has succeeded.

    This is what makes a *recurrence* reportable again: the period of
    overdueness ended, so the next one is a new alarm rather than a repeat.
    """
    async with session() as db_session:
        await db_session.execute(_CLEAR, {"identifier": identifier})
        await db_session.commit()


async def suppressed_identifiers() -> set[str]:
    """Every piece of work whose overdue report has already been delivered."""
    async with session() as db_session:
        result = await db_session.execute(_SUPPRESSED)
        return {row.identifier for row in result}
