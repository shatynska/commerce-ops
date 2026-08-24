## Purpose

The steps management page: lets a signed-in admin see the live step set whole — grouped by gate, filterable and searchable — and change it in place through the validated authoring writes: inline edit, create, retire and un-retire, and reordering a gate's steps, with every rejected write rendering its full fault list.

## ADDED Requirements

### Requirement: The step table shows the live set whole

The admin page SHALL render every live step of the served playbook in one table, grouped by gate in the gate sequence's order, with each gate's steps in their authored order. The table SHALL be filterable by gate and by discipline, and searchable by description text; an active filter or search narrows what is shown without changing the underlying set. Retired steps SHALL NOT appear in the default view, but SHALL be reachable through an explicit control that shows them marked as retired, so that un-retiring is possible from the page.

#### Scenario: The whole live set is one page

- **WHEN** the admin page is opened with no filter active
- **THEN** every live step is rendered, grouped by gate in gate order, each gate's steps in authored order

#### Scenario: Filters narrow without altering

- **WHEN** a gate filter and a discipline filter are applied together
- **THEN** only live steps matching both remain visible
- **AND** clearing the filters shows the full set unchanged

#### Scenario: Search matches description text

- **WHEN** a search term is entered
- **THEN** only steps whose description contains the term remain visible

#### Scenario: Retired steps are reachable but set apart

- **WHEN** the control revealing retired steps is engaged
- **THEN** retired steps render visibly marked as retired
- **AND** they are absent from the default view

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

The page SHALL let a step be moved to a different position among its gate's steps, persisted through the authoring reorder write. The new order SHALL be visible immediately after the move and identical on the next full page load. A rejected reorder — including one rejected because the step set changed underneath it — SHALL leave the rendered order matching the served set and say why.

#### Scenario: A move sticks

- **WHEN** a step is moved to the top of its gate on the page
- **THEN** the page shows it first in its gate
- **AND** a fresh page load shows the same order

#### Scenario: A stale move leaves truth on the page

- **WHEN** a reorder is rejected because the step set changed underneath it
- **THEN** the page re-renders the served order and states why the move did not land

### Requirement: What authoring refuses to update renders read-only

Fields the authoring capability does not accept updates to — a step's identifier and its discipline — and framework-owned facts such as a step's provenance SHALL render as read-only on the page, never as editable inputs whose submission would be refused.

#### Scenario: The identifier cannot be typed into

- **WHEN** a step's inline edit form is opened
- **THEN** the identifier and discipline render as text, not as inputs
