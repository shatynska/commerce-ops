## Context

See proposal.md - Why. Relevant existing state:

- `products` has real launch-instance data: `Product.current_gate` in Postgres, read via `ProductRepository` (from `add-products-store`). `products/application/__init__.py` is currently empty — no use cases exist yet.
- The only existing Slack integration is inbound: `omni_agent/infrastructure/driving/slack.py` verifies Slack's own signature on events it receives. This change adds the opposite direction — the app calling out to Slack — for a *different* Slack app (`product_agent`), not `omni_agent`'s bot.
- Deployment is one long-lived `app` container plus `postgres`, via `docker-compose.yml` on a shared host, delivered by the existing `deploy-pipeline` capability (GHCR image, SSH over a private tailnet, secrets rendered fresh into `.env`). No scheduler of any kind exists yet.
- `app`'s only network today is `platform_edge` (shared Traefik ingress, also used by other apps on the host) plus `appdb` (private to `app` and `postgres`).
- `.importlinter`'s `shared-boundary` contract is one-directional: it forbids `commerce_ops.shared` from importing `commerce_ops.products` or `commerce_ops.omni_agent`. The reverse is allowed — a module's own layer may reach the same-or-lower corresponding layer within `shared` (the Shared Kernel exception), which is what lets this change place the trigger-secret guard in `shared.infrastructure` and have `products.infrastructure` import it (see Decisions).
- `Product` carries no history/event log — only `current_gate`, `launch_date`, `created_at`, `updated_at`. There's no data today to build a meaningfully different weekly/monthly/quarterly report from a daily one; that's separate, already-planned design work this change doesn't do.

## Goals / Non-Goals

**Goals:**
- Trigger reports without adding scheduling logic to the app process itself, and without relying on undocumented host-level setup (crontab/Ansible) that lives outside this repository.
- Keep each trigger endpoint reachable only by the automation meant to call it, without over-building for a threat model (a public third party) that doesn't apply here.
- Keep `products` owning its own Slack presence and its own driving routes, consistent with how `omni_agent` already owns its Slack route.
- Stand up the trigger plumbing for all five planned cadences now, so their reporting logic can be dropped in later without re-touching infrastructure — while being honest that only `daily` does anything today.

**Non-Goals:**
- Real reporting content for weekly/biweekly/monthly/quarterly — each endpoint exists, is guarded, and is triggerable, but intentionally performs no reporting action. That content is planned separately.
- Gate-aware or otherwise rich content for `daily` itself — this first pass exists mainly to verify the database connection this change wires up (`ProductRepository` → Postgres) actually works end-to-end; it lists product names only.
- Exactly-once delivery guarantees for any report (see Risks below).
- Inbound Slack commands/interactivity for `product_agent` — anticipated future work. This change only wires up the bot token; the signing secret it would need for inbound verification is captured when the app is created but not delivered or checked anywhere here.
- Alerting/escalation on repeated report-delivery failures — logged only for now (see Risks).

## Decisions

**Trigger mechanism: a `cron` service in `docker-compose.yml`, not an in-process scheduler, GitHub Actions cron, or host crontab.**
Keeping the trigger declared in `docker-compose.yml` keeps it version-controlled and visible to the next reader of this repo, unlike a host crontab or Ansible step that would only exist on the shared host. An in-process scheduler (e.g. APScheduler inside `app`) was considered and rejected in favor of this, mainly to keep the trigger mechanism itself declarative and inspectable in the repo rather than embedded in application startup code, and to keep `app`'s own process free of scheduling concerns it doesn't otherwise have.

**`cron` is a minimal image running a plain crontab, not a label-driven scheduler (e.g. Ofelia).**
A label-driven scheduler was considered, since this compose file already configures Traefik via labels. Rejected for now: it's an additional image/dependency for what a five-line crontab already does. `cron` is named generically (not `product-monitoring-cron`) because it's already carrying five lines for one capability and will likely carry more for others over time, each hitting its own already-module-owned endpoint on its own schedule — this is ops configuration, not a shared abstraction, and doesn't revisit the "no generic router" decision below.

**`cron` reaches `app` over a new private `app_cron` network, not the shared `platform_edge` network.**
`app` is already on `platform_edge` (Traefik, public via `fuperia.shatynska.com`) for unrelated reasons, so the trigger endpoints are reachable over the public internet regardless of which network `cron` uses — `app_cron` does not replicate `appdb`'s isolation of Postgres (which is on no public-facing network at all). What `app_cron` actually buys is narrower: `cron` itself never needs to join the shared `platform_edge` fabric (so it isn't exposed to, or exposable by, whatever else attaches to that ingress network), and its calls to `app` don't make an unnecessary round-trip out through Traefik/TLS termination and back in for what's purely internal traffic. The real protection against an arbitrary caller invoking these endpoints is `TRIGGER_SECRET` alone — consistent with `internal-trigger/spec.md`'s own Purpose, which frames the guard as existing precisely because network placement isn't a sufficient trust boundary here. `appdb` is renamed to `app_db` regardless, so both new/renamed networks name their two members the same way (`app_db` = app + db, `app_cron` = app + cron).

