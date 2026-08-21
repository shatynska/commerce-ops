"""Driven adapter: posts product-monitoring messages via the `product_agent`
Slack app.

Lazily constructs its `WebClient` (mirroring
`omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache`
pattern) so importing this module never requires
`PRODUCT_AGENT_SLACK_BOT_TOKEN`/`PRODUCT_AGENT_MONITORING_CHANNEL_ID` to be
set -- the PR-validation gate runs with neither present.
"""

from __future__ import annotations

import functools
import os

from slack_sdk import WebClient


@functools.lru_cache
def _get_slack_client() -> WebClient:
    return WebClient(token=os.environ["PRODUCT_AGENT_SLACK_BOT_TOKEN"])


def post_monitoring_message(message: str) -> None:
    channel = os.environ["PRODUCT_AGENT_MONITORING_CHANNEL_ID"]
    _get_slack_client().chat_postMessage(channel=channel, text=message)
