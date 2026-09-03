## Why

The Outcome column shipped in #157 and is wrong on the live page in two ways, one a
defect and one a design the user has since rejected on sight.

**The defect.** `.evidence-summary` is a flex **row** — written when the cell held one
child and a chevron. The finding's result, rule and comment were added as three more
children of it, so they lay out as three narrow columns instead of stacking. The column
is unreadable in production right now.

**The design.** With the columns fixed, the treatment is still not what it should be. The
separating rule reads as table furniture; the finding's comment carries its own two-line
clamp while the verbatim evidence carries another, so the chevron opens only part of the
cell; and the cell is taller than a scannable table row wants to be. What is wanted is
two paragraphs — the established fact in its own ink, then the model's account of it —
with the whole cell two lines closed and the chevron opening all of it.

The second half is why this is a change and not a patch: the served specification requires
a `finding-divide` element to sit between result and comment, and the design removes it.
That clause exists to keep the distinction off colour alone, so it is not simply deleted —
it is re-grounded on the thing that replaces it.

## What Changes

- **The separating element goes.** Two block-level paragraphs, one after the other, is the
  separation. `finding-divide` is removed from the requirement, from the markup, and from
  the tests that assert it.
- **The accessibility clause stays, re-grounded.** The distinction must still be carried by
  more than colour. A paragraph break is structural: a reader who cannot distinguish the
  colours, or who is in the theme the colour was not chosen for, still sees two paragraphs
  on their own lines. What is dropped is the demand for a *specific* separating element,
  not the property it existed to guarantee.
- **One clamp over the whole cell.** The result, the comment, the verbatim evidence and the
  provenance sit inside a single clamped container, two lines closed, and the disclosure
  opens all of it. Today the comment and the evidence clamp separately and the provenance
  never clamps at all, so the chevron opens a fraction of what a reader wants.
- **The clamp becomes a height rather than a line count.** `-webkit-line-clamp` clamps
  *inline* content; the two paragraphs are blocks, and block children of a `-webkit-box`
  are browser-dependent. This is the same trap the previous change's review caught one
  level down.
- **The columns defect is fixed by the same restructuring** — paragraphs inside the clamped
  container stack by construction, so no wrapper and no `flex-wrap` are needed.

### Non-goals

- **No change to what is recorded.** The carried finding, its storage, its travel through a
  pending result and its arrival on the report are all untouched. This is presentation.
- **No change to the other clauses of the rendering requirement.** Field and value still
  lead with no prose before them; the wording still comes off the record; an empty value
  still reads as visible text; the markers `finding-result` and `finding-comment` stay.
- **No change to the dossier or to Slack**, which render results from a different store and
  were out of scope in #157 for reasons that have not changed.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-admin`: *A carried finding's result is rendered ahead of its comment* — the
  separating element is removed, the structural clause is re-grounded on the paragraph
  break, and the clamp is stated as one over the whole cell rather than as separate clamps
  the chevron only partly opens.

## Impact

- **Modified**: `launch.html` (the finding block moves inside `.evidence-clamp` as two
  paragraphs), `vocabulary.css` (`.finding-divide` removed; the clamp becomes a
  `max-height`; `.evidence-summary` loses the `flex-wrap` it never needed).
- **Tests**: `tests/unit/launch/infrastructure/driving/test_launch_detail_finding_rendering.py`
  — the `finding-divide` assertions become obsolete and are replaced by ones over the
  paragraph break and the single clamp.
- **No schema change, no migration, no new configuration.** Nothing outside the launch
  detail page's rendering is touched.
- **The common path stays byte-identical.** A recording carrying no finding renders exactly
  as it does today; the existing pinned test is what proves it rather than the change
  merely intending it.
