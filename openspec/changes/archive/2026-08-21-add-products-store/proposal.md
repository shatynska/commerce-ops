## Why

`products` module currently has a domain model for the abstract launch playbook (`launch-playbook`: gates, step definitions, timing anchors) but nothing that represents a concrete product moving through it, and no persistence anywhere in the project — no DB driver, no migrations, no `DATABASE_URL`, in the app or the deploy pipeline. Work on the launch process itself needs a real product record to run against; this change gives it one, and gives the project its first Postgres-backed store to build further persistence on.

## What Changes

- Add SQLAlchemy (async) and Alembic as the project's DB access and migration tooling — first such dependency in the project, sets the convention for future repositories.
- Add a `products` table (via the first Alembic migration) holding a product's catalog identity together with its current position in the launch-playbook gate sequence: identifier, SKU, ASIN (nullable), name, the playbook version it is running under, and its current gate.
- Add a `ProductRepository` driven adapter in `products/infrastructure/driven/`, following the existing layer split (domain stays free of I/O).
- Add a `postgres` service to the production `docker-compose.yml`, on a new private compose network separate from the existing `platform_edge` Traefik network, backed by a named Docker volume so data survives redeploys. This is a real production database; for now it doubles as the environment used to exercise the launch process end to end while that process is still being built.
- Run pending Alembic migrations on application container startup, before the app begins serving traffic.
- Add the new `POSTGRES_PASSWORD` (and related connection) runtime secret to the deploy workflow's rendered `.env` step — the GitHub Environment secret itself must be created by a repo admin, outside this change.

## Capabilities

### New Capabilities
- `launch-instance`: a product's persisted catalog identity and its current position in the launch-playbook gate sequence.

### Modified Capabilities
- `deploy-pipeline`: the delivered `docker-compose.yml` now provisions a Postgres service alongside the app (private network, persistent volume), and the app container performs pending database migrations as part of its startup before it is considered live.

## Impact

- `pyproject.toml`: new dependencies (SQLAlchemy async driver, Alembic).
- `src/commerce_ops/products/infrastructure/driven/`: new repository adapter and ORM mapping.
- New `alembic/` migration directory and its first revision (the `products` table).
- `docker-compose.yml`: new `postgres` service, new private network, new named volume.
- `Dockerfile` / container `CMD`: migration step added before `uvicorn` starts.
- `.github/workflows/deploy.yml`: `.env` render step gains the Postgres connection secret(s).
- New GitHub Environment secret (`POSTGRES_PASSWORD` or equivalent) — created manually, outside this change's scope.
- `tests/integration/products/`: first integration tests exercising a real Postgres connection.
