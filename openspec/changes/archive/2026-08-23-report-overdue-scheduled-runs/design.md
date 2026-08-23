## Context

See proposal.md — Why. Constraints that shape the approach:

- **`replace-cron-with-job-runner` lands first**, providing the run history, the last-success accessor, the worker process, and the `scheduled-jobs` capability this change adds to.
- **`.importlinter`'s `shared-boundary` contract forbids `commerce_ops.shared` from importing `commerce_ops.products` or `commerce_ops.omni_agent`**, unconditionally. `lint-imports` runs in the commit hook and in CI.
- **`module-layers` forbids `shared.application` from importing `shared.infrastructure`.** Which layer of `shared` holds the check therefore decides what it may reach.
- **The only adapter that posts to the monitoring channel is `products/infrastructure/driven/slack_notifier.py`**, whose `post_monitoring_message(message: str) -> None` is a module-level async function.
- **`main.py`, `preflight.py` and `worker.py` sit outside the three `.importlinter` containers** and may import anything.
- **`app` is internet-facing** — Traefik routes `Host(fuperia.shatynska.com)` to port 8000 with no path restriction — and `/health` is already served unauthenticated.
- **The prerequisite places job definitions in `products/infrastructure/driving/`**, on the reasoning that a scheduled job is a driving adapter. Schedules, and therefore tolerances, are declared there.

## Goals / Non-Goals

**Goals:**

- A failing scheduled job is reported to the people who need to know, once.
- An absent worker is detectable from outside the deployment, and promptly.
- The difference between those two is explicit rather than assumed.

**Non-Goals:**

- **Building or configuring the external checker.** No uptime monitor exists in this project or in `/infrastructure`. This change provides the endpoint it would poll.
- **Notifying on recovery.** Work that recovers produces no message; the team gets an alarm and no all-clear. At one job and one channel the alternative is more traffic for little gain, and the freshness endpoint always shows current state. Recorded as a decision so the next change does not have to guess whether it was one.
- **Run-history retention or pruning.** The last-success accessor reads the runner's own history; pruning it naively would delete the evidence this change depends on.
- **Alerting anywhere other than Slack**, and **paging, escalation or severity tiers.**
- **Reporting on work with no declared schedule.** The four unscheduled cadences must never appear as overdue.

## Decisions

### Schedules and tolerances live in one registry that `shared` owns and job modules populate

This is the boundary problem this change has to solve, and the notifier is only half of it.

The prerequisite puts the daily digest's schedule in `products/infrastructure/driving/`. The overdue check needs the tolerance to compare against, and it lives in `shared`, which may not import `products`. The freshness endpoint on `app` needs the same tolerance. Three consumers, one fact, and a contract in the way.

**A `shared`-owned registry that job definition modules register into, populated through one shared registration module.** A job module declares its schedule and tolerance together — keeping them adjacent, which is what makes "tolerance exceeds the longest gap" checkable — and registration hands both to `shared`. `shared` reads its own registry and imports nothing.

**One registration call, not two declarations of the same schedule.** The obvious shape has the job module apply the runner's periodic decorator with a cron expression *and* register a tolerance with a copy of that expression. Then the runner fires on one value while the longest-gap check validates the other, and nothing notices when they diverge: a job moved to weekdays-only would report itself overdue across every weekend, which is exactly the false alarm the tolerance rule exists to prevent. The converse is as bad — a periodic registered with the runner but absent from the registry is invisible to both the check and the endpoint, and "every registered work has a tolerance" is satisfied circularly if "registered" means the tolerance registry.

So registration is a **single helper** that takes the schedule once, applies the runner's periodic with it, and writes the registry entry from the same value. The enumeration the tolerance assertion runs over is **the runner's registered periodics**, not the registry — so the assertion polices the registry rather than agreeing with it.

