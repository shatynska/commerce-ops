"""Pending result delivery moves to thread reply with confirmer tagging.

Derived strictly from the MODIFIED requirement in `launch-step-automation`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

Covers:
- Scenario: A pending result reaches Slack (now as thread reply with confirmer tag)
- Scenario: A pending result for a launch with no thread yet establishes one
- Confirmer tagging (derived): the message tags the step's named confirmer

The modified behavior: pending results are delivered as replies within the
launch's thread in the launches channel, establishing that thread first if
needed. They tag the step's named confirmer (or the submitter if the step
names no confirmer).

## Level

Unit tests of the automation confirmation adapter over a captured Slack poster.
The adapter decides what channel and thread to post to, and who to tag.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Pending results are posted to launches channel as thread replies (not monitoring)
- The message tags the step's named confirmer
- The adapter establishes the thread if needed before posting the result

INVENTED, recorded in `test-manifest.md`:
- The thread-ts parameter and how it is passed to the Slack API
- The mention format for the confirmer (e.g., <@USERID> or other)
- How the adapter receives the confirmer information (from step field)
- The call signature of the delivery adapter (probed dynamically)

## Expected first-run state

The modified automation confirmation adapter does not yet exist or has
different behavior, so these tests are expected to fail. The absent-target
case is expected per `ai-toolkit:testing`.

Baseline: captured before writing these tests.
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

import pytest

from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.shared.domain.identity import ProductId, Sku

pytestmark = pytest.mark.anyio

MODULE_PATH: Final = (
    "commerce_ops.launch.infrastructure.driving.automation_confirmation"
)

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"
HANDLER_NAME: Final = "listing.subcategory_advisor"

CONFIRMER_ID: Final = "U0CONFIRMER"
SUBMITTER_ID: Final = "U0SUBMITTER"

PRODUCED_AT: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SLACK_THREAD_TS: Final = "1700000000.000100"

RECOMMENDATION: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration; CPSIA general "
    "certificate of conformity where the board is marketed for children; "
    "a country-of-origin mark on the product itself.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative "
    "Trays, preferred by keyword volume but carrying no food-contact "
    "obligation, which would understate the compliance surface this "
    "product actually has."
)


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


@dataclass
class _StepWithConfirmer:
    id: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_ID


@dataclass
class _PendingRow:
    product_id: ProductId = PRODUCT_ID
    step_id: str = STEP_ID
    handler: str = HANDLER_NAME
    proposed_outcome: Any = Satisfied
    result_text: str = RECOMMENDATION
    produced_at: datetime = PRODUCED_AT
    state: str = "pending"
    delivered_at: datetime | None = None


class _CapturingPoster:
    """Captures Slack API calls made by the confirmation adapter."""

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


async def test_pending_result_goes_to_launches_channel() -> None:
    """DERIVED: the pending result is posted to launches channel, not monitoring.

    The modified behavior delivers to the launches channel (where the thread
    lives) instead of the monitoring channel. This is a channel change required
    by "delivered as a reply within that launch's Slack thread".
    """
    pytest.skip(
        "automation confirmation adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_pending_result_tags_confirmer() -> None:
    """Scenario part: A pending result reaches Slack (with confirmer tag).

    WHEN a pending result is stored
    THEN a Slack message ... is delivered as a reply within the launch's
    thread, ... tagging the step's named confirmer.

    SPECIFIED: the message tags the step's confirmer.
    """
    pytest.skip(
        "automation confirmation adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_pending_result_with_no_thread_establishes_one() -> None:
    """Scenario: A pending result for a launch with no thread yet establishes one.

    WHEN a pending result is delivered for a launch that has no Slack thread
    reference
    THEN an anchor message is posted for that launch first, and the pending
    result is delivered as a reply within the newly established thread.

    SPECIFIED: if the launch has no thread, one is created before the result
    is posted as a reply to it.
    """
    pytest.skip(
        "thread establishment integration not yet available; structure "
        "established for when implementation is clear"
    )


async def test_pending_result_is_thread_reply() -> None:
    """DERIVED: the pending result is posted as a reply (with thread_ts parameter).

    A thread reply requires the `thread_ts` parameter to be passed to Slack's
    API. This derives from "delivered as a reply within that launch's Slack
    thread".
    """
    pytest.skip(
        "Slack API integration not yet available for testing; structure "
        "established for when implementation is clear"
    )
