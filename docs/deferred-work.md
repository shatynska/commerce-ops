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

**A second dependent, added by `add-launch-journal` (2026-08-28):** `LaunchJournal.rollback`. The launch use cases roll the shared session back when a journal append fails, so that the command's remaining work — most sharply the catalog steady-state stamp a graduating advance performs — runs on a usable session. That rollback discards nothing of the command's own persistence *only because* `LaunchRepository.save` has already committed by the time the append is reached. Make those repositories commit-neutral and the same rollback throws the command's own write away, violating the requirement it exists to uphold (`launch-journal`, "A failed append never fails the command it records, nor disturbs its work"). The R6 tests in `tests/unit/launch/application/test_launch_journal_containment.py` go red if it happens; fix the append site in `use_cases._journal` in the same change.

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

Verified directly: `logging.getLogger("__main__").getEffectiveLevel()` is 30 and `isEnabledFor(INFO)` is `False` after `configure_logging()`, and both processes emit nothing at all on a successful run. `seed_admin` is unaffected because it logs through `commerce_ops.access.application.members`, a real package logger. `preflight` is unaffected because it uses `print`.

The consequence is not cosmetic: `seed_playbook`'s "added N step(s)" line is how anyone would know the seeding ran, so **the 352-row seed reached production silently**. `ERROR` records still surface, so a *failing* step does still name itself — but a step that hangs emits neither, which is why a mid-chain hang in either process is diagnosable only by `docker exec`.

The fix is small — give each module a package logger rather than `__name__` under `-m`, or set the level on root — but it is a behaviour change to logging and belongs in its own change rather than folded into a `HEALTHCHECK` edit.

**Recorded in**: `let-the-start-chain-finish`'s `proposal.md` (Out of scope) and `design.md` (Risks).

### The admin stays server-rendered, in this repository

The admin surface — the steps page and the membership today, a launch-products page and a product list planned — could move onto a JSON API, onto React, and/or into its own repository. All three were weighed on 2026-08-27 and deferred. They are recorded together because they are not independent moves.

**A separate repository forces the API**; React does not. In-process calls into `launch.application` and `access.application` become network calls the moment the admin leaves this deployable, so the possible order is API → React → repository, each optional given the one before it. Nothing recorded here forecloses any of them.

**React is a foundation change, not a UI choice.** The Node-free stance is deliberate and already recorded twice: `AGENTS.md` picks gitlint over commitlint "specifically to avoid a Node.js dependency in this otherwise pure-Python project", and `README.md`'s Technology section names Python/FastAPI/LangGraph as owner-supplied rather than proposed. Adopting React means editing that section, not adding a page. Against that cost, the only admin surface React genuinely earns is a monitoring dashboard with charts — and monitoring's live numbers are slice 8 of `docs/domain-map.md`, blocked on marketplace access. Steps, members, launch products and a product list are tables and forms, which htmx already renders.

**The repository split's costs are flat — they do not shrink by waiting.** Auth crosses the wire: `verify_admin_session` resolves a session's principal against the membership in-process, and the membership is the source of truth for admin capability. `.importlinter`'s 18 contracts stop applying, so a module boundary this project enforces mechanically at commit time becomes whatever the API happens to expose. Every change touching a domain rule *and* its admin rendering becomes two coordinated PRs, against `AGENTS.md`'s rule that a change reaches the server through one — `record-gate-and-discipline-as-fields`, 58 tasks across domain, specs and admin, is exactly the shape that would split. Two deploy pipelines double `AGENTS.md`'s four-step rule for adding a runtime variable, while the drift check in `tests/unit/shared/application/test_settings.py` still covers one of them. `admin-session`, `playbook-admin` and `members-admin` would move to a second OpenSpec store. `shared/domain`'s vocabulary — `Discipline`, `LifecycleStage`, `Severity`, `ProductId`, `Sku` — is then duplicated, published as a package, or reduced to bare strings. And CORS becomes necessary, which `main.py` does not configure at all today.

**If React is what is actually wanted, it does not require the split.** An `admin-ui/` directory in this repository, built in a second `Dockerfile` stage and served as static files by FastAPI, with TypeScript types generated from FastAPI's own OpenAPI schema, buys React and TS without any cost in the paragraph above, and keeps one PR shipping a domain change together with its UI. Node enters the build, not the runtime image. It adds no process to the `CMD` chain, so the `--start-period` clearance measured above is unaffected.

**The one thing worth doing, and it is not itself a deferral.** *Corrected 2026-08-28: the surfaces built since have done it, and the entry as first written no longer holds.* `launch_admin.py` and `product_dossier.py` both name a read-model layer as typed frozen dataclasses — `LaunchRow`, `StepLine`, `GateGroup`, `JournalLine`, `LaunchDetail`; `ProductRow`, `Identity`, `RecordEntry`, `Dossier` — with shaping separable from rendering and checkable by `mypy`. That was this entry's advice, taken.

What remains true is the *older* surface. `playbook_admin.py` is still 1403 lines mixing form parsing, fault attribution, ordering and rendering, and its nearest thing to a view model is still `_row(record, members) -> dict[str, Any]` (`playbook_admin.py:719`) — private, untyped, and inseparable from the adapter around it. Retrofitting it is a change in its own right and nobody has proposed one.

`_require_admin` has gone the other way: three copies when this was written, **five** now (`playbook_admin.py`, `members_admin.py`, `admin_assets.py`, `launch_admin.py`, `product_dossier.py`). Each new admin surface adds one, and the shape is identical in all five — a session cookie verified against an injected verifier, refusing with the app's own 404. That is the duplication worth naming now, and it is smaller than the read-model retrofit was.

The API argument is unchanged and is now better supported: a `@dataclass(frozen=True)` is a FastAPI response model in all but the decorator, and two of the four admin surfaces already have theirs. Resource-shaped URLs cost nothing extra and spare the same rework.

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

### The sub-category advisor's supported path has never run

`separate-the-verdict-from-the-prose`'s task 6.1 asked for a pass proposing
`Satisfied` with a recommendation naming node, demands and alternative. It
was not observable on 2026-08-28 and is recorded here rather than ticked.

The deployment holds no product the advisor can classify. Both launches
serving `lp.listing.007` are for products named `TestProductName13` and
`TestProductName14` — names that describe no product, so a refusal is the
correct answer and the supported branch has nothing to exercise it. Every
live run so far has taken the refusal path.

What this leaves untested **against a real model**: that the verdict line
parses as `supported`, that the veto does not fire on a well-formed
recommendation, and that `Satisfied` is proposed with a pending result
delivered to Slack. All three are asserted in
`tests/agents/step_handlers/listing/`, against stubs.

**A fourth, added by `await-the-subcategory-advisors-graph` (2026-09-02):
the async transport.** The advisor now reaches the model through
`ainvoke` rather than `invoke`, and no live run has yet exercised that
path either — the deployment holds no classifiable product, so the first
real invocation exercises the supported branch *and* the awaited
round-trip together, neither previously observed in production. The
stubs answer `ainvoke` faithfully, but a stub is not an HTTP client:
what is unobserved is the real `httpx` async path under `ChatOpenAI`,
including how a timeout or a retry surfaces through it.

**Trigger to close.** The first product registered with a name a model can
classify — a real listing rather than a placeholder. Read the pass's result
then: a pending result carrying a node path, its demands and a rejected
alternative closes it. Check the worker's own progress across that run
too, not only the result: the point of the async conversion is that the
pass's other work continued while the model was answering, and a run that
produced a good recommendation while stalling everything else would look
identical in the result alone.

### No test can catch a blocking call added inside the advisor's async node

`await-the-subcategory-advisors-graph` left the advisor with three guards
against the loop-pinning defect it repaired, and established by mutation —
each revert applied to the shipped code, the suite re-run — that a fourth
shape defeats all three.

| Reverted to | Caught by | Result |
| --- | --- | --- |
| `propose()` → `running.invoke(...)` | the graph's own `TypeError` | caught |
| `recommend` body → `structured.invoke(...)` | the stubs' raising `invoke` | 106 failed |
| `recommend` made synchronous | the refusal test, and the stubs' raising `invoke` | 3 failed |
| a blocking call added *inside* an otherwise-correct async `recommend` | **nothing** | **117 passed** |

