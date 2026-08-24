## MODIFIED Requirements

### Requirement: Playbooks are versioned

A playbook SHALL carry a version identifier, and a launch SHALL record the version identifier it was started under as an audit stamp. The step set itself SHALL be **live**: there is one current step set, an authored change to it takes effect on the next read, and no read path selects among stored definitions by version — every launch, whenever started, is served the current step set. The recorded version stamp exists so that a launch's history remains interpretable ("what definition era did this start under"), not to freeze behavior. For that interpretability to mean anything, the served playbook's version identifier SHALL change whenever the step set changes — it is, or is derived from, the step-set version that serializes writes — so two launches stamped with different identifiers started under genuinely different definitions, and a constant identifier does not satisfy this requirement.

#### Scenario: The loaded playbook reports its version

- **WHEN** a playbook is loaded
- **THEN** it reports a version identifier

#### Scenario: A launch records the version it started under

- **WHEN** a launch is started
- **THEN** it records the served playbook's version identifier
- **AND** that record is an audit stamp — no subsequent read of the playbook branches on it

#### Scenario: An authored change changes the served version identifier

- **WHEN** the playbook is read, the step set is then changed by an accepted write, and the playbook is read again
- **THEN** the two reads report different version identifiers

#### Scenario: An authored change reaches a launch already in flight

- **WHEN** the step set is changed after a launch has started, and the playbook is next read on that launch's behalf
- **THEN** the read serves the current step set, including the change

### Requirement: An incoherent playbook is rejected at load time
Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's description is empty, consists only of whitespace, or is not declared at all
- a step definition's description spans more than one line — a description is composed into a task's name, and a name is a single line
- a step definition's execution mode is automated or AI-assisted while its rule policy is absent
- a step definition is classified `prohibited-tactic` and is also marked as blocking its gate
- a step definition's binding is `lesson` and it is marked as blocking its gate — advice that blocks a gate the way a framework rule does is a category error
- a gate has no blocking step attached to it — the gate-holding floor its own requirement states, promoted to a coherence rule now that the step set is editable, so no sequence of writes can leave a gate that opens for free
- a gate's authored metric condition has an empty threshold description

#### Scenario: Gate sequence deviates from the specification

- **WHEN** a playbook's gate sequence omits a gate, adds one, repeats a position, or orders the gates differently from the defined sequence
- **THEN** loading fails with an error naming the deviation

#### Scenario: A gate's opening mode disagrees with the specification

- **WHEN** a playbook declares an opening mode for a gate that differs from the mode this specification assigns to it
- **THEN** loading fails with an error naming that gate

#### Scenario: Duplicate step identifier

- **WHEN** a playbook defines two steps with the same identifier
- **THEN** loading fails with an error naming that identifier

#### Scenario: Step references an unknown gate

- **WHEN** a step definition declares a gate that is not part of the gate sequence
- **THEN** loading fails with an error naming the step and the unknown gate

#### Scenario: A step with no description is rejected by name

- **WHEN** a playbook declares a step whose description is empty, consists only of whitespace, or omits the description entirely
- **THEN** loading fails with an error naming that step, in the same aggregated report as any other fault

#### Scenario: A description spanning several lines is rejected

- **WHEN** a playbook declares a step whose description contains a line break
- **THEN** loading fails with an error naming that step

#### Scenario: Automation without a decided rule

- **WHEN** a step definition declares an automated or AI-assisted execution mode and has no rule policy
- **THEN** loading fails with an error naming that step

#### Scenario: A prohibited tactic cannot block a gate

- **WHEN** a step definition is classified `prohibited-tactic` and marked as blocking its gate
- **THEN** loading fails with an error naming that step

#### Scenario: A lesson cannot block a gate

- **WHEN** a step definition's binding is `lesson` and it is marked as blocking its gate
- **THEN** loading fails with an error naming that step

#### Scenario: A gate with no blocking step is rejected

- **WHEN** a playbook's steps leave any gate with no step whose blocking flag is true
- **THEN** loading fails with an error naming that gate

#### Scenario: A malformed metric condition is rejected

- **WHEN** a playbook authors a metric condition whose threshold description is empty
- **THEN** loading fails with an error naming the gate carrying it

#### Scenario: Multiple violations are reported together

- **WHEN** a playbook contains two distinct coherence violations
- **THEN** loading fails once, and the failure names both

#### Scenario: A malformed step is reported alongside a coherence violation

- **WHEN** a playbook contains one step whose timing anchor is invalid and a second, separate coherence violation
- **THEN** loading fails once, and the failure names both faults

#### Scenario: A coherent playbook loads

- **WHEN** a playbook satisfies every coherence rule
- **THEN** it loads successfully and exposes its gates and step definitions

### Requirement: The shipped playbook carries the authored step set
The stored step set SHALL be seeded, exactly once, with the authored `v1` step definitions — not started empty. The seeded set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) as follows: the BUILD THE LISTING area is represented completely — every ID-bearing row of that area appears as a step — and every other gate carries a representative subset. Each seeded step's identifier SHALL be the reference document's own row ID, its description SHALL be that row's own text, and its provenance SHALL carry that row's source citation, so every seeded step traces to exactly one reference row and can be read without opening it.

A seeded step's description SHALL be the text of its reference row transcribed unaltered, except that trailing whitespace SHALL be removed, and then any trailing character in the closed set `;` `:` `,` `.` — repeating until neither whitespace nor one of those four characters remains at the end. No other character SHALL be stripped, and nothing else SHALL be changed — not the wording, the casing, or the order of clauses.

