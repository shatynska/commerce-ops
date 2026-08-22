## Why

`README.md`'s Technology section names Slack Bolt as the Slack interface's technology. No Bolt is installed. `omni_agent/infrastructure/driving/slack.py` hand-rolls signature verification, event-type dispatch and the URL-verification challenge against raw `slack-sdk` instead.

That gap is about to widen. The pending `add-product-creation-clickup-task` change needs slash commands and modals, and its design.md commits to hand-rolling `application/x-www-form-urlencoded` parsing, the nested JSON inside the `payload` form field, a `views.open` call against Slack's ~3-second `trigger_id` budget, and `response_action: errors` for inline validation. Bolt provides every one of those directly. Building a second hand-rolled layer, then migrating both, costs more than migrating one now.

Two further defects are fixed on the way, because the migration touches the same code:

- **Blocking I/O on the event loop.** `products/infrastructure/driving/monitoring.py`'s `daily` route is `async def` and calls `post_monitoring_message()` synchronously, which calls `slack_sdk.WebClient.chat_postMessage()` — blocking HTTP. The event loop stalls for a full Slack round-trip on every daily run.
- **A graph rebuilt per message.** `omni_agent/application/use_cases.py`'s `answer_question` calls `build_production_graph()` on every invocation, constructing a `ChatOpenAI` and recompiling the graph each time, then invoking it synchronously.

This change was originally part of `revise-foundation-for-launch-mvp` and was split out after review found two of its premises false. Both were then verified directly against `slack-bolt` 1.30.0 and against the existing tests; the corrected findings are in design.md and are the reason this is its own change rather than a footnote in another.

## What Changes

- **`omni_agent`'s inbound Slack route is re-implemented on Bolt.** `slack_bolt`'s `AsyncApp` behind `AsyncSlackRequestHandler`, mounted at the same path (`POST /omni_agent/slack/events`), replacing the hand-rolled `SignatureVerifier`, the `url_verification` branch and the `event_callback`/`app_mention` dispatch.
- **The Bolt app is constructed with a custom `authorize` callable and no `token` argument**, so no `auth.test` network call is ever made. This is not a preference — it is the only construction that avoids one; see design.md.
- **A shared construction helper** in `shared/infrastructure/driving/` gives each module a lazily-built, per-app Bolt instance, so `products` follows the same pattern when it gains inbound routes rather than inventing a second.
- **An event Bolt has no listener for is acknowledged**, instead of answering 404 as Bolt does by default. This is a new requirement on `slack-trigger`, covering behavior the current adapter has and Bolt does not.
- **Outbound Slack calls and model invocation become async.** `slack_notifier.post_monitoring_message` moves to `AsyncWebClient` and becomes a coroutine; `monitoring.py` awaits it. `answer_question` becomes a coroutine over `graph.ainvoke`, with the compiled graph built once rather than per message.
- **Two existing test files get fixture corrections**, unavoidably: their doubles are synchronous and cannot stand in for coroutines. Every assertion and postcondition is preserved — only the doubles become awaitable, and one internal seam changes name. See design.md; this is stated as a decision because the split-out parent change wrongly claimed these files could stay untouched.

## Capabilities

### Modified Capabilities
- `slack-trigger`: gains a requirement that an event with no registered handler is still acknowledged.

`product-monitoring` is **not** modified. Its "Report Delivery Failure Is Decoupled From The Trigger" requirement describes the same behavior before and after — the `try`/`except`/log structure is identical, only awaited.

## Impact

- `pyproject.toml`: adds `slack-bolt` and `aiohttp` (required by Bolt's async app). Verified to resolve: `slack-bolt` 1.30.0 brings `slack-sdk` 3.43.0, inside the existing `>=3.36,<4` pin.
- Rewritten: `omni_agent/infrastructure/driving/slack.py`. New: `shared/infrastructure/driving/slack_app.py`. Modified: `omni_agent/application/use_cases.py`, `products/infrastructure/driven/slack_notifier.py`, `products/infrastructure/driving/monitoring.py`, `pyproject.toml`.
- **Test files modified**, with assertions preserved: `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py` and `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`.
- **Test files NOT modified**, and constraining the implementation: `test_main_slack_wiring.py` and `test_main_monitoring_wiring.py` each run `commerce_ops.main` in a fresh interpreter and run its lifespan with three named secrets absent, requiring success. Bolt app construction must therefore stay lazy and must never happen at import time.
- **`deploy-pipeline`'s "Pull Request Validation Gate" runs "without any host connection"**, so the unit tier must make no outbound Slack call. This is exactly what the `authorize` decision protects, and it is verified explicitly rather than assumed.
- No Slack app reconfiguration: the Events Request URL is unchanged. No environment variable is added, removed or renamed.
- **Unblocks `add-product-creation-clickup-task`**, whose Slack-handling design decisions this supersedes. That change must be revised via `openspec-update-change` before it is implemented; it is unimplemented, so nothing is unwound.

### Deliberately out of scope
- **Inbound Slack routes for `products`** (slash command, interactivity). The shared helper is built so that change uses it, but no `product_agent` route is added here.
- **Durability of deferred work.** Bolt schedules listener work as an asyncio task, which is lost on container restart — the same limitation `BackgroundTasks` has today. This change neither improves nor worsens it; only a job runner fixes it, and that is a separate change.
- **`omni_agent`'s graph itself.** Its nodes, model choice and lack of tools are untouched beyond building it once and invoking it with `ainvoke`.
