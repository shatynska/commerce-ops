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

The name is required and SHALL NOT be empty, and a name consisting only of whitespace SHALL be treated as empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty, whitespace-only, or absent name; that rejection is stated once, with the other load-time rules, rather than twice.

The name and the description are two fields because they answer to two audiences: the name is what a person scans in a list of work, and the description is what they read once they have decided to do it. Carrying one field for both forces every description to be short enough to be a name, which is why the single-line rule belongs to the name and not to the description.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, name, gate, discipline, scope, timing anchor, blocking flag, kind, status, and hazard classification are all present
- **AND** its description, assignees, handler, confirmer and provenance reference are present only if authored
- **AND** the gate it starts at and the steps it waits on are read back as declared

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

### Requirement: A step names who does the work and whether a person accepts it

Each step definition SHALL declare a kind — `human`, meaning a person does the work, or `automated`, meaning code does — and, separately, MAY name a confirmer: the one person who must accept an automated result before the step counts as resolved.

These are two independent facts and SHALL NOT be collapsed into one. Whether the code that resolves a step calls a language model is an implementation detail of that code, and the playbook SHALL NOT record it: the thing the launch reacts to is whether a named person must accept what came back.

A `human` step's confirmer SHALL carry no meaning — the person doing the work is the person attesting it — and SHALL be accepted rather than rejected, so that flipping a step's kind does not require clearing an unrelated field.

#### Scenario: An automated step declares whether its result is accepted

- **WHEN** an automated step is read back
- **THEN** it carries its kind and, separately, its confirmer, present only if one is named

#### Scenario: The playbook records no automation detail beyond the kind

- **WHEN** a step's declared fields are read
- **THEN** nothing states how the automation works — only that code resolves it, and who, if anyone, must accept the result

#### Scenario: Kind and confirmation are independent

- **WHEN** the step vocabulary is read
- **THEN** an automated step may name a confirmer or none, and neither is rejected

#### Scenario: A human step's confirmer is accepted, not rejected

- **WHEN** a `human` step is written naming a confirmer
- **THEN** the write is accepted, and the step's kind is unaffected

### Requirement: A step names the people responsible for it

Each step definition SHALL be able to name zero or more assignees, each referencing a person by the roster's own generated identifier (`roster`). An assignee reference SHALL be to a person the roster carries; a reference to an identifier no roster entry has SHALL be rejected, naming the step and the unknown identifier.

An `active` `human` step SHALL name at least one assignee who is active on the roster: human work nobody is responsible for is work that will not happen, and a projected task nobody is assigned is the shape that failure takes today. An `automated` step MAY name assignees or none; naming them no longer says who is asked to confirm a result — that is the confirmer's question alone (*A step names who confirms an automated result*).

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

### Requirement: The authored set exercises the full step vocabulary

The **seeded** step set SHALL contain at least one step for every timing-anchor kind (offset, window, open-ended, recurring) and at least one step for every discipline in the shared vocabulary, so that no part of the vocabulary the playbook defines goes unrepresented by the work it ships with.

Every seeded step SHALL be `draft` and SHALL be `human`, and SHALL name no assignee. This is the whole point of seeding the reference document entire: 352 rows nobody has yet judged are work written down, not work in play. A seeded set is therefore **not ready** to hold a launch, and the deployment says so rather than pretending otherwise.

It follows that the seeded set SHALL NOT be required to exercise `kind`, `status` or name a `confirmer`. Requiring an `automated` step would mean seeding a claim that code resolves it, and requiring an `active` step would mean pre-committing the review the seed exists to enable. Both are consequences of every step being a draft nobody has judged, so neither can be asked of this seed.

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

- **WHEN** the seeded step set is grouped by kind and confirmer and filtered by hazard
- **THEN** every step is `human` and none names a confirmer, so no coverage of `automated` is required of the seed
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

### Requirement: What blocks a step from being activated is reported

The capability SHALL report which of the authored step set's definitions cannot yet be made `active`, each identified by its identifier, its gate, its owning discipline and its status, together with what it is missing — a registered handler, or an active assignee. The outstanding work of getting a step ready stays visible while the set is authored, rather than surfacing one step at a time when someone tries to activate it.

#### Scenario: Steps that cannot be activated are listed with their reason

- **WHEN** the report is requested against a set holding one ready step and one automated draft with no handler
- **THEN** exactly the draft is reported, with its identifier, gate, discipline and status, and the missing handler named

