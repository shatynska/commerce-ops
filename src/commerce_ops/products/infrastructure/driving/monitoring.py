"""Driving adapter: the five `product-monitoring` cadence trigger routes.

Implements the `product-monitoring` capability
(`openspec/changes/add-product-agent-daily-digest/specs/product-monitoring/spec.md`).
Each route is guarded by the shared `internal-trigger` mechanism; only
`daily` has real reporting logic today (see design.md's Decisions) -- the
other four call a no-op placeholder use case whose content is planned
separately.

Collaborators (`run_daily_digest`, `run_pending_cadence_report`,
`post_monitoring_message`, `get_session`) are imported by name into this
module's own namespace and referenced as bare globals in each route body,
mirroring `omni_agent/infrastructure/driving/slack.py`'s `answer_question`
pattern -- this is what lets tests substitute fakes via
`monkeypatch.setattr(monitoring, "...", fake)` / `app.dependency_overrides`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from commerce_ops.products.application import (
    run_daily_digest,
    run_pending_cadence_report,
)
from commerce_ops.products.infrastructure.driven.product_repository import (
    ProductRepository,
)
from commerce_ops.products.infrastructure.driven.slack_notifier import (
    post_monitoring_message,
)
from commerce_ops.shared.infrastructure.driven.database import get_session
from commerce_ops.shared.infrastructure.driving.trigger_guard import (
    require_trigger_secret,
)

router = APIRouter()

_logger = logging.getLogger(__name__)


def _format_daily_message(names: Sequence[str]) -> str:
    if not names:
        return "No products are currently being monitored."
    listing = "\n".join(f"- {name}" for name in names)
    return f"Products currently being monitored:\n{listing}"


async def _attempt_post(message: str) -> None:
    try:
        await post_monitoring_message(message)
    except Exception:
        # Delivery failure is logged, not surfaced back through the trigger
        # response -- see product-monitoring's "Report Delivery Failure Is
        # Decoupled From The Trigger" requirement.
        _logger.exception("failed to post a product-monitoring message to Slack")


@router.post("/products/monitoring/daily")
async def daily(
    _guard: None = Depends(require_trigger_secret),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    repository = ProductRepository(session)
    try:
        names = await run_daily_digest(repository)
    except Exception:
        # Distinct from a delivery failure: the endpoint's actual job (the
        # database read) never completed -- see product-monitoring's
        # "Database Read Failure Is Surfaced, Not Treated Like A Delivery
        # Failure" requirement.
        _logger.exception("daily product-monitoring digest could not read the database")
        await _attempt_post("Could not read products from the database.")
        return JSONResponse(status_code=500, content={"status": "database read failed"})

    await _attempt_post(_format_daily_message(names))
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.post("/products/monitoring/weekly")
async def weekly(_guard: None = Depends(require_trigger_secret)) -> JSONResponse:
    run_pending_cadence_report("weekly")
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.post("/products/monitoring/biweekly")
async def biweekly(_guard: None = Depends(require_trigger_secret)) -> JSONResponse:
    run_pending_cadence_report("biweekly")
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.post("/products/monitoring/monthly")
async def monthly(_guard: None = Depends(require_trigger_secret)) -> JSONResponse:
    run_pending_cadence_report("monthly")
    return JSONResponse(status_code=202, content={"status": "accepted"})


@router.post("/products/monitoring/quarterly")
async def quarterly(_guard: None = Depends(require_trigger_secret)) -> JSONResponse:
    run_pending_cadence_report("quarterly")
    return JSONResponse(status_code=202, content={"status": "accepted"})
