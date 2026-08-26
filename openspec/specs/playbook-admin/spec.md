# playbook-admin Specification

## Purpose
The steps management page: lets a signed-in admin see the authored step set whole — every status other than `retired`, grouped by gate, filterable and searchable, with the served steps set apart from the ones that are not — and change it through the validated authoring writes. Editing a step, changing its status, retiring and un-retiring it, and reordering a gate's active steps all happen in place on the list; creating a step has its own surface, reached from the list without traversing the set, so that reaching it never depends on how many steps are shown. Every rejected write renders its full fault list, and a rejected create keeps what was typed.

## Requirements

### Requirement: The step table shows the live set whole

The admin page SHALL render, in one table, every step the authored set
holds other than the `retired` ones — `active`, `draft` and
`in-development` alike — grouped by gate in the gate sequence's order,
with each gate's active steps in their authored order and its non-active
steps outside that order. "Live" is not used here: the word meant
"served" when the set had two states, and the set now has four. The table SHALL be filterable by gate and
by discipline, and searchable by the text of a step's name **and** its
description; an active filter or search narrows what is shown without
changing the underlying set. Retired
steps SHALL NOT appear in the default view, but SHALL be reachable
through an explicit control that shows them marked as retired, so that
un-retiring is possible from the page.

Searching both fields is what keeps search useful once the two are
separate: an author who remembers a phrase does not remember which of the
two fields they wrote it in.

Each **active** step SHALL render its own position among its gate's
active steps, together with how many active steps that gate holds; a
`draft` or `in-development` step holds no slot and SHALL render no
position. The position SHALL
reflect the whole gate, not the narrowed view, so that an admin working
under a filter can see where a step sits in the order that is actually
persisted.

#### Scenario: The whole live set is one page

- **WHEN** the admin page is opened with no filter active
- **THEN** every step other than the `retired` ones is rendered, grouped by gate in gate order
- **AND** each gate's active steps stand in authored order, with its non-active steps outside that order

#### Scenario: Filters narrow without altering

- **WHEN** a gate or discipline filter is applied
- **THEN** only the matching steps are shown, and the underlying step set is unchanged

#### Scenario: Search matches description text

- **WHEN** a search term is entered that appears in one step's name and in another step's description
- **THEN** both steps are shown

#### Scenario: Retired steps are reachable but set apart

- **WHEN** the control that shows retired steps is used
- **THEN** retired steps are shown marked as retired, and are not interleaved with the served set

#### Scenario: A position is read against the whole gate

- **WHEN** a filter narrows a gate to a subset of its active steps
- **THEN** each visible active step renders its position among that gate's active steps and the gate's active count
- **AND** those positions are unchanged by the filter

### Requirement: A step can be edited in place

The page SHALL let a step's authorable fields be edited inline and saved through the authoring update write. A saved edit SHALL re-render the step with its new values. A rejected write SHALL re-render the form still holding the submitted values, carrying **every** fault the write's validation reported. A write rejected because the step set changed underneath the form SHALL persist nothing and SHALL say so, so the admin re-reads before retrying.

"Every fault" SHALL hold across **all the values the surface itself
parses before the write**, not merely within one kind of them. Where a
submission carries both an unrecognised value in one control and an
unparseable one in another, the rejection SHALL report both, rather than
stopping at whichever was read first. A rejection an admin has to
correct one fault at a time is the failure this guarantee exists to
prevent.

The scope is stated precisely because it cannot honestly be wider. The
surface parses submitted values before calling the write at all, so a
submission the surface refuses never reaches the coherence rules and
their faults are never computed. What this guarantees is that the
surface reports everything **it** found, not that a rejection unites
faults the write never produced.

#### Scenario: A clean edit lands

- **WHEN** an edit with valid values is saved
- **THEN** the step re-renders with the new values

#### Scenario: A rejected edit shows every fault

- **WHEN** a submitted edit violates two coherence rules at once
- **THEN** the re-rendered form reports both faults
- **AND** the submitted values are still in the form
- **AND** the served step set is unchanged

#### Scenario: Faults from different sources arrive together

- **WHEN** a submitted write carries both an unrecognised value in a
  field the surface parses and an unparseable timing anchor
- **THEN** the rejection reports both faults
- **AND** neither source's faults are dropped in favour of the other's

#### Scenario: A create wrong in a field and in its discipline reports both

- **WHEN** a create carries both an unrecognised value in a field the
  surface parses and an unrecognised discipline
- **THEN** the rejection reports both faults
- **AND** each marks its own control

#### Scenario: A stale edit is surfaced, not silently dropped