**`app_db` and `app_cron` stay separate networks; `cron` does not get direct database access.**
Considered merging them so `cron` could someday trigger a database-adjacent job directly. Rejected: Postgres is a driven dependency of `app`'s own repositories (e.g. `ProductRepository`'s gate validation) — nothing else is meant to reach it directly, which is exactly why `appdb` was isolated in the first place. A future scheduled database-adjacent task should be a new `app` endpoint (going through the domain/application layer like everything else) with its own `cron` line, not direct `cron`-to-Postgres access.

**Trigger authentication: one shared `TRIGGER_SECRET`, not a secret per endpoint or per cadence.**
Per-endpoint secrets would only add a real boundary if different, differently-trusted callers held different secrets. Every crontab line lives in the same `cron` container and already sees its whole environment, so a compromised `cron` container can trigger everything regardless of whether the secrets are split. `TRIGGER_SECRET` is unscoped by module, following this repo's existing convention for cross-cutting infra secrets (`POSTGRES_PASSWORD`, `IMAGE_TAG`) as distinct from module-owned integration credentials (`PRODUCT_AGENT_SLACK_BOT_TOKEN`, `OMNI_AGENT_SLACK_BOT_TOKEN`).

**The trigger-secret guard lives in `shared.infrastructure`, as a `Depends()` dependency each module's own route imports — not a shared route, and not a shared dispatch/registry.**
A single shared HTTP route in `shared` that fans out to multiple modules' use cases was considered and rejected: it would need `shared` to call into `products`' (or another module's) `application` layer, which `.importlinter`'s `shared-boundary` contract already forbids. A shared *guard function* is different in kind: it has no business logic, calls into no module, and is explicitly within the Shared Kernel exception (a module's `infrastructure` layer may reach any of `shared`'s layers). `products` keeps owning its own five routes; each just attaches the shared guard.

**Five cadence-triggered endpoints now, but real reporting logic only for `daily`.**
Content for weekly/biweekly/monthly/quarterly requires product-status design that doesn't exist yet (see Context) and is being planned separately from this change. Standing up the trigger plumbing for all five now — cron lines, guarded routes — lets that content be dropped in later without re-touching infrastructure. Each non-daily route acknowledges its trigger and performs no reporting action, logged as an intentional no-op rather than an error, mirroring the already-decided "delivery failure is logged, not surfaced back through the trigger response" pattern below — "not implemented yet" and "implemented but the downstream post failed" both leave the trigger response unaffected.

**`daily`'s content is a plain product-name listing, not a gate-based report.**
This first cadence exists primarily to verify the database connection this change wires up (`ProductRepository` → Postgres) actually works end-to-end. Gate-aware or otherwise richer content is real reporting-logic work reserved for a later pass, same as the other four cadences.

**The `daily` use case depends on a consumer-owned `Protocol` port, not directly on `ProductRepository`.**
`ProductRepository` lives in `products.infrastructure.driven`; `.importlinter`'s `module-layers` contract (`infrastructure → application → domain`, higher may import lower, never the reverse) forbids `products.application` from importing it directly — the same rule `module-boundary-conventions` added CI enforcement for. Per that change's own documented escalation ladder, a consumer-owned `Protocol` port is the answer once a dependency needs to cross this boundary: `products.application` defines a small port (e.g. `ProductNameReader`, one method returning `Sequence[str]` — plain names, not the ORM `Product` row, so no infrastructure type crosses into `application`). The concrete `ProductRepository` satisfies it structurally; the driving route constructs the repository and passes it into the use case, the same composition-root pattern `main.py` already uses for wiring driving adapters.

**`ProductRepository` gains a `list_names()` method; the daily route gets its own session-scoped FastAPI dependency.**
`ProductRepository` today only exposes `create`, `get_by_id`, `get_by_sku`, and `update_current_gate` — no listing method exists, so one is added. This is also the first driving route in the app that needs a live `AsyncSession`: an engine is constructed lazily and cached (mirroring the `functools.lru_cache` pattern `omni_agent/infrastructure/driving/slack.py` already uses for its `WebClient`/`SignatureVerifier`), and a per-request dependency yields a session from it via `async_sessionmaker` — the same `create_async_engine`/`async_sessionmaker` shape `tests/integration/products/conftest.py` already establishes for testing `ProductRepository` directly.

**A database-read failure is surfaced distinctly from a report-delivery (Slack) failure.**
The two are different in kind: a Slack-post failure happens *after* the daily use case has already done its job (read the database, assembled the report) — only the notification step failed, so the existing "delivery failure is logged, not surfaced" treatment is appropriate. A database-read failure means the endpoint's actual job — the thing `daily` exists to verify — never ran; treating it identically would make the smoke test always report success regardless of whether the database was reachable. The endpoint responds with a failing status in this case, and additionally attempts to post a message to Slack naming the failure, so it's visible in the same channel without depending on that post succeeding to know something went wrong (the failing HTTP status is the primary signal either way).

**`cron`'s schedule is defined inline in `docker-compose.yml`'s `command:`, not a separate crontab file.**
`deploy-pipeline`'s file-delivery step is hardcoded to ship exactly `docker-compose.yml` and `.env` (`.github/workflows/deploy.yml`'s `tar -czf - docker-compose.yml .env`) — any other file (e.g. a mounted crontab) would never reach the host, and `cron` would fail to start correctly post-deploy undetected, since the post-deploy health check targets `app`, not `cron`. Defining the five lines inline keeps this change's "Modified Capabilities: none" claim for `deploy-pipeline` true, since no change to that delivery step is needed.

