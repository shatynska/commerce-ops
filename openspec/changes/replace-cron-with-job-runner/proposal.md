## Why

Scheduled work runs today through a BusyBox `crond` container that fires `wget` at five HTTP endpoints. Every property that makes scheduled work trustworthy is missing, and one of them is actively discarding evidence of failure.

Read the command `docker-compose.yml`'s `cron` service actually runs:

```
0 6 * * * wget -q -T 10 -O /dev/null --header="Authorization: Bearer $TRIGGER_SECRET" --post-data= http://app:8000/products/monitoring/daily
```

- **The response is written to `/dev/null`.** `monitoring.py`'s daily route deliberately returns HTTP 500 when the database read fails — `product-monitoring` has a whole requirement about surfacing that distinctly from a delivery failure. Nobody will ever see it. The failure path was specified, implemented, tested, and then routed to a black hole.
- **There are no retries.** If the app container is mid-restart at 06:00, that day's digest is skipped silently and permanently.
- **There is no run history.** The question "did the daily digest run yesterday, and did it succeed?" has no answer anywhere in the system.
- **`depends_on: - app` carries no condition**, although the `Dockerfile` already defines a `HEALTHCHECK` on `/health` that would make `condition: service_healthy` work. On a redeploy, `crond` starts against an app that may not be serving.
- **No `TZ` is set**, so every schedule is UTC. That may be intended; nothing records it either way, which makes it a latent surprise rather than a decision.

**And the trigger surface is publicly reachable.** The Traefik labels route `Host(fuperia.shatynska.com)` to port 8000 with no path restriction, so `POST https://fuperia.shatynska.com/products/monitoring/daily` is reachable from the open internet, defended only by a static bearer secret with no rotation and no rate limiting. The `app_cron` network isolates the cron container from other networks; it does not isolate the endpoint from the internet.

Underneath all of it is a structural problem that will not improve with patching: **a fire-and-forget HTTP POST cannot express retry, backoff, idempotency, or run history**, because those are properties of a queue, not of a request.

## What Changes

- **A Postgres-backed job runner replaces `crond`.** Scheduled work becomes jobs in a queue held in the database the application already runs, executed by a worker process, with retries, backoff, and per-run history as properties of the runner rather than things to build.
- **The `cron` container is removed** from `docker-compose.yml` and replaced by a `worker` service running from the same image as `app`, with the image's HTTP healthcheck overridden — a worker serves no HTTP and would otherwise report unhealthy forever.
- **The five HTTP cadence routes are removed**, and with them the `internal-trigger` capability and `TRIGGER_SECRET`. The worker invokes the application layer directly, which is what a driving adapter is supposed to do — the current arrangement has one driving adapter calling another over the network to reach the application layer. This also deletes the public trigger surface described above outright.
- **The four unimplemented cadences stop being scheduled.** Weekly, biweekly, monthly and quarterly all call a use case that logs and returns; scheduling them produces four recurring no-ops. Their reporting logic depends on marketplace data that is deferred, so they return to the schedule when they have something to report. **BREAKING** for `product-monitoring`, which currently requires them to be triggerable.
- **Run history is recorded and queryable**, so "did it run, and did it succeed" has an answer.
- **What a missed window means is decided**, rather than left to whatever the runner happens to do: a run whose due moment passed while no worker was available is performed once when a worker returns, not silently skipped and not replayed once per missed window.
- **`condition: service_healthy` and an explicit `TZ`** are set, making the existing `HEALTHCHECK` load-bearing and log timestamps unambiguous. `TZ` does not control the schedule and could not: the runner interprets every schedule in UTC, so `TZ=UTC` matches the logs to the schedule rather than setting it.

## Capabilities

### New Capabilities
- `scheduled-jobs`: running the application's recurring work on a schedule inside the deployment — retrying a failed run with backoff, and recording each run's outcome so it can be asked about afterwards.