- **WHEN** an edit is submitted after another write has changed the step set
- **THEN** nothing is persisted and the page states the set changed underneath the edit

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

A fault a rejected create reports about **the step being created** SHALL
NOT identify that step by the identifier the write would have generated.
No such step exists — the identifier is generated before validation and
nothing was persisted — so naming it sends the admin looking for a step
that is not there.

The rewriting SHALL be exactly this and no more: the leading
`step '<identifier>' ` — the words every step-level fault opens with —
is removed, and the remainder of the fault is rendered exactly as the
write reported it. No fault text is composed by the surface. The literal
form is given because it is the delta a test is derived from, and an
intent is not assertable.

A consequence, accepted rather than repaired: what remains reads as a
predicate without a subject — *"is automated and beyond draft but
carries no automation brief"*. Repairing it inside the fault would mean
composing text, which the sentence above forbids. Where the rendering
needs a subject, it belongs to the surface around the list rather than
to the fault.

Faults about the step set, which may legitimately name steps that do
exist, SHALL keep the identifiers they carry. So SHALL a fault the
surface does not recognise: unrecognised is unclassified, and a surface
that guessed would strip identifiers from faults naming steps the admin
would need to go and look at.

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

#### Scenario: A rejected create does not name the step it did not persist

- **WHEN** a create is rejected by a fault about the step being created
- **THEN** the reported fault does not identify that step by a generated
  identifier
- **AND** no step carrying that identifier is in the served set

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

### Requirement: A gate's steps can be reordered from the page

The page SHALL let a step be moved to a different position among its
gate's active steps, persisted through the authoring reorder write.

A move SHALL name the visible step the moved step is to come to rest
**after**, or name the head of the visible list. The moved step SHALL be
placed immediately after the step it names, and a move naming the head
SHALL place it immediately before the first visible step other than
itself — never ahead of steps the filter is hiding beyond that point.
Every step other than the moved one SHALL keep its relative order, steps
the filter is hiding included. A move that would leave the visible order
unchanged SHALL be treated as no move at all and SHALL persist nothing.

A move SHALL be submitted against the version of the step set that the
view it was made on was rendered from, and SHALL be rejected unless that
version is still the one the page reads when it computes the move's
position — so that a move made on a list a later accepted write has
superseded is refused rather than recomputed against a set the admin
never saw. The position SHALL then be applied only to that same version
of the set, so a write accepted in between rejects the move rather than
receiving a position computed without it.

Reordering SHALL be unavailable, and the page SHALL state why and offer
to leave the view in one action, wherever a move cannot be given an
honest meaning:

- while a text search is active — over a step's name or its description
  alike — because a text match selects an incidental set of steps in
  which a single move may cross an arbitrary number of unmatched ones;
- while retired steps are shown, because a retired step holds no
  position in its gate's active order and so can neither be moved nor be
  named as the step to come to rest after.

Steps that are `draft` or `in-development` SHALL NOT make reordering
unavailable, though they hold no slot either. The retired-steps rule is
page-wide because revealing retired steps is a deliberate act that puts
the page into a different mode; drafts appear in the default view, so the
same rule would remove reordering from any gate anyone is drafting in,
which is most of them. Instead they SHALL render outside the gate's
orderable list, so a move can neither name one as its resting place nor
cross one, and the gate's active steps stay reorderable exactly as they
are today. A move naming a step that holds no slot SHALL be refused
without persisting anything, like any other move that cannot be given an
honest meaning.

A gate filter or a discipline filter SHALL NOT make reordering
unavailable. Where reordering is unavailable, a move submitted anyway
SHALL be refused without persisting anything, so the restriction does
not rest on the rendered controls alone.

The new order SHALL be visible immediately after the move and identical
on the next full page load. A rejected reorder — including one rejected
because the step set changed underneath it — SHALL leave the rendered
order matching the served set and say why.

#### Scenario: A move sticks

- **WHEN** a step is moved to the top of its gate on the page
- **THEN** the page shows it first in its gate
- **AND** a fresh page load shows the same order

#### Scenario: A filtered move lands against the visible step it names

- **WHEN** a step is moved to come to rest after a visible step that a discipline filter separates from it by hidden steps
- **THEN** the moved step comes to rest immediately after that visible step
- **AND** the narrowed view shows the two in the requested order

#### Scenario: A filtered move upwards lands against the visible step above the one it passes

- **WHEN** a step is moved one visible position up, past a visible step that hidden steps separate from the visible step above that one
- **THEN** the moved step comes to rest immediately after the visible step above the one it passed
- **AND** ahead of the hidden steps separating those two, rather than immediately above the step it passed

#### Scenario: A filtered move disturbs nothing else

