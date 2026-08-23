from __future__ import annotations

from commerce_ops.catalog.application.errors import (
    DuplicateSkuError,
    ProductNotFoundError,
)
from commerce_ops.catalog.application.ports import (
    CatalogStore,
    ProductLister,
)
from commerce_ops.catalog.application.use_cases import (
    change_stage,
    get_product_by_id,
    get_product_by_sku,
    list_products,
    record_asin,
    register_product,
)

# `change_stage` is public, so the rejection it raises is part of the
# public surface too — callers outside this module (launch's graduation
# wiring) must be able to catch it without reaching into catalog.domain.
from commerce_ops.catalog.domain.product import StageTransitionError

__all__ = [
    "CatalogStore",
    "DuplicateSkuError",
    "ProductLister",
    "ProductNotFoundError",
    "StageTransitionError",
    "change_stage",
    "get_product_by_id",
    "get_product_by_sku",
    "list_products",
    "record_asin",
    "register_product",
]
