## Context

See `proposal.md` for motivation. Two facts shape the approach:

- The consuming side is done: `clickup_webhook.py` already verifies, deduplicates and records deliveries at `/webhooks/clickup/tasks`, and `CLICKUP_WEBHOOK_SECRET` is already provisioned on the host (`docs/deferred-work.md`, line 99). Nothing on the receiving end changes.
- Nobody has ever told ClickUp to send to it. `add-clickup-completion-loop`'s own proposal scoped registration as "operational... outside this application," and no script or runbook step exists anywhere in the repo to do it — a person would have to hand-craft a ClickUp API call and there is no record of anyone having done so.

The repo already has a precedent for "operational, but not manual and not lost": `seed_admin.py` — a standalone `commerce_ops.*` module chained into the container's start command (`Dockerfile:86`) between `alembic upgrade head` and the server, idempotent, not part of the serving process. That shape fits this problem better than a one-off curl command a person runs once and nobody can find again.

## Goals / Non-Goals

**Goals:**
- Get ClickUp actually delivering to the existing webhook endpoint, as a repeatable, reviewable, idempotent step rather than a manual one-time action nobody can reproduce.
- Only then relax `clickup_sync_job`'s cadence, once delivery is confirmed in production.

**Non-Goals:**
- Fixing `LaunchRepository.save`'s missing optimistic concurrency (`docs/deferred-work.md`) — already recorded there as its own future change, belonging to the repository rather than to this trigger. This change accepts the risk and documents it; it does not fix it.
- Anything about `gate_progression_job` or the Slack confirmation ask — `advance-gates-from-clickup-webhook`.
- Alerting on webhook health (e.g. "no delivery seen in N hours") — a real gap this change creates (see Risks) but a new capability of its own, not bundled here.

## Decisions

### Registration ships as a committed, idempotent pre-serving step, not a manual API call

**Chosen:** a new `src/commerce_ops/register_clickup_webhook.py`, mirroring `seed_admin.py`'s shape — `GET /api/v2/team/{team_id}/webhook` to check whether a webhook already targets this deployment's endpoint **and configured folder**, `POST .../webhook` to create one only if none does. Wired into `Dockerfile`'s CMD chain alongside `seed_admin`/`seed_playbook`/`check_step_handlers`.

**Alternative considered:** a manual, documented one-time API call (curl or ClickUp's UI), matching `add-clickup-completion-loop`'s original framing of registration as "outside this application." Rejected — that framing was written when nobody had done it yet, and the fact that it *still* hasn't happened months later is itself the evidence a manual step doesn't survive contact with reality here.

**Correction after review:** the original version of this decision claimed a committed step "self-heals... without anyone having to remember" if the subscription is ever deleted. That claim does not hold as stated. ClickUp generates each subscription's signing secret itself at creation time and returns it in the response (confirmed against ClickUp's API reference) — the caller never supplies one. So a recreated subscription gets a *different* secret than the one this deployment is configured with, and every delivery against it fails signature verification, silently, while ClickUp's own UI shows a healthy, present subscription. A committed step still beats a manual one — it *detects* the missing-subscription condition and creates a replacement rather than leaving completions dead with no explanation at all — but it does not self-heal the secret-mismatch failure mode it introduces. See the new spec requirement below for the mitigation this decision now depends on: every create, not only a first one, logs the new secret at warning level, naming exactly what a person must do next.

### Failure is best-effort, not deploy-blocking — a deliberate divergence from `seed_admin`

**Chosen:** the step catches its own exceptions, logs a clear warning, and always exits `0`. A failed registration never blocks the deploy or crash-loops the server.

**Alternative considered:** chain it with `&&` like every other pre-serving step, so a broken ClickUp API call blocks the deploy the way an unadministrable roster does. Rejected: `seed_admin`'s hard gate makes sense because an admin-less roster breaks a feature the moment the new release starts serving. This capability was explicitly designed the other way — `launch-clickup-sync`'s own requirement is "through webhook deliveries when they arrive **and through a periodic reconciliation pass when they do not**." A registration failure degrades exactly to today's behavior (poll-only), not to a broken deployment. Coupling deploy success to a third-party API being reachable at that exact moment, for a feature that already has a designed fallback, buys nothing and risks blocking an unrelated release on a ClickUp outage.

### The workspace (`team_id`) is resolved at registration time, not configured

ClickUp's webhook endpoint is scoped by `team_id` in the URL path, and no such setting exists today (`settings.py` has `clickup_api_token`, `clickup_launch_folder_id`, `clickup_webhook_secret`, two field ids — no team/workspace id).

