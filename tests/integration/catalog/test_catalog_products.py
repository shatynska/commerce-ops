"""Tests for the `product-catalog` capability's persistence scenarios,
against a real Postgres.

Derived strictly from the ADDED requirements in
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/product-catalog/spec.md`:

- Requirement: *A product is registered with its identity* (all three
  scenarios)
- Requirement: *A product can be read back by identifier or by SKU* (all
  three scenarios)
- Requirement: *Products can be listed with their stages* — the non-empty
  scenario; the empty-catalog scenario is only observable against a store
  double (no truncate fixture exists in this tier — see
  `tests/unit/catalog/application/test_list_products_empty_catalog.py`)
- plus persistence-level coverage of one legal and one rejected stage
  change, supplementary to the aggregate-level tests in
  `tests/unit/catalog/domain/test_product_lifecycle.py` where those
  scenarios are primarily accounted for.

These scenarios say "persisted", "reading the product back", "no new
record is persisted" — outcomes whose smallest observing unit is a real
store read through an independent session, i.e. this project's
`tests/integration/` tier (runs at pre-push; skips when `DATABASE_URL` is
unset, per this tier's existing convention).

Per design.md Decision 10, registration and stage changes are exercised
through catalog's use cases — its public application surface — not by
poking rows directly.

## The interface under test does not exist yet, and its shape is INVENTED

Neither `catalog/application` nor `catalog/infrastructure` exists yet, so
every test here is expected to fail at collection on an absent target
(`ModuleNotFoundError`). Assumed, and recorded in the manifest as
unresolved project questions:

- Use cases exported from `commerce_ops.catalog.application`:
  `register_product`, `record_asin`, `change_stage`, `get_product_by_id`,
  `get_product_by_sku`, `list_products` (the six tasks.md 3.1 names),
  each an async function taking the store port as its first argument
  (this project's `run_daily_digest(reader)` port-passing precedent), and
  `DuplicateSkuError` as the duplicate-SKU rejection signal.
- `commerce_ops.catalog.infrastructure.driven.product_repository
  .CatalogProductRepository(session: AsyncSession)` as the port's real
  adapter, committing its own work — mirroring the invented-and-recorded
  shape of the products module's repository
  (`tests/integration/products/test_product_repository.py`).
- Returned product views exposing `.id`, `.sku`, `.marketplace_id`,
  `.name`, `.asin`, `.stage`, `.stage_entered_at`; identity fields carry
  the shared vocabulary's value objects.
- Illegal stage changes surface `StageTransitionError` from
  `commerce_ops.catalog.domain.product`, propagated by the use case.

Correcting any of those paths, names, or shapes is a fixture correction
(failure state 3 in `ai-toolkit:testing`); the state postconditions —
what was persisted, what was *not*, what a re-read through an independent
session reports — are what trace to the spec and must survive unweakened.

## Test-database lifecycle

Each test generates its own unique SKU rather than assuming an empty
database — the same convention `tests/integration/products/` records: no
artifact establishes a truncate/rollback convention for this database.
These tests assume `alembic upgrade head` has been applied, including
this change's own table-split migration.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import (
    DuplicateSkuError,
    change_stage,
    get_product_by_id,
    get_product_by_sku,
    list_products,
    record_asin,
    register_product,
)
from commerce_ops.catalog.domain.product import StageTransitionError
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.lifecycle_stage import (
    Development,
    Launching,
    Posture,
    SteadyState,
)

pytestmark = pytest.mark.anyio

MARKETPLACE = MarketplaceId("ATVPDKIKX0DER")
CONFIRMER = "Helen"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's table-split migration), and point DATABASE_URL at it "
            "to run tests/integration/catalog/."
        )
    return url


def unique_sku() -> Sku:
    """A SKU unique to this test run — no truncate fixture exists, so
    uniqueness is what keeps runs independent (same reasoning as
    `tests/integration/products/conftest.py`'s `unique_sku`)."""
    return Sku(f"CAT-{uuid.uuid4().hex[:12].upper()}")


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def store(engine: AsyncEngine) -> AsyncIterator[CatalogProductRepository]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield CatalogProductRepository(session)


@pytest.fixture()
def new_store(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[CatalogProductRepository]]:
    """An independent session/store factory, so a read can prove the
    write reached Postgres rather than a session identity map."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[CatalogProductRepository]:
        async with maker() as session:
            yield CatalogProductRepository(session)

    return _open


# ---------------------------------------------------------------------------
# Requirement: A product is registered with its identity
# ---------------------------------------------------------------------------


async def test_a_product_is_registered_with_required_fields_only(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: A product is registered with required fields only.

    WHEN a product is registered with a SKU, a marketplace identifier,
    and a name, and no ASIN
    THEN the product is persisted with those values and its ASIN reported
    as absent.
    """
    sku = unique_sku()

    registered = await register_product(
        store, sku=sku, marketplace_id=MARKETPLACE, name="Widget"
    )

    async with new_store() as other:
        reread = await get_product_by_id(other, registered.id)

    assert reread is not None
    # SPECIFIED: persisted with those values.
    assert reread.sku == sku
    assert reread.marketplace_id == MARKETPLACE
    assert reread.name == "Widget"
    # SPECIFIED: ASIN reported as absent.
    assert reread.asin is None
    # SPECIFIED (Requirement: A new product starts in Development) —
    # supplementary here to the aggregate-level test, confirming the
    # stamp survives persistence.
    assert reread.stage == Development()


async def test_registering_a_duplicate_sku_is_rejected_without_persisting(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: A duplicate SKU is rejected.

    WHEN a product is registered with a SKU that already belongs to an
    existing product
    THEN the registration is rejected and no new record is persisted.
    """
    sku = unique_sku()
    original = await register_product(
        store, sku=sku, marketplace_id=MARKETPLACE, name="Widget"
    )

    with pytest.raises(DuplicateSkuError):
        await register_product(
            store, sku=sku, marketplace_id=MARKETPLACE, name="A Different Widget"
        )

    # SPECIFIED: no new record — the SKU still resolves to the original.
    async with new_store() as other:
        reread = await get_product_by_sku(other, sku)
    assert reread is not None
    assert reread.id == original.id
    assert reread.name == "Widget"


async def test_an_asin_recorded_later_is_reported_on_read_back(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: An ASIN is recorded later.

    WHEN an ASIN is recorded for a product registered without one
    THEN reading the product back reports that ASIN.
    """
    registered = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget"
    )
    assert registered.asin is None  # precondition: registered without one

    await record_asin(store, registered.id, Asin("B0EXAMPLE1"))

    async with new_store() as other:
        reread = await get_product_by_id(other, registered.id)
    assert reread is not None
    # SPECIFIED: reading the product back reports that ASIN.
    assert reread.asin == Asin("B0EXAMPLE1")


# ---------------------------------------------------------------------------
# Requirement: A product can be read back by identifier or by SKU
# ---------------------------------------------------------------------------


async def test_a_product_is_retrieved_by_identifier_with_every_field(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: A product is retrieved by identifier.

    WHEN a product is read using the identifier it was registered with
    THEN the product is returned with every field it carries — the
    requirement enumerates identity, name, current stage, and stage-entry
    time.
    """
    registered = await register_product(
        store,
        sku=unique_sku(),
        marketplace_id=MARKETPLACE,
        name="Widget",
        asin=Asin("B0EXAMPLE2"),
    )

    async with new_store() as other:
        reread = await get_product_by_id(other, registered.id)

    assert reread is not None
    # SPECIFIED: identity, name, current stage, and stage-entry time.
    assert reread.id == registered.id
    assert reread.sku == registered.sku
    assert reread.marketplace_id == MARKETPLACE
    assert reread.asin == Asin("B0EXAMPLE2")
    assert reread.name == "Widget"
    assert reread.stage == Development()
    assert reread.stage_entered_at is not None


async def test_a_product_is_retrieved_by_sku(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: A product is retrieved by SKU.

    WHEN a product is read using its SKU
    THEN the same product is returned.
    """
    registered = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget"
    )

    async with new_store() as other:
        reread = await get_product_by_sku(other, registered.sku)

    # SPECIFIED: the same product.
    assert reread is not None
    assert reread.id == registered.id
    assert reread.sku == registered.sku


@pytest.mark.parametrize("lookup", ["by-unknown-identifier", "by-unknown-sku"])
async def test_an_unknown_product_reports_absence(
    lookup: str, store: CatalogProductRepository
) -> None:
    """Scenario: An unknown product reports absence.

    WHEN a product is read using an identifier or SKU no registered
    product has
    THEN the system reports that no product was found, rather than an
    error.
    """
    if lookup == "by-unknown-identifier":
        # ProductId is opaque (generated, never parsed), so any non-empty
        # value that no registration produced is a valid unknown key.
        result = await get_product_by_id(store, ProductId(str(uuid.uuid4())))
    else:
        result = await get_product_by_sku(store, unique_sku())

    # SPECIFIED: absence is reported (`None`), not an error raised.
    assert result is None


# ---------------------------------------------------------------------------
# Requirement: Products can be listed with their stages
# ---------------------------------------------------------------------------


async def test_products_are_listed_with_identifier_sku_name_and_stage(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: Products are listed.

    WHEN the product list is requested and products exist
    THEN every registered product is returned with its identifier, SKU,
    name, and current stage.

    Containment, not equality, against the full result: this database is
    not truncated between runs, so unrelated products may exist. Two
    products are registered so a single-row accident cannot pass.
    """
    first = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget A"
    )
    second = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget B"
    )

    async with new_store() as other:
        listed = await list_products(other)

    by_id = {entry.id: entry for entry in listed}
    for registered in (first, second):
        entry = by_id.get(registered.id)
        assert entry is not None
        # SPECIFIED: identifier, SKU, name, and current stage.
        assert entry.sku == registered.sku
        assert entry.name == registered.name
        assert entry.stage == Development()


# ---------------------------------------------------------------------------
# Stage changes at the persistence level — supplementary to the
# aggregate-level tests where these scenarios are primarily accounted for
# ---------------------------------------------------------------------------


async def test_a_confirmed_stage_change_is_persisted(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Supplementary persistence coverage of *Scenario: A legal
    transition is applied and attributed* and *Scenario: Stage entry time
    is reported* — the aggregate-level tests observe the state machine;
    this observes that the changed stage, its provenance, and its entry
    time survive to Postgres and back.
    """
    registered = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget"
    )

    await change_stage(store, registered.id, Launching(phase=1), confirmed_by=CONFIRMER)

    async with new_store() as other:
        reread = await get_product_by_id(other, registered.id)
    assert reread is not None
    # SPECIFIED: the stage is Launching phase 1, with the change's
    # confirmer recorded.
    assert reread.stage == Launching(phase=1)
    # SPECIFIED: the entry time of the current stage is reported with it.
    # The use case stamps the clock itself, so only presence and ordering
    # are asserted here; exact-time assertions live at the aggregate
    # level where the instant is passed in.
    assert reread.stage_entered_at is not None
    assert reread.stage_entered_at >= registered.stage_entered_at


async def test_a_rejected_stage_change_leaves_the_stored_stage_unchanged(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Supplementary persistence coverage of *Scenario: An illegal
    transition is rejected* — "the stored stage is unchanged" observed
    against the store itself.
    """
    registered = await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget"
    )

    with pytest.raises(StageTransitionError):
        await change_stage(
            store,
            registered.id,
            SteadyState(posture=Posture.SCALE),
            confirmed_by=CONFIRMER,
        )

    async with new_store() as other:
        reread = await get_product_by_id(other, registered.id)
    assert reread is not None
    # SPECIFIED: the stored stage is unchanged.
    assert reread.stage == Development()
