## ADDED Requirements

### Requirement: A gate carries authored metric conditions

A gate SHALL be able to carry zero or more authored metric conditions, each naming the metric it turns on by metric identifier and carrying a human-readable threshold description stating what must hold. A metric condition's threshold description SHALL NOT be empty. The metric identifier is a reference only: no metric registry exists yet, and until one does, whether a metric condition holds is established by human attestation recorded against a launch — a concern of the launch-instance capability, not of this definition. When live observation later arrives, the same authored condition is evaluated against data; the definition SHALL NOT need to change for that switch.

#### Scenario: A gate's metric conditions are read back

- **WHEN** a gate authored with a metric condition is read from a loaded playbook
- **THEN** the condition reports its metric identifier and its threshold description

#### Scenario: A gate with no metric conditions is valid

- **WHEN** a gate authored with no metric conditions is read
- **THEN** it reports an empty set of metric conditions

### Requirement: Gate conditions unify step obligations and metric conditions

A gate's conditions SHALL be readable as one collection covering both kinds of thing the gate waits on: one step obligation per blocking step definition attached to the gate, and the gate's authored metric conditions. Step obligations SHALL be derived from the step definitions' own gate and blocking declarations — never authored a second time on the gate — so a blocking fact exists in exactly one place. A non-blocking step SHALL NOT appear among a gate's conditions.

#### Scenario: A blocking step appears as a step obligation

- **WHEN** a step definition declares gate `listable` and is marked blocking, and the `listable` gate's conditions are read
- **THEN** the conditions include a step obligation naming that step's identifier

#### Scenario: A non-blocking step produces no condition

- **WHEN** a step definition declares gate `listable` and is not marked blocking
- **THEN** the `listable` gate's conditions include no obligation for that step

#### Scenario: Authored metric conditions appear alongside derived obligations

- **WHEN** a gate has both a blocking step attached and an authored metric condition
- **THEN** reading its conditions returns both, each identifiable as its kind

### Requirement: Step outcome vocabulary

The capability SHALL define the vocabulary a step's resolution is expressed in: `NotStarted`, `InProgress`, `Satisfied`, `Blocked` carrying a reason, `Refused`, and `NotApplicable` carrying a reason — an outcome, not a boolean, because absent and inapplicable differ and "missing is not fine". A `Blocked` or `NotApplicable` outcome SHALL reject construction without a non-empty reason. The vocabulary SHALL answer which outcomes are permitted as terminal for a step given its hazard classification, and the answer SHALL be complete over all six outcomes: for a `prohibited-tactic` step the only permissible terminal outcome is `Refused`; for any other step the permissible terminal outcomes are `Satisfied` and `NotApplicable`, and `Refused` is not permissible. `NotStarted`, `InProgress`, and `Blocked` are never terminal for any step — a blocked step awaits resolution, it has not reached one. Recording and transitioning outcomes at runtime belongs to the launch-instance capability, not here.

#### Scenario: A blocked outcome carries its reason

- **WHEN** a `Blocked` outcome is constructed with a reason
- **THEN** it reports that reason

#### Scenario: An outcome requiring a reason rejects an empty one

- **WHEN** a `Blocked` or `NotApplicable` outcome is constructed with an empty reason
- **THEN** construction fails

#### Scenario: A prohibited tactic can only terminate in refusal

- **WHEN** the vocabulary is asked whether `Satisfied` is a permissible terminal outcome for a step classified `prohibited-tactic`
- **THEN** it answers no
- **AND** it answers yes for `Refused`

#### Scenario: An ordinary step cannot be refused

- **WHEN** the vocabulary is asked whether `Refused` is a permissible terminal outcome for a step whose hazard classification is `none` or `compliance-obligation`
- **THEN** it answers no

#### Scenario: Blocked is never terminal, inapplicability is

- **WHEN** the vocabulary is asked about the remaining outcomes for a step whose hazard classification is `none` or `compliance-obligation`
- **THEN** it answers yes for `NotApplicable`
- **AND** it answers no for `Blocked`, `NotStarted`, and `InProgress`

### Requirement: Discipline is drawn from the shared vocabulary

A step definition's owning discipline SHALL be one of the disciplines the shared vocabulary defines. The attribute SHALL be named discipline — the ownership tag formerly named track — and there SHALL be exactly one name for it across the playbook's authored form, its loaded form, and this specification.

#### Scenario: Discipline is restricted to the shared vocabulary

- **WHEN** a step definition declares a discipline outside the shared vocabulary's set
- **THEN** loading fails with an error naming the step and the unrecognised discipline

### Requirement: Undecided rule policies are reported

The capability SHALL report which of a loaded playbook's step definitions carry no rule policy — the steps whose acceptance criterion is still undecided — each identified by its identifier, its gate, its owning discipline, and its execution mode, so the outstanding decisions remain visible while the playbook is authored rather than surfacing one at a time.

#### Scenario: Steps without a rule policy are listed

- **WHEN** the report is requested against a playbook containing one step with a rule policy and one without
- **THEN** exactly the step without a rule policy is reported, with its identifier, gate, discipline, and execution mode

#### Scenario: A fully decided playbook reports nothing

- **WHEN** the report is requested against a playbook in which every step carries a rule policy
- **THEN** the report is empty

## MODIFIED Requirements

### Requirement: A step definition declares how it is to be resolved

Each step definition SHALL declare all of:

- a unique identifier within the playbook, expressed as a human-readable slug
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

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, gate, discipline, scope, timing anchor, binding, blocking flag, execution mode, and hazard classification are all present
- **AND** its rule policy and provenance reference are present only if authored

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

### Requirement: An incoherent playbook is rejected at load time

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
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

## REMOVED Requirements

### Requirement: Track names one of a fixed set of disciplines

**Reason**: The ownership tag is renamed to discipline per the settled naming decision (2026-08-23, `introduce-catalog-and-shared-vocabulary`), and its value set now lives in the shared vocabulary rather than being restated here, so launch and the future monitoring context speak one discipline set.

**Migration**: Author and read the attribute as `discipline`; the permitted values are the shared vocabulary's discipline set, unchanged in content. Validation behavior is preserved by the added requirement "Discipline is drawn from the shared vocabulary".
