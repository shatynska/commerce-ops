## 1. Pin the behaviour before fixing it

- [x] 1.1 Confirm `keep-handler-imports-cheap` has landed. If it has not, stop and reconcile: this change's Impact and Decision 2 assume a handler module no longer pulls LangGraph into the start chain.
- [x] 1.2 Record the baseline: run `uv run pytest tests/unit/test_registrations_across_processes.py` on the unmodified tree and note that it passes. A test written after a fix proves nothing about the fix unless the red state was observed first.
- [x] 1.3 Add a case to that file driving `commerce_ops.check_step_handlers` as a third root, modelled on `test_both_composition_roots_resolve_the_same_handler_names` (`:292`) and its `_handler_names` helper (`:263`) — **not** on the recurring-work roots at `:66-67`, which compare a different registry. Assert the third root's handler names are **equal to** the other two roots', not merely non-empty (design.md, Decision 3).
- [x] 1.4 Run the new case against the unmodified `check_step_handlers.py` and confirm it **fails**, reporting an empty registry against two non-empty ones. This is the change's central evidence; without observing it, the fix is unverified.

## 2. Write the scenarios at the level that can fail

- [x] 2.1 Derive tests for the remaining three scenarios — task 1.3 already discharges *The reporting process holds the deployment's own registrations*. Read each **WHEN** literally: "started the way the deployment starts it" means the process is driven as a process, not that a registry is handed to a function.
- [x] 2.1a **Each of them runs in a fresh interpreter**, using the subprocess pattern `test_registrations_across_processes.py` establishes (`_handler_names`, `:263`). This is not style. `HANDLERS` is a module global and five `tests/unit` files import `commerce_ops.registrations` at module scope, so pytest collection populates it for the whole run — verified: importing `shared/infrastructure/driven/test_recurring_work_registry.py` takes the registry from 0 to 1. An in-process test is red when run as a single file and green in the full tree, so it would pass 2.3 and still fail to catch a revert (design.md, Decision 4). The step set can be substituted inside the driver script, so no database is needed.
- [x] 2.2 Before writing them, check what already exists: `tests/unit/launch/application/test_step_activation.py:636-699` and `tests/unit/test_check_step_handlers_reads_the_authored_set.py:329` both cite the startup clause and both supply a registry. Neither is wrong and neither should be changed — they cover the filtering rule. The new tests cover where the registry came from.
- [x] 2.3 Confirm the tests for *A registered handler draws no fault at startup* and *An unregistered handler is named at startup* **fail** against the unmodified module, and confirm it by running the full `tests/unit` tree, not the file alone — the single-file result is exactly the false green 2.1a describes.
- [x] 2.3a *The faults the report names do not stop the deployment* is **exempt** from 2.3: `check_step_handlers.py:94` returns zero today and task 3.3 forbids changing it, so that test is green on both sides by design. Its value is regression protection for behaviour this change must preserve, not red-then-green. Do not churn looking for a red state it cannot have.

## 3. Register handlers in the process that reports on them

- [x] 3.1 In `src/commerce_ops/check_step_handlers.py`, import `register_all` from `commerce_ops.registrations` **at module scope** and call it before the report runs, as `main.py:69` and `worker.py` do. Module scope is load-bearing: the guard reads each root by import alone, so a function-local import would pass review and fail the test (design.md, Decision 1).
- [x] 3.2 Extend that module's docstring to say why the import is there: importing a handler module is what registers it, so a process that reports on the registry must populate it. Note that the module sits outside `.importlinter`'s containers — its docstring already establishes this — which is what makes naming `registrations` legal here.
- [x] 3.3 Change nothing else in the module: not the advisory exit-zero stance, not the `authored_definitions` read, not the session handling or `dispose_engine` call. Each is separately reasoned about in the existing docstring and each is correct (design.md, Non-Goals).
- [x] 3.4 Re-run 1.3's and 2.1's cases and confirm they now pass.

## 4. Correct the stale reasoning the defect left behind

- [x] 4.1 Fix the docstring at `tests/unit/test_registrations_across_processes.py:303-304`, which states that a handler imported into only one root leaves "`check_step_handlers` reporting it registered". That is wrong in **both** directions and this change does not make it true: before the fix the report says the same regardless of what any root imports; after it, a handler absent from `registrations.py` is reported *un*registered. Replace the sentence rather than softening it.
- [x] 4.2 Correct the same claim in `src/commerce_ops/registrations.py:46-47`, where the handler-module comment reasons about the report as a working guard.

## 5. Verify

- [x] 5.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `uv run lint-imports` — the last to confirm importing `registrations` from `check_step_handlers` breaks no contract.
- [x] 5.2 Run `uv run pytest tests/unit tests/agents`.
- [ ] 5.3 Optional, and only where a database is reachable — a sighting, not a gate; the tests at 1.3 and 2.1 are the change's evidence. Drive `_report()` directly, with logging configured in the snippet:

      DATABASE_URL=... uv run python -c "import asyncio, logging; logging.basicConfig(level=logging.INFO); import commerce_ops.check_step_handlers as c; asyncio.run(c._report())"

  Three reasons the obvious command shows nothing: run as `python -m`, the module's logger is `__main__` and inherits root at `WARNING`, so the success line is dropped (`docs/deferred-work.md:224-232`); `LOG_LEVEL` does not help, since `logging.py:78-79` sets root to `WARNING` and only the `commerce_ops` logger to the threshold; and `_report()` does not call `configure_logging()` itself, so without the `basicConfig` above `logging.lastResort` emits at `WARNING` and drops the line anyway. `database.py:31-37` reads `os.environ` with no dotenv, hence the explicit `DATABASE_URL`.
- [x] 5.4 Confirm no `Dockerfile` change was needed — the start chain (`:86`) already runs this process at the right point, and its exit status is unchanged.
- [x] 5.5 Measure the **import** cost before and after — `time uv run python -c "import commerce_ops.check_step_handlers"` — and record both figures in the PR. Import, not the `python -m` run: it isolates exactly the cost Decision 2 is about, and it needs no `DATABASE_URL`, so it is runnable wherever 5.3 is not. With `keep-handler-imports-cheap` landed the expected added cost is the four job modules (~0.42s locally, neither `langgraph` nor `openai` present); a materially larger figure, or either library appearing in `sys.modules`, means that change did not do what it claimed and this one should not merge.