The fourth passes because every guard's premise still holds: LangGraph has
already yielded by the time the node body runs, so "other work progressed"
is satisfied; the node is still a coroutine, so nothing raises; the
dependency is still awaited on the invoking thread, so thread identity is
satisfied. The mutated suite ran in 4.0s against 0.9s and nothing asserted
on that, because a wall-clock assertion is what `AGENTS.md`'s determinism
rule forbids this tier to carry.

This is a limit of what a deterministic test can establish about a
coroutine, not a gap a cleverer assertion closes — which is why
`launch-step-automation`'s *A handler's waiting does not stop the process*
places "which entry point a handler reached" at review rather than at
runtime. Recorded so the next author reads the boundary rather than
inferring from three green guards that there is none.

**Trigger to close.** A mechanism that makes loop-blocking observable
without wall-clock timing — `asyncio`'s debug mode and its slow-callback
logging are the obvious candidate, and it would apply to every handler
rather than to this one. Not attempted here: it is a test-harness
capability, not a change to the advisor.

### The integration tier's local setup is per-clone, and fails open

Three related gaps, all with one cause: the tier's database resolver does
something other than what the person running it assumes, and says nothing.

`tests/integration/conftest.py` resolves `DATABASE_URL`, then `.env.test`, then
`.env`. If none resolves it **skips**, and `pre-push` reports
`pytest (integration)... Passed` for a tier that never ran. Surveyed on
2026-08-28:

Surveyed 2026-08-28 and **not re-surveyed since**; two of its rows name clones that
no longer exist, and two worktrees created since are absent. Treat it as evidence
that the shape recurs, not as a census.

| Clone | `.env.test` names | |
| --- | --- | --- |
| `commerce-ops` | `commerce_ops_test` | shares a database |
| `commerce-ops-launch-pages` | `commerce_ops_test` | shares the same one |
| `commerce-ops-launch-journal` | `commerce_ops_launch_journal_test` | its own |
| `commerce-ops-automated-step` | *none* | skips silently |
| `commerce-ops-product-dossier` | *none* | skips silently |

**The skip is configurable and deliberately left alone.**
`COMMERCE_OPS_REQUIRE_DATABASE=1` turns it into a failure; CI sets it and
`pre-push` does not, because the flag fires only when *no* URL resolves, so
setting it would change behaviour for one population alone — a contributor with
no local Postgres, "the one least able to act on the failure". That argument is
sound for a project with contributors. It does not describe this one: the
database runs continuously, and the two clones above are not a contributor
without Postgres but a worktree nobody wrote a file into. Reversing the decision
for this repository is a judgement, which is why it is deferred here rather than
edited into the hook.

**A shared test database is not safe for concurrent runs.** The tier writes
freely and `test_scheduled_runs_freshness_cache.py` issues an unscoped
`DELETE FROM known_work`. Two clones pointing at `commerce_ops_test` while two
sessions push at once produce failures that read as defects and are not.
`commerce-ops-launch-journal` already holds the shape worth standardising — one
database per worktree on the same container, which costs a `CREATE DATABASE` and
an `alembic upgrade head`, no second container and no second port.

**Rung 3 can reach the development database.** `commerce-ops/.env` names
`commerce_ops`, and is shadowed only by that clone's `.env.test`. Delete or
rename one file and the tier falls through to it and runs that unscoped delete
against it, green. Nothing in the resolver refuses a URL naming the database the
developer works in, though `.env.test` exists precisely to "keep the tier out
of" it.

**Corrected 2026-09-02, because the original wording overstated this and the
overstatement was repeated.** This entry used to call `commerce_ops` "the
database carrying 1880 launch positions" and the hazard "that unscoped delete
against **real data**". It is a *development* database. Production is the
deployed container on its own host with its own volume; nothing here is business
data, and no local run can reach it. Losing `commerce_ops` costs local state, not
records anyone needs.

The hazard survives the correction, for a different reason, and the reason is the
better one: the tier **writes freely** into whatever it finds, and
`test_playbook_seed.py` asserts a "before any authored edit" premise that any
admin-UI editing done in a development database breaks. So rung 3 produces a
wrecked development state and a run whose failures read as defects and are not —
which is this file's recurring pattern, not a data-loss event. Whoever closes
this should argue it on correctness, not on stakes that are not there.

**Recorded in**: `2026-08-25-verify-the-integration-tier`'s `design.md` — *A
required-tier flag turns a skip into a failure — in CI only*, which argues the
`pre-push` decision and the rung order. The survey above and the rung-3 hazard
are recorded here first.

**The first gap is closed for the gate, and only for the gate**
(`restore-the-skipped-integration-tests`, 2026-09-02). CI's ephemeral database is
named `commerce_ops_test`, and `COMMERCE_OPS_REQUIRE_DATABASE` now also arms
`tests/conftest.py`'s no-skip guard over `tests/integration`, so a skipped *test*
fails the job whatever its reason. That change was prompted by a worse instance of
the same defect than this entry records: the gate was running **132 of 137**
integration tests and reporting a pass, because the five that check gate readiness
and stand-down refuse a database not named `*_test` and CI's was named
`commerce_ops`. The flag could not see it — it fires only when no URL resolves, and
one resolved. `pre-push` still sets nothing, so a worktree with no `.env.test` still
skips the tier and still reports `Passed`.

**Accumulated debris is inert — measured, not assumed** (2026-09-02). A
`TEMPLATE` copy of the shared `commerce_ops_test`, carrying 1325 `retired` rows in
`ignition`, passed exactly as a freshly seeded database did — `137 passed, 1 skipped`
when measured, *before* that change deleted one test; the same comparison today reads
`137 passed, 0 skipped` on both. The point is the equality, not the figure.
The "harmless residue" premise in `test_playbook_authoring_live.py`'s docstring
holds at that volume, so none of the three gaps below owes a cleanup. A red
integration run met locally is a configuration fault until proven otherwise; check
the database is seeded as well as migrated before concluding anything else.

**Trigger to close.** Either of the two that remain: `pre-push` setting the flag,
now that a failure there would name a real fault rather than an absent Postgres; or
a per-worktree database convention with a script that creates, migrates **and
seeds** one. Plus the third, which was always independent: the resolver refusing a
URL that names the working database. The last is still the one worth doing whether
or not the others are.

### Per-worktree test databases accumulate, and nothing drops them

The convention `docs/deferred-work.md` proposes — one database per worktree on the
shared container — is already in use, unwritten and unautomated. Sessions that hit
the fail-open trap create one by hand and name it after their branch. Nobody deletes
it when the worktree goes.

Surveyed 2026-09-02, on the running container:

| database | its worktree |
| --- | --- |
| `commerce_ops` | the working database — not a test database at all |
| `commerce_ops_test` | the main clone |
| `commerce_ops_anchor_test` | `inject-the-thread-anchor-poster` — live |
| `commerce_ops_failopen_test` | `close-the-integration-tier-fail-open` — live |
| `commerce_ops_await_test` | **orphan** — worktree gone |
| `commerce_ops_gate_progression_test` | **orphan** — worktree gone |
| `commerce_ops_launch_journal_test` | **orphan** — clone gone |

Three of seven are orphans, and two live worktrees
(`playbooks-as-versioned-graphs`, `rebuild-the-member-directory`) carry no
`.env.test` at all, so the tier fails open in both right now.

Nothing here is broken today: an orphan costs disk and nothing else. It is recorded
because it is an obligation the provisioning script has to answer *before* it is
written, not after. A script that creates a database per worktree without deciding
who drops it converts an occasional hand-made mess into a systematic one — and
`EnterWorktree`/`ExitWorktree` know nothing about databases, so removal cannot simply
be hung off worktree teardown. Whoever writes that script owns this question.

### The working database is behind head, which is currently hiding the rung-3 hazard

`commerce_ops` — the development database `.env` names, holding **2019** launch
positions accumulated by development and testing, not by anyone's business — sits at
`1a2b3c4d5e6f`, four revisions behind the repository's head `c04d95ba6e31`
(2026-09-02). Every test database on the container is at head.

That matters for one reason. The entry above records that the resolver's third rung
reaches this database, and that the tier would then run its unscoped
`DELETE FROM known_work` against real data, green. Today it probably would not get
that far: the schema is old enough that the tier would fail early and loudly instead.

