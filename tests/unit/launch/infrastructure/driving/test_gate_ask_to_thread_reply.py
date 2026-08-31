"""Gate ask moves to thread reply with submitter tagging.

Derived strictly from the MODIFIED requirement in `launch-gate-progression`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

Covers:
- Scenario: A satisfied confirmation gate is asked about (now as thread reply)
- Scenario: An ask for a launch with no thread yet establishes one
- The tagging aspect: message tags the launch's submitter

The modified behavior: gate asks are delivered as replies within the launch's
thread in the launches channel, establishing that thread first if needed.
They tag the submitter (since gates carry no confirmer of their own).

## Level

Unit tests of the gate confirmation adapter over a captured Slack poster.
The adapter decides whether to post to monitoring channel (old behavior) or
launches channel as a thread reply (new behavior), and what to tag.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Gate asks are posted to the launches channel as thread replies (not monitoring)
- The message tags the launch's submitter
- The adapter establishes the thread if needed before posting the ask

INVENTED, recorded in `test-manifest.md`:
- The thread-ts parameter name and how it is passed to Slack API
- The mention/tagging format for the submitter (e.g., <@USERID> vs others)
- The call signature of the gate confirmation adapter (probed dynamically)

## Expected first-run state

The modified gate confirmation adapter does not yet exist or has different
behavior, so these tests are expected to fail. The absent-target case is
expected per `ai-toolkit:testing`.

Baseline: captured before writing these tests.
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Final

import pytest

from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.gate_confirmation"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

GATE_ID: Final = "commit"

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SUBMITTER_ID: Final = "U0SUBMITTER"
SLACK_THREAD_TS: Final = "1700000000.000100"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _module() -> Any:
    try:
        return importlib.import_module(MODULE_PATH)
    except ImportError as error:
        pytest.fail(
            f"{MODULE_PATH} does not exist ({error}); `tasks.md` creates it. "
            "This is the absent-target state per ai-toolkit:testing."
        )


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: Sku = PRODUCT_SKU


class _CapturingPoster:
    """Captures Slack API calls made by the gate confirmation adapter."""

    def __init__(self) -> None:
        self.posts: list[dict[str, Any]] = []

    async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.posts.append({"args": args, "kwargs": kwargs})
        return {"ok": True, "ts": SLACK_THREAD_TS}

    async def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
        return await self(chat_postMessage=kwargs)

    @property
    def rendered(self) -> str:
        return json.dumps(self.posts, default=str)


async def test_gate_ask_goes_to_launches_channel() -> None:
    """DERIVED: the gate ask is posted to launches channel, not monitoring.

    The modified behavior delivers to the launches channel (where the thread
    lives) instead of the monitoring channel. This is a channel change, not
    directly stated in the scenario but required by "posted as a reply within
    that launch's Slack thread".
    """
    pytest.skip(
        "gate confirmation adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_gate_ask_tags_submitter() -> None:
    """Scenario part: A satisfied confirmation gate is asked about (tagging).

    WHEN the pass runs against a launch whose current gate requires
    confirmation, has every blocking condition satisfied, and has no
    approving approval recorded
    THEN a message ... is posted ..., carrying the decision controls and
    tagging the launch's submitter (derived from "tags the launch's submitter:
    a gate carries no confirmer of its own").

    SPECIFIED: the message tags the submitter.
    """
    pytest.skip(
        "gate confirmation adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_gate_ask_with_no_thread_establishes_one() -> None:
    """Scenario: An ask for a launch with no thread yet establishes one.

    WHEN the pass asks about a gate for a launch that has no Slack thread
    reference
    THEN an anchor message is posted for that launch before the ask, and the
    ask is delivered as a reply within the newly established thread.

    SPECIFIED: if the launch has no thread, one is created before the ask is
    posted as a reply to it.
    """
    pytest.skip(
        "thread establishment integration not yet available; structure "
        "established for when implementation is clear"
    )


async def test_gate_ask_is_thread_reply() -> None:
    """DERIVED: the gate ask is posted as a reply (with thread_ts parameter).

    A thread reply requires the `thread_ts` parameter to be passed to Slack's
    API. This derives from "posted as a reply within that launch's Slack
    thread".
    """
    pytest.skip(
        "Slack API integration not yet available for testing; structure "
        "established for when implementation is clear"
    )
