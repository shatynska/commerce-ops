## Why

Ops can currently only pull product status by asking `omni_agent` in Slack; nothing pushes it proactively. Now that `add-products-store` gives `products` a real, Postgres-backed record of each product, the team wants proactive Slack reports on a range of schedules, through its own dedicated Slack app ("product_agent") — starting with the trigger plumbing for all of them now, and real reporting content rolled in over time as it's designed.

## What Changes

- Add five independently triggerable, `products`-owned driving HTTP endpoints — daily, weekly, biweekly, monthly, quarterly — each guarded by a shared internal-trigger mechanism. Only the **daily** endpoint has real reporting logic in this change: it lists the name of every existing product, primarily to verify the database connection this change wires up actually works end-to-end. The other four acknowledge their trigger and intentionally do nothing yet — their content is planned separately and will be filled in later without touching this change's plumbing.
- Add a reusable internal-trigger authentication guard (a bearer-secret header, checked with a constant-time comparison) that any module's driving adapter can attach via `Depends()` when it must trust only internal automation as its caller, not public or Slack traffic. Lives in `shared.infrastructure`, per the Shared Kernel exception.
- Add a `cron` service to `docker-compose.yml` with five crontab lines — one per cadence — each firing against `app` over a new private `app_cron` Docker network shared only between `app` and `cron`.
- Rename the existing `appdb` network to `app_db`, and name the new network `app_cron`, so both networks name their two members the same way `app_db` now does.
- New runtime secrets, delivered the same way every other runtime secret already reaches the container: `PRODUCT_AGENT_SLACK_BOT_TOKEN` (the `product_agent` app's bot token, used for the daily post) and `TRIGGER_SECRET` (shared by every internal-trigger-guarded endpoint, not scoped per-endpoint — the whole `cron` container is one trust boundary regardless). `PRODUCT_AGENT_SLACK_SIGNING_SECRET` is generated automatically when the `product_agent` Slack app is created — captured and held for later, but not delivered or checked anywhere in this change, since nothing here has an inbound endpoint that needs it yet.

## Capabilities

### New Capabilities
- `internal-trigger`: a reusable authentication contract for HTTP endpoints meant to be invoked only by trusted internal automation (e.g. a scheduler), rejecting any request that doesn't present the shared trigger secret.
- `product-monitoring`: five independently triggerable cadence endpoints for product-status reporting to Slack via the `product_agent` app, invoked through the `internal-trigger` mechanism; only `daily` reports real content today.

### Modified Capabilities
(none — `deploy-pipeline`'s existing secret- and compose-file-delivery requirements already cover a new service and new secrets without any change to their own text)

## Impact

- `docker-compose.yml`: new `cron` service with five crontab lines; new `app_cron` network; `appdb` renamed to `app_db`.
- New env vars: `PRODUCT_AGENT_SLACK_BOT_TOKEN`, `TRIGGER_SECRET`, and a channel-id config value for where the daily report posts.
- A new Slack app ("product_agent") registered in the Slack workspace — external setup, not code, but its bot token becomes a runtime secret this change wires up; its signing secret is captured for later use but not wired in here.
- `src/commerce_ops/shared/infrastructure/`: new internal-trigger-secret guard.
- `src/commerce_ops/products/infrastructure/driving/`: five new HTTP routes, one per cadence.
- `src/commerce_ops/products/application/`: first real content in this currently-empty module — a use case listing product names for `daily`, plus a shared no-op placeholder used by the other four cadences.
- `src/commerce_ops/products/infrastructure/driven/`: new Slack-posting adapter.
