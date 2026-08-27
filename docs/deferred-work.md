# Deferred work

Things this project has deliberately **not** done, recorded so they are not rediscovered as surprises.

Each item is already argued somewhere — in a change's `design.md`, a non-goal, or an open question. That is the right place for the reasoning, and this file does not repeat it. What this file adds is **findability**: a change's artifacts move to `openspec/changes/archive/` once it ships, and a deferral recorded only there is a deferral nobody will find again.

Delete an entry when it is done or when it stops being true. An entry that no longer holds is worse than no entry.

---

## Belongs to the `/infrastructure` repository, not this one

These affect the host or the deployment platform, and would be wrong to fix here.

### Docker log rotation — unhandled

Docker's default `json-file` driver runs with **no `max-size`** anywhere on this host. Container logs grow unbounded on the boot disk, and `configure-application-logging` increases the rate by making application `INFO` records visible for the first time.

A repository-wide search of `/infrastructure` for `max-size`, `log-driver`, `log_opts` and `logrotate` returns **nothing**, so this is genuinely unconfigured rather than configured elsewhere. It belongs in that repo's host configuration — the `geerlingguy.docker` role takes `docker_daemon_options`, which writes `/etc/docker/daemon.json` — because it affects every container on a shared host, not just this application.

**Recorded in**: `configure-application-logging`'s `design.md` (Non-Goals) and `proposal.md` (Impact).

### `app-deploy` does not remove retired services

The host runs `docker compose pull && up -d --wait`. Removing a service from `docker-compose.yml` does **not** stop or delete its running container — Compose leaves orphans in place unless `--remove-orphans` is passed, which `app-deploy` does not.

Observed rather than theorised: `replace-cron-with-job-runner` deleted the `cron` service, and after **two** subsequent deploys `commerce-ops-cron-1` was still `Up`, firing `wget` at endpoints that no longer exist over a network `app` had already left. Harmless in that instance — the requests failed DNS resolution before reaching anything — but the container was removed by hand, and nothing in the pipeline would have removed it.

The consequence is general: any future change that retires a service leaves its container running on the host until someone notices. It is not visible from this repository, since `docker-compose.yml` correctly describes the intended state; only `docker compose ps` on the host reveals the difference.

The fix is a flag in that repo's `app-deploy` script. It is not free of judgement — `--remove-orphans` deletes any container Compose does not recognise, so a service someone added out-of-band would be removed too — which is why it belongs with the people who own the host rather than being asserted from here.

**Recorded in**: `replace-cron-with-job-runner`'s task 6.5.

### No external checker polls the run-freshness endpoint

`report-overdue-scheduled-runs` exposes `/health/scheduled-runs` precisely so something **outside** the deployment can detect a dead worker — a check running inside the worker cannot observe the worker's own absence. No uptime monitor is configured in this project or in `/infrastructure`.

Until one polls it, the dead-worker case is *detectable*, not *detected*. The endpoint reduces the remaining work to a configuration task rather than a development one.

**Recorded in**: `report-overdue-scheduled-runs`'s `design.md` (Open Questions) and its task 7.6.

### Postgres backups are boot-disk snapshots only

`/infrastructure`'s `terraform/environments/prod/main.tf` sets `backups = true`, so Hetzner snapshots the **boot disk**. Docker's data-root is not relocated, so `commerce_ops_pgdata` sits there and *is* inside those snapshots.

The caveat: that is a whole-server image of a *running* Postgres. Recoverable via crash recovery in practice, but there is no `pg_dump`, no point-in-time recovery, no tested restore, and no way to restore the database without rolling back the entire server. Adequate for the MVP; worth a real dump job before there is data anyone would miss.

Note also that `/infrastructure`'s own `add-prod-data-volume` design records that the attached Hetzner **volume** has no backup equivalent. That does not bite yet, because Postgres is not on it — but it would the moment Docker's data-root moved.

---

## Deferred technical work in this repository

### `get_settings()` cannot be used as a runtime accessor

`pydantic-settings` validates the whole model on construction, so `get_settings()` raises if **any** required variable is faulty. `preflight.py` deliberately lets the process start when a non-startup-critical variable is faulty — that is `runtime-configuration`'s "Only A Startup-Critical Fault Prevents Startup".

