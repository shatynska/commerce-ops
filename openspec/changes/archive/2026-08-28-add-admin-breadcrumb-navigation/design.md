## Context

See `proposal.md` for motivation. The relevant current state:

- `.page-head` (in `shared/infrastructure/driving/static/vocabulary.css`) is
  a two-child flex row: an `<h1>` on the left, one right-aligned control on
  the right. What occupies the right slot today is inconsistent — a "back"
  link on three depth-1 templates (`launch.html`, `edit.html`, `new.html`,
  each with its own copy-pasted markup and comment), the primary "Add step"
  action on the top-level `page.html`, and nothing at all on `product.html`.
- `_admin_header.html` (`shared/infrastructure/driving/templates/`) is the
  one precedent for shared admin chrome: a single partial, included from
  every admin page, naming the top-level surfaces (Products, Launches,
  Playbook steps, Users) and marking whichever one the caller is on as
  `current` rather than a link.
- The launch's journal renders inline as a `<section class="journal">` at
  the bottom of `launch.html` today; there is no journal route.
- `edit.html`'s and `new.html`'s back/cancel links already carry the
  admin's active narrowing forward (`{{ page_path }}{{ narrowing.suffix() }}`);
  `launch.html`'s does not, deliberately (`launch-admin`'s existing "way
  back" requirement records why).

## Goals / Non-Goals

**Goals:**
- One shared breadcrumb partial, in the shape `_admin_header.html`
  established, replacing every page-local "back"/"cancel" copy.
- A right-hand "descendants" region on a detail page, populated only when
  that page has a child page to offer, sharing the slot the old back link
  used to occupy.
- Split the launch journal into its own page, as the first thing the
  descendants region links to.
- Link a step's name to its edit page, matching how a launch's label and a
  product's SKU already link to their own detail pages.

**Non-Goals:**
- Removing the step row's own `edit`/`retire`/status controls — parked in
  the separate `move-step-actions-into-step-pages` change, which depends on
  this one landing first.
- Product categories (Photos, etc.) — the descendants region is built to
  carry more than one entry, but nothing populates a second entry yet.
- Changing what `_admin_header.html` does — it keeps switching between
  top-level admin surfaces; the breadcrumb is a separate control with a
  separate job (see the `launch-admin` delta's note on this).

## Decisions

**The breadcrumb's current segment *is* the page's `<h1>` — a page
carrying a breadcrumb keeps no separate title.** The first cut kept the
trail on its own line above `.page-head`, with the page's own `<h1>`
unchanged below it. Two things were wrong with that, both surfaced by
looking at the built page rather than the markup: the trail, included
directly into `<main class="container">` — a block context, not a flex
one — rendered as a full-width bar regardless of `display: flex` on the
`<nav>` itself (a block-level element fills its container's width
whether or not it is itself a flex container; only *its children*
would have shrunk), and the trail's current segment duplicated the
page's own title verbatim on every page that had one (`launch.html`'s
`<h1>{{ launch.label }}</h1>` beside a breadcrumb already ending in
`launch.label`).

Fixed by moving `_breadcrumb.html`'s include inside `.page-head` (so the
trail is a flex *item*, not a lone block, and `display: inline-flex`
on `.breadcrumb` stops it claiming the main axis on its own) and
promoting the current segment to a literal `<h1 class="breadcrumb-
current">`. Sizing settled through live review, below, at `1.3rem`/`600`
— smaller than Pico's own `2rem` default so it still reads as *a*
heading without competing with the handful of top-level list pages that
render no breadcrumb and keep their own plain `<h1>` at the same shared
scale. `launch.html`, `journal.html`, `product.html`, `edit.html` and
`new.html` all drop their separate `<h1>` accordingly; `edit.html`'s
generic "Edit step" and `new.html`'s "Add a step" are gone entirely,
replaced by the step's own name (or "New step") at heading size.

Alternative considered, and originally chosen: the trail on its own
line, title kept separate — rejected once built, for the two reasons
above; a three-segment trail's wrapping (the original worry that
motivated putting it on its own line) turns out to be an ordinary,
acceptable flex-wrap under `.page-head`'s existing `flex-wrap: wrap`,
not the problem it was assumed to be.

