## 1. The shared breadcrumb partial

- [ ] 1.1 Add `_breadcrumb.html` to `shared/infrastructure/driving/templates/`, alongside `_admin_header.html`. It renders a `breadcrumb` list of `(label, href)` ancestor links followed by the current page's own label, un-linked, and — when the page passes one — a `descendants` list of `(label, href)` links rendered on the right (`design.md` — Decisions 1 and 3). Renders nothing when a page passes no `breadcrumb`.
- [ ] 1.2 Add the CSS for it in `shared/infrastructure/driving/static/vocabulary.css`: the trail sits on its own line above `.page-head`, left-aligned with the `<h1>` below it (`design.md` — Decision 1, rejecting the inline-in-`.page-head` alternative). The descendants region takes `.page-head`'s existing right slot; leave `.page-head-action` (`Add step`) untouched, since it already occupies that slot on pages that pass no `descendants`.
- [ ] 1.3 Add the header/breadcrumb tests where the admin-header tests already live (`tests/unit/launch/infrastructure/driving/test_admin_header_names_every_surface.py` is the sibling, not the site — a new `test_breadcrumb_*.py` beside it), covering: an ancestor link is offered, the current segment is un-linked, and an empty `descendants` list renders nothing.

## 2. The launch surfaces

- [ ] 2.1 In `launch_admin.py`, replace the detail route's `page_head` "Back to the launches" context with a `breadcrumb` of one ancestor (`Launches`, unnarrowed) plus the launch's own label, and a `descendants` list naming `Journal`. Update `launch.html` to include `_breadcrumb.html` instead of its own `<a>...Back to the launches</a>`.
- [ ] 2.2 Extract the launch-identifier resolution and its three-way absence refusal (no position / forbidden scope / unknown identifier) out of the detail route into a function both the detail route and the new journal route call (`design.md` — Decision on reuse). This is what keeps the two routes' refusal shapes identical by construction rather than by the two handlers agreeing independently.
- [ ] 2.3 Add the journal route (`/admin/launches/{product_id}/journal`) and a `journal.html` template, carrying the journal rendering (newest first, empty-journal statement) moved out of `launch.html`'s inline `<section class="journal">`, plus a two-ancestor `breadcrumb` (`Launches`, then the launch's own label) and no `descendants` of its own yet.
- [ ] 2.4 Remove the inline `<section class="journal">` from `launch.html` along with the `launch.journal` context it rendered, once 2.3 serves the same content on its own page.
- [ ] 2.5 Confirm `launch.html`, `journal.html` and the list still carry the shared admin header, ride the admin-session guard, and refuse identically to each other and to the list's product-cannot-resolve/forbidden/unknown cases — the `launch-admin` delta's extended "Both surfaces" requirements.

## 3. The product dossier

- [ ] 3.1 In `product_dossier.py`, add a `breadcrumb` of one ancestor (`Products`, unnarrowed) plus the product's own name to the dossier route's context.
- [ ] 3.2 Update `product.html` to include `_breadcrumb.html` inside a `page-head` it does not have today (currently a bare `<h1>{{ it.name }}</h1>`).
- [ ] 3.3 Extend `tests/unit/launch/infrastructure/driving/test_product_dossier_page.py` to cover the new breadcrumb: the product index is reachable in one action, and the trail's last segment names the product and is not a link.

## 4. Playbook steps: name link and edit/create breadcrumb

- [ ] 4.1 In `page.html`'s `step_cells` macro, wrap the step's name in a link to `{{ page_path }}/steps/{{ step.identifier }}/edit{{ narrowing.suffix() }}` (the same route `edit.html`'s row already reaches via the `edit` action). Leave `row_actions`'s own `edit` control exactly as it renders today.
- [ ] 4.2 In `playbook_admin.py`, add a `breadcrumb` of one ancestor (`Playbook steps`, carrying the caller's narrowing forward) plus the step's own name to the edit route's context, and the same ancestor plus `New step` to the create route's context — narrowing-preserving in both, unlike the launch detail page's link (`design.md` — Decision 2, and the `playbook-admin` delta's note on why the two differ).
- [ ] 4.3 Update `edit.html` and `new.html` to include `_breadcrumb.html` instead of their own `Back to the table` / `Cancel` anchors — dropping the `<a>` but keeping the `hx-boost="false"` and narrowing-suffix behavior those anchors carried, since `_breadcrumb.html`'s ancestor links need the same treatment for the reason the removed comments on both pages record.
- [ ] 4.4 Extend `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py` (name link) and `test_playbook_admin_create_page.py` / a new edit-page test (breadcrumb, narrowing carried) to cover 4.1–4.3.

## 5. Verify against the specification

- [ ] 5.1 Run the tests derived from all three delta specs (`launch-admin`, `product-dossier`, `playbook-admin`) and confirm every new and modified scenario is observed, including the extended read-only/session/vocabulary/absence scenarios that now cover the journal page.
- [ ] 5.2 Run `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, and the unit + agents tier; run the integration tier before pushing.
- [ ] 5.3 Manually visit every admin page the shared `.page-head` CSS reaches, not only the seven touched by this change — the Launches list, the Products index and the Playbook steps list included — and confirm none of them renders a breadcrumb line or shifted spacing (`design.md`'s Risks section names this as the mitigation for the CSS change reaching every admin page at once).

## 6. Confirm against the deployment

- [ ] 6.1 After merge and deploy, open a launch from the list, follow its breadcrumb back to the (unnarrowed) list, then open its journal from the descendants region and follow both ancestor links from there.
- [ ] 6.2 Open a product from the index, confirm its breadcrumb reaches the index back.
- [ ] 6.3 Narrow the playbook steps table, open a step by its name, confirm the breadcrumb's `Playbook steps` link returns to the table under the same narrowing — then repeat from the create surface.
