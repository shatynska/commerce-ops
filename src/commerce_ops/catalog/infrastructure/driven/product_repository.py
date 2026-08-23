"""Driven adapter: persists and retrieves `Product` aggregates via SQLAlchemy.

Satisfies `catalog.application`'s `CatalogStore` and `ProductNameReader`
ports structurally. Callers own the `AsyncSession`; each method commits its
own work, following the convention the products module's repository
recorded.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.catalog.application.errors import (
    DuplicateSkuError,
    ProductNotFoundError,
)
from commerce_ops.catalog.domain.product import Product
from commerce_ops.catalog.infrastructure.driven.models import CatalogProduct
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    LifecycleStage,
    Posture,
    Retired,
    SteadyState,
)


def _stage_to_columns(
    stage: LifecycleStage,
) -> tuple[str, int | None, str | None]:
    match stage:
        case Development():
            return "development", None, None
        case Launching(phase=phase):
            return "launching", phase, None
        case SteadyState(posture=posture):
            return "steady-state", None, posture.value
        case Retired():
            return "retired", None, None
        case _:  # pragma: no cover - the sum type above is closed
            raise ValueError(f"not a lifecycle stage: {stage!r}")


def _stage_from_columns(
    kind: str, launching_phase: int | None, posture: str | None
) -> LifecycleStage:
    match kind:
        case "development":
            return Development()
        case "launching":
            if launching_phase is None:
                raise ValueError("a launching row must carry its phase")
            return Launching(phase=launching_phase)
        case "steady-state":
            if posture is None:
                raise ValueError("a steady-state row must carry its posture")
            return SteadyState(posture=Posture(posture))
        case "retired":
            return Retired()
        case _:
            raise ValueError(f"unrecognised stage kind in the database: {kind!r}")


def _row_id(product_id: ProductId) -> uuid.UUID | None:
    """The row key for a product identifier, or None when the opaque value
    cannot be a row key at all — which reads as absence, not an error."""
    try:
        return uuid.UUID(product_id.value)
    except ValueError:
        return None


def _to_domain(row: CatalogProduct) -> Product:
    return Product(
        id=ProductId(str(row.id)),
        sku=Sku(row.sku),
        marketplace_id=MarketplaceId(row.marketplace_id),
        name=row.name,
        asin=Asin(row.asin) if row.asin is not None else None,
        stage=_stage_from_columns(row.stage, row.launching_phase, row.posture),
        stage_entered_at=row.stage_entered_at,
        stage_confirmed_by=row.stage_confirmed_by,
    )


class CatalogProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, product: Product) -> None:
        kind, phase, posture = _stage_to_columns(product.stage)
        row = CatalogProduct(
            id=uuid.UUID(product.id.value),
            sku=product.sku.value,
            marketplace_id=product.marketplace_id.value,
            asin=product.asin.value if product.asin is not None else None,
            name=product.name,
            stage=kind,
            launching_phase=phase,
            posture=posture,
            stage_entered_at=product.stage_entered_at,
            stage_confirmed_by=product.stage_confirmed_by,
        )
        self._session.add(row)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise DuplicateSkuError(
                f"a product with SKU '{product.sku.value}' already exists"
            ) from exc

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        row_id = _row_id(product_id)
        if row_id is None:
            return None
        row = await self._session.get(CatalogProduct, row_id)
        return _to_domain(row) if row is not None else None

    async def get_by_sku(self, sku: Sku) -> Product | None:
        result = await self._session.execute(
            select(CatalogProduct).where(CatalogProduct.sku == sku.value)
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row is not None else None

    async def list(self) -> Sequence[Product]:
        result = await self._session.execute(select(CatalogProduct))
        return [_to_domain(row) for row in result.scalars().all()]

    async def list_names(self) -> Sequence[str]:
        result = await self._session.execute(select(CatalogProduct.name))
        return result.scalars().all()

    async def save(self, product: Product) -> None:
        row_id = _row_id(product.id)
        row = (
            await self._session.get(CatalogProduct, row_id)
            if row_id is not None
            else None
        )
        if row is None:
            raise ProductNotFoundError(f"no product with id '{product.id.value}'")
        kind, phase, posture = _stage_to_columns(product.stage)
        row.asin = product.asin.value if product.asin is not None else None
        row.name = product.name
        row.stage = kind
        row.launching_phase = phase
        row.posture = posture
        row.stage_entered_at = product.stage_entered_at
        row.stage_confirmed_by = product.stage_confirmed_by
        await self._session.commit()
