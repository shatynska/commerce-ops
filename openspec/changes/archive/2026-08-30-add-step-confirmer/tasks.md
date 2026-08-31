## 1. Domain (`launch_playbook.py`)

- [x] 1.1 Replace `needs_confirmation: bool = False` and `automation_brief: str | None = None` on `StepDefinition` with `confirmer: str | None = None`.
- [x] 1.2 In `_automation_faults`, drop the `automation_brief`-beyond-draft clause and the human-step-cannot-carry-a-brief clause; keep the handler-required-when-active clause and the human-cannot-name-a-handler clause.
- [x] 1.3 Add a pure, per-step load-time check (called from the same per-step loop as `_automation_faults`) rejecting a step whose `assignees` names exactly one person who is also its `confirmer`. Independent of `kind` — applies wherever the shape occurs.
- [x] 1.4 Add `confirmer_faults(steps, *, known, active)` alongside `assignee_faults`: a confirmer reference SHALL be to a person the roster carries (unconditional), and SHALL be active where the naming step is `active` and `automated`. Same "write-time precondition, not load-time rule" shape as `assignee_faults`.
- [x] 1.5 Update the module-level docstring on `StepKind` (currently references `StepDefinition.needs_confirmation`) to reference `confirmer`.

## 2. Application

- [x] 2.1 `playbook_authoring.py`: update `create_step`/`update_step` signatures — drop `needs_confirmation`, `automation_brief`; add `confirmer: str | None = None`.
- [x] 2.2 `playbook_authoring.py`: in `_precondition_faults`, call `confirmer_faults(touched, known=known, active=active)` alongside `assignee_faults`, inside the existing `if roster is not None:` block.
- [x] 2.3 `activation_readiness.py`: remove `MISSING_BRIEF` and its check in `_what_is_missing`; keep `MISSING_HANDLER` and `MISSING_ASSIGNEE` as they are. Update the module docstring's "covers the brief, the handler and an active human step's assignees" line.

## 3. Infrastructure — driven (persistence)

- [x] 3.1 `models.py`: drop the `needs_confirmation` and `automation_brief` columns from `PlaybookStepRow` (or equivalent); add `confirmer: Mapped[str | None] = mapped_column(String, nullable=True)`.
- [x] 3.2 `playbook_repository.py`: update both directions of the row↔`StepDefinition` mapping to match (drop the two old fields, map `confirmer`).
- [x] 3.3 Write an Alembic migration: drop `needs_confirmation` (bool, not null) and `automation_brief` (text, nullable) columns; add `confirmer` (string, nullable). No backfill — confirmed with the user that all current data is test data.

## 4. Infrastructure — driving (automation pass and confirmation)

- [x] 4.1 `automation_pass.py`: in `_settle`, change `if terminal and step.needs_confirmation:` to `if terminal and step.confirmer is not None:`.
- [x] 4.2 `automation_confirmation.py`: narrow `_handle_decision`'s accept/reject authority from "any known, active roster identity" to "the identity belonging to the step's named confirmer, who must be active." Implemented one layer down from where this task described it: `_decide` in `automated_decisions.py` already had the `playbook` and roster person in scope (it's where "known"/"active" were already checked), so the confirmer-match check (`_step_for(playbook, step_id)`, compared against `person.id`) landed there rather than in `automation_confirmation.py`'s thin adapter, which only relays the Slack identity string and never touches the roster or playbook itself.
- [x] 4.3 Preserve the existing wiring-fault handling (`UnreadableRosterError` path) unchanged — only the identity-matching rule changes, not how a broken roster collaborator is reported.
- [x] 4.4 Update `automation_confirmation.py`'s module docstring, which currently states "Only a known, active person may decide" as the implemented rule.

## 5. Infrastructure — driving (admin UI)

