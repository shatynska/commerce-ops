## MODIFIED Requirements

### Requirement: A step can be created

The system SHALL allow a new step definition to be created with the full authorable shape: name, optional description, gate, discipline, scope, timing anchor, blocking flag, kind, status, hazard, optional assignees, an optional confirmer, an optional start gate, an optional set of steps it waits on, and — for an `automated` step — an optional handler. The system SHALL generate the created step's identifier — the author does not choose it — in a namespace distinct from the seeded set's, carrying the step's discipline as its second segment (`mg.creative.001` is a `creative` step), so a step's origin and discipline stay legible from its identifier alone. The created step's provenance SHALL record the authoring principal and the creation date.

A step created as `active` SHALL be part of the served step set on the next read; a step created in any other status SHALL NOT be served, and SHALL be readable in the authored set. Creating a step as a `draft` SHALL require only what a draft carries, so that work can be written down before it is ready — which is the point of the status existing.

#### Scenario: A created step joins the served set

- **WHEN** a step is created as `active` with valid authorable fields
- **THEN** the next read of the playbook serves it, carrying a generated identifier whose second segment is its discipline
- **AND** its provenance records who created it and when

#### Scenario: Created identifiers never collide with the seeded namespace

- **WHEN** a step is created
- **THEN** its generated identifier is not in the seeded set's namespace and equals no existing step's identifier, retired steps included

#### Scenario: A step is created declaring when it starts

- **WHEN** a step is created declaring a start gate and one or more steps it waits on
- **THEN** both are persisted and read back on the created step

#### Scenario: A step is created declaring neither

- **WHEN** a step is created declaring no start gate and no steps it waits on
- **THEN** it is created, and is eligible from a launch's first gate

### Requirement: Activation is a validated transition

Moving a step to `active` SHALL be a write validated like any other, against the rules its kind and status carry: an `automated` step needs a handler the code registers; a `human` step needs at least one assignee who is active on the roster. A refused activation SHALL name the step and what it is missing, and SHALL persist nothing.

Activation SHALL be a deliberate act rather than a consequence of anything else. A handler appearing in the code does not activate the step naming it: whoever registers the handler is not necessarily whoever decides the step is ready, and a step that begins holding a gate because a deploy happened is a gate whose obligations moved without anyone choosing it.

Moving a step *out* of `active` SHALL be validated the same way, and SHALL additionally be refused where the set is currently ready and the move would leave the step's gate unheld — a status change is a write like any other, and carries the same one-directional rule. Where the set is **not** ready, no such refusal applies, so a set under construction can be rearranged freely until it first becomes servable.

#### Scenario: An activation that satisfies its kind's rules lands

- **WHEN** an `automated` step carrying a registered handler is activated
- **THEN** the write lands and the next read serves the step

#### Scenario: A refused activation explains itself and persists nothing

- **WHEN** a `human` step naming no active assignee is activated
- **THEN** the write is refused naming the step and what it lacks, and a subsequent read observes the set exactly as it was

#### Scenario: Registering a handler does not activate anything

- **WHEN** the code begins registering a handler an `in-development` step names
- **THEN** that step's status is unchanged until someone activates it

#### Scenario: Un-activating a gate's last blocking step is refused

- **WHEN** a step is moved out of `active` while it is its gate's only active blocking step, in a set where every gate is currently held
- **THEN** the write is refused, exactly as retiring it would be

#### Scenario: Un-activating within a set that is not ready is permitted

- **WHEN** a step is moved out of `active` while it is its gate's only active blocking step, in a set where some other gate is already unheld
- **THEN** the write lands, since the set was not being served in the first place

### Requirement: Every write is validated as the playbook it would produce

A create, update, status change, retire or un-retire SHALL be validated by evaluating the **entire step set as it would stand after the write** against the launch playbook's coherence rules, and SHALL be rejected whole when that resulting set is incoherent — nothing of a rejected write is persisted. The rejection SHALL report **every** fault found, each naming the offending step or gate, exactly as loading an incoherent playbook does.

Leaving a gate with no active blocking step is no longer among those coherence rules (see `launch-playbook`), and SHALL instead be governed one-directionally, against the set as it stood before the write:

- A write against a set that is **already ready** SHALL be rejected when it would leave any gate with no active blocking step. This preserves the protection a launch depends on: the playbook a running launch is being held to cannot stop serving because of a single authoring action.
- A write against a set that is **not ready** SHALL NOT be rejected for leaving gates unheld. A set being built toward readiness must be able to reach it, and rejecting every activation until all eight gates are held at once would make the first activation impossible and the set unreachable from its own starting state.

This is deliberately asymmetric, and the asymmetry is the point: it is always permitted to move a set toward being served, and never permitted to move a served set away from it in a single write.

Write-side validation SHALL apply the load-side rules **and, in addition, the preconditions a load cannot check**: that a step's assignees name people the roster carries; that an `active` `human` step names at least one assignee who is active; that a step's confirmer, where one is named, is a person the roster carries; that an `active` `automated` step naming a confirmer names one who is active; and that a step named in another's `after_steps` is `active` and is not classified `prohibited-tactic`. The first four are functions of the roster rather than of the step set, so a load does not evaluate them (see `launch-playbook`). The last is a function of the step set — the load category — and sits here for a different reason, stated with the rule itself: retiring or re-classifying a step is a legitimate authoring action whose blast radius must be the write rather than every stored playbook.