**The registry must be populated identically in both processes**, and the obvious mechanism gets this wrong. Having `worker.py` and `main.py` each carry their own list of job-module imports means two lists kept in step by hand — and the failure is silent and asymmetric: if `main.py` imports the `products` job modules but not the check module that registers worker liveness, the endpoint quietly omits the very thing that makes it a dead-man's switch, and a test asserting "the registry is non-empty" passes in both processes. That restores the 30-hour latency this design exists to remove, at runtime, with a green suite.

So the imports live in **one** module — `registrations.py`, a sibling of `main.py`, `preflight.py` and `worker.py`, outside the `.importlinter` containers and therefore free to import anything — exposing a `register_all()` that both roots call. One list, not two; divergence is impossible by construction rather than by discipline. It also turns an import-for-side-effect into an ordinary call, which ruff's default `F401` does not flag — the earlier shape would have failed the commit hook and invited a developer to "fix" it by deleting exactly the import the design depends on.

**The safeguard has to run in separate interpreters, or it proves nothing.** The registry is a module-global in `shared`. Within one pytest process, importing `worker` and importing `main` read the *same object*, so any in-process comparison of "the registry after each root" is tautological — it holds even when `main.py` never calls `register_all()` at all, which is precisely the divergence it is meant to detect. The test therefore runs each root in a fresh interpreter and compares serialized identifier/tolerance pairs, following the subprocess pattern `tests/unit/test_startup_without_configuration.py` already uses for process-global effects.

This is worth stating because the weaker version looks entirely convincing.

**One list means the worker stops carrying its own.** `replace-cron-with-job-runner` has `worker.py` import the job definition modules directly. Once `registrations.py` exists, that list moves into it and `worker.py` calls `register_all()` like `main.py` does — otherwise "one list, not two" is a claim about a file that is not the only file with a list.

**Alternatives.** *Tolerances in a table, seeded by migration* — makes the endpoint trivially correct, but separates the tolerance from the schedule it must be compared against, so drift becomes invisible; rejected. *Two per-root import lists* — rejected above. *Inject the registry as a parameter at both roots* — `main.py` gains knowledge of job definitions and two roots still need keeping in step; the shared registration module achieves the same isolation with one list.

**One consumer, one answer** is a requirement rather than a convention here, because the failure it prevents is silent: a check and an endpoint disagreeing about what is overdue produces an alarm nobody can reconcile with the dashboard.

### The overdue check reports through a `Protocol` port, injected by `worker.py`

The check is cross-cutting, so its home is `shared`; the channel is `products`-owned, and `shared-boundary` is machine-enforced. `shared/application/ports.py` gains a `MonitoringNotifier` Protocol declaring `post_monitoring_message`; `products`' `slack_notifier` **module** satisfies it structurally; `worker.py` passes the module in.

