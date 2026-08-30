## Context

See `proposal.md` for motivation. The current shape, before this change:

```
StepDefinition
├── kind: StepKind (human | automated)
├── needs_confirmation: bool = False
├── assignees: tuple[str, ...] = ()
├── automation_brief: str | None = None
└── handler: str | None = None
```

`needs_confirmation` gates a separate path in `automation_pass.py._settle`: a
terminal automated outcome is either recorded immediately or stored as a
"pending result" awaiting a Slack decision. `automation_confirmation.py`
currently lets *any* known, active roster identity press Accept/Reject on
that pending result — decision authority is not scoped to the step's
assignees or to anyone in particular.

`automation_brief` is validated only at write time (required to leave
`draft`) and read only by `activation_readiness.report_activation_blockers`.
It reaches no other consumer: it is not in the ClickUp task body (only
`description` is, and only `human` steps get ClickUp tasks), and the seeded
step set — always `draft` + `human` — never carries one.

## Goals / Non-Goals

**Goals:**
- Replace `needs_confirmation: bool` with `confirmer: str | None`, a single roster identifier that both signals confirmation is needed (non-null) and names who decides.
- Narrow Slack decision authority on a pending result to that one identity.
- Remove `automation_brief` entirely.
- Reorder the step authoring form so the group `[Confirmer, Kind, Assignees|Handler]` comes last, with `Assignees` and `Handler` toggling visibility by `Kind`.

**Non-Goals:**
- No ClickUp-side reject/reopen mechanism for `human` steps. ClickUp has no built-in equivalent to Bitrix24's controller-approval flow — approval-style behavior there is only ever built out of custom statuses plus automations, and this deployment's `clickup_sync.py` currently reads a task's state as binary closed/open only. Extending a `human` step's `confirmer` into an actual reject-and-reopen loop is a separate, later change.
- No coherence rule barring `confirmer` from also being one of several assignees — only the single-assignee-equals-confirmer shape is rejected (see the `launch-playbook` delta).
- No backfill migration for `automation_brief` → `description`. All current data is test data.

## Decisions

**`confirmer` is a bare nullable string column, unconstrained at the DB level.** Mirrors how `assignees` (a `JSONB` list of roster identifiers) is already handled: no FK, validated at the application layer via the roster reader, for the same reason `assignee_faults` gives — the roster changes independently of the step set, so a DB constraint would make deactivating or removing a person a step-set-breaking operation.

**Confirmer's known/active checks live in a new function alongside `assignee_faults`; the single-assignee-equals-confirmer rule does not.** `assignee_faults(steps, *, known, active)` stays assignee-only; a sibling `confirmer_faults(steps, *, known, active)` mirrors its two-part shape for `confirmer` — known-to-roster unconditionally, active-on-roster scoped to `active`+`automated`. Both are roster-dependent and are called from the same write-time precondition site in `playbook_authoring.py`, the same way `assignee_faults` is today (see `tasks.md` 1.4, 2.2).

The single-assignee-equals-confirmer rule is **not** part of `confirmer_faults` and is **not** a write-time precondition at all. It needs no roster to evaluate — it is a pure function of one step's own `assignees` and `confirmer` fields — so it belongs with the other purely step-set-derived rules that are checked on every load, not only on a write: `_automation_faults`, `_dependency_faults`, and the rest of the per-step loop `LaunchPlaybook.__init__` already runs. It is added as its own small per-step function, called from that same loop, and is enumerated in the `launch-playbook` delta's *An incoherent playbook is rejected against its steps' status and shape* (a REMOVED+ADDED pair, renamed from *...against each step's status* because a MODIFIED block cannot drop the old "brief absent" scenario the way this rename lets a clean REMOVE+ADD do) alongside the rules already there (see `tasks.md` 1.3). This does mean a playbook already carrying this shape — however it got there — fails to *load*, not merely fails its next write, which is the same severity every other purely-structural coherence rule in this list already carries (e.g. a `human` step carrying a handler).

**`human` step's `confirmer` is accepted, not rejected — following the old `needs_confirmation` lineage, not the `automation_brief`/`handler` lineage.** These two lineages already coexist in the current spec for different reasons: `automation_brief`/`handler` describe *how the work gets done* and contradict `kind = human` outright, so they're rejected; `needs_confirmation` was an orthogonal fact about *review*, not about who does the work, so it was ignored instead — explicitly to avoid punishing an author who flips `kind` back and forth while iterating. `confirmer` plays the same orthogonal role `needs_confirmation` did, so it inherits the same treatment.

**Decision authority narrows unconditionally — no "any active person" fallback when no confirmer is named.** This was a deliberate, explicit choice: a pending result only ever exists for a step naming a confirmer in the first place (`automation_pass.py`'s `_settle` only stores one where `step.confirmer is not None`), so there is no state where a pending result exists *and* no confirmer is named. The question "who decides when nobody is named" therefore does not arise — it's not a fallback being removed, it's a state that can't occur.

**Form field order.** The full field list, in the order the template renders them, becomes:

```
Status, Name, Description, Gate, Discipline, Scope, Blocking, Hazard,
Timing anchor (kind/days/start/end/cadence), Starts at gate, After steps,
──────────────────────────────────────────────────────────────────────
Confirmer, Kind, Assignees (kind=human) | Handler (kind=automated)
```

The last group moves to the end of the form, in that internal order. `Kind`'s
existing position (already near the end, just before the old
`automation_brief`/`handler` pair) barely moves; `Confirmer` is new;
`Assignees` moves from its current early-middle slot (right after the
timing-anchor block) down to the end, directly where `Handler` now also
lives — the two occupy the same visual slot, toggled by `Kind`, the way
`automation_brief`/`handler` are already toggled by the `automated` flag in
`_fields.html`'s existing JS. `Automation brief`'s input is deleted outright
rather than repositioned.

**Confirmer picker is single-select, not the multi-value checkbox list `assignees`/`after_steps` use.** A radio-button group (or a `<select>`) reusing the picker's existing styling, offering every roster person plus one explicit option — labeled "No confirmation needed" — bound to an empty/absent value, distinguishable from a control that simply has nothing selected yet.

**Alembic migration drops two columns and adds one, no backfill.** `needs_confirmation` (`Boolean`, `nullable=False`) and `automation_brief` (`Text`, nullable) are dropped; `confirmer` (`String`, nullable) is added. Confirmed with the user: all current data is test data, so no `automation_brief` → `description` backfill is needed.

## Risks / Trade-offs

- **Single point of failure on decisions.** A pending result now blocks entirely if its confirmer is unreachable (off, offboarded mid-flight, etc.) — there is no other active person who can step in. Accepted deliberately: the previous "anyone active" latitude is exactly what made "who confirms" ambiguous, which is the problem this change exists to fix. Mitigation, if it becomes a real operational problem, is a later change (e.g., reassigning a step's confirmer is already just an ordinary authoring write, so recovery is "an admin edits the step," not a system outage).
- **Broad mechanical test surface.** A large number of unit and integration tests construct `StepDefinition` with `needs_confirmation=...` and/or `automation_brief=...` keyword arguments (well over a hundred call sites across the suite). None of this is conceptually risky — it's a mechanical field-set update — but it is a wide diff to review. `openspec-test-writer` will derive the new/changed test expectations from the delta specs above; the existing suite's fixture helpers get updated to match the new field set as part of implementation, not treated as spec-covered behavior change.
- **Two independent removals in one change.** `confirmer` and `automation_brief`'s removal don't depend on each other technically. Bundling was a deliberate choice (confirmed with the user) because both are touched by the same authoring-form pass and are small enough together to stay reviewable in one sitting.