**That is luck, not a guard, and it expires the moment anyone runs
`alembic upgrade head` against their development database** — an ordinary thing to
do, which would silently remove the only thing currently standing between rung 3 and
those 2019 rows. Nobody should rely on it, and nobody should be reassured by never
having seen rung 3 do damage: the reason is a stale schema, not a safety property.

There is a second, unrelated reason to migrate it anyway, and it points the other
way. CI creates an empty Postgres and migrates that; the deploy host migrates a
populated one. So **no migration in this repository is exercised against populated
data anywhere except in production.** This database is the only populated one
available, which makes `alembic upgrade head` against it a free rehearsal of what a
deploy does — and makes dropping and recreating it a loss of the only fixture that
rehearsal has. Worth weighing before anyone tidies it away.

It also means a rung-3 failure met today reads as a migration error rather than as a
misconfigured tier, which is one more way this class of fault arrives wearing the
wrong label.

### The gate's green depends on one integration test seeding a roster for another

`tests/integration/launch/test_playbook_authoring_roster_live.py` skips when the
roster carries no active person, and says in its own docstring that it "adds nobody
to a shared roster to avoid the skip". Nothing in CI's preparation creates one:
`alembic upgrade head` inserts no person and `seed_playbook` writes no roster at all.

It passes only because `test_gate_progression_atomicity_live.py`'s `_seed_decider`
creates an active admin earlier in the same session, through the real `access` use
cases, and never removes it. Confirmed on a local test database: exactly **one**
active roster person, and it is that one.

The coupling predates `restore-the-skipped-integration-tests`. What that change did
was convert its failure mode from a silent skip into a **hard failure of the whole
validation job**, since a skipped integration test now fails the gate. So reordering
or renaming a launch test file, running the tier under `-k`, `--lf` or xdist, or
having the atomicity test error before it reaches `_press`, turns the gate red for a
reason unrelated to the code under review. Found by `/code-review` on PR #149
(2026-09-02).

Two fixes are available and the choice is not obvious, which is why this is recorded
rather than done: seed a roster person in CI's preparation chain — cheap, and it puts
a person in a database whose emptiness some other test may one day rely on — or have
the roster test create its own, which is more correct and makes that file a
roster-writing module with the cleanup obligations that implies. A tier-level fixture
is a third option and inherits the first's objection.

### A wall-clock assertion in the commit-time tier fails under CI load

`tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py`
asserts a Slack acknowledgement returns within `SLOW_PERSISTENCE_SECONDS / 2` — 0.75s
— while a collaborator is made to take 1.5s, proving the ack does not wait on
persistence. On a loaded two-core GitHub runner it measured **2.175s** and failed the
job (2026-09-02, PR #149); the same commit passed on re-run, passes locally, and had
passed eleven consecutive CI runs before.

So it is event-loop starvation meeting a wall-clock budget, not a defect in the code
under test — a real property asserted by a proxy that shared hardware can violate. It
will fire again at random, and the next reader will spend an afternoon on it, which is
the "failures that read as defects and are not" pattern this file exists to shorten.
Whoever takes it should decide whether the property can be asserted without a
stopwatch — observing that the response is produced before the collaborator completes,
rather than timing it — since widening the budget only makes the flake rarer.

### `launch-playbook` says the seeded set is entirely human, and it is not

`openspec/specs/launch-playbook/spec.md`'s *A registered runtime does not activate a
seeded step* states "the seeded set is entirely `human` drafts", while
`tests/integration/launch/test_registered_handlers_activate_nothing.py` asserts the
seeded set carries automated steps — and passes. Both are right about their own
moment: `lp.listing.014` and `lp.traffic.001` are `automated`, backfilled before
`seed-the-reference-step-set` made the seed human-only, and they survive.

Noticed during review of `restore-the-skipped-integration-tests` (2026-09-02) and
deliberately not fixed there, per the scope rule. It is not urgent: the failure mode
is a loud assertion failure in a test that names the discrepancy, not a silent
vacuum. What it needs is a decision about which sentence is wrong — the scenario's
clause, or the two surviving rows — and that belongs to `launch-playbook`.

### Graduation cannot be triggered, and the persisted launch cannot say it happened

`advance-gates-and-confirm-in-slack` wires the gate ratchet for the first seven
gates and deliberately stops short of `graduated`. Two separate things block it,
and the second is a defect rather than a scope decision.

**~~Nothing can reach the graduation gate.~~ Closed 2026-09-01 by
`replace-metric-conditions-with-steps`.** `graduated`, `stock-ready` and
`phase-one-complete` authored metric conditions satisfiable only by an
attestation nothing could record, so a launch advanced to `stock-ready` and
stopped. Gates author no conditions now: each of those obligations is a
blocking step, resolved by a recorded outcome through the path every other
obligation already uses.

Two things that change carries are worth keeping here rather than only in the
archive. The six steps are seeded `draft`, so **the launches parked at
`stock-ready` when it deployed advanced past it unchecked** and no activation
pulls them back — gate readiness reads only the current gate. And
`graduated`'s `review-rating` condition was removed **with no successor**: no
reference row restates it, so there was no step to seed and the change did not
invent one. A person still weighs rating stability, `graduated` being a
confirmation gate; what went is the machine-checkable obligation.

The rest of this entry stands.

**The persisted launch cannot distinguish a graduated launch from one standing
at the final gate.** `launch-instance`'s enumeration requirement states this as
deliberate, and `LaunchRepository.list_all`'s docstring records the consequence:
a launch waiting at `graduated` for its approval is exactly what a report wants
to show, and the stored shape cannot tell it from one whose gate already opened.
`Launch.__init__` sets `_graduated = False` on every rehydration, so the flag is
process-local and does not survive a read.

**No longer latent — confirmed in production, 2026-09-02.** A launch (product
`399a0a06-0a2d-4b79-b9c5-182ede671fbd`, launch date 2027-02-01) reached
`graduated` that morning on its `phase-one-complete` approval, and stands there
with no way to be asked. `/admin/launches` reports it as awaiting confirmation,
reading `list_all`; the ten-minute pass, reading `list_active`, has never seen
it — the walk logs 21 launches and this is not one of them. Its
`launch_gate_ask_suppression` rows record an ask for `commit`, `order` and
`phase-one-complete`, and none for `graduated`. So the first bullet below is
live; the second is still latent, no advancing pass reading `list_all`.

It breaks in both directions:

- A pass reading `list_active` never sees a launch standing at `graduated` —
  `list_active` filters on `current_gate != 'graduated'` — so the graduation ask
  can never be posted.
- A pass reading `list_all` re-advances an already-graduated launch on every
  run: `advance_gate`'s `self._graduated` guard is False after rehydration, the
  gate's conditions are all still satisfied, so it re-opens `graduated`,
  re-emits `LaunchGraduated`, and re-stamps the catalog. `product-catalog`
  rejects the same-stage transition, which `launch-instance` requires to be
  reported as "an error naming the manual catalog correction required" — a false
  instruction to correct a correctly-stamped product, delivered on every pass.

**So a future change owes two things together** — three until
`replace-metric-conditions-with-steps` removed attestation outright, taking the
surface for `record_metric_attestation` off the list — and they are one change
because neither is useful alone: a persisted graduation marker on the launch,
and the graduation ask itself — the five-posture approving choice, and carrying
a refused catalog stamp back to the decider. The posture choice cannot be
defaulted: `launch-instance` requires the approver to name it, because the
system never chooses one.

The domain half is already built and waiting. `Launch.approve_gate` requires a
posture on the graduation approval and rejects one on every other gate,
`LaunchGraduated` carries it, and `progress_launch` stamps the catalog through
`stamp_steady_state`. What is missing is only the way to obtain the posture from
a person — today's ask carries two buttons and no third choice — together with
the three refusals standing in for it: `gate_decisions.py`'s `_FINAL_GATE`
refusal, `gate_confirmation.py`'s `FinalGateNotAsked`, and `list_active`'s
filter.

Note also that `InventoryOverride` is one of the five postures and
`shared-vocabulary` marks it temporary — "a state a product must eventually
leave" — with nothing in the launch process to leave it. Whether the graduation
ask should offer it is an open question for that change, not a settled one.

**Recorded in**: `advance-gates-and-confirm-in-slack`'s `design.md` (Non-Goals
and Risks) and `proposal.md` (Impact). Found by `openspec-change-reviewer`
during that change's spec review, 2026-08-28.

