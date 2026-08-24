# playbook-authoring Specification

## Purpose
Lets the step set of the launch playbook be authored at runtime — steps created, updated, retired and un-retired through validated write operations — while the framework the steps hang on (the gates, their opening modes, their metric conditions, the coherence rules) stays owned by the repository.

## Requirements

### Requirement: A step can be created

The system SHALL allow a new step definition to be created with the full authorable shape: description, gate, discipline, scope, timing anchor, binding, blocking flag, execution mode, hazard, and optional rule policy. The system SHALL generate the created step's identifier — the author does not choose it — in a namespace distinct from the seeded set's, carrying the step's discipline as its second segment (`mg.creative.001` is a `creative` step), so a step's origin and discipline stay legible from its identifier alone. The created step's provenance SHALL record the authoring principal and the creation date. A created step SHALL be part of the served step set on the next read.

#### Scenario: A created step joins the served set

- **WHEN** a step is created with valid authorable fields
- **THEN** the next read of the playbook serves it, carrying a generated identifier whose second segment is its discipline
- **AND** its provenance records who created it and when

#### Scenario: Created identifiers never collide with the seeded namespace

- **WHEN** a step is created
- **THEN** its generated identifier is not in the seeded set's namespace and equals no existing step's identifier, retired steps included

### Requirement: A step can be updated

The system SHALL allow an existing step's authorable fields to be updated — seeded and authored steps alike. A step's identifier SHALL NOT be updatable, and neither SHALL its discipline: every identifier's second segment carries the discipline, and other capabilities compose surfaces that rely on that segment telling the truth, so changing a step's discipline is done by retiring the step and creating its successor. An update SHALL record the updating principal and date alongside the step's existing provenance, so a seeded step's reference citation survives its first edit while the edit itself is attributed. An updated step SHALL be served with its new field values on the next read.

#### Scenario: An edit is served on the next read

- **WHEN** a step's description is updated
- **THEN** the next read of the playbook serves the step with the new description under its unchanged identifier

#### Scenario: A discipline change is rejected

- **WHEN** an update attempts to change a step's discipline
- **THEN** the update is rejected and the step is unchanged

#### Scenario: An edit to a seeded step keeps its citation and gains attribution

- **WHEN** a seeded step is updated
- **THEN** its provenance still carries the reference row's source citation
- **AND** the update's principal and date are recorded

### Requirement: A step can be retired and un-retired

The system SHALL allow a step to be retired rather than deleted: a retired step is excluded from the served step set, but its stored definition, its identifier, and every outcome recorded against it persist, so history stays interpretable. Retiring SHALL record the retiring principal and date. The system SHALL allow a retired step to be un-retired, restoring it to the served set; un-retiring SHALL likewise record the principal and date, so a reversal of retirement is as attributed as the retirement was. No operation SHALL delete a step.

#### Scenario: A retired step leaves the served set

- **WHEN** a step is retired
- **THEN** the next read of the playbook does not serve it
- **AND** its stored definition and identifier persist, with the retirement's principal and date recorded

#### Scenario: A retired step's history stays readable

- **WHEN** outcomes were recorded against a step and the step is then retired
- **THEN** those recorded outcomes remain readable and still name the step's identifier

#### Scenario: An un-retired step rejoins the served set

- **WHEN** a retired step is un-retired
- **THEN** the next read of the playbook serves it again under its original identifier
- **AND** the un-retirement's principal and date are recorded

### Requirement: Every write is validated as the playbook it would produce

A create, update, retire or un-retire SHALL be validated by evaluating the **entire step set as it would stand after the write** against the launch playbook's coherence rules, and SHALL be rejected whole when that resulting set is incoherent — nothing of a rejected write is persisted. The rejection SHALL report **every** fault found, each naming the offending step or gate, exactly as loading an incoherent playbook does; write-side validation and load-side validation SHALL apply the same rules, so no write can persist a set that a load would reject. This includes rejecting a write that would leave any gate without a blocking step.

#### Scenario: A rejected write reports all faults and persists nothing

- **WHEN** an update would leave a step's description empty and would also mark a `lesson`-bound step as blocking
- **THEN** the write is rejected reporting both faults
- **AND** the served step set is unchanged

#### Scenario: Retiring a gate's last blocking step is rejected

- **WHEN** a retire targets the only blocking step attached to a gate
- **THEN** the write is rejected, naming the gate that would be left unheld

#### Scenario: What a write cannot persist, a load cannot see

- **WHEN** any sequence of accepted writes has been applied
- **THEN** loading the playbook succeeds — the served set is coherent by construction

### Requirement: Authoring never touches the framework

Write operations SHALL be limited to step definitions. The gate sequence, each gate's opening mode, and each gate's authored metric conditions SHALL NOT be creatable, updatable, or removable through this capability — the framework is owned by the repository and changes only by a repository change.

#### Scenario: The framework is not writable

- **WHEN** the authoring operations are enumerated
- **THEN** none of them accepts a gate, an opening mode, or a metric condition as a writable target
