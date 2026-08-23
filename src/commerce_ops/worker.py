"""Entry point: the process that runs this application's scheduled work.

Implements the `scheduled-jobs` capability
(`openspec/changes/replace-cron-with-job-runner/specs/scheduled-jobs/spec.md`).

Separate from the HTTP process, not a thread inside it: the spec requires a
worker failure not to stop HTTP being served, a long-running job would
otherwise compete with request handling in one event loop, and `app` can be
restarted or rolled without interrupting a job mid-flight. See design.md,
"The worker is a separate service from the same image".
"""

from __future__ import annotations

import asyncio
import logging

from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driven.job_runner import app
from commerce_ops.shared.infrastructure.logging import configure_logging

# Before anything else, so this process's own startup records survive --
# `application-logging` binds every entrypoint, and a worker's value is
# what it reports.
configure_logging()

# Imported for the import's own sake: importing a module that holds a job
# definition is what registers its schedule. A worker that registers nothing
# runs perfectly healthy and schedules nothing, and with the container's
# healthcheck disabled there would be no signal at all. Task 6.4a guards
# this line specifically, because an unused-looking import is exactly the
# kind a later cleanup removes.
from commerce_ops.products.infrastructure.driving import (
    daily_digest_job as _daily_digest_job,
)

__all__ = ["main"]

_REGISTERED_JOB_MODULES = (_daily_digest_job,)

# Named explicitly, NOT `__name__`. Compose runs this module as
# `python -m commerce_ops.worker`, where `__name__` is `"__main__"` -- a
# logger outside the `commerce_ops` tree, which inherits root's WARNING and
# silently drops every INFO record below. Verified against a running
# container: with `__name__`, this process logged nothing for its whole life.
_logger = logging.getLogger("commerce_ops.worker")


async def _run() -> None:
    # The runner's own records sit under `procrastinate`, which
    # `application-logging` deliberately holds at WARNING -- an unconfigured
    # dependency stays quiet. So this process says for itself that it started,
    # what it will run, and that it stopped; without these three records a
    # worker that registered no schedule looks exactly like one that did, and
    # its healthcheck is disabled precisely because nothing else can tell them
    # apart from outside.
    schedules = sorted(
        f"{entry.task.name} ({entry.cron})"
        for entry in app.periodic_registry.periodic_tasks.values()
    )
    _logger.info(
        "scheduled-work worker starting; %d schedule(s) registered: %s",
        len(schedules),
        ", ".join(schedules) or "none",
    )
    try:
        async with app.open_async():
            await app.run_worker_async()
    finally:
        _logger.info("scheduled-work worker stopping; closing the connection pool")
        # The worker holds the process-wide session provider's engine through
        # every job it ran, so it closes the pool before exiting -- the same
        # obligation `database-session` places on any process that obtained a
        # session, not only on the HTTP one.
        await dispose_engine()
        _logger.info("scheduled-work worker stopped")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
