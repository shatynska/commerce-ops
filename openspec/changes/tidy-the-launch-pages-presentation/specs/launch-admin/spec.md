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
match an element rendered by any other admin surface loading that stylesheet,
**save for a rule whose declarations are custom properties only** — a block
that defines `--tokens` and sets no rendered property changes nothing on a
surface that never reads them, and the theme blocks every token in this
vocabulary is declared in are exactly that. The obligation is about what a
rule *renders*, not about what it matches —
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
SHALL break the tie, and the **latest** such step in that order SHALL win — the
authored order `launch-playbook` obliges, and naming the direction is what makes
this a rule rather than a preference. Same-instant ties are ordinary rather than
exotic: one automated pass records several outcomes at once.

Only `Satisfied` counts, which excludes the terminal outcomes `Refused` and
`NotApplicable` as well as the unresolved ones. That is deliberate: the column
answers what has been *completed*, and a step refused or ruled inapplicable was
resolved without being completed. A launch whose only resolved steps are those
therefore states that nothing has been completed, which is accurate rather than
a gap.

The row SHALL name the step by its **name**, never by its identifier — the
identifier is opaque, and this capability already keeps opaque identifiers off a
row that resolved. The recording time SHALL be rendered no coarser than the
minute and SHALL carry the zone it is read in, so that a time near a day
boundary cannot be read as the wrong day. The fact is drawn from the served step
set the report carries, so a completion recorded against a step since retired is
not named — the same boundary every other consumer of that report works within.

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

- **WHEN** a listed launch has one step completed earlier and a **different** step whose most recent recording is an outcome other than completion
- **THEN** its row names the completed step, not the more recently recorded one

*(Two steps, deliberately: re-recording a step replaces its stored outcome and
its provenance together, so one step cannot hold both an earlier completion and
a later non-completion.)*

#### Scenario: A tie is broken in a stated direction

- **WHEN** two of a launch's steps are completed and recorded at the same instant
- **THEN** its row names the later of the two in the report's order, on every rendering

#### Scenario: A launch with nothing completed says so

- **WHEN** a listed launch has no completed step
- **THEN** its row states that nothing has been completed, rather than rendering an empty cell

#### Scenario: The column does not change what is listed

- **WHEN** the list is rendered
- **THEN** the launches enumerated, their order and any active narrowing are what they would be without this column

### Requirement: A step's outcome is rendered as a tag carrying its state

The detail page SHALL render each step's outcome as a tag, and SHALL carry that
step's state on the element holding the step, so that what has been done on a
launch is readable by treatment before it is read by word. The states are the
outcome vocabulary `launch-playbook` owns, plus the distinct state of nothing
having been recorded at all.

A step recorded as not started and a step with no recorded outcome SHALL remain
distinguishable, which this capability already requires and which the treatment
must therefore carry rather than erase: the two SHALL differ in the words they
render **and** in the treatment their tag receives. A single grey shared by both
would satisfy neither.

The outcome vocabulary's members are class names — `NotStarted`, `InProgress` —
and SHALL be rendered as the words an admin uses rather than as those tokens. A
member the page does not know SHALL render under its own name rather than
disappearing: an unrecognised outcome is a fact, and a blank where one belongs
is the failure this surface exists to prevent.

The treatment SHALL be observable in the rendered response, and the literal
tokens are given because they are what a test is derived from, as this delta's
first requirement already does for the narrowing bar: the outcome's tag carries
the marker `outcome-tag`, and the element holding the step carries `state-`
followed by the outcome's own name lowercased — `state-satisfied`,
`state-blocked` — with a step carrying no recorded outcome carrying
`state-unrecorded`. That last is the marker the distinction above rests on: the
two states carry different markers, and never one shared marker.

Every fact the capability requires the detail page to render about a step SHALL
still be rendered — its name, its identifier, its owning discipline, whether it
blocks, its due period, whether it is overdue, its recorded outcome and that
recording's provenance. This requirement re-lays them out; it removes none, and
the capability's own list governs rather than any shorter list restated here.
Evidence written
by an automated handler runs to several sentences, and SHALL be laid out within
a bounded measure rather than across the page's full width, and SHALL NOT be
truncated: an ellipsis on the one field explaining why a step was refused
suppresses exactly the fact a reader came for.

The recording time MAY be rendered at a coarser precision than it is stored, and
SHALL be rendered no coarser than the minute and SHALL carry the zone it is read
in. Dropping microseconds loses nothing a reader wanted; dropping the zone
changes which day an instant near a boundary belongs to, which is a fact and not
a precision. The permission is bounded here because unbounded it licenses a year.

