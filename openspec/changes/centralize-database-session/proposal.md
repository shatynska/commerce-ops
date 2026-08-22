## Why

The application's only database engine is owned by a driving adapter, is never closed, and cannot be reached by anything that is not an HTTP request.

`products/infrastructure/driving/monitoring.py` holds it: a `functools.lru_cache`-cached `_get_engine()` calling `create_async_engine(os.environ["DATABASE_URL"])`, plus a `get_session()` FastAPI dependency built on it. Four problems follow, and they compound:

- **A driving adapter owns a driven concern.** In this project's ports-and-adapters shape, the HTTP routes are a driving adapter; the database connection is something the application layer is driven *to*. The engine ended up inside the HTTP adapter because the HTTP adapter was the only caller — which is exactly the coupling the layering exists to prevent.
- **Nothing outside an HTTP request can get a session.** The scheduler change adds a worker process that is not hosted by the HTTP server at all. As things stand it would have to either import a `products` driving adapter to reach the database — a worker reaching through another module's HTTP adapter to find a connection — or call `create_async_engine` again, duplicating the engine construction, the `DATABASE_URL` read and the scheme validation, with no single place to fix any of them and no bound on the aggregate connections the deployment opens against Postgres's `max_connections`.
- **The engine is never disposed, and the process is never asked to.** Nothing in `src/` calls `dispose()`, `main.py` declares no lifespan, and the container's start command does not `exec` the server, so SIGTERM never reaches it — every redeploy severs in-flight sessions at SIGKILL rather than letting them finish and be released. There is also no disposal hook a non-HTTP process could call even if it wanted to, which is the part the worker will need.
- **`DATABASE_URL` is read outside the declaration**, by direct `os.environ` subscript, in the one module whose comment in `settings.py` already points at it as the reason the URL's scheme is validated there.

The timing is deliberate. The module that owns the engine today is the same module the scheduler change retires, and the parked `add-product-creation-clickup-task` change is written to depend on `monitoring.py`'s `get_session` by name. Moving ownership now means the scheduler change inherits a session provider instead of inventing one, and the parked change is rewritten against a stable home rather than against a module that is about to disappear.

## What Changes

- **A single database session provider is introduced in `shared`**, owning the engine and the session factory for the whole process, reached the same way by every caller.
- **It serves callers inside and outside a request.** The HTTP layer keeps a FastAPI dependency; a plain asynchronous context manager serves any caller that is not an HTTP request — the coming worker, and anything else that runs outside the server.
- **The engine is disposed when the process shuts down**, through a lifespan on the FastAPI application, so connections are released rather than abandoned. Disposal succeeds whether or not an engine was ever created.
- **`monitoring.py` stops owning the engine.** Its `_get_engine()` is removed and its `get_session()` becomes a thin delegation, so its tests keep overriding the same dependency they already override.
- **Exactly one connection pool serves domain-data access per process**, regardless of how many callers ask for a session. Infrastructure holding a connection or pool for its own bookkeeping — a task queue's tables, for instance — is outside that, on an axis design.md records: what the connection is *used for*, not how many there are.
- **`DATABASE_URL` continues to be read directly rather than through `get_settings()`**, for a reason recorded in design.md: `get_settings()` validates the whole model and raises when *any* required variable is faulty, while `preflight.py` deliberately lets the process start with non-startup-critical faults present. A runtime accessor built on `get_settings()` would therefore fail on a missing Slack token. The read moves into one place and keeps the scheme validation the settings model already declares.

## Capabilities

### New Capabilities
- `database-session`: providing database sessions to every caller in the process — request-scoped and otherwise — from a single connection pool whose lifetime is bounded by the process's, without requiring the database to be configured in order to import or start the application.

### Modified Capabilities

(none. `product-monitoring`'s requirements are unchanged: the daily route still reads products and still distinguishes a database-read failure from a delivery failure. Only where its session comes from changes, which is implementation, not behavior.

`runtime-configuration` is likewise unchanged. Its permission is a **single** sentence: "It does NOT require that every read go through the declaration: a module MAY read a variable directly where per-request tolerance of absence is itself required behavior, as `internal-trigger`'s … requires of the trigger guard." The colon specifies the trigger guard's case, which is not this change's — the provider fails loudly on absence rather than tolerating it. What licenses this read is the main clause plus settled in-tree practice: `clickup_client.py` and `slack_notifier.py` both read `os.environ[...]` directly and raise on absence today, under this same requirement, with no exemption recorded and none demanded. The requirement's own SHALL governs *declaring*, and `DATABASE_URL` stays declared and stays visible to the drift scanner.)

## Impact

- **New**: `src/commerce_ops/shared/infrastructure/driven/database.py` (engine, session factory, request dependency, standalone context manager, disposal), and its unit tests.
- **Modified**: `products/infrastructure/driving/monitoring.py` loses `_get_engine` and rebinds `get_session` to the provider's dependency; `main.py` gains a lifespan that disposes the engine on shutdown; `shared/application/settings.py`'s comment on `_REQUIRED_DATABASE_SCHEME`, which currently cites `monitoring.py` as the reason the scheme is validated.
- **Import boundaries hold as they are.** No `forbidden` contract names the `products.infrastructure` → `shared.infrastructure` edge: `products-infrastructure-boundary` forbids only `commerce_ops.omni_agent`. The `module-layers` contract declares `containers`, so it orders layers *within* each container and does not reach this edge at all. `monitoring.py` already imports `shared.infrastructure.driving.trigger_guard` on exactly this basis. No contract changes.
- **Existing regression guards constrain the implementation, in two distinct ways.** `test_main_monitoring_wiring.py` is the one that clears `DATABASE_URL`; `test_main_slack_wiring.py` clears only the two Slack secrets and `OPENAI_API_KEY`. In both files the fresh-interpreter subprocess runs `python -c "import commerce_ops.main"` and therefore covers **import only** — the lifespan is exercised separately, in-process, through a context-managed `TestClient` fixture. So: engine creation must stay lazy for the import guard, and disposal must tolerate an engine that was never created for the `TestClient` guards — the operative reason being that neither guard ever requests a session, not that `DATABASE_URL` is absent. Neither file is modified.
- **`tests/integration/products/conftest.py` builds its own engine and session factory** and is deliberately left alone — an integration test pointing at a test database is a legitimate second owner, outside the application process this change is about.
- **Unblocks two changes**: the scheduler change's worker inherits a session provider instead of duplicating engine construction, the `DATABASE_URL` read and its scheme validation, and the parked `add-product-creation-clickup-task` change gains a stable session home to be rewritten against.
- **Fixes a live defect the change depends on**: the container's start command does not `exec` the server, so `sh` remains PID 1 and SIGTERM never reaches uvicorn — verified directly. Without that fix the lifespan added here would never run in production. See design.md, "The container's start command must `exec` the server".
- No new dependency; no schema change; no migration.
