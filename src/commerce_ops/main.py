from __future__ import annotations

from fastapi import FastAPI

from commerce_ops.shared.infrastructure.driving import health, slack

app = FastAPI()
app.include_router(health.router)
app.include_router(slack.router)
