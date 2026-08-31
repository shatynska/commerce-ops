## Context

See `proposal.md` for the motivation. Nothing new needs building: the cascade this change triggers already exists twice over — as `gate_progression_job.py`'s per-launch loop body, and as `gate_confirmation.py`'s `_advance_after_approval`, which is the existing precedent for running exactly this cascade *from outside the periodic pass*, off a single event (a button press) rather than a scheduled walk. This change adds a third trigger of the same shape, at one call site.

Two existing pieces set the shape, and the design copies each rather than inventing beside it:

- **`gate_progression_job.py`'s per-launch unit** — `_advance_one` (opens `transaction()`, takes `hold_launch_advance_lock`, calls `progress_launch`), `_awaiting_gate` (reads the cascade's result for a gate to ask about, excluding the final gate), and `_ask_if_owed` (outside the lock, cool-off-gated `post_gate_ask` via `GateAskSuppressionRepository`). Together these are exactly the per-launch body the walk repeats; nothing about them is specific to being called from a loop.
- **`gate_confirmation.py`'s `_advance_after_approval`** — the existing precedent for triggering this same cascade from a single external event outside the periodic pass, including reading `playbook.live` fresh rather than being handed one, since a single-event trigger has no walk-wide playbook to share.

## Goals / Non-Goals

**Goals:**

- A ClickUp closure that satisfies a gate's last condition gets an ask (or a further advance) within roughly the latency the webhook already gives completion recording, not the periodic pass's up-to-ten-minute wait.
- The webhook's acknowledgement to ClickUp is never delayed or put at risk by the advance cascade or by a Slack delivery it may trigger.
- No duplicate ask versus the periodic pass; no new persisted state.
- The amended `SHALL NOT` protects every call site except this one, named explicitly, and changes no rule the cascade itself applies.

**Non-Goals:**

- Touching `record_step_outcome` or its other three call sites (`clickup_sync_job`, `automation_pass`, `automation_confirmation`) — they keep today's convergence-only behavior.
- Shortening `gate_progression_job`'s own cadence, or anything about `clickup_sync_job`'s cadence.
- Any new persisted state — reuses `GateAskSuppressionRepository` and `hold_launch_advance_lock` exactly as they stand.

## Decisions

### Decision 1: Extract the per-launch cascade as its own callable, exported from `gate_progression_job.py`

The webhook needs the unit `_advance_one` + `_awaiting_gate` + `_ask_if_owed` already express as the walk's inner loop body, for one product rather than a candidate list. Extract that trio into one function, `advance_and_ask(product_id: ProductId, *, now: datetime.datetime | None = None) -> None`, added to `gate_progression_job.py` and exported from its `__all__`:

1. Read `playbook.live` in its own `session()` — following `_advance_after_approval`'s shape (a fresh read per trigger), not the walk's (one read shared across a candidate list), since this is a single-launch trigger with no walk to amortize the read over.
2. `PlaybookNotReadyError` is caught here and stands the trigger down for this one product — logged, not raised — the same treatment `run_gate_progression_pass` gives the whole walk, scoped to one launch instead. The periodic pass remains the thing that recovers once the playbook is ready again.
3. Run `_advance_one` (transaction + lock + `progress_launch`), then `_awaiting_gate`, then — outside the lock, back on the outer `session()` — `_ask_if_owed`.

**Extracted into `gate_progression_job.py`, not a new shared module.** `gate_progression_job.py` already imports `post_gate_ask` from `gate_confirmation.py` — a sibling driving adapter in the same module — so a driving adapter importing a function from another driving adapter within `launch/infrastructure/driving/` is established precedent, not a new architectural shape. A new module would exist for exactly one caller pair (`clickup_webhook.py` importing `advance_and_ask`) and buys nothing a direct import doesn't; `import-linter`'s boundary is each module's `application/__init__.py` surface, which neither file touches to reach the other.

### Decision 2: Dispatched as a FastAPI `BackgroundTask`, passed only the product identifier

`clickup_webhook.py`'s handler gains a `BackgroundTasks` parameter and, immediately before `return _acknowledged()` on the path that called `record_step_outcome`, adds `background_tasks.add_task(_trigger_advance_and_ask, mapped.product_id)` — a thin module-local wrapper around `advance_and_ask` (see Decision 3) rather than the import itself.

Passed the plain `ProductId` value, never the request's `db_session` or a loaded entity: Starlette runs a background task *after* the response is sent, by which point the request's `async with session()` block has already exited and committed. `advance_and_ask` opens its own `session()`/`transaction()`, exactly as `_advance_after_approval` and `_advance_one` already do independently of whatever session their caller happens to hold.

**Rejected: routing this through the scheduled-job runner** (`register_scheduled` / `recurring_work`). That mechanism is for cadence-registered, recurring work carrying a tolerance and overdue-reporting; a single ad hoc call triggered by one HTTP delivery has no cadence to register and no meaningful "overdue" state. It is also, on this exact file, what `clickup_webhook.py`'s own docstring already forbids for a different case: *"`scheduled-jobs` forbids an externally reachable route that starts recurring work"*. Worth naming explicitly since it is the same file: `advance_and_ask` runs once, over one already-identified product, and registers nothing recurring — it is not a way to trigger the reconciliation pass, it is a single cascade invocation, indistinguishable in kind from what a button press already does inline in `gate_confirmation.py`.

