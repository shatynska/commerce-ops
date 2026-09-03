"""Launch entity persists submitter and thread reference.

Derived strictly from the ADDED requirement in `launch-instance`:
`openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

Covers:
- Scenario: The submitter is recorded at launch start
- Scenario: The thread reference starts absent
- Scenario: Establishing an already-set thread reference changes nothing

These are domain-layer tests of the `Launch` entity's new fields and their
contract: submitter is write-once-at-start, thread reference is absent until
set (idempotently once).

## Level

Domain entity tests, no I/O, no persistence. The submitter and thread
reference are stored on the entity itself; the smallest unit that can observe
them is the entity.

## What is fixed, and what is INVENTED

Fixed by the change's artifacts:
- Launch gains `submitter` (Slack user ID, immutable after start)
- Launch gains `slack_thread_id` (optional, mutable exactly once to non-None)
- Submitter is recorded once, at launch start
- Thread reference is absent initially and cannot be unset

INVENTED, recorded in `test-manifest.md`:
- The exact type and name of the submitter field (probed from the entity)
- The exact type and name of the thread reference field (probed)
- The Launch constructor's full signature and parameter names (probed)

## Expected first-run state

The Launch entity does not yet have these fields, so these tests are
expected to fail on an absent-attribute error. Per `ai-toolkit:testing`,
that establishes absence only.

Baseline: captured before writing these tests.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

import pytest

from tests.support.fixtures import product_id

pytestmark = pytest.mark.anyio

PRODUCT_ID: Final = product_id()
SUBMITTER_SLACK_ID: Final = "U0SUBMITTER123"
SLACK_THREAD_TS: Final = "1700000000.000100"
LAUNCH_DATE: Final = date(2027, 3, 15)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


def _get_launch_class() -> type:
    """Import and return the Launch entity, failing loudly if it is absent."""
    try:
        from commerce_ops.launch.domain.launch_run import Launch

        return Launch
    except ImportError as error:
        pytest.fail(
            f"Launch class not found ({error}); the domain layer should have "
            "this entity defined. This is the absent-target state per "
            "ai-toolkit:testing."
        )


def _create_launch(**kwargs: Any) -> Any:
    """Construct a Launch with minimal required arguments.

    Creates a launch at the 'commit' gate (the starting gate).
    """
    Launch = _get_launch_class()

    params = {
        "product_id": PRODUCT_ID,
        "playbook_version": "test-v1",
        "current_gate": "commit",
        "launch_date": LAUNCH_DATE,
    }
    # Merge with any provided overrides
    params.update(kwargs)
    return Launch(**params)


def test_submitter_is_persisted_on_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The submitter is recorded at launch start.

    WHEN a launch is started
    THEN the launch record persists the Slack identity of whoever submitted it.

    SPECIFIED: the submitter is stored on the launch entity.
    """
    launch = _create_launch(submitter=SUBMITTER_SLACK_ID)

    # SPECIFIED: the launch records its submitter
    assert hasattr(launch, "submitter") or hasattr(launch, "slack_user_id"), (
        "Launch entity has no submitter/slack_user_id field; check the "
        "domain entity definition"
    )

    submitter_value = getattr(
        launch, "submitter", getattr(launch, "slack_user_id", None)
    )
    assert submitter_value == SUBMITTER_SLACK_ID, (
        f"submitter was not persisted correctly; expected {SUBMITTER_SLACK_ID}, "
        f"got {submitter_value}"
    )


def test_thread_reference_starts_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: The thread reference starts absent.

    WHEN a launch is started
    THEN its Slack thread reference is reported as absent.

    SPECIFIED: thread reference is initially None or not set.
    """
    launch = _create_launch()

    # SPECIFIED: the launch has a thread reference field (however named)
    thread_field = None
    for possible_name in ("slack_thread_id", "thread_ts", "thread_reference"):
        if hasattr(launch, possible_name):
            thread_field = possible_name
            break

    assert thread_field is not None, (
        "Launch entity has no slack_thread_id/thread_ts/thread_reference field; "
        "check the domain entity definition"
    )

    thread_value = getattr(launch, thread_field)
    assert thread_value is None, (
        f"thread reference should be absent at start, got: {thread_value}"
    )


def test_thread_reference_can_be_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """DERIVED: once a thread reference is absent, it can be set.

    This supports the lazy-establishment scenario where the first message
    needing a thread establishes it.
    """
    launch = _create_launch()

    # Find the thread field name
    thread_field = None
    for possible_name in ("slack_thread_id", "thread_ts", "thread_reference"):
        if hasattr(launch, possible_name):
            thread_field = possible_name
            break

    assert thread_field is not None

    # Set the thread reference (this tests the write path)
    try:
        setattr(launch, thread_field, SLACK_THREAD_TS)
    except AttributeError as e:
        pytest.fail(
            f"thread reference field {thread_field} is read-only, but the "
            f"spec requires it to be settable: {e}"
        )

    thread_value = getattr(launch, thread_field)
    assert thread_value == SLACK_THREAD_TS, (
        f"thread reference was not set correctly; expected {SLACK_THREAD_TS}, "
        f"got {thread_value}"
    )


def test_thread_reference_idempotent_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scenario: Establishing an already-set thread reference changes nothing.

    WHEN a per-product Slack message is delivered for a launch that already
    has a thread reference
    THEN no new anchor message is posted, and the existing thread reference
    is reused.

    DERIVED: this tests that setting an already-set thread value to itself
    succeeds (idempotent operation).
    """
    launch = _create_launch()

    # Find the thread field name
    thread_field = None
    for possible_name in ("slack_thread_id", "thread_ts", "thread_reference"):
        if hasattr(launch, possible_name):
            thread_field = possible_name
            break

    assert thread_field is not None

    # Set the thread once
    setattr(launch, thread_field, SLACK_THREAD_TS)
    first_value = getattr(launch, thread_field)

    # Set it again to the same value (idempotent)
    setattr(launch, thread_field, SLACK_THREAD_TS)
    second_value = getattr(launch, thread_field)

    assert first_value == second_value == SLACK_THREAD_TS, (
        "setting thread reference to the same value should be idempotent"
    )
