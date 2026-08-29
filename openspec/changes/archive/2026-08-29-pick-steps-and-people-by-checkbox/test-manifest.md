# Test manifest — `pick-steps-and-people-by-checkbox`

Written before any implementation, from the change's delta specs alone.
No implementation source was read: the MODIFIED requirement's superseded
half was established by comparing the delta against the requirement as it
stands in `openspec/specs/playbook-admin/spec.md`, not against code.

**This manifest is not an artifact the OpenSpec schema knows about.** It
will not appear among `openspec instructions apply`'s context files and
must be read on purpose before implementing.

## Baseline

Full, not scoped.

```
uv run pytest tests/unit tests/agents
1660 passed, 0 failed
```

Taken at `/home/shatynska/projects/commerce-ops`, branch
`contain-the-gap-record-fault`, commit `81e042a`, 2026-08-29, working
tree clean but for an untracked `.claude/worktrees/`. The integration
tier was not run: this change is presentation-only and reaches no I/O,
and `AGENTS.md` runs that tier at `pre-push` rather than at commit time.

After the tests below were added, the same command reports **1666
passed, 24 failed** — 1690 total, being the 1660 of the baseline plus
the 30 tests added here. No previously passing test changed state.

## Test command

```
uv run pytest <identifier>
```

Every identifier below is runnable on its own.

## Files added

| File | Subject |
| --- | --- |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py` | MODIFIED *The step form carries every authorable field* — the response half of its multi-value control rules, plus the two relocated scenarios |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_dependency_option_filtering.py` | ADDED *The dependency control's options can be filtered* — the response half |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_picker_vocabulary_scope.py` | The MODIFIED requirement's stylesheet-scoping clause (`tasks.md` 5.5) |

No existing test file was edited, deleted or disabled. **This pass adds
tests and never subtracts.**

Abbreviations used below:

- `MVC` = `tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py`
- `FIL` = `tests/unit/launch/infrastructure/driving/test_playbook_admin_dependency_option_filtering.py`
- `SCO` = `tests/unit/launch/infrastructure/driving/test_playbook_admin_picker_vocabulary_scope.py`

---

## Scenario accounting

**23 `#### Scenario:` blocks in the delta; 23 accounted for below.**
13 in the MODIFIED requirement, 10 in the ADDED one.

### MODIFIED: *The step form carries every authorable field*

| # | Scenario | Accounted for |
| --- | --- | --- |
| 1 | The form offers name and description separately | **Uncovered here — already covered.** Reproduced verbatim from the served spec and unchanged by this delta; covered by `test_playbook_admin_step_fields.py::test_the_form_offers_name_and_description_separately` and its neighbours. Nothing this change does touches it. |
| 2 | Assignees are chosen from the roster | `MVC::test_assignees_are_chosen_from_the_rosters_active_people` — relocated per `tasks.md` 7.1/7.2. The existing coverage in `test_playbook_admin_step_fields.py` is in the obsolete list below. |
| 3 | A form rejected by validation shows every fault with the typed values | **Uncovered here — already covered.** Unchanged by this delta; covered by `test_playbook_admin_step_fields.py::test_a_form_rejected_by_validation_shows_every_fault_with_the_typed_values`. The two-controls half of it is covered afresh by `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected`. |
| 4 | The form offers both start fields | **Uncovered here — already covered.** Unchanged; `test_playbook_admin_start_fields.py::test_the_form_offers_both_start_fields`, which locates fields by name and not by element, so this change does not supersede it. |
| 5 | Starting immediately is an offered choice | **Uncovered here — already covered.** The start-gate control is not one of the two this change redraws; `test_playbook_admin_start_fields.py::test_starting_immediately_is_an_offered_choice`. |
| 6 | The dependency control is grouped and self-excluding | `MVC::test_the_dependency_control_is_grouped_and_self_excluding` — every assertion about *what* is offered preserved, only the locators moved (`tasks.md` 7.1, 7.2). |
| 7 | A multi-valued control clears without a modifier key | **Split.** Response half: `MVC::test_each_multi_valued_control_renders_a_control_per_value[assignees]`, `[after_steps]`. Behaviour half — that the values can be chosen and cleared with no modifier held — **confirmed by direct inspection of the rendered page**, per the requirement's own classification. |
| 8 | What is chosen is rendered apart from the options and names its field | `MVC::test_what_is_chosen_is_rendered_apart_from_the_options_and_names_its_field`, with `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other` for the chip half. |
| 9 | A cleared value is not left shown as chosen | **Split.** Response half: `MVC::test_the_stylesheet_carries_a_checked_state_rule_reaching_chosen_set` and the negative half of `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other`. The scenario proper — that a value cleared from `chosen-set` stops being shown, with the options unenhanced — is **confirmed by direct inspection of the rendered page**. This is the one `tasks.md` 7.4 names first, since a toggle affordance would silently restore it. |
| 10 | An emptied control still submits its key | `MVC::test_an_emptied_control_still_submits_its_key[assignees]`, `[after_steps]`. See **Gap 1**: neither classification paragraph classifies this obligation; it is covered because `tasks.md` 7.5 assigns it explicitly. |
| 11 | A cleared control stays cleared when the write is rejected | `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected[assignees]`, `[after_steps]`. See **Gap 1**. |
| 12 | A submission omitting the key means the empty set | `MVC::test_a_submission_omitting_the_key_means_the_empty_set[assignees]`, `[after_steps]` (re-render path) and `MVC::test_a_submission_omitting_the_dependency_key_saves_the_empty_set` (write path). See **Gap 1**. |
| 13 | A fault mark cannot be hidden by what the author did to the options | **Split.** Response half: `MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within[assignees]`, `[after_steps]`. That no *filtering* of the options removes the mark is **confirmed by direct inspection of the rendered page**. |

