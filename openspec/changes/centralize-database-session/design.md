## Context

See proposal.md — Why. This section records only the constraints that shape the approach.

**What exists today** (`products/infrastructure/driving/monitoring.py`):

```python
@functools.lru_cache
def _get_engine() -> AsyncEngine:
    return create_async_engine(os.environ["DATABASE_URL"])


async def get_session() -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    async with session_factory() as session:
        yield session
```

The laziness is deliberate and load-bearing — its own comment records why — and must be preserved. A new `async_sessionmaker` is built per request, which is cheap but pointless; the factory is stateless with respect to the session and belongs beside the engine.

**`main.py` declares no lifespan.** FastAPI supplies a no-op default.

**What the two regression guards actually do**, since the design leans on their exact shape:

- Both run a fresh-interpreter subprocess as `python -c "import commerce_ops.main"` — **import only, no lifespan**.
- Only `test_main_monitoring_wiring.py` clears `DATABASE_URL`. `test_main_slack_wiring.py` clears the two Slack secrets and `OPENAI_API_KEY`, leaving `DATABASE_URL` in place.
- The lifespan is exercised separately and in-process, through each file's context-managed `TestClient` fixture.

So laziness is what the import guards require, and disposal-tolerance is what the `TestClient` guards require — the latter because **neither guard ever requests a session**, which is the operative fact, not the absence of `DATABASE_URL`.

**Permission for the direct `os.environ` read.** `runtime-configuration`'s permission is one sentence, not two: "It does NOT require that every read go through the declaration: a module MAY read a variable directly where per-request tolerance of absence is itself required behavior, as `internal-trigger`'s … requires of the trigger guard." The colon specifies the trigger guard's case, and that case is **not** this change's — the provider fails loudly on an absent setting rather than tolerating it.

The permission relied on is therefore the main clause, supported by settled practice rather than by splitting the sentence: `clickup_client.py` reads `os.environ["CLICKUP_API_TOKEN"]` and `slack_notifier.py` reads `os.environ["PRODUCT_AGENT_SLACK_BOT_TOKEN"]`, both directly, both raising on absence, both under this requirement today with no exemption recorded. Those are stronger evidence than any reading of the sentence, because they are reads that do *not* tolerate absence and are accepted as they stand. The reason this change needs the permission at all is the `get_settings()` trap below.

**`get_settings()` cannot serve as a runtime accessor.** `pydantic-settings` validates the entire model on construction, so `get_settings()` raises `ValidationError` if *any* required variable is faulty. `preflight.py` deliberately allows the process to start when a non-startup-critical variable is faulty — that is `runtime-configuration`'s "Only A Startup-Critical Fault Prevents Startup". The two combine into a live trap: a deployment missing only `PRODUCT_AGENT_SLACK_BOT_TOKEN` starts by design, and every `get_settings()` call in it then raises. This is why every module in the tree reads `os.environ` directly, and why `settings.py`'s docstring describes the model as "a declaration plus a startup check". This change does not attempt to fix that; it works within it.

## Goals / Non-Goals

**Goals:**

- One owner for the engine, reachable identically from request and non-request callers.
- Connections released at process shutdown.
- The scheduler change inherits a session provider rather than inventing one.

**Non-Goals:**

- **Making `get_settings()` usable at runtime.** Real, and out of scope — it is a change to `runtime-configuration`'s own model, affecting every reader in the tree, and it should not ride along inside a change about session ownership. Recorded here so it is not mistaken for an oversight.
- **Transaction or unit-of-work management.** `ProductRepository` commits its own work today (recorded as an invented assumption in `tests/integration/products/conftest.py`). Whether that stays is a domain question tied to the product-creation work, not a plumbing one.
- **Pool sizing, timeouts, pre-ping, or retry-on-disconnect.** Defaults are untuned today and stay untuned; tuning without a workload to tune against is guessing. The single owner is what makes tuning a one-line change later.
- **Touching `tests/integration/products/conftest.py`.** An integration test pointing at a test database is a legitimate second engine owner, outside the application process.
- **Read replicas, multiple databases, or per-module engines.** One database, per the modular-monolith architecture.

## Decisions

### The one-pool requirement is scoped to domain-data access, not to connection count

The obvious wording — "at most one connection pool per process, full stop" — was the first draft and is wrong, for a reason worth recording at the requirement's own address rather than in whichever change first trips over it.

A requirement about how *the application obtains sessions* should not double as a cap on every connection any library opens. A task queue's `LISTEN`, a metrics exporter's connection, a migration tool's — none of these are ways to reach domain data, and all of them would warrant their own connection even under a single driver, because their connection characteristics differ from a request-scoped session's. Forbidding them would be forbidding a category of library rather than protecting anything this change cares about.

So the axis is **what the connection is used for**: one pool for everything that touches domain data; infrastructure bookkeeping is exempt, and the exemption says "connection or pool" explicitly, because a pooled queue client is the ordinary shape and a requirement that admitted only a single connection would be exempting a thing that does not exist.

