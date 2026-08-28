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

**Breadcrumb is a line of its own, above `.page-head`, not inline in its
flex row.** The user's request was a link "next to the title," and a
two-segment trail (`Launches › TestProductName15`) fits inline; a
three-segment one (`Launches › TestProductName15 › Journal`) next to an
`<h1>` sized heading wraps awkwardly on a narrow viewport once both share
one flex row with a right-hand action. Putting the trail on its own line
immediately above `.page-head`, left-aligned with the `<h1>` below it,
scales to any depth without changing where the eye looks for either the
trail or the title. Alternative considered: keep it inline in
`.page-head`'s left slot alongside the `<h1>` — rejected for the wrapping
reason above, though it would have meant one fewer CSS rule.

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

- Exact breadcrumb styling (separator glyph, spacing, type scale) is left
  to implementation — it doesn't change what any requirement asserts, only
  how it looks, so it's picked when the CSS is written rather than decided
  here.