The marks a launch carries SHALL name what they are about. "Awaiting
confirmation" is a fact about the launch's current **gate** — `launch-instance`
holds it true even after a *rejecting* decision, since a rejection leaves the
gate still waiting on one — and read bare beside a step recorded `Blocked` it
was reported as a contradiction by the admin who first read it. It is not one;
the two are different facts about different things, and the wording SHALL say
whose. The same holds for the launch date's own mark.

What can be read from a response is the markers, the words, and that no fact was
dropped. That the tag and the edge are legible, that the measure is bounded, and
that a gate can be read at a glance SHALL be confirmed by direct inspection of
the rendered page.

#### Scenario: An outcome renders as a tag carrying its state

- **WHEN** a launch's detail page renders a step with a recorded outcome
- **THEN** the outcome is rendered within an element carrying `outcome-tag`
- **AND** the element holding that step carries `state-` followed by the outcome's own name lowercased

#### Scenario: Unrecorded stays distinguishable from not started

- **WHEN** a detail page renders a step recorded as not started and a step with nothing recorded
- **THEN** the two render different words
- **AND** the first carries `state-notstarted` while the second carries `state-unrecorded`

#### Scenario: A mark names what it is about

- **WHEN** the list renders a launch whose gate awaits confirmation and whose date is at risk
- **THEN** each mark names the thing it is a fact about, rather than naming the state alone

#### Scenario: A recording time keeps its zone

- **WHEN** either page renders the time an outcome was recorded
- **THEN** that time is rendered no coarser than the minute and carries the zone it is read in

#### Scenario: An outcome renders as words, not as its token

- **WHEN** a detail page renders a step whose outcome is `NotStarted`
- **THEN** the rendered outcome reads as words rather than as the vocabulary's token

#### Scenario: An unknown outcome still renders

- **WHEN** the page is asked to render an outcome for which it holds no wording
- **THEN** the outcome is rendered under its own name rather than omitted

*(The vocabulary is closed at six members, so this case is not reachable through
the domain today. It is stated as an obligation on the page's own mapping —
exercised at the mapping, not through a launch — because the day it becomes
reachable is the day a member is added, and a blank where an outcome belongs is
the failure this surface exists to prevent.)*

#### Scenario: Long evidence is bounded, not truncated

- **WHEN** a detail page renders a step whose evidence runs to several sentences
- **THEN** the whole of that evidence is present in the response

### Requirement: A launch's detail page offers the way back to the list

The detail page SHALL offer the launch list in one action, without scripting.

The header does not serve this today and is not obliged to. Both pages are
required to identify the launch surface as the one being viewed, so the header
renders `Launches` as a position rather than as a link — and the requirement
that the header make *the other* admin surfaces reachable says nothing about the
list an admin arrived from, because the list is the same surface. Nothing
therefore obliged a way back, and there was none. Whether a header entry could
also link to its own surface's index is a template question this requirement
does not settle; what it settles is that the page offers the list.

The offer SHALL reach the list as the list renders with no narrowing and nothing
revealed. Carrying the reader's narrowing back is a defensible alternative and
is deliberately not chosen: an admin leaving a launch is leaving the narrowing
that found it as often as not, and a control that silently restores a filter is
harder to understand than one that plainly returns.

#### Scenario: The list is reachable from a launch's detail page

- **WHEN** a launch's detail page is rendered
- **THEN** it offers the launch list in one action, without scripting

### Requirement: The gate a reader navigated to is distinct from the gate the launch stands at

The gate sequence SHALL distinguish the gate the launch stands at from a gate
the reader has merely navigated to. Every entry in the sequence is an anchor into
its own gate's steps, so following one moves the page without moving the launch;
marking only the current gate leaves that mark reading as "the entry you
selected" when the two differ, which is how the admin who first read the page
read it.

This is a **stylesheet** obligation and is stated as one. Which entry a reader
followed is a URL fragment, and a fragment is never sent to a server: the
response is identical whichever entry was followed, so no scenario over a
response can observe it. What a response *can* carry is the stylesheet it loads,
and that is where the obligation is placed — the served stylesheet SHALL carry a
rule for the navigated-to gate group distinct from the rule marking the current
gate. That the two read as different at a glance SHALL be confirmed by direct
inspection of the rendered page.

#### Scenario: The stylesheet distinguishes the two

- **WHEN** the served stylesheet is read
- **THEN** it carries a rule that applies to the gate group a reader has navigated to
- **AND** that rule is distinct from the one marking the gate the launch stands at