The two combine into a live trap: a deployment missing only `PRODUCT_AGENT_SLACK_BOT_TOKEN` starts by design, and every `get_settings()` call in it then raises. **This is why every module in the tree reads `os.environ` directly** — the settings model is a declaration plus a startup check, not an accessor.

Fixing it changes the shape of the declaration `runtime-configuration` specifies and affects every reader, so it deserves its own change rather than riding along inside one.

**Recorded in**: `centralize-database-session`'s `design.md` (Context, and an explicit non-goal).

### Aggregate connections against `max_connections` are unbounded

`database-session`'s one-pool requirement governs **domain-data access**, and explicitly exempts infrastructure holding its own connection or pool for bookkeeping — which is what lets the job runner's second driver comply. What no requirement does is bound the *total* connections the deployment opens against Postgres's `max_connections`.

Stated as a non-goal rather than an oversight: bounding it means knowing every component's pool size and the server's limit, which is deployment-wide tuning with no workload to tune against yet. Whoever first hits a connection ceiling owns it.

**Recorded in**: `centralize-database-session`'s `design.md`, "What is now unbounded, stated plainly".

### Run-history retention

The job runner's history grows without limit. At one daily job that is years from mattering, and pruning naively would delete the last-success evidence `report-overdue-scheduled-runs` reads to decide what is overdue. Any future retention work inherits that constraint.

**Recorded in**: `replace-cron-with-job-runner`'s `design.md` (Non-Goals).

### Repositories commit their own writes, so a caller cannot own a transaction

`CatalogProductRepository.add` and `LaunchRepository.save` each end with `await self._session.commit()`, and `add` performs its own `rollback()` before raising `DuplicateSkuError`. Two writes through two repositories are therefore **two transactions**, however carefully a caller shares one session between them.

That collides with `launch-entry`'s "Registration and start are atomic", whose scenario is precisely: registration succeeds, the launch start is rejected, and *neither* may survive. `start-launch-from-slack`'s `design.md` Decision 3 specifies the mechanism as "both writes run in a single `session()` scope" — which does not hold against repositories that commit inside that scope.

**What was built instead**, to ship the capability: `shared/infrastructure/driven/database.py`'s `transaction()` binds a session to an explicit connection with SQLAlchemy's `join_transaction_mode="create_savepoint"`, so each inner `commit()` releases a SAVEPOINT and each inner `rollback()` unwinds only to one. The outer transaction, begun and ended by that provider, is the only thing that decides whether anything persists. It is a **workaround at one call site** for a property the repositories should have.

**The right fix** is to make those repositories commit-neutral — the write, the flush, and the domain-rejection translation stay; the `commit()` moves out to whoever owns the unit of work. Deferred rather than done here because it is not this change's scope: `CatalogProductRepository` and `LaunchRepository` are also called by the ClickUp webhook, the completion-loop sync job and the daily digest, each of which would need its transaction boundary decided. That is its own reviewable change.

Until then, any *new* caller needing two writes to land together must use `transaction()`, not `session()` — and every other caller still relies on its repository to commit.

**Verified against Postgres** (2026-08-24): `tests/integration/launch/test_slack_entry_start.py` passes, including the scenario that forces the launch start to fail after a real catalog write and asserts nothing survives and the SKU stays free for resubmission.

**Recorded in**: `start-launch-from-slack`'s `design.md` (Decision 3); the workaround is documented on `transaction()` itself.

### The ClickUp variables are optional, and the reason has weakened

`CLICKUP_API_TOKEN`, `CLICKUP_LAUNCH_FOLDER_ID` and `CLICKUP_WEBHOOK_SECRET` are all declared optional. The project owner has asked for them to be **required** (2026-08-24). Note what that would and would not do: required is not startup-critical, so preflight would report an absent variable *by name* and the application would still start and serve. It buys visibility at startup, not a refusal to boot, and it changes no runtime behaviour — every consumer reads `os.environ` directly.

**The two halves are not the same problem.**

`CLICKUP_LAUNCH_FOLDER_ID` and `CLICKUP_WEBHOOK_SECRET` are optional by *design choice*, recorded only in a settings comment. No specification requires it. `launch-clickup-sync` already demands the stronger runtime behaviour — "when the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped" — so marking them required adds a startup report on top of a guarantee that already exists. Compatible; a small change.

`CLICKUP_API_TOKEN` is different: `clickup-task-client` explicitly requires that the system "SHALL NOT require that credential to be present except when a request is actually made", with a scenario stating that nothing fails when the application starts without it. Marking it required contradicts that requirement as written, so it needs a `MODIFIED` delta against that capability, not a settings edit.

