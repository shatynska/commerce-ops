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
- a name: what the step asks for, stated briefly enough to read at a glance and occupying a single line
- the gate it must be resolved before
- the discipline that owns it — drawn from the shared vocabulary's discipline set
- its scope: whether the step concerns the product itself, or the product on one marketplace
- a timing anchor
- whether it blocks its gate
- its kind — `human` or `automated` — and whether its result needs confirmation by a person
- its lifecycle status
- its hazard classification (see below) — declared explicitly, or `none` by default when the author declares nothing

and SHALL be able to declare, optionally:

- a description: the work in full, which MAY span lines and MAY be absent when the name says everything
- its assignees: the people responsible for it
- an automation brief and a handler, where its kind is `automated`
- a provenance reference into the source material it derives from

The name is required and SHALL NOT be empty, and a name consisting only of whitespace SHALL be treated as empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty, whitespace-only, or absent name; that rejection is stated once, with the other load-time rules, rather than twice.

The name and the description are two fields because they answer to two audiences: the name is what a person scans in a list of work, and the description is what they read once they have decided to do it. Carrying one field for both forces every description to be short enough to be a name, which is why the single-line rule belongs to the name and not to the description.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, name, gate, discipline, scope, timing anchor, blocking flag, kind, confirmation flag, status, and hazard classification are all present
- **AND** its description, assignees, automation brief, handler and provenance reference are present only if authored

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

### Requirement: The seeded step set carries the authored v1 definitions

The stored step set SHALL be seeded with the authored step definitions — not started empty. The seeded set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) **completely**: every ID-bearing row of every area appears as a step, except those excluded below for restating a gate's authored metric condition, so a gate carries what the reference document puts behind it rather than a sample of it. Each seeded step's identifier SHALL be the reference document's own row ID and its provenance SHALL carry that row's source citation, so every seeded step traces to exactly one reference row.

A seeded step's **description** SHALL be the text of its reference row transcribed unaltered, except that trailing whitespace SHALL be removed, and then any trailing character in the closed set `;` `:` `,` `.` — repeating until neither whitespace nor one of those four characters remains at the end. No other character SHALL be stripped, and nothing else SHALL be changed — not the wording, the casing, or the order of clauses.

The set is closed deliberately, and is not "trailing punctuation": reference rows end variously in a closing quote, a closing parenthesis, or a `+` (as in "A+"), and each of those is part of what the row says rather than a fragment's terminal mark. A rule broad enough to remove them would silently corrupt the text it exists to preserve.

Transcribing this way is what makes every seeded description re-derivable from the reference document and comparable against it, so that a divergence between the two is detectable rather than silent. The reference document's wording belongs to the team that wrote it; the seed moves it, and does not improve it.

A seeded step's **name** SHALL be authored rather than transcribed, and SHALL be at most 80 characters. The two fields answer to different readers: a name is scanned in a list and composed into a task tracker's title, while a description is read once someone has decided to do the work. Transcribing the row into the name — as this requirement previously required — produces names with a median of 114 characters and a maximum of 253, which is a paragraph occupying a title. The authored name SHALL preserve any leading marker the row carries (`TOS RISK:`, `EU:`, `NOTE:`), because those are what a reader scans for, and SHALL preserve any numeric threshold the row states, because a threshold is the work rather than a detail of it.

An authored name is not re-derivable from the reference document, and this requirement SHALL NOT claim it is. What stays re-derivable is the description; a divergence in the text the reference owns remains detectable.

A seeded step's identifier SHALL carry its declared discipline as its second segment (`lp.creative.008` is a `creative` step). This is what allows a surface composed from the identifier to omit the discipline without losing it, and it holds for every step of the seeded set.

Rows of the reference document that restate a condition a gate already authors as a metric condition SHALL NOT additionally appear as seeded steps: one obligation is expressed once.

These guarantees describe the set the **preparation step** establishes (see *The step set is seeded before the application serves*), not the set the migration-era seed left behind. That earlier seed remains as it was — it runs exactly once per environment, from its own vendored file, and is what a database built from scratch receives before the preparation step has run.

