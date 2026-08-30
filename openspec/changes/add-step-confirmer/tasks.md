## 1. Domain (`launch_playbook.py`)

- [ ] 1.1 Replace `needs_confirmation: bool = False` and `automation_brief: str | None = None` on `StepDefinition` with `confirmer: str | None = None`.
- [ ] 1.2 In `_automation_faults`, drop the `automation_brief`-beyond-draft clause and the human-step-cannot-carry-a-brief clause; keep the handler-required-when-active clause and the human-cannot-name-a-handler clause.
- [ ] 1.3 Add a pure, per-step load-time check (called from the same per-step loop as `_automation_faults`) rejecting a step whose `assignees` names exactly one person who is also its `confirmer`. Independent of `kind` — applies wherever the shape occurs.
- [ ] 1.4 Add `confirmer_faults(steps, *, known, active)` alongside `assignee_faults`: a confirmer reference SHALL be to a person the roster carries (unconditional), and SHALL be active where the naming step is `active` and `automated`. Same "write-time precondition, not load-time rule" shape as `assignee_faults`.
- [ ] 1.5 Update the module-level docstring on `StepKind` (currently references `StepDefinition.needs_confirmation`) to reference `confirmer`.

## 2. Application

- [ ] 2.1 `playbook_authoring.py`: update `create_step`/`update_step` signatures — drop `needs_confirmation`, `automation_brief`; add `confirmer: str | None = None`.
- [ ] 2.2 `playbook_authoring.py`: in `_precondition_faults`, call `confirmer_faults(touched, known=known, active=active)` alongside `assignee_faults`, inside the existing `if roster is not None:` block.
- [ ] 2.3 `activation_readiness.py`: remove `MISSING_BRIEF` and its check in `_what_is_missing`; keep `MISSING_HANDLER` and `MISSING_ASSIGNEE` as they are. Update the module docstring's "covers the brief, the handler and an active human step's assignees" line.

## 3. Infrastructure — driven (persistence)

- [ ] 3.1 `models.py`: drop the `needs_confirmation` and `automation_brief` columns from `PlaybookStepRow` (or equivalent); add `confirmer: Mapped[str | None] = mapped_column(String, nullable=True)`.
- [ ] 3.2 `playbook_repository.py`: update both directions of the row↔`StepDefinition` mapping to match (drop the two old fields, map `confirmer`).
- [ ] 3.3 Write an Alembic migration: drop `needs_confirmation` (bool, not null) and `automation_brief` (text, nullable) columns; add `confirmer` (string, nullable). No backfill — confirmed with the user that all current data is test data.

## 4. Infrastructure — driving (automation pass and confirmation)

- [ ] 4.1 `automation_pass.py`: in `_settle`, change `if terminal and step.needs_confirmation:` to `if terminal and step.confirmer is not None:`.
- [ ] 4.2 `automation_confirmation.py`: narrow `_handle_decision`'s accept/reject authority from "any known, active roster identity" to "the identity belonging to the step's named confirmer, who must be active." This needs the step's `confirmer` in scope at decision time — `_handle_decision` already loads the `playbook` via `PlaybookRepository`, so resolve the step definition for `step_id` and compare the pressing Slack identity's resolved roster person against `step.confirmer`.
- [ ] 4.3 Preserve the existing wiring-fault handling (`UnreadableRosterError` path) unchanged — only the identity-matching rule changes, not how a broken roster collaborator is reported.
- [ ] 4.4 Update `automation_confirmation.py`'s module docstring, which currently states "Only a known, active person may decide" as the implemented rule.

## 5. Infrastructure — driving (admin UI)

