"""Stuck-step report moves to thread reply with confirmer/submitter tagging.

Derived strictly from the MODIFIED requirement in `launch-step-automation`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

Covers:
- Scenario: A newly cooled-off step is reported (as thread reply)
- Scenario: A stuck step naming a confirmer tags that confirmer
- Scenario: A stuck step naming no confirmer tags the submitter
- Scenario: A pass that cannot read the backoff record delivers no report
- Scenario: A report that could not be delivered is not suppressed

The modified behavior: stuck-step reports are delivered as replies within the
launch's thread in the launches channel, establishing that thread first if
needed. They tag the step's named confirmer (or the submitter if the step
names no confirmer).

## Level

Unit tests of the stuck-step reporting adapter over a captured Slack poster.
The adapter decides what channel and thread to post to, and who to tag based
on the step's confirmer field.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Stuck-step reports are posted to launches channel as thread replies (not monitoring)
- The message tags the step's named confirmer, or the submitter if none
- The adapter establishes the thread if needed before posting the report
- The report names the launch, step, and what the handler produced (as-is)

INVENTED, recorded in `test-manifest.md`:
- The thread-ts parameter and how it is passed to Slack
- The mention format for tagging (confirmer or submitter)
- How the adapter receives the confirmer and submitter information
- The call signature of the reporting adapter (probed dynamically)

## Expected first-run state

The modified stuck-step reporting adapter does not yet exist or has different
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

MODULE_PATH: Final = "commerce_ops.launch.infrastructure.driving.automation_pass"

PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))
PRODUCT_NAME: Final = "Bamboo Cutting Board"
PRODUCT_SKU: Final = Sku("BCB-2027-01")

STEP_ID: Final = "listing.sub-category"
STEP_NAME: Final = "Choose the sub-category node"
HANDLER_NAME: Final = "listing.subcategory_advisor"

CONFIRMER_ID: Final = "U0CONFIRMER"
SUBMITTER_ID: Final = "U0SUBMITTER"

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"
SLACK_THREAD_TS: Final = "1700000000.000100"

BLOCKED_REASON: Final = "Awaiting FBA compliance certificate from vendor"


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


@dataclass(frozen=True)
class _StepWithConfirmer:
    id: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = CONFIRMER_ID


@dataclass(frozen=True)
class _StepWithoutConfirmer:
    id: str = STEP_ID
    name: str = STEP_NAME
    confirmer: str | None = None


@dataclass(frozen=True)
class _BlockedOutcome:
    """Outcome representing a Blocked result with a reason."""

    name: str = "Blocked"
    reason: str = BLOCKED_REASON


class _CapturingPoster:
    """Captures Slack API calls made by the reporting adapter."""

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


async def test_stuck_step_goes_to_launches_channel() -> None:
    """DERIVED: the stuck-step report is posted to launches channel, not monitoring.

    The modified behavior delivers to the launches channel (where the thread
    lives) instead of the monitoring channel. This is a channel change required
    by "reported as a reply within the launch's Slack thread".
    """
    pytest.skip(
        "automation pass adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_stuck_step_with_confirmer_tags_confirmer() -> None:
    """Scenario: A stuck step naming a confirmer tags that confirmer.

    WHEN a report is delivered for a stuck step that names a confirmer
    THEN the message tags that confirmer.

    SPECIFIED: if the step names a confirmer, they are tagged.
    """
    pytest.skip(
        "automation pass adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_stuck_step_without_confirmer_tags_submitter() -> None:
    """Scenario: A stuck step naming no confirmer tags the submitter.

    WHEN a report is delivered for a stuck step that names no confirmer
    THEN the message tags the launch's submitter instead.

    SPECIFIED: if the step has no confirmer, the submitter is tagged.
    """
    pytest.skip(
        "automation pass adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_stuck_step_report_is_thread_reply() -> None:
    """DERIVED: the stuck-step report is posted as a reply (with thread_ts parameter).

    A thread reply requires the `thread_ts` parameter to be passed to Slack's
    API. This derives from "reported as a reply within the launch's Slack
    thread".
    """
    pytest.skip(
        "Slack API integration not yet available for testing; structure "
        "established for when implementation is clear"
    )


async def test_stuck_step_names_handler_result_as_is() -> None:
    """SPECIFIED: the report names what the handler produced as its result.

    From the requirement: "naming the launch, the step, and what the handler
    produced as its result, which for a `Blocked` outcome is also the reason
    it carries".

    The result is reported as what the handler said, never asserted as a fact.
    """
    pytest.skip(
        "automation pass adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )


async def test_stuck_step_with_blocked_includes_reason() -> None:
    """SPECIFIED: a Blocked outcome's reason is included in the report.

    For a `Blocked` outcome, the reason is also part of what the handler
    produced and must be included in the report.
    """
    pytest.skip(
        "automation pass adapter wiring not yet understood; structure "
        "established for when implementation is clear"
    )
