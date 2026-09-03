# launch-admin Specification

## Purpose
The launch-tracking surface: lets a signed-in admin see every product in
launch at once — where each stands in the gate sequence, whether its date
is at risk and whether it waits on a member — and open one launch to read
its steps, their recorded outcomes and its journal. It reports what the
launch context already holds and changes none of it.

## Requirements

### Requirement: The launch list enumerates every launch and renders those in play

The list SHALL enumerate every persisted launch position the caller's
access scope permits. Which of those launches are rendered is governed by
the default-view rule below; each row that is rendered SHALL name the
product, the launch's current gate, its launch date or the absence of
one, whether its date is at risk, and whether its current gate awaits
confirmation.

Each rendered row SHALL offer that launch's detail page in one action.
Reachability SHALL NOT depend on scripting, and SHALL NOT depend on how
many rows are shown or on any active narrowing — the guarantee
`playbook-admin` already carries for its own controls, and for the same
reason: this list is unbounded until pagination is answered, and a detail
page reachable only by typing a URL is one nobody reaches.

The scope SHALL be the one resolved for the session's own principal
identity, never a fixed or unrestricted scope the surface supplies for
itself. Every admin-capable principal resolves to an unrestricted scope
today, so the two are indistinguishable by observation now and would
diverge silently the moment product-level scoping exists, which is
exactly the failure a surface naming its own scope would ship.

The at-risk and awaits-confirmation states SHALL be evaluated as of the
date the page is rendered. Both are derived as of a caller-supplied date,
so a surface leaving it unstated would render a defensible page and an
indefensible one from the same code.

A launch whose catalog
product's lifecycle stage is steady-state or retired SHALL NOT appear in
the default view, but SHALL be reachable through an explicit control that
shows it marked as no longer in play — The predicate is `briefing`'s own
definition of a launch that is no longer active, adopted rather than
restated so two capabilities cannot drift on what counts as in play. The
shape is `playbook-admin`'s for retired steps, and holds for the same
reason: a set that only grows answers
"what is in play" worse every month, while deleting the answer outright
loses a record someone eventually wants.

Where no enumerated launch is out of play, the control SHALL say so when
used rather than revealing an empty section unannounced.

The mark SHALL distinguish a launch whose product is in steady state
from one whose product was retired, and SHALL derive from that stage
rather than from the launch's own gate — the stage is the observable the
filter uses, and a product may reach steady state without this launch
having graduated. A product may be retired from any stage, so this
control also holds launches abandoned in flight, and filing an abandoned
launch under a word that says it finished would hide the one launch a
reader is most likely hunting for.

A launch whose product the catalog cannot resolve SHALL be rendered in
the default view. The filter fails toward showing, never toward silence,
which is `briefing`'s rule for the same judgement on the same data.

This does not hide a launch awaiting its graduation approval.
`launch-instance` stamps the product steady-state only **after** the
graduating advance is persisted, so a launch standing at the last gate
with its approval outstanding still has a launching product and still
appears — which is the case with the most claim on someone's attention.

The enumeration itself stays unfiltered, and that is not a contradiction:
`launch-instance` enumerates without a lifecycle filter deliberately — because the launch context does
not own a product's stage — and the same sentence directs whoever
consumes the enumeration to filter by the catalog's stage stamp. This
surface is that consumer, and it already reads the stamp: the product
identities it resolves carry each product's current lifecycle stage.
Narrowing what is shown while enumerating everything is exactly what this
capability requires of every other narrowing.

An enumeration yielding nothing SHALL render the page saying so. It is
not an error and not an absent page: "no product is in launch" is an
answer, and one an admin may need to trust.

A default view emptied **by the filter**, every enumerated launch being
no longer in play, SHALL say that instead, and SHALL offer the control
that reveals them. Where a narrowing is also active, the narrowing's own
empty state SHALL govern: it names something the admin just did and can
undo, which is the more actionable of the two. The control that reveals
launches no longer in play is not a narrowing for any of these rules. It is a third state, distinct from an empty
enumeration and from a narrowing that matched nothing, and R3's reasoning
applies to it unchanged: the three answer different questions and an
admin acts differently on each.

A read of product identities that fails **entirely** SHALL render every
row by its raw product identifier, rather than failing the page. The
per-product rule above is not enough on its own: the outage that takes
the whole read down is exactly the moment someone opens this page to ask
where things stand, and a surface that answers that question with an
error is worse than one that answers it with identifiers.

#### Scenario: Every permitted launch is listed

- **WHEN** several launch positions exist whose products are in launching stages, and the list is opened with no narrowing under a scope permitting all of them
- **THEN** each is rendered as its own row, naming its product, current gate, launch date, at-risk state and awaiting-confirmation state

#### Scenario: The list is evaluated as of the day it is rendered

- **WHEN** the list is rendered on two dates, between which a launch's blocking step passes its due period unresolved
- **THEN** that launch is not marked at risk on the earlier rendering and is marked at risk on the later one

