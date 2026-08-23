## MODIFIED Requirements

### Requirement: A launch position is persisted for a catalog product

The system SHALL persist a launch record carrying: a reference to a catalog product by its product identifier, the `launch-playbook` version the launch runs under (pinned at start and never changed for the life of the launch), the current gate, an optional launch date, the per-step progress recorded so far, the gate approvals recorded so far, and the metric attestations recorded so far. At most one launch record SHALL exist per product. Creating a launch for a product identifier that no catalog product has SHALL be rejected. Starting a launch SHALL be reported as a `LaunchStarted` occurrence carrying the product identifier and the pinned playbook version.

#### Scenario: A launch position is created for an existing product

- **WHEN** a launch is started for a registered catalog product against a playbook version, with no launch date
- **THEN** the record is persisted referencing that product with that version pinned, the launch date is reported as absent, and a `LaunchStarted` occurrence is reported

#### Scenario: A launch position for an unknown product is rejected

- **WHEN** a launch is started for a product identifier no catalog product has
- **THEN** the start is rejected and nothing is persisted

#### Scenario: A second launch position for the same product is rejected

- **WHEN** a launch is started for a product that already has a launch record
- **THEN** the start is rejected and the existing record is unchanged

### Requirement: A product's current gate is restricted to the launch-playbook gate sequence

A launch record's current gate SHALL be one of the eight gate ids `launch-playbook` defines (`commit`, `order`, `listable`, `stock-ready`, `live`, `ignition`, `phase-one-complete`, `graduated`). A newly started launch SHALL begin at `commit`, the first gate in that sequence; a launch is never started at any other gate. Persisting a current gate outside the eight SHALL be rejected.

#### Scenario: A new product defaults to the first gate

- **WHEN** a launch is started
- **THEN** its current gate is reported as `commit`

#### Scenario: An unrecognized gate is rejected

- **WHEN** an attempt is made to persist a launch record whose current gate is not one of the eight `launch-playbook` gate ids
- **THEN** the operation is rejected and the stored gate is unchanged

### Requirement: A launch position can be read back by product identifier

The system SHALL retrieve a persisted launch record given the product identifier it references — the pinned playbook version, current gate, launch date, every recorded step progress with its provenance, every gate approval, and every metric attestation — and SHALL report absence rather than an error when the product has no launch record.

#### Scenario: A launch position is retrieved

- **WHEN** a launch that has recorded step outcomes, a gate approval, and a metric attestation is read using its product identifier
- **THEN** the record is returned with the pinned version, current gate, launch date, each step's outcome and provenance, each approval, and each attestation it was persisted with

#### Scenario: A product without a launch position reports absence

- **WHEN** a launch record is read for a product identifier that has none
- **THEN** the system reports that none exists, rather than an error

## REMOVED Requirements

### Requirement: A product's current gate can be updated

**Reason**: Free-form current-gate updates deliberately did not validate transitions, as a stopgap until the launch aggregate existed. They permitted skipping gates, moving backwards, and opening gates whose conditions were unsatisfied — all of which the gate-advance requirements below now forbid.

**Migration**: The stored gate changes only through gate advancement ("A gate opens only when every blocking condition attached to it is satisfied"). Existing launch-position rows carry over unchanged; only the unvalidated mutation path is retired.

## ADDED Requirements

### Requirement: A step outcome is recorded with provenance

The system SHALL record, against a launch, an outcome for a step the pinned playbook version defines, using the `launch-playbook` outcome vocabulary (`NotStarted`, `InProgress`, `Satisfied`, `Blocked` with a reason, `Refused`, `NotApplicable` with a reason). Every recorded outcome — non-terminal ones included — SHALL carry recording provenance: a source (`clickup`, `automated`, or `attestation`), who recorded it, when, and evidence. Completion is always recorded, never inferred. Terminal outcomes SHALL be restricted by the step's hazard as `launch-playbook` defines: a `prohibited-tactic` step can only terminate in `Refused`; any other step terminates in `Satisfied` or `NotApplicable` and can never be `Refused`. A later recording for the same step SHALL replace the stored outcome and its provenance — the hazard restrictions apply to every recording — and a re-recording SHALL NOT reverse a gate that has already opened. Recording an outcome for a step identifier the pinned playbook version does not define SHALL be rejected. A step reaching `Satisfied` SHALL be reported as a `StepSatisfied` occurrence; a step reaching `Refused` SHALL be reported as a `StepRefused` occurrence.

