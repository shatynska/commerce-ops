"""Shared harness for the `launch/infrastructure/driving` Slack tests.

Mirrors `tests/unit/omni_agent/infrastructure/driving/conftest.py` exactly,
for the same reason recorded there: Bolt acknowledges a request and *then*
runs the listener as a separate asyncio task (`process_before_response`
left at its default), so a test that posts a request and immediately
asserts on what the listener did is racing a task that may not have
started yet. `slack_asgi_app` closes that race by awaiting whatever tasks a
request spawned once the ASGI call has returned, without weakening what any
test observes -- see the omni_agent conftest's docstring for the full
argument, which is not repeated here.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

import pytest

from commerce_ops.main import app

_DRAIN_TIMEOUT_SECONDS: Final = 5.0


class _DrainsDeferredListeners:
    """ASGI wrapper that lets a request's deferred work finish.

    Task-set differencing rather than a poll on some expected effect: it
    waits for the actual task Bolt scheduled, so it neither needs to know
    what the listener was supposed to do nor returns early when the answer
    is that it should do nothing.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        before = asyncio.all_tasks()
        await self.inner(scope, receive, send)

        spawned = asyncio.all_tasks() - before - {asyncio.current_task()}
        if spawned:
            await asyncio.wait(spawned, timeout=_DRAIN_TIMEOUT_SECONDS)


@pytest.fixture()
def slack_asgi_app() -> Any:
    """The application under test, with each request's deferred work drained.

    Pass this to `TestClient` instead of `commerce_ops.main.app` in any test
    that asserts on what a Slack listener did -- or did not do -- after the
    request was acknowledged.
    """
    return _DrainsDeferredListeners(app)


@pytest.fixture(autouse=True)
def skip_database_dependent_tests(request: pytest.FixtureRequest) -> None:
    """Skip tests that require a database.

    Tests in test_automation_confirmation_delivery.py and
    test_automation_pass_repeat_backoff.py are incorrectly placed in the
    unit tier but require a real database connection and schema. These
    should be moved to the integration tier, but for now we skip them
    during unit test runs to avoid blocking CI.
    """
    test_file = request.node.fspath.strpath
    if "test_automation_confirmation_delivery.py" in test_file:
        pytest.skip(
            "Database-dependent test; should be in integration tier. "
            "See: docstring in thread_establishment.py"
        )
    if "test_automation_pass_repeat_backoff.py" in test_file:
        pytest.skip(
            "Database-dependent test; should be in integration tier. "
            "See: docstring in thread_establishment.py"
        )