### Nothing records that a gate was asked about, or that an ask failed

`launch-journal` defines seven entry kinds — `launch-started`,
`step-outcome-recorded`, `gate-approval-recorded`, `gate-opened`,
`launch-graduated`, `launch-date-moved`, `advance-refused` — and none of them is
an ask. The only trace an ask leaves is a `launch_gate_ask_suppression` row,
which is a cool-off record rather than a history: one row per (launch, gate),
overwritten on each ask, also written by `record_rejection` having delivered
nothing at all, and reachable from no admin surface.

A failed delivery leaves less than that. `_ask_if_owed` catches it, logs a
warning and returns, and `launch-gate-progression` requires exactly that — "a
delivery that fails ... SHALL NOT fail the run" — so `/health/scheduled-runs`
reports the pass healthy while every ask it owes is failing. The reasoning for
that is sound and is not what is deferred here. What is deferred is that nothing
a person can reach says an ask was owed, attempted, or lost.

The consequence: "the admin says a gate awaits confirmation and no message
arrived" is not answerable from any surface this project offers. On 2026-09-02
it was answered instead by reading worker container logs and querying
`launch_gate_ask_suppression` over SSH — and the answer was the final-gate
deferral above, a case where no ask was ever owed. A journal entry when an ask
is delivered and when one fails would have made that a glance.

Worth pairing with the graduation change rather than doing first. The entry
above is why the question got asked, and observability that still cannot say
"this gate will never be asked about" leaves the same confusion standing.

**Recorded in**: nothing yet — found while diagnosing a launch standing at
`graduated`, 2026-09-02. This file is its first record.

### `LaunchRepository.save` overwrites the whole aggregate, with no optimistic concurrency

`_update` sets `playbook_version`, `current_gate` and `launch_date` from the
in-memory aggregate unconditionally, then `DELETE`s and re-inserts every row of
all three child tables. There is no version column, no `WHERE` on prior state,
and no lock: whichever writer commits last wins the entire launch record.

Two writers already exist and neither takes a lock. `record_step_outcome` has
four call sites — the ClickUp webhook, the ClickUp sync job (`*/10`), the
automation pass (`*/15`) and the automation confirmation handler — each of which
loads a launch, mutates it and saves the whole of it back. Today the visible cost
is bounded: they mostly touch different steps, `current_gate` never moves, so a
clobber loses at worst a concurrently-recorded step outcome that the next
reconciliation pass re-records.

**`advance-gates-and-confirm-in-slack` sharpens it**, because that change is what
makes `current_gate` move. A recording path that loaded a launch before a gate
crossing and saves after it writes the stale gate back — a launch going
*backwards* through a sequence `launch-instance` requires to be monotonic, and a
later pass re-crossing the gate and re-emitting `GateOpened` into the journal.

That change accepts the window rather than closing it, and says why in its
`design.md` Decision 11: the window is milliseconds wide, the next pass re-crosses
within ten minutes so it self-heals, and no gate in its scope has an external
effect when re-crossed — `graduated`, the one that stamps the catalog, is
excluded from it. Extending its advisory lock to the four recording sites would
mean touching every one of them, which is precisely what that change's Decision 1
exists to avoid.

**The right fix belongs to the repository, not to a caller**: a version column
checked on write, or a narrowed update that writes only what the command changed
instead of the whole aggregate. It wants doing before the deferred graduation
work lands, because `graduated` *does* have an external effect when re-crossed —
it stamps the catalog product's lifecycle stage — so the self-healing argument
that makes the window acceptable today expires exactly when that change ships.

Related: *Repositories commit their own writes, so a caller cannot own a
transaction*, above, is the same object's other structural defect, and both would
sensibly be fixed together.

**Widened on 2026-08-31.** `clickup_sync_job`'s reconciliation cadence moved
from `*/10 * * * *` to twice daily, ahead of the reliability-observation
period `shift-clickup-completions-to-webhook`'s own `tasks.md` (3.4) had made
a precondition for that — an explicit decision, made under pressure from real
ClickUp `429`s and accepted because only test data is at stake while no real
production launch exists yet (a separate, parallel change addresses the `429`
handling itself). This pass is one of the four recording paths that clobber
the whole aggregate on save, so the self-healing window this entry accepts
widened with it, from ~10 minutes to up to ~12 hours. The urgency behind
fixing this properly is correspondingly higher for as long as that cadence
stands.

**Recorded in**: `advance-gates-and-confirm-in-slack`'s `design.md` (Decision 11).
Found by `openspec-change-reviewer` during that change's spec review and
confirmed against `launch_repository.py`, 2026-08-28.

### An integration test assumes every `lp.` human step is active

`tests/integration/launch/test_registered_handlers_activate_nothing.py`
asserts that every seeded `lp.`-prefixed human step is `active`. That held
while the only `lp.` rows were the 97 the seed migration wrote, of which 95
became `active`. It stopped holding when `seed-the-reference-step-set`
delivered `playbook_reference.yaml`, whose 352 identifiers are a superset of
the same `lp.` namespace and which `seed_playbook` inserts **as drafts** — so
255 `lp.` human steps are legitimately not active, and the assertion lists all
255 back.

**It is unrelated to `let-a-step-say-when-it-starts`**, and was verified so:
the test fails identically with that change's source reverted to its parent
commit. It is recorded here because it fails only on a database that has had
the preparation step run against it, which is why it can pass in one
environment and fail in another for reasons having nothing to do with the code
under test.

**The premise to correct, not the assertion.** What the test is really about
is that a handler existing does not activate a step — "activation is an
authoring act". The seeded-and-active set it wants is the *migrated* one, so
the fix is to scope it to the 97 identifiers the seed migration wrote (or to
the steps the vendored file does not carry as drafts), not to relax the
status check.

**Trigger to close.** The next change touching the seeded step set, or anyone
running `tests/integration` against a database where `seed_playbook` has run
and wondering whether the failure is theirs.

### `after_steps` is not projected onto ClickUp's own task dependencies

`let-a-step-say-when-it-starts` gave a step an `after_steps` set — the steps
it waits on — and stops at deciding when the system *asks* for the work.
ClickUp can carry the same fact natively, and does not.

**The API supports it.** `POST /api/v2/task/{task_id}/dependency` takes
exactly one of `depends_on` (the task waits on that one) or `dependency_of`
(it blocks that one); `DELETE` on the same path removes an edge. Our client is
already v2, so this is one function beside `add_task_tag`.

**It fits the convergence design unusually well.** `GET /api/v2/list/{id}/task`
returns a `dependencies` array on every task, and `clickup_client.list_tasks`
already takes that read once per pass with pagination — so `converge_launch`
could read the current edges, add what is missing and remove what is stale at
**no extra request at all**. `_task_state` simply does not parse the field yet.

**What it cannot be is the enforcement.** ClickUp's Dependency Warning
ClickApp warns when someone closes a task that is waiting on another and then
lets them close it; there is no setting that refuses. So the edges are
advisory, the release predicate remains the thing that decides, and the
projection must not be written as though ClickUp were holding the line.

**Nor can it carry `starts_at_gate`.** That field points at a gate, and a gate
is not a task, so there is nothing to depend on. Two workarounds were
considered and both rejected: fanning each step out to every blocking task of
every earlier gate is hundreds of edges re-derived on each playbook edit,
against a rate-limited API; and synthesising a task per gate invents a ClickUp
object with no counterpart in the domain, needing its own completion semantics
and its own reconciliation.

**Why it was left out** rather than folded in: it is independent of the
release predicate, touches no domain code, and would have pushed a change that
already spans seven capabilities past what one sitting can review. The
prerequisite is that the Dependency Warning ClickApp is enabled in the Space —
without it not even the warning appears.

**Trigger to close.** Someone asking why a task's dependencies are visible in
this system and not in ClickUp; or the first launch where an author uses
`after_steps` in earnest and wants the ordering where the work is done.

### `omni_agent`'s graph node is synchronous, and reaches the model blockingly

