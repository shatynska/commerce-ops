## 1. Shared internal-trigger guard

- [x] 1.1 Add a `TRIGGER_SECRET`-backed FastAPI dependency in `shared/infrastructure/` that checks an `Authorization` bearer header with a constant-time comparison, rejecting with 401 when the header is missing, doesn't match, or `TRIGGER_SECRET` isn't configured
- [x] 1.2 Export it from `shared`'s appropriate surface so `products` (and any future module) can attach it via `Depends()` without `shared` importing anything module-specific

## 2. Products: repository, port, and session wiring

- [x] 2.1 Add `list_names()` to `ProductRepository` (`products/infrastructure/driven/product_repository.py`), returning every product's name
- [x] 2.2 Define a consumer-owned `Protocol` port in `products/application/` (e.g. `ProductNameReader`, one async method returning `Sequence[str]`) that the daily use case depends on instead of importing `ProductRepository` directly — required by `.importlinter`'s `module-layers` contract (see design.md's Decisions)
- [x] 2.3 Add a lazily-constructed, cached async engine and a per-request `AsyncSession` FastAPI dependency in `products/infrastructure/driving/`, mirroring `tests/integration/products/conftest.py`'s `create_async_engine`/`async_sessionmaker` pattern and `omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache` pattern for lazy client construction

## 3. Products: monitoring use cases

- [x] 3.1 Add a `daily` use case to `products/application/` that depends on the `ProductNameReader` port (Task 2.2) and returns product names, or an explicit "no products exist" result when there are none; lets a database-read failure propagate rather than swallowing it
- [x] 3.2 Add a shared no-op placeholder use case for the weekly, biweekly, monthly, and quarterly cadences that performs no reporting action and logs that it was triggered as an intentional no-op
- [x] 3.3 Export both from `products/application/__init__.py`

## 4. Products: Slack notifier (driven adapter)

- [x] 4.1 Add `products/infrastructure/driven/slack_notifier.py`: wraps `slack_sdk.WebClient` using `PRODUCT_AGENT_SLACK_BOT_TOKEN`, posts a given message to the configured channel
- [x] 4.2 On a Slack API failure posting an already-assembled report, log the failure; do not raise it up to the caller in a way that would change the trigger endpoint's response (see design.md's Decisions)
- [x] 4.3 Read the target channel id from a new env var (e.g. `PRODUCT_AGENT_MONITORING_CHANNEL_ID`)

## 5. Products: monitoring trigger routes (driving adapter)

- [x] 5.1 Add five routes in `products/infrastructure/driving/` — `POST /products/monitoring/daily`, `/weekly`, `/biweekly`, `/monthly`, `/quarterly` — each guarded by the shared internal-trigger dependency from Task 1, `daily` additionally depending on the session dependency from Task 2.3
- [x] 5.2 Wire `daily` to call the use case from Task 3.1 (constructing `ProductRepository` from the request's session to satisfy the port from Task 2.2), then the Slack notifier from Task 4
- [x] 5.3 On a database-read failure in `daily` (the use case from Task 3.1 raising), respond with a failing status and attempt (best-effort, not blocking the response) to post a failure message via the Task 4 notifier — distinct from Task 4.2's log-only handling of a delivery failure
- [x] 5.4 Wire the other four routes to call the no-op placeholder from Task 3.2 only — no Slack notifier call
- [x] 5.5 Every route otherwise (i.e. outside the database-read-failure case above) returns a response reflecting that the trigger was received and processed, independent of whether a Slack post succeeded
- [x] 5.6 Register the routes' router in `main.py`, alongside the existing per-module routers

## 6. Docker Compose: trigger infrastructure

- [x] 6.1 Rename the `appdb` network to `app_db` (update both the network's own declaration and the `postgres`/`app` services' `networks:` lists)
- [x] 6.2 Add a new `app_cron` network, private (not `external: true`)
- [x] 6.3 Add `app` to the `app_cron` network, alongside its existing `platform_edge` and `app_db` memberships
- [x] 6.4 Add a `cron` service: a minimal image whose `command:` defines a crontab inline (not a separate mounted file — `deploy-pipeline`'s file delivery ships only `docker-compose.yml` and `.env`) with five lines, one per cadence, each firing against its own path from Task 5.1 with the `Authorization` header set from `TRIGGER_SECRET`; joined only to `app_cron`
- [x] 6.5 Deliver `TRIGGER_SECRET` to `cron` via `env_file: .env`, same as `app`

## 7. Secrets delivery

- [x] 7.1 Add `PRODUCT_AGENT_SLACK_BOT_TOKEN`, `PRODUCT_AGENT_MONITORING_CHANNEL_ID`, and `TRIGGER_SECRET` to the `.env`-rendering step in `.github/workflows/deploy.yml`
- [ ] 7.2 Register the corresponding values as GitHub Actions secrets on the `production` Environment (external/manual step — create the `product_agent` Slack app, install it to the workspace with `chat:write`, invite the bot to the target channel, generate a `TRIGGER_SECRET` value) — **cannot be done from this session; requires manual action in the Slack admin console and GitHub repo settings**
- [ ] 7.3 Capture the `product_agent` app's auto-generated signing secret and hold it wherever such values are kept for now — do not add it to `.env`, GitHub Actions secrets, or any verification code in this change — **cannot be done from this session; the Slack app doesn't exist yet**

## 8. Tests

- [x] 8.1 Unit tests for the internal-trigger guard: missing header, wrong secret, correct secret, unconfigured secret (`internal-trigger` capability's scenarios)
- [x] 8.2 Unit tests for the `daily` use case against a fake `ProductNameReader`: product names returned correctly, "no products exist" case, a reader failure propagates rather than being swallowed
- [x] 8.3 Unit test for `ProductRepository.list_names()` (Task 2.1) — covered under `tests/integration/products/` per this repo's testing-tier convention, since it exercises real Postgres
- [x] 8.4 Unit tests for the no-op placeholder use case: performs no reporting action, logs as intentional (covered at route level per test-manifest.md's recorded Level choice — the placeholder's own shape is never fixed by any artifact, so a separate direct test would duplicate ground without adding scenario evidence)
- [x] 8.5 Unit tests for all five routes: guard rejection short-circuits before any use case runs; `daily` calls the notifier on success; a Slack-post failure (after a successful read) still yields a trigger-accepted response; a database-read failure yields a failing response and an attempted failure post; the other four never call the notifier (`product-monitoring` capability's scenarios)
- [x] 8.6 Regression guard mirroring `test_main_slack_wiring.py`: importing `main` and hitting `/health` succeeds without `TRIGGER_SECRET`/`PRODUCT_AGENT_SLACK_BOT_TOKEN`/`DATABASE_URL` in the environment (PR-validation gate runs with no production secrets) — `DATABASE_URL`'s absence specifically guards Task 2.3's engine staying lazily constructed rather than built at import time
