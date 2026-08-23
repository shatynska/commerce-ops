"""Driving adapter: the daily product-monitoring cadence, as scheduled work.

Implements the `product-monitoring` and `scheduled-jobs` capabilities
(`openspec/changes/replace-cron-with-job-runner/specs/`).

This takes the place of `monitoring.py`'s five HTTP routes. A scheduled job
is a *driving* adapter -- it calls into the application layer exactly as the
retired route did -- so it lives in `products` rather than in `shared`, where
it may freely reach this module's own repository and notifier without
`shared` ever importing a business module. See design.md, "The daily job
definition lives in `products`, not in `shared`".

Collaborators (`run_daily_digest`, `post_monitoring_message`, `session`) are
imported by name into this module's namespace and referenced as bare globals
in the job body, keeping `monitoring.py`'s own pattern -- which is what lets
tests substitute fakes with `monkeypatch.setattr`.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from procrastinate import RetryStrategy, job_context

from commerce_ops.products.application import run_daily_digest
from commerce_ops.products.infrastructure.driven.product_repository import (
    ProductRepository,
)
from commerce_ops.products.infrastructure.driven.slack_notifier import (
    post_monitoring_message,
)
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driven.job_runner import app

__all__ = [
    "daily_digest",
    "post_monitoring_message",
    "run_daily_digest",
    "session",
]

_logger = logging.getLogger(__name__)

# 06:00, matching the crontab the retired `cron` container ran. Interpreted in
# UTC -- the runner accepts no timezone parameter, so this is not a choice the
# deployment can get wrong. See design.md, "The schedule is interpreted in UTC".
DAILY_SCHEDULE = "0 6 * * *"

# Exponential backoff, small maximum. The failure mode is a transient database
# or network problem; still failing after several spaced attempts means the
# problem is not transient. Initial figures, recorded to be revisited with a
# week of real behaviour (design.md, Open Questions).
#
# tasks.md 2.6 records "3 attempts, 60s base". The runner computes its delay
# as `wait + linear_wait * attempts + exponential_wait ** (attempts + 1)`, so
# passing 60 as `exponential_wait` would mean 60s, then an hour, then 2.5
# DAYS -- a third retry landing after two further daily runs had come and
# gone, and a failure message arriving days after the outage. The 60s base is
# therefore the floor (`wait`), with a bounded exponential term on top:
# 64s, 76s, 124s. Successive retries still wait longer, which is what the
# `scheduled-jobs` requirement asks.
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 60
BACKOFF_EXPONENT_SECONDS = 4

RETRY_STRATEGY = RetryStrategy(
    max_attempts=MAX_ATTEMPTS,
    wait=BACKOFF_BASE_SECONDS,
    exponential_wait=BACKOFF_EXPONENT_SECONDS,
)


def _format_daily_message(names: Sequence[str]) -> str:
    if not names:
        return "No products are currently being monitored."
    listing = "\n".join(f"- {name}" for name in names)
    return f"Products currently being monitored:\n{listing}"


async def _attempt_post(message: str) -> None:
    try:
        await post_monitoring_message(message)
    except Exception:
        # Delivery failure is logged and goes no further: it neither fails the
        # run nor schedules a retry. A delivery failure does not establish that
        # nothing was delivered, so retrying would trade a possible duplicate
        # report for one that is stale by the time it lands -- see
        # product-monitoring's "Report Delivery Failure Is Decoupled From The
        # Trigger".
        _logger.exception("failed to post a product-monitoring message to Slack")


def _is_final_attempt(
    context: job_context.JobContext, exception: BaseException
) -> bool:
    """Whether the retry strategy will not retry after this attempt.

    Asked of the strategy itself rather than recomputed from `MAX_ATTEMPTS`.
    The strategy is the single place the maximum is declared (tasks.md 2.7a),
    and its own arithmetic decides what "final" means -- duplicating that
    comparison here is how the message and the retry count drift apart.
    """
    return (
        RETRY_STRATEGY.get_retry_decision(exception=exception, job=context.job) is None
    )


@app.periodic(cron=DAILY_SCHEDULE)
@app.task(name="products.monitoring.daily", pass_context=True, retry=RETRY_STRATEGY)
async def daily_digest(context: job_context.JobContext, timestamp: int) -> None:
    """Post the daily digest of monitored product names."""
    try:
        async with session() as db_session:
            names = await run_daily_digest(ProductRepository(db_session))
    except Exception as exc:
        # Distinct from a delivery failure: the run's actual job -- the
        # database read -- never completed, so the run is recorded as failed
        # and the runner retries it.
        _logger.exception("daily product-monitoring digest could not read the database")
        if _is_final_attempt(context, exc):
            # Only on the attempt that will not be retried. Posting on every
            # attempt turns one outage into three identical Slack messages --
            # the change that exists to make failure visible making it noise
            # instead. See product-monitoring's "An intermediate failed
            # attempt does not post".
            await _attempt_post("Could not read products from the database.")
        raise

    await _attempt_post(_format_daily_message(names))
