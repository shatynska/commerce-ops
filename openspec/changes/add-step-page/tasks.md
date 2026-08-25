## 1. Sequencing prerequisite

- [ ] 1.1 Confirm `reorder-steps-under-filters` has merged to `main` before starting sections 2, 3 and 5; all three depend on its filter-carrying mechanism (design.md — Sequencing). Merging is not archiving — the spec-level hazard is guarded at 6.6
- [ ] 1.2 Rebase this branch on `main` and drop whatever that change did to the create form's `action`, since this change deletes that form
- [ ] 1.3 Confirm the `## MODIFIED` block for *The narrowed view survives every write and every move between views* still matches the requirement as it landed in `openspec/specs/playbook-admin/spec.md`, and reconcile it if that change's wording moved
- [ ] 1.4 Confirm the same for the narrowing clauses inside the creation requirement, which assert narrowing behaviour that other requirement defines

## 2. Tests derived from the delta specs

- [ ] 2.1 Dispatch `ai-toolkit:openspec-test-writer` scoped to the scenarios this change introduces — the creation requirement's, the two create-surface narrowing scenarios, and the anchor requirement's. The other five narrowing scenarios belong to `reorder-steps-under-filters` and are already covered by its tests
- [ ] 2.2 Record the baseline: run `uv run pytest` and confirm the new tests fail for the stated reason, not for a missing import or fixture

## 3. The create surface

- [ ] 3.1 Hoist `_DISCIPLINE_OPTIONS: Final = [d.value for d in Discipline]` to module scope and have `_option_context()` (`playbook_admin.py:250`) use it — today `discipline_options` exists only as a dict key, so `_submitted_values` cannot refer to it
- [ ] 3.2 Add `"discipline": form.get("discipline") or _DISCIPLINE_OPTIONS[0]` to `_submitted_values` (`playbook_admin.py:348`) — without the key a rejection reverts the discipline and the retry generates an identifier `update_step` will refuse to correct. Not a `""` default: an empty string matches no option and renders nothing selected
- [ ] 3.2a Make the discipline field required, resolving the disagreement between the create route's `Discipline.LISTING` fallback (`playbook_admin.py:435`) and the template's first option (`strategy`) — the select always submits a value, so only a hand-built POST omits it
- [ ] 3.3 Add `GET {PAGE_PATH}/steps/new` behind `_require_admin`, rendering a new `templates/new.html` that includes `_fields.html` with `include_discipline = true`
- [ ] 3.4 Accept the active narrowing on that route and render **Cancel** as a link back to the list carrying it
- [ ] 3.5 Carry the active narrowing on `POST {PAGE_PATH}/steps/create` too — via the create form's `action` query string — and use it for the rejection re-render's **Cancel** link and for the success redirect. Task 1.2 removes what `reorder-steps-under-filters` put there, so this does not arrive for free
- [ ] 3.6 Put `hx-boost="false"` on the **Add step** control, on the create form in `new.html`, and on **Cancel** — so no transition depends on an attribute inherited from a page being replaced. Setting it on `new.html`'s `<body>` instead would not work: while **Add step** is still boosted, the response is swapped *into* `page.html`'s body and the new body's attributes are discarded (design.md — Success redirects)
- [ ] 3.7 Change `POST {PAGE_PATH}/steps/create` to re-render `new.html` on an `InvalidPlaybookError`, passing `_submitted_values(form)` alongside the fault list
- [ ] 3.8 Do the same on `StaleStepSetError`: the stale notice plus the submitted values, persisting nothing
- [ ] 3.9 On a create that lands, return `303` to `{PAGE_PATH}?<narrowing>&created=<identifier>#step-<identifier>`, taking the identifier from the `StepRecord` `create_step` returns. The `created` parameter is what makes 3.11 possible — a fragment is never sent to the server
- [ ] 3.10 Give each rendered step row an `id` matching that fragment, escaping the dots wherever the identifier is used as a CSS selector
- [ ] 3.11 Have the list `GET` read `created`, and render the notice only when clearing the narrowing being offered would actually reveal that step — name it as falling outside, and offer the clear
- [ ] 3.12 Have that clear-narrowing offer keep `created` and the fragment, so clearing lands on the created step rather than at the top of the set
- [ ] 3.13 Render the list unchanged when `created` is absent, names no served step, or names one the offered clear would not reveal — a step retired since it was created is served by `steps.load()` and filtered by `_visible`, so a naive "served but hidden" test would offer a clear that reveals nothing
- [ ] 3.14 Carry `created` forward only on the clear-narrowing offer of 3.12 — the list's own controls carry the narrowing alone, so the notice cannot re-fire on renders that follow an unrelated action

## 4. Timing anchor inputs

- [ ] 4.1 Wrap each anchor input in `_fields.html` in its own group, so a group can be rendered offered or not offered. Per input, not per kind: `anchor_start` serves two kinds and must not be rendered twice
- [ ] 4.2 Render that state server-side from the anchor kind the surface was rendered with — the step's own on a fresh edit, the submitted one around a rejection, the default on a fresh create
- [ ] 4.3 Add the inline script re-applying the state on `anchor_kind` change, leaving not-offered inputs in the DOM so their values survive. Place it inside the swapped region, with `_fields.html` — a `<head>` script never runs on the edit page, which is reached by a boosted body swap
- [ ] 4.4 Confirm a not-offered input's value submitting is still ignored by `_anchor_from_form`
- [ ] 4.5 Keep `anchor_start` offered under both `window` and `open-ended` — it is the one input two kinds share (`_fields.html:71`) — and keep the kind selector offered under every kind
- [ ] 4.6 Confirm the edit page inherits both, since `_fields.html` is shared

## 5. The list page

- [ ] 5.1 Remove the create section from `page.html`
- [ ] 5.2 Add the **Add step** control ahead of the gate tables, linking to the create surface and carrying the active narrowing
- [ ] 5.3 Confirm no create form remains within or after the gate tables

## 6. Verification

- [ ] 6.1 Run `uv run pytest` and confirm the tests from section 2 now pass, with no previously passing test weakened, skipped or deleted
- [ ] 6.2 Confirm the existing create test (`test_playbook_admin_page.py:767-791`) still passes across the `200` → `303` change — `_submit` calls `client.request(...)` without `follow_redirects`, so the TestClient default of `True` applies
- [ ] 6.3 Note that the same test finds the **Add step** control only because `_control(page, contains=("new",))` matches the `/steps/new` route; renaming that route breaks it
- [ ] 6.4 Run `ruff check`, `ruff format --check`, `mypy`, and `import-linter` — confirm no new module-boundary violation
- [ ] 6.5 Exercise the surface by hand: a rejected create keeps all fourteen values including the discipline; a create under a search term that hides it says so rather than looking lost; the anchor offers only its kind's inputs
- [ ] 6.6 Before archiving, confirm `reorder-steps-under-filters` is already archived and that `openspec/specs/playbook-admin/spec.md` carries its narrowing requirement — archiving out of order silently drops this change's create-surface clauses
- [ ] 6.7 After archiving, edit `openspec/specs/playbook-admin/spec.md` directly to correct the capability Purpose, which still says the set is changed "in place" by "inline edit, create". A Purpose is not carried by a delta, so `openspec validate` will not report it
- [ ] 6.8 Confirm `git diff` touches no file under `launch/domain/` or `launch/application/`