**There is a real argument for amending it.** That requirement was written when `clickup_client` had no caller at all. Since the completion loop shipped, ClickUp is load-bearing — the only thing projecting a launch's work, converging every 30 minutes — and a launch started from Slack now depends on it. "Absent until first use" is a reasonable rule for an unused client and a weak one for a credential the system needs continuously. Whoever picks this up should argue that change on its merits rather than quietly flipping the declaration.

**Recorded in**: `clickup-task-client`'s "Authentication is configured independently of any one caller"; `launch-clickup-sync`'s projection requirement; the optionality comments in `shared/application/settings.py`.

**Before that configuration lands, clear the test launches.** Checked on the deployment 2026-08-24: `launch_positions` holds 4 rows pinned to `v1`, all of them test launches started while trying out `start-launch-from-slack`, and the owner has confirmed they are disposable. None has ever been projected — the deployment carries no `CLICKUP_*` variable at all, so no convergence pass has reached ClickUp and no per-launch list exists. The moment a token and a valid folder id arrive, the first pass would project roughly 92 tasks per launch, about 368 in total, onto launches nobody wants. Delete them first: the five child tables cascade on delete, and here there is no ClickUp list left behind to archive by hand.

**A second, separate defect in the same area.** `CLICKUP_LAUNCH_FOLDER_ID` is currently set to `901220457229`, which is the id of the *list* named "Launches", not a folder — `GET /list/901220457229` resolves, `GET /folder/901220457229` does not. Projection creates one list per launch inside a parent folder, so that value cannot work even once the token is present. Whoever takes this up needs a real folder id, not just the three variables added to `deploy.yml`.

### The parked `add-product-creation-clickup-task` change — superseded

**Closed out by `start-launch-from-slack`**, which covers this ground on current foundations: a slash command and modal on the `product_agent` app that registers the product and starts its launch. The ClickUp half of the parked proposal is obsolete rather than deferred — the completion loop (`launch-clickup-sync`) now projects a launch's whole list and per-step tasks automatically, so a single hand-created task would be duplicated or fought by the next convergence pass. It remains true that `clickup_client` gains no new caller from this direction.

The local branch holding that proposal (`0b9b85c`) was deleted on 2026-08-24, once this change shipped. This entry survives it only so the supersession stays findable; the reasoning is in the archived change.

**Recorded in**: `start-launch-from-slack`'s `proposal.md` (Why).

### `playbook_admin`'s guard does not fail closed when its collaborators are un-injected

`playbook_admin.py` takes `directory` and `admin_sessions` as module-level globals that `main.py` assigns after the app is built. The comment above them states that "absent injection refuses every request, which is the failing-closed direction". **That is not what happens.**

Observed rather than theorised, against the module as it stands: with both globals at their `None` default, a request bearing *no* cookie returns `404` — correct, because `_require_admin` short-circuits before touching them. A request bearing *any* cookie reaches `verify_admin_session`, which calls `sessions.find(...)` on `None` and raises `AttributeError`, producing **`500 Internal Server Error`**.

That breaks `admin-session`'s requirement *"Admin access fails closed and absence-shaped"* twice over: a `500` is not a refusal, and it is trivially distinguishable from the `404` an unregistered route returns — so an un-injected deployment advertises that the admin surface exists to anyone who sends a cookie.

**Latent, not live.** `main.py` assigns both globals at import, so a normally started application never reaches this state. The exposure is to a future composition root that adds a route, reorders startup, or mounts this router in a second app without repeating the assignment — exactly the kind of drift the "one guard, produced in one place" design exists to prevent. `admin_link.py` does not share the hole: it builds its `admin_sessions` at import time rather than receiving it.

Not fixed in `reorder-steps-under-filters`, which added a route riding the same guard and verified that route's *refusal* shape, but did not change the guard. A fix is small — refuse when either global is absent, before the cookie is read — and belongs with a test at the `admin-session` tier rather than folded into an unrelated change.

**Recorded in**: `reorder-steps-under-filters`'s implementation notes; the false claim is the comment above `directory`/`admin_sessions` in `playbook_admin.py`.

### `procrastinate` and `psycopg_pool` can outlive a cancellation