#### Scenario: A row opens its launch

- **WHEN** the list is rendered
- **THEN** each row offers that launch's detail page in one action, without scripting

#### Scenario: A row opens its launch however many are shown

- **WHEN** the list is rendered under a narrowing, and again with none
- **THEN** every rendered row offers its detail page in one action in both cases

#### Scenario: A restricted scope lists only its launches

- **WHEN** the list is opened under a scope permitting some products but not others
- **THEN** exactly the permitted products' launches are rendered

*(No principal resolves to such a scope today — `access-scope` resolves
every active member unrestricted — so this scenario is exercised
with the **scope resolver alone** stubbed to return a restricted scope,
the real enumeration behind it, asserting the rows actually rendered.
Stubbing further and asserting only that the surface passed the scope on
would establish something weaker than this scenario states; asserting it
where a scope is constructed directly would test the use case, which is
not what this requirement constrains.)*

#### Scenario: A launch with no date renders the absence

- **WHEN** a listed launch has no launch date
- **THEN** its row states that it has none, rather than rendering an empty or defaulted date

#### Scenario: A finished launch leaves the default view

- **WHEN** the list is opened with no narrowing and a launch's catalog product is in a steady-state or retired stage
- **THEN** that launch is not rendered

#### Scenario: A finished launch stays reachable

- **WHEN** the control that shows launches no longer in play is used, and one launch's product is in steady state while another's is retired
- **THEN** both are rendered, each marked, and the two marks differ

#### Scenario: Revealing when nothing is out of play says so

- **WHEN** the control that reveals launches no longer in play is used and every enumerated launch is in play
- **THEN** the page says there are none, rather than revealing an empty section

#### Scenario: An unresolvable product's launch stays in the default view

- **WHEN** the list is opened with no narrowing and a launch's catalog product cannot be resolved
- **THEN** that launch is rendered

#### Scenario: A launch at the final gate is still listed

- **WHEN** a launch stands at the last gate of the sequence with its graduation approval outstanding, so its product is not yet steady-state
- **THEN** it is rendered in the default view like any other launch

#### Scenario: Product identities cannot be read at all

- **WHEN** the list is rendered and product identities cannot be read at all
- **THEN** every row is rendered, each identified by its raw product identifier

#### Scenario: A launch whose product cannot be resolved is still listed

- **WHEN** a launch position exists whose product identity cannot be resolved
- **THEN** its row is rendered, identified by its raw product identifier

#### Scenario: No launches renders a page, not an error

- **WHEN** the list is opened and no launch position the caller may see exists
- **THEN** the page is rendered and states that no product is in launch

#### Scenario: A narrowing's empty state governs when both apply

- **WHEN** every enumerated launch is no longer in play and a narrowing is also active
- **THEN** the page reports the narrowing as having matched nothing and offers to clear it, rather than reporting the filter-emptied state

#### Scenario: A default view emptied by the filter says which state it is in

- **WHEN** the list is opened with no narrowing and every enumerated launch is no longer in play
- **THEN** the page states that no launch is in play and offers the control that reveals the others
- **AND** says so distinguishably from the page rendered when no launch position exists at all

### Requirement: The list is ordered by attention, deterministically

Rows SHALL be ordered so that launches whose date is at risk come first,
then launches whose current gate awaits confirmation, then the rest. A
launch matching both SHALL appear once, in the first band — the band order is
`briefing`'s own cause ranking, which grades an at-risk date above a gate
awaiting confirmation. The single appearance is not `briefing`'s rule and
is not claimed to be: that context emits both items for one product, and
what forces one row here is this capability's own requirement of one row
per launch.

The bands hold only launches in play. Rows revealed by the control that
shows launches no longer in play SHALL be rendered set apart from them,
ordered by launch date with the most recent first, undated last and ties
broken by product identifier, and SHALL NOT be interleaved into the
bands. That is the companion half of the shape
`playbook-admin` uses, whose retired steps are "not interleaved with the
served set", and without it a graduated launch could outrank a live one:
authoring a new active blocking step gives every launch an unresolved
step with a past due period, so `launch-instance` reports even graduated
launches at risk.

Within a band, rows SHALL be ordered by launch date with the earliest
first, launches with no date last, and ties broken by product
identifier. No ordering this requirement states, in a band or among the
revealed rows, SHALL depend on how the underlying enumeration happens to
arrive: two renders over the same launches SHALL agree even
where the enumeration hands them over in a different order.

Naming the key is what makes that testable. "Deterministic and stable"
alone is satisfied by a stable sort over arrival order, which is the very
thing the sentence exists to forbid.

#### Scenario: An at-risk launch precedes one awaiting confirmation

- **WHEN** the list holds a launch whose date is at risk and a launch whose current gate awaits confirmation
- **THEN** the at-risk launch is rendered first

