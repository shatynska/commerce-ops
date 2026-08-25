# Design — redesign-step-fields

## Context

See `proposal.md — Why`. What shapes the approach:

- `StepDefinition` is a frozen dataclass in `launch/domain/launch_playbook.py`; the playbook validates its own coherence at construction, and `playbook-authoring` reuses that same construction to validate every write. So a field's rules are written once and hold at load and at write alike.
- Retirement today lives on the *record* (`StepRecord.retired_by` / `unretired_by` in `playbook_authoring`), not on the definition. The new `status` overlaps it.
- `clickup_sync._task_name` composes `description · identifier` and truncates, spilling into the body only when the name will not fit. That machinery exists because there is one text field, not because anyone wanted it.
- `move-principals-to-roster` shipped a roster whose people carry generated identifiers, display names, ClickUp user ids and an active flag, reachable only through `access.application`'s public surface (`.importlinter` enforces it).
- `add-step-page` is proposed but parked, and should be drafted against this field set.

## Goals / Non-Goals

**Goals:**

- A step that can produce a good ClickUp task on its own: a name, a body, and someone responsible.
- Fields an author can fill honestly at the moment they are writing the step, including when the automation does not exist.
- One place per fact: what the launch reacts to lives on the step; how the code happens to work does not.

**Non-Goals:**

- **Running** an automated step. This change lets a step declare a handler and refuses to activate one naming a handler the code does not register; invoking it and recording what it returns is the automation runtime, and is its own change.
- Assigning by role rather than by person — that waits on the roster growing roles.
- Any change to gates, timing anchors, hazards or outcomes.

## Decisions

### 1. One change, not two, though it is large

The obvious split is "name/description + assignees" then "kind + status + brief". I did not take it, and the reason is that the halves interlock through validation rather than merely sitting near each other: `status` decides *when* the brief and handler are required, `kind` decides *which* of assignees or handler an activation demands, and assignees are only required because an `active` `human` step needs one. Split, the first change would ship a `StepDefinition` the second immediately rewrites, and the seeded set would migrate twice.

The cost is a large review. It is mitigated by the deltas being mostly restatements of existing requirements against the new fields rather than new behaviour — three of the four capabilities change because a field they name was renamed or replaced. If a reviewer disagrees, the available cut is narrower than it first looks: the form must migrate to the new fields in this change whatever else waits, because it currently submits `binding`, `execution` and `rule_policy`, which cease to exist — and deferring the assignee control would make an `active` `human` step un-creatable from the page, which is nearly every step there is. What can genuinely be deferred is the status-change control and the widened search.

A stronger argument for keeping it whole than the interlock alone: the ClickUp body's meaning is decided jointly by both halves — it depends on `description` being separate *and* on the projection filter changing — so a split would leave the first change specifying a body rule the second invalidates.

### 2. `status` replaces record-level retirement rather than sitting beside it

Retirement becomes `status: retired`, and the retire / un-retire use cases set it. Two mechanisms for "is this step in play" is one more than the question has answers, and a step could otherwise be `active` and retired at once — a state nothing could sensibly resolve.

The attribution the record carries (`retired_by`, `retired_on`, and their un-retire counterparts) stays exactly as it is: it records *who moved the step and when*, which the status itself cannot say. What goes is the *derivation* of liveness from those fields.

*Alternative considered*: keep retirement where it is and let `status` carry only `draft` / `in-development` / `active`. Rejected — every read would then have to ask two questions to decide whether to serve a step, and the answer to "why is this step not being served" would live in two places.

The merge has a cost the first draft of this design did not price. Retirement used to be *guaranteed reversible*: un-retiring restored a step to the served set, full stop. `active` is now a validated state, so restoring straight to it could fail — a step retired months ago may name an assignee who has since left. Un-retiring therefore returns a step to `in-development`, and activating is the separate act it is for any other step. That is a real change to an existing requirement, and `playbook-authoring`'s retire/un-retire requirement is modified to say so rather than leaving it to be derived.

### 3. `kind` + `needs_confirmation` replace `ExecutionMode`

The three-value enum is replaced by two orthogonal fields. What the launch reacts to is whether a person must accept the result; whether the resolving code calls a model is invisible to every rule in the system today, and recording it invited the reading that `ai-assisted` is a *kind of automation the playbook manages*, which it is not.

`needs_confirmation` on a `human` step is specified as meaningless-and-ignored rather than rejected. Rejecting it would mean an author flipping a step from automated to human has to clear an unrelated field before the write is accepted — a validation error that teaches nothing.

### 4. The handler is a name the code registers, checked at activation

A step names a handler; the code registers handlers under names; activation fails if the name is unregistered. This is the `registrations.py` pattern the project already uses for scheduled work, and it is why activation must be an explicit act rather than something a deploy causes: the person who registers a handler is not necessarily the person who decides the step is ready to hold a gate.

*Alternative considered*: derive the handler from the identifier by convention. Rejected — it makes every rename a silent unbinding, and gives an author no way to see what a step is bound to.

### 5. `binding` is removed rather than kept as a label

