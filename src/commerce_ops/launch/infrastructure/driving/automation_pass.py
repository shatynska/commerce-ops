"""Driving adapter: the pass that runs what an `automated` step names.

Implements `launch-step-automation`'s "An automated step's handler is
invoked by recurring work", whose closing clause — invocation is not
reachable from outside the deployment — makes this scheduled work rather
than anything a request can start.

Each pass does two halves in order: deliver the pending results a previous
pass could not, then walk every active launch and resolve the automated
steps that are still open. Delivery goes first so a Slack outage costs at
most one cycle rather than stranding a result until something else
produces one.

**Terminality, not whether a confirmer is named, decides what is held.**
A non-terminal outcome is recorded directly whatever the step says about
confirmation: it is a handler reporting that the step is *not* resolved,
and holding it would ask a person to accept "in progress" — a proposal
with nothing in it to agree with, which would then suppress re-invocation
until they clicked. Only a terminal proposal is a result anyone can
accept.

Collaborators arrive as arguments rather than as module globals, unlike
`clickup_sync_job`'s pattern: this module's work is a pure function of
them, which is what lets the whole pass be exercised without a database.
The scheduled entry point below is the one place that builds the real
ones.
"""

from __future__ import annotations

import datetime
import functools
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from commerce_ops.launch.application import (
    HANDLERS,
    StepContext,
    StepResolution,
    record_step_outcome,
)
from commerce_ops.launch.domain.launch_playbook import (
    Hazard,
    LaunchPlaybook,
    StepDefinition,
    StepKind,
    StepStatus,
    permissible_terminal_outcomes,
)
from commerce_ops.launch.domain.launch_run import Launch, Provenance
from commerce_ops.launch.infrastructure.driven.automated_results import (
    AutomatedResultRepository,
)
from commerce_ops.launch.infrastructure.driven.automated_step_backoff import (
    AutomatedStepBackoffRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_journal_repository import (
    LaunchJournalRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.launch_thread_delivery import (
    establish_thread_and_resolve_mention,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.launch.infrastructure.driven.slack_notifier import launches_channel
from commerce_ops.launch.infrastructure.driving import automation_confirmation
from commerce_ops.shared.application.ports import MonitoringNotifier
from commerce_ops.shared.domain.identity import ProductId
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "AUTOMATION_SCHEDULE",
    "AUTOMATION_TOLERANCE",
    "COOL_OFF",
    "REPEAT_COOL_OFF",
    "TASK_NAME",
    "notifier",
    "read_product",
    "resolve_automated_steps",
    "run_automation_pass",
    "session",
]

_logger = logging.getLogger(__name__)

_AUTOMATED_SOURCE = "automated"

# How long a person's rejection stands before the same step is proposed
# again. A module constant, never configuration: there is no
# per-deployment answer to how long a disagreement should hold, and a
# configured value would owe the four obligations `AGENTS.md` places on
# every runtime variable. Without it, one rejection buys a fresh handler
# run every pass forever, and a Slack message each time.
COOL_OFF = datetime.timedelta(hours=24)

# After a handler repeats the non-terminal outcome the step already
# carries. Its own constant rather than a reuse of `COOL_OFF`: the two
# answer different questions — a person disagreed, versus a machine
# repeated itself — and sharing one would mean a later change to either
# silently moving the other. Same value today, and a fixed property of
# the system rather than a configured one, for the reason the rejection
# cool-off already records.
REPEAT_COOL_OFF = datetime.timedelta(hours=24)

TASK_NAME = "launch.automation.resolution_pass"

# Every 15 minutes rather than the ClickUp pass's 10: a pass here may cost
# a model call per unresolved automated step, where that one costs two
# cheap reads. A pending result and a rejection each suppress
# re-invocation, so the steady-state cost is bounded by the steps actually
# open.
AUTOMATION_SCHEDULE = "*/15 * * * *"

# Comfortably longer than the worker's own liveness tolerance, which
# `scheduled-jobs` requires of every piece of work it runs: an absent
# worker must become visible before the work it failed to run does. Also
# far longer than the 15-minute gap, so a merely delayed run is never
# reported overdue.
AUTOMATION_TOLERANCE = datetime.timedelta(hours=6)

# Injected by `worker.py` after `register_all()`, never at import and never
# as a job argument. `None` in the HTTP process, which registers this
# module but never runs the job.
read_product: Callable[..., Awaitable[Any]] | None = None

# The channel a stuck step is reported to, injected the same way and for
# the same reason `clickup_sync_job.notifier` is: the runner passes only
# serializable values to a job, and the only notifier this deployment has
# lives outside this module. `None` in the HTTP process — and a stuck-step
# report then logs at error rather than vanishing, since a step nobody can
# resolve is exactly what must not go unmentioned.
notifier: MonitoringNotifier | None = None


def _is_terminal_for(step: StepDefinition, outcome: Any) -> bool:
    """Whether `outcome` is one this step's hazard permits as terminal."""
    kind = outcome if isinstance(outcome, type) else type(outcome)
    return kind in permissible_terminal_outcomes(step.hazard)


def _is_settled(launch: Launch, step: StepDefinition) -> bool:
    progress = launch.progress_for(step.identifier)
    if progress is None:
        return False
    return _is_terminal_for(step, progress.outcome)


def _automated_steps(playbook: LaunchPlaybook) -> tuple[StepDefinition, ...]:
    return tuple(
        step
        for step in playbook.served_steps
        if step.kind is StepKind.AUTOMATED and step.status is StepStatus.ACTIVE
    )


class BackoffStoreUnrestorable(RuntimeError):
    """The shared store could not be restored after a contained backoff
    fault, so the walk ended.

    `launch-step-automation`: a pass that walked on against a store it
    cannot restore would persist nothing while reporting success, which
    is worse than stopping. The same judgement `_restore_after_store_fault`
    records for the ClickUp pass.
    """


def _outcome_kind(outcome: Any) -> type:
    """The outcome's kind, which is what a repeat is judged on.

    Never the value: `Blocked` is a frozen dataclass whose equality
    includes its reason, and an LLM-backed handler rewords its reason on
    every call — so `==` would find no two blocks alike, the cool-off
    would engage never, and the rule would appear to work while changing
    nothing (`launch-step-automation`, "disregarding any reason either
    carries").
    """
    return outcome if isinstance(outcome, type) else type(outcome)


def _row_kind(row: Any) -> Any:
    for name in ("noted_kind", "outcome_kind", "outcome", "kind", "noted_outcome"):
        held = getattr(row, name, None)
        if held is not None:
            return held
    return None


def _row_moment(row: Any) -> datetime.datetime | None:
    for name in ("noted_at", "when"):
        held = getattr(row, name, None)
        if isinstance(held, datetime.datetime):
            return held
    return None


def _row_reported(row: Any) -> bool:
    for name in ("reported_at", "reported", "has_been_reported"):
        held = getattr(row, name, None)
        if held is not None and held is not False:
            return True
    return False


def _governs(row: Any, launch: Launch, step: StepDefinition) -> bool:
    """Whether this row still speaks for the step.

    **Lifting is lazy, not swept.** A row whose noted kind is not the kind
    of the step's currently recorded outcome governs nothing — neither the
    cool-off nor the report suppression — so nothing has to remember to
    delete it. That is what lets `automation_confirmation`, which records
    for these same steps, stay untouched: every recording surface gets
    this right by doing nothing.
    """
    if row is None:
        return False
    progress = launch.progress_for(step.identifier)
    if progress is None:
        return False
    return bool(_row_kind(row) == _outcome_kind(progress.outcome))


async def run_automation_pass(
    *,
    launches: Any,
    playbook: LaunchPlaybook,
    handlers: Any,
    results: Any,
    record_outcome: Callable[..., Awaitable[Any]],
    read_product: Callable[..., Awaitable[Any]],
    deliver: Callable[..., Awaitable[Any]],
    backoff: Any,
    notifier: Any,
    establish_thread: Callable[..., Awaitable[tuple[str, str | None]]],
    now: datetime.datetime,
) -> None:
    """Deliver what is waiting, then resolve what is open.

    `backoff` and `notifier` are required rather than defaulted, for the
    reason `add-launch-journal` made its own port required: a defaulted
    collaborator is one a composing adapter can forget silently, and the
    feature then does nothing while every test still passes. `establish_thread`
    is the same rule applied to the stuck-step report's own thread-and-mention
    preamble (`launch_thread_delivery.establish_thread_and_resolve_mention`
    in production) -- threaded as an argument like every other collaborator
    here, not a module global, which is what lets this pass be exercised
    without a database.
    """
    active: Sequence[Launch] = await launches.list_active()

    await _deliver_waiting(
        results=results,
        playbook=playbook,
        read_product=read_product,
        deliver=deliver,
        now=now,
    )

    for launch in active:
        await _walk_launch(
            launch=launch,
            playbook=playbook,
            handlers=handlers,
            results=results,
            record_outcome=record_outcome,
            read_product=read_product,
            deliver=deliver,
            backoff=backoff,
            notifier=notifier,
            establish_thread=establish_thread,
            now=now,
        )


async def _deliver_waiting(
    *,
    results: Any,
    playbook: LaunchPlaybook,
    read_product: Callable[..., Awaitable[Any]],
    deliver: Callable[..., Awaitable[Any]],
    now: datetime.datetime,
) -> None:
    """Post every pending result nothing has managed to post yet.

    The product and the step's name are resolved here rather than left to
    the adapter: the requirement is that the message *names the product
    and the step*, and a row carries only their identifiers. Delivering
    without them produces a message headed "an unnamed product", which
    names nothing a person can act on.

    A failure leaves `delivered_at` unstamped and the row standing, so the
    next pass tries again — the decoupling the daily briefing already keeps
    between assembling a report and delivering it. Nothing is recorded
    either way: an undelivered proposal is not a decided one.
    """
    steps_by_id = {step.identifier: step for step in playbook.served_steps}
    for row in await results.undelivered():
        step_id = getattr(row, "step_id", None)
        step = steps_by_id.get(str(step_id))
        try:
            # The row carries the identifier as the database spells it; the
            # catalog read wants the value object. A stored row is read back
            # long after the pass that wrote it, so the conversion belongs
            # here rather than being assumed of whatever produced the row.
            product = await read_product(ProductId(str(getattr(row, "product_id", ""))))
            await deliver(
                result=row,
                product=product,
                step_name=step.name if step else None,
                step=step,
            )
        except Exception:
            _logger.warning(
                "automation pass: could not deliver the pending result for "
                "step '%s' on product '%s'; it still stands and will be "
                "delivered again",
                getattr(row, "step_id", "?"),
                getattr(row, "product_id", "?"),
                exc_info=True,
            )
            continue
        await results.mark_delivered(row, now)


async def _walk_launch(
    *,
    launch: Launch,
    playbook: LaunchPlaybook,
    handlers: Any,
    results: Any,
    record_outcome: Callable[..., Awaitable[Any]],
    read_product: Callable[..., Awaitable[Any]],
    deliver: Callable[..., Awaitable[Any]],
    backoff: Any,
    notifier: Any,
    establish_thread: Callable[..., Awaitable[tuple[str, str | None]]],
    now: datetime.datetime,
) -> None:
    if launch.current_gate == "graduated":
        return

    product: Any = None
    for step in _automated_steps(playbook):
        if _is_settled(launch, step):
            continue

        # Before the backoff read and before the handler is resolved, so
        # an unreleased step costs no read, produces no stuck-step report,
        # and is not named every pass for an unregistered handler it will
        # not be asked to run for several gates yet. It has not failed to
        # make progress — it has not been asked to. The startup
        # registration report is where an unregistered handler is named
        # meanwhile.
        if not launch.has_released(playbook, step):
            continue

        row, row_ok = await _contained(
            backoff=backoff,
            what="reading the backoff record",
            launch=launch,
            step=step,
            call=lambda step=step: backoff.read(launch.product_id, step.identifier),  # type: ignore[misc]
        )
        governs = row_ok and _governs(row, launch, step)
        noted_at = _row_moment(row) if governs else None
        cooled = noted_at is not None and now - noted_at < REPEAT_COOL_OFF

        # A step already cooled off is not invoked, so its report cannot
        # ride along with an invocation. It is owed one all the same
        # whenever the last pass could not deliver it — a failed delivery,
        # or a read that could not say whether it had been delivered.
        if cooled and not _row_reported(row):
            if product is None:
                product = await read_product(launch.product_id)
            await _report_stuck_step(
                launch=launch,
                step=step,
                produced=_recorded_result(launch, step),
                backoff=backoff,
                notifier=notifier,
                establish_thread=establish_thread,
                product=product,
                now=now,
            )

        if not await _is_open(
            launch=launch, step=step, results=results, cooled=cooled, now=now
        ):
            continue

        handler = _resolve(handlers, step, launch)
        if handler is None:
            continue

        # Read the catalog once per launch, and only where a step actually
        # needs resolving: a pass over launches with nothing open should
        # cost no catalog reads at all.
        if product is None:
            product = await read_product(launch.product_id)

        # Read before the handler runs and before `_settle` replaces it:
        # a repeat is the proposed outcome against the one *already*
        # recorded.
        carried = launch.progress_for(step.identifier)

        resolution = await _invoke(
            handler=handler, step=step, launch=launch, product=product, now=now
        )
        if resolution is None:
            continue

        await _settle(
            launch=launch,
            step=step,
            resolution=resolution,
            handler_name=str(step.handler),
            results=results,
            record_outcome=record_outcome,
            deliver=deliver,
            now=now,
        )

        await _note_repeat(
            launch=launch,
            step=step,
            carried=carried,
            resolution=resolution,
            already_reported=governs and _row_reported(row),
            row_ok=row_ok,
            backoff=backoff,
            notifier=notifier,
            establish_thread=establish_thread,
            product=product,
            now=now,
        )


def _recorded_result(launch: Launch, step: StepDefinition) -> str:
    """What the handler produced, as the recording kept it.

    `_settle` records a non-terminal outcome with `evidence=resolution.result`,
    so the produced text is on the launch's own record — which is what
    lets a pass report a step it did not invoke.
    """
    progress = launch.progress_for(step.identifier)
    if progress is None:
        return ""
    return progress.provenance.evidence


async def _note_repeat(
    *,
    launch: Launch,
    step: StepDefinition,
    carried: Any,
    resolution: StepResolution,
    already_reported: bool,
    row_ok: bool,
    backoff: Any,
    notifier: Any,
    establish_thread: Callable[..., Awaitable[tuple[str, str | None]]],
    product: Any,
    now: datetime.datetime,
) -> None:
    """Note a handler repeating itself, and report the step the first time.

    A repeat is established from *two* recordings, never predicted from
    one: whether a handler has more to say is not knowable without asking
    it, so a step reporting a non-terminal outcome for the first time
    stays eligible. That deliberately spends one further invocation on a
    step that turns out to be stuck, which is exactly what distinguishes
    it from a step that is progressing.
    """
    outcome = resolution.outcome
    if _is_terminal_for(step, outcome) or _is_any_terminal(outcome):
        return
    if carried is None:
        return
    kind = _outcome_kind(outcome)
    if kind is not _outcome_kind(carried.outcome):
        return

    _, noted = await _contained(
        backoff=backoff,
        what="noting a repeat in the backoff record",
        launch=launch,
        step=step,
        call=lambda: backoff.note(launch.product_id, step.identifier, kind, now),
    )
    # Reporting degrades toward *silence*, the opposite of invocation: a
    # pass that could not read the row cannot know whether this step has
    # already been reported, and a report that cannot be recorded as
    # delivered cannot be delivered *once*. Attempting one anyway would
    # turn a store outage into a message every fifteen minutes — the
    # repetition the report-once rule exists to prevent. Nothing is lost:
    # the step is reported on the first pass that can read the row again.
    if not (row_ok and noted) or already_reported:
        return

    await _report_stuck_step(
        launch=launch,
        step=step,
        produced=resolution.result,
        backoff=backoff,
        notifier=notifier,
        establish_thread=establish_thread,
        product=product,
        now=now,
    )


def _stuck_step_message(
    *, launch: Launch, step: StepDefinition, produced: str, product: Any
) -> str:
    named = getattr(product, "name", None) or getattr(product, "sku", None)
    return (
        f"An automated launch step has stopped making progress — "
        f"'{step.name}' ({step.identifier}) on "
        f"{named or launch.product_id}. Its handler reported the same "
        f"thing twice running, so it will not be asked again for a day. "
        f"It needs something a person can supply.\n\n"
        f"What the handler produced:\n{produced}"
    )


async def _report_stuck_step(
    *,
    launch: Launch,
    step: StepDefinition,
    produced: str,
    backoff: Any,
    notifier: Any,
    establish_thread: Callable[..., Awaitable[tuple[str, str | None]]],
    product: Any,
    now: datetime.datetime,
) -> None:
    """Report the step, then record that it was reported — in that order.

    The stamp is written only after a delivery succeeds. Recording first
    and then failing to deliver would silence the step for exactly as
    long as it stays stuck, since the row is lifted by the step *moving*
    and not by Slack recovering.
    """
    if notifier is None:
        _logger.error(
            "automation pass: step '%s' on product '%s' has stopped making "
            "progress but no monitoring notifier is configured; the report "
            "was not delivered",
            step.identifier,
            launch.product_id,
        )
        return
    message = _stuck_step_message(
        launch=launch, step=step, produced=produced, product=product
    )
    try:
        sku_value = ""
        marketplace_value = ""
        if product:
            sku = getattr(product, "sku", None)
            sku_value = sku.value if sku else ""
            marketplace = getattr(product, "marketplace_id", None)
            marketplace_value = marketplace.value if marketplace else ""
        thread_ts, mention = await establish_thread(
            launch.product_id,
            product.name if product else str(launch.product_id),
            sku_value,
            marketplace_value,
            step=step,
        )
        mention_tag = f" <@{mention}>" if mention else ""
        await notifier.post_monitoring_message(
            channel=launches_channel(),
            text=mention_tag + message,
            thread_ts=thread_ts,
        )
    except Exception:
        _logger.warning(
            "automation pass: could not report that step '%s' on product "
            "'%s' has stopped making progress; nothing is recorded as "
            "reported and the next pass tries again",
            step.identifier,
            launch.product_id,
            exc_info=True,
        )
        return
    await _contained(
        backoff=backoff,
        what="stamping the backoff record as reported",
        launch=launch,
        step=step,
        call=lambda: backoff.mark_reported(launch.product_id, step.identifier, now),
    )


async def _contained(
    *,
    backoff: Any,
    what: str,
    launch: Launch,
    step: StepDefinition,
    call: Callable[[], Awaitable[Any]],
) -> tuple[Any, bool]:
    """Run one backoff-record access, containing a fault.

    Returns `(value, ok)`. A failure is logged, the shared store is
    restored, and `ok` is False — the caller then degrades in whichever
    direction *it* degrades, which is not the same direction for both
    callers (see `_is_open` and `_report_stuck_step`).

    The restore is the part that is easy to omit and impossible to do
    without. This record is touched per step *inside* the walk, so a
    failed statement left unrestored makes every later `record_outcome`
    in the pass fail — the pass writing nothing while reporting success.
    That is `c8bca97`'s fault in a worse place than the one it was fixed
    for. Where the restore itself fails there is nothing left to do but
    stop, which `BackoffStoreUnrestorable` does.
    """
    try:
        return await call(), True
    except Exception:
        _logger.warning(
            "automation pass: %s failed for step '%s' on product '%s'; the "
            "step is treated as it would have been before the repeat "
            "cool-off existed, and the pass continues",
            what,
            step.identifier,
            launch.product_id,
            exc_info=True,
        )
    try:
        await backoff.rollback()
    except Exception as unrestorable:
        raise BackoffStoreUnrestorable(
            f"the backoff record's store could not be restored after {what} "
            f"failed for step '{step.identifier}' on product "
            f"'{launch.product_id}'; the pass ends here rather than walk on "
            f"against a store that cannot record"
        ) from unrestorable
    return None, False


async def _is_open(
    *,
    launch: Launch,
    step: StepDefinition,
    results: Any,
    cooled: bool,
    now: datetime.datetime,
) -> bool:
    """The four conditions the requirement names, in one place.

    `cooled` — the fourth — is decided by the caller rather than read
    here, because the same row also decides whether the step is owed a
    report, and reading it twice per step would double the cost of the
    cheapest thing this pass does.
    """
    if _is_settled(launch, step):
        return False
    if cooled:
        return False
    if await results.pending_for(launch.product_id, step.identifier) is not None:
        # A step awaiting a person is not a step awaiting more work, and a
        # second result would leave two proposals and no way to say which
        # was decided.
        return False
    rejection = await results.latest_rejection(launch.product_id, step.identifier)
    if rejection is not None:
        decided_at = getattr(rejection, "decided_at", None) or getattr(
            rejection, "produced_at", None
        )
        if decided_at is not None and now - decided_at < COOL_OFF:
            return False
    return True


def _resolve(handlers: Any, step: StepDefinition, launch: Launch) -> Any | None:
    """The step's handler, or None having reported why it is unresolvable.

    Advisory, exactly as the startup handler report is: a step nothing can
    resolve is a deployment fault worth naming, never a reason to stop
    resolving everything else.
    """
    # Asked as a membership question, not by resolving and checking for
    # None: "does this deployment register the name" is what the
    # requirement is about, and it is the question every registry answers
    # the same way — `resolve` is free to raise for a name it never held.
    name = step.handler
    handler = handlers.resolve(name) if name is not None and name in handlers else None
    if handler is None:
        _logger.warning(
            "automation pass: step '%s' on product '%s' names handler '%s', "
            "which this deployment does not register; it will not resolve "
            "until the handler is registered or the step leaves 'active'",
            step.identifier,
            launch.product_id,
            name,
        )
        return None
    return handler


async def _invoke(
    *,
    handler: Any,
    step: StepDefinition,
    launch: Launch,
    product: Any,
    now: datetime.datetime,
) -> StepResolution | None:
    """Run the handler, or report the crash and resolve nothing.

    A failure records no outcome at all, `Blocked` included: a step nothing
    could evaluate has not been evaluated, and a crash written down as a
    handler's own judgement would hide the fault behind a plausible launch
    state.
    """
    context = StepContext(step=step, launch=launch, product=product, as_of=now)
    try:
        resolution: StepResolution = await handler(context)
        return resolution
    except Exception:
        _logger.warning(
            "automation pass: handler '%s' failed resolving step '%s' on "
            "product '%s'; nothing is recorded for it and the pass continues",
            step.handler,
            step.identifier,
            launch.product_id,
            exc_info=True,
        )
        return None


async def _settle(
    *,
    launch: Launch,
    step: StepDefinition,
    resolution: StepResolution,
    handler_name: str,
    results: Any,
    record_outcome: Callable[..., Awaitable[Any]],
    deliver: Callable[..., Awaitable[Any]],
    now: datetime.datetime,
) -> None:
    outcome = resolution.outcome
    terminal = _is_terminal_for(step, outcome)

    if not terminal and _is_any_terminal(outcome):
        # Terminal in the vocabulary, but not for this hazard: a fault at
        # production time rather than at recording time, so it is visible
        # now instead of failing on every press of accept, forever.
        _logger.warning(
            "automation pass: handler '%s' proposed '%s' for step '%s' on "
            "product '%s', which its hazard '%s' does not permit as "
            "terminal; the proposal is refused, nothing is recorded and "
            "nothing is stored",
            handler_name,
            _name_of(outcome),
            step.identifier,
            launch.product_id,
            step.hazard.value,
        )
        return

    if terminal and step.confirmer is not None:
        await results.store(
            product_id=launch.product_id,
            step_id=step.identifier,
            handler=handler_name,
            proposed_outcome=outcome,
            result_text=resolution.result,
            produced_at=now,
        )
        return

    await record_outcome(
        product_id=launch.product_id,
        step_id=step.identifier,
        outcome=outcome,
        provenance=Provenance(
            source=_AUTOMATED_SOURCE,
            who=handler_name,
            when=now,
            evidence=resolution.result,
        ),
    )


def _is_any_terminal(outcome: Any) -> bool:
    """Whether the outcome is terminal for *some* hazard.

    Separates "this handler proposed a conclusion the step forbids" from
    "this handler reported no conclusion", which the two branches above
    must not confuse: the first is a fault, the second is ordinary.
    """
    kind = outcome if isinstance(outcome, type) else type(outcome)
    return any(kind in permissible_terminal_outcomes(hazard) for hazard in Hazard)


def _name_of(outcome: Any) -> str:
    kind = outcome if isinstance(outcome, type) else type(outcome)
    return getattr(kind, "__name__", str(outcome))


async def _read_product_or_fail(product_id: Any) -> Any:
    if read_product is None:
        raise RuntimeError(
            "the automation pass needs the catalog product a handler is "
            "given, but no product reader was injected; `worker.py` "
            "supplies one after `register_all()`"
        )
    return await read_product(product_id)


@register_scheduled(
    name=TASK_NAME,
    schedule=AUTOMATION_SCHEDULE,
    tolerance=AUTOMATION_TOLERANCE,
)
async def resolve_automated_steps(timestamp: int) -> None:
    """Resolve every open automated step of every active launch.

    A run that completed its walk is a successful run whatever individual
    handlers or deliveries did: `scheduled-jobs`' retry and overdue
    reporting answer whether the pass is running, not whether every step
    within it resolved. A handler that failed is reported and reconsidered
    on the next pass, which is the retry.
    """
    async with session() as db_session:
        launches = LaunchRepository(db_session)
        # The playbook is live and read per pass — every launch resolves
        # against the same served set, whatever version stamp it recorded.
        playbook = await PlaybookRepository(db_session).get("live")
        record = functools.partial(
            record_step_outcome,
            launches,
            ServedPlaybooks(playbook),
            journal=LaunchJournalRepository(db_session),
        )
        await run_automation_pass(
            launches=launches,
            playbook=playbook,
            handlers=HANDLERS,
            results=AutomatedResultRepository(db_session),
            record_outcome=record,
            read_product=_read_product_or_fail,
            deliver=automation_confirmation.deliver_pending_result,
            backoff=AutomatedStepBackoffRepository(db_session),
            notifier=notifier,
            establish_thread=establish_thread_and_resolve_mention,
            now=datetime.datetime.now(datetime.UTC),
        )
