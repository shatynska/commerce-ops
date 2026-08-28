## Context

See `proposal.md` — Why, for the motivation. What shapes the approach here is that almost nothing needs building: `launch-instance` already specifies gate advancement, approval, `awaiting_confirmation` and graduation in full, and `launch_run.py` implements all of it under test. This change is a trigger and an adapter; it changes no domain rule, and adds one public read (Decision 3).

Three existing pieces of this repository set the shape, and the design copies each rather than inventing beside it:

- **`automation_confirmation.py`** — a proposal put to a person in Slack, the presser's identity resolved through the roster, accept/reject buttons carrying a JSON subject, refusals returned as reasoned `Decision` objects rather than raised. The gate ask is the same exchange with `{product_id, gate_id}` in place of `{product_id, step_id}`.
- **`field_gap_suppression.py`** — a stored record meaning "this has been reported and nothing has changed", written *only after a delivery succeeds*, deliberately a table rather than process state so a restart does not resume a flood.
- **`clickup_sync_job.py` / `automation_pass.py`** — a recurring pass that walks every active launch, contains a per-launch failure, reports each one as it happens, and fails the run in aggregate.

The relevant cadences: ClickUp sync `*/10`, automation `*/15`, overdue check hourly.

## Goals / Non-Goals

**Goals:**

- Gates advance without anyone having to remember to advance them.
- Every recorded approval names a real, active person from the roster.
- The person who presses a button learns what their press did.
- Nothing in the launch's **rules** changes. The one domain addition is a private readiness computation becoming a public read, argued in Decision 3.

**Non-Goals:**

- Per-step release conditions (`starts_at_gate`, `after_step`). Deferred to the follow-on change, and unsafe before this one — see `proposal.md` — Impact.
- Any advance a human can *target*. `advance_gate` takes no target by design; nothing here adds one, and there is deliberately no "set this launch to gate N" operation, in the admin surface or anywhere else.
- Live metric evaluation. `record_metric_attestation` stays unwired: gates carrying metric conditions will not open until attestation has a surface, which is domain-map slice 7's business, not this change's.
- Graduation, in every part — the ask, the posture choice, the catalog stamp and its refusal. See Decision 8.
- Backfilling stranded launches. Every launch is test data; the first pass advances what it can and the rest are reset by hand.

## Decisions

### Decision 1: Advancement is a convergence pass, not a consequence of recording

`record_step_outcome` has four call sites (`clickup_webhook`, `clickup_sync_job`, `automation_pass`, `automation_confirmation`). The obvious trigger is "advance after recording", either inside the use case or at each call site.

**Rejected, in both forms.** Advancing needs the Slack notifier (the ask), and the recording paths have no business holding one. Putting it inside `record_step_outcome` drags both dependencies into all four callers and turns a narrow write into a cascade; putting it at each call site writes the same logic four times and still drags the dependencies. Worse, neither covers a gate that becomes ready *without* an outcome being recorded — through a metric attestation, a playbook step being retired, or a launch that was already complete before this shipped.

A pass covers all of those uniformly and leaves `record_step_outcome` untouched. **The cost is latency**: a gate opens up to one pass-interval after its last condition is met. Against a launch measured in days and weeks, and given the existing passes already run at 10 and 15 minutes, this is immaterial — and it is the same trade `clickup-sync`'s reconciliation pass already makes for completions whose webhook was missed.

### Decision 2: Its own scheduled job, not a rider on the automation pass

Gate progression could ride `automation_pass`'s existing walk — it already iterates active launches with the playbook and launch loaded.

**Rejected.** `scheduled-jobs` records only whether a run succeeded, so sharing a job means a gate-progression failure fails the automation run and vice versa, and neither's run record says which concern broke. This repository already separates `clickup_sync_job`, `automation_pass` and `overdue_check` into their own jobs for that reason. A separate job also gets its own schedule, which matters because this one is on a human's critical path in a way the others are not.

**Cadence: `*/5 * * * *`** — faster than its neighbours because it is the cheapest pass in the system (Postgres reads, no external API calls except an occasional Slack post) and because the interval is what a person waits between a gate becoming ready and being asked about it.

### Decision 3: The pass reads before it commands

