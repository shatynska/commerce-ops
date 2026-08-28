"""The repeat-backoff record against a real Postgres.

`cool-off-a-repeatedly-blocked-step`'s unit tests drive the *pass* over an
in-memory double, which is the right level for every scenario the delta
spec states — each is stated over a pass. One obligation is not
observable there, and its `test-manifest.md` says so explicitly:

> `tasks.md` 3.1's store-side obligation — noting a repeat against a
> different outcome kind clears the reported stamp. Deliberately **not**
> modelled by the fake … The accessor's own behaviour is an integration
> question against a table that does not exist yet.

The table exists now, and the obligation is carried by an
`ON CONFLICT … DO UPDATE` whose `CASE` decides whether the reported stamp
survives. Nothing else exercises that SQL, and getting it wrong is
silent: the stamp would simply persist, and a step that moved and got
stuck again would never be reported a second time.

So this file tests the accessor, not the pass. Written after the
implementation rather than before it — recorded here as the deviation it
is (AGENTS.md — test design before implementation), because what it
covers only became testable once the shape it pins was chosen.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    GateOpening,
    InProgress,
    LaunchPlaybook,
)
from commerce_ops.launch.infrastructure.driven.automated_step_backoff import (
    AutomatedStepBackoffRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku

pytestmark = pytest.mark.anyio

MARKETPLACE = MarketplaceId("ATVPDKIKX0DER")
STEP = "listing.sub-category"

FIRST = datetime(2027, 4, 1, 9, 0, tzinfo=UTC)
LATER = FIRST + timedelta(hours=1)
LATER_STILL = FIRST + timedelta(hours=2)

GATES = (
    "commit",
    "order",
    "listable",
    "stock-ready",
    "live",
    "ignition",
    "phase-one-complete",
    "graduated",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture()
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    made = create_async_engine(database_url)
    try:
        yield made
    finally:
        await made.dispose()


@pytest.fixture()
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


#: The four the playbook's coherence rules require to be confirmed.
CONFIRMATION_GATES = frozenset({"commit", "order", "phase-one-complete", "graduated"})


def _playbook() -> LaunchPlaybook:
    return LaunchPlaybook(
        version="backoff-live-v1",
        gates=tuple(
            Gate(
                identifier=name,
                position=index,
                opening=(
                    GateOpening.REQUIRES_CONFIRMATION
                    if name in CONFIRMATION_GATES
                    else GateOpening.AUTOMATIC
                ),
            )
            for index, name in enumerate(GATES, start=1)
        ),
        steps=(),
    )


@pytest.fixture()
def launched_product(
    sessions: async_sessionmaker[AsyncSession],
) -> Callable[[], Awaitable[ProductId]]:
    """A registered product with a launch — the backoff row's foreign key
    is the launch position, not the product."""

    async def _make() -> ProductId:
        async with sessions() as session:
            product = await register_product(
                CatalogProductRepository(session),
                sku=Sku(f"BKF-{uuid.uuid4().hex[:10].upper()}"),
                marketplace_id=MARKETPLACE,
                name="Backoff Test Widget",
            )
        async with sessions() as session:
            from commerce_ops.launch.domain.launch_run import Launch

            launch, _ = Launch.start(product_id=product.id, playbook=_playbook())
            await LaunchRepository(session).save(launch)
        return product.id

    return _make


async def test_an_absent_row_reads_as_nothing(
    sessions: async_sessionmaker[AsyncSession],
    launched_product: Callable[[], Awaitable[ProductId]],
) -> None:
    product_id = await launched_product()
    async with sessions() as session:
        assert (
            await AutomatedStepBackoffRepository(session).read(product_id, STEP) is None
        )


async def test_a_noted_repeat_round_trips(
    sessions: async_sessionmaker[AsyncSession],
    launched_product: Callable[[], Awaitable[ProductId]],
) -> None:
    """The kind is stored as a kind and read back as the outcome type, so
    the pass compares it against a recorded outcome without knowing this
    module's stored spellings."""
    product_id = await launched_product()
    async with sessions() as session:
        await AutomatedStepBackoffRepository(session).note(
            product_id, STEP, Blocked("no confident node"), FIRST
        )
    async with sessions() as session:
        row = await AutomatedStepBackoffRepository(session).read(product_id, STEP)

    assert row is not None
    # The *kind*, not the outcome: a reason never reaches the record.
    assert row.noted_kind is Blocked
    assert row.noted_at == FIRST
    assert row.reported_at is None


