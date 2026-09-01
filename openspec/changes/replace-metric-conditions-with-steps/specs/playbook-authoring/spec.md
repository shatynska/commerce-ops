## MODIFIED Requirements

### Requirement: A step can be created

The system SHALL allow a new step definition to be created with the full authorable shape: name, optional description, gate, discipline, scope, timing anchor, blocking flag, kind, status, hazard, optional assignees, an optional confirmer, an optional start gate, an optional set of steps it waits on, an optional metric identifier, and — for an `automated` step — an optional handler. The system SHALL generate the created step's identifier — the author does not choose it — in a namespace distinct from the seeded set's, carrying the step's discipline as its second segment (`mg.creative.001` is a `creative` step), so a step's origin and discipline stay legible from its identifier alone. The created step's provenance SHALL record the authoring principal and the creation date.

A step created as `active` SHALL be part of the served step set on the next read; a step created in any other status SHALL NOT be served, and SHALL be readable in the authored set. Creating a step as a `draft` SHALL require only what a draft carries, so that work can be written down before it is ready — which is the point of the status existing.

#### Scenario: A created step joins the served set

- **WHEN** a step is created as `active` with valid authorable fields
- **THEN** the next read of the playbook serves it, carrying a generated identifier whose second segment is its discipline
- **AND** its provenance records who created it and when

#### Scenario: Created identifiers never collide with the seeded namespace

- **WHEN** a step is created
- **THEN** its generated identifier is not in the seeded set's namespace and equals no existing step's identifier, retired steps included

#### Scenario: A step is created declaring when it starts

- **WHEN** a step is created declaring a start gate and one or more steps it waits on
- **THEN** both are persisted and read back on the created step

#### Scenario: A step is created declaring neither

- **WHEN** a step is created declaring no start gate and no steps it waits on
- **THEN** it is created, and is eligible from a launch's first gate

### Requirement: Authoring never touches the framework

Write operations SHALL be limited to step definitions. The gate sequence and each gate's opening mode SHALL NOT be creatable, updatable, or removable through this capability — the framework is owned by the repository and changes only by a repository change.

The framework is smaller than it was. A gate now carries its sequence position and its opening mode and nothing else: what a gate waits on is stated by its steps, which are authorable. A threshold a gate turns on is therefore editable, as the description of the step that establishes it, by whoever may edit that step — no longer a repository change. This is the intended consequence of expressing every gate obligation as a step, not an incidental widening: the numbers a launch is held to are the team's to revise, while the sequence they are revised within is not.

#### Scenario: The framework is not writable

- **WHEN** the authoring operations are enumerated
- **THEN** none of them accepts a gate or an opening mode as a writable target

#### Scenario: A threshold is editable as the step that states it

- **WHEN** a step declaring a metric identifier has its description updated through the authoring operations
- **THEN** the write is validated and persisted like any other step update, and the served step carries the new text

## ADDED Requirements

### Requirement: A step's metric identifier is authorable

The authoring operations SHALL accept a step's metric identifier as a writable field, settable when a step is created and changeable when it is updated, and SHALL accept its absence — almost every step declares none. A write supplying a metric identifier SHALL be validated by the same whole-set validation every other write obeys, and SHALL be rejected where the identifier is not one the shared vocabulary accepts.

No write SHALL be rejected because the metric a valid identifier names is undefined. Nothing defines metrics yet, so a rule requiring the identifier to resolve would reject every write of every metric step; the identifier is a reference to be resolved later, exactly as `launch-playbook` states it.

#### Scenario: A step is created declaring a metric identifier

- **WHEN** a step is created with a metric identifier the shared vocabulary accepts
- **THEN** the write is persisted and the served step reports that identifier

#### Scenario: A step's metric identifier is changed

- **WHEN** an update supplies a metric identifier different from the one the step carries
- **THEN** the write is persisted and the served step reports the new identifier

#### Scenario: A step is created declaring no metric identifier

- **WHEN** a step is created supplying no metric identifier
- **THEN** the write is persisted and the served step reports none

#### Scenario: An invalid metric identifier is rejected

- **WHEN** a write supplies a metric identifier the shared vocabulary rejects — empty, or carrying leading or trailing whitespace
- **THEN** the write is rejected and nothing is persisted

#### Scenario: An identifier naming no defined metric is accepted

- **WHEN** a write supplies a well-formed metric identifier naming a metric nothing defines
- **THEN** the write is persisted, because no registry exists against which to resolve it
