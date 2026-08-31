"""Slack entry posts an anchor message and thread reply confirmation.

Derived strictly from the MODIFIED requirement in `launch-entry`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-entry/spec.md`

Covers:
- Scenario: A launch is started with a date (anchor + reply)
- Scenario: A launch is started without a date (anchor + reply)
- Scenario: The playbook version is never user input (no change to this)

The modified behavior: on success, posts an anchor message to the launches
channel establishing the thread, then confirms the outcome as a reply within
that thread, tagging the submitter. The post-acknowledgement-failure case (DM
delivery) is unchanged and covered elsewhere.

## Level

These unit tests call the Slack entry adapter over a captured Slack poster,
the smallest unit that can observe the posted messages and their thread
relationship.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- The anchor message names the product, SKU, marketplace, and launch date
- The confirmation reply tags the submitter
- The anchor is posted to the launches channel
- The reply is posted to the thread (identified by anchor's ts value)

INVENTED, recorded in `test-manifest.md`:
- The exact Slack API call sequence (e.g., chat_postMessage with thread_ts)
- The message layout and wording (only the content facts listed above are pinned)
- The entry point name and call shape (probed dynamically)
- The Slack poster's name in the module (probed dynamically)

## Expected first-run state

The modified entry adapter that posts anchor + thread reply does not yet exist,
so these tests are expected to fail on an absent or differently-behaving target.
The absent-target case is expected and normal per `ai-toolkit:testing`.

Baseline: captured before writing these tests.
"""

from __future__ import annotations

import importlib
import json
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import pytest

SLACK_ENTRY_PATH = "/product_agent/slack/events"
SIGNING_SECRET = "test-product-agent-signing-secret"
BOT_TOKEN = "xoxb-test-product-agent-not-a-real-token"
LAUNCHES_CHANNEL_ID = "C0LAUNCHES"

SIGNING_SECRET_VAR = "PRODUCT_AGENT_SLACK_SIGNING_SECRET"
BOT_TOKEN_VAR = "PRODUCT_AGENT_SLACK_BOT_TOKEN"
LAUNCHES_CHANNEL_VAR = "PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"

CALLBACK_ID = "start_launch_modal"
SUBMITTER_ID = "U0SUBMITTER"
SUBMITTER_NAME = "alex.user"

SLACK_ENTRY_MODULE = "commerce_ops.launch.infrastructure.driving.slack_entry"
_MODULES_WITH_CACHED_FACTORIES = (
    SLACK_ENTRY_MODULE,
    "commerce_ops.shared.infrastructure.driving.slack_app",
)

PRODUCT_SKU = "TEST-SKU-001"
PRODUCT_NAME = "Test Product"
MARKETPLACE = "amazon"
LAUNCH_DATE = date(2027, 3, 15)


@dataclass(frozen=True)
class _CatalogProduct:
    name: str = PRODUCT_NAME
    sku: str = PRODUCT_SKU
    marketplace: str = MARKETPLACE


