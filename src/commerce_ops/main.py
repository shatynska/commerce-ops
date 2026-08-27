from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.access.application import Person, list_people, verify_admin_session
from commerce_ops.access.infrastructure.driven.roster_repository import (
    PostgresRoster,
)
from commerce_ops.access.infrastructure.driving import admin_link as access_admin_link
from commerce_ops.access.infrastructure.driving import (
    roster_admin as access_roster_admin,
)
from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.domain.product import Product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.infrastructure.driving import (
    automation_confirmation as launch_automation_confirmation,
)
from commerce_ops.launch.infrastructure.driving import (
    clickup_webhook as launch_clickup_webhook,
)
from commerce_ops.launch.infrastructure.driving import (
    launch_admin as launch_tracking_admin,
)
from commerce_ops.launch.infrastructure.driving import (
    playbook_admin as launch_playbook_admin,
)
from commerce_ops.launch.infrastructure.driving import (
    slack_entry as launch_slack_entry,
)
from commerce_ops.omni_agent.infrastructure.driving import slack as omni_agent_slack
from commerce_ops.registrations import register_all
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.infrastructure.driven.database import dispose_engine, session
from commerce_ops.shared.infrastructure.driving import (
    admin_assets as shared_admin_assets,
)
from commerce_ops.shared.infrastructure.driving import health, scheduled_runs
from commerce_ops.shared.infrastructure.logging import configure_logging

# After the imports, before the routers: closing the window over the
# adapter modules' own import-time records would require this call above
# the imports, which ruff's E402 forbids -- a deliberate trade, not an
# oversight (design.md, "Call it at module import in main.py").
configure_logging()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Nothing here reads the database. The first admin is seeded by
    # `commerce_ops.seed_admin`, a step of its own between the migration
    # and the server in the container's start chain: seeding here would
    # make the serving process open a connection before its first request,
    # which `database-session` requires not to happen.
    yield
    # Disposes the engine if one was created, tolerating one that never
    # was -- see `centralize-database-session`'s design.md, "Disposal
    # happens in a FastAPI lifespan, and tolerates an engine that was never
    # created".
    await dispose_engine()


# The same one list the worker calls, so both processes hold the same
# registry. This process never runs the work; it reports on it, and it can
# only report on what it knows about (tasks.md 1.3).
register_all()

# The roster replaced the repo-owned principals file
# (`move-principals-to-roster`), so there is no longer a document to
# validate at import: the store only ever holds what the roster's own
# validated writes produced. Constructing the collaborator touches no
# database — the connection is opened per operation, no earlier than the
# first one — so importing this module still requires no configuration.
roster = PostgresRoster()

app = FastAPI(lifespan=_lifespan)
app.include_router(health.router)
app.include_router(scheduled_runs.router)
app.include_router(omni_agent_slack.router)
# Mounted without a prefix, as the Slack adapter is: the router declares
# its own full path.
app.include_router(launch_clickup_webhook.router)
app.include_router(launch_slack_entry.router)
app.include_router(access_admin_link.router)
app.include_router(launch_playbook_admin.router)
app.include_router(access_roster_admin.router)
app.include_router(launch_tracking_admin.router)
app.include_router(shared_admin_assets.router)


async def _register_catalog_product(
    db_session: AsyncSession,
    *,
    sku: Sku,
    marketplace_id: MarketplaceId,
    name: str,
    asin: Asin | None,
) -> ProductId:
    """Registers a product on the launch-entry adapter's own session.

    Lives here, in the composition root, because `.importlinter`'s
    `products-infrastructure-boundary` bars the launch module from
    constructing catalog's store -- exactly as `worker.py` supplies
    `clickup_sync_job.read_product` for the same reason. Building the store
    on the *caller's* session is what puts the catalog write and the launch
    write in one transaction (design.md Decision 3).

    Returns the identifier rather than the aggregate, so the adapter never
    handles a catalog domain object.
    """
    product = await register_product(
        CatalogProductRepository(db_session),
        sku=sku,
        marketplace_id=marketplace_id,
        name=name,
        asin=asin,
    )
    return product.id