`advance_gate` refuses by raising `GateBlockedError`, and `use_cases.py`'s `advance_gate` journals a `KIND_ADVANCE_REFUSED` entry on that path before re-raising — unconditionally, as `launch-journal` requires, because "unsatisfied conditions are recomputed from current state, so once satisfied nothing can establish that they ever blocked an advance, or when".

The obvious pass commands an advance for every launch and lets the refusal be the answer. **Rejected**: at `*/5`, with most launches on most passes having an unsatisfied condition, that appends ~288 identical entries per launch per day to an append-only record specified to be read most-recent-first and kept for the life of the launch. Within a week every human-meaningful entry sits below thousands of machine refusals, and the refusal entry stops meaning "an attempt was blocked" because every moment is such an entry.

The obvious place to read that from is the launch report, and it is the wrong place: `LaunchReport` carries `steps`, `gate_sequence`, `at_risk` and `awaiting_confirmation` among its fields, and none of them answers "may this gate open". `ReportedStep` gives each served step's recorded outcome, so blocking-step satisfaction is derivable — but a gate's **authored metric conditions** appear nowhere on the report, and `awaiting_confirmation` is false for an automatic gate whatever its conditions' state. Judging readiness from the report would therefore call a metric-gated gate ready on its blocking steps alone, command the advance, be refused, and flood the journal at exactly the gate this design's Risks section predicts every launch will stall at.

So the judgement is made where the rule lives. `Launch._unsatisfied_conditions(playbook)` already computes precisely it — every step obligation, every authored metric condition, and the approval a confirmation gate needs — and `advance_gate` uses it to decide. This change makes that computation **public** and the pass calls it, so the pass's answer and the advance's answer are the same computation rather than two that must be kept in agreement.

That is an addition to the launch domain, and the only one: a private computation becomes a public read. No rule changes, no state changes, `advance_gate` is untouched. The design's "no domain change" goal is stated precisely for that reason — no change to the launch's **rules** — and this is the one thing it permits.

The alternative was to recompute readiness in the application layer from `conditions_for_gate`, `progress_for`, `attestations` and `approval_for`, all of which are already public. Rejected: it copies a domain rule into a caller, where it can drift from the rule the advance actually applies, and a drift between them is exactly the disagreement this decision exists to prevent.

The alternative was amending `launch-journal` so a repeated refusal is not appended. Rejected: it weakens a record built for people in order to accommodate a poll, when the poll can simply not ask.

The benign residue is a race — a condition regressing between read and command produces a refusal and one journal entry. That is a real blocked attempt and deserves its entry.

### Decision 4: Cascade by calling `advance_gate` again, not by changing it

A launch whose conditions are satisfied for several consecutive gates should not need one pass per gate. `advance_gate` opens exactly one gate and takes no target, and that is a deliberate domain invariant — "gates advance monotonically, one at a time, never skipped".

The pass loops: attempt, and on success attempt again, until the launch's current gate may not open or the launch reaches the final gate of the sequence. Every gate crossed is a real `advance_gate` call that evaluated its own conditions and emitted its own `GateOpened`, so the journal records each crossing individually and nothing is skipped. The alternative — a domain-level "advance as far as possible" — would put the loop where the invariant lives and make the single-step guarantee something a reader has to reconstruct.

The loop is bounded by the gate sequence being eight long and strictly forward, so it terminates without a counter.

### Decision 5: One cool-off rule, covering first ask, silence and rejection

The naive suppression is "ask once per gate, ever". That is wrong in two directions: a gate whose ask nobody answered is never asked about again, and a *rejected* gate can never be reconsidered even after the reason for the rejection has passed.

A single record — `(product_id, gate_id, delivered_at)`, at most one row per pair — with the rule *ask only where no record younger than 24 hours exists* covers all three cases at once. A rejecting decision refreshes `delivered_at`, so the day runs from the decision rather than from the ask that prompted it.

24 hours, and a module constant rather than configuration, follows `automation_pass`'s `COOL_OFF` precedent verbatim, including its reasoning: there is no per-deployment answer to how long a disagreement should hold, and a configured value would owe the four obligations `AGENTS.md` places on every runtime variable.

**Written only after a successful delivery**, per `field_gap_suppression`'s rule and for its reason: recording first and then failing to deliver would silence the gate for a day with nobody having been asked. A write that fails *after* a successful delivery leaves the gate eligible and produces a duplicate ask on the next pass — the accepted trade, same as its precedent.

