# Tasks — redesign-step-fields

> **Sequencing.** This change depends on `move-principals-to-roster`: assignee
> validation and ClickUp assignment both read the roster through
> `access.application`. That change's *code* is on `main` and deployed; its
> *archive* — which is what puts the `roster` and `roster-admin` capabilities
> into `openspec/specs/` — is still open as PR #60. Until that merges, this
> change's references to the roster capability resolve only on a branch
> carrying the archive, so review and implementation should both start from
> one.

## 1. Domain: the step's field set

- [ ] 1.1 Add `StepKind` (`human`, `automated`) and `StepStatus` (`draft`, `in-development`, `active`, `retired`) to `launch_playbook.py`; delete `Binding` and `ExecutionMode`.
- [ ] 1.2 Restate `StepDefinition`: add `name`, `assignees`, `kind`, `needs_confirmation`, `status`, `automation_brief`, `handler`; make `description` optional and multi-line; drop `binding` and `execution`; keep `rule_policy`'s prose under its new name.
- [ ] 1.3 Rewrite the coherence rules: the single-line rule moves from description to name; the automation rule becomes status-dependent (brief beyond `draft`, handler at `active`); a `human` step carrying automation fields is a fault; the lesson-cannot-block rule goes; the gate-holding floor counts only `active` blocking steps.
- [ ] 1.4 Define the status transition rule in the domain: any status may move to any other, each move validated by the rules of the status moved *to*, plus the whole-set rules. Define "beyond `draft`" as `in-development` or `active`, excluding `retired`.
- [ ] 1.5 Add the assignee rules — an assignee must be a person the roster carries, and an `active` `human` step needs at least one who is active. The domain cannot read the roster, so it validates against a set of known-active identifiers the caller supplies; the application layer is what fetches them.

## 2. Application: authoring, activation, reporting

- [ ] 2.1 Extend `create_step` / `update_step` to the new fields; a status change routes through the same validation as any other write.
- [ ] 2.2 Implement activation as a validated transition, including refusing a de-activation that would leave a gate unheld.
- [ ] 2.3 Add the handler registry — the names the code answers to — and check a step's handler against it at activation. Mirror `registrations.py`'s shape rather than inventing a second idiom.
- [ ] 2.4 Check a handler's *registration* only when a step is activated, never at load (design Decision 6's principle applies to the registry as it does to the roster), and report at startup any `active` step whose handler the deployed registry no longer answers for.
- [ ] 2.5 Replace `undecided_rule_policies.py` with a report of what blocks activation: the step, its status, and which of brief / handler / active assignee it lacks.
- [ ] 2.6 Take a roster reader as a collaborator so assignee validation can resolve identifiers, supplied by the composition root across the module boundary (`import-linter` forbids `launch` reaching into `access`'s internals).
- [ ] 2.7 Un-retire returns a step to `in-development`, not `active` — a step retired long ago may no longer satisfy activation, and activating is the separate deliberate act. Update the existing use case and its attribution accordingly.
- [ ] 2.8 Keep the assignee checks out of the load path: they are write-time preconditions only (design Decision 6), so the loaded playbook needs no roster reader and a roster deactivation never breaks a load.
- [ ] 2.9 Retirement now sets `status`; keep `retired_by`/`retired_on` and their un-retire counterparts recording who moved the step and when.

## 3. Infrastructure: persistence and migration

- [ ] 3.1 Add the new columns to the step model, nullable, keeping `binding` / `execution` / `rule_policy` for now.
- [ ] 3.2 Write the backfill migration exactly as Migration Plan step 2 states it, not by the obvious column-for-column mapping: `name` ← `description`; `description` ← null; kind/confirmation ← execution; `status` ← `active` for live `human` rows, `in-development` for the two automated rows, `retired` where the record shows retirement; `automation_brief` ← `rule_policy` **only for rows becoming `automated`** and null on `human` rows, which the rules forbid from carrying one; `assignees` ← empty. Copying `rule_policy` unconditionally produces 95 human steps carrying a brief, which is an unloadable playbook.
- [ ] 3.3 Update the repository's row↔record mapping both ways.
- [ ] 3.4 A follow-up migration dropping `binding`, `execution` and `rule_policy` — after the deployed code has stopped reading them, per the Migration Plan's step 4.

## 4. ClickUp projection

- [ ] 4.1 Replace the composed-from-description name with the step's `name`; the body becomes the `description` where one exists rather than the overflow of a too-long name.
- [ ] 4.2 Change the projection filter to `kind == human` and `status == active`.
- [ ] 4.3 Project assignees, resolving each person to their ClickUp user id and reporting — not silently dropping — an assignee the roster carries without one.
- [ ] 4.4 Generalise the retired-step loop to every non-active step, in both directions, keeping retirement as its named instance.
- [ ] 4.5 Reconcile assignees on later passes, not only at creation, so already-projected tasks stop being unowned; respect a person's own assignment change in ClickUp as an edited name or body is respected.
- [ ] 4.6 Compose **no** body for a step carrying no description, and never write a body the system did not compose — otherwise the migration wipes the body of every task whose name was shortened under the old rule.
- [ ] 4.7 Keep the retained-composition rules exactly as they are; confirm an unedited existing task heals to the new composition and a person-edited one is still never rewritten.

## 5. Admin page

- [ ] 5.1 Add the new fields to the form, with the description as a multi-line input and automation fields hidden or disabled on a `human` step.
- [ ] 5.2 Assignee selection from the roster's active people, by display name.
- [ ] 5.3 Render non-active steps outside their gate's orderable list so the gate's active steps stay reorderable, and refuse server-side a move naming a step that holds no slot; extend the search-disables-reordering rule to a match on the name as well as the description.
- [ ] 5.4 Show status and assignees on the table; show non-active steps set apart from the served set.
- [ ] 5.5 Offer status changes, surfacing a refusal with the refusal's own explanation.
- [ ] 5.6 Extend the search to match name and description alike.

## 6. Tests

- [ ] 6.1 Derive tests from the delta specs before implementing (`ai-toolkit:openspec-test-writer`), per the project's workflow.
- [ ] 6.2 Reconcile `playbook-authoring`'s whole-set validation scenario, which currently tests an empty description and a `lesson`-bound blocking step — neither of which remains a fault.
- [ ] 6.3 Reconcile the existing step tests: the seeded-set re-derivation tests move from description to name, the execution-mode vocabulary tests become kind-and-confirmation, and the lesson-cannot-block test goes with the rule. **Rewrite from the new requirement; do not edit assertions to pass.**
- [ ] 6.4 Integration-tier coverage for the migration's backfill against live Postgres.

## 7. Documentation and verification

- [ ] 7.1 Update the capability `Purpose` paragraphs the change's vocabulary outdates — `launch-clickup-sync`'s "human-attested steps", `playbook-authoring`'s retire/un-retire framing, and `playbook-admin`'s "live step set whole" — directly in `openspec/specs/`, since a delta's Purpose is ignored for an existing capability.
- [ ] 7.2 Update `AGENTS.md`'s architecture summary where it describes what a step declares, and `README.md` where it names the step vocabulary.
- [ ] 7.3 Re-sequence `add-step-page` against this field set, or note in its proposal that it is superseded by the form this change specifies.
- [ ] 7.4 Full verification: `uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and both migrations against a local database.
