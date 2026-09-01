## Context

See proposal.md — Why. Four facts of the current code shape everything below.

- **The removal is one branch.** `_unsatisfied_gate_conditions` (`launch_run.py:658-684`) loops over `conditions_for_gate(self.current_gate)` and splits on `isinstance(condition, StepObligation)`. Deleting the `else:` arm and its attestation search is the whole domain change; `conditions_for_gate` then returns one type and the `GateCondition` union collapses.
- **Readiness reads only the current gate.** That same loop is keyed to `self.current_gate`, so a launch already past a gate is never re-judged against it. This is why the `draft` decision below has the consequence it has.
- **The gate-holding floor already guarantees the outcome.** `launch-playbook`'s floor makes a step set that leaves any gate unheld unservable, and launches are running, so every gate already carries at least one active blocking step. Removing an obligation cannot open a gate for free.
- **The seed's exclusion is a data fact, not a rule.** `alembic/data/playbook_reference.yaml` holds 352 entries against the reference document's 358 ID-bearing rows; `lp.inventory.039` sits at line 3272 and `lp.inventory.042` at line 3492 with the two excluded rows missing between them.

Constraints: the launch module's public surface is its `application/__init__.py` (import-linter enforced); the domain layer does no I/O; every change reaches the server through a pull request, so the migration runs on merge and cannot be staged by hand afterwards.

## Goals / Non-Goals

**Goals**
- One kind of gate condition, resolved by one mechanism, reported by one surface.
- The launch↔monitoring join survives the removal, carried by the step.
- The six reference rows are seeded as they were always written — steps with an identifier, a discipline, a timing anchor and a source citation.
- The threshold becomes readable and editable by the people held to it.

**Non-Goals**
- Recording the observed value. A completed task records that someone completed it; capturing "73 fulfillable units" needs an input the free ClickUp plan cannot offer, and belongs to the later Slack-modal change (`docs/deferred-work.md`).
- Activating the six steps. They are seeded `draft`, like every other seeded row.
- A metric registry, stage-keyed thresholds, or anything monitoring owns. This change carries the identifier forward and stops there.
- Reconciling the three parked launches with the check they will skip. See Risks.

## Decisions

### 1. The metric identifier moves onto the step, and nothing else does

`MetricCondition` carried two things: a `MetricId` and a threshold string. They go to different places. The identifier becomes an optional `StepDefinition` field; the threshold becomes the step's `description`.

Splitting them is the point. The identifier is a machine reference — opaque, unresolved, and the only reason `MetricId` was made a shared value object rather than a launch-local one (`complete-playbook-definition` design.md:33). The threshold is prose a person reads before doing the work, which is exactly what `description` already is, and it inherits admin editing and ClickUp projection for free.

*Alternative considered*: a `threshold` field of its own on the step — rejected because it would be a second place to state the work, displayed separately from the description that states the rest of it, and because nothing would read it that does not already read the description.

*Settled, not open*: `lp.ppc.048` becomes **one** step carrying its four criteria in its description. The seeding rule requires every seeded identifier to be a reference-document row ID, and the document gives that row one; splitting it would invent three identifiers nothing traces to.

*Alternative considered*: keeping `MetricCondition` on the gate and adding a surface for attestation (`add-metric-attestation-surface`) — rejected as the proposal argues: it preserves two mechanisms for one kind of obligation, and the reference document these obligations come from does not make the distinction.

### 2. The identifier is inert

A step declaring a `metric_id` is resolved by its recorded outcome, exactly as any other step. The identifier changes no rule: not gate readiness, not projection, not the journal's kind, not what the automation pass does. Nothing validates that the metric it names is defined, because nothing defines metrics.

This is deliberate under-design. The temptation is to make a metric step special now — a different journal kind, a different tag on the admin page, a check that the identifier resolves. Each would have to be unpicked when the registry arrives and takes ownership of what a metric *means*. Carrying an inert reference costs one nullable column and keeps the eventual join available.

