## MODIFIED Requirements

### Requirement: The authored set exercises the full step vocabulary

The **seeded** step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring), at least one step for every discipline in the shared vocabulary, at least one `prohibited-tactic` step and at least one `compliance-obligation` step, at least one step of each kind, and at least one automated step that needs confirmation alongside one that does not.

Every seeded `human` step SHALL be `active`. The seeded `automated` steps SHALL be `in-development`: the seed delivers no handler for either of them, and `active` would be a claim that something resolves them. That a runtime now exists to invoke handlers (`launch-step-automation`) does not change what the seed delivers — activation is an authoring act performed against a deployment that registers the step's handler, never something seeding or deploying does on an author's behalf. Neither is a blocking step, so the gate-holding floor is unaffected — which is what makes this the honest migration rather than a compromise.

Tactics the reference document marks as suspension risks SHALL be represented as `prohibited-tactic` steps only where the row names a tactic to refuse; a row that is a caution about a mistake SHALL remain an ordinary step, because heeding a caution is satisfiable work while a tactic can only be refused.

Like its sibling seed requirement, this describes the seed and only the seed: it is a property of what the one-time seeding delivers, not a standing invariant of the served set. Write validation under `playbook-authoring` enforces the coherence rules, and does not additionally hold authored changes to this coverage — retiring the last step of some timing-anchor kind is a permissible authoring decision, not a fault.

#### Scenario: Anchor kinds are all present

- **WHEN** the seeded step set is grouped by timing-anchor kind
- **THEN** each of offset, window, open-ended, and recurring is represented by at least one step

#### Scenario: Every discipline appears

- **WHEN** the seeded step set is grouped by discipline
- **THEN** every discipline of the shared vocabulary is represented by at least one step

#### Scenario: Execution modes and the compliance hazard are represented

- **WHEN** the seeded step set is grouped by kind and confirmation and filtered by hazard
- **THEN** `human` and `automated` are each represented, an automated step needing confirmation and one not needing it are both present, and at least one `compliance-obligation` step exists

#### Scenario: Prohibited tactics are present and never block

- **WHEN** the seeded step set is filtered to hazard `prohibited-tactic`
- **THEN** at least one such step exists
- **AND** none of them has a true blocking flag

#### Scenario: Outstanding rule-policy decisions stay visible

- **WHEN** the report of what blocks activation runs over the authored set while any step cannot yet be made `active`
- **THEN** it lists exactly those steps

#### Scenario: A registered runtime does not activate a seeded step

- **WHEN** a deployment registers step handlers and the seeded step set is read back
- **THEN** the seeded `automated` steps are still `in-development`, having been activated by no one