async def test_a_repeat_of_the_same_kind_keeps_the_reported_stamp(
    sessions: async_sessionmaker[AsyncSession],
    launched_product: Callable[[], Awaitable[ProductId]],
) -> None:
    """The step is still stuck on the same thing, and has already been
    reported: a second message would be the wall of identical messages the
    report-once rule exists to prevent.

    The two blocks are worded differently on purpose — that is the case
    the whole change turns on, and a store comparing outcomes rather than
    kinds would clear the stamp here.
    """
    product_id = await launched_product()
    repository = AutomatedStepBackoffRepository
    async with sessions() as session:
        await repository(session).note(
            product_id, STEP, Blocked("I cannot confidently determine"), FIRST
        )
    async with sessions() as session:
        await repository(session).mark_reported(product_id, STEP, FIRST)
    async with sessions() as session:
        await repository(session).note(
            product_id, STEP, Blocked("I am unable to determine"), LATER
        )
    async with sessions() as session:
        row = await repository(session).read(product_id, STEP)

    assert row is not None
    assert row.noted_at == LATER, "the cool-off did not re-anchor to the later repeat"
    assert row.reported_at == FIRST, (
        "a differently worded block of the same kind cleared the reported "
        "stamp; the step is still stuck on the same thing and must not be "
        "reported twice"
    )


async def test_a_repeat_of_a_different_kind_clears_the_reported_stamp(
    sessions: async_sessionmaker[AsyncSession],
    launched_product: Callable[[], Awaitable[ProductId]],
) -> None:
    """The obligation nothing else covers. A step that moved and got stuck
    again is owed a fresh report, and a plain `SET noted_kind=…,
    noted_at=…` would leave the old stamp and silence it for good."""
    product_id = await launched_product()
    repository = AutomatedStepBackoffRepository
    async with sessions() as session:
        await repository(session).note(product_id, STEP, Blocked("stuck"), FIRST)
    async with sessions() as session:
        await repository(session).mark_reported(product_id, STEP, FIRST)
    async with sessions() as session:
        await repository(session).note(product_id, STEP, InProgress, LATER_STILL)
    async with sessions() as session:
        row = await repository(session).read(product_id, STEP)

    assert row is not None
    assert row.noted_kind is InProgress
    assert row.noted_at == LATER_STILL
    assert row.reported_at is None, (
        "the reported stamp survived a repeat against a different outcome "
        "kind, so a step that moved and got stuck again would never be "
        "reported a second time"
    )


async def test_removing_the_launch_removes_its_backoff_rows(
    sessions: async_sessionmaker[AsyncSession],
    launched_product: Callable[[], Awaitable[ProductId]],
) -> None:
    product_id = await launched_product()
    survivor_id = await launched_product()
    async with sessions() as session:
        await AutomatedStepBackoffRepository(session).note(
            product_id, STEP, Blocked("stuck"), FIRST
        )
    async with sessions() as session:
        await AutomatedStepBackoffRepository(session).note(
            survivor_id, STEP, Blocked("stuck"), FIRST
        )

    async with sessions() as session:
        await session.execute(
            text("DELETE FROM launch_positions WHERE product_id = CAST(:pid AS uuid)"),
            {"pid": product_id.value},
        )
        await session.commit()

    async with sessions() as session:
        repository = AutomatedStepBackoffRepository(session)
        assert await repository.read(product_id, STEP) is None
        # The cascade is keyed by launch, not a table-wide sweep.
        assert await repository.read(survivor_id, STEP) is not None
