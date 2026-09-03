"""Driven adapter: where a produced result waits for a member's decision.

`launch-step-automation`'s pending-result store, shaped like
`ClickUpMappingRepository` — a thin repository over one table, holding no
policy of its own. What may be stored, what a decision means and when a
step becomes eligible again are the pass's and the use cases' business;
this only reads and writes rows.

Callers own the `AsyncSession`; each method commits its own work, the
convention every repository in this module follows.

Two things it does decide, because both are properties of storage:

- **A second pending row is refused by the database**, through the partial
  unique index, not by a check here. `store` therefore lets the integrity
  error surface rather than pre-checking: a pre-check would be a
  read-then-write and would lose exactly the race the index exists for.
- **Settling never deletes.** A decided row keeps standing with its state,
  its decider and the moment — the record of a compliance-adjacent
  decision, and the input the cool-off reads.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.infrastructure.driven.models import AutomatedStepResult
from commerce_ops.shared.domain.identity import ProductId

__all__ = ["AutomatedResultRepository"]

PENDING = "pending"
ACCEPTED = "accepted"
REJECTED = "rejected"
VOIDED = "voided"


def _outcome_name(outcome: Any) -> str:
    """The stored spelling of a proposed outcome.

    A name rather than a pickled value: the row is read back by a member's
    decision, possibly after a deploy, and a stored class reference would
    tie a waiting proposal to the code that produced it.
    """
    if isinstance(outcome, str):
        return outcome
    kind = outcome if isinstance(outcome, type) else type(outcome)
    return str(getattr(kind, "__name__", outcome))


def _finding_to_row(finding: Any) -> dict[str, Any] | None:
    """The stored payload for a finding held with a pending result.

    The same four keys the recording stores, so that carrying it onto the
    recording at acceptance is a read and a pass-through rather than a
    second shape to keep in step.
    """
    if finding is None:
        return None
    # A `CarriedFinding` from the pass, or a mapping from a caller that
    # built one itself. Both are accepted because the column is the
    # store's contract and not the pass's: reading the payload back at
    # acceptance goes through one shape either way.
    if isinstance(finding, Mapping):
        field = finding.get("field")
        reads_as = finding.get("reads_as")
        value = finding.get("value")
        comment = finding.get("comment")
    else:
        field = getattr(finding, "field", None)
        reads_as = getattr(finding, "reads_as", None)
        value = getattr(finding, "value", None)
        comment = getattr(finding, "comment", None)
    if field is None or value is None:
        # No field, or no value, is no finding: `launch-instance` admits
        # one spelling of empty and neither of these is it.
        return None
    return {
        "field": field,
        "reads_as": reads_as,
        "value": value,
        "comment": comment,
    }


class AutomatedResultRepository:
    """Reads and writes pending results on the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def store(
        self,
        *,
        product_id: ProductId,
        step_id: str,
        handler: str,
        proposed_outcome: Any,
        result_text: str,
        produced_at: datetime,
        finding: Any = None,
    ) -> AutomatedStepResult:
        row = AutomatedStepResult(
            id=uuid.uuid4(),
            product_id=uuid.UUID(product_id.value),
            step_id=step_id,
            handler=handler,
            proposed_outcome=_outcome_name(proposed_outcome),
            result_text=result_text,
            finding=_finding_to_row(finding),
            produced_at=produced_at,
            state=PENDING,
        )
        self._session.add(row)
        # Committed here, not left to the caller: it is what makes the row
        # visible to the *other* session the index arbitrates against, and
        # a losing race then fails inside this call — where the pass can
        # catch it and leave the step for a later cycle — rather than at
        # an unrelated commit further out.
        await self._session.commit()
        return row

    async def pending_for(
        self, product_id: ProductId, step_id: str
    ) -> AutomatedStepResult | None:
        result = await self._session.execute(
            select(AutomatedStepResult).where(
                AutomatedStepResult.product_id == uuid.UUID(product_id.value),
                AutomatedStepResult.step_id == step_id,
                AutomatedStepResult.state == PENDING,
            )
        )
        return result.scalars().first()

    async def by_id(self, result_id: str | uuid.UUID) -> AutomatedStepResult | None:
        identifier = (
            result_id if isinstance(result_id, uuid.UUID) else uuid.UUID(str(result_id))
        )
        return await self._session.get(AutomatedStepResult, identifier)

    async def for_product(self, product_id: ProductId) -> list[AutomatedStepResult]:
        """Every row retained for a product, newest first.

        The first read here that serves a *record* rather than the
        decision loop: no state filter, no step filter, and no knowledge
        of access scope — a row in every state, for a step the playbook
        may no longer define, for a launch that may have graduated. What
        may be seen is the use case's business, as it is for every other
        read in this module.

        `id` breaks the tie because `produced_at` alone does not order
        totally: two results produced within one pass can share it, and a
        database is free to return equal keys in any order, so an
        unchanged page could re-render with its entries swapped. The
        identifier carries no meaning and is never presented — it is here
        so the order is a function of the data.
        """
        result = await self._session.execute(
            select(AutomatedStepResult)
            .where(AutomatedStepResult.product_id == uuid.UUID(product_id.value))
            .order_by(
                AutomatedStepResult.produced_at.desc(),
                AutomatedStepResult.id.desc(),
            )
        )
        return list(result.scalars().all())

    async def undelivered(self) -> list[AutomatedStepResult]:
        result = await self._session.execute(
            select(AutomatedStepResult)
            .where(
                AutomatedStepResult.state == PENDING,
                AutomatedStepResult.delivered_at.is_(None),
            )
            .order_by(AutomatedStepResult.produced_at)
        )
        return list(result.scalars().all())

    async def mark_delivered(
        self, row: AutomatedStepResult, when: datetime | None = None
    ) -> None:
        row.delivered_at = when or datetime.now(tz=row.produced_at.tzinfo)
        await self._session.commit()

    async def settle(
        self,
        row: AutomatedStepResult,
        *,
        state: str,
        decided_by: str,
        decided_at: datetime,
    ) -> None:
        """Record a decision on a row, keeping it."""
        row.state = state
        row.decided_by = decided_by
        row.decided_at = decided_at
        await self._session.commit()

    async def void(
        self, row: AutomatedStepResult, *, decided_at: datetime | None = None
    ) -> None:
        """Retire a proposal nobody can act on any more.

        Its own state, never `rejected`: nobody rejected it, and the
        cool-off must not treat it as though somebody had.
        """
        row.state = VOIDED
        row.decided_at = decided_at
        await self._session.commit()

    async def latest_rejection(
        self, product_id: ProductId, step_id: str
    ) -> AutomatedStepResult | None:
        """The most recent *rejection*, which is the cool-off's only input.

        Deliberately not "the most recent settled row": an accepted row
        resolves the step, and a voided one records that nobody decided.
        Neither is a member's disagreement, and only a disagreement holds
        a step back.
        """
        result = await self._session.execute(
            select(AutomatedStepResult)
            .where(
                AutomatedStepResult.product_id == uuid.UUID(product_id.value),
                AutomatedStepResult.step_id == step_id,
                AutomatedStepResult.state == REJECTED,
            )
            .order_by(AutomatedStepResult.decided_at.desc())
            .limit(1)
        )
        return result.scalars().first()