# Injected after the routers, never at import of the adapter itself: the
# adapter resolves this at call time, so the assignment need only happen
# before the first request.
launch_slack_entry.register_catalog_product = _register_catalog_product

# The admin page's guard collaborators, injected the same way: the launch
# module may not import the access module's infrastructure, so the
# composition root hands it the startup-validated directory and the same
# session store the exchange route writes into.
launch_playbook_admin.roster = roster
launch_playbook_admin.admin_sessions = access_admin_link.admin_sessions
access_roster_admin.roster = roster
access_roster_admin.admin_sessions = access_admin_link.admin_sessions
launch_tracking_admin.roster = roster
launch_tracking_admin.admin_sessions = access_admin_link.admin_sessions


class _RequestScopedCatalog:
    """The catalog reads the launch-tracking pages make, each on its own
    session.

    Lives here for the reason `_register_catalog_product` below does:
    `.importlinter` permits `launch.infrastructure` the catalog's public
    surface and forbids it the catalog's infrastructure, so only the
    composition root can build the store those reads run against. The
    page holds the port; the root holds the repository.

    Only `list` and `get_by_id` — the two reads the pages make. A page
    that could write to the catalog would be a page this one is not.
    """

    async def list(self) -> Sequence[Product]:
        async with session() as db_session:
            return await CatalogProductRepository(db_session).list()

    async def get_by_id(self, product_id: ProductId) -> Product | None:
        async with session() as db_session:
            return await CatalogProductRepository(db_session).get_by_id(product_id)


launch_tracking_admin.catalog = _RequestScopedCatalog()


class _RosterReader:
    """Reads the roster for the automated-result decision controls.

    A **reader**, not the store the admin pages get. Those hold one
    collaborator serving two contracts -- `verify_admin_session` is typed
    `RosterStore` and genuinely needs one -- so they take the store and
    adapt it internally. This adapter has no second contract: resolving
    the deciding Slack identity is the only thing it wants a roster for,
    so it takes the reader and nothing else.

    The store was handed over here unadapted once. `PostgresRoster`
    answers `load()`/`save()`, the decision path reads `list_people()`,
    and the probe that missed resolved it to "no such person" -- so every
    accept and reject, by every identity, was refused as though the
    roster did not carry the decider.

    Near-identical to `worker.py._RosterReader`, deliberately: the two
    composition roots are separate processes, neither may import the
    other, and each is the only place in its own process permitted to
    construct `access`'s store. A shared helper would need to live
    outside both `.importlinter` containers, which is what a composition
    root *is*.
    """

    async def list_people(self) -> tuple[Person, ...]:
        # `roster` is resolved here, per call, rather than captured at
        # construction. Binding it in `__init__` would seal the store in
        # before any test could reach it, and the one test that proves
        # this wiring works substitutes exactly there -- see
        # `tests/unit/launch/infrastructure/driving/test_automated_decision_wiring.py`.
        # (`worker.py`'s reader differs: it constructs a fresh
        # `PostgresRoster()` per call and so has no global to resolve.)
        return await list_people(roster=roster)


# The accept/reject controls on an automated result resolve the deciding
# Slack identity through the roster. `launch` may not construct access's
# store, so the root supplies the reader over it.
launch_automation_confirmation.read_people = _RosterReader()


async def _verify_admin_session(*, session_id: str) -> str | None:
    """The shared asset route's guard, injected the same way and for the
    same reason the two admin pages' collaborators are: `shared` may not
    import `access`, so it cannot resolve a session itself. It is handed a
    callable that either answers a principal or answers nothing, and knows
    nothing else about what an admin is."""
    return await verify_admin_session(
        roster,
        access_admin_link.admin_sessions,
        session_id=session_id,
        now=datetime.now(UTC),
    )


shared_admin_assets.verify = _verify_admin_session
