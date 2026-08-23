"""Tests for the launch-position record (`launch-instance`, as reshaped
by `introduce-catalog-and-shared-vocabulary`), against a real Postgres.

Derived strictly from the launch-instance delta at
`openspec/changes/introduce-catalog-and-shared-vocabulary/specs/launch-instance/spec.md`:

- ADDED Requirement: *A launch position is persisted for a catalog
  product* (all three scenarios)
- ADDED Requirement: *A launch position can be read back by product
  identifier* (both scenarios)
- MODIFIED Requirement: *A product's current gate is restricted to the
  launch-playbook gate sequence* (both scenarios, as revised — now about
  the launch position)
- MODIFIED Requirement: *A product's current gate can be updated* (both
  scenarios, as revised)

The MODIFIED requirements' scenarios are covered here as new tests, per
the delta operation's meaning: the revised behavior gets fresh coverage;
the existing tests asserting the superseded flat-record shape
(`tests/integration/products/test_product_repository.py`) are recorded in
the manifest's obsolete list and are not edited by this pass.

This is a **new** file. Both the existing files in this directory keep
running against the pre-change repository until implementation lands;
nothing here touches them or their `conftest.py`.

Every scenario here states persistence outcomes ("persisted", "nothing is
persisted", "the record is returned", real FK existence against the
catalog), so the integration tier is the smallest level that can observe
them.

## The interface under test does not exist yet, and its shape is INVENTED

tasks.md 4.2 reshapes the products module's model and repository to the
launch-position record but fixes no names. Assumed, and recorded in the
manifest as unresolved project questions:

- `commerce_ops.launch.infrastructure.driven.launch_position_repository`
  exporting `LaunchPositionRepository(session: AsyncSession)` and a
  single `LaunchPositionError` raised for every rejection this delta
  describes (unknown product, second position, unrecognized gate, update
  of a nonexistent position) — the same
  one-exception-per-rejected-operation-family precedent
  `test_product_repository.py` records.
- Methods `create(product_id, playbook_version, current_gate=None,
  launch_date=None)`, `get_by_product_id(product_id)`, and
  `update_current_gate(product_id, gate)`, each async and committing its
  own work; `create`/`get_by_product_id` return a record exposing
  `.product_id`, `.playbook_version`, `.current_gate`, `.launch_date`.
- Catalog products to reference are registered through
  `commerce_ops.catalog.application` (see
  `tests/integration/catalog/test_catalog_products.py`'s docstring for
  that invented surface).

Correcting any path, name, or signature above is a fixture correction
(failure state 3 in `ai-toolkit:testing`); what must survive unweakened
are the postconditions each test asserts — what was persisted, what was
not, and what a re-read through an independent session reports.

## Test-database lifecycle

Same convention as the rest of this directory: unique SKUs per test, no
truncate fixture, `alembic upgrade head` (including this change's
table-split migration) assumed applied, and a skip when `DATABASE_URL`
is unset.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from typing import Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_position_repository import (
    LaunchPositionError,
    LaunchPositionRepository,
)
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

pytestmark = pytest.mark.anyio

# SPECIFIED: the eight gate ids, exactly as the MODIFIED requirement
# enumerates them.
EIGHT_GATE_IDS: Final = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)

NOT_A_GATE: Final = "not-a-real-gate"

MARKETPLACE = MarketplaceId("ATVPDKIKX0DER")


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
            "to run these tests."
        )
    return url


def _unique_sku() -> Sku:
    return Sku(f"LP-{uuid.uuid4().hex[:12].upper()}")


@pytest.fixture()
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def positions(engine: AsyncEngine) -> AsyncIterator[LaunchPositionRepository]:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield LaunchPositionRepository(session)


@pytest.fixture()
def new_positions(
    engine: AsyncEngine,
) -> Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]]:
    """An independent session/repository factory, so reads prove the
    write reached Postgres rather than a session identity map."""
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[LaunchPositionRepository]:
        async with maker() as session:
            yield LaunchPositionRepository(session)

    return _open


@pytest.fixture()
def registered_product_id(engine: AsyncEngine) -> Callable[[], Awaitable[ProductId]]:
    """A factory registering a fresh catalog product and returning its
    identifier — every launch position needs an existing catalog product
    to reference."""

    async def _register() -> ProductId:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=_unique_sku(),
                marketplace_id=MARKETPLACE,
                name="Launch Test Widget",
            )
        return product.id

    return _register


# ---------------------------------------------------------------------------
# ADDED Requirement: A launch position is persisted for a catalog product
# ---------------------------------------------------------------------------


async def test_a_launch_position_is_created_for_an_existing_product(
    positions: LaunchPositionRepository,
    new_positions: Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A launch position is created for an existing product.

    WHEN a launch position is created for a registered catalog product
    with a playbook version and no launch date
    THEN the record is persisted referencing that product, with the
    launch date reported as absent.
    """
    product_id = await registered_product_id()

    await positions.create(product_id, playbook_version="v1")

    async with new_positions() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    # SPECIFIED: persisted referencing that product.
    assert reread.product_id == product_id
    assert reread.playbook_version == "v1"
    # SPECIFIED: launch date reported as absent.
    assert reread.launch_date is None


