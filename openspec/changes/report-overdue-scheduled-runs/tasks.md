## 0. Prerequisites

- [ ] 0.1 Confirm `replace-cron-with-job-runner` has landed, **including its last-success accessor** (its task 2.10) — this change consumes that accessor rather than building one

## 1. The schedule and tolerance registry

- [ ] 1.1 Add a registry in `shared` holding, per piece of recurring work, its identifier, its schedule and its tolerance — the single declaration both the overdue check and the freshness endpoint read (`scheduled-jobs`: "Every consumer reads the same declaration")
- [ ] 1.1a Add a **single registration helper** that takes the schedule **once**, applies the job runner's periodic with it, and writes the registry entry from that same value. Do **not** let a job module declare the cron expression to the runner and separately pass a copy to the registry: the runner would fire on one value while the longest-gap check validated the other, and a job moved to weekdays-only would report itself overdue every weekend (`scheduled-jobs`: "The schedule run and the schedule checked are the same value")
- [ ] 1.2 Convert the prerequisite's job definitions in `products/infrastructure/driving/` to register through that helper, declaring schedule and tolerance **together** so the two stay adjacent
- [ ] 1.3 Add `src/commerce_ops/registrations.py` — a sibling of `main.py`, `preflight.py` and `worker.py`, outside the `.importlinter` containers — holding **one** list of job-module imports (the `products` job definitions **and** the overdue-check module from section 4) and exposing `register_all()`. Call it from both `worker.py` and `main.py`. One list, not two per-root lists: the failure mode is silent and asymmetric, and `main.py` omitting the check module would leave the endpoint without worker liveness while every non-emptiness test still passed (design.md — "Schedules and tolerances live in one registry")
- [ ] 1.3a Remove `worker.py`'s own job-module import list (added by the prerequisite's task 2.8) and have it call `register_all()` instead — otherwise "one list, not two" is false and the divergence this design exists to prevent is still possible
- [ ] 1.4 Test: run **each composition root in a fresh interpreter** (the subprocess pattern `tests/unit/test_startup_without_configuration.py` already uses), dump each registry's identifier/tolerance pairs, and assert they are identical. An **in-process** comparison cannot fail: the registry is a module-global, so importing either root reads the same object — it would pass even when `main.py` never calls `register_all()` at all, which is exactly the divergence being tested for (`scheduled-jobs`: "Every process holds the same registration")
- [ ] 1.4a Require `register_all()` and everything it imports to read no configuration at import time. It pulls the job modules into `main.py`'s import graph, and `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" is enforced by an existing fresh-interpreter guard that would fail
- [ ] 1.4b Make registration idempotent per identifier, and a conflicting re-registration of the same identifier an error — `register_all()` can run twice in one process (both roots imported in a test), and silently overwriting would hide a duplicate-identifier mistake
- [ ] 1.5 Declare the daily digest's tolerance as 30 hours — longer than its 24-hour interval, so a delayed or in-progress run is never reported
- [ ] 1.6 Assert, not merely by convention, that each tolerance exceeds the **longest gap between consecutive scheduled runs over a bounded horizon** — computed from the schedule expression, not assumed uniform. A weekday-only schedule gaps 72 hours over a weekend and a monthly one 28–31 days, and the four suspended cadences return to the schedule later (`scheduled-jobs`: "A tolerance exceeds its work's longest scheduling gap")
- [ ] 1.6b Enumerate from **the job runner's registered periodics**, not from the registry, when asserting that every piece of work has a tolerance. Enumerating the registry makes the assertion circular — it can only find what is already there, so a periodic registered with the runner and missing from the registry passes unnoticed while being invisible to both the check and the endpoint (`scheduled-jobs`: "Every piece of work the runner will run has a tolerance")
- [ ] 1.6a Declare `croniter` directly in `pyproject.toml` rather than relying on it arriving transitively with the runner — `pyproject.toml`'s existing `aiohttp` comment records this project's convention for a package it uses but does not own, and a runner release that drops or renames the transitive dependency would otherwise break 1.6 through an unrelated `uv sync`

## 2. The notifier port

- [ ] 2.1 Add a `MonitoringNotifier` `Protocol` to `shared/application/ports.py` declaring `post_monitoring_message(message: str) -> None` as an async method, with a docstring recording that `shared-boundary` forbids `shared` from importing `products`
- [ ] 2.2 Export it from `shared/application/__init__.py`'s `__all__`
- [ ] 2.3 Test: `products`' `slack_notifier` **module** satisfies the Protocol structurally — bind the module itself to a `MonitoringNotifier`-typed name, mirroring how the existing `ClickUpTaskWriter` test binds `clickup_client`. Note the port is satisfied by the module, not by the bare `post_monitoring_message` function; a Protocol declaring a method is not satisfied by a function of that name

