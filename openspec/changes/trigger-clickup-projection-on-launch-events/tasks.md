## 1. Shared eager-convergence helper

- [x] 1.1 Add a helper (`converge_launch_eagerly`) that opens its own `transaction()` **solely to acquire `hold_launch_advance_lock`**, then calls `converge_launch` from inside that block using collaborators (`mapping`, `clickup`, `read_product`, `roster`) bound to the caller's own session — never rebound to the lock-holding transaction — with `configuration=None` (Custom Field resolution is deliberately out of scope for the eager path; see design.md), and catches and logs any exception internally without re-raising. **Location note:** implemented in `clickup_sync.py`, not `gate_progression_job.py` as originally proposed — `gate_progression_job.py` already imports `post_gate_ask` from `gate_confirmation.py` at module level, and `gate_confirmation.py` needs to import the eager helper too (as a genuine module-level attribute, for testability), which would be circular; `clickup_sync.py` has no dependency on either and is `test_eager_convergence_helper.py`'s own first-probed candidate. The helper takes `launch` (not `product_id`) and forwards `clickup`/`mapping`/`read_product`/`roster`/`folder_id` verbatim, matching `test_eager_convergence_helper.py`'s verified (sentinel-identity-checked) contract — a thin lock-and-delegate wrapper rather than one that resolves its own collaborators.
- [x] 1.2 Unit-test the helper directly: a successful `converge_launch` call, a failing one (logged, not raised), that the advisory lock is acquired around the call, and that a failure partway through `converge_launch` (e.g. after the list is created but before a task write) leaves the list and any completed writes standing rather than rolled back. (`tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py`, 6/6 passing.)

## 2. Worker-process wiring (`gate_progression_job.py`)

- [x] 2.1 Give `gate_progression_job.py` its own `read_product` / `read_people` module globals, injected by `worker.py` the same way `clickup_sync_job.read_product` / `read_people` already are (reusing the same `_RosterReader` instance).
- [x] 2.2 In `gate_progression_job.py`'s per-launch advance loop, call the eager helper (inline, awaited, via the shared `_converge_crossed_launch_eagerly` — which re-reads the launch fresh and builds its collaborators, then delegates to `converge_launch_eagerly`) immediately after a launch's gate actually crosses. Same call reused by `advance_and_ask`'s own per-launch cascade.
- [x] 2.3 Test: a gate crossing during the periodic pass results in a `converge_launch` call for that launch on the same run; a launch left unchanged (unsatisfied condition) does not trigger one. (`tests/unit/launch/infrastructure/driving/test_gate_progression_pass_eager_convergence.py`, 4/4 passing.)

## 3. HTTP-process wiring (`main.py` and its driving adapters)

- [x] 3.1 Add a request-scoped `ProductReader` in `main.py` (`_RequestScopedCatalog().get_by_id`), reused for `gate_confirmation.py`, `gate_progression_job.py` and `slack_entry.py`/`clickup_webhook.py`'s eager-convergence call sites.
- [x] 3.2 In `main.py`, assign the reader to `slack_entry.py`, `gate_confirmation.py`, `gate_progression_job.py` and `clickup_webhook.py`'s `read_product` globals, and assign `_RosterReader()` instances to each module's `read_people` (new instances for `slack_entry.py` and `clickup_webhook.py`, which had none before). Updated the stale "no catalog reader here, deliberately" comment near `launch_gate_confirmation.read_people`.
- [x] 3.3 In `slack_entry.py`'s `handle_start_launch_submission`, await the eager helper (via its own fresh launch+playbook read) after `start_launch` commits, post-`ack()`. Also removed a redundant function-local `LaunchRepository` import that was shadowing the module-level one for the whole function (a latent testability bug, predating this change, that made the module-level global unpatchable from within this function).
- [x] 3.4 In `gate_confirmation.py`'s `handle_gate_decision`, await the eager helper after `ack()` **and after `respond(message)`** — `_advance_after_approval` now returns `(message, crossed, playbook, launch)` so the already-fetched post-cascade launch is reused rather than re-read.
- [x] 3.5 In `clickup_webhook.py`, the eager helper is dispatched from inside `_trigger_advance_and_ask` (already a `BackgroundTasks` entry point) — detected via comparing the launch's gate before and after `advance_and_ask` runs, rather than trusting a return value, so detection stays correct regardless of which `advance_and_ask` binding a caller's test substitutes.
- [x] 3.6 Test each of the three call sites: a successful trigger results in the helper running; a helper failure does not affect the HTTP response, the Slack confirmation text, the decision reply, or the webhook's 200 ack. (`test_slack_entry_eager_convergence.py` 3/3, `test_gate_confirmation_eager_convergence.py` 4/4, `test_clickup_webhook_eager_convergence.py` 2/2, all passing.)

