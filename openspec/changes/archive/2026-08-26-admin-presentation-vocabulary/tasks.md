## 1. The shared asset route

- [x] 1.1 Create `shared/infrastructure/driving/static/` and move
  `pico.min.css` into it from `launch/infrastructure/driving/static/`.
  `htmx.min.js` stays in `launch` — only the playbook page uses it.
- [x] 1.2 Add `shared/infrastructure/driving/admin_assets.py`: a router
  with `GET /admin/assets/{asset}`, a module-level `verify: Any = None`
  injected by the composition root, and a guard that resolves it at call
  time and raises a bare `HTTPException(404)` on refusal — the shape
  `roster_admin._require_admin` already uses.
- [x] 1.2a Make an **un-injected** `verify` refuse with that same bare
  404. Failing open would answer 200 to an anonymous caller while every
  other admin path answered 404 — an existence oracle for the admin
  surface. Cover it with a test: absent guard, not passing guard.
- [x] 1.3 Copy the traversal guard from `playbook_admin.py`'s
  `static_asset` verbatim
  (`path.parent != _STATIC_DIR.resolve() or not path.is_file()`),
  rather than reinventing it.
- [x] 1.4 Mount the router in `main.py` alongside its neighbours and
  inject `verify` there, next to the existing `roster` /
  `admin_sessions` injection.
- [x] 1.5 Confirm `uv run lint-imports` passes — `shared` must import no
  business module, and neither admin module gains an import of the
  other.

## 2. The stylesheet

- [x] 2.1 Add `shared/infrastructure/driving/static/vocabulary.css` with
  the token layer: colour, spacing and type scale as custom properties
  on `:root`, `--font-ui` a `system-ui` stack and `--font-mono` a
  `ui-monospace` stack. Nothing binary, no `@font-face`.
- [x] 2.2 Add the action vocabulary: `.row-action` for every action
  control, `.danger` distinguishing the destructive one by colour and
  border only — never by size or weight, or retire stays the loudest
  control and the requirement fails.
- [x] 2.3 Add the density layer: the action cells' forms as
  `display: inline` so each single-action form's button becomes the
  inline item, and `.mark` pills for the facts cell. `display: contents`
  on a flex cell was the first approach and was replaced by the fallback
  `design.md` — Risks already named: `display: flex` on a `<td>` replaces
  `display: table-cell`, so the cell leaves the table's column model and
  stops sizing with its column.
- [x] 2.4 Add `.field-faults` treatment and `.just-created` (an untimed
  background tint — no fade on a timer, which no response could assert).
- [x] 2.5 Ensure whatever treatment `.inapplicable` carries **never
  hides** its fieldset, and never reaches the faults inside it. Hiding it
  outright would break what `attribute-faults-to-fields` established;
  dimming the fault defeats the same guarantee more quietly, and every
  scenario would still pass. **Settled: it carries no treatment.** Three
  were built and rejected on sight (pale fill, bordered grey box,
  transparent controls with a dashed edge) — each read as a region
  demanding attention rather than one to ignore. The controls render as
  ordinary fields and stay `disabled`, which is the served guarantee.
- [x] 2.5a Do **not** apply `opacity` to `.inapplicable` or to any
  ancestor of `.field-faults` — **the `<label>` included**. The mark is
  rendered inside the label, after the control and its `<small>`
  (`_fields.html`, the automation fieldset), so `.inapplicable label`
  reaches it. And the reflexive rescue does not work: `opacity` creates
  a stacking context, so `.inapplicable .field-faults { opacity: 1 }`
  cannot restore what an ancestor dimmed. Dim the control elements
  themselves (`legend`, `textarea`, `input`, `small`), or dim by colour
  rather than by opacity. Since 2.5 settled on no treatment, this stands
  as the rule for whoever adds one; the stylesheet keeps it, with a
  comment naming exactly what not to do.

## 3. The shared header

- [x] 3.1 Add `shared/infrastructure/driving/templates/_admin_header.html`,
  taking which surface is current and rendering both surfaces, with the
  current one identified rather than linked.
- [x] 3.2 Give both modules' Jinja `Environment`s a `ChoiceLoader` over
  their own `templates/` plus the shared one — the `_TEMPLATES`
  definition in `playbook_admin.py` and in `roster_admin.py`.
- [x] 3.3 Include the header on `page.html`, `new.html`, `edit.html` and
  `roster.html`.
- [x] 3.4 Mark the header's outbound link from the playbook surfaces
  `hx-boost="false"`, for the reason the Add step control's comment in
  `page.html` already records: boosted, htmx swaps the roster page into
  this body and discards its own body attributes.

## 4. The playbook templates

- [x] 4.1 Point `page.html`, `new.html` and `edit.html` at
  `/admin/assets/pico.min.css` and add `/admin/assets/vocabulary.css`.
  `htmx.min.js` keeps its existing `/admin/static/` href.
- [x] 4.2 Turn every action control into a `.row-action`: the `edit`
  link becomes `<a … role="button" class="row-action">` — matching the
  buttons, not the reverse — and the retire button additionally carries
  `danger`. Un-retire carries `.row-action` and **no** `danger`.
  **`page.html` renders a step row twice** — the served table and the
  "Not served at this gate" table — each with its own edit link, retire
  form and `status_control` call. Both sites, or a draft's row keeps the
  old vocabulary while every delta scenario still passes.