Once established, the step set changes through the `playbook-authoring` capability and through the preparation step, and through nothing else. A step edited through authoring is thereafter governed by its recorded authorship rather than by re-derivability from the reference document; a step the preparation step re-establishes carries no authoring attribution, exactly as the migration-era seed's rows carry none.

#### Scenario: The shipped playbook loads with steps

- **WHEN** the playbook is loaded after seeding
- **THEN** it loads coherently and its step list is non-empty
- **AND** every gate has at least one step attached

#### Scenario: BUILD THE LISTING is fully represented

- **WHEN** the seeded step set is compared against the ID-bearing rows of the reference document's BUILD THE LISTING area
- **THEN** every such row's ID appears as a step identifier

#### Scenario: Every area is fully represented

- **WHEN** the seeded step set is compared against the ID-bearing rows of every area of the reference document
- **THEN** every such row's ID appears as a step identifier, except those excluded for restating a gate's authored metric condition

#### Scenario: A step traces to its source row

- **WHEN** any seeded step is read, before any authored edit to it
- **THEN** its identifier is a reference-document row ID and its provenance reference is that row's source citation
- **AND** the second segment of that identifier is the step's declared discipline

#### Scenario: A step states its work without the source document

- **WHEN** any seeded step is read
- **THEN** its name is non-empty

#### Scenario: Every description re-derives from its reference row

- **WHEN** every seeded step's description, before any authored edit to it, is compared against the text of the reference row its identifier names, reduced by the trimming rule above
- **THEN** each description equals that row's trimmed text exactly

#### Scenario: A name is short enough to title a task

- **WHEN** every seeded step's name is measured
- **THEN** none exceeds 80 characters

#### Scenario: A row's leading marker survives into its name

- **WHEN** a seeded step's reference row begins with `TOS RISK:`, `EU:` or `NOTE:`
- **THEN** its authored name begins with that same marker

#### Scenario: A gate-authored condition is not duplicated as a step

- **WHEN** the seeded step identifiers are compared against the reference rows that restate a gate's authored metric conditions
- **THEN** none of those rows' IDs appears as a step identifier

#### Scenario: The seed runs once

- **WHEN** the seed has already populated the step set and the **migration machinery** runs again
- **THEN** the step set is not re-seeded by it and authored changes made since are not overwritten by it
- **AND** this says nothing about the preparation step, which is a separate write path governed by its own requirement

### Requirement: Every gate is held by at least one blocking step

Each of the eight gates SHALL have at least one **active** blocking step attached to it before the playbook may be served to a launch, so that no gate's step obligations are trivially satisfied by an empty set. Advice, cautions and optional-at-launch work are expressed by not blocking; with `binding` removed the playbook records no separate notion of advice for a rule to key on.

This floor is a property of the **served** set, not a coherence rule. A step set that leaves a gate unheld SHALL load, and SHALL be readable and editable through the authoring surface — a set whose steps are all `draft` is a legitimate state of a playbook being written, not a malformed one. What such a set SHALL NOT do is hold a launch; see *A playbook that cannot hold a launch is not served*.

Counting only active steps is what makes the floor mean what it says: a gate whose only blocking step is a draft is a gate that would open for free, and the floor exists to make that state unservable.

#### Scenario: No gate opens for free

- **WHEN** a playbook is served to a launch and its served steps are grouped by gate
- **THEN** every gate has at least one active step with a true blocking flag

#### Scenario: A set that leaves a gate unheld still loads

- **WHEN** a step set satisfying every coherence rule leaves one or more gates with no active blocking step
- **THEN** it loads, and its authored steps are readable

#### Scenario: A set whose steps are all drafts loads

- **WHEN** every step in the set carries a status other than `active`
- **THEN** the set loads and no gate-holding fault is reported

### Requirement: The authored set exercises the full step vocabulary

The **seeded** step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring) and at least one step for every discipline in the shared vocabulary, so that no part of the vocabulary the playbook defines goes unrepresented by the work it ships with.

