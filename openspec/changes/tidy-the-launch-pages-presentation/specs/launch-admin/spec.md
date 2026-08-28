## ADDED Requirements

### Requirement: The list's narrowing is one bar of peer controls

The list's narrowing controls, and the control that reveals launches no longer
in play, SHALL be presented together as one bar of peer controls. Each control
SHALL be sized to its own content; none SHALL be rendered at the width of the
page's container.

The steps page implements this shape already, and it is adopted here for the
reason the deployed page demonstrated: the narrowing is the control an admin
reaches for most, and a stack of full-width form controls makes the page's
quietest job its loudest region. The submit control ran past half the viewport,
which is what a control that inherits its container's width does. No existing
requirement of `playbook-admin` states this shape — what that capability
records, and what is borrowed here, is the standard that a presentation
decision be carried by a marker a response can be asked for.

The reveal control SHALL lead the bar and SHALL NOT be the most prominent
control in it. It governs the same enumeration the narrowing form narrows
within, and as a paragraph of its own it read as an announcement. Placing it in
the bar is presentation only: it remains **not a narrowing** for every rule that
distinguishes an empty enumeration from a narrowing that matched nothing, and
this requirement changes none of them.

Because the two are presented as peers, they SHALL compose as peers. A
narrowing submitted while launches no longer in play are revealed SHALL leave
them revealed, narrowed within themselves and set apart, exactly as
*Narrowing the list changes what is shown, never what is enumerated* already
requires of a narrowing applied to that set. A bar whose two controls each
discard the other's state is a worse defect than the stack it replaces, because
it looks like one control.

The same holds for the offer to clear a narrowing that matched nothing. That
offer exists because the admin can undo what they just did; returning them to an
unrevealed default view undoes something else as well. Where that offer is made
while launches no longer in play are revealed, it SHALL clear the narrowing and
leave them revealed. This state is newly reachable from the bar, which is why it
is stated here rather than left as it was.

The presentation SHALL be observable in the rendered response — the bar carries
the marker `narrowing-bar`; the bar's **action** controls, which are its submit
and the reveal control, each carry `row-action`; and the reveal control carries
the further marker `quiet`. The controls that select a narrowing SHALL NOT carry
an action marker, which is what distinguishes them from the controls that act.
This is the standard `playbook-admin` holds for the same vocabulary in *A
step's actions are presented as one affordance vocabulary*, and the literal
tokens are given because they are what a test is derived from.

The markers are a necessary condition, not a sufficient one. They establish
that the vocabulary was applied; they cannot establish that the bar occupies one
line or that no control runs to the container's width, which no server response
can show. Those SHALL be confirmed by direct inspection of the rendered page.

Nothing in this requirement changes **what the narrowing selects** or which
narrowings are offered. Each narrowing SHALL stay requestable exactly as it is
today — the gate narrowing by the `gate` parameter, the needs-attention
narrowing by `attention=1` — so a URL naming a narrowing keeps its meaning. A
narrowing parameter that is present but empty SHALL narrow nothing, exactly as
an absent one does. That equivalence is not a new licence: it is how the
surface already reads both, and stating it is what makes a control that always
submits its name — which every `<select>` in a GET form does — a legitimate way
to offer a narrowing.

The bar SHALL render each active narrowing as the state of the control that
sets it, so that what the list is showing can be read from the bar. A control
that submits a narrowing it does not display leaves an admin unable to tell a
narrowed list from an unnarrowed one, and the next thing they submit silently
clears it.

#### Scenario: The narrowing renders as one marked bar

- **WHEN** the list is rendered
- **THEN** its narrowing controls and its reveal control are rendered within one element carrying `narrowing-bar`
- **AND** the bar's submit control and its reveal control each carry `row-action`

#### Scenario: The reveal control is distinguished, not amplified

- **WHEN** the list is rendered
- **THEN** the control that reveals launches no longer in play carries `quiet`
- **AND** no other control in the bar carries it

#### Scenario: A gate narrowing is requested as it was

- **WHEN** the list's narrowing is submitted selecting one gate
- **THEN** the request carries the same gate parameter the surface accepted before, and the same rows are narrowed to

#### Scenario: A needs-attention narrowing is requested as it was

