"""Driving adapter: the ClickUp completion loop's periodic convergence pass.

Implements `launch-clickup-sync`'s "The reconciliation pass records
completions and reopenings the webhook missed", whose opening clause makes
this scheduled work rather than anything triggerable from outside the
deployment.

Each run walks every active launch and does both halves in order: converge
ClickUp toward the launch's schedule (list, tasks, due dates), then read
back what changed and record it. Graduated launches never appear —
`list_active()` filters them out, so no pass has to remember the rule.

Collaborators are imported by name into this module's namespace and
referenced as bare globals, keeping `daily_digest_job.py`'s pattern.
`read_product` is the exception and arrives by injection: the launch module
may not import the catalog's own store (`.importlinter`'s
`products-infrastructure-boundary`), so `worker.py` — which sits outside
those containers — supplies the reader, exactly as it supplies
`overdue_check.notifier`.
"""

from __future__ import annotations

import datetime
import functools
import logging
import os

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.domain.launch_playbook import PlaybookNotReadyError
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    ProductReader,
    RosterReader,
    converge_launch,
    ensure_tag_vocabulary,
    reconcile_launch,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.shared.infrastructure.driven import clickup_client as clickup
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "SYNC_SCHEDULE",
    "SYNC_TOLERANCE",
    "TASK_NAME",
    "read_people",
    "read_product",
    "reconcile_clickup_completions",
    "record_step_outcome",
    "session",
]

_logger = logging.getLogger(__name__)

TASK_NAME = "launch.clickup.completion_pass"

# Every 10 minutes. The webhook is what makes completion prompt; this pass
# exists to catch what it missed, so its cadence sets how long a dropped
# delivery can go unnoticed, not how quickly completion is normally seen.
#
# Lowered from 30 minutes on 2026-08-24. That figure was sized for a pass
# standing behind a working webhook; until one is registered, this pass is
# the only path completion travels, and half an hour of it is felt by
# whoever ticked the task. Steady-state cost is two ClickUp reads per
# active launch per pass, so tripling the rate stays far inside the
# ~100 req/min budget. The first projection of a new launch (~185 calls)
# is unaffected -- that spike is per launch, not per pass.
SYNC_SCHEDULE = "*/10 * * * *"

# Comfortably longer than the worker's own liveness tolerance, which
# `scheduled-jobs` requires of every piece of work it runs: an absent
# worker must become visible before the work it failed to run does. Also
# far longer than the 10-minute gap, so a merely delayed run is never
# reported overdue.
SYNC_TOLERANCE = datetime.timedelta(hours=6)


# Injected by `worker.py` after `register_all()`, never at import and never
# as a job argument. `None` in the HTTP process, which registers this module
# but never runs the job.
read_product: ProductReader | None = None

# The roster reader, injected the same way and for the same reason: a
# projected task is assigned to the step's assignees, resolved through the
# roster to their ClickUp users, and the launch module may only reach
# `access` through its public application surface.
read_people: RosterReader = None


def _launch_folder_id() -> str | None:
    # A literal variable name, so the environment-drift check can see this
    # read (see `clickup_webhook`'s own note).
    return os.environ.get("CLICKUP_LAUNCH_FOLDER_ID")


async def _read_product_or_fail(product_id: object) -> object:
    if read_product is None:
        raise RuntimeError(
            "the ClickUp completion pass needs to name a new launch list "
            "after its catalog product, but no product reader was injected; "
            "`worker.py` supplies one after `register_all()`"
        )
    return await read_product(product_id)  # type: ignore[arg-type]


@register_scheduled(
    name=TASK_NAME,
    schedule=SYNC_SCHEDULE,
    tolerance=SYNC_TOLERANCE,
)
async def reconcile_clickup_completions(timestamp: int) -> None:
    """Converge every active launch's ClickUp projection, then read it back."""
    folder_id = _launch_folder_id()

    async with session() as db_session:
        launches = LaunchRepository(db_session)
        mapping = ClickUpMappingRepository(db_session)
        active = await launches.list_active()
        # The playbook is live and read per pass — every launch converges
        # against the same served set, whatever version stamp it recorded.
        try:
            playbook = await PlaybookRepository(db_session).get("live")
        except PlaybookNotReadyError as unready:
            # A playbook still being authored is an expected state, not an
            # outage, so the pass stands down and the run is recorded as
            # having succeeded: `scheduled-jobs` records only success or
            # failure, and a failure would put a working deployment into
            # retry and overdue reporting for something retrying cannot
            # fix. The cost is accepted — a stood-down pass refreshes the
            # work's last success, so overdue reporting cannot fire while
            # the playbook is unready. The daily briefing carries that
            # signal instead, on every run while it lasts.
            _logger.info(
                "ClickUp completion pass standing down: the playbook cannot "
                "hold a launch (gates: %s)",
                ", ".join(unready.unheld_gates),
            )
            return
        record = functools.partial(
            record_step_outcome, launches, ServedPlaybooks(playbook)
        )

        # After the stand-down return above, so a pass that declines to run
        # creates nothing in the space either; and before the loop, so the
        # vocabulary costs one resolve and one read per pass rather than
        # per launch.
        await ensure_tag_vocabulary(clickup=clickup, folder_id=folder_id)

        _logger.info("ClickUp completion pass starting over %d launch(es)", len(active))
        for launch in active:
            await converge_launch(
                launch=launch,
                playbook=playbook,
                clickup=clickup,
                mapping=mapping,
                read_product=_read_product_or_fail,
                roster=read_people,
                folder_id=folder_id,
            )
            await reconcile_launch(
                launch=launch,
                playbook=playbook,
                clickup=clickup,
                mapping=mapping,
                record_outcome=record,
            )
