"""Driving adapter: the recurring pass that advances launch gates.

Implements `launch-gate-progression`'s *A recurring pass advances every
launch whose gate may open*, *The pass stands down while the playbook
cannot hold a launch*, *One launch's failure does not stop the other
launches being advanced*, *A gate awaiting only confirmation is asked
about in Slack* and *A gate is asked about at most once a day*.

Its own job rather than a rider on `automation_pass`: `scheduled-jobs`
records only whether a run succeeded, so sharing one would make a
gate-progression failure fail the automation run and leave neither run
record saying which concern broke.

The shape is `clickup_sync_job.py`'s, deliberately and in both halves --
the stand-down as well as the containment. Readiness is established once,
above the walk; a per-launch failure is contained, reported as it happens
and named again in the aggregate that fails the run; a cancellation is
left to propagate.

**The lock is taken here, not in the use case.** `transaction()` is shared
*infrastructure*, and no module's `application/` layer imports it. So this
adapter opens the transaction and takes the product's advisory lock around
`progress_launch`, and `gate_confirmation.py` does the same on the decision
path. Between them that is what makes a gate crossing happen once.

**The ask is posted outside the lock.** A delivery that hangs must never
hold a launch against the decision path.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import Any

from commerce_ops.launch.application import progress_launch
from commerce_ops.launch.domain.launch_playbook import (
    GATE_SEQUENCE,
    PlaybookNotReadyError,
)
from commerce_ops.launch.infrastructure.driven.clickup_mapping import (
    ClickUpMappingRepository,
)
from commerce_ops.launch.infrastructure.driven.clickup_sync import (
    MembersReader,
    ProductReader,
    converge_launch_eagerly,
)
from commerce_ops.launch.infrastructure.driven.gate_ask_suppression import (
    GateAskSuppressionRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_advisory_lock import (
    hold_launch_advance_lock,
)
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import LaunchRepository
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
)
from commerce_ops.launch.infrastructure.driving.gate_confirmation import post_gate_ask
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven import clickup_client as clickup
from commerce_ops.shared.infrastructure.driven.database import session, transaction
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "ASK_COOL_OFF",
    "PROGRESSION_SCHEDULE",
    "PROGRESSION_TOLERANCE",
    "TASK_NAME",
    "ClickUpMappingRepository",
    "GateAskSuppressionRepository",
    "LaunchRepository",
    "PlaybookRepository",
    "advance_and_ask",
    "clickup",
    "converge_launch_eagerly",
    "gate_progression_pass",
    "post_gate_ask",
    "progress_launch",
    "read_members",
    "read_product",
    "run_gate_progression_pass",
    "session",
    "transaction",
]

_logger = logging.getLogger(__name__)

TASK_NAME = "launch.gates.progression_pass"

# Injected by the composition root (`worker.py` in the worker process,
# `main.py` in the HTTP process — each supplies its own reader, exactly as
# `clickup_sync_job.read_product`/`read_members` are injected by `worker.py`
# alone, because `launch` may not import catalog's or access's own stores).
# `None` until injected; `converge_launch_eagerly` requires `read_product`
# (see `clickup_sync.py`'s `ProductReader`, which has no default) and treats
# `read_members` as optional, exactly as `converge_launch` does.
read_product: ProductReader | None = None
read_members: MembersReader = None

_FINAL_GATE = GATE_SEQUENCE[-1]

# Matching the ClickUp pass rather than beating it. `*/5` was the design's
# first answer -- this is the cheapest pass in the system, and the interval
# is what a member waits between a gate becoming ready and being asked about
# it -- and `scheduled-jobs`' longest-gap computation refuses it: it walks
# every occurrence over a 400-day horizon and caps that walk at 60,000, which
# `*/5` exceeds (115,200) and `*/10` does not (57,600). The horizon is
# load-bearing, so the schedule is what moves. Ten minutes is still the
# fastest anything in this deployment runs.
PROGRESSION_SCHEDULE = "*/10 * * * *"

# `scheduled-jobs` requires a tolerance exceeding the longest gap between
# consecutive runs; ten minutes here. Set far above that, and above the
# worker's own liveness tolerance, so an absent worker becomes visible
# before the work it failed to run does -- a merely delayed run must never
# be reported overdue.
PROGRESSION_TOLERANCE = datetime.timedelta(hours=6)

# How long an ask stands before the same gate is put to a member again.
# A module constant, never configuration: there is no per-deployment answer
# to how often a member should be asked the same question, and a configured
# value would owe the four obligations `AGENTS.md` places on every runtime
# variable. The reasoning `automation_pass.COOL_OFF` records, for the same
# shape of question.
ASK_COOL_OFF = datetime.timedelta(hours=24)


class GateProgressionPassError(RuntimeError):
    """One or more launches could not be advanced, so the run failed.

    Raised once, after the walk, naming every launch that failed rather
    than only the first: containment governs which launches are attempted,
    never whether a fault is visible.
    """


def _pass_failure(failed: list[str]) -> GateProgressionPassError:
    return GateProgressionPassError(
        "the gate-progression pass could not advance "
        f"{len(failed)} launch(es): {', '.join(failed)}"
    )


async def _restore_after_store_fault(db_session: Any) -> None:
    """Put a shared store back where the next launch's writes can record.

    A failure of the restore itself is deliberately not caught here; the
    caller chains it to the aggregate, because continuing against a store
    that cannot record is worse than not continuing.
    """
    if db_session is None:
        return
    rollback = getattr(db_session, "rollback", None)
    if rollback is None:
        return
    await rollback()


def _launch_folder_id() -> str | None:
    # A literal variable name, so the environment-drift check can see this
    # read (see `clickup_webhook`'s and `clickup_sync_job`'s own notes).
    return os.environ.get("CLICKUP_LAUNCH_FOLDER_ID")


async def _read_product_or_fail(product_id: ProductId) -> Any:
    # Matching `clickup_sync_job._read_product_or_fail`'s pattern: `read_product`
    # is declared `ProductReader | None` because it starts unset, but
    # `converge_launch_eagerly` needs a plain `ProductReader` — this narrows
    # that at the one call site that needs it, failing loudly rather than
    # with a bare `TypeError` if the composition root never injected one.
    if read_product is None:
        raise RuntimeError(
            "eager convergence needs to name a launch's ClickUp list after "
            "its catalog product, but no product reader was injected; "
            "worker.py/main.py supply one after register_all()"
        )
    return await read_product(product_id)


async def _converge_crossed_launch_eagerly(
    product_id: ProductId, *, playbook: Any
) -> None:
    """Look the launch back up and hand it to `converge_launch_eagerly`,
    with this module's own collaborators — the shared boilerplate both
    `advance_and_ask` and `run_gate_progression_pass`'s loop need to call
    the lock-and-delegate helper, which takes a `Launch` and its
    collaborators rather than resolving them itself.

    A fresh read on its own session, not the crossing's: by the time this
    runs, the crossing's own transaction has already closed (`_advance_one`
    returns after its `async with` exits), so there is nothing left to
    reuse, and a fresh read is what reflects the launch's just-crossed
    state in any case.

    Absent (deleted between the crossing and this read) is a silent no-op:
    there is nothing left to converge, and the periodic pass's own walk
    will simply not find this launch either.

    Guards the call independently of `converge_launch_eagerly`'s own catch:
    exactly as `clickup_webhook.py`'s `_trigger_advance_and_ask` does not
    rely on `advance_and_ask` catching its own failures, this caller's own
    insulation must hold regardless of what the `converge_launch_eagerly`
    binding does — including a test or future change substituting it with
    something that raises.
    """
    try:
        async with session() as db_session:
            launch = await LaunchRepository(db_session).get_by_product_id(product_id)
            if launch is None:
                return
            await converge_launch_eagerly(
                launch,
                playbook=playbook,
                clickup=clickup,
                mapping=ClickUpMappingRepository(db_session),
                read_product=_read_product_or_fail,
                members=read_members,
                folder_id=_launch_folder_id(),
            )
    except Exception:
        _logger.warning(
            "eager convergence: could not be triggered for product %s; it "
            "is left as it stands and the next periodic clickup_sync_job "
            "pass will retry it",
            product_id.value,
            exc_info=True,
        )


async def _advance_one(
    *,
    product_id: ProductId,
    playbook: Any,
) -> Any:
    """One launch's cascade, under its own transaction and advisory lock.

    Its own transaction per launch, not one for the walk: a launch whose
    cascade fails must leave the launches already advanced standing, and a
    single transaction over the walk would discard them all.
    """
    async with transaction() as db_session:
        await hold_launch_advance_lock(db_session, product_id)
        return await progress_launch(
            launches=LaunchRepository(db_session),
            playbook=playbook,
            product_id=product_id,
            journal=LaunchJournalRepository(db_session),
        )


def _crossed(progressed: Any) -> tuple[str, ...]:
    """Whatever `crossed` the cascade reported, tolerating a caller's fake
    that models less than the real `LaunchProgressed` does — the same
    duck-typed leniency `_awaiting_gate` below already extends to
    `awaiting_confirmation`/`current_gate`, and for the same reason: this
    module is exercised by tests substituting `progress_launch` with
    stand-ins of varying completeness, and a plain attribute access would
    make every one of them model a field only this one new branch reads."""
    return tuple(getattr(progressed, "crossed", None) or ())


def _awaiting_gate(progressed: Any) -> str | None:
    """The gate the cascade reported the launch waiting on, if any."""
    if not getattr(progressed, "awaiting_confirmation", False):
        return None
    for name in ("awaiting_gate", "gate_id", "current_gate"):
        gate = getattr(progressed, name, None)
        if isinstance(gate, str) and gate:
            # The final gate is never asked about. `list_active` already
            # keeps such a launch out of the walk, and this keeps it out of
            # the ask as well -- the exclusion is a property of the
            # capability, not of which launches the pass happens to be
            # handed.
            return None if gate == _FINAL_GATE else gate
    return None


async def _ask_if_owed(
    *,
    product_id: ProductId,
    gate_id: str,
    db_session: Any,
    now: datetime.datetime,
) -> None:
    """Post the ask unless this gate has been put to someone within the day.

    Outside the advance lock, by construction: the caller has left the
    transaction that held it before this is reached.

    A failed delivery is reported and leaves the gate eligible for the next
    pass, and does **not** fail the run. A Slack outage is not a fault of
    the advancing this pass exists to do, and failing the run for it would
    put the deployment into retry and overdue reporting for every pass the
    outage lasts.
    """
    suppression = GateAskSuppressionRepository(db_session)
    if await suppression.is_suppressed(
        product_id, gate_id, now=now, cool_off=ASK_COOL_OFF
    ):
        return
    try:
        await post_gate_ask(product_id=product_id, gate_id=gate_id)
    except Exception:
        _logger.warning(
            "gate progression: the confirmation ask for gate '%s' on product "
            "%s could not be delivered; nothing is recorded, so the gate "
            "stays eligible and the ask is attempted again on the next pass",
            gate_id,
            product_id.value,
            exc_info=True,
        )
        return
    # Recorded only after the delivery succeeded. Recording first and then
    # failing to deliver would silence the gate for a day with nobody having
    # been asked -- the mistake `field_gap_suppression` documents for its
    # own row.
    await suppression.record_delivery(product_id, gate_id, now)


async def advance_and_ask(
    product_id: ProductId, *, now: datetime.datetime | None = None
) -> bool:
    """Run the pass's own per-launch cascade for one launch, immediately.

    `advance-gates-from-clickup-webhook`'s single named exception to
    *Advancement is a convergence pass and not a consequence of recording
    an outcome*: the ClickUp webhook calls this, off its response path,
    for the one launch a delivery just completed a step on. Every rule
    this module applies to the periodic walk — read-before-command, the
    advisory lock, the 24-hour ask cool-off, the final-gate exclusion —
    applies here unchanged; only the trigger differs.

    Reads the served playbook in its own session rather than sharing the
    walk's, since a single-launch trigger has no walk to amortize the read
    over (`gate_confirmation.py`'s `_advance_after_approval` is the
    existing precedent for a fresh per-trigger read). A stand-down
    (`PlaybookNotReadyError`) is logged and stood down for this one
    product; the periodic pass remains what recovers once the playbook is
    ready again.

    Returns whether a gate actually crossed — informational for a caller
    that wants it, though `clickup_webhook.py`'s own eager-convergence
    dispatch (`trigger-clickup-projection-on-launch-events`, `tasks.md`
    3.5) deliberately does not read it, comparing the launch's gate before
    and after instead, so its detection stays correct against whatever
    this function's binding does in a given caller's tests. This function
    stays scoped to gate advancement and does not trigger eager
    convergence itself, unlike `gate_progression_job.py`'s own
    periodic-pass loop, which has no equivalent caller to report back to.

    Never raises: a fault here is a pure latency optimization lost, not a
    functional regression, since the identical `_advance_one`/
    `progress_launch` path is exercised by the periodic pass every ten
    minutes regardless. Returns `False` on any such fault — nothing to
    eagerly converge if the cascade itself did not run.
    """
    now = now or datetime.datetime.now(tz=datetime.UTC)
    try:
        async with session() as db_session:
            try:
                playbook = await PlaybookRepository(db_session).get("live")
            except PlaybookNotReadyError as unready:
                _logger.info(
                    "advance-and-ask trigger standing down for product %s: "
                    "the playbook cannot hold a launch (gates: %s)",
                    product_id.value,
                    ", ".join(unready.unheld_gates),
                )
                return False

            progressed = await _advance_one(product_id=product_id, playbook=playbook)
            gate_id = _awaiting_gate(progressed)
            if gate_id is not None:
                await _ask_if_owed(
                    product_id=product_id,
                    gate_id=gate_id,
                    db_session=db_session,
                    now=now,
                )
            return bool(_crossed(progressed))
    except Exception:
        _logger.warning(
            "advance-and-ask trigger: the launch for product %s could not "
            "be advanced; it is left as it stands and the next periodic "
            "pass will retry it",
            product_id.value,
            exc_info=True,
        )
        return False


async def run_gate_progression_pass(now: datetime.datetime | None = None) -> None:
    """Advance every launch whose gate may open, and ask about those that
    await only a human decision.

    The pass body, separate from the registration below so that what the
    scheduler needs (a `timestamp` it supplies) stays out of what the pass
    is: the clock is an argument here, defaulted rather than reached for,
    which is what lets the walk be driven at a fixed moment.
    """
    now = now or datetime.datetime.now(tz=datetime.UTC)

    async with session() as db_session:
        # Readiness, established **once, before the walk begins**, rather
        # than per launch: the served set is a property of the deployment,
        # identical for every launch in this run.
        try:
            playbook = await PlaybookRepository(db_session).get("live")
        except PlaybookNotReadyError as unready:
            # An expected stage of a deployment being set up, not an
            # outage. Recorded as a **succeeded** run: `scheduled-jobs`
            # records only success or failure, and a failure would put a
            # working deployment into retry and overdue reporting for
            # something retrying cannot fix. The accepted cost is that a
            # stood-down pass refreshes the work's last success, so this
            # capability raises no signal of its own during a stand-down;
            # the daily briefing names the unheld gates instead, on every
            # run while it lasts.
            _logger.info(
                "gate-progression pass standing down: the playbook cannot "
                "hold a launch (gates: %s)",
                ", ".join(unready.unheld_gates),
            )
            return

        launches = LaunchRepository(db_session)
        # `list_active` already excludes a launch standing at the final
        # gate, which is what keeps the graduation exclusion true of the
        # walk as well as of the ask.
        candidates = [launch.product_id for launch in await launches.list_active()]

        _logger.info(
            "gate-progression pass starting over %d launch(es)", len(candidates)
        )
        failed: list[str] = []
        for product_id in candidates:
            try:
                progressed = await _advance_one(
                    product_id=product_id, playbook=playbook
                )
                gate_id = _awaiting_gate(progressed)
                if gate_id is not None:
                    await _ask_if_owed(
                        product_id=product_id,
                        gate_id=gate_id,
                        db_session=db_session,
                        now=now,
                    )
                # A gate this same walk just crossed should not also wait
                # for `clickup_sync_job`'s next twice-daily run for its
                # newly released steps' tasks — the eager path this
                # periodic pass already had for gate advancement itself,
                # extended to the projection direction. Inside the `try`
                # like `_ask_if_owed` above, though `converge_launch_eagerly`
                # never raises by construction.
                if _crossed(progressed):
                    await _converge_crossed_launch_eagerly(
                        product_id, playbook=playbook
                    )
            except Exception:
                # `Exception`, not a curated list: a fault nobody predicted
                # is exactly the one that must not starve the launches
                # behind it. `BaseException` stays uncaught, so a cancelled
                # worker stops walking rather than booking the cancellation
                # against a product.
                failed.append(product_id.value)
                # Reported here as well as in the aggregate below: the
                # aggregate is what fails the run, this is what makes the
                # fault diagnosable, and a walk that failed on three
                # launches says so three times.
                _logger.warning(
                    "gate-progression pass: the launch for product %s could "
                    "not be advanced; it is left as it stands and the walk "
                    "continues to the next launch",
                    product_id.value,
                    exc_info=True,
                )
                try:
                    await _restore_after_store_fault(db_session)
                except Exception as unrecoverable:
                    # The recovery itself failing means the pass can no
                    # longer reach a state in which the next launch's
                    # writes could be recorded, so the walk ends and the
                    # aggregate is chained to the reason it ended.
                    raise _pass_failure(failed) from unrecoverable

        if failed:
            raise _pass_failure(failed)


@register_scheduled(
    name=TASK_NAME,
    schedule=PROGRESSION_SCHEDULE,
    tolerance=PROGRESSION_TOLERANCE,
)
async def gate_progression_pass(timestamp: int) -> None:
    """The scheduled entry point. `timestamp` is the scheduler's, and the
    pass has no use for it: the moment it works from is its own."""
    await run_gate_progression_pass()