Every seeded step SHALL be `draft` and SHALL be `human`, and SHALL name no assignee. This is the whole point of seeding the reference document entire: 352 rows nobody has yet judged are work written down, not work in play. A seeded set is therefore **not ready** to hold a launch, and the deployment says so rather than pretending otherwise.

It follows that the seeded set SHALL NOT be required to exercise `kind`, `status` or `needs_confirmation`. Requiring an `automated` step would mean seeding a claim that code resolves it, and requiring an `active` step would mean pre-committing the review the seed exists to enable. Both are consequences of every step being a draft nobody has judged, so neither can be asked of this seed.

The **hazard** vocabulary is different and its coverage SHALL be kept: at least one `prohibited-tactic` step and at least one `compliance-obligation` step SHALL be present. A human pass has already classified rows of the reference document, and those classifications SHALL be carried across unchanged, so both are satisfiable without classifying anything new. What the seed SHALL NOT do is invent a classification for a row the human pass did not reach: a wrong `prohibited-tactic` produces a step whose only terminal outcome is `Refused` — work that can never be done — so an unreached row SHALL arrive as `none`.

That a runtime now exists to invoke handlers (`launch-step-automation`) does not change what a seed delivers, and under this requirement it changes it less than before: the seeded set carries no `automated` step at all. Registering a handler activates nothing, because activation is an authoring act performed against a deployment that registers the step's handler — never something seeding or deploying does on an author's behalf. The paragraph this replaces said the same of the two automated steps the migration-era seed delivered; the principle survives its subject.

The rule this requirement previously carried — that a suspension-risk row becomes a `prohibited-tactic` step only where it names a tactic to refuse, while a caution remains ordinary work — is superseded rather than dropped: carrying the human pass across unchanged and classifying nothing new delivers the same outcome without asking the seed to make the judgement.

Like its sibling seed requirement, this describes the seed and only the seed: it is a property of what seeding delivers, not a standing invariant of the served set. Write validation under `playbook-authoring` enforces the coherence rules, and does not additionally hold authored changes to this coverage.

#### Scenario: Anchor kinds are all present

- **WHEN** the seeded step set is grouped by timing-anchor kind
- **THEN** each of offset, window, open-ended, and recurring is represented by at least one step

#### Scenario: Every discipline appears

- **WHEN** the seeded step set is grouped by discipline
- **THEN** every discipline of the shared vocabulary is represented by at least one step

#### Scenario: Execution modes and the compliance hazard are represented

- **WHEN** the seeded step set is grouped by kind and confirmation and filtered by hazard
- **THEN** every step is `human` and none needs confirmation, so no coverage of `automated` is required of the seed
- **AND** at least one `compliance-obligation` step exists

#### Scenario: Prohibited tactics are present and never block

- **WHEN** the seeded step set is filtered to hazard `prohibited-tactic`
- **THEN** at least one such step exists
- **AND** none of them has a true blocking flag

#### Scenario: Every seeded step is a draft nobody owns

- **WHEN** the seeded step set is read
- **THEN** every step is `draft`, every step is `human`, and no step names an assignee

#### Scenario: A seeded playbook is not ready

- **WHEN** the playbook is read on a launch's behalf immediately after seeding
- **THEN** it is refused as not ready, naming every gate no surviving active blocking step holds — all eight where the seed is the whole set

#### Scenario: A registered runtime does not activate a seeded step

- **WHEN** a deployment registers step handlers and the seeded step set is read back
- **THEN** no seeded step has become `active` or `automated` — the seeded set is entirely `human` drafts, and registering a handler activates nothing

#### Scenario: Outstanding rule-policy decisions stay visible

- **WHEN** the report of what blocks activation runs over the authored set while any step cannot yet be made `active`
- **THEN** it lists exactly those steps

### Requirement: A step declares a lifecycle status, and only active steps are served

