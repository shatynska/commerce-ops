## 1. Template: remove the row-level controls

- [x] 1.1 In `page.html`, remove the `status`/`actions` `<th>`s from both table headers (served table and not-served table).
- [x] 1.2 Remove the `<td class="actions">{{ row_actions(step) }}</td>` call from both table bodies (the served-table loop and the not-served-table loop).
- [x] 1.3 Remove `step_cells`'s own trailing `<td class="actions">` (the `status_control`/`step.status_label` cell).
- [x] 1.4 Delete the `status_control` and `row_actions` macros now that neither has a caller.

## 2. Template and CSS: fixed column widths

- [x] 2.1 Give both of `page.html`'s tables a shared class (or reuse `.gate-group` if the section wrapper already carries one) so CSS can scope to them.
- [x] 2.2 In `vocabulary.css`, add `table-layout: fixed` plus a percentage width per remaining column (move, position, name, identifier, assignees, discipline, facts), mirroring `launch.html`'s own scheme and its explanatory comment.
- [x] 2.3 Give any column that can carry a `nowrap` tag or mark a `min-width` floor and wrap the table in an `overflow-x: auto` container, mirroring the launch detail page's own narrow-viewport fix — check whether `facts` (which can hold multiple `.mark`s) needs one.

## 3. Migrate tests off the row's retire/un-retire/status controls

Every test below currently discovers a control on the **list page** via a control-vocabulary helper (`_require_control`, `_status_control`, `_control`) and submits it there. Each moves to: open the step's edit page (the existing `_edit_form`/`_edit_surface`-style helper each file already has), set the `status` field to the target value, and submit that form instead. Where a test's own docstring or scenario title says "from the page" without naming the list specifically, no change to the docstring is needed — the edit page is still "the page."