### Decision 6: The button press advances inline; the pass is not the only path

The pass could be the sole advancer, with a press recording only the approval. **Rejected**: the presser would get "Recorded" and learn nothing, while the gate opened minutes later with nobody watching. A person who presses a button and is told only that the press was filed cannot tell an approval that opened a gate from one that hit a condition which regressed while they were deciding.

So a press records the approval and attempts the advance immediately, replying with what happened. This is not a second mechanism: it is the same `advance_gate` call the pass makes, invoked from a place that has someone to tell. The pass remains the safety net for a press whose advance failed after the approval was recorded.

Two advancing paths means they can meet. A press landing inside a pass window could have both cross the same gate, and a gate crossing is not idempotent — it emits `GateOpened` and journals it. So a launch is advanced by one path at a time — and the mechanism has to be named, because the obvious ones do not work here. The pass runs in the worker and the decision listener in the HTTP process (tasks 6.1, 6.2), so no in-process lock spans them. A row lock taken when the launch is loaded does not span a cascade either: `LaunchRepository.save` commits its own writes, as `docs/deferred-work.md` records, so the lock would release at the first crossing and the second would race.

A Postgres **advisory lock keyed on the product**, taken inside `transaction()` and held for the whole cascade, satisfies both. `transaction()` is this repository's established answer to exactly this problem — it binds a session to one connection with `join_transaction_mode="create_savepoint"` so an inner `commit()` releases a savepoint rather than ending the outer transaction — and `docs/deferred-work.md` states the rule that follows from it: any new caller needing two writes to land together must use `transaction()`, not `session()`. An advisory lock is database-level, so it holds across processes as well as across the cascade.

**The lock is taken in the two driving adapters, not in the use case.** `transaction()` lives in `shared/infrastructure/driven/database.py`, and no module's `application/` layer imports `shared.infrastructure` anywhere in this repository — the Shared Kernel rule is same-or-lower matching layer, never the reverse, and task 6.4 re-checks it. So `gate_progression_job.py` and `gate_confirmation.py` each open `transaction()`, take the lock, and call `progress_launch` inside it. That is the precedent exactly: `clickup_sync_job.py` and `automation_confirmation.py` — the two modules this change is modelled on — already use `transaction()` at the driving adapter. The key derivation is shared between them so the two cannot drift apart on which lock they take.

`progress_launch` therefore takes the **product identifier**, not a pre-loaded launch, and reads the launch under the lock, re-reading after each crossing. The walk's `list_active` result is a candidate set, nothing more: a launch it loaded before the lock could have been advanced by a decision in the meantime, and judging readiness from that copy would command a crossing nobody judged.

A gate declining to open is the cascade's **stopping condition, not its failure**, and the two must not be conflated because a refusal arrives as a raised `GateBlockedError`. The cascade catches that one and commits: the crossings it made were valid, and `advance_gate` has already journaled the refusal, which no later pass can reconstruct once the condition is satisfied — the entry Decision 3's whole argument is built on protecting. Any *other* exception is a failure and unwinds. Without that distinction the read-before-command race, which Decision 3 knowingly accepts, would discard valid crossings, destroy the refusal entry, and fail a run the delta says must not fail.

One consequence follows from holding the cascade in one transaction and is chosen rather than inherited: **a cascade that fails part-way — for any reason other than a gate declining — is undone entirely**, crossings already made included. This is the opposite of `launch-clickup-sync`'s rule that work completed for a launch before its failure stands, and the difference is the cost of redoing it — that pass's unit is a launch's whole ClickUp projection, many API calls against a rate budget, where discarding completed work is expensive and externally visible. A cascade here is a few cheap Postgres writes with no external effect, so the next pass simply redoes them five minutes later, and all-or-nothing buys an atomic unit over a partially-advanced launch nobody chose.

**The approval write sits outside the cascade's atomic unit, deliberately.** A recorded decision is a fact about what a person did, and losing it because a later crossing failed would be wrong twice over: the person believes they approved, and the ask's cool-off record — written on an earlier pass, outside any of this — would keep the gate from being asked about again for a day. So the decision path records the `GateApproval` in its own transaction first, then takes the lock and runs the cascade. The window this opens, in which an approval exists and the gate has not yet opened, is a state the design already accepts and relies on: the pass is the safety net that crosses the gate on its next run.

