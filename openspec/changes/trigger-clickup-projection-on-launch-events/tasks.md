## 1. Shared eager-convergence helper

- [ ] 1.1 Add a helper (e.g. `converge_launch_eagerly` or similar, colocated with `converge_launch` in `clickup_sync.py`, or as a thin driving-adapter function next to `advance_and_ask` in `gate_progression_job.py`) that opens its own `transaction()` **solely to acquire `hold_launch_advance_lock`**, then calls `converge_launch` from inside that block using collaborators (`mapping`, `clickup`, `read_product`, `roster`) bound to the caller's own session — never rebound to the lock-holding transaction — and catches and logs any exception internally without re-raising. Do **not** mirror `gate_progression_job.py`'s `_advance_one`, which rebinds its repository to the new transaction on purpose (see design.md, "The lock acquisition and `converge_launch`'s own writes deliberately do not share a transaction"); rebinding `mapping` here would make a mid-launch failure roll back writes that `launch-clickup-sync` requires to survive.
- [ ] 1.2 Unit-test the helper directly: a successful `converge_launch` call, a failing one (logged, not raised), that the advisory lock is acquired around the call, and that a failure partway through `converge_launch` (e.g. after the list is created but before a task write) leaves the list and any completed writes standing rather than rolled back.

## 2. Worker-process wiring (`gate_progression_job.py`)

- [ ] 2.1 Give `gate_progression_job.py` its own `read_product` / `read_people` module globals, injected by `worker.py` the same way `clickup_sync_job.read_product` / `read_people` already are (reusing the same reader instances).
- [ ] 2.2 In `gate_progression_job.py`'s per-launch advance loop, call the eager helper (inline, awaited) immediately after a launch's gate actually crosses.
- [ ] 2.3 Test: a gate crossing during the periodic pass results in a `converge_launch` call for that launch on the same run; a launch left unchanged (unsatisfied condition) does not trigger one.

## 3. HTTP-process wiring (`main.py` and its driving adapters)

- [ ] 3.1 Add a request-scoped `ProductReader` in `main.py`, mirroring `_RequestScopedCatalog`'s existing pattern, for use by the eager-convergence call sites.
- [ ] 3.2 In `main.py`, assign the new `ProductReader` to `slack_entry.py`, `gate_confirmation.py`, and `clickup_webhook.py`'s reader globals, and assign a **new** `_RosterReader()` instance to `launch_slack_entry.read_people` and `launch_clickup_webhook.read_people` (only `gate_confirmation.py` and `automation_confirmation.py` currently have one wired — these two do not exist yet). Update the comment near `launch_gate_confirmation.read_people = _RosterReader()` that currently states no catalog reader is needed there.
- [ ] 3.3 In `slack_entry.py`'s `handle_start_launch_submission`, await the eager helper directly after `start_launch` commits, following `ack()` — the same post-ack continuation pattern `gate_confirmation.py` already uses for `post_gate_ask` (Bolt listeners have no `BackgroundTasks`; `process_before_response` stays `False`, so Slack has already been acknowledged by the time this runs).
- [ ] 3.4 In `gate_confirmation.py`'s `handle_gate_decision`, await the eager helper directly, after `ack()` **and after `respond(message)` has sent the decider their reply**, once a decision's `progress_launch` call actually crosses a gate — same pattern as 3.3, ordered so the decider's reply is never held up by ClickUp latency.
- [ ] 3.5 In `clickup_webhook.py`, dispatch the eager helper via `BackgroundTasks` (this route is genuine FastAPI, unlike 3.3/3.4) alongside — or from within — `advance_and_ask`, after a gate crossing.
- [ ] 3.6 Test each of the three call sites: a successful trigger results in the helper running (backgrounded for the webhook, awaited post-ack for the two Bolt listeners); a helper failure does not affect the HTTP response, the Slack confirmation text, the decision reply, or the webhook's 200 ack.

## 4. Worker-pass concurrency fix (`clickup_sync_job.py`)

- [ ] 4.1 Restructure `reconcile_clickup_completions`'s per-launch loop so each launch's `converge_launch` call runs inside a `transaction()` opened **only to hold `hold_launch_advance_lock`** — `converge_launch`'s own collaborators (`mapping`, `clickup`, `read_product`, `roster`) stay bound to the pass's existing outer `session()`, exactly as today; do not rebind them to the lock transaction (see design.md and task 1.1 — this is *not* `_advance_one`'s shape). Leave the pass's outer `session()` (playbook read, Custom Field configuration read) and the `reconcile_launch` call for each launch unchanged.
- [ ] 4.2 Confirm the pass's existing per-launch `try`/`except` containment (a launch whose projection raises is not reconciled on that run) still holds with the lock acquisition now wrapping `converge_launch`.
- [ ] 4.3 Test: `converge_launch` failing inside the pass still skips that launch's `reconcile_launch` call on the same run, and does not affect any other launch in the same walk.
- [ ] 4.4 Test (regression against `launch-clickup-sync`'s existing "A partially projected launch keeps what its failed attempt achieved" scenario): a launch's list and some of its tasks are created, then `converge_launch` raises before finishing — the list and the task associations recorded before the failure survive it in the restructured pass, exactly as before this change, and the next run's projection continues from them rather than restarting.

## 4a. Advisory-lock documentation

- [ ] 4a.1 Update `launch_advisory_lock.py`'s module docstring: it currently states the lock is "taken inside `transaction()` it is held for the whole cascade" as the pattern's whole point, describing only the same-session shape `_advance_one`, `_advance_after_approval`, and `launch_thread_lock.py`'s callers all use. Add a description of this change's lock-only-transaction shape (task 1.1, 4.1) and why it is safe despite the guarded writes running through a different session — so a future reader is not misled into rebinding those writes to the lock's session and silently reintroducing the rollback risk task 4.4 regression-tests against.

## 5. Stale cadence string

- [ ] 5.1 Update `CLICKUP_SYNC_CADENCE_DESCRIPTION` in `slack_entry.py` to describe the new near-immediate behavior, and fix the matching stale "the pass runs every ten minutes" comment in `clickup_sync.py:700`.

## 6. Cross-cutting tests

- [ ] 6.1 Integration test: starting a launch results in its first released steps' tasks existing in ClickUp without running `clickup_sync_job`'s pass.
- [ ] 6.2 Integration test: a gate crossing via each of the three paths (decision, periodic gate-progression pass, webhook-triggered `advance_and_ask`) results in the newly released steps' tasks existing without running `clickup_sync_job`'s pass.
- [ ] 6.3 Integration test: two concurrent triggers for the same brand-new launch (e.g. an eager call racing the periodic `clickup_sync_job` pass, now that both take `hold_launch_advance_lock` per task 4.1) produce exactly one ClickUp list, not two.
- [ ] 6.4 Regression test: `clickup_sync_job`'s own cadence, fallback role, and reconciliation half are unaffected — its existing test suite continues to pass, updated only where task 4.1's restructuring touches test setup.

## 7. Verification

- [ ] 7.1 Run `uv run pytest` (unit + agents + integration tiers) and confirm green.
- [ ] 7.2 Run `ruff check`, `ruff format --check`, and `mypy`.
- [ ] 7.3 Manually verify in a real/staging deployment: start a launch, confirm its ClickUp list and first tasks appear within seconds rather than waiting for the next `0 6,18 * * *` run.
