## Why

The admin surfaces are about to grow a third level of nesting — a launch's
journal is becoming its own page, and a product dossier will soon split into
categories (photos and the like). The one "way back" control each depth-1
page carries today only returns one level, is copy-pasted per template
(`launch.html`, `edit.html`, `new.html`), and is entirely absent from the
product dossier. That stops scaling once a page can sit two or three levels
deep, so the trail and the way further in need a shared shape before the next
level is added.

## What Changes

- Replace each page's own "Back to X" control, and its own separate `<h1>`,
  with a shared breadcrumb trail naming every ancestor as a link and the
  current page as the un-linked last segment (`Launches › TestProductName15
  › Journal`) — the last segment rendered as the page's own `<h1>`, so the
  page carries no separate, duplicate title. Applies to `launch.html`,
  `edit.html`, `new.html`, and — newly — `product.html`, which carries no
  way back today.
- Add a right-hand region beside a detail page's title that links to that
  page's own child pages ("descendants"), populated only when it has any.
  Top-level list pages (Launches, Products, Playbook steps) leave this region
  unused, since a row's own name is already the way in — it stays free for
  the page's existing primary action (Add step, unaffected by this change).
- Split the launch detail page's inline Journal section into its own page,
  reached from the launch detail page's descendants region. This is the
  first descendant the pattern serves.
- Make a step's name in the playbook steps table a link into its edit page,
  the same way a launch's label and a product's name already link into their
  own detail pages. Its "Back to the table" becomes the breadcrumb
  `Playbook steps › <step name>`. The row's own edit/retire/status controls
  are unchanged here — see the separate `move-step-actions-into-step-pages`
  change for relocating those onto the step's page.
- Presentation consistency across every admin surface, settled through
  live review of the running pages rather than planned up front: one shared
  link colour and heading scale; every row/column border and table-header
  weight brought to the same light, thin treatment (`launch-admin`'s
  existing per-region rules already required *some* rule reach each
  region — this settles what that rule is, project-wide); the product
  index and the launches list each split their SKU into its own column,
  identity-styled, with the row's name — not its code — as the link; the
  launch detail page's per-gate step list moves from a card-per-step
  `<ul>` to a `<table>` matching the playbook steps page's own shape,
  carrying every fact and marker (`outcome-tag`, `state-*`) the existing
  requirement already names. `roster.html` (outside every capability this
  change otherwise touches) picks up the same shared title container for
  the same reason the product index and launches list needed it: one rule
  for the space under a title, not a spacing accident of whichever element
  happens to follow a bare `<h1>`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `launch-admin`: "A launch's detail page offers the way back to the list"
  is replaced by the breadcrumb trail requirement. "A launch's detail page
  renders its journal, newest first" is replaced by the journal living on
  its own page, reached as a descendant of the launch detail page.
- `product-dossier`: gains a breadcrumb-trail requirement on the dossier
  page, where none exists today.
- `playbook-admin`: the edit page's "Back to the table" control is replaced
  by the breadcrumb trail. The step table gains a requirement that a step's
  name opens its edit page, alongside the existing "A step can be edited in
  place" requirement.

## Impact

- New shared template partial for the breadcrumb trail and the descendants
  region, included wherever `_admin_header.html` is today.
- New route, handler and template for the launch journal page
  (`launch_admin.py`), replacing the inline `journal` section of
  `launch.html`.
- `page.html`: step rows link the step's name to `edit.html`; the identity
  and name columns swap order (name leads); no other row behavior changes.
- `product.html`: gains a `page-head` it does not have today; its index
  row links the product's name rather than its SKU, with SKU moved to its
  own identity column.
- `launches.html`: gains its own identity column (SKU), split out of the
  combined `label` string; `launch_admin.py`'s `LaunchRow` gains a `sku`
  field and a `_row_identity` helper alongside the existing `_label_for`
  (still used, name-only now, by the detail and journal pages' titles).
- `launch.html`: its per-gate step list is now a `<table>`, not a `<ul>` —
  `vocabulary.css`'s `.gate-group` rules and three test files' own
  `_gate_group` locators (each file keeps its own copy, per this project's
  no-shared-test-helper convention) were updated together with it, since a
  `<tbody>` is now a smaller — but unaddressed — candidate than the
  `id`-carrying `<section>` the old locators assumed was smallest.
- `roster.html`: gains the shared `page-head` container, presentation only.
- New shared token (`--link`) and shared heading rules (`main.container
  h1`/`h2`) in `vocabulary.css`, reached by every admin page through the
  one stylesheet route they already load — no new route, no per-page
  styling.
- Presentation-only otherwise — no change to what any surface reads or
  writes, and no new capability.
