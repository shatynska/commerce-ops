# launch-playbook delta — author-playbook-steps

## ADDED Requirements

### Requirement: The shipped playbook carries the authored step set

The shipped `v1` playbook SHALL carry authored step definitions, not an empty step list. The authored set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) as follows: the BUILD THE LISTING area is represented completely — every ID-bearing row of that area appears as a step — and every other gate carries a representative subset. Each step's identifier SHALL be the reference document's own row ID, and its provenance SHALL carry that row's source citation, so every authored step traces to exactly one reference row.

Rows of the reference document that restate a condition a gate already authors as a metric condition SHALL NOT additionally appear as steps: one obligation is expressed once.

#### Scenario: The shipped playbook loads with steps

- **WHEN** the shipped playbook is loaded
- **THEN** it loads coherently and its step list is non-empty
- **AND** every gate has at least one step attached

#### Scenario: BUILD THE LISTING is fully represented

- **WHEN** the shipped playbook's steps are compared against the ID-bearing rows of the reference document's BUILD THE LISTING area
- **THEN** every such row's ID appears as a step identifier in the playbook

#### Scenario: A step traces to its source row

- **WHEN** any authored step is read from the loaded playbook
- **THEN** its identifier is a reference-document row ID and its provenance reference is that row's source citation

#### Scenario: A gate-authored condition is not duplicated as a step

- **WHEN** the shipped playbook's step identifiers are compared against the reference rows that restate a gate's authored metric conditions
- **THEN** none of those rows' IDs appears as a step identifier

### Requirement: Every gate is held by at least one blocking step

Each of the eight gates SHALL have at least one blocking step attached, so that no gate's step obligations are trivially satisfied by an empty set. Blocking steps SHALL be `framework`-bound (the coherence rules already forbid the alternatives); steps that are advice, cautions, or optional-at-launch work SHALL NOT block.

#### Scenario: No gate opens for free

- **WHEN** the shipped playbook's steps are grouped by gate
- **THEN** every gate has at least one step with a true blocking flag

### Requirement: The authored set exercises the full step vocabulary

The authored step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring), at least one step for every discipline in the shared vocabulary, at least one `prohibited-tactic` step and at least one `compliance-obligation` step, and at least one step of each execution mode. Steps whose execution mode requires a rule policy SHALL carry one; human-attested steps MAY ship without one, appearing in the undecided-rule-policies report.

Tactics the reference document marks as suspension risks SHALL be represented as `prohibited-tactic` steps only where the row names a tactic to refuse; a row that is a caution about a mistake SHALL remain an ordinary step, because heeding a caution is satisfiable work while a tactic can only be refused.

#### Scenario: Anchor kinds are all present

- **WHEN** the shipped playbook's steps are grouped by timing-anchor kind
- **THEN** each of offset, window, open-ended, and recurring is represented by at least one step

#### Scenario: Every discipline appears

- **WHEN** the shipped playbook's steps are grouped by discipline
- **THEN** every discipline of the shared vocabulary is represented by at least one step

#### Scenario: Execution modes and the compliance hazard are represented

- **WHEN** the shipped playbook's steps are grouped by execution mode and filtered by hazard
- **THEN** each of automated, AI-assisted, and human-attested is represented by at least one step
- **AND** every step whose execution mode requires a rule policy carries one
- **AND** at least one `compliance-obligation` step exists

#### Scenario: Prohibited tactics are present and never block

- **WHEN** the shipped playbook's steps are filtered to hazard `prohibited-tactic`
- **THEN** at least one such step exists
- **AND** none of them has a true blocking flag

#### Scenario: Outstanding rule-policy decisions stay visible

- **WHEN** the undecided-rule-policies report runs over the shipped playbook while any human-attested step lacks a decided rule policy
- **THEN** it lists exactly those steps

This scenario describes the authoring-in-progress state this change ships; once every rule policy is decided, a follow-up change amends it rather than a fully decided playbook counting as a violation.