### ADDED: *The dependency control's options can be filtered*

| # | Scenario | Accounted for |
| --- | --- | --- |
| 1 | The control offers both ways of filtering | `FIL::test_the_control_offers_both_ways_of_filtering` |
| 2 | Each gate states how many options it offers | `FIL::test_each_gate_states_how_many_options_it_offers` |
| 3 | The region for the hidden-chosen report exists before anything is hidden | `FIL::test_the_region_for_the_hidden_chosen_report_exists_before_anything_is_hidden` — both halves: the role marker present, the occurrence marker absent from every render. |
| 4 | Every option carries the gate its text filtering matches on | `FIL::test_every_option_carries_the_gate_its_text_filtering_matches_on` |
| 5 | A later gate is marked against the gate the form was rendered with | `FIL::test_a_later_gate_is_marked_against_the_gate_the_form_was_rendered_with` |
| 6 | A create surface marks against the gate it was rendered holding | `FIL::test_a_create_surface_marks_against_the_gate_it_was_rendered_holding` |
| 7 | The filtering reaches no link and no submission | `FIL::test_the_filtering_reaches_no_link_and_no_submission` |
| 8 | The control is complete without filtering | `FIL::test_the_control_is_complete_without_filtering` |
| 9 | Filtering narrows what is shown and never what is chosen | **Uncovered — confirmed by direct inspection of the rendered page.** The scenario says so in its own third bullet ("this is confirmed by direct inspection of the rendered page, no response being able to establish it"), and the requirement's classification paragraph assigns both the narrowing and the hidden-chosen report there. No response can carry it: filtering never survives a render. |
| 10 | Gate filtering and text filtering compose | **Uncovered — confirmed by direct inspection of the rendered page.** Stated in the scenario itself and in the classification paragraph. |

---

## Obligations confirmed by direct inspection of the rendered page

Taken **verbatim** from the delta's own two paragraphs, per `tasks.md`
7.0. None of these is asserted here, and none is asserted through a
proxy pretending to be it. This repository has three Python test tiers
(`AGENTS.md` — *Testing Strategy*) and nothing that drives a browser;
`tasks.md` 7.0 forbids growing one for this change.

From *The step form carries every authorable field*:

- that each control's values can be chosen and cleared without a modifier key
- that clearing from `chosen-set` actually clears
- that a cleared value actually stops being shown
- that no filtering removes a mark

From *The dependency control's options can be filtered*:

- that the filtering *narrows* what is shown
- that the two mechanisms compose
- that a chosen option hidden by filtering is still submitted
- that the report appears when one is

`tasks.md` 7.4 requires that the confirmation be recorded once it is
made. **It has not been made yet** — this pass wrote tests and confirmed
nothing by hand. Whoever implements the change records the confirmation
here or in the change's own artifacts.

