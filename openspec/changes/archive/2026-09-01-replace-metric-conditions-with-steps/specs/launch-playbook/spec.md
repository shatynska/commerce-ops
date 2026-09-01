## ADDED Requirements
### Requirement: A gate's conditions are the obligations of its blocking steps

A gate's conditions SHALL be readable as one collection of step obligations: one obligation per blocking step definition attached to the gate. Step obligations SHALL be derived from the step definitions' own gate and blocking declarations — never authored a second time on the gate — so a blocking fact exists in exactly one place. A non-blocking step SHALL NOT appear among a gate's conditions. A gate SHALL carry no condition of any other kind: everything a gate waits on is a step, so that one mechanism resolves every obligation and one surface reports every unmet one.

#### Scenario: A blocking step appears as a step obligation

- **WHEN** a step definition declares gate `listable` and is marked blocking, and the `listable` gate's conditions are read
- **THEN** the conditions include a step obligation naming that step's identifier

#### Scenario: A non-blocking step produces no condition

- **WHEN** a step definition declares gate `listable` and is not marked blocking
- **THEN** the `listable` gate's conditions include no obligation for that step

#### Scenario: A gate waits on nothing but its steps

- **WHEN** any gate's conditions are read
- **THEN** every condition returned is a step obligation naming a blocking step of that gate

### Requirement: The seeded step set carries every reference row

The stored step set SHALL be seeded with the authored step definitions — not started empty. The seeded set SHALL represent the reference launch plan (`docs/reference/product-launch.md`) **completely**: every ID-bearing row of every area appears as a step, so a gate carries what the reference document puts behind it rather than a sample of it. Each seeded step's identifier SHALL be the reference document's own row ID and its provenance SHALL carry that row's source citation, so every seeded step traces to exactly one reference row.

A seeded step's **description** SHALL be the text of its reference row transcribed unaltered, except that trailing whitespace SHALL be removed, and then any trailing character in the closed set `;` `:` `,` `.` — repeating until neither whitespace nor one of those four characters remains at the end. No other character SHALL be stripped, and nothing else SHALL be changed — not the wording, the casing, or the order of clauses.

The set is closed deliberately, and is not "trailing punctuation": reference rows end variously in a closing quote, a closing parenthesis, or a `+` (as in "A+"), and each of those is part of what the row says rather than a fragment's terminal mark. A rule broad enough to remove them would silently corrupt the text it exists to preserve.

Transcribing this way is what makes every seeded description re-derivable from the reference document and comparable against it, so that a divergence between the two is detectable rather than silent. The reference document's wording belongs to the team that wrote it; the seed moves it, and does not improve it.

A seeded step's **name** SHALL be authored rather than transcribed, and SHALL be at most 80 characters. The two fields answer to different readers: a name is scanned in a list and composed into a task tracker's title, while a description is read once someone has decided to do the work. Transcribing the row into the name — as this requirement previously required — produces names with a median of 114 characters and a maximum of 253, which is a paragraph occupying a title. The authored name SHALL preserve any leading marker the row carries (`TOS RISK:`, `EU:`, `NOTE:`), because those are what a reader scans for, and SHALL preserve any numeric threshold the row states, because a threshold is the work rather than a detail of it.

An authored name is not re-derivable from the reference document, and this requirement SHALL NOT claim it is. What stays re-derivable is the description; a divergence in the text the reference owns remains detectable.

A seeded step's identifier SHALL carry its declared discipline as its second segment (`lp.creative.008` is a `creative` step). This is what allows a surface composed from the identifier to omit the discipline without losing it, and it holds for every step of the seeded set.

A reference row **whose own words make passing a gate conditional on it** SHALL be seeded as a step marked blocking on that gate. Such a row is a step in the reference document, carrying an identifier, a discipline, a timing anchor and a source citation like every other row; seeding it as anything else, or omitting it, leaves the obligation it states expressed nowhere a launch can resolve.

Where that row states a **numeric or comparative threshold on one named quantity** — rather than merely mentioning a number, and rather than conditioning the gate on several qualitative criteria — it SHALL additionally declare a metric identifier naming that quantity. The two clauses are separate on purpose: blocking says the gate waits on the row, and the identifier says which quantity the row establishes. A row conditioning a gate on criteria that name no single quantity SHALL be seeded blocking and SHALL declare no metric identifier, because an identifier invented for it would name nothing an observation could ever resolve to — the join the field exists for, filled with a value that defeats it.

Two rows MAY declare the same metric identifier. The identifier names the quantity, not the row, so two rows stating different readings of one quantity name it identically; that is the convention working rather than a collision, and the gate is then held by both steps.

The criterion is the row's own wording, not any list held elsewhere: nothing outside the reference document says which rows these are, and a document that gains such a row later gains a blocking metric step by the same reading. The judgement is made **when a row is transcribed**, by whoever transcribes it — it is an editorial reading, not a computation — so what a test asserts is the resulting set, not the selection.

