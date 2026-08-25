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

### Small cleanups, not worth a change each

Verified present at the time of writing; suitable for one chore commit.

| Item | Why |
|---|---|
| No `.dockerignore` | The whole build context — `.venv/`, `.git/`, caches — ships to the daemon on every build. The image itself is clean, since the `Dockerfile` copies selectively. |
| `anyio` undeclared | The test suite depends on its pytest plugin (`pytestmark = pytest.mark.anyio`) but gets it transitively. `pyproject.toml`'s own `aiohttp` comment records this project's convention of declaring such packages directly. |
| `httpx2` in dev dependencies | It is a runtime requirement of `openai`, not a test dependency. Likely added by mistake. |
| `description = "Add your description here"` | Placeholder from the project template. Deliberately excluded from `tighten-type-checking` as unrelated scope. |
| No `known-first-party` for ruff's isort | Without `known-first-party = ["commerce_ops"]` under `[tool.ruff.lint.isort]`, ruff infers first-party packages per invocation, so the classification changes with the set of files it is handed. `uv run ruff check` over the whole project passes while the `pre-commit` hook — which passes explicit staged paths — fails `I001` on those same files, and fixing one file at a time reports success while fixing them together still finds errors. Cost a commit two attempts to diagnose; the one-line declaration makes it deterministic. |