---

## Gaps in the delta (`tasks.md` 7.0 — reported, not resolved by guesswork)

`tasks.md` 7.0: "Anything either requirement obliges and neither list
classifies is a gap in the delta, and is to be reported rather than
assigned by guesswork."

**Gap 1 — the emptied-key obligations are unclassified.** *The step form
carries every authorable field* obliges that "An emptied multi-valued
control SHALL still submit its key, present and empty" and that "A
submission that carries no such key SHALL nonetheless be read as the
empty set, by every reader of it". Neither of the requirement's two
lists mentions either. Three of its scenarios rest on them (10, 11, 12).
**Covered anyway, and not by guesswork:** `tasks.md` 7.5 assigns them a
test in as many words ("Cover the emptied-key case from group 3,
including the rejected-write re-render"). The classification paragraph
should say so too, so that the two artifacts do not disagree.

**Gap 2 — the scoping clause is unclassified and carries no scenario.**
The same requirement obliges that "No rule introduced for either of
these controls, or for the filtering … SHALL render on an element
another admin surface renders" and that "None SHALL select `gate` or
`empty` unqualified". Neither list mentions it, and no `#### Scenario:`
states it. **Covered anyway, and not by guesswork:** the requirement
itself says the arrangement is to be made "rather than left to be caught
by inspection", and `tasks.md` 5.5 assigns the test. `SCO` is that test.

**Gap 3 — "attaches to the control as a whole" is unclassified.** The
requirement obliges that "A fault marking either control SHALL attach to
the control as a whole"; the response list names only *where* the mark
renders ("outside anything the options are scrolled within"). Covered
incidentally, as the DERIVED guard in
`MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within`
— the guard fails where the control is unmarked, so the response
assertion is not vacuous. `tasks.md` 6.1 carries the obligation
separately.

**Gap 4 — "the counts SHALL NOT track the text filtering" is
unclassified.** *The dependency control's options can be filtered*
obliges it; neither list mentions it. It is an enhancement behaviour and
no response can carry it. **Not covered, and not assigned:** reported
here per 7.0 rather than moved onto the inspection list by guesswork.

**Gap 5 — "rendered once, with the form, and never recomputed" is
unclassified.** Same requirement, same reasoning: what a response can be
asked is which gates are marked, which is covered; that the marks are
not recomputed as the author changes the gate control is a behaviour
neither list places. **Not covered, and not assigned.**

**Gap 6 (lesser) — the *absence* of `hidden-chosen` is unclassified.**
The response list names "that the region for the hidden-chosen report
exists" but not that the occurrence marker is absent from a render.
Scenario 3's second bullet states it, and the requirement says no
response can carry the occurrence at all, so the absence is read here as
response-askable and asserted in
`FIL::test_the_region_for_the_hidden_chosen_report_exists_before_anything_is_hidden`.
The reading is recorded rather than left implicit.

**Reading recorded, not a gap.** "Where the gate the form was rendered
with names no gate of the sequence … no gate SHALL be marked as later"
carries no scenario of its own. It is read here as falling under the
response list's "that later gates are marked and offered" — *which*
gates are marked is the same obligation, not a further one — and is
covered by
`FIL::test_a_gate_naming_none_of_the_sequence_marks_nothing_as_later`.

---

## Assertion classification

Every assertion in the three files is annotated in place as
**SPECIFIED**, **DERIVED** or (in the file docstrings) **INVENTED**
locator. The summary:

### Specified — traces to a stated requirement

- A control per value, for each of the two fields.
- A region marked `chosen-set` per control, naming its field, rendered
  apart from the options.
- A chip element per chosen value, and none for an unchosen one.
- A served-stylesheet rule keyed on a control's checked state reaching
  `chosen-set`.
- The always-submitted empty value; the absent key read as the empty
  set; a cleared control still cleared on a rejected re-render; a
  non-empty choice still parsing.
- A fault mark rendering outside the element the options are scrolled
  within.
- The dependency control's exclusions (`active` only, not the edited
  step), its identifier-and-name labelling, its grouping by gate.
- The assignee control offering the roster's *active* people by display
  name, and accepting no free-typed identifier.
- Controls marked `option-gate-filter` offering each gate that holds
  options; one marked `option-filter` accepting text.
