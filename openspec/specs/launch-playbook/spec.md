# launch-playbook Specification

## Purpose

Defines what an Amazon product launch consists of: an ordered sequence of commitment gates and the step definitions attached to them, versioned and authored in the repository, so that launches of individual products can later be run against a known, coherent definition.

## Requirements

### Requirement: Gate sequence orders the launch

A launch playbook SHALL define its ordering as a sequence of commitment gates, each representing a point at which money, stock, or public exposure becomes irreversible. The sequence SHALL be exactly the following eight gates in this order:

1. `commit` — the product is worth developing
2. `order` — the purchase order may be placed
3. `listable` — everything buildable without stock or a live listing is ready
4. `stock-ready` — sufficient fulfillable units are available
5. `live` — the listing may be switched on
6. `ignition` — the marketing launch may fire
7. `phase-one-complete` — the ranking push has done its work
8. `graduated` — the launch is over

Gates SHALL be the only ordering primitive in the playbook. Step definitions attached to the same gate SHALL carry no ordering relative to one another.

#### Scenario: Gates expose a stable order

- **WHEN** the playbook's gates are read
- **THEN** they are returned in the defined order, each carrying its position in the sequence
- **AND** two gates never share a position

#### Scenario: Steps at the same gate are unordered

- **WHEN** two step definitions declare the same gate
- **THEN** the playbook expresses no ordering between them

### Requirement: A gate declares how it opens

Each gate SHALL declare whether it opens automatically once its blocking conditions are satisfied, or requires explicit human confirmation in addition.

A gate SHALL require confirmation when its opening turns on a judgement that no objective condition settles — committing capital, or declaring a phase of the launch finished. A gate SHALL open automatically when its preconditions are an observable state of the world. By that criterion `commit`, `order`, `phase-one-complete` and `graduated` require confirmation, and `listable`, `stock-ready`, `live` and `ignition` open automatically.

Note, as context for applying that criterion rather than as a requirement of this capability: opening a gate grants permission for the work beyond it and does not itself perform that work. This is why `ignition` opens automatically despite being the launch's most consequential moment — its preconditions are observable, and firing the launch is a step, not the gate. What happens when a gate opens is specified by the launch-instance capability, not here.

#### Scenario: A discretionary gate is marked as requiring confirmation

- **WHEN** the `commit`, `order`, `phase-one-complete`, or `graduated` gate is read
- **THEN** it reports that it requires human confirmation to open

#### Scenario: An objective gate opens automatically

- **WHEN** the `listable`, `stock-ready`, `live`, or `ignition` gate is read
- **THEN** it reports that it opens automatically

### Requirement: Track names one of a fixed set of disciplines

A step definition's track SHALL be one of the following twelve disciplines, matching the ownership boundaries the source material already uses: `strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`, `price`, `ppc`, `customer`, `external`, `traffic`.

#### Scenario: Track is restricted to the known disciplines

- **WHEN** a step definition declares a track outside this set
- **THEN** loading fails with an error naming the step and the unrecognised track

### Requirement: A step definition declares how it is to be resolved

Each step definition SHALL declare all of:

- a unique identifier within the playbook, expressed as a human-readable slug
- the gate it must be resolved before
- the track that owns it — the discipline whose expertise the step belongs to
- its scope: whether the step concerns the product itself, or the product on one marketplace
- a timing anchor
- its binding: whether it is a rule the launch is held to, or advice
- whether it blocks its gate
- its execution mode: automated, AI-assisted, or attested by a person
- its hazard classification (see below) — declared explicitly, or `none` by default when the author declares nothing
- optionally, the rule policy stating what we specifically do — which MAY be absent while the decision is outstanding
- optionally, a provenance reference into the source material it derives from

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, gate, track, scope, timing anchor, binding, blocking flag, execution mode, and hazard classification are all present
- **AND** its rule policy and provenance reference are present only if authored

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

### Requirement: Hazard classification distinguishes what is refused from what is complied with

A step definition SHALL declare exactly one hazard classification:

- `none` — the step carries no terms-of-service exposure
- `prohibited-tactic` — a tactic that risks account suspension, recorded so that it is recognised and refused. Its only terminal state is refusal; it can never be satisfied
- `compliance-obligation` — an obligation or hazard whose terminal state is compliance. It can be satisfied, and it MAY block a gate