`omni_agent/application/graph.py`'s `call_model` node is a plain `def`
calling `model.invoke(state["messages"])` — the shape the sub-category
advisor was copied from, and the one
`await-the-subcategory-advisors-graph` removed there in 2026-09.

**It is not the same defect, and the difference is why this is an entry
rather than a change.** Its caller already awaits: `use_cases.py:34` runs
`await graph.ainvoke(...)`, and LangGraph hands a synchronous node to a
worker thread when reached that way (measured, `langgraph` 1.2.11 — the
node body observes a different `threading.get_ident()`). So the event
loop is not pinned, which the advisor's was. What remains is a blocking
client inside a graph whose library offers a native async path, costing a
thread per invocation for work that is only waiting, and depending on an
accommodation the framework makes rather than on the code asking for the
right thing.

`launch-step-automation`'s *A handler's waiting does not stop the process*
does not reach it: `omni_agent` is not a step handler, and that
requirement governs handlers. Its own capability, `omni-agent`, says
nothing about transport. So nothing in the repository currently obliges
this to change — which is the actual finding.

The fix is the same two lines the advisor took: `call_model` becomes
`async def`, `model.invoke` becomes `await model.ainvoke`. What makes it a
change rather than a chore is that it makes that graph async-only too, so
every caller and every test of it moves with it, and the question of
whether the obligation should be stated somewhere `omni_agent` reads
belongs with it.

**Trigger to close.** Whenever `omni_agent` is next worked on for its own
reasons, or when a second handler-like graph appears and the obligation
needs a home broader than `launch-step-automation`.

### The step set's provenance is split across two files, one of which is stale

`alembic/data/playbook_v1.yaml` (97 steps) and
`alembic/data/playbook_reference.yaml` (352 steps) sit side by side in the same
directory, and only the second describes the live set. The first is read by
exactly one thing — migration `d2f8b3c64e17` — and its identifiers are a strict
subset of the second's. Nothing says so at either file, and the name `v1` reads
as *the current version* rather than *the set as it stood in August 2026*.

**It has already cost a wrong analysis.** `let-a-step-say-when-it-starts` was
scoped, counted and argued against `playbook_v1.yaml` on the assumption that it
was the seed, and its proposal claimed the served set was 97 steps with 65 on
`listable`. The real numbers are 95 served of 352 stored, with 64 on `listable`
and 255 standing as `draft` — a backlog three times the size of what is served,
and the single strongest argument for that change. The corrected reading changed
what the change had to do, not merely what it said: the backfill had to widen
from the served set to the authored one.

**What is wanted.** `playbook_v1.yaml` should stop being referenced from the
migrations or from anywhere else, leaving one file that describes the step set.
The obstacle is only that `d2f8b3c64e17` reads it at runtime, so removing the
file means reworking or collapsing that migration.

**The obstacle is smaller than it looks, and this is the decision that unblocks
it:** the deployed database is a test database and may be dropped to nothing.
Migration history therefore does not have to be preserved across this — the
seed chain may be collapsed, rewritten, or replaced by a single revision that
establishes the current schema and lets `seed_playbook` deliver the content.
Recorded here because that licence is not visible from the repository and a
future reader would otherwise assume production data constrains it.

**Two things want doing at the same time, and one of them is a defect.**

*The status split is not what was intended.* `b8e5c04a1d39` mapped the v1
`execution` values onto the current fields, sending 95 `human-attested` rows to
`active` + `human` and the other two to `in-development` + `automated`. The two
`in-development` rows were not a deliberate choice and were not known about
until they were found while scoping `let-a-step-say-when-it-starts`. The
intention is that the whole set is `active` and `human`. Whether that is a data
correction or a rewritten seed depends on how the file consolidation above is
resolved, which is why the two belong together.

*A new field on a step reaches the stored rows twice, by two different routes,
and the vendored file is the route that gets forgotten.* A migration backfills
the rows that exist when it runs; `seed_playbook` inserts rows the vendored file
names and the database does not, on **every container start**, and it builds
each `StepDefinition` from the file's own keys. A field the file does not carry
is therefore delivered at its dataclass default for every row seeded after the
backfill — silently, and only for rows nobody had yet. Any change adding a field
to a step owes `playbook_reference.yaml` and `seed_playbook.py` the same
attention it owes the migration.

**Trigger to close.** Any of: `playbook_v1.yaml` being referenced by nothing;
the step set needing a status correction; or the next change that adds a field
to a step definition.

### A stray, unscoped ClickUp webhook subscription predates this project's own

ClickUp's team turned out to already have a second, unrelated webhook
subscription pointed at the same endpoint — unscoped (`folder_id: None`, so
every task event in the whole workspace, not just this deployment's launch
folder), already `suspended` by ClickUp after 106 accumulated delivery
failures, predating `register_clickup_webhook.py` entirely (which never
creates an unscoped subscription — its own idempotency check requires a
folder match). It briefly caused real confusion during rollout: an ad hoc
lookup script that filtered only by `endpoint` (not `endpoint` **and**
`folder_id`, the way the production idempotency check correctly does)
picked up that stale subscription's secret instead of the real one, and it
took a second, fuller lookup to find both. It was left in place rather than
deleted, since removing another team's ClickUp resource is a decision for
whoever owns that workspace, not something to do by the way.

**Recorded in**: `shift-clickup-completions-to-webhook`'s `tasks.md`, now at
`openspec/changes/archive/2026-08-30-shift-clickup-completions-to-webhook/`.

### A handler's finding recorder is keyed by a step identifier Postgres owns

`worker.py:136` wires the sub-category advisor's recording capability as
`automation_pass.recorders = {"lp.listing.007": _record_sub_category}`, and
`_record_finding` (`automation_pass.py:762-795`) looks the recorder up by
`step.identifier`.

The literal is correct against `launch-step-automation`, which wires a
recorder *"for `lp.listing.007` specifically — not for every step"*, and the
`recorders` docstring argues correctly that keying by handler name would be
wrong, since a handler's name says nothing about which step invoked it.

What is deferred is the consequence. Since `move-playbook-steps-to-postgres`
the step set is a live, admin-editable set of rows, and this literal is a
reference into it from source. A step re-authored to carry
`listing.subcategory_advisor` under a different identifier — or the advisor
being pointed at a second step — resolves no recorder, and
`_record_finding` returns `True` and lets the outcome settle **with no log
line at all**. The finding is dropped in silence, and the only symptom is a
product whose `sub_category` never fills in while its step records
`Satisfied` on schedule.

The narrow fix is one `INFO` record when a `Success` finding arrives for a
step no recorder is wired for — enough to make the gap visible without
inventing a policy. The broader question, deferred: whether "which steps
record a finding" belongs in source at all, or is a property of the step
row, like `handler` already is.

**Trigger to close.** A second step gaining a recording capability, or the
first time `lp.listing.007` is re-authored.

### Rejecting an automated result records no reason, and nothing can learn from it

`reject_automated_result` records a fixed string (`automated_decisions.py:205-213`):

```python
Blocked(reason=f"{who} rejected the automated result produced by {handler}")
```

with evidence `f"{handler}: {produced} — rejected by {who}"`. The person
rejecting it has nowhere to say **what was wrong, or what would have been
right**, so a rejection carries who and when and nothing about why.

The concrete case is `lp.listing.007`: the advisor proposes a sub-category,
its confirmer judges a different one better, and there is no field to say
which one or on what grounds. The step records `Blocked`, the pass re-runs
it under `cool-off-a-repeatedly-blocked-step`'s cool-off, and the advisor
reasons its way to the same answer, having been told nothing.

**The reading half already works.** A re-invoked handler can reach the prior
outcome with no new plumbing: `StepContext.launch` is the `Launch`
aggregate, `progress_for` (`launch_run.py:344`) returns
`StepProgress(outcome, provenance)`, and `Provenance` carries `evidence`.
The retry loop closes on its own. What is missing is only the *capture* — a
text input on the Slack rejection, threaded through
`reject_automated_result` into the recorded reason.

Note that the opposite direction already exists: `Success.comment`
(`shared/domain/result.py`) is documented as *"optional — additional
information, for a person or for tuning"*, which is the handler talking to a
person. This entry is the person talking back.