- Each gate stating its offered count, the edited step excluded from its
  own gate's count.
- The `hidden-chosen-notice` region present; `hidden-chosen` absent.
- Every option carrying its gate.
- Later gates offered and marked, in the filtering and in the list;
  nothing marked where the gate names no gate of the sequence; the
  create surface marking against the gate it was rendered holding.
- No link and no submission carrying the filtering.
- Every option present, grouped, and what is stored shown as chosen.
- A statement rendered for the no-match case.
- Neither the filtering controls nor the gate marks worded as the step's
  own gate, nor as blocking or blocked.
- No rule this change adds rendering on an element another admin surface
  renders; `gate` and `empty` never selected unqualified.

### Derived — inferred, no stated requirement covers it

Each is annotated `# DERIVED` at its assertion.

- That the per-value controls cover exactly what the field offers — the
  complement that stops "a control per value" being satisfied by one
  stray checkbox.
- That an `active` step *is* offered, so the dependency control's
  exclusions are not satisfied by an empty control.
- That the fixture's stored values really are shown as chosen, so the
  chip assertions discriminate.
- That the rejection really marks the control, so the
  outside-the-scroll-container assertion is not vacuous.
- That this change's regions render at least one class no sibling
  surface renders, so `SCO`'s rule filter selects something.
- That gates *not* later than the one the form was rendered with are
  **not** marked — the complement of the marking rule, which the
  requirement states only in the positive.

### Deliberately untested

- The eight obligations listed under *Obligations confirmed by direct
  inspection*, above, with the reason recorded there.
- **`tasks.md` 4.8's second half** — "hide a gate heading whose options
  are all filtered away". `design.md` — Risks records it as presentation
  and explicitly not an obligation, so no test asserts it.
- **`tasks.md` 5.3, 5.4, 5.7** — the picker's bounded height and scroll
  container, the gate row wrapping, and the enhancement staying inline
  with the form's existing script. All computed style or asset shape; no
  delta obligation states them and no response carries them.
- **`tasks.md` 2.8** — that no "waits on nothing" option is added.
  Nothing exists to remove (the task says so), and the delta states no
  obligation about it.
- **Gaps 4 and 5**, above: not covered *and not assigned*, per 7.0.

---

## Obsolete tests

Every entry is a **candidate for human confirmation**, never a
conclusion. **None of these tests was edited, deleted or disabled by
this pass.**

### Search bound

Searched **within `tests/**/test_*.py` and nowhere else**, for
`optgroup`, `multiple`, `_options_of`, `["assignees"]`, `["after_steps"]`
and `selects` across the whole tree. No earlier `test-manifest.md` path
was supplied to this dispatch, so no scenario-to-test mapping was drawn
on; this is a search result, not an index lookup. Four superseded
assertions were found and are listed below — this is **"these were found
by this search"**, not "these are all that exist".

### Candidates

| Test (runner-selectable) | Superseding delta | Evidence |
| --- | --- | --- |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_start_fields.py::test_the_dependency_control_is_grouped_and_self_excluding` | MODIFIED *The step form carries every authorable field* — "Every control admitting more than one value SHALL be choosable and clearable without a modifier key", and the response list's "that each control renders a control per value" | Asserts `dependency in parsed.multiple` ("the dependency control admits only one step"), reads its options from `parsed.selects[dependency]`, and reads grouping from `_FormParser`'s `optgroup` labels. That file's own docstring records these as its INVENTED locators; `proposal.md` — Tests names the file and says its "parser and those assertions move to the new shape". A relocated equivalent, preserving every assertion about *what* is offered, is `MVC::test_the_dependency_control_is_grouped_and_self_excluding`. |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py::test_assignees_are_chosen_from_the_rosters_active_people` | Same requirement, same clause, applied to the assignee control | `assignee_selects = {name: options for name, options in parsed.selects.items() if "assign" in name}` followed by `assert assignee_selects, "the assignee control is not a chooser: the form's selects are …"` — the control being a `<select>` with `<option>`s is the assertion. A relocated equivalent is `MVC::test_assignees_are_chosen_from_the_rosters_active_people`. |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_roster.py::test_a_write_names_a_person_the_page_offered` | Same | `offered = [value for value, _ in _options_of(_states(surface)["assignees"])]`. `_options_of` collects `<option>` elements only, and `_states` takes the *first* element named `assignees` — after this change that is the hidden always-submitted value, which carries no options. The scenario the test covers (*A write names a person the page offered*, `playbook-admin` — *Every write is judged against the same roster the page reads*) is **not** superseded; only the way it reads what the page offered is. `tasks.md` 7.6. |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_writes_reach_the_roster.py::test_a_roster_refusal_is_explicable_from_the_page` | Same | The same `_options_of(_states(surface)["assignees"])` locator, used for the guard `assert NOBODY not in offered`. Same distinction: the scenario stands, the locator does not. `tasks.md` 7.6. |