Two library behaviours combine so that **a cancelled task can survive its own
cancellation and run forever**, and any caller that cancels a task touching the
connection pool inherits them. They are recorded here because they are not
fixed — only this project's exposure to them was.

This is what made the integration tier hang intermittently until
`isolate-tests-from-the-shared-runner` (2026-08-25). The tests are no longer
exposed: the two files that start a worker own private `procrastinate.App`s
whose periodic registries are empty, so no side task loops, and a tier-level
guard in `tests/integration/conftest.py` fails any future test that starts a
worker against a registry holding production work. The archived change carries
the captured await chain and the measurements.

**`src/` still has a caller.** `worker.py:56` calls `register_all()` and
`worker.py:141` calls `app.run_worker_async()` with `install_signal_handlers`
defaulting to `True`, so the deployed worker runs this same cancel-and-gather
path over a periodic deferrer on **every** SIGTERM, with all three real jobs
registered. What bounds it there is not absence but Docker's stop grace
period: a wedged shutdown is ended by SIGKILL rather than hanging forever.
Benign in effect — but if a worker is ever seen being killed on stop rather
than exiting cleanly, this is the mechanism to look at first.

- `procrastinate`'s `cancel_and_capture_errors` (`utils.py:232`) gathers side
  tasks with no timeout after a single `cancel()`.
- `psycopg_pool` classifies `asyncio.CancelledError` as a retryable client
  exception (`pool_async.py:38`) and retries around it.

Three side tasks are cancelled on that path, not one. The periodic deferrer is
where this was caught, and it dominates because with an armed registry it does
pool work at `periodic.py:136` immediately, before its first sleep. But
`_update_heartbeat` (`worker.py:483-492`) and `_poll_jobs_to_abort`
(`worker.py:494-514`) loop over pool-backed calls too — they merely sleep
first, so a cancellation usually lands where it propagates. Their exposure is
inference from the same verified mechanism rather than something measured, and
it is the reason a rare stall should be checked against this entry before being
filed as something new.

Neither has been reported upstream.

### The create surface has no signed-out panel

Every other admin surface answers an expired session with a rendered panel — "Signed out … nothing was saved" — swapped in by `page.html`'s `htmx:responseError` handler. The create surface (`new.html`) shows FastAPI's raw `{"detail":"Not Found"}` instead.

**Two causes, and fixing either alone does nothing.** The handler fires only on an XHR (`event.detail.xhr`), and `add-step-page` deliberately un-boosts the transitions to and from the create surface so the success redirect's fragment is honoured — which removes the XHR. It also lives in `page.html`'s own inline script, which `new.html` does not carry, so re-boosting would not restore it either.

**No requirement is broken.** `admin-session`'s *Admin access fails closed and absence-shaped* asks only that the refusal be shaped like a missing route, and a raw 404 body satisfies that. What is lost is the explanation, on the one surface where an admin may have typed a screenful of fields before the session expired.

The fix is not just moving the script: the un-boosted create `POST` is a real form submission, so the browser navigates to the 404 rather than handing it to a JS handler at all. Whoever takes it up should decide whether the refusal is server-rendered for this surface instead.

**Recorded in**: `add-step-page`'s `design.md` (Risks / Trade-offs).

### Refresh-resubmit is fixed for creating and for nothing else

`add-step-page` made a successful create redirect (`303`) rather than render, so refreshing after a create no longer resubmits it. Editing, retiring, un-retiring, reordering and status changes all still render the list from their own `POST`, so a refresh on any of them re-submits the write.

Stated as an accepted asymmetry rather than an oversight: creating had to redirect regardless, because it is the one write that lands the admin on a *different* page from the one they posted to. `reorder-steps-under-filters` had already rejected Post/Redirect/Get for the others on a real constraint — a rejected write carries faults and submitted values, which a redirect cannot carry without a flash cookie. Making the rest symmetric means solving that, not copying the create route.

**Recorded in**: `add-step-page`'s `design.md` (Success redirects; rejection renders).

### Whether creating should offer a status at all

The create surface offers `draft`, `in-development` and `active` (never `retired`). It is not settled that it should: an author might always create a `draft` and reach `active` through the status control `redesign-step-fields` added, which is the validated transition with its own rules.

Nothing is broken either way — the creation requirement is written to hold for whichever status a step is created with, and carries a scenario for an `active` create and for a `draft` one. This is a question about what the form offers, not about what the page guarantees.

