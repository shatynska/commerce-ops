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

**Terminality, not the confirmation flag, decides what is held.** A
non-terminal outcome is recorded directly whatever the step says about
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
from commerce_ops.launch.infrastructure.driven.launch_repository import (
    LaunchRepository,
)
from commerce_ops.launch.infrastructure.driven.playbook_repository import (
    PlaybookRepository,
    ServedPlaybooks,
)
from commerce_ops.launch.infrastructure.driving import automation_confirmation
from commerce_ops.shared.infrastructure.driven.database import session
from commerce_ops.shared.infrastructure.driven.recurring_work import register_scheduled

__all__ = [
    "AUTOMATION_SCHEDULE",
    "AUTOMATION_TOLERANCE",
    "COOL_OFF",
    "TASK_NAME",
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


async def run_automation_pass(
    *,
    launches: Any,
    playbook: LaunchPlaybook,
    handlers: Any,
    results: Any,
    record_outcome: Callable[..., Awaitable[Any]],
    read_product: Callable[..., Awaitable[Any]],
    deliver: Callable[..., Awaitable[Any]],
    now: datetime.datetime,
) -> None:
    """Deliver what is waiting, then resolve what is open."""
    active: Sequence[Launch] = await launches.list_active()

    await _deliver_waiting(results=results, deliver=deliver, now=now)

    for launch in active:
        await _walk_launch(
            launch=launch,
            playbook=playbook,
            handlers=handlers,
            results=results,
            record_outcome=record_outcome,
            read_product=read_product,
            deliver=deliver,
            now=now,
        )


async def _deliver_waiting(
    *, results: Any, deliver: Callable[..., Awaitable[Any]], now: datetime.datetime
) -> None:
    """Post every pending result nothing has managed to post yet.

    A failure leaves `delivered_at` unstamped and the row standing, so the
    next pass tries again — the decoupling the daily briefing already keeps
    between assembling a report and delivering it. Nothing is recorded
    either way: an undelivered proposal is not a decided one.
    """
    for row in await results.undelivered():
        try:
            await deliver(result=row)
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
    now: datetime.datetime,
) -> None:
    if launch.current_gate == "graduated":
        return

    product: Any = None
    for step in _automated_steps(playbook):
        if not await _is_open(launch=launch, step=step, results=results, now=now):
            continue

        handler = _resolve(handlers, step, launch)
        if handler is None:
            continue

        # Read the catalog once per launch, and only where a step actually
        # needs resolving: a pass over launches with nothing open should
        # cost no catalog reads at all.
        if product is None:
            product = await read_product(launch.product_id)

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


async def _is_open(
    *, launch: Launch, step: StepDefinition, results: Any, now: datetime.datetime
) -> bool:
    """The three conditions the requirement names, in one place."""
    if _is_settled(launch, step):
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

    if terminal and step.needs_confirmation:
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
            record_step_outcome, launches, ServedPlaybooks(playbook)
        )
        await run_automation_pass(
            launches=launches,
            playbook=playbook,
            handlers=HANDLERS,
            results=AutomatedResultRepository(db_session),
            record_outcome=record,
            read_product=_read_product_or_fail,
            deliver=automation_confirmation.deliver_pending_result,
            now=datetime.datetime.now(datetime.UTC),
        )
