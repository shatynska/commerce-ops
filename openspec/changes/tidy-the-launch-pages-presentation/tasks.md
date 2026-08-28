## 1. Establish what the vocabulary already gives

- [x] 1.1 Read `vocabulary.css`'s `.narrowing-bar` block and confirm its rules are scoped to `.narrowing-bar`'s descendants, not to the steps page or its table, so the launches bar inherits every sizing rule with no new CSS. `design.md` — Decision 1 — asserts this; confirm it rather than assume it. Note in particular that the sizing rules are element-scoped (`.narrowing-bar select`, `.narrowing-bar input`), so no select needs an action marker to be sized.
- [x] 1.2 List, from the two launch templates, every class the pages render, and confirm against `vocabulary.css` which of them no rule matches. Include the ones the header include brings with it (`admin-header`, `admin-surface`), which the vocabulary **does** style, so they are not this change's to touch. That list is the scope of group 3 — write it down, so a fact left unstyled is a decision rather than an oversight.
- [x] 1.3 Record which class names the templates reuse for two unrelated things — at least `finished` (the revealed section, and the mark on a revealed row), `gate` (a row's gate fact, and a gate-sequence entry), `launch-date`, `empty`, and `current`. `current` is the one that escapes these pages: the gate sequence's current entry (`launch.html:25`) and the header's current surface (`_admin_header.html:43`), which every admin page renders. Group 3's rules are scoped against this list; see `design.md` — Decision 5a.
- [x] 1.4 Confirm the shared stylesheet is the only place either page's presentation may live — `launch-admin`'s *The pages' presentation comes from the shared admin vocabulary*, and `playbook-admin`'s *The presentation assets stay behind the admin guard and need no build step*. Nothing in this change adds a `<style>` block, a `style` attribute, or an asset.

## 2. The narrowing bar

- [x] 2.1 Wrap the list's narrowing and its reveal control in one `.narrowing-bar`, the reveal control leading, in the shape `page.html` uses.
- [x] 2.2 Give the reveal control `role="button"` and `class="row-action quiet"`, replacing the bare `.reveal` anchor. Both hrefs it renders — reveal and hide — keep exactly the query strings the route builds today.
- [x] 2.3 Move the narrowing form's controls into a `fieldset role="group"` and mark its submit `row-action`. Mark the submit and the reveal control only: the selects carry no action marker, matching both `page.html` and the delta's own wording. The submit's word may change from `Apply` to `Narrow` to match the sibling surface; nothing else about the form's contract changes.
- [x] 2.4 Replace the needs-attention checkbox with a `<select name="attention">` offering `every launch` (value `""`) and `needs attention` (value `"1"`), and give the gate select the same bare-option shape the steps page uses (`every gate`) rather than a separate `<label>`. Give each select an `aria-label`: dropping the `<label>` elements removes the controls' only accessible name, and `page.html:109` already shows the remedy this repository uses.
- [x] 2.5 Render the active narrowing as each select's `selected` option — both the gate select and the new attention select. The checkbox rendered `checked`, so this is a state the surface shows today and must not lose. Nothing in the existing suite reads it back; that is why the delta carries a scenario for it.
- [x] 2.6 Carry the reveal state through the narrowing form: `{% if reveal %}<input type="hidden" name="finished" value="1">{% endif %}`, mirroring `page.html:87`. Without it a narrowing submitted from the bar drops the reveal, which is the composition defect `design.md` — Decision 3 — records. The route already reads `finished`; do not change it.
- [x] 2.7 Carry the reveal state on the offer to clear a narrowing that matched nothing (`launches.html:44`), which today targets `page_path` and so returns an unrevealed default view. Reveal-then-narrow-to-nothing is newly reachable from the bar, and the delta requires clearing to leave the reveal standing.
- [x] 2.8 Confirm in `launch_admin.py` that `attention=` and an absent `attention` are the same request — `(query_params.get("attention") or "").strip()` at `:484`, narrowing on `bool(gate or attention)` at `:491`. Do not change the route. If this does not hold, fix the template's option values, never the parsing.
- [x] 2.9 Confirm the `finished` and `gate` parameters are otherwise untouched, and that a request carrying `?attention=1` from a bookmark still narrows.

## 3. The vocabulary rules for the launch surfaces

- [x] 3.1 Add a `vocabulary.css` section for the launch list — `.launches`, `.launch-row`, and the facts a row carries — laying the row out as one flex line at baseline with a gap, the link taking the free space, the remaining facts at the quiet ink and fine scale the file's existing tokens give. Reuse `--space-*`, `--ink-quiet`, `--size-fine`; introduce a new token only if no existing one fits.
- [x] 3.2 Add the rules for the detail page — `.gate-sequence`, `.gate-group`, `.gate-heading`, `.step-row` and the facts a step row carries. The step's identifier, discipline and provenance recede; its name, due period and marks stay at reading weight. Leave the journal alone: `read_journal` is `None` and `_detail_for` hard-codes `journal=()`, so no entry renders. Journal-entry rules belong with `add-launch-journal`, where they can be looked at.
- [x] 3.3 Add the rules for the list's revealed section and its `.empty` statements, so a revealed set stays visibly set apart from the bands rather than merely following them. Scope the section's own rules `section.finished`, so they cannot reach the `mark finished` chip on a revealed row.
- [x] 3.4 Confirm every rule added in this group is scoped against the reused class names from 1.3, and that no selector this change adds matches an element rendered by any other surface loading this stylesheet — the steps page, the roster page, the product index (`products.html`) and the product dossier (`product.html`). A selector reaching any of them is a defect of this change, not a bonus.
- [x] 3.5 Amend the `.narrowing-bar` block's comment (`vocabulary.css:443–446`), which says "Both narrow the same set." Once the launches bar is the block's second consumer that is false — the reveal control is not a narrowing, which the delta spends a paragraph establishing. Leaving it teaches the next reader the one thing this change exists to deny.
- [x] 3.6 Confirm no rule renders any fact, or a container holding one, as `display: none`, `visibility: hidden`, or at an ink or scale quieter than the surface's ordinary text where the spec requires it legible — the negative obligation this change's third requirement carries, and the one `playbook-admin` already learned by writing it wrong once.

## 4. The raw product identifier

- [x] 4.1 Remove the `product-id` span from the list row, and let the row's label carry the identifier on the fallback path. `_label_for` already returns the identifier *as* the label when the product is `None` (`launch_admin.py:274`), so the fallback requirement is met by the label alone — and keeping the span as well would print the same 36 characters twice on precisely the row this change exists to make readable. Do not reintroduce it under a `resolved` condition: that is the doubled identifier, not a fix for it.
- [x] 4.2 Confirm both halves against the read model rather than by comparing strings: a resolved row shows no identifier, an unresolved row shows it once as its name. `resolved` (`:180`) is what distinguishes them.
- [x] 4.3 Confirm the row still opens its launch: the identifier stays in the row's link target and in nothing else it renders.
- [x] 4.4 Leave the detail page alone here. It names the launch by `label`, which is already the identifier only on the fallback path, and its step identifiers are required rendered by *A launch's detail page renders its position and every served step*.

## 4a. The last-completed column (added after review, at the admin's direction)

- [x] 4a.1 Carry the most recently recorded completion on the list's read model, from the launch report the page already reads. No further read, no new port.
- [x] 4a.2 Count only a `Satisfied` outcome, order by recording time rather than playbook order, and break a tie by the report's own order.
- [x] 4a.3 Render it as its own column, stating the absence where nothing has been completed rather than leaving the cell empty.
- [x] 4a.4 Pin the reading in tests written alongside the implementation — `test_launch_admin_last_completed.py`. Note in that file that this reverses the project's usual order, and why.
- [ ] 4a.5 Before archive, have `openspec-change-reviewer` read this requirement against the capability. It is the one part of this change that skipped the review `AGENTS.md` binds, at the admin's direction; the skip is recorded in `design.md` — Decision 7.

## 5. Verify against the specification

- [x] 5.1 Run the tests derived from this change's delta spec and confirm each scenario is observed.
- [x] 5.2 Run the whole existing `test_launch_admin_list.py` and `test_launch_admin_detail.py` suites. The narrowing scenarios in particular: `_attention_params` discovers the control from the rendered page and `_selected_of` reads a select's selected option, so the checkbox-to-select substitution should be absorbed — "should" is why they are run before anything is judged.
- [x] 5.3 Run the `playbook-admin`, `roster-admin` and product-dossier surface suites. Note what they can and cannot establish: they read markup, and this change edits markup only on the launch surfaces, so a stylesheet rule that reached a sibling surface would **not** show up here. The selector check is 3.4 and 6.4.
- [ ] 5.4 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the unit + agents tier; run the integration tier before pushing.

## 6. Confirm against the deployment

- [ ] 6.1 After merge and deploy, open `/admin/launches` from a fresh admin link and confirm the narrowing is one line of controls, each sized to its word, with no control running to the container's width. This is the defect that opened the change and it cannot be read from a response.
- [ ] 6.2 Reveal launches no longer in play, then submit a narrowing from the bar, and confirm the revealed set is still revealed. Then confirm the bar shows the narrowing that is active.
- [ ] 6.3 Confirm a row reads as a row: product, gate, date and marks legible and set apart, with no raw identifier on a resolved row. Confirm a launch whose product does not resolve shows its identifier exactly once — if no such launch exists in the deployment, confirm it from the rendered test instead and say which.
- [ ] 6.4 Open a launch from a row and confirm the detail page's gate groups and step rows read as rows, that every fact the page rendered before is still rendered, and that the empty-journal statement still reads correctly.
- [ ] 6.5 Confirm the steps page, the roster page, the product index and the product dossier are unchanged by direct comparison, not by inference from the tests. Look at the admin header in particular: it is the region an unscoped `.current` rule would reach, and it renders on every one of them. This is the only check that can actually catch a stylesheet rule reaching a sibling surface.

## 7. Sequencing

- [ ] 7.1 Do not archive this change before `add-launch-tracking-pages` archives. That change introduces `launch-admin`, is merged and deployed but unarchived, and is itself blocked behind `add-launch-journal`. Archiving this one first creates `openspec/specs/launch-admin/spec.md` holding three presentation requirements and none of the capability they presuppose, and `openspec validate` will not object.
- [ ] 7.2 Merge this change unarchived, as `add-launch-tracking-pages` itself did (PR #89). `AGENTS.md` makes the archive the last commit before a merge; that rule cannot be met while the chain ahead is unarchived, and `add-launch-journal` does not yet exist as a change directory at all, so the chain's release is indefinite. Record the exception on the PR rather than leaving the next reader to rediscover it.
- [x] 7.3 Confirm no other in-flight change carries a `launch-admin` delta that would be written against this change's wording, the way `add-launch-tracking-pages` checks its neighbours for header deltas.