### 3. The six rows are seeded `draft`, and the three parked launches skip the check

`launch-playbook` requires every seeded step to be `draft` — *"rows nobody has yet judged are work written down, not work in play"*. The six are seeded the same way, which means that on deploy `stock-ready` loses its metric condition and gains a step that holds nothing.

This happens on three gates at once, not one: `stock-ready` loses `units-fulfillable`, `phase-one-complete` loses `sales-velocity` and `organic-share`, and `graduated` loses `tacos` and `review-rating`.

The consequence, stated plainly: `Disposable food trays 31`, `32` and `33` advance past `stock-ready` on the next progression pass with no stock check of any kind, and because readiness reads only the current gate, activating `lp.inventory.040` afterwards never pulls them back. The pass continues while gates keep opening (`launch-gate-progression`), so a launch may travel further than `stock-ready` in that first pass — as far as the next gate holding an unresolved blocking step, or `phase-one-complete`, which requires a confirmation nobody has given and so stops there with its own metric obligations already gone. The check applies to launches that reach `stock-ready` after activation, and to no launch that has already passed it.

This was chosen over seeding the six `active`. Seeding them active would hold the three launches on a real check, but it contradicts the seeding rule for every row, and it would create three ClickUp tasks for a gate whose obligation nobody has yet judged as ready to enforce. The parked launches are parked on an *unreachable* condition today, so the check is not being removed from a working process — it is being moved from a mechanism that never ran to one that will, once activated.

*Alternative considered*: seeding `lp.inventory.040` active and the other five draft — rejected as the worst of both: an exception to the seeding rule justified by which gate happens to be occupied this month.

### 4. Retire the `attestation` provenance source rather than repurpose it

`PROVENANCE_SOURCES` becomes `("clickup", "automated")`. A metric step completed in ClickUp records source `clickup`, like every other human step.

Repurposing `attestation` for a human metric step was considered and rejected. It would mean the same act — a person ticking a ClickUp task — records two different sources depending on whether the step happens to name a metric, which is a distinction the recorder cannot see and nobody reading the journal would expect. A source names the channel an outcome arrived through, not the significance of the step.

### 5. The `metric-attested` journal kind is removed rather than retained for history

No entry of that kind was ever written, the command having had no surface, so nothing is lost and no read path needs a branch for legacy rows. `gate_id` leaves the entry shape with it, that kind being its only populator (`journal.py:104`).

### 6. The preparation step delivers the six rows; migrations only change the schema

The six rows are **not** inserted by a migration. `launch-playbook`'s *The step set is seeded before the application serves* settles this explicitly — *"the migration machinery cannot express it, because a migration runs exactly once per environment while a reference document that gains a row must be able to deliver it later"* — and carries the scenario *A reference row added later is delivered* for exactly this case. `seed_playbook.py` reads `alembic/data/playbook_reference.yaml` and inserts every vendored step no stored step names, leaving every stored step untouched.

So adding the six entries to that file is the whole of their delivery: the preparation step, which already runs between migration and server on every deploy, inserts them on the next one. Writing an insert migration would duplicate a write path the spec assigns elsewhere, and would not reach an environment migrated before it was written.

Two migrations remain, both schema-only, in this order:

1. Add the nullable `metric_id` column to `playbook_steps` — before the preparation step can write a value into it.
2. Drop `launch_metric_attestations`.

The drop is the irreversible one and belongs last, after the change has demonstrably done its additive work.

**A database built from scratch is covered, and the two seeds do not share a file.** The migration-era seed (`d2f8b3c64e17`) reads `alembic/data/playbook_v1.yaml` — 107 entries, none of them the six. The preparation step reads `alembic/data/playbook_reference.yaml` — 352 entries, 358 after this change. So on a fresh build Alembic replays the v1 seed at its own old revision, the column migration follows, and the preparation step then inserts every step no stored step names, the six among them, carrying their identifiers. The hazard of a shared file — six rows landing at a revision where the column does not exist, and `launch-playbook` spec:787 then forbidding a corrected definition from reaching a step that already exists — does not arise.

