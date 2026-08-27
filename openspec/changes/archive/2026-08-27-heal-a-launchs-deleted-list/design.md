## Context

See `proposal.md` — Why. This design covers only what that leaves open: how a deleted list is *detected*, given that ClickUp does not volunteer the fact through any call the pass already makes.

Two properties of the current code shape everything below.

`_ensure_list` (`clickup_sync.py:596`) trusts the mapping absolutely: a recorded list identifier is returned without any check that it still names a list. There is no place in the pass where a list's own existence is ever established.

The read that *would* be the natural place to notice — `list_tasks(list_id)` at `clickup_sync.py:524` — cannot tell. A deleted list answers it successfully and empty. That is not inferred: the production failure surfaced on `create_task`, and `list_tasks` raises on a non-2xx through `raise_for_status()` (`clickup_client.py:171`), so for the traceback to have named `create_task` the task read must have returned normally.

So the signal the pass already has is ambiguous:

```
       recorded list_id
             │
             ▼
      list_tasks(list_id)      ← already taken, every pass
             │
     ┌───────┴────────┐
  tasks ≠ ∅        tasks = ∅
     │                 │
   alive       ┌───────┴────────┐
               │                │
        live but empty     deleted
               └── indistinguishable ──┘
```

Only `GET /list/{id}` disambiguates, by answering `200` with `"deleted": true`. The client has no such call today.

## Goals / Non-Goals

**Goals:**

- Establish a recorded list's existence from ClickUp's own statement about it, at a defined point in the pass.
- Keep the rule stated in the spec simple enough to survive being read by someone who was not here.

**Non-Goals:**

- Renaming lists, or any `update_list` capability. See `proposal.md` — Impact.
- Detecting anything else that ClickUp may have deleted (a folder, the space).

## Decisions

### Decision 1: The list is verified unconditionally, before it is used

Every pass, for every launch that has a recorded list, `_ensure_list` reads `GET /list/{id}` and heals when the answer is `"deleted": true`. The check is not conditioned on anything the pass observes elsewhere.

**Alternatives considered:**

*Verify only when the task read comes back empty.* An empty read is the only state a deleted list can present, so a probe conditioned on it would detect the fault just as promptly, and — since a live list keeps its tasks and never empties again — would cost nothing at all in steady state.

*Infer from the `404` on `create_task`.* Rejected in the proposal and not reopened here: a write `404` is also what a transient fault or a permissions change looks like.

**Why unconditional, over the conditional probe:**

The efficiency argument that would favour the conditional version does not survive being priced. The pass runs on `*/10 * * * *` (`clickup_sync_job.py:79`) over five active launches, and already costs two ClickUp reads per launch per pass. A third makes it **thirty extra requests per hour** against a budget of roughly six thousand. The comment sitting directly above that schedule already spent a threefold rate increase on the same budget and recorded it as "far inside" — so this is not a place where requests are scarce.

With cost neutral, the choice falls to what each version costs a *reader*. Unconditional verification states one rule: before a recorded list is used, it is confirmed to exist. The conditional version has to state a two-step dance — an empty read, then a second call to interpret it — and a spec scenario written that way describes a mechanism rather than an obligation. It also couples the healing rule to an incidental property of the other read, so that a future change to how tasks are fetched could silently disarm the healing without touching anything that mentions healing.

**What it does cost is failure surface, and that is accepted rather than unnoticed.** Under Decision 4 a non-success on this read fails the launch's pass. Taken unconditionally, that is a third request per launch per pass that can fail a launch which would never have needed healing — where the conditional alternative would have exposed only launches whose task read came back empty. This is the axis on which the two options genuinely differ, cost having come out neutral. It is accepted because the pass is convergent (a transient failure costs one ten-minute cycle) and because containment already reports a failing launch per launch, so the failure is visible rather than silent.

**This decision is recorded so it is not reopened on cost grounds.** The Impact section of the proposal frames the read budget as a question this change must settle; it is settled, and the answer is that the budget was never the constraint.

### Decision 2: every task mapping is discarded — for coherence, not for correctness

All of the launch's task mappings are discarded when its list is replaced. **The stated justification changes.**

`proposal.md` originally grounded this in a retained observation reaching a fresh task. That ground does not hold. `record_task` (`clickup_mapping.py:106`) deletes the row and inserts a new one with `last_observed_closed=False`, and says so in its own docstring; the composition columns reset with the row rather than being carried. Healing re-projects correctly with no discard at all — `present` is empty, every projectable unfinished step falls to the create branch at `clickup_sync.py:563`, and its mapping is rebuilt there.

