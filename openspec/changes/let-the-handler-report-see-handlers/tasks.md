## 1. Pin the behaviour before fixing it

- [ ] 1.1 Confirm `keep-handler-imports-cheap` has landed. If it has not, stop and reconcile: this change's Impact and Decision 2 assume a handler module no longer pulls LangGraph into the start chain.
- [ ] 1.2 Record the baseline: run `uv run pytest tests/unit/test_registrations_across_processes.py` on the unmodified tree and note that it passes. A test written after a fix proves nothing about the fix unless the red state was observed first.
- [ ] 1.3 Add a case to that file driving `commerce_ops.check_step_handlers` as a third root, modelled on `test_both_composition_roots_resolve_the_same_handler_names` (`:292`) and its `_handler_names` helper (`:263`) — **not** on the recurring-work roots at `:66-67`, which compare a different registry. Assert the third root's handler names are **equal to** the other two roots', not merely non-empty (design.md, Decision 3).
- [ ] 1.4 Run the new case against the unmodified `check_step_handlers.py` and confirm it **fails**, reporting an empty registry against two non-empty ones. This is the change's central evidence; without observing it, the fix is unverified.

## 2. Write the scenarios at the level that can fail

- [ ] 2.1 Derive tests from the four added delta scenarios, reading each **WHEN** literally: "started the way the deployment starts it" means the process is driven as a process, not that a registry is handed to a function. A test that supplies a fake registry satisfies the words but not the requirement, and passes before the fix (design.md, Decision 4).
- [ ] 2.2 Before writing them, check what already exists: `tests/unit/launch/application/test_step_activation.py:636-699` and `tests/unit/test_check_step_handlers_reads_the_authored_set.py:329` both cite the startup clause and both supply a registry. Neither is wrong and neither should be changed — they cover the filtering rule. The new tests cover where the registry came from.
- [ ] 2.3 Confirm each new test fails against the unmodified module before task 3 is applied. A scenario-derived test that is green before the fix has been written at the wrong level, which is this change's most likely failure.

## 3. Register handlers in the process that reports on them

- [ ] 3.1 In `src/commerce_ops/check_step_handlers.py`, import `register_all` from `commerce_ops.registrations` **at module scope** and call it before the report runs, as `main.py:69` and `worker.py` do. Module scope is load-bearing: the guard reads each root by import alone, so a function-local import would pass review and fail the test (design.md, Decision 1).
- [ ] 3.2 Extend that module's docstring to say why the import is there: importing a handler module is what registers it, so a process that reports on the registry must populate it. Note that the module sits outside `.importlinter`'s containers — its docstring already establishes this — which is what makes naming `registrations` legal here.
- [ ] 3.3 Change nothing else in the module: not the advisory exit-zero stance, not the `authored_definitions` read, not the session handling or `dispose_engine` call. Each is separately reasoned about in the existing docstring and each is correct (design.md, Non-Goals).
- [ ] 3.4 Re-run 1.3's and 2.1's cases and confirm they now pass.

## 4. Correct the stale reasoning the defect left behind

- [ ] 4.1 Fix the docstring at `tests/unit/test_registrations_across_processes.py:303-304`, which states that a handler imported into only one root leaves "`check_step_handlers` reporting it registered". That is wrong in **both** directions and this change does not make it true: before the fix the report says the same regardless of what any root imports; after it, a handler absent from `registrations.py` is reported *un*registered. Replace the sentence rather than softening it.
- [ ] 4.2 Correct the same claim in `src/commerce_ops/registrations.py:46-47`, where the handler-module comment reasons about the report as a working guard.

## 5. Verify

- [ ] 5.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `uv run lint-imports` — the last to confirm importing `registrations` from `check_step_handlers` breaks no contract.
- [ ] 5.2 Run `uv run pytest tests/unit tests/agents`.
- [ ] 5.3 Optional, and only where a database is reachable: drive `_report()` directly rather than through `python -m`, e.g. `DATABASE_URL=... uv run python -c "import asyncio, commerce_ops.check_step_handlers as c; asyncio.run(c._report())"` with a root-level log override. Two reasons the obvious command does not work: run as `python -m`, this module's logger is `__main__` and inherits root at `WARNING`, so its success line is dropped (`docs/deferred-work.md:224-232`) — `LOG_LEVEL` does not help, it sets the `commerce_ops` logger only — and `database.py:31-37` reads `os.environ` with no dotenv, so `DATABASE_URL` must be exported. The test at 1.3 is the change's evidence; this step is a sighting, not a gate.
- [ ] 5.4 Confirm no `Dockerfile` change was needed — the start chain (`:86`) already runs this process at the right point, and its exit status is unchanged.
- [ ] 5.5 Time the process before and after (`time uv run python -m commerce_ops.check_step_handlers`) and record the delta in the PR. With `keep-handler-imports-cheap` landed the expected cost is the four job modules (~0.42s locally); a materially larger figure means that change did not do what it claimed and this one should not merge.
