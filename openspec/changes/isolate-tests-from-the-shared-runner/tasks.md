## 1. Baseline, before anything is changed

- [ ] 1.1 Record the stall rate on the current tree: run `tests/integration/shared/test_scheduled_runs_freshness_unreachable.py` followed by `tests/integration/shared/test_scheduled_run_history.py` with `-p no:randomly` under a 90s ceiling, at least 15 times, and record how many stalled. Without a baseline, a green run afterwards establishes nothing — the defect is intermittent.
- [ ] 1.2 Record the same for `test_scheduled_run_history.py` alone, so the "alone it passes" half is measured on this machine rather than inherited from `docs/deferred-work.md`.
- [ ] 1.3 List every row in the development database's `procrastinate_jobs` whose `task_name` is not `tests.%`, with task name, status and count, and save it. This is both the evidence for task 4.1 and the check that 4.1 deleted what it meant to.

## 2. Isolate the runner tests from the shared registry

- [ ] 2.1 In `tests/integration/shared/test_scheduled_run_history.py`, build the file's own `procrastinate.App` the way `job_runner.py` builds the shared one (`PsycopgConnector` over `_queue_pool`/`queue_conninfo`), and register `tests.run_history.*` on it instead of on `runner_app`.
- [ ] 2.2 Point `_drain()` and every `open_async()` in that file at the private App.
- [ ] 2.3 Keep `last_successful_run` reading through the application's own session provider — tasks.md 2.10a of `replace-cron-with-job-runner` requires it, and it is unaffected by which App defers the work.
- [ ] 2.4 Update the module docstring: it currently gives "so that what is exercised is this application's runner" as the reason for using `runner_app`. Record what is still exercised (the schema migration, the accessor) and what deliberately is not (the shared periodic registry), per design.md Decision 1.
- [ ] 2.5 Do the same for `tests/integration/shared/test_periodic_defer_dedup.py`, whose `_drain()` calls `runner_app.run_worker_async()` and carries the same exposure even though its own periodic registration is already file-owned.
- [ ] 2.6 Verify the isolation directly: assert in each file that the App it drives has an empty `periodic_registry`, so a future edit that reintroduces the coupling fails a test rather than reintroducing an intermittent hang.

## 3. Bound the drain

- [ ] 3.1 Wrap `run_worker_async` in `asyncio.wait_for` in both files, with a ceiling chosen against the baseline from 1.1/1.2 and an order of magnitude above it.
- [ ] 3.2 Give the ceiling a named constant and a comment saying what it is for — a wedge detector, not a latency budget — following `BOUNDED_SECONDS` in `test_scheduled_runs_freshness_unreachable.py`.
- [ ] 3.3 Confirm the bound actually fires: temporarily arm the registry (e.g. `register_all()` from a scratch plugin) and check that a stall now fails the test instead of hanging. Revert the temporary arming.

## 4. Clear what the defect wrote

- [ ] 4.1 Delete from the **development** database only (`.env` / `.env.test`), the `procrastinate_jobs` rows for `briefing.daily`, `launch.clickup.completion_pass`, `shared.scheduled_runs.overdue_check` and `products.monitoring.daily`, together with their `procrastinate_events` and `procrastinate_periodic_defers`. Confirm against the list from 1.3 first.
- [ ] 4.2 Do **not** touch the deployment's database. Its rows for those task names are genuine runs.
- [ ] 4.3 Re-run the 1.3 query and confirm only `tests.%` rows remain.

## 5. Verification

- [ ] 5.1 Repeat 1.1 on the changed tree with the same iteration count and ceiling. Report the before/after stall counts as numbers, not as "it seems fixed".
- [ ] 5.2 Run the whole `tests/integration` tier to completion and confirm no new `briefing.daily`, `launch.clickup.completion_pass` or `shared.scheduled_runs.overdue_check` row appears — the second defect, checked directly rather than assumed to follow from the first.
- [ ] 5.3 Run the commit-time tier (`tests/unit` + `tests/agents`) — `test_job_runner_schedules.py`, `test_known_work_anchor.py` and `test_recurring_work_registry.py` all assert what the shared registry holds and must be unaffected.
- [ ] 5.4 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`.

## 6. Record it

- [ ] 6.1 Replace the "The integration tier hangs intermittently when two files run together" entry in `docs/deferred-work.md` with the confirmed mechanism, or delete it if this change closes it — an entry that no longer holds is worse than none, by that file's own rule.
- [ ] 6.2 Add an entry for the upstream property that remains: `procrastinate`'s `cancel_and_capture_errors` gathers side tasks with no deadline, and `psycopg_pool` classifies `asyncio.CancelledError` as a retryable client exception, so a cancelled task touching the pool can survive its cancellation. `src/` has no such caller today; the next one inherits the trap.
- [ ] 6.3 Note in the same entry that the two-file reproduction was minimal rather than special: four integration modules arm the registry by importing `register_all()`, and two of them sort before `test_scheduled_run_history.py`.