### Decision 3: The background task swallows and logs its own failures; it never raises into Starlette, and never suppresses the periodic pass

`advance_and_ask` catches broadly (`except Exception`) around the whole body and logs a warning naming the product, rather than letting anything escape. Two reasons, both already established elsewhere in this capability:

- An exception raised from inside a `BackgroundTask` has no client left to report to — the response is already sent — so letting it propagate only produces a bare, hard-to-attribute server log entry instead of a clear one.
- Nothing this trigger does is the *only* writer of any state the periodic pass depends on. The advance itself is idempotent-by-construction (`progress_launch` re-reads current state under the lock), and the only other write — the ask cool-off row — is written the same way, by the same `GateAskSuppressionRepository`, whichever path gets there first. So a failure here changes nothing about what the next `*/10` pass sees or does; it is a pure latency optimization, and losing it silently degrades to exactly today's behavior for that one launch on that one occasion.

This mirrors `_ask_if_owed`'s existing failure handling exactly: log and return, never fail the caller. `clickup_webhook.py` does not rely on that catch alone, though: it wraps its own dispatch in a module-local `_trigger_advance_and_ask`, which awaits `advance_and_ask` under its own `except Exception` and logs. This makes the route's insulation from the cascade a property of the route itself, holding independently of whatever `advance_and_ask`'s own body does — the two catches are redundant by design, not by oversight, and the redundancy is what a route-level test can assert without depending on the cascade's internal behavior. It is *not* the same shape as `run_gate_progression_pass`'s per-launch containment, and the difference is worth stating rather than glossing over: the pass's containment still surfaces a contained advance failure at the run level (via `GateProgressionPassError`, which fails the run and reaches `scheduled-jobs`' own failure/overdue reporting) — only an *ask-delivery* failure is absorbed without failing the run. `advance_and_ask` is never registered as scheduled work at all (Decision 2), so it has no run-level surface to fail into, for any failure inside it — a fault specific to being invoked from a `BackgroundTask` would show up only as a log warning, with no job-failure or overdue signal. This is accepted, not overlooked: the trigger's own advance failures are not the only chance the system gets to notice a systemic problem, since the identical `_advance_one`/`progress_launch` code path is exercised by the periodic pass every ten minutes over every active launch, and a genuine defect in that shared code will still surface there as a failed run. What has no independent surface is a fault specific to *this* call site alone (e.g. something about being invoked from a `BackgroundTask` rather than the walk) — accepted because this trigger is a pure latency optimization: losing it silently degrades to exactly today's pass-only behavior for that one occasion, which is not a regression worth a new alerting path.

### Decision 4: The spec amendment names the exception at the call site, not as a change to the cascade's rules

The `launch-gate-progression` delta amends exactly one sentence — *"In particular this capability SHALL NOT advance a launch as part of recording a step outcome, so that a launch's position is never a side effect of a completion arriving."* — to carve a single named exception for the ClickUp webhook's own recording of a step outcome, and states plainly that the `SHALL NOT` remains in force, unqualified, for every other path that records a step outcome.

Everything else about the cascade is unchanged for this call site too: it is still read-before-command (Decision 3 of the archived design), still one gate at a time via repeated `advance_gate` calls (Decision 4), still serialized against the periodic pass and against a button press by the same advisory lock (Decision 6), still subject to the same 24-hour ask cool-off (Decision 5). The amendment is procedural — *which call site may trigger the cascade* — not a new advancement rule.

## Risks / Trade-offs

- **A third advancing entry point races the other two on the same advisory lock.** Already true of the pass vs. a button press (archived Decision 6, Decision 11); this adds a third contender for the same lock, not a new kind of race. The lock still guarantees one crossing happens once; a webhook trigger that loses the race simply observes the launch as the winner left it, same as `_advance_after_approval` already does when the pass wins.
- **A webhook delivery during a stand-down (`PlaybookNotReadyError`) does nothing for that one launch.** Accepted: the periodic pass is still the thing that recovers once the playbook is ready, exactly as it is today; this trigger's absence of effect during a stand-down is the same non-event the pass already treats as expected, not a failure.
- **Background-task ordering gives no guarantee relative to other requests**, only that it runs after this response is flushed. Immaterial here: nothing awaits its result, and the periodic pass and button press already tolerate arbitrary interleaving with each other.
- **A fault specific to `advance_and_ask`'s own call site has no run-level failure surface.** Because it is deliberately never registered as scheduled work (Decision 2), a bug that only manifests when this cascade is invoked from a `BackgroundTask` — as opposed to a bug in the shared `_advance_one`/`progress_launch` code, which the periodic pass would independently surface as a failed run — would show up only as a log warning. Accepted: this trigger is a pure latency optimization, so its silent failure degrades to exactly today's pass-only behavior for that one occasion, not a functional regression.

## Migration Plan

None. No new table, no new column, no new configuration — reuses `gate_ask_suppression` and `launch_advisory_lock` unchanged. Ships as code plus the one spec amendment, behind the standard branch-and-PR workflow `AGENTS.md` requires, with the archive as the last commit before merge.

## Open Questions

None outstanding — the mechanics were fully worked out in the handoff this change starts from; what remained was exactly this document.