**Each cadence gets its own route (distinct path), not one route parameterized by cadence.**
E.g. `POST /products/monitoring/daily`, `/weekly`, `/biweekly`, `/monthly`, `/quarterly`. `cron` needs one fixed URL per line regardless of how the route is implemented internally; separate paths keep each cadence's logs and observability distinct and let each evolve its own request/response shape later without a shared dispatch branch.

**Digest content, endpoint ownership, and Slack adapter placement: `products`-owned, not `shared`.**
Follows the pattern `omni_agent` already established for its own Slack route: each module owns its own driving adapters and credentials. The daily report reads real data through `products`' own `ProductRepository`; a `shared`-owned report would need to reach into `products` to do that, which the same import-linter contract forbids.

**Report-delivery failure is logged, not surfaced back through the trigger response.**
The `cron` container's job is only to fire the trigger; whether a report actually reaches Slack is a separate concern with its own failure modes. Coupling the two would make `cron`'s own success/failure reflect Slack's availability rather than whether the trigger itself was received. A Slack-post failure is logged; the endpoint still acknowledges the trigger. Turning logged failures into active alerting is explicitly deferred (see Non-Goals).

**`PRODUCT_AGENT_SLACK_SIGNING_SECRET` is generated but not delivered.**
Creating the `product_agent` Slack app produces this secret automatically, whether or not it's used yet. Capturing its value now (wherever such values are held before entering CI) costs nothing and saves a trip back into Slack's admin console later. It is not added to `.env`, GitHub Actions secrets, or any verification code in this change — nothing here reads it, since there is no inbound endpoint yet for it to verify.

## Risks / Trade-offs

- **[Risk]** `cron` firing twice for the same trigger (e.g. a container restart near the scheduled time, or a manual re-run) sends a report twice. → **Mitigation**: none built into this change; accepted for a low-stakes internal notification. Revisit only if it proves disruptive in practice.
- **[Risk]** A Slack-post failure is currently only visible in logs — nothing actively surfaces it. → **Mitigation**: explicitly deferred (see Non-Goals); the requirement (`product-monitoring` capability) only commits to logging, not to silence, so alerting can be layered on later without a spec change.
- **[Risk]** `cron`'s container restarting or the host rebooting near a scheduled time can cause a missed trigger entirely (plain crontab has no persistence/catch-up). → **Mitigation**: accepted; these are convenience notifications, not a system of record.
- **[Risk]** A silent no-op on the weekly/biweekly/monthly/quarterly endpoints could be mistaken for a bug rather than an intentional placeholder. → **Mitigation**: each logs explicitly that it's an intentional no-op pending planned content, distinguishable in logs from a genuine failure.
- **[Risk]** Once real content is added to the non-daily cadences, a day where multiple cadences coincide (e.g. the 1st of the month is also a daily-triggering day) could post duplicate or overlapping content to the same channel. → **Mitigation**: out of scope here since non-daily cadences do nothing today; must be resolved (distinct channels, suppression logic, or accepted overlap) when that content is actually designed.

## Migration Plan

- Additive: new `docker-compose.yml` service and network, one network rename (`appdb` → `app_db`, no data migration — Postgres itself isn't reachable differently, only the network's declared name changes), new env vars delivered through the existing secret-rendering step in `deploy-pipeline`. No existing endpoint, table, or credential changes.
- Rollback: revert the compose/service changes and stop delivering the new env vars; no persisted state this change introduces needs unwinding.
