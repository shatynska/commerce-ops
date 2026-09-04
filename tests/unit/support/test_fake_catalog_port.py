"""`FakeCatalogPort`'s contract, stated directly.

The lockstep proof compares this fake against each of the sixteen `_Catalog`
declarations on the calls those files execute. The outage path is the one this
module has to carry on its own: only three of the sixteen ever set `fails`, so
for the other thirteen the raising branch is behaviour the pairing never reaches.
"""

from __future__ import annotations

import datetime

import pytest

from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.fakes import FakeCatalogPort

pytestmark = pytest.mark.anyio

MARKETPLACE = MarketplaceId("ATVPDKIKX0DER")
REGISTERED_AT = datetime.datetime(2027, 3, 2, 9, 0, tzinfo=datetime.UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _product(sku: str, name: str) -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=REGISTERED_AT,
    )


async def test_an_empty_catalog_lists_nothing() -> None:
    assert await FakeCatalogPort().list_products() == ()


async def test_lists_the_products_it_was_given_in_order() -> None:
    first, second = _product("PX-100", "Alpha"), _product("PX-200", "Beta")

    assert await FakeCatalogPort(first, second).list_products() == (first, second)


async def test_resolves_a_product_by_its_identifier() -> None:
    wanted, other = _product("PX-100", "Alpha"), _product("PX-200", "Beta")

    catalog = FakeCatalogPort(wanted, other)

    assert await catalog.get_product_by_id(wanted.id) is wanted


async def test_answers_none_for_a_product_the_catalog_cannot_resolve() -> None:
    """Absent from `products` is the catalog not knowing it -- distinct from
    the outage below, which is the catalog not being readable at all."""
    catalog = FakeCatalogPort(_product("PX-100", "Alpha"))

    assert await catalog.get_product_by_id(ProductId("no-such-product")) is None


async def test_an_outage_makes_both_reads_raise() -> None:
    """`fails` is the outage *Product identities cannot be read at all* is
    about, and it makes the whole port unreadable rather than one product
    unresolvable."""
    catalog = FakeCatalogPort(_product("PX-100", "Alpha"), fails=True)

    with pytest.raises(ConnectionError, match="unreachable"):
        await catalog.list_products()
    with pytest.raises(ConnectionError, match="unreachable"):
        await catalog.get_product_by_id(ProductId("anything"))


async def test_the_reads_tolerate_the_scope_their_call_sites_pass() -> None:
    """Production hands both reads a scope this double does not model."""
    product = _product("PX-100", "Alpha")
    catalog = FakeCatalogPort(product)

    assert await catalog.list_products("a-scope") == (product,)
    assert await catalog.get_product_by_id(product.id, "a-scope") is product