**The trail is server-assembled per page, not inferred from the URL.**
Each handler already builds a small amount of page-specific context
(`page_path`, `narrowing`, `launch.label`); the breadcrumb rides the same
pattern — a plain `breadcrumb: list[tuple[label, href]]` (ancestors) plus
the current page's own label (rendered as the trail's last, un-linked,
segment) passed into the template. Alternative considered: derive segment
labels from the URL path — rejected because a URL segment is an
identifier (`/admin/launches/{uuid}`), never the human label a trail needs
(a launch's product name, a step's own name), so the handler has to supply
the label regardless.

**No shared Python helper for assembling the trail, only a shared
template partial for rendering it.** Three pages need this today
(detail, journal, product dossier), plus edit/create's simpler
one-segment version — few enough that a `breadcrumb=[("Launches", ...),
(launch.label, None)]` literal per handler is no less clear than a helper
function would be, and the project's own guidance is against
introducing an abstraction ahead of the duplication that would justify
it. The partial (`_breadcrumb.html`, alongside `_admin_header.html`) is
still shared, because it is markup and CSS classes that must not drift
between pages the way three copy-pasted "back" links already had.
Revisit a helper if product categories multiply the call sites enough
that the literal starts repeating non-trivial logic, not just data.

**The journal page reuses the detail page's launch-identifier
resolution.** Both routes resolve the same launch position by the same
identifier and must refuse identically (`launch-admin`'s existing
absence-indistinguishable-from-nonexistent requirement, now extended to
the journal route). Extracting that resolution into one function the two
route handlers both call is what keeps that guarantee true by
construction rather than by two handlers happening to agree.

**The descendants region is opt-in per page, not a fixed second header
slot.** A page passes a `descendants` list (empty by default) into the
same context the breadcrumb rides in; the partial renders nothing when
it's empty, which is what leaves top-level list pages free to keep using
`.page-head`'s right slot for their own primary action (`Add step`
unaffected — it isn't touched by this change).

### Presentation refinements, settled through live review

The breadcrumb work's own scope stayed as planned above; the following
were decided by looking at the running pages together, once the trail
existed to look at, and are recorded here because each is a real
decision rather than an implementation default.

**One link colour, not Pico's own primary blue.** Every admin link
(the breadcrumb's own ancestors excepted, which keep `--ink-quiet` as
their own deliberate choice) now reads in a new `--link` token
(`#0369a1` light / `#38bdf8` dark) rather than Pico's `#0172ad` —
identical, in light mode, to the "Add step" button's own fill, which
read as the same colour as a button rather than as a link's own accent.
Checked against white at roughly 5.9:1, past WCAG AA's 4.5:1 for body
text.

