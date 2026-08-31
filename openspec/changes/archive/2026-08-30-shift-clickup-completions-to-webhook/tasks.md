## 1. Registration step

- [x] 1.1 Add `src/commerce_ops/register_clickup_webhook.py`, mirroring `seed_admin.py`'s shape: a thin `main()`/CLI entry over testable helper functions, `configure_logging()`, its own engine lifecycle if it needs the database (it does not — this step talks only to ClickUp's API and reads settings).
- [x] 1.2 Resolve the workspace: `GET /api/v2/team`; proceed only if exactly one team is returned, else log a warning naming the ambiguity and stop (best-effort — see 1.6).
- [x] 1.3 Guard `admin_base_url`: if it is `None`, log a warning naming the gap and stop, mirroring 1.2's shape — never compose the endpoint from an unset value.
- [x] 1.4 Check for an existing matching subscription: `GET /api/v2/team/{team_id}/webhook`, looking for one whose `endpoint` equals `f"{settings.admin_base_url}/webhooks/clickup/tasks"` **and** whose `folder_id` equals `settings.clickup_launch_folder_id` — both, not endpoint alone, so a subscription left over from a since-changed `CLICKUP_LAUNCH_FOLDER_ID` doesn't get treated as covering the *current* folder. If a subscription matching both is found, log and do nothing further; any other subscription found (endpoint matches, folder doesn't) is left alone and does not count as a match.
- [x] 1.5 If none found, create one: `POST /api/v2/team/{team_id}/webhook` with `endpoint`, `events: ["taskStatusUpdated"]`, `folder_id: settings.clickup_launch_folder_id`. Resolved during design review: ClickUp's Create Webhook endpoint takes no caller-supplied secret — it generates one and returns it in the response. Log that returned secret at warning level, naming explicitly that the deployment's `CLICKUP_WEBHOOK_SECRET` Environment secret must be set or updated to match it before deliveries will verify — this applies identically whether this is the first registration ever or a recreation after a prior subscription was removed; the step has no way to tell those apart and must log the secret every time it creates. Also added a guard for `CLICKUP_LAUNCH_FOLDER_ID` itself being unset (not spelled out in tasks.md, but symmetric with 1.3's guard and consistent with `design.md`'s "scoped to the launch folder, not the whole workspace" intent — a subscription would otherwise have nothing to be scoped to).
- [x] 1.6 Wrap the whole step so any exception (missing settings, ClickUp API error, network failure, team ambiguity) is caught, logged as a warning naming the reason, and the step exits `0` regardless — per `design.md`'s best-effort decision, this must never block the deploy or crash-loop the server.
- [x] 1.7 Update `admin_base_url`'s doc comment in `settings.py` to name its second consumer (webhook endpoint composition), without changing its type, optionality, or existing fail-closed behavior for the admin surface.
- [x] 1.8 Wire the step into `Dockerfile`'s CMD chain (after `seed_playbook`, before `check_step_handlers`), as a plain chained command per 1.6's exit-0 guarantee.

## 2. Tests for the registration step

Derive these from `specs/launch-clickup-sync/spec.md`'s new requirement and its scenarios — each scenario below names the one it covers.

Written by a dispatch of `ai-toolkit:openspec-test-writer`: `tests/unit/test_register_clickup_webhook.py`, `test-manifest.md` at this change's root. All 8 scenarios covered, 10 test executions (one parametrized ×2). One `type: ignore` the test-writer added defensively (anticipating an untyped stub) was removed once the real, typed implementation made it unused — a fixture correction, not an assertion change.

- [x] 2.1 *A first registration creates a subscription and surfaces its secret*: given a token resolving to exactly one team and no existing matching webhook, the step calls create with the expected `endpoint`, `events`, and `folder_id`, and logs the response's `secret` at warning level naming the required `CLICKUP_WEBHOOK_SECRET` update.
- [x] 2.2 *An existing matching subscription is not recreated*: given one team and an existing webhook whose `endpoint` **and** `folder_id` already match, the step makes no create call.
- [x] 2.3 *A recreated subscription surfaces its secret exactly as a first registration does*: given the same no-match condition as 2.1 (the step cannot distinguish "never registered" from "registered, then removed"), assert the logging behavior is identical either way — i.e. that nothing in the implementation conditions the warning-level secret log on this being a first run.
- [x] 2.3a *A changed launch folder gets its own fresh subscription*: given an existing webhook whose `endpoint` matches but whose `folder_id` is a different value than currently configured, the step treats this as no match — it creates a new subscription scoped to the current folder and logs its secret, and makes no attempt to modify or delete the mismatched one.
- [x] 2.4 *An ambiguous workspace takes no action*: given a token resolving to zero or multiple teams, the step logs a warning and makes no create call.
- [x] 2.5 *A missing public endpoint takes no action*: given `admin_base_url` unset, the step logs a warning and makes no create call — covers 1.3.
- [x] 2.6 *A registration failure does not block the deployment*: given any exception from the ClickUp calls (a 4xx/5xx response, a transport failure), the step logs a warning and `main()` still returns/exits `0`.
- [x] 2.7 *Starting the server performs no registration*: confirm (or add, if missing) a test asserting the webhook route itself (`clickup_webhook.py`) and server startup are unaffected — this change adds a new pre-serving step and a new caller of the ClickUp API, not a new behavior on the receiving end or in the serving process.

