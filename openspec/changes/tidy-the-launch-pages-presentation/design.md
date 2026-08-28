## Context

See `proposal.md` — *Why*. The three defects were found by opening the deployed
pages, which is `add-launch-tracking-pages` task group 8 doing its job.

What shapes the approach:

- Both launch pages already load `pico.min.css` and `vocabulary.css` from the
  shared guarded route, and are required by *The pages' presentation comes from
  the shared admin vocabulary* to carry no styling of their own. So every rule
  this change writes goes in `vocabulary.css`, which the playbook and roster
  surfaces load too.
- Pico's own reset sets `button[type=submit], input:not([type=checkbox],[type=radio]), select, textarea { width: 100% }`. Every admin surface fights this. The playbook
  page wins by scoping `width: auto` to `.narrowing-bar`; the roster page wins
  through `form.authoring`; the launches page has neither wrapper, so it loses.
  That is the whole mechanism behind the oversized `Apply`.
- Of everything the two launch pages render, `vocabulary.css` matches only
  `mark`, `container` and `form.narrowing`. `mark` is why the attention marks
  are the one legible thing on a row; `form.narrowing` is a bare `display: flex`
  (`:461`), which is why the narrowing is a row of full-width boxes rather than
  a literal stack. Nothing matches `launches`, `launch-row`, `product-id`,
  `gate`, `launch-date`, `reveal`, `finished`, `gate-sequence`, `gate-group`,
  `step-row`, `step-name`, `step-id`, `discipline`, `due` or `outcome`.
- **Five** admin surfaces load this stylesheet, not three: the step list, the
  roster page, the product index and the product dossier (`products.html`,
  `product.html`, from `add-product-dossier-page`), and these two. Every
  cross-surface obligation in this change ranges over all of them.
- `launch-admin` has no spec in `openspec/specs/`: `add-launch-tracking-pages` is
  merged and deployed but unarchived, itself blocked behind `add-launch-journal`
  (its task 6.2).

## Goals / Non-Goals

**Goals:**

- One narrowing shape across the admin surfaces, so the steps page and the
  launches page are recognisably the same product and one presentation fix
  reaches both.
- Rules in the shared vocabulary for what the launch surfaces render, written so
  that adding them cannot change what the playbook or roster surfaces render.
- Presentation decisions expressed as markers a response can be asked for,
  wherever they can be — the standard `playbook-admin` set for its own
  vocabulary.

**Non-Goals:**

- No change to what either page enumerates, orders, serves or refuses. No route,
  use case, read model, or query contract changes, beyond the element the
  needs-attention narrowing is submitted from.
- No design-token change. The vocabulary's spacing, ink and scale variables are
  used as they stand; nothing here introduces a new one unless a rule genuinely
  has no existing token to reach for.
- No responsive breakpoint work, no build step, no asset. *The presentation
  assets stay behind the admin guard and need no build step* binds this change
  as it binds the vocabulary it extends.
- Not the roster page, not the steps page, not the product dossier pages.

## Decisions

### 1. Reuse `.narrowing-bar` rather than write a second bar

The launches narrowing adopts the playbook page's markup shape: a
`.narrowing-bar` wrapper holding the reveal control and the form, the form's
controls inside a `fieldset role="group"`, the submit carrying `row-action`.
Every sizing rule then applies with no new CSS at all — the existing block is
already written against `.narrowing-bar select`, `.narrowing-bar input`,
`.narrowing-bar .row-action`.

*Alternative considered:* a `.launch-narrowing` block of its own. Rejected — it
is the same control doing the same job on a sibling surface, and a second block
is exactly the divergence *The pages' presentation comes from the shared admin
vocabulary* exists to prevent. If the two ever need to differ, the difference
should be a rule that says so, not two independent blocks that drifted.

*Consequence to check:* the existing rules are scoped `.narrowing-bar select`,
not `.narrowing .narrowing-bar select`, so they reach the launches bar
unmodified. Task 1.1 verifies that by reading the block rather than assuming it.

### 2. The needs-attention checkbox becomes a select

`role="group"` renders its children as one segmented control; a bare checkbox
with a text label inside that group reads as neither a segment nor a label. The
narrowing becomes two selects and a submit — the steps page's own shape —
with the second offering `every launch` / `needs attention`.