The set is closed deliberately, and is not "trailing punctuation": reference rows end variously in a closing quote, a closing parenthesis, or a `+` (as in "A+"), and each of those is part of what the row says rather than a fragment's terminal mark. A rule broad enough to remove them would silently corrupt the text it exists to preserve.

Transcribing this way is what makes every seeded description re-derivable from the reference document and comparable against it, so that a divergence between the two is detectable rather than silent. The reference document's wording belongs to the team that wrote it; the seed moves it, and does not improve it.

A seeded step's identifier SHALL carry its declared discipline as its second segment (`lp.creative.008` is a `creative` step). This is what allows a surface composed from the identifier to omit the discipline without losing it, and it holds for every step of the seeded set.

Rows of the reference document that restate a condition a gate already authors as a metric condition SHALL NOT additionally appear as seeded steps: one obligation is expressed once.

These guarantees describe the seed. Once seeded, the step set changes only through the `playbook-authoring` capability, and a step edited that way is thereafter governed by its recorded authorship, not by re-derivability from the reference document.

#### Scenario: The shipped playbook loads with steps

- **WHEN** the playbook is loaded after seeding
- **THEN** it loads coherently and its step list is non-empty
- **AND** every gate has at least one step attached

#### Scenario: BUILD THE LISTING is fully represented

- **WHEN** the seeded step set is compared against the ID-bearing rows of the reference document's BUILD THE LISTING area
- **THEN** every such row's ID appears as a step identifier

#### Scenario: A step traces to its source row

- **WHEN** any seeded step is read, before any authored edit to it
- **THEN** its identifier is a reference-document row ID and its provenance reference is that row's source citation
- **AND** the second segment of that identifier is the step's declared discipline

#### Scenario: A step states its work without the source document

- **WHEN** any seeded step is read
- **THEN** its description is non-empty

#### Scenario: Every description re-derives from its reference row

- **WHEN** every seeded step's description, before any authored edit to it, is compared against the text of the reference row its identifier names, reduced by the trimming rule above
- **THEN** each description equals that row's trimmed text exactly

#### Scenario: A gate-authored condition is not duplicated as a step

- **WHEN** the seeded step identifiers are compared against the reference rows that restate a gate's authored metric conditions
- **THEN** none of those rows' IDs appears as a step identifier

#### Scenario: The seed runs once

- **WHEN** the seed has already populated the step set and the migration machinery runs again
- **THEN** the step set is not re-seeded and authored changes made since the seed are not overwritten

### Requirement: Every gate is held by at least one blocking step

Each of the eight gates SHALL have at least one blocking step attached **in the served step set at all times** — at seed, and after every authored change — so that no gate's step obligations are trivially satisfied by an empty set. Blocking steps SHALL be `framework`-bound (the coherence rules already forbid the alternatives); steps that are advice, cautions, or optional-at-launch work SHALL NOT block. This floor is itself a coherence rule (see the incoherence requirement), so it is enforced by the same validation at load and at every write alike.

#### Scenario: No gate opens for free

- **WHEN** the served step set is grouped by gate, at any point in the set's life
- **THEN** every gate has at least one step with a true blocking flag

### Requirement: The authored set exercises the full step vocabulary

The **seeded** step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring), at least one step for every discipline in the shared vocabulary, at least one `prohibited-tactic` step and at least one `compliance-obligation` step, and at least one step of each execution mode. Seeded steps whose execution mode requires a rule policy SHALL carry one; human-attested steps MAY be seeded without one, appearing in the undecided-rule-policies report.

Tactics the reference document marks as suspension risks SHALL be represented as `prohibited-tactic` steps only where the row names a tactic to refuse; a row that is a caution about a mistake SHALL remain an ordinary step, because heeding a caution is satisfiable work while a tactic can only be refused.

Like its sibling seed requirement, this describes the seed and only the seed: it is a property of what the one-time seeding delivers, not a standing invariant of the served set. Write validation under `playbook-authoring` enforces the coherence rules, and does not additionally hold authored changes to this coverage — retiring the last step of some timing-anchor kind is a permissible authoring decision, not a fault.

#### Scenario: Anchor kinds are all present

- **WHEN** the seeded step set is grouped by timing-anchor kind
- **THEN** each of offset, window, open-ended, and recurring is represented by at least one step

#### Scenario: Every discipline appears

- **WHEN** the seeded step set is grouped by discipline
- **THEN** every discipline of the shared vocabulary is represented by at least one step

#### Scenario: Execution modes and the compliance hazard are represented

- **WHEN** the seeded step set is grouped by execution mode and filtered by hazard
- **THEN** each of automated, AI-assisted, and human-attested is represented by at least one step
- **AND** every seeded step whose execution mode requires a rule policy carries one
- **AND** at least one `compliance-obligation` step exists

#### Scenario: Prohibited tactics are present and never block

- **WHEN** the seeded step set is filtered to hazard `prohibited-tactic`
- **THEN** at least one such step exists
- **AND** none of them has a true blocking flag

#### Scenario: Outstanding rule-policy decisions stay visible

- **WHEN** the undecided-rule-policies report runs over the served playbook while any human-attested step lacks a decided rule policy
- **THEN** it lists exactly those steps

This scenario describes the authoring-in-progress state; once every rule policy is decided, a follow-up change amends it rather than a fully decided playbook counting as a violation.
