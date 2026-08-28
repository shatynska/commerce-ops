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

`CLICKUP_API_TOKEN`, `CLICKUP_LAUNCH_FOLDER_ID` and `CLICKUP_WEBHOOK_SECRET` are all declared optional. The project owner has asked for them to be **required** (2026-08-24). Note what that would and would not do: required is not startup-critical, so preflight would report an absent variable *by name* and the application would still start and serve. It buys visibility at startup, not a refusal to boot, and it changes no runtime behaviour — every consumer reads `os.environ` directly. All three are delivered to the host (`7e25508`, 2026-08-24), so what is left here is the declaration, not whether the deployment has them.

**The two halves are not the same problem.**

`CLICKUP_LAUNCH_FOLDER_ID` and `CLICKUP_WEBHOOK_SECRET` are optional by *design choice*, recorded only in a settings comment. No specification requires it. `launch-clickup-sync` already demands the stronger runtime behaviour — "when the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped" — so marking them required adds a startup report on top of a guarantee that already exists. Compatible; a small change.

`CLICKUP_API_TOKEN` is different: `clickup-task-client` explicitly requires that the system "SHALL NOT require that credential to be present except when a request is actually made", with a scenario stating that nothing fails when the application starts without it. Marking it required contradicts that requirement as written, so it needs a `MODIFIED` delta against that capability, not a settings edit.

**There is a real argument for amending it.** That requirement was written when `clickup_client` had no caller at all. Since the completion loop shipped, ClickUp is load-bearing — the only thing projecting a launch's work, converging every 30 minutes — and a launch started from Slack now depends on it. "Absent until first use" is a reasonable rule for an unused client and a weak one for a credential the system needs continuously. Whoever picks this up should argue that change on its merits rather than quietly flipping the declaration.

**Recorded in**: `clickup-task-client`'s "Authentication is configured independently of any one caller"; `launch-clickup-sync`'s projection requirement; the optionality comments in `shared/application/settings.py`.

### The parked `add-product-creation-clickup-task` change — superseded

**Closed out by `start-launch-from-slack`**, which covers this ground on current foundations: a slash command and modal on the `product_agent` app that registers the product and starts its launch. The ClickUp half of the parked proposal is obsolete rather than deferred — the completion loop (`launch-clickup-sync`) now projects a launch's whole list and per-step tasks automatically, so a single hand-created task would be duplicated or fought by the next convergence pass. It remains true that `clickup_client` gains no new caller from this direction.

The local branch holding that proposal (`0b9b85c`) was deleted on 2026-08-24, once this change shipped. This entry survives it only so the supersession stays findable; the reasoning is in the archived change.

**Recorded in**: `start-launch-from-slack`'s `proposal.md` (Why).

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

**`src/` still has a caller.** `worker.py:60` calls `register_all()` and
`worker.py:184` calls `app.run_worker_async()` with `install_signal_handlers`
defaulting to `True`, so the deployed worker runs this same cancel-and-gather
path over a periodic deferrer on **every** SIGTERM, with all three real jobs
registered. What bounds it there is not absence but Docker's stop grace
period: a wedged shutdown is ended by SIGKILL rather than hanging forever.
Benign in effect — but if a worker is ever seen being killed on stop rather
than exiting cleanly, this is the mechanism to look at first.

- `procrastinate`'s `cancel_and_capture_errors` (`utils.py:215`) gathers side
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

Every other admin surface answers an expired session with an in-page notice — "That write did not complete: this admin session has ended…" — reported by the `htmx:responseError` / `htmx:sendError` / `htmx:timeout` listener in `_admin_header.html`. The create surface (`new.html`) shows FastAPI's raw `{"detail":"Not Found"}` instead.

**One cause, and it is not where the script lives.** `new.html` *does* include `_admin_header.html` (`new.html:21`), so it carries the listener — `restore-admin-step-writes` moved it out of `page.html`'s own inline script for exactly this class of reason, and it no longer claims "nothing was saved", which a listener watching a response status cannot establish. What defeats it here is that `add-step-page` deliberately un-boosts the transitions to and from the create surface so the success redirect's fragment is honoured (`hx-boost="false"` on the form, `new.html:53`, and on Cancel, `:29`). An un-boosted `POST` is a real browser form submission: htmx never sees the response, so no `htmx:*` event fires at all and the browser navigates to the 404.

**No requirement is broken.** `admin-session`'s *Admin access fails closed and absence-shaped* asks only that the refusal be shaped like a missing route, and a raw 404 body satisfies that. What is lost is the explanation, on the one surface where an admin may have typed a screenful of fields before the session expired.

