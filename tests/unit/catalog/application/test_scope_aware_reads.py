"""Scope-aware catalog reads (`product-catalog`).

Derived strictly from the two MODIFIED requirements in
`openspec/changes/introduce-access-scope/specs/product-catalog/spec.md`:

- *A product can be read back by identifier or by SKU* (all 4 scenarios,
  as revised)
- *Products can be listed with their stages* (all 4 scenarios, as revised)

Every scenario is covered here as revised, not merely the two the change
adds: the delta restates all eight, and three of the four pre-existing ones
now carry a scope clause that no existing test exercises. See
`test-manifest.md` at the change root for the accounting, including the
existing tests this change supersedes (this pass never edits them).

## Why the application level

The filtering the delta introduces is stated about the *use cases* -- what
a read returns, what a list contains -- and `design.md` puts it there
(Decision 7; `tasks.md` 3.1). A fake store answering with real `Product`
aggregates is the smallest unit that can observe "the store held it and the
read still reported absence", which is exactly what an out-of-scope read
must do. A real store cannot observe it any better and would only add
Postgres to the loop, so this stays in the fast mocked unit tier.

## The store double ignores any scope handed to it, deliberately

`_FakeCatalogStore` filters nothing. If an implementation pushed scope
filtering down into the store port instead of applying it in the use case,
this double would hand back everything and the filtering assertions below
would fail -- which is the honest outcome, since `design.md` places the
filter in the use case. The double's methods therefore accept and discard
extra arguments rather than rejecting them: a signature mismatch would fail
these tests for a reason unrelated to what they assert.

## What exists and what does not

`get_product_by_id`, `get_product_by_sku` and `list_products` exist today
and are exercised by
`tests/integration/catalog/test_catalog_products.py`; the `AccessScope`
parameter and the filtering are what this change adds (`tasks.md` 1.1,
3.1). So these tests are expected to fail on an absent target twice over:
`AccessScope` does not exist (`ModuleNotFoundError` at import), and the use
cases do not yet take a scope (`_scope_argument` below fails the test by
name when they do not). Per `ai-toolkit:testing`, neither failure
establishes anything about the assertions themselves.

INVENTED, and recorded as unresolved project questions in the manifest:

- `commerce_ops.shared.domain.access_scope.AccessScope` and its two
  construction spellings -- the same INVENTED shapes
  `tests/unit/shared/domain/test_access_scope.py` records, duplicated here
  rather than imported so that neither file's subject depends on the
  other's helpers.
- How the scope reaches each use case. `_scope_argument` finds the
  parameter whose name contains "scope" and passes the scope by that name,
  so a differently-ordered or differently-spelled parameter is not a
  correction at all; a use case taking *no* scope parameter fails loudly,
  which is the requirement rather than an accommodation.
- The store port's method names (`_FakeCatalogStore` answers to several).

What must survive unweakened: which products each read returns, and that an
out-of-scope read is indistinguishable from a read of a product that does
not exist.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.catalog.application import (
    get_product_by_id,
    get_product_by_sku,
    list_products,
)
from commerce_ops.catalog.domain.product import Product
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Development

pytestmark = pytest.mark.anyio

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
# DERIVED fixed time: no artifact fixes a clock; a timezone-aware instant
# makes the stage-entry assertion exact, as `test_product_lifecycle.py`
# already does.
T_REGISTERED: Final = datetime(2026, 8, 23, 9, 0, tzinfo=UTC)

# INVENTED: see `tests/unit/shared/domain/test_access_scope.py`.
_UNRESTRICTED_NAMES: Final = (
    "unrestricted",
    "UNRESTRICTED",
    "all_products",
    "ALL_PRODUCTS",
    "unrestricted_scope",
)
_EXPLICIT_FACTORY_NAMES: Final = (
    "of",
    "permitting",
    "for_products",
    "restricted_to",
    "explicit",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    # Pinned to asyncio, matching every other async test file here.
    return "asyncio"


def _unrestricted() -> AccessScope:
    return AccessScope.unrestricted()


def _permitting(*product_ids: ProductId) -> AccessScope:
    return AccessScope.permitting(product_ids)


def _scope_argument(use_case: Any, scope: AccessScope) -> dict[str, Any]:
    """The scope, keyed by whatever the use case calls its scope parameter.

    SPECIFIED, not an accommodation: both requirements state the read takes
    "the caller's access scope", so a use case with no such parameter fails
    here by name rather than being called without one.
    """
    for name, parameter in inspect.signature(use_case).parameters.items():
        if "scope" in name:
            assert parameter.kind is not inspect.Parameter.POSITIONAL_ONLY, (
                f"`{use_case.__name__}`'s scope parameter is positional-only; "
                "pass it positionally instead (a fixture correction)"
            )
            return {name: scope}
    pytest.fail(
        f"`{use_case.__name__}` takes no access-scope parameter, so the "
        "caller's scope cannot reach the read at all"
    )


class _FakeCatalogStore:
    """In-memory catalog store holding real `Product` aggregates.

    It filters nothing and ignores any extra argument a use case hands it
    (see the module docstring). Several method spellings are answered
    because no artifact fixes the port's names.
    """

    def __init__(self, *products: Product) -> None:
        self._products = tuple(products)

    async def list(self, *_args: Any, **_kwargs: Any) -> tuple[Product, ...]:
        return self._products

    async def list_all(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        return await self.list(*args, **kwargs)

    async def all(self, *args: Any, **kwargs: Any) -> tuple[Product, ...]:
        return await self.list(*args, **kwargs)

    async def get_by_id(
        self, product_id: ProductId, *_args: Any, **_kwargs: Any
    ) -> Product | None:
        for product in self._products:
            if product.id == product_id:
                return product
        return None

    async def get(
        self, product_id: ProductId, *args: Any, **kwargs: Any
    ) -> Product | None:
        return await self.get_by_id(product_id, *args, **kwargs)

    async def get_by_product_id(
        self, product_id: ProductId, *args: Any, **kwargs: Any
    ) -> Product | None:
        return await self.get_by_id(product_id, *args, **kwargs)

    async def get_by_sku(self, sku: Sku, *_args: Any, **_kwargs: Any) -> Product | None:
        for product in self._products:
            if product.sku == sku:
                return product
        return None

    async def find_by_sku(self, sku: Sku, *args: Any, **kwargs: Any) -> Product | None:
        return await self.get_by_sku(sku, *args, **kwargs)

    # Write-side members of the store port. The read use cases never call
    # them; they are here because the port declares them, and a double
    # that does not satisfy the protocol fails type checking for a reason
    # unrelated to anything asserted below.
    async def add(self, product: Product) -> None:
        self._products = (*self._products, product)

    async def save(self, product: Product) -> None:
        self._products = tuple(
            product if existing.id == product.id else existing
            for existing in self._products
        )


def _product(sku: str, name: str) -> Product:
    return Product.register(
        sku=Sku(sku),
        marketplace_id=MARKETPLACE,
        name=name,
        registered_at=T_REGISTERED,
    )


def _unknown_product_id() -> ProductId:
    return ProductId(str(uuid.uuid4()))


async def _read_by_id(
    store: _FakeCatalogStore, product_id: ProductId, scope: AccessScope
) -> Any:
    return await get_product_by_id(
        store, product_id, **_scope_argument(get_product_by_id, scope)
    )


async def _read_by_sku(store: _FakeCatalogStore, sku: Sku, scope: AccessScope) -> Any:
    return await get_product_by_sku(
        store, sku, **_scope_argument(get_product_by_sku, scope)
    )


async def _list(store: _FakeCatalogStore, scope: AccessScope) -> tuple[Any, ...]:
    return tuple(await list_products(store, **_scope_argument(list_products, scope)))


# ---------------------------------------------------------------------------
# Requirement: A product can be read back by identifier or by SKU
# ---------------------------------------------------------------------------


async def test_a_product_is_retrieved_by_identifier_under_a_permitting_scope() -> None:
    """Scenario: A product is retrieved by identifier.

    WHEN a product is read using the identifier it was registered with,
    under a scope that permits that identifier
    THEN the product is returned with every field it carries.

    A second, unpermitted product sits in the store so that "returned" is
    the scope's decision about this product rather than a read that ignores
    the scope entirely.
    """
    wanted = _product("WIDGET-001", "Widget A")
    other = _product("WIDGET-002", "Widget B")
    store = _FakeCatalogStore(wanted, other)

    found = await _read_by_id(store, wanted.id, _permitting(wanted.id))

    assert found is not None
    # SPECIFIED: every field it carries -- identity, name, current stage,
    # and stage-entry time (the requirement statement's enumeration), plus
    # the SKU and marketplace the registration carried.
    assert found.id == wanted.id
    assert found.sku == Sku("WIDGET-001")
    assert found.marketplace_id == MARKETPLACE
    assert found.name == "Widget A"
    assert found.stage == Development()
    assert found.stage_entered_at == T_REGISTERED


async def test_a_product_is_retrieved_by_sku_under_a_permitting_scope() -> None:
    """Scenario: A product is retrieved by SKU.

    WHEN a product is read using its SKU, under a scope that permits its
    product identifier
    THEN the same product is returned.

    "The same product" is asserted against the identifier the by-identifier
    read answers with, so the two reads agree rather than each being
    checked against a literal.
    """
    wanted = _product("WIDGET-001", "Widget A")
    other = _product("WIDGET-002", "Widget B")
    store = _FakeCatalogStore(wanted, other)
    scope = _permitting(wanted.id)

    by_sku = await _read_by_sku(store, Sku("WIDGET-001"), scope)
    by_id = await _read_by_id(store, wanted.id, scope)

    assert by_sku is not None
    assert by_id is not None
    # SPECIFIED: the same product.
    assert by_sku.id == by_id.id == wanted.id
    assert by_sku.name == "Widget A"


@pytest.mark.parametrize("permissive", [True, False], ids=["unrestricted", "empty"])
async def test_an_unknown_product_reports_absence_under_any_scope(
    permissive: bool,
) -> None:
    """Scenario: An unknown product reports absence.

    WHEN a product is read using an identifier or SKU no registered product
    has, under any scope
    THEN the system reports that no product was found, rather than an
    error.

    "Under any scope" is exercised at both ends of the range: the
    unrestricted scope and the scope that permits nothing. Reaching the
    assertions at all is the "rather than an error" half.
    """
    registered = _product("WIDGET-001", "Widget A")
    store = _FakeCatalogStore(registered)
    scope = _unrestricted() if permissive else _permitting()

    by_id = await _read_by_id(store, _unknown_product_id(), scope)
    by_sku = await _read_by_sku(store, Sku("WIDGET-NOBODY-HAS"), scope)

    # SPECIFIED: no product was found.
    assert by_id is None
    assert by_sku is None


async def test_an_out_of_scope_product_reports_the_same_absence() -> None:
    """Scenario: An out-of-scope product reports the same absence.

    WHEN a registered product is read by identifier or by SKU under a scope
    that does not permit its product identifier
    THEN the system reports that no product was found, exactly as it does
    for a product that does not exist.

    "Exactly as" is asserted by comparing the two answers to each other,
    not merely by checking each is falsy: a hidden product reported as a
    distinct sentinel, a raised "forbidden" error, or a stripped-down
    placeholder would each leak that the product exists, and each would
    fail here while a bare `assert not found` would let two of the three
    through.
    """
    hidden = _product("WIDGET-001", "Widget A")
    permitted = _product("WIDGET-002", "Widget B")
    store = _FakeCatalogStore(hidden, permitted)
    scope = _permitting(permitted.id)

    out_of_scope_by_id = await _read_by_id(store, hidden.id, scope)
    out_of_scope_by_sku = await _read_by_sku(store, Sku("WIDGET-001"), scope)
    nonexistent_by_id = await _read_by_id(store, _unknown_product_id(), scope)
    nonexistent_by_sku = await _read_by_sku(store, Sku("WIDGET-NOBODY-HAS"), scope)

    # SPECIFIED: the same absence a nonexistent product reports.
    assert out_of_scope_by_id == nonexistent_by_id
    assert out_of_scope_by_sku == nonexistent_by_sku
    assert out_of_scope_by_id is None
    assert out_of_scope_by_sku is None
    # DERIVED, so the assertions above cannot pass by everything being
    # absent: the permitted product is still readable under this scope.
    assert await _read_by_id(store, permitted.id, scope) is not None


# ---------------------------------------------------------------------------
# Requirement: Products can be listed with their stages
# ---------------------------------------------------------------------------


async def test_products_are_listed_under_the_unrestricted_scope() -> None:
    """Scenario: Products are listed.

    WHEN the product list is requested under the unrestricted scope and
    products exist
    THEN every registered product is returned with its identifier, SKU,
    name, and current stage.

    Two products, so a single-row accident cannot pass, and equality on the
    identifier set rather than containment -- unlike the integration tier,
    this store holds exactly what the test put in it.
    """
    first = _product("WIDGET-001", "Widget A")
    second = _product("WIDGET-002", "Widget B")
    store = _FakeCatalogStore(first, second)

    listed = await _list(store, _unrestricted())

    by_id = {entry.id: entry for entry in listed}
    # SPECIFIED: every registered product.
    assert set(by_id) == {first.id, second.id}
    for registered in (first, second):
        entry = by_id[registered.id]
        # SPECIFIED: identifier, SKU, name, and current stage.
        assert entry.sku == registered.sku
        assert entry.name == registered.name
        assert entry.stage == Development()


async def test_a_restricted_scope_lists_only_its_products() -> None:
    """Scenario: A restricted scope lists only its products.

    WHEN the product list is requested under a scope permitting some
    registered products' identifiers but not others
    THEN exactly the permitted products are returned.

    Two permitted and one not, so an implementation returning only the
    first permitted product fails alongside one that returns everything.
    """
    first = _product("WIDGET-001", "Widget A")
    second = _product("WIDGET-002", "Widget B")
    hidden = _product("WIDGET-003", "Widget C")
    store = _FakeCatalogStore(first, second, hidden)

    listed = await _list(store, _permitting(first.id, second.id))

    # SPECIFIED: exactly the permitted products.
    assert {entry.id for entry in listed} == {first.id, second.id}


async def test_an_empty_catalog_lists_nothing() -> None:
    """Scenario: An empty catalog lists nothing.

    WHEN the product list is requested and no products exist
    THEN an empty result is returned.

    The pre-existing
    `tests/unit/catalog/application/test_list_products_empty_catalog.py`
    covers this scenario under the call convention this change supersedes
    (no scope parameter); it is listed in the manifest's obsolete-tests
    section, and this pass neither edits nor deletes it. Asserted here
    under the unrestricted scope, so an empty result cannot be explained by
    the scope permitting nothing.
    """
    listed = await _list(_FakeCatalogStore(), _unrestricted())

    # SPECIFIED: an empty result -- not None, not an error.
    assert len(listed) == 0


async def test_a_scope_permitting_nothing_lists_nothing() -> None:
    """Scenario: A scope permitting nothing lists nothing.

    WHEN the product list is requested under a scope that permits no
    product identifier and products exist
    THEN an empty result is returned rather than an error.

    Two products exist, so the empty result is the scope's doing; reaching
    the assertion is the "rather than an error" half.
    """
    store = _FakeCatalogStore(
        _product("WIDGET-001", "Widget A"), _product("WIDGET-002", "Widget B")
    )

    listed = await _list(store, _permitting())

    assert len(listed) == 0
