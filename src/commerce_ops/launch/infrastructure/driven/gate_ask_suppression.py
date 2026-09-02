"""Driven adapter: when a launch's gate was last put to a member.

Implements the retention half of `launch-gate-progression`'s *A gate is
asked about at most once a day*.

At most one row per (launch, gate). Its presence, and its age, are the
whole of what the once-a-day rule reads: an ask is owed only where no row
younger than the cool-off stands.

**Two writers, and the distinction matters.** `record_delivery` is written
only *after* the ask reaches Slack -- recording first and then failing to
deliver would silence a gate for a day with nobody having been asked, the
mistake `field_gap_suppression` documents for its own row. `record_rejection`
is written having delivered nothing at all: a member who declines a gate
starts the day running from their decision, or one who declines at hour 23
is asked again an hour later.

`is_suppressed` is offered alongside the raw read so a caller can ask the
question without reaching into the row. The caller supplies both the moment
and the cool-off: the clock never lives in a repository, and the cool-off is
a property of the pass that asks (`gate_progression_job.ASK_COOL_OFF`),
not of the storage that remembers.

Takes the caller's session rather than opening one, for the reason
`field_gap_suppression` records: a second session is a second transaction,
so a write here would escape whatever isolation its caller runs under --
which for the rejecting decision is exactly the transaction that makes it
land together with the approval it accompanies.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import text

from commerce_ops.shared.domain.identity import ProductId

__all__ = ["GateAskSuppressionRepository"]

_READ = text(
    """
    SELECT asked_at FROM launch_gate_ask_suppression
    WHERE product_id = :product_id AND gate_id = :gate_id
    """
)

_WRITE = text(
    """
    INSERT INTO launch_gate_ask_suppression (product_id, gate_id, asked_at)
    VALUES (:product_id, :gate_id, :asked_at)
    ON CONFLICT (product_id, gate_id) DO UPDATE
    SET asked_at = EXCLUDED.asked_at
    """
)


class GateAskSuppressionRepository:
    """The ask cool-off record, over the caller's session."""

    def __init__(self, db_session: Any) -> None:
        self._session = db_session

    async def read(
        self, product_id: ProductId, gate_id: str
    ) -> datetime.datetime | None:
        """When this launch's gate was last asked about or decided against."""
        result = await self._session.execute(
            _READ,
            {"product_id": uuid.UUID(product_id.value), "gate_id": gate_id},
        )
        row = result.first()
        return None if row is None else row[0]

    async def is_suppressed(
        self,
        product_id: ProductId,
        gate_id: str,
        *,
        now: datetime.datetime,
        cool_off: datetime.timedelta,
    ) -> bool:
        """Whether an ask is withheld for this launch and gate."""
        asked_at = await self.read(product_id, gate_id)
        return asked_at is not None and now - asked_at < cool_off

    async def record_delivery(
        self, product_id: ProductId, gate_id: str, when: datetime.datetime
    ) -> None:
        """Record a delivered ask. Called only after it reached Slack."""
        await self._write(product_id, gate_id, when)

    async def record_rejection(
        self, product_id: ProductId, gate_id: str, when: datetime.datetime
    ) -> None:
        """Record a rejecting decision, which delivered nothing.

        Commits like every other write here. What makes it land together
        with the rejecting approval is the `transaction()` its adapter
        opens around both: under that provider an inner commit releases a
        savepoint rather than ending the outer transaction, so the two
        writes stand or fall as one. Declining to commit here instead
        would lose the write outright for any caller that did not know to
        wrap it.
        """
        await self._write(product_id, gate_id, when)

    async def _write(
        self,
        product_id: ProductId,
        gate_id: str,
        when: datetime.datetime,
    ) -> None:
        await self._session.execute(
            _WRITE,
            {
                "product_id": uuid.UUID(product_id.value),
                "gate_id": gate_id,
                "asked_at": when,
            },
        )
        # Each repository in this project commits its own write; a caller
        # needing two to land together uses `transaction()`, which turns
        # this into a savepoint rather than a transaction boundary.
        await self._session.commit()
