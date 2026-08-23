# add-clickup-completion-loop — Tasks

## 1. Shared ClickUp client extensions

- [x] 1.1 Add a read-side value object to `shared/domain/clickup.py` (task identifier, status name, closed-type flag, due date or `None`) alongside `ClickUpTask`, and a list-creation result carrying the new list's identifier
- [x] 1.2 Add `create_list(folder_id, name)` to `shared/infrastructure/driven/clickup_client.py`, returning the created list's identifier, errors propagating uncaught as the existing operations do
- [x] 1.3 Add `list_tasks(list_id)` to the client: includes closed tasks (`include_closed`), follows ClickUp's pagination until exhausted, maps each task to the read-side value object with the closed judgement taken from the status `type` field and the due date parsed from ClickUp's epoch-millisecond field (`None` when unset)
- [x] 1.4 Extend `shared/application/ports.py`'s ClickUp port(s) so `launch` infrastructure consumes the new operations through the same seam existing callers use

## 2. Configuration

- [x] 2.1 Declare `clickup_launch_folder_id` and `clickup_webhook_secret` as optional (`NonEmpty | None = None`) fields in `Settings`, with comments tying their optionality to the capability degrading rather than the app

## 3. Mapping persistence

- [x] 3.1 Add `launch_clickup_lists` (product_id → list_id) and `launch_clickup_tasks` (product_id + step_id → task_id, unique both ways, plus a last-observed-closed column updated by every observation) to `launch/infrastructure/driven/models.py`
- [x] 3.2 Write the Alembic migration for the two tables (upgrade and downgrade)
- [x] 3.3 Add `list_active()` to `LaunchRepository` — every launch whose current gate is short of `graduated`, hydrated as full aggregates

## 4. Sync core

- [x] 4.1 Create `launch/infrastructure/driven/clickup_sync.py`: the shared transition-based translation — observed closed state vs the mapping row's last-observed state; not-closed → closed yields `Satisfied`, closed → open yields `InProgress`, no transition yields nothing — with the observation always persisted to the mapping row, never compared against the step's recorded outcome
- [x] 4.2 Implement due-date resolution: step's `AnchorPeriod` end from the launch date, `None` when no launch date or when the anchor is open-ended or recurring
- [x] 4.3 Implement the convergence pass for one launch: ensure list exists (create + record association, named from the catalog product's name and SKU via `catalog.application.get_product_by_id`), ensure a task per human-attested non-prohibited step (create + record mapping, skipping existing; re-projecting a mapped task absent from the list read unless the step's recorded outcome is terminal), correct drifted or stale due dates by comparing the read-back due date and updating only differing tasks
- [x] 4.4 Implement pull-side reconciliation for one launch: read the list's tasks, run each mapped task through the shared transition translation, record resulting outcomes through `record_step_outcome` with source `clickup` and the `clickup-reconciliation` recorder

## 5. Webhook intake

- [x] 5.1 Create `launch/infrastructure/driving/clickup_webhook.py`: FastAPI route verifying HMAC-SHA256 of the raw body against `clickup_webhook_secret` (constant-time compare, reject on missing/invalid/unconfigured before any payload-dependent behavior)
- [x] 5.2 Handle `taskStatusUpdated` deliveries: resolve the task through the mapping (acknowledge and ignore unmapped tasks, tasks mapped to graduated launches, and other event types), run it through the shared transition translation — updating the mapping row's last-observed state — and record through `record_step_outcome` with the acting ClickUp user as recorder
- [x] 5.3 Mount the webhook router in `main.py`

## 6. Reconciliation job

- [x] 6.1 Create `launch/infrastructure/driving/clickup_sync_job.py`: `register_scheduled` job (every 30 minutes, tolerance per `scheduled-jobs` conventions) running the convergence pass then pull-side reconciliation over `list_active()`, skipping graduated launches by construction and failing the run when the folder id is unconfigured while work exists
- [x] 6.2 Add the job module to `registrations.py`'s `JOB_MODULES` one list

## 7. Verification

- [x] 7.1 Run the change's derived test manifest (unit + agents tiers) and the integration tier for the new migration/repository paths
- [x] 7.2 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and the import-linter contract; confirm `alembic upgrade head` and `downgrade` round-trip on a scratch database
- [x] 7.3 Update `docs/domain-map.md`: mark slice 4 realized and reflect any detail this change settled