Each step definition SHALL declare a status: `draft`, `in-development`, `active` or `retired`. The status says how far the step has been carried, not what it asks for, and it decides what the rest of the system may do with it.

Only `active` steps SHALL be served to a launch, count toward a gate's obligations, or be projected to a task tracker. The playbook's own step queries — by gate, by scope — SHALL answer the **served** set, so nothing that advances a launch can be handed a draft by accident; the authored set is reached by a separate read, which is the read the admin surface already uses to reveal retired steps. `draft`, `in-development` and `retired` steps SHALL remain readable to whoever authors the step set and SHALL be excluded from every served view. A step that has not been made active is therefore free to be incomplete: this is what lets an author write down work whose automation does not exist yet, rather than inventing a description of code nobody has written.

Status SHALL be declared explicitly, with `draft` the value a step carries when its author declares nothing.

Any status MAY move to any other, and every move SHALL be a write validated by the rules of the status it moves **to**. A move into or out of `retired` is the one exception to that freedom: it SHALL be the retirement or un-retirement write itself — carrying the attribution `playbook-authoring` requires of it, and arriving at `in-development` on the way out — whatever surface asks for the change, so that a status control cannot become a second way out of `retired` that lands somewhere else and records nobody — so there is no transition table to consult beyond the target's own requirements, and no ordering a step must climb. What makes a move legal is that the step satisfies where it is going, plus the whole-set rules every write obeys: moving a step out of `active` is refused where the set is currently ready and the move would leave its gate unheld, exactly as retiring it is, and is permitted where the set is not ready — the one-directional rule `playbook-authoring` states.

"Beyond `draft`" means `in-development` or `active`, and does not include `retired`: a step abandoned before its automation was ever specified is retired without ever owing a brief, which is the honest record of what happened to it.

#### Scenario: A draft step is authored but not served

- **WHEN** a step is created with status `draft`
- **THEN** it is readable in the authored set, and the served playbook does not carry it

#### Scenario: Only active steps hold a gate

- **WHEN** a gate holds one active blocking step and one `in-development` blocking step
- **THEN** only the active one holds the gate, and the `in-development` one contributes no obligation

#### Scenario: A retired step leaves the served set without leaving the record

- **WHEN** a step's status becomes `retired`
- **THEN** it is no longer served, and it remains readable to authors with its history intact

### Requirement: A step names who does the work and whether a person accepts it

Each step definition SHALL declare a kind — `human`, meaning a person does the work, or `automated`, meaning code does — and, separately, whether the result needs confirmation by a person before the step counts as resolved.

These are two independent facts and SHALL NOT be collapsed into one. Whether the code that resolves a step calls a language model is an implementation detail of that code, and the playbook SHALL NOT record it: the thing the launch reacts to is whether a person must accept what came back.

A `human` step's confirmation flag SHALL carry no meaning — the person doing the work is the person attesting it — and SHALL be ignored rather than rejected, so that flipping a step's kind does not require clearing an unrelated field.

#### Scenario: An automated step declares whether its result is accepted

- **WHEN** an automated step is read back
- **THEN** it carries its kind and, separately, whether its result needs a person's confirmation

#### Scenario: The playbook records no automation detail beyond the kind

- **WHEN** a step's declared fields are read
- **THEN** nothing states how the automation works — only that code resolves it, and whether a person accepts the result

#### Scenario: Kind and confirmation are independent

- **WHEN** the step vocabulary is read
- **THEN** an automated step may either need confirmation or not, and neither combination is rejected

### Requirement: A step carries the brief and the handler its automation needs

An `automated` step SHALL be able to declare an automation brief — what the code must establish, in prose — and a handler naming the use case that resolves it.

Neither SHALL be required of a `draft` step. The brief SHALL be required to leave `draft`, because a step nobody can state the acceptance criterion for is not ready to be built. The handler SHALL be required to become `active`. That a handler is *present* is a property of the step set, and is checked whenever the playbook is loaded. That the running code actually **registers** it is not — it is a property of the deployed code, which changes without the step set changing — so it SHALL be checked when a step is activated and SHALL NOT be re-checked at load, for the same reason assignees are not: a rename in the registry would otherwise make every stored playbook unloadable, taking down launches to report a deployment fault. A deployment whose registry no longer answers for an `active` step's handler SHALL instead be reported at startup, where a deployment fault belongs.

