# launch-playbook delta — describe-playbook-steps

## MODIFIED Requirements

### Requirement: A step definition declares how it is to be resolved

Each step definition SHALL declare all of:

- a unique identifier within the playbook, expressed as a human-readable slug
- a description: the work the step asks for, readable without consulting the source material, and occupying a single line
- the gate it must be resolved before
- the discipline that owns it — drawn from the shared vocabulary's discipline set
- its scope: whether the step concerns the product itself, or the product on one marketplace
- a timing anchor
- its binding: `framework` — a rule the launch is held to — or `lesson` — advice
- whether it blocks its gate
- its execution mode: automated, AI-assisted, or attested by a person
- its hazard classification (see below) — declared explicitly, or `none` by default when the author declares nothing
- optionally, the rule policy stating what we specifically do — which MAY be absent while the decision is outstanding
- optionally, a provenance reference into the source material it derives from

The description is required and SHALL NOT be empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty or absent description; that rejection is stated once, with the other load-time rules, rather than twice.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, description, gate, discipline, scope, timing anchor, binding, blocking flag, execution mode, and hazard classification are all present
- **AND** its rule policy and provenance reference are present only if authored

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

### Requirement: The shipped playbook carries the authored step set

The shipped `v1` playbook SHALL carry authored step definitions, not an empty step list. The authored set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) as follows: the BUILD THE LISTING area is represented completely — every ID-bearing row of that area appears as a step — and every other gate carries a representative subset. Each step's identifier SHALL be the reference document's own row ID, its description SHALL be that row's own text, and its provenance SHALL carry that row's source citation, so every authored step traces to exactly one reference row and can be read without opening it.

A shipped step's description SHALL be the text of its reference row transcribed unaltered, except that trailing whitespace SHALL be removed, and then any trailing character in the closed set `;` `:` `,` `.` — repeating until neither whitespace nor one of those four characters remains at the end. No other character SHALL be stripped, and nothing else SHALL be changed — not the wording, the casing, or the order of clauses.

The set is closed deliberately, and is not "trailing punctuation": reference rows end variously in a closing quote, a closing parenthesis, or a `+` (as in "A+"), and each of those is part of what the row says rather than a fragment's terminal mark. A rule broad enough to remove them would silently corrupt the text it exists to preserve.

Transcribing this way is what makes every shipped description re-derivable from the reference document and comparable against it, so that a divergence between the two is detectable rather than silent. The reference document's wording belongs to the team that wrote it; this specification moves it, and does not improve it.

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

#### Scenario: A step states its work without the source document

- **WHEN** any authored step is read from the loaded playbook
- **THEN** its description is non-empty

#### Scenario: Every description re-derives from its reference row

- **WHEN** every authored step's description is compared against the text of the reference row its identifier names, reduced by the trimming rule above
- **THEN** each description equals that row's trimmed text exactly

#### Scenario: A gate-authored condition is not duplicated as a step

- **WHEN** the shipped playbook's step identifiers are compared against the reference rows that restate a gate's authored metric conditions
- **THEN** none of those rows' IDs appears as a step identifier

### Requirement: An incoherent playbook is rejected at load time

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's description is empty, or is not declared at all
- a step definition's description spans more than one line — a description is composed into a task's name, and a name is a single line
- a step definition's execution mode is automated or AI-assisted while its rule policy is absent
- a step definition is classified `prohibited-tactic` and is also marked as blocking its gate
- a step definition's binding is `lesson` and it is marked as blocking its gate — advice that blocks a gate the way a framework rule does is a category error
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

- **WHEN** a playbook declares a step whose description is empty, or omits the description entirely
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