Note precisely what is and is not borrowed from `ClickUpTaskWriter`. Shared: the device — a structural `Protocol` letting a capability cross a boundary neither side may import across. Not shared: that port exists because of `module-layers` (a business module's application layer may not reach `shared.infrastructure`), the opposite direction to this one; and it has **no caller anywhere in `src/`**, so its composition-root wiring has never actually been written. This is the first time this project wires one. Claiming an established, exercised pattern would overstate it.

The port is passed the **module**, not the function — matching how the existing structural test binds `clickup_client` itself to a `ClickUpTaskWriter`-typed name. A Protocol declaring a method is not satisfied by a bare function of that name, and the two must not be mixed up at the wiring site.

### The check lives in `shared/infrastructure/driving/`

It is a scheduled job, and the prerequisite establishes that a scheduled job is a driving adapter. That placement also settles what it may reach: an infrastructure-layer module may import `shared.infrastructure.driven`, where the last-success accessor and the suppression repository live, which `shared.application` could not. The Protocol stays in `shared/application/ports.py`, where that file's docstring says ports exposed to other modules belong.

### First-known is its own table, written by whichever process first sees the work

"Work that has never succeeded is overdue once its tolerance has elapsed since the system first knew of it" needs an anchor, and the run history has none — it records runs, and a deployment whose worker never started has none.

**Who writes it decides whether the change works at all.** If only the check writes it, a worker that never starts leaves every piece of work without an anchor, the endpoint can compute no overdueness, and it reports healthy forever — the precise failure this capability exists to expose, reintroduced by the mechanism meant to close it. So `app` must write it too.

**Which `app` path, specifically — and one of the two candidates is barred.** `app` has exactly two places it could write: module import (or the lifespan `centralize-database-session` adds), and request handling.

- **The lifespan is barred.** `runtime-configuration`'s "Importing And Starting The Application Do Not Require Configuration To Be Present" requires startup to succeed with every variable absent, and `tests/unit/test_startup_without_configuration.py` enforces it by starting `main.app` under a `TestClient` with `DATABASE_URL` unset. A database write there either fails that guard or must swallow its own failure — and a best-effort anchor write is no anchor at all, since the case it exists for is exactly the one where things are not working.
- **The freshness endpoint's own handler writes it**, upserting first-known for every registered work before it evaluates. Chosen. It costs nothing at startup, is compatible with the requirement as it stands, and anchors at the first poll — which is when someone first cares.

The cost, stated: an anonymous `GET` performs a bounded, idempotent write (one row per registered piece of work, inserted once and never again). And the brief response cache must not short-circuit the upsert — not because new work appears mid-process (the registry is fixed at import), but because that write is what a cache-hit request has instead of a read, and so is how it discovers unreadable state at all. See "Unauthenticated, with the `/health` analogy stated at its actual strength".

Anchoring at first poll rather than at deploy means the anchor is slightly later than it could be. That is the trade for not putting a database write on a startup path a published requirement protects — and since the endpoint exists to be polled by an external checker, "first poll" is the moment the guarantee starts mattering.

**It is a separate table from suppression**, because the two lifecycles are incompatible and one row cannot carry both. First-known must exist before any report and persist across successes; the suppression record is written only *after* a delivered report and cleared *on* success. Folding them together means either the anchor is erased whenever work recovers, or suppression's write-after-delivery rule is violated for the row that carries the anchor.

**Alternatives.** *Seed first-known in the migration* — anchors to schema-apply time, close enough to first deploy and immune to a dead worker, but the migration would need to know the work set, which reintroduces the tolerances-in-a-table drift rejected above. *Write it only in the worker* — fails the never-started case, as above.

### Suppression is a table, written only after delivery succeeds

In-memory state would satisfy "report once" until the worker restarted — and a crash-looping worker is exactly when the outage is ongoing, so the memory version produces a message per restart: the flood the requirement exists to prevent, arriving by the worst route.

**The write must follow the delivery, not precede it.** If suppression is recorded and the Slack post then fails, the period's only alarm is lost permanently — suppression lifts when the *work* succeeds, not when the channel recovers, so nothing ever retries. Deliver first, record second; a failed delivery leaves the work eligible at the next check. This is deliberately the opposite of the prerequisite's rule that a delivery failure does not fail the digest's run: the digest is a report about products, and a duplicate is worse than a miss; this is the alarm itself, where a miss is worse than a duplicate.

Clearing on success is what defines the end of a period of overdueness, which gives recurrence-after-recovery for free.

**A delivery failure must not fail the check's own run**, and this is a separate decision from the ordering above. The check's successful runs are the worker's liveness evidence; if a failed Slack post failed the run, a Slack outage would make that evidence stale and the freshness endpoint would report an absent worker while the worker was running normally — turning a chat outage into a false page and making the endpoint Slack-dependent, which is exactly what design.md claims it is not. So: the check records a successful run whenever it completed its *evaluation*, regardless of delivery outcome, and a failed delivery is expressed solely by not writing suppression.

Note this is the same rule the prerequisite applies to the digest, reached by a different argument. The "a miss is worse than a duplicate" reasoning above governs the suppression *ordering*, not the run outcome; the two must not be conflated.

**If the suppression write itself fails after a successful delivery**, the next check reports again. That duplicate is the accepted outcome, consistent with preferring a duplicate to a miss for the alarm itself.

### The worker's own liveness is monitored work

Without this, the freshness endpoint's dead-worker latency is bounded below by the shortest tolerance of anything it watches — 30 hours, with only the daily digest enrolled. The endpoint exists to make an absent worker visible, and 30 hours is roughly when a human would notice the digest missing anyway, so it would deliver almost nothing.

The overdue check already runs hourly and already records a successful run each time. Those records are a per-hour heartbeat. Enrolling the check itself as monitored work, with a tolerance of a few hours, costs one registration and turns the endpoint into a genuine dead-man's switch: a dead worker becomes visible in hours, long before any work it runs is due.

### The freshness endpoint reads the database, never the worker

Any implementation that asks the worker anything fails exactly when it is needed. It reads recorded state through the session provider, on `app`.

**Unhealthy is signalled by HTTP status**, not only in the body, so an off-the-shelf monitor can be pointed at the URL with no custom logic — the whole reason the endpoint exists rather than someone reading logs. The path is `/health/scheduled-runs`, and its router is registered in `main.py` like every other route in the tree.

### The freshness response is a fixed JSON shape, and 200/503 carries the signal

```json
{
  "status": "ok",
  "work": [
    {"id": "overdue-check",        "last_success": "2026-08-23T14:00:03Z", "tolerance_seconds": 14400,  "overdue": false},
    {"id": "product-daily-digest", "last_success": null,                   "tolerance_seconds": 108000, "overdue": false}
  ]
}
```

- `status` is `"ok"` or `"unhealthy"`, reusing `/health`'s existing `{"status": "ok"}` vocabulary rather than inventing a second vocabulary one endpoint over.
- `work` is sorted by `id`, so two responses are diffable.
- `last_success` is RFC 3339 UTC, or `null` where the work has never succeeded — `null` *is* how "never" is expressed, not a sentinel string a checker would have to know about.
- `tolerance_seconds` is included so a reader can tell an overdue verdict from a merely slow one without opening the repository.
- `status` is `"unhealthy"` when any entry is `overdue`, **or** when the recorded state could not be read. It is deliberately not derived from the entries alone: the outage case below carries no entries at all, and an implementation that computes `status` by scanning `work` reports `"ok"` in a body sent with a 503.

**HTTP status: 200 healthy, 503 when any piece of work is overdue.** 503 is what an off-the-shelf uptime monitor already treats as down, which is the entire point of signalling by status rather than in prose.

**Database unreachable: 503 with `{"status": "unhealthy", "work": []}`.** Indistinguishable to a monitor from overdue work — which is correct, since both mean the deployment cannot demonstrate that its scheduled work is happening — while the empty array tells a human which of the two they are looking at. Only successful reads enter the cache, and the anchor upsert runs on every request including a cache hit — those two together, not the cache rule alone, are what stop a cached healthy answer from outliving the state it was computed from. Precisely: the upsert catches any fault that also prevents a write, which is every failure mode named here — connection loss, timeout expiry, an absent or malformed setting. A fault that disables reads alone is caught at the next cache miss instead, so it is masked for at most one cache window.

**Unreachable is bounded in time, not just in outcome.** The anchor upsert and the read are given a short timeout, and expiry *is* the unreachable case. Without one, a database that accepts connections and never answers produces a hanging request rather than a prompt 503 — on the one endpoint whose entire purpose is to be polled by something that will conclude nothing from a request that never returns.

### Unauthenticated, with the `/health` analogy stated at its actual strength

It exposes the names of scheduled work, when each last succeeded, and whether each is within tolerance. No product data, no counts, no configuration.

Unauthenticated by decision, not omission: an authenticated endpoint needs a credential delivered to whatever polls it, and the prerequisite removes a shared-secret mechanism precisely because a static bearer token on a public endpoint is a liability with no rotation story. Reintroducing one to protect the fact that a digest ran at 06:00 is a poor trade.

**Where the `/health` analogy stops:** `health-check`'s spec requires that endpoint to touch nothing external, while this one queries Postgres on every anonymous request from the open internet. The precedent covers *exposure*, not *I/O*. The response is therefore cached briefly — a few seconds is ample, since the underlying state changes hourly at most. Stated at its actual strength: the cache bounds the *read and evaluation*, not the whole request, because the anchor upsert is deliberately exempt from it (see "First-known is its own table"). That exemption is **not** an optimisation waiting to be removed: the per-request upsert is the only database access a cache-hit request still makes, and so it is the mechanism by which such a request discovers that the recorded state has become unreadable. Memoising it away would leave a cache hit doing no I/O at all, and the endpoint would serve its last healthy answer through the first seconds of an outage. The cost is one bounded idempotent write per anonymous request — the cost already accepted under "First-known is its own table", not a new one.

Accepted trade, in two parts. An outsider can learn that this deployment runs scheduled work and whether it is currently healthy. And every anonymous request costs one upsert per registered piece of work, cache hit or not — in-process memoisation is deliberately unavailable as a mitigation, for the reason just given, so the write rate follows the request rate. If that ever needs a bound, it belongs at the edge as rate limiting, not in the handler; nothing here tasks one. If the set of scheduled work ever includes names that are themselves sensitive, this decision needs revisiting.

## Risks / Trade-offs

- **The overdue check shares the fate of what it watches.** → Stated as context in the requirement rather than pretended away. The freshness endpoint is the mitigation and runs in a different process; the worker-liveness enrolment is what makes it prompt.
- **The mitigation is incomplete until an external checker exists.** → The honest position: this change makes the dead-worker case *detectable*, not *detected*. Recorded as an open item.
- **A Slack outage means the report does not arrive**, and the reporter has no reporter. → Bounded by the deliver-then-record ordering: the next check retries rather than going silent. The freshness endpoint does not depend on Slack at all.
- **`main.py` could fail to call `register_all()`**, leaving the endpoint enumerating nothing and reporting healthy while the worker is fine. → A test runs each composition root in a **fresh interpreter** and compares serialized registry contents. An in-process comparison cannot catch this, since both roots read the same module-global — see the registry decision.
- **`register_all()` pulls the job modules into `main.py`'s import graph**, so any configuration read at import in that graph would break `runtime-configuration`'s empty-environment guarantee and the fresh-interpreter guard that enforces it. → A task requires `register_all()` and everything it imports to read no configuration at import; the existing guard verifies it.
- **Suppression could mask a genuinely new problem** — overdue, reported, then failing for a different reason with no second message. → Accepted: the message says the work is not succeeding, which stays true. Per-cause reporting is a change with its own design.

## Migration Plan

1. Land `replace-cron-with-job-runner`, including its last-success accessor.
2. Add the schedule/tolerance registry in `shared` and the single registration helper; convert the prerequisite's job definitions to register through it, taking the schedule once.
3. Add `registrations.py` with the one import list and `register_all()`; call it from `worker.py` (replacing that change's own import list) and from `main.py`.
4. Add the `MonitoringNotifier` port; confirm `products`' notifier module satisfies it structurally.
5. Add **both** tables and their migrations — suppression, and `known_work` for the anchor — and verify `upgrade`/`downgrade` for each.
6. Add the overdue-check job, scheduled hourly, registered through the helper, with the notifier injected at `worker.py` after `register_all()`; enrol its own liveness as monitored work.
7. Add the freshness route, register its router in `main.py`, and have its handler upsert the anchor before evaluating.
8. Deploy, then verify: stop the `worker` container, confirm the endpoint reports unhealthy within the worker's own tolerance rather than the digest's, restart it, confirm it returns to healthy.

**Rollback**: revert and redeploy. The suppression and `known_work` tables remain until `alembic downgrade` is run, harmlessly. Nothing yet polls the endpoint, so no external contract breaks.

## Open Questions

- **Which external uptime checker polls the endpoint, and from where?** Belongs to `/infrastructure`; the endpoint's contract does not depend on the answer.
- **The hourly check interval, the worker-liveness tolerance and the digest's 30-hour tolerance are initial figures.** All are constants, none changes the specs or the task breakdown, and all are better chosen after a few weeks of real run history.
