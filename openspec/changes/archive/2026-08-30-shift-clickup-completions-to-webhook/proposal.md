## Why

The ClickUp completion webhook (`clickup_webhook.py`) is fully implemented and already verifies, deduplicates, and records against the same `record_step_outcome` use case as the reconciliation pass — but ClickUp itself was never told to deliver to it. The 10-minute reconciliation pass (`clickup_sync_job`) is therefore the *only* path a completion travels today, which is why every ClickUp task closure takes up to 10 minutes to be reflected in the launch. `SYNC_SCHEDULE` was already tightened from 30 to 10 minutes as a stopgap for exactly this reason (2026-08-24). Registering the webhook lets completions record near-instantly for the common case, and only then does it make sense to relax the reconciliation pass back to a safety-net cadence instead of the primary path.

## What Changes

- Add a committed, idempotent pre-serving step (`register_clickup_webhook.py`, modeled on `seed_admin.py`) that registers a ClickUp webhook subscription pointed at this deployment's `/webhooks/clickup/tasks`, subscribed to `taskStatusUpdated`. ClickUp generates the subscription's signing secret itself and returns it in the creation response — the step never sends one — so it logs that secret at warning level for a person to apply to the deployment's `CLICKUP_WEBHOOK_SECRET` Environment secret, every time it creates a subscription, not only on a first run.
- Confirm webhook deliveries are arriving reliably in production over an observation period before touching the pass's cadence.
- Lower `clickup_sync_job.SYNC_SCHEDULE` from `*/10 * * * *` to a 1–2×/day cadence, and adjust `SYNC_TOLERANCE` to stay comfortably above the new gap, per `scheduled-jobs`' tolerance rule — the pass's role narrows from "the only path completion travels" to "catch what the webhook missed," which is what its own docstring already says it should be.
- No change to `gate_progression_job` or the Slack confirmation ask — a recorded completion still becomes an ask through that pass's own cadence, addressed separately in `advance-gates-from-clickup-webhook`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: adds a requirement for the registration step itself — its idempotent check-then-create behavior, its team/folder/endpoint resolution rules, and its deliberately non-blocking failure semantics (contrasted with `roster`'s admin-seeding step, which this step is modeled on but diverges from on that one point) — as SHALL language with scenarios, the same treatment `roster`'s own equivalent step already gets. The reconciliation pass's cadence itself (`SYNC_SCHEDULE`, `SYNC_TOLERANCE`) remains a module constant and not a spec-level requirement, since `launch-clickup-sync` already states only that the pass runs "periodically, on a declared schedule" without pinning a number; only the new registration step's behavior is added as a requirement.

## Impact

- **Operational**: registration itself ships as code (see below) rather than a manual API call, but the ClickUp-side subscription it produces should be confirmed delivering reliably before the cadence change ships.
- **Code**: new `src/commerce_ops/register_clickup_webhook.py`; its wiring into `Dockerfile`'s CMD chain; `admin_base_url`'s doc comment in `shared/application/settings.py` (a second named consumer, no type/optionality change); `src/commerce_ops/launch/infrastructure/driving/clickup_sync_job.py` — `SYNC_SCHEDULE` and `SYNC_TOLERANCE` constants, changed only in the second of this change's two deploys.
- **Risk**: `docs/deferred-work.md` notes that `LaunchRepository.save`'s lack of optimistic concurrency currently self-heals within one reconciliation-pass interval — a step outcome clobbered by a concurrent writer is re-recorded by "the next reconciliation pass." Stretching that pass to 1–2×/day stretches the same self-healing window from ~10 minutes to up to ~12 hours. Worth a deliberate look (and possibly worth fixing the underlying race, or scoping the cadence change to something less extreme) rather than an unexamined side effect — left for `design.md`.
