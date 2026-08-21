from __future__ import annotations

from fastapi import FastAPI

from commerce_ops.omni_agent.infrastructure.driving import slack as omni_agent_slack
from commerce_ops.shared.infrastructure.driving import health

app = FastAPI()
app.include_router(health.router)
app.include_router(omni_agent_slack.router)