### At risk, but not superseded — recorded separately

These assert obligations this change does **not** touch. Their reading
mechanism may stop reaching what it reads once a control is a group of
inputs rather than one element. Listed so the implementation step is not
surprised, and deliberately kept out of the obsolete list, since nothing
about what they assert has been superseded.

- `test_playbook_admin_start_fields.py::test_each_start_rule_is_attributed_to_its_control[…]` (six parametrised cases),
  `::test_a_multi_step_fault_marks_the_edited_steps_control`,
  `::test_a_transitive_deadlock_marks_every_declaration_it_turns_on` —
  all read a mark through `_marking_of`, whose `_region_of` is "the
  largest ancestor holding this control and no other". A group of
  checkboxes sharing one `name` collapses that region to the input
  itself, which carries no text; the reading then survives only through
  `aria-describedby`/`aria-errormessage` or a `data-*` attribute whose
  value is the field name. This is exactly what `tasks.md` 6.1 and 6.2
  are for.
- `test_playbook_admin_step_fields.py::test_a_refused_activation_explains_itself_on_the_page` —
  its inline comment about "the edit form's parsed fields default an
  unselected multi-select to its first option" describes a parsing
  artifact that ceases to exist. The assertion is unaffected; the
  comment goes stale.

### Checked and clear

`test_playbook_admin_write_failure_notice.py` (`tasks.md` 7.6): its
`_field(values, "assignee")` resolves by exact field name first, and the
hidden always-submitted value keeps `assignees` present among the form's
submittable fields, so the payload it builds still names a person. Its
`_form_control` already skips unchecked checkboxes, which is the correct
reading of a checkbox group. **No superseded assertion found in that
file.**

---

## Unresolved project questions

Recorded per the dispatched non-interactive discharge: read
`AGENTS.md` (the authority) and `CLAUDE.md` (which imports it); where a
question arose that neither answers, the assumption taken and the tests
depending on it are recorded here rather than resolved silently.

| Question | Assumption taken | Tests depending on it |
| --- | --- | --- |
| Must `option-gate-filter` offer **every** framework gate, or only the gates that hold offered options? Scenario 1 says "offer each gate"; the counts clause says "how many of the offered options each gate holds", which a gate holding none satisfies with `0`. | Asserted only over gates that hold at least one offered option. A control for an empty gate is neither required nor forbidden by these tests. | `FIL::test_the_control_offers_both_ways_of_filtering`, `FIL::test_each_gate_states_how_many_options_it_offers`, `FIL::test_a_later_gate_is_marked_against_the_gate_the_form_was_rendered_with` |
| How is a marker carried — class token, `data-*` attribute, or `id`? `playbook-admin` pins markers and never elements. | All three accepted. Correction point `_carries`, in each file. | Every test in `MVC`, `FIL` and `SCO` that locates a marker |
| What element is "a control per value"? | `<input type="checkbox">` carrying the field's name. A checkbox is the only per-value control that toggles without a modifier. Correction point `_VALUE_INPUT_TYPES`. | `MVC::test_each_multi_valued_control_renders_a_control_per_value[…]` and everything that reads the offered set through it |
| How does `chosen-set` "name its field"? | By carrying the field's submitted name, or a word of it, in an attribute or in its text. Correction point `_NAMES_OF_FIELD`. | `MVC::test_what_is_chosen_is_rendered_apart_from_the_options_and_names_its_field`, `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other` |
| What is a "chip"? | An element inside the field's `chosen-set` region, other than an input, naming the value by identifier or display name. Correction point `_chips_of`. | `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other`, `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected[…]` |
| How is a gate "marked as later"? No artifact fixes the wording. | A class or `data-*` token containing `later`, or one of `later` / `after this gate` / `starts after` / `downstream` in the control's own text. Correction point `_marked_later`. | `FIL::test_a_later_gate_is_marked_…`, `FIL::test_a_create_surface_marks_…`, `FIL::test_a_gate_naming_none_of_the_sequence_…` |
| How does the surface word the no-match case? | One of a generous phrasing set. Correction point `_NO_MATCH_WORDS`. | `FIL::test_the_no_match_case_carries_a_statement` |
| What wording "reads as the step's own gate"? | A narrow phrase set (`step's gate`, `gate of this step`, …) plus the blocking words `tasks.md` 5.6 names. Deliberately narrow: a wide set would fail on any heading containing the word *gate*, which the filter row must contain. Correction points `_OWN_GATE_PHRASES`, `_BLOCKING_WORDS`. | `FIL::test_neither_the_filtering_controls_nor_the_gate_marks_read_as_the_steps_own_gate` |
| How is a fault attributed to a control that is now a group of inputs? `tasks.md` 6.1 asks that it still be, and fixes no mechanism. | A `data-*` attribute whose value is the field name, an aria reference from one of the field's inputs, or a marking attribute on one — the reading `test_playbook_admin_start_fields.py` records. Correction point `_fault_texts`. | `MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within[…]` |
| Which admin surfaces count as "another admin surface"? | The step list, the roster page, the launch list, the launch detail, the product index and the product dossier — the six the app composes besides the step form itself. | `SCO::test_no_rule_this_change_adds_renders_on_another_admin_surface` |

