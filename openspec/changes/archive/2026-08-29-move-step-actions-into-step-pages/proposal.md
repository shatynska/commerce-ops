## Why

`add-admin-breadcrumb-navigation` made a step's name the way into its own edit page, offered **alongside** the row's existing edit/retire/un-retire/status controls, not instead of them. Once that path in is established, keeping all four as separate row actions on the playbook steps table duplicates that entry point and keeps every row busy with controls that belong to a step, not to the list of them — the same clutter a launch's own detail page was already relieved of.

Unlike when that first change was proposed, the destination already carries what the row would give up: the step's edit page (`edit.html`, via the shared `_fields.html` partial) already renders a `status` select offering every status a step can hold, `retired` included, submitted through the same save the rest of the form uses. Retiring, un-retiring and changing status are one field on that page today, not a gap this change has to fill.

## What Changes

- Remove the `status` and `actions` columns from the playbook steps table — the status-change control and the edit/retire/un-retire buttons a row currently offers.
- The row's own `edit` action is removed; the step's name (already a link to the same edit page, per `add-admin-breadcrumb-navigation`) becomes the row's only way into a step.
- Status changes, retiring and un-retiring move to happen on the step's edit page, through the `status` field the form already renders — no new control is added there.
- The table becomes read-only apart from reordering: position, identifier, name (linked), assignees, discipline and facts. The move controls and narrowing are untouched.
- Column widths are set to a standard, fixed share of the table for both the served and the not-served tables, so a column no longer lands at a different width gate to gate depending on what that gate's steps happen to fill it with.
- **BREAKING**: an admin acting on a step from the list — editing, retiring, un-retiring, changing status — must now open the step's edit page first; the row itself no longer offers those actions directly.

## Capabilities

### Modified Capabilities

- `playbook-admin`: "A step's actions are presented as one affordance vocabulary" narrows to the one action a row still offers — reordering; "A step's name in the table opens its edit page" drops the now-false "alongside the row's existing edit action, not instead of it" caveat, since the name is now the row's only way into the step; "A rejected write names the fields its faults concern" narrows the step list's exemption from field attribution to the move rejection alone — a retirement, un-retirement or status-change rejection is now an edit-form rejection like any other, and is attributed the same way; "The narrowed view survives every write and every move between views" replaces its retirement-rejection example with move — the one write left that still renders its rejection on the list — and gains a new scenario stating explicitly that a rejected retirement now follows the edit form's own rejected-write behavior instead.

## Impact

- `page.html`: the `status_control` and `row_actions` macros' output, and the `status`/`actions` columns' `<th>`s, are removed from both the served table and the not-served table. Column widths become fixed.
- `vocabulary.css`: fixed-width column rules added for the playbook table (mirroring the launch detail page's own, from `add-admin-breadcrumb-navigation`'s follow-up polish); the `status_control` markup's styling rules, now unused, are removed if nothing else references them.
- Tests currently exercising retire, un-retire or status-change through the list page's row controls move to exercise the edit page's `status` field instead. Tests asserting the row's `edit`/`status`/`actions` controls and their markers move or are retired, since the controls they assert on no longer exist.
- The `status_control` macro and its dedicated `/steps/{id}/status` POST route become unreached from the UI; the route itself is left in place, since removing it is not part of what this change was asked to do.