**Recorded in**: `add-step-page`'s `design.md` (Open Questions).

### The container start chain is ~14× slower on the host than locally

The `Dockerfile`'s CMD chain — `preflight`, `alembic upgrade head`, `seed_admin`, `seed_playbook`, `check_step_handlers`, then uvicorn — runs in **1.8s** locally against a real Postgres:

| Step | Local |
|---|---|
| `alembic upgrade head` | 0.59s |
| `preflight` | 0.11s |
| `seed_admin` | 0.31s |
| `seed_playbook` | 0.50s (inserting all 352 rows; 0.48s with nothing to add) |
| `check_step_handlers` | 0.31s |

On the deploy host the same chain reaches healthy at ~26.5s, and that is what made the 5s start period tight enough for one added process to break every deploy (`let-the-start-chain-finish`). Nobody has established where the factor of fourteen goes — plausibly uvicorn importing LangGraph and the OpenAI client on a small shared VPS, but that is a guess, not a measurement.

**The chain's own duration on the host has never been measured**, only bounded. `Started` → `Healthy` is the moment of the first *successful* probe, so it snaps up to the probe cadence and over-states the chain; on a failing deploy it is only a lower bound. Anything sized against it should be sized as a clearance, not a ratio.

**Post-merge reading (task 4.4 of `let-the-start-chain-finish`)**: _not yet taken — record the first passing deploy's `Started` → `Healthy` figure here._ At or below 40s the shipped 60s window remains compliant; above 40s the window must grow and a follow-up change is owed. Expect ~36.5s on a pre-25.0 Docker engine, or nearer ~30s on 25.0+, where a 5s start-interval applies by default.

**Recorded in**: `let-the-start-chain-finish`'s `proposal.md` (Out of scope) and `design.md` (Context, Migration Plan).

### `seed_playbook` and `check_step_handlers` emit no `INFO` records

Both run as `python -m commerce_ops.<module>`, so `__name__` is `"__main__"` and their module logger is `__main__` — which inherits **root** at `WARNING`, not `commerce_ops` at `INFO`. Every `INFO` record from them is dropped in production.

Verified directly: `logging.getLogger("__main__").getEffectiveLevel()` is 30 and `isEnabledFor(INFO)` is `False` after `configure_logging()`, and both processes emit nothing at all on a successful run. `seed_admin` is unaffected because it logs through `commerce_ops.access.application.roster`, a real package logger. `preflight` is unaffected because it uses `print`.

The consequence is not cosmetic: `seed_playbook`'s "added N step(s)" line is how anyone would know the seeding ran, so **the 352-row seed reached production silently**. `ERROR` records still surface, so a *failing* step does still name itself — but a step that hangs emits neither, which is why a mid-chain hang in either process is diagnosable only by `docker exec`.

The fix is small — give each module a package logger rather than `__name__` under `-m`, or set the level on root — but it is a behaviour change to logging and belongs in its own change rather than folded into a `HEALTHCHECK` edit.

**Recorded in**: `let-the-start-chain-finish`'s `proposal.md` (Out of scope) and `design.md` (Risks).

### Small cleanups, not worth a change each

Verified present at the time of writing; suitable for one chore commit.

| Item | Why |
|---|---|
| No `.dockerignore` | The whole build context — `.venv/`, `.git/`, caches — ships to the daemon on every build. The image itself is clean, since the `Dockerfile` copies selectively. |
| `anyio` undeclared | The test suite depends on its pytest plugin (`pytestmark = pytest.mark.anyio`) but gets it transitively. `pyproject.toml`'s own `aiohttp` comment records this project's convention of declaring such packages directly. |
| `httpx2` in dev dependencies | It is a runtime requirement of `openai`, not a test dependency. Likely added by mistake. |
| `description = "Add your description here"` | Placeholder from the project template. Deliberately excluded from `tighten-type-checking` as unrelated scope. |
| No `known-first-party` for ruff's isort | Without `known-first-party = ["commerce_ops"]` under `[tool.ruff.lint.isort]`, ruff infers first-party packages per invocation, so the classification changes with the set of files it is handed. `uv run ruff check` over the whole project passes while the `pre-commit` hook — which passes explicit staged paths — fails `I001` on those same files, and fixing one file at a time reports success while fixing them together still finds errors. Cost a commit two attempts to diagnose; the one-line declaration makes it deterministic. |
