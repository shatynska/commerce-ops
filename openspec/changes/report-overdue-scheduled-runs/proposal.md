## Why

`replace-cron-with-job-runner` gives scheduled work retries and a run history, but nothing reads that history. The failure it leaves open is the one the project was founded on avoiding.

`docs/reference/start-here.md` states the principle: *"a process that depends on someone remembering will eventually be missed, and nobody will notice it was missed."* After the scheduler change, the deployment can be half-up — `app` serving HTTP and looking perfectly healthy, `worker` absent or crash-looping — and nothing scheduled runs. Nobody finds out until someone notices the daily digest stopped arriving, which is exactly the "depends on someone remembering" failure mode, applied to the system itself.

Two distinct problems sit behind that, and they need different answers:

- **The job is failing while the worker is alive.** This is the common case, and something inside the deployment can detect it by reading the run history.
- **The worker is gone.** Nothing inside the deployment can detect this, because the thing that would detect it is the thing that is gone. A dead-man's switch hosted by the process it watches is not a dead-man's switch.

## What Changes

- **An overdue check runs on its own schedule**, reads the run history, and posts to the team's Slack channel when a piece of recurring work has not succeeded within a tolerance declared for it — naming the work and when it last succeeded.
- **A continuing outage is reported once, not on every check.** Suppression state is persisted, so a week-long outage produces one message rather than a wall of identical ones that trains the team to ignore the channel — and so a worker restart does not resume the flood.
- **Run freshness is exposed over HTTP**, served by `app` and read from the database, so a checker **outside** the deployment can determine whether scheduled work is still happening without asking the worker anything. This is what makes the dead-worker case detectable at all.
- **The limit is stated rather than papered over.** The in-deployment check detects a failing job, not an absent worker; the specification says so, and says which requirement covers the other case.
- **The external checker does not exist yet**, in this repository or in `/infrastructure`. Building it is out of scope; this change is what turns it into a configuration task rather than a development one.

## Capabilities

### Modified Capabilities
- `scheduled-jobs`: gains overdue detection and reporting, suppression of repeated reports for a continuing outage, and an HTTP surface reporting run freshness for an external checker. The capability's existing requirements — schedules, retries, missed windows, run history — are unchanged; these are added concerns, not altered behavior.

## Impact

- **Depends on `replace-cron-with-job-runner`**, which must land first: this change reads the run history that one creates, and the tolerance it enforces is meaningless before there are scheduled runs.
- **New**: an overdue-check job, a schedule/tolerance registry with a single registration helper, a `registrations.py` composition module, **two** tables with their own Alembic migrations — a suppression record, and a separate `known_work` record holding each work's first-known time — a notifier port in `shared/application/ports.py`, and a freshness route on `app` at `/health/scheduled-runs`. The two tables are separate because their lifecycles are incompatible: suppression is written after a delivered report and cleared on success, while the anchor must exist before any report and persist across successes. The last-success accessor is **not** new here — `replace-cron-with-job-runner` builds it, and this change consumes it.
- **The worker's own liveness becomes monitored work.** Without it the freshness endpoint's dead-worker latency is bounded below by the shortest tolerance it watches — 30 hours for the daily digest — which is roughly when someone would notice the digest missing anyway. The check already runs hourly and already records each run; enrolling those records turns the endpoint into a genuine dead-man's switch.
- **Two module-boundary problems this change has to solve**, both created by `.importlinter`'s `shared-boundary` contract forbidding `commerce_ops.shared` from importing `commerce_ops.products` at all:
  - *The notifier.* The cross-cutting check must post to the `product_agent` monitoring channel, whose only adapter lives in `products`. Resolved by a `Protocol` port in `shared.application`, satisfied structurally by `products`' notifier module and injected by `worker.py`, which sits outside the layered contracts. This borrows the *device* from `ClickUpTaskWriter` but not its precedent: that port exists for a different contract, in the opposite direction, and has no caller anywhere in `src/`, so its composition-root wiring has never actually been written. This is the first.
  - *The tolerances.* The prerequisite declares each job's schedule in `products/infrastructure/driving/`, and the tolerance belongs beside it. But the check in `shared` and the endpoint on `app` both need it. Resolved by a `shared`-owned registry that job modules register into at import — so `shared` reads its own registry and imports nothing.
- **A schema addition**: the suppression state is a table with its own migration. The run history itself is the runner's, and is not duplicated.
- **A new externally reachable endpoint** on a service the proposal for the previous change showed is internet-facing. design.md records what it discloses and why it is unauthenticated, alongside the `/health` precedent.
- **Run-history retention becomes relevant.** The last-success query reads the runner's history, so any future pruning must preserve last-success evidence. Named here, not solved here.