The lock itself is taken with the **transaction-scoped** advisory lock, released by the transaction ending rather than by an explicit unlock. The session-scoped variant on a pooled connection would survive the transaction and travel to whichever caller next borrowed that connection, deadlocking both paths for that product — the drift the shared key exists to prevent, arriving one level down. So the adapters share the acquire helper, not only the key derivation.

The Slack ask is posted **outside** the lock. A delivery that hangs must never hold a launch against the other path.

### Decision 7: Known and active, not admin

`automated_decisions.py` requires a decider to be known to the roster and active, and does not require `admin`. Gate approval mirrors it.

The tempting alternative is admin-only, on the grounds that gates are the launch's commitment points and heavier than accepting a subcategory recommendation. **Rejected as a category error**: roster `admin` means "may administer the system" — the roster and the playbook — and this repository has never used it to mean commercial authority over a launch. Making gate approval the first place it means that would silently redefine the flag for every other place it is read.

If launch authority should be distinct from both, it wants its own roster concept and its own change. Recorded here so the choice is visible rather than inherited by accident.

### Decision 8: Graduation is left out entirely

`graduated` needs a discriminator the persisted launch does not have. `launch-instance`'s enumeration requirement states the non-distinction as deliberate; `LaunchRepository.list_all`'s docstring records the consequence; and `Launch.__init__` sets `_graduated = False` on every rehydration, so the flag is process-local.

Every available proxy breaks:

- `list_active` filters on `current_gate != 'graduated'`, so a launch *standing* at `graduated` awaiting its approval is never walked — the graduation ask could never fire.
- `list_all` walks already-graduated launches, whose conditions are all still satisfied, so `advance_gate` re-opens the gate, re-emits `LaunchGraduated` and re-stamps the catalog on every pass; `product-catalog` rejects the same-stage transition, which `launch-instance` requires be reported as "an error naming the manual catalog correction required" — a false instruction, every five minutes.
- The catalog stage stamp misreads a graduation whose stamp was refused, which is exactly the state `launch-instance` requires to be tolerated.

Fixing it means persisting a graduation marker: a domain change and a migration, in a change whose safety rests on making almost none. And it buys nothing today, which is checked rather than assumed: `_AUTHORED_METRIC_CONDITIONS` in `launch_playbook.py` attaches metric conditions to `stock-ready`, `phase-one-complete` and `graduated`, attestation has no surface, so a launch stalls at `stock-ready` — gate 4 of 8 — and cannot reach the final gate by any path. Task 7.10 re-checks this against the code rather than trusting it from here, because the day `phase-one-complete` stops authoring a metric condition is the day this reasoning silently expires.

So the pass walks `list_active` and this change carries no graduation behaviour. The remedy belongs with the attestation surface it depends on, as one change; recorded in `docs/deferred-work.md`.

The cost, stated plainly: once attestation exists, `phase-one-complete` can open and park a launch at `graduated` with no ask and nothing reporting it. Unreachable until then.

### Decision 9: A decision names the gate, and a stale gate is refused

The button value carries `{product_id, gate_id}`, following `_decision_value`'s reasoning — the pair rather than a row id, because a control that named a row would keep working after that row was settled.

A decision whose `gate_id` is not the launch's current gate is refused outright. Without this, a day-old ask still sitting in Slack would record an approval against a gate the launch has already passed — attaching a human decision to a commitment point that is no longer live, and, for `graduated`, potentially stamping a posture nobody currently intends.

### Decision 10: The pass's launch set is gate-based, matching ClickUp sync rather than the briefing

`briefing` and `launch-admin` decide which launches are in play from the catalog's stage stamp; `launch-clickup-sync` excludes only the final gate. The pass follows the latter, because it does what that capability does — converge every launch that has not finished — rather than deciding what is worth a person's attention.

The consequence, accepted: a launch whose catalog product has been retired is still advanced, and can still be asked about in Slack. Adopting the briefing's predicate would mean a catalog read per launch on a pass whose whole argument is that it is cheap, to suppress a case that is not known to occur. Revisit it if a retired product ever produces an ask.

### Decision 11: Two windows are accepted rather than closed

Both were found in review, both are real, and both are recorded here rather than fixed, because closing either costs more than it buys at this change's scope.