- [x] 4.3 Give the action `<td>`s `class="actions"` — the selector
  task 2.3 relies on. No such class exists today; `actions` appears in
  `page.html` only as `<th>` header text, so without this the density
  layer is dead CSS that no scenario would catch. Otherwise leave every
  action form exactly as it is: five separate forms to five endpoints,
  with their hidden inputs intact. **The row reads by meaning**: the
  reorder pair moved to a `reorder` cell beside the `position` it
  changes and the status control took a column of its own, so the
  classes are `reorder`, `position` and two `actions` cells rather than
  one. See `design.md` — *The row reads by meaning, not by control
  type*.
- [x] 4.4 Render the facts cell as `.mark` pills instead of the
  `·`-joined sentence in `page.html`'s `step_cells` macro.
- [x] 4.5 Add `just-created` to the step row when
  `step.identifier == created`, using the `created` variable
  `_render_page` already passes to `page.html`. Apply it at **both** row
  sites: a step created as a `draft` renders in the non-active table,
  and that is the case the served spec gives its own scenario to.

## 5. The authoring form

- [x] 5.1 Do **not** restructure the anchor groups. An earlier draft of
  this change moved `hidden` from each group's `<label>` onto its
  `<input>` to reveal a trapped fault; there is no trapped fault — a
  mark cannot land on a not-offered anchor input — and the move would
  break the live toggle in `_fields.html`, which owns `hidden` on the
  label. See `design.md` — *The fault-visibility defect does not exist,
  and the treatment is negative*. This task exists to stop the surgery
  being reintroduced, and is complete when nothing in the diff touches
  those groups.
- [x] 5.2 Do not add a rendering-invariant test for marks nested inside
  not-offered elements. A third draft specified one; it was cut because
  a *reworded* rule produces no mark at all (`_crossing` returns no
  fields on no match) and a rule *added* would be missing from the
  provocation sweep anyway, by that sweep's own docstring. See
  `design.md`. If someone later adds an attribution rule naming an anchor
  field, the served requirement *Every rule an authoring write can
  provoke attributes its fault* is what governs it.
- [x] 5.3 Group the eleven top-level controls into field sections
  alongside the two existing fieldsets, within the three bounds
  `design.md` — *Field grouping is presentation, and carries three hard
  bounds* sets: no field added, removed, renamed or reordered in the
  submitted body; no mark separated from the control it concerns; the
  anchor and automation fieldsets keep their `hidden` / `disabled`
  semantics. If the change has grown too large by this point, this is
  the task to cut — nothing else depends on it.

## 6. The roster page

- [x] 6.1 Delete the inline `<style>` block from `roster.html` and link
  `/admin/assets/pico.min.css` and `/admin/assets/vocabulary.css`.
- [x] 6.2 Give the page a proper document shell — it currently opens at
  `<!doctype html>` with a bare `<title>` and no `<head>`, `<body>` or
  viewport meta. Do this **before** 6.1 and 6.3, which both assume it.
- [x] 6.3 Apply the action vocabulary to all four actions the roster
  delta names: `Add person`, `Save edit`, `Deactivate` and `Reactivate`
  become `.row-action`, with `Deactivate` alone carrying `danger`. The
  create submit is easy to miss — it is the one action not on a person's
  row.
- [x] 6.4 Give the roster's action cells `class="actions"` too, for the
  same selector, then replace the classes the deleted style block served
  (`.deactivated`, `.attribution`, `form.inline`) with vocabulary
  equivalents, keeping deactivated people visibly set apart — that is a
  standing `roster-admin` requirement, not a style choice.

## 7. Verification

- [x] 7.1 Run `uv run pytest` and confirm the existing suites still
  pass. The full `tests/unit` + `tests/agents` tier runs at commit time,
  so a restyle that breaks a markup assertion fails here.
- [x] 7.2 Confirm no template anywhere still references
  `/admin/static/pico.min.css` — an unstyled page still returns 200, so
  this break is silent and must be checked by grep.
- [x] 7.3 Run `uv run ruff check`, `uv run ruff format --check`,
  `uv run mypy` and `uv run lint-imports`.
- [x] 7.4 Start the app against the seeded set and check by hand: a step
  occupies one row, a gate is scannable, and the page is far short of
  the ~23,000px it stands at today. No test tier can measure a rendered
  row's height, so this stays a manual check rather than a scenario.
- [x] 7.5 Check by hand that both header links work in a real browser,
  in both directions, and that the roster page's forms still post after
  losing their inline styles.
- [x] 7.6 Check by hand that a `human` step rejected for carrying an
  automation brief shows that fault legibly on the dimmed automation
  fieldset — the reachable not-offered case, and the half a response
  cannot establish. Dimmed, never hidden.
- [x] 7.7 Check by hand what the markers cannot establish: that a step
  row's actions sit on one line, and that retire is **not** the most
  prominent control in the row. The `row-action` / `danger` scenarios
  pass for any stylesheet, including one that leaves retire loudest, so
  without this check the affordance requirement's substance is enforced
  by nothing.