No question arose that `AGENTS.md` answers and these tests contradict.
The tier placement (`tests/unit/<module>/<layer>/`), the test command
(`uv run pytest`) and the test-path glob (`tests/**/test_*.py`) are all
taken from `AGENTS.md` — *Testing Strategy* as written.

`ai-toolkit:testing` and `ai-toolkit:python` were both loaded before any
test was written; the stack has a matching skill, so no absence is
recorded here.

---

## Expected first-run state, per test

30 tests added: **24 fail, 6 pass.** Each pass is accounted for below;
none is recorded as coverage of new behaviour.

### Failing on the value produced (the strongest failure state)

The two controls execute and render — as `<select multiple>` — so these
tests reach their assertions and discriminate. Not an absent target.

- `MVC::test_each_multi_valued_control_renders_a_control_per_value[assignees]`
- `MVC::test_each_multi_valued_control_renders_a_control_per_value[after_steps]`
- `MVC::test_what_is_chosen_is_rendered_apart_from_the_options_and_names_its_field`
- `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other`
- `MVC::test_the_stylesheet_carries_a_checked_state_rule_reaching_chosen_set`
- `MVC::test_an_emptied_control_still_submits_its_key[assignees]`
- `MVC::test_an_emptied_control_still_submits_its_key[after_steps]`
- `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected[assignees]`
- `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected[after_steps]`
- `MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within[assignees]`
- `MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within[after_steps]`
- `MVC::test_the_dependency_control_is_grouped_and_self_excluding`
- `MVC::test_assignees_are_chosen_from_the_rosters_active_people`
- `FIL::test_the_control_offers_both_ways_of_filtering`
- `FIL::test_each_gate_states_how_many_options_it_offers`
- `FIL::test_the_region_for_the_hidden_chosen_report_exists_before_anything_is_hidden`
- `FIL::test_every_option_carries_the_gate_its_text_filtering_matches_on`
- `FIL::test_a_later_gate_is_marked_against_the_gate_the_form_was_rendered_with`
- `FIL::test_a_create_surface_marks_against_the_gate_it_was_rendered_holding`
- `FIL::test_a_gate_naming_none_of_the_sequence_marks_nothing_as_later`
- `FIL::test_the_control_is_complete_without_filtering`
- `FIL::test_the_no_match_case_carries_a_statement`
- `FIL::test_neither_the_filtering_controls_nor_the_gate_marks_read_as_the_steps_own_gate`

Two of those merit a note, because the two cleared-control cases fail on
their *second* assertion. Their first — that the re-rendered form holds
the control cleared — passes today: the re-render already reads an
absent or empty key as the empty set. They fail on the `chosen-set`
region being absent. Recorded so nobody reads the first assertion as
newly satisfied work.

