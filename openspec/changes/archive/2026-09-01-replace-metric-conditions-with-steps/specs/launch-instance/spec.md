## MODIFIED Requirements

### Requirement: A launch position is persisted for a catalog product

The system SHALL persist a launch record carrying: a reference to a catalog product by its product identifier, the `launch-playbook` version identifier the launch was started under (recorded at start as an audit stamp, never changed for the life of the launch, and read through by no behavior — every read of the playbook serves the live step set), the current gate, an optional launch date, the per-step progress recorded so far, and the gate approvals recorded so far. At most one launch record SHALL exist per product. Creating a launch for a product identifier that no catalog product has SHALL be rejected. Starting a launch SHALL be reported as a `LaunchStarted` occurrence carrying the product identifier and the recorded version identifier.

#### Scenario: A launch position is created for an existing product

- **WHEN** a launch is started for a registered catalog product, with no launch date
- **THEN** the record is persisted referencing that product with the served playbook's version identifier recorded, the launch date is reported as absent, and a `LaunchStarted` occurrence is reported

#### Scenario: A launch position for an unknown product is rejected

- **WHEN** a launch is started for a product identifier no catalog product has
- **THEN** the start is rejected and nothing is persisted

#### Scenario: A second launch position for the same product is rejected

- **WHEN** a launch is started for a product that already has a launch record
- **THEN** the start is rejected and the existing record is unchanged

### Requirement: A launch position can be read back by product identifier

The system SHALL retrieve a persisted launch record given the product identifier it references — the recorded version identifier, current gate, launch date, every recorded step progress with its provenance, and every gate approval — and SHALL report absence rather than an error when the product has no launch record.

A read made on a caller's behalf SHALL additionally be subject to that caller's access scope: a launch whose product identifier the scope does not permit SHALL report the same absence as a product with no launch record, so that a read can never confirm the existence of a launch the caller may not see. The scope decides whether a read yields a record at all; it SHALL NOT change what a retrieved record carries, and it SHALL NOT require any particular read to carry the whole persisted record.

#### Scenario: A launch position is retrieved

- **WHEN** a launch that has recorded step outcomes and a gate approval is read using its product identifier
- **THEN** the record is returned with the recorded version identifier, current gate, launch date, each step's outcome and provenance, and each approval it was persisted with

#### Scenario: A product without a launch position reports absence

- **WHEN** a launch record is read for a product identifier that has none, under any scope
- **THEN** the system reports that none exists, rather than an error

#### Scenario: An out-of-scope launch reports the same absence

- **WHEN** a launch record is read on a caller's behalf for a product identifier that caller's scope does not permit
- **THEN** the system reports that none exists, exactly as it does for a product with no launch record

### Requirement: A step outcome is recorded with provenance

The system SHALL record, against a launch, an outcome for a step the served playbook defines, using the `launch-playbook` outcome vocabulary (`NotStarted`, `InProgress`, `Satisfied`, `Blocked` with a reason, `Refused`, `NotApplicable` with a reason). Every recorded outcome — non-terminal ones included — SHALL carry recording provenance: a source (`clickup` or `automated`), who recorded it, when, and evidence. Completion is always recorded, never inferred. Terminal outcomes SHALL be restricted by the step's hazard as `launch-playbook` defines: a `prohibited-tactic` step can only terminate in `Refused`; any other step terminates in `Satisfied` or `NotApplicable` and can never be `Refused`. A later recording for the same step SHALL replace the stored outcome and its provenance — the hazard restrictions apply to every recording — and a re-recording SHALL NOT reverse a gate that has already opened. Recording an outcome for a step identifier the served playbook does not define — an identifier that never existed and a retired step's alike — SHALL be rejected; outcomes already recorded against a step before its retirement remain stored and readable. A step reaching `Satisfied` SHALL be reported as a `StepSatisfied` occurrence; a step reaching `Refused` SHALL be reported as a `StepRefused` occurrence.

A step establishing a metric is recorded through this same path, with the source that recorded it — there is no source naming the significance of the step rather than the channel the outcome arrived through.

#### Scenario: A satisfied step is recorded with its provenance

- **WHEN** a `Satisfied` outcome is recorded for a defined step with source `clickup`, a named recorder, a timestamp, and evidence
- **THEN** reading the launch back reports that step's outcome as `Satisfied` with exactly that provenance, and a `StepSatisfied` occurrence is reported