**Chosen:** call `GET /api/v2/team` with the configured token and use the sole team it returns. If the token can see zero or more than one team, the step logs a warning naming the ambiguity and does nothing (falls back to best-effort semantics above) rather than guessing.

**Alternative considered:** add `CLICKUP_TEAM_ID` as a new required setting. Rejected for now — it would owe `AGENTS.md`'s full four-part ceremony (Environment secret, `deploy.yml` render, `settings.py` declaration, settings-drift test) for a value the API can already tell us, for a deployment that has never needed to disambiguate more than one ClickUp workspace anywhere else in the codebase. Worth revisiting only if that assumption ever breaks.

### The webhook is scoped to the launch folder, not the whole workspace

**Chosen:** the registration call passes `folder_id: settings.clickup_launch_folder_id`, so ClickUp only sends deliveries for tasks inside lists under that folder — which is exactly the set `clickup_webhook.py` can resolve through `ClickUpMappingRepository` anyway.

**Correction after review:** the idempotency check (see the shape of the step, above) matches an existing subscription on *both* its endpoint and its folder, not on the endpoint alone. An endpoint-only match would let a subscription left over from a since-changed `CLICKUP_LAUNCH_FOLDER_ID` satisfy the check for the *current* folder — silently leaving the current folder unregistered, indefinitely, with no signal. Matching on both means a folder reconfiguration is treated exactly like "no subscription exists yet": the step creates a fresh, correctly-scoped one, and the old subscription becomes the stale leftover the Risk below already accounted for — an outcome the mechanism now actually produces, rather than one only the prose claimed.

**Alternative considered:** register at the team (workspace) level, which is broader but simpler to reason about and immune to the folder ever changing. Rejected — `clickup_webhook.py` already acknowledges-and-ignores unmapped tasks safely either way, so correctness doesn't depend on this, but a team-wide subscription means every task edit anywhere in the workspace round-trips through this deployment's endpoint for no benefit, which is needless load and needless attack surface for an internet-facing route.

### The endpoint URL reuses `admin_base_url` rather than adding a new setting

`admin_base_url` is already "the public URL the admin surface is reachable at" (`settings.py`) — which is to say, this deployment's own public base URL, currently consumed only by the admin-link adapter. The registration step composes `f"{admin_base_url}/webhooks/clickup/tasks"` from it rather than introducing a second setting for the same fact. Its doc comment gains a second named consumer; nothing about its optionality, type, or the admin surface's own fail-closed behavior changes.

It stays optional, and the registration step MUST guard for it being unset explicitly — the same shape as the team-ambiguity guard above, not an unconditional string interpolation. `f"{admin_base_url}/webhooks/clickup/tasks"` with `admin_base_url is None` silently composes the literal string `"None/webhooks/clickup/tasks"` rather than raising, which ClickUp's API would not reject up front (it validates as any non-empty string, not as a reachable one) — a permanently-undeliverable subscription created with no diagnostic signal at all. The step SHALL check for `None` the same way it checks for an ambiguous workspace, and take no action beyond logging the gap.

### Cadence: twice daily, not once

**Chosen:** `SYNC_SCHEDULE = "0 6,18 * * *"` (06:00 and 18:00 UTC), `SYNC_TOLERANCE = datetime.timedelta(hours=24)`.

The proposal's Impact section flags that the `LaunchRepository.save` self-healing window (docs/deferred-work.md) scales with this pass's interval — a clobbered step outcome sits unrecorded until the next reconciliation run. Twice daily bounds that window to at most 12 hours rather than the ~24 hours a once-daily schedule would allow, while still cutting ClickUp API load by ~99% versus today's `*/10`. Tolerance is set to 24h: comfortably above the 12h worst-case gap between runs, and above `overdue_check.CHECK_TOLERANCE` (4h, the worker's own liveness floor), so a merely-delayed run is never reported overdue while a genuinely stopped worker still becomes visible well within a day.

Both constants stay module constants, matching `SYNC_SCHEDULE`'s existing pattern and `ASK_COOL_OFF`'s stated reasoning: there is no per-deployment answer to this cadence, so it owes none of `AGENTS.md`'s runtime-variable ceremony.

The scheduler's own longest-gap cap (60,000 occurrences over a 400-day horizon, per `gate_progression_job.py`'s Decision 2) is not in play here — twice daily is 800 occurrences over that horizon, far under it.

## Risks / Trade-offs