#### Scenario: Revealed rows order most recent first

- **WHEN** launches no longer in play are revealed, holding two with launch dates and one with none
- **THEN** the dated ones are rendered most recent first, and the undated one last

#### Scenario: Launches no longer in play stand outside the bands

- **WHEN** the control revealing launches no longer in play is used, and one of them is reported at risk
- **THEN** it is rendered set apart from the launches in play, not among the at-risk band

#### Scenario: A launch in both bands appears once

- **WHEN** a launch's date is at risk and its current gate also awaits confirmation
- **THEN** it is rendered exactly once, among the at-risk launches

#### Scenario: Unchanged data renders in the same order

- **WHEN** the list is rendered twice over the same launches with nothing changed between
- **THEN** the rows appear in the same order both times

#### Scenario: Arrival order does not reach the page

- **WHEN** two launches in the same attention band are enumerated in one order, and then in the opposite order with nothing else changed
- **THEN** the rows appear in the same order both times, earliest launch date first

#### Scenario: A launch with no date sorts last within its band

- **WHEN** a band holds a launch with a launch date and a launch without one
- **THEN** the dated launch is rendered first

### Requirement: Narrowing the list changes what is shown, never what is enumerated

The list SHALL be narrowable by gate and by whether a launch needs
attention. An active narrowing SHALL change only which of the enumerated
rows are rendered — never which launches are enumerated, and never their
relative order among those that remain.

A narrowing SHALL apply to the revealed rows as it applies to the rows in
play, narrowing each set within itself and leaving them set apart. A
launch no longer in play can still be reported at risk, so a
needs-attention narrowing that silently skipped the revealed set would
answer its own question wrongly.

A narrowing that matches nothing SHALL say so and offer to clear itself,
rather than rendering as an empty list indistinguishable from having no
launches at all. The two states answer different questions and an admin
acts differently on each.

#### Scenario: A gate narrowing hides without removing

- **WHEN** the list is narrowed to one gate
- **THEN** only launches at that gate are rendered, and the launches enumerated are unchanged

#### Scenario: A narrowing reaches the revealed rows too

- **WHEN** launches no longer in play are revealed and a narrowing is applied
- **THEN** the narrowing applies to those rows as it does to the rows in play, and the two sets stay set apart

#### Scenario: Narrowing to launches needing attention

- **WHEN** the list is narrowed to launches needing attention
- **THEN** only launches whose date is at risk or whose current gate awaits confirmation are rendered

#### Scenario: Narrowing preserves the attention order

- **WHEN** a narrowing is applied to a list holding launches in more than one attention band
- **THEN** the rendered rows keep the same relative order they had unnarrowed

#### Scenario: A narrowing matching nothing says so

- **WHEN** a narrowing matches no launch
- **THEN** the page says the narrowing matched nothing and offers to clear it, distinguishably from the page rendered when no launch exists

### Requirement: A launch's detail page renders its position and every served step

The detail page SHALL render the gate sequence in its order, identifying
which gate the launch currently stands at, and SHALL render every step
the served playbook holds, each with its name, its identifier, its owning
discipline, whether it blocks, its recorded outcome where one exists, the
provenance of that recording, its due period where the launch's date
yields one, and whether it is overdue.

A step with no recorded outcome SHALL be rendered as unrecorded, distinct
from one recorded as not started. Nothing having been recorded and
something having been recorded as "not started" are different facts, and
only the second carries a provenance naming who said so.

The page SHALL name the launch's product. Where the catalog cannot
resolve it, or cannot be read at all, the page SHALL identify the launch
by its raw product identifier and render everything else unchanged — the
same trade the list makes, for the same reason, and stated here because a
rule recorded only for the list is a rule the detail page does not have.

Steps SHALL be grouped by the gate they belong to, in the gate
sequence's order, and the group holding the launch's current gate SHALL
be the page's own landing position. An ungrouped list is unusable at the
size the served step set reaches, and a page opening anywhere other than
where the launch stands would make its most-read fact the hardest to
find.

Within each gate, steps SHALL be rendered in the authored order that
gate's steps carry, which `launch-playbook` obliges every consumer that
lists a gate's steps to follow, and which this change requires the
report's entries to arrive in. Rendering a gate's steps in whatever order
they arrive is the failure the list's own ordering rule already forbids,
for the same reason.

The gate each step belongs to, and the gate sequence itself, SHALL come
from the launch report, which this change requires to carry both. The
page reads no playbook: that is the arrangement the three other report
facts here exist to preserve, and grouping would otherwise be the one
place it broke.

The overdue judgement, and every other fact the report derives from a
date, SHALL be evaluated as of the date the page is rendered — the same
obligation the list carries, for the same reason: a surface leaving it
unstated would render a defensible page and an indefensible one from the
same code.

The overdue judgement SHALL be taken from the launch report rather than
derived on the page: whether a step is overdue depends on the terminal
outcomes its hazard permits, and this change adds the `launch-instance`
requirement that carries it on the report for exactly this reason.