## 3. Suppression state

- [ ] 3.1 Add a **suppression** table recording that an overdue report has been delivered for a piece of work, with its own Alembic migration and a `downgrade` — **not** folded into the runner's own tables, which a runner schema upgrade could replace
- [ ] 3.2 Add a **separate `known_work`** table recording when the system first knew of each piece of work. It must be separate: first-known has to exist before any report and persist across successes, while the suppression row is written only after a delivered report and cleared on success — one row cannot carry both lifecycles, and folding them either erases the anchor on recovery or breaks the write-after-delivery rule (design.md — "First-known is its own table")
- [ ] 3.2a Write the first-known row as an **idempotent upsert from the freshness endpoint's handler, before it evaluates**, as well as from the overdue check in the worker. The recorded time is the first observed and is never advanced. A worker that never starts would otherwise leave every work without an anchor, so the endpoint could compute no overdueness and would report healthy forever (`scheduled-jobs`: "A worker that never started still produces an anchor", "A later observation does not advance the anchor")
- [ ] 3.2b Do **not** put the anchor write in `main.py`'s lifespan or at import. `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" is enforced by `tests/unit/test_startup_without_configuration.py`, which starts `main.app` with `DATABASE_URL` absent — a write there either fails that guard or must swallow its own failure, and a best-effort anchor is no anchor in exactly the situation it exists for (design.md — "Which `app` path, specifically")
- [ ] 3.3 Verify `uv run alembic upgrade head` then `downgrade -1` against a local Postgres
- [ ] 3.4 Add a repository for it in `shared/infrastructure/driven/`, using `centralize-database-session`'s provider
- [ ] 3.5 Write the suppression record **only after a report has been delivered successfully** — never before. Recording first and failing to deliver loses the period's only alarm permanently, since suppression lifts when the work succeeds and not when Slack recovers (design.md — "Suppression is a table, written only after delivery succeeds")
- [ ] 3.6 Clear the **suppression** record when the work next succeeds — this defines the end of a period of overdueness and makes recurrence reportable again. Do **not** clear the first-known row (`scheduled-jobs`: "A success does not erase the first-known time")
- [ ] 3.7 If a suppression write fails after a successful delivery, allow the next check to report again — the duplicate is the accepted outcome, consistent with preferring a duplicate to a miss for the alarm itself

## 4. The overdue check

- [ ] 4.1 Add the overdue-check job in **`shared/infrastructure/driving/`** — a scheduled job is a driving adapter, and that layer may import `shared.infrastructure.driven` where the accessor and repository live, which `shared.application` could not. It must not import `products`; `lint-imports` enforces this
- [ ] 4.2 Wire the notifier in `src/commerce_ops/worker.py` as a **separate step after `register_all()`**, passing `products`' `slack_notifier` **module** — `worker.py` sits outside the `.importlinter` containers, which is what makes the injection legal. `register_all()` itself must stay notifier-free, since `main.py` calls the same function and has no notifier; and the notifier is never a job argument, since the runner passes only serializable values to a job
- [ ] 4.3 Schedule it hourly
- [ ] 4.4 Determine overdueness from the registry's tolerance against the accessor's last success, or against the first-known time where there has been no success
- [ ] 4.5 Report each overdue piece of work once, naming the work and when it last succeeded, or that it has never succeeded
- [ ] 4.6 Do not report work that is absent from the registry — the four unscheduled cadences must never appear as overdue
- [ ] 4.7 **Enrol the overdue check's own successful runs as monitored work**, with a tolerance of a few hours, registering it through `registrations.py` so both processes see it. Without this the freshness endpoint's dead-worker latency is bounded below by the shortest tolerance it watches — 30 hours — which is roughly when a human would notice the digest missing anyway (design.md — "The worker's own liveness is monitored work"; `scheduled-jobs`: "The Process Running Scheduled Work Is Itself Monitored Work")
- [ ] 4.8 **Record the check's run as successful whenever it completed its evaluation, regardless of whether delivery succeeded.** A failed delivery is expressed solely by not writing suppression. Failing the run instead would make the liveness evidence stale during a Slack outage, so the endpoint would report an absent worker while the worker was running normally — a false page, and it would make the Slack-independent endpoint Slack-dependent (`scheduled-jobs`: "A completed evaluation records a successful run despite a failed delivery")

## 5. The freshness endpoint

