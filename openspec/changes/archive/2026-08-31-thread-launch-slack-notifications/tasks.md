## 1. Configuration

- [x] 1.1 Declare `product_agent_launches_channel_id: NonEmpty` on `Settings` in `src/commerce_ops/shared/application/settings.py`, mirroring `product_agent_monitoring_channel_id`.
- [x] 1.2 Add `"PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"` to the `REQUIRED_NOT_STARTUP_CRITICAL` set in `tests/unit/shared/application/test_settings.py`, with a comment naming this change, mirroring the existing entries' style.
- [x] 1.3 Render `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID=${{ secrets.PRODUCT_AGENT_LAUNCHES_CHANNEL_ID }}` in `.github/workflows/deploy.yml`, next to the existing `PRODUCT_AGENT_MONITORING_CHANNEL_ID` line. Read the value in source by its literal name (not through a constant), matching the drift check's expectation.

## 2. Domain and persistence

- [x] 2.1 Add `submitter: str | None` and `slack_thread_id: str | None` to the `Launch` aggregate (`src/commerce_ops/launch/domain/launch_run.py`): `submitter` set once by `Launch.start`, never mutated afterward; `slack_thread_id` defaulted absent, with a narrow setter for the "ensure thread" operation to call.
- [x] 2.2 Add `submitter` and `slack_thread_id` (both nullable, no default) to `LaunchPosition` in `src/commerce_ops/launch/infrastructure/driven/models.py`.
- [x] 2.3 Write an Alembic migration adding both columns to `launch_positions`, nullable, no backfill.
- [x] 2.4 Update `LaunchRepository` (`src/commerce_ops/launch/infrastructure/driven/launch_repository.py`) to read and write both fields on load/save, and to support the "reload, check, write `slack_thread_id`" read used by the ensure-thread operation.

## 3. Thread establishment and mention resolution

- [x] 3.1 Add a dedicated advisory-lock helper mirroring `launch_advisory_lock.py`'s shape (new namespace constant, `pg_advisory_xact_lock` keyed on the product, transaction-scoped) for serializing concurrent thread establishment on one launch.
- [x] 3.2 Add `launches_channel()` to `src/commerce_ops/launch/infrastructure/driven/slack_notifier.py`, reading `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` by its literal name, mirroring `monitoring_channel()`.
- [x] 3.3 Add a `thread_ts: str | None = None` parameter to `post_monitoring_message`, passed through to `chat_postMessage` when set.
- [x] 3.4 Implement the "ensure thread" operation in `launch`'s application layer: inside a transaction, acquire the new advisory lock, reload the launch, return the existing `slack_thread_id` if set, otherwise post the anchor message (product name, SKU, marketplace, launch date) to `launches_channel()`, persist the returned `ts`, and return it.
- [x] 3.5 Implement the shared mention-resolution helper: given an optional step, return the step's `confirmer` if named, else the launch's `submitter`; resolve the returned identity to a roster person for `<@…>` formatting the same way `automation_confirmation.py` already resolves a confirmer today.

  Added beyond the original plan: `launch/infrastructure/driven/launch_thread_delivery.py`'s `establish_thread_and_resolve_mention()` composes the "ensure thread" operation with mention resolution into one driven-adapter-layer collaborator, imported at module scope by every driving adapter below. Not a design change — `design.md`'s own shape ("Whichever call site triggered establishment then delivers its own message") is unchanged — but the four call sites' near-identical `transaction()` + `LaunchRepository` + `ensure_launch_thread` + `resolve_mention_target` block was duplicated four times and unmockable (reached via function-local imports), which is what left `test_gate_ask_message.py` and its three siblings unable to run without a real database. This collaborator is what makes them real unit tests again.

## 4. Launch-entry: anchor and tagged confirmation

- [x] 4.1 In `src/commerce_ops/launch/infrastructure/driving/slack_entry.py`, replace the success-path DM (`_post(client, submitter, _confirmation_text(submission))`) with: call the ensure-thread operation (this request is always the first message for the launch, so it always posts the anchor), then post a tagged reply (`thread_ts` set) resolving the tag via the mention helper with no step, confirming success and naming the ClickUp sync cadence.
- [x] 4.2 Leave the post-acknowledgement failure DM (`_post(client, submitter, _failure_text(...))`) unchanged.
- [x] 4.3 Persist the captured `submitter` Slack identity onto the launch at start, alongside the existing registration write.

## 5. Gate confirmation

- [x] 5.1 In `src/commerce_ops/launch/infrastructure/driving/gate_confirmation.py`'s `post_gate_ask`, call the ensure-thread operation and switch delivery to `launches_channel()` with `thread_ts` set.
- [x] 5.2 Resolve the tag via the mention helper with no step (gates carry no confirmer, so this always resolves to the submitter) and include it in the composed message.