**A second press can record an approval against a gate just crossed.** The gate-currency check (Decision 9) runs before the lock, since the approval write is deliberately outside the cascade's atomic unit. Two genuinely concurrent presses can therefore both pass it. No gate moves twice — the lock still holds that — and the residue is one extra approval row and its journal entry. Judged the way Decision 3 judges the read-before-command race: a window named, not a defect hidden.

**A recording path can write back a stale `current_gate`.** `LaunchRepository._update` sets `position.current_gate = launch.current_gate` unconditionally and replaces every child row, so any caller that loaded a launch before a crossing and saves after it regresses the gate. `record_step_outcome`'s four call sites take no advisory lock, and two of them are recurring passes over the same launch set.

This is a pre-existing property of the repository — two recording paths could already clobber each other's step progress — but this change sharpens it, because `current_gate` now actually moves. Accepted for three reasons: the window is milliseconds wide; the next pass re-crosses the gate within five minutes, so it self-heals; and no gate in this change's scope has an external effect when re-crossed, `graduated` being excluded. Extending the lock to the four recording sites would mean touching every one of them, which is exactly what Decision 1 keeps this change out of.

The general hazard — a full-aggregate overwrite with no optimistic concurrency — is recorded in `docs/deferred-work.md` as its own future change, since it belongs to the repository rather than to this trigger.

## Risks / Trade-offs

- **A gate opens up to 5 minutes after its conditions are met** → Accepted, Decision 1. Immaterial for a process measured in days; the alternative gives every recording path a Slack notifier it has no business holding, and still misses a gate that becomes ready without an outcome being recorded.
- **Gates carrying metric conditions will not open at all** → `record_metric_attestation` has no surface, so a launch advances until it meets the first gate authoring a metric condition and stops. This is pre-existing and stated as a Non-Goal, but it means **this change alone does not get a launch to `graduated`** — worth knowing before the first pass runs and appears to stall. Which gates author metric conditions is repo-owned framework in `launch_playbook.py`; the implementer should read it rather than trust a list here.
- **No requirement caps asks per run, and a failed delivery never takes a cool-off** → The first pass meets an empty cool-off table, so every launch standing at a satisfied confirmation gate is asked in one run; and because a cool-off is written only after a successful delivery, a rate-limited batch retries every five minutes with no cool-off ever taken. Accepted rather than capped — a cap would need a rule for which launch waits, and none is obviously right — with task 7.5 counting the launches before the first run so the volume is known rather than discovered.
- **The first pass will advance every test launch at once** → Several launches move several gates and post several asks in one run. Expected, not a fault; but it is the moment to watch the monitoring channel, and a reason to deploy this when someone is looking.
- **A duplicate ask after a cool-off write fails** → Accepted, Decision 5, same trade as `field_gap_suppression`.
- **A retired product's launch is still advanced** → Accepted, Decision 10.
- **A launch parked at `graduated` is invisible** → Accepted, Decision 8; unreachable until attestation exists, and recorded in `docs/deferred-work.md` so it is not rediscovered as a surprise.
- **An approval recorded whose advance then fails** → The approval stands and the gate stays closed; the next pass retries the advance. Correct behaviour — the human's decision is a fact and should not be lost because the advance that followed it failed — but it means a rejected-then-fixed condition opens the gate later without anyone pressing anything again.
- **Slack asks could become noise if many launches sit ready** → Bounded by one ask per launch-gate per day, and the briefing already reports the same launches. If it is still too much, the cool-off constant is the single place to change.

## Migration Plan

1. One Alembic migration creating the ask cool-off table. No data migration, no backfill.
2. Deploy. The worker registers the new schedule; the first pass advances every launch it can and posts asks for gates awaiting confirmation.
3. Rollback: remove **both** registrations — the worker's schedule and the HTTP process's decision listeners. Removing only the schedule leaves asks already posted in Slack still pressable and still advancing gates, since a press is the second advancing path. With both gone the added read has no callers, no domain rule changed, and a rolled-back deployment leaves advanced launches correctly advanced — an opened gate is a legitimate state whether or not this pass exists. The table can be dropped separately or left.

Per `AGENTS.md`, this ships as a branch and a pull request; the archive is the last commit before the merge.

## Open Questions

- **Which Slack channel the ask lands in.** It uses `monitoring_channel` because `automation_confirmation` does, and the two are the same kind of message. Whether launch approvals eventually deserve their own channel is a configuration question that changes no requirement here.
