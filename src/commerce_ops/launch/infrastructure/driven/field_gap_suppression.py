"""Driven adapter: which Custom Field configuration gap has been reported.

Implements the retention half of `launch-clickup-sync`'s *The Custom Field
configuration is checked once per pass and a gap is reported without
stopping the pass*.

At most one row. It means "a gap of exactly this content has been reported,
and the configuration has not changed since". A pass reports only a gap whose
content differs from the row's, so a misconfiguration standing over days
produces one message rather than one per pass.

**Written only after a delivery succeeds**, never before. Recording first and
then failing to deliver would silence that gap permanently, since the row is
lifted by the configuration being repaired and not by Slack recovering. Where
the write fails *after* a successful delivery the gap simply stays eligible
and the next pass reports again -- a duplicate message, which is the accepted
trade and the same one `scheduled-jobs` makes for a continuing outage.

A table rather than process state, because a restart must not resume the
flood; and a table of its own rather than `scheduled_run_report_suppression`,
whose row is lifted when its work *succeeds* -- this pass succeeds precisely
while the gap stands, so that lifecycle would clear the row on the very
passes it exists to suppress. See the migration and design.md, "Suppression
gets its own table".
"""

from __future__ import annotations

import datetime
from typing import Any

from sqlalchemy import text

__all__ = [
    "clear_reported_field_gap",
    "record_field_gap_reported",
    "reported_field_gap",
]

_READ = text("SELECT identity FROM clickup_field_gap_suppression WHERE id IS TRUE")

_RECORD = text(
    """
    INSERT INTO clickup_field_gap_suppression (id, identity, reported_at)
    VALUES (TRUE, :identity, :reported_at)
    ON CONFLICT (id) DO UPDATE
    SET identity = EXCLUDED.identity, reported_at = EXCLUDED.reported_at
    """
)

_CLEAR = text("DELETE FROM clickup_field_gap_suppression WHERE id IS TRUE")


async def reported_field_gap(db_session: Any) -> str | None:
    """The content of the gap last reported, or `None` where none stands.

    Takes the pass's own session rather than opening one. That is not an
    optimisation: a second session is a second transaction, so a write here
    would escape whatever isolation its caller is running under -- which in
    the integration tier means data outliving the test that made it. It also
    makes the requirement's premise true by construction, since the record
    genuinely shares the store the launches' writes use.
    """
    result = await db_session.execute(_READ)
    row = result.first()
    return None if row is None else str(row[0])


async def record_field_gap_reported(identity: str, db_session: Any) -> None:
    """Record that a gap of exactly this content has been delivered.

    Called only after the report reached Slack. Upserts rather than inserts:
    a gap whose content changed has already been reported under the new
    content by the time this runs, and the row must follow it.
    """
    await db_session.execute(
        _RECORD,
        {
            "identity": identity,
            "reported_at": datetime.datetime.now(tz=datetime.UTC),
        },
    )
    # Each repository in this project commits its own write; a caller needing
    # two to land together uses `transaction()`, which turns these into
    # savepoints rather than transaction boundaries.
    await db_session.commit()


async def clear_reported_field_gap(db_session: Any) -> None:
    """Lift the suppression, so a gap appearing again is reported again.

    Called on a pass that finds no gap -- the configuration was repaired --
    and on one that performs no check because the capability was withdrawn,
    since a deployment that has opted out has no standing gap for a report to
    be suppressed against and leaving the row would let a later opt-in meet
    an unrepaired gap in silence.

    **Not** called on a stand-down, on a failed folder read, or where no
    launch folder is configured: none of those says anything about the
    configuration, and lifting on them would make a deployment whose playbook
    or reachability flaps re-report the same unrepaired gap on every pass --
    the flood the report-once rule exists to prevent, arriving by the other
    door.
    """
    await db_session.execute(_CLEAR)
    await db_session.commit()