What actually survives a heal is narrower, and inert:

| mapping | after healing | stale? |
|---|---|---|
| projectable, unfinished | re-created; row replaced by `record_task` | no |
| defined, work settled (projectable or not) | `continue` at `clickup_sync.py:538` — row keeps the dead `task_id` and its observed state | **no — load-bearing, see Decisions 2a and 2b** |
| no longer projectable, work unsettled | never enters `steps`; read on every reconcile, dropped before any comparison | yes, indefinitely |

The second residual was checked for reach and has none. `reconcile_launch` reads it (`clickup_sync.py:655`) but discards it at `present.get(mapped.task_id) → None` before any state is compared. Webhook intake cannot reach it either: `resolve_task` looks up by `task_id`, and those identifiers name tasks ClickUp has destroyed and does not reissue.

The first residual is **not** inert, and an earlier draft of this table said it was. It is read on every pass, by the guard below, and discarding it changes what the pass does. Decision 2a is the correction.

**But the discard is not behaviourally inert, and an earlier draft of this decision wrongly said it was.** The analysis above asks what survives if no discard happens. It does not ask what the discard itself causes, and there the answer is not nothing. The guard that keeps finished work from being re-projected reads:

```python
# clickup_sync.py:537
if mapped is not None and task is None and _is_terminal(launch, step):
    continue
```

Its first conjunct is a mapping's *existence*. Discard the mapping and `mapped is None`, so the guard does not fire, the step falls through to the create branch, and a step already recorded terminal is given a fresh open task in the replacement list. That breaks a requirement already recorded — `launch-clickup-sync`'s scenario *A deleted task for finished work stays gone* — and it does it in the list this change exists to restore.

The outcomes actually at stake are `Satisfied` and `NotApplicable`, and only those. `permissible_terminal_outcomes` (`launch_playbook.py:207`) permits `Refused` **only** for a `prohibited-tactic` step, and `is_projectable` excludes exactly that hazard — so a projectable step can never carry `Refused`, and an earlier draft of this decision was wrong to call it the sharp case. The sharp case is `NotApplicable`: work someone judged unnecessary, re-presented as outstanding, with nothing in the list saying it was ever settled.

**So the discard exempts mappings for steps whose work is already finished** (see the requirement, and Decision 2a below), and is built for the remainder. The reason for building it at all is that it makes the requirement shorter. The two candidate rules are not "more code" versus "less code" — they are:

> A launch whose recorded list has been deleted is given a new one, and its task mappings are discarded with it.

against

> A launch whose recorded list has been deleted is given a new one. Mappings for projectable, unfinished steps are replaced as those steps re-project; mappings for finished or no-longer-projectable steps are left naming tasks that no longer exist.

The first is one sentence and has no exceptions to carry. The second cannot be stated without describing the convergence loop's internals, which is exactly what a behaviour contract is supposed to be free of. In a repository where the spec is the artifact that has to stay readable, the smaller diff buys the worse requirement.

The coherence argument runs the same way: a task mapping means nothing except relative to the list holding the task. Leaving children pointed at a parent known to be dead makes the mapping table state something untrue, at the one moment when the system knows it is untrue — later, nothing distinguishes those rows from merely old ones.

**Alternative considered — discard only the residuals** (terminal and no-longer-projectable, since the rest are replaced anyway). Rejected for the same reason: it is the honest description of the mechanism and the worst of the three to state as a rule.

**What the spec must not say.** The requirement states the discard as an obligation, never as a precondition for re-projection. Re-projection does not depend on it and would keep working if it were removed, and a future reader who believes otherwise will reason wrongly about both.

### Decision 2a: the exemption is stated in terms of the launch, not the loop

A mapping for a step whose recorded outcome is terminal is exempt from the discard and stands.

This costs Decision 2 its clean single sentence, and it is worth being clear about what it does *not* cost. The rejected alternative was unstateable because it could only be phrased in terms of `present`, the create branch and which steps the loop reaches. This exemption is phrased in terms of the launch's own state — *is this step's work finished* — which is a fact about the launch, readable without knowing how projection is implemented. The requirement stays a behaviour contract.

It also corrects the framing of what such a mapping *is*. Decision 2's residuals table called it inert. It is not: it is precisely what tells the projection that this step's work is done and its task is not to be recreated. It is a working record whose task happens to be gone, and it is the one row the heal must not touch.

