## Context

See `proposal.md` — Why. What follows is what the design has to fit.

**The two controls today**, both in `_fields.html`:

```
assignees    <select multiple size="4">   roster's active people, by display name
after_steps  <select multiple size="7">   every active step, <optgroup> per gate,
                                          plus an empty-valued "waits on nothing"
```

**The set the second one ranges over**, measured against the live table:

```
all 94   commit 4   order 3   listable 63   stock-ready 3
         live 9     ignition 7   phase-one-complete 2   graduated 3
```

95 `active` steps, less the one being edited. Two thirds on one gate. 255 further
steps stand as `draft`, and each activation adds one to this list.

**What the write path does with them.** `_form_of` reads both with
`posted.getlist(...)`, filtering empty values; `_authorable_fields` puts the
tuples straight onto the definition. Nothing in that path knows or cares what
kind of control produced the values, which is why this change reaches no
further than the template, the option builder and the stylesheet.

**What the surface already promises.** `playbook-admin` requires that a form
"does not invite a value the write would refuse", that a rejected write marks
the controls its faults concern, and — for the dependency control — that
options are grouped by gate and identified by both identifier and name. None
of that is being revisited; the question is only how the options are drawn.

## Goals / Non-Goals

**Goals:**

- Clearing and choosing without a modifier key, on both controls.
- Make a 95-option set navigable in the time an author actually has: find one
  step, see what is already chosen, and get back out.
- Keep every control working with JavaScript disabled, since the form's
  existing script is already written that way.

**Non-Goals:**

- Changing any write rule. What may be depended upon and what a start gate may
  name are settled and untouched.
- A filter on assignees. The roster is a team; a search box over it is
  furniture that has to be maintained and read.
- Anything outside the step form — the roster's own admin surface keeps the
  controls it has.

## Decisions

### Checkboxes, not a repaired `<select multiple>`

The dead end has a cheap patch — the empty-valued "waits on nothing" option
shipped with `let-a-step-say-when-it-starts` clears the set in one click — and
that patch is why this is a usability change rather than a defect fix. What it
cannot repair is that `<select multiple>` shows one window onto its options,
requires a modifier key to add a second, and gives no way to review what is
chosen without scrolling back through everything that is not.

*Alternative considered: keep the select and add a "Clear" button.* Rejected:
it addresses only the half already addressed, and leaves ctrl-click as the way
to add a second value.

*Alternative considered: a text input with `datalist` autocompletion.* Good at
finding one step and bad at everything else here — it holds one value, so a set
needs repeated inputs, and it shows nothing of what is chosen.

A checkbox group submits identically to a multi-select under `getlist` for any
non-empty choice, which is what keeps this change inside the template — with
one exception, below, that is easy to miss and expensive to miss.

### An emptied control must still submit its key

`<select multiple>` with an empty-valued option always posts the field; a
checkbox group with nothing checked posts nothing. So the naive translation
turns "cleared" into "absent", and a rejected write that re-renders from the
submission would restore what the author had just cleared — the surface is
required to come back holding what was submitted, and it would be holding the
opposite.

Both controls therefore carry a hidden always-submitted value, and the reader
treats an absent key as the empty set. Belt and braces deliberately: the hidden
value is what makes the POST honest, and the absent-key reading is what keeps a
hand-made or scripted submission from meaning something else.

*Alternative considered: keep the visible "waits on nothing" option.* It would
also keep the key present, but it is now a second way to spell what unchecking
already says, and an option among options that means "none of these options" is
the kind of thing that has to be explained every time it is read.

### Chips for what is chosen, above the list

The control's own answer to "what does this step wait on?" is currently
"scroll and look for the highlighted rows". The chosen set is small — nought to
three in every case anybody has described — so it fits above the picker as
plain removable chips, and a reader gets the answer without touching the list.

The chips are the same fact as the checked boxes, rendered twice. That is
deliberate: the list answers "what may I choose", the chips answer "what have I
chosen", and one control answering both is what makes the current one hard to
read.

### Two ways of filtering the dependency control, and none on assignees

"Filtering" throughout, and never "narrowing": this capability already uses
*narrowing* for the page state that survives a write and travels on links, and
giving the same name to a transient filter local to one unsaved control would
make both unreadable.

Grouping was the answer the requirement already reached for and it is not
enough on its own: a group of 63 is not navigable because it is labelled. Two
mechanisms, because they fail differently — a gate filter control is one click and
no typing, and text finds a step whose gate the author does not remember.