- **WHEN** a move is made while a filter hides part of the gate
- **THEN** every step other than the moved one holds its relative order, hidden steps included

#### Scenario: A move to the head of a narrowed list stops at the first visible step

- **WHEN** a step is moved to the head of a gate narrowed by a filter, and that gate holds hidden steps before the first visible one
- **THEN** the moved step comes to rest immediately before the first visible step
- **AND** behind those hidden steps

#### Scenario: A move to the end of a narrowed list stops at the last visible step

- **WHEN** a step is moved to come to rest after the last visible step of a gate narrowed by a filter, and that gate holds hidden steps after it
- **THEN** the moved step comes to rest immediately after that last visible step
- **AND** ahead of those hidden steps

#### Scenario: A move that changes nothing persists nothing

- **WHEN** a move is submitted that would leave the visible order as it already stands
- **THEN** nothing is persisted and the served order is unchanged

#### Scenario: Reordering is unavailable under a description search

- **WHEN** the list is narrowed by a text search over the name or the description
- **THEN** the reorder controls are inert
- **AND** the page states that reordering is unavailable while a search is active and offers to clear it in one action

#### Scenario: Reordering is unavailable while retired steps are shown

- **WHEN** the control revealing retired steps is engaged
- **THEN** the reorder controls are inert
- **AND** the page states that reordering is unavailable while retired steps are shown and offers to hide them in one action

#### Scenario: A move submitted where reordering is unavailable is refused

- **WHEN** a move is submitted while a text search is active or retired steps are shown
- **THEN** nothing is persisted and the page says why the move was refused

#### Scenario: A move submitted from a superseded list is rejected

- **WHEN** a move is submitted from a list that a later accepted write has superseded
- **THEN** nothing is persisted and the page states the set changed underneath the move
- **AND** the move's position is not computed against the newer set

#### Scenario: A stale move leaves truth on the page

- **WHEN** a reorder is rejected because the step set changed underneath it
- **THEN** the page re-renders the served order and states why the move did not land

#### Scenario: A draft in the gate does not remove reordering

- **WHEN** a gate holding a draft and three active steps is rendered in the default view
- **THEN** the gate's active steps can still be reordered, and the draft is not a position a move may name

### Requirement: What authoring refuses to update renders read-only

Fields the authoring capability does not accept updates to — a step's identifier and its discipline — and framework-owned facts such as a step's provenance SHALL render as read-only on the page, never as editable inputs whose submission would be refused.

#### Scenario: The identifier cannot be typed into

- **WHEN** a step's inline edit form is opened
- **THEN** the identifier and discipline render as text, not as inputs

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

### Requirement: The step form carries every authorable field

The step form SHALL offer every field the authoring capability accepts: the name, the description, the assignees, the kind, whether the result needs confirmation, the status, the hazard, and — for an `automated` step — the automation brief and the handler, alongside the gate, scope, timing anchor and blocking flag it already carries.

The name and the description SHALL be distinct inputs, and the description's input SHALL accept more than one line: a single-line box for a field whose whole purpose is to be longer than the name would teach the author the opposite of what the two fields are for.

Assignees SHALL be chosen from the roster's active people rather than typed, so an author cannot name a person who does not exist and cannot mistype an identifier. The people offered SHALL be identified by their display names, since an author knows colleagues by name and not by generated identifier.

Fields that carry no meaning for the step's current kind — an automation brief on a `human` step — SHALL either be hidden or render disabled, so the form does not invite a value the write would refuse.

#### Scenario: The form offers name and description separately

- **WHEN** a step's form is opened
- **THEN** the name and the description are separate inputs, and the description accepts line breaks

#### Scenario: Assignees are chosen from the roster

- **WHEN** the assignee control is opened
- **THEN** it offers the roster's active people by display name, and does not accept a free-typed identifier

#### Scenario: A form rejected by validation shows every fault with the typed values

- **WHEN** a submitted step violates two of the new field rules at once
- **THEN** the re-rendered form reports both faults and still holds what was typed, and the step set is unchanged

### Requirement: Steps that are not active are visible to authors and set apart

The page's default view SHALL show every `draft`, `in-development` and `active` step the authored set holds, and SHALL make each step's status legible. `retired` steps SHALL stay behind the explicit control that already reveals them, as they do today — the page reads the authored set by the same path that control already uses, which now answers with every status rather than adding a second read — retirement is the end of a step's life and does not belong in the working view, while a draft is work in progress and does.

