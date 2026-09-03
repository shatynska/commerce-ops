"""The three hazard-category states survive a Postgres round trip
(`product-catalog`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/product-catalog/spec.md`

Covers, at the storage level `tasks.md` 1.5 asks for, the scenarios of
*A hazard-category finding can be recorded against a product* and *A
product reports its hazard categories in three states, never two* whose
truth depends on what the column actually holds:

- Hazard categories are recorded for a product with none
- An empty set is recorded as an empty set
- A later recording replaces the earlier one wholesale
- An empty set replaces a recorded set
- Recording does not require a particular stage
- A never-screened product reports the question as open
- A cleared product reports an answered question
- A flagged product reports its categories
- A product predating the field reports the question as open

## Level — and why this tier, not only the unit one

`tasks.md` 1.5 is explicit: "this tier is where the storage decision is
actually proved: the in-memory double cannot distinguish a column that
stores `[]` as `NULL`." Every scenario above is also covered against a
store double; none of that coverage can observe a mapping that collapses
`{}` into `NULL` on the way down or on the way back up, which
`design.md` Decision 1 identifies as the single defect this change is
most exposed to and `tasks.md` 2.3 names as "the one mapping where a
falsy-value shortcut silently collapses the two states".

Every read is taken through an **independent session**, so a passing
assertion is a statement about Postgres rather than about a session
identity map — the convention
`tests/integration/catalog/test_catalog_products.py` established and
whose fixtures this file duplicates rather than imports, this project
sharing no test-helper module.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 1 and `tasks.md` 2.1-2.3: a nullable
`hazard_categories text[]` on `products`, no default, no backfill, with
`NULL` and `{}` kept distinct across the round trip.

Fixed by `tasks.md` 3.2-3.3: `record_hazard_categories` exported from
`commerce_ops.catalog.application`, taking the store, the product id and
the categories.

INVENTED, recorded in `test-manifest.md`: the positional call convention,
matching `record_asin`'s call in the sibling file; and that the read-back
view exposes the recorded set under `.hazard_categories`, mirroring
`.asin` and `.sub_category`.

## Expected first-run state

The column, the mapping and the use case do not exist (`tasks.md` 2.1-3.3),
so every test here is expected to fail on an absent target — `ImportError`
at collection. Per `ai-toolkit:testing` that establishes absence only.

The tier itself is configured in this worktree and genuinely runs;
baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/integration` — 152 passed, 0 failed,
0 skipped; `uv run pytest tests/unit tests/agents` — 2352 passed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import (
    change_stage,
    get_product_by_id,
    record_hazard_categories,
    register_product,
)
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from commerce_ops.shared.domain.lifecycle_stage import Retired

pytestmark = pytest.mark.anyio

MARKETPLACE: Final = MarketplaceId("ATVPDKIKX0DER")
CONFIRMER: Final = "Helen"

FLAGGED: Final = ("supplements",)
LATER_FLAGGED: Final = ("medical devices", "lighters")
EMPTY: Final[tuple[str, ...]] = ()


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def unique_sku() -> Sku:
    """A SKU unique to this run — no truncate fixture exists in this tier,
    so uniqueness is what keeps runs independent."""
    return Sku(f"HAZ-{uuid.uuid4().hex[:12].upper()}")


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(database_url)
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
    maker = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def _open() -> AsyncIterator[CatalogProductRepository]:
        async with maker() as session:
            yield CatalogProductRepository(session)

    return _open


async def _reread(
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
    product_id: Any,
) -> Any:
    async with new_store() as other:
        reread = await get_product_by_id(
            other, product_id, scope=AccessScope.unrestricted()
        )
    assert reread is not None, "the product could not be read back at all"
    return reread


def _reading(view: Any) -> Any:
    return view.hazard_categories


def _members(view: Any) -> list[str]:
    reading = _reading(view)
    assert reading is not None, (
        "the round trip reported the hazard categories as never recorded "
        "where a set was recorded — `NULL` was stored, or read, for a "
        "value that was not absent"
    )
    assert not isinstance(reading, str), (
        f"the round trip reported the string {reading!r} rather than a set "
        "of categories"
    )
    return list(reading)


async def _registered(store: CatalogProductRepository) -> Any:
    return await register_product(
        store, sku=unique_sku(), marketplace_id=MARKETPLACE, name="Widget"
    )


# ---------------------------------------------------------------------------
# The three states, across the round trip
# ---------------------------------------------------------------------------


async def test_a_never_screened_product_round_trips_as_never_recorded(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenarios: *A never-screened product reports the question as open*
    and *A product predating the field reports the question as open*.

    A product registered without hazard categories is exactly what every
    row predating the migration is — `design.md` Decision 1 takes `NULL`
    for those rows deliberately, "no default, because a default of `'{}'`
    would declare every existing product screened and clear". So this row
    covers both scenarios: at the storage level they are the same fact.
    """
    registered = await _registered(store)

    reread = await _reread(new_store, registered.id)

    assert _reading(reread) is None, (
        "a product nothing has screened round-trips as something other "
        f"than absent: {_reading(reread)!r}"
    )