## 3. PR 1 — ship registration, hold cadence

This section is this change's first mergeable unit. **Do not begin section 4 in the same PR or the same implementation pass as this section** — see 3.4.

- [ ] 3.1 Open this section's work (tasks 1.x, 2.x) as its own PR. `SYNC_SCHEDULE`/`SYNC_TOLERANCE` are untouched in this PR — this deploy's only effect should be that a ClickUp webhook subscription now exists.
- [ ] 3.2 Merge and deploy. Confirm registration succeeded: application logs from `register_clickup_webhook`, and/or the subscription visible in ClickUp's own webhook settings.
- [ ] 3.3 Observe real deliveries over a few days of actual ClickUp task closures: confirm `clickup_webhook.py` is recording outcomes (application logs, or comparing journal entries with provenance source `clickup` against when tasks were actually closed) rather than everything still arriving only via the `*/10` poll.
- [ ] 3.4 **STOP — human confirmation gate.** Section 4 (the cadence change) is not to be started, by a person or an agent working through this checklist, until a person has explicitly confirmed that 3.3's observation period showed reliable delivery. This is a precondition on continuing this change, not a task to check off unilaterally — `design.md`'s whole argument for why the widened `LaunchRepository.save` self-healing window (see 4.3) is safe to accept depends on the webhook actually being the primary path by the time the cadence changes, not on trusting that it will be.

**3.3/3.4 never happened, and section 4 was started anyway.** This change was
archived once PR 1 shipped (see 4.5's note below), before either 3.3's
observation period or 3.4's confirmation gate. Section 4 was picked up on
2026-08-31, on an explicit decision to accept that unmet precondition —
real ClickUp `429`s from the combined load of this pass and the automation
pass needed relieving immediately (a separate, parallel change addresses
`429` handling itself), and only test data was at stake, with no real
production launch yet, making the accepted risk (a wider, unobserved
`LaunchRepository.save` clobber window — see 4.3) tolerable. Left unchecked
above because the observation itself still never happened, not because the
decision to proceed without it was an oversight.

## 4. PR 2 — lower the reconciliation cadence (only after 3.4 is confirmed)

Its own PR, opened after 3.4, not a continuation commit on PR 1's branch.
**Actually opened 2026-08-31 without 3.4's confirmation — see the note above.**

- [x] 4.1 Change `clickup_sync_job.SYNC_SCHEDULE` to `"0 6,18 * * *"` and `SYNC_TOLERANCE` to `datetime.timedelta(hours=24)`, updating the module's own comment to explain the new cadence the way the current one explains `*/10` (referencing that the webhook is now the primary path, this pass the safety net).
- [x] 4.2 Update `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py`: `EXPECTED_INTERVAL_SECONDS` to `12 * 60 * 60`, and its docstring's cadence reference — this file's own comments already anticipate this ("If the cadence is revised again, this figure is the thing to correct").
- [x] 4.3 Add a note to `docs/deferred-work.md`'s existing `LaunchRepository.save` entry recording that this change widened its self-healing window from ~10 minutes to up to ~12 hours, so the item's priority can be reassessed with current information rather than the figure it was originally accepted under.
- [ ] 4.4 Merge and deploy this PR separately from PR 1.
- [x] 4.5 ~~Archive this change...~~ Already archived with PR 1, out of order — see the note above 4.1. Nothing left to archive here; this section's own tasks.md is being updated in place as the durable record instead.

## 5. Verification

Run against each PR before it merges, not only once at the end.

- [x] 5.1 `uv run pytest` — full `tests/unit` + `tests/agents` tier green (1699 passed, for PR 1's scope). Also ran `uv run lint-imports` — all 18 contracts kept.
- [x] 5.2 `ruff check` and `ruff format --check` — both clean.
- [x] 5.3 `mypy` (full project, 396 source files) — clean.
- [ ] 5.4 For PR 2 specifically: re-run `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py` after 4.2, confirming the new interval and tolerance both satisfy `scheduled-jobs`' registry-level checks (`test_recurring_work_registry.py` if it enumerates all registered work).