Steps that are not `active` SHALL be visibly set apart from the served set rather than interleaved with it, so an author can tell at a glance which steps a launch is actually being held to. They hold no slot in their gate's order (`playbook-authoring`), so they SHALL render no position among the gate's active steps rather than a misleading one, and SHALL render outside the gate's orderable list — which is what lets the gate's active steps stay reorderable while a draft sits in the same gate.

A step's assignees SHALL be shown on the table alongside it. A `human` step that is `active` and shows no assignee is a state the write rules forbid, so showing assignees is what makes that rule's effect visible rather than merely enforced.

#### Scenario: Draft and in-development steps are shown and marked

- **WHEN** the page is opened against a set holding a draft and an active step in the same gate
- **THEN** both are shown, each carrying its status, and the draft is set apart from the served set
- **AND** the draft renders no position among the gate's active steps

#### Scenario: Retired steps stay behind their control

- **WHEN** the page is opened with no control engaged
- **THEN** retired steps are not shown, and draft and in-development steps are

#### Scenario: Assignees are visible on the table

- **WHEN** a step naming two assignees is rendered
- **THEN** both are shown by display name alongside the step

### Requirement: A step's status can be changed from the page

The page SHALL offer changing a step's status, including activating it. A refused change — an activation whose step lacks what its kind requires, or a de-activation that would leave a gate unheld — SHALL be surfaced on the page carrying the refusal's own explanation, and SHALL leave the set unchanged.

#### Scenario: An activation lands and the step joins the served set

- **WHEN** an author activates a step carrying everything its kind requires
- **THEN** the step is shown as active and among the served set

#### Scenario: A refused activation explains itself

- **WHEN** an author activates a `human` step naming no active assignee
- **THEN** the page shows the refusal's explanation and the step's status is unchanged

<!-- Two headings below keep the word "live": a MODIFIED requirement must
     carry its requirement and scenario titles forward unchanged, so the
     titles predate the word's retirement while their bodies do not use it. -->

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

### Requirement: A rejected write names the fields its faults concern

A surface **carrying the authorable form** — the edit form and the
create surface — SHALL name, for each fault it reports, the form fields
that fault concerns, so that an admin reads which controls to touch
rather than translating prose back into inputs.

This requirement binds those two surfaces only. The step list also
renders rejections — of a retirement, an un-retirement, a status change
or a move — and carries no authorable form for a fault to be attributed
against; those rejections SHALL keep rendering at page level exactly as
they do.

Attribution SHALL be **additional to** the fault list, never a filter:
every fault the write reported SHALL still be rendered in full, in the
surface's own fault list, whether or not it was attributed. A fault the
surface cannot attribute SHALL be rendered at page level, exactly as it
would have been without this requirement — an unrecognised fault
degrades, it does not disappear.

Faults concern fields in three ways, and each SHALL be treated
differently:

- A fault about **one field** SHALL mark that field.
- A fault about a **combination of fields** SHALL mark **every** field
  in the combination. Neither value is wrong on its own — an `automated`
  step carrying no automation brief is refused for the pair, and
  changing either the kind or the brief resolves it — so marking one
  would tell the admin to change that one.
- A fault about the **step set as a whole, or about a gate**, SHALL mark
  no field and SHALL be rendered at page level. Such a fault does not
  concern anything the form in front of the admin carries.

Where more than one fault concerns the same field, that field SHALL be
marked once and SHALL carry all of them, so that a field is not silently
attributed to only the first rule that named it.

Marking SHALL be observable in the rendered response — the field's own
control carries the fault text it was marked with — rather than
expressed only visually, so that what an admin is told is what a
response can be asked for.

A marked control MAY be one the surface does not offer, and the
combination treatment guarantees it will sometimes be: a `human` step
carrying an automation brief is refused for the pair, and the automation
controls render un-offered on a `human` step. Marking SHALL render the
fault text adjacent to such a control just as it does for any other, and
SHALL NOT change whether the control is offered. Telling an admin which
pair was refused is the point; silently omitting half of it because one
half is currently un-offered would leave the refusal unexplained.

#### Scenario: A fault about one field marks that field

- **WHEN** a write is rejected because a step's name is empty
- **THEN** the re-rendered surface marks the name field with that fault
- **AND** no other field is marked with it

#### Scenario: A fault about a combination marks every field in it

- **WHEN** a write is rejected because a `human` step carries an
  automation brief
- **THEN** the re-rendered surface marks both the kind field and the
  automation brief field with that fault

#### Scenario: A fault about the step set marks no field

- **WHEN** a write is rejected because a gate would be left with no
  active blocking step
- **THEN** the re-rendered surface reports that fault at page level
- **AND** marks no field with it

#### Scenario: Attribution never shortens the fault list

- **WHEN** a write is rejected reporting one fault the surface attributes
  and one it does not
