## Why

The admin surface has no presentation vocabulary of its own. It renders
on Pico's defaults, and the defaults actively mislead: `<button>` is
styled as a filled primary control while `<a>` is a link, so `retire` —
the destructive action — is the loudest thing in the row and `edit` does
not look like an affordance at all. Each action is its own block-level
`<form>`, so the four action controls stack vertically rather than
sitting in a row, making a step's row roughly 220px tall. Against 105
seeded steps that is a page around 23,000px long, on which about four
steps are visible at once.

This was originally scoped inside `add-step-page` and carved out on
review, which found it implemented no requirement at all — roughly a
quarter of that change's tasks traced to nothing in any spec, which is
the state the spec-driven rule exists to prevent.

## What Changes

- The admin surfaces gain one vendored stylesheet and the font faces it
  names, served by the existing guarded `/admin/static/{asset}` route
  alongside `htmx.min.js` and `pico.min.css`. No Node toolchain, no
  build step; Pico stays as the form-control substrate and the new
  stylesheet is a token and density layer over it.
- A step's actions share one affordance vocabulary: every action renders
  as a control of the same weight, sitting in one row, with the
  destructive action distinguished by treatment rather than by
  prominence.
- The step table becomes dense enough to scan a gate — a step occupies
  one row, and the facts a step carries render as compact marks rather
  than as a sentence.
- The authoring surfaces gain grouped field sections rather than a
  single column of fourteen full-width controls.

## Capabilities

### Modified Capabilities

- `playbook-admin`: the step-table requirement gains what is genuinely
  behaviour rather than taste — that a step's actions are presented as
  one affordance vocabulary in which the destructive action is not the
  most prominent, and that the assets the surface loads remain behind
  the admin guard and require no build step.

Everything else in this change is design, not behaviour, and belongs in
`design.md` rather than in a requirement. That boundary is the point of
carving it out: a spec that pins colours or type scales would be a spec
describing an implementation.

## Impact

- `launch/infrastructure/driving/static/` — the stylesheet and the
  vendored faces, subset, with each licence confirmed to permit
  redistribution.
- `launch/infrastructure/driving/templates/` — `page.html`, `edit.html`,
  `new.html` and `_fields.html`.

## Sequencing

Last of the three. It restyles surfaces the other two changes are still
reshaping — `add-step-page` moves the create form out of `page.html`,
`attribute-faults-to-fields` adds fault marking to `_fields.html` — and
styling markup that is about to change is wasted work. It also absorbs
the list-table restyle that `add-step-page` deferred.
