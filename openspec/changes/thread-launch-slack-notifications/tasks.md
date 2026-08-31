## 1. Configuration

- [ ] 1.1 Declare `product_agent_launches_channel_id: NonEmpty` on `Settings` in `src/commerce_ops/shared/application/settings.py`, mirroring `product_agent_monitoring_channel_id`.
- [ ] 1.2 Add `"PRODUCT_AGENT_LAUNCHES_CHANNEL_ID"` to the `REQUIRED_NOT_STARTUP_CRITICAL` set in `tests/unit/shared/application/test_settings.py`, with a comment naming this change, mirroring the existing entries' style.
- [ ] 1.3 Render `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID=${{ secrets.PRODUCT_AGENT_LAUNCHES_CHANNEL_ID }}` in `.github/workflows/deploy.yml`, next to the existing `PRODUCT_AGENT_MONITORING_CHANNEL_ID` line. Read the value in source by its literal name (not through a constant), matching the drift check's expectation.

## 2. Domain and persistence

- [ ] 2.1 Add `submitter: str | None` and `slack_thread_id: str | None` to the `Launch` aggregate (`src/commerce_ops/launch/domain/launch_run.py`): `submitter` set once by `Launch.start`, never mutated afterward; `slack_thread_id` defaulted absent, with a narrow setter for the "ensure thread" operation to call.
- [ ] 2.2 Add `submitter` and `slack_thread_id` (both nullable, no default) to `LaunchPosition` in `src/commerce_ops/launch/infrastructure/driven/models.py`.
- [ ] 2.3 Write an Alembic migration adding both columns to `launch_positions`, nullable, no backfill.
- [ ] 2.4 Update `LaunchRepository` (`src/commerce_ops/launch/infrastructure/driven/launch_repository.py`) to read and write both fields on load/save, and to support the "reload, check, write `slack_thread_id`" read used by the ensure-thread operation.

## 3. Thread establishment and mention resolution

- [ ] 3.1 Add a dedicated advisory-lock helper mirroring `launch_advisory_lock.py`'s shape (new namespace constant, `pg_advisory_xact_lock` keyed on the product, transaction-scoped) for serializing concurrent thread establishment on one launch.
- [ ] 3.2 Add `launches_channel()` to `src/commerce_ops/launch/infrastructure/driven/slack_notifier.py`, reading `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` by its literal name, mirroring `monitoring_channel()`.
- [ ] 3.3 Add a `thread_ts: str | None = None` parameter to `post_monitoring_message`, passed through to `chat_postMessage` when set.
- [ ] 3.4 Implement the "ensure thread" operation in `launch`'s application layer: inside a transaction, acquire the new advisory lock, reload the launch, return the existing `slack_thread_id` if set, otherwise post the anchor message (product name, SKU, marketplace, launch date) to `launches_channel()`, persist the returned `ts`, and return it.
- [ ] 3.5 Implement the shared mention-resolution helper: given an optional step, return the step's `confirmer` if named, else the launch's `submitter`; resolve the returned identity to a roster person for `<@…>` formatting the same way `automation_confirmation.py` already resolves a confirmer today.

## 4. Launch-entry: anchor and tagged confirmation

- [ ] 4.1 In `src/commerce_ops/launch/infrastructure/driving/slack_entry.py`, replace the success-path DM (`_post(client, submitter, _confirmation_text(submission))`) with: call the ensure-thread operation (this request is always the first message for the launch, so it always posts the anchor), then post a tagged reply (`thread_ts` set) resolving the tag via the mention helper with no step, confirming success and naming the ClickUp sync cadence.
- [ ] 4.2 Leave the post-acknowledgement failure DM (`_post(client, submitter, _failure_text(...))`) unchanged.
- [ ] 4.3 Persist the captured `submitter` Slack identity onto the launch at start, alongside the existing registration write.

## 5. Gate confirmation

- [ ] 5.1 In `src/commerce_ops/launch/infrastructure/driving/gate_confirmation.py`'s `post_gate_ask`, call the ensure-thread operation and switch delivery to `launches_channel()` with `thread_ts` set.
- [ ] 5.2 Resolve the tag via the mention helper with no step (gates carry no confirmer, so this always resolves to the submitter) and include it in the composed message.

## 6. Automated-result confirmation

- [ ] 6.1 In `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py`'s `deliver_pending_result`, call the ensure-thread operation and switch delivery to `launches_channel()` with `thread_ts` set.
- [ ] 6.2 Resolve the tag via the mention helper using the pending result's step, and include it in `compose_message`.

## 7. Stuck-step alert

- [ ] 7.1 In `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`'s `_report_stuck_step`, call the ensure-thread operation and switch delivery from `notifier.post_monitoring_message(message)` to `launches_channel()` with `thread_ts` set.
- [ ] 7.2 Resolve the tag via the mention helper using the stuck step, and include it in `_stuck_step_message`.

## 8. Tests

- [ ] 8.1 Unit tests for the ensure-thread operation: first caller posts the anchor and persists `ts`; a second, concurrent caller reuses the same reference and posts no second anchor; a caller for a launch that already has a reference skips straight to reuse.
- [ ] 8.2 Unit tests for the mention-resolution helper: a step naming a confirmer resolves to that confirmer; a step naming none, and the no-step case, resolve to the launch's submitter.
- [ ] 8.3 Update `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py` (and any other test asserting the DM confirmation) for the anchor-plus-tagged-reply behavior, keeping the failure-DM assertions unchanged.
- [ ] 8.4 Update `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py` and `test_automation_confirmation_delivery.py` for delivery to `launches_channel()` as a thread reply, and for the new tagging behavior.
- [ ] 8.5 Add or update a test for `automation_pass.py`'s stuck-step report asserting delivery to `launches_channel()` as a thread reply, tagging the step's confirmer or the submitter fallback.
- [ ] 8.6 Confirm `clickup_sync_job.py`'s and `overdue_check.py`'s existing tests still assert delivery to `monitoring_channel()`, unchanged.
- [ ] 8.7 Add a settings test confirming `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` is declared and required-not-startup-critical, mirroring the existing `PRODUCT_AGENT_MONITORING_CHANNEL_ID` coverage.

## 9. Verification

- [ ] 9.1 Run `uv run pytest` (unit + agents tier) and confirm it passes.
- [ ] 9.2 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`.
- [ ] 9.3 Confirm the migration applies cleanly against a local database and `launch_positions` gains both columns.
