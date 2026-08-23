"""Catalog use cases: the module's public behavior over the store port.

Implements `product-catalog`'s registration, read-back, and listing
requirements, and drives the aggregate's stage machine (see
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`).
Per design.md Decision 10, these use cases are the only way registration
and stage changes are exercised — there is no HTTP/Slack driving surface
for catalog yet.

The clock is stamped here (`datetime.now(UTC)`) rather than inside the
aggregate, so the aggregate's own tests can pass exact instants in.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from commerce_ops.catalog.application.errors import ProductNotFoundError
from commerce_ops.catalog.application.ports import CatalogStore
from commerce_ops.catalog.domain.product import Product, StageChanged
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import LifecycleStage


async def register_product(
    store: CatalogStore,
    *,
    sku: Sku,
    marketplace_id: MarketplaceId,
    name: str,
    asin: Asin | None = None,
) -> Product:
    product = Product.register(
        sku=sku,
        marketplace_id=marketplace_id,
        name=name,
        asin=asin,
        registered_at=datetime.now(UTC),
    )
    await store.add(product)
    return product


async def record_asin(store: CatalogStore, product_id: ProductId, asin: Asin) -> None:
    product = await _existing(store, product_id)
    product.record_asin(asin)
    await store.save(product)


async def change_stage(
    store: CatalogStore,
    product_id: ProductId,
    new_stage: LifecycleStage,
    *,
    confirmed_by: str,
) -> StageChanged:
    product = await _existing(store, product_id)
    changed = product.change_stage(
        new_stage, confirmed_by=confirmed_by, at=datetime.now(UTC)
    )
    await store.save(product)
    return changed


async def get_product_by_id(
    store: CatalogStore, product_id: ProductId
) -> Product | None:
    return await store.get_by_id(product_id)


async def get_product_by_sku(store: CatalogStore, sku: Sku) -> Product | None:
    return await store.get_by_sku(sku)


async def list_products(store: CatalogStore) -> Sequence[Product]:
    return await store.list()


async def _existing(store: CatalogStore, product_id: ProductId) -> Product:
    product = await store.get_by_id(product_id)
    if product is None:
        raise ProductNotFoundError(f"no product with id '{product_id.value}'")
    return product
