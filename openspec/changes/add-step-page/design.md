## Context

See `proposal.md` — Why. The constraints that shape the approach:

- Editing already lives on its own page (`GET`/`POST`
  `{PAGE_PATH}/steps/{step_id}/edit`, `edit.html`, with
  `PAGE_PATH = "/admin/playbook"`, `playbook_admin.py:80`). Creating
  being embedded in the list is the anomaly, not the thing being
  invented here.
- `_submitted_values` (`playbook_admin.py:348`) echoes thirteen form
  fields around a rejection and is already used by the edit path. It has
  **no `discipline` key** — the edit surface renders discipline
  read-only, so it never needed one. The create surface renders it as an
  input (`_fields.html:6-14`), so creating needs the helper extended by
  one key as well as called.
- `_anchor_from_form` (`playbook_admin.py:175`) reads only the inputs the
  selected kind uses and ignores the rest, so an input that is present
  but irrelevant is already harmless on submission.
- `create_step` returns the created `StepRecord`
  (`playbook_authoring.py:232`), so the new identifier is available to
  the redirect.
- The project is pure Python with no Node toolchain
  (`AGENTS.md` — Development Tooling).
- The guard is one dependency, `_require_admin`, and refusal is the
  app's own 404. Nothing here may create a route outside it.
- `reorder-steps-under-filters` is in flight against `page.html`.

## Goals / Non-Goals

**Goals:**

- Make the create surface reachable, and make a rejection cost nothing.
- Keep this change's edit of `page.html` small enough to rebase over the
  reorder work without a real merge.
- Keep every scenario in the delta observable from a server response,
  since the test tiers are server-side pytest with no browser tooling
  (`AGENTS.md` — Testing Strategy).

**Non-Goals:**

- Fault attribution. Deferred to `attribute-faults-to-fields`.
- The presentation vocabulary and the list-table restyle. Deferred to
  `admin-presentation-vocabulary`.
- A general filter-carrying helper. `reorder-steps-under-filters` owns
  that mechanism and lands first; this change consumes it.

## Decisions

### Sequencing: build on `reorder-steps-under-filters`, do not race it

That change is in implementation; this one is in planning. It owns the
filter-carrying mechanism — the query string appended to form actions
and navigation links — which is precisely what **Cancel** and the
post-create return need. Building a second mechanism here and
reconciling them later is strictly worse than waiting.

The specification side of the dependency is the part with teeth. This
change's delta carries a `## MODIFIED` block for a requirement that
change `ADDED`s, so the two share one header. `openspec validate` does
not catch a `MODIFIED` block aimed at a requirement absent from
`openspec/specs/` — it passes today — so the archive order is a human
obligation. Archived out of order, this change's extension lands first
and the counterpart's narrower version of the same header can overwrite
the create-surface clauses. The creation requirement's own narrowing
clauses carry the same exposure by a different route. `tasks.md` 1.3 and
1.4 cover both.

**Alternative rejected — land this first and let the reorder change
adapt.** It is the further-along change, its mechanism is the dependency
rather than the dependent, and it has already been reviewed and
committed against the current shape of `page.html`.

### Creating gets a page, matching how editing already works

`GET {PAGE_PATH}/steps/new` renders the create surface; `POST
{PAGE_PATH}/steps/create` keeps its path and form field names. A
rejection re-renders the create template with `_submitted_values(form)`
and the fault list, exactly as the edit path does.

`_submitted_values` gains `"discipline": form.get("discipline", "")`.
Without it the field silently reverts to `discipline_options[0]` and the
retry generates an identifier embedding the wrong discipline — which
`update_step` then refuses to correct, leaving retire-plus-successor as
the only recovery. This is the highest-consequence defect the change
fixes, and it is one line.

**Alternative rejected — a dialog or an HTMX-swapped panel on the list
page.** A page's worth of form that has to survive a rejection with
values and faults intact. A separate URL gets that for free.