- **WHEN** the list's narrowing is submitted selecting launches needing attention
- **THEN** the request carries `attention=1`, and exactly the launches needing attention are rendered

#### Scenario: An empty narrowing parameter narrows nothing

- **WHEN** the list is requested with its narrowing parameters present but empty
- **THEN** the rendered rows are those the list renders when the parameters are absent altogether

#### Scenario: The bar shows the narrowing it submitted

- **WHEN** the list is rendered under a gate narrowing and under the needs-attention narrowing
- **THEN** each narrowing is rendered as the selected state of the control that sets it

#### Scenario: A narrowing submitted from the bar keeps the reveal

- **WHEN** launches no longer in play are revealed, and a narrowing is then submitted from the bar
- **THEN** those launches are still revealed, narrowed within themselves and set apart from the rows in play

#### Scenario: Clearing a narrowing keeps the reveal

- **WHEN** launches no longer in play are revealed, a narrowing is applied that matches nothing in either set, and the offer to clear that narrowing is used
- **THEN** the narrowing is cleared and those launches are still revealed

#### Scenario: The reveal control still reveals

- **WHEN** the reveal control is used from the bar
- **THEN** launches no longer in play are rendered, marked and set apart, exactly as before

### Requirement: A row names its product, and falls back to the raw identifier only when it must

Where the catalog resolves a launch's product, the list's row SHALL name the
launch by that product and SHALL NOT render the raw product identifier as a
fact of its own beside it. Where the catalog cannot resolve the product, or
cannot be read at all, the row SHALL render the raw product identifier, which is
what this capability already requires and is the whole of what it requires it
for.

The identifier is opaque by `shared-vocabulary`'s own rule — generated, never
parsed for meaning — so on a resolved row it is 36 characters an admin can
neither read nor act on, sitting between the product's name and its gate. The
admin who first opened the deployed page asked what it was; that question is the
defect.

A row that falls back to the identifier SHALL render it **once**. The fallback
already names the launch by that identifier, so a row rendering it a second
time as a fact beside the name prints the same 36 characters twice on precisely
the row this requirement exists to make readable.

This constrains only what is **rendered as a fact**. The identifier stays in the
row's link target, which is how the page addresses a launch, and nothing here
changes which launch a row opens or how.

#### Scenario: A resolved product's row carries no raw identifier

- **WHEN** a launch is listed whose catalog product resolves to a name
- **THEN** its row names the product
- **AND** does not render the raw product identifier among the facts it shows

#### Scenario: A resolved product's row still opens its launch

- **WHEN** a launch is listed whose catalog product resolves to a name
- **THEN** its row still offers that launch's detail page in one action

#### Scenario: An unresolvable product's row still renders its identifier

- **WHEN** a launch is listed whose catalog product cannot be resolved
- **THEN** its row renders the raw product identifier, as the fallback requirement already obliges
- **AND** renders it once

#### Scenario: A wholesale identity outage still renders identifiers

- **WHEN** the list is rendered and product identities cannot be read at all
- **THEN** every row renders its raw product identifier

### Requirement: The shared vocabulary carries rules for what these surfaces render

The shared admin vocabulary SHALL carry presentation rules for the regions both
pages render — the list's rows and its revealed section, and the detail page's
gate sequence, gate groups and step rows — so that a row's facts are set apart
from one another rather than running together as one line of prose.

The pages are already required to take their presentation from that stylesheet
and to carry none of their own. That requirement is satisfied by a vocabulary
that reaches almost nothing either page renders, which is the state the surfaces
shipped in: of everything the two pages render, the vocabulary matches only
`mark`, `container` and `form.narrowing`, so a row's attention marks are legible
and every other fact on it is an unmarked run of text. Inheriting a vocabulary
that says nothing about you is not the guarantee the earlier requirement was
written to give.

Every fact either page renders today SHALL still be rendered. No rule SHALL
render any of them — or a container holding one — as not displayed, or as less
legible than the surface's ordinary text. This is the same negative obligation
`playbook-admin` states for a marked control's fault, stated here for the facts
these surfaces exist to show: a step's recorded provenance and a launch's
attention marks are what an admin opens the page for, and a presentation
decision that quiets one is a silent breach of the requirement that renders it.