`Binding` has exactly one enforced effect: a `lesson` may not block its gate. That is a statement about `blocking`, expressed on a second field, and the coherence rule exists only to keep the two agreeing. Where a step came from — the reference document's advice rather than its rules — is what `provenance` already records.

*Alternative considered*: keep it as a display tag with no rules. Rejected — a field that constrains nothing and that no surface reads is a field the next author has to ask about, which is the question that started this change.

### 6. Assignee rules are write-time preconditions, not coherence rules

Every load-time coherence rule is a function of the step set alone, which is what lets one predicate guard a load and a write alike. Assignee validity is not: it depends on the roster, which changes without the step set changing. Left in the coherence list, deactivating a person would retroactively make a stored playbook unloadable — a write in one module breaking a capability that accepted no write, and the direct contradiction of `playbook-authoring`'s "what a write cannot persist, a load cannot see".

So the two assignee rules are checked when a step is written and never when the playbook is loaded. A step whose assignee has since been deactivated keeps loading and keeps being served; the readiness report is what surfaces it. The guarantee `playbook-authoring` carries becomes explicitly one-directional, which is stated there rather than left to be inferred.

*Alternative considered*: give the load path a roster reader too. Rejected — it makes every playbook read depend on another module's store being reachable, and turns a roster edit into a launch-wide outage.

### 7. `launch` reads the roster through `access.application`

Validating an assignee and projecting one to ClickUp both need roster data, and `launch` may only reach `access` through its public application surface. `launch`'s use cases therefore take a roster reader as a collaborator, supplied by the composition root, exactly as `worker.py` already supplies `clickup_sync_job.read_product` across the same kind of boundary.

*Alternative considered*: copy the person's name and ClickUp id onto the step at authoring time. Rejected — it makes every roster correction a step rewrite, and the point of referencing by identifier is that it does not.

## Risks / Trade-offs

- **[Migrating the seeded set is a data rewrite, not an additive migration]** → The text and vocabulary mappings are total and mechanical, and the seeded rows stay re-derivable from the reference document, so a mistake is detectable by the existing re-derivation scenario rather than silent. What is *not* mechanical is status and assignees, and the Migration Plan decides both explicitly rather than by default: the two non-blocking automated rows drop to `in-development`, and every migrated human step is active and unowned.
- **[Every existing ClickUp task's composed name changes meaning]** → It does not: the composition is `name · identifier` where the name is the text that was the description, so an unedited task composes to exactly what it already carries and heals to it. Person-edited tasks remain untouched, as they already are.
- **[The body of a task whose name was shortened could be wiped]** → It would have been: such a task's body holds the step's full former text, was written by the system, and therefore matches its retained value, so a rule composing an *empty* body for a description-less step would rewrite it away. The spec instead composes **no** body for a step carrying no description, and the system never writes a body it did not compose, so those tasks keep what they have.
- **[Migrated steps are active and unowned]** → Deliberate, and visible: they appear in the readiness report until someone accepts them. The ClickUp assignee reconciliation means assigning a step reaches its already-projected task, so this resolves by ordinary use rather than needing a migration.
- **[`launch` gaining a dependency on `access` couples two modules that were independent]** → It is a dependency on a public application surface that `import-linter` already permits and enforces, and it is the dependency the roster was built to serve. The alternative — denormalising people onto steps — trades a module edge for stale data.
- **[Requiring an active assignee on active human steps could block activating work nobody owns yet]** → That is the intent: the step stays `in-development` until someone owns it, which is a truer statement than an active step assigned to nobody. The escape hatch is that `in-development` steps are freely authored and edited.

## Migration Plan

1. Land the schema migration adding the new columns, nullable, and keeping the old ones.
2. Backfill, informed by what the seed actually holds — 97 steps, of which 95 are `human-attested`, one `ai-assisted` and one `automated`, and **neither** of the latter two is blocking:
   - `name` ← `description`; `description` ← null.
   - `kind`/`needs_confirmation` ← `execution` (`human-attested` → `human`; `automated` → `automated` without confirmation; `ai-assisted` → `automated` needing confirmation).
   - `status` ← `active` for live `human` rows; `in-development` for the two automated rows, since no runtime registers a handler for them and `active` would claim something resolves them; `retired` where the record shows retirement. Neither automated row blocks a gate, so the gate-holding floor is unaffected.
   - `automation_brief` ← `rule_policy` **only for rows becoming `automated`**; null on `human` rows, which the rules forbid from carrying one.
   - `assignees` ← empty. The 95 migrated human steps are active and unowned, and the readiness report says so. Backfilling an owner — the roster's only person — would make the report claim the work is owned when nobody has accepted it, which is the honest signal this change exists to produce.
3. Deploy the code reading the new columns.
4. Drop `binding`, `execution` and `rule_policy` in a follow-up migration, once the deployed code no longer reads them.

Rollback between steps 2 and 3 is redeploying the previous image: the old columns are still populated and the new ones are ignored by old code.

## Open Questions

None. The deferred items — running a handler, assigning by role — are scoped out above rather than left undecided.