- **THEN** both faults are rendered in the surface's fault list
- **AND** the one it attributes is additionally marked on its field

#### Scenario: A field two faults concern carries both

- **WHEN** a write is rejected by two faults that both concern the kind
  field
- **THEN** the kind field is marked once
- **AND** carries both faults

#### Scenario: An unparseable anchor value marks the input it came from

- **WHEN** a write is rejected because one of the timing anchor's
  numeric inputs cannot be read as a number
- **THEN** the re-rendered surface marks that input with the fault
- **AND** marks neither of the anchor's other numeric inputs

#### Scenario: Both authoring surfaces attribute alike

- **WHEN** an edit and a create are each rejected by a fault about one
  field
- **THEN** each surface marks that field on its own rendering

### Requirement: Every rule an authoring write can provoke attributes its fault

Every coherence rule and parse failure that a submitted **edit or
create** can provoke SHALL be attributed to the fields it concerns, or
SHALL satisfy the page-level criterion below. There SHALL be no rule
whose fault the surface fails to recognise by accident.

The page-level criterion is a property of the fault, not a decision the
attribution records: a fault is held at page level when **it concerns no
control the authorable form carries** — a fault about the step set as a
whole, or about a gate. Stating it this way is deliberate. Were
"deliberately page-level" defined as whatever attribution declines to
attribute, this requirement would be satisfiable by declaring every gap
deliberate, and it would assert nothing.

This requirement exists because some faults are attributed by matching
message text authored in another layer. A rule reworded there would
silently stop matching and degrade to page level, which the requirement
above permits by design — so nothing about the rendering would reveal
it. The obligation is therefore stated over the rules as a set rather
than over any one rendering.

Rules a write cannot provoke are outside this requirement — the gate
sequence is constructed by the system rather than submitted, and step
identifiers are generated rather than typed — since a rule that cannot
be provoked cannot be checked by provoking it.

#### Scenario: No rule an authoring write can provoke is unattributed by accident

- **WHEN** every rule an edit or a create can provoke is provoked in
  turn
- **THEN** each resulting fault is either attributed to the fields it
  concerns, or concerns no control the authorable form carries
- **AND** no fault falls through unrecognised

### Requirement: A step's actions are presented as one affordance vocabulary

Every action a step's row offers — reordering, changing status, editing,
retiring, un-retiring — SHALL be presented as a control of the same
weight as its siblings, and a step's row SHALL occupy one line rather
than stacking its controls one per line. Which actions a row offers is
unchanged by this requirement: a step that offers no move today offers
none after it.

Actions that act on the same thing SHALL be grouped with the thing they
act on rather than pooled into one cell by virtue of all being controls.
The reorder pair belongs beside the position it changes; the status
control belongs in the status column. What the requirement forbids is
the vertical stack that cost a step five lines of height, not a layout
that reads by meaning — an admin looking for "where does this sit" and
an admin looking for "retire this" are looking for different things.

The **destructive** action SHALL be distinguished by its own treatment
rather than by being the most prominent control in the row. Retiring a
step is the action an admin is least likely to want by accident, and a
vocabulary in which it is the loudest thing on the row invites exactly
that.

Both the presentation and the destructive distinction SHALL be
observable in the rendered response — each action control carries the
marker `row-action`, and the destructive one carries the further marker
`danger` — rather than being expressed only visually. This is the same
standard the surface already holds for fault marking, and for the same
reason: what an admin is told must be something a response can be asked
for. The literal tokens are given because they are what a test is
derived from, as this capability already does for its fault-rewriting
rule.

The markers are a necessary condition, not a sufficient one. They
establish that the vocabulary was applied; they cannot establish that a
row occupies one line or that the destructive action is not the most
prominent, which no server response can show. Those SHALL be confirmed
by direct inspection of the rendered page.

Nothing in this requirement licenses removing an action, changing what
an action does, or changing which actions a row offers for a given step.

#### Scenario: A row's actions share one vocabulary

- **WHEN** an active step's row is rendered with its full set of actions
- **THEN** every action control carries `row-action`
- **AND** no action is rendered as an unmarked link among marked controls

#### Scenario: The destructive action is distinguished, not amplified

- **WHEN** an active step's row is rendered
- **THEN** the retire control carries `danger`
- **AND** no other action control on that row carries it

#### Scenario: A retired step's only action speaks the same vocabulary

- **WHEN** a retired step's row is rendered from the view that reveals
  retired steps
- **THEN** its un-retire control carries `row-action`
- **AND** does not carry `danger`

#### Scenario: The vocabulary does not change which actions are offered

