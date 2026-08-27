## Why

One launch whose ClickUp state cannot be converged currently aborts the whole completion pass, so every launch the pass had not reached yet is left unprojected — not degraded, not delayed, but never touched, for as long as the condition lasts.

This is not hypothetical. On 2026-08-27 a ClickUp list belonging to one launch was deleted in ClickUp while the mapping still recorded it. Every pass since read that list as empty, took the re-projection branch for each of its steps, and got `404 Not Found` from `create_task`:

```
ClickUp completion pass starting over 5 launch(es)
  launch 1  converged: 9 tasks healed
  launch 2  create_task → HTTPStatusError: 404  💥
  launches 3, 4, 5  never reached
```

A product launched that morning was one of the three. It received no list and no task, its Slack confirmation notwithstanding, and nothing in the deployment said so: the run was recorded as failed, but a failed run is indistinguishable from one whose *first* launch failed, and the freshness endpoint stayed inside its six-hour tolerance throughout. The fault belonged to one launch; the outage belonged to all of them.

The pass is written as convergence over one launch — `converge_launch` and `reconcile_launch` each take a single launch and heal whatever they find. What is missing is the guarantee that this per-launch shape actually holds when a launch fails: the loop that drives them has no containment, so one launch's exception is every launch's outage.

## What Changes

- The completion pass SHALL attempt every active launch, whatever happened to the ones before it. A failure — from either half, projection or reconciliation — is contained to the launch it belongs to, reported against that launch, and does not stop the walk. Two things still end a walk, and both are stated in the spec: the process being cancelled or shut down, and a failure of the recovery the pass performs between launches, after which it could only attempt launches whose results it cannot record.
- A run in which any launch failed SHALL still be reported as a **failed run**. Containment is about not starving the other launches, not about tolerating the fault: a run that swallowed the failure would leave `scheduled-jobs` reporting green while a launch goes unprojected indefinitely, which is the blind spot this deployment has already been bitten by once (see `launch-clickup-sync`'s stand-down requirement, which accepts that trade *only* because the daily briefing raises the signal instead — nothing raises a signal here).
- The existing obligation that an unconfigured parent folder fails the run rather than skipping a launch silently is preserved: that condition is reached by every launch that needs a list, so it fails each of them and the run still fails.

Explicitly not in this change:

- **Healing a launch whose ClickUp list was deleted.** That is the fault that exposed this one, and it is its own change — it needs a rule for detecting a dead list and for discarding the task mappings that die with it. Leaving it unfixed is deliberate here: it is the fixture that makes this change's effect observable, since the broken launch must keep failing while the launches behind it start converging. It is owed, not optional — while the fixture stands, this pass never records a success, so the deployment stays unhealthy and `scheduled-jobs` stays quiet about it by design (design.md — Risks; tasks.md 5.4). The fixture therefore stands until the follow-up healing change lands — not until the observations are made. The observations in tasks.md §5 bound when that change must be *proposed*, on the strength of them rather than at some later convenience; what ends the unhealthy state is its merge. A bound is stated here because nothing else can carry it: this change is archived before the merge, so the obligation would otherwise live only in an archived checklist nobody reopens.
- The automation pass's own per-launch containment. It contains handler failures already; whether it contains everything else is a separate question about a separate capability.
- Deterministic ordering of the walk. See design.md — it is a consequence of the current fault, not a cause, and containment removes what made the order matter.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: adds a requirement that a launch's failure is contained to that launch while the run still reports failure, and narrows the reconciliation requirement to match — "every active launch's mapped tasks" gains one exception, the launch whose projection raised on the same run, which is left unread and unobserved so its completions are deferred rather than consumed. The projection and stand-down requirements are unaffected, and so — deliberately, having been considered — is the requirement carrying completion from ClickUp to the launch: webhook intake is a separate path into the same launches, gated on the delivery and the mapping rather than on anything the completion pass did, so a launch whose projection is failing still records a completion that a delivery brings it. Only the completions reconciliation was the sole path for are deferred.

## Impact

- `src/commerce_ops/launch/infrastructure/driving/clickup_sync_job.py` — the loop in `reconcile_clickup_completions`, which is the only place both halves are driven across launches.
- No change to `clickup_sync.py`'s own passes, to the mapping store, or to the ClickUp client: this is about what drives them, not what they do.
- `scheduled-jobs` is unchanged and is what carries the reporting: a failed run is already retried with increasing delay and already surfaces through overdue reporting once its tolerance is exceeded.
- Retries and the ten-minute schedule now re-walk the healthy launches while a broken one persists. Convergence is idempotent, so this heals rather than duplicates; the cost is one list read per healthy launch per attempt.
