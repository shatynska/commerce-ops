## 1. Dependencies

- [x] 1.1 Add `slack_sdk` to `pyproject.toml` runtime dependencies, pinned to a conservative version range
- [x] 1.2 Run `uv sync` to update the lockfile and environment

## 2. Deploy pipeline secrets

- [x] 2.1 Add `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN`, and `OPENAI_API_KEY` as GitHub Actions secrets scoped to the `production` Environment (manual, outside the repo)
- [x] 2.2 In `.github/workflows/deploy.yml`'s "Render .env" step, add lines writing `OMNI_AGENT_SLACK_SIGNING_SECRET`, `OMNI_AGENT_SLACK_BOT_TOKEN`, and `OPENAI_API_KEY` from `secrets.*`, alongside the existing `IMAGE_TAG` line
- [x] 2.3 Add `env_file: .env` to `docker-compose.yml`'s `app` service so the container's process environment picks up the rendered values

## 3. Slack driving adapter — module and verification

- [x] 3.1 Create `src/commerce_ops/shared/infrastructure/driving/slack.py`
- [x] 3.2 Implement cached factories (e.g. `functools.lru_cache`-wrapped `get_signature_verifier()` and `get_slack_client()`) that construct `slack_sdk.signature.SignatureVerifier` (from `OMNI_AGENT_SLACK_SIGNING_SECRET`) and `slack_sdk.WebClient` (from `OMNI_AGENT_SLACK_BOT_TOKEN`) from the ambient environment — do NOT construct either at module import time; they must only run when first invoked from a request
- [x] 3.3 Add a FastAPI route (`POST /slack/events`) that reads the raw body and headers, verifies the request via `SignatureVerifier.is_valid_request(...)` (rejecting on failure), and — if the parsed body's `type` is `url_verification` — returns `{"challenge": ...}` echoing the received value

## 4. app_mention handling

- [x] 4.1 In the same route, when the parsed body is an `event_callback` for `app_mention`, call `background_tasks.add_task(handle_app_mention, event)` and return `200` immediately — before any omni-agent invocation happens
- [x] 4.2 Implement `handle_app_mention(event)`: strip the `<@BOTID>` mention token from the event text to derive the question, invoke `omni_agent.application.graph.build_production_graph()`, and post the answer back to the originating channel via `WebClient.chat_postMessage`
- [x] 4.3 In `handle_app_mention`, catch any exception from the omni-agent invocation and post a visible failure message to the originating channel instead of letting it fail silently — covers "Answer Generation Failure Is Visible in Slack"

## 5. Wiring

- [x] 5.1 Include the new Slack router in `main.py`, alongside `health.router`

## 6. Tests

- [x] 6.1 Test: importing `commerce_ops.main` succeeds with `OMNI_AGENT_SLACK_SIGNING_SECRET`/`OMNI_AGENT_SLACK_BOT_TOKEN` absent from the environment, and the existing `tests/unit/test_health.py` still passes unmodified — guards against the Slack adapter being constructed eagerly at import time, which would break the PR-validation CI job (no access to production-scoped secrets, no host/network connection)
- [x] 6.2 Test: a request to the events endpoint with an invalid/missing Slack signature is rejected and does not invoke omni-agent — covers "Slack Request Authenticity Is Verified"
- [x] 6.3 Test: a `url_verification` challenge request receives a response echoing the same challenge value — covers "Endpoint Responds to Slack's URL Verification Challenge"
- [x] 6.4 Test: an `app_mention` event is acknowledged (route returns) before the omni-agent call/reply completes (e.g. the background work is scheduled rather than awaited inline) — covers "Slack Events Are Acknowledged Within Slack's Timeout"
- [x] 6.5 Test: a valid `app_mention` event results in the mention text (with the bot-ID token stripped) being passed to omni-agent, and its answer being posted back to the originating channel — covers "Slack App Mention Triggers Omni"
- [x] 6.6 Test: when omni-agent's invocation raises inside `handle_app_mention`, a failure message is posted to the originating channel instead of nothing — covers "Answer Generation Failure Is Visible in Slack"
- [x] 6.7 Test: an `app_mention` from an arbitrary workspace member is processed the same as any other, with no identity check performed — covers "No Sender Identity Restriction (Deferred)"

## 7. Verification

- [x] 7.1 Run `uv run pytest` and confirm the new tests and the existing suite pass
- [x] 7.2 Run `ruff check` and `ruff format --check`
- [x] 7.3 Run `mypy`