Where the served playbook holds no step at all, the page SHALL render the
gate sequence and say that no step is served, rather than rendering gate
groups that are silently empty.

A recorded outcome for a step the served playbook no longer holds SHALL
NOT be rendered, and this is a deliberate boundary rather than an
oversight. Such outcomes remain stored and readable by `launch-instance`,
but the launch report is built from the served step set and does not
carry them, so rendering them would require a read this surface does not
have. What the page shows is the launch against the playbook as it now
stands.

#### Scenario: The page names its product

- **WHEN** a launch's detail page is opened
- **THEN** it names the launch's product

#### Scenario: An unresolvable product falls back to its identifier

- **WHEN** a launch's detail page is opened and the catalog cannot resolve its product
- **THEN** the page identifies the launch by its raw product identifier and renders the rest unchanged

#### Scenario: The gate sequence shows the launch's position

- **WHEN** a launch's detail page is opened
- **THEN** every gate of the sequence is rendered in order and the launch's current gate is identified among them

#### Scenario: A launch whose playbook serves no step says so

- **WHEN** a launch's detail page is opened and the served playbook holds no step
- **THEN** the gate sequence is rendered and the page states that no step is served

#### Scenario: Steps are grouped by gate and the page lands on the current one

- **WHEN** a launch's detail page is opened and its steps span several gates
- **THEN** the steps are rendered grouped by their gate in the gate sequence's order
- **AND** within each gate they stand in that gate's authored order
- **AND** the group holding the launch's current gate is the page's landing position

#### Scenario: A step renders its name, not only its identifier

- **WHEN** a launch's detail page is opened
- **THEN** each step is rendered with the name the served playbook gives it

#### Scenario: A recorded step renders its provenance

- **WHEN** a step has a recorded outcome
- **THEN** the page renders that outcome together with who recorded it, when, from what source, and the evidence given

#### Scenario: An unrecorded step is distinct from one recorded not-started

- **WHEN** one step has no recorded outcome and another is recorded as not started
- **THEN** the two are rendered distinguishably

#### Scenario: A step renders its discipline, whether it blocks, and its due period

- **WHEN** a launch with a launch date has its detail page opened
- **THEN** each step renders the discipline it is owned by, whether it blocks its gate, and the due period the launch date yields for it

#### Scenario: The page is evaluated as of the day it is rendered

- **WHEN** the same launch's detail page is rendered on two dates, between which a step's due period fully passes with the step unresolved
- **THEN** the step is not marked overdue on the earlier rendering and is marked overdue on the later one

#### Scenario: A step the report does not mark overdue is not rendered overdue

- **WHEN** a step whose hazard permits only `Refused` has reached `Refused`, its due period has fully passed, and the report does not mark it overdue
- **THEN** the page does not render it as overdue

#### Scenario: An overdue step is marked

- **WHEN** the launch report marks a step overdue
- **THEN** the page renders it as overdue

### Requirement: Both surfaces are read-only

Neither the list, the detail page, nor the launch's journal page SHALL
offer any control that changes launch state. Approving a gate, accepting
or rejecting an automated result, recording an outcome and moving a
launch date SHALL remain reachable only by the paths that already serve
them.

Stated as a requirement rather than left as an omission: these pages
render an admin's own launches beside controls they are used to acting
through elsewhere, and "there is deliberately nothing to press here" is
the guarantee that makes the surface safe to open on a live launch. The
journal page inherits the guarantee rather than earning it separately —
it renders the same append-only record the detail page rendered before
this change moved it, and moving where a record is shown does not make
it writable.

#### Scenario: The pages present no launch-changing control

- **WHEN** any of the list, the detail page, or the journal page is rendered for a launch in any state
- **THEN** it offers no control that records an outcome, approves a gate, decides an automated result, or moves a launch date

### Requirement: A launch the caller may not see is indistinguishable from one that does not exist

A detail page or a journal page requested for an identifier with no
launch position, for one the caller's scope does not permit, and for an
identifier naming nothing the system knows SHALL each be refused
identically, in the same shape as a request for a route that does not
exist.

The refusal turns on the **launch position**, never on whether the
catalog can name the product. A launch position whose product the catalog
cannot resolve SHALL be served, not refused: the list renders that launch
by its raw identifier and offers its detail page in one action, so
refusing it here would put a dead end behind a row this capability
deliberately keeps visible — and during a catalog outage it would put one
behind every row. The journal page resolves the same launch position the
detail page does, so it is served or refused by the identical rule.

`launch-instance` already reports absence and refusal identically on the
read itself, so that a caller cannot confirm the existence of a launch
they may not see. A surface that answered the three differently would
give back exactly what that read withholds.

#### Scenario: A product with no launch is refused as absent

- **WHEN** a detail page or a journal page is requested for a product that has no launch position
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: A forbidden launch is refused identically

