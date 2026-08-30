## Why

Even after `shift-clickup-completions-to-webhook` makes completion *recording* near-instant, the Slack confirmation ask for a gate a ClickUp closure just satisfied still waits for `gate_progression_job`'s next `*/10` run — because `launch-gate-progression` currently forbids advancing as a side effect of recording an outcome at all ("this capability SHALL NOT advance a launch as part of recording a step outcome"), a deliberate choice recorded as Decision 1 in `advance-gates-and-confirm-in-slack`'s design. That decision is still right in general — a gate can become ready through a metric attestation, a playbook edit, or an already-satisfied launch, none of which a ClickUp trigger would ever see — but it means the single most common trigger, a person closing a ClickUp task, still costs up to 10 minutes of a person's time waiting to be asked to confirm what they just finished.

## What Changes

- Narrowly amend `launch-gate-progression`'s convergence-only rule: add a reactive advance-and-ask trigger **at the ClickUp webhook call site only** (`clickup_webhook.py`), invoked after a webhook delivery causes `record_step_outcome` to record a transition — not inside `record_step_outcome` itself, and not at the other three call sites (`clickup_sync_job`, `automation_pass`, `automation_confirmation`), which keep today's convergence-only behavior and Decision 1's coupling objection intact for them.
- The reactive trigger runs the same cascade `gate_progression_job` already runs for one launch — `progress_launch` inside `transaction()` + `hold_launch_advance_lock`, then `post_gate_ask` outside the lock, gated by the existing `GateAskSuppressionRepository` 24h cool-off — so a webhook-triggered ask and a periodic-pass ask for the same gate cannot double-post; the cool-off already makes repeats within a day a no-op.
- It runs off the webhook's response path (e.g. as a background task) so a slow advance cascade or a slow Slack delivery never delays the webhook's acknowledgement back to ClickUp.
- `gate_progression_job`'s `*/10` pass is unchanged and remains the only mechanism for every non-ClickUp way a gate becomes ready — this change adds a fast path for one trigger, it does not replace the convergence pass or attempt to shorten its cadence (which `advance-gates-and-confirm-in-slack`'s Decision 2 already established is at a hard floor: `*/5` is refused by `scheduled-jobs`' longest-gap computation).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-gate-progression`: the requirement "Advancement is a convergence pass and not a consequence of recording an outcome" currently states an unqualified SHALL NOT ("this capability SHALL NOT advance a launch as part of recording a step outcome"). This change carves a single, named exception into it — the ClickUp webhook's own recording of a step outcome may also trigger the same advance-and-ask cascade for that launch — while keeping the SHALL NOT in force for every other recording path and for every gate-readiness cause the webhook cannot observe.

## Impact

- **Code**: `src/commerce_ops/launch/infrastructure/driving/clickup_webhook.py` (new trigger call, background-task dispatch), likely a small shared helper extracted from `gate_progression_job.py`'s `_advance_one`/`_ask_if_owed` so the webhook and the periodic pass call the same cascade rather than duplicating it.
- **Design questions for `design.md`**: how the trigger is dispatched without blocking the webhook's ack (FastAPI `BackgroundTasks` vs. the job-runner used for scheduled work); whether `_advance_one`/`_ask_if_owed` should be exported from `gate_progression_job.py` or extracted to a shared module both driving adapters import; what happens if the background trigger fails silently (it must not fail the webhook's already-sent 200 OK, and must not suppress the next periodic pass from catching it).
- **Explicitly not in scope**: touching `record_step_outcome` or the other three call sites; shortening `gate_progression_job`'s own cadence; anything about `clickup_sync_job`'s cadence (that is `shift-clickup-completions-to-webhook`, applied first).
