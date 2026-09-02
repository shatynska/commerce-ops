"""Driven adapter: which ClickUp list and tasks stand for which launch.

Implements `launch-clickup-sync`'s recording obligations — "SHALL record
the association between the launch and its list", "SHALL record the
association between each step and its task", and "SHALL retain, per mapped
task, the closed state it last observed".

No domain object learns of a ClickUp identifier: the mapping is
infrastructure, as the domain map's open question leans ("infrastructure
until the mapping grows rules of its own"). `ClickUpTaskMapping` below is a
read shape this module hands back, not a domain value.

Callers own the `AsyncSession`; each method commits its own work, the
convention `launch_repository` records.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.launch.infrastructure.driven.models import (
    LaunchClickUpList,
    LaunchClickUpTask,
)
from commerce_ops.shared.domain.identity import ProductId


@dataclass(frozen=True, slots=True)
class ClickUpTaskMapping:
    """One step's ClickUp task, the closed state last observed for it, and
    the name, body and assignees the system last set on it (None where the
    system never wrote that field, or on rows predating retention)."""

    product_id: ProductId
    step_id: str
    task_id: str
    last_observed_closed: bool
    retained_name: str | None = None
    retained_body: str | None = None
    retained_assignees: tuple[str, ...] | None = None


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    """The row key for a product identifier, or None when the opaque value
    cannot be a row key at all — read as an unmapped product."""
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


class ClickUpMappingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_id_for(self, product_id: ProductId) -> str | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        row = await self._session.get(LaunchClickUpList, row_id)
        return row.list_id if row is not None else None

    async def record_list(self, product_id: ProductId, list_id: str) -> None:
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(f"no launch for product '{product_id.value}'")
        existing = await self._session.get(LaunchClickUpList, row_id)
        if existing is None:
            self._session.add(LaunchClickUpList(product_id=row_id, list_id=list_id))
        else:
            existing.list_id = list_id
        await self._session.commit()

    async def replace_list_discarding_tasks(
        self,
        product_id: ProductId,
        list_id: str,
        *,
        spare: Sequence[str] = (),
    ) -> None:
        """Record a replacement list and discard the launch's task mappings,
        in one commit.

        One operation rather than `record_list` followed by a discard,
        because every other method here commits for itself: two calls would
        leave a window in which a crash records the new list while the dead
        list's mappings survive, or discards the mappings while the dead
        list stays recorded — and the second of those mints a further list
        on the next pass, orphaning this one. Committing once removes the
        window instead of choosing which side of it to fail on. It also
        names what happened: the launch's projection was reset.

        `spare` names the steps whose mappings stand — the ones whose work
        is already finished. Their tasks died with the list like every
        other, but the mapping is what tells the projection not to recreate
        them; discarding it would put completed work back into the
        replacement list as a fresh open task. The caller decides which
        those are, because deciding needs the step definitions and this
        store holds none. See `heal-a-launchs-deleted-list`'s design.md,
        Decisions 2a, 2b and 3.
        """
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(f"no launch for product '{product_id.value}'")
        spared = {str(step_id) for step_id in spare}
        discard = delete(LaunchClickUpTask).where(
            LaunchClickUpTask.product_id == row_id
        )
        if spared:
            discard = discard.where(LaunchClickUpTask.step_id.not_in(spared))
        await self._session.execute(discard)
        existing = await self._session.get(LaunchClickUpList, row_id)
        if existing is None:
            self._session.add(LaunchClickUpList(product_id=row_id, list_id=list_id))
        else:
            existing.list_id = list_id
        # The single commit this operation exists for. Both writes land or
        # neither does.
        await self._session.commit()

    async def task_for(
        self, product_id: ProductId, step_id: str
    ) -> ClickUpTaskMapping | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        row = await self._session.get(LaunchClickUpTask, (row_id, step_id))
        return _mapping_from(row) if row is not None else None

    async def tasks_for(self, product_id: ProductId) -> list[ClickUpTaskMapping]:
        row_id = _row_id(product_id)
        if row_id is None:
            return []
        rows = await self._session.scalars(
            select(LaunchClickUpTask).where(LaunchClickUpTask.product_id == row_id)
        )
        return [_mapping_from(row) for row in rows]

    async def resolve_task(self, task_id: str) -> ClickUpTaskMapping | None:
        """The step a ClickUp task stands for. Webhook intake arrives
        holding only the task identifier, which is what the unique
        constraint on `task_id` exists for."""
        row = await self._session.scalar(
            select(LaunchClickUpTask).where(LaunchClickUpTask.task_id == task_id)
        )
        return _mapping_from(row) if row is not None else None

    async def record_task(
        self, product_id: ProductId, step_id: str, task_id: str
    ) -> None:
        """Map a step to a task, replacing whatever task it mapped to
        before.

        A replacement resets the retained observed state: the new task has
        never been observed closed, and the old task identifier must stop
        resolving — otherwise a late delivery for a task that was deleted
        in ClickUp would still record against the step.
        """
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(f"no launch for product '{product_id.value}'")
        await self._session.execute(
            delete(LaunchClickUpTask).where(
                LaunchClickUpTask.product_id == row_id,
                LaunchClickUpTask.step_id == step_id,
            )
        )
        self._session.add(
            LaunchClickUpTask(
                product_id=row_id,
                step_id=step_id,
                task_id=task_id,
                last_observed_closed=False,
            )
        )
        await self._session.commit()

    async def observe(self, product_id: ProductId, step_id: str, closed: bool) -> None:
        """Retain the closed state just read for a task. Every observation
        writes this — webhook delivery and reconciliation read alike — so
        the next reading can tell a transition from a repeat."""
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(f"no launch for product '{product_id.value}'")
        row = await self._session.get(LaunchClickUpTask, (row_id, step_id))
        if row is None:
            raise ValueError(
                f"step '{step_id}' of product '{product_id.value}' has no "
                f"mapped ClickUp task to observe"
            )
        row.last_observed_closed = closed
        await self._session.commit()

    async def record_composition(
        self,
        product_id: ProductId,
        step_id: str,
        *,
        name: str | None = None,
        body: str | None = None,
        assignees: Sequence[str] | None = None,
    ) -> None:
        """Retain what the system just wrote for a task's field — every
        system write of a name, a body or an assignee set updates that
        field's retained value; `None` leaves it untouched.

        An *empty* assignee sequence is a value, not an absence: it
        records that the system last set nobody, which is what lets a
        later pass tell its own silence from a member's edit."""
        row_id = _row_id(product_id)
        if row_id is None:
            raise ValueError(f"no launch for product '{product_id.value}'")
        row = await self._session.get(LaunchClickUpTask, (row_id, step_id))
        if row is None:
            raise ValueError(
                f"step '{step_id}' of product '{product_id.value}' has no "
                f"mapped ClickUp task to retain a composition for"
            )
        if name is not None:
            row.retained_name = name
        if body is not None:
            row.retained_body = body
        if assignees is not None:
            row.retained_assignees = [str(user) for user in assignees]
        await self._session.commit()


def _mapping_from(row: LaunchClickUpTask) -> ClickUpTaskMapping:
    return ClickUpTaskMapping(
        product_id=ProductId(str(row.product_id)),
        step_id=row.step_id,
        task_id=row.task_id,
        last_observed_closed=row.last_observed_closed,
        retained_name=row.retained_name,
        retained_body=row.retained_body,
        retained_assignees=(
            None if row.retained_assignees is None else tuple(row.retained_assignees)
        ),
    )