#### Scenario: A set of ready steps reports nothing

- **WHEN** the report is requested against a set in which every step can be made `active`
- **THEN** the report is empty

## ADDED Requirements

### Requirement: An incoherent playbook is rejected against its steps' status and shape

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

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

#### Scenario: A sole assignee who is also the confirmer fails to load

- **WHEN** a playbook contains a step naming exactly one assignee and naming that same person as its confirmer
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

### Requirement: A step names who confirms an automated result

Each step definition MAY name a confirmer: a single person, referenced by the roster's own generated identifier (`roster`), trusted to accept or reject an automated step's proposed result. A confirmer reference SHALL be to a person the roster carries; a reference to an identifier no roster entry has SHALL be rejected, naming the step and the unknown identifier.

Naming a confirmer is what makes a step's result require confirmation — there is no separate flag. A step naming no confirmer needs none; its result is recorded as soon as a handler produces a terminal outcome. This is the whole of the former `needs_confirmation` flag's meaning, carried by one field instead of two.

An `active` `automated` step naming a confirmer SHALL name one who is active on the roster; a confirmer whose roster entry is deactivated stops satisfying the requirement exactly as an assignee's deactivation does, for the same reason: whether a person is active is a fact about the roster, not about the step set, so this is a **write-time precondition, not a load-time coherence rule**. A load SHALL NOT re-check it: a step whose confirmer has since been deactivated SHALL continue to load and be served, and its automated results SHALL continue to be held pending until an author names someone else.

A step whose `assignees` names exactly one person, where that person is also the confirmer, SHALL be rejected: a single actor confirming their own work is not a second opinion, and the shape can never produce one no matter how many times it is pressed. Two or more assignees naming the confirmer among them, or no assignees at all, are both unaffected by this rule — only the case where the confirmer is the step's *only* named assignee is incoherent.

This holds regardless of `kind`, including on a `human` step, where a named confirmer otherwise carries no meaning today (*A step names who does the work and whether a person accepts it*). It is authored-shape hygiene rather than a live behavioral concern for a `human` step in this deployment: nothing reads a `human` step's confirmer yet, but the identical shape is exactly what a later human-step confirmation flow — a person's own ClickUp completion checked by a second person before it counts as done — would need to reject for the same reason it is rejected for an `automated` step's Slack accept/reject today. Catching it once, at the field's own coherence rule, means that flow inherits a correct step set rather than needing to re-derive this rule itself.

Unlike the two preconditions above, this is a **load-time coherence rule**: it is a pure function of the step set's own `assignees` and `confirmer` fields, needs no roster to evaluate, and is therefore enumerated alongside the other load-time rules in *An incoherent playbook is rejected against its steps' status and shape* — a playbook already carrying this shape SHALL fail to load, not merely fail its next write.

Confirmers SHALL be referenced by identifier rather than by name or Slack identity, so that correcting a person's details never rewrites the steps that point at them — the same guarantee `assignees` already carries.

#### Scenario: An automated step names its confirmer

- **WHEN** an automated step naming a confirmer is read back
- **THEN** its confirmer identifier is present

#### Scenario: An unknown confirmer is rejected

- **WHEN** a step names a confirmer identifier the roster does not carry
- **THEN** the write is rejected with a fault naming the step and that identifier

#### Scenario: A deactivated confirmer does not satisfy the requirement

- **WHEN** an `active` `automated` step is written naming a confirmer whose roster entry is deactivated
- **THEN** the write is rejected, exactly as if it named nobody

#### Scenario: A sole assignee cannot also be the confirmer

- **WHEN** a step names exactly one assignee, and names that same person as its confirmer
- **THEN** the write is rejected with a fault naming the step

#### Scenario: A confirmer among several assignees is not rejected

- **WHEN** a step names two or more assignees, one of whom is also its confirmer
- **THEN** the write is accepted

#### Scenario: Correcting a person does not touch the steps that confirm through them

- **WHEN** a person's display name is corrected on the roster
- **THEN** every step naming them as confirmer still names them, unchanged

### Requirement: A step carries the handler its automation needs

An `automated` step SHALL be able to declare a handler naming the use case that resolves it.