A `human` step SHALL carry neither, and declaring either on one SHALL be rejected.

#### Scenario: A draft automated step needs neither

- **WHEN** an automated step is created as a draft with no brief and no handler
- **THEN** the write is accepted

#### Scenario: Leaving draft requires the brief

- **WHEN** an automated step with no automation brief is moved out of `draft`
- **THEN** the write is rejected with a fault naming the step and the missing brief

#### Scenario: A handler the code does not register cannot be activated

- **WHEN** an automated step naming a handler no registered use case answers to is made `active`
- **THEN** the write is rejected with a fault naming the step and the unknown handler

#### Scenario: A human step carries no automation fields

- **WHEN** a `human` step is written with an automation brief or a handler
- **THEN** the write is rejected with a fault naming the step

### Requirement: A step names the people responsible for it

Each step definition SHALL be able to name zero or more assignees, each referencing a person by the roster's own generated identifier (`roster`). An assignee reference SHALL be to a person the roster carries; a reference to an identifier no roster entry has SHALL be rejected, naming the step and the unknown identifier.

An `active` `human` step SHALL name at least one assignee who is active on the roster: human work nobody is responsible for is work that will not happen, and a projected task nobody is assigned is the shape that failure takes today. An `automated` step MAY name assignees — where it needs confirmation they are who is asked — and MAY name none.

Assignees SHALL be referenced by identifier rather than by name or Slack identity, so that correcting a person's details never rewrites the steps that point at them.

Both rules above are **write-time preconditions, not load-time coherence rules**, and this is deliberate. Every load-time rule is a function of the step set alone, which is what lets one predicate guard a load and a write alike; whether an assignee exists and is active is a function of the roster, which changes without the step set changing. Were these load-time rules, deactivating a person would retroactively make a stored playbook unloadable — a write in another module breaking a capability that accepted no write. A load SHALL NOT re-check assignees: a step whose assignee has since been deactivated SHALL continue to load and be served, and SHALL appear in the report of what a step still needs.

#### Scenario: An active human step needs someone responsible

- **WHEN** a `human` step naming no assignee is made `active`
- **THEN** the write is rejected with a fault naming the step

#### Scenario: An unknown person is rejected

- **WHEN** a step names an assignee identifier the roster does not carry
- **THEN** the write is rejected with a fault naming the step and that identifier

#### Scenario: A deactivated person does not satisfy the requirement

- **WHEN** a `human` step is made `active` naming only assignees whose roster entries are deactivated
- **THEN** the write is rejected, exactly as if it named nobody

#### Scenario: Correcting a person does not touch the steps

- **WHEN** a person's display name is corrected on the roster
- **THEN** every step naming them still names them, unchanged

### Requirement: An incoherent playbook is rejected against each step's status

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

Every rule below is a statement about the step set's own internal consistency, and each holds whatever the set's stage of completion. Whether the set is *finished* — whether every gate is held — is deliberately not among them: it is a property of the served set, governed by its own requirement, so that a set under construction is incomplete rather than incoherent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's name is empty, consists only of whitespace, or is not declared at all
- a step definition's name spans more than one line — a name is composed into a task's name, and a name is a single line
- a step definition is `automated` and beyond `draft` while its automation brief is absent
- a step definition is `automated` and `active` while its handler is absent
- a step definition is `human` while carrying an automation brief or a handler
- a step definition is classified `prohibited-tactic` and is also marked as blocking its gate
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

#### Scenario: A step with no name is rejected by identifier

- **WHEN** a playbook declares a step whose name is empty, consists only of whitespace, or omits the name entirely
- **THEN** loading fails with an error naming that step, in the same aggregated report as any other fault

#### Scenario: A name spanning several lines is rejected