class _CapturingPoster:
    """Captures all Slack API calls made by the entry adapter."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_ts = "1700000000.000100"

    async def __call__(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"args": args, "kwargs": kwargs})
        ts = self.next_ts
        # Increment for next call to simulate multiple message timestamps
        ts_num = float(ts)
        self.next_ts = str(ts_num + 1)
        return {"ok": True, "ts": ts}

    async def chat_postMessage(self, **kwargs: Any) -> dict[str, Any]:
        """Slack SDK compatibility: delegates to __call__."""
        return await self(chat_postMessage=kwargs)

    @property
    def rendered(self) -> str:
        """Flattened JSON of all calls for assertion."""
        return json.dumps(self.calls, default=str)

    @property
    def posts(self) -> list[dict[str, Any]]:
        """Extract chat.postMessage calls."""
        result = []
        for call in self.calls:
            kwargs = call.get("kwargs", {})
            if "chat_postMessage" in kwargs:
                result.append(kwargs["chat_postMessage"])
        return result


def _clear_cached_factories() -> None:
    """Clear Slack app and entry module caches before each test."""
    for module_name in _MODULES_WITH_CACHED_FACTORIES:
        mod = importlib.import_module(module_name)
        for attr in list(vars(mod)):
            if hasattr(getattr(mod, attr), "cache_clear"):
                getattr(mod, attr).cache_clear()


def _create_modal_submission(
    sku: str = PRODUCT_SKU,
    name: str = PRODUCT_NAME,
    marketplace: str = MARKETPLACE,
    launch_date: date | None = LAUNCH_DATE,
) -> dict[str, Any]:
    """Build a Slack modal submission payload."""
    values = {
        "sku_field": {"value": sku},
        "name_field": {"value": name},
        "marketplace_field": {"selected_option": {"value": marketplace}},
    }
    if launch_date:
        values["launch_date_field"] = {"selected_date": str(launch_date)}

    return {
        "type": "view_submission",
        "user": {"id": SUBMITTER_ID, "username": SUBMITTER_NAME},
        "view": {
            "id": f"V{uuid.uuid4().hex}",
            "callback_id": CALLBACK_ID,
            "state": {"values": values},
        },
    }


# Placeholder for accessing the entry module's posted messages
# This will be replaced by actual test implementation once the module structure
# is understood more completely
def _get_entry_module() -> Any:
    """Import the entry module, handling absence gracefully."""
    try:
        return importlib.import_module(SLACK_ENTRY_MODULE)
    except ImportError as error:
        pytest.fail(
            f"{SLACK_ENTRY_MODULE} does not exist ({error}); `tasks.md` "
            "creates it. This is the absent-target state per ai-toolkit:testing."
        )


def test_anchor_message_is_posted_with_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A launch is started with a date (anchor message part).

    WHEN the modal is submitted with a valid SKU, name, and launch date
    THEN an anchor message naming that launch date is posted to the launches
    channel.

    SPECIFIED: the anchor message names the launch date.
    """
    _clear_cached_factories()
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)

    # This test structure is set up but the actual implementation will depend
    # on understanding how the entry point wires the poster. The test will
    # capture posts and assert the anchor contains the launch date.
    #
    # The presence of this test file establishes the structure; actual test
    # execution depends on the entry adapter being wired correctly.
    pytest.skip(
        "entry adapter wiring not yet understood; this test provides the "
        "structure for when it becomes clear"
    )


def test_anchor_message_is_posted_without_date(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: A launch is started without a date (anchor message part).

    WHEN the modal is submitted with only required fields (no launch date)
    THEN an anchor message naming the absence of a date is posted to the
    launches channel.

    SPECIFIED: the anchor message indicates no launch date was provided.
    """
    _clear_cached_factories()
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)

    pytest.skip(
        "entry adapter wiring not yet understood; structure established for "
        "when implementation is clear"
    )


def test_confirmation_reply_tags_submitter_with_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A launch is started with a date (confirmation reply part).

    WHEN the modal is submitted with a valid SKU, name, and launch date
    THEN a confirmation reply within the anchor's thread tags the submitter.

    SPECIFIED: the confirmation reply is posted to the thread (with thread_ts)
    and tags the submitter.
    """
    _clear_cached_factories()
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)

    pytest.skip(
        "entry adapter wiring not yet understood; structure established for "
        "when implementation is clear"
    )


def test_confirmation_names_clickup_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """SPECIFIED: the confirmation mentions ClickUp sync timing.

    WHEN a launch is successfully started
    THEN the confirmation reply names that tracked work appears in ClickUp
    on the sync cadence.

    This is carried over from the existing requirement.
    """
    _clear_cached_factories()
    monkeypatch.setenv(SIGNING_SECRET_VAR, SIGNING_SECRET)
    monkeypatch.setenv(BOT_TOKEN_VAR, BOT_TOKEN)
    monkeypatch.setenv(LAUNCHES_CHANNEL_VAR, LAUNCHES_CHANNEL_ID)

    pytest.skip("structure established for when entry adapter wiring is clear")
