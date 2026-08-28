## Why

The launch tracking pages shipped and were opened against the deployment
(`add-launch-tracking-pages`, tasks 8.1–8.3). They serve the right facts, and
they read badly. Three defects were found by looking at them:

1. The list's narrowing renders as full-width form controls, with an `Apply`
   button running past half the viewport. The steps page solved this already —
   its narrowing is a single right-aligned bar at the table's own type scale —
   and the launches form does pick up `form.narrowing { display: flex }`, the
   one rule it shares. Every rule that actually *sizes* those controls is scoped
   to a `.narrowing-bar` wrapper the launches page does not have, so Pico's own
   `button[type=submit], select { width: 100% }` wins unopposed.
2. Every list row carries the product's raw `ProductId` — a UUID — beside the
   product's name, on every row, whether or not the name resolved. The
   capability requires that identifier as a **fallback**, for the launch whose
   catalog product cannot be read; rendering it always puts a 36-character
   string an admin cannot act on in the middle of every line. The admin who
   opened the page asked what it was, which is the defect stated as a symptom.
3. Both pages' rows are sequences of unstyled `<span>`s. Of everything the two
   pages render, the shared vocabulary matches only `mark`, `container` and
   `form.narrowing` — so the attention marks are legible and every other fact
   runs together as one line of prose: `ACME-42 — Widget Pro d8ccbed7-… Gate
   commit 2026-11-01`. The pages satisfy *The pages' presentation comes from the
   shared admin vocabulary* by carrying no styling of their own, and the
   vocabulary holds up its half for almost nothing they render.

## What Changes

- The list's narrowing is rebuilt in the shape the steps page uses: one
  `.narrowing-bar` holding the control that reveals launches no longer in play
  and the narrowing form, the form's controls grouped in a `role="group"`
  fieldset, its submit carrying the `row-action` marker the vocabulary sizes.
  The `Apply` button becomes a control sized to its word.
- The needs-attention **checkbox becomes a select** (`every launch` /
  `needs attention`), so the bar is a row of peer controls rather than a
  checkbox wedged among them. A narrowing is still requested as `attention=1`,
  so no bookmarked or shared URL changes meaning. A select always submits its
  name, so an unnarrowed submission sends the parameter empty where the
  unchecked checkbox sent nothing — the route already reads empty and absent
  identically, as it has always had to for the gate select's `All gates`.
- The narrowing form **carries the reveal state through**, as the steps page's
  form carries its retired state. Today, submitting the narrowing while
  launches no longer in play are revealed silently drops the reveal. That is
  already true and merely obscure; presenting the two controls as peers in one
  bar would make it read as the new bar being broken.
- The list stops rendering the raw product identifier on a row whose product
  resolved. A row whose product cannot be resolved still renders it, which is
  what the existing requirement asks for and what the existing scenarios assert.
- The shared vocabulary gains rules for what the launch surfaces actually
  render: the list's rows and revealed section, and the detail page's gate
  sequence, gate groups and step rows. Each row becomes one legible line with
  its facts set apart, at the weight the `mark` vocabulary already establishes.
  The rules live in `vocabulary.css` with every other admin rule; neither page
  gains styling of its own. The journal region is left alone: `read_journal` is
  `None` until `add-launch-journal` lands, so the detail page renders only the
  empty-journal statement and there is no entry to style or to look at.
- Nothing about what either page **enumerates, serves, orders or refuses**
  changes. No fact is removed from the detail page, no row leaves the list, no
  route or query contract changes beyond the checkbox-to-select substitution
  above, and both surfaces stay read-only.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-admin`: the presentation the surfaces are already required to inherit
  is given its own requirements — the narrowing presented as one bar of peer
  controls rather than full-width stacked ones, a row read as a row, and the
  raw product identifier confined to the fallback the capability already scopes
  it to.

  **This capability has no spec in `openspec/specs/` yet.** It is introduced by
  `add-launch-tracking-pages`, which is merged and deployed but not archived —
  it is itself blocked behind `add-launch-journal`. So this change's delta is
  written as ADDED requirements, and it must not archive before
  `add-launch-tracking-pages` does. Archiving first would create
  `openspec/specs/launch-admin/spec.md` holding three presentation requirements
  and none of the capability they presuppose, and `openspec validate` would not
  object.

## Impact

- `src/commerce_ops/launch/infrastructure/driving/templates/launches.html` — the
  narrowing bar, the identifier fallback, row markers.
- `src/commerce_ops/launch/infrastructure/driving/templates/launch.html` — no
  edit. Its gate groups and step rows already carry the markers the third
  requirement asks for; what that page gains is rules in the stylesheet.
- `src/commerce_ops/shared/infrastructure/driving/static/vocabulary.css` — rules
  for the launch surfaces' regions, beside the ones the other surfaces already
  carry. **Five** admin surfaces load this stylesheet — the step list, the
  roster page, the product index, the product dossier and these two — so no
  selector this change adds may match an element any of the others renders.
- `tests/unit/launch/infrastructure/driving/test_launch_admin_list.py` and
  `test_launch_admin_detail.py` — the existing suites discover the narrowing
  from the rendered page rather than hard-coding its element, and read a
  `<select>`'s selected option, so the checkbox-to-select substitution is
  absorbed rather than breaking them. What they gain is the tests derived from
  this change's own scenarios.
- No route, no use case, no read model, no migration, no dependency.
