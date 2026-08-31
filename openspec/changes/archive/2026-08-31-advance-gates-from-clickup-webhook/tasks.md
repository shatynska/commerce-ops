## 1. Extract the per-launch cascade in `gate_progression_job.py`

- [x] 1.1 Add `advance_and_ask(product_id: ProductId, *, now: datetime.datetime | None = None) -> None` to `gate_progression_job.py`: read `playbook.live` in its own `session()`, catch `PlaybookNotReadyError` and stand down (log, return) for that one product, then run `_advance_one`, compute `_awaiting_gate`, and — outside the lock, on the outer session — call `_ask_if_owed`.
- [x] 1.2 Wrap the whole body of `advance_and_ask` in a broad `except Exception` that logs a warning naming the product and returns, so no failure inside it ever propagates to a caller.
- [x] 1.3 Export `advance_and_ask` from `gate_progression_job.py`'s `__all__`.
- [x] 1.4 Confirm `run_gate_progression_pass`'s existing loop body is unchanged in behavior — either leave it calling `_advance_one`/`_awaiting_gate`/`_ask_if_owed` directly, or refactor it to call the new `advance_and_ask` internally if that removes duplication cleanly; either way, the periodic pass's own failure containment and `GateProgressionPassError` aggregation must be unaffected.

## 2. Wire the trigger into the ClickUp webhook

- [x] 2.1 Add `advance_and_ask` (from `gate_progression_job.py`) to `clickup_webhook.py`'s bare-global imports and `__all__`, following the module's own documented convention for testability via `monkeypatch.setattr`.
- [x] 2.2 Add a `BackgroundTasks` parameter to `receive_clickup_event`.
- [x] 2.3 After the `async with session()` block that calls `record_step_outcome` exits (i.e. after that transition is committed) and before `return _acknowledged()`, call `background_tasks.add_task(_trigger_advance_and_ask, mapped.product_id)` — a thin module-local wrapper that awaits `advance_and_ask` under its own `except Exception`, so the route's insulation from the cascade does not depend on `advance_and_ask`'s own catch (`design.md` — Decision 3) — passing only the `ProductId` value, never the request's `db_session` or any loaded entity.
- [x] 2.4 Verify no other early-return path in `receive_clickup_event` (unmapped task, no transition, unready playbook with an unserved step, unprojected step) schedules the background task — it must fire only on the path that actually recorded a step outcome.

## 3. Tests

- [x] 3.1 Confirm the tests the test-writer derives from the two new/modified spec scenarios (`A ClickUp webhook delivery may trigger an advance-and-ask cascade...`, `A decision and a webhook-triggered advance do not cross the same gate twice`, and the updated `Recording an outcome does not itself advance a launch`) pass against the implementation.
- [x] 3.2 Run `uv run pytest` (unit + agents tier) and confirm green.

## 4. Verification and archive

- [x] 4.1 Run `ruff check`, `ruff format --check`, and `mypy`.
- [ ] 4.2 Run the full test suite including the integration tier if touched (this change adds no new I/O, so the unit/agents tier should suffice, but confirm no import-linter contract is violated by `clickup_webhook.py` importing from `gate_progression_job.py`).
- [ ] 4.3 Open the PR per `AGENTS.md`'s workflow; archive (`openspec archive advance-gates-from-clickup-webhook --yes`) as the last commit before merge.
