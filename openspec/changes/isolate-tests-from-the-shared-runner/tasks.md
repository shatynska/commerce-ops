## 1. Baseline, before anything is changed

- [ ] 1.1 Record the stall rate on the current tree: run `tests/integration/shared/test_scheduled_runs_freshness_unreachable.py` followed by `tests/integration/shared/test_scheduled_run_history.py` with `-p no:randomly` under a 90s ceiling, at least 15 times, and record how many stalled. Without a baseline, a green run afterwards establishes nothing — the defect is intermittent.
- [ ] 1.2 Record the same for `test_scheduled_run_history.py` alone, so the "alone it passes" half is measured on this machine rather than inherited from `docs/deferred-work.md`.
- [ ] 1.3 Name the database section 4 will delete from, before deleting anything: print the URL the tier actually resolves (`DATABASE_URL`, else `.env.test`, else `.env` — the order `tests/integration/conftest.py` applies, which is *not* the order an earlier draft of this task listed), redacted through that module's own `_redacted`. Then list every row in it whose `task_name` is not `tests.%`, with task name, status and count, and save both.
- [ ] 1.4 Record whether a worker has ever been run against that database (`python -m commerce_ops.worker`, or a local `docker compose` worker service). Nothing in procrastinate's schema records which process deferred a row, so this is the only thing that distinguishes test junk from a genuine local run — and if the answer is "yes" or "unknown", say so in section 4 rather than asserting provenance the data cannot support.

## 2. Isolate the runner tests from the shared registry

- [ ] 2.1 In `tests/integration/shared/test_scheduled_run_history.py`, build the file's own `procrastinate.App`, **importing `_queue_pool`, `queue_conninfo` and `PERIODIC_DEFAULTS` from `job_runner` by name rather than re-deriving them**. `periodic_defaults=PERIODIC_DEFAULTS` is not optional: procrastinate's own default is `max_delay=600`, and the reuse is what keeps the connection derivation and the missed-window rule shared with the application.
- [ ] 2.2 Register `tests.run_history.*` on that App, and point `_drain()` and every `open_async()` in the file at it.
- [ ] 2.3 Keep `last_successful_run` reading through the application's own session provider — tasks.md 2.10a of `replace-cron-with-job-runner` requires it, and it is unaffected by which App defers the work.
- [ ] 2.4 Update the module docstring: it currently gives "so that what is exercised is this application's runner" as the reason for using `runner_app`. Record what is still exercised (the schema migration, the accessor, the connection derivation and periodic defaults reused by name) and what deliberately is not (the shared registry and the shared `App` object), per design.md Decision 1.
- [ ] 2.5 Do the same for `tests/integration/shared/test_periodic_defer_dedup.py`. Note that its deferrer is constructed with `**runner_app.periodic_defaults` (line 159–160) — that reference must move to the private App's defaults too, or the file's own precondition (`first_offer` being non-empty for an 06:00 tick) stops holding.
- [ ] 2.6 Make the isolation self-enforcing rather than merely asserted: have `_drain()` and the assertion read the App from **one** module-level constant, and assert that constant's `periodic_registry` is empty. An assertion against a different name than `_drain()` uses stays green when a future edit points `_drain()` back at `runner_app`, which is the edit worth catching.

## 3. Guard the whole tier, not just these two files

- [ ] 3.1 Add a session-scoped autouse guard to `tests/integration/conftest.py` that fails loudly when a worker is started against a non-empty `runner_app.periodic_registry`. This is what makes design.md's second Goal a property rather than a sentence: tasks 2.x fix the two files that exhibit the defect, and nothing in them stops a future file calling `runner_app.run_worker_async()` while four sibling modules keep the registry armed.
- [ ] 3.2 The guard reads and fails; it must not empty or mutate the registry. The four modules that call `register_all()` are correct as they are and must keep seeing an armed registry — the guard fires on *starting a worker* against it, not on it being armed.
- [ ] 3.3 Verify the guard by the failure it is for: temporarily point one of the runner tests back at `runner_app`, confirm the guard fails it with a message naming the registry contents, then revert.

