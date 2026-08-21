"""Driven adapter: persists and retrieves `Product` rows via SQLAlchemy.

Implements `launch-instance`'s persistence requirements (see
`openspec/changes/add-products-store/specs/launch-instance/spec.md`).
Callers own the `AsyncSession`; each method here commits its own work, since
this change adds no use case that would otherwise own the transaction (see
design.md's Decisions section on `ProductRepository`).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.products.infrastructure.driven.models import GATE_IDS, Product


class ProductRepositoryError(Exception):
    """A create or update was rejected: a duplicate SKU, an unrecognized
    gate, or an update targeting a product that does not exist."""


class ProductRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        sku: str,
        name: str,
        playbook_version: str,
        asin: str | None = None,
        launch_date: date | None = None,
        current_gate: str = "commit",
    ) -> Product:
        if current_gate not in GATE_IDS:
            raise ProductRepositoryError(f"unrecognized gate '{current_gate}'")

        product = Product(
            sku=sku,
            name=name,
            playbook_version=playbook_version,
            asin=asin,
            launch_date=launch_date,
            current_gate=current_gate,
        )
        self._session.add(product)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ProductRepositoryError(
                f"a product with SKU '{sku}' already exists"
            ) from exc
        return product

    async def get_by_id(self, product_id: UUID) -> Product | None:
        return await self._session.get(Product, product_id)

    async def get_by_sku(self, sku: str) -> Product | None:
        result = await self._session.execute(select(Product).where(Product.sku == sku))
        return result.scalar_one_or_none()

    async def update_current_gate(self, product_id: UUID, current_gate: str) -> None:
        if current_gate not in GATE_IDS:
            raise ProductRepositoryError(f"unrecognized gate '{current_gate}'")

        product = await self._session.get(Product, product_id)
        if product is None:
            raise ProductRepositoryError(f"no product with id '{product_id}'")

        product.current_gate = current_gate
        await self._session.commit()