- [x] 5.1 `playbook_admin.py`: `_edit_values` and `_submitted_values` — drop `needs_confirmation`, `automation_brief`; add `confirmer`. Also updated `_row` (step-list display) and `page.html`'s row mark from a boolean "needs confirmation" badge to "confirmed by {name}", and `_authorable_fields`' parsing.
- [x] 5.2 `playbook_admin.py`: `_form_of` — confirmed no change needed; `confirmer` flows through the generic single-valued `fields` dict already.
- [x] 5.3 `playbook_admin.py`: updated the `_CROSSINGS` table — dropped the two `automation_brief` entries, added one for the load-time sole-assignee-confirmer rule and one for both confirmer write-time preconditions (placed before the assignee "whom the roster does not carry" entry, since `_crossing` returns on the first substring match and the two messages share that tail).
- [x] 5.4 `templates/_fields.html`: reordered — `Starts at gate`/`Waits on` now sit in their own "When it starts" fieldset right after the timing anchor; `Confirmer`, `Kind`, `Assignees`, and the handler-only fieldset now form the final "How it is resolved" group, in that order.
- [x] 5.5 `templates/_fields.html`: `Needs confirmation` replaced by a single-`<select>` `Confirmer` control sourced from `assignee_options`, with a "No confirmation needed" option bound to `""`/`None`.
- [x] 5.6 `templates/_fields.html`: assignees visibility simplified to `hidden` exactly when `kind == automated` (pinned open when marked) — the `needs_confirmation` disjunction and its rationale comment are gone.
- [x] 5.7 `templates/_fields.html`: `Automation brief` textarea removed; the fieldset (still legended "Automation (automated steps only)") now carries only `Handler`, and its "pinned when marked" logic keys on `marks.get("handler")` alone.
- [x] 5.8 `templates/_fields.html`'s toggle script: dropped the `confirmation` select lookup and the `confirmed` branch — assignees now toggles on `automated` alone; the disable loop is unchanged in shape, now touching only the `handler` input since the brief textarea is gone.

## 6. Seed and reference data

- [x] 6.1 `alembic/data/generate_playbook_reference.py`: remove the `"needs_confirmation": False` literal from the generated step dict; add nothing in its place (the seeded set never names a confirmer, consistent with *A step names who confirms an automated result* and the seed's own "SHALL NOT be required to exercise... a confirmer" rule). Also regenerated the committed `alembic/data/playbook_reference.yaml` (352 lines removed, nothing else changed) since a test asserts the generator's output matches the committed file.
- [x] 6.2 `seed_playbook.py`: drop the `needs_confirmation=step["needs_confirmation"]` keyword from the `StepDefinition` construction; do not add a `confirmer=` keyword (defaults to `None`).

## 7. Test suite (mechanical field-set update)

- [x] 7.1 Updated every `StepDefinition(...)`/`create_step(...)`/`update_step(...)` call site passing `needs_confirmation=` or `automation_brief=` across `tests/unit/` and `tests/integration/` to the new field set — bulk-deleted the boilerplate `=False`/`=None` cases with a scripted pass, then hand-fixed every `needs_confirmation=True` site to a real `confirmer=` value (introducing a second roster-person constant in files where the sole assignee would otherwise collide with the new sole-assignee-equals-confirmer coherence rule).
- [x] 7.2 Retired `test_step_kind_and_confirmation.py` and `test_step_automation_brief_and_handler.py` wholesale (superseded by `test_step_confirmer.py` and the `launch-playbook`/`playbook-authoring` deltas' handler-only coverage). Rewrote the tests whose subject was specifically the removed brief behavior rather than deleting them outright: `test_step_activation.py`'s human-step-automation-fields test (now handler-only), `test_report_activation_blockers.py`'s brief-missing scenario (now handler-missing), `test_playbook_coherence_by_status.py`'s two-violations test (swapped the now-inert "automated past draft, no brief" case for "automated, active, no handler"), `test_playbook_readiness.py`'s coherence-rule sweep (swapped the same case for "human step carrying a handler"), and the `playbook_admin` fault-attribution/create-page/anchor-inputs/step-fields/presentation-vocabulary tests that provoked a rejection via `automation_brief` (now via `handler`) — plus three new `_PROVOCATIONS` entries in `test_playbook_admin_fault_attribution.py` covering the confirmer write-time and load-time rules the old exhaustiveness table had no entries for.
- [x] 7.3 Ran `uv run pytest tests/unit tests/agents` (1717 passed) and `uv run pytest tests/integration` (3 passed, 123 skipped — no `DATABASE_URL` in this environment, consistent with the project's own skip convention) plus `ruff check`, `ruff format --check`, `mypy .` and `lint-imports`, all clean. One real bug surfaced and fixed along the way: `automated_decisions.py`'s new confirmer-match check originally read `person.id`, which the real roster's `Person` domain object does not carry (it uses `.identifier`) — every production decision would have been wrongly refused. Fixed by reusing `playbook_authoring.person_identifier()`, the helper already written for exactly this shape seam.

## 8. Cross-references and stray wording

- [x] 8.1 `product_dossier.py`'s module docstring (currently: "...totally so for a product whose automated steps need no confirmation") — reword to match `confirmer` terminology, per the `product-dossier` delta.
- [x] 8.2 Swept `src/` for remaining `needs_confirmation`/`automation_brief`/"confirmation flag"/"automation brief" mentions and updated them: `clickup_sync.py`'s `is_projectable` docstring, `templates/product.html`'s retained-record comment. `grep -rn "needs_confirmation\|automation_brief\|confirmation flag\|automation brief" src/` now returns nothing.
