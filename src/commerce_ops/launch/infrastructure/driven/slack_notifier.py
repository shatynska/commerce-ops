"""Driven adapter: posting a launch message to the monitoring channel.

Reads the same two variables the briefing's notifier reads
(`PRODUCT_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_MONITORING_CHANNEL_ID`)
and deliberately does **not** import it: `.importlinter`'s
`products-infrastructure-boundary` forbids `launch.infrastructure` from
naming `briefing` at all. Sharing a variable is not the same as sharing a
module, and the boundary is what keeps the second true while the first
stays convenient.

The client is constructed lazily, mirroring the `functools.lru_cache`
pattern `omni_agent`'s adapter and the briefing notifier both use, so
importing this module never requires either credential to be set — the
PR-validation gate imports the app with neither present and must succeed.
"""

from __future__ import annotations

import functools
import os
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

__all__ = ["monitoring_channel", "post_monitoring_message"]


@functools.lru_cache
def _get_slack_client() -> AsyncWebClient:
    return AsyncWebClient(token=os.environ["PRODUCT_AGENT_SLACK_BOT_TOKEN"])


def monitoring_channel() -> str:
    # A literal variable name, so the environment-drift check can see this
    # read — a read through a constant looks like a variable nobody uses.
    return os.environ["PRODUCT_AGENT_MONITORING_CHANNEL_ID"]


async def post_monitoring_message(
    *, channel: str, text: str, blocks: list[dict[str, Any]] | None = None
) -> None:
    """Post to the monitoring channel, optionally with interactive blocks.

    `text` is always sent even where blocks are: Slack uses it for the
    notification and for clients that cannot render blocks, so a
    blocks-only message arrives as a silent, empty-looking one.
    """
    if blocks is None:
        await _get_slack_client().chat_postMessage(channel=channel, text=text)
        return
    await _get_slack_client().chat_postMessage(
        channel=channel, text=text, blocks=blocks
    )
