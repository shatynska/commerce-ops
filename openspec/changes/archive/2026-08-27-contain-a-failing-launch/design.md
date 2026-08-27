## Context

See proposal.md — Why, for the production fault that exposed this.

What matters for the approach is where the walk lives. `clickup_sync.py` holds two passes, each taking exactly one launch: `converge_launch` drives ClickUp toward what the launch's schedule implies, `reconcile_launch` drives recorded outcomes toward what ClickUp says. Neither knows other launches exist. The walk across launches lives in the driving adapter, `clickup_sync_job.reconcile_clickup_completions`, as a bare `for launch in active:` with both halves called in order and nothing between them and the job's own failure.

Two existing decisions constrain what containment may do:

- `scheduled-jobs` treats a run's outcome as a single fact — succeeded or failed — with retry and overdue reporting hanging off it. There is no per-launch outcome to report to, and this change does not invent one.
- `launch-clickup-sync`'s stand-down requirement already spends this capability's one "expected failure reported as success", and pays for it by having the daily briefing raise the signal instead. Nothing plays that role for a launch that cannot be converged.

Three facts about the job as it stands today decide what containment has to do, and each was read from the source rather than assumed:

- **Readiness is determined before the walk.** `reconcile_clickup_completions` loads the served playbook once, ahead of the loop, and returns on `PlaybookNotReadyError` — the stand-down. Containment therefore cannot convert a stand-down into per-launch failures, because no launch is attempted during one. This is why the delta can state the carve-out as a fact about the pass rather than as a new obligation on it, and it is a constraint on the implementation: readiness must stay above the loop.
- **Every write in the walk is already committed when it is made — both writing paths, not just one.** The job runs on `session()`, not `transaction()`, and every repository in this project commits its own write. Projection's writes go through the mapping store, which commits inside `record_list`, `record_task`, `record_composition` and `observe`. Reconciliation's writes go somewhere else entirely — `record_step_outcome` saves through `LaunchRepository.save`, which commits on both its insert and its update path — so a recorded outcome is durable when it is recorded, exactly as a mapping row is. Both halves had to be checked: the delta promises that completed work stands, and an outcome left pending would be discarded by the rollback below while the `observe` that consumed its transition had already committed, losing a completion permanently. Neither path leaves anything pending.
- **The unconfigured-folder check is reached per launch.** It is raised from `_ensure_list`, inside projection, for a launch that needs a list — not as a guard above the walk. So containment turns that condition into one failure per such launch rather than one abort per run, which is what the delta states and what its scenario tests.

## Goals / Non-Goals

**Goals:**

- Every active launch is attempted on every run.
- A launch's fault is attributable to that launch in the log, not merely present in a traceback.
- The run's reported outcome still reflects that something is wrong.

**Non-Goals:**

- Diagnosing or healing any particular failure, the deleted list included (proposal.md — What Changes).
- Any change to what either pass does for a launch. This change is about the driver.
- A per-launch health signal, or overdue reporting that can tell "one launch is broken" from "the pass is not running". See Open Questions.

## Decisions

### Containment lives in the job's loop, not inside the passes

The `try` goes around the pair of calls in `reconcile_clickup_completions`, not inside `converge_launch` or `reconcile_launch`.

Those two functions are the unit of work, and their contract with every caller — the job, the tests that drive them directly — is that a fault in converging *this* launch surfaces to whoever asked. Pushing containment into them would swallow the fault at the wrong altitude: a test driving `converge_launch` over a broken fixture would see it return normally, and the module's own docstring promise that a crashed pass heals on the next run would quietly become a promise that nothing crashes at all.

The loop is also the only place that knows there *are* other launches, which is the whole subject of the requirement.

### Both halves of one launch are contained as a single unit, and a failed convergence skips that launch's reconciliation

They run as an ordered pair by design — convergence establishes the list and the task mappings that reconciliation then reads back — so a launch whose convergence raised is a launch whose projection is in an unknown state. Reconciling it anyway would be a third state nobody has specified.

The alternative, containing each half separately so a launch with a broken projection could still have its completions recorded, was considered and rejected — but on a narrower claim than "reconciliation would have nothing to read anyway". That is true of the fault at hand (a deleted list reads as empty from both directions) and not true in general: a convergence that raises while assigning a task, or on a roster read, leaves every existing mapping intact and reconciliation perfectly able to read closed tasks and record completions. Under this rule those completions are withheld.

It is rejected on simplicity instead. Splitting the halves needs its own answer to what a half-succeeded launch is — which outcome it reports, what the next run may assume about it — and that is a second concept for a change whose whole subject is containment. One launch, one attempt, one outcome.

