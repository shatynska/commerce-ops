## Why

`assignees` answers who does a step's work, but for an `automated` step whose
result `needs_confirmation`, nothing names who is trusted to accept or reject
it — the runtime lets *any* known, active roster person decide, and the
playbook spec's own rationale ("where it needs confirmation they are who is
asked") already gestures at a narrower rule the implementation never
enforced. A step's confirmer is a distinct responsibility from its doer, and
it is always exactly one person, not a set — a shape the current boolean
flag cannot express. Separately, `automation_brief` has proven to add no
real value once a step names a `handler`: the ticket that builds a handler
already needs far more specification than a one-line brief holds, and
`description` covers what the brief was for. Both fields are touched by the
same authoring-form pass, so they are addressed together.

## What Changes

- **BREAKING**: `needs_confirmation: bool` is replaced by `confirmer: str | None` on a step definition. A named confirmer *is* the "needs confirmation" fact — there is no longer a separate flag, and no state where confirmation is needed but nobody is named.
- **BREAKING**: Deciding a pending automated result in Slack is restricted to the step's named `confirmer` alone. The existing "any known, active roster person may decide" latitude is removed — a pending result now blocks entirely if the confirmer is unreachable, with nobody else able to act on it.
- A step definition may name a `confirmer`: a single roster identifier, validated the same way an assignee is (must be known to the roster; must be active where the step is `active` and `automated`).
- A `human` step's `confirmer` carries no meaning and is accepted rather than rejected — the same treatment `needs_confirmation` received on `human` steps, so flipping `kind` never forces clearing an unrelated field.
- New coherence rule: a step is rejected where `assignees` names exactly one person who is also its `confirmer` — that shape can never produce a real second opinion.
- **BREAKING**: `automation_brief` is removed entirely — the field, its "required to leave draft" write-time rule, and its entry in the activation-blockers report. An `automated` step's only remaining authoring requirement is a `handler`, required to become `active`.
- The step authoring form (`playbook_admin.py`) reorders its fields: `Confirmer`, `Kind`, and then `Assignees` (kind = `human`) or `Handler` (kind = `automated`, shown in Assignees' place) move to the end of the form, in that order. The `Automation brief` input is removed.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `launch-playbook`: the step-definition field set changes (`needs_confirmation` → `confirmer`, `automation_brief` removed); the assignee/confirmer coherence rules gain the confirmer-known/active write-time preconditions and the single-assignee-equals-confirmer rejection, the latter a load-time coherence rule enumerated in the renamed *An incoherent playbook is rejected against its steps' status and shape* (formerly *...against each step's status*; renamed as part of a REMOVED+ADDED pair, since dropping its now-void "brief absent" scenario couldn't be expressed as a same-titled MODIFIED — the ADDED version also edits, rather than drops, the "human step carrying a brief or a handler" bullet down to "carrying a handler"); the automation-brief-and-handler requirement narrows to handler alone; the "field set is read back" scenario and the seeded-set requirements' mention of `needs_confirmation` update to `confirmer`.
- `launch-step-automation`: "Only a known, active person may decide a pending result" is replaced by "only the step's named confirmer may decide it" — the roster-membership and active-status checks still apply, but scoped to one identifier instead of the whole roster; the hold-vs-record-immediately requirements and the retained-record boundary reword "confirmation flag" to "confirmer"; the accept/reject requirements' scenarios reword "a known active person" to "the step's named confirmer".
- `playbook-authoring`: "A step can be created" drops `confirmation flag`/`automation brief` from the authorable field list and adds `confirmer`; "Activation is a validated transition" drops the automation-brief clause from what an `automated` step needs to activate; "Every write is validated as the playbook it would produce" — which names and counts the roster-dependent write-time preconditions and the three cases a supplied roster can fall into — is updated to include confirmer's known/active preconditions alongside the assignee ones, since `confirmer_faults` shares that exact validation site and shape.
- `product-dossier`: "The produced record states what it does not cover" rewords "a step whose confirmation flag is true" to "a step naming a confirmer" — a terminology update with no behavioral change, since a named confirmer is exactly the old flag's true state.

## Impact

- Domain: `src/commerce_ops/launch/domain/launch_playbook.py` (`StepDefinition`; `assignee_faults` gains a sibling `confirmer_faults` for the roster-dependent write-time checks; a separate pure per-step function adds the load-time sole-assignee-equals-confirmer coherence rule).
- Application: `src/commerce_ops/launch/application/playbook_authoring.py` (create/update signatures), `src/commerce_ops/launch/application/activation_readiness.py` (drop `MISSING_BRIEF`).
- Infrastructure (driven): `src/commerce_ops/launch/infrastructure/driven/models.py` (drop `needs_confirmation`, `automation_brief`; add `confirmer`), `playbook_repository.py`, an Alembic migration (drop two columns, add one, no backfill — all current data is test data).
- Infrastructure (driving): `src/commerce_ops/launch/infrastructure/driving/playbook_admin.py` and `templates/_fields.html` (field reorder, new single-select confirmer picker, brief input removed), `src/commerce_ops/launch/infrastructure/driving/automation_pass.py` (`step.needs_confirmation` → `step.confirmer is not None`), `src/commerce_ops/launch/infrastructure/driving/automation_confirmation.py` (decision authority narrows to the resolved confirmer identity).
- Specs: `openspec/specs/launch-playbook/spec.md`, `openspec/specs/launch-step-automation/spec.md`, `openspec/specs/playbook-authoring/spec.md`, `openspec/specs/product-dossier/spec.md`.
- Tests: the wide set of unit/integration tests constructing `StepDefinition` with `needs_confirmation=...` or `automation_brief=...` kwargs need updating to the new field set (mechanical, but broad).
