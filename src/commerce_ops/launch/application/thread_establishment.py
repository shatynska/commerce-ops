"""Operations for establishing and using a launch's Slack thread.

`thread-launch-slack-notifications` consolidates per-launch messages into
dedicated Slack threads. This module provides:

1. Lazy thread establishment: the first per-product message posts an anchor
   (product name, SKU, marketplace, launch date) and records the thread ID
   for reuse by subsequent messages; concurrent callers race under an
   advisory lock and produce exactly one anchor.

2. Mention resolution: who to tag in a message — the step's confirmer if
   it names one, else the launch's submitter.
"""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from slack_sdk.web.async_client import AsyncWebClient

from commerce_ops.launch.application.playbook_authoring import (
    RosterReader,
    person_identifier,
)
from commerce_ops.launch.application.ports import LaunchStore
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from commerce_ops.launch.domain.launch_playbook import StepDefinition

__all__ = ["ensure_launch_thread", "resolve_mention_target"]


@functools.lru_cache
def _get_slack_client() -> AsyncWebClient:
    return AsyncWebClient(token=os.environ["PRODUCT_AGENT_SLACK_BOT_TOKEN"])


async def ensure_launch_thread(
    db_session: AsyncSession,
    launch_store: LaunchStore,
    product_id: ProductId,
    product_name: str,
    product_sku: str,
    product_marketplace: str,
    *,
    hold_lock: Callable[[AsyncSession, ProductId], Any],
    channel: Callable[[], str],
) -> str:
    """Establish or reuse a launch's Slack thread, returning its reference.

    Posts an anchor message naming the product, SKU, marketplace, and launch
    date the first time this is called for a launch; concurrent callers race
    under an advisory lock and produce exactly one anchor. Later callers
    reuse the existing thread reference without posting a second anchor.

    Returns the thread reference (`ts`) as a string.
    """
    # Acquire the lock, reload the launch to re-check the thread reference
    # under lock, and post if absent.
    await hold_lock(db_session, product_id)
    launch = await launch_store.get_by_product_id(product_id)
    if launch is None:
        raise RuntimeError(f"no launch found for product {product_id.value}")
    if launch.slack_thread_id is not None:
        # Another caller won the race and established it first.
        return launch.slack_thread_id
    # Post the anchor message and persist the thread reference.
    anchor_text = _compose_anchor_message(
        product_name, product_sku, product_marketplace, launch.launch_date
    )
    # The anchor is posted as a top-level message in launches_channel;
    # the returned ts becomes the thread reference for this and all future
    # per-product messages.
    response = await _get_slack_client().chat_postMessage(
        channel=channel(), text=anchor_text
    )
    thread_ts: str = response["ts"]
    launch.slack_thread_id = thread_ts
    await launch_store.save(launch)
    return thread_ts


async def resolve_mention_target(
    launch: Launch,
    step: StepDefinition | None = None,
    *,
    roster: RosterReader | None = None,
) -> str | None:
    """Resolve who to tag in a launch message, as a Slack identity or nothing.

    Given a step naming a confirmer, resolves that confirmer **through the
    roster** to their Slack identity; otherwise returns the launch's
    `submitter`, which is already one (`slack_entry.py` records
    `body["user"]["id"]` at launch start).

    The returned value is a Slack identity usable in `<@identity>` syntax
    without further translation, or `None`. That is what this docstring
    always claimed and what the confirmer branch did not do: `step.confirmer`
    holds the roster's own generated identifier, which Slack cannot resolve
    and renders as inert literal text, so the two messages whose entire
    purpose is to notify a named person notified nobody.

    A named confirmer is resolvable for tagging only where the roster carries
    them, carries them with a Slack identity, and carries them **active**.
    The active condition is the one that occurs durably: deactivation keeps
    the entry's Slack identity intact, and a decision is accepted only from
    an active confirmer, so tagging a deactivated one summons a person whose
    accept and reject are certain to be refused.

    A gap resolves to `None` and is reported, never raised: what each caller
    does about a missing tag differs (the pending-result ask carries none,
    the stuck-step report substitutes the submitter and says so), and both
    need the message itself to go out regardless. This is deliberately the
    opposite disposition from `automation_confirmation._roster_or_fail`,
    which raises — there the roster read *is* the decision, here it is an
    embellishment on a message whose substance does not depend on it.
    """
    if step is None or not step.confirmer:
        # The submitter needs no translation, so this branch never reads the
        # roster. That is what keeps the gate ask, the launch confirmation
        # and every step naming no confirmer working through a roster outage
        # or a composition root that never injected a reader.
        return launch.submitter
    return await _slack_identity_of(
        step.confirmer, launch=launch, step=step, roster=roster
    )


