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
  (`AGENTS.md` — Testing Strategy). Where a guarantee genuinely ends at
  the browser — scroll position — the delta stops at what the response
  says, and the browser half is verified by hand.

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

`_submitted_values` gains a `discipline` key defaulting to the same
value the template does. A `""` default will not do: it matches no
`<option>`, so nothing renders `selected`, and the browser falls back to
displaying and submitting the first option — the very defect being
fixed, wearing a different disguise.

The default has to come from somewhere both can reach. `discipline_options`
today exists only as a key `_option_context()` builds
(`playbook_admin.py:250`), so it is not a name `_submitted_values` can
refer to. Hoist it to a module constant and have both use it:

    _DISCIPLINE_OPTIONS: Final = [d.value for d in Discipline]

The create route's own fallback (`Discipline.LISTING`,
`playbook_admin.py:435`) disagrees with the template's first option
(`strategy`) — a create posting no discipline yields a `listing` step
while the re-rendered form shows `strategy`. Rather than pick a winner,
**the field is made required**: the select always submits a value, so
only a hand-built `POST` omits it, and a refused hand-built `POST` is a
better answer than either silent default.
Without the key the field silently reverts to `discipline_options[0]` and the
retry generates an identifier embedding the wrong discipline — which
`update_step` then refuses to correct, leaving retire-plus-successor as
the only recovery. This is the highest-consequence defect the change
fixes, and it is one line.

**Alternative rejected — a dialog or an HTMX-swapped panel on the list
page.** A page's worth of form that has to survive a rejection with
values and faults intact. A separate URL gets that for free.

### Success redirects; rejection renders

A create that lands returns `303` to the list URL carrying the active
narrowing, the created step's identity, and a `#step-<identifier>`
fragment. A rejected create renders the create template directly.

`reorder-steps-under-filters` rejected Post/Redirect/Get because a
rejected write has *faults and submitted values* to carry, which a
redirect cannot carry without a flash cookie. The success path carries
neither — but it is not empty, and an earlier draft of this document
wrongly said it was. It carries one thing: **which step was created**.

That matters because a fragment is never transmitted to the server. A
redirect to `…?<narrowing>#step-<id>` tells the browser where to scroll
and tells the server nothing, so the list render that follows could not
know a step had just been created, could not decide whether the
narrowing hides it, and could not say so. The rule below would have been
unimplementable.

So the redirect carries the identity as a query parameter as well:

    303 → {PAGE_PATH}?<narrowing>&created=<identifier>#step-<identifier>

`created` is server-visible, which is what makes the "falls outside the
narrowing" rule testable in the pytest tier. It survives a refresh, and
it keeps the URL honest about what happened.

The *addressing* clause rests on a different observable: the created
step's row carries `id="step-<identifier>"`, and the `303`'s `Location`
carries the matching fragment. Those two are the assertable markers —
naming them here, as `hidden` is named below, keeps the requirement at
the level of behaviour while leaving the test author nothing to invent.
Asserting merely that the identifier appears in the body would be
vacuous, since the row is rendered either way.

When the notice fires is stated once, in the delta, and not restated
here: the test is whether clearing the narrowing the notice offers to
clear would actually reveal the named step. That rule covers the stale
bookmark, the hand-edited URL and — less obviously — the step retired
since it was created, which `steps.load()` still returns and `_visible`
(`playbook_admin.py:271-279`) then filters out. Such a step *is* among
the served records, so a "among the served records and hidden" test
would fire on it and offer a clear that reveals nothing.

Unlike every other write, a successful create must land the admin on a
*different page* from the one they posted to, so rendering the list in
the `POST` response would leave the URL on the create path with a
resubmit on refresh.

The residual cost is real and small: after this change, refresh-resubmit
is fixed for create and not for edit, retire, un-retire or reorder.

**The transition to and from the create surface is un-boosted**, which
is not the same as saying `new.html` is un-boosted — an earlier draft
said that, and it does not work. `page.html:10` carries
`hx-boost="true"` on `<body>`, and hx-boost is inherited, so the **Add
step** anchor is boosted: htmx fetches the create surface and swaps it
into the *existing* body. `new.html`'s own `<body>` element is discarded
along with its attributes, so an `hx-boost="false"` there never takes
effect, the create `POST` is XHR, the `303` is followed by XHR, and the
fragment is not honoured. Worse, the behaviour would differ depending on
whether the admin clicked **Add step** or loaded the URL directly.

The boost is therefore switched off at the places that survive the
swap: `hx-boost="false"` on the **Add step** control itself, on the
create form in `new.html`, and on **Cancel**. All three are real
navigations, so the fragment works on the path admins actually take and
no transition depends on an inherited attribute nobody wrote down.

Identifiers contain dots, which are legal in a fragment and an `id`, but
must be escaped wherever the identifier is used as a CSS selector.

**Alternative rejected — rendering the list from the `POST`.** Keeps one
pattern, but leaves the URL wrong, makes refresh a resubmit, and gives
the fragment nowhere to live.

### A created step the narrowing would hide

"Return under the active narrowing" and "bring the created step into
view" conflict whenever the narrowing excludes the created step — routinely
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

"Not offered" is expressed as the `hidden` attribute on each input's
own group. The grouping is per input, not per kind: `anchor_start` is
used by both `window` and `open-ended` (`_fields.html:71`), so a
per-kind partition would have to render it twice, and two inputs of one
name submit two values — `_form_of` keeps the last, which would coerce
an open-ended anchor's start to the hidden group's empty value. Naming the marker here rather than in the requirement keeps the
requirement at the level of behaviour while still giving the test author
something to assert — a mismatch is then a fixture correction, not an
invented assumption.

Inputs rendered as not offered stay in the DOM carrying their values, so
a reconsidered kind loses nothing, and `_anchor_from_form` ignores the
ones its kind does not use.

Without script, the rendered kind's inputs are correct and changing the
select does not re-apply the state until the next render. That is a
degradation from live to per-render, not to broken — which is why the
requirement is written against the kind a surface *was rendered with*
rather than against the one currently selected in the browser.

The script lives inside the swapped region — with `_fields.html`, not in
`<head>`. The edit surface is reached by a boosted swap that replaces
only `body`'s innerHTML, so a `<head>`-placed script would never run
there: liveness would silently be present on the create page and absent
on the edit page, a per-surface split with no reason behind it.

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
- **The create flow has no signed-out panel.** → Two causes, not one:
  `page.html`'s `htmx:responseError` handler fires only on an XHR
  (`event.detail.xhr`), which un-boosting removes; and the handler lives
  in `page.html`'s own script, which `new.html` does not carry — so
  re-boosting would not restore it either. An expired session on a
  create shows FastAPI's raw `{"detail":"Not Found"}` instead of
  "Signed out … nothing was saved". This still satisfies `admin-session`'s
  absence-shaped refusal, so no requirement is broken, and it is
  accepted here rather than papered over — the create surface wanting
  its own refusal treatment is a real gap, but it is one this change
  did not create and does not need to close.

## Migration Plan

None. No schema, data or persisted-state change. Deployment is routes
and templates; rollback is a revert of the branch.

## Open Questions

- Whether the created step is visually distinguished at all once the
  redirect lands, and if so for how long. This change requires only that
  the list *address* it; a visual treatment is neither specified nor
  built here. Deferrable: it changes neither the specs, the routes, nor
  the task breakdown, and it belongs with
  `admin-presentation-vocabulary`.