**What triggered the wording.** `replace-cron-with-job-runner` adopts `procrastinate`, which brings `psycopg[pool]` alongside `asyncpg` — a second driver and a second pool, serving the queue's own tables. Naming that here is deliberate: a requirement whose shape was set by a sibling change, with the reasoning stored only in that sibling, is exactly the decision-that-lives-nowhere failure `AGENTS.md` warns about. The narrowing is not a concession to that change; it is the correct scope, and that change is what made the incorrect scope visible.

**What is now unbounded, stated plainly.** proposal.md names two harms from a second engine: no single place to fix construction, and no bound on the aggregate connections the deployment opens against Postgres's `max_connections`. This requirement addresses the first. It does **not** address the second — an exempt component's pool size is outside it. That is a **non-goal here, not an oversight**: bounding the aggregate means knowing every component's pool size and the server's limit, which is deployment-wide tuning with no workload to tune against yet. The single provider makes the application's own share a one-line change; whoever first hits a connection ceiling owns the rest, and this paragraph is what tells them the requirement never covered it.

### The provider lives in `shared/infrastructure/driven/`

The database is something the application is driven *to*, so `driven` is the correct side; `shared` because every module reaches the same Postgres instance, which is the modular monolith's stated shape.

`.importlinter` permits this without amendment, though not for the reason it first appears. The `module-layers` contract declares `containers`, so it orders layers *within* each container and does not evaluate a `commerce_ops.products.infrastructure` → `commerce_ops.shared.infrastructure` edge at all. What permits the import is that no `forbidden` contract names it: `products-infrastructure-boundary` forbids only `commerce_ops.omni_agent`. `monitoring.py` already imports `shared.infrastructure.driving.trigger_guard` on exactly this basis, which is the working precedent. No contract is edited by this change.

### Two accessors over one engine, not two engines

The provider exposes:

- an asynchronous context manager for any caller — the standalone form, and the only one the coming worker needs;
- a FastAPI dependency for the HTTP layer, implemented as a thin generator over the same context manager.

The dependency is kept rather than telling routes to use the context manager directly, because FastAPI's `app.dependency_overrides` is how the existing route tests substitute a fake session (`test_monitoring_routes.py:195`), and that mechanism only works on a dependency. Removing it would force a rewrite of tests this change has no business rewriting.

**Alternative considered — expose only the session factory** and let each caller manage `async with`. Rejected: it puts the release-on-exception obligation on every call site, which is exactly the kind of thing that is correct in all four call sites today and wrong in the eighth.

### Engine creation stays lazy; the session factory is created with it

Laziness is required by `runtime-configuration`'s import/start guarantee and enforced by two fresh-interpreter tests. The engine is therefore built on first session request, not at import and not in the lifespan.

The `async_sessionmaker` moves beside the engine and is built once with it, rather than per request as today. It is stateless with respect to individual sessions, so this changes no behavior — it removes a per-request allocation and puts the `expire_on_commit=False` setting in one place instead of leaving it to each caller to remember.

### Disposal happens in a FastAPI lifespan, and tolerates an engine that was never created

`main.py` gains an explicit lifespan whose shutdown half disposes the engine if one was created and returns otherwise. The "if one was created" branch is not defensive padding — it is the path both `TestClient` guards take, since neither ever requests a session.

**The wiring itself needs its own test.** Adding `dispose_engine()` and forgetting to pass `lifespan=` to `FastAPI(...)` would leave the change's headline defect — the engine is never disposed — in place while every unit test, both regression guards, `mypy`, `ruff` and `lint-imports` still pass, because the guards all take the no-engine path. A test that starts and stops `main.app` with an engine in existence, asserting disposal happened, is the only thing that can catch it before the post-deploy `pg_stat_activity` check.

**Alternative considered — an `atexit` handler.** Rejected: engine disposal is a coroutine, and `atexit` runs after the event loop is gone. The lifespan is the mechanism designed for this.

### The container's start command must `exec` the server, or the lifespan never runs

A lifespan only runs its shutdown half if the process receives a shutdown signal, and in this deployment it does not.

The `Dockerfile`'s `CMD` is `["sh", "-c", "uv run python -m commerce_ops.preflight && uv run alembic upgrade head && uv run uvicorn ..."]`. Because the final command sits in an `&&` list, `sh` does **not** exec-optimize it: verified directly — `sh -c 'true && sleep 20'` leaves `sh` as the running process with `sleep` as a forked child. In the container that makes `sh` PID 1 and uvicorn a grandchild. `docker stop` sends SIGTERM to PID 1; `sh` does not forward signals to children; uvicorn never learns it is stopping; ten seconds later Docker sends SIGKILL.

**So without this fix, every task in this change could pass and the deployed engine would still never be disposed** — the lifespan would be correctly written, correctly wired, and never invoked. The post-deploy `pg_stat_activity` check would show connections lingering and point at the code, which is the wrong place to look.