**One limit to design around.** `Launch._step_progress` is keyed by step
identifier and holds only the latest outcome, so a handler would see the
last rejection, not a history of them. One corrective round is free; several
rounds of "not this, and not that either" need the append-only launch
journal and a reader for it, which is its own decision.

**Trigger to close.** The first handler whose output is a judgement a person
is likely to disagree with more than once — or *write on acceptance, not on
production* landing, since both touch the same Slack decision path.

### The shared test database is a shared mutable resource, and one module rewrites it

`tests/integration/launch/test_playbook_readiness_live.py` demotes each
gate's blocking step to `draft`, asserts what that makes unready, and
restores the snapshot in a `finally` — with a module-scoped restore around
the whole file and a final test that re-reads the set so a lost restore is
loud. That is careful, and it is still only safe while **exactly one test run
touches the database at a time**.

It is not currently safe, because nothing enforces that. `AGENTS.md` names
one database, `commerce_ops_test`, and every worktree and session points at
it. Two overlapping runs interleave snapshot and restore — A snapshots
`active`, B demotes to `draft`, A restores `active`, B restores from a
snapshot taken after A's demotion — and the last writer wins with the wrong
value. An interrupted run loses the `finally` outright.

**Observed, 2026-09-02.** `commerce_ops_test` was left with `lp.strategy.030`
— the `graduated` gate's only blocking step — sitting at `draft`. The tier
then failed 62 tests, 54 of them raising
`PlaybookNotReadyError: gate 'graduated' has no active blocking step
attached` from files with nothing to do with the step set, and 7 more
failing downstream of it. The first run after the corruption was green; the
next was not, so the failure looked like whatever change was in hand. It was
repaired through `change_step_status`, the validated authoring use case,
rather than by an `UPDATE` — the same write the module's own restore makes.

Two facts worth keeping, because each rules something out:

- **Concurrency alone does not corrupt it.** Two integration tiers run
  simultaneously against a freshly seeded database produced 12 failures
  between them and left every gate held. The interleaving has to land in the
  wrong order, so this is rare and non-deterministic — which is exactly what
  makes it expensive when it happens.
- **`seed_playbook` cannot repair it.** That step adds only rows no stored
  step names and never touches an existing one, deliberately: a row that
  differs from its vendored counterpart is indistinguishable from an
  authored edit. So a demoted step stays demoted through any number of
  re-seeds.

The same database also carries **1,315 retired `ignition` steps** and several
hundred drafts accumulated by past runs. That debris is noise rather than
breakage — the tier passes with it present — but it is the same cause seen
over a longer period.

**The fix is an isolated database per worktree**, which two sessions reached
independently on 2026-09-02 and which `AGENTS.md` does not yet describe:
`createdb`, `alembic upgrade head`, `python -m commerce_ops.seed_playbook`,
and a `.env.test` naming it. It composes with the entry above — the seeding
sentence that file already owes is the same sentence.

**Trigger to close.** Whenever `AGENTS.md`'s integration-tier section is next
edited: both this and *A migrated database is not a seeded one* are closed by
the same paragraph.

### A migrated database is not a seeded one

`AGENTS.md` tells a developer to "create and migrate `commerce_ops_test` once
by hand". Migrating is not enough, and has not been since
`move-playbook-steps-to-postgres`: the migration-era seed
(`d2f8b3c64e17_seed_playbook_steps.py:52`) reads its own vendored file,
`alembic/data/playbook_v1.yaml`, and inserts **107** steps. The served set
comes from the *preparation step*, `seed_playbook.py`, which reads
`alembic/data/playbook_reference.yaml` — **358** steps since
`replace-metric-conditions-with-steps`, 352 before it.

So a database that has only been migrated carries a quarter of the step set,
and a test asserting the served count fails against it for a reason that looks
like a defect in whatever change is in hand. `replace-metric-conditions-with-steps`
widened the gap from 245 steps to 251; it did not create it.

The fix is a sentence in `AGENTS.md` and, where CI builds a database, a
`seed_playbook` run after `alembic upgrade head`. It is not this change's to
make: the gap predates it, and closing it is a change of its own.

**Trigger to close.** The next time a developer or a CI job is set up against
a fresh database — or the next test that asserts the served step count and
fails for this reason rather than its own.

**The trigger fired, 2026-09-02**, and the entry cost what it predicted.
`inject-the-thread-anchor-poster` built an isolated `commerce_ops_anchor_test`
rather than mutate the shared one; `alembic upgrade head` alone left 97 `lp.*`
steps, and four integration tests failed asserting 358 — the failures naming a
step count, not a seed. `uv run python -m commerce_ops.seed_playbook` against
the same `DATABASE_URL` brought it to 358 and the tier to green. That command
is the missing sentence, and it is still owed to `AGENTS.md`.

### Production code carries tolerances for incomplete test doubles

Several modules read one value through several attribute spellings, or
through `getattr` with a default, explicitly so that a test's stand-in need
not model the real collaborator:

- `gate_progression_job.py:256` — *"tolerating a caller's fake that models
  less than the real `LaunchProgressed` does"*
- `gate_progression_job.py:266` — `_awaiting_gate` probes
  `("awaiting_gate", "gate_id", "current_gate")` for one value
- `clickup_sync.py:128-136` — `_members` probes three shapes for one
  reader
- `automated_decisions.py:86-90` — *"three spellings"* for one member lookup
- `playbook_authoring.py:243-253` — `member_identifier` probes
  `("identifier", "id", "member_id")`

Part of this is legitimate: `.importlinter` forbids `launch` from naming
`catalog`'s and `access`'s types, so a shape is read where a type cannot be
named. The rest is the dependency running backwards — production code
widened so that a double written to the minimum keeps passing. It is also
where a good deal of `automation_pass.py`'s 35 `: Any` annotations come
from, which is `mypy strict` being satisfied nominally.

**Corrected twice, and the second correction changes the method.** The first
(2026-09-04, while implementing `share-the-unit-test-harness`) found the list
stale in both directions: five stood and five were listed, but not the same
five. The second (2026-09-04, while implementing `share-the-value-doubles`)
found *that* list incomplete too — and the reason it keeps going stale is that
every version of it was assembled by grepping a **spelling**.

Measured **structurally** instead — a `getattr` over a loop variable ranging
across a tuple of string literals, whatever the loop variable is named — `src/`
carries **ten** such probes, six of them the member-identifier probe:

| site | probe | first recorded |
|---|---|---|
| `clickup_sync.py:140` | `("identifier", "id", "member_id")` | 2026-09-04 (1st) |
| `playbook_authoring.py:272` | the same, verbatim | 2026-09-04 (1st) |
| `playbook_admin.py:321` | the same, verbatim | **2026-09-04 (2nd)** |
| `activation_readiness.py:204` | the same, verbatim | **2026-09-04 (2nd)** |
| `roles.py:729` | `("identifier", "member_id", "id")` | **2026-09-04 (2nd)** |
| `gate_decisions.py:105` | `("identifier", "id", "name")` | **2026-09-04 (2nd)** |
| `gate_progression_job.py:271` | `("awaiting_gate", "gate_id", "current_gate")` | 2026-09-04 (1st) |
| `automation_pass.py:209` | `("noted_kind", "outcome_kind", "outcome", "kind", "noted_outcome")` | **2026-09-04 (2nd)** |
| `automation_pass.py:217` | `("noted_at", "when")` | **2026-09-04 (2nd)** |
| `automation_pass.py:225` | `("reported_at", "reported", "has_been_reported")` | **2026-09-04 (2nd)** |

Two of the ten — `gate_decisions.py:105` and `roles.py:729`, both member-shape —
iterate a loop variable named `attribute` rather than `name`, which is exactly
why a sweep for the literal string `for name in (` found the other eight and
missed these. **Re-measure by shape, not by spelling; that is the durable part
of this entry.**

The earlier table's line numbers were **not** stale, and were wrongly reported
as such in a draft of `share-the-value-doubles`: it anchored each site on the
enclosing `def` where the table above anchors on the `for`.

**Five tolerances stand that the shape measurement cannot find**, because none
is a loop over spellings. All five are live:

