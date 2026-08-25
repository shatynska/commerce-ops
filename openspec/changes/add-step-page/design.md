## Context

See `proposal.md` — Why. The constraints that shape the approach:

- Editing already lives on its own page (`GET`/`POST`
  `{PAGE_PATH}/steps/{step_id}/edit`, `edit.html`, with
  `PAGE_PATH = "/admin/playbook"`). Creating being embedded in the list
  is the anomaly, not the thing being invented here.
- `_submitted_values(form: dict[str, str])` echoes the form back around a
  rejection and is already used by the edit path. Two things are wrong
  with it for this change, and they are different in kind — one is a
  missing key, the other is the wrong shape. See the decision below.
- `_form_of` reduces the posted form with
  `{key: str(value) for key, value in posted.items()}`. Starlette's
  `FormData.items()` yields every pair including repeats, so the
  comprehension keeps the **last** value under any repeated key.
- `_anchor_from_form` reads only the inputs the selected anchor kind uses
  and ignores the rest, so an input that is present but irrelevant is
  already harmless on submission. `_fields.html` renders the anchor kind
  selector plus `anchor_days`, `anchor_start`, `anchor_end` and
  `anchor_cadence`, all four unconditionally.
- `create_step` returns the created `StepRecord`, so the new identifier
  is available to the redirect.
- Both `page.html` and `edit.html` carry `hx-boost="true"` on `<body>`.
- The project is pure Python with no Node toolchain
  (`AGENTS.md` — Development Tooling).
- The guard is one dependency, `_require_admin`, and refusal is the
  app's own 404. Nothing here may create a route outside it.
- `redesign-step-fields` is in flight against every one of these files.

Line numbers are deliberately omitted from this document. Every symbol
named above sits in a file `redesign-step-fields` rewrites, so a line
number recorded now is wrong by the time this change is applied — which
is exactly what happened to the previous draft.

## Goals / Non-Goals

**Goals:**

- Make the create surface reachable, and make a rejection cost nothing —
  including a rejection of a form that names people.
- Keep this change's edit of `page.html` small enough to rebase over
  `redesign-step-fields` without a real merge.
- Keep every scenario in the delta observable from a server response,
  since the test tiers are server-side pytest with no browser tooling
  (`AGENTS.md` — Testing Strategy). Where a guarantee genuinely ends at
  the browser — scroll position — the delta stops at what the response
  says, and the browser half is verified by hand.

**Non-Goals:**

- **The field set.** Which fields the form carries, how the assignee
  control is populated from the roster, and what the new fields mean are
  `redesign-step-fields`'s decisions. This change relocates the form and
  owns its rejection path; it does not choose its contents.
- Fault attribution. Deferred to `attribute-faults-to-fields`.
- The presentation vocabulary and the list-table restyle. Deferred to
  `admin-presentation-vocabulary`.
- A general filter-carrying helper. `reorder-steps-under-filters` owns
  that mechanism and is archived; this change consumes it.

## Decisions

### Sequencing: build on `redesign-step-fields`, do not race it

That change rebuilds the step's field set across the domain, the
application, persistence and the admin page. The create form is one of
the surfaces it rebuilds — its task 5.1 adds the new fields to the form,
5.2 renders assignee selection from the roster. This change moves that
same form to its own page.

Landing this change first would mean `redesign-step-fields` adding seven
fields to a template that has just moved and resolving its own
rejection-path work against a create route whose response contract has
just changed from `200`-with-list to `303`-to-list. Landing it second
means this change's template is the one that receives those fields,
once.

The specification side is weaker than the previous sequencing
dependency but not absent. The two deltas **share no requirement
header** — this change MODIFIES *Steps can be created, retired and
un-retired from the page* and *The narrowed view survives every write
and every move between views*, and `redesign-step-fields` touches
neither — so there is no block-overwriting hazard of the kind
`reorder-steps-under-filters` carried. The hazard here is semantic:
archived first, this change's creation requirement would assert where a
created step renders in the vocabulary of a lifecycle status the served
specs do not yet define, and `openspec validate` checks headers rather
than whether a requirement's terms mean anything. `tasks.md` 1.1 and 6.6
guard it at both ends.

**Alternative rejected — fold the create surface into
`redesign-step-fields`.** One pass over the form instead of two, which
is genuinely attractive. Rejected because that change is already 39
tasks and four capabilities, and `AGENTS.md` asks for changes small
enough to review in one sitting and for a change that grows to cover
multiple independent concerns to be split rather than extended.