async def _slack_identity_of(
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    roster: RosterReader | None,
) -> str | None:
    """One roster identifier translated to a Slack identity, or `None` and a report.

    Every gap names the step, the launch and the confirmer that could not be
    resolved — the trade `clickup_sync._clickup_users` already makes for an
    assignee with no ClickUp account, and for the same reason: a failure
    here would hide a data gap behind a retry, and the run record only says
    whether the pass succeeded.
    """
    people = await _people_or_none(confirmer, launch=launch, step=step, roster=roster)
    if people is None:
        return None

    for person in people:
        try:
            identifier = person_identifier(person)
        except ValueError:
            continue
        if identifier != confirmer:
            continue
        slack_identity = getattr(person, "slack_identity", None)
        if not slack_identity:
            # Defence-in-depth, not a state the specifications say occurs:
            # `roster` requires every entry to carry a non-empty Slack
            # identity and `Person.faults()` enforces it. Kept because it
            # costs one condition and is what a reader looks for.
            _report_gap(
                "the roster carries them without a Slack identity",
                confirmer,
                launch=launch,
                step=step,
            )
            return None
        if not getattr(person, "active", True):
            _report_gap(
                "they are deactivated on the roster, so a decision could not "
                "be accepted from them in any case",
                confirmer,
                launch=launch,
                step=step,
            )
            return None
        return str(slack_identity)

    _report_gap("the roster does not carry them", confirmer, launch=launch, step=step)
    return None


async def _people_or_none(
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    roster: RosterReader | None,
) -> tuple[Any, ...] | None:
    """Everyone the roster carries, or `None` and a report where it cannot be read.

    Covers all three ways the delta names — no reader at all, a reader of the
    wrong shape, and one that fails — because they fail at three different
    points and catching one is not catching the others.
    """
    if roster is None:
        _report_gap(
            "no roster reader is wired into this process, so nothing could "
            "translate the identifier",
            confirmer,
            launch=launch,
            step=step,
        )
        return None
    lister = getattr(roster, "list_people", None)
    if lister is None:
        _report_gap(
            f"the roster collaborator {type(roster).__name__} answers no "
            "`list_people()`, which is a wiring fault rather than a fact "
            "about the confirmer",
            confirmer,
            launch=launch,
            step=step,
        )
        return None
    try:
        return tuple(await lister())
    except Exception:  # noqa: BLE001 — an unreadable roster still sends the message
        _report_gap(
            "the roster could not be read",
            confirmer,
            launch=launch,
            step=step,
            with_traceback=True,
        )
        return None


def _report_gap(
    why: str,
    confirmer: str,
    *,
    launch: Launch,
    step: StepDefinition,
    with_traceback: bool = False,
) -> None:
    _logger.warning(
        "step '%s' on product '%s' names confirmer '%s', who cannot be tagged: "
        "%s; the message is delivered without that mention",
        step.identifier,
        launch.product_id.value,
        confirmer,
        why,
        exc_info=with_traceback,
    )


def _compose_anchor_message(
    product_name: str, product_sku: str, product_marketplace: str, launch_date: Any
) -> str:
    """Compose the anchor message for a launch thread."""
    date_str = launch_date.isoformat() if launch_date else "TBD"
    return (
        f"*{product_name}*\n"
        f"SKU: {product_sku}\n"
        f"Marketplace: {product_marketplace}\n"
        f"Launch Date: {date_str}"
    )