- **WHEN** a playbook declares a step whose name contains a line break
- **THEN** loading fails with an error naming that step

#### Scenario: A description spanning several lines is accepted

- **WHEN** a playbook declares a step whose description contains line breaks
- **THEN** the playbook loads, and the description is carried unaltered

#### Scenario: Automation past draft without a brief

- **WHEN** an `automated` step beyond `draft` has no automation brief
- **THEN** loading fails with an error naming that step

#### Scenario: A prohibited tactic cannot block a gate

- **WHEN** a step definition is classified `prohibited-tactic` and marked as blocking its gate
- **THEN** loading fails with an error naming that step

#### Scenario: A gate with no active blocking step is rejected

- **WHEN** a playbook's steps leave any gate with no active step whose blocking flag is true
- **THEN** the rejection happens when that playbook is asked for in order to hold a launch, naming the gate, and not when it is loaded

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

### Requirement: What blocks a step from being activated is reported

The capability SHALL report which of the authored step set's definitions cannot yet be made `active`, each identified by its identifier, its gate, its owning discipline and its status, together with what it is missing — an automation brief, a registered handler, or an active assignee. The outstanding work of getting a step ready stays visible while the set is authored, rather than surfacing one step at a time when someone tries to activate it.

#### Scenario: Steps that cannot be activated are listed with their reason

- **WHEN** the report is requested against a set holding one ready step and one automated draft with no brief
- **THEN** exactly the draft is reported, with its identifier, gate, discipline and status, and the missing brief named

#### Scenario: A set of ready steps reports nothing

- **WHEN** the report is requested against a set in which every step can be made `active`
- **THEN** the report is empty

### Requirement: A playbook that cannot hold a launch is not served

A playbook SHALL be **ready** exactly when every gate has at least one active blocking step attached. Readiness SHALL be derived from the step set on every read and SHALL NOT be stored, so it can never disagree with the steps it summarises.

The read that serves a launch SHALL refuse a playbook that is not ready, and the refusal SHALL name the gates holding no active blocking step. The read that serves the authoring surface SHALL NOT be refused for that reason, so a set under construction stays visible and editable throughout.

Not being ready SHALL be reported as its own condition, distinguishable by a consumer from an incoherent playbook: the first is an expected stage of a set being written, the second is a defect. A playbook that is **absent** SHALL remain an error and SHALL NOT be reported as not ready — nothing to serve and nothing built yet are different failures.

The refusal SHALL additionally carry the playbook it was constructed from. A consumer that is declining to act may still owe an obligation that turns on what the set contains — `launch-clickup-sync`'s intake owes opposite treatments to a served and a non-served step's task — and a refusal that carried only the gate names would force it either to take a second read or to guess. The playbook is coherent; the only thing wrong with it is that it cannot hold a launch, which is exactly what the refusal says.

The carried playbook SHALL be used only to classify what the set contains. It SHALL NOT be used to advance, project or report on a launch, and SHALL NOT be supplied to a use case in place of a playbook obtained by a read that succeeded. Without this the refusal would hand back the very aggregate it withheld, and the guarantee that a launch is only ever advanced through a playbook that can hold one would rest on the good manners of each consumer rather than on the refusal.

#### Scenario: A launch cannot be advanced by an unready playbook

- **WHEN** a consumer asks for the playbook on a launch's behalf — to advance one, project one, or report on one — and one or more gates hold no active blocking step
- **THEN** the request is refused, and the refusal names those gates

#### Scenario: Authoring reads an unready playbook freely

- **WHEN** the authoring surface reads a step set that leaves gates unheld
- **THEN** the read succeeds and every authored step is listed, whatever its status

#### Scenario: Readiness follows the set without ceremony

- **WHEN** the last gate holding no active blocking step gains one through an ordinary authoring write
- **THEN** the next serving read succeeds, with no further action

#### Scenario: A refusal carries the set it declined to serve

- **WHEN** a consumer is refused a playbook because a gate is unheld
- **THEN** the refusal carries both the unheld gate identifiers and the playbook itself, so the consumer can tell a served step from one that is not without taking a second read