async def test_a_recorded_empty_set_round_trips_as_recorded_and_empty(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenarios: *An empty set is recorded as an empty set* and *A cleared
    product reports an answered question*.

    **The row this tier exists for.** `{}` and `NULL` are two different
    column values and one falsy Python value; an ORM mapping, a repository
    conversion or a migration default that treats them alike passes every
    unit-level test in this change and fails here.
    """
    registered = await _registered(store)
    unscreened = await _registered(store)

    await record_hazard_categories(store, registered.id, EMPTY)

    reread = await _reread(new_store, registered.id)
    never = await _reread(new_store, unscreened.id)
    assert _members(reread) == []
    assert _reading(reread) != _reading(never), (
        "a screening that found the product clear round-trips identically "
        "to a product nothing has ever screened; the storage collapsed "
        "`{}` into `NULL`"
    )


async def test_a_recorded_non_empty_set_round_trips_with_every_member(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenarios: *Hazard categories are recorded for a product with none*
    and *A flagged product reports its categories*.

    Several members, so a mapping that stores only the first — or joins
    them into one string — is caught. The member with a space in it is
    deliberate: it is what the authored description's own wording looks
    like.
    """
    registered = await _registered(store)

    await record_hazard_categories(store, registered.id, LATER_FLAGGED)

    reread = await _reread(new_store, registered.id)
    assert _members(reread) == list(LATER_FLAGGED)


async def test_a_later_recording_replaces_the_stored_set_wholesale(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: A later recording replaces the earlier one wholesale."""
    registered = await _registered(store)
    await record_hazard_categories(store, registered.id, FLAGGED)

    await record_hazard_categories(store, registered.id, LATER_FLAGGED)

    reread = await _reread(new_store, registered.id)
    assert _members(reread) == list(LATER_FLAGGED)
    for earlier in FLAGGED:
        assert earlier not in _members(reread), (
            f"{earlier!r} survived in the stored set, so the later "
            "recording was appended to the column rather than replacing it"
        )


async def test_a_stored_set_is_replaced_by_an_empty_set(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: An empty set replaces a recorded set.

    The clear-after-flagged case, across the round trip: "a screening that
    found a product clear replaces a set recorded by an earlier screening
    that flagged it". An implementation skipping the write for a falsy
    value leaves the flag standing and fails here.
    """
    registered = await _registered(store)
    unscreened = await _registered(store)
    await record_hazard_categories(store, registered.id, FLAGGED)

    await record_hazard_categories(store, registered.id, EMPTY)

    reread = await _reread(new_store, registered.id)
    never = await _reread(new_store, unscreened.id)
    assert _members(reread) == []
    assert _reading(reread) != _reading(never), (
        "an empty set stored over a flag round-trips as never screened"
    )


async def test_recording_does_not_require_a_particular_stage(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """Scenario: Recording does not require a particular stage.

    Asserted through the persisted stage as well, so that a recording that
    quietly moved the product would be caught rather than read as success.
    """
    registered = await _registered(store)
    await change_stage(store, registered.id, Retired(), confirmed_by=CONFIRMER)

    await record_hazard_categories(store, registered.id, FLAGGED)

    reread = await _reread(new_store, registered.id)
    assert _members(reread) == list(FLAGGED)
    assert reread.stage == Retired()


async def test_the_three_states_are_pairwise_distinguishable_in_storage(
    store: CatalogProductRepository,
    new_store: Callable[[], AbstractAsyncContextManager[CatalogProductRepository]],
) -> None:
    """The requirement's own statement — "SHALL NOT collapse any two of
    them" — asserted over three rows in one database rather than against
    literals.

    This is `tasks.md` 1.3's pairwise assertion at the tier where the
    distinction is actually enforced by the column's nullability
    (`design.md` Decision 1).
    """
    never = await _registered(store)
    clear = await _registered(store)
    flagged = await _registered(store)
    await record_hazard_categories(store, clear.id, EMPTY)
    await record_hazard_categories(store, flagged.id, FLAGGED)

    readings = {
        "never recorded": _reading(await _reread(new_store, never.id)),
        "recorded and empty": _reading(await _reread(new_store, clear.id)),
        "recorded and non-empty": _reading(await _reread(new_store, flagged.id)),
    }
    for left, right in (
        ("never recorded", "recorded and empty"),
        ("never recorded", "recorded and non-empty"),
        ("recorded and empty", "recorded and non-empty"),
    ):
        assert readings[left] != readings[right], (
            f"{left!r} and {right!r} both round-trip as {readings[left]!r}"
        )