The query contract is preserved deliberately: the select is named `attention`
with values `""` and `"1"`, so a submission sends `attention=1` when narrowing
and `attention=` when not. `launch_admin.py:484` reads it as
`(request.query_params.get("attention") or "").strip()` and narrows on
`bool(gate or attention)` (`:491`), so an empty parameter and an absent one are
already the same thing — which is also how the gate select has always behaved
with its `All gates` option. A bookmarked `?attention=1` keeps working
unchanged.

The delta states this as the equivalence it is, **not** as "the parameter is
absent when not narrowing". A `<select>` in a GET form always submits its name;
a requirement forbidding that would be false on the day it archived, of
behaviour the existing gate select already has.

The select must also render the active narrowing as `selected`. The checkbox
rendered `checked`, so this is a state the surface shows today; a select that
forgets it leaves the list narrowed while the bar reads `every launch`, and the
next submission from that bar silently clears the narrowing. It is a scenario
in the delta rather than a note here, because nothing in the existing suite
would catch it — those tests *drive* the narrowing, they do not read it back.

*Alternative considered:* keep the checkbox, place it in the bar but outside the
fieldset. Rejected — it leaves two narrowings that look like different kinds of
thing, and the vertical alignment of a checkbox against grouped selects is the
kind of thing that reads as broken rather than as deliberate.

*Alternative considered:* three-state select including "no longer in play".
Rejected — that control is **not a narrowing**, by an explicit clause of
`launch-admin`, and folding it into the narrowing select would make a spec
distinction invisible in the UI that most needs to show it.

### 3. The reveal control leads the bar, styled `row-action quiet`

Exactly what the steps page does with its retired toggle, which is the same
control with the same meaning: show me the set I usually do not want to see.
Reusing the treatment is what makes the two pages read as one product.

Its position in the bar is presentation only. The delta spec states outright
that it stays not-a-narrowing for the empty-state rules, because the one thing a
reader would reasonably infer from the new layout is the thing that is not true.

**But peers must compose.** The narrowing form submits `gate` and `attention`
only; `finished=1` is not among its fields, so submitting a narrowing while
launches no longer in play are revealed drops the reveal. That is true of the
page as it stands — the two controls sit in separate bands, so it reads as two
separate actions — and putting them in one bar turns an obscure defect into one
that reads as the new bar being broken. The steps page solved this in one line
(`page.html:87`: `{% if narrowing.retired %}<input type="hidden" name="retired"
value="1">{% endif %}`), and the same line is what the launches form takes. No
route or query change: `finished` is a parameter the route already reads.

*Alternative considered:* declare the non-composition out of scope, since it
predates this change. Rejected — the change's whole claim is that the bar reads
as one control, and a control that discards half its own state on submission
does not.

### 4. Rows are flex lines, not a grid, and not a table

`.launch-row` and `.step-row` become `display: flex; flex-wrap: wrap;
align-items: baseline` with a gap, the naming element taking the free space and
the remaining facts sitting after it at the quiet ink and fine scale the `mark`
and `td small` rules already establish.

*Alternative considered:* a real `<table>`, as the steps page uses. Rejected —
the templates chose `<ul>/<li>` for a stated reason recorded in both files: the
row must be **one element** carrying the launch's link and every fact about it,
so that the element a reader lands on is the line they see. A table puts the
link in a cell and makes the facts its siblings. That reason has not changed.

*Alternative considered:* CSS grid on the `<ul>` with `display: contents` on
each `<li>`, to align columns across rows. Rejected — `display: contents`
removes the row's own box, which is the thing the markup exists to have, and its
accessibility behaviour across browsers is not something to bet a guarantee on.
The cost accepted is that columns do not align down the list; the marks are
optional per row (*stated only when true*), so a grid would need a placeholder
cell per absent mark, which is worse.

### 5. Optional facts stay stated-when-true; presentation carries the weight

No fact becomes conditional and no fact is dropped, on either page — including
the detail page's step identifier, which *A launch's detail page renders its
position and every served step* requires explicitly. What changes is weight:
identifier, discipline and provenance recede to the quiet ink; name, gate, date
and marks stay at reading weight.

The one removal is the list's raw product identifier on a **resolved** row,
which the capability never asked for. The detail page needs no such change: it
already names the launch by `label`, which is the identifier only on the
fallback path.

