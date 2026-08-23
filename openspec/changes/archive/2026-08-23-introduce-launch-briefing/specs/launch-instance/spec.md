# launch-instance delta — introduce-launch-briefing

## ADDED Requirements

### Requirement: Launch positions are enumerable with their reports

The system SHALL report every persisted launch position, each with the same content a single-product read yields (steps with due periods and recorded progress, and the at-risk evaluation), evaluated as of a caller-supplied date. Enumeration SHALL NOT filter by lifecycle: the launch context does not own a product's stage, and its persisted shape deliberately does not distinguish a graduated launch from one standing at the final gate — whoever consumes the enumeration filters by the catalog's stage stamp.

#### Scenario: All launch positions are reported

- **WHEN** several launch positions exist and the launches are enumerated as of a date
- **THEN** every persisted launch position SHALL be reported, each with its steps' due periods, recorded progress, and at-risk evaluation as of that date

#### Scenario: No launches yields an empty enumeration

- **WHEN** no launch position exists and the launches are enumerated
- **THEN** the system SHALL report an empty result, not an error

### Requirement: The launch report carries each step's discipline and names the steps behind an at-risk date

The launch report SHALL carry, on each step entry, the owning discipline the playbook assigns to that step, and its at-risk evaluation SHALL name the overdue blocking steps that produced it. The report is the whole of what a consumer may know about a launch: a fact a consumer needs SHALL travel on the report rather than be re-derived from the playbook outside the launch context.

#### Scenario: A step entry carries its owning discipline

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL carry the discipline the playbook assigns to that step

#### Scenario: The at-risk evaluation names its overdue blocking steps

- **WHEN** a launch's report states the launch date is at risk
- **THEN** the at-risk evaluation SHALL name each overdue blocking step that produced it

### Requirement: The launch report states whether the current gate awaits confirmation

The launch report SHALL state that the current gate awaits confirmation exactly when that gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval has been recorded for it. In every other case — an automatic gate, unsatisfied blocking conditions, an approval already recorded, or a launch that has already graduated — the report SHALL state that it does not.

#### Scenario: A satisfied confirmation gate without an approval awaits confirmation

- **WHEN** the current gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval is recorded for it
- **THEN** the launch report SHALL state the gate awaits confirmation

#### Scenario: Unsatisfied blocking conditions mean the gate is not awaiting confirmation

- **WHEN** the current gate requires confirmation and at least one blocking condition attached to it is unsatisfied
- **THEN** the launch report SHALL state the gate does not await confirmation

#### Scenario: A recorded approving approval ends the wait

- **WHEN** the current gate requires confirmation, its blocking conditions are satisfied, and an approving approval is recorded for it
- **THEN** the launch report SHALL state the gate does not await confirmation

#### Scenario: An automatic gate never awaits confirmation

- **WHEN** the current gate opens automatically
- **THEN** the launch report SHALL state the gate does not await confirmation, whatever its conditions' state
