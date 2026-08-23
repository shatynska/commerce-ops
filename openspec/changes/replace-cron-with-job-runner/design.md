## Context

See proposal.md — Why. Constraints that shape the approach:

- **The application connects to Postgres with `asyncpg`**, through SQLAlchemy's async engine. The scheme is validated as `postgresql+asyncpg` in `settings.py`, and `alembic/env.py` runs migrations over that same async engine.
- **`centralize-database-session` must land first.** The worker runs outside any HTTP request; today the only way to obtain a session is to import a `products` driving adapter or construct a second engine.
- **`configure-application-logging` must land first.** A worker's output is its value, and application `INFO` records are currently discarded.
- **Schema changes go through Alembic.** One migration exists, applied by the `Dockerfile`'s `CMD` chain — `preflight && alembic upgrade head && uvicorn` — before uvicorn starts.
- **The `Dockerfile` defines a `HEALTHCHECK`** polling `http://localhost:8000/health`. It is baked into the image, so every service built from that image inherits it.
- **`.importlinter` forbids `shared` from importing any business module**, in both directions of the layered contracts. Anything cross-cutting that needs to reach `products` must either live in `products`, or take a port and be wired by an entry point outside the contracts.
- **Deployment ships two files only** — `docker-compose.yml` and a rendered `.env` — over one SSH session to a forced command.

## Goals / Non-Goals

**Goals:**

- Scheduled work that retries, records what happened, and does not silently skip a window.
- No externally reachable interface whose purpose is to start internal work.
- A foundation that can express multi-step asynchronous work.

**Non-Goals:**

- **Overdue reporting and the freshness endpoint.** Split into `report-overdue-scheduled-runs`, which needs this change's run history to exist. They also carry their own decisions — module placement under the `shared`-cannot-import-`products` rule, suppression state and its schema, and what an externally reachable freshness endpoint may disclose — none of which belong in a change about replacing cron. **Until that change lands, a dead worker is undetected**, exactly as today.
- **The ClickUp reconciliation pass.** Nothing to reconcile: `clickup_client` has no caller in the tree.
- **Giving the four unimplemented cadences reporting content.** Their content depends on deferred marketplace data. They keep their use case and lose their schedule.
- **Distributed or multi-host workers.** One worker container on one host.
- **A general workflow engine.** Multi-week, human-in-the-loop launch workflows may eventually justify Temporal (see Decisions); nothing in the MVP does.
- **Run-history retention.** The history grows unbounded; at one daily job that is years away from mattering, and pruning naively would delete the last-success evidence `report-overdue-scheduled-runs` reads. It belongs with that change or later, deliberately.

## Decisions

### Adopt `procrastinate`, accepting a second Postgres driver

`procrastinate` 3.9.0 is a Postgres-backed task queue: jobs in a table, `LISTEN`/`NOTIFY` for wakeup, asyncio-native, periodic tasks via `croniter`, retry strategies with exponential backoff, and job status/attempt history in its own tables. No broker, no Redis, no additional service.

**Its cost, stated plainly: it depends on `psycopg[pool]` (psycopg 3), while this application connects with `asyncpg`.** Two Postgres drivers in the process, and a second pool.

**And that driver needs a libpq wrapper it does not bring with it.** Installing `procrastinate>=3.9,<4` into a clean environment pulls `psycopg` and `psycopg-pool` but no wrapper, and `import procrastinate` fails with "no pq wrapper available" until `psycopg[binary]` is added. `asyncpg` bundles its own, so nothing currently in this tree establishes that libpq is present on a developer machine or in the image. The dependency therefore names the binary extra rather than assuming the system library — recorded as a decision, because the failure it prevents surfaces at import time and reads as a broken test suite rather than a missing library.

This is compatible with `centralize-database-session` **as that change is now written**, and on the requirement's own terms rather than by reading around it. That requirement governs how the application obtains sessions reaching **domain data**, and exempts infrastructure holding a connection or pool of its own for its own bookkeeping. The queue's driver serves the queue's own tables and its `LISTEN`; it is never a route to products, launches or any other domain data, which continue to come from the single provider and its pool. An earlier draft of this design argued instead about what the requirement "was protecting" — reinterpreting rather than amending, which was the wrong move; the requirement itself was corrected at its own address, with the reasoning recorded there.

