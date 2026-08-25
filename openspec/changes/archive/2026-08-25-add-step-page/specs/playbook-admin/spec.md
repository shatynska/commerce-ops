## MODIFIED Requirements

### Requirement: Steps can be created, retired and un-retired from the page

The admin surface SHALL offer creating a step with the full authorable
shape — the identifier is generated, never asked for — and retiring or
un-retiring a step. Each flow SHALL go through the corresponding
authoring write, and a rejection SHALL render its full fault list the
same way a rejected edit does.

Creating SHALL live on its own surface rather than within the step
list, and SHALL be reachable from the list without traversing the step
set, so that reaching it does not depend on how many steps are shown.

A create rejected by validation SHALL re-render the create surface
still holding **every** submitted value, carrying every fault the write
reported. Every value means every one: the fields the surface shares
with editing, the timing anchor's inputs, the discipline — which only
the create surface offers, since a step's discipline cannot be updated —
and **each** person named as an assignee, not merely one of them. A
create rejected because the step set changed underneath it SHALL persist
nothing, say so, and likewise keep what was typed. This is the guarantee
a rejected edit already carries; a create surface that loses a set of
named people on a rejection is worse than one that loses a line of text,
because retyping it means remembering who was on it.

The create surface SHALL require a discipline, and a create submitted
without one SHALL be refused rather than assigned a default. A step's
discipline is carried in the identifier the write generates and cannot
be updated afterwards, so a default chosen on the admin's behalf is a
choice they cannot reverse. The surface offers a discipline selector,
which always submits one of its options; refusing is therefore an answer
only a request built by hand can provoke, and a refusal is a better
answer to it than a silent default.

Leaving the create surface without creating SHALL return to the step
list narrowed as it was when the create surface was opened. A create
that lands SHALL likewise return to the step list under that same
narrowing, and the list SHALL identify which step was just created —
addressing it directly, so that a browser can bring it into view.

Where the created step renders depends on the status it was created
with, and the list SHALL address it wherever that is: a step created
`active` among its gate's active steps, and a step created `draft` or
`in-development` among the non-active steps set apart from the served
set, holding no position in its gate's order. Addressing SHALL NOT
assume the created step joined the served order, since a step written
down before it is ready is the case the draft status exists to serve.

The create surface SHALL NOT offer `retired` among the statuses a step
can be created with, and a create submitting `retired` SHALL be refused
rather than persisted. Retirement is the end of a step's life and is
reached through the retire flow, which records who ended it; a step
created straight into it would render behind the control that reveals
retired steps, where the list could not address it and the notice below
could not help. Leaving this to the rendered control alone would rest
the rule on markup — which this capability already declines to do for
reordering, refusing a move submitted where reordering is unavailable
rather than trusting the absent control.

These two refusals — a create naming no discipline, and a create naming
`retired` — answer requests the create surface cannot have produced,
since its own controls always submit a discipline and never offer
`retired`. They SHALL be refused without rendering a create surface, and
are therefore not "rejected by validation" in the sense used above: there
is no admin mid-edit whose typed values must survive, and rendering a
form in answer to a request no form made would invent a session that
does not exist.

Where the active narrowing would hide the created step, the list SHALL
render under that narrowing and SHALL state that the created step falls
outside it, naming it and offering to clear the narrowing. That offer
SHALL keep addressing the created step, so that clearing the narrowing
brings it into view rather than landing at the top of the whole set. A
create SHALL NOT appear to have been lost.

The notice SHALL be rendered only where clearing the narrowing it offers
to clear would reveal the named step. Where the named step is not among
the steps the page's own read returns, or where clearing that narrowing
would not reveal it — a step retired since it was created, say — the
list SHALL render as it would without the name. An offer the admin
cannot act on is worse than saying nothing.

"The steps the page's read returns" is deliberately not "the served
set". The served set is the `active` steps a launch is held to, and a
step created as a `draft` is by definition outside it while being
exactly the step this notice exists to find. The test is what the page
would render once the narrowing is cleared, not what a launch is held
to.

#### Scenario: Creating is reachable regardless of how large the set is

- **WHEN** the admin page is opened with the full step set rendered
- **THEN** a control opening the create surface is rendered ahead of the
  gate tables
