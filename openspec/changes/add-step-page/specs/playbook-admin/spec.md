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
still holding **every** submitted value — the discipline and the timing
anchor's inputs included — carrying every fault the write reported. This
is the guarantee a rejected edit already carries. A create rejected
because the step set changed underneath it SHALL persist nothing, say
so, and likewise keep what was typed.

Leaving the create surface without creating SHALL return to the step
list narrowed as it was when the create surface was opened. A create
that lands SHALL likewise return to the step list under that same
narrowing, with the created step in view. Where the active narrowing
would hide the created step, the list SHALL render under that narrowing
and SHALL state that the created step falls outside it, offering to
clear it — a create SHALL NOT appear to have been lost.

#### Scenario: Creating is reachable regardless of how large the set is

- **WHEN** the admin page is opened with the full live step set rendered
- **THEN** a control opening the create surface is rendered ahead of the
  gate tables
- **AND** no create form is rendered within or after the gate tables

#### Scenario: A created step appears in its gate

- **WHEN** a step is created from the create surface with valid fields,
  under a narrowing the created step matches
- **THEN** the step list is shown again under that narrowing, with the
  created step in view, as the last step of its gate, carrying its
  generated identifier

#### Scenario: A create the narrowing would hide is not left looking lost

- **WHEN** a step is created while a description search is active that
  the created step's description does not match
- **THEN** the step list is shown under that search
- **AND** states that the created step falls outside the active
  narrowing, offering to clear it

#### Scenario: A rejected create keeps every submitted value

- **WHEN** a submitted create is rejected by validation
- **THEN** the re-rendered create surface reports every fault the write
  reported
- **AND** every submitted value, the timing anchor's included, is still
  in the form
- **AND** the served step set is unchanged

#### Scenario: A rejected create keeps the submitted discipline

- **WHEN** a create submitting a discipline other than the first offered
  is rejected by validation
- **THEN** the re-rendered create surface still shows the submitted
  discipline selected
- **AND** a corrected resubmission generates an identifier carrying that
  discipline

#### Scenario: A stale create is surfaced, not silently dropped

- **WHEN** a create is submitted after another write has changed the
  step set
- **THEN** nothing is persisted and the surface states the set changed
  underneath the create
- **AND** the submitted values are still in the form

#### Scenario: Leaving the create surface returns to the narrowed list

- **WHEN** the create surface is opened from a list narrowed by a gate
  filter, a discipline filter or a search term, and is left without
  creating
- **THEN** the step list is shown narrowed exactly as it was

#### Scenario: A blocked retirement explains itself

- **WHEN** retiring a step is rejected because its gate would be left
  with no blocking step
- **THEN** the page renders the fault naming that gate and the step
  remains live

### Requirement: The narrowed view survives every write and every move between views

Every write made from the page — an edit, a creation, a retirement, an
un-retirement, a reorder — SHALL carry forward the narrowing that was
active when it was made: the gate filter, the discipline filter, the
description search, and whether retired steps are shown. Navigation
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

- **WHEN** a retirement is rejected while a description search is active
- **THEN** the re-rendered list reports the faults
- **AND** still applies the search term

#### Scenario: A rejected creation keeps the narrowing without leaving the create surface

- **WHEN** a creation is rejected while a description search is active
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

### Requirement: The timing anchor offers only the inputs its selected kind uses

A step's timing anchor takes different inputs depending on its kind. An
authoring surface SHALL render, as offered, only the inputs the anchor
kind it was rendered with actually uses; the inputs belonging to the
other kinds SHALL be rendered as not offered. Which kind a surface is
rendered with is the step's own on a fresh edit, the submitted one
around a rejection, and the default on a fresh create.

Inputs rendered as not offered SHALL retain whatever value they carry,
so that a kind selected and then reconsidered does not discard what was
already entered.

#### Scenario: Only the selected kind's inputs are offered

- **WHEN** an authoring surface is rendered with the anchor kind
  `offset`
- **THEN** the inputs the `offset` kind uses are rendered as offered
- **AND** the inputs belonging only to the other anchor kinds are
  rendered as not offered

#### Scenario: A rejection re-renders against the submitted kind

- **WHEN** a write submitting the anchor kind `window` is rejected
- **THEN** the re-rendered surface offers the inputs the `window` kind
  uses
- **AND** the inputs belonging only to the other anchor kinds are
  rendered as not offered
- **AND** the values submitted for those other kinds are retained
