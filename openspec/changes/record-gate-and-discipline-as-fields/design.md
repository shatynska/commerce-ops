## Context

See proposal.md — Why. The state this design starts from: `converge_launch` in `launch/infrastructure/driven/clickup_sync.py` writes `gate:` and `discipline:` tags, `clickup_sync_job.reconcile_clickup_completions` drives it once per pass over every active launch, and `worker.py` already injects a real Slack notifier into the overdue check through `shared.application.ports.MonitoringNotifier`.

Two constraints shape everything below. First, ClickUp's Custom Fields are addressed by UUID and their options by UUID, and neither is created by being used the way a tag is. Second, `runtime-configuration` forbids the configuration check from touching the network — *"Checking Configuration Performs No Network Or Database Access… so that a configuration fault is distinguishable from a reachability fault"* — so the field check cannot live in `preflight` and must live in the pass.

## Goals / Non-Goals

**Goals**

- Resolve a step's gate and discipline to option identifiers using no name-matching on the *field*, only on its options.
- Detect a configuration gap completely, before any task is written, at a cost of one request per pass.
- Report a gap where a person will see it, exactly once per standing gap, without any of it being able to stop a launch's work.

**Non-Goals (design-level, beyond the proposal's)**

- Caching the field configuration across passes. One folder read per pass is cheap against a pass that already makes on the order of a hundred task requests, and a cache would delay noticing a gap by however long it lived.
- Any general "ClickUp configuration" abstraction. Two fields, named by two variables.
- Reusing `scheduled-jobs`' suppression table. Argued below.

## Decisions

### The system reads the field configuration and never writes it

ClickUp's public API documents six Custom Field endpoints — four reads (list, folder, space, workspace), set value, remove value — and no create or update. Creating a field is an open feature request on ClickUp's own board.

That documented picture is not the whole truth, and this change deliberately does not act on the rest of it. Measured against the live workspace on 2026-08-27:

```
POST   /api/v2/list/{list_id}/field     {}  → 400 {"err":"Field type is required","ECODE":"FIELD_002"}
POST   /api/v2/folder/{folder_id}/field {}  → 400 {"err":"Field type is required","ECODE":"FIELD_002"}
OPTIONS /api/v2/field/{field_id}            → 405, header `allow: PATCH`
PATCH  /api/v2/field/{field_id}         {}  → 403 {"err":"Access denied for updating field api","ECODE":"FIELD_262"}
POST   /api/v2/field/{field_id}/option      → 404 page not found
POST   /api/v3/list/{list_id}/field         → 404 page not found
```

So an undocumented create endpoint exists and validates, and an undocumented update endpoint exists but refuses this token. (The `403` was measured against a field identifier that does not exist, so it does not conclusively separate "this token may not update fields" from "permissions could not be resolved for an absent field". Settling that would need a real field to PATCH against, and the answer would not change the decision.)

**Rejected: create the fields, and repair a missing option, through those endpoints.** Three reasons, in order of weight:

1. Appending an option puts it **last** in `orderindex`. Ordering is the entire reason to prefer a Custom Field over a tag, so a repair that restores the value while destroying the order repairs the symptom and breaks the goal. A repair that preserved order would have to PATCH the whole option list back, overwriting whatever a person had done to it — which is the "is a person's edit preserved or overruled" question the predecessor explicitly declined to open, reopened here on an undocumented endpoint.
2. Undocumented behaviour is not a contract. This project has been here: the predecessor built six drafts of a tag-seeding subsystem on an unmeasured premise and deleted the whole thing when the premise turned out false. Building on a measured but unsupported premise is the same wager with better odds and the same failure mode.
3. `PATCH` is refused today anyway.

**Consequence accepted:** the fields are a hand-configuration step, like the launch folder itself. What this change owes in exchange is that a misconfiguration cannot be silent — which is what the second requirement is for.

### The fields are named by identifier, not by name

`CLICKUP_GATE_FIELD_ID` and `CLICKUP_DISCIPLINE_FIELD_ID` hold UUIDs, read once and matched exactly.

**Rejected: resolve the field by its name** (`"Gate"`, `"Discipline"`). A rename in ClickUp is an ordinary thing for a person to do and would be indistinguishable from the field having been deleted — silently disabling both fields with no way for the check to say which happened. A field UUID is stable for the life of the field, so pinning it makes a rename a non-event and makes absence mean absence.

**How a deployment declines, under a rendered `.env`.** `deploy.yml` renders every value as `echo "NAME=${{ secrets.NAME }}"` inside one unconditional block, so an unset secret produces `NAME=` rather than no line at all — confirmed by reading the workflow. That matters here because an empty identifier is a reported gap: rendered unconditionally, a deployment that declined the capability would be reported as broken on every pass, and the rollback below would not work. So these two lines are rendered **conditionally**, present only when the secret is non-empty, and declining is expressed by the line's absence. This keeps both properties that are wanted: silence still means "not asked for", and a mis-rendered blank is still caught mechanically rather than by a reviewer noticing it.

**Cost, stated because `AGENTS.md` prices it explicitly:** each variable needs four things — an Environment **secret**, a `secrets`-sourced line in `deploy.yml`, a declaration on the settings model, and a mirror in `tests/unit/shared/application/test_settings.py`'s declared set — and must be read by its literal name so the drift check can see it consumed. The `BOOTSTRAP_ADMIN_IDENTITY` incident of 2026-08 was exactly this list done as three of four, with `vars` in place of `secrets`; these two are secrets and neither carries a literal fallback.

Both are declared **optional**. `runtime-configuration` has each declaration carry "whether it is required or optional", and only *required* variables may be marked startup-critical — so "required but not startup-critical" is the wrong shelf for these: it would make an absent identifier a reported configuration fault, which is exactly what a deployment declining the capability must not produce. Optional is what makes silence mean "not asked for". That capability needs no delta.

### An unset variable is an opt-out; a set-but-unresolvable one is a fault — **per field**

A deployment naming no field writes no values and reports nothing. A deployment naming a field that is absent, is of the wrong type, is optionless, or lacks options reports it.

The distinction matters because the test environments and any future deployment without a configured ClickUp folder would otherwise generate a Slack report on every pass for a capability nobody asked for. Silence must mean "not asked for", and noise must mean "asked for and broken".

**There are three states, not two.** *Absent* is a decline and is silent. *Present and non-empty but unresolvable* is a fault and is reported. *Present but empty* is the third, and it is a fault too — it is what a mis-rendered deployment produces for a field somebody meant to configure, so answering it with the silence owed to a decline would be answering a mistake by ignoring it. Because `deploy.yml` would render a blank for an unset secret, declining is made expressible by rendering the line conditionally (above), which keeps the three states distinguishable at the boundary.

**The rule is per field, not per pair.** An earlier draft defined it only for "neither identifier configured", leaving one-set-one-unset undefined — and that state is not hypothetical: it is what a half-finished Migration Plan step 3, or the `secrets`-vs-`vars` slip this design already names as a risk, actually produces. Each field is independently opted out when its identifier is unset, and the gap definition's clauses are assessed only for a field that is configured.

**Rejected: treat a half-configured deployment as a fault outright.** Simpler, but it contradicts the principle above — a deployment that deliberately wants only the gate field ordered, which is the field this whole change is argued from, would be reported as broken for getting exactly what it asked for.

### The configuration is read at folder scope, once per pass, ahead of the launch loop

`GET /api/v2/folder/{folder_id}/field`, using the `CLICKUP_LAUNCH_FOLDER_ID` the job already resolves.

**Rejected: read at list scope** (`GET /api/v2/list/{list_id}/field`). A folder-scoped field is available to every list in the folder, so list scope answers the same question once per launch instead of once per pass, and cannot answer it at all when no launch is active — which is precisely when a fresh misconfiguration should still be found. Measured: the folder endpoint answers `{"fields": []}` for the current launch folder, so it is reachable and presently empty.

**Rejected: check per task, at the point of writing.** This is the shape the request arrived in, and it has a blind spot the set comparison does not: a gate whose steps are all already resolved, or which no active launch has reached, is never checked, so a missing option for `graduated` or `phase-one-complete` stays invisible until a product arrives there — months later, and at the worst moment. It also produces one log record per task for a single cause; a pass over a fully projected launch would emit on the order of a hundred and eighty identical lines.

Placement: after the `PlaybookNotReadyError` stand-down and before the launch loop, so a stood-down pass makes no ClickUp request at all, and the resolved options are threaded into `converge_launch` as data rather than re-read per launch.

### A gap is reported to Slack, never by failing the run

Through the existing `MonitoringNotifier` port, which `worker.py` already satisfies with `products`' Slack notifier for the overdue check — so this adds a consumer, not plumbing, and crosses no `.importlinter` boundary that is not already crossed.

**Rejected: raise, and let the run be recorded as failed.** It reaches a human eventually, through overdue reporting, and it is the loudest thing available — but the price is that a Custom Field misconfiguration stops projection *and* completion intake for **every** launch. That is the exact fault `openspec-change-reviewer` caught in rounds one and two of the predecessor. Retrying also cannot resolve it: no number of retries makes a person add a drop-down option. Nothing about a gap is therefore among the things that make a run fail. That is deliberately weaker than "the pass records success", which an earlier draft of this design asserted and which the merged *One launch's failure does not stop the other launches being converged* forbids: a run carrying a failed launch is a failed run whatever else was true of it, and a gap must not be able to swallow that. The analogy to the stand-down holds for the reasoning — retrying cannot resolve either — but not for the outcome: a stand-down declines the whole pass, while a gap lets it run.

**Rejected: a warning-level log record only.** It is what the predecessor does for a failed tag write, and it is right there, because a missing tag is cosmetic and self-healing on the next pass. A configuration gap is neither: nothing in the deployment will fix it, so a channel nobody reads means it is never fixed.

### The values are set after creation, never inside the create call

Carrying both values inside `POST /list/{id}/task` saves two requests per created task. It also puts them on the path that brings a step's work into being, so a rejection — a stale option id read before a hand edit, a field the list will not accept, any malformed entry — costs the step its task entirely, and `clickup-task-client` requires such a failure to propagate rather than be swallowed. That contradicts this change's guarantee that a Custom Field fault costs the field values and nothing else.

**This decision was made the other way first, and reversed after four review rounds.** The optimisation was kept and the contradiction handled by retrying a rejected create without the values. That retry then needed: a bound to one attempt; a split between rejections the task system *answered* and creates whose outcome was unknown; an exclusion for authorisation failures and rate limits, which are answered but unaddressable; a reclassification of 5xx, which is answered but leaves the outcome exactly as unknown as a lost connection; and a qualification written into the guarantee itself. It also obliged `clickup-task-client` to make an answered rejection distinguishable from no response — a demand on a shared capability existing solely to serve this branch. Five clauses on the failure path of the operation that creates a step's work, four of them present only to stop an optimisation costing a task.

**The arithmetic that justified keeping it was wrong.** An earlier draft priced the alternative as "a standing 3x on the request budget". It is not standing: it is **+2 requests per created task, once per task, ever** — roughly +360 on a launch's first pass, and nothing on any pass thereafter. Steady-state passes over an already-projected launch are unaffected, and the correction-path backfill this change already accepts pays exactly that price once for every task that exists today, which is evidence the deployment absorbs it.

**Chosen:** set the values after the task exists. The guarantee then needs no qualification **on this path**, because nothing about these two fields touches the call that creates a task. It carries exactly one qualification overall, on a different path entirely — a shared store this concern cannot restore, recorded in Risks below. The retry rule, both of its exclusions, the 5xx classification, the guarantee's carve-out and the client's distinguishability obligation are all deleted rather than fixed.

**A hazard this removes from view rather than solves.** A create whose response is lost may already have created the task, and projection keys on the recorded mapping, so the next pass creates a second one and the first is never named, dated, corrected or closed by any pass. That orphan belongs to the create path as it already stands; this change no longer touches that path at all, so it neither introduces nor closes the hazard. Named so a later change can take it up rather than rediscover it. The alternative that would close it — read the list for an existing task before creating — puts a read on the failure path and is out of scope here.

### The read and the write must speak the same representation

The no-op guarantee — and the "one-time correction" budget — rests on the value a task reports for a drop-down being comparable to the option identifier a write sends. Nothing established that, and its worst case is not a rejected write but a *successful* one: if the two differ in form, every task differs from its step on every pass, and the system issues two writes per task per pass forever, each succeeding and changing nothing. Mocked tests would not see it, because a mock returns whatever the implementation expects.

It is settled in the client rather than assumed. `clickup-task-client` now requires an option-set value to be reported as that option's identifier, normalising where the task system reports it otherwise — from what the task payload itself carries, never from a *separately obtained* field definition and never by a second request, which would turn one read into two and put another failure on the path; a definition the payload itself carries is part of the payload. The read is required to be **total**: no field value of any shape may make it raise. That is the load-bearing half. This read gates a launch's projection and its completion intake, so a value the client cannot interpret must not be able to stop either — one hand edit in ClickUp would otherwise stop convergence for everything. The state is not hypothetical: it is what the delete-and-recreate fallback recorded in Risks below leaves on every task at once, and what changing a field's type under existing values leaves too.

An uninterpretable value is reported as the payload carries it rather than as absent. **Not** because absence would cost a write per pass — an earlier draft of this paragraph claimed that and it is false: a value reported absent is written once, after which the task carries a declared option and normalises thereafter, which is the same single write the unnormalised path produces. The reason is information: a caller must be able to tell "nothing set" from "something the client did not recognise", and reporting absence destroys that distinction.

Task 7.10a checks the whole of it end to end: a second pass over an already-valued task must send no write.

**Measured 2026-08-27, and the mismatch is real.** ClickUp's wire form for a drop-down value is *not* the option identifier a write sends:

```
POST /task/{id}/field/{field_id}  {"value": "7ac255e6-…"}   → 200      (a uuid)
GET  /task/{id}                   → custom_fields[].value = 3          (an int: orderindex)
```

So a caller comparing what a task carries against what it would write finds them different on every task, on every pass, forever — two writes per task per pass, each succeeding and changing nothing. This is the failure this decision exists to prevent, and it is invisible to a mocked test, which returns whatever the implementation expects.

**The normalisation is possible from the payload alone**, so the requirement stands as written and the Risks entry below does not fire: each entry of a task's `custom_fields` carries its own `type_config.options`, each option carrying both `orderindex` and `id`. Mapping the reported integer to the option's identifier therefore needs no field definition obtained separately and no second request.

**An unset drop-down omits the `value` key entirely** rather than reporting `0`. That distinction is load-bearing: `0` is a legitimate value — orderindex 0 is `commit` on the gate field — so a client that read absence as `0` would report every unvalued task as already carrying the first gate.

### Suppression gets its own table, keyed by the gap's content

A row holding the identity of the last gap **reported** and when. A gap is re-reported when no row stands, or when the row's identity differs from the current gap's. The row is cleared on a pass that finds no gap.

Identity is the **content** of the whole finding — per field, the **set** of gap kinds found (empty identifier, absent, uninterpretable, wrong type, optionless, duplicate option name, missing options, wrong order — a field can be in several at once, so it is compared as a set), the sorted missing option names, the duplicated names, and the gate-option order observed — the last omitted, along with the order kind, while a duplicate stands on that field, or reordering options during an unrepaired duplicate would change the identity and re-report it — not merely "a gap exists", and not the missing options alone. Seven of the eight gap kinds name nothing missing — only *missing options* does — so an identity over missing options would collapse them: a wrong-typed field repaired into a wrongly-ordered one would match the standing row and meet silence, which is the failure the report-once rule must not be able to cause. A gap that grows or changes names a repair nobody has been asked for yet, so it must be reported; a gap that is unchanged must not.

The row is also cleared where the capability is **withdrawn** — a pass performing no check because neither identifier is configured — but *not* on a stand-down, not on a failed folder read, and not on a pass that made no check because no launch folder is configured. Without the first, the design's own rollback — unset both variables — leaves a row standing that nothing will ever clear, so opting back in later with the same unrepaired gap finds a matching identity and reports nothing: silence meaning "broken", which is the one thing this whole requirement exists to prevent. Without the exclusions, a deployment whose playbook moves in and out of readiness re-reports the same unrepaired gap on every ready pass — the flood the report-once rule exists to prevent, arriving by the other door. A stand-down says nothing about the configuration and is not a withdrawal of the capability.

**Rejected: in-memory suppression.** `report-overdue-scheduled-runs` already settled this — *"so a worker restart does not resume the flood."* A crash-looping worker would report on every restart.

**Rejected: one suppression row per field rather than one per finding.** Identity is already taken per field, so this is a question of storage granularity, not of structure. Per-field rows would make the flapping consequence above disappear rather than bound it: an empty-identifier field is never read, so its row would be written once and stay suppressed through any reachability weather, while a configured field's row would simply not be touched on a read-less pass. It is declined for a property the single row has and per-field rows lose — **one message per repair round**. A person repairing a configuration wants to be told once what is wrong with it, not once per field; and the flap the single row admits is bounded to one message per transition, which is a smaller cost than a report that fragments as the configuration does.

**Rejected: reusing `scheduled-jobs`' suppression table.** Its rows are keyed by a piece of recurring *work* and are lifted by that work succeeding; this pass succeeds precisely while the gap stands, so the two lifecycles are contradictory. Borrowing the table would mean either a synthetic work key that no work registers, or changing what suppression means for the overdue check. The rule that suppression is written **only after successful delivery** is borrowed; the storage is not.

### The check covers the option *order*, not only the option set

Every other clause of the gap definition can pass on a gate field whose options name all eight gates in the wrong sequence — and that field produces exactly the view the tags produced, which is what this change exists to stop. An unchecked order is the stated purpose failing with no signal at all.

**What forced this into the design was a fact already recorded above and not followed through.** The measurement under *The system reads the field configuration and never writes it* establishes that an appended option lands **last** in `orderindex`. That was written as an argument against self-repair. It is equally an argument about *hand* repair: the obvious response to "gate `stock-ready` has no option" is to add one, which clears the reported gap and silently introduces a wrong order. Reporting a missing option while not reporting the order therefore hands someone an instruction that breaks the thing the report was protecting. Checking both is what closes the loop.

`clickup-task-client`'s new read requirement already returns "those options in the order the field declares them", so the information is in hand.

**Rejected: resolve a gate to its option by `orderindex` rather than by name.** It would make order load-bearing in resolution instead of merely reported — but it breaks the exact-name matching this design argues for, and a reorder would then silently re-gate every task rather than being reported as the configuration mistake it is. Detection is the right shape; resolution stays by name.

### Both fields are drop-downs, including discipline

The gate field must be a drop-down: ordering is the whole argument for it, and only a declared option set has an order.

Discipline has no inherent order, so that argument does not reach it, and a plain text field would have no options to drift — a genuinely lighter configuration. It is nonetheless specified as a drop-down, because a mixed pair is harder to explain to whoever configures both by hand than a matched pair, and because the saving is small.

**The check is type-aware, and an earlier draft of this design was wrong to reject that.** It reasoned that optionlessness was a sufficient proxy for the type. It is not: a multi-select field declares options too, so it passes an optionless-only check while every write against it behaves as the task system decides for that type. `folder_fields` already returns each field's type, so comparing it costs one clause of the gap definition and closes the case. A hand-configuration mistake that the configuration check cannot see is precisely the failure this check exists to prevent.

**Consequence:** narrowing discipline to a text field later is a change, not a configuration choice — now two clauses of the gap definition rather than one. Nothing here forecloses it.

## Risks / Trade-offs

- **A field that reads as well-formed but refuses writes is not detectable by the folder read, and is carried by warning logs alone.** → The folder read establishes that a field exists, is of the right type and declares the right options; it cannot establish that a given list will accept a write to it. Such a field produces two failed writes and two warning records per task per pass, indefinitely, with nothing in Slack — which sits badly beside this design's own rejection of "a warning-level log record only" and its claim that a misconfiguration cannot be silent. The claim is hereby narrowed: **what cannot be silent is a misconfiguration the folder read can see.** Escalating a whole-pass write failure to the gap channel would close this class and is deliberately out of scope; it is named here so a later change can take it up rather than rediscover it.
- **A wrong-typed field that nonetheless declares matching options.** → Detection alone was not enough: resolution would succeed and the pass would write to a field whose write semantics it had just established it did not intend, once per task, acquiring the per-task noise the check was chosen to avoid. No value is written for any field found in a gap of the kinds that withhold writes.
- **Someone edits an option and the pass corrects a value that was deliberate.** → Accepted and specified: these two fields are wholly determined by the step, so there is nothing a person could mean by editing them. The way to change a task's gate is to move the step. Unlike the name and body, no retained-composition machinery is needed, because there is no legitimate person-edit to distinguish.
- **The two variables are added as `vars` rather than `secrets`, or rendered unconditionally.** → Either produces a blank value. A blank is no longer silent: it is a reported gap, which closes the `BOOTSTRAP_ADMIN_IDENTITY` shape mechanically rather than by a reviewer noticing. The residual risk is the opposite one — a *declining* deployment whose lines are rendered anyway is reported as broken — and task 1.3a checks both directions, in the rendered `.env` and in the process environment the pass actually reads. The blank finding is also composed independently of the folder read, so an unreachable ClickUp cannot hide it: the catch must not depend on the service whose configuration is in question. It is suppressed like any other delivered report, under the identity of what was composed — otherwise it would repeat on every pass of a reachability outage. The consequence, accepted: while reachability flaps with a gap standing on both fields, the reading pass composes the whole finding and the read-less pass composes only the blank part, so each transition reports once. That is the right way round — a partial finding is different news, and the alternative silences the whole finding behind the partial one.
- **A field nobody in this system owns could have disabled the check permanently.** → The folder read returns every field in the launch folder, at any type. Before this was closed, an unanticipated field shape would have raised on every read, and — unlike a transport fault — nothing here can remove the field that causes it, so the check would have degraded to warning logs forever. Closed by requiring the folder read to be total, the same obligation the task read carries and for the same reason. Recorded because the asymmetry survived several rounds: the task read got the rule when its failure mode was argued, and the folder read did not, though it is on the same path.
- **A shared store this concern cannot restore is the one path where the guarantee is qualified.** → **Any** failed access of the suppression record — a read as much as a write, since either can leave a shared session unusable — on a session shared with the per-launch writes obliges a restore before the **first** launch is attempted; where the restore itself fails, `One launch's failure does not stop the other launches being converged` gives the ground for ending the walk and failing the run — a ground it states for a failed recovery *between* launches, which this change extends to the pre-walk restore by its own judgement rather than by that requirement's mandate. So a fault of this concern can cost more than the field values, on exactly one path, and the requirement says so rather than leaving the guarantee reading as absolute. The alternative — continue against a store that cannot record — means writing to ClickUp and losing the record of the write, which that requirement judges worse than stopping.
- **While the suppression store is unusable, no gap reaches Slack at all.** → The clause that stops a store fault aborting the pass necessarily also stops the report: a failed read cannot tell a standing gap from a new one, so it reports none. That narrows "a misconfiguration cannot be silent" a second time — the first narrowing is the write-refusing field above — and the silence lasts as long as the store fault, carried by warning logs. Accepted because the alternative is a store fault costing every launch its projection, and recorded so the claim is not read as unqualified.
- **The Slack channel is down while a gap appears.** → Suppression is written only after delivery, so the gap is re-reported next pass. The failed delivery is not among the things that make the run fail, so the freshness evidence `scheduled-jobs` depends on is not affected by a channel outage.
- **A gap leaves a re-gated task stating a gate that is no longer its step's.** → Bounded and accepted: correction needs an option to correct *to*, and writing an approximation or clearing the value would each state something untrue. The gap is what is reported; repairing it corrects the tasks on the next pass. This is the predecessor's accepted defect surviving inside the gap and nowhere else, so the retirement claim is qualified rather than dropped.
- **Extending the discipline vocabulary now carries a ClickUp obligation.** → `shared-vocabulary` says the set "is deliberately extensible… without structural change to the vocabulary". After this change, adding a member is still free in code but produces a configuration gap and a Slack report until someone hand-adds a matching option. Not a contradiction, but a new obligation on an unrelated future change, and it is recorded in the Migration Plan so it is discoverable without deploying and waiting for the report.
- **One extra request per pass.** → Negligible against a pass already making roughly a hundred and eighty on a first projection; and the pass stands down before making it when the playbook is unready.
- **If the task payload carries neither the option identifier nor the field's options, the normalisation obligation and its no-second-request constraint are jointly unsatisfiable.** → Task 2.4a takes that measurement before the normalisation is written. If it comes back that way, the answer is to reopen this decision — either the read takes the field definitions the pass has already fetched, or the comparison moves to the caller — and **not** to let the caller silently absorb the difference, which is the write storm this decision exists to prevent. Recorded because every other unmeasured premise here carries its consequence, and this one did not.
- **Whether a drop-down option can be dragged into position by hand is unmeasured.** → The section above measures six endpoints precisely because "undocumented behaviour is not a contract", and then the Migration Plan instructs a reorder it never checked. If options cannot be reordered in place, the report names a repair nobody can perform and the fallback — delete and recreate the options in order — changes every option identifier, which the correction path would then heal across every task. Task 7.10b measures it before the change ships rather than after.
- **The `403` on `PATCH` is not fully diagnosed.** → It does not gate the design: the decision is not to write field configuration under any permission.
- **The predecessor is not archived, so this change's REMOVED delta has no target.** → Ordering prerequisite, tracked as task 0.1 and repeated here because a reviewer reading design alone would not see it.

## Migration Plan

1. Archive `tag-tasks-with-gate-and-discipline` so the baseline records the tag requirement this change removes. **Nothing else may be sequenced before this.**
2. Create both Custom Fields by hand at **folder** scope on the launch folder, as drop-downs, with options named **exactly** — character for character, matched on the identifier string — by the eight gate identifiers in `GATE_SEQUENCE` order and the twelve `Discipline` values. An option differing by case, spacing or wording is not a match and is reported as a gap; the report names what the field does declare, so a typo is diagnosable from the message.
3. Set both field UUIDs as Environment secrets and render them in `deploy.yml` from `secrets`.
4. Deploy. The first pass backfills every existing task's values convergently; a rate-limited pass resumes on the next one.
5. **Standing obligation from here on:** adding a discipline to `Discipline`, or a gate to `GATE_SEQUENCE`, now also means adding a matching option by hand to the corresponding field — **and, for a gate, dragging that option into its sequence position**. An option added through ClickUp's own control lands last, which clears the missing-option gap and opens an order gap; the report names the order found so the move is obvious, but it is a second step and it is easy to stop after the first.
6. The `gate:`/`discipline:` tags already on tasks are left in place and cleared by hand if wanted. Nothing in the system reads or writes them after this change.

**Rollback**: unset both secrets, so `deploy.yml`'s conditional render omits both lines. The pass reverts to the opt-out path — no field writes, no reports, and any standing suppression row cleared as a withdrawal — and every other projection behaviour is untouched. The tags do not come back, and the tasks keep whatever values were written; neither is a broken state. A full revert of the code additionally restores tagging, which is additive and will re-tag on the next pass.

## Open Questions

None. The one candidate — whether discipline should be a drop-down or a text field — was resolved above rather than deferred, because the gap definition turns on it.
