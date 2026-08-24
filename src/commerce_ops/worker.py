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
from datetime import date

from commerce_ops.catalog.domain.product import Product
from commerce_ops.launch.application import LaunchReport
from commerce_ops.shared.domain.access_scope import AccessScope
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import dispose_engine
from commerce_ops.shared.infrastructure.driven.job_runner import app
from commerce_ops.shared.infrastructure.logging import configure_logging

# Before anything else, so this process's own startup records survive --
# `application-logging` binds every entrypoint, and a worker's value is
# what it reports.
configure_logging()

# The one list of job modules lives in `registrations.py`, called by this
# root and by `main.py` alike. This process must not keep its own list: two
# lists is exactly the divergence that leaves the freshness endpoint
# reporting on a different set of work than the worker actually runs
# (tasks.md 1.3a).
from commerce_ops.briefing.infrastructure.driven import slack_notifier
from commerce_ops.briefing.infrastructure.driving import daily_briefing_job
from commerce_ops.catalog.application import get_product_by_id
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.application import read_launches
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.shipped_playbooks import (
    ShippedPlaybooks,
)
from commerce_ops.launch.infrastructure.driving import clickup_sync_job
from commerce_ops.registrations import register_all
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driving import overdue_check

__all__ = ["main"]

register_all()

# Injected after `register_all()`, as a separate step. `register_all()` itself
# stays notifier-free because `main.py` calls the same function and has no
# notifier to give; and the notifier is never a job argument, since the runner
# passes only serializable values to a job. This module sits outside
# `.importlinter`'s containers, which is what makes naming both sides legal
# (tasks.md 4.2).
overdue_check.notifier = slack_notifier

# Scheduled work is not a person: the daily briefing addresses the whole
# team and the ClickUp sync names a list for every launch, so neither
# impersonates an asker whose visibility could be narrower. Named once here,
# at the composition root, so that every internal read says which scope it
# runs under rather than defaulting into one.
_INTERNAL_SCOPE = AccessScope.unrestricted()


async def _read_catalog_product(product_id: ProductId) -> Product | None:
    """Name a launch's ClickUp list after its catalog product.

    Injected here for the same reason the notifier is: the launch module
    may not import the catalog's own store, and this module sits outside
    `.importlinter`'s containers, which is what makes naming both sides
    legal. It opens its own session — the pass may run for many launches,
    and this read is not part of their transaction.
    """
    async with session() as db_session:
        return await get_product_by_id(
            CatalogProductRepository(db_session), product_id, scope=_INTERNAL_SCOPE
        )


clickup_sync_job.read_product = _read_catalog_product


async def _read_launch_reports(*, as_of: date) -> tuple[LaunchReport, ...]:
    """Every launch, reported as of `as_of`, for the daily briefing.

    Closed over its own session here for the same reason the ClickUp
    reader is: briefing may not import launch's repository, and only this
    module — outside `.importlinter`'s containers — may name both sides.
    """
    async with session() as db_session:
        return await read_launches(
            LaunchRepository(db_session),
            ShippedPlaybooks(),
            as_of=as_of,
            scope=_INTERNAL_SCOPE,
        )


daily_briefing_job.read_launch_reports = _read_launch_reports
# The briefing names each item's product, and reads the stage stamp that
# decides whether a launch is still worth briefing — both from catalog's
# public surface, never from its store.
daily_briefing_job.read_product = _read_catalog_product

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