What that requirement does **not** do is bound the aggregate connections the deployment opens against Postgres's `max_connections`, and adding a second pool makes that bound less notional. It is a stated non-goal there rather than an oversight; noted here because this change is what first makes it matter.

Two drivers remains a genuine maintenance cost — two sets of connection semantics, two things to keep working across a Postgres upgrade. It is accepted, not dismissed.

**Alternative considered — `pgqueuer` 0.26.1.** It avoids the second driver entirely: `asyncpg` is one of its supported drivers, and it offers cron-style recurring tasks, `execute_after`, and retry strategies. On driver consistency it is the better fit. Rejected on maturity: it is pre-1.0, and this component's entire reason to exist is that scheduled work must be trustworthy. Taking a pre-1.0 dependency for the reliability layer trades the problem this change is solving for a differently-shaped version of it.

**Alternative considered — Temporal.** The right answer for durable multi-month workflows, which the launch process eventually is. Rejected for now: operating a Temporal server and worker fleet is a large commitment to make before the first scheduled job works reliably. Recorded so a later launch-workflow change revisits it deliberately.

**Alternative considered — APScheduler in the app process.** Rejected: its persistence is a job *store*, not a run history, and an in-process scheduler dies with the process it is in.

**On reversibility.** The domain use cases (`run_daily_digest`) are untouched and uncoupled from the runner; what is coupled is the job definitions, the worker entry point, and the last-success accessor this change adds. That accessor is a real coupling to the runner's own tables, and it is worth naming rather than claiming the runner is trivially swappable.

### Install the runner's schema through Alembic, and state the mechanism

`procrastinate` ships schema-management commands of its own. Using them would mean two mechanisms applying schema to one database with no shared ordering, and a second startup step with its own failure mode. Instead one Alembic migration applies the runner's schema SQL, keeping Alembic the single answer to "what shape is this database, and how did it get there", pinning the runner's schema version to a migration revision, and giving `downgrade` a place to drop it.

**The mechanism has to be written down, because it is not free.** `alembic/env.py` runs over the `postgresql+asyncpg` engine, and the runner's schema is a multi-statement script including `$$`-quoted function bodies. SQLAlchemy's asyncpg dialect routes `execute()` through prepared statements, which reject multi-statement scripts. `exec_driver_sql` is **not** the way out, despite the name: it is a SQLAlchemy `Connection` method that routes through dialect execution and lands on the same prepare (verified against the installed SQLAlchemy). The escape is asyncpg's own `Connection.execute()`, reached from the raw driver connection beneath the bind — and because the migration body runs synchronously inside `connection.run_sync(...)`, awaiting it needs the greenlet bridge `sqlalchemy.util.await_only`. An explicit `$$`-aware statement split is the fallback, and is the fragile branch.