- **AND** no create form is rendered within or after the gate tables

#### Scenario: A created step appears in its gate

- **WHEN** a step is created from the create surface as `active` with
  valid fields, with no narrowing active
- **THEN** the step list is shown again with the created step rendered
  as the last step of its gate's active steps, carrying its generated
  identifier
- **AND** the list addresses that step directly, so a browser lands on
  it rather than at the top

#### Scenario: A step created as a draft is addressed where it renders

- **WHEN** a step is created from the create surface as a `draft`, with
  no narrowing active
- **THEN** the step list is shown again with the created step rendered
  among the non-active steps, set apart from the served set and holding
  no position in its gate's order
- **AND** the list addresses that step directly

#### Scenario: A created step the narrowing keeps visible is still identified

- **WHEN** a step is created under a narrowing the created step matches
- **THEN** the step list is shown under that narrowing with the created
  step rendered
- **AND** the list addresses that step directly

#### Scenario: A create the narrowing would hide is not left looking lost

- **WHEN** a step is created while a search is active that matches
  neither the created step's name nor its description
- **THEN** the step list is shown under that search
- **AND** names the created step and states that it falls outside the
  active narrowing, offering to clear the narrowing
- **AND** taking that offer shows the list with the narrowing cleared,
  still addressing the created step rather than the top of the set

#### Scenario: A step named as created but not there is ignored

- **WHEN** the list is requested naming a created step that the page's
  read does not return at all
- **THEN** the list renders as it would without that name
- **AND** states nothing about a step falling outside the narrowing

#### Scenario: A draft the narrowing would hide is named like any other step

- **WHEN** a step is created as a `draft` while a gate filter is active
  that its gate does not match
- **THEN** the step list is shown under that filter
- **AND** names the created step and offers to clear the filter, exactly
  as it would for a step created `active`

#### Scenario: A named step the offer could not reveal is ignored

- **WHEN** the list is requested naming a created step that has since
  been retired, from a view that does not reveal retired steps
- **THEN** the list renders as it would without that name
- **AND** does not offer to clear a narrowing that would not reveal it

#### Scenario: A rejected create keeps every submitted value

- **WHEN** a submitted create is rejected by validation
- **THEN** the re-rendered create surface reports every fault the write
  reported
- **AND** every submitted value, the timing anchor's included, is still
  in the form
- **AND** the served step set is unchanged

#### Scenario: A rejected create keeps every assignee that was named

- **WHEN** a create naming two assignees is rejected by validation
- **THEN** the re-rendered create surface still shows both of them named
- **AND** neither is dropped nor replaced by the other

#### Scenario: A rejected create keeps the submitted discipline

- **WHEN** a create submitting a discipline other than the first offered
  is rejected by validation
- **THEN** the re-rendered create surface still shows the submitted
  discipline selected
- **AND** a corrected resubmission generates an identifier carrying that
  discipline

#### Scenario: A create naming no discipline is refused, not defaulted

- **WHEN** a create is submitted carrying no discipline at all
- **THEN** it is refused without a create surface being rendered, and
  nothing is persisted
- **AND** no step is created carrying a discipline the submission did
  not name

#### Scenario: A create naming a retired status is refused

- **WHEN** a create is submitted naming `retired` as the status
- **THEN** it is refused without a create surface being rendered, and
  nothing is persisted
- **AND** the create surface offers no such status to begin with

#### Scenario: A stale create is surfaced, not silently dropped

- **WHEN** a create is submitted after another write has changed the
  step set
- **THEN** nothing is persisted and the surface states the set changed
  underneath the create
- **AND** the submitted values are still in the form

#### Scenario: A blocked retirement explains itself

- **WHEN** retiring a step is rejected because its gate would be left
  with no blocking step
- **THEN** the page renders the fault naming that gate and the step is
  not retired

### Requirement: The narrowed view survives every write and every move between views

Every write made from the page — an edit, a creation, a retirement, an
un-retirement, a reorder — SHALL carry forward the narrowing that was
active when it was made: the gate filter, the discipline filter, the
text search, and whether retired steps are shown. Navigation
between the list and a step's edit form, and between the list and the
create surface, SHALL carry that narrowing too, in both directions, and
so SHALL the control that reveals or hides retired steps.