This obligation binds a rule that reaches a fact **by accident** as much as one
aimed at it. Both pages reuse a class name for two unrelated things — the
revealed section and the mark on a revealed row, a row's gate and the gate
sequence's entries — so a rule written for a region and left unscoped will
reach a mark it was never meant to touch. One such name escapes these pages
altogether: the gate sequence marks its current entry `current`, which is also
how the shared header marks the surface being viewed, on **every** admin
surface. Rules SHALL be scoped so that this cannot happen, rather than left to
be caught by inspection.

The rules SHALL live in the shared stylesheet with every other admin rule, and
neither page SHALL gain styling of its own. No selector this change adds SHALL
match an element rendered by any other admin surface loading that stylesheet —
which today is the step list, the roster page, the product index and the product
dossier, and tomorrow is whatever is added next.

What can be read from a response is that the regions are marked, that no fact
was dropped or hidden, and which selectors the served stylesheet carries. The
selectors this change adds are those its own diff introduces to that stylesheet;
they are what the obligations above are read against. That a row reads as a row
SHALL be confirmed by direct inspection of the rendered page.

#### Scenario: The list's rows are marked as rows

- **WHEN** the list is rendered
- **THEN** each launch is rendered within one element carrying `launch-row`, holding every fact that row shows

#### Scenario: The detail page's rows are marked as rows

- **WHEN** a launch's detail page is rendered
- **THEN** each served step is rendered within one element carrying `step-row`, holding every fact that step shows

#### Scenario: No fact is lost to the vocabulary

- **WHEN** either page is rendered
- **THEN** every fact the capability requires that page to render is present in the response
- **AND** none of them, nor a container holding one, is rendered as not displayed

#### Scenario: The vocabulary carries a rule for each region

- **WHEN** the served stylesheet is read
- **THEN** it carries a rule reaching each of the list's rows, the list's revealed section, the detail page's gate sequence, its gate groups and its step rows

#### Scenario: No selector this change adds reaches another surface

- **WHEN** the served stylesheet is read
- **THEN** no selector this change adds matches an element rendered by the step list, the roster page, the product index or the product dossier

#### Scenario: A reused class name is never selected unqualified

- **WHEN** the served stylesheet is read
- **THEN** no selector this change adds selects `finished`, `gate`, `launch-date`, `empty` or `current` unqualified

### Requirement: The list names the completion recorded most recently

Each row SHALL name the step on that launch whose completion was recorded
most recently, and when it was recorded. A launch on which nothing has been
completed SHALL say so rather than rendering an empty cell: an empty cell reads
as a fact the page failed to fetch, and at the first gate having completed
nothing is the ordinary case.

"Most recently" is by **recording time**, not by the playbook's order. The two
disagree whenever a completion is backfilled — a step finished weeks ago but
recorded today leads, though later steps are already done — and the recording
reading is chosen because the column answers what most recently *happened* on a
launch, not how far along it has got. A list read for "where does this stand"
is read for recent activity.

Only a `Satisfied` outcome SHALL count. Every outcome is recorded with the same
provenance, so taking the latest recording of any outcome would let a step
recorded as blocked read as the launch's latest completion.

Where two completions carry the same recording time, the report's own order
SHALL break the tie — the authored order `launch-playbook` obliges — so the
column never orders itself by chance.

This fact comes from the launch report the list already reads. The page issues
no further read to obtain it, and no launch is enumerated, ordered or narrowed
differently for it.

#### Scenario: The most recently recorded completion is named

- **WHEN** a listed launch has two completed steps recorded at different times
- **THEN** its row names the one recorded later, and when it was recorded

#### Scenario: Recording time governs, not playbook order

- **WHEN** a listed launch has a completion recorded today for a step earlier in the playbook than one recorded last week
- **THEN** its row names the step recorded today

#### Scenario: Only a completion counts

- **WHEN** a listed launch's most recent recording is an outcome other than completion, over an earlier completion
- **THEN** its row names the earlier completion, not the more recent recording

#### Scenario: A launch with nothing completed says so

- **WHEN** a listed launch has no completed step
- **THEN** its row states that nothing has been completed, rather than rendering an empty cell

#### Scenario: The column does not change what is listed

- **WHEN** the list is rendered
- **THEN** the launches enumerated, their order and any active narrowing are what they would be without this column