**Alternative rejected — draft this against today's fields and adapt on
arrival.** That is the state this change was found in, and the adaptation
is not mechanical: the field set decides what the rejection path has to
carry, and the status field decides where a created step renders.

### Creating gets a page, matching how editing already works

`GET {PAGE_PATH}/steps/new` renders the create surface; `POST
{PAGE_PATH}/steps/create` keeps its path and form field names. A
rejection re-renders the create template with the submitted values and
the fault list, exactly as the edit path does.

**Alternative rejected — a dialog or an HTMX-swapped panel on the list
page.** A page's worth of form that has to survive a rejection with
values and faults intact — and under the new field set it is closer to
two pages' worth. A separate URL gets that for free.

### The submitted-values helper needs a different shape, not one more key

This is the decision the new field set forces, and it replaces the
previous draft's "one line" framing.

`_submitted_values` has two distinct defects for a create surface:

**A missing key — `discipline`.** The edit surface renders discipline
read-only, because `update_step` refuses discipline changes, so the
helper never needed the key. The create surface renders it as an input.
Without the key the template falls back to its first option, so a
rejected create reverts the discipline; the retry then generates an
identifier embedding the wrong one, which `update_step` will not
correct. `redesign-step-fields` keeps both underlying rules — the
identifier still carries the discipline as its second segment, and
discipline is still not updatable — so this defect survives that change
unless something closes it. **This change closes it**, and it is
genuinely one key.

A `""` default will not do: it matches no `<option>`, so nothing renders
`selected`, and the browser falls back to displaying and submitting the
first option — the same defect wearing a disguise. The default must come
from somewhere both the helper and `_option_context()` can reach, which
today it does not: `discipline_options` exists only as a key
`_option_context()` builds. Hoisting it to a module constant gives both
a name to refer to.

Separately, the create route's own fallback (`Discipline.LISTING`)
disagrees with the template's first option (`strategy`) — a create
posting no discipline yields a `listing` step while the re-rendered form
shows `strategy`. Rather than pick a winner, **the field is made
required**: the select always submits a value, so only a hand-built
`POST` omits it, and a refused hand-built `POST` is a better answer than
either silent default.

This is a change to what the endpoint accepts, so it is stated in the
delta as a clause and a scenario rather than only here. `AGENTS.md` has
tests derived strictly from the specification deltas; a behaviour that
lives only in a design document and a task ships untested, and a later
change reverses it without noticing there was anything to reverse.

**A wrong shape — `assignees`.** Assignees are zero or more roster
identifiers, submitted as a repeated form key. `_form_of` collapses
repeats to the last value and `_submitted_values` reads with
`form.get()`, so a create naming three people and rejected comes back
naming one. No number of added keys fixes this; the chokepoint is
`_form_of`'s `dict[str, str]`, which cannot represent a repeated key at
all.

**Who ought to own fixing it — and who probably will.**
`redesign-step-fields` ought to. It introduces assignees and carries the
requirement that a rejected form still holds what was typed, and that
requirement binds the edit form as much as the create form.

But that expectation is weaker than it first looks, and planning on it
would be a mistake. **That change carries no task for the reshape.** Its
tasks 5.1 and 5.2 add the fields to the form and render assignee
selection from the roster; nothing in its 39 tasks names `_form_of`,
`_submitted_values`, or the round-trip. Its one rejection scenario —
*a form rejected by validation shows every fault with the typed values*
— describes a step violating two field rules, and would pass against a
helper that keeps only the last value under a repeated key. So the
defect can pass straight through that change untouched.

**Task 3.2b is therefore written as the fix, with verification as the
cheap branch** — not the other way round. If the shape is already
correct on arrival, the task collapses to an assertion and costs
nothing. If it is not, this change fixes it, because the create
surface's own requirement cannot be met otherwise.

That fix is not local, and the task says so rather than pretending
otherwise: `_form_of` returns `dict[str, str]` and every write route
consumes it — create, edit, retire, un-retire, reorder — so widening it
to carry repeated keys touches each call site and `_authorable_fields`
besides. mypy bounds the blast radius, but this is shared code inside a
change whose stated non-goal is the field set. It is accepted as a
contingency, and 6.4's boundary check is what confirms it stayed inside
the infrastructure layer.

