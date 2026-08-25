# playbook-authoring Specification

## Purpose
Lets the step set of the launch playbook be authored at runtime — steps created, updated, and moved through their lifecycle status (activated, de-activated, retired and un-retired) by validated write operations — while the framework the steps hang on (the gates, their opening modes, their metric conditions, the coherence rules) stays owned by the repository. Only an `active` step is served to a launch, so activation is a deliberate act validated against what the step's kind requires of it.

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

### Requirement: A gate's steps can be reordered

The system SHALL allow a step to be moved to a chosen position among the live steps of its own gate. The write SHALL renumber the gate's live steps as one atomic operation, so that after it every live step of the gate holds a distinct slot and the relative order of the steps that were not moved is preserved. Reordering SHALL be subject to the same whole-set validation and write serialization as every other authoring write — a reorder concurrent with another accepted write on a stale view of the set SHALL be rejected without persisting anything. The reorder's principal and date SHALL be recorded against the moved step, as an update's are. The new order SHALL be served on the next read. A reorder addresses a position among the step's own gate's live steps only, and SHALL NOT change the step's gate or any other of its fields — changing a step's gate is an update to the step's gate field.

A reorder MAY be submitted against a caller-supplied view of the set —
the set version the chosen position was computed from. Where one is
supplied, the reorder SHALL be rejected unless that version is the
version the write itself reads, and SHALL NOT be retried against a newer
view: a position computed against one view of the set carries no meaning
against another. Rejection SHALL NOT depend on the supplied version being
older than the one read — a supplied version that does not match is
refused whichever way it differs, so that a value the caller does not
hold cannot be presented as a view of the set. Where no view is supplied,
the position is understood to be computed against whatever view the write
itself reads, and the write MAY resolve a concurrent write by re-reading
and recomputing.

#### Scenario: A moved step is served in its new slot

- **WHEN** a gate's third step is moved to the gate's first position
- **THEN** the next read serves that gate's steps with the moved step first
- **AND** the remaining steps keep their previous relative order
- **AND** the move's principal and date are recorded against the moved step

#### Scenario: A stale reorder is rejected whole

- **WHEN** a reorder is submitted against a version of the step set that a later accepted write has superseded
- **THEN** the reorder is rejected and the served order is unchanged

#### Scenario: A reorder never leaves the step's own gate

- **WHEN** a step is moved to any accepted position
- **THEN** the step's gate and every other field are unchanged
- **AND** the order of every other gate's steps is unchanged

#### Scenario: A supplied view is not retried past

- **WHEN** a reorder supplying the set version its position was computed from meets a set that a later accepted write has moved past
- **THEN** the reorder is rejected without persisting anything
- **AND** the position is not recomputed and reapplied against the newer set

#### Scenario: A supplied view that does not match is refused whichever way it differs

- **WHEN** a reorder supplies a set version that is not the version the write reads, and is not an earlier one
- **THEN** the reorder is rejected without persisting anything

#### Scenario: A reorder without a supplied view still resolves concurrency

- **WHEN** a reorder supplying no view of the set meets a concurrent accepted write
- **THEN** the write may re-read the set and apply the chosen position against it

### Requirement: Every live step holds a slot in its gate's order

Each gate's live steps SHALL stand in a single authored order at all times. The step set as it stands when this capability arrives SHALL keep the order it was being served in as its initial authored order. A created step SHALL take the last slot of its gate. An un-retired step SHALL rejoin as the last slot of its gate rather than reclaiming a remembered position. An update that changes a step's gate SHALL place the step in the last slot of its new gate. Retiring a step SHALL remove it from its gate's live order without disturbing the relative order of the steps that remain.

#### Scenario: A created step appends to its gate

- **WHEN** a step is created for a gate that already has live steps
- **THEN** the next read serves it as that gate's last step

#### Scenario: An un-retired step rejoins at the end

- **WHEN** a step is retired and later un-retired
- **THEN** the next read serves it as the last step of its gate, whatever slot it held before retirement

#### Scenario: A gate change appends to the new gate

- **WHEN** an update moves a step to a different gate
- **THEN** the next read serves it as the last step of its new gate
- **AND** the steps of its old gate keep their relative order

#### Scenario: Retirement closes the gap

- **WHEN** a step is retired from the middle of its gate's order
- **THEN** the next read serves the gate's remaining steps in their previous relative order with no gap in the listing