- [x] 3.1 `test_playbook_admin_page.py::test_a_blocked_retirement_explains_itself` — retire via the edit form's `status` field instead of the row's `retire` control.
- [x] 3.2 `test_playbook_admin_step_fields.py::test_an_activation_from_the_page_lands_and_joins_the_served_set` — activate via the edit form's `status` field instead of `_status_control`.
- [x] 3.3 `test_playbook_admin_step_fields.py::test_a_refused_activation_explains_itself_on_the_page` — same migration as 3.2, for the refusal case.
- [x] 3.4 `test_playbook_admin_step_fields.py` — once nothing else in the file calls it, delete the now-unused `_status_control` helper.
- [x] 3.5 `test_playbook_admin_filtered_moves.py::test_an_accepted_write_keeps_the_narrowing` — retire via the edit form's `status` field. Its assertions stay valid as written: `save_edit` renders the list (`_render_page`) on success exactly as `retire_step` did, so an accepted retirement still ends on the list under the same narrowing.
- [x] 3.6 `test_playbook_admin_filtered_moves.py::test_a_rejected_list_level_write_keeps_the_narrowing` — this scenario is now about **move**, not retirement (per the corrected `The narrowed view survives every write and every move between views` delta: a rejected retirement renders the edit form, not the list, so it no longer illustrates "list-level"). Rewrite the test itself to reject a move — e.g. reuse `test_a_stale_move_leaves_truth_on_the_page`'s stale-version setup, or a move a coherence rule refuses — while a text search is active, and assert the search term still applies to the re-rendered list. Rename the test to match (e.g. `test_a_rejected_move_keeps_the_narrowing`) since, unlike a spec scenario title, a test function name carries no archive constraint.
- [x] 3.6a Add a new test for the delta's new `A rejected retirement keeps the narrowing without leaving the edit form` scenario: reject a retirement (a gate-unheld refusal) submitted through the edit form's `status` field while a gate filter is active, assert the edit form re-renders with the fault (not the list), and assert returning to the list from the form still applies the gate filter — mirroring `test_a_rejected_edit_keeps_the_narrowing_without_leaving_the_form` in the same file.
- [x] 3.7 `test_playbook_admin_filtered_moves.py::test_un_retiring_keeps_the_retired_steps_visible` — un-retire via the edit form's `status` field. Its assertions stay valid as written, for the same reason as 3.5: an accepted un-retirement still ends on the list.
- [x] 3.8 `test_playbook_admin_writes_reach_the_roster.py::test_each_write_reaches_the_roster` — the `retire`, `unretire` and `change_status` (the `else` branch) parametrize cases move to submit through the edit form; `create` and `save_edit` are untouched.
- [x] 3.9 `test_playbook_admin_write_failure_notice.py::test_a_failed_write_does_not_read_as_a_successful_one` — retire via the edit form instead of the row's `retire` control.
- [x] 3.10 `test_playbook_step_name_link.py::test_a_steps_name_opens_its_edit_page` — not caught by the pre-implementation grep (its file name doesn't match `test_playbook_admin*`). Asserted the row's separate `edit` action was "still present and unchanged" alongside the name link, per the requirement's pre-modification text; rewritten to assert only the name link, matching the modified requirement.

## 4. Retire the row-vocabulary presentation tests

These assert presentation of controls (`status`, `edit`, `retire`, `un-retire`) that no longer exist on the row at all. Per the delta spec's rewritten "A step's actions are presented as one affordance vocabulary," the row now offers only reordering.

- [x] 4.1 `test_playbook_admin_presentation_vocabulary.py::test_a_rows_actions_share_one_vocabulary` — rewrite to assert the reorder pair alone carries `row-action` (the delta spec's new "A row's actions share one vocabulary" scenario), replacing the "at least 3 controls including status/edit/retire" assumption.
- [x] 4.2 `test_playbook_admin_presentation_vocabulary.py::test_a_non_active_steps_row_speaks_the_same_vocabulary` — a draft's row no longer offers any action control at all (it holds no slot to reorder either); rewrite to assert that, or retire the test if `test_a_retired_steps_only_action_speaks_the_same_vocabulary`'s rewrite already covers "no actions at all" for a non-active row.
- [x] 4.3 `test_playbook_admin_presentation_vocabulary.py::test_the_destructive_action_is_distinguished_not_amplified` — rewrite to assert no control on any row carries `danger` (the delta spec's new scenario body), since retiring is no longer a row action to distinguish.
- [x] 4.4 `test_playbook_admin_presentation_vocabulary.py::test_a_retired_steps_only_action_speaks_the_same_vocabulary` — rewrite to assert a retired step's row carries no `row-action` control at all (the delta spec's new scenario body), replacing the "un-retire carries row-action, not danger" assertion.
- [x] 4.5 `test_playbook_admin_presentation_vocabulary.py::test_the_vocabulary_does_not_change_which_actions_are_offered` — re-run as-is once 4.1–4.4 land; it only exercises move controls, so it should need no change, but confirm rather than assume.
- [x] 4.6 Re-grep the file for `_is_action_control`, `_in_action_cell`, `RETIRE_HINTS`/`UNRETIRE_HINTS`/`DANGER` after 4.1–4.4: delete whichever become unused rather than leaving them dead.

## 5. Spec-adjacent verification

- [x] 5.1 Confirm `test_playbook_admin_page.py::test_retired_steps_are_reachable_but_set_apart`'s `assert "retired" in revealed.lower()` still passes once the retired row's `step.status_label` text is gone — it may now depend solely on the `class="step status-retired"` marker, which is fine, but confirm rather than assume.
- [x] 5.2 Confirm the `/steps/{id}/status`, `/steps/{id}/retire` and `/steps/{id}/unretire` routes and their use-case-level tests (outside `driving/`, if any) are untouched — this change removes only the row's markup, not the routes or the write logic behind them.

## 6. Verify

- [x] 6.1 `uv run pytest tests/unit tests/agents` passes in full.
- [x] 6.2 `uv run ruff check .` and `uv run ruff format --check .` pass.
- [x] 6.3 `uv run mypy --no-incremental .` passes.
- [x] 6.4 `uv run lint-imports` passes.
- [x] 6.5 `openspec validate move-step-actions-into-step-pages --strict` passes.
