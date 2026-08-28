"""Driven adapter: which automated steps have stopped making progress.

Implements the retention half of `launch-step-automation`'s *A handler
that repeats itself is not asked again immediately* and *A step whose
handler has stopped making progress is reported once*
(`openspec/changes/cool-off-a-repeatedly-blocked-step/`).

One row per (launch, step), carrying both decisions: `noted_at` anchors
the cool-off, `reported_at` suppresses a second report. They key on the
same thing and are lifted by the same event, so keeping them apart would
mean two writes that could disagree.

**Nothing lifts a row.** `noted_kind` records which outcome the row was
noted against, and the pass ignores a row whose kind is not the step's
currently recorded one. That is what lets `automation_confirmation` —
which records outcomes for these same steps — stay untouched: a
delete-on-change rule would be owed by every present and future
recording surface, and silently forgotten by the next one.

**`mark_reported` is called only after a report has been delivered.**
Stamping first and then failing to deliver would silence the step for as
long as it stays stuck, since the row is lifted by the step moving and
not by Slack recovering — the discipline `field_gap_suppression` records
for the same reason.

Callers own the `AsyncSession`; each method commits its own write, this
package's convention. `rollback` is part of the surface because the pass
touches this record *inside* its walk, where a failed statement would
otherwise leave every later recording in the pass failing.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Final

from sqlalchemy import case, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    InProgress,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
)
from commerce_ops.launch.infrastructure.driven.models import AutomatedStepBackoff
from commerce_ops.shared.domain.identity import ProductId

# The stored spelling of each outcome kind, matching `OUTCOME_KINDS` and
# the table's check constraint. Keyed by type because a *kind* is what a
# repeat is judged on — never the outcome value, whose `reason` an
# LLM-backed handler rewords on every call.
_KIND_NAMES: Final[dict[type, str]] = {
    NotStarted: "not-started",
    InProgress: "in-progress",
    Satisfied: "satisfied",
    Blocked: "blocked",
    Refused: "refused",
    NotApplicable: "not-applicable",
}
_KINDS_BY_NAME: Final[dict[str, type]] = {
    name: kind for kind, name in _KIND_NAMES.items()
}


def _kind_name(outcome: Any) -> str:
    kind = outcome if isinstance(outcome, type) else type(outcome)
    name = _KIND_NAMES.get(kind)
    if name is None:
        raise ValueError(f"'{kind}' is not a launch-playbook outcome kind")
    return name


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


class StepBackoff:
    """What the pass reads back: the kind this row was noted against, when,
    and whether the step has been reported.

    `noted_kind` is rehydrated to the outcome *type*, so the pass compares
    it against a recorded outcome's kind without knowing this module's
    stored spellings.
    """

    __slots__ = ("noted_at", "noted_kind", "reported_at")

    def __init__(
        self,
        *,
        noted_kind: type,
        noted_at: datetime.datetime,
        reported_at: datetime.datetime | None,
    ) -> None:
        self.noted_kind = noted_kind
        self.noted_at = noted_at
        self.reported_at = reported_at


class AutomatedStepBackoffRepository:
    """The backoff record over Postgres."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, product_id: ProductId, step_id: str) -> StepBackoff | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        result = await self._session.execute(
            select(AutomatedStepBackoff).where(
                AutomatedStepBackoff.product_id == row_id,
                AutomatedStepBackoff.step_id == step_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        kind = _KINDS_BY_NAME.get(row.noted_kind)
        if kind is None:
            # A kind this deployment does not know is read as no row at
            # all: the pass then invokes, which is the safe direction.
            return None
        return StepBackoff(
            noted_kind=kind, noted_at=row.noted_at, reported_at=row.reported_at
        )

    async def note(
        self,
        product_id: ProductId,
        step_id: str,
        outcome: Any,
        when: datetime.datetime,
    ) -> None:
        """Record that the handler repeated itself.

        Noting a *different* kind than the row carries clears the reported
        stamp: the step moved and got stuck again, and is owed a fresh
        report. A plain `SET noted_kind=…, noted_at=…` would leave the
        stamp and silently suppress it.
        """
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(
                f"'{product_id.value}' is not a product identifier a backoff "
                f"record can reference"
            )
        kind = _kind_name(outcome)
        statement = insert(AutomatedStepBackoff).values(
            product_id=row_id,
            step_id=step_id,
            noted_kind=kind,
            noted_at=when,
            reported_at=None,
        )
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["product_id", "step_id"],
                set_={
                    "noted_kind": statement.excluded.noted_kind,
                    "noted_at": statement.excluded.noted_at,
                    # Kept where the kind is unchanged — the step is still
                    # stuck on the same thing and has already been
                    # reported. Cleared where it changed: the step moved
                    # and got stuck again, which is a fresh report.
                    "reported_at": case(
                        (
                            AutomatedStepBackoff.noted_kind
                            == statement.excluded.noted_kind,
                            AutomatedStepBackoff.reported_at,
                        ),
                        else_=None,
                    ),
                },
            )
        )
        await self._session.commit()

    async def mark_reported(
        self, product_id: ProductId, step_id: str, when: datetime.datetime
    ) -> None:
        row_id = _row_id(product_id)
        if row_id is None:
            return
        result = await self._session.execute(
            select(AutomatedStepBackoff).where(
                AutomatedStepBackoff.product_id == row_id,
                AutomatedStepBackoff.step_id == step_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is not None:
            row.reported_at = when
            await self._session.commit()

    async def rollback(self) -> None:
        """Unwind a failed access, leaving the session usable for the rest
        of the walk."""
        await self._session.rollback()
