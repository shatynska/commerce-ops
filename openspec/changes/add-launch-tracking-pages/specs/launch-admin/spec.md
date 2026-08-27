## Purpose

The launch-tracking surface: lets a signed-in admin see every product in
launch at once — where each stands in the gate sequence, whether its date
is at risk and whether it waits on a person — and open one launch to read
its steps, their recorded outcomes and its journal. It reports what the
launch context already holds and changes none of it.

## ADDED Requirements

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
every active roster member unrestricted — so this scenario is exercised
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

#### Scenario: An overdue step is marked

- **WHEN** the launch report marks a step overdue
- **THEN** the page renders it as overdue

### Requirement: A launch's detail page renders its journal, newest first

The detail page SHALL render the launch's journal with the most recent
entry first, each entry naming what occurred, when, and what caused it.

A launch whose journal holds nothing SHALL render the section saying so.
A journal is empty for launches that predate it, and a section that
vanished when empty would read as "nothing happened" on exactly those
launches.

#### Scenario: Entries render newest first

- **WHEN** a launch's journal holds several entries
- **THEN** they are rendered most recent first

#### Scenario: An empty journal says so

- **WHEN** a launch's journal holds no entry
- **THEN** the section is rendered and states that nothing is recorded

### Requirement: Both surfaces are read-only

Neither page SHALL offer any control that changes launch state. Approving
a gate, accepting or rejecting an automated result, recording an outcome
and moving a launch date SHALL remain reachable only by the paths that
already serve them.

Stated as a requirement rather than left as an omission: these pages
render an admin's own launches beside controls they are used to acting
through elsewhere, and "there is deliberately nothing to press here" is
the guarantee that makes the surface safe to open on a live launch.

#### Scenario: The pages present no launch-changing control

- **WHEN** either page is rendered for a launch in any state
- **THEN** it offers no control that records an outcome, approves a gate, decides an automated result, or moves a launch date

### Requirement: A launch the caller may not see is indistinguishable from one that does not exist

A detail page requested for an identifier with no launch position, for
one the caller's scope does not permit, and for an identifier naming
nothing the system knows SHALL each be refused identically, in the same
shape as a request for a route that does not exist.

The refusal turns on the **launch position**, never on whether the
catalog can name the product. A launch position whose product the catalog
cannot resolve SHALL be served, not refused: the list renders that launch
by its raw identifier and offers its detail page in one action, so
refusing it here would put a dead end behind a row this capability
deliberately keeps visible — and during a catalog outage it would put one
behind every row.

`launch-instance` already reports absence and refusal identically on the
read itself, so that a caller cannot confirm the existence of a launch
they may not see. A surface that answered the three differently would
give back exactly what that read withholds.

#### Scenario: A product with no launch is refused as absent

- **WHEN** a detail page is requested for a product that has no launch position
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: A forbidden launch is refused identically

- **WHEN** a detail page is requested for a launch the caller's scope does not permit
- **THEN** the response is identical in shape to the one given for a product with no launch

*(Unreachable end to end for the same reason, and covered the same way:
the scope resolver alone is stubbed, and the response is asserted against
the one given for a product with no launch.)*

#### Scenario: A launch whose product cannot be resolved is served

- **WHEN** a detail page is requested for a launch position whose product the catalog cannot resolve
- **THEN** the page is served, identifying the launch by its raw product identifier

#### Scenario: An unknown identifier is refused identically

- **WHEN** a detail page is requested for an identifier with no launch position and no catalog product
- **THEN** the response is identical in shape to the other two refusals

### Requirement: Both surfaces ride the admin session and carry the shared header

Every route of both pages SHALL require a valid admin session and SHALL
refuse a request without one in the same absence-shaped way every other
admin route does. Both SHALL carry the header the other admin surfaces
carry, identifying the launch surface as the one being viewed, and from
each the other admin surfaces SHALL be reachable in one action without
scripting.

#### Scenario: A request without a session is refused as absent

- **WHEN** either page is requested with no admin session, or with one that has expired
- **THEN** the response is shaped like a request for a route that does not exist

#### Scenario: The header names the other surfaces

- **WHEN** either page is rendered
- **THEN** its header identifies the launch surface as the one being viewed and offers the other admin surfaces in one action

### Requirement: The pages' presentation comes from the shared admin vocabulary

Both pages' presentation SHALL come from the same stylesheet the other
admin surfaces load, rather than from styling carried in the pages
themselves, so that a change to the vocabulary reaches every admin
surface rather than some of them.

`roster-admin` already requires this of itself, and records why: a page
carrying its own styling is why two surfaces an admin moves between look
like two products, and — more to the point — why a presentation fix
applied to one silently does not apply to the other, a divergence nothing
in the repository reveals. A third surface introduced with its own
styling would recreate that divergence rather than inherit its fix.

The pages SHALL reach that stylesheet through a route no single admin
surface owns, on the same terms every other surface reaches it, and SHALL
NOT reach it through a route belonging to the module that owns another
admin surface.

#### Scenario: The pages carry no styling of their own

- **WHEN** either page is rendered
- **THEN** its presentation comes from the shared admin stylesheet, and the page carries no styling of its own

#### Scenario: The stylesheet is not reached through another surface's route

- **WHEN** either page is rendered
- **THEN** the stylesheet it loads is served by a route no single admin surface owns

#### Scenario: A vocabulary change reaches these pages

- **WHEN** the shared admin stylesheet changes
- **THEN** both pages render under the changed vocabulary without either page being edited
