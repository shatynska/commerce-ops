## 1. Dependencies & Migration Tooling

- [x] 1.1 Add SQLAlchemy (async) and an async Postgres driver, plus Alembic, to `pyproject.toml`
- [x] 1.2 Scaffold `alembic/` with an async-compatible env, reading `DATABASE_URL` from the environment

## 2. Domain-Facing Schema

- [x] 2.1 Write the first Alembic revision creating `products` (`id`, `sku`, `asin`, `name`, `playbook_version`, `current_gate`, `launch_date`, `created_at`, `updated_at`), with a unique constraint on `sku` and a check constraint on `current_gate` against the eight `launch-playbook` gate ids
- [x] 2.2 Add the SQLAlchemy model for `products` in `products/infrastructure/driven/`

## 3. Repository

- [x] 3.1 Implement `ProductRepository` in `products/infrastructure/driven/` — create, get by id, get by SKU, update current gate
- [x] 3.2 Default `current_gate` to `commit` on create when none is given
- [x] 3.3 Reject creation with a duplicate SKU or an unrecognized `current_gate`
- [x] 3.4 Reject an update to a nonexistent product or to an unrecognized `current_gate`

## 4. Local Postgres for Development

- [x] 4.1 Document running the compose file's `postgres` service locally (e.g. `docker compose up postgres`) and pointing `DATABASE_URL` at it, so `tests/integration/products/` is runnable before the pre-push hook enforces it

## 5. Deploy Pipeline

- [x] 5.1 Add a `postgres` service to `docker-compose.yml` with a named volume for its data
- [x] 5.2 Add a `healthcheck` to the `postgres` service (e.g. `pg_isready`) — required for `service_healthy` below to be evaluable at all
- [x] 5.3 Add a new private `appdb` network; put `postgres` on it only, and add `app` to it alongside the existing `platform_edge` network
- [x] 5.4 Add `depends_on: postgres: condition: service_healthy` to the `app` service
- [x] 5.5 Change the app image's startup command to run `alembic upgrade head` before starting `uvicorn`, failing startup (not serving traffic) if migrations fail
- [x] 5.6 Add the Postgres connection secret(s) to `deploy.yml`'s `.env` render step
- [x] 5.7 Note in the PR description that a repo admin must create the corresponding GitHub Environment secret before merging, or the first post-merge deploy will fail closed at container start (`POSTGRES_PASSWORD` already created — will note as confirmed, not as a pending blocker, in the PR description)

## 6. Tests

- [x] 6.1 Add `tests/integration/products/` covering the `launch-instance` spec's scenarios against a real Postgres connection
- [x] 6.2 Run `uv run pytest` (all tiers) and confirm the pre-commit/pre-push hooks pass
