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
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from slack_sdk.web.async_client import AsyncWebClient

from commerce_ops.launch.application.ports import LaunchStore
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.identity import ProductId

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
    channel: str,
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
        channel=channel, text=anchor_text
    )
    thread_ts: str = response["ts"]
    launch.slack_thread_id = thread_ts
    await launch_store.save(launch)
    return thread_ts


async def resolve_mention_target(
    launch: Launch, step: StepDefinition | None = None
) -> str | None:
    """Resolve who to tag in a launch message: the step's confirmer or the launch's submitter.

    Given a step, returns the step's `confirmer` if it names one; otherwise
    returns the launch's `submitter`. If neither is available (a step with
    no confirmer and a launch with no submitter), returns None — the message
    will be posted without a tag, and Slack will silently drop any unresolvable
    mention token.

    The returned value is a Slack identity (user ID) that can be used in
    `<@identity>` mention syntax.
    """
    if step is not None and step.confirmer:
        return step.confirmer
    return launch.submitter


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
