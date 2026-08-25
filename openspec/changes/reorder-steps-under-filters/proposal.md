## Why

The steps management page is unusable at the size of the set it actually
serves. The seeded playbook holds 105 steps, 65 of them in the `listable`
gate alone, so an admin filters first as a matter of course — and every
write then throws the filter away and returns the unfiltered list. The
cause is not the page's server-rendered approach: the filter state lives
in the query string and the `GET` route reads it correctly, but every
mutating route re-renders with `_render_page()` and no arguments, and no
form carries the filter back to the server in the first place.

Underneath that sits a second fault the reset was masking. Reordering
ignores the active filter entirely — it sorts the gate's whole live set —
so once filters survive a write, pressing the move button appears to do
nothing: the step swaps with a neighbour the filter is hiding.

## What Changes

- Every write carries the active filter — gate, discipline, search term
  and the show-retired control — and re-renders the view the admin was
  looking at, instead of resetting to the unfiltered default. This
  covers the edit round trip, whose link and back-link discard the
  filter today, as well as the list-level writes.
- Reordering becomes filter-aware. A move names the visible step it
  should come to rest after — or the head of the visible list — and the
  page places it there, with every other step, hidden ones included,
  keeping its relative order.
- Reordering goes inert, with the reason stated, in the two views where
  a move cannot be given an honest meaning: while a description search
  is active, and while retired steps are shown. Gate and discipline
  filters leave it live.
- A reorder is submitted against the version of the step set the view it
  was made on was rendered from, and is checked against that version both
  when its position is computed and when it is persisted, so a move made
  on a list another write has superseded is rejected rather than silently
  applied to a set the admin never saw.
- Each step renders its position within its gate, so a move that crosses
  steps the filter is hiding is readable rather than silent.

## Capabilities

### New Capabilities

None. This changes how an existing page behaves, not what the system can
do.

### Modified Capabilities

- `playbook-admin`: a new requirement that the narrowed view survives
  every write **and** every movement between the list and a step's edit
  form, which is navigation rather than a write and was where the filter
  leaked. The reorder requirement is redefined to
  state what a move means while a filter narrows the list, and where
  reordering is unavailable. The step-table requirement gains the
  per-gate position.
- `playbook-authoring`: the reorder requirement gains a caller-supplied
  view of the set. Its existing scenario — *"a reorder submitted against
  a version of the step set that a later accepted write has superseded"*
  is rejected — cannot be satisfied by any caller today, because
  `reorder_step` loads its own view and retries on conflict. That retry
  is safe only while the position is recomputed from each fresh load;
  once the caller computes the position from a filtered view, a retry
  would apply a stale position to a newer set. Pinning the version
  suppresses the retry and makes the existing scenario reachable.

No **BREAKING** changes: the persisted step set, the schema, the
validation rules and the meaning of a step's order are untouched.

## Impact

- `src/commerce_ops/launch/infrastructure/driving/playbook_admin.py` —
  filter reading centralised into one helper used by the read routes and
  every write route; `_move` replaced by a filter-aware move deriving
  its target index from a named visible neighbour and the version it was
  computed against.
- `src/commerce_ops/launch/application/playbook_authoring.py` —
  `reorder_step` accepts an optional expected set version; when given, a
  version that is not the one the write reads is rejected instead of
  retried, whichever way it differs.
- `src/commerce_ops/launch/infrastructure/driving/templates/page.html`
  and `edit.html` — form actions, the edit link, the retired-toggle
  links and the back link carry the filter; the position column; the
  inert states and their explanations.
- `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py`
  and the authoring tests gain coverage for filter survival, filtered
  move placement, the inert views, and the pinned-version rejection.
- No migration, no schema change, no change to the domain layer.

## Sequencing against `add-step-page`

`add-step-page`, in flight alongside this change, moves creation onto its
own surface and MODIFIES this change's added requirement — *"The narrowed
view survives every write and every move between views"* — to cover the
list⇄create-surface transition. That requirement does not exist in
`openspec/specs/playbook-admin/spec.md` until this change is archived, so
**this change SHALL be archived first**; archiving `add-step-page` before
it would leave that MODIFIED block with no requirement to modify.

The scenario "A rejected list-level write keeps the narrowing" is written
against a **retirement** rather than a creation for the same reason: once
creation re-renders its own surface, a rejected creation stops being an
example of a write that re-renders the list.

## Deferred to a follow-on change

Reordering by **dragging** is deliberately out of scope here, and is
recorded for a follow-on change once this one is shipped. It carries the
page's first HTMX fragment rendering, out-of-band swaps for the fault
and notice regions, and a third vendored front-end asset — a distinct
risk surface from the bug this change fixes, and one that reads better
as its own reviewable unit. The move rule this change specifies is what
dragging would express, so the follow-on is presentational.

The consequence accepted meanwhile: a move still re-renders the whole
page and returns the admin to the top of the list. With the filter now
surviving the write, the list being scrolled is a narrowed one, which is
what makes this tolerable rather than merely deferred.

Also deferred, as before: a "move to position N" input, the better
answer for the unfiltered 65-step gate.