**One heading scale, not Pico's per-tag defaults.** `main.container h1`
(`1.3rem`/`600`) and `main.container h2` (`1.15rem`/`600`) replace
Pico's own `2rem`/`700` and `1.75rem`/`700` — the second because an
unstyled `<h2>` (the product dossier's "Results retained for a
decision", the roster's "Active users") rendered *larger* than the
page's own `<h1>`, an inverted hierarchy nothing had asserted on
purpose. `.gate-name` (a gate's own heading, on both the playbook steps
page and — see below — the launch detail page) is smaller again
(`var(--size-body)`), reused as one rule between the two pages rather
than restated per page.

**One border treatment for every row and column divider.** Pico
triples a `<thead>`'s own border width (`0.1875rem` against every other
row's `0.0625rem`) — the reason the playbook steps table's own header
line read thicker than its row lines. Every divider this file owns
(`.gate-group .gate-heading`, `.launches .launch-row`, `.admin-header`,
`section.finished`) now reads `var(--pico-border-width) solid
var(--pico-muted-border-color)` — Pico's own table-border tokens,
reached directly rather than approximated, so agreement with the
playbook table's own row borders is exact rather than a matched shade.

**The gate a reader navigated to is marked on the gate's own name, not
by an indent or a border.** Two earlier shapes for this (an outlined
box, then a left-accent-plus-indent) were both tried and rejected live;
the `:target` gate's `.gate-name` simply switches to `--link`. The
"— current gate" text this section's heading carried for the *launch's
own* current gate (a different fact — see `launch-admin`'s own
requirement on this) was dropped outright: it duplicated the amber
gate-sequence pill above without adding a fact the pill did not already
carry.

**The launch detail page's per-gate step list is a `<table>`, matching
the playbook steps page's own shape — not a design goal stated up
front, but the shape once both pages sat side by side under one
heading and border vocabulary.** Every fact `launch-admin`'s existing
requirement names — name, identifier, discipline, blocking, overdue,
due period, recorded outcome and its provenance — and every marker that
requirement fixes (`outcome-tag`, `state-*` on the row) carry over
unchanged; only the wrapping element does not. The outcome tag keeps
its own per-state fill (an explicit call: a left-edge accent was tried
alongside it and dropped as redundant, per the same requirement's own
"readable by treatment" clause, which does not ask for two treatments
at once). One correction this forced: three test files' own
`_gate_group` locator (each file keeps its own copy — no shared
test-helper module in this project) picked "the smallest element
holding exactly one gate's steps," which used to be the addressable
element and, under a `<table>`, is now an unaddressed `<tbody>` a
`:target` rule and a fragment link can't reach. Each copy now filters
to `id`-carrying candidates before taking the smallest.

**SKU and name are separate columns everywhere they appear together,
with the name — not the code — as the link.** `product.html`'s index
already had both facts in adjacent columns; only the link moved. The
launches list did not have the two apart at all — `label` was a single
`"SKU — Name"` string — so `LaunchRow` gained a `sku` field alongside
`label` (still assembled by the existing `_label_for`, but reduced to
name-only: the detail and journal pages' own titles no longer carry a
SKU prefix either, for the same "the page's title says one thing"
reason `edit.html`'s generic title was dropped above).

**Not yet settled: column order does not agree between the three
tables.** The product index and the launches list both read
identity-then-name (SKU, then the product's or launch's name); the
playbook steps table was flipped the other way, name-then-`id`, on a
direct request scoped to that one page. Raised and left open rather
than guessed at, since the two orders are both defensible and the
request that produced one of them did not settle the other two — see
Open Questions.

## Risks / Trade-offs

- **[Risk]** An admin with `launch.html`'s old anchor (`#journal`, if any
  existed) or a saved scroll position loses the inline journal section →
  **Mitigation**: this is an internal admin tool with no external links
  into the page; grep confirms no other template or handler links to that
  anchor.
- **[Risk]** `.page-head`'s CSS changes reach every admin page at once
  (list pages included, even though they render no breadcrumb) →
  **Mitigation**: the breadcrumb block renders nothing when a page passes
  no `breadcrumb` context, so top-level pages are visually unchanged; a
  manual pass over all seven touched pages happens before merge.
- **[Risk]** The step-name link change touches `page.html`'s existing
  `step_cells` macro, which several scenarios in `playbook-admin`'s spec
  already cover → **Mitigation**: the new requirement explicitly asserts
  the row's existing `edit` action is untouched, and the test-writer
  derives its scenario from that assertion directly.

## Migration Plan

Ships through the normal PR-to-`main` deploy pipeline; no data migration
(presentation-only, no schema change) and no feature flag (internal admin
surface, single deploy). Rollback is a straight revert.

## Open Questions

- Exact breadcrumb styling (separator glyph, spacing, type scale) —
  **settled**, through the live review recorded under "Presentation
  refinements" above, rather than left open as originally planned.
- Column order for a table carrying both an identity (SKU/`id`) and a
  name column: identity-first (today's product index and launches list)
  or name-first (today's playbook steps table, after a request scoped to
  that one page only). Whichever is chosen, bringing the other two
  tables into agreement is a small, mechanical follow-up — but guessing
  which way risks a second reorder, so it stays open here rather than
  being picked silently.