| site | what it tolerates |
|---|---|
| `gate_progression_job.py:256` (`_crossed`) | `getattr` with a default — a fake modelling less than `LaunchProgressed` |
| `clickup_sync.py:128` (`_members`) | three *reader shapes*: `list_members()`, a callable, a plain iterable |
| `activation_readiness.py:179` (`_members_of`) | the same three reader shapes |
| `activation_readiness.py:150` (`_registered_names`) | two reader shapes: `names()` or a plain iterable |
| `playbook_authoring.py:389` (`_registered_names`) | the same two |

**The last three were found by `share-the-stateful-fakes` (2026-09-04), and how
they were missed is the durable part.** A *reader* shape is a function resolving
one value through more than one calling convention — a `getattr` for a named
method, a `callable()` test, or a bare fall-through over the collaborator
itself. It matches no spelling-shaped pattern, so every sweep of this ground
found `clickup_sync` alone. Measure for the *shape of the resolution*, not for
the names it tries. Note that `_crossed` is a fourth kind again — a `getattr`
with a default over a single spelling — and is grouped here only because it,
too, is invisible to a spelling sweep.

Two others were closed, each after failing in production, which is the argument
for the whole entry: `automated_decisions._member_for` (three spellings for one
member lookup) refused every decision by every identity, and
`playbook_authoring._read_members` (three reader shapes) produced
`'PostgresMembers' object is not iterable` mid-write.

**Where this stands after `share-the-value-doubles` (2026-09-04).** All 52
member doubles in `tests/` now expose `identifier` — 49 by aliasing a shared
type whose field is `id` with `identifier` derived from it, 3 through a
three-line adapter over that type. So the second and third branches of all six
member-identifier probes are dead: nothing in `tests/` reaches them any more.
That is what the deletion needed, and the deletion is still not this entry's to
perform.

**Where the reader shapes stand after `share-the-stateful-fakes` (2026-09-04),
which is a narrowing and not a closure.** All 20 handler-name doubles present
`names()` alone — `FakeHandlerRegistry.__iter__` was dropped, licensed by
mutating every local `__iter__` to raise and finding the commit tier still
green — so both `_registered_names` sites take their first branch from
`tests/`. The members side is narrower but **not** empty: 41 of the 43
`_FakeMembers` present `list_members()` alone, and what still supplies the other
two conventions is 23 module-level `_members()` reader functions, five
`_ReaderMembers`, `_StoreShapedMembers`, `_Members`, `_FailingMembers`, two
`_PlaybookMembers` and this change's own two keeps. **Do not narrow
`clickup_sync._members` or `activation_readiness._members_of` on the strength of
that change**; the population is measured, the branches are not dead.

Not fixable on its own. A tolerance may only be deleted once the doubles it
tolerates are complete. `share-the-value-doubles` completed the value doubles
and `share-the-stateful-fakes` completed 175 of the 191 stateful declarations in
its scope; both make deletion *safer*, and neither makes it complete. **`unify-launch-adapter-dependencies` performs it** — protocols naming a
shape without naming a type `.importlinter` forbids — and
`docs/proposed-change-order.md` now orders it after the doubles for that reason.
Recorded here because the finding predates all of them and outlives any one
landing alone.

### The member-identifier probes' fall-through branches are now untested

**Found by `/code-review` on `share-the-value-doubles`, 2026-09-04, and it is
that change succeeding rather than failing.** All 52 member doubles now expose
`identifier`, so every one of the six member-identifier probes matches on its
**first** branch. The `"id"` and `"member_id"` branches are unreachable from any
test.

Demonstrated by mutation: rewriting all six probes to `for name in
("identifier",)` leaves **2,482 of 2,482 passing** on that branch, where the
same mutation of only two of them against the pre-change tests produced **177
failures and 14 errors**.

That is exactly what the change set out to do — a branch no double needs is a
branch that can be deleted. The cost is that the interval before it *is* deleted
is unguarded. `playbook_authoring.member_identifier`'s own docstring says the
`id` branch exists because "a reader that answers rows of its own may spell it
`id`", and if that branch is reordered, narrowed or dropped early, admin writes
raise `ValueError: a member exposes no identifier` in production and no test
reports it.

Worth being clear about what was lost: the old protection was **accidental and
misleading**. A test double spelling `id` was never evidence that a production
reader spells `id`; it was evidence that the double modelled the minimum. So
this entry is not a regression to repair but an interval to close, and the way
to close it is to delete the branches rather than to re-grow doubles that
exercise them.

Closes with `unify-launch-adapter-dependencies`, which
`docs/proposed-change-order.md` now orders after both doubles slices. Until
then: **do not narrow any of the six probes on the strength of a green suite.**
The six are `clickup_sync.py:140`, `playbook_authoring.py:272`,
`playbook_admin.py:321`, `activation_readiness.py:204`, `roles.py:729` and
`gate_decisions.py:105`.

### `uv run pytest` fails at collection, and no gate notices

`AGENTS.md` documents the test command as `uv run pytest`. On `main` it does not
run: `testpaths` names all three tiers, and two basenames repeat across them —
`test_product_hazard_categories.py` in `tests/unit/catalog/domain/` and
`tests/integration/catalog/`, and `test_placeholder.py` in `tests/unit/` and
`tests/integration/`. Under pytest's `prepend` import mode, with no `__init__.py`
in those directories, both import as the same top-level module and collection is
interrupted with `import file mismatch`.

**Every gate invokes the tiers separately** — `pre-commit` and CI both run
`pytest tests/unit tests/agents` and then `pytest tests/integration` — so none
of them ever hits it. Only the documented command does, which is why it has
survived: the failure is invisible to exactly the population that would fix it.

Found 2026-09-04 while taking a whole-suite baseline for
`share-the-unit-test-harness`, which measured per tier instead and recorded why.

**Two fixes, and they differ in scope.** Rename one file of each pair, which is
two commits and no semantics; or add the missing `__init__.py` files, of which
only 9 of roughly 70 test directories have one. `share-the-unit-test-harness`'s
`design.md` Decision 1 considered the second and rejected it as unnecessary
scope — this finding is the evidence against that judgement, since those
absences have already cost the project its documented test command.

**Trigger to close.** Anyone running `uv run pytest` and believing the result;
or the next change that adds a test file whose basename already exists in
another tier.

### Migration `1a2b3c4d5e6f` carries a hand-invented revision id

`alembic/versions/1a2b3c4d5e6f_add_slack_thread_fields_to_launch_positions.py`
uses a sequential placeholder where every other revision in the tree carries
generated hex (`028812c68321`, `e6c1a92d7f04`, `d715ad9feed4`). It is
cosmetic and it collides with nothing.

**It must not be corrected.** The id is written into `alembic_version` in
every environment that has run it, production included; renaming it would
strand those databases at a revision that no longer exists. Recorded so the
inconsistency is not rediscovered as a defect and "fixed".

The generalisable part is the convention: a revision id comes from
`alembic revision`, never from typing one out.

### Three seams a unit test has to work around, measured

`restore-the-skipped-unit-tests` (2026-09-01) restored 44 tests that had been
skipped wholesale under the false reason "Unit test requires database". None
needed a database. What each of them actually needed was to get around a place
where production code reaches for a global instead of taking a collaborator,
and the corrections are still standing in `tests/` because removing the seams
was `inject-the-thread-anchor-poster`'s scope, not that change's. **One of the
three is now gone** — that change retired the Slack client; the other two
stand, and its design says why each was out of its scope.

Recorded with what each one cost, because this is the most concrete evidence
that change has:

| Seam | What it cost a test |
|---|---|
| `launch_thread_delivery.establish_thread_and_resolve_mention` opens its own `transaction()` (`:82`) | Substituting `slack_entry.transaction` does not reach a second module's own import of the same name. This is what made two files look database-bound. Two test files now substitute `transaction`, `LaunchRepository` and `hold_launch_thread_establishment_lock` on that module. |
| ~~`thread_establishment._get_slack_client()` is an `lru_cache`d `AsyncWebClient` reading `PRODUCT_AGENT_SLACK_BOT_TOKEN`~~ — **retired** by `inject-the-thread-anchor-poster` (2026-09-02) | It cost this: the anchor post bypassed the injected poster entirely, so a test could only observe it by patching `AsyncWebClient.api_call` at class level, and had then to add `thread_establishment` to its cache-reset list or the cached client outlived the test. The client is now the injected `post_anchor` port. `test_thread_establishment_race.py` substitutes a plain recording callable; no cache-reset list names `thread_establishment` anywhere in `tests/`, and no fixture sets `PRODUCT_AGENT_SLACK_BOT_TOKEN` for this reason alone. |
| `launches_channel()` reads `os.environ` directly (`slack_notifier.py:44`) | Raises `KeyError` inside `_report_stuck_step`'s own `try`, which swallows it into a warning — seven tests failing on an empty message list with nothing in the failure naming the cause. Three files now set the variable by fixture. |

