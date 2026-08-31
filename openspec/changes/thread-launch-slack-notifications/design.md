## Context

See `proposal.md` for motivation. Three things about the current state shape this design:

- **No shared Slack client.** Each bounded context owns its own thin notifier (`launch/infrastructure/driven/slack_notifier.py`, `briefing/infrastructure/driven/slack_notifier.py`), by design — `.importlinter`'s `products-infrastructure-boundary` forbids `launch.infrastructure` from naming `briefing` at all. This change stays inside `launch`'s own notifier.
- **`Product` and `Launch` are different aggregates in different modules.** `Product` lives in `catalog`; the gate/step machinery around one product's launch lives in `launch`'s `LaunchPosition` (table `launch_positions`, `product_id` as its primary key — at most one per product, by construction). `launch.infrastructure` cannot import `catalog.infrastructure` directly (the same import-linter contract), which is why the two new fields this change adds belong on `launch_positions`, not on the catalog product: no cross-module read or write is needed to use them, and they stop mattering at exactly the point `launch_positions` already stops mattering — a product's launch has ended.
- **A precedent for cross-process locking on one launch already exists.** `launch_advisory_lock.py` holds a Postgres advisory lock, keyed on the product and scoped to a transaction (`pg_advisory_xact_lock`), specifically because a launch's two advance paths (the recurring pass, in the worker; a person's Slack decision, in the HTTP process) run in different processes and an in-process lock or a row lock taken at load time cannot span either the cross-process gap or a multi-step cascade. The same shape of problem — several call sites, in different processes, that might each try to establish a launch's Slack thread at once — recurs here.

## Goals / Non-Goals

**Goals:**
- One operation, callable from every driving adapter that posts about a launch, that resolves an existing thread reference or establishes one exactly once under concurrent callers.
- One operation that resolves who a message should tag, given an optional step.
- Minimal, additive persistence: two nullable columns, no backfill migration.

**Non-Goals:**
- Not renaming or consolidating `launch`'s and `briefing`'s separate notifiers — this change only extends `launch`'s.
- Not building a general-purpose "who to tag" registry beyond the confirmer/submitter rule this change specifies.
- Not addressing the still-open question from `advance-gates-and-confirm-in-slack`'s design.md about whether gate approvals deserve their own channel — the two-channel split this change introduces (launches vs. monitoring) is a different axis (per-product vs. cross-product) and doesn't resolve or depend on that one.

## Decisions

**`slack_thread_id` stores the anchor message's bare `ts`, not a `(channel, ts)` pair.** There is exactly one launches channel; every reply a launch ever posts goes to it. Storing the channel alongside would only matter if a launch's thread could ever live in more than one channel, which nothing in this design does. Confirmed with the user (YAGNI over defensive schema).

**Both new fields live on `launch_positions`, keyed with it.** `submitter` (a roster Slack identity, recorded once at launch start) and `slack_thread_id` (absent until first needed) round-trip through the `Launch` aggregate (`launch/domain/launch_run.py`) exactly the way `launch_date` already does: plain fields, read by the repository on load, written back on save. `submitter` is set once at construction (`Launch.start`) and never mutated again; `slack_thread_id` is the one field on the aggregate that a driving adapter mutates outside the domain's own command methods, via a narrow setter the "ensure thread" operation below calls.

**A dedicated advisory lock, not the existing one.** `hold_launch_advance_lock` exists to serialize the two paths that *advance a gate* — reusing its key would mean establishing a launch's Slack thread blocks behind (or blocks) an unrelated, potentially multi-step gate cascade for the same product, and vice versa. This change adds a second, structurally identical lock — same `pg_advisory_xact_lock` pattern, transaction-scoped, keyed on the product — under its own namespace constant, so the two concerns can never contend with each other by accident.

**The "ensure thread" operation is transactional: lock, re-check, post, persist, all before the caller's own message goes out.** Shape:

```
begin transaction
  acquire the thread-establishment advisory lock for this product
  reload the launch row
  if slack_thread_id is already set:
    commit, return it                         # someone else won the race
  post the anchor message (name, SKU, marketplace, launch date)
  write the returned ts as slack_thread_id
commit                                          # releases the lock
return slack_thread_id
```

Locking before the re-check, not after, is what makes the operation idempotent under the concurrent case the `launch-instance` delta's race scenario specifies: two callers racing to be first both block on the same key, the first to acquire it does the post-and-persist, and the second — once unblocked — reloads the row, sees the field already set, and skips straight to reuse. Whichever call site triggered establishment then delivers its own message as a reply using the returned `ts`; the anchor post and the triggering message are two separate `chat.postMessage` calls (the second with `thread_ts` set), not one.

**Mention resolution is one small, shared function: `step`-or-`None` in, a Slack identity out.** Given a step, it returns the step's `confirmer` where non-null; otherwise (`confirmer` absent, or no step at all — a gate ask) it returns the launch's `submitter`. Every call site — `gate_confirmation.py` (no step, always submitter), `automation_confirmation.py` and `automation_pass.py`'s stuck-step report (both already have the step) — calls this once rather than re-deriving the fallback rule. The identity is resolved to a roster person for the `<@…>` tag the same way `automation_confirmation.py` already resolves a confirmer's roster entry today for decision authority; it is not a new roster read pattern.

