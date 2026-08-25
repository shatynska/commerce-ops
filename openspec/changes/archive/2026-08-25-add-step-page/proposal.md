## Why

Creating a step is the one authoring write the page hides. The create
form is the last section of `page.html`, below every gate's table — and
with 105 seeded steps the list above it runs roughly twenty screens, so
an admin opening the page for the first time concludes there is no way
to add a step at all. That is not a scrolling inconvenience; it is a
capability the surface fails to advertise.

`redesign-step-fields` is about to make that worse in a specific way.
It roughly doubles the form: `name` and `description` become separate
inputs, `description` becomes multi-line, and `assignees`, `kind`,
`needs_confirmation`, `status`, `automation_brief` and `handler` arrive,
against `binding`, `execution` and `rule_policy` leaving. A form that
size is not a section to append to a list — and
appending it to the bottom of twenty screens is the wrong order of
operations, because every field added there is added somewhere nobody
has found.

Underneath the burial sits a second fault, and the new field set
sharpens it. A rejected create renders the *list* with faults, and the
list renders the create form with no submitted values — so everything
typed is discarded on the way back. The edit path does not have this
problem: it already echoes `_submitted_values(form)`.

Two of the new fields make that loss materially worse than it is today:

- **Assignees are people.** `_submitted_values(form: dict[str, str])`
  reads single values with `form.get()`. Assignees are zero or more
  roster identifiers, so they are submitted as repeated form keys, and a
  flat `dict[str, str]` keeps only the last one. The helper cannot
  round-trip them at all — this is a shape problem, not a missing key.
- **Discipline is unrecoverable.** It is the one field unique to the
  create surface — the edit surface renders it read-only, because
  `update_step` refuses discipline changes — so `_submitted_values` has
  no key for it and the template falls back to its first option. A
  rejected create silently reverts the discipline; the corrected
  resubmission then generates `mg.<wrong-discipline>.<seq>`, which
  `update_step` will not correct, leaving retirement plus a successor
  step as the only recovery. `redesign-step-fields` keeps both rules —
  the identifier still carries the discipline as its second segment, and
  discipline is still not updatable — so this defect survives that change
  untouched unless something closes it.

## What Changes

- Creating a step gets its own page, reached by an **Add step** control
  on the list. The create form leaves `page.html`.
- A rejected create re-renders the form still holding every submitted
  value — the discipline and the full set of named assignees included.
- **Cancel** returns to the list carrying the filter that was active
  when **Add step** was pressed.
- A create that lands returns to the list under that same filter, which
  names the step just created and addresses it directly so a browser
  lands on it. **Where the created step lands depends on the status it
  was created with**: an `active` step takes the last slot of its gate's
  order, while a `draft` or `in-development` step holds no slot and
  renders among the non-active steps set apart from the served set. The
  list addresses it wherever it landed. Where the filter would hide it,
  the list says so and offers to clear the filter, so a create never
  looks lost. The redirect carries the created step's identity as a query
  parameter — a fragment alone is never sent to the server, so the list
  could not otherwise know a create had happened.
- **Two submissions the create surface cannot have produced are refused
  rather than absorbed**: one naming no discipline, and one naming
  `retired` as the status. The surface always submits a discipline and
  never offers `retired`, so both answer hand-built requests — and both
  would otherwise persist a step nobody chose: a discipline defaulted
  into an identifier that cannot be corrected, or a step created behind
  the control that reveals retired steps, where the list cannot address
  it. Neither refusal re-renders a form, since there is no half-typed
  one to hand back.
- The timing-anchor fieldset offers only the inputs the anchor kind it
  was rendered with actually uses. It currently renders the kind selector
  plus all four value inputs — days, start, end, cadence — of which at
  most two apply to any kind, with nothing saying which.

**Deliberately deferred to their own changes**, on review findings that
this change bundled five concerns into one unreviewable unit:

- **Fault attribution** — marking the fields a fault concerns, in the
  three treatments (single field, combination, set-level). Deferred to
  `attribute-faults-to-fields`, which also owns removing the generated
  identifier from a rejected create's faults. It applies to both
  authoring surfaces, and its design questions should not hold this page.
  That change is itself downstream of `redesign-step-fields`, since the
  fields it attributes faults to are the ones that change.
- **The presentation vocabulary** — the token set, typography, vendored
  stylesheet and font faces. Deferred to
  `admin-presentation-vocabulary`, which also absorbs the list-table
  restyle. As scoped here it implemented no requirement at all, which is
  the state the spec-driven rule exists to prevent.