- **WHEN** a step that cannot be moved further up is rendered
- **THEN** its move control is still rendered inert, exactly as before
- **AND** carries `row-action` like every other action

### Requirement: The vocabulary never suppresses a marked control's fault

`playbook-admin` already requires a fault to be rendered adjacent to a
marked control whether or not that control is offered, and requires
marking never to change whether it is offered. Those marks currently
ship with no presentation treatment at all. This requirement binds the
treatment they are about to receive: **the vocabulary SHALL NOT suppress
a fault the surface marked.**

The case this actually concerns is the automation controls. A `human`
step carrying an automation brief is refused for the pair, marking both
the kind and the brief, and the brief renders disabled among controls a
step of that kind cannot use. Any treatment that sets those controls
apart is presentation; hiding them would remove a fault the surface is
required to render, turning a styling decision into a silent breach of
an existing guarantee.

So the obligation is negative and specific: no rule in the vocabulary
SHALL render a marked control's fault, or a container holding one, as
not displayed **or as less legible than the surface's ordinary text**.
A disabled control stays disabled, and the fault marked on it stays as
readable as any other.

Both halves are stated because the second is the one a treatment reaches
by accident. The mark renders *inside* the marked control's label, so
the natural way to set a region apart — reducing its opacity — applies
to descendants and takes the fault down with the controls; opacity also
establishes a stacking context, so restoring it on the mark alone does
not work. Setting apart a control an admin cannot use is legitimate;
dimming the sentence explaining why their write was refused defeats the
guarantee it exists to serve. The legibility half cannot be read from a
response and is confirmed by inspection.

This requirement binds whatever treatment the surface carries, including
none. The vocabulary as built gives those controls no treatment of its
own — every version tried read as a region demanding attention rather
than one that can be ignored, which is the opposite of what it means —
so the controls render as ordinary fields and the browser's own
rendering of a disabled control is what says they are not offered. That
makes this requirement trivially satisfied rather than carefully
satisfied, and it stays stated for exactly that reason: it is the
constraint on the treatment somebody adds next.

#### Scenario: A fault on a disabled automation control is not suppressed

- **WHEN** a `human` step carrying an automation brief is rejected for
  the pair
- **THEN** the mark carrying that fault is rendered
- **AND** the automation brief control is still disabled
- **AND** neither that mark, nor the fieldset holding it, is rendered as
  not displayed

### Requirement: A created step is distinguished on the row the list lands on

The step list already addresses a just-created step directly, so that a
browser brings it into view. Where the list is rendered naming a created
step that it actually renders, that step's row SHALL additionally be
distinguished from every other row, and the distinction SHALL be carried
in the response — the marker `just-created` on that row — rather than
depending on scripting.

Addressing without distinguishing lands the admin somewhere in a table
of 105 rows with nothing saying which row was the point. The two are one
guarantee: find it, then see it.

The distinction SHALL follow the addressing exactly, and SHALL never
outrun it. Where the list renders without naming a created step, or
names one it does not render — a step the narrowing hides, or one
retired since it was created, both of which the list already handles by
rendering as though unnamed — no row SHALL be distinguished. A row
highlighted on a page that is not the result of a create would be a
claim about a step nobody just created.

#### Scenario: The created step's row is distinguished

- **WHEN** a create lands and the list is rendered naming the created
  step, with no narrowing hiding it
- **THEN** that step's row carries `just-created`
- **AND** no other row carries it

#### Scenario: A step created as a draft is distinguished where it renders

- **WHEN** a step is created as a `draft` and the list is rendered
  naming it, with no narrowing hiding it
- **THEN** its row among the non-active steps carries `just-created`
- **AND** no row among the served steps carries it

#### Scenario: A list not naming a created step distinguishes nothing

- **WHEN** the list is rendered without naming a created step
- **THEN** no row carries `just-created`

#### Scenario: A named step the list does not render distinguishes nothing

- **WHEN** the list is rendered naming a created step that its own read
  does not return
- **THEN** the list renders as it would without that name
- **AND** no row carries `just-created`

### Requirement: The page carries a header from which the other admin surface is reachable

Every page this capability serves — the step list, the edit surface and
the create surface — SHALL carry a header naming the admin surfaces the
session can reach, and from it the roster page SHALL be reachable in one
action.

The header exists because the surfaces are otherwise unconnected. The
admin session lands on this page and nothing on it, or on any page
reachable from it, mentions that a roster page exists. An admin who does
not already know the URL cannot get there, and the roster is where
people — including the assignees this page's own form offers — are
added and deactivated.