- [ ] 5.1 Add the route at `/health/scheduled-runs` in **`shared/infrastructure/driving/`**, beside `health.py`, reading the registry and recorded state through the session provider — it must **not** contact the worker in any way, since the worker's absence is what it exists to expose
- [ ] 5.2 **Register its router in `main.py`**, as every other route in the tree requires — a green unit suite does not catch an unregistered router
- [ ] 5.3 Report, per piece of work, when it last succeeded or that it never has
- [ ] 5.4 Signal unhealthy by **HTTP status**, not only in the body, so an off-the-shelf uptime monitor can act on it without parsing prose
- [ ] 5.5 Report **healthy** in a deployment where nothing has yet run and no tolerance has elapsed since first-known — a fresh deploy must not alarm (`scheduled-jobs`: "A freshly deployed system reports healthy")
- [ ] 5.6 Respond, rather than failing or hanging, while no worker is available
- [ ] 5.7 Cache the response briefly (a few seconds) so repeated anonymous requests cost one query rather than one each — the endpoint is unauthenticated on an internet-facing service, and unlike `/health` it touches the database (design.md — "Unauthenticated, with the `/health` analogy stated at its actual strength"). The cache must **not** short-circuit task 3.2a's anchor upsert, or a newly registered piece of work would go unanchored for as long as a cached response is served
- [ ] 5.8 Decide and implement the endpoint's behavior when the database is unreachable: respond unhealthy rather than serving a stale healthy answer, and cache only successful reads so an outage cannot be masked by the cache in 5.7

## 6. Tests

- [ ] 6.1 Test: work outside its tolerance, worker alive, posts a message naming the work and its last success (`scheduled-jobs`: "Overdue work is reported")
- [ ] 6.2 Test: work that has never succeeded is reported once its tolerance has elapsed since first-known
- [ ] 6.3 Test: a freshly known piece of work is not overdue before its tolerance elapses (`scheduled-jobs`: "A freshly deployed system does not report work as overdue immediately")
- [ ] 6.4 Test: work within tolerance is not reported
- [ ] 6.5 Test: work absent from the registry is never reported
- [ ] 6.6 Test: a piece of work already reported is not reported again while it stays overdue
- [ ] 6.7 Test: **a report whose delivery fails leaves the work eligible, and the next check attempts it again** (`scheduled-jobs`: "A failed delivery leaves the work eligible to be reported again")
- [ ] 6.8 Test: suppression survives a restart — with the record present, a fresh check posts nothing
- [ ] 6.9 Test: work reported, then succeeding, then overdue again, is reported a second time
- [ ] 6.10 Test: the check's own liveness is among the monitored work, and its tolerance is shorter than the daily digest's (`scheduled-jobs`: "An absent worker becomes visible well before the work it runs is overdue")
- [ ] 6.11 Test: the endpoint reports per-work last success, and "never" where applicable
- [ ] 6.12 Test: the endpoint's HTTP status distinguishes unhealthy from healthy
- [ ] 6.13 Test: the endpoint reports healthy on a fresh deployment where nothing has run
- [ ] 6.14 Test: the endpoint responds and reports overdueness with no worker available, and makes no call to the worker (`scheduled-jobs`: "The endpoint does not consult the process running scheduled work")
- [ ] 6.15 Test: the check and the endpoint reach the same verdict for the same work, reading the registry populated by `registrations.py` — not an ad-hoc registry built in the test (`scheduled-jobs`: "Every consumer reads the same declaration")
- [ ] 6.16 Test: a delivery failure leaves the check's own liveness evidence fresh — the run is recorded successful and the endpoint does not report the worker absent (`scheduled-jobs`: "A completed evaluation records a successful run despite a failed delivery", "The freshness interface is unaffected by a reporting-channel outage")
- [ ] 6.17 Test: with the worker never having started, one request to the endpoint anchors each registered work, and a later request once the tolerance has elapsed reports it overdue (`scheduled-jobs`: "A worker that never started still produces an anchor")
- [ ] 6.18 Test: a work's first-known time is unchanged after it succeeds (`scheduled-jobs`: "A success does not erase the first-known time")
- [ ] 6.19 Test: a second observation does not advance an existing first-known time (`scheduled-jobs`: "A later observation does not advance the anchor")
- [ ] 6.20 Test: a periodic registered with the runner but absent from the registry fails the tolerance assertion — the guard against 1.6b's circularity

## 7. Verification

- [ ] 7.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports` — the last is the real check on section 4's placement
- [ ] 7.2 Run the integration tier against a local Postgres with both migrations applied
- [ ] 7.3 Run `openspec validate report-overdue-scheduled-runs --strict`
- [ ] 7.4 Locally: bring the stack up, stop the `worker` container, and confirm the endpoint reports unhealthy once the **worker-liveness** tolerance elapses — hours, not the digest's 30. Restart it and confirm it returns to healthy. This is the end-to-end demonstration that the dead-worker case is now visible and prompt
- [ ] 7.5 After deploy: confirm the endpoint is reachable and reports healthy
- [ ] 7.6 Hand to the user, or record in `/infrastructure`, that an external uptime checker should be pointed at `/health/scheduled-runs` — the change is not fully realized until something outside the deployment polls it (design.md — Open Questions)