### Failing on the absent region

- `SCO::test_no_rule_this_change_adds_renders_on_another_admin_surface`
  — no surface renders `chosen-set`, `option-filter`,
  `option-gate-filter`, `hidden-chosen-notice` or a per-value control,
  so there is nothing for a rule to be scoped to. It establishes that
  the regions do not exist and **nothing about the scoping assertion**,
  which becomes readable the moment the controls render. The guard is
  explicit rather than implicit precisely so a vacuous pass cannot read
  as the scoping having been arranged.

### Passing on the first run — regression guards, not coverage

- `MVC::test_a_submission_omitting_the_key_means_the_empty_set[assignees]`
- `MVC::test_a_submission_omitting_the_key_means_the_empty_set[after_steps]`
- `MVC::test_a_submission_omitting_the_dependency_key_saves_the_empty_set`
- `MVC::test_a_non_empty_choice_still_parses_and_echoes_no_empty_value`

  `tasks.md` 3.2 and 3.4 say as much: the write path already filters
  empties out of `getlist`, and the re-render already shows nothing
  chosen where the key is absent. These guard that the change does not
  break what already holds — and that is the whole hazard the
  requirement names, since a checkbox group that stopped posting its key
  would land in exactly this path. Each was checked for vacuity against
  a positive control: submitting the stored values re-renders them as
  chosen, so the reading discriminates. The reading is deliberately
  shape-agnostic (`_shown_as_chosen` reads both a checked per-value
  control and a selected `<option>`) for that reason.

- `FIL::test_the_filtering_reaches_no_link_and_no_submission` — there is
  no filtering yet, so nothing carries it. It is what would catch the
  filtering becoming a second page narrowing by accident
  (`tasks.md` 4.10).

- `SCO::test_gate_and_empty_are_never_selected_unqualified` — the served
  sheet carries no such selector today. It is what would catch the
  picker's styles adding one; `gate` is a class name several admin
  surfaces render and `empty` another.

---

## What the implementation step must make pass

Everything in the two failing lists above. In `tasks.md` order:

- **1.x** — `FIL::test_each_gate_states_how_many_options_it_offers`,
  `FIL::test_a_later_gate_is_marked_…`,
  `FIL::test_a_create_surface_marks_…`,
  `FIL::test_a_gate_naming_none_of_the_sequence_…`,
  `MVC::test_the_dependency_control_is_grouped_and_self_excluding`.
- **2.x** — `MVC::test_each_multi_valued_control_renders_a_control_per_value[…]`,
  `MVC::test_what_is_chosen_is_rendered_apart_…`,
  `MVC::test_a_chip_exists_for_each_chosen_value_and_for_no_other`,
  `MVC::test_the_stylesheet_carries_a_checked_state_rule_reaching_chosen_set`,
  `MVC::test_assignees_are_chosen_from_the_rosters_active_people`.
- **3.x** — `MVC::test_an_emptied_control_still_submits_its_key[…]`,
  `MVC::test_a_cleared_control_stays_cleared_when_the_write_is_rejected[…]`,
  and keeping the four regression guards green.
- **4.x** — `FIL::test_the_control_offers_both_ways_of_filtering`,
  `FIL::test_the_region_for_the_hidden_chosen_report_exists_…`,
  `FIL::test_every_option_carries_the_gate_…`,
  `FIL::test_the_control_is_complete_without_filtering`,
  `FIL::test_the_no_match_case_carries_a_statement`,
  and keeping `FIL::test_the_filtering_reaches_no_link_and_no_submission`
  green.
- **5.x** — `SCO::test_no_rule_this_change_adds_renders_on_another_admin_surface`,
  and keeping `SCO::test_gate_and_empty_are_never_selected_unqualified`
  green.
- **6.x** — `MVC::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within[…]`,
  plus the *at risk* tests listed above, which 6.1 and 6.2 are what keep
  passing.
- **5.6** — `FIL::test_neither_the_filtering_controls_nor_the_gate_marks_read_as_the_steps_own_gate`.

The eight obligations under *Obligations confirmed by direct inspection*
are **not** in that list and never become green here. They are confirmed
by hand and the confirmation recorded, per `tasks.md` 7.4.
