"""Driven adapter: the launch journal's append-only store.

Implements `launch-journal`'s persistence
(`openspec/changes/add-launch-journal/`). Three methods, and each is
small on purpose: the journal has no update path and no delete path, so
there is nothing here to diff or reconcile.

Callers own the `AsyncSession`; `append` commits its own write, the
convention this package's `launch_repository` records.

**`rollback` is part of the port, not an implementation detail.** A
failed append leaves the session refusing every later statement, and the
use case's containment calls this so that the command's remaining work —
most sharply the catalog stamp a graduating advance performs — runs on a
usable session. Without it, catching the append's exception would still
let the journal break a graduation.

An entry that names no moment is stamped here from the database clock
(`func.now()`, the `launch_positions.created_at` precedent), because the
application layer holds no clock (design.md Decision 6).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.application.journal import JournalOccurrence
from commerce_ops.launch.infrastructure.driven.models import LaunchJournalEntry
from commerce_ops.shared.domain.identity import ProductId


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    """The row key for a product identifier, or None where the opaque
    value cannot be a row key at all — read as a product with no launch,
    which the journal reports as an empty journal rather than an error."""
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


class LaunchJournalRepository:
    """`LaunchJournal` over Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(self, occurrence: JournalOccurrence) -> None:
        """Insert one entry. Never an update: a second occurrence against
        the same subject is a second row."""
        row_id = _row_id(occurrence.product_id)
        if row_id is None:
            raise ValueError(
                f"'{occurrence.product_id.value}' is not a product identifier "
                f"a launch journal entry can reference"
            )
        entry = LaunchJournalEntry(
            product_id=row_id,
            kind=occurrence.kind,
            actor=occurrence.actor,
            source=occurrence.source,
            subject_id=occurrence.subject_id,
            subject_label=occurrence.subject_label,
            details=dict(occurrence.details),
        )
        if occurrence.occurred_at is not None:
            # Left unset otherwise, so the column's server default — the
            # database clock — stamps an occurrence that names no moment.
            entry.occurred_at = occurrence.occurred_at
        self._session.add(entry)
        await self._session.commit()

    async def read(self, product_id: ProductId) -> tuple[JournalOccurrence, ...]:
        """One launch's entries, most recent first.

        Ordered by the moment each entry names, ties broken by append
        order with the later append first — so two entries stamped in the
        same reconciliation pass still report in the order they happened.
        """
        row_id = _row_id(product_id)
        if row_id is None:
            return ()
        result = await self._session.execute(
            select(LaunchJournalEntry)
            .where(LaunchJournalEntry.product_id == row_id)
            .order_by(
                LaunchJournalEntry.occurred_at.desc(),
                LaunchJournalEntry.sequence.desc(),
            )
        )
        return tuple(
            JournalOccurrence(
                product_id=product_id,
                kind=row.kind,
                occurred_at=row.occurred_at,
                actor=row.actor,
                source=row.source,
                subject_id=row.subject_id,
                subject_label=row.subject_label,
                details=dict(row.details),
            )
            for row in result.scalars()
        )

    async def rollback(self) -> None:
        """Unwind the failed append, leaving the session usable for the
        work that follows the command it was recording."""
        await self._session.rollback()