The remedy is one word: `exec` before the final command, so uvicorn replaces the shell and becomes PID 1. `uv run` must also pass the signal through rather than swallow it, which is why the verification is an observation of uvicorn's own shutdown log rather than an inspection of the command string.

This is a pre-existing defect, not one this change introduces — graceful shutdown has never worked in this deployment. It is in scope here because this change is the first to depend on it, and fixing it elsewhere would leave this change's central requirement unmet for reasons invisible in its own artifacts.

**Fallback, if `uv run` does not forward the signal.** `exec uv run uvicorn ...` puts `uv run` itself at PID 1, not uvicorn — that is sufficient only if `uv run` forwards SIGTERM to the child process it spawns. Verified directly (task 3.4, local image build against a real Postgres): `docker stop` returned in well under a second and uvicorn logged its own "Shutting down" / "Application shutdown complete." sequence, so `uv run` does forward it and no further change is needed. Had that verification instead shown uvicorn never logging shutdown, the remedy would have been to put uvicorn itself at PID 1 — e.g. `exec uv run --no-sync uvicorn ...` if `--no-sync` alone proved insufficient, or invoking uvicorn through its own installed console script directly (bypassing `uv run`'s process wrapping) after `uv sync` has already run in the preceding `&&` steps. This is recorded so a future regression here is a known, bounded fix rather than a rediscovery.

Note this covers the HTTP process only. The worker process the scheduler change introduces is a separate container with its own pool, and will need its own disposal at its own shutdown; the provider exposing a single explicit disposal function is what lets that be a one-line call there rather than a second design. This is why the delta's requirement binds "a process that has obtained a session" rather than "the application" — the latter would read, once archived, as a standing requirement the worker silently fails until its own change lands.

### `DATABASE_URL` is read directly, in one place, with the scheme validated at the read

Reading it through `get_settings()` is unavailable for the reason in Context. The read therefore stays an `os.environ` read, but moves from a driving adapter into the provider, so there is exactly one **inside the application process**. `alembic/env.py:24` reads it too, in the separate migration process the `Dockerfile`'s `CMD` chain runs before uvicorn; that is out of scope here and deliberately left alone.

The scheme check the settings model already declares (`postgresql+asyncpg`) is applied at this read too. Without it, a plain `postgresql://` URL fails inside SQLAlchemy with an error naming neither the variable nor the required scheme — the exact failure `settings.py`'s `_must_be_an_async_postgres_url` was written to prevent, and which is currently only prevented in preflight. Reusing that validator rather than restating the scheme keeps one definition.

Absence and emptiness are reported the same way, naming `DATABASE_URL`, rather than surfacing as a bare `KeyError` as they do today.

### `monitoring.py` keeps a `get_session` name

Its `get_session` becomes a re-export of the provider's dependency rather than disappearing. `test_monitoring_routes.py` overrides `monitoring.get_session` by attribute, and `monitoring.py`'s module docstring explains that its collaborators are referenced as bare globals specifically so tests can substitute them. Keeping the name means this change touches no test in that file — and the scheduler change, which retires those routes, removes the name then.

## Risks / Trade-offs

- **Adding a lifespan to `main.py` could break the `TestClient` guards.** → The shutdown path returns early when no engine was created, which is the path both take; both files are run unmodified as an explicit task, not assumed to pass.
- **A single pool is a single point of contention *within one process*** — two callers sharing a process share its connection limit. This does **not** describe the scheduler's worker, which is a separate container and therefore has its own pool no matter what this change does. → The contention risk applies only to callers genuinely sharing a process, which today means HTTP request handlers alone. What the single provider buys across processes is different and still worth having: one engine construction, one `DATABASE_URL` read, one scheme validation, and one place to change pool sizing when the aggregate against Postgres's `max_connections` needs bounding.
- **`lru_cache` on an engine factory holds it for the process's life, so disposal must be paired with cache invalidation** or a disposed engine is handed to the next caller. → Disposal clears the cache as part of the same operation; a test requests a session after disposal to confirm a usable engine is produced rather than a disposed one.
- **The `get_settings()` trap described in Context stays live** after this change. → Out of scope by explicit non-goal, but now recorded in a design document rather than only in a settings docstring. It deserves its own change.

## Migration Plan

1. Add the provider with engine, session factory, standalone context manager, dependency, and disposal.
2. Point `monitoring.py`'s `get_session` at it and delete `_get_engine`.
3. Add the lifespan to `main.py`.
4. Run the two fresh-interpreter guards unmodified, then the full suite.

No schema change, no data migration, no external contract. Rollback is reverting the commit; the previous behavior — one engine owned by a driving adapter, never disposed — returns intact.

Deploy verification: `docker logs` shows a clean shutdown on the next redeploy, and Postgres's `pg_stat_activity` shows the previous process's connections gone rather than lingering until timeout.
