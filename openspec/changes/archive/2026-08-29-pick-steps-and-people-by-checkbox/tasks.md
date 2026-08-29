## 1. What the option builder hands the template

- [x] 1.1 Have `playbook_admin._dependency_options` carry, per gate, how many **offered options** it holds — the count after the exclusions, so on an edit the step's own gate is one short of that gate's true size, while on a create no step is excluded on *that* ground — every step that is not `active` is excluded on both — and whether it is later than the gate the form was rendered with
- [x] 1.2 Compute "later than" against **the gate the form was rendered with**: the step's own on an edit, the gate the submission carried when re-rendering a rejected write, and whatever the create surface was rendered holding otherwise. Rendered once, never recomputed as the author changes the gate control — that is what keeps the marks markup rather than something the enhancement owes
- [x] 1.3 Keep the exclusions exactly as they are — every step that is not `active`, and on an edit the step being edited. This change moves no write rule and must not quietly move that one
- [x] 1.4 Leave `_assignee_options` as it is: the roster is a handful of people and the simple control needs nothing it does not already return

## 2. The two controls

- [x] 2.1 Render the assignee control as a checkbox per active person, each `name="assignees"`
- [x] 2.2 Render the dependency control as a checkbox per offered step, each `name="after_steps"`, grouped by gate with the gate heading sticking to the top edge of the scroll container
- [x] 2.3 Render what is chosen in a region marked `chosen-set`, one per control and each naming the field it belongs to, since the form carries two
- [x] 2.4 Make the clearing affordance in `chosen-set` act on the option's own control, so clearing needs no script — one control per value, the checkboxes still authoritative
- [x] 2.5 Make what `chosen-set` shows follow the control's own state **without the enhancement**, by a CSS rule keyed on the checked state. That affordance is a toggle: if the rendering does not follow, an author clears a value, sees it still listed, acts again to be sure, and silently restores it. A checked-state rule reaches its target by sibling relation, so a chip must sit where its own input can select it; `design.md` records the arrangement — one input per value in `chosen-set` with its chip beside it, each option row a label bound to that same input. Build that, rather than discovering the constraint and reaching for an inline style block, which 5.1 forbids
- [x] 2.6 Where the enhancement runs, let it **add** a chip for a value checked since the render and **remove** one it added — and never touch the inputs. They live in `chosen-set` under 2.5's arrangement and are what submits, so a script that regenerated the region's content would delete them, take the author's whole choice with it, and leave a write that succeeds having cleared the field
- [x] 2.7 Mark gates later than the gate the form was rendered with in the group headings, and offer every one of them
- [x] 2.8 Add no "waits on nothing" option. Unchecking is the way back to none, and an option among options meaning "none of these options" has to be explained every time it is read. (One was written while this problem was being diagnosed and was never committed; nothing has to be removed.)

## 3. An emptied control must still submit its key

- [x] 3.1 Give both controls a hidden always-submitted value carrying the field's own name and an empty string, so an emptied control posts a present-and-empty key rather than no key at all. Without it a cleared control simply stops posting, since the `<select multiple>` it replaces posted its field whenever anything was selected
- [x] 3.2 Have **every** reader of `after_steps` and `assignees` treat an absent key as the empty set. The write path already does — `getlist` filters empties — so the one that needs making true is the re-render, which is where a restored value would surface
- [x] 3.3 Confirm a write **rejected for an unrelated fault** re-renders with the cleared control still cleared — the case where absent-read-as-unsubmitted would silently restore what the author had just removed
- [x] 3.4 Confirm a non-empty choice still **parses** as it did — the hidden field adds an empty string to the wire, which the readers filter out — so `_form_of` and `_authorable_fields` need no other change, and confirm `_submitted_values` filters it too rather than echoing an empty value back as a chosen one

## 4. Filtering the dependency control

- [x] 4.1 Render gate controls marked `option-gate-filter`, each stating its offered count, plus one that clears the filtering. `option-gate-filter` and not `gate-filter`: the step list already has a gate filter of its own, and one name for two unrelated things in one capability is one too many
- [x] 4.2 Mark later gates there as well as in the list
- [x] 4.3 Render a text control marked `option-filter`, matching identifier, name **and** gate together, so `live` finds a gate and `ppc` finds an identifier
- [x] 4.4 Compose the two: a gate chosen and text entered show their intersection
- [x] 4.5 **Filtering shows and hides only.** Confirm it never checks or unchecks anything, and that a step chosen under one filtering is still submitted under another that hides it
- [x] 4.6 Render the region for that report always, marked `hidden-chosen-notice` for its role, and add `hidden-chosen` naming the count only once a chosen option actually is hidden — the `write-failure-notice`/`write-failed` split, and necessary here because filtering never survives a render, so no response can carry the occurrence
- [x] 4.7 Keep the gate counts fixed to what the control offers; they must not track the text filtering, which changes moment to moment
- [x] 4.8 Say plainly when the filtering in force matches no option, which the delta requires, and hide a gate heading whose options are all filtered away, which it does not — that one is presentation, recorded in `design.md` under Risks
- [x] 4.9 Confirm the whole control still works with the enhancement absent: every option present, grouped, scrollable, and what is stored shown as chosen
- [x] 4.10 Confirm the filtering controls carry no navigation — no link on the form carries the filtering and no filtering state reaches the submission, so it cannot become a second page narrowing by accident

