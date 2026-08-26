## Why

The admin surfaces have no presentation vocabulary of their own, and the
defaults they fall back on actively mislead.

The playbook page renders on Pico's defaults, where `<button>` is a
filled primary control and `<a>` is a link. So `retire` — the
destructive action — is the loudest thing in a step's row, while `edit`
does not look like an affordance at all. Each action is its own
block-level `<form>`, so the row's controls stack vertically rather than
sitting together: the reorder pair, the status control, `edit` and
`retire` occupy five stacked blocks and roughly 220px of height. Against
the 105 seeded steps in `alembic/data/playbook_v1.yaml` that is a page
around 23,000px long, on which about four steps are visible at once.

The roster page does not even reach Pico. It carries nine lines of
inline `<style>` in the template itself, so the two admin surfaces a
single admin moves between look like two different products, and a
change to either one's presentation reaches only that one.

The two surfaces are also not connected to each other at all. The Slack
command mints a link to `ADMIN_HOME_PATH` — `/admin/playbook` — so every
admin session lands on the playbook page, and no template in the
repository carries an `href` to `/admin/roster`. `roster.html` carries
no `href` at all, so there is no way back either. The roster page is
reachable only by an admin who knows to type the URL, which in practice
means it is not reachable. A vocabulary that makes two surfaces look
like one product while leaving no way to travel between them would be
solving the smaller half of the problem.

Two further gaps have opened since this was first scoped, both left here
deliberately by the changes that created them:

- **Fault marks ship unstyled.** `attribute-faults-to-fields` renders
  `<ul class="field-faults" data-field="…">` beside a refused control,
  and its design records — in as many words, "Marking ships unstyled" —
  that this change owns the treatment. The case that matters is the
  not-offered one it names: a `human` step carrying an automation brief
  is refused for the pair and marks both halves, and the brief renders
  disabled in the fieldset this change is about to dim. The obligation
  is therefore negative — dimming must not become hiding, nor swallow
  the fault it sits beside — and it is the whole of the fix.
- **A created step is addressed but not distinguished.** `add-step-page`
  makes the list land on `#step-<identifier>` after a create, and its
  design leaves to this change whether that step is visually
  distinguished at all.

This change was originally scoped inside `add-step-page` and carved out
on review, which found it implemented no requirement at all — roughly a
quarter of that change's tasks traced to nothing in any spec, which is
the state the spec-driven rule exists to prevent.

## What Changes

- **One vocabulary, served to both admin surfaces.** A single stylesheet
  lives in `shared`, the only place `launch.infrastructure` and
  `access.infrastructure` may both reach without breaking an
  `import-linter` contract, served by one guarded route both surfaces
  reach on equal terms. Pico stays as the form-control substrate — and
  moves to `shared` alongside it, since a substrate only one module can
  reach cannot be shared — and the new stylesheet is a token and density
  layer over it.
- **No vendored faces and no build step.** The type layer is a tuned
  system stack — `system-ui` for prose, `ui-monospace` for identifiers,
  gates and anchors. Nothing binary is committed, no licence needs
  auditing, and the stylesheet is served exactly as it sits in the
  repository. This departs from the change's original framing, which
  called for subset vendored faces; subsetting is a build step in all but
  name, and `AGENTS.md` scopes this project to pure Python with no build
  toolchain.
- **A step's actions share one affordance vocabulary.** Every action
  renders as a control of the same weight, sitting in one row, with the
  destructive action distinguished by treatment rather than by
  prominence.
- **The step table becomes dense enough to scan a gate** — a step
  occupies one row, and the facts a step carries render as compact marks
  rather than as a sentence.
- **The vocabulary never suppresses a fault the surface marked.** The
  fieldset a step's kind cannot use is dimmed, never hidden, so a mark
  landing on a disabled automation control stays legible. No template
  restructuring: two earlier drafts of this change proposed surgery on
  the timing-anchor groups to free a "trapped" fault, and no such fault
  exists — the surface parses only the inputs the submitted anchor kind
  uses, so a mark cannot land on one it does not offer. A third draft
  kept a rendering invariant guarding a rule someone might add later;
  that too is cut, for reasons `design.md` records. What remains is the
  dim, and the rule that it must not swallow the fault it sits beside.
- **A created step is distinguished on the row the list lands on**, so
  the redirect resolves into something the eye finds.
- **The authoring surfaces gain grouped field sections** rather than a
  single column of eleven top-level controls above two already-grouped
  fieldsets.
- **The roster page drops its inline `<style>`** and adopts the same
  vocabulary, including the action treatment for `Deactivate`.
- **Each admin surface carries a header naming both surfaces**, so an
  admin can travel between the playbook page and the roster page in one
  action from either side, rather than by typing a URL.

## Capabilities

### Modified Capabilities

- `playbook-admin`: gains what is genuinely behaviour rather than taste —
  that a step's actions are presented as one affordance vocabulary in
  which the destructive action is not the most prominent; that the
  vocabulary never suppresses a fault the surface marked — neither
  hiding it nor dimming it along with the control it concerns; that a
  created step is distinguished
  on the row the list addresses; that the surface carries a header from
  which the roster page is reachable in one action; and that the assets
  the surface loads stay behind the admin guard and need no build step.
- `roster-admin`: gains that the page's presentation comes from the
  shared vocabulary rather than from page-local styling, so a change to
  the vocabulary reaches both admin surfaces; that its actions carry the
  same affordance treatment; and that it carries the same header, from
  which the playbook page is reachable in one action.

Everything else in this change is design, not behaviour, and belongs in
`design.md` rather than in a requirement. That boundary is the point of
carving it out: a spec that pinned colours or type scales would be a
spec describing an implementation.

## Impact

- `shared/infrastructure/driving/` — the new stylesheet and the guarded
  route that serves it, with the guard injected by the composition root
  the way `roster` and `admin_sessions` already are; plus the shared
  header partial both surfaces include.
- `shared/infrastructure/driving/static/pico.min.css` — moved here from
  `launch`. The vocabulary is a layer over Pico, so the roster page needs
  the same substrate for the two surfaces to actually match; a substrate
  reachable from only one module cannot be shared.
- `launch/infrastructure/driving/static/htmx.min.js` — stays. Only the
  playbook page uses htmx; the roster page is plain form posts by
  design.
- `launch/infrastructure/driving/templates/` — `page.html`, `edit.html`,
  `new.html` and `_fields.html`.
- `access/infrastructure/driving/templates/roster.html` — loses its
  inline `<style>`, gains the shared stylesheet and the header.
- `main.py` — injects the asset route's guard, and mounts its router.

No schema, data or persisted-state change. No new `import-linter`
contract, and no existing one relaxed.

## Sequencing

Unblocked. Both changes this one waited on have landed and been
archived — `add-step-page` (2026-08-25) and `attribute-faults-to-fields`
(2026-08-26) — so the surfaces it restyles are no longer moving. It is
the last of the three, as planned, and it absorbs the list-table restyle
that `add-step-page` deferred along with the two gaps named in **Why**.
