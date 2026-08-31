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
from typing import Any

from commerce_ops.launch.application import record_step_outcome
from commerce_ops.launch.application.field_configuration import (
    FieldConfiguration,
    check_field_configuration,
)
from commerce_ops.launch.application.field_configuration import (
    describe_gap as _describe_configuration,
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
from commerce_ops.launch.infrastructure.driven.field_gap_suppression import (
    clear_reported_field_gap,
    record_field_gap_reported,
    reported_field_gap,
)
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.shared.application.ports import MonitoringNotifier
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

# Twice daily. The webhook is now the primary path completion travels;
# this pass is the safety net for what it missed, so its cadence sets how
# long a dropped delivery can go unnoticed, not how quickly completion is
# normally seen.
#
# Lowered from */10 on 2026-08-31, completing the second of the two stages
# `shift-clickup-completions-to-webhook` planned (`design.md` -- "Cadence:
# twice daily, not once"). That change's own `tasks.md` (4, 3.4) made this
# conditional on first confirming reliable webhook delivery over a real
# observation period -- which did not happen; the change was archived once
# the webhook was merely confirmed *working*, not observed reliable over
# days. This cadence change was made anyway, on an explicit decision to
# accept that unmet precondition: real ClickUp 429s from the combined load
# of this pass and the automation pass needed relieving immediately (a
# separate, parallel change addresses 429 handling itself), and only test
# data is at stake while no real production launch exists yet. See that
# archived change's `tasks.md`, section 4's note, for the full record, and
# `docs/deferred-work.md`'s `LaunchRepository.save` entry for the
# self-healing window this widened.
SYNC_SCHEDULE = "0 6,18 * * *"

# Comfortably longer than the worker's own liveness tolerance, which
# `scheduled-jobs` requires of every piece of work it runs: an absent
# worker must become visible before the work it failed to run does. Also
# far longer than the 12-hour gap, so a merely delayed run is never
# reported overdue.
SYNC_TOLERANCE = datetime.timedelta(hours=24)


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


# Injected by `worker.py` after `register_all()`, never at import and never as
# a job argument -- the same shape the overdue check uses, and for the same
# reasons: the runner passes only serializable values to a job, and the only
# notifier this deployment has lives outside this module's own module. It is
# `None` in the HTTP process, which registers this job module but never runs
# it.
notifier: MonitoringNotifier | None = None


async def _deliver_configuration_report(message: str) -> bool:
    """Post the configuration report, saying whether it actually arrived.

    The return value decides whether suppression is written, so a delivery
    that failed leaves the gap eligible to be reported on the next pass
    rather than being silently suppressed -- the rule `scheduled-jobs`
    already states for a continuing outage, borrowed here.

    A failure to deliver never fails the run and never stops the pass:
    delivery sits on the pre-walk path ahead of every launch, so a fault
    there must no more stop a launch being projected than a fault in the
    folder read does.
    """
    if notifier is None:
        _logger.error(
            "a ClickUp Custom Field configuration gap was found but no "
            "monitoring notifier is configured; the report was not delivered"
        )
        return False
    try:
        await notifier.post_monitoring_message(message)
    except Exception:
        _logger.exception("failed to deliver a Custom Field configuration report")
        return False
    return True


async def _restore_after_store_fault(db_session: Any) -> None:
    """Put a shared store back in a state where the launches' writes record.

    A failed access can leave a shared session unusable, so every launch
    after it would write to ClickUp and lose the record of the write. The
    restore is attempted before the first launch is attempted.

    **A failure of the restore itself is deliberately not caught.** It
    propagates, ending the walk and failing the run, because continuing
    against a store that cannot record is worse than not continuing -- the
    judgement `One launch's failure does not stop the other launches being
    converged` already makes for a failed recovery between launches.
    """
    if db_session is None:
        return
    rollback = getattr(db_session, "rollback", None)
    if rollback is None:
        return
    await rollback()


async def _report_field_configuration(
    configuration: FieldConfiguration, db_session: Any = None
) -> None:
    """Report a gap once, and lift the record when there is nothing to report.

    Every access of the retained record is contained: it sits on the pre-walk
    path ahead of every launch, so an uncaught fault here would abort the pass
    before anything was projected -- a fault wholly inside this concern
    costing the projection and completion intake of every launch, which the
    guarantee this requirement makes forbids.

    A failed **read** reports no gap on that pass: the system cannot then tell
    a standing gap from a new one, and repeating a message already delivered
    is worse than deferring one by a pass. A failed **write** after a
    delivered report simply leaves the gap eligible again -- the report has
    gone out and cannot be recalled.

    Where the record shares a store with the writes the pass makes for each
    launch, a failed access can leave that store unusable, so it is restored
    before the first launch is attempted. **A failed restore is not
    contained**: the walk ends and the run is recorded as failed, on the
    ground `One launch's failure does not stop the other launches being
    converged` gives for a failed recovery between launches, which this
    extends to the pre-walk restore. Continuing would project launches whose
    ClickUp writes could not be recorded -- writing to ClickUp and losing the
    record of the write, which that requirement judges worse than stopping.
    This is the one path on which a fault of this concern costs more than the
    field values.
    """
    if not configuration.authoritative:
        # Nothing could be established about the two fields -- the folder's
        # fields could not be read, or no launch folder is configured. That
        # says nothing about the configuration, so the record is left exactly
        # as it stands: lifting it here would make a deployment whose
        # reachability flaps re-report the same unrepaired gap every time it
        # recovered, which is the flood the report-once rule exists to
        # prevent, arriving by the other door. Any empty-identifier finding
        # is still reported below, because it needs no read.
        if not configuration.has_gap:
            return
    elif not configuration.has_gap:
        # Repaired, or never broken. Lifting here is what makes a gap
        # appearing again reportable rather than suppressed forever.
        try:
            await clear_reported_field_gap(db_session)
        except Exception:
            # Deliberately no restore here. The clear runs on a pass that
            # found no gap, so nothing was reported and no later launch
            # depends on it; and the record keeps its own session, so a
            # failure here cannot leave the launches' store unusable. The
            # restore belongs to the read and write paths, where a report is
            # actually in flight.
            _logger.warning(
                "the ClickUp Custom Field gap record could not be cleared; a "
                "later gap of the same content may go unreported until it "
                "can be, and the pass continues",
                exc_info=True,
            )
        return

    identity = repr(configuration.identity())
    try:
        already = await reported_field_gap(db_session)
    except Exception:
        await _restore_after_store_fault(db_session)
        _logger.warning(
            "the ClickUp Custom Field gap record could not be read; this pass "
            "reports no gap rather than risk repeating one already delivered, "
            "and every launch is still projected, corrected and reconciled",
            exc_info=True,
        )
        return
    if already == identity:
        # A *continuing* gap of unchanged content. Reported once, not on
        # every pass: a wall of identical messages trains the team to ignore
        # the channel, which costs more than the gap itself.
        return

    message = (
        "ClickUp Custom Field configuration needs attention — a projected "
        "task's gate and discipline cannot be fully recorded until it is "
        "repaired. The launch's work is projected and its completions still "
        "flow; only these two field values are affected.\n\n"
        + _describe_configuration(configuration)
    )
    if not await _deliver_configuration_report(message):
        return
    try:
        await record_field_gap_reported(identity, db_session)
    except Exception:
        await _restore_after_store_fault(db_session)
        _logger.warning(
            "a ClickUp Custom Field configuration gap was reported but the "
            "record of it could not be written; the same gap will be reported "
            "again on the next pass, and the pass continues",
            exc_info=True,
        )


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
            record_step_outcome,
            launches,
            ServedPlaybooks(playbook),
            journal=LaunchJournalRepository(db_session),
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
        field_configuration = await _read_field_configuration(folder_id)
        await _report_field_configuration(field_configuration, db_session)
        configuration = field_configuration.writable_options()

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