The handler SHALL NOT be required of a `draft` step, and SHALL be required to become `active`. That a handler is *present* is a property of the step set, and is checked whenever the playbook is loaded. That the running code actually **registers** it is not — it is a property of the deployed code, which changes without the step set changing — so it SHALL be checked when a step is activated and SHALL NOT be re-checked at load, for the same reason assignees are not: a rename in the registry would otherwise make every stored playbook unloadable, taking down launches to report a deployment fault. A deployment whose registry no longer answers for an `active` step's handler SHALL instead be reported at startup, where a deployment fault belongs.

That startup report SHALL be produced by a process in which every handler this deployment answers for is registered. A report produced against a registry holding none of them SHALL NOT satisfy this requirement: such a report answers identically for a deployment that registers a step's handler and one that does not, and so establishes nothing about either.

The report SHALL name every `active` `automated` step whose handler is unregistered, and SHALL NOT, on account of the faults it names, prevent the deployment from starting — one unresolvable step leaves every other part of a launch working.

A `human` step SHALL carry no handler, and declaring one SHALL be rejected.

#### Scenario: A draft automated step needs no handler yet

- **WHEN** an automated step is created as a draft with no handler
- **THEN** the write is accepted

#### Scenario: A handler the code does not register cannot be activated

- **WHEN** an automated step naming a handler no registered use case answers to is made `active`
- **THEN** the write is rejected with a fault naming the step and the unknown handler

#### Scenario: The reporting process holds the deployment's own registrations

- **WHEN** the process that makes the startup report is started the way the deployment starts it
- **THEN** the registry it consults holds every handler this deployment answers for, and holds the same handlers as every other process of this deployment that consults the registry

#### Scenario: A registered handler draws no fault at startup

- **WHEN** the process that makes the startup report is started the way the deployment starts it, over a step set holding an `active` `automated` step whose handler this deployment's code registers
- **THEN** no fault is reported for that step

#### Scenario: An unregistered handler is named at startup

- **WHEN** the process that makes the startup report is started the way the deployment starts it, over a step set holding an `active` `automated` step whose handler this deployment's code does not register
- **THEN** the report names that step and the handler it could not resolve

#### Scenario: The faults the report names do not stop the deployment

- **WHEN** the startup report names one or more `active` `automated` steps whose handlers are unregistered
- **THEN** the deployment continues to start, and every step whose handler is registered is unaffected

#### Scenario: A human step carries no handler

- **WHEN** a `human` step is written with a handler
- **THEN** the write is rejected with a fault naming the step

## REMOVED Requirements

### Requirement: A step carries the brief and the handler its automation needs

**Reason**: The automation brief added no operational value once a step names a handler — the ticket that builds a handler already carries far more specification than a one-line brief held, and `description` covers what the brief was for. Its "required to leave draft" gate is removed with it; an automated step's only remaining authoring requirement is a handler, required to become `active` (see the new *A step carries the handler its automation needs*).

**Migration**: No stored data is migrated — the field and its database column are dropped outright. All data authored against it so far is test data.

### Requirement: An incoherent playbook is rejected against each step's status

Loading a playbook SHALL validate its coherence and SHALL fail rather than returning a partially valid playbook. The failure SHALL report **every** fault found, each naming the offending step or gate, so that authoring a large playbook does not require repeated load attempts to discover successive faults. This SHALL cover malformed individual step definitions — a step whose shape is wrong or whose timing anchor is invalid — and malformed authored metric conditions, as well as violations of the coherence rules below, since during a bulk import malformed steps are the likelier error and reporting them one at a time is the experience this requirement exists to prevent. Write validation under `playbook-authoring` applies these same rules to the step set a write would produce, so what a write cannot persist, a load cannot see.

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

**Reason**: One of this requirement's bullets, and the scenario *Automation past draft without a brief*, describe the removed `automation_brief` field and no longer apply. A second bullet — *a step definition is `human` while carrying an automation brief or a handler* — is edited rather than dropped, losing only its "automation brief or" clause, since the handler half still holds. A MODIFIED block cannot drop a scenario, so the requirement is replaced whole — see the renamed ADDED requirement *An incoherent playbook is rejected against its steps' status and shape*, which keeps every other bullet and scenario verbatim and adds the new sole-assignee-equals-confirmer bullet and scenario in the brief-scenario's place.

**Migration**: No stored data is migrated. Behaviorally, a playbook that (however unlikely) already has a step naming exactly one assignee who is also its confirmer now fails to load, where previously that shape had no meaning to reject.
