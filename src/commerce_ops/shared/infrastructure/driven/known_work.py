"""Driven adapter: when the system first knew of each piece of recurring work.

Implements the `scheduled-jobs` capability's "Work Is Overdue Relative To Its
Last Success Or To When It Was First Known"
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`).

This is the anchor a never-succeeded piece of work is measured from. Without
it there is nothing to subtract a tolerance from, so work that has never run
could either never be overdue or be overdue from the epoch -- and a freshly
deployed system would alarm on its first request.

**The recorded time is the first observed and is never advanced.** A later
observation leaves it alone, and a success does not erase it: the suppression
record is what a success clears, not this. See design.md, "First-known is its
own table".

Written from both processes -- the overdue check in the worker and the
freshness endpoint's handler -- because a worker that never starts would
otherwise leave every piece of work without an anchor, and the endpoint could
then compute no overdueness and would report healthy forever.
"""

from __future__ import annotations

import datetime

from sqlalchemy import text

from commerce_ops.shared.infrastructure.driven.database import session

__all__ = ["first_known_times", "record_first_known"]

# `ON CONFLICT DO NOTHING` is what makes this idempotent and non-advancing in
# one statement: the first writer's time stands, and every later request is a
# no-op rather than an update. Doing it as read-then-write would race two
# concurrent requests into advancing it.
_RECORD_FIRST_KNOWN = text(
    """
    INSERT INTO known_work (identifier, first_known_at)
    VALUES (:identifier, :first_known_at)
    ON CONFLICT (identifier) DO NOTHING
    """
)

_FIRST_KNOWN_TIMES = text("SELECT identifier, first_known_at FROM known_work")


async def record_first_known(identifiers: list[str]) -> None:
    """Anchor each identifier that has no anchor yet, leaving the rest alone."""
    if not identifiers:
        return
    now = datetime.datetime.now(datetime.UTC)
    async with session() as db_session:
        for identifier in identifiers:
            await db_session.execute(
                _RECORD_FIRST_KNOWN,
                {"identifier": identifier, "first_known_at": now},
            )
        await db_session.commit()


async def first_known_times() -> dict[str, datetime.datetime]:
    """When each recorded piece of work was first known, by identifier."""
    async with session() as db_session:
        result = await db_session.execute(_FIRST_KNOWN_TIMES)
        return {row.identifier: row.first_known_at for row in result}
