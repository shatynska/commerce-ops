## ADDED Requirements

### Requirement: A gate's steps can be reordered

The system SHALL allow a step to be moved to a chosen position among the live steps of its own gate. The write SHALL renumber the gate's live steps as one atomic operation, so that after it every live step of the gate holds a distinct slot and the relative order of the steps that were not moved is preserved. Reordering SHALL be subject to the same whole-set validation and write serialization as every other authoring write — a reorder concurrent with another accepted write on a stale view of the set SHALL be rejected without persisting anything. The reorder's principal and date SHALL be recorded against the moved step, as an update's are. The new order SHALL be served on the next read. A reorder addresses a position among the step's own gate's live steps only, and SHALL NOT change the step's gate or any other of its fields — changing a step's gate is an update to the step's gate field.

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