#### Scenario: A satisfied step is recorded with its provenance

- **WHEN** a `Satisfied` outcome is recorded for a defined step with source `attestation`, a named recorder, a timestamp, and evidence
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

- **WHEN** an outcome is recorded for a step identifier the pinned playbook version does not define
- **THEN** the recording is rejected

### Requirement: A gate opens only when every blocking condition attached to it is satisfied

A launch SHALL advance from its current gate only to the next gate in the `launch-playbook` sequence — gates advance monotonically, are never skipped, and never move backwards. The current gate SHALL open only when every blocking condition attached to it is satisfied: every step obligation (a blocking step attached to the gate) has reached a permitted terminal outcome (`Satisfied` or `NotApplicable`), and every authored metric condition is satisfied. A `Refused` outcome never satisfies any condition. Advancing SHALL be reported as a `GateOpened` occurrence; an advance attempted while any blocking condition is unsatisfied SHALL be rejected and reported as a `GateBlocked` occurrence naming each unsatisfied condition.

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

### Requirement: A confirmation gate additionally requires a recorded approval

For a gate whose `launch-playbook` opening mode is `requires-confirmation`, the launch SHALL advance only when, in addition to every blocking condition being satisfied, an approval for that gate has been recorded carrying the decision, a named approver, and a timestamp. An approval's decision SHALL be either approving or rejecting; only an approving decision satisfies the approval requirement — a rejecting decision is recorded but keeps the gate closed. An approval without a named approver SHALL be rejected. An approval naming a posture for any gate other than `graduated` SHALL be rejected. An automatic gate SHALL NOT require an approval.

#### Scenario: A confirmation gate with satisfied conditions but no approval stays closed

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied but no approval for it has been recorded, and the launch is advanced
- **THEN** the advance is rejected and the current gate is unchanged

#### Scenario: A confirmation gate opens once approved

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied and an approval with a named approver is recorded
- **THEN** the launch advances and a `GateOpened` occurrence is reported

#### Scenario: An approval without a named approver is rejected

- **WHEN** a gate approval is recorded without a named approver
- **THEN** the recording is rejected

#### Scenario: A rejecting decision keeps the gate closed

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied, an approval with a rejecting decision is recorded, and the launch is advanced
- **THEN** the advance is rejected and the current gate is unchanged

#### Scenario: A posture on a non-graduation approval is rejected

- **WHEN** an approval for a gate other than `graduated` names a posture
- **THEN** the recording is rejected

### Requirement: A metric condition is satisfied by human attestation until live evaluation exists

Until the metric registry evaluates live observations, a gate's authored metric condition SHALL count as satisfied only when a metric attestation has been recorded against the launch for that gate's condition, carrying who attested, when, and evidence. Recording an attestation for a metric condition the pinned playbook version does not author on that gate SHALL be rejected.

#### Scenario: An attested metric condition counts as satisfied

- **WHEN** an attestation with a named attester and evidence is recorded for a metric condition authored on the current gate, and every other blocking condition is satisfied
- **THEN** the gate's conditions count as satisfied and the launch can advance

#### Scenario: An unattested metric condition keeps the gate closed

- **WHEN** the launch is advanced while a metric condition authored on the current gate has no recorded attestation
- **THEN** the advance is rejected and a `GateBlocked` occurrence names that metric condition

#### Scenario: An attestation for a condition the gate does not author is rejected