#### Scenario: The carried set may be classified but not acted on

- **WHEN** a consumer holds the playbook carried by a refusal
- **THEN** it may ask which of that set's steps are served, and may not use it to advance, project or report on a launch

#### Scenario: Not ready is distinguishable from incoherent

- **WHEN** a consumer is refused a playbook because a gate is unheld
- **THEN** the condition reported is distinct from the one reported for a playbook that violates a coherence rule

#### Scenario: An absent playbook is still an error

- **WHEN** no step set exists at all
- **THEN** the failure reported is that the playbook is absent, not that it is unready

### Requirement: The step set is seeded before the application serves

The seeded step set SHALL be established by a preparation step that runs between the schema migration and the serving process, not by the serving process itself and not by the migration machinery. Reading or writing the step set inside the server would make it open a database connection before its first request, which `database-session` forbids; and the migration machinery cannot express it, because a migration runs exactly once per environment while a reference document that gains a row must be able to deliver it later.

The step SHALL insert every vendored step no stored step names, and SHALL leave every stored step exactly as it stands — whatever its status, whatever an author has since made of it, whether or not the vendored set names it. A stored step SHALL NOT be replaced, re-dated, re-statused, un-retired, de-activated or stripped of an assignee by a seeding run.

Identity is the only question the step is entitled to ask of the stored set. Whether a stored row *differs* from its vendored counterpart is not a question it may act on, because a row that differs is indistinguishable from one an author edited — the difference is the edit. So the rule is drawn on the identifier, which `playbook-authoring` requires to be unique and never updatable, and which is therefore a key that cannot move underneath the comparison.

This is what makes the step safe to run on every container start, and why nothing arms it. Running it twice in succession SHALL change nothing the first run did not, so its condition is readable from the data in the way `roster`'s admin-seeding condition is — and a step whose condition is readable needs no signal delivered alongside it. A signal *would* have been needed for a step that replaces, because runtime configuration reaches a host only when a deployment is made, so a signal withdrawn after an armed deploy would go on arming every restart until the next one.

It follows that a **corrected** vendored definition SHALL NOT reach a step that already exists. Correcting a stored step is an authoring act, performed through the surface `playbook-authoring` governs, by someone who can see what they are changing and whose change is attributed. A wholesale refresh requires emptying the step set first, which is a deliberate destructive act and SHALL look like one.

Exit status SHALL be the whole interface — zero when the set is established, non-zero with the reason on stderr when it cannot be — so the start chain stops on a failure rather than serving a set nobody verified.

#### Scenario: An empty set receives the whole vendored set

- **WHEN** the step runs against a step set carrying none of the vendored steps
- **THEN** every vendored step is stored, and the step exits zero

#### Scenario: Running twice changes nothing the first run did not

- **WHEN** the step runs against a set that already carries every vendored step
- **THEN** nothing is written and the step exits zero

#### Scenario: A step the vendored set names is left exactly as it stands

- **WHEN** the step runs against a set holding a step whose identifier the vendored set names, which an author has renamed, activated and assigned
- **THEN** that step keeps its name, its status, its assignee and its attribution

#### Scenario: A retired step is not returned by a seeding run

- **WHEN** the step runs against a set holding a `retired` step whose identifier the vendored set names
- **THEN** that step is still `retired` afterwards, and the principal and date of its retirement are unchanged

#### Scenario: A step outside the vendored set survives

- **WHEN** the step runs against a set holding a step created through the authoring surface, which the vendored set does not name
- **THEN** it is still stored afterwards, with its status and attribution unchanged

#### Scenario: A reference row added later is delivered

- **WHEN** the vendored set gains a step no stored step names, and the step runs
- **THEN** that step is stored, and no other stored step is altered

#### Scenario: A failure leaves the previous set intact

- **WHEN** the step fails part-way through persisting the set
- **THEN** the stored set is exactly what it was before the run, and the step exits non-zero with the reason on stderr
