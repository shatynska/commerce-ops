## Why

`launch-clickup-sync` only creates ClickUp lists and tasks (`converge_launch`) from one place: `clickup_sync_job`'s periodic reconciliation pass, whose cadence was widened today from `*/10 * * * *` to twice daily (`shift-clickup-completions-to-webhook`, to relieve real ClickUp 429s). That widening was scoped to the *completion* direction, which now has the webhook as its fast path and the pass as its fallback — but the *creation* direction shares the same pass and cadence, so it has no fast path at all: a newly started launch, or a launch whose gate just opened new released steps, now waits up to ~12 hours (was ~10 minutes) before any ClickUp task exists for it.

Gate advancement itself is not the bottleneck — `progress_launch` is pure Postgres, and two of its three trigger points (`gate_confirmation.py`'s Slack confirm, and `advance-gates-from-clickup-webhook`'s webhook-triggered `advance_and_ask`) already run it immediately. But none of the three call sites — including `gate_progression_job`'s own periodic pass — does anything afterward to get the newly released steps' tasks into ClickUp; that is left entirely to the next twice-daily `clickup_sync_job` run, independent of how quickly the gate itself opened.

Separately, `slack_entry.py`'s post-`/start-launch` confirmation still tells the submitter their tasks will "appear within about 10 minutes" (`CLICKUP_SYNC_CADENCE_DESCRIPTION`) — accurate when written, false since today's cadence change, and understating the real wait by up to ~70x regardless of what this change does.

## What Changes

- Add a single-launch, eager call to the existing `converge_launch` (creation/update only — list, tasks, due dates, Custom Fields; never `reconcile_launch`, which stays exactly as it is, driven by the webhook and the periodic pass) immediately after:
  - `start_launch` succeeds (`slack_entry.py`), and
  - `progress_launch` actually crosses a gate, at all three of its existing call sites (`gate_confirmation.py`'s Slack confirm, `gate_progression_job`'s own periodic advance, and `clickup_webhook.py`'s `advance_and_ask`) — so a gate opened by any of the three reasons a gate opens gets its newly released steps' tasks without waiting on the separate `clickup_sync_job` cadence.
- `clickup_sync_job`'s twice-daily pass keeps its cadence, its role as the fallback for both directions (a missed eager call, a folder/list repair, due-date drift, Custom Field drift, reconciliation), and its containment and stand-down behavior exactly as `shift-clickup-completions-to-webhook` and `retry-clickup-rate-limits` left them. One narrow exception: its per-launch `converge_launch` call moves into its own transaction holding the same per-product advisory lock the eager path takes, so the two cannot race and create a duplicate ClickUp list on a launch's first convergence (see `design.md`). This is a change to how that one call is wrapped, not to what the pass does, when it runs, or what it reports.
- Fix `CLICKUP_SYNC_CADENCE_DESCRIPTION` in `slack_entry.py` to describe the new reality (tasks appear immediately, barring the same per-launch failure modes `launch-clickup-sync` already contains) rather than a stale number.
- Explicitly not in scope: shortening or otherwise changing `clickup_sync_job`'s cadence; the completion/reconciliation direction (`reconcile_launch`, the webhook's own recording path); `progress_launch`'s own advancement rules or triggers (`launch-gate-progression` is unchanged — this adds a call *after* it succeeds, not a new reason it runs); the `LaunchRepository.save` whole-aggregate-clobber defect noted in `docs/deferred-work.md` (unaffected — `converge_launch` does not call `LaunchRepository.save`).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: adds a new requirement describing an eager, single-launch trigger for the creation/update half of projection (`converge_launch`) at launch start and at a gate crossing, run in addition to — not instead of — the periodic reconciliation pass. No existing requirement's behavior changes: the reconciliation pass, the webhook, and every projection/eligibility rule (release, hazard, kind, status, Custom Fields, retained-composition healing, etc.) apply identically whether a task was created by the eager trigger or by the pass, because both call the same `converge_launch`.

## Impact

- **Code**:
  - `src/commerce_ops/launch/infrastructure/driving/slack_entry.py` — call `converge_launch` after `start_launch` commits; update `CLICKUP_SYNC_CADENCE_DESCRIPTION`.
  - `src/commerce_ops/launch/infrastructure/driving/gate_confirmation.py`, `gate_progression_job.py`, `clickup_webhook.py` — call `converge_launch` after a successful `progress_launch` gate crossing, at all three existing call sites.
  - `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py` / `clickup_sync_job.py` — `converge_launch` is already scoped to one launch (called per-launch inside the pass's walk today). `clickup_sync_job.py`'s per-launch loop is restructured so that call runs inside its own `transaction()` holding `hold_launch_advance_lock`, mirroring `gate_progression_job.py`'s `_advance_one`; the pass's outer session, its playbook/configuration reads, and `reconcile_launch`'s call are unaffected.
- **Design questions for `design.md`**: whether the eager call runs synchronously (as the periodic pass already does, awaited) or is dispatched via `BackgroundTasks`/similar so a slow ClickUp write never delays a Slack response or the webhook's acknowledgement, matching `advance_and_ask`'s precedent; whether it runs inside or outside the DB transaction/advisory lock that `progress_launch` and `start_launch` already use; how a failure in the eager call is handled given `launch-clickup-sync`'s existing per-launch containment and stand-down rules (it must not fail the caller — a Slack confirm, a webhook ack — and must not suppress the next periodic pass from catching what the eager call missed); interaction with the ClickUp 429 pressure that motivated widening `clickup_sync_job`'s cadence today (an eager single-launch call is a different cost shape than a full active-launch sweep, but is still new call volume against the same rate-limited API, and `retry-clickup-rate-limits`' backoff is the existing mitigation to lean on rather than a new one).
- **Dependencies**: none new. Reuses `converge_launch`, `retry-clickup-rate-limits`' backoff, and the advisory-lock/transaction patterns `gate_progression_job.py` and `gate_confirmation.py` already use.