**Alternative considered — keep the whole-launch discard and drop `mapped is not None` from the guard**, so terminality alone decides. Smaller in code, and it preserves Decision 2's one-sentence rule. Rejected because it silently changes an unrelated case this change did not propose: a step whose terminal outcome was recorded through Slack *before it was ever projected* has no mapping, is currently given a task on first projection, and would stop being given one. That is a change to first projection, not to healing.

**Alternative considered — accept the re-projection and state it**, letting the replacement list carry a task for every projectable step. Rejected: it needs a delta against *Human steps are projected as tasks…*, and it reverses a judgement that requirement records deliberately — "a task for something already recorded as done is only noise."

### Decision 2b: the exemption ranges over the playbook's authored steps, judged hazard-independently, and the caller decides it

The heal evaluates the exemption against `playbook.authored_steps` — every step the playbook defines, whatever its status — not against `served_steps`, and not against the projectable subset the convergence loop iterates. (`authored_steps` rather than the equal-valued `steps`: the domain fronted the attribute with a named accessor precisely so a caller has to say which set it means, and this is the one place where which set is the entire question.)

**And it is judged without reference to the step's current hazard.** Terminality as `_is_terminal` computes it resolves through `permissible_terminal_outcomes(step.hazard)`, so it is hazard-relative — and hazard is authorable. A step recorded `Satisfied`, later re-authored `prohibited-tactic`, is defined by `authored_steps` but not *terminal*, so a hazard-relative exemption would discard its mapping; revert the hazard and the step is handed a fresh open task for finished work. That is pass two's defect surviving in the third of the three filters this decision set out to lift.

The exemption asks whether the work was finished, and re-authoring the rules for finishing a step does not unfinish work already done. So it asks whether the recorded outcome settles work *for any* hazard — `automation_pass.py:404` already carries that shape (`any(kind in permissible_terminal_outcomes(hazard) for hazard in Hazard)`), and the recorded requirement *Human steps are projected as tasks…* already glosses terminal as the flat triple, so this reading is the one the existing spec text describes.

The projection guard at `clickup_sync.py:537` stays hazard-relative and is not touched. The two compose correctly: across a flip to `prohibited-tactic` the step is not projectable, so the loop never reaches it; on revert, the mapping is still there, so the guard fires and no task is created.

**The store cannot decide this, and the task list must not offer it as an option.** Terminality is hazard-dependent: `_is_terminal` resolves through `permissible_terminal_outcomes(step.hazard)`, so judging it needs the step *definition*. `ClickUpMappingRepository` holds two tables and no playbook, and giving it one would drag the domain vocabulary across a boundary the module's layering exists to keep. The caller evaluates terminality and hands the store the mappings to spare.

**The range must be the authored set, not the served one.** `served_steps` is `steps` filtered to `ACTIVE` (`launch_playbook.py:679`), and the projectable set narrows that again to human, non-`prohibited-tactic` work. But mappings outlive all three filters — the recorded requirement *A step that is not active leaves the loop* obliges exactly that. Range the exemption over the projectable set and a step that is terminal *and* currently retired or automated has its mapping discarded; should it return to active human work, it is handed a fresh open task for work already finished. That is the same defect as Issue 1, surviving in a narrower case.

Ranging over the authored set is nearly free: `converge_launch` already receives the playbook (`clickup_sync.py:491-500`). It is not entirely free, and an earlier draft overstated it — the heal lives in `_ensure_list`, whose signature carries no playbook. One argument has to reach it. Note that `_ensure_list` already takes a `steps` parameter its body never reads (`clickup_sync.py:596-604`), so this may replace that dead argument rather than add a sixth.

**A mapping whose step the playbook does not define at all is discarded.** Nothing can ever re-project it — the loop only iterates defined steps — so discarding is both decidable and harmless.

This branch is **defensive**, and it is worth being explicit that no sanctioned operation reaches it. `playbook-authoring` states "No operation SHALL delete a step": a step is retired, and a retired step is still authored, so it is still in `authored_steps` and still exempt if its work was finished. The branch covers what the authoring surface cannot produce — mappings older than the playbook's move into Postgres, and anything left by a direct database edit — and it exists so the heal has a defined answer rather than an unhandled lookup.

### Decision 3: the replacement and the discard are one operation, in one transaction

The mapping store gains a single method that records the new list identifier and deletes the launch's task mappings in one commit — not `record_list` followed by a separate discard.

Every method on `ClickUpMappingRepository` commits for itself (`record_list` at `clickup_mapping.py:77`, `record_task` at `:134`), so two calls mean two transactions and a window between them. Sequenced one way — discard first — a crash in that window leaves the *dead* list still recorded with its mappings gone, and the next pass mints a second replacement list, orphaning the first. Sequenced the other way, a crash leaves the new list recorded with stale mappings intact, which is benign but permanent, since nothing revisits it.