**What this change owns either way.** The create surface's own rejection
path — re-rendering `new.html` rather than the list — and the
create-specific guarantee that it loses nothing on the way. The delta
carries a scenario for the two-assignee case on the create surface
specifically. That is not a duplicate of `redesign-step-fields`'s
generic scenario: this change builds the surface that rejection now
renders, the rejection path it replaces is the one that discarded
everything, and the two-assignee case is the narrowest one that
distinguishes "holds what was typed" from "holds one of what was
typed".

### Success redirects; rejection renders

A create that lands returns `303` to the list URL carrying the active
narrowing, the created step's identity, and a `#step-<identifier>`
fragment. A rejected create renders the create template directly.

`reorder-steps-under-filters` rejected Post/Redirect/Get because a
rejected write has *faults and submitted values* to carry, which a
redirect cannot carry without a flash cookie. The success path carries
neither — but it is not empty. It carries one thing: **which step was
created**.

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

Unlike every other write, a successful create must land the admin on a
*different page* from the one they posted to, so rendering the list in
the `POST` response would leave the URL on the create path with a
resubmit on refresh.

The residual cost is real and small: after this change, refresh-resubmit
is fixed for create and not for edit, retire, un-retire or reorder.

**The transition to and from the create surface is un-boosted**, which
is not the same as saying `new.html` is un-boosted. `page.html`'s
`<body>` carries `hx-boost="true"`, and hx-boost is inherited, so the
**Add step** anchor is boosted: htmx fetches the create surface and
swaps it into the *existing* body. `new.html`'s own `<body>` element is
discarded along with its attributes, so an `hx-boost="false"` there
never takes effect, the create `POST` is XHR, the `303` is followed by
XHR, and the fragment is not honoured. Worse, the behaviour would differ
depending on whether the admin clicked **Add step** or loaded the URL
directly.

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

### Where a created step lands depends on the status it was created with

`redesign-step-fields` makes status authorable at create, and its
authoring delta is explicit about the consequence: a created step takes
the last slot of its gate *where it is created `active`*, and takes no
slot otherwise. Its admin delta places non-active steps outside their
gate's orderable list, set apart from the served set.

So "the created step is rendered as the last step of its gate" — the
previous draft's headline scenario, and the base requirement's — is true
only for an `active` create. A step created as a `draft` renders
somewhere else entirely, and it is the case the draft status was added
to serve: writing down work before it is ready.

The addressing mechanism is indifferent to this, which is what makes the
resolution cheap. The row carries `id="step-<identifier>"` wherever it
is rendered, and the fragment finds it. What must not happen is the
*implementation* assuming the served order — looking the created step up
among a gate's active steps, or rendering the notice by asking whether
it appears in that order. The delta states the rule as "address it
wherever it renders" for that reason, and the tasks say so twice.

### A created step the narrowing would hide

"Return under the active narrowing" and "bring the created step into
view" conflict whenever the narrowing excludes the created step —
possible under a gate or discipline filter, and routine under a search.

The narrowing wins, and the page says what happened: it renders under
the narrowing and states that the created step falls outside it,
offering to clear it. This reuses the affordance
`reorder-steps-under-filters` established for telling the admin that
what they did is not fully visible.

When the notice fires is stated once, in the delta, and not restated
here: the test is whether clearing the narrowing the notice offers to
clear would actually reveal the named step. That rule covers the stale
bookmark, the hand-edited URL and — less obviously — the step retired
since it was created, which the page's read still returns and the
retired-steps control then filters out. The page's read *does* return
such a step, so a "returned but hidden" test would fire on it and offer
a clear that reveals nothing.

One input to that test changes under `redesign-step-fields`: search
matches a step's **name and its description**, not the description
alone. A created step is hidden by a search only when the term matches
neither. The delta's scenario is written that way, and the check must
ask the page's own filter rather than reimplement it.

**"Served" is a trap here, and the delta avoids the word deliberately.**
`redesign-step-fields` claims it for the `active` set — the steps a
launch is actually held to — across four capability deltas. The notice's
precondition is not about that set at all: it asks whether the step
would appear once the narrowing is cleared, and a step created as a
`draft` is outside the served set while being exactly the step the
notice exists to find. Written as "not among the served records", the
rule reads as suppressing the notice for every non-active create, which
contradicts the same requirement's *a create SHALL NOT appear to have
been lost* two paragraphs above. So the requirement says "the steps the
page's own read returns" and says why, and task 3.13 uses the same
phrase rather than the shorter one.