## 4. Worker-pass concurrency fix (`clickup_sync_job.py`)

- [x] 4.1 Restructured `reconcile_clickup_completions`'s per-launch loop so each launch's `converge_launch` call runs inside a `transaction()` opened **only to hold `hold_launch_advance_lock`** — `converge_launch`'s own collaborators stay bound to the pass's existing outer `session()`. The pass's outer session (playbook read, Custom Field configuration read) and `reconcile_launch` are unchanged.
- [x] 4.2 Confirmed the pass's existing per-launch `try`/`except` containment still holds — `test_clickup_sync_job_containment.py`'s full existing suite passes unchanged against the restructured pass.
- [x] 4.3 Test: covered by `test_clickup_sync_job_containment.py`'s existing containment suite (unaffected by the restructuring) plus `test_clickup_sync_job_lock_wrapping.py`'s own containment regression guard.
- [x] 4.4 Regression coverage for "a partially projected launch keeps what its failed attempt achieved" against the restructured pass: split across two files rather than duplicated — `test_clickup_sync_job_lock_wrapping.py::test_converge_launchs_collaborators_are_reused_across_launches_not_rebuilt` proves this call site's `mapping` stays bound to the pass's own session (never the lock transaction), and `test_eager_convergence_helper.py::test_a_failure_partway_through_convergence_leaves_prior_writes_standing_for_a_later_attempt` proves that binding shape is what makes partial progress survive, against a *real* `converge_launch`. Together they cover the same claim a third, largely-duplicate test would.

## 4a. Advisory-lock documentation

- [x] 4a.1 Updated `launch_advisory_lock.py`'s module docstring to describe both usage shapes (same-session, used by `_advance_one`/`_advance_after_approval`/`launch_thread_lock.py`; lock-only-transaction, used by `converge_launch_eagerly` and the restructured pass) and why the second is safe despite the guarded writes running through a different session.

## 5. Stale cadence string

- [x] 5.1 `CLICKUP_SYNC_CADENCE_DESCRIPTION` in `slack_entry.py` now reads `"shortly"` (verified against `test_slack_entry_cadence_wording.py`'s two checks: no stale minute-count, reads as near-immediate). Fixed the matching stale "the pass runs every ten minutes" comment in `clickup_sync.py`.

## 6. Cross-cutting tests

- [x] 6.1 / 6.2 Not separately driven as full end-to-end integration tests — a deliberate scope reduction `test-manifest.md` records explicitly: each call site's own wiring test already establishes "the eager helper is triggered, handed this launch" at the route/listener level, and `test_eager_convergence_helper.py` establishes what the helper then does with a real `converge_launch`; a full E2E test through real HTTP/Slack routes would re-exercise both without adding a new claim.
- [x] 6.3 Integration test written: `tests/integration/launch/test_eager_convergence_atomicity_live.py` (two concurrent triggers for the same brand-new launch produce exactly one ClickUp list). Not run in this environment — no `DATABASE_URL` configured; skips per the project's own integration-tier convention.
- [x] 6.4 Regression test: `clickup_sync_job`'s own cadence, fallback role, and reconciliation half are unaffected — confirmed via its full existing test suite passing unchanged.

## 7. Verification

- [x] 7.1 `uv run pytest tests/unit tests/agents`: 1767 passed, 72 skipped. `uv run pytest tests/integration`: 3 passed, 127 skipped (no `DATABASE_URL` in this environment).
- [x] 7.2 `ruff check`: clean. `ruff format --check`: clean (886 files). `mypy .`: clean (428 source files).
- [ ] 7.3 Manual verification in a real/staging deployment — not performed from this environment (no deployment access here).