**The launch-entry confirmation moves entirely off the DM path, except for post-acknowledgement failure.** Today `slack_entry.py` DMs the submitter twice: once on success, once on a failure that happens after Slack has already acknowledged the modal. Only the success path changes — it becomes the anchor post (which this same request establishes, being the very first message for that launch) followed immediately by a tagged thread reply naming that ClickUp will pick the launch up. The failure path is unchanged and stays a DM: `launch-entry`'s existing "Acknowledgement is independent of persistence" requirement already commits to reporting that failure "as a message" to the submitter without naming a channel, and a failed start has, by definition, no thread to reply into.

**No journal entry for thread establishment.** Considered and explicitly declined (confirmed with the user). The launch journal's eight occurrence kinds are a deliberately closed vocabulary, one per accepted domain command, mirrored by a database `CHECK` constraint and matched exhaustively in code that raises on anything unmapped; every existing append happens in `launch/application/use_cases.py`, next to the use case for the command it records, and nothing in `infrastructure/driving` writes to it directly today. "A Slack thread got created" is a side effect of notifying someone, not a domain command's outcome, and `launch_positions.slack_thread_id` being non-null is already the durable record of the fact — a ninth journal kind would buy no auditability the column doesn't already give, at the cost of a schema migration and an exhaustive-match update the journal's own design treats as deliberately expensive.

**Channel split: launches vs. monitoring, decided by whether a message names one product.** `gate_confirmation.py`'s ask, `automation_confirmation.py`'s pending-result ask, and `automation_pass.py`'s stuck-step report all already carry the product or the step (hence the product) they concern — all three move to the launches channel, as thread replies. `clickup_sync_job.py`'s Custom Field configuration-gap report and `shared/infrastructure/driving/overdue_check.py`'s overdue-work digest are configuration- and cross-product-scoped respectively, not tied to a single launch — both stay on `monitoring_channel()`, untouched. The daily briefing (`briefing`'s own notifier) is a separate module and separate credential set already; it is not touched by this change either.

**Settings wiring follows the existing four-part pattern for a new runtime variable**, without a `runtime-configuration` spec delta: `PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` is declared on `Settings` in `shared/application/settings.py`, added to the `REQUIRED_NOT_STARTUP_CRITICAL` set `tests/unit/shared/application/test_settings.py` compares against, and rendered in `deploy.yml` from `secrets.PRODUCT_AGENT_LAUNCHES_CHANNEL_ID` (the Environment secret is already set) — mirroring exactly how `PRODUCT_AGENT_MONITORING_CHANNEL_ID` is declared today. No spec delta is needed because `runtime-configuration`'s requirement — that every variable the runtime needs be declared in one place — does not change; this only adds one more instance of it, the same way every prior variable addition (`ADMIN_BASE_URL`, `BOOTSTRAP_ADMIN_IDENTITY`, the ClickUp field IDs, and `PRODUCT_AGENT_MONITORING_CHANNEL_ID` itself) added an instance without a spec change.

## Risks / Trade-offs

- **Removing the DM confirmation is a visible, breaking behavior change for whoever submits a launch.** They previously got a private message; now the same information is public in the launches channel, tagged. Accepted deliberately (confirmed with the user) — it's the whole point of consolidating per-launch traffic into one visible thread.
- **A resolved mention that fails to render** (a stale or deactivated `slack_identity`) degrades to plain, untagged text rather than blocking delivery — Slack silently drops an unresolvable `<@…>` token rather than rejecting the message, so this needs no special handling, only a note that "tagged" is best-effort, not guaranteed-visible.
- **A second advisory-lock namespace is one more piece of cross-process coordination to reason about.** Mitigated by mirroring `launch_advisory_lock.py`'s existing, already-reviewed shape exactly rather than inventing a new mechanism.
- **Two channels is two places configuration can drift** (e.g., one environment has the launches channel set and another doesn't). Mitigated by `runtime-configuration`'s existing drift check, which already fails a deployment missing a required, non-startup-critical variable's declaration — same as it does for the monitoring channel today.

## Migration Plan

Both new `launch_positions` columns (`submitter`, `slack_thread_id`) are nullable with no default and need no backfill: every launch that predates this change simply has both absent, and the lazy-establishment mechanism gives it a thread the first time any per-product message needs to be sent for it — which is also how this gets exercised against real (or test) pre-existing launches once deployed, per the user's own request to use this path as the verification. `submitter` on a pre-existing launch stays permanently absent (nothing recorded whoever historically started it), which only affects the mention fallback: a message for such a launch with no step-named confirmer and no submitter tags no one, and is still delivered.

Rollout order: the Environment secret is already set; land the settings/deploy.yml wiring and the migration first (additive, inert on its own), then the notifier and driving-adapter changes.