**Also out of scope, and owned by `redesign-step-fields`:** the field
set itself. That change decides which fields the form carries, renders
the assignee control against the roster, and makes the form's rejection
path carry the new fields. This change moves that form to its own
surface and states what a rejection and a landing must do there. Where
the two touch the same helper they touch it for different reasons, and
this change's tasks say which reason is whose.

No **BREAKING** changes: the authoring writes, their validation, and the
persisted step set are untouched. The `POST` that creates a step keeps
its path (`{PAGE_PATH}/steps/create`) and its form field names. Its
success response changes from `200` with the re-rendered list to `303`
redirecting to it; browsers and the existing test, which follows
redirects, are unaffected.

## Capabilities

### New Capabilities

None. Creating a step is an existing capability of the page; this change
alters where it lives and how it answers a rejection.

### Modified Capabilities

- `playbook-admin`: the creation requirement is redefined to place
  creating on its own reachable surface, to carry every submitted value
  through a rejection, to require a discipline rather than defaulting
  one, to keep `retired` off the statuses a step can be created with,
  and to state what happens when the active narrowing would hide the
  created step or the status it was created with places it outside the
  served order. The narrowing requirement is extended to cover
  moving between the list and the create surface. A new requirement
  states that a timing anchor's unused inputs are not offered.

**Two reproduced wordings are deliberately corrected**, and neither is a
silent drift:

- The narrowing requirement's list of what a write carries forward says
  "the description search". Under `redesign-step-fields` a search matches
  a step's name as well as its description, and no delta of that change
  touches this requirement — so nobody else corrects the term, and
  archiving this change would otherwise re-bless it as current. It reads
  "the text search" here.
- The retained scenario *A blocked retirement explains itself* ends "the
  step remains live". `redesign-step-fields` retires the word "live" —
  the set has four statuses now, not two — so the scenario reads "the
  step is not retired", which says the same thing in the vocabulary that
  survives.

The capability's Purpose is corrected on archive: it still describes the
set being changed "in place" through "inline edit, create", and creating
no longer happens in the list. `redesign-step-fields` also rewrites that
Purpose (its task 7.1) for its own reason — the word "live" — so
whichever archives second reconciles rather than overwrites.

`playbook-authoring` and `launch-playbook` are deliberately **not**
modified. Nothing here changes what a write accepts, what a status
means, or what the roster answers.

## Impact

**Affected code**

- `launch/infrastructure/driving/playbook_admin.py` — a `GET` route
  serving the create surface; the existing `POST` re-rendering it on
  rejection with the submitted values; `_submitted_values` gaining the
  create-unique `discipline` and a shape that carries multi-valued
  assignees; the redirect target after a create that lands.
- `launch/infrastructure/driving/templates/new.html` — new file.
- `launch/infrastructure/driving/templates/_fields.html` — the anchor
  input groups. Shared with the edit page, which inherits the change.
- `launch/infrastructure/driving/templates/page.html` — the create
  section removed, an **Add step** control added.

**Explicitly untouched**

The domain and application layers.

**Coordination — this change is sequenced after `redesign-step-fields`
and MUST NOT be applied or archived before it**

That change rebuilds the step's field set across all four layers, and
the create form is one of the surfaces it rebuilds. Drafting this change
against today's fields would produce a create page that has to be
rewritten on arrival.

- **The form this change relocates is the form that change rebuilds.**
  Landing this first means `redesign-step-fields` adds seven fields to a
  template that has just moved, and resolves its own rejection-path work
  against a create route whose response contract has just changed.
- **Three of its requirements bear on this change's own scenarios.** *The
  step form carries every authorable field* states the general rule that
  a field carrying no meaning for a step's kind is hidden or disabled —
  the same principle this change's anchor requirement applies on a
  different axis. *Steps that are not active are visible to authors and
  set apart* is what decides where a created step renders. *The step
  table shows the live set whole* makes search match a step's name as
  well as its description, which changes when the active narrowing hides
  a created step.
- **The two deltas share no requirement header.** This change MODIFIES
  *Steps can be created, retired and un-retired from the page* and *The
  narrowed view survives every write and every move between views*;
  `redesign-step-fields` touches neither. So the `MODIFIED` blocks here
  reproduce text that change does not move, and the archive order is not
  a text-collision hazard the way `reorder-steps-under-filters` was.
- **The hazard is semantic instead.** Archived out of order, this
  change's creation requirement would assert where a created step
  renders, in the vocabulary of a status field the served specs do not
  yet describe. `openspec validate` cannot see that — it checks headers,
  not whether a requirement's terms are defined.

`reorder-steps-under-filters`, this change's previous prerequisite, is
**archived**; its narrowing requirement is in `openspec/specs/` and the
`MODIFIED` block here reproduces it as it landed.