- **The `LaunchRepository.save` self-healing window widens from ~10 minutes to up to ~12 hours** → Accepted per the cadence decision above. Worth flagging to whoever owns `docs/deferred-work.md`'s recorded item on this: the margin this change leaves is much thinner than the one that made the race "immaterial" when it was first accepted, and that item's own priority should probably be reconsidered once this ships (a task, not a fix, in `tasks.md`).
- **A silently broken webhook now degrades to a 12-hour blind spot with no alarm** → Partially mitigated. The sharpest instance — a subscription recreated after deletion, receiving a new ClickUp-generated secret this deployment doesn't have — is caught at the moment it happens: the new spec requirement has every create log the secret at warning level, naming exactly what to do. What remains unmitigated is a person not reading that log line before the next deploy ships, and any *other* silent failure mode (a ClickUp-side outage, a network partition) that isn't a create at all. Full webhook-health observability (e.g. "no delivery seen in N hours" alerting) is still a follow-up capability, not a rider on this change — but the specific, worst failure mode the review surfaced (recreate-with-mismatched-secret) now has a signal where before it had none.
- **Registering at the folder level ties the subscription to `CLICKUP_LAUNCH_FOLDER_ID`** → If that value is ever reconfigured to a different folder, the old subscription is not automatically cleaned up (ClickUp does not know the old folder is no longer relevant), but — since the idempotency check matches on endpoint *and* folder, not endpoint alone — the new folder does get its own fresh subscription on the next deploy rather than being silently left uncovered. Only the old subscription's cleanup is left undone. Acceptable: folder reconfiguration is rare and already an operational action with other manual consequences, and an orphaned subscription is inert, not harmful.
- **`GET /api/v2/team` returning more than one team silently disables registration** → Accepted per the team-resolution decision; the step logs the ambiguity rather than guessing, and the deployment falls back to poll-only, exactly as it behaves today.
- **The mitigation for the secret-mismatch failure mode is itself a secondary exposure** → logging ClickUp's generated secret at warning level puts it into application logs, which are typically retained and aggregated more broadly, and read by more people, than the settings store the secret otherwise lives in exclusively. Accepted: this is a deploy-time log line produced only on the rare event of a create (first registration, or a recreation nobody should be causing routinely), not a runtime or per-request log path, and the alternative — logging nothing — is exactly the silent failure mode this exists to prevent. Not mitigated further here (e.g. by truncating to a verification fragment instead of the full secret); worth a second look if this deployment's log aggregation is ever less access-controlled than the settings store.

## Migration Plan

Ships as two deploys under this one change, not bundled into a single commit that both registers and immediately relies on the registration:

1. **Deploy the registration step only.** `SYNC_SCHEDULE`/`SYNC_TOLERANCE` stay unchanged (`*/10`, 6h). The step runs on the next deploy, registers the webhook (or confirms one already matches), and the poll continues exactly as today — so this deploy is a no-op for anyone observing launch behavior.
2. **Observe.** Confirm webhook deliveries are actually arriving and being recorded — application logs from `clickup_webhook.py`, or ClickUp's own webhook delivery history in its UI, over a few days of real task closures.
3. **Deploy the cadence change.** A small follow-up commit changing only `SYNC_SCHEDULE`/`SYNC_TOLERANCE` to the twice-daily values, once step 2 gives confidence.
4. **Rollback:** removing the registration step from the Dockerfile chain leaves any already-created ClickUp webhook subscription in place (harmless — `clickup_webhook.py` still verifies and processes deliveries correctly whether or not this repo remembers registering it) and reverts to manual/no re-registration on future deploys. Reverting the cadence constants alone restores `*/10` polling immediately, independent of whether the webhook is still registered.

## Open Questions

- **Resolved during review:** ClickUp's Create Webhook endpoint takes only `endpoint`, `events`, and an optional location scope (`folder_id` among them) — there is no caller-supplied secret parameter. The response carries a `secret` field ClickUp generates itself. This is not the direction the original design assumed as its default case, and the Decisions and spec requirement above are written to that corrected understanding: the step never sends a secret, it only ever receives and logs one.
- **What token scope/permission does registering a webhook require?** `CLICKUP_API_TOKEN` already exists and is used for task/list operations; whether it also carries webhook-management permission needs confirming against ClickUp's docs or a test call at implementation time. Left open deliberately: unlike the secret-direction question, no branch of the answer changes this design's approach, only whether task 1.1 clears on the first try or needs a token-scope fix first.
