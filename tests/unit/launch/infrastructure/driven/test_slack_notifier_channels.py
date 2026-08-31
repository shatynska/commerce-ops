"""Slack notifier exposes channel references for both monitoring and launches.

Derived strictly from the delta spec of `thread-launch-slack-notifications`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

This file tests the infrastructure layer's Slack notifier as it gains support
for a second channel (`launches_channel()` alongside the existing
`monitoring_channel()`), required for the lazy-establishment behavior and
thread-reply delivery in the modified capabilities.

Covers as derived (inferred from the change's impact statement): the notifier
exposes a callable that returns the launches channel ID, and that it reads from
`PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` (already provisioned per the proposal).

## Level

These are unit tests of the notifier module itself, without persistence or
network calls. The channel functions are pure environment reads and are the
smallest unit observable.

## Expected first-run state

The `launches_channel()` function does not yet exist in `slack_notifier.py`,
so these tests are expected to fail on an absent target (`AttributeError`).
Per `ai-toolkit:testing`, that establishes absence only.

Baseline: run before writing any test.
"""

from __future__ import annotations

from typing import Final

import pytest

from commerce_ops.launch.infrastructure.driven import slack_notifier

LAUNCHES_CHANNEL_ID: Final = "C0LAUNCHES"


def test_launches_channel_reads_environment_variable(monkeypatch: pytest.MonkeyPatch) -> None:
    """DERIVED: the launches channel ID is read from the environment.

    This parallels the existing `monitoring_channel()` pattern.
    """
    monkeypatch.setenv("PRODUCT_AGENT_LAUNCHES_CHANNEL_ID", LAUNCHES_CHANNEL_ID)

    channel = slack_notifier.launches_channel()

    assert channel == LAUNCHES_CHANNEL_ID


def test_monitoring_channel_remains_available(monkeypatch: pytest.MonkeyPatch) -> None:
    """The existing `monitoring_channel()` is unchanged by this change.

    SPECIFIED: `monitoring_channel()` continues to work as before.
    """
    monitoring_id = "C0MONITORING"
    monkeypatch.setenv("PRODUCT_AGENT_MONITORING_CHANNEL_ID", monitoring_id)

    channel = slack_notifier.monitoring_channel()

    assert channel == monitoring_id
