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

- Replace each page's own "Back to X" control with a shared breadcrumb trail
  rendered beside its `<h1>`, naming every ancestor as a link and the current
  page as the un-linked last segment (`Launches › TestProductName15 ›
  Journal`). Applies to `launch.html`, `edit.html`, `new.html`, and — newly —
  `product.html`, which carries no way back today.
- Add a right-hand region beside a detail page's title that links to that
  page's own child pages ("descendants"), populated only when it has any.
  Top-level list pages (Launches, Products, Playbook steps) leave this region
  unused, since a row's own name is already the way in — it stays free for
  the page's existing primary action (Add step, unaffected by this change).
- Split the launch detail page's inline Journal section into its own page,
  reached from the launch detail page's descendants region. This is the
  first descendant the pattern serves.
- Make a step's name in the playbook steps table a link into its edit page,
  the same way a launch's label and a product's SKU already link into their
  own detail pages. Its "Back to the table" becomes the breadcrumb
  `Playbook steps › <step name>`. The row's own edit/retire/status controls
  are unchanged here — see the separate `move-step-actions-into-step-pages`
  change for relocating those onto the step's page.

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
- `page.html`: step rows link the step's name to `edit.html`; no other row
  behavior changes.
- `product.html`: gains a `page-head` it does not have today.
- Presentation-only otherwise — no change to what any surface reads or
  writes, and no new capability.
