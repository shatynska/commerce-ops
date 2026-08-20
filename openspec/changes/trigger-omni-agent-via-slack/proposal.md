## Why

`omni-agent` exists (a LangGraph graph that answers a question via OpenAI) but nothing invokes it in production — no route, no Slack listener — by explicit design of `add-omni-agent`, which deferred triggering to a follow-up change. The project's own foundation names Slack as a primary, two-way interaction channel alongside the HTTP API, not a secondary add-on. This change adds the first real entry point: mentioning the bot in a Slack channel triggers Omni and posts its answer back. It also closes a pre-existing gap this trigger would otherwise inherit — the deploy pipeline currently delivers no runtime secrets to the container at all (not even `OPENAI_API_KEY`, which `omni-agent` already needs), so `omni-agent` cannot actually run in production yet either.

## What Changes

- Add a Slack Events API route mounted into the existing FastAPI app (alongside `/health`), verifying Slack's request signature and handling the one-time `url_verification` handshake Slack performs when the endpoint is registered.
- On an `app_mention` event, acknowledge within Slack's ~3-second window and process the mention asynchronously — Slack retries on timeout, so the language-model call cannot happen inline before the ack.
- Invoke `omni_agent`'s `build_production_graph()` with the mention's text as the question, then post the generated answer back to the originating channel via `chat.postMessage` using the bot token.
- No sender-identity guard in this change — deliberately deferred, consistent with the deferral already recorded in `add-omni-agent`'s proposal. Access control for now is solely which channel(s) the bot is invited to.
- If invoking omni-agent fails while processing a mention, post a visible failure message to the originating channel rather than leaving the mention unanswered.
- Add `slack_sdk` as a new runtime dependency.
- Extend the deploy pipeline's `.env` rendering (`.github/workflows/deploy.yml`) to also carry `OPENAI_API_KEY`, `SLACK_SIGNING_SECRET`, and `SLACK_BOT_TOKEN` from GitHub Actions secrets (same Environment-scoped pattern already used for the deploy SSH key), and add `env_file: .env` to `docker-compose.yml`'s `app` service so the running container actually receives them.

## Capabilities

### New Capabilities
- `slack-trigger`: a Slack Events API endpoint that receives and verifies `app_mention` events, triggers `omni-agent` with the mention text, and replies in the originating channel with the generated answer.

### Modified Capabilities
- `deploy-pipeline`: the rendered `.env` file's contents change from carrying only the image tag to also carrying application runtime secrets, delivered to the container via `docker-compose.yml`'s `env_file`.

## Impact

- `pyproject.toml`: adds the `slack_sdk` dependency.
- New code mounting a Slack Events route into the existing FastAPI app (exact module location decided in design.md), calling into `omni_agent.application.graph`.
- `.github/workflows/deploy.yml`: the "Render .env" step gains `OPENAI_API_KEY`, `SLACK_SIGNING_SECRET`, `SLACK_BOT_TOKEN` sourced from `secrets.*`.
- `docker-compose.yml`: `app` service gains `env_file: .env`.
- External prerequisite (outside this repo): the Slack app already exists; its Event Subscriptions Request URL needs pointing at `https://fuperia.shatynska.com/slack/events` once this is deployed, and the bot needs inviting into the target channel(s).
- No changes to `omni-agent`'s graph or spec — this change only adds a caller.