The cost is real and is stated in the delta rather than left to be discovered: a launch whose projection keeps failing has no ClickUp completion recorded for as long as that lasts, so its gates do not open on ClickUp's evidence. The deployment will be in exactly that state for the broken fixture launch during the observation window.

The cost is bounded to reconciliation's own path, and the delta says so rather than overclaiming: webhook intake reaches the same launches independently, gated on the delivery and the mapping, so a completion that is *delivered* still records for a launch whose projection is failing. What is deferred is the completions reconciliation was the only path for — which, on this deployment today, is all of them: no webhook is registered yet, and `clickup_sync_job` records that the pass is currently the only path completion travels. The requirement is written for the system, not for that configuration, but it is worth knowing that the practical effect on the fixture launch during the observation window is total.

What keeps that cost a *delay* rather than a loss is that the skip is total — the launch is not read at all. Reconciliation records on a transition of the retained observed state, so a tempting future optimisation ("reconcile it anyway, just don't record") would observe the tasks, consume the transition, and destroy the completion it declined to record. The delta states the two together and forbids separating them for this reason; it is the same mechanism the stand-down requirement already relies on for a served step.

### Any exception is contained; `BaseException` is not

The catch is `except Exception`, not a curated list of ClickUp or database error types.

The pass cannot enumerate what its collaborators can raise — the fault that prompted this change was an `httpx.HTTPStatusError` surfacing from a mapping row that had gone stale, which no reasonable list would have anticipated — and a fault nobody predicted is exactly the one that must not starve the other launches. `automation_pass._invoke` already catches `Exception` around a handler for the same reason.

`BaseException` is deliberately excluded: a worker being cancelled or shut down must stop walking launches, not log the cancellation against a product and carry on to the next one.

### A contained failure rolls the session back before the next launch

The delta promises that no state left by one launch's attempt affects another's. What a rollback needs in order to be safe is not that committed work survives it — that is trivially true — but that **nothing is pending when it runs**. Context establishes exactly that, for both of the walk's writing paths: the mapping store and the outcome recorder each commit as they write, so a rollback at any point in the walk has nothing of the failed launch's work to discard. Durability settled, what remains is session usability.

The pass shares one `AsyncSession` across the whole walk. An exception raised by ClickUp or by composition leaves it perfectly usable; an exception raised by the *database* leaves the transaction in a failed state, and every subsequent launch's write would then fail against a session poisoned by a launch that has already been reported. So a contained failure rolls the session back before the walk continues.

The rollback is unconditional rather than conditional on the exception's origin: distinguishing a database fault from a ClickUp one means classifying exception types, which is exactly the enumeration this design refuses elsewhere, and a rollback with nothing to undo costs nothing. Everything already committed is untouched by it — that is what makes this safe to do blindly.

A rollback that itself raises ends the walk — and the delta says so rather than leaving it to the implementation, because it is an exception to the requirement's own absolute and has to be visible there.

It is *caught*, not left to propagate. Letting it propagate would be simpler and is wrong for one reason: the launches already contained on that run would then be named nowhere but their individual log records, and the run would fail with an error about a rollback rather than about the launches. So the failure ends the walk and the aggregate is raised from it, chained, so neither the cause nor the list survives at the other's expense.

The argument is not merely that the connection is gone and the remaining launches would fail anyway. It is that they would fail *after* doing ClickUp work. Projection writes to ClickUp first and records what it wrote second, so a launch attempted against an unusable session creates a list or a task and then cannot record it — and an unrecorded list is precisely how the fault that prompted this whole change gets manufactured: the next run finds no association and makes a second one. Continuing past a failed recovery would trade a summary line for orphaned ClickUp artifacts.

What ending the walk costs is stated in the delta: the aggregate error names only the launches contained before that point. It costs nothing from the record, because each contained failure was already reported in its own right as it happened.

A cancellation ends the walk too, but not the same way, and the delta keeps them apart deliberately. Not because naming the contained launches there would be impossible — a `finally` around the walk could log the summary and still let the cancellation propagate uncaught — but because it would buy nothing. A run record that says the worker was stopped already explains why the walk is short; a run record that says a rollback raised does not explain which launches had already failed, which is exactly why that path is required to name them. What the runner records for a process that stopped is `scheduled-jobs`' business, not this requirement's.

### The run fails after the walk, naming every launch that failed

Failures are collected and raised once, at the end, as a single error naming each failed launch by its product identifier. Raising the first exception when the walk finishes would report one fault and hide the rest; not raising at all is the invisibility the requirement forbids. The identifier rather than the catalog name, because the job holds the identifier already and reading the catalog on the failure path adds a read that can itself fail while reporting a failure.

