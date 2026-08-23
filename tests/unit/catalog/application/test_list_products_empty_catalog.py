"""Test for the `product-catalog` list use case's empty-catalog behavior.

Derived strictly from one scenario of the ADDED requirement *Products can
be listed with their stages* in
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`:

    Scenario: An empty catalog lists nothing
    WHEN the product list is requested and no products exist
    THEN an empty result is returned

## Why this one scenario is covered here and not in the integration tier

The rest of the capability's persistence scenarios (registration,
read-back, non-empty listing) are covered in
`tests/integration/catalog/test_catalog_products.py` against a real
Postgres. "No products exist" is the one precondition that tier cannot
establish: this project's integration convention provides no
truncate/rollback fixture (recorded in
`tests/integration/products/test_product_repository.py`'s own docstring —
rows persist across runs, which is why `unique_sku()` exists there), so an
empty store is only observable against a store double. The smallest unit
that can observe "empty in → empty out, not an error" is the list use
case over an empty port — this test.

## The interface under test does not exist yet, and its shape is INVENTED

`catalog/application` does not exist yet (tasks.md 3.1 creates it), so
this test is expected to fail on an absent target (`ModuleNotFoundError`).
Assumed here, recorded in the manifest as unresolved project questions:

- `commerce_ops.catalog.application.list_products`, an async use case
  taking its consumer-owned store port as one positional argument —
  mirroring this project's own `run_daily_digest(reader)` port-passing
  precedent (`tests/unit/products/application/test_daily_digest.py`).
- The port method the use case pulls the products from is `list()`,
  returning a sequence. The fake below implements only that.

If the real use case differs — a different function name, a differently
named or shaped port method, a class-based use case — correcting the
import or the fake is a fixture correction; what must survive unweakened
is the assertion: an empty store yields an empty result, not an error and
not a sentinel.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from commerce_ops.catalog.application import list_products
from commerce_ops.catalog.domain.product import Product

pytestmark = pytest.mark.anyio


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, per the reasoning recorded in
    # tests/unit/products/application/test_daily_digest.py's own
    # anyio_backend fixture (no trio dependency, nothing calls for one).
    return "asyncio"


class _EmptyStore:
    """A catalog-store double holding no products."""

    async def list(self) -> Sequence[Product]:
        return []


async def test_an_empty_catalog_lists_nothing() -> None:
    """Scenario: An empty catalog lists nothing.

    WHEN the product list is requested and no products exist
    THEN an empty result is returned.
    """
    result = await list_products(_EmptyStore())

    # SPECIFIED: an empty result — not None, not an error. Asserted via
    # emptiness rather than `== []` so a tuple or other empty sequence
    # also satisfies it (the spec constrains content, not container type).
    assert len(result) == 0
