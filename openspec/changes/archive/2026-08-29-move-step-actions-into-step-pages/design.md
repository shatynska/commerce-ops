## Context

See proposal.md for motivation. Two facts from reading the current code shape the approach:

1. `edit.html` already renders a full `status` `<select>` (via the shared `_fields.html` partial), offering every status a step can hold, `retired` included, submitted through the same `/steps/{id}/edit` POST the rest of the form uses. The parked version of this proposal assumed the edit page would need to *gain* retire/un-retire/status controls; it already has an equivalent one. This change is therefore pure removal on the list side, not relocation-plus-removal.
2. `td.actions` and its `.row-action`/`select` styling in `vocabulary.css` are shared with `roster.html` (the Users page), which also renders an `actions` column. Those rules stay; only `page.html`'s own two columns and the markup that fills them go.
3. `update_step` (behind the edit form's POST) and `retire_step`/`unretire_step` (behind the row controls this change removes) share the same `_write_fields`/`_crossing_retired` logic in `playbook_authoring.py`, so a `status=retired` submission through the edit form stamps `retired_by`/`retired_on` the same way the dedicated route does. One difference exists and is accepted, not fixed: `update_step` calls `_write_fields` with `attribute_as_update=True`, so a retirement made through the edit form additionally stamps `updated_by`/`updated_on`, which `retire_step`'s own `attribute_as_update=False` does not. No spec scenario asserts anything about those two fields, so nothing this change is bound by is affected — recorded here so the divergence is a decision, not an oversight found later.

## Goals / Non-Goals

**Goals:**
- Remove the `status` and `actions` columns and the controls they hold from both of `page.html`'s tables (served and not-served).
- Give both tables a fixed, standard column-width scheme so a column holds its width across every gate's table on the page, matching the launch detail page's own fixed layout.
- Carry every test currently proving retire/un-retire/status-change through the list's row controls over to prove the same behavior through the edit page's `status` field instead, so no coverage is lost.

**Non-Goals:**
- Touching `roster.html` or its shared `.actions`/`row-action` CSS beyond what page.html itself stops using.
- Removing the `/steps/{id}/status` POST route, the `/retire` or `/unretire` routes, or the `status_control` macro's Python-side handler. They become unreached from this UI but are not asked to be deleted, and another caller (a future API consumer, a script) is not this change's business to rule out.
- Changing what a status change, retirement or un-retirement *does* — only where the control that starts it lives.

## Decisions

**The `status_control` and `row_actions` macros are deleted, not left dead.** Once neither call site remains (both the served-table loop and the not-served-table loop drop their `<td class="actions">` calls), the macros have no caller in the file; `page.html` is the only template that defines them. Leaving an unused macro in a template a reader has no reason to open again is the same debt an unused function is anywhere else in the codebase.

**The dedicated `/steps/{id}/status` route is kept, unlike the macro that called it.** A macro is presentation, owned entirely by this page; a route is a wider surface this change was not asked to narrow, and AGENTS.md's scope discipline treats "improvement noticed along the way" as a separate change, not a rider on this one.

**Column widths mirror the launch detail page's own scheme** (`table-layout: fixed` with a percentage per column, scoped to a class both tables share) rather than inventing a second convention. The two tables' column sets differ, so the percentages themselves are page-specific, but the mechanism — and the "why" comment explaining it — is the same one already landed for `launch.html`.

**Tests move to the edit page rather than being deleted and silently uncovered.** A test that currently opens the list, finds a `retire` control on a row, and submits it is rewritten to instead open the step's edit page and submit its `status` field as `retired` — proving the same behavior (a blocked retirement explains itself, a retirement lands, an un-retirement lands) through the surface that now offers it. Tests that assert only presentation of the now-removed controls (the row-action/danger marker vocabulary, the `status`/`actions` column headers) are retired outright, since there is nothing left on the row for them to assert about.

**`A rejected write names the fields its faults concern` is modified, not left alone.** That requirement's own text exempted the list's retirement/un-retirement/status-change rejections from field attribution, reasoning that the list "carries no authorable form to attribute against." Once those three write kinds move onto the edit form, that reasoning is false for them — the edit form is exactly the kind of surface the requirement already binds. Left unmodified, the merged spec would assert something the implementation this change ships contradicts. The narrowed requirement keeps the list's exemption for the one write kind still native to it — move — and states plainly that the other three are now ordinary edit-form rejections.

**`The narrowed view survives every write and every move between views` is modified too, for the identical reason.** Its own "A rejected list-level write keeps the narrowing" scenario used a rejected retirement as its example of a write that "reports the faults" on the re-rendered *list* — read directly against `playbook_admin.py`, a rejection (`InvalidPlaybookError`) from `save_edit` renders `_render_edit` (the edit form), never `_render_page` (the list), regardless of which field was rejected. Confirmed live in both directions: an *accepted* retirement, un-retirement or status-change still ends on the list either way, since `save_edit` renders the list on success — so the requirement's other **accepted-write** scenarios needed no change. The one rejected-write scenario that named retirement was stale, and its body is replaced with a rejected move, the sole write left that renders its own rejection on the list. A **new** scenario, "A rejected retirement keeps the narrowing without leaving the edit form," is added alongside it — retirement's rejection behavior is now a specific case of the general rejected-edit rule, but this spec's own practice elsewhere is to state each write kind's scenario explicitly rather than leave it to be inferred from a more general one, and a test derived only from the general scenario would not by itself prove retirement specifically follows it.

## Risks / Trade-offs

- [An admin used to retiring from the list muscle-memories the old row button] → The status field on the edit page is not new UI to learn, only a different door to the same field; the step's name has been a one-click path to that page since `add-admin-breadcrumb-navigation`.
- [A test asserting row-level retire/status coverage is missed during migration, silently dropping coverage] → Every such test is grepped for by the markers this change removes (`status_control`, `row_actions`, `class="actions"` within `page.html`'s own tests, the dedicated `/status`/`/retire`/`/unretire` submissions reached through the list) before the change is considered done, not just the ones found on a first pass.

## Migration Plan

Applied and merged in one PR, like `add-admin-breadcrumb-navigation` before it — there is no intermediate state to roll out gradually, since the destination (the edit page's `status` field) already exists and ships with this same change's test migration, not after it. Rollback is a revert of the merge commit.