This settles the question the opposite way from `launch-step-automation`, whose own per-launch walk requires that "a pass that completed its walk SHALL be recorded as a successful run whatever individual handlers or deliveries did". The asymmetry is deliberate, and the difference it rests on is what the failure leaves behind, not where it is reported — both capabilities report a failure to the log and nowhere else. An automated step that fails to resolve leaves the launch exactly as it was: the work is simply not done yet, and the next pass reconsiders it, which is the retry. A launch that is never converged has no ClickUp list and no task at all — the work does not exist for anyone to do — and from outside, that is indistinguishable from the pass not running. That is what the run's outcome has to carry here and does not have to carry there. Until something else carries it, the run's outcome is the only signal there is, and the Open Question below is where that gap is recorded.

The message is the report. `scheduled-jobs` carries no structured per-launch outcome, so the launches are named in the raised error — which the runner logs — and each contained failure is additionally logged with its own traceback as it happens, so the log holds both the summary and the detail.

### The walk's order is left as it is

`LaunchRepository.list_active()` selects with no `ORDER BY`, so the order active launches come back in is unspecified. Under the current fault, that order decides which launches are starved and which are not, which is intolerable — but it is intolerable *because* of the abandonment this change removes. Once every launch is attempted, the order stops being load-bearing.

Adding an `ORDER BY` would change a repository read shared with other callers, to make reproducible a starvation that no longer happens. If a later change wants a stable order for its own reasons, it can have it then.

## Risks / Trade-offs

- **A permanently broken launch keeps the work red forever, and a second, unrelated failure lands in the same red state.** → The raised error names every failed launch on every run, so the log distinguishes one broken launch from two. What this change does not offer is a signal that separates them *outside* the log; that is the Open Question below, and it is not made worse than it is today.
- **Retries now re-walk the healthy launches while a broken one persists.** → Convergence is idempotent — this is the property the whole module is built on — so a re-walk heals rather than duplicating. The cost is one ClickUp list read per healthy launch per attempt, comfortably inside the rate budget the ten-minute cadence was already sized against.
- **A contained failure leaves that launch's ClickUp state partly converged.** → Already true today, and unchanged: the next attempt continues from what is there. The requirement states this rather than leaving it to be discovered.
- **While the fixture launch stands broken, this work never succeeds — and `scheduled-jobs` reports a continuing outage once, not repeatedly.** → A period of overdueness ends only when the work next succeeds, so the completion pass will raise a single Slack report and then say nothing further for as long as the deleted list is left in place, while `/health/scheduled-runs` shows it unhealthy throughout. This is the intended reading of the fixture, not a surprise — task 5.3 requires exactly that unhealthy state as proof containment did not swallow the fault — but it means the Slack channel is not the place to watch during the observation window, and it is the reason the follow-up healing change is owed rather than optional (task 5.4).
- **Under a database outage that the rollback still survives, containment multiplies a pre-existing orphaning risk.** Projection writes to ClickUp before recording what it wrote, so a launch whose recording fails leaves a list or task in ClickUp with no association — and the next run, finding none, makes another. Today the first such launch aborts the run and at most one launch orphans; with containment, every launch needing a list can. → Partly bounded, and accepted unmitigated beyond that. The bound covers only one shape of database fault: a session too broken to roll back ends the walk before it can orphan anything more. The residual is the other shape — a database that refuses writes while accepting rollbacks, as a read-only failover or a full disk does — and there the walk continues, orphaning one list or task per launch that needs one, per attempt, for as long as the condition lasts. Work people then do in an orphaned list is invisible to the system: its tasks carry no mapping, so a delivery for them is acknowledged and ignored.

Nothing in this change or the follow-up cleans that up. The follow-up heals a launch whose *recorded* list is gone, which is the inverse fault — here the artifact exists and the record does not — so it is named here as accepted rather than passed off as mitigated. It is worth revisiting if a database outage ever produces it; it is not worth a second concept in a change about containment.
- **A condition that fails every launch — no folder configured, ClickUp unreachable — now costs one attempt and one logged traceback per launch per attempt, where it used to cost one per run.** → Bounded by launches × retry attempts, with no writes attempted beyond the one that fails, and accepted: a global outage that is noisier in the log is a fair price for a single launch's outage that is no longer silent for the others.
- **`except Exception` around the pair could make a programming error look like an environmental one.** → The run still fails, and the per-launch log record carries the full traceback, so the fault is neither hidden nor downgraded — only attributed to a launch.

## Migration Plan

None. No schema, no configuration, no data. The change deploys as code through the ordinary pull-request path; rollback is a revert, after which the pass abandons its walk on the first failure exactly as it does now.

## Open Questions

- Should overdue reporting be able to distinguish "one launch has been failing for six hours" from "the completion pass is not running"? Both are a single failed work item today. Answering it means giving `scheduled-jobs` a vocabulary for partial outcomes, which is a change to that capability rather than this one, and neither this change's specs nor its approach depend on the answer.