A `prohibited-tactic` step SHALL NOT be markable as blocking a gate, because a gate can never wait on something that can never be satisfied. No such restriction SHALL apply to a `compliance-obligation` step.

#### Scenario: A compliance obligation may block a gate

- **WHEN** a step definition is classified `compliance-obligation` and marked as blocking its gate
- **THEN** the playbook loads successfully

#### Scenario: Classification is always present

- **WHEN** a step definition is read from a loaded playbook
- **THEN** it reports one of the three hazard classifications, defaulting to `none` when the author declared nothing

### Requirement: Provenance references are never identifiers

A step definition's provenance reference SHALL be treated as a citation into the source material only. It SHALL NOT be required to be unique across step definitions, and SHALL NOT be usable to address a step.

#### Scenario: Two steps cite the same source row

- **WHEN** two step definitions declare the same provenance reference
- **THEN** the playbook loads successfully
- **AND** each step remains addressable only by its own identifier

### Requirement: Timing anchors resolve against the launch date

The launch date SHALL mean the **marketing launch date** — the day the launch fires — and SHALL be **offset zero** for every anchor. Offsets before it are negative; offsets after it are positive. Offsets are therefore zero-based: the launch day itself is offset 0, and the day after it is offset 1. Timing anchors are planning positions, not commitments: a step's anchor SHALL NOT be read as an obligation that its gate is open on that date.

A timing anchor SHALL take one of four forms:

- an **offset** — a whole number of days relative to the launch date
- a **window** — a span between two such offsets
- an **open-ended** anchor — a start offset with no end, expressing an obligation that begins on a day and does not expire
- a **recurrence** — a fixed cadence

Given a launch date, an offset anchor SHALL resolve to a single day, a window anchor to a bounded date range, and an open-ended anchor to a range with a start and no end. A recurring anchor SHALL NOT resolve to a date range, because it describes a repeating obligation rather than a due date.

#### Scenario: An offset anchor resolves to a single day

- **WHEN** an anchor of −7 days is resolved against a launch date
- **THEN** the resulting range starts and ends on the day seven days before the launch date

#### Scenario: A window anchor resolves to a bounded span

- **WHEN** an anchor spanning offsets 28 through 55 is resolved against a launch date
- **THEN** the resulting range starts 28 days after and ends 55 days after the launch date

#### Scenario: An open-ended anchor resolves to a start with no end

- **WHEN** an anchor beginning at offset 59 with no end is resolved against a launch date
- **THEN** the resulting range starts 59 days after the launch date
- **AND** the range reports no end date

#### Scenario: The launch day itself is offset zero

- **WHEN** an anchor of offset 0 is resolved against a launch date
- **THEN** the resulting range starts and ends on the launch date itself

#### Scenario: A recurring anchor has no due date

- **WHEN** a recurring anchor is resolved against a launch date
- **THEN** no date range is produced, and the anchor reports its cadence instead

#### Scenario: A window with a reversed span is rejected

- **WHEN** a window anchor is defined whose end offset precedes its start offset
- **THEN** it is rejected as invalid

### Requirement: Playbooks are versioned

A playbook SHALL carry a version identifier, so that a launch run against it can record which definition it was started under and remain interpretable after the playbook changes.

#### Scenario: The loaded playbook reports its version

- **WHEN** a playbook is loaded
- **THEN** it reports the version identifier it was authored with

### Requirement: An incoherent playbook is rejected at load time

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's execution mode is automated or AI-assisted while its rule policy is absent
- a step definition is classified `prohibited-tactic` and is also marked as blocking its gate

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

#### Scenario: Multiple violations are reported together

- **WHEN** a playbook contains two distinct coherence violations
- **THEN** loading fails once, and the failure names both

#### Scenario: A malformed step is reported alongside a coherence violation

- **WHEN** a playbook contains one step whose timing anchor is invalid and a second, separate coherence violation
- **THEN** loading fails once, and the failure names both faults

#### Scenario: A coherent playbook loads

- **WHEN** a playbook satisfies every coherence rule
- **THEN** it loads successfully and exposes its gates and step definitions

### Requirement: An undecided rule does not prevent loading

A step definition whose rule policy is absent SHALL load successfully provided its execution mode is attestation by a person. This allows the playbook to carry work whose acceptance criterion has not yet been decided.

#### Scenario: Human-attested step with no rule policy

- **WHEN** a step definition declares human attestation as its execution mode and has no rule policy
- **THEN** the playbook loads successfully and the step reports its rule policy as absent