**Filtering shows and hides; it never chooses or unchooses.** The distinction
is the one thing here that can silently lose an author's work, and it was
found the hard way: filtering to a gate, unticking everything visible, and
concluding the control was empty while a chosen row sat hidden. Hence the
rule, and hence the surface saying so whenever a chosen option is hidden
rather than leaving the author to infer it.

Text matches **identifier, name and gate together**. Matching the gate too
costs one word per row and means `live` finds that gate's steps without the
author reaching for the gate filter controls; the two mechanisms then agree rather than
competing.

*The counts on the gate filter controls are not decoration.* `listable 63` beside
`commit 4` states the shape of the set before an author starts scrolling, which
is precisely the fact that makes the control feel unusable when it is
discovered by scrolling instead.

Assignees gets neither. One active person today, and a team roster besides; a
filter there would be a control to maintain, test and read past.

The markers are `option-filter` and `option-gate-filter`, in one family and
both naming the control they belong to. `gate-filter` alone would have collided
with the step list's own gate filter, which this capability already has.

### The marks are rendered once, with the form

They describe **the gate the form was rendered with** — the step's own on an
edit, the submitted one around a rejection, whatever the create surface was
rendered holding otherwise — and are never recomputed as the author changes the
gate control.

*Alternative considered: recompute them live.* Accurate at every moment, and it
costs the claim that the marks are markup: they would move into the enhancement
and the degradation rule would have to cover them. It buys accuracy in one case
— changing the gate mid-create — that the form elsewhere trusts the author to
resolve, since the marks withhold nothing and the refusal they hint at is
decided by the write, not by them.

The cost of the cheap choice, stated plainly: an author who changes the gate
without submitting reads marks for the gate they arrived with until the form is
rendered again.

### Clearing from `chosen-set` is not scripted, and the chip must follow the box

The region is required to be clearable from unconditionally, so its affordance
acts on the option's own control rather than on a copy — one control per value,
the checkboxes still authoritative, and nothing to run. Had clearing been
scripted, a form without the enhancement would have shown values it would not
let an author remove, which is exactly the trap the region exists to avoid.

**That affordance is a toggle, and this is the trap the first version of this
decision walked into.** Acting on the option's own control means a second
action on the same affordance *chooses the value again*. If what is shown in
`chosen-set` does not follow the control, an author clears a value, sees it
still listed, acts on it again to be sure — and restores it, with nothing
saying so. Their clearing undone by the action they took to confirm it.

So the rendering must follow the control's state whether or not the
enhancement is running, which a CSS rule keyed on the control's checked state
does with nothing to run.

**That forces a markup arrangement, and it is a decision rather than something
to discover mid-task.** A checked-state rule reaches its target by sibling
relation, and a shared static stylesheet cannot carry a selector per value — so
a chip must sit where its own input can select it. The arrangement:

    chosen-set
      └─ per chosen value:  <input>  +  its chip        (siblings)
    options
      └─ per option:        <label for=…> naming that same input

One input per value, living in `chosen-set` with its chip beside it; the option
row is a label bound to that same input, so clicking either acts on one control
and the checkboxes stay the single authority on what submits. Visual placement
is the containers' own ordering, not a second copy of the input.

**What the enhancement may therefore touch.** It may add a chip for a value
checked since the render, and remove one it added. It **SHALL NOT** touch the
inputs — they are what submits, and a script that regenerated this region's
contents would delete them, taking the author's whole choice with it and
leaving a write that succeeds having cleared the field. Without the script a
newly checked value simply shows no chip until the next render, which is a loss
of convenience and not of correctness.

*Alternative considered: render a chip for every offered value and hide the
unchecked ones.* Nothing would be scripted here at all — but it puts 94 chip
elements in every render of the dependency control, and it makes the
response-level assertion that a chip exists per chosen value vacuous, since it
would hold with nothing chosen. This stays inside what the change already commits to
— "the checkboxes, the grouping and the marks are markup and CSS" — and needs
no new mechanism.

*Alternative considered: accept the stale rendering and say so.* Cheaper to
write and worse to use: it leaves the surface asserting a value is chosen when
it is not, which is the mirror of the state `hidden-chosen` exists to prevent
and the only one of the two nothing else would name.

### Later gates marked, never hidden

