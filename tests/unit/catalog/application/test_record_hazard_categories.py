"""`catalog.application.record_hazard_categories` — the use case wiring a
store around `Product.record_hazard_categories` (`product-catalog`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/product-catalog/spec.md`

Covers, at the use-case/wiring level `tasks.md` 1.1-1.3 asks for, the
scenarios of *A hazard-category finding can be recorded against a
product* and *A product reports its hazard categories in three states,
never two* that are about a recording travelling through a store:

- Hazard categories are recorded for a product with none
- An empty set is recorded as an empty set
- A later recording replaces the earlier one wholesale
- An empty set replaces a recorded set
- Recording does not require a particular stage
- A cleared product reports an answered question
- A flagged product reports its categories

*A never-screened product reports the question as open*, *A product
predating the field reports the question as open* and *What was screened
against is not recorded with the result* are not re-derived here: they
are facts about a product with nothing recorded, or about what a
recording does not carry, rather than about this use case's own wiring,
and are covered at the domain level in
`tests/unit/catalog/domain/test_product_hazard_categories.py`. Recorded
rather than silently omitted, per this pass's accounting rule.

This file is the deliberate mirror of
`tests/unit/catalog/application/test_record_sub_category.py`, which
`tasks.md` 3.2 names as the shape `record_hazard_categories` copies. See
`test-manifest.md` at the change root for the full accounting.

## Level

An async use case over a store port, per `tasks.md` 3.2 ("shaped like
`record_sub_category`"). The store is the same generous double
`test_record_sub_category.py` uses, answering every read-method spelling
`_AsinStore` answers to plus `save`, so whichever the real use case
reaches for is already satisfied.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 3.2 and 3.3: an async function
`record_hazard_categories(store, product_id, categories)` exported from
`commerce_ops.catalog.application`'s `__all__`.

INVENTED, recorded in `test-manifest.md`:

- The argument-passing convention (positional rather than keyword),
  matching how `test_record_sub_category.py` and
  `tests/integration/catalog/test_catalog_products.py` call the two
  sibling use cases.
- The store double's method names, inherited from
  `test_record_sub_category.py`'s own documented assumption.
- That `None` is the never-recorded reading — see the domain file's
  docstring for why, and note that the empty-set scenarios here compare
  against a *second product's* reading rather than against that literal.

## Expected first-run state

Neither `record_hazard_categories` nor the domain method it wraps exists
yet (`tasks.md` 3.1-3.3), so every test here is expected to fail on an
absent target — `ImportError` at collection. Per `ai-toolkit:testing`
that establishes absence only.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, cast

import pytest

from commerce_ops.catalog.application import record_hazard_categories
from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Retired

pytestmark = pytest.mark.anyio

T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)
T_RETIRED: Final = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
CONFIRMER: Final = "Helen"

FLAGGED: Final = ("supplements",)
LATER_FLAGGED: Final = ("medical devices", "lighters")
EMPTY: Final[tuple[str, ...]] = ()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


class _HazardStore:
    """The smallest catalog store `record_hazard_categories` needs,
    mirroring `test_record_sub_category.py`'s `_SubCategoryStore` — every
    read-method spelling that stub answers to, plus `save`."""

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


def _registered(sku: str = "WIDGET-HAZ-101") -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MarketplaceId("ATVPDKIKX0DER"),
        name="Widget",
        registered_at=T_REGISTERED,
    )


def _reading(product: Product) -> Any:
    return product.hazard_categories


def _members(product: Product) -> list[str]:
    reading = _reading(product)
    assert reading is not None, (
        "the product reports its hazard categories as never recorded where "
        "the use case recorded a set"
    )
    assert not isinstance(reading, str), (
        f"the stored reading is the string {reading!r}; a set of categories "
        "is not one of them"
    )
    return list(reading)


async def test_hazard_categories_are_recorded_for_a_product_with_none() -> None:
    """Scenario: Hazard categories are recorded for a product with none."""
    product = _registered()
    store = _HazardStore(product)

    # `cast(Any, store)`: `_HazardStore` carries only the membership the
    # use case reaches, not the full `CatalogStore` protocol — the same
    # reason `test_record_sub_category.py` casts.
    await record_hazard_categories(cast(Any, store), product.id, FLAGGED)

    assert _members(store.product) == list(FLAGGED)


async def test_an_empty_set_is_recorded_as_an_empty_set() -> None:
    """Scenario: An empty set is recorded as an empty set.

    The row that fails an implementation storing "nothing recorded" for an
    empty input. The comparison is against a *second, untouched* product
    rather than against a literal sentinel, so a different sentinel is a
    fixture correction and the distinction is not.
    """
    product = _registered()
    store = _HazardStore(product)
    untouched = _registered("WIDGET-HAZ-102")

    await record_hazard_categories(cast(Any, store), product.id, EMPTY)

    assert _members(store.product) == []
    assert _reading(store.product) != _reading(untouched), (
        "an empty set recorded through the use case reads back the same as "
        "a product nothing has ever screened"
    )


async def test_a_later_recording_replaces_the_earlier_one_wholesale() -> None:
    """Scenario: A later recording replaces the earlier one wholesale."""
    product = _registered()
    store = _HazardStore(product)
    await record_hazard_categories(cast(Any, store), product.id, FLAGGED)

    await record_hazard_categories(cast(Any, store), product.id, LATER_FLAGGED)

    assert _members(store.product) == list(LATER_FLAGGED)
    for earlier in FLAGGED:
        assert earlier not in _members(store.product), (
            f"{earlier!r} survived a wholesale replacement through the use "
            "case, so the later recording merged rather than replaced"
        )


async def test_an_empty_set_replaces_a_recorded_set() -> None:
    """Scenario: An empty set replaces a recorded set."""
    product = _registered()
    store = _HazardStore(product)
    untouched = _registered("WIDGET-HAZ-103")
    await record_hazard_categories(cast(Any, store), product.id, FLAGGED)

    await record_hazard_categories(cast(Any, store), product.id, EMPTY)

    assert _members(store.product) == []
    assert _reading(store.product) != _reading(untouched), (
        "recording an empty set over a flag left the product reading as "
        "never screened rather than as screened and clear"
    )


async def test_recording_does_not_require_a_particular_stage() -> None:
    """Scenario: Recording does not require a particular stage."""
    product = _registered()
    product.change_stage(Retired(), confirmed_by=CONFIRMER, at=T_RETIRED)
    store = _HazardStore(product)

    await record_hazard_categories(cast(Any, store), product.id, FLAGGED)

    assert _members(store.product) == list(FLAGGED)
    assert store.product.stage == Retired()


async def test_a_cleared_product_reports_an_answered_question() -> None:
    """Scenario: A cleared product reports an answered question, read back
    through the store the use case saved to."""
    product = _registered()
    store = _HazardStore(product)

    await record_hazard_categories(cast(Any, store), product.id, EMPTY)

    assert _reading(store.product) is not None
    assert _members(store.product) == []


async def test_a_flagged_product_reports_its_categories() -> None:
    """Scenario: A flagged product reports its categories, read back
    through the store the use case saved to."""
    product = _registered()
    store = _HazardStore(product)

    await record_hazard_categories(cast(Any, store), product.id, LATER_FLAGGED)

    assert _members(store.product) == list(LATER_FLAGGED)


async def test_the_recording_is_saved_and_not_only_held_in_memory() -> None:
    """DERIVED from `tasks.md` 3.2's "shaped like `record_sub_category`",
    not from a `#### Scenario:`.

    The three-state distinction is worthless if the use case mutates the
    aggregate and never asks the store to keep it. Asserted by counting
    the store's `save` calls rather than by reading the product back,
    since the double hands out the same object either way.
    """
    product = _registered()
    saves: list[Product] = []

    class _CountingStore(_HazardStore):
        async def save(self, product: Product) -> None:
            saves.append(product)
            self.product = product

    store = _CountingStore(product)

    await record_hazard_categories(cast(Any, store), product.id, EMPTY)

    assert saves, (
        "the use case recorded the categories on the aggregate without "
        "asking the store to keep them"
    )
