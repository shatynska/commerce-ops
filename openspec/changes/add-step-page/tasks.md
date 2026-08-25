## 1. Sequencing prerequisite

- [ ] 1.1 Confirm `reorder-steps-under-filters` has merged to `main` before starting sections 2, 3 and 5; all three depend on its filter-carrying mechanism (design.md — Sequencing)
- [ ] 1.2 Rebase this branch on `main` and drop whatever that change did to the create form's `action`, since this change deletes that form
- [ ] 1.3 Confirm the `## MODIFIED` block for *The narrowed view survives every write and every move between views* still matches the requirement as it landed in `openspec/specs/playbook-admin/spec.md`, and reconcile it if that change's wording moved
- [ ] 1.4 Confirm the same for the narrowing clauses inside the creation requirement, which assert narrowing behaviour that other requirement defines

## 2. Tests derived from the delta specs

- [ ] 2.1 Dispatch `ai-toolkit:openspec-test-writer` against the approved delta specs to produce the test files and `test-manifest.md`
- [ ] 2.2 Record the baseline: run `uv run pytest` and confirm the new tests fail for the stated reason, not for a missing import or fixture

## 3. The create surface

- [ ] 3.1 Add `"discipline": form.get("discipline", "")` to `_submitted_values` (`playbook_admin.py:348`) — without it a rejection reverts the discipline to `discipline_options[0]` and the retry generates an identifier `update_step` will refuse to correct
- [ ] 3.2 Add `GET {PAGE_PATH}/steps/new` behind `_require_admin`, rendering a new `templates/new.html` that includes `_fields.html` with `include_discipline = true`
- [ ] 3.3 Accept the active narrowing on that route and render **Cancel** as a link back to the list carrying it
- [ ] 3.4 Leave `new.html` un-boosted, so the post-create redirect is a plain navigation and its fragment is honoured (design.md — Success redirects)
- [ ] 3.5 Change `POST {PAGE_PATH}/steps/create` to re-render `new.html` on an `InvalidPlaybookError`, passing `_submitted_values(form)` alongside the fault list
- [ ] 3.6 Do the same on `StaleStepSetError`: the stale notice plus the submitted values, persisting nothing
- [ ] 3.7 On a create that lands, return `303` to the list URL carrying the narrowing plus a `#step-<identifier>` fragment, taking the identifier from the `StepRecord` `create_step` returns
- [ ] 3.8 Give each rendered step row an `id` matching that fragment, escaping the dots wherever the identifier is used as a CSS selector
- [ ] 3.9 When the created step falls outside the active narrowing, render the list under that narrowing and state that the created step is outside it, offering to clear it

## 4. Timing anchor inputs

- [ ] 4.1 Group each anchor kind's inputs in `_fields.html` so a group can be rendered offered or not offered as a unit
- [ ] 4.2 Render that state server-side from the anchor kind the surface was rendered with — the step's own on a fresh edit, the submitted one around a rejection, the default on a fresh create
- [ ] 4.3 Add the inline script re-applying the state on `anchor_kind` change, leaving not-offered inputs in the DOM so their values survive
- [ ] 4.4 Confirm a not-offered input's value submitting is still ignored by `_anchor_from_form`
- [ ] 4.5 Confirm the edit page inherits both, since `_fields.html` is shared

## 5. The list page

- [ ] 5.1 Remove the create section from `page.html`
- [ ] 5.2 Add the **Add step** control ahead of the gate tables, linking to the create surface and carrying the active narrowing
- [ ] 5.3 Confirm no create form remains within or after the gate tables

## 6. Verification

- [ ] 6.1 Run `uv run pytest` and confirm the tests from section 2 now pass, with no previously passing test weakened, skipped or deleted
- [ ] 6.2 Confirm the existing create test (`test_playbook_admin_page.py:767-791`) still passes across the `200` → `303` change, since its client follows redirects
- [ ] 6.3 Run `ruff check`, `ruff format --check`, `mypy`, and `import-linter` — confirm no new module-boundary violation
- [ ] 6.4 Exercise the surface by hand: a rejected create keeps all fourteen values including the discipline; a create under a search term that hides it says so rather than looking lost; the anchor offers only its kind's inputs
- [ ] 6.5 Confirm `git diff` touches no file under `launch/domain/` or `launch/application/`