- **WHEN** a detail page or a journal page is requested for a launch the caller's scope does not permit
- **THEN** the response is identical in shape to the one given for a product with no launch

*(Unreachable end to end for the same reason, and covered the same way:
the scope resolver alone is stubbed, and the response is asserted against
the one given for a product with no launch.)*

#### Scenario: A launch whose product cannot be resolved is served

- **WHEN** a detail page is requested for a launch position whose product the catalog cannot resolve
- **THEN** the page is served, identifying the launch by its raw product identifier

#### Scenario: An unknown identifier is refused identically

- **WHEN** a detail page or a journal page is requested for an identifier with no launch position and no catalog product
- **THEN** the response is identical in shape to the other two refusals

### Requirement: Both surfaces ride the admin session and carry the shared header

Every route of the list, the detail page and the journal page SHALL
require a valid admin session and SHALL refuse a request without one in
the same absence-shaped way every other admin route does. All three
SHALL carry the header the other admin surfaces carry, identifying the
launch surface as the one being viewed, and from each the other admin
surfaces SHALL be reachable in one action without scripting.

The header identifies the surface a caller is *within*; the breadcrumb
trail beside each page's title identifies the specific launch and page
within it. The two are not the same control and this requirement does
not merge them — the header's job is switching between admin surfaces,
the breadcrumb's is moving within this one.

#### Scenario: A request without a session is refused as absent

- **WHEN** any of the three pages is requested with no admin session, or with one that has expired
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: The header names the other surfaces

- **WHEN** any of the three pages is rendered
- **THEN** its header identifies the launch surface as the one being viewed and offers the other admin surfaces in one action

### Requirement: The pages' presentation comes from the shared admin vocabulary

The list, the detail page and the journal page SHALL come from the same
stylesheet the other admin surfaces load, rather than from styling
carried in the pages themselves, so that a change to the vocabulary
reaches every admin surface rather than some of them.

`members-admin` already requires this of itself, and records why: a page
carrying its own styling is why two surfaces an admin moves between look
like two products, and — more to the point — why a presentation fix
applied to one silently does not apply to the other, a divergence nothing
in the repository reveals. The journal page, introduced by this change,
is bound by the same requirement rather than being free to invent its own
styling.

The pages SHALL reach that stylesheet through a route no single admin
surface owns, on the same terms every other surface reaches it, and SHALL
NOT reach it through a route belonging to the module that owns another
admin surface.

#### Scenario: The pages carry no styling of their own

- **WHEN** any of the three pages is rendered
- **THEN** its presentation comes from the shared admin stylesheet, and the page carries no styling of its own

#### Scenario: The stylesheet is not reached through another surface's route

- **WHEN** any of the three pages is rendered
- **THEN** the stylesheet it loads is served by a route no single admin surface owns

#### Scenario: A vocabulary change reaches these pages

- **WHEN** the shared admin stylesheet changes
- **THEN** all three pages render under the changed vocabulary without any of them being edited

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
which today is the step list, the Team page, the product index and the product
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
- **THEN** no selector this change adds matches an element rendered by the step list, the Team page, the product index or the product dossier

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

The detail page SHALL carry a breadcrumb trail naming the launch list as
a link and the launch itself as the current, un-linked, segment — the
current segment rendered as the page's own title, so the page carries no
separate title beside it. Following the list link SHALL reach the list
in one action, without scripting.

The header does not serve this today and is not obliged to. Both pages are
required to identify the launch surface as the one being viewed, so the header
renders `Launches` as a position rather than as a link — and the requirement
that the header make *the other* admin surfaces reachable says nothing about the
list an admin arrived from, because the list is the same surface. Nothing
therefore obliged a way back, and there was none. Whether a header entry could
also link to its own surface's index is a template question this requirement
does not settle; what it settles is that the page offers the list.

The link SHALL reach the list as the list renders with no narrowing and nothing
revealed. Carrying the reader's narrowing back is a defensible alternative and
is deliberately not chosen: an admin leaving a launch is leaving the narrowing
that found it as often as not, and a control that silently restores a filter is
harder to understand than one that plainly returns.

#### Scenario: The list is reachable from a launch's detail page

- **WHEN** a launch's detail page is rendered
- **THEN** its breadcrumb trail offers the launch list in one action, without scripting
- **AND** the trail's last segment names the launch and is not a link

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

### Requirement: A launch's detail page offers its journal in one action

The detail page SHALL offer the launch's journal page in one action,
without scripting, in a region beside the page's title reserved for the
page's own descendants. A launch whose journal holds nothing SHALL still
offer the journal page — the journal page itself, not the detail page,
is what states there is nothing recorded.

#### Scenario: The journal is reachable from a launch's detail page

- **WHEN** a launch's detail page is rendered
- **THEN** it offers that launch's journal page in one action, without scripting

#### Scenario: An empty journal is still reachable

