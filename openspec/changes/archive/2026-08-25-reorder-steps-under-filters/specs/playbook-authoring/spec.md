## MODIFIED Requirements

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