#### Scenario: A re-recorded outcome replaces the stored one without reopening gates

- **WHEN** a step recorded as `Satisfied` is later re-recorded as `Blocked` with a reason, after the gate it is attached to has already opened
- **THEN** the stored outcome and provenance are replaced, and the launch's current gate is unchanged

#### Scenario: A prohibited-tactic step is refused

- **WHEN** a `Refused` outcome is recorded for a step classified `prohibited-tactic`
- **THEN** the outcome is recorded and a `StepRefused` occurrence is reported

#### Scenario: Satisfying a prohibited-tactic step is rejected

- **WHEN** a `Satisfied` outcome is recorded for a step classified `prohibited-tactic`
- **THEN** the recording is rejected and the step's stored outcome is unchanged

#### Scenario: Refusing an ordinary step is rejected

- **WHEN** a `Refused` outcome is recorded for a step not classified `prohibited-tactic`
- **THEN** the recording is rejected and the step's stored outcome is unchanged

#### Scenario: An unknown step identifier is rejected

- **WHEN** an outcome is recorded for a step identifier the served playbook does not define
- **THEN** the recording is rejected

### Requirement: A gate opens only when every blocking condition attached to it is satisfied

A launch SHALL advance from its current gate only to the next gate in the `launch-playbook` sequence — gates advance monotonically, are never skipped, and never move backwards. The current gate SHALL open only when every blocking condition attached to it is satisfied: every step obligation (a blocking step attached to the gate) has reached a permitted terminal outcome (`Satisfied` or `NotApplicable`). A `Refused` outcome never satisfies any condition. Advancing SHALL be reported as a `GateOpened` occurrence; an advance attempted while any blocking condition is unsatisfied SHALL be rejected and reported as a `GateBlocked` occurrence naming each unsatisfied condition.

A gate waits on its blocking steps and on nothing else, so a threshold a gate turns on holds it as the obligation of the step that establishes it, satisfied by that step's recorded outcome.

#### Scenario: An automatic gate opens when every blocking condition is satisfied

- **WHEN** every blocking condition attached to the current automatic gate is satisfied and the launch is advanced
- **THEN** the current gate becomes the next gate in the sequence and a `GateOpened` occurrence is reported

#### Scenario: An advance with an unresolved blocking step is rejected

- **WHEN** the launch is advanced while a blocking step attached to the current gate has not reached a permitted terminal outcome
- **THEN** the advance is rejected, the current gate is unchanged, and a `GateBlocked` occurrence names that unsatisfied condition

#### Scenario: A refused prohibited-tactic step never holds a gate closed

- **WHEN** a non-blocking `prohibited-tactic` step attached to the current gate is `Refused` and every blocking condition attached to that gate is satisfied
- **THEN** the launch advances — refusal neither satisfies nor blocks any condition

#### Scenario: An advance moves to exactly the next gate

- **WHEN** the launch advances from its current gate
- **THEN** the current gate becomes exactly the next gate in the `launch-playbook` sequence — the advance operation offers no way to target a later or an earlier gate, so gates can never be skipped and never move backwards

#### Scenario: An unresolved metric step holds its gate closed

- **WHEN** the launch is advanced while a blocking step declaring a metric identifier, attached to the current gate, has no permitted terminal outcome
- **THEN** the advance is rejected and a `GateBlocked` occurrence names that step, exactly as for any other blocking step


## REMOVED Requirements

### Requirement: A metric condition is satisfied by human attestation until live evaluation exists

**Reason**: `launch-playbook` no longer authors metric conditions on gates, so there is nothing for an attestation to satisfy. The obligation each condition expressed is now a blocking step, satisfied by a recorded step outcome through the path every other obligation already uses. Attestation was in any case unreachable: no driving adapter ever called it, so no condition was ever satisfied by one and every gate authoring a condition stalled indefinitely.

**Migration**: A gate that authored a metric condition now carries a blocking step declaring the same metric identifier; recording that step's outcome opens the gate. The persisted attestation store is dropped, having never held a row. A launch standing at a gate whose condition was unattested advances on that gate's remaining obligations, which is a state change to verify against production before the drop runs.
