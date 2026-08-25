# playbook-admin Specification

## Purpose
The steps management page: lets a signed-in admin see the authored step set whole — every status other than `retired`, grouped by gate, filterable and searchable, with the served steps set apart from the ones that are not — and change it in place through the validated authoring writes: inline edit, create, status change, retire and un-retire, and reordering a gate's active steps, with every rejected write rendering its full fault list.

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

#### Scenario: A clean edit lands

- **WHEN** an edit with valid values is saved
- **THEN** the step re-renders with the new values

#### Scenario: A rejected edit shows every fault

- **WHEN** a submitted edit violates two coherence rules at once
- **THEN** the re-rendered form reports both faults
- **AND** the submitted values are still in the form
- **AND** the served step set is unchanged

#### Scenario: A stale edit is surfaced, not silently dropped

- **WHEN** an edit is submitted after another write has changed the step set
- **THEN** nothing is persisted and the page states the set changed underneath the edit

### Requirement: Steps can be created, retired and un-retired from the page

The page SHALL offer creating a step with the full authorable shape — the identifier is generated, never asked for — and retiring or un-retiring a step. Each flow SHALL go through the corresponding authoring write, and a rejection SHALL render its full fault list the same way a rejected edit does.

#### Scenario: A created step appears in its gate

- **WHEN** a step is created from the page with valid fields
- **THEN** the table shows it as the last step of its gate, carrying its generated identifier

#### Scenario: A blocked retirement explains itself

- **WHEN** retiring a step is rejected because its gate would be left with no blocking step
- **THEN** the page renders the fault naming that gate and the step remains live

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
description search, and whether retired steps are shown. Navigation
between the list and a step's edit form SHALL carry that narrowing too,
in both directions, and so SHALL the control that reveals or hides
retired steps.

Where a write re-renders the list, it SHALL render it under that
narrowing. Where a write re-renders some other view — a rejected edit
re-renders the edit form, as the editing requirement demands — the
narrowing SHALL be preserved so that the next render of the list applies
it. A write SHALL NOT widen, clear, or otherwise alter what the page
shows beyond the effect of the write itself.

#### Scenario: An accepted write keeps the narrowing

- **WHEN** a step is retired while a gate filter and a discipline filter are active
- **THEN** the re-rendered list still applies both filters
- **AND** shows the same gate and discipline selections as before the write

#### Scenario: A rejected list-level write keeps the narrowing

- **WHEN** a retirement is rejected while a description search is active
- **THEN** the re-rendered list reports the faults
- **AND** still applies the search term

#### Scenario: A rejected edit keeps the narrowing without leaving the form

- **WHEN** an edit is rejected while a gate filter is active
- **THEN** the edit form re-renders with its faults and the submitted values, as the editing requirement requires
- **AND** returning to the list from that form applies the gate filter

#### Scenario: Opening and leaving an edit form preserves the narrowing

- **WHEN** a step's edit form is opened from a narrowed list and left without saving
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
