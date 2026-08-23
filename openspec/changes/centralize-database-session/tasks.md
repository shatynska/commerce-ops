## 1. The session provider

- [x] 1.1 Add `src/commerce_ops/shared/infrastructure/driven/database.py`
- [x] 1.2 Reuse the scheme validator from `shared/application/settings.py` so the required scheme has one definition, and **rename it to a public name** there (updating `settings.py`'s own use) — a leading-underscore function that another layer now depends on gives a future editor of `settings.py` no signal, and no lint rule in this project's ruff selection would catch its removal. Do **not** move it here: `settings.py` needs it for `DatabaseUrl`'s `AfterValidator`, and importing it back would be `shared.application` importing `shared.infrastructure`, which `.importlinter`'s `module-layers` contract forbids
- [x] 1.3 Add a lazy, cached engine factory reading `os.environ.get("DATABASE_URL")` with the variable name as a string literal at the read site (the drift scan in `test_settings_env_drift.py` recognises `os.environ[...]`, `.get(...)` and `os.getenv(...)` with a constant argument; `.get` is used here so absence is a value to report rather than a `KeyError` to catch), validating the scheme, and reporting absence or emptiness in a message naming `DATABASE_URL`
- [x] 1.4 Build the `async_sessionmaker(expire_on_commit=False)` once alongside the engine, not per session request
- [x] 1.5 Add `session()` — an `@asynccontextmanager` yielding an `AsyncSession`, releasing it on both normal completion and exception, letting the exception propagate unchanged
- [x] 1.6 Add `get_session()` — the FastAPI dependency, a thin `AsyncIterator` over `session()`
- [x] 1.7 Add `dispose_engine()` — awaits `engine.dispose()` if an engine was created, returns without error otherwise, and clears the factory cache in the same operation so a later session request builds a fresh engine

## 2. Retire the driving adapter's ownership

- [x] 2.1 Delete `_get_engine` from `products/infrastructure/driving/monitoring.py` and its `create_async_engine`/`async_sessionmaker`/`os` imports
- [x] 2.2 Rebind `monitoring.get_session` to the provider's dependency, keeping the module-level name so `test_monitoring_routes.py:195`'s `app.dependency_overrides[monitoring.get_session]` keeps resolving untouched (that file overrides `get_session` through `dependency_overrides` specifically, not by monkeypatching — its monkeypatched collaborators are `run_daily_digest` and `post_monitoring_message`)
- [x] 2.3 Update `monitoring.py`'s module docstring: the engine comment no longer describes this module
- [x] 2.4 Update `settings.py`'s comment on `_REQUIRED_DATABASE_SCHEME`, which currently points at `monitoring.py`'s `create_async_engine` as the reason the scheme is validated

## 3. Process lifetime

- [x] 3.1 Add an `@asynccontextmanager` lifespan to `src/commerce_ops/main.py` whose shutdown half awaits `dispose_engine()`, and pass it to `FastAPI(lifespan=...)`
- [x] 3.2 If `configure-application-logging` has landed, keep its `configure_logging()` call at module import rather than folding it into the new lifespan — it must cover import-time records (see that change's design.md)
- [x] 3.3 **Make the container's start command `exec` the server**: change the `Dockerfile`'s `CMD` chain so the final command is `exec uv run uvicorn ...`. Without this, `sh` stays PID 1 (verified: `sh -c 'true && sleep 20'` leaves `sh` running with `sleep` as a forked child), SIGTERM never reaches uvicorn, and the lifespan added in 3.1 never runs in the deployment — every test in section 4 would pass while nothing was ever disposed (design.md — "The container's start command must `exec` the server")
- [x] 3.3a Add a line to the `Dockerfile`'s existing `CMD` comment block recording **why** `exec` is there, citing `database-session`'s process-exit requirement. The comment block explains every other element of that chain; without this the reason lives only in an archived design doc, and a future edit drops `exec` silently with every test still green. `docker-compose.yml`'s `cron` service already uses `exec crond -f -l 2` as an in-tree precedent
- [x] 3.3b Record the fallback in design.md and here: if task 3.4 shows uvicorn logs no shutdown, `uv run` is not forwarding the signal, and the remedy is a start command that puts uvicorn itself at PID 1. Do not leave the implementer to invent a deployment decision mid-task
- [x] 3.4 Verify the signal actually arrives, rather than inferring it from the command string: run the container, `docker compose stop`, and confirm uvicorn logs its own shutdown **and** that the stop returns promptly instead of hanging for the ~10s SIGKILL timeout. `uv run` must forward the signal too, which is why this is an observation and not a code review

## 4. Tests

- [x] 4.1 Unit test: two session requests draw from the same engine instance (spec: "Repeated session requests share one pool")
- [x] 4.2 Unit test: a request-scoped session and a standalone session draw from the same engine instance (spec: "Request-scoped and standalone callers share one pool")
- [x] 4.3 Unit test: `session()` yields a usable session to a caller with no HTTP request in progress (spec: "Work that is not an HTTP request obtains a session")
- [x] 4.4 Unit test: the session is released when the caller's block completes (spec: "A session is released after the caller's work completes")
- [x] 4.5 Unit test: the session is released when the caller's block raises, and the exception propagates unchanged (spec: "A session is released when the caller's work raises")
- [x] 4.6 Unit test: `dispose_engine()` after use disposes the engine — this covers the provider's half only, **not** the application-shutdown scenario
- [x] 4.6a Unit test: start and stop `commerce_ops.main.app` through a context-managed `TestClient` **with an engine in existence**, and assert the engine was actually disposed (spec: "The HTTP process releases connections when it stops"). This is the only check that catches a `dispose_engine()` that was written but never wired into `FastAPI(lifespan=...)` — every other task in this list, plus both regression guards, passes in that case because they all take the no-engine path (design.md — "The wiring itself needs its own test")
- [x] 4.7 Unit test: `dispose_engine()` with no engine ever created returns without raising (spec: "Shutdown with no database use is not an error")
- [x] 4.8 Unit test: a session requested after `dispose_engine()` gets a fresh, usable engine rather than the disposed one (design.md — Risks, third entry)
- [x] 4.9 Unit test: importing the provider with `DATABASE_URL` absent does not read it; the read happens on first session request (spec: "The connection setting is read only when a session is first requested")
- [x] 4.9a Unit test: **stopping** the HTTP application object with `DATABASE_URL` absent and no session requested succeeds (spec: "Starting and stopping with the database unconfigured"). The *starting* half is already covered by `tests/unit/test_startup_without_configuration.py`, which starts `main.app` under a `TestClient` with every declared variable absent and asserts `/health` serves — cite it rather than duplicating it
- [x] 4.10 Unit test: requesting a session with `DATABASE_URL` absent fails with a report naming `DATABASE_URL` (spec: "A session is requested with the setting absent")
- [x] 4.11 Unit test: requesting a session with a `postgresql://` (non-async) URL fails with a report naming `DATABASE_URL` and the required scheme (spec: "A session is requested with a setting the application cannot connect with")
- [x] 4.12 Run `test_main_slack_wiring.py`, `test_main_monitoring_wiring.py` and `tests/unit/test_startup_without_configuration.py` **unmodified**. Their fresh-interpreter subprocess covers **import only** (`python -c "import commerce_ops.main"`); their context-managed `TestClient` fixtures are what exercise the lifespan, in-process. All three must still pass (design.md — Risks, first entry)
- [x] 4.13 Run `tests/unit/products/infrastructure/driving/test_monitoring_routes.py` **unmodified** — its dependency overrides must still resolve against `monitoring.get_session`

## 5. Verification

- [x] 5.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports`
- [x] 5.2 Run the integration tier against a local Postgres (`uv run pytest tests/integration`) — it owns its own engine and must be unaffected
- [x] 5.3 Run `openspec validate centralize-database-session --strict`
- [ ] 5.4 After deploy: confirm a clean shutdown in `docker logs` on the next redeploy, and that the previous process's connections are gone from `pg_stat_activity` rather than lingering until timeout. If task 3.4 was skipped, a failure here is ambiguous between the new code and the process chain — which is why 3.4 comes first