This is the part of the change most likely to need adjustment on contact, so the task asserts the mechanism rather than the outcome, and the fallback (accepting the runner's own CLI as a second schema mechanism) is recorded as the thing to fall back to if it proves impractical.

**And a hazard that neither branch avoids: autogenerate will propose dropping the runner's tables.** `alembic/env.py` sets `target_metadata = Base.metadata` with no `include_object` or `include_name` filter. `Base.metadata` describes `products`' models only. Once the runner's tables exist in the database and not in that metadata, the next `alembic revision --autogenerate` anyone runs — for an unrelated feature, months from now — emits `op.drop_table` for every one of them, destroying the run history that this change's own "Every Run's Outcome Is Recorded And Can Be Asked About Afterwards" requirement and the whole of `report-overdue-scheduled-runs` depend on.

This is not a consequence of choosing Alembic over the runner's CLI: the tables are unknown to the metadata either way, so the recorded fallback is no mitigation. It therefore belongs here rather than in an implementer's judgement.

The remedy is an `include_name`/`include_object` filter rejecting the runner's table prefix, plus a test asserting the filter actually names those objects, so removing it fails rather than silently arming the hazard again.

A table-name filter is sufficient because autogenerate's comparison covers tables, columns, indexes and constraints — it does not emit drops for functions, triggers or enum types, so tables and what hangs off them are the whole hazard. That is the criterion for reading task 1.8's empirical run as clean.

The predicate lives in an importable module under `src/`, not in `alembic/env.py`: that file has no package around it and executes `context.config` at import, so a predicate defined there could not be unit-tested. It is passed at both the offline and online `context.configure()` calls, so the two paths cannot diverge.

**Alternative considered — install the runner's schema into a dedicated Postgres schema.** Stronger, since autogenerate does not reflect non-default schemas without `include_schemas=True`, so the exclusion holds even if someone deletes the filter. Rejected as the default on cost: it needs a search-path or a schema-qualified connection string for the queue, and the last-success accessor's raw SQL would need schema-qualifying too. (An earlier draft also claimed it would create "a second place where what shape is this database is answered" — that is wrong, since the dedicated schema would still be created by the same Alembic migration, and the rejection does not need it.) Worth revisiting if the filter ever proves fragile.

### The worker is a separate service from the same image, with the healthcheck overridden

`docker-compose.yml` gains a `worker` service using the same `image:` and `env_file:` as `app`, overriding `command:`. Same image because the worker imports the same application code, and a second image would let the two drift.

Separate service rather than a thread in the app process: the spec requires a worker failure not to stop HTTP being served; a long-running job would otherwise compete with request handling in one event loop; and `app` can be restarted or rolled without interrupting a job mid-flight.

**The image's `HEALTHCHECK` must be overridden.** It polls `http://localhost:8000/health`, which the worker does not serve — inherited unchanged, the worker reports unhealthy for its entire life. In a change whose purpose is making a half-up deployment detectable, leaving a permanently-red health signal on the new service would poison the signal on day one. The worker declares `healthcheck: disable: true`: a process whose liveness question is "is it running jobs" is not answerable by an HTTP probe, and answering it properly is `report-overdue-scheduled-runs`' job, from outside.

**Ordering.** The worker depends on `postgres` being healthy *and* on `app` being healthy. The second is not a leftover from the retired `cron` service's HTTP coupling — the worker never calls `app` over HTTP. It is schema readiness: `app`'s command chain runs `alembic upgrade head`, and `app` becomes healthy only after it completes, so `depends_on: app: condition: service_healthy` is what stops the worker starting against a database with no runner schema and crash-looping until the migration lands.

The worker joins `app_db` only — no HTTP surface, so no `platform_edge`. The `app_cron` network is removed with the `cron` service.

### The schedule is interpreted in UTC, and `TZ` is set to UTC to match

**The runner offers no timezone to declare, so UTC is not a preference here — it is the only zone available.** Verified against `procrastinate` 3.9.0 and its `croniter` 6.2.4 dependency: `PeriodicTask` constructs `croniter.croniter(self.cron)` with no timezone parameter, and the deferrer evaluates it from POSIX timestamps, which croniter reads as UTC. Ticks computed under `TZ=UTC`, `TZ=Asia/Kolkata` and `TZ=America/New_York` were identical.

The property the spec actually needs — that a schedule does not shift with the host it runs on — therefore holds **structurally**, without configuration, which is stronger than holding by a setting someone can get wrong. What does not exist is a way to *configure* the zone: an earlier draft of the requirement asked for "an explicitly configured timezone", and nothing in the runner could have satisfied it. The requirement was restated to say UTC; the test asserting host-independence was left alone.

`TZ=UTC` is then set on both services for a different purpose: making log timestamps unambiguous and matching the schedule, so a reader is not converting between two zones. It does not influence scheduling, and could not.

UTC rather than the team's local timezone would have been the choice anyway: a local zone shifts the daily digest by an hour twice a year relative to everything else in the logs, and DST transitions are a recurring source of jobs that run twice or not at all. The cost is that "06:00 daily" is not 06:00 for the team; the fix, when it matters, is choosing the UTC hour that lands where the team wants it — a schedule change, not a timezone change.

That is now the **only** lever. A zone observing DST cannot be expressed at all without wrapping the runner's deferrer, which this change does not do; a fixed-offset zone is expressible only as the equivalent UTC hour. If a real requirement for a local zone appears, it is a change against the runner's periodic machinery, not a setting.

### The daily job definition lives in `products`, not in `shared`

A scheduled job is a **driving** adapter: it calls into the application layer, exactly as the retired HTTP route did. So the daily digest's job definition belongs in `products/infrastructure/driving/`, taking the place of `monitoring.py`'s routes, where it may freely reach `products`' own notifier and repository.

Two things live in `shared/infrastructure/driven/` instead: the runner's application object — the queue itself, infrastructure the whole process shares — and the last-success accessor over the runner's job history, which belongs beside the queue it reads and which `report-overdue-scheduled-runs` consumes from both the worker and the HTTP process.

**The accessor queries through the session provider, not the runner's connector.** The sibling's freshness endpoint calls it from the HTTP process, which would otherwise acquire the queue's psycopg pool for a read that is not queue work — widening the two-driver footprint this design scopes to the worker. The cost, stated: reading the queue's tables with the application's own SQLAlchemy session means raw SQL against the runner's physical schema rather than its supported job-manager API, which is a tighter coupling than the reversibility note above admits. Accepted, because keeping the second driver out of the HTTP process is worth more than insulating one read. `products.infrastructure` importing `shared.infrastructure` is already permitted and already practised (`monitoring.py` imports `shared.infrastructure.driving.trigger_guard` today).

This keeps `shared` free of any `products` import, which `.importlinter` enforces. The harder version of this problem — a genuinely cross-cutting check that must post to a `products`-owned Slack channel — arrives with `report-overdue-scheduled-runs` and is that change's to solve.

### Retries: exponential backoff, a small maximum, and no retry on delivery failure

The daily digest retries with exponential backoff up to a small maximum. Its failure mode is a transient database or network problem; if it is still failing after several spaced attempts, the problem is not transient.

**Retries make the failure message a per-outage decision, not a per-run one.** Posting "could not read products from the database" on every attempt turns one outage into three identical Slack messages — the change that exists to make failure visible making it noise instead. So the message is posted only on the attempt the retry strategy will not retry. The job body therefore needs both the current attempt number, which the runner supplies in its job context, and the declared maximum, which it reads from the same place the retry strategy is configured rather than from a second literal. This makes the retry maximum load-bearing on behavior and not only on timing, which is why it is recorded here and not left to Open Questions.

Slack delivery failure explicitly does **not** retry and does not fail the run — recorded as a requirement in the `product-monitoring` delta with its rationale: a delivery failure does not establish that nothing was delivered, so retrying trades a possible duplicate report for a report that is stale by the time it lands.

### A missed window runs once, not once per window

The runner must be configured deliberately here, because both plausible behaviours are defensible in general and only one is right for a report. A digest is a statement about the present; replaying four missed daily windows produces four stale reports and no useful information, while skipping silently is the defect this change exists to fix. Running once on return is the only option that is neither.

**The knob is `App(periodic_defaults={"max_delay": ...})`, and its default is wrong for this job.** `PeriodicDeferrer`'s `max_delay` defaults to 10 minutes, and a due moment older than that is **dropped** — the runner's own docstring calls this deliberate, "especially important for tasks intended to run during off-peak hours, such as intensive nightly tasks", which is precisely the shape of this digest. Left at the default, a worker outage spanning more than ten minutes across 06:00 silently skips that day — reproducing, inside this change, the second bullet of proposal.md's Why.

**So `max_delay` is set wide enough that no plausible outage drops a window.** Once it is, "several missed windows produce one run" holds by construction: a freshly-started deferrer yields only the most recent tick.

**A late digest is not a stale one, and that asymmetry is the whole reason for choosing no bound.** The staleness argument above is about replaying a *backlog* — four reports where one was wanted. It says nothing against a single run that happens late, because the job re-reads the database when it runs: a digest produced six hours after its due moment reports the products that exist six hours after its due moment, which is current information, merely later than intended. Reading the staleness argument as also arguing for a tight lateness bound is the mistake this paragraph exists to prevent; the next reader will otherwise reach for the ten-minute default and think the text supports it.

If a bound is ever wanted, it belongs in the requirement rather than in a setting: "run once on return" with an unstated threshold past which the run is silently dropped is exactly the shape of undocumented behaviour this change was written against.

## Risks / Trade-offs

- **Two Postgres drivers in one process.** → Accepted, with the reasoning above, and compatible with the prerequisite's requirement as written rather than by reinterpretation.
- **A new silent-failure mode: `worker` is not running, so nothing scheduled happens, while `app` looks healthy.** → Real, and **not addressed by this change** — that is `report-overdue-scheduled-runs`. Named plainly because splitting the work means this interval exists. It is no worse than today, where the same failure exists undetected; it is a new *shape* of it.
- **The runner's schema now lives in this project's migration history.** → Deliberate. A runner upgrade with schema changes becomes a migration to write, which is better than two schema mechanisms on one database.
- **The Alembic-over-asyncpg mechanism may not survive contact.** → The task asserts the mechanism, not just the outcome, and the fallback is recorded.
- **Removing `internal-trigger` removes the only manual trigger**, which is genuinely useful in operations. → The runner's CLI can defer a job from inside the container, which covers the operational need without a public endpoint. A Slack command, if wanted, belongs in a change that designs it with the `product_agent` app's own authorization.
- **A Postgres-wide outage defeats the attempt-gating entirely.** The queue lives in the same Postgres as the domain data, so if Postgres is unreachable the worker cannot fetch the job, cannot mark it failed, cannot schedule a retry, and never reaches the final attempt on which the message is posted — the outage most obviously deserving a Slack message produces none, and no run record either. → The gating is correct for failures that leave the queue's own connection usable (pool exhaustion, a statement timeout, a `products`-table fault). The wider case is `report-overdue-scheduled-runs`' territory: no run recorded is exactly what its overdue check detects. Named so the boundary is on the record rather than discovered during a silent morning.
- **The four cadences leaving the schedule could read as functionality removed.** → No reporting behavior is lost: all four log and return today. What is removed is the appearance of scheduled work where none exists.

## Migration Plan

1. Land `configure-application-logging` and `centralize-database-session` — hard prerequisites.
2. Add the dependency and the Alembic migration; confirm `upgrade head` and `downgrade` both work against a local Postgres, through the stated execution mechanism.
3. Add the runner object, the daily job definition, and the worker entry point. The job calls the existing `run_daily_digest` use case through the session provider, unchanged.
4. Replace `cron` with `worker` in `docker-compose.yml`: healthcheck disabled, `TZ`, both `depends_on` conditions.
5. Remove the five routes, `trigger_guard.py`, `TRIGGER_SECRET`, and the tests belonging to them; amend the five regression guards that transcribe it.
6. Deploy. `docker-compose.yml` ships whole, so `cron` is removed and `worker` created in the same `docker compose up`.
7. Verify: the worker logs its startup; a manually deferred job runs and is recorded; the next scheduled 06:00 run appears in the history.

**Rollback.** Revert the commit and redeploy: `docker-compose.yml` returns to the `cron` service, the routes and guard return with it. The runner's tables remain until `alembic downgrade` is run, which is harmless — unused tables — so no database step is required.

**One ordering constraint on rollback, and it is a trap.** Deleting `TRIGGER_SECRET` from the GitHub Actions `production` environment must **not** happen at the same time. Once deleted, a revert restores the `cron` service and the fail-closed guard, `.env` renders no secret, and all five `wget` calls receive 401 into `/dev/null` — silently reproducing the exact failure this change exists to remove. So the secret is deleted only after a soak period during which rollback is no longer contemplated, and the runbook says so.

## Open Questions

- **What is the daily digest's retry maximum and backoff base?** Does not change the specs, the approach or the task breakdown; better chosen with a week of real behavior. An initial figure is recorded in the task list.