A **seeded** step's metric identifier SHALL be a lowercase hyphenated noun phrase naming the quantity the threshold is on, and nothing else — not the gate, not the row, not the threshold's value (`units-fulfillable`, not `stock-ready-units` or `sixty-to-eighty-units`). Nothing validates this, no registry existing to validate against, so the convention is stated here to be followed rather than enforced: the identifier's whole purpose is that an observation of the same quantity later resolves to the same name, which an ad-hoc name silently defeats. It binds the seed, not the authoring surface: a write is rejected only on what the shared vocabulary refuses, and no validation SHALL be derived from this paragraph.

A row whose hazard forbids it from blocking SHALL NOT be made blocking by this rule. The coherence rules reject a `prohibited-tactic` step that blocks its gate, and a rule that required one would make the set unloadable rather than express the obligation.

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
- **THEN** every such row's ID appears as a step identifier, with no exception

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

#### Scenario: A threshold row is seeded as a blocking metric step

- **WHEN** a reference row conditioning a gate on a threshold on one named quantity is read from the seeded set
- **THEN** it appears as a step, is marked blocking, declares the gate its words condition, and declares a metric identifier naming that quantity

#### Scenario: A gate-conditioning row naming no single quantity blocks without an identifier

- **WHEN** a reference row whose words condition a gate on several qualitative criteria is read from the seeded set
- **THEN** it appears as a step and is marked blocking on that gate, and declares no metric identifier

#### Scenario: Two rows establishing one quantity share its identifier

- **WHEN** two reference rows state different readings of the same quantity as a condition of one gate
- **THEN** both are seeded blocking on that gate and both declare the same metric identifier

#### Scenario: A row merely mentioning a number is an ordinary step

- **WHEN** a reference row states a number without making a gate conditional on it
- **THEN** it is seeded as an ordinary step, neither blocking by virtue of the number nor declaring a metric identifier

#### Scenario: A metric identifier names the quantity alone

- **WHEN** every seeded step declaring a metric identifier is read
- **THEN** each identifier is a lowercase hyphenated noun phrase naming the quantity its threshold is on, carrying no gate name and no threshold value

#### Scenario: The seed runs once

- **WHEN** the seed has already populated the step set and the **migration machinery** runs again
- **THEN** the step set is not re-seeded by it and authored changes made since are not overwritten by it
- **AND** this says nothing about the preparation step, which is a separate write path governed by its own requirement

### Requirement: An incoherent playbook is rejected against its steps alone

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

Every rule below is a statement about the step set's own internal consistency, and each holds whatever the set's stage of completion. Whether the set is *finished* — whether every gate is held — is deliberately not among them: it is a property of the served set, governed by its own requirement, so that a set under construction is incomplete rather than incoherent.

A playbook SHALL be rejected when any of the following holds:

- its gate sequence is not exactly the eight gates named in this specification, in that order, each holding a distinct position
- a step declares a start gate naming no gate in that sequence
- a step declares a start gate later than the gate it belongs to, or naming the final gate
- the steps' dependency declarations contain a cycle
- a `blocking` step transitively depends on a step whose start gate is later than its own gate
- a gate's declared opening mode does not match the mode this specification assigns to it
- two step definitions share an identifier
- a step definition declares a gate that is not in the gate sequence
- a step definition's name is empty, consists only of whitespace, or is not declared at all
- a step definition's name spans more than one line — a name is composed into a task's name, and a name is a single line
- a step definition is `automated` and `active` while its handler is absent
- a step definition is `human` while carrying a handler
- a step definition names exactly one assignee who is also its confirmer
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

#### Scenario: A step with no name is rejected by identifier

- **WHEN** a playbook declares a step whose name is empty, consists only of whitespace, or omits the name entirely
- **THEN** loading fails with an error naming that step, in the same aggregated report as any other fault

#### Scenario: A name spanning several lines is rejected

- **WHEN** a playbook declares a step whose name contains a line break
- **THEN** loading fails with an error naming that step

#### Scenario: A description spanning several lines is accepted

- **WHEN** a playbook declares a step whose description contains line breaks
- **THEN** the playbook loads, and the description is carried unaltered

#### Scenario: A sole assignee who is also the confirmer fails to load

- **WHEN** a playbook contains a step naming exactly one assignee and naming that same person as its confirmer
- **THEN** loading fails with an error naming that step

#### Scenario: A prohibited tactic cannot block a gate

- **WHEN** a step definition is classified `prohibited-tactic` and marked as blocking its gate
- **THEN** loading fails with an error naming that step

#### Scenario: A gate with no active blocking step is rejected

- **WHEN** a playbook's steps leave any gate with no active step whose blocking flag is true
- **THEN** the rejection happens when that playbook is asked for in order to hold a launch, naming the gate, and not when it is loaded

#### Scenario: Multiple violations are reported together

- **WHEN** a playbook contains two distinct coherence violations
- **THEN** loading fails once, and the failure names both

#### Scenario: A malformed step is reported alongside a coherence violation

- **WHEN** a playbook contains one step whose timing anchor is invalid and a second, separate coherence violation
- **THEN** loading fails once, and the failure names both faults

#### Scenario: A coherent playbook loads

- **WHEN** a playbook satisfies every coherence rule
- **THEN** it loads successfully and exposes its gates and step definitions