## 4. Bound the drain

- [ ] 4.1 Start the worker run as its own task and bound it with `asyncio.wait({task}, timeout=CEILING)`, failing the test when the task is still pending. **Not `asyncio.wait_for`** — it awaits the coroutine it cancelled, so against an uncancellable one (the defect class this change documents) it hangs instead of failing. See design.md Decision 2.
- [ ] 4.2 State in the failure message that the orphaned worker task survives the failing test, so the loop-teardown warning that follows is expected rather than a second defect.
- [ ] 4.3 Give the ceiling a named constant and a comment saying what it is for — a wedge detector, not a latency budget — following `BOUNDED_SECONDS` in `test_scheduled_runs_freshness_unreachable.py`, and choose it against the 1.1/1.2 baseline with an order of magnitude of headroom.
- [ ] 4.4 Confirm the bound fires against the App actually under test: register a `* * * * *` periodic task on the **private** App so its deferrer really loops, and check the test fails at the ceiling. Revert afterwards. Arming `runner_app.periodic_registry` instead proves nothing once task 2 has landed — it no longer reaches the App the test drives, so the run passes quickly and a green result is indistinguishable from never having exercised the bound.

## 5. Clear what the defect wrote

- [ ] 5.1 Against the one database named in 1.3, delete the `procrastinate_jobs` rows for `briefing.daily`, `launch.clickup.completion_pass`, `shared.scheduled_runs.overdue_check` and `products.monitoring.daily`, together with their `procrastinate_events` and `procrastinate_periodic_defers`. Confirm against the list from 1.3 first, and record 1.4's answer beside it.
- [ ] 5.2 Do **not** touch the deployment's database. Its rows for those task names are genuine runs.
- [ ] 5.3 Re-run the 1.3 query and confirm only `tests.%` rows remain.

## 6. Verification

- [ ] 6.1 Repeat 1.1 on the changed tree with the same iteration count and ceiling, and report before/after as numbers. Treat the count as corroboration, not proof: against a 2/15 baseline, 0/15 arises by chance about 12% of the time with no fix at all. The load-bearing evidence is 2.6, 3.1 and the mechanism.
- [ ] 6.2 Run the whole `tests/integration` tier to completion and confirm no new `briefing.daily`, `launch.clickup.completion_pass` or `shared.scheduled_runs.overdue_check` row appears — the second defect, checked directly rather than assumed to follow from the first.
- [ ] 6.3 Run the commit-time tier (`tests/unit` + `tests/agents`) — `test_job_runner_schedules.py`, `test_known_work_anchor.py` and `test_recurring_work_registry.py` all assert what the shared registry holds and must be unaffected.
- [ ] 6.4 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports` — the full set `deploy-pipeline`'s "Pull Request Validation Gate" names, so CI is not the first to run one of them.

## 7. Record it

- [x] 7.1 Rewrite `docs/deferred-work.md`'s hang entry with the confirmed mechanism. **Already done** in this change's first commit (`667fa00`), under the heading "The integration tier hangs intermittently — cause identified 2026-08-25".
- [x] 7.2 Add "The upstream properties this depends on". **Already done** in the same commit.
- [x] 7.3 Record that the two-file reproduction was minimal rather than special. **Already done** in the same commit.
- [ ] 7.4 Correct the claim that `src/` has no caller exposed to the upstream trap. `worker.py:56` calls `register_all()` and `worker.py:141` calls `run_worker_async()` with signal handlers installed, so the deployed worker runs the same cancel-and-gather path on every SIGTERM. Its exposure is bounded by Docker's stop grace period, not by absence. The claim is currently wrong in `docs/deferred-work.md` and must be fixed there as well as in `design.md`.
- [ ] 7.5 On merge, delete the two entries that stop being true: "The integration tier hangs intermittently — cause identified 2026-08-25" and "Tests defer and run production jobs — the same root, the quieter half". Keep "The upstream properties this depends on", which survives this change. `docs/deferred-work.md`'s own rule is that an entry which no longer holds is worse than no entry.
