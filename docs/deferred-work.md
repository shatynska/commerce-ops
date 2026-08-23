# Deferred work

Things this project has deliberately **not** done, recorded so they are not rediscovered as surprises.

Each item is already argued somewhere — in a change's `design.md`, a non-goal, or an open question. That is the right place for the reasoning, and this file does not repeat it. What this file adds is **findability**: a change's artifacts move to `openspec/changes/archive/` once it ships, and a deferral recorded only there is a deferral nobody will find again.

Delete an entry when it is done or when it stops being true. An entry that no longer holds is worse than no entry.

---

## Needs a decision before it can be built

### `specify-non-string-message-content`

`omni_agent`'s `answer_question` ends with `return result["messages"][-1].content`, which LangChain types as `Any` and which can genuinely be a **list of content blocks** rather than a string. `tighten-type-checking` holds that line with a scoped `# type: ignore` rather than fixing it, because fixing it means choosing what the ops team sees, and the recorded `omni-agent` spec settles neither option:

- **Join the text blocks.** The model did answer, so reporting a failure would be wrong. Sits awkwardly with nothing, but produces a lossy join for structured content.
- **Treat it as a failure.** Simpler, but `slack.py` catches broadly and posts "Sorry, I ran into an error" for a call that succeeded — which reads against `omni-agent`'s "Model failure is surfaced, not masked", scoped as it is to a *failed* model call.

**Latent, not live**: `build_production_graph` pins `ChatOpenAI(model="gpt-4o-mini")` with no multimodal input and no structured output, so `.content` is a `str` on every path exercised today. There is time to specify it properly.

**Blocks**: archiving `tighten-type-checking` (its task 5.5 makes proposing this change a precondition).
**Recorded in**: `tighten-type-checking`'s `design.md`, "The `Any` return … is held with a scoped ignore".

---

## Belongs to the `/infrastructure` repository, not this one

These affect the host or the deployment platform, and would be wrong to fix here.

### Docker log rotation — unhandled

Docker's default `json-file` driver runs with **no `max-size`** anywhere on this host. Container logs grow unbounded on the boot disk, and `configure-application-logging` increases the rate by making application `INFO` records visible for the first time.

A repository-wide search of `/infrastructure` for `max-size`, `log-driver`, `log_opts` and `logrotate` returns **nothing**, so this is genuinely unconfigured rather than configured elsewhere. It belongs in that repo's host configuration — the `geerlingguy.docker` role takes `docker_daemon_options`, which writes `/etc/docker/daemon.json` — because it affects every container on a shared host, not just this application.

**Recorded in**: `configure-application-logging`'s `design.md` (Non-Goals) and `proposal.md` (Impact).

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

### The parked `add-product-creation-clickup-task` change

A fully reviewed change proposal on the local branch of the same name (commit `0b9b85c`), never implemented. It adds a Slack modal on the `product_agent` app for creating a product, plus a best-effort ClickUp task — and it is the only thing that would give `clickup_client` a caller, which it currently lacks entirely.

**It is stale in two ways.** Its tasks were written before the Bolt migration and describe a hand-rolled `SignatureVerifier` and manual form-body parsing, both of which Bolt supersedes — and `shared/infrastructure/driving/slack_app.py` now exists as the registry it should register with. It also predates `centralize-database-session`, so its instruction to obtain a session from `monitoring.py` needs repointing at the shared provider.

Needs an `openspec-update-change` pass before implementation. Parked deliberately: its domain logic warrants review first.

### Small cleanups, not worth a change each

Verified present at the time of writing; suitable for one chore commit.

| Item | Why |
|---|---|
| No `.dockerignore` | The whole build context — `.venv/`, `.git/`, caches — ships to the daemon on every build. The image itself is clean, since the `Dockerfile` copies selectively. |
| `anyio` undeclared | The test suite depends on its pytest plugin (`pytestmark = pytest.mark.anyio`) but gets it transitively. `pyproject.toml`'s own `aiohttp` comment records this project's convention of declaring such packages directly. |
| `httpx2` in dev dependencies | It is a runtime requirement of `openai`, not a test dependency. Likely added by mistake. |
| `description = "Add your description here"` | Placeholder from the project template. Deliberately excluded from `tighten-type-checking` as unrelated scope. |
| No `known-first-party` for ruff's isort | Without `known-first-party = ["commerce_ops"]` under `[tool.ruff.lint.isort]`, ruff infers first-party packages per invocation, so the classification changes with the set of files it is handed. `uv run ruff check` over the whole project passes while the `pre-commit` hook — which passes explicit staged paths — fails `I001` on those same files, and fixing one file at a time reports success while fixing them together still finds errors. Cost a commit two attempts to diagnose; the one-line declaration makes it deterministic. |