- **WHEN** a launch's detail page is rendered for a launch whose journal holds no entry
- **THEN** the detail page still offers the journal page in one action

### Requirement: A launch's journal page carries a breadcrumb to the list and to its launch

The journal page SHALL carry a breadcrumb trail naming, in order, the
launch list and the launch itself, each as a link, with the journal page
named last as the current, un-linked, segment — rendered as the page's
own title, so the page carries no separate title beside it. The list
link SHALL reach the list as it renders with no narrowing and nothing
revealed, for the reason the detail page's own list link does. The
launch link SHALL reach that launch's detail page.

#### Scenario: Both ancestors are reachable from the journal page

- **WHEN** a launch's journal page is rendered
- **THEN** its breadcrumb trail offers the launch list and that launch's detail page, each in one action
- **AND** the trail's last segment names the journal and is not a link

### Requirement: A launch's detail page distinguishes a step that has not started

A launch's detail page SHALL render every served step whether or not the launch has released it, and SHALL distinguish those it has not released. Hiding them is forbidden: the page exists to show the launch's whole plan against its position, and a page showing less than the playbook would misrepresent what the launch is committed to.

An unreleased step SHALL carry a mark saying what it is waiting for — the gate it starts at, the steps it waits on, or both — so that a reader can tell a step nobody has begun from a step nobody *may yet* begin. The two are different facts about the launch and the surface SHALL NOT collapse them: a step that is unrecorded and released is work outstanding, and a step that is unrecorded and unreleased is work not yet asked for.

The mark's wording SHALL be drawn from *starting*, and SHALL NOT use *blocked* or any inflection of it. This surface already renders a step's `blocking` declaration and the `Blocked` step outcome, which are two distinct senses of the word on one page; a third would make the page unreadable. A step's own gate and its start gate SHALL likewise be worded so that neither can be read as the other.

A step whose start gate the launch has not reached SHALL NOT be marked overdue. The page SHALL NOT reach that conclusion itself: the overdue judgement is taken from the launch report, as this capability already requires, and `launch-instance` carries the rule. Stated here as what the page renders rather than as what it decides — a surface suppressing the mark on its own would leave the page, the report and the daily briefing saying different things about one step, which is the arrangement carrying the fact on the report exists to prevent.

A step the launch has reached but which waits on an unresolved dependency MAY be both marked overdue and marked as waiting, and the page SHALL render both rather than letting either suppress the other. The two say different things — the work is late, and this is what it is late behind — and a reader needs them together.

#### Scenario: An unreleased step is rendered, not hidden

- **WHEN** a launch standing at `commit` is rendered and its served playbook carries steps that start at `listable`
- **THEN** those steps appear on the page under their own gates

#### Scenario: An unreleased step says what it waits for

- **WHEN** a step the launch has not released is rendered
- **THEN** it carries a mark naming the gate it starts at, the steps it waits on, or both

#### Scenario: Unreleased is distinguishable from unrecorded

- **WHEN** a page renders one released step with no recorded outcome and one unreleased step with no recorded outcome
- **THEN** the two are distinguishable from one another on the page

#### Scenario: A released step carries no such mark

- **WHEN** a step the launch has released is rendered
- **THEN** it carries no start mark, whatever it declares

#### Scenario: A step whose start gate is not reached is never marked overdue

- **WHEN** a step whose start gate the launch has not reached has a due period that has passed
- **THEN** it is not marked overdue, the launch report not stating it as overdue

#### Scenario: A step waiting on a dependency can be both overdue and waiting

- **WHEN** a step the launch has reached waits on an unresolved dependency and the report states it as overdue
- **THEN** the page renders both the overdue mark and the mark naming what it waits for

#### Scenario: The page carries no third sense of blocked

- **WHEN** the detail page is rendered for a launch with unreleased steps
- **THEN** no mark introduced for release uses the word *blocked* or an inflection of it

### Requirement: A launch's journal page renders every entry as a row, newest first

The journal page SHALL render the launch's journal as a table, with the
most recent entry first, a row for each entry carrying when it
occurred, its label, a gate/step, its source, who recorded it, and a
detail — when leading the row, since a journal is read by when
something happened before it is read by what happened.
The gate/step column SHALL carry the entry's subject where that subject
names a gate or a step, and SHALL be empty otherwise. Detail is
this page's own composed phrase, built from `launch-journal`'s per-kind
fact fields (`playbook_version`, `outcome`, `reason`, `evidence`,
`decision`, `posture`, `standing_at`, `previous_date`,
`new_date`, `unsatisfied`) — the page tried a
column per fact, then two columns, and settled on one short readable
phrase per entry, the shape closest to how a reader actually wants to
scan a kind-specific fact. The phrase SHALL NOT restate a subject that
already has its own gate/step column.

Every journal kind now names either a gate or a step as its subject, so
the gate/step column is empty only where an occurrence names no subject
at all. A metric obligation reaches this page as an ordinary step, its
threshold being the step's own description, and needs no exception to
the columns' meaning.