The common shape is worth stating once: **each fault is absorbed by an
`except` before it reaches an assertion**, so every one of them presents as
"the message never arrived" rather than as itself. That is why five commits in
one afternoon read the whole set as a database problem and widened a skip list
instead of diagnosing it.

A related finding, not in the table because it is not a seam: an incomplete
double can produce a *passing* test through the same swallowing path.
`test_slack_entry_unready_playbook.py::test_a_start_against_a_ready_playbook_is_unaffected`
passed for weeks while `RuntimeError: DATABASE_URL is not set` was raised on
every run and answered by the direct-message fallback, so it observed none of
the threaded delivery it is about. It is fixed, but the class is general and
the commit-time tier's new zero-skip guard cannot catch it — a swallowed error
produces a pass, not a skip.

### Three shared spellings mean something else in two files

`share-the-ordered-html-harness` (2026-09-05) left
`test_playbook_admin_dependency_option_filtering` and
`test_playbook_admin_multi_value_controls` out of the HTML migration, because
each declares `_flat(node: _Node) -> str` where `tests/support/html.py` has
`flat(text: str) -> str` — the collision `share-the-unit-test-harness` task 3.1
caught and named.

**It did not catch three more in the same two files.** Both also declare
`_carries`, `_attribute_text` and `_ancestors`, and all three differ from the
shared functions those spellings name elsewhere:

| spelling | there | `tests/support/html.py` |
|---|---|---|
| `_carries` | matches a class, **an `id`, or any `data-*` value** | a class token only |
| `_attribute_text` | joins the element's **own** attribute values | walks descendants, filters to `class`, `title`, `aria-label`, `id`, `data-*`, lowercases |
| `_ancestors` | walks **past** `#document` | stops below it |

Measured with `grep -rn 'from tests.support.html import <name> as _<name>'
tests/`: **12 files alias at least one of the three** — `ancestors` in 12,
`attribute_text` in 4, `carries` in 3. So a reader moving between files meets
the same `_`-prefixed spelling meaning two things.

**This is a naming hazard, not a defect.** Every assertion in those two files is
correct as written; the divergent readings are deliberate and the files are the
only callers. What is missing is the record, which is what the rest of the suite
does: a `**Kept local**` note at the declaration naming the shared function it
is not and the input that distinguishes them. Six such notes across two files.

**Not a rename.** `share-the-ordered-html-harness` measured that answer for its
own ten keeps and rejected it: 92 sites, 56 of them inside `def test_` bodies,
and `_carries` is a proper substring of `_page_carries` and of three test
function names, so a textual rename corrupts them while the suite stays green.

**The measurement method, which is the transferable part.** Do not decide these
by reading and do not decide them by running. A source comparison over-reports
difference — it reads a parameter rename as divergence. Execution over-reports
sameness — in that change a helper agreed with the shared function on every call
the tier made while carrying a demonstrably different body, and another agreed
on all 163 calls with its divergent branch *executing* 4 times. Use both, each
as a veto in one direction: source difference vetoes a migrate, execution
disagreement vetoes a keep, and reading adjudicates the rest.

### Small cleanups, not worth a change each

Verified present 2026-09-01; suitable for one chore commit.

| Item | Why |
|---|---|
| No `.dockerignore` | The whole build context — `.venv/`, `.git/`, caches — ships to the daemon on every build. The image itself is clean, since the `Dockerfile` copies selectively. |
| `anyio` undeclared | The test suite depends on its pytest plugin (`pytestmark = pytest.mark.anyio`) but gets it transitively. `pyproject.toml`'s own `aiohttp` comment records this project's convention of declaring such packages directly. |
| `httpx2` in dev dependencies | It is a runtime requirement of `openai`, not a test dependency. Likely added by mistake. |
| `description = "Add your description here"` | Placeholder from the project template. Deliberately excluded from `tighten-type-checking` as unrelated scope. |
| No `known-first-party` for ruff's isort | Without `known-first-party = ["commerce_ops"]` under `[tool.ruff.lint.isort]`, ruff infers first-party packages per invocation, so the classification changes with the set of files it is handed. `uv run ruff check` over the whole project passes while the `pre-commit` hook — which passes explicit staged paths — fails `I001` on those same files, and fixing one file at a time reports success while fixing them together still finds errors. Cost a commit two attempts to diagnose; the one-line declaration makes it deterministic. |
| `post_monitoring_message` is misnamed | `launch/infrastructure/driven/slack_notifier.py` takes `channel` as an argument and is called with `launches_channel()` at every launch-thread site. It posts to whichever channel it is given; only its name still says otherwise. `post_message`. **Measured, 2026-09-02, and declined by `inject-the-thread-anchor-poster` rather than folded in as this row previously invited.** The rename's scope is **14 occurrences over 5 source files** (`slack_notifier.py` 2, `gate_confirmation.py` 4, `automation_confirmation.py` 4, `slack_entry.py` 3, `launch_thread_delivery.py` 1) plus the launch-side tests. An unqualified `grep` gives 27 source and 42 test occurrences; of those, 11 source and 20 test belong to `briefing`/`shared` and their **different function of the same name**, as does `shared/application/ports.py`'s `MonitoringNotifier.post_monitoring_message(message: str)`, not part of the rename. **The precondition this row named is now met** (`fix-stuck-step-report-notifier`, 2026-09-03): `clickup_sync_job.py:200` still calls the message-only shape correctly, and `automation_pass.py`'s call is no longer on an injected collaborator that is `briefing`'s notifier — `worker.py` now injects `launch`'s own module, typed as a new `ThreadReplyNotifier` Protocol (`launch/application/ports.py`) rather than `MonitoringNotifier`. **This makes the ambiguity a three-way one, not settled by that fix**: `briefing/application/ports.py`'s `MonitoringNotifier.post_monitoring_message(message: str)`, `shared/application/ports.py`'s Protocol of the same name and shape, and `launch/application/ports.py`'s new `ThreadReplyNotifier.post_monitoring_message(*, channel, text, thread_ts=None)` are three same-named methods across three Protocols with two incompatible shapes — a future reader still has to know which one a given call site means. `fix-stuck-step-report-notifier`'s `design.md` deliberately left this rename out of its own scope, recording the same reasoning this row already gave. Both source-side occurrence counts above predate that change and want re-measuring before this is picked up. |
| `Proposal.outcome` and `Proposal.finding` are `Any` | `step_handlers/listing/subcategory_advisor.py:229-236`. `StepResolution` types the same two values properly (`StepOutcomeValue`, `Result[Any, Any] \| None`), and `Proposal` exists only to carry them one function further. Nothing forces the widening — no import boundary is crossed here. |
| `docs/domain-map.md` still describes `Principal` and a repo-owned YAML | Its access slice names `Principal` as the `access` root model, and describes principals as "repo-owned YAML granting by SKU" with grants "translated to identifiers at resolution time". Both were made false by `move-principals-to-roster` (2026-08), which replaced the file with a Postgres-backed directory and the grant model with active-member → unrestricted. **Deliberately left by `rename-the-roster-to-members`**, which corrected the same vocabulary everywhere else, and which excludes this file whole so the exclusion is enforced rather than asserted: the stale text carries neither stem, so no substitution row or completeness check reaches it, and correcting it means a hand edit outside the machine-checked half of a change whose whole warrant is that everything is inside it. More to the point, a correct fix is not a rename — the SKU-granting design no longer exists in any form — so it is a judgement about the map's accuracy, which is different work. |
| Comment archaeology in `main.py` | `main.py:261-272` spends five lines describing what a *previous version of a comment* said. Git holds that. The comment convention this project keeps — record the reasoning, not just the behaviour — is worth keeping; recording the reasoning's own edit history is not. |
