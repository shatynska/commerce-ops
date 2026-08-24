from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.access.application import PrincipalsDirectory
from commerce_ops.access.infrastructure.driven.principals_loader import (
    load_shipped_principals,
)
from commerce_ops.access.infrastructure.driving import admin_link as access_admin_link
from commerce_ops.catalog.application import register_product
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.infrastructure.driving import (
    clickup_webhook as launch_clickup_webhook,
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
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driving import health, scheduled_runs
from commerce_ops.shared.infrastructure.logging import configure_logging

# After the imports, before the routers: closing the window over the
# adapter modules' own import-time records would require this call above
# the imports, which ruff's E402 forbids -- a deliberate trade, not an
# oversight (design.md, "Call it at module import in main.py").
configure_logging()


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
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

# Eagerly, before this process serves anything: `access-scope` requires a
# malformed principals directory to stop the process from starting to serve
# rather than surface on an individual asker's resolution, and this is the
# process that will serve scope resolution.
#
# Not in `preflight.py`, though that is where a deploy-time check would
# otherwise belong: `runtime-configuration` requires the configuration check
# to read only the process environment and its outcome to depend only on the
# declared variables, which a repo-owned file's faults would break. The file
# needs no configuration to read, so loading it here leaves
# `runtime-configuration`'s "importing and starting require no configuration"
# guarantee intact.
principals: PrincipalsDirectory = load_shipped_principals()

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
launch_playbook_admin.directory = principals
launch_playbook_admin.admin_sessions = access_admin_link.admin_sessions