Where an entry's `actor` matches a member the membership carries — by that
member's member identifier or by their ClickUp user id — the page
SHALL render the member's name rather than the raw identifier; where
it matches neither, the page SHALL render the raw value rather than
omitting it or failing.

Where an entry carries no source, the page SHALL render its source
column as `system` rather than as an absence — `system` names that no
channel was recorded for the occurrence, independently of whether the
entry names an actor: a graduating entry carries a known approver and
still no recorded source, and SHALL still read `system` in that column
without implying the approver is unknown, since `who` renders that
fact in its own column regardless.

The presentation SHALL be observable in the rendered response, and
SHALL match the visual vocabulary the detail page's own step table
uses for the same purpose (`kind-tag`/`outcome-tag`'s shared shape;
row height and font size inherited from the site-wide table rule
rather than overridden per page) rather than a distinct one:

- Each row SHALL carry the marker `category-` followed by the entry's
  category, one of `category-progression`, `category-judgment`,
  `category-blocked`, `category-admin`, matching the standard `A
  step's outcome is rendered as a tag carrying its state` already
  holds for the detail page's own markers: the literal tokens are
  given because they are what a test is derived from.
- The label SHALL render as a tag carrying the marker `kind-tag`,
  coloured according to the row's category — the same "readable by
  treatment before it is read by word" standard `outcome-tag` already
  holds, applied to the kind a reader scans a journal by instead of
  the outcome a reader scans a step by.