### Modified Capabilities
- `product-monitoring`: its cadences stop being HTTP endpoints and become scheduled jobs, so every requirement phrased in terms of an endpoint, a triggering request, or a response status is restated in terms of a run and its outcome. The requirement that the four unimplemented cadences be triggerable is removed. (Requirement *headers* keep their existing wording where OpenSpec's header matching requires it; a header rename would need a REMOVE-plus-ADD pair and would lose the change history.)
- `runtime-configuration`: one requirement's illustrative example cites `internal-trigger`, which this change removes. The permission itself still stands and is still relied on by `LOG_LEVEL` and `DATABASE_URL`, but its condition is generalised as well as its example: from "where per-request tolerance of absence is itself required behavior" — a criterion written for the trigger guard, which would cover neither remaining reader once the guard is gone — to "where routing it through the declaration would defeat required behavior". A wider class of direct reads, deliberately.
- `deploy-pipeline`: its Postgres-isolation requirement says the database "SHALL be reachable only from the `app` service" — true when `app` was the only service this application ran. The worker needs the same database for the same reasons, so the requirement is restated as isolation from the public-facing network and from other applications on the host, rather than from this application's own processes. The two existing scenarios are unchanged and a third is added, along with the normative clause it guards: the network SHALL NOT be declared external to this compose file, which is the mechanism by which "isolation from other applications on the host" is achieved rather than merely asserted — an external network can be joined by services this application does not define.

### Removed Capabilities
- `internal-trigger`: its only consumer was the five cadence routes. With no endpoint invoked by internal automation, a shared-secret guard protects nothing.

## Impact

- **New dependency**: a job runner and, with it, a second Postgres driver in the process — plus the libpq wrapper that driver does not install by default, which the dependency line has to name explicitly. See design.md, which records the choice, the alternative that avoids the second driver, and why it was not taken.
- **New**: a worker entry point, the daily job definition, a last-success accessor over the runner's job history in `shared/infrastructure/driven/`, an autogenerate-exclusion predicate beside it, and an Alembic migration installing the runner's schema.
- **Modified**: `alembic/env.py` gains that exclusion filter at both its `context.configure()` calls — without it the next autogenerated migration for any unrelated feature would propose dropping the run history.
- **Removed**: `docker-compose.yml`'s `cron` service and `app_cron` network; `products/infrastructure/driving/monitoring.py`'s five routes; `shared/infrastructure/driving/trigger_guard.py`; `TRIGGER_SECRET` from the settings model and from `deploy.yml`'s `.env` render step; `test_internal_trigger_guard.py` and the retired routes' tests.
- **Five regression guards are amended, not deleted** — `test_settings.py`, `test_settings_env_drift.py`, `test_preflight.py`, `test_startup_without_configuration.py` and `test_logging_process_boundary.py` each hard-code `TRIGGER_SECRET` in a transcribed set. They test the configuration declaration — and, in the last case, logging across a process boundary — not the trigger guard, so removing the variable means updating their transcriptions. The fifth is stale rather than breaking, since `Settings` ignores extra variables, so only a grep finds it.
- **Depends on `centralize-database-session`**, which has landed: the worker runs outside any HTTP request and needs a session. That change's "One Connection Pool Per Process Serves Every Application Session" requirement explicitly admits infrastructure holding its own connection for a non-session purpose, which is what the queue's `LISTEN` connection is — so the second driver is compatible with it as written, not in spite of it.
- **Depends on `configure-application-logging`**, which has landed: a worker's value is what it reports, and application `INFO` records were discarded before it.
- **Does not include overdue reporting or the freshness endpoint.** Those need this change's run history to exist first, and they carry their own design questions — where a cross-cutting check lives given `shared` may not import a business module, what state suppresses a repeated alert, and what an externally reachable freshness endpoint may disclose. They are `report-overdue-scheduled-runs`, proposed separately.
- **Does not include the ClickUp reconciliation pass.** There is nothing to reconcile yet: `clickup_client` has no caller anywhere in the tree, so no ClickUp task exists for Postgres to drift from. It belongs after `add-product-creation-clickup-task`.
- **Deploy**: one `.env` variable removed rather than added, and a `worker` service that must be running for any scheduled work to happen — a new way for the deployment to be silently half-up, which `report-overdue-scheduled-runs` exists to catch and which this change deliberately leaves undetected in the interim.
