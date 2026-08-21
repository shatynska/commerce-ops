## Context

No part of this project touches Postgres yet, in the app or the deploy pipeline: `pyproject.toml` has no DB driver, `docker-compose.yml` runs only the `app` service against the external `platform_edge` Traefik network, and `deploy.yml` renders `.env` with only the Slack/OpenAI secrets. `launch-playbook` (`src/commerce_ops/products/domain/launch_playbook.py`) already defines the abstract shape a launch instance must eventually reference — an 8-gate sequence (`commit` → ... → `graduated`) and a versioned playbook — but nothing yet represents one concrete product's position in it. See proposal.md - Why.

The production `docker-compose.yml` is delivered by `deploy.yml` to `/opt/commerce-ops` on the host and driven by a fixed, out-of-repo script (`app-deploy`, in the sibling `/infrastructure` repo) that runs `docker compose pull && up -d --wait`. Nothing besides `docker-compose.yml` and a freshly rendered `.env` travels to the host on each deploy — no bind-mounted directories, no separately-triggered commands.

## Goals / Non-Goals

**Goals:**
- Give the project its first real persistence: a `products` table holding a product's catalog identity and its current gate.
- Establish the house pattern for DB access (SQLAlchemy async + Alembic) and for wiring a module's Postgres repository into `infrastructure/driven/`, for future modules to follow.
- Get a real (if currently also test-serving) Postgres instance running in production, deployed by the existing pipeline, without widening what that pipeline exposes.

**Non-Goals:**
- Gate-transition logic (validating that a product may move from one gate to the next, running blocking steps, honoring a gate's confirmation requirement) — this change only stores and updates *which* gate a product is currently at; enforcing the launch-playbook's rules about how it got there is future work.
- A `launch-instance` FastAPI surface (HTTP routes) — this change adds the repository and the schema; wiring it to a driving adapter is separate.
- Any change to `/health` — it stays deliberately DB-independent per the existing `health-check` spec.
- Backups, connection pooling tuning, or any Postgres operational hardening beyond what's needed for this to run reliably as described below.

## Decisions

**SQLAlchemy (async) + Alembic, over raw asyncpg/psycopg.** This is the first table the project has; it will not be the last. Alembic gives every future module a shared, reviewable migration history from day one rather than hand-rolled SQL per module. Cost is more dependency surface up front, accepted since the alternative (raw SQL migrations) is what every subsequent module would then also have to hand-roll.

**One `products` table, catalog fields and current gate together**, rather than splitting catalog identity from launch state into two tables now. Columns:

| Column | Type | Notes |
|---|---|---|
| `id` | UUID, PK | surrogate key |
| `sku` | text, unique, not null | our identifier; the business key |
| `asin` | text, nullable | Amazon's identifier; unset until the listing exists |
| `name` | text, not null | |
| `playbook_version` | text, not null | which `launch-playbook` version this product runs under (see that capability's "Playbooks are versioned" requirement) |
| `current_gate` | text, not null | one of the 8 gate ids from `launch-playbook`'s fixed sequence; defaults to `commit` (the first gate) at creation |
| `launch_date` | date, nullable | unknown until later in the process |
| `created_at`, `updated_at` | timestamptz, not null | |

`current_gate` is constrained (application-level check, mirrored as a DB check constraint) to the exact 8 gate ids `launch-playbook` defines, so this table can never drift to a gate name the playbook doesn't recognize — without this capability re-implementing or depending on the playbook's own gate-ordering or opening-mode rules, which stay owned by `launch-playbook`.

**Migrate on container startup**, over a separate deploy-triggered step. The deploy trigger (`app-deploy`) is a fixed script outside this repo, so the only lever this repo has without also changing that external script is the image's own entrypoint. Trade-off accepted: a bad migration blocks the app container from starting until fixed (see Risks below), rather than failing in a separate, more isolated step.

**New private compose network (`appdb`) for `app` ↔ `postgres`,** instead of reusing `platform_edge`. `platform_edge` is the shared, external Traefik-facing network other applications on the host may also sit on; Postgres has no HTTP surface and no reason to be reachable from it. `app` joins both networks; `postgres` joins only `appdb`.

**Postgres service declares its own `healthcheck` (e.g. `pg_isready`).** `app`'s `depends_on: postgres: condition: service_healthy` is only evaluable if `postgres` has a healthcheck to report against — without one, Compose cannot satisfy that condition and the "app waits for Postgres to be healthy" behavior this change specifies would not actually hold. This is not optional configuration; it's load-bearing for the `deploy-pipeline` delta's "App does not start before Postgres is healthy" scenario.

**Named Docker volume for Postgres data**, not a bind mount. Only `docker-compose.yml` and `.env` travel to the host on deploy — a bind mount would need a host path this repo has no channel to provision or reference reliably; a named volume is created and persisted by Docker itself, keyed off the compose file already being delivered.

**`ProductRepository` lives in `products/infrastructure/driven/`**, alongside the existing `playbook_loader.py`, per the project's own module-boundary convention (driven adapters in `infrastructure/driven`, domain stays free of I/O). Its interface is consumed by `products/application` (currently empty); this change does not yet add a use case that calls it, since none is needed to exercise the store directly via integration tests.

## Risks / Trade-offs

- **Migrate-on-startup blocks the app on a bad migration** → accepted for now (see Decisions); revisit if this project starts writing schema changes frequently enough for it to bite.
- **Real production data with no backup story yet** → the proposal is explicit this DB doubles as the test bed while the launch process is built; do not put anything in it that can't be lost until backups become a separate change.
- **`current_gate` duplicates knowledge of `launch-playbook`'s gate ids as a literal list** in this table's constraint → accepted rather than introducing a cross-module dependency from `products` infrastructure back into `products.domain`'s gate enum for one constrained column list; revisit if the two ever drift.
- **New GitHub Environment secret required** (`POSTGRES_PASSWORD` or equivalent) → must be created by a repo admin outside this change; deploy will fail closed (container won't start without it) rather than defaulting to an insecure value.

## Migration Plan

1. Add SQLAlchemy + Alembic to `pyproject.toml`; scaffold `alembic/` with an async-compatible env.
2. Write the first Alembic revision creating `products`.
3. Add `ProductRepository` and its SQLAlchemy model in `products/infrastructure/driven/`.
4. Add `postgres` service (with a `healthcheck`), `appdb` network, and named volume to `docker-compose.yml`; add `depends_on: postgres: condition: service_healthy` to `app`.
5. Change the app image's startup command to run `alembic upgrade head` before `uvicorn`.
6. Add the Postgres connection secret(s) to `deploy.yml`'s `.env` render step.
7. (Outside this change) a repo admin creates the corresponding GitHub Environment secret before this merges to `main`, or the first post-merge deploy fails closed at container start.
8. Add `tests/integration/products/` exercising the repository against a real Postgres (e.g. via the new compose service, or a locally-run equivalent for CI).

No rollback beyond the pipeline's existing behavior is needed: if the deploy's health check fails, `deploy.yml` already fails the workflow run without rolling the container back automatically, consistent with current behavior for any other failed deploy.
