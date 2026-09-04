"""Letting a Slack request's deferred listener work finish before asserting.

Bolt acknowledges an Events API request and *then* runs the listener, as a
separate asyncio task: `process_before_response` is left at its `False`
default, so `AsyncioListenerRunner.run` schedules the listener with
`asyncio.ensure_future(...)` and returns the acknowledgement without awaiting
it (slack_bolt 1.30.0, `listener/asyncio_runner.py:137`). That is the specified
behaviour -- `slack-trigger`'s "Slack Events Are Acknowledged Within Slack's
Timeout" requires exactly it -- and nothing here changes it.

What it costs the tests is a race. `TestClient` returns to the calling thread
as soon as the response is sent, while the listener task is still only
scheduled on the portal's event loop, and there is no await between scheduling
it and returning: the ack has already been recorded, so the `while
ack.response is None` loop that would otherwise yield never runs. A test that
posts an event and immediately asserts on what the listener did is therefore
reading a task that may not have started. Measured at roughly one failure per
25 runs of the omni_agent driving directory, landing on a different test each
time; CI hit it as
`test_slack_events_endpoint.py::test_any_workspace_member_can_trigger_omni[another-arbitrary-member]`.

`DrainsDeferredListeners` closes the race without weakening what any test
observes. It awaits the tasks a request spawned only *after* the ASGI call has
returned, so the response -- and its ordering against the listener, which
`test_app_mention_is_acknowledged_before_answer_generation` asserts -- is
entirely unaffected. The negative assertions get stronger as a side effect:
"omni-agent was not invoked" now means the listener ran to completion and did
not invoke it, rather than possibly that it had not started yet.

This lived in two conftests, `launch/infrastructure/driving/` and
`omni_agent/infrastructure/driving/`. The first opened by declaring itself a
mirror of the second "exactly, for the same reason recorded there" and deferred
the whole argument to it -- one wrapper, one explanation, living in one of the
two copies. Both now hold a fixture that calls this.
"""

from __future__ import annotations

import asyncio
from typing import Any, Final

# Bounded so a task that never completes fails the test that is waiting on its
# effect, rather than hanging the suite. Generous relative to the work actually
# awaited here (a mocked answer and a mocked post), because the ceiling is only
# ever reached on failure.
DRAIN_TIMEOUT_SECONDS: Final = 5.0


class DrainsDeferredListeners:
    """ASGI wrapper that lets a request's deferred work finish.

    Task-set differencing rather than a poll on some expected effect: it waits
    for the actual task Bolt scheduled, so it neither needs to know what the
    listener was supposed to do nor returns early when the answer is that it
    should do nothing.
    """

    def __init__(self, inner: Any) -> None:
        self.inner = inner

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        before = asyncio.all_tasks()
        await self.inner(scope, receive, send)

        spawned = asyncio.all_tasks() - before - {asyncio.current_task()}
        if spawned:
            await asyncio.wait(spawned, timeout=DRAIN_TIMEOUT_SECONDS)