- **WHEN** an attestation is recorded for a metric identifier the pinned playbook version does not author on the named gate
- **THEN** the recording is rejected

### Requirement: Step due dates derive from the launch date and re-resolve when it moves

When a launch has a launch date, every step's due period SHALL derive from that date and the step's `launch-playbook` timing anchor. When the launch has no launch date, due periods SHALL be reported as absent rather than invented. Moving the launch date SHALL re-resolve every step's due period at once from the new date and SHALL be reported as a `LaunchDateMoved` occurrence carrying the previous and new dates.

#### Scenario: A step's due period derives from the launch date

- **WHEN** a launch has a launch date and a step's timing anchor is an offset of -30 days
- **THEN** that step's due period is reported as the single day 30 days before the launch date

#### Scenario: Without a launch date there are no due periods

- **WHEN** a launch has no launch date
- **THEN** every step's due period is reported as absent

#### Scenario: Moving the launch date re-resolves every due period

- **WHEN** the launch date is moved to a date 14 days later
- **THEN** every step's due period is reported re-resolved from the new date, and a `LaunchDateMoved` occurrence carries the previous and new dates

### Requirement: The launch date is reported at risk when a blocking unresolved step is overdue

Evaluated as of a given date, a launch with a launch date SHALL be reported at risk — a `LaunchDateAtRisk` occurrence naming each such step — when any blocking step's due period has fully passed and that step has not reached a permitted terminal outcome. A launch with no launch date, or whose overdue steps are all non-blocking or already resolved, SHALL NOT be reported at risk.

#### Scenario: An overdue unresolved blocking step puts the date at risk

- **WHEN** the launch is evaluated on a date after a blocking step's due period has fully passed and that step has not reached a permitted terminal outcome
- **THEN** a `LaunchDateAtRisk` occurrence is reported naming that step

#### Scenario: An overdue non-blocking step does not put the date at risk

- **WHEN** the only steps whose due periods have passed unresolved are non-blocking
- **THEN** no `LaunchDateAtRisk` occurrence is reported

#### Scenario: A resolved overdue step does not put the date at risk

- **WHEN** every blocking step whose due period has passed has reached a permitted terminal outcome
- **THEN** no `LaunchDateAtRisk` occurrence is reported

#### Scenario: A launch without a launch date is never at risk

- **WHEN** a launch with no launch date is evaluated
- **THEN** no `LaunchDateAtRisk` occurrence is reported

### Requirement: Graduation stamps the catalog product steady-state

Opening the `graduated` gate SHALL be reported as a `LaunchGraduated` occurrence, and the system SHALL then — after the advanced launch is persisted — attempt to change the referenced catalog product's lifecycle stage, through the `product-catalog` capability, to steady state with a posture chosen by the graduation approver — the system never chooses a posture itself — recording that approver as the stage change's human confirmer. When `product-catalog`'s transition rules reject the stage change (the product is not in a stage from which steady state is reachable), the advance SHALL stand, no stage SHALL change, and the failure SHALL be reported as an error naming the manual catalog correction required. A graduation approval that does not name a posture SHALL be rejected.

#### Scenario: Graduation stamps the product with the approver's chosen posture

- **WHEN** every blocking condition on `graduated` is satisfied for a product in a launching stage and an approval naming an approver and a posture is recorded, and the launch is advanced
- **THEN** a `LaunchGraduated` occurrence is reported and the catalog product's stage becomes steady state with the chosen posture, confirmed by that approver

#### Scenario: A rejected stage stamp leaves the advance standing

- **WHEN** the `graduated` gate opens for a product whose current stage does not permit a transition to steady state
- **THEN** the launch's current gate remains `graduated`, the product's stage is unchanged, and an error is reported naming the manual catalog correction required

#### Scenario: A graduation approval without a posture is rejected

- **WHEN** an approval for the `graduated` gate is recorded without naming a posture
- **THEN** the recording is rejected
