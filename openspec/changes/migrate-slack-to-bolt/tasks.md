## 1. Dependencies

- [ ] 1.1 Add `slack-bolt` and `aiohttp` to `pyproject.toml`'s `dependencies`, pinning `slack-bolt` with a compatible-release constraint rather than an open upper bound (design.md, Risks)
- [ ] 1.2 Run `uv sync` and confirm the resolved `slack-sdk` stays inside the existing `>=3.36,<4` pin (checked at proposal time: `slack-bolt` 1.30.0 → `slack-sdk` 3.43.0)

## 2. Shared Bolt construction

- [ ] 2.1 Add `shared/infrastructure/driving/slack_app.py` with a factory building an `AsyncApp` from a supplied bot token and signing secret
- [ ] 2.2 Construct it with **no `token` argument** and a custom async `authorize` callable returning a fixed `AuthorizeResult` carrying the bot token. Passing `token` alongside `authorize` makes Bolt install `AsyncSingleTeamAuthorization` and ignore the `authorize` — `if self._token:` wins over `elif self._async_authorize is not None:` (design.md, Verified Finding 1)
- [ ] 2.3 Do **not** pass `token_verification_enabled` — `AsyncApp` has no such parameter; it exists only on the synchronous `App`
- [ ] 2.4 Register a catch-all listener so an event with no specific handler is acknowledged with a success status instead of Bolt's default 404
- [ ] 2.5 Provide the FastAPI wiring helper over `slack_bolt.adapter.fastapi.async_handler.AsyncSlackRequestHandler`, so a module mounts its own app at its own path
- [ ] 2.6 Keep construction lazy behind a cached factory — no `AsyncApp` at import time and none at startup (constrained by `test_main_slack_wiring.py`'s fresh-interpreter import guard, which is not modified)
- [ ] 2.7 Catch `slack_bolt.error.BoltError` as well as `KeyError`/`ValueError` around construction, so an absent **or empty** signing secret yields 401 rather than 500

## 3. omni_agent migration

- [ ] 3.1 Rewrite `omni_agent/infrastructure/driving/slack.py` on the shared helpers, keeping the route at `POST /omni_agent/slack/events`
- [ ] 3.2 Delete the hand-rolled `SignatureVerifier` construction, the `url_verification` branch and the `event_callback`/`app_mention` dispatch — Bolt provides all three
- [ ] 3.3 Register an `app_mention` listener that strips the leading mention token, awaits `answer_question`, and posts the answer to the originating channel via the injected `client`
- [ ] 3.4 Keep the failure path: an exception from `answer_question` posts a visible failure message to the originating channel (`slack-trigger`: "Answer Generation Failure Is Visible in Slack")
- [ ] 3.5 Add a listener-level guard against bot-authored events (checking the event's `bot_id`/`subtype`) rather than relying solely on Bolt's `bot_user_id`-keyed filter, since the fixed `AuthorizeResult` supplies that value ourselves (design.md, Risks)
- [ ] 3.6 Confirm the acknowledgement is not gated on generation time (`slack-trigger`: "Slack Events Are Acknowledged Within Slack's Timeout")
- [ ] 3.7 Confirm no workspace-member identity check is introduced (`slack-trigger`: "No Sender Identity Restriction (Deferred)")

## 4. Async model invocation

- [ ] 4.1 Change `omni_agent/application/use_cases.py`'s `answer_question` to `async def` over `graph.ainvoke`
- [ ] 4.2 Build the compiled graph once behind a lazy cached factory instead of per invocation, keeping import free of `OPENAI_API_KEY`

## 5. Async outbound Slack

- [ ] 5.1 Change `products/infrastructure/driven/slack_notifier.py` to `AsyncWebClient`; make `post_monitoring_message` a coroutine, keeping the lazy cached-client construction
- [ ] 5.2 Await it from `products/infrastructure/driving/monitoring.py`'s `_attempt_post`, preserving the existing `try`/`except`/`logger.exception` structure exactly (`product-monitoring`: "Report Delivery Failure Is Decoupled From The Trigger")
- [ ] 5.3 Confirm no blocking Slack or model call remains inside any `async def` route or listener

## 6. Test fixture corrections

These files are modified. Assertions and postconditions must not change — only the doubles' sync/async shape and one substitution seam.

- [ ] 6.1 `tests/unit/omni_agent/infrastructure/driving/test_slack_events_endpoint.py`: make `_RecordingAnswerQuestion.__call__` and `_RecordingSlackClient.chat_postMessage` `async def`, recording and returning exactly what they do now
- [ ] 6.2 Same file: update the `slack_client` fixture, which currently hard-asserts `getattr(slack_adapter, "get_slack_client")` is not `None`, to substitute at the seam Bolt actually uses (the injected `client`)
- [ ] 6.3 Same file: re-express `test_app_mention_is_acknowledged_before_answer_generation`, whose current ordering assertion rests on FastAPI `BackgroundTasks` semantics that Bolt does not provide, so that it still proves the acknowledgement precedes generation under Bolt's scheduling
- [ ] 6.4 `tests/unit/products/infrastructure/driving/test_monitoring_routes.py`: make the `post_monitoring_message` double awaitable. Left synchronous, `await None` raises `TypeError` into `_attempt_post`'s broad `except`, is logged, and every assertion still passes — the tests would go green while proving nothing (design.md)
- [ ] 6.5 Review the diff of both files and confirm no assertion, expected value or postcondition changed

## 7. New tests for this change's own requirements

- [ ] 7.1 An authentic `event_callback` whose event type has no handler receives a success status and does not invoke omni-agent (`slack-trigger`: "An Event With No Registered Handler Is Still Acknowledged")
- [ ] 7.2 Handling a signed `app_mention` with a fake token attempts **no** outbound Slack call other than the answer post — asserted by intercepting outbound HTTP, not by inspection. This is the test that would have caught the `auth.test` defect (`slack-trigger`: "Handling An Event Requires No Credential Verification Call To Slack")
- [ ] 7.3 Application startup makes no outbound Slack call
- [ ] 7.4 An authentic inbound request is verified and acknowledged while outbound Slack is unreachable
- [ ] 7.5 A bot-authored `app_mention` does not trigger a reply

## 8. Pending change reconciliation

- [ ] 8.1 Revise `openspec/changes/add-product-creation-clickup-task/` via `openspec-update-change`: its design.md decisions on form-encoded parsing, per-route signature verification, and calling `views.open` through `slack_notifier` are superseded by Bolt's `command`, `view_submission` and `views.open`
- [ ] 8.2 Confirm that change still owns registering `CLICKUP_API_TOKEN`, `PRODUCT_LAUNCH_CLICKUP_LIST_ID` and `PRODUCT_AGENT_SLACK_SIGNING_SECRET` through `deploy.yml`'s render step, and flipping the first and last from optional to required in the settings model `revise-foundation-for-launch-mvp` introduces

## 9. Verification

- [ ] 9.1 Confirm `test_main_slack_wiring.py` and `test_main_monitoring_wiring.py` pass **unmodified**
- [ ] 9.2 Confirm every remaining `slack-trigger` and `product-monitoring` scenario test passes, with only the fixture corrections of section 6 applied
- [ ] 9.3 Run the unit tier with no network route to Slack available and confirm it passes — the direct check on `deploy-pipeline`'s "without any host connection" gate
- [ ] 9.4 Run `uv run pytest`, `uv run mypy .`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports --config .importlinter`
- [ ] 9.5 Run `openspec validate migrate-slack-to-bolt --strict`
- [ ] 9.6 After deploy, confirm in Slack that a mention still receives an answer and that Slack's Event Subscriptions page still shows the Request URL as verified
