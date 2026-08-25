## Why

Creating a step is the one authoring write the page hides. The create
form is the last section of `page.html`, below every gate's table — and
with 105 seeded steps the list above it runs roughly twenty screens, so
an admin opening the page for the first time concludes there is no way
to add a step at all. That is not a scrolling inconvenience; it is a
capability the surface fails to advertise.

Underneath that sits a second fault the burial was hiding. A rejected
create renders `_render_page(faults=...)` (`playbook_admin.py:441`), and
the list page renders the create form with `values = {}`
(`page.html:92`) — so everything typed is discarded on the way back. The
edit path does not have this problem: it already echoes
`_submitted_values(form)` (`playbook_admin.py:419`). The spec left the
gap open by attaching the surviving-values requirement to editing and
asking only that a rejected create render "the full fault list the same
way".

The discipline makes that loss worse than an annoyance. It is the one
field unique to the create surface, `_submitted_values` has no key for
it, and `_fields.html` falls back to the first option — so a rejected
create silently reverts it. A corrected resubmission then generates
`mg.<wrong-discipline>.<seq>`, and `update_step` refuses discipline
changes (`playbook_authoring.py:250-255`), leaving retirement plus a
successor step as the only recovery.

## What Changes

- Creating a step gets its own page, reached by an **Add step** control
  on the list. The create form leaves `page.html`.
- A rejected create re-renders the form still holding every submitted
  value, the discipline included — which requires `_submitted_values` to
  gain the one key it lacks.
- **Cancel** returns to the list carrying the filter that was active
  when **Add step** was pressed.
- A create that lands returns to the list under that same filter with
  the new step in view. Where the filter would hide the created step,
  the list says so and offers to clear it, so a create never looks lost.
- The timing-anchor fieldset offers only the inputs the anchor kind it
  was rendered with actually uses. It currently renders all five — kind,
  days, start, end, cadence — of which at most two apply, with nothing
  saying which.

**Deliberately deferred to their own changes**, on review findings that
this change bundled five concerns into one unreviewable unit:

- **Fault attribution** — marking the fields a fault concerns, in the
  three treatments (single field, combination, set-level). Deferred to
  `attribute-faults-to-fields`, which also owns removing the generated
  identifier from a rejected create's faults. It applies to both
  authoring surfaces, and its design questions should not hold this page.
- **The presentation vocabulary** — the token set, typography, vendored
  stylesheet and font faces. Deferred to
  `admin-presentation-vocabulary`, which also absorbs the list-table
  restyle. As scoped here it implemented no requirement at all, which is
  the state the spec-driven rule exists to prevent.

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
  through a rejection, and to state what happens when the active
  narrowing would hide the created step. The narrowing requirement
  introduced by `reorder-steps-under-filters` is extended to cover
  moving between the list and the create surface. A new requirement
  states that an anchor's unused inputs are not offered.

`playbook-authoring` and `launch-playbook` are deliberately **not**
modified.

## Impact

**Affected code**

- `launch/infrastructure/driving/playbook_admin.py` — a `GET` route
  serving the create surface; the existing `POST` re-rendering it on
  rejection with the submitted values; `_submitted_values` gaining a
  `discipline` key; the redirect target after a create that lands.
- `launch/infrastructure/driving/templates/new.html` — new file.
- `launch/infrastructure/driving/templates/_fields.html` — the anchor
  input groups. Shared with the edit page, which inherits the change.
- `launch/infrastructure/driving/templates/page.html` — the create
  section removed, an **Add step** control added.

**Explicitly untouched**

The domain and application layers.

**Coordination — this change is sequenced after
`reorder-steps-under-filters` and MUST NOT be archived before it**

That change is already in implementation and introduces the
filter-carrying mechanism this change consumes for **Cancel** and for
the post-create return.

- Its `## ADDED` requirement *The narrowed view survives every write and
  every move between views* states a rule this change's new surface has
  to honour. This change carries a `## MODIFIED` block for it, purely
  **extending** it: two scenarios covering the create surface, and a
  clause carrying the narrowing between the list and that surface. It
  corrects nothing — that change's `836db0e` already rewrote its
  *rejected list-level write* scenario against a retirement rather than
  a creation, for exactly this reason.
- The two deltas therefore **share exactly one requirement header**:
  `reorder-steps-under-filters` ADDs it, this change MODIFIES it. That
  is the sequencing dependency, not an accident to be resolved.
- **The tooling does not enforce the ordering.** `openspec validate`
  passes on a `MODIFIED` block for a requirement not yet in
  `openspec/specs/`. Archived out of order, this change's extension
  lands first and the counterpart's narrower `ADDED` version of the same
  header can then overwrite the create-surface clauses.
- The creation requirement's own narrowing clauses carry the same
  exposure by a different route: that requirement *does* exist in the
  served specs, so archiving this change alone would assert narrowing
  behaviour whose defining requirement is absent.

In `page.html` the overlap is small in both directions: that change
appends the filter query string to every form action, including the
create form this change deletes. Rebase on `main` once it merges.
