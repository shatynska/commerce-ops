"""Driven adapter: persists and retrieves launch-position records.

Implements `launch-instance`'s reshaped persistence requirements (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/launch-instance/spec.md`).
Callers own the `AsyncSession`; each method commits its own work, per the
convention this module's pre-split repository recorded.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.products.infrastructure.driven.models import (
    GATE_IDS,
    LaunchPosition,
)
from commerce_ops.shared.domain.identity import ProductId

FIRST_GATE = "commit"


@dataclass(frozen=True, slots=True)
class LaunchPositionRecord:
    """A launch position as callers see it: the product reference carries
    the shared vocabulary's `ProductId`, not the row's raw key."""

    product_id: ProductId
    playbook_version: str
    current_gate: str
    launch_date: date | None


def _to_record(row: LaunchPosition) -> LaunchPositionRecord:
    return LaunchPositionRecord(
        product_id=ProductId(str(row.product_id)),
        playbook_version=row.playbook_version,
        current_gate=row.current_gate,
        launch_date=row.launch_date,
    )


class LaunchPositionError(Exception):
    """A create or update was rejected: an unknown product, a second
    position for the same product, an unrecognized gate, or an update
    targeting a product that has no launch position."""


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    """The row key for a product identifier, or None when the opaque value
    cannot be a row key at all — read as an unknown product."""
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


class LaunchPositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        product_id: ProductId,
        *,
        playbook_version: str,
        current_gate: str = FIRST_GATE,
        launch_date: date | None = None,
    ) -> LaunchPositionRecord:
        if current_gate not in GATE_IDS:
            raise LaunchPositionError(f"unrecognized gate '{current_gate}'")
        row_id = _row_id(product_id)
        if row_id is None:
            raise LaunchPositionError(
                f"no catalog product with id '{product_id.value}'"
            )

        position = LaunchPosition(
            product_id=row_id,
            playbook_version=playbook_version,
            current_gate=current_gate,
            launch_date=launch_date,
        )
        self._session.add(position)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # Either the product does not exist (foreign key) or it already
            # has a launch position (primary key) — both are rejections.
            await self._session.rollback()
            raise LaunchPositionError(
                f"could not create a launch position for product "
                f"'{product_id.value}': the product is unknown or already "
                f"has one"
            ) from exc
        return _to_record(position)

    async def get_by_product_id(
        self, product_id: ProductId
    ) -> LaunchPositionRecord | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        row = await self._session.get(LaunchPosition, row_id)
        return _to_record(row) if row is not None else None

    async def update_current_gate(
        self, product_id: ProductId, current_gate: str
    ) -> None:
        if current_gate not in GATE_IDS:
            raise LaunchPositionError(f"unrecognized gate '{current_gate}'")

        row_id = _row_id(product_id)
        row = (
            await self._session.get(LaunchPosition, row_id)
            if row_id is not None
            else None
        )
        if row is None:
            raise LaunchPositionError(
                f"product '{product_id.value}' has no launch position"
            )

        row.current_gate = current_gate
        await self._session.commit()
