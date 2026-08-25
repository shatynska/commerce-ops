# Redesign What a Step Declares

## Why

A step is the unit a ClickUp task is built from, and the fields it carries today cannot build a good one. There is no task name and no task body — one `description` field is composed into the task's *name*, which is why the domain forbids it from spanning more than one line, and why anything longer than a name has to be truncated into one. Nobody can be assigned: no field names a person, so every projected task lands unowned.

Three further fields do not earn their place as written. `automated` and `ai-assisted` are treated identically everywhere the code reads them — both demand a rule policy, both are excluded from ClickUp, and neither has execution machinery behind it — so the distinction records how the work will be done rather than anything the launch reacts to; what actually differs is whether a person must accept the result. `rule_policy` is required the moment a step is marked automated, but the automation it describes usually does not exist yet, so an author must either write a policy for code nobody has committed or leave the step un-authorable. And `binding` has exactly one effect in the whole codebase: a `lesson` may not block its gate.

Now that people are roster rows (`move-principals-to-roster`), assignment has something real to point at, and this is the moment to fix the rest with it rather than migrate the step set twice.

## What Changes

- **A step gains a `name` and keeps a `description`, and they stop being the same field.** `name` is short and single-line — it becomes the ClickUp task's name. `description` becomes optional, may span lines, and becomes the task's body. **BREAKING**: today's single-line `description` rule moves to `name`.
- **A step gains `assignees`** — zero or more roster people, referenced by the roster's generated identifiers. A projected task is assigned to them.
- **BREAKING**: `automated` and `ai-assisted` collapse into one `automated` kind plus a separate `needs_confirmation` flag. The two axes become independent: whether *code or a person* does the work, and whether *a person must accept the result*. Whether the code calls a model is an implementation detail the playbook stops recording.
- **A step gains a lifecycle `status`** — `draft`, `in-development`, `active`, `retired` — and validation tightens as the step matures. Only `active` steps are served to launches, hold gates, and reach ClickUp; the rest are visible to authors only. This is what lets an author write down a step whose automation does not exist yet, which today is impossible without inventing a rule policy.
- **`rule_policy` becomes `automation_brief`**, required only to leave `draft`, and a step gains an optional `handler` naming the use case that resolves it. Activating an automated step requires a `handler` that the code actually registers.
- **BREAKING**: `binding` is removed. Its one effect — advice may not block a gate — is expressed by the `blocking` flag it constrained, and where a step came from is what `provenance` already records.
- **The seeded `lp.*` set migrates**: each step's current `description` becomes its `name`, `human-attested` becomes `human`, `automated`/`ai-assisted` become `automated` with `needs_confirmation` set from which it was, every live step becomes `active`, and `lesson` steps keep `blocking: false`.

Deliberately out of scope: **running** an automated step. This change lets a step *declare* a handler and refuses to activate one naming a handler the code does not register; actually invoking it, and recording what it returns, is the automation runtime and belongs to its own change. Also out of scope: assigning by role rather than by person, which waits on the roster growing roles.

## Capabilities

### Modified Capabilities

- `launch-playbook`: the step-definition requirement is restated around the new field set; `binding` and its lesson-cannot-block rule are removed; the execution-mode vocabulary is replaced by kind plus confirmation; the lifecycle status and its status-dependent coherence rules are added; the single-line rule moves from description to name; the seeded-set requirements are restated against the migrated fields.
- `playbook-authoring`: create and update accept the new fields; activation is a validated transition with its own rules (an active human step needs at least one active assignee; an active automated step needs a registered handler); the gate-holding floor counts only active steps.
- `playbook-admin`: the step form gains name, description, assignees, kind, confirmation, status, automation brief and handler; the table shows status and assignees; non-active steps are visible to authors and set apart from the served set.
- `launch-clickup-sync`: a projected task takes its name from `name` and its body from `description` rather than composing and truncating one field, and carries its assignees; only `active` steps project.

## Impact

- **`launch` domain**: `StepDefinition` gains `name`, `assignees`, `kind`, `needs_confirmation`, `status`, `automation_brief`, `handler`; loses `binding` and `execution`; `description` changes meaning. `Binding` and `ExecutionMode` are deleted; `StepKind` and `StepStatus` are added.
- **`launch` application**: `playbook_authoring`'s create/update signatures change; a new activation rule set; the undecided-rule-policy report becomes a report of what blocks activation.
- **`launch` infrastructure**: the step table gains columns and loses two; a migration rewrites the seeded set; the admin page and its templates grow the new fields; `clickup_sync`'s name composition and truncation are replaced by a direct mapping, and it gains assignee projection.
- **Cross-module**: `launch` needs to resolve roster people to validate assignees and to project them to ClickUp, which it may only do through `access`'s public application surface — a new dependency between the two modules, and the first consumer of the roster beyond access itself.
- **Sequencing**: `add-step-page` is parked behind this change; it should be drafted against the field set this establishes rather than today's.
