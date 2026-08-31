"""`catalog.application.record_sub_category` — the use case wiring a store
around `Product.record_sub_category` (`product-catalog`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/product-catalog/spec.md`

Covers the same scenarios as
`tests/unit/catalog/domain/test_product_sub_category.py`, at the
use-case/wiring level `tasks.md` 6.4 also asks for:

- A sub-category is recorded for a product with none
- A later recording replaces the earlier one
- Recording does not require a particular stage

*An unrecorded sub-category reports absence* is not re-derived here: it is
a fact about a freshly-registered product with nothing recorded, not
about this use case's own wiring, and is fully covered at the domain
level. Recording that choice explicitly rather than silently omitting the
scenario, per this pass's own accounting rule.

## Level

`design.md` Decision 3's `SubCategoryRecorder` port and `tasks.md` 3.2
both describe `record_sub_category` as "mirroring `record_asin`'s shape
(store, product_id, value; no confirmer)" — an async use case over a
store port. `record_asin` itself has no unit-level test in this project
(only `tests/integration/catalog/test_catalog_products.py`'s persistence
test, and a stub-store consumer in
`tests/unit/launch/infrastructure/driving/test_product_dossier_page.py`);
this file follows `tasks.md` 6.4's explicit instruction to test the new
use case at unit level, over a stub store mirroring that file's
`_AsinStore` double, rather than only at the domain level above.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 3 / `tasks.md` 3.2: an async function taking
the store, the product id and the value, with no confirmer.

INVENTED, recorded in `test-manifest.md`:

- The store's method names. `_SubCategoryStore` answers to every read-
  method spelling `_AsinStore` already answers to
  (`get_by_id`/`get`/`get_by_product_id`) plus `save`, so whichever one
  the real use case reaches for is already satisfied — the same
  generosity `_AsinStore` itself uses for the same unresolved question.
- The exported name `commerce_ops.catalog.application.record_sub_category`,
  fixed by `tasks.md` 3.3 ("Export `record_sub_category` from
  `catalog.application`'s public surface") but not the argument-passing
  convention (positional vs. keyword); this file calls it positionally
  (`store, product.id, NODE`), matching how
  `tests/integration/catalog/test_catalog_products.py` calls
  `record_asin(store, registered.id, Asin(...))`.

## Expected first-run state

Neither the use case nor the domain method it wraps exists yet
(`tasks.md` 3.1-3.3), so every test here is expected to fail on an absent
target (`ImportError`). Per `ai-toolkit:testing` that establishes absence
only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from commerce_ops.catalog.application import record_sub_category
from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Retired

pytestmark = pytest.mark.anyio

T_REGISTERED = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_RETIRED = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
CONFIRMER = "Helen"

NODE = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
LATER_NODE = "Home & Kitchen > Kitchen & Dining > Kitchen Utensils & Gadgets"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class _SubCategoryStore:
    """The smallest catalog store `record_sub_category` needs, mirroring
    `test_product_dossier_page.py`'s `_AsinStore` — every read-method
    spelling that stub answers to, plus `save`."""

    def __init__(self, product: Product) -> None:
        self.product = product

    async def get_by_id(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get(self, product_id: Any, *args: Any, **kwargs: Any) -> Product:
        return self.product

    async def get_by_product_id(
        self, product_id: Any, *args: Any, **kwargs: Any
    ) -> Product:
        return self.product

    async def save(self, product: Product) -> None:
        self.product = product


def _registered() -> Product:
    return Product.register(
        sku=Sku("WIDGET-SUBCAT-002"),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=T_REGISTERED,
    )


async def test_a_sub_category_is_recorded_for_a_product_with_none() -> None:
    """Scenario: A sub-category is recorded for a product with none.

    WHEN a sub-category node is recorded for a product that has none
    recorded yet
    THEN reading the product back reports that node.
    """
    product = _registered()
    store = _SubCategoryStore(product)

    # `cast(Any, store)`: `_SubCategoryStore` carries only the members
    # `record_sub_category` reaches, not the full `CatalogStore` protocol —
    # the same reason `test_product_dossier_page.py`'s `_AsinStore` casts
    # for `record_asin`.
    await record_sub_category(cast(Any, store), product.id, NODE)

    assert store.product.sub_category == NODE


async def test_a_later_recording_replaces_the_earlier_one() -> None:
    """Scenario: A later recording replaces the earlier one."""
    product = _registered()
    store = _SubCategoryStore(product)
    await record_sub_category(cast(Any, store), product.id, NODE)

    await record_sub_category(cast(Any, store), product.id, LATER_NODE)

    assert store.product.sub_category == LATER_NODE


async def test_recording_does_not_require_a_particular_stage() -> None:
    """Scenario: Recording does not require a particular stage."""
    product = _registered()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_RETIRED)
    store = _SubCategoryStore(product)

    await record_sub_category(cast(Any, store), product.id, NODE)

    assert store.product.sub_category == NODE
    assert store.product.stage == Retired()
