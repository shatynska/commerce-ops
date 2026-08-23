"""Driving adapter: how recently each piece of recurring work succeeded.

Implements the `scheduled-jobs` capability's "Run Freshness Is Reportable Over
HTTP"
(`openspec/changes/report-overdue-scheduled-runs/specs/scheduled-jobs/spec.md`).

Served from the HTTP process and derived from recorded state alone. **It never
contacts the worker in any way** -- that process's absence is the condition
this interface exists to make visible, so any implementation that asks the
worker anything fails exactly when it is needed.

Unauthenticated by decision, like `/health`, but unlike `/health` it touches
Postgres on every anonymous request. The response is therefore cached briefly.
The anchor upsert is deliberately **not** cached: it is the only database
access a cache-hit request makes, and so the only way such a request can
discover that the recorded state has become unreadable. See design.md,
"Unauthenticated, with the `/health` analogy stated at its actual strength".
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import time

from fastapi import APIRouter, Response

from commerce_ops.shared.infrastructure.driven.job_history import last_successful_run
from commerce_ops.shared.infrastructure.driven.known_work import (
    first_known_times,
    record_first_known,
)
from commerce_ops.shared.infrastructure.driven.recurring_work import registered_work

__all__ = ["CACHE_SECONDS", "TIMEOUT_SECONDS", "router", "scheduled_runs"]

_logger = logging.getLogger(__name__)

router = APIRouter()

# A few seconds is ample: the underlying state changes hourly at most, and
# this bounds what repeated anonymous requests cost in *evaluation*. It does
# not bound the anchor upsert, which runs on every request -- see the module
# docstring.
CACHE_SECONDS = 5.0

# "Unreachable" is bounded in time, not just in outcome. Without this, a
# database that accepts connections and never answers produces a hanging
# request rather than a prompt 503 -- on the one endpoint whose entire purpose
# is to be polled by something that concludes nothing from a request that
# never returns (tasks.md 5.8a).
TIMEOUT_SECONDS = 5.0

_UNHEALTHY: dict[str, object] = {"status": "unhealthy", "work": []}

# (cached_at, payload, status). The age is compared against CACHE_SECONDS at
# read time rather than an expiry being computed at write time, so changing
# the TTL takes effect on the entry already held instead of only on the next
# one written.
_cache: tuple[float, dict[str, object], int] | None = None


def _entry(
    identifier: str,
    last_success: datetime.datetime | None,
    tolerance: datetime.timedelta,
    overdue: bool,
) -> dict[str, object]:
    return {
        "id": identifier,
        # `null` is how "never succeeded" is expressed -- not a sentinel
        # string a checker would have to know about.
        "last_success": (
            last_success.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")
            if last_success is not None
            else None
        ),
        "tolerance_seconds": int(tolerance.total_seconds()),
        "overdue": overdue,
    }


async def _evaluate() -> tuple[dict[str, object], int]:
    work = registered_work()
    anchors = await first_known_times()
    now = datetime.datetime.now(datetime.UTC)

    entries: list[dict[str, object]] = []
    for identifier in sorted(work):
        tolerance = work[identifier].tolerance
        last_success = await last_successful_run(identifier)
        reference = last_success or anchors.get(identifier)
        overdue = reference is not None and now - reference > tolerance
        entries.append(_entry(identifier, last_success, tolerance, overdue))

    unhealthy = any(entry["overdue"] for entry in entries)
    payload: dict[str, object] = {
        "status": "unhealthy" if unhealthy else "ok",
        "work": entries,
    }
    # 503 is what an off-the-shelf uptime monitor already treats as down,
    # which is the entire point of signalling by status rather than in prose.
    return payload, 503 if unhealthy else 200


@router.get("/health/scheduled-runs")
async def scheduled_runs(response: Response) -> dict[str, object]:
    """Report per-work freshness, and signal unhealthy by HTTP status."""
    global _cache

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            # Before evaluating, and before consulting the cache: a worker
            # that never starts would otherwise leave every piece of work
            # without an anchor, so nothing could be computed as overdue and
            # this endpoint would report healthy forever (tasks.md 3.2a).
            await record_first_known(sorted(registered_work()))

            # `time.monotonic()`, not the running loop's clock: the loop's
            # time is relative to that loop, and a process serving requests
            # across more than one loop would be comparing two unrelated
            # origins -- an age of "half a second" computed from numbers that
            # never shared a zero.
            now = time.monotonic()
            if _cache is not None and now - _cache[0] < CACHE_SECONDS:
                _, cached_payload, cached_status = _cache
                response.status_code = cached_status
                return cached_payload

            payload, status = await _evaluate()
    except Exception:
        # Any fault that prevents reading recorded state: a refused or
        # never-answering connection, or an absent or malformed connection
        # setting, which `database-session` raises at the point of use rather
        # than by expiry. Answering unhealthy is the point -- serving a stale
        # healthy answer is the one outcome that must not happen, so nothing
        # is read from the cache here either (tasks.md 5.8, 5.8b).
        _logger.exception("scheduled-run freshness could not be determined")
        response.status_code = 503
        return dict(_UNHEALTHY)

    # Only successful reads enter the cache, so an outage cannot be masked by
    # a previously computed healthy answer. A non-positive TTL means caching is
    # off, so nothing is stored either -- storing an entry that can never be
    # read back is how a "cache disabled" setting still leaves one behind.
    if CACHE_SECONDS > 0:
        _cache = (now, payload, status)
    response.status_code = status
    return payload