- [ ] 5.1 `playbook_admin.py`: `_edit_values` and `_submitted_values` — drop `needs_confirmation`, `automation_brief`; add `confirmer`.
- [ ] 5.2 `playbook_admin.py`: `_form_of` — `confirmer` is single-valued (unlike `assignees`/`after_steps`), so read it with `form.get("confirmer")`, normalizing an empty/absent submission to `None`. No change needed to the multi-value-control helper itself.
- [ ] 5.3 `playbook_admin.py`: locate wherever assignee-picker fault-attribution or fault-narrowing pairs list field names together (e.g. the `_Crossing`/pairing tuples seen for `("kind", "status", "assignees")`, `("kind", "automation_brief")`) and update for the new field set — drop `automation_brief` references, add `confirmer` where a coherence fault on it should attribute back to the form.
- [ ] 5.4 `templates/_fields.html`: reorder the tail of the form to `Confirmer`, `Kind`, then `Assignees` (kind=`human`) or `Handler` (kind=`automated`) in Assignees' slot. Move the whole group — currently `Needs confirmation` sits right after the timing-anchor block, `Assignees` right after that, and `Kind`/`Automation` sit near the very end — down to the end, in the new internal order.
- [ ] 5.5 `templates/_fields.html`: replace the `Needs confirmation` `<select>` with a single-select `Confirmer` control (radio group or `<select>`) offering the roster's people plus one explicit "No confirmation needed" option bound to an empty/null value. Reuse the existing picker styling/marking (`marked(marks, ...)`) rather than introducing a new pattern.
- [ ] 5.6 `templates/_fields.html`: simplify the assignees-visibility condition. Drop the `person_involved` disjunction (`kind == human OR needs_confirmation == true`) entirely — replace with a plain `kind == human` check, since assignees no longer has any connection to confirmation. Update the comment block explaining the old disjunction's rationale (now obsolete) or remove it.
- [ ] 5.7 `templates/_fields.html`: remove the `Automation brief` `<textarea>` and its `<small>` hint from the automation fieldset, leaving `Handler` as the sole control there. Reconsider whether the fieldset wrapper and its "pinned when marked" logic (currently keyed on `marks.get("automation_brief") or marks.get("handler")`) still need the brief half of that OR — narrow to `marks.get("handler")` alone.
- [ ] 5.8 `templates/_fields.html`'s toggle script: replace the `confirmation` select lookup and the assignees toggle's `confirmed` branch with a plain kind-only toggle; drop the `automation_brief`-vs-`handler` joint disable loop's brief half (the loop can stay, now touching only the `handler` input).

## 6. Seed and reference data

- [ ] 6.1 `alembic/data/generate_playbook_reference.py`: remove the `"needs_confirmation": False` literal from the generated step dict; add nothing in its place (the seeded set never names a confirmer, consistent with *A step names who confirms an automated result* and the seed's own "SHALL NOT be required to exercise... a confirmer" rule).
- [ ] 6.2 `seed_playbook.py`: drop the `needs_confirmation=step["needs_confirmation"]` keyword from the `StepDefinition` construction; do not add a `confirmer=` keyword (defaults to `None`).

## 7. Test suite (mechanical field-set update)

- [ ] 7.1 Update every `StepDefinition(...)`/`create_step(...)`/`update_step(...)` call site passing `needs_confirmation=` or `automation_brief=` across `tests/unit/launch/` and `tests/integration/launch/` to the new field set. This is a wide, mechanical rename, not new test coverage — the delta specs' new/changed scenarios are `openspec-test-writer`'s responsibility, run separately before this task group.
- [ ] 7.2 Update or retire the tests whose subject is specifically the removed behavior: `test_step_kind_and_confirmation.py`'s boolean-shape assertions, `test_step_automation_brief_and_handler.py`'s brief-specific scenarios, and any fixture helper (e.g. `_automated(...)`) whose keyword defaults reference the old fields.
- [ ] 7.3 Run `uv run pytest` and resolve any remaining failures from the field-set change before treating this change as implementable-complete.

## 8. Cross-references and stray wording

- [ ] 8.1 `product_dossier.py`'s module docstring (currently: "...totally so for a product whose automated steps need no confirmation") — reword to match `confirmer` terminology, per the `product-dossier` delta.
- [ ] 8.2 Sweep for any remaining `needs_confirmation`/`automation_brief`/"confirmation flag"/"automation brief" mentions in comments or docstrings outside the files already named above (e.g. via `grep -rn "needs_confirmation\|automation_brief\|confirmation flag" src/`) and update them to the `confirmer`/handler-only vocabulary.