## MODIFIED Requirements
### Requirement: A step definition declares how it is to be resolved
Each step definition SHALL declare all of:

- a unique identifier within the playbook, expressed as a human-readable slug
- a name: what the step asks for, stated briefly enough to read at a glance and occupying a single line
- the gate it must be resolved before
- the discipline that owns it — drawn from the shared vocabulary's discipline set
- its scope: whether the step concerns the product itself, or the product on one marketplace
- a timing anchor
- whether it blocks its gate
- its kind — `human` or `automated`
- its lifecycle status
- its hazard classification (see below) — declared explicitly, or `none` by default when the author declares nothing

and SHALL be able to declare, optionally:

- a description: the work in full, which MAY span lines and MAY be absent when the name says everything
- its assignees: the people responsible for it
- the gate it starts at: absent means it may start from the launch's first gate
- the steps it waits on: empty means it waits on none
- a handler, where its kind is `automated`
- a confirmer: the one person who must accept an automated result before the step counts as resolved
- a provenance reference into the source material it derives from
- a metric identifier, drawn from the shared vocabulary, naming the metric the step establishes

The name is required and SHALL NOT be empty, and a name consisting only of whitespace SHALL be treated as empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty, whitespace-only, or absent name; that rejection is stated once, with the other load-time rules, rather than twice.

The name and the description are two fields because they answer to two audiences: the name is what a person scans in a list of work, and the description is what they read once they have decided to do it. Carrying one field for both forces every description to be short enough to be a name, which is why the single-line rule belongs to the name and not to the description.

A declared metric identifier is a reference and nothing more. No metric registry exists, so nothing SHALL validate that the metric it names is defined, and the identifier SHALL NOT change how the step is resolved: a step naming a metric is resolved by its recorded outcome exactly as any other step is. It records that this step is where a named metric is established for a launch, so that an observation of the same metric can later be related to it. Almost every step declares none.

The threshold a metric step establishes SHALL live in the step's own description, as the work it asks for, rather than in a field of its own. A threshold stated as the work is what the person doing the work reads, and is editable by whoever may edit the step; a threshold carried separately would be a second place to state the same obligation.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, name, gate, discipline, scope, timing anchor, blocking flag, kind, status, and hazard classification are all present
- **AND** its description, assignees, handler, confirmer, provenance reference and metric identifier are present only if authored
- **AND** the gate it starts at and the steps it waits on are read back as declared

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

#### Scenario: A metric identifier names no defined metric

- **WHEN** a step declares a metric identifier naming a metric no registry defines
- **THEN** the playbook loads, because resolution against a metric registry is not this definition's concern

#### Scenario: A metric identifier does not change how a step resolves

- **WHEN** a step declaring a metric identifier records a satisfying outcome
- **THEN** its gate obligation counts as satisfied on that outcome alone, exactly as for a step declaring none

## REMOVED Requirements
### Requirement: A gate carries authored metric conditions

**Reason**: A gate's metric condition expressed an obligation a step already expresses, and the reference document it derives from states each such threshold as an ordinary row — carrying an identifier, a discipline, a timing anchor and a source citation. Carrying it as a second kind of condition required a second way to satisfy it, which no surface ever offered, so every gate authoring one stalled every launch that reached it.

**Migration**: Each authored condition becomes a blocking step declaring the metric identifier the condition named, seeded from the reference row that states the threshold. The threshold text moves into that step's description, where it is displayed and editable. No condition data is carried forward: none was ever satisfied.

### Requirement: Gate conditions unify step obligations and metric conditions

**Reason**: With metric conditions removed there is one kind of gate condition, so a requirement whose subject is the unification of two kinds no longer has one. Its surviving content — obligations derived from the steps' own declarations, and non-blocking steps producing none — is restated by *A gate's conditions are the obligations of its blocking steps*.

**Migration**: None. Reading a gate's conditions returns step obligations, as it did before for every gate authoring no metric condition.

### Requirement: The seeded step set carries the authored v1 definitions

**Reason**: The requirement excluded from the seed every reference row that restated a gate's authored metric condition, so that one obligation was expressed once. With gates authoring no conditions, that exclusion leaves six obligations expressed nowhere. *The seeded step set carries every reference row* replaces it, seeding those rows as blocking steps and keeping every transcription, naming and identifier rule unchanged.

**Migration**: The six excluded rows — `lp.inventory.040`, `lp.inventory.041`, `lp.strategy.025`, `lp.strategy.033`, `lp.ppc.048` and `lp.finance.036` — are seeded, each blocking, each declaring the metric identifier of the condition it restates, and each `draft` like every other seeded row. A test asserting their absence asserts their presence instead.


### Requirement: An incoherent playbook is rejected against its steps' status and shape

**Reason**: The rule set covered "malformed authored metric conditions" and rejected a playbook whose gate authored a condition with an empty threshold description. With gates authoring no conditions, that clause, that bullet and their scenario describe a fault no playbook can carry. *An incoherent playbook is rejected against its steps alone* replaces it, keeping all fourteen remaining rules and every other scenario unchanged.

**Migration**: None. A playbook that loaded before this change loads after it, one fewer rule having been applied to a construct it no longer contains.
