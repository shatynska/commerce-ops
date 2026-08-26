"""Driving adapter: the daily launch briefing, as scheduled work.

Implements the `briefing` capability's *The daily briefing runs on a
schedule*, *Delivery failure is decoupled from the run* and *A failure to
assemble is surfaced, not treated like a delivery failure*.

This takes the retired daily digest's schedule slot and tolerance: the
daily message is now the briefing, and two daily messages would dilute
the silent-when-clean discipline the briefing exists to hold.

Its two readers arrive as module-level injection points rather than being
constructed here. Briefing's infrastructure may not import launch's or
catalog's, so `worker.py` — which sits outside `.importlinter`'s
containers — composes them from those modules' public surfaces and closes
each over its own session, exactly as it does for
`clickup_sync_job.read_product`.

Collaborators are referenced as bare module globals in the job body,
keeping `daily_digest_job.py`'s pattern — which is what lets tests
substitute fakes with `monkeypatch.setattr`.
"""

from __future__ import annotations

import datetime
import logging

from procrastinate import RetryStrategy, job_context

from commerce_ops.briefing.application import (
    LaunchReports,
    LaunchReportsUnavailableError,
    ProductReader,
    run_daily_briefing,
)
from commerce_ops.briefing.infrastructure.driven.slack_notifier import (
    post_monitoring_message,
)
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "daily_briefing",
    "post_monitoring_message",
    "read_launch_reports",
    "read_product",
    "run_daily_briefing",
]

_logger = logging.getLogger(__name__)

TASK_NAME = "briefing.daily"

# The retired digest's slot, inherited: 06:00 UTC. The runner accepts no
# timezone parameter, so this is not a choice the deployment can get wrong.
DAILY_SCHEDULE = "0 6 * * *"

# Longer than the 24-hour interval, so a run that is merely delayed — or
# still in flight — is never reported as overdue. Declared beside the
# schedule it is measured against, because they are one decision.
DAILY_TOLERANCE = datetime.timedelta(hours=30)

# The digest's figures, unchanged: the failure mode this retries is a
# transient database problem, and it is the same database.
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 60
BACKOFF_EXPONENT_SECONDS = 4

RETRY_STRATEGY = RetryStrategy(
    max_attempts=MAX_ATTEMPTS,
    wait=BACKOFF_BASE_SECONDS,
    exponential_wait=BACKOFF_EXPONENT_SECONDS,
)

# The one audience this slice delivers to: the configured monitoring
# channel, which the notifier resolves for itself. Named rather than left
# implicit because `assemble_daily_briefing` takes the audience as a
# parameter from day one — the shape `access` needs in slice 6.
AUDIENCE = "monitoring-channel"

# Injected by `worker.py` after `register_all()`, never at import and never
# as a job argument: the runner passes only serializable values to a job,
# and briefing may not import the modules these read from. They are `None`
# in the HTTP process, which registers the same job module but never runs
# it.
read_launch_reports: LaunchReports | None = None
read_product: ProductReader | None = None


class _ModuleNotifier:
    """Adapts this module's `post_monitoring_message` global to the
    notifier port.

    Resolves the global at call time rather than capturing it, so a test
    that patches the module attribute is what the briefing posts through.
    """

    async def post_monitoring_message(self, message: str) -> None:
        await post_monitoring_message(message)


async def _attempt_post(message: str) -> None:
    try:
        await post_monitoring_message(message)
    except Exception:
        # Logged and no further: a delivery failure neither fails the run
        # nor schedules a retry.
        _logger.exception("failed to post a launch-briefing message to Slack")


def _is_final_attempt(
    context: job_context.JobContext, exception: BaseException
) -> bool:
    """Whether the retry strategy will not retry after this attempt.

    Asked of the strategy itself rather than recomputed from
    `MAX_ATTEMPTS`: the strategy is the single place the maximum is
    declared, and duplicating its arithmetic is how the message and the
    retry count drift apart.
    """
    return (
        RETRY_STRATEGY.get_retry_decision(exception=exception, job=context.job) is None
    )


@register_scheduled(
    name=TASK_NAME,
    schedule=DAILY_SCHEDULE,
    tolerance=DAILY_TOLERANCE,
    pass_context=True,
    retry=RETRY_STRATEGY,
)
async def daily_briefing(context: job_context.JobContext, timestamp: int) -> None:
    """Assemble the day's launch briefing and deliver it if there is one.

    Only an *assembly* failure reaches this handler: `run_daily_briefing`
    swallows a delivery failure itself, so a run that got as far as a
    briefing is a successful run whether or not Slack accepted it. A
    clean day is likewise a success that posts nothing.
    """
    if read_launch_reports is None or read_product is None:
        # Fails the run deliberately: an uninjected reader means this
        # process was never composed to run the briefing, and reporting
        # success would make the silence indistinguishable from a clean
        # day.
        raise RuntimeError(
            "the daily briefing has no launch-reports reader or product "
            "reader injected; it cannot be assembled"
        )

    try:
        await run_daily_briefing(
            read_launch_reports=read_launch_reports,
            read_product=read_product,
            notifier=_ModuleNotifier(),
            audience=AUDIENCE,
            as_of=datetime.datetime.now(datetime.UTC).date(),
        )
    except LaunchReportsUnavailableError as unavailable:
        # Ahead of the assembly-failure branch on purpose: a source that
        # cannot answer yet is an expected stage of a deployment being set
        # up, not a failure to read data, and retrying cannot resolve it.
        # So the run succeeds and is not retried — and a message goes out
        # naming what is still missing, because the alternative is a clean
        # briefing, which posts nothing and reads as an all-clear.
        #
        # Posted on every run while the condition lasts, deliberately: the
        # existing once-per-outage hook is retry exhaustion, which a
        # succeeded run never reaches, and no other state is kept to tell a
        # continuing condition from a new one.
        _logger.info(
            "the launch source cannot supply reports; briefing stood down",
            extra={"identifiers": list(unavailable.identifiers)},
        )
        await _attempt_post(
            "Could not assemble the daily launch briefing: the launch "
            "source cannot supply reports"
            + (
                f" ({', '.join(unavailable.identifiers)})"
                if unavailable.identifiers
                else ""
            )
            + "."
        )
        return
    except Exception as exc:
        # Distinct from a delivery failure: the briefing was never
        # assembled, so the run is recorded as failed and the runner
        # retries it.
        _logger.exception("the daily launch briefing could not be assembled")
        if _is_final_attempt(context, exc):
            # Only on the attempt that will not be retried, so one outage
            # produces one message rather than one per attempt.
            await _attempt_post("Could not assemble the daily launch briefing.")
        raise