async def test_a_launch_position_for_an_unknown_product_is_rejected(
    positions: LaunchPositionRepository,
) -> None:
    """Scenario: A launch position for an unknown product is rejected.

    WHEN a launch position is created for a product identifier no catalog
    product has
    THEN the creation is rejected and nothing is persisted.
    """
    # ProductId is opaque (generated, never parsed), so a fresh value no
    # registration produced is a valid unknown identifier.
    unknown_id = ProductId(str(uuid.uuid4()))

    with pytest.raises(LaunchPositionError):
        await positions.create(unknown_id, playbook_version="v1")

    # SPECIFIED: nothing is persisted.
    assert await positions.get_by_product_id(unknown_id) is None


async def test_a_second_launch_position_for_the_same_product_is_rejected(
    positions: LaunchPositionRepository,
    new_positions: Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A second launch position for the same product is
    rejected.

    WHEN a launch position is created for a product that already has one
    THEN the creation is rejected and the existing record is unchanged.
    """
    product_id = await registered_product_id()
    await positions.create(product_id, playbook_version="v1")

    with pytest.raises(LaunchPositionError):
        await positions.create(product_id, playbook_version="v2")

    # SPECIFIED: the existing record is unchanged.
    async with new_positions() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    assert reread.playbook_version == "v1"


# ---------------------------------------------------------------------------
# ADDED Requirement: A launch position can be read back by product
# identifier
# ---------------------------------------------------------------------------


async def test_a_launch_position_is_retrieved_with_every_field(
    positions: LaunchPositionRepository,
    new_positions: Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A launch position is retrieved.

    WHEN a launch position is read using the product identifier it was
    created for
    THEN the record is returned with every field it was persisted with.
    """
    product_id = await registered_product_id()
    await positions.create(
        product_id,
        playbook_version="v1",
        current_gate="order",
        launch_date=date(2027, 3, 1),
    )

    async with new_positions() as other:
        reread = await other.get_by_product_id(product_id)

    assert reread is not None
    # SPECIFIED: every field it was persisted with.
    assert reread.product_id == product_id
    assert reread.playbook_version == "v1"
    assert reread.current_gate == "order"
    assert reread.launch_date == date(2027, 3, 1)


async def test_a_product_without_a_launch_position_reports_absence(
    positions: LaunchPositionRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A product without a launch position reports absence.

    WHEN a launch position is read for a product identifier that has none
    THEN the system reports that none exists, rather than an error.

    The product is a real, registered catalog product — so this is
    exactly the post-split state the delta introduces (a catalog-only
    product), not merely an unknown identifier.
    """
    product_id = await registered_product_id()

    result = await positions.get_by_product_id(product_id)

    # SPECIFIED: absence (`None`), not an error.
    assert result is None


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A product's current gate is restricted to the
# launch-playbook gate sequence
# ---------------------------------------------------------------------------


async def test_a_new_launch_position_defaults_to_the_first_gate(
    positions: LaunchPositionRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A new product defaults to the first gate (as revised).

    WHEN a launch position is created without specifying a current gate
    THEN its current gate is reported as `commit`.
    """
    product_id = await registered_product_id()

    created = await positions.create(product_id, playbook_version="v1")

    # SPECIFIED: defaults to `commit`.
    assert created.current_gate == "commit"


async def test_creating_with_an_unrecognized_gate_is_rejected(
    positions: LaunchPositionRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: An unrecognized gate is rejected (create half).

    WHEN a launch position is created ... with a current gate that is not
    one of the eight `launch-playbook` gate ids
    THEN the operation is rejected and the stored gate is unchanged.

    DERIVED (same reading `test_product_repository.py` records for the
    pre-change shape): on the create path there is no prior stored gate,
    so "unchanged" is asserted as nothing having been persisted at all.
    """
    product_id = await registered_product_id()

    with pytest.raises(LaunchPositionError):
        await positions.create(
            product_id, playbook_version="v1", current_gate=NOT_A_GATE
        )

    assert await positions.get_by_product_id(product_id) is None


async def test_updating_to_an_unrecognized_gate_is_rejected(
    positions: LaunchPositionRepository,
    new_positions: Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: An unrecognized gate is rejected (update half).

    WHEN a launch position is ... updated with a current gate that is not
    one of the eight `launch-playbook` gate ids
    THEN the operation is rejected and the stored gate is unchanged.
    """
    product_id = await registered_product_id()
    created = await positions.create(product_id, playbook_version="v1")
    assert created.current_gate == "commit"  # precondition

    with pytest.raises(LaunchPositionError):
        await positions.update_current_gate(product_id, NOT_A_GATE)

    # SPECIFIED: the stored gate is unchanged.
    async with new_positions() as other:
        reread = await other.get_by_product_id(product_id)
    assert reread is not None
    assert reread.current_gate == "commit"


@pytest.mark.parametrize("gate_id", EIGHT_GATE_IDS)
async def test_creating_with_each_of_the_eight_gate_ids_is_accepted(
    gate_id: str,
    positions: LaunchPositionRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """DERIVED, not a named scenario: the requirement states the gate
    SHALL be one of the eight ids, but the named scenarios exercise only
    the default and one rejected value. Parametrized over all eight,
    following this project's precedent for testing a fixed-vocabulary
    requirement exhaustively (`test_product_repository.py`'s counterpart
    and `test_playbook_loader.py`'s gate parametrizations).
    """
    product_id = await registered_product_id()

    created = await positions.create(
        product_id, playbook_version="v1", current_gate=gate_id
    )

    assert created.current_gate == gate_id


# ---------------------------------------------------------------------------
# MODIFIED Requirement: A product's current gate can be updated
# ---------------------------------------------------------------------------


async def test_updating_the_current_gate_to_a_valid_gate_persists(
    positions: LaunchPositionRepository,
    new_positions: Callable[[], AbstractAsyncContextManager[LaunchPositionRepository]],
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: A product's current gate is updated to a valid gate (as
    revised).

    WHEN an existing launch position's current gate is updated to `order`
    THEN reading it back reports `order` as its current gate.
    """
    product_id = await registered_product_id()
    await positions.create(product_id, playbook_version="v1")

    await positions.update_current_gate(product_id, "order")

    async with new_positions() as other:
        reread = await other.get_by_product_id(product_id)
    # SPECIFIED: reading it back reports `order`.
    assert reread is not None
    assert reread.current_gate == "order"


async def test_updating_a_product_with_no_launch_position_is_rejected(
    positions: LaunchPositionRepository,
    registered_product_id: Callable[[], Awaitable[ProductId]],
) -> None:
    """Scenario: Updating a nonexistent product is rejected (as revised).

    WHEN a current-gate update targets a product identifier that has no
    launch position
    THEN the update is rejected.

    Exercised with a real catalog product that has no launch position —
    the sharper post-split case — and the delta's own wording ("that has
    no launch position") covers it.
    """
    product_id = await registered_product_id()

    with pytest.raises(LaunchPositionError):
        await positions.update_current_gate(product_id, "order")