One transaction removes the window rather than choosing which side of it to fail on. It also names the thing that actually happened — the launch's projection was reset — instead of two mechanical steps that only mean something together.

**Alternative considered:** let the caller order two existing calls and accept the benign failure mode (record first, discard second). Rejected because "benign but permanent" is precisely the state Decision 2 exists to avoid, and it would be reachable by crash even after this change shipped.

### Decision 4: a read that fails is a failure, never a deletion

The new read reports a list as deleted only when ClickUp says so. A non-successful response — `404` included — and an unreachable ClickUp alike propagate as errors; the launch's pass fails and containment reports it, exactly as it does today.

The alternative is to treat `404` on `GET /list/{id}` as a deletion, on the reasoning that a list that cannot be fetched is unusable either way. It is rejected on two independent grounds. It is the same inference this change exists to refuse — the proposal's second bullet forbids reading a deletion out of a failed request, and a failed read is no better evidence than a failed write: it is equally what a withdrawn permission or a mistaken identifier produces. And it would require the client to suppress a non-success response, which `clickup-task-client` forbids of every operation it has.

**The cost of that choice is real and is stated rather than hidden.** ClickUp reports `"deleted": true` for a list in its trash. If a list is purged, the read presumably answers `404` instead, and under this decision such a launch fails every pass and is never healed — which is the very state the proposal opens on. This change therefore heals a *deleted* list, not a *purged* one, and the observation it was proposed on (list `901220624358`, still answering `"deleted": true` on 2026-08-27) is a list in trash.

Whether a purged list is worth healing is a separate question, and answering it means answering how to distinguish a purge from a permissions fault without guessing — likely by asking the folder what lists it holds rather than asking the list about itself. That is a different mechanism and belongs to a different change. Recorded here so the gap is known rather than discovered.

**The gap is time-bound, and so is this change's own verification.** Trash retention is finite, so the healing property holds only while the dead list is still in it. Tasks 5.1 and 5.2 confirm this change against list `901220624358` specifically; if that list is purged before merge, those tasks cannot pass, and their failure would mean the retention window closed — not that healing is broken. Confirm on the next launch whose list is deleted instead, and record that the original observation expired.

## Risks / Trade-offs

**A crash between minting the replacement list and recording it leaves an orphan** → This is the orphaning residual `proposal.md` excludes as the inverse fault, arriving through a door this change opens: `create_list` succeeds, the process dies before the transaction in Decision 3 commits, and ClickUp holds a list no record names. The next pass probes the *old* identifier, finds it deleted, and mints a second replacement. Decision 3 narrows this to the one window that cannot be closed from inside the database — ClickUp is not a transaction participant — but does not remove it. The exclusion still stands, since the residual is not made worse in kind; it is no longer only containment's to own, and one answer will have to cover both.

**Verification runs on launches that will never need it** → Accepted, and priced above. A list that has never been deleted is confirmed alive six times an hour for the rest of its life.

**`"deleted": true` is a single observed ClickUp behaviour** → It was read from the live API against list `901220624358` on 2026-08-27, while that list was in trash. Decision 4 settles what happens when the read answers anything else: the launch fails its pass and is contained, degrading to the status quo rather than to something worse. The known gap — a list purged from trash is not healed — is recorded there rather than left to be found.

**The exemption depends on the recorded outcome, and a step reaching terminality mid-pass is not caught** → A step's terminal outcome is what exempts its mapping. The launch is read once for the walk, so a step attested terminal between that read and the discard has its mapping discarded and a fresh open task created for finished work.

**This does not self-correct, and an earlier draft of this entry wrongly said it did.** The next pass finds the recreated task *present*, so the re-projection guard — which turns on the task being absent — does not fire, and the pass maintains it: name, body, assignees, due date, indefinitely. The system never closes a task on its own (the recorded *The system never closes a task* scenario forbids it), so the task stays open for work already done. If someone closes it to tidy up, that reads as a transition and records `Satisfied` over the stored outcome and provenance — which for a step recorded `NotApplicable` is a wrong outcome, not merely a redundant one.

Accepted as a residual rather than guarded, on reachability: the only route is a Slack attestation for a step of *this* launch landing inside the heal of that same launch, which happens once in the life of a broken list. Recorded as a live residual so that a future reader deciding whether to close it — cheaply, by re-reading terminality inside the Decision 3 transaction — is not told it fixes itself.