The header SHALL identify which surface is currently being viewed, so it
reads as a position rather than as an undifferentiated pair of links.
The create and edit surfaces are not themselves named in the header;
each SHALL identify the playbook surface as current, since that is the
surface an admin is within while authoring a step.

Reachability SHALL NOT depend on scripting, and SHALL NOT depend on the
step set: the header renders the same whether the set holds one step or
every one, and whatever narrowing is active. This is the guarantee the
create control already carries on this page, for the same reason — a
control that is only reachable after scrolling past 105 steps is one an
admin concludes does not exist.

Travelling to the roster page SHALL NOT be treated as a write and SHALL
carry nothing forward: the roster page has no narrowing of its own, and
the narrowing requirement governs movement between this capability's own
views, not departure from them.

One consequence is accepted rather than repaired, and is stated because
it is invited by this requirement's own rationale. The roster is where
assignees are added, so an admin part-way through a create who finds an
assignee missing is exactly the person the header serves — and departing
from a filled authoring surface **discards what was typed**. The
surrounding spec works hard to keep a rejected create's values,
including each named assignee, but that guarantee is about a rejection,
not about a deliberate departure. The header SHALL therefore be no
harder to leave from than any other link, and recovery is the browser's
back-navigation. A confirmation prompt was considered and refused: it
would make the common case — travelling from an untouched list — worse
in order to protect the rare one, and this capability nowhere else
guards a navigation.

#### Scenario: Departing from the create surface carries nothing forward

- **WHEN** the header's roster link is taken from the create surface
- **THEN** the roster page is served
- **AND** nothing the create surface held is persisted

#### Scenario: The roster page is reachable from the step list

- **WHEN** the step list is rendered
- **THEN** its header offers the roster page in one action
- **AND** identifies the step list as the surface currently viewed

#### Scenario: The header does not depend on how many steps are shown

- **WHEN** the step list is rendered under a narrowing that matches no
  step at all
- **THEN** the header is still rendered and still offers the roster page

#### Scenario: The authoring surfaces carry the header too

- **WHEN** the create surface and a step's edit surface are each
  rendered
- **THEN** each carries the header offering the roster page
- **AND** each identifies the playbook surface as the one currently
  viewed

### Requirement: The presentation assets stay behind the admin guard and need no build step

The stylesheet the admin surfaces load SHALL be served only to a caller
holding a valid admin session, and a caller without one SHALL be refused
in the same shape as any other unauthorised admin path — the app's own
404, identical to an unregistered route, revealing nothing about what
exists. The vendored assets the playbook page already loads keep this
guarantee unchanged.

The stylesheet SHALL be served as it is committed to the repository,
with no build, compile, bundle or transform step between the source and
what is served. What a reviewer reads in the diff is what a browser
receives.

This is a constraint on the whole vocabulary, not on one file. Adopting
a mechanism that needs a build step — a preprocessor, a bundler, a
subsetting pass over binary assets — would break it however small the
step was, which is why the type layer uses system fonts and this change
commits nothing binary.

#### Scenario: The stylesheet is refused without an admin session

- **WHEN** the stylesheet is requested with no admin session cookie
- **THEN** the response is the same 404 an unregistered route returns
- **AND** carries no stylesheet content

#### Scenario: The stylesheet is served to an admin

- **WHEN** the stylesheet is requested with a valid admin session
- **THEN** it is served
- **AND** its bytes are those of the file committed to the repository

#### Scenario: No build artifact stands between source and response

- **WHEN** the repository is checked out and the application is started
  with no build or asset step run
- **THEN** the admin surfaces load their stylesheet successfully

### Requirement: Every write is judged against the same roster the page reads

The page reads the roster to render a step's assignees and to offer who can be named. The writes it makes are judged against the roster too, by the preconditions `playbook-authoring` owns and states — this requirement adds no rule of its own about who may be named. What it adds is that both readings SHALL reach the **same** roster: whatever the page offers as an assignee, a write from that page SHALL be able to name, and whatever a write refuses on roster grounds SHALL be explicable from what the page itself displayed.

No write SHALL be refused **on roster grounds** for a reason that cannot be explained by what the page displayed. This binds refusals about people; it says nothing about a write failing for other reasons, which is the subject of *A write that fails is never silent* below.

#### Scenario: A write names a person the page offered

- **WHEN** an author saves a step naming an assignee the page offered them in the assignee control
- **THEN** the write is judged on the rules, not refused for being unable to read the roster
- **AND** the step is saved naming that person

#### Scenario: Each write reaches the roster

- **WHEN** a create, an edit, a status change, a retirement or an un-retirement is submitted from the page
- **THEN** each one evaluates its roster preconditions against the roster the page reads

#### Scenario: A roster refusal is explicable from the page

