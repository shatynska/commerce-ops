from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from commerce_ops.omni_agent.infrastructure.driving import slack as omni_agent_slack
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driving import health
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


app = FastAPI(lifespan=_lifespan)
app.include_router(health.router)
app.include_router(omni_agent_slack.router)