### 5a. Rules are scoped against the templates' reused class names

Both templates use one class name for two unrelated things. `finished` is the
revealed `<section>` (`launches.html:74`) **and** the mark on a revealed row
(`:88`). `gate` is a row's gate fact (`:62`) **and** an entry in the detail
page's gate sequence (`launch.html:25`). `launch-date` and `empty` each name
two things across the two pages.

One name escapes the launch surfaces entirely: `current` marks the gate
sequence's current entry (`launch.html:25`) **and** the header's current surface
(`_admin_header.html:43`), which every admin page renders. An unscoped
`.current` rule would restyle the header on all five surfaces — the widest blast
radius any rule in this change could have, from the shortest selector.

So an unscoped `.finished { background: … }` written for the section overrides
`.mark`'s background on the `Retired` / `Steady state` chip by source order —
quieting a fact the third requirement's negative obligation exists to protect.
Rules are therefore scoped by what they are for (`section.finished`,
`.launch-row .gate`, `.launches .launch-date`), and the delta states the
obligation rather than leaving it to inspection.

*Alternative considered:* rename the classes in the templates. Rejected for this
change — it touches markup the existing suites address, for a problem correct
scoping solves outright. Worth doing if the collisions grow.

### 6. The delta is ADDED, and this change archives after `add-launch-tracking-pages`

`MODIFIED` requires the existing requirement block to copy from
`openspec/specs/launch-admin/spec.md`, which does not exist. The three
requirements are genuinely new concerns over unchanged behaviour, which is what
ADDED is for. The ordering constraint is real and is a task, not a note:
archiving this change first would create the capability's main spec from three
presentation requirements referring to rules that are not there, and
`openspec validate` would not object — the same trap `add-launch-tracking-pages`
records for itself against `add-launch-journal`.

`add-launch-journal` does not exist as a change directory at all, so the chain's
release is indefinite. That does not block this change: `AGENTS.md` requires the
archive to be the last commit before a merge, and `add-launch-tracking-pages`
itself merged unarchived under exactly this constraint (PR #89). This change
merges the same way, and archives in order once the chain clears.

## Risks / Trade-offs

- **A shared stylesheet edit reaches the playbook and roster surfaces** → Every
  new rule is scoped to a class only the launch surfaces render; no `.html`
  outside the two launch templates renders any of `launches`, `step-row`,
  `gate`, `discipline`, `due`, `outcome`, `finished` or `empty`. The delta's
  scenario is written against the **served stylesheet's selectors**, not against
  the sibling surfaces' markup: a CSS-only change cannot alter that markup, so a
  scenario phrased at the markup level could not fail and would be a mitigation
  in name only.
- **A rule reaches a fact by accident within these surfaces** → The real
  collision risk is internal, not cross-surface. See Decision 5a.
- **`attention=` (empty) reaching the route where the checkbox sent nothing** →
  Read and found equivalent: the route strips the value and narrows on its
  truthiness, so empty and absent already agree, as they do for the gate select.
  The route is not touched; if this ever stops holding, the fix belongs in the
  template's option values, never in loosening the route.
- **The existing suites discover the narrowing from the page** → They read a
  `<select>`'s selected option and skip an unchecked checkbox, so the
  substitution should be absorbed. "Should" is why the full list and detail
  suites run before anything else is judged.
- **The journal region cannot be looked at** → `_detail_for` hard-codes
  `journal=()` / `journal_available=False` (`launch_admin.py:412`), and
  `read_journal` is `None` until `add-launch-journal` lands. So no journal entry
  renders, there is nothing to style and nothing to inspect. The journal is out
  of this change's region list; what the deployment check confirms is that the
  empty-journal statement reads correctly.
- **The claims that matter most cannot be tested** → "One line", "not wider than
  its word", "reads as a row" are inspection-only, as `playbook-admin` already
  concedes for the same vocabulary. Group 5 is the deployment check, and it is
  where this change is actually judged.
- **Archive order** → Stated as a task with the reason attached, because the
  failure is silent.

## Open Questions

None. The one question that would have changed the specs — what the row should
do with the raw identifier — was put to the admin who found it and answered:
render it only where the product cannot be resolved.
