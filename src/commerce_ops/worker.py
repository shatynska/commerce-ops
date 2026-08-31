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

from commerce_ops.access.application import Person, list_people
from commerce_ops.access.infrastructure.driven.roster_repository import PostgresRoster
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
from commerce_ops.briefing.application import LaunchReportsUnavailableError
from commerce_ops.briefing.infrastructure.driven import slack_notifier
from commerce_ops.briefing.infrastructure.driving import daily_briefing_job
from commerce_ops.catalog.application import get_product_by_id, record_sub_category
from commerce_ops.catalog.infrastructure.driven.product_repository import (
    CatalogProductRepository,
)
from commerce_ops.launch.application import read_launches
from commerce_ops.launch.domain.launch_playbook import PlaybookNotReadyError
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.launch.infrastructure.driving import (
    automation_pass,
    clickup_sync_job,
    gate_confirmation,
    gate_progression_job,
)
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
# The ClickUp Custom Field configuration report, injected for the same reason
# and in the same place: the pass reports a misconfiguration to the team's
# channel, and `launch` reaches that channel through the same port rather than
# by importing the module that owns it.
clickup_sync_job.notifier = slack_notifier
# The stuck-step report, for the same reason again: a step whose handler
# has stopped making progress needs a person, and this is how `launch`
# reaches the team's channel without importing the module that owns it.
automation_pass.notifier = slack_notifier

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

# The automation pass hands each handler the catalog product its launch is
# for, so a handler never fetches one itself -- the boundary is crossed
# here, once, instead of once per handler. Same reader, same reason as the
# ClickUp pass's: `launch` may not import catalog's store, and only this
# module sits outside `.importlinter`'s containers.
automation_pass.read_product = _read_catalog_product


async def _record_sub_category(product_id: ProductId, sub_category: str) -> None:
    """The sub-category advisor's recording capability for `lp.listing.007`.

    Injected here for the same reason `_read_catalog_product` is: `launch`
    may not import catalog's store (`SubCategoryRecorder`,
    `launch/application/ports.py`), and only this module sits outside
    `.importlinter`'s containers. Its own session, opened per call, for
    the same reason the catalog reader's is: the pass may resolve many
    launches, and this write is not part of any one launch's transaction.
    """
    async with session() as db_session:
        await record_sub_category(
            CatalogProductRepository(db_session), product_id, sub_category
        )


# Wired for `lp.listing.007` specifically, not for every automated step —
# `launch-step-automation`'s recording capability is per-step, and this is
# the only step this deployment writes a finding for today.
automation_pass.recorders = {"lp.listing.007": _record_sub_category}

# The gate-progression pass asks about a gate by naming the product, so the
# ask adapter needs the same catalog reader for the same reason: `launch`
# may not import catalog's store, and only this module sits outside
# `.importlinter`'s containers. Without it the ask still goes out, naming
# the launch by identifier.
gate_confirmation.read_product = _read_catalog_product

# `gate_progression_job`'s own `converge_launch_eagerly` (`trigger-clickup-
# projection-on-launch-events`) needs the same catalog reader `clickup_sync_job`
# has, for the same reason and by the same route: `converge_launch` requires
# it, with no default, to name a launch's ClickUp list.
gate_progression_job.read_product = _read_catalog_product


class _RosterReader:
    """Reads the roster for the ClickUp pass, on its own session.

    Injected here for the same reason the catalog reader is: `launch` may
    only reach `access` through its public application surface, and only
    this module — outside `.importlinter`'s containers — may name both
    sides. A projected task is assigned to the step's assignees, which is
    what needs resolving.
    """

    async def list_people(self) -> tuple[Person, ...]:
        # `PostgresRoster` opens its own session per operation, so this
        # read is not part of any launch's transaction.
        return await list_people(roster=PostgresRoster())


clickup_sync_job.read_people = _RosterReader()
# Same reason and same route as `read_product` above: reused rather than a
# second instance, since both readers are stateless.
gate_progression_job.read_people = clickup_sync_job.read_people


async def _read_launch_reports(*, as_of: date) -> tuple[LaunchReport, ...]:
    """Every launch, reported as of `as_of`, for the daily briefing.

    Closed over its own session here for the same reason the ClickUp
    reader is: briefing may not import launch's repository, and only this
    module — outside `.importlinter`'s containers — may name both sides.
    """
    async with session() as db_session:
        try:
            playbook = await PlaybookRepository(db_session).get("live")
        except PlaybookNotReadyError as unready:
            # Translated here, and only here. `briefing` may not name
            # `launch.domain`, and by its own convention names nothing from
            # `launch` at all — its report port is structurally typed for
            # exactly that reason. This module sits outside every
            # `.importlinter` container, which is what lets it hold both
            # sides, and it already does the same for the product and
            # roster readers.
            raise LaunchReportsUnavailableError(
                identifiers=unready.unheld_gates
            ) from unready
        return await read_launches(
            LaunchRepository(db_session),
            ServedPlaybooks(playbook),
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
