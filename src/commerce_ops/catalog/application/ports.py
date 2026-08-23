"""Consumer-owned ports `catalog.application` depends on.

`.importlinter`'s `module-layers` contract forbids `catalog.application`
from importing `catalog.infrastructure` directly.
`CatalogProductRepository` (infrastructure) satisfies these Protocols
structurally, so it can be passed in without either layer importing the
other by name — the same pattern `products.application` recorded for its
pre-split reader port.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import ProductId, Sku


class ProductLister(Protocol):
    """The narrow read port listing needs.

    Separate from `CatalogStore` because listing is the one use case that
    reads nothing else: a caller that can only list — a read model, a test
    double — should not have to satisfy the whole store. Same reasoning
    that keeps `ProductNameReader` narrow.
    """

    async def list(self) -> Sequence[Product]: ...


class CatalogStore(ProductLister, Protocol):
    """The persistence port the catalog use cases speak."""

    async def add(self, product: Product) -> None: ...

    async def get_by_id(self, product_id: ProductId) -> Product | None: ...

    async def get_by_sku(self, sku: Sku) -> Product | None: ...

    async def save(self, product: Product) -> None: ...


class ProductNameReader(Protocol):
    """The daily digest's read port (moved here from `products.application`
    with the digest itself — design.md Decision 9 as amended)."""

    async def list_names(self) -> Sequence[str]: ...