- **WHEN** a write is refused on roster grounds
- **THEN** the refusal concerns people the page displayed or offered, and never the page's inability to read the roster at all

### Requirement: A write that fails is never silent

Every write the page offers SHALL report its outcome to the admin. A write that is refused renders its faults, as this capability already requires. A write that fails for a reason the page has no fault rendering for SHALL still be reported.

No write SHALL be able to leave the page in a state indistinguishable from one where nothing was submitted, and no failed write SHALL be able to leave the page looking as though it succeeded. This binds every write on the page, whether submitted as an ordinary form post or through the page's progressive enhancement — an enhancement that discards a failed response is exactly how a whole page of broken writes went unnoticed. It binds all three ways such a submission can fail: a response the page cannot render, no response at all, and a response that never arrives in time.

What the report SHALL say is bounded by what the page can establish. The page observes that a submission did not complete; it does **not** observe whether anything was persisted, because a failure raised after the set was written produces the same response as one raised before it. The report SHALL therefore state that the write did not complete and that what the page is showing may no longer describe the step set, and SHALL direct the admin to reload to see the set as it stands. It SHALL NOT assert that nothing was saved.

The report SHALL be observable in the rendered response. The container it renders into SHALL carry the literal marker `write-failure-notice`, which names the container's **role** and is therefore present on every admin page whether or not anything has failed; the marker `write-failed` SHALL appear only once a failure has actually been reported into it. The distinction is the one this capability already draws for `just-created` — a marker that asserts an occurrence must never outrun the occurrence. Whether the notice then *appears* on a live failure is confirmed by inspection; that there is a container for it to appear in is not.

Which submissions this page enhances is fixed here rather than left to the templates to decide, because two of the clauses below turn on it: as of this change the step list and the edit surface are enhanced, and the create surface is not. A later change to that set SHALL amend this requirement rather than silently narrow what an admin is told — otherwise un-boosting a form would shrink the guarantee with no test failing and nothing recording that it had shrunk.

Where a submission the page enhances fails because the admin's own session has ended, the report SHALL say so and offer the way back, rather than presenting an expired session as an unexplained failure — it is the one case in this class the admin can act on directly. The page SHALL reach that reading from what it already knows (it posted to a route it had just rendered, so a refusal of that route is the guard's), and SHALL NOT require the server to mark the refusal. The guard's answer to a write SHALL stay indistinguishable from an unregistered route's — the shape `playbook-admin` already describes for every unauthorised admin path, and binding here on this requirement's own account.

A submission the page does **not** enhance — one deliberately left un-boosted, or any submission where the enhancement is unavailable — satisfies this requirement through the browser's own rendering of the failure. That is less legible and carries none of the wording above, and it is accepted: what this requirement forbids is silence, not inelegance.

#### Scenario: An unanticipated failure is reported

- **WHEN** a write fails with a response the page has no fault rendering for
- **THEN** the page reports that the write did not complete and directs the admin to reload

#### Scenario: A failure with no response is reported too

- **WHEN** a write submitted through the page's progressive enhancement receives no response, or none in time
- **THEN** the page reports it exactly as it reports a failed response, rather than remaining as it was

#### Scenario: The report does not claim what the page cannot know

- **WHEN** any such failure is reported
- **THEN** the report does not state that nothing was saved

#### Scenario: A failed write does not read as a successful one

- **WHEN** a write fails before the set is written
- **THEN** the page does not render as though the write was accepted, and the step set is unchanged

#### Scenario: A failed write does not read as an unsubmitted one

- **WHEN** a write submitted through the page's progressive enhancement fails
- **THEN** the page changes in a way the admin can see, rather than remaining exactly as it was before submitting

#### Scenario: The report is observable in the response

- **WHEN** an admin page the failure report can render into is served
- **THEN** it carries a container marked `write-failure-notice`, so a response can be asked whether there is somewhere for the report to appear
- **AND** that container carries `write-failed` only once a failure has been reported into it

#### Scenario: An ended session says so

- **WHEN** a submission from the step list or the edit surface fails because the admin's session is no longer live
- **THEN** the page says the session ended and offers the way back, rather than reporting an unexplained failure

#### Scenario: The guard's refusal stays indistinguishable

- **WHEN** the page distinguishes an ended session from any other failure
- **THEN** it does so from what it already knew about the route it posted to, and the server's refusal is not marked to make it recognisable

#### Scenario: A failure is visible on a submission the page does not enhance

- **WHEN** a write fails on a submission from the create surface, or on any submission where the enhancement is unavailable
- **THEN** the failure is still visible to the admin, even if less legibly presented and without the wording above