**Alternative rejected — silently clearing the narrowing.** Violates the
narrowing requirement's *SHALL NOT widen, clear, or otherwise alter what
the page shows beyond the effect of the write itself*.

### Anchor inputs: server-rendered state, script only for liveness

The offered/not-offered state is rendered **server-side** from the
anchor kind the surface is rendered with — the step's own on a fresh
edit, the submitted one around a rejection, the default on a fresh
create. A small inline script re-applies it when the anchor kind select
changes, so the surface responds without a round trip.

Server-rendering is what makes both scenarios observable in a response
body, which the test tiers can assert. Had the state existed only after
a script ran, neither scenario would have been testable in this stack
and `openspec-test-writer` would have had nothing to derive.

**"Not offered" is the `hidden` attribute, not `disabled`, and the
distinction is load-bearing.** `redesign-step-fields` states the general
rule for a field carrying no meaning for a step's kind as "hidden **or**
disabled", which is right for an automation brief on a human step: that
value should not reach the write. The anchor's case is the opposite. The
requirement here demands that a not-offered input *retain* its value so
that a reconsidered anchor kind loses nothing — and a disabled input
submits nothing, so `disabled` would satisfy the visibility half and
silently break the retention half. The delta says so in normative text
rather than leaving it to be rediscovered.

The grouping is per input, not per anchor kind: `anchor_start` is used
by both `window` and `open-ended`, so a per-kind partition would have to
render it twice, and two inputs of one name submit two values —
`_form_of` keeps the last, which would coerce an open-ended anchor's
start to the hidden group's empty value.

Inputs rendered as not offered stay in the DOM carrying their values,
and `_anchor_from_form` ignores the ones its kind does not use — which
is what makes retaining them safe rather than merely tidy. The delta
carries a scenario for that, so the property is asserted rather than
assumed.

Without script, the rendered kind's inputs are correct and changing the
select does not re-apply the state until the next render. That is a
degradation from live to per-render, not to broken — which is why the
requirement is written against the anchor kind a surface *was rendered
with* rather than against the one currently selected in the browser.

The script lives inside the swapped region — with `_fields.html`, not in
`<head>`. The edit surface is reached by a boosted swap that replaces
only `body`'s innerHTML, so a `<head>`-placed script would never run
there: liveness would silently be present on the create page and absent
on the edit page, a per-surface split with no reason behind it.

**On the requirement's title.** The previous draft called it *The timing
anchor offers only the inputs the kind it was rendered with uses*. Under
`redesign-step-fields`, `kind` becomes a step field naming `human` or
`automated`, and both requirements live in the same capability spec —
so the unqualified word now reads two ways. The title and body say
"anchor kind" throughout.

**Alternative rejected — `hx-get` fetching the fieldset per kind.** A
network round trip for a visibility decision, and it would have to carry
the rest of the form's values back and forth to avoid losing them.

## Risks / Trade-offs

- **Every file this change touches is being rewritten concurrently by
  `redesign-step-fields`.** → This change is sequenced strictly after it
  and rebased on `main` once it merges. Its own edit to `page.html` is a
  deletion plus one control; its edit to `_fields.html` is confined to
  the anchor group.
- **The rejection path's correctness depends on a fix this change most
  likely has to make.** → The multi-valued assignee round-trip *ought*
  to belong to `redesign-step-fields`, but that change carries no task
  for it, so plan on doing it here and treat arriving-already-fixed as
  the lucky branch, not the expected one. The work is a signature change
  on `_form_of`, which every write route consumes — create, edit,
  retire, un-retire, reorder — plus `_authorable_fields`, so the blast
  radius is the helper's call sites rather than the helper alone. mypy
  bounds it and 6.4 confirms it stayed inside the infrastructure layer,
  but this is shared code touched inside a change whose stated non-goal
  is the field set. Budget it.
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
- Whether **Add step** should offer a status at all, or always create a
  `draft` and leave activation to the status control
  `redesign-step-fields` adds. The delta is written to hold either way —
  it says where a created step is addressed *given* the status it was
  created with, and carries a scenario for each — so this is a question
  about the form, which that change owns, not about this one.
