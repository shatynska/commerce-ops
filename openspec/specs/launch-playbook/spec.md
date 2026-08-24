# launch-playbook Specification

## Purpose

Defines what an Amazon product launch consists of: an ordered sequence of commitment gates — the framework, code-owned in the repository — and the step definitions attached to them, stored in the database as one live, versioned set, so that launches of individual products run against a known, coherent definition that authored changes reach without a deployment.

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

Gates SHALL remain the only *commitment* ordering primitive in the playbook. Step definitions attached to the same gate SHALL additionally carry an authored order relative to one another — a total order within the gate, exposed by the served step set and followed by every consumer that lists a gate's steps. This within-gate order SHALL carry no commitment semantics: it SHALL never affect when a gate opens, which steps block it, or how step completion is evaluated — reordering a gate's steps changes how they are listed, and nothing else.

#### Scenario: Gates expose a stable order

- **WHEN** the playbook's gates are read
- **THEN** they are returned in the defined order, each carrying its position in the sequence
- **AND** two gates never share a position

#### Scenario: Steps at a gate are served in their authored order

- **WHEN** a gate's steps are read from the served playbook
- **THEN** they arrive in the gate's authored order
- **AND** two reads with no intervening write arrive in the same order

#### Scenario: Steps at the same gate are unordered

*(Retained name: "unordered" now means unordered to the commitment machinery — the authored order exists, and this scenario pins down that it never reaches an evaluation.)*

- **WHEN** a gate's steps are reordered and the gate's advancement, blocking evaluation, and step completion are then evaluated
- **THEN** the commitment machinery treats the gate's steps as an unordered set: each evaluation comes out exactly as it did before the reorder

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

### Requirement: Discipline is drawn from the shared vocabulary

A step definition's owning discipline SHALL be one of the disciplines the shared vocabulary defines. The attribute SHALL be named discipline — the ownership tag formerly named track — and there SHALL be exactly one name for it across the playbook's authored form, its loaded form, and this specification.

#### Scenario: Discipline is restricted to the shared vocabulary

- **WHEN** a step definition declares a discipline outside the shared vocabulary's set
- **THEN** loading fails with an error naming the step and the unrecognised discipline

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

The description is required and SHALL NOT be empty, and a description consisting only of whitespace SHALL be treated as empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty, whitespace-only, or absent description; that rejection is stated once, with the other load-time rules, rather than twice.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, description, gate, discipline, scope, timing anchor, binding, blocking flag, execution mode, and hazard classification are all present
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

### Requirement: An undecided rule does not prevent loading

A step definition whose rule policy is absent SHALL load successfully provided its execution mode is attestation by a person. This allows the playbook to carry work whose acceptance criterion has not yet been decided.

#### Scenario: Human-attested step with no rule policy

- **WHEN** a step definition declares human attestation as its execution mode and has no rule policy
- **THEN** the playbook loads successfully and the step reports its rule policy as absent

### Requirement: Undecided rule policies are reported

The capability SHALL report which of a loaded playbook's step definitions carry no rule policy — the steps whose acceptance criterion is still undecided — each identified by its identifier, its gate, its owning discipline, and its execution mode, so the outstanding decisions remain visible while the playbook is authored rather than surfacing one at a time.

#### Scenario: Steps without a rule policy are listed

- **WHEN** the report is requested against a playbook containing one step with a rule policy and one without
- **THEN** exactly the step without a rule policy is reported, with its identifier, gate, discipline, and execution mode

#### Scenario: A fully decided playbook reports nothing

- **WHEN** the report is requested against a playbook in which every step carries a rule policy
- **THEN** the report is empty

### Requirement: The seeded step set carries the authored v1 definitions
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