### Success redirects; rejection renders

A create that lands returns `303` to the list URL carrying the active
narrowing and a `#step-<identifier>` fragment. A rejected create renders
the create template directly.

`reorder-steps-under-filters` rejected Post/Redirect/Get because a
rejected write has faults and submitted values to carry, which a
redirect cannot carry without a flash cookie. That objection is silent
on the success path, which has nothing to carry — and unlike every other
write, a successful create must land the admin on a *different page*
from the one they posted to, so rendering the list in the `POST`
response would leave the URL on the create path with a resubmit on
refresh.

The residual cost is real and small: after this change, refresh-resubmit
is fixed for create and not for edit, retire, un-retire or reorder.

`new.html` is **not** `hx-boost`ed. Under boosting the redirect is
followed by XHR and fragment handling is not guaranteed; a plain
navigation makes `#step-<identifier>` work the way the requirement
assumes. Identifiers contain dots, which are legal in a fragment and an
`id`, but must be escaped wherever the identifier is used as a CSS
selector.

**Alternative rejected — rendering the list from the `POST`.** Keeps one
pattern, but leaves the URL wrong, makes refresh a resubmit, and gives
the fragment nowhere to live.

### A created step the narrowing would hide

"Return under the active narrowing" and "with the created step in view"
conflict whenever the narrowing excludes the created step — routinely
true under a description search, and possible under a gate or discipline
filter. Left unresolved, the admin sees a list that appears not to have
accepted the write.

The narrowing wins, and the page says what happened: it renders under
the narrowing and states that the created step falls outside it,
offering to clear it. This reuses the affordance
`reorder-steps-under-filters` already establishes for telling the admin
that what they did is not fully visible.

**Alternative rejected — silently clearing the narrowing.** Violates the
narrowing requirement's *SHALL NOT widen, clear, or otherwise alter what
the page shows beyond the effect of the write itself*.

### Anchor inputs: server-rendered state, script only for liveness

The offered/not-offered state is rendered **server-side** from the anchor
kind the surface is rendered with — the step's own on a fresh edit, the
submitted one around a rejection, the default on a fresh create. A small
inline script re-applies it when the kind select changes, so the surface
responds without a round trip.

Server-rendering is what makes both scenarios observable in a response
body, which the test tiers can assert. Had the state existed only after
a script ran, neither scenario would have been testable in this stack and
`openspec-test-writer` would have had nothing to derive.

Inputs rendered as not offered stay in the DOM carrying their values, so
a reconsidered kind loses nothing, and `_anchor_from_form` ignores the
ones its kind does not use.

Without script, the rendered kind's inputs are correct and changing the
select does not re-apply the state until the next render. That is a
degradation from live to per-render, not to broken — which is why the
requirement is written against the kind a surface *was rendered with*
rather than against the one currently selected in the browser.

**Alternative rejected — `hx-get` fetching the fieldset per kind.** A
network round trip for a visibility decision, and it would have to carry
the rest of the form's values back and forth to avoid losing them.

## Risks / Trade-offs

- **`page.html` is being rewritten concurrently.** → This change's edit
  there is a deletion plus one control. Rebase after the reorder change
  merges.
- **`_fields.html` is shared with the edit page.** → Intended: the anchor
  requirement is written for the authoring surfaces, not for creating
  alone. The cost is that the edit page changes here too and must be
  verified.
- **Two response patterns for writes.** → Split on a stated line, and
  confined to create.
- **The create surface ships on unstyled Pico.** → Accepted consequence
  of deferring the presentation vocabulary. The page is reachable and
  correct before it is handsome.

## Migration Plan

None. No schema, data or persisted-state change. Deployment is routes
and templates; rollback is a revert of the branch.

## Open Questions

- How long the created step stays visually distinguished after the
  redirect lands. Deferrable: it changes neither the specs, the routes,
  nor the task breakdown, and it lands naturally with
  `admin-presentation-vocabulary`.