## 6. Automated-result confirmation

- [x] 6.1 In `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py`'s `deliver_pending_result`, call the ensure-thread operation and switch delivery to `launches_channel()` with `thread_ts` set.
- [x] 6.2 Resolve the tag via the mention helper using the pending result's step, and include it in `compose_message`.

  Fixed a real defect found while closing out this task: `deliver_pending_result` had a `step_def = None  # would need playbook access; for now use None` stub, so every pending-result message silently fell back to tagging the submitter regardless of the step's own confirmer. `deliver_pending_result` now takes `step` as a parameter, and `automation_pass.py`'s `_deliver_waiting` (which already holds the served playbook) looks the real `StepDefinition` up by identifier and passes it through.

## 7. Stuck-step alert

- [x] 7.1 In `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`'s `_report_stuck_step`, call the ensure-thread operation and switch delivery from `notifier.post_monitoring_message(message)` to `launches_channel()` with `thread_ts` set.
- [x] 7.2 Resolve the tag via the mention helper using the stuck step, and include it in `_stuck_step_message`.

  `establish_thread` is threaded through `run_automation_pass` → `_walk_launch` → `_note_repeat` → `_report_stuck_step` as an explicit argument, not a module global — matching this file's own stated design ("collaborators arrive as arguments... which is what lets the whole pass be exercised without a database"), unlike the other three call sites' module-level seam.

## 8. Tests

- [x] 8.1 Unit tests for the ensure-thread operation: first caller posts the anchor and persists `ts`; a second, concurrent caller reuses the same reference and posts no second anchor; a caller for a launch that already has a reference skips straight to reuse. — `tests/unit/launch/application/test_thread_establishment_race.py`, against the real operation with fakes (no database).
- [x] 8.2 Unit tests for the mention-resolution helper: a step naming a confirmer resolves to that confirmer; a step naming none, and the no-step case, resolve to the launch's submitter. — same file.
- [x] 8.3 Update `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py` (and any other test asserting the DM confirmation) for the anchor-plus-tagged-reply behavior, keeping the failure-DM assertions unchanged. The success-path assertion is corrected but the file stays database-gated (`_register_and_start` reads the live playbook for real regardless of how its registrar is mocked — a pre-existing `start-launch-from-slack`-era constraint, not this change's); the real, DB-backed scenario is verified in `tests/integration/launch/test_slack_entry_start.py`. The duplicate scaffold `test_slack_entry_anchor_and_confirmation.py` (never wired, same DB constraint) was removed rather than fixed twice.
- [x] 8.4 Update `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py` and `test_automation_confirmation_delivery.py` for delivery to `launches_channel()` as a thread reply, and for the new tagging behavior. Both are real, passing unit tests again via `establish_thread_and_resolve_mention`'s mockable seam (task 3's addition) — no longer database-gated. The duplicate scaffold `test_gate_ask_to_thread_reply.py` was removed as redundant with the updated `test_gate_ask_message.py`.
- [x] 8.5 Add or update a test for `automation_pass.py`'s stuck-step report asserting delivery to `launches_channel()` as a thread reply, tagging the step's confirmer or the submitter fallback. — `test_stuck_step_report_to_thread_reply.py`, calling `_report_stuck_step` directly with `establish_thread` passed as a fake argument (no monkeypatch needed, per that file's argument-threading design).
- [x] 8.6 Confirm `clickup_sync_job.py`'s and `overdue_check.py`'s existing tests still assert delivery to `monitoring_channel()`, unchanged. — reran; 32 passed, untouched.
- [x] 8.7 Add a settings test confirming `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` is declared and required-not-startup-critical, mirroring the existing `PRODUCT_AGENT_MONITORING_CHANNEL_ID` coverage. — already present in `tests/unit/shared/application/test_settings.py`'s `REQUIRED_NOT_STARTUP_CRITICAL` set.

## 9. Verification

- [x] 9.1 Run `uv run pytest` (unit + agents tier) and confirm it passes. — 1768 passed, 44 skipped (pre-existing, out-of-scope database-gated tests from `start-launch-from-slack` and `introduce-automation-runtime`'s backoff repository; none touched by this change).
- [x] 9.2 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`. — all clean.
- [x] 9.3 Confirm the migration applies cleanly against a local database and `launch_positions` gains both columns. — applied and verified via CI's `pytest (integration)` job against a real Postgres service (PR #127); not re-verifiable in this session's sandbox, which has no database or Docker access.