The fix is therefore not a matter of moving or re-including the script. Whoever takes it up decides either that this surface's refusal is server-rendered, or that the create transition can be boosted without losing the redirect fragment.

**Recorded in**: `add-step-page`'s `design.md` (Risks / Trade-offs); the listener it needs is in `_admin_header.html`.

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

**Post-merge reading (task 4.4 of `let-the-start-chain-finish`)**: taken from run [`33044226427`](https://github.com/shatynska/commerce-ops/actions/runs/33044226427) on 2026-08-27, the first passing deploy since `32958746253`. `Started` 05:59:43.659 → `Healthy` 06:00:16.164 = **32.50s**. The spec requires the window to exceed that by at least two probe intervals — 32.50 + 20 = 52.50s — and the window is 60s, so it is compliant with 7.5s to spare. **No follow-up is owed.**

Two things that reading settles. The 6s step from the four-process chain's 26.50s to 32.50s is the cost of `seed_playbook` joining the chain, measured rather than inferred — it is what exhausted the old 5s window. And 32.50s sits nearer the ~30s prediction for a Docker 25.0+ engine (5s start-interval by default) than the ~36.5s one for an older engine, which is weak evidence the host runs 25.0 or later. Weak, not conclusive: compose's status polling sits between the probe and the reported timestamp, so the figure is not a clean probe tick. If the engine version ever matters, read it from the host rather than inferring it from this.

The next step added to the start chain must re-take this reading. At 32.50s there is room for roughly one more step of this size before the 40s ceiling; a second would breach it.

**Recorded in**: `let-the-start-chain-finish`'s `proposal.md` (Out of scope) and `design.md` (Context, Migration Plan).

### `seed_playbook` and `check_step_handlers` emit no `INFO` records

Both run as `python -m commerce_ops.<module>`, so `__name__` is `"__main__"` and their module logger is `__main__` — which inherits **root** at `WARNING`, not `commerce_ops` at `INFO`. Every `INFO` record from them is dropped in production.

Verified directly: `logging.getLogger("__main__").getEffectiveLevel()` is 30 and `isEnabledFor(INFO)` is `False` after `configure_logging()`, and both processes emit nothing at all on a successful run. `seed_admin` is unaffected because it logs through `commerce_ops.access.application.roster`, a real package logger. `preflight` is unaffected because it uses `print`.

The consequence is not cosmetic: `seed_playbook`'s "added N step(s)" line is how anyone would know the seeding ran, so **the 352-row seed reached production silently**. `ERROR` records still surface, so a *failing* step does still name itself — but a step that hangs emits neither, which is why a mid-chain hang in either process is diagnosable only by `docker exec`.

The fix is small — give each module a package logger rather than `__name__` under `-m`, or set the level on root — but it is a behaviour change to logging and belongs in its own change rather than folded into a `HEALTHCHECK` edit.

**Recorded in**: `let-the-start-chain-finish`'s `proposal.md` (Out of scope) and `design.md` (Risks).

### The admin stays server-rendered, in this repository

The admin surface — the steps page and the roster today, a launch-products page and a product list planned — could move onto a JSON API, onto React, and/or into its own repository. All three were weighed on 2026-08-27 and deferred. They are recorded together because they are not independent moves.

**A separate repository forces the API**; React does not. In-process calls into `launch.application` and `access.application` become network calls the moment the admin leaves this deployable, so the possible order is API → React → repository, each optional given the one before it. Nothing recorded here forecloses any of them.

**React is a foundation change, not a UI choice.** The Node-free stance is deliberate and already recorded twice: `AGENTS.md` picks gitlint over commitlint "specifically to avoid a Node.js dependency in this otherwise pure-Python project", and `README.md`'s Technology section names Python/FastAPI/LangGraph as owner-supplied rather than proposed. Adopting React means editing that section, not adding a page. Against that cost, the only admin surface React genuinely earns is a monitoring dashboard with charts — and monitoring's live numbers are slice 8 of `docs/domain-map.md`, blocked on marketplace access. Steps, roster, launch products and a product list are tables and forms, which htmx already renders.

**The repository split's costs are flat — they do not shrink by waiting.** Auth crosses the wire: `verify_admin_session` resolves a session's principal against the roster in-process, and the roster is the source of truth for admin capability. `.importlinter`'s 18 contracts stop applying, so a module boundary this project enforces mechanically at commit time becomes whatever the API happens to expose. Every change touching a domain rule *and* its admin rendering becomes two coordinated PRs, against `AGENTS.md`'s rule that a change reaches the server through one — `record-gate-and-discipline-as-fields`, 58 tasks across domain, specs and admin, is exactly the shape that would split. Two deploy pipelines double `AGENTS.md`'s four-step rule for adding a runtime variable, while the drift check in `tests/unit/shared/application/test_settings.py` still covers one of them. `admin-session`, `playbook-admin` and `roster-admin` would move to a second OpenSpec store. `shared/domain`'s vocabulary — `Discipline`, `LifecycleStage`, `Severity`, `ProductId`, `Sku` — is then duplicated, published as a package, or reduced to bare strings. And CORS becomes necessary, which `main.py` does not configure at all today.

**If React is what is actually wanted, it does not require the split.** An `admin-ui/` directory in this repository, built in a second `Dockerfile` stage and served as static files by FastAPI, with TypeScript types generated from FastAPI's own OpenAPI schema, buys React and TS without any cost in the paragraph above, and keeps one PR shipping a domain change together with its UI. Node enters the build, not the runtime image. It adds no process to the `CMD` chain, so the `--start-period` clearance measured above is unaffected.

**The one thing worth doing, and it is not itself a deferral.** No read-model layer exists between the use cases and the templates: `playbook_admin.py` is 1403 lines mixing form parsing, fault attribution, ordering and rendering, and its nearest thing to a view model is `_row(record, people) -> dict[str, Any]` (`playbook_admin.py:719`) — private, untyped, and inseparable from the adapter around it. `_require_admin` stands in three copies (`playbook_admin.py`, `roster_admin.py`, `admin_assets.py`). Naming that layer as typed frozen dataclasses when the next admin surface is built is better structure on its own terms, and it is separately what would make a later API roughly a day of serialization rather than a rewrite — a `@dataclass(frozen=True)` is a FastAPI response model in all but the decorator. Resource-shaped URLs cost nothing extra and spare the same rework.

**Triggers to reopen.** React: when slice 7 or 8 makes a charted monitoring dashboard real. The repository split: a second consumer of the API (a mobile client, another service), separate teams owning the two ends, or genuinely divergent deploy cadences. None holds today, for one deployable and one ops team.

**Recorded in**: this entry. Unlike its neighbours it has no change behind it — it was settled in exploration on 2026-08-27, and this file is the primary record until a change takes it up.

### Three `product-dossier` behaviours no deployment has yet exercised

`add-product-dossier-page`'s section 9 confirmed what the deployment could
show on 2026-08-28 and named what it could not. Three cases have no data to
render, and none is a defect:

| Case | Why it could not be observed | Where it is asserted |
|---|---|---|
| A retired product set apart on the index | Two products exist, neither retired | `test_product_index_page.py` — *Setting apart outranks the SKU sort* |
| A graduated launch's dossier | No launch has reached `graduated` | `test_product_dossier_page.py` — *A graduated launch does not remove the dossier* |
| An `accepted`, `rejected` or `voided` entry | One retained result existed, and it was `pending` | `test_product_dossier_page.py` — one scenario per state |

The last is the one worth re-checking when data allows, because it is where
a wrong label misattributes a decision: a `voided` entry must read as
*withdrawn* and carry no decider, never as *rejected*. Reaching the three
settled states costs at least the 24-hour rejection cool-off
(`automation_pass.py`'s `COOL_OFF`), and `voided` additionally needs a step
moved out of `active` between a result being produced and its decision.

**Trigger to close.** A retired product, a graduated launch, or a settled
automated result appearing in production — whichever arrives first, check
the corresponding case then rather than manufacturing it.

### Small cleanups, not worth a change each

Verified present at the time of writing; suitable for one chore commit.

| Item | Why |
|---|---|
| No `.dockerignore` | The whole build context — `.venv/`, `.git/`, caches — ships to the daemon on every build. The image itself is clean, since the `Dockerfile` copies selectively. |
| `anyio` undeclared | The test suite depends on its pytest plugin (`pytestmark = pytest.mark.anyio`) but gets it transitively. `pyproject.toml`'s own `aiohttp` comment records this project's convention of declaring such packages directly. |
| `httpx2` in dev dependencies | It is a runtime requirement of `openai`, not a test dependency. Likely added by mistake. |
| `description = "Add your description here"` | Placeholder from the project template. Deliberately excluded from `tighten-type-checking` as unrelated scope. |
| No `known-first-party` for ruff's isort | Without `known-first-party = ["commerce_ops"]` under `[tool.ruff.lint.isort]`, ruff infers first-party packages per invocation, so the classification changes with the set of files it is handed. `uv run ruff check` over the whole project passes while the `pre-commit` hook — which passes explicit staged paths — fails `I001` on those same files, and fixing one file at a time reports success while fixing them together still finds errors. Cost a commit two attempts to diagnose; the one-line declaration makes it deterministic. |
