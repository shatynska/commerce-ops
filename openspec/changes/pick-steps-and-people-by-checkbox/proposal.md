## Why

**The step form's two multi-valued controls cannot be cleared, and one of them cannot realistically be used at all.**

Both are `<select multiple>`. That control deselects only on ctrl/cmd-click: a plain click *replaces* the whole selection with the option clicked, so once an author has chosen anything there is no plain-click route back to none. For `after_steps` none is the **ordinary** value — most steps wait on nothing — and an author who picked a step by accident had no way to undo it. `let-a-step-say-when-it-starts` shipped a partial answer, an empty-valued "waits on nothing" option that clears the set in one click, and that fixed the dead end without touching what makes the control hard to use.

**What makes it hard to use is its size.** The control offers every `active` step but the one being edited: **94 today of 95 active, 63 of them on `listable` alone**. They arrive in one seven-row window, so choosing `lp.ppc.003` means scrolling blind through eight gate groups, and every step after the first needs a ctrl-click. Once anything is chosen there is no way to see what, short of scrolling back to find it. The requirement that the options be "grouped by the gate they belong to" was written to make a list this long navigable; grouping alone does not, because the reader still cannot see the whole of any group.

This was invisible while the control was only ever exercised against a fixture of seven steps. It is visible the moment the form is opened against the real set, and it will get worse: 255 more steps stand as `draft`, and each activation adds one.

**Assignees has the same dead end for the same reason**, and none of the size problem — the roster is a team. It is included here because the two controls sit adjacent on one form, and fixing the interaction of one while leaving its neighbour clearing only by ctrl-click would teach an author that the form is inconsistent rather than that one control is special.

## What Changes

- **Both controls become checkbox lists.** Clearing is unchecking, choosing is clicking, and neither needs a modifier key. Each checkbox carries the same `name` its `<option>` did, so a non-empty choice **parses** exactly as before — the hidden value below adds an empty string to the wire, which every reader of these keys already filters out.

- **An emptied control still submits its key.** This is the one place the submission shape does change, and it would be easy to miss: today an emptied `after_steps` still posts, because the empty-valued "waits on nothing" option is selected and carries the name. Unchecked checkboxes post nothing at all, so without care an emptied control becomes an *absent* key rather than a present-and-empty one — and a surface that reads absent as "not submitted" would silently restore what the author had just cleared when a write is rejected for some unrelated fault. Both controls therefore carry a hidden always-submitted value, and **every** reader of these keys treats an absent one as the empty set — the write path already does, by filtering empties out of `getlist`; the re-render path is where it has to be made true.

- **What is chosen is shown above the list**, as a row of removable chips. The question "what does this step wait on?" becomes readable without scrolling — which the current control cannot answer at all once the list is longer than its box.

- **The dependency control gains two ways of filtering its options, because it is the one with 94.** Gate controls carrying counts filter to one gate in a click; a text control matches identifier, name **and** gate, so `ppc` and `live` both find what an author means. They compose. **Filtering changes only what is shown** — never what is chosen, and never what submits — and where it hides a chosen option the surface says so.

- **The gate counts are load-bearing, not decoration.** `listable 63` against `commit 4` states the shape of the set before an author starts scrolling, which is the fact that makes the control feel unusable in the first place. They count what the control *offers*, so on an edit the step's own gate is one short of its true size.

- **Gates after the gate the form was rendered with are marked**, in the filtering as well as in the list — the step's own on an edit, the submitted one around a rejection, and whatever the create surface was rendered holding otherwise. Rendered once with the form and never recomputed, so they stay markup rather than becoming something the enhancement owes. Depending on a later step is permitted for a non-blocking step and refused for a blocking one, and the mark says so without the form deciding which the author meant.

- **Assignees gets the simple form only**: chips and checkboxes, no filter and no grouping. The roster is a handful of colleagues an author knows by name, and a filter over it would be furniture.

- **Both degrade to a working control where the enhancement cannot run.** The checkboxes, the grouping and the marks are markup and CSS; only the filtering and the live agreement of the chosen-set are enhanced, and without them the list is still complete, grouped and scrollable, showing what was stored as chosen. This is the progressive-enhancement the form's existing script already follows for the kind and anchor toggles.

**Not in this change.** No write rule moves: what may be depended upon, what a start gate may name, and every refusal they can provoke are exactly as `let-a-step-say-when-it-starts` left them. Nothing outside the step form changes; the roster surface's own controls are not touched.

## Capabilities

### New Capabilities

None. This restates how two existing controls are presented.

### Modified Capabilities

- `playbook-admin`: *The step form carries every authorable field* gains the multi-value control rules — clearable without a modifier, what is chosen rendered apart from the options and following their checked state, the emptied-key submission shape, where a fault mark on either control renders, and the rule scoping. A new requirement, *The dependency control's options can be filtered*, carries the filtering, the counts, the later-gate marks and what a response can be asked of them; it is separate because none of it is about the form carrying a field, and folding it in would leave every later delta re-carrying it verbatim.

## Impact

**Presentation only.** `_fields.html` gains the two control bodies and a filter script; the shared admin vocabulary gains the chosen-set, gate-filter and picker styles, each scoped so it matches nothing another admin surface renders. `playbook_admin._dependency_options` already groups by gate and already excludes the non-`active` steps and the step being edited — it gains the per-gate counts of what it offers, and each group's position relative to the gate the form was rendered with.

**No write *rule* changes**, and one read does — on the re-render path rather than the write path. `_form_of` reads both fields with `getlist`, which a checkbox group satisfies identically for a non-empty choice; the emptied case is what the hidden always-submitted value and the absent-key reading above are for. `_submitted_values` and `_authorable_fields` are otherwise untouched, and what may be depended upon is not revisited at all.

**Tests.** `test_playbook_admin_start_fields.py` pins `<select>`, `multiple` and `optgroup` as the dependency control's shape. Those are that file's own INVENTED locators rather than anything the capability requires — the recorded requirement asks only that the control admit more than one step, group them by gate, and identify each by identifier and name, all of which a checkbox list satisfies. Its parser and those assertions move to the new shape.