Where a write re-renders the list, it SHALL render it under that
narrowing. Where a write re-renders some other view — a rejected edit
re-renders the edit form, and a rejected creation re-renders the create
surface, as the editing and creation requirements demand — the narrowing
SHALL be preserved so that the next render of the list applies it. A
write SHALL NOT widen, clear, or otherwise alter what the page shows
beyond the effect of the write itself.

#### Scenario: An accepted write keeps the narrowing

- **WHEN** a step is retired while a gate filter and a discipline filter are active
- **THEN** the re-rendered list still applies both filters
- **AND** shows the same gate and discipline selections as before the write

#### Scenario: A rejected list-level write keeps the narrowing

- **WHEN** a retirement is rejected while a text search is active
- **THEN** the re-rendered list reports the faults
- **AND** still applies the search term

#### Scenario: A rejected creation keeps the narrowing without leaving the create surface

- **WHEN** a creation is rejected while a text search is active
- **THEN** the create surface re-renders with its faults and the submitted values, as the creation requirement requires
- **AND** returning to the list from that surface applies the search term

#### Scenario: A rejected edit keeps the narrowing without leaving the form

- **WHEN** an edit is rejected while a gate filter is active
- **THEN** the edit form re-renders with its faults and the submitted values, as the editing requirement requires
- **AND** returning to the list from that form applies the gate filter

#### Scenario: Opening and leaving an edit form preserves the narrowing

- **WHEN** a step's edit form is opened from a narrowed list and left without saving
- **THEN** the list re-renders under the same narrowing

#### Scenario: Opening and leaving the create surface preserves the narrowing

- **WHEN** the create surface is opened from a narrowed list and left without creating
- **THEN** the list re-renders under the same narrowing

#### Scenario: Un-retiring keeps the retired steps visible

- **WHEN** a step is un-retired from the view that reveals retired steps
- **THEN** the re-rendered list still reveals retired steps
- **AND** still applies whatever gate and discipline filters were active

## ADDED Requirements

### Requirement: A timing anchor offers only the inputs its own kind uses

A step's timing anchor takes different inputs depending on which anchor
kind it declares. An authoring surface SHALL render, as offered, only
the inputs the anchor kind it was rendered with actually uses; the
inputs belonging **only** to the other anchor kinds SHALL be rendered as
not offered. An input more than one anchor kind uses SHALL stay offered
for every kind that uses it, and the control that selects the anchor
kind SHALL always be offered. Which anchor kind a surface is rendered
with is the step's own on a fresh edit, the submitted one around a
rejection, and the default on a fresh create.

This is the same principle the step form already applies to fields
carrying no meaning for a step's kind, on a different axis: the anchor's
kind rather than the step's. It differs in one respect, and the
difference is binding. Inputs rendered as not offered SHALL retain
whatever value they carry, and SHALL still be submitted, so that an
anchor kind selected and then reconsidered does not discard what was
already entered. Rendering them merely disabled would satisfy the first
sentence and break this one, since a disabled input submits nothing.

An anchor value submitted for a kind the surface was not rendered with
SHALL have no effect on the step that is written.

#### Scenario: Only the selected anchor kind's inputs are offered

- **WHEN** an authoring surface is rendered with the anchor kind
  `offset`
- **THEN** the inputs the `offset` kind uses are rendered as offered
- **AND** the inputs belonging only to the other anchor kinds are
  rendered as not offered

#### Scenario: A rejection re-renders against the submitted anchor kind

- **WHEN** a write submitting the anchor kind `window` is rejected
- **THEN** the re-rendered surface offers the inputs the `window` kind
  uses
- **AND** the inputs belonging only to the other anchor kinds are
  rendered as not offered
- **AND** the values submitted for those other kinds are retained

#### Scenario: An input two anchor kinds share stays offered for both

- **WHEN** an authoring surface is rendered with each of the two anchor
  kinds that share an input
- **THEN** that input is rendered as offered under both

#### Scenario: A value carried by a not-offered input does not reach the step

- **WHEN** a write is submitted carrying a value in an input the
  submitted anchor kind does not use
- **THEN** the written step's timing anchor is the one its kind
  describes, unaffected by that value
