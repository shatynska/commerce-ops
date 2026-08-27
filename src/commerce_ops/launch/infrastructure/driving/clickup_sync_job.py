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
from collections.abc import Sequence

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.application.field_configuration import (
    FieldConfiguration,
    check_field_configuration,
)
from commerce_ops.launch.domain.launch_playbook import PlaybookNotReadyError
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    ProductReader,
    RosterReader,
    converge_launch,
    reconcile_launch,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.shared.domain.clickup import ClickUpFieldDefinition
from commerce_ops.shared.infrastructure.driven import clickup_client as clickup
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "SYNC_SCHEDULE",
    "SYNC_TOLERANCE",
    "TASK_NAME",
    "ClickUpCompletionPassError",
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


class ClickUpCompletionPassError(RuntimeError):
    """One or more launches could not be converged, so the run failed.

    Raised once, after the walk, naming every launch that failed rather
    than only the first: containment governs which launches are attempted,
    never whether a fault is visible, and `scheduled-jobs` carries no
    per-launch outcome to report to — so the run's own failure is the only
    signal an unprojected launch has.
    """


def _pass_failure(products: Sequence[str]) -> ClickUpCompletionPassError:
    """The run's failure, naming each failed launch by its product.

    By identifier rather than catalog name: the identifier is what the
    pass already holds, and reading the catalog to render a failure is one
    more thing that can fail while reporting a failure.
    """
    return ClickUpCompletionPassError(
        f"the ClickUp completion pass failed for {len(products)} launch(es), "
        f"by product: {', '.join(products)}"
    )


async def _read_product_or_fail(product_id: object) -> object:
    if read_product is None:
        raise RuntimeError(
            "the ClickUp completion pass needs to name a new launch list "
            "after its catalog product, but no product reader was injected; "
            "`worker.py` supplies one after `register_all()`"
        )
    return await read_product(product_id)  # type: ignore[arg-type]


def _field_identifiers() -> tuple[str | None, str | None]:
    """The two configured Custom Field identifiers, read by literal name.

    Read straight from the environment rather than through a parsed
    accessor: absent and present-but-empty must stay distinguishable here,
    because the two mean different things -- absent is how a deployment
    declines the capability and is answered with silence, while empty is
    what a mis-rendered secret produces for a deployment that meant to opt
    in, and is reported as a configuration gap.
    """
    return (
        os.environ.get("CLICKUP_GATE_FIELD_ID"),
        os.environ.get("CLICKUP_DISCIPLINE_FIELD_ID"),
    )


async def _read_field_configuration(folder_id: str | None) -> FieldConfiguration:
    """What resolves and what is missing, for this pass.

    No read is made where no launch folder is configured -- leaving *Each
    launch is projected into its own ClickUp list* the sole authority on
    that condition rather than opening a second one -- and none where
    neither identifier is configured, since a deployment that named no field
    has declined the capability. In both cases the empty-identifier finding
    is still composed, because it is established by the configuration alone
    and needs no network at all: the catch for a mis-rendered secret must
    not depend on the very service whose configuration is in question.

    A read that does not complete costs this pass its field values and
    nothing else. It is a **reachability** fault, not a configuration gap,
    and `runtime-configuration` requires the two to stay distinguishable --
    reporting an unreachable ClickUp as two absent fields would deliver a
    false repair instruction and then suppress the truth behind it.
    """
    gate_field_id, discipline_field_id = _field_identifiers()
    if folder_id is None or (gate_field_id is None and discipline_field_id is None):
        return check_field_configuration(
            gate_field_id=gate_field_id,
            discipline_field_id=discipline_field_id,
            fields=None,
        )
    try:
        fields: tuple[ClickUpFieldDefinition, ...] | None = await clickup.folder_fields(
            folder_id
        )
    except Exception:
        _logger.warning(
            "the launch folder's Custom Fields could not be read; this pass "
            "writes no Custom Field value and reports no configuration gap "
            "derived from them, and every launch is still projected, "
            "corrected and reconciled",
            exc_info=True,
        )
        fields = None
    return check_field_configuration(
        gate_field_id=gate_field_id,
        discipline_field_id=discipline_field_id,
        fields=fields,
    )


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

        # The Custom Field configuration, established **once, before the
        # walk begins**, in the same phase as readiness. Checking once
        # rather than per task is what makes the check complete: a gap is a
        # property of the configuration, identical for every task of every
        # launch, so discovering it only where a task happens to need it
        # would leave a gate no launch has reached unchecked until one did.
        #
        # It sits after the stand-down deliberately -- a stood-down pass
        # declines entirely and reaches ClickUp for nothing at all -- and
        # before the launch loop, so it answers even on a pass with no
        # active launch. That last is the whole reason folder scope was
        # chosen over list scope: a list-scoped read could not answer when
        # no launch exists, which is exactly when a fresh misconfiguration
        # should still be found. It must not move behind an early return on
        # an empty launch set.
        configuration = (await _read_field_configuration(folder_id)).writable_options()

        _logger.info("ClickUp completion pass starting over %d launch(es)", len(active))
        failed: list[str] = []
        for launch in active:
            # Both halves in one `try`, which is what makes them one unit:
            # a launch whose projection raised is not reconciled, because
            # projection establishes the list and the mappings
            # reconciliation reads back. Skipping it *entirely* — not
            # reading it and declining to record — is load-bearing:
            # reconciliation records on a transition of the retained
            # observed state, so observing without recording would consume
            # the transition and lose the completion for good.
            try:
                await converge_launch(
                    launch=launch,
                    playbook=playbook,
                    clickup=clickup,
                    mapping=mapping,
                    read_product=_read_product_or_fail,
                    roster=read_people,
                    folder_id=folder_id,
                    configuration=configuration,
                )
                await reconcile_launch(
                    launch=launch,
                    playbook=playbook,
                    clickup=clickup,
                    mapping=mapping,
                    record_outcome=record,
                )
            except Exception:
                # `Exception`, not a curated list: the fault that made this
                # necessary was an `HTTPStatusError` surfacing from a
                # mapping row that had gone stale, and a fault nobody
                # predicted is exactly the one that must not starve the
                # launches behind it. `BaseException` stays uncaught, so a
                # cancelled worker stops walking rather than booking the
                # cancellation against a product.
                failed.append(launch.product_id.value)
                # Reported here rather than only in the aggregate below:
                # the aggregate is what fails the run, this is what makes
                # the fault diagnosable, and a walk that failed on three
                # launches says so three times.
                _logger.warning(
                    "ClickUp completion pass: the launch for product %s could "
                    "not be converged; it is left as it stands and the walk "
                    "continues to the next launch",
                    launch.product_id.value,
                    exc_info=True,
                )
                try:
                    # Every write in the walk commits as it is made, so this
                    # discards nothing; what it restores is a session left
                    # unusable by a *database* fault, which would otherwise
                    # fail every launch behind this one.
                    await db_session.rollback()
                except Exception as unrecoverable:
                    # The recovery itself failing means the pass can no
                    # longer reach a state in which the next launch's writes
                    # could be recorded. Continuing would write to ClickUp
                    # and lose the record of it — which is how a list with
                    # no association gets made, the very fault this pass
                    # exists to survive. So the walk ends here, and the
                    # aggregate is chained to the reason it ended.
                    raise _pass_failure(failed) from unrecoverable

        if failed:
            raise _pass_failure(failed)
