from __future__ import annotations

from fastapi import FastAPI

from commerce_ops.omni_agent.infrastructure.driving import slack as omni_agent_slack
from commerce_ops.products.infrastructure.driving import (
    monitoring as products_monitoring,
)
from commerce_ops.shared.infrastructure.driving import health
from commerce_ops.shared.infrastructure.logging import configure_logging

# After the imports, before the routers: closing the window over the
# adapter modules' own import-time records would require this call above
# the imports, which ruff's E402 forbids -- a deliberate trade, not an
# oversight (design.md, "Call it at module import in main.py").
configure_logging()

app = FastAPI()
app.include_router(health.router)
app.include_router(omni_agent_slack.router)
app.include_router(products_monitoring.router)