- The source SHALL render as a tag carrying the marker `mark`, the
  page's existing plain-fact vocabulary (`A step's actions are
  presented as one affordance vocabulary`'s sibling for a stated fact
  rather than a control) — flat and uncoloured by category, since a
  source is where an occurrence arrived from, not a judgement on it.

The markers are a necessary condition, not a sufficient one — that the
categories are visually distinguished from one another, and that the
journal table's row height and type size read as one page with the
detail page's own tables, SHALL be confirmed by direct inspection of
the rendered page.

A launch whose journal holds nothing SHALL render the page saying so.
A journal is empty for launches that predate it, and a page that could
not be reached when empty would read as "nothing happened" on exactly
those launches — which is why the detail page offers this page
regardless of whether anything is recorded.

#### Scenario: An entry names when it occurred

- **WHEN** a launch's journal holds an entry
- **THEN** its row shows the moment it occurred, in its own column

#### Scenario: An entry's row shows its subject, source and who recorded it as separate facts

- **WHEN** a launch's journal holds an entry carrying a subject, a source and an actor
- **THEN** its row shows each in its own column, and none of the three is folded into a sentence with another

#### Scenario: A kind's facts are composed into the row's detail phrase

- **WHEN** a launch's journal holds a `step-outcome-recorded` entry carrying an outcome and a reason
- **THEN** its row's detail column shows a phrase naming both, without a further column for the second

#### Scenario: A detail phrase does not restate the subject

- **WHEN** a launch's journal holds an entry carrying a subject that names a gate or a step
- **THEN** its row's detail column does not repeat that subject — the subject is read from its own gate/step column instead

#### Scenario: A metric step reads as a step

- **WHEN** a launch's journal holds a `step-outcome-recorded` entry for a blocking step declaring a metric identifier
- **THEN** its row's gate/step column carries that step, exactly as for any other step, and its detail column carries the entry's own facts

#### Scenario: A sourceless entry's source column says system

- **WHEN** a launch's journal holds an entry carrying no source
- **THEN** its row's source column reads `system`, whether or not that entry names an actor

#### Scenario: A known actor resolves to their name by member identifier

- **WHEN** an entry's `actor` is the member identifier of a member the membership carries
- **THEN** the row shows that member's name rather than the raw identifier

#### Scenario: A known actor resolves to their name by ClickUp user id

- **WHEN** an entry's `actor` is the ClickUp user id of a member the membership carries
- **THEN** the row shows that member's name rather than the raw identifier

#### Scenario: An unresolvable actor renders as its raw value

- **WHEN** an entry's `actor` does not match any member the membership carries, by either identifier
- **THEN** the row shows the raw actor value rather than omitting it

#### Scenario: An entry's row shows its label as a coloured kind tag and carries its category marker

- **WHEN** a launch's journal holds an entry
- **THEN** its row shows the entry's short label as a tag carrying the marker `kind-tag`, coloured according to the row's category, and the row carries the marker `category-` followed by its category

#### Scenario: A source renders as a plain, uncoloured tag

- **WHEN** a launch's journal holds an entry carrying a source
- **THEN** its row shows that source as a tag carrying the marker `mark`, its colour independent of the row's category

#### Scenario: Entries render newest first

- **WHEN** a launch's journal holds several entries
- **THEN** the journal page renders them most recent first

#### Scenario: An empty journal says so

- **WHEN** a launch's journal holds no entry
- **THEN** the journal page renders and states that nothing is recorded

### Requirement: A carried finding's result is rendered ahead of its comment

Where a step's recording carries a finding, the launch detail page SHALL render that finding's **field and value first**, and the finding's comment after it, as two distinguishable parts of the outcome the page already renders.

**The result SHALL lead with the field and the value and nothing else.** No introductory sentence, no restatement of the step, no label narrating what is about to be shown — the field's name and its value are the whole of it. What the page is reporting is a fact the launch now asserts, and a reader scanning a column of them must be able to read the fact itself rather than a sentence containing it.

**The field SHALL be rendered as the words an admin uses, not as its storage identifier.** This capability already requires the outcome vocabulary be rendered as an admin's words rather than as its tokens, and a field name is the same kind of thing: `sub_category` is how a column is spelled, not how a person reads. The wording SHALL be supplied alongside the sink registration that names the field, so that naming a sink and naming how it reads are one act, and SHALL reach the page **on the carried finding itself** — the page SHALL NOT resolve it through a registry of its own. Where the carried finding has no wording, the field's own name SHALL be rendered rather than nothing — an unrendered fact is the failure this surface exists to prevent.

**An empty value SHALL be rendered as visible text standing for emptiness, inside the result itself, and that text counts as the value rather than as a label.** An empty value is a result — something was established and it was empty — and it is exactly the state a reader most needs distinguished from a step that established nothing. Rendering it as blank, as whitespace, as an element carrying a class and no text, or by omitting the result SHALL NOT satisfy this: a reader must be able to see that the answer was "none", not infer it from an absence.

*"Text", not "marker", deliberately.* This capability uses **marker** for a literal class name, and the class names this requirement fixes are named below; what an empty value needs is something a person reads.

**The result and the comment SHALL carry distinct literal markers in the rendered response.** The result element SHALL carry `finding-result` and the comment element `finding-comment`. The markers are given because they are what a test is derived from, exactly as this capability's outcome-tag requirement already does — and they are a **necessary and not a sufficient** condition: carrying them satisfies this clause and does not by itself satisfy the one below.

**The distinction SHALL be carried by structure, not only by colour.** The result and the comment SHALL be separate block-level elements, and a separating element carrying `finding-divide` SHALL sit between them. That separation is observable in the rendered response, which is what makes this requirement assertable rather than a matter of opinion — and it is what a reader who cannot distinguish the colours, or who is reading in the theme the colour was not chosen for, has left.

Colour MAY carry the distinction in addition, and where it does it SHALL come from the presentation vocabulary's own tokens rather than from literal values, so that both themes are covered by construction. **A rendering distinguished only by a colour declaration SHALL NOT satisfy this**, whatever class names it carries.

Weight, spacing and which token is used are not fixed here. They are visual judgements settled by looking at the running page, and fixing them in a specification would be pretending a test can decide them.

**A recording carrying no finding SHALL render as it does without this change.** That is every recording made before this capability existed and every recording by a handler reporting no finding, so the unchanged path is the common one and SHALL NOT be disturbed.

**The verbatim evidence and the provenance SHALL still be rendered.** The result and comment lead the cell; they do not replace what the page already shows. The evidence is the record of what a member was shown, and a presentation that dropped it in favour of a tidier rendering would lose the only account of what was actually read.

#### Scenario: The field and value lead the outcome

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the finding's field and value are rendered ahead of the comment, the result element carrying `finding-result` and the comment element `finding-comment`

#### Scenario: The result carries no leading prose

- **WHEN** the detail page renders a carried finding's result
- **THEN** what precedes the field in that result is nothing — no introductory sentence and no narrating label

#### Scenario: The field reads as an admin's words

- **WHEN** the detail page renders a carried finding that carries a wording for its field
- **THEN** that wording is rendered rather than the storage identifier

#### Scenario: A field with no supplied wording still renders

- **WHEN** the detail page renders a carried finding that carries no wording
- **THEN** the field's own name is rendered rather than nothing

#### Scenario: An empty value renders as readable text

- **WHEN** the detail page renders a step whose carried finding has an empty value
- **THEN** the result carries visible text standing for emptiness, distinguishable from a step whose recording carries no finding at all

#### Scenario: The distinction survives without colour

- **WHEN** a carried finding's result and comment are rendered
- **THEN** they are separate block-level elements with a separating element carrying `finding-divide` between them, so that a rendering whose only difference is a colour declaration does not satisfy this

#### Scenario: A recording with no carried finding is rendered unchanged

- **WHEN** the detail page renders a step whose recording carries no finding
- **THEN** its outcome renders as it did before this capability existed

#### Scenario: The evidence and provenance are still rendered

- **WHEN** the detail page renders a step whose recording carries a finding
- **THEN** the verbatim evidence and the recording's provenance are rendered as well, the result and comment leading rather than replacing them