Note also that "migrated" has never implied "seeded" in this project: a migrate-only database has carried the 107-step v1 set rather than the served set since `move-playbook-steps-to-postgres`. This change widens the gap from 245 steps to 251; it does not create it. The test-database instruction in `AGENTS.md` is therefore already incomplete, and correcting it is not this change's to make.

### 7. The drop is gated on a production check, not on this document

The proposal asserts the table is empty; that assertion came from a document, and dropping a table is not reversible. A task in `tasks.md` requires confirming `SELECT count(*) FROM launch_metric_attestations` is zero against production **before** the drop migration is written, and revising this design if it is not. A non-empty table would mean an attestation reached the table through a path nobody has found, which is a different change.

## Risks / Trade-offs

- **The three parked launches pass `stock-ready` with no stock check.** → Accepted deliberately (Decision 3), and it is the state they are effectively in today, since nothing can satisfy the condition that holds them. Mitigation available at any time: activate `lp.inventory.040` before the launches next advance, which holds them on the real check instead. That is an admin action, not a deploy.
- **A threshold becomes editable by anyone who may edit steps.** → This is intended (`playbook-authoring` delta), but it is a genuine widening: `60–80 fulfillable units` was previously changeable only by a repository change and a deploy. Mitigation: none imposed here. The numbers are the team's; the gate sequence they sit in remains code-owned.
- **The value observed at a gate is recorded nowhere.** → Accepted, and recorded in the proposal's *Deferred, deliberately*. The cost lands later: a launch history carrying no stock levels is a history monitoring cannot mine. Mitigation: the Slack-modal change, which the rejection-reason entry in `docs/deferred-work.md` already needs for its own reasons.
- **Six new steps appear on in-flight launches' ClickUp lists once activated.** → The convergence pass is designed for exactly this (*"a step activated after the launch started is projected on the next pass like any other"*), so no special handling; worth knowing before activation rather than after.
- **`add-metric-attestation-surface` remains on its own branch.** → It is superseded, and merging both would reinstate what this change removes. Mitigation: abandon that branch as part of this change's completion.

## Migration Plan

- **Deploy**: the column migration and the drop migration run on merge, in that order; the preparation step then runs and inserts the six rows. No backfill: the six steps are new rows, and the dropped table has nothing to preserve.
- **Immediately after deploy**: the next progression pass advances the three parked launches past `stock-ready`. This is expected, and is the visible signal that the change took effect.
- **Rollback**: reverting the code restores the metric conditions, and the gates they sit on become unsatisfiable again — the state before this change. The dropped table would need recreating by a down-migration; it holds nothing, so an empty recreate is a faithful rollback.
- **Activation, separately and later**: activating the six steps through the admin surface is an ordinary authoring write, subject to the same validation as any other, and is not part of this change.

## Open Questions

- **Which gate does each of the four later rows belong to?** `lp.strategy.025` and `lp.strategy.033` restate `phase-one-complete` conditions and `lp.finance.036` restates a `graduated` one, but each row's own **WHEN** column (`Week 5-8`, `Day 60+`) states when the work happens, not which gate it holds. The seeding task resolves this per row against `author-playbook-steps` design.md:73, which names what each restates; nothing about the approach changes either way.


## A note on one inherited cross-reference

`launch-journal`'s *An entry carries the labels the occurrence concerned* ends with a paragraph reading "which **this change** deliberately leaves alone; it is recorded in `design.md` — Decision 7". That sentence was written by the change that introduced the exception, and the delta carries it forward verbatim because a MODIFIED requirement restates the whole block.

Both references are to *that* change, not this one. This design's Decision 7 is the attestation-table precondition and has nothing to do with a refused advance's condition names. Task 6.5 rewrites the sentence to name the originating change, so the pointer resolves for whoever reads the archived spec.