## 5. Presentation

- [x] 5.1 Put the `chosen-set`, `option-gate-filter` and picker styles in the shared admin vocabulary, not on this page, as every other admin style is
- [x] 5.2 **Scope every rule this change adds so it renders on nothing another admin surface renders, and select `gate` or `empty` nowhere unqualified** — over what a rule renders and not what it matches, so a custom-property-only block is exempt, as `launch-admin` words it for its own — now an obligation of this capability's own delta, modelled on the one `launch-admin` states for its selectors rather than inherited from it, since that requirement binds only the selectors that change added. One stylesheet serves them all, and an unscoped `.gate` or `.chip` rule would restyle the launch list's gate cell and the detail page's gate sequence
- [x] 5.3 Give the picker a bounded height and its own scroll container; the page body must not scroll sideways for it
- [x] 5.4 Let the gate row wrap rather than scroll sideways on a narrow viewport — eight gate names, one of them `phase-one-complete`
- [x] 5.5 Assert from the served stylesheet that no rule this change adds renders on an element another admin surface renders, and that none selects `gate` or `empty` unqualified — the delta requires this be arranged rather than caught by inspection, and inspection is what 5.2 rests on until this test exists
- [x] 5.6 Keep both controls clear of *blocked* and its inflections, **and** confirm neither the gate filter row nor the group headings can be read as stating the step's own gate — this change puts a row of eight gate names beside the control that does carry that gate, which is the half of that rule it actively strains
- [x] 5.7 Keep the enhancement inline with the form's existing script, which is what `design.md` assumes throughout. Serving it as a new asset would put it under the guard-and-no-build rule the stylesheet and vendored assets follow, and no clause here binds that — so do not, without adding one

## 6. Fault attribution

- [x] 6.1 Confirm every fault these two fields can provoke still marks its control now that the control is a group of inputs — the six the previous change added, plus the assignee rules
- [x] 6.2 Render a mark on either control **outside the scroll container and unaffected by filtering**, so a mark cannot land where the author must scroll or un-filter to find it
- [x] 6.3 Confirm a rejected write still re-renders holding what was chosen, both controls included

## 7. Tests

- [x] 7.0 Split the new obligations by what can establish them before writing any of them, taking the two lists **verbatim** from the delta — the paragraph beginning "What a response can be asked of these two controls" and the one beginning "What a response can be asked, and what it cannot". Do not restate them here; two lists that differ is what this task exists to prevent. Anything either requirement obliges and neither list classifies is a gap in the delta, and is to be reported rather than assigned by guesswork. Assert the response half; confirm the rest by direct inspection of the rendered page and record that it was, as this capability already does for what a row's single line cannot be asked of a response. Do **not** grow a browser tier for it — that is a change of its own, against the project's Node-free commitment
- [x] 7.1 Move `test_playbook_admin_start_fields.py`'s control probes off `<select>`/`multiple`/`optgroup` and onto the markers this change pins — `chosen-set`, `option-gate-filter`, `option-filter`, `hidden-chosen` — which is what the capability already does for `row-action` and `narrowing-bar`, and what keeps a later change free to replace the element
- [x] 7.2 Keep every assertion that file makes about *what* is offered — the exclusions, the identifier-and-name labelling, the grouping — and change only how they are located
- [x] 7.3 Cover, from a response, exactly the obligations 7.0 assigns to it — including that a chip element exists per chosen value and that the served stylesheet carries the checked-state rule reaching `chosen-set`, which is as far as a response reaches toward the toggle trap
- [ ] 7.4 Confirm by direct inspection of the rendered page, and record that it was, the obligations 7.0 assigns there — first among them that a cleared value stops being shown with the enhancement absent, since that is the case where a toggle affordance would silently restore it
- [x] 7.5 Cover the emptied-key case from group 3, including the rejected-write re-render
- [x] 7.6 Check `test_playbook_admin_writes_reach_the_roster.py` and `test_playbook_admin_write_failure_notice.py` still address the assignee field now that it is a checkbox group

## 8. Verification

- [x] 8.1 Run `uv run pytest` over `tests/unit` and `tests/agents`
- [x] 8.2 Run `ruff check`, `ruff format --check` and `mypy`
- [x] 8.3 Render the step form against the live step set — not the fixture — and confirm the control is usable at 94 options rather than at seven, which is the whole of what this change is for
- [x] 8.4 Render the **create** surface too, and confirm the later-gate marks are computed against the gate it was rendered holding rather than against a step that does not exist. The counts are of what the control offers and do not depend on the gate at all — check that nothing has made them appear to
- [x] 8.5 Confirm the form submits and saves both fields end to end, the empty set included

---

**On 7.4, which is the one task still open.** The form was rendered against the
live 95-step set, served with the real stylesheet and script, and the four
behaviours 7.0 assigns to inspection were written down for a person to try:
clearing a chip twice without the value returning, the two filterings
composing, a chosen option surviving a filtering that hides it, and the whole
control working with the enhancement absent. **Nobody has recorded trying
them.** They cannot be reached from a server response and this repository has
no tier that drives a browser, so the confirmation is a human act and remains
outstanding — deliberately left open rather than ticked on the strength of the
page having been rendered.