A step may depend on one that starts later — freely where it does not block its
gate, and never where it does, which the load rules refuse transitively. The
filter row and the group headings both mark those gates rather than removing
them, for the reason the start-gate control already gives: whether the choice is
refused turns on the `blocking` flag and the step's own gate, both editable in
the same submission, so hiding options would decide for the author which half of
a combination fault they meant.

### What is scripted, and what is not

Two things are scripted and no more: the filtering, and adding a chip for a
value checked since the render (and removing one it added). `chosen-set`
following its controls' *checked* state is CSS, which is what makes the toggle
trap unreachable without a script; the enhancement only spares an author from
waiting for a render to see a chip appear. Everything else —
checkboxes, grouping, the marks, and `chosen-set` following its controls' checked
state — is markup and CSS. With the script
absent the picker is a complete, grouped, scrollable list of checkboxes and the
chips are whatever the server rendered — everything is reachable, only the
filtering is gone. This is the degradation the form's existing script already
accepts for the kind and anchor toggles, and it is why the filter is not worth
a round trip to the server.

*Alternative considered: filter over htmx, server-side.* The form is a single
unsaved edit, so a round trip would either have to carry every other field
along or persist a half-finished step. Neither is worth what a client-side
substring match costs.

### What a response can establish, and what it cannot

The filtering is the enhancement, so a server response can be asked whether
the controls are there, whether each gate states its count, whether every
option carries its gate word, whether later gates are marked and offered,
whether any link carries the filtering, and whether the region the
hidden-chosen report appears in exists. It cannot be asked whether filtering actually narrows
anything, whether the two mechanisms compose, or whether the report appears —
those are behaviours, and this repository's tiers are pure Python with nothing
that drives a browser.

Rather than leave that gap to be discovered when the tests are written, the
requirement says per obligation which is which, and designates the rest for
direct inspection of the rendered page — the device this capability already
uses for what a row's single line cannot be asked of a response. Adding a
browser tier would be a change of its own, against the project's Node-free
commitment, and is not proposed here.

`hidden-chosen` follows from the same fact. Filtering never survives a render,
so no response can carry a *populated* report — which is why the region's role
marker (`hidden-chosen-notice`, always present) is split from the occurrence
marker (`hidden-chosen`, present only when something is hidden), exactly as
`write-failure-notice` is split from `write-failed`.

## Risks / Trade-offs

**A gate heading whose options are all filtered away is hidden**, so the
filtered list reads as a list of what matched rather than as a set of empty
headings. Presentation, not an obligation: nothing turns on it, and an
implementation that left the headings would be worse to read and not wrong.

**A long list of checkboxes is taller than a `<select>`.** → The picker is a
scroll container with a fixed maximum height, and its gate headings stick to
the top edge while scrolling, so the group a row belongs to is always on
screen. Filtering is what makes the height a non-question in practice.

**The chips duplicate state that also lives in the checkboxes.** They can
disagree if the script fails mid-interaction. → The checkboxes are what
submits; the chips are a read-only rendering of them, rebuilt from the boxes on
every change rather than tracked separately, so a disagreement cannot survive
one interaction. Without the script the chips are simply what the server
rendered for the stored value, which is correct for a form nobody has yet
touched.

**The counts are computed per render.** → They come from the same grouping pass
that already builds the options; nothing further is read.

**The filter row wraps to two lines on a narrow viewport.** Eight gate names,
one of them `phase-one-complete`. → Accepted: it wraps rather than scrolling
sideways, which is the rule `restore-launch-detail-column-widths` set for this
admin, and no information is lost when it does.

**This is the third session in a row to edit `test_playbook_admin_start_fields.py`'s
locators**, each time because the file probes for a control shape no requirement
fixes and each time following that file's own "correct this file's field
addressing" instruction. → The delta deliberately fixes no element — this is a
presentation change and mandating markup is the failure mode it is most exposed
to — so it cannot end the churn that way. What it does instead is what this
capability already does for `row-action`, `just-created` and `narrowing-bar`:
pin **markers** rather than elements. `chosen-set`, `option-gate-filter`,
`option-filter` and `hidden-chosen` are observable in the rendered response and
are what a test addresses, while the element carrying each stays free. A future
change may replace the checkbox with anything it likes and the tests keep
pointing at the right thing.

## Migration Plan

None. No stored data, no schema, no write path. The change is what the form
draws; an author who reloads the page gets the new controls, and a form
submitted from the old ones would submit the same field names either way.