Every one of these preconditions SHALL be evaluated over **the steps the write creates or modifies**, and never over the whole resulting set. This is not a softening: evaluating them set-wide would mean that the migrated step set — 95 active steps deliberately left unowned — refuses every subsequent create, update, retirement and status change until all 95 are assigned, which is the backfill the migration declined to invent. Scoped to the touched steps, an author who edits a migrated step must give it an owner before it saves, and every other step is left as it is until someone gets to it. The load-side rules keep their whole-set evaluation, which is what makes the set coherent by construction. The guarantee this requirement carries is therefore one-directional and SHALL be read as such: what a write cannot persist, a load cannot see — but a set a load accepts is not necessarily one a write would accept today, because the roster may have moved underneath it.

The dependency preconditions are functions of the step set alone and SHALL therefore be evaluated on every write, whatever the caller supplies as a roster and whether or not one is supplied at all. Only the assignee and confirmer preconditions turn on the roster, and only they are subject to the three cases below. A dependency rule skipped because no roster was supplied would be a step-set rule going unevaluated for a reason having nothing to do with it.

The roster the assignee and confirmer preconditions are evaluated against is supplied by the caller, and SHALL answer to **one** stated shape. Three cases follow, and they are distinct:

1. A roster that answers the stated shape — the preconditions are evaluated, as above.
2. **No roster supplied at all** — a permitted case, meaning "the assignee and confirmer preconditions are not being evaluated here"; the dependency preconditions are evaluated regardless. This is the one sanctioned way they are not applied, and it is a decision the caller makes explicitly rather than a state a write can drift into. The load-side rules are still evaluated in full.
3. A roster supplied that does **not** answer the stated shape — a defect of *wiring*, and it SHALL be refused as one: a named **error**, identifying what was supplied and what was expected, raised before any part of the write is attempted rather than reported among the write's coherence faults. The word "fault" is reserved throughout for an entry in a rejected write's fault list; this is deliberately not one. It is not a judgement about the playbook the caller submitted, so it SHALL NOT be rendered as a rejection of that submission, and a surface that renders coherence faults SHALL NOT be able to present it as one.

Case 3 SHALL never be resolvable into case 2: a roster that cannot be read SHALL NOT cause the preconditions to be skipped, and SHALL NOT allow a write to succeed as though none had been supplied. This exists because the opposite arrangement shipped — the collaborator was accepted in whichever of several shapes it happened to arrive in, the shape production actually supplied was not among them, and the failure surfaced as an internal error raised from inside the write rather than as a refusal naming the mis-wiring.

#### Scenario: A rejected write reports all faults and persists nothing

- **WHEN** an update would leave a step's name empty and would also mark a `prohibited-tactic` step as blocking
- **THEN** the write is rejected reporting both faults
- **AND** the served step set is unchanged

#### Scenario: Retiring a gate's last blocking step is rejected

- **WHEN** a retire targets the only active blocking step attached to a gate, in a set where every gate is currently held
- **THEN** the write is rejected, naming the gate that would be left unheld

#### Scenario: A write against a set that is not ready may leave it unready

- **WHEN** a step is activated in a set where no step is yet active, leaving seven gates still unheld
- **THEN** the write lands, and the gates still unheld are not reported as faults

#### Scenario: An untouched unowned step does not block an unrelated write

- **WHEN** a step is edited in a set that also holds `active` `human` steps naming no assignee
- **THEN** the write is judged on the step it touches, and the unowned steps elsewhere do not refuse it

#### Scenario: Editing an unowned step requires giving it an owner

- **WHEN** an `active` `human` step naming no assignee is itself updated
- **THEN** the write is refused until it names an assignee who is active

#### Scenario: A roster change does not break an accepted set

- **WHEN** the sole assignee of an `active` `human` step is deactivated on the roster
- **THEN** the playbook still loads and still serves that step, and the step is reported as needing an assignee

#### Scenario: A roster change does not break an accepted step's confirmer

- **WHEN** the confirmer of an `active` `automated` step is deactivated on the roster
- **THEN** the playbook still loads and still serves that step, and its automated results continue to be held pending

#### Scenario: A collaborator of the wrong shape is refused by name

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the write is refused with a named error identifying the collaborator supplied and the shape expected
- **AND** the step set is unchanged

#### Scenario: A mis-wiring is not reported as a rejection of the submission

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the refusal is raised rather than reported among the write's coherence faults, so a surface rendering those faults cannot present the mis-wiring as a fault of what was submitted

#### Scenario: A mis-shaped collaborator never passes for an absent one

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the write is not treated as one made without a roster, and the assignee and confirmer preconditions are not skipped

#### Scenario: No roster is still a permitted case

- **WHEN** a write is made with no roster collaborator at all
- **THEN** the write proceeds, evaluating every rule except the assignee and confirmer ones

#### Scenario: What a write cannot persist, a load cannot see

- **WHEN** any sequence of accepted writes has been applied
- **THEN** loading the playbook succeeds — the served set is coherent by construction

#### Scenario: A dependency precondition is evaluated with no roster supplied

- **WHEN** a write naming a `retired` step in another step's `after_steps` is validated with no roster supplied
- **THEN** the write is refused, the dependency precondition having been evaluated
