## ADDED Requirements

### Requirement: Activation is a validated transition

Moving a step to `active` SHALL be a write validated like any other, against the rules its kind and status carry: an `automated` step needs an automation brief and a handler the code registers; a `human` step needs at least one assignee who is active on the roster. A refused activation SHALL name the step and what it is missing, and SHALL persist nothing.

Activation SHALL be a deliberate act rather than a consequence of anything else. A handler appearing in the code does not activate the step naming it: whoever registers the handler is not necessarily whoever decides the step is ready, and a step that begins holding a gate because a deploy happened is a gate whose obligations moved without anyone choosing it.

Moving a step *out* of `active` SHALL be validated the same way, so a step cannot be un-activated where doing so would leave its gate unheld — the gate-holding floor governs the whole set, and a status change is a write like any other.

#### Scenario: An activation that satisfies its kind's rules lands

- **WHEN** an `automated` step carrying a brief and a registered handler is activated
- **THEN** the write lands and the next read serves the step

#### Scenario: A refused activation explains itself and persists nothing

- **WHEN** a `human` step naming no active assignee is activated
- **THEN** the write is refused naming the step and what it lacks, and a subsequent read observes the set exactly as it was

#### Scenario: Registering a handler does not activate anything

- **WHEN** the code begins registering a handler an `in-development` step names
- **THEN** that step's status is unchanged until someone activates it

#### Scenario: Un-activating a gate's last blocking step is refused

- **WHEN** a step is moved out of `active` while it is its gate's only active blocking step
- **THEN** the write is refused, exactly as retiring it would be

## MODIFIED Requirements

### Requirement: A step can be retired and un-retired

The system SHALL allow a step to be retired rather than deleted: retiring SHALL set the step's status to `retired`, which excludes it from the served step set, while its stored definition, its identifier, and every outcome recorded against it persist, so history stays interpretable. Retiring SHALL record the retiring principal and date. The system SHALL allow a retired step to be un-retired; un-retiring SHALL likewise record the principal and date, so a reversal of retirement is as attributed as the retirement was. No operation SHALL delete a step.

Un-retiring SHALL return the step to `in-development`, not to `active`. Retirement is no longer the inverse of un-retirement, and this is the honest consequence of activation being validated: a step retired months ago may name an assignee who has since left, or a handler nothing registers any more, and restoring it straight to the served set would either fail the write or serve a step that cannot be resolved. Returning it to `in-development` always succeeds, and activating it is the separate deliberate act it is for any other step.

#### Scenario: A retired step leaves the served set

- **WHEN** a step is retired
- **THEN** the next read of the playbook does not serve it
- **AND** its stored definition and identifier persist, with the retirement's principal and date recorded

#### Scenario: A retired step's history stays readable

- **WHEN** outcomes were recorded against a step and the step is then retired
- **THEN** those recorded outcomes remain readable and still name the step's identifier

#### Scenario: An un-retired step rejoins the served set

- **WHEN** a retired step is un-retired
- **THEN** it returns to the authored set under its original identifier as `in-development`, and is served once it is activated
- **AND** the un-retirement's principal and date are recorded

### Requirement: Every write is validated as the playbook it would produce

A create, update, status change, retire or un-retire SHALL be validated by evaluating the **entire step set as it would stand after the write** against the launch playbook's coherence rules, and SHALL be rejected whole when that resulting set is incoherent — nothing of a rejected write is persisted. The rejection SHALL report **every** fault found, each naming the offending step or gate, exactly as loading an incoherent playbook does. This includes rejecting a write that would leave any gate without an active blocking step.

Write-side validation SHALL apply the load-side rules **and, in addition, the preconditions a load cannot check**: that a step's assignees name people the roster carries, and that an `active` `human` step names at least one who is active. Those two are functions of the roster rather than of the step set, so a load does not evaluate them (see `launch-playbook`).

Those two preconditions SHALL be evaluated over **the steps the write creates or modifies**, and never over the whole resulting set. This is not a softening: evaluating them set-wide would mean that the migrated step set — 95 active steps deliberately left unowned — refuses every subsequent create, update, retirement and status change until all 95 are assigned, which is the backfill the migration declined to invent. Scoped to the touched steps, an author who edits a migrated step must give it an owner before it saves, and every other step is left as it is until someone gets to it. The load-side rules keep their whole-set evaluation, which is what makes the set coherent by construction. The guarantee this requirement carries is therefore one-directional and SHALL be read as such: what a write cannot persist, a load cannot see — but a set a load accepts is not necessarily one a write would accept today, because the roster may have moved underneath it.

#### Scenario: A rejected write reports all faults and persists nothing

- **WHEN** an update would leave a step's name empty and would also mark a `prohibited-tactic` step as blocking
- **THEN** the write is rejected reporting both faults
- **AND** the served step set is unchanged

#### Scenario: Retiring a gate's last blocking step is rejected

- **WHEN** a retire targets the only active blocking step attached to a gate
- **THEN** the write is rejected, naming the gate that would be left unheld

#### Scenario: What a write cannot persist, a load cannot see

- **WHEN** any sequence of accepted writes has been applied
- **THEN** loading the playbook succeeds — the served set is coherent by construction

#### Scenario: An untouched unowned step does not block an unrelated write

- **WHEN** a step is edited in a set that also holds `active` `human` steps naming no assignee
- **THEN** the write is judged on the step it touches, and the unowned steps elsewhere do not refuse it

#### Scenario: Editing an unowned step requires giving it an owner

- **WHEN** an `active` `human` step naming no assignee is itself updated
- **THEN** the write is refused until it names an assignee who is active

#### Scenario: A roster change does not break an accepted set

- **WHEN** the sole assignee of an `active` `human` step is deactivated on the roster
- **THEN** the playbook still loads and still serves that step, and the step is reported as needing an assignee

### Requirement: Every live step holds a slot in its gate's order

Each gate's **active** steps SHALL stand in a single authored order at all times. The step set as it stands when this capability arrives SHALL keep the order it was being served in as its initial authored order. A created step SHALL take the last slot of its gate where it is created `active`, and SHALL take no slot otherwise. An update that changes a step's gate SHALL place the step in the last slot of its new gate. A step leaving `active` — by retirement or by any other status change — SHALL be removed from its gate's order without disturbing the relative order of the steps that remain, and a step entering `active` SHALL take the last slot of its gate rather than reclaiming a remembered position.

Slots belong to the served order, so a `draft` or `in-development` step holds none: there is one order, and it is the order a launch is held to.

#### Scenario: A created step appends to its gate

- **WHEN** a step is created as `active` for a gate that already has active steps
- **THEN** the next read serves it as that gate's last step

#### Scenario: An un-retired step rejoins at the end

- **WHEN** a step is retired and later un-retired and activated
- **THEN** the next read serves it as the last step of its gate, whatever slot it held before retirement

#### Scenario: A draft holds no slot

- **WHEN** a step is created as a `draft`
- **THEN** it holds no position in its gate's order, and the gate's active steps keep the positions they had

#### Scenario: A gate change appends to the new gate

- **WHEN** an update moves a step to a different gate
- **THEN** the next read serves it as the last step of its new gate
- **AND** the steps of its old gate keep their relative order

#### Scenario: Retirement closes the gap

- **WHEN** a step is retired from the middle of its gate's order
- **THEN** the next read serves the gate's remaining steps in their previous relative order with no gap in the listing

### Requirement: A step can be created

The system SHALL allow a new step definition to be created with the full authorable shape: name, optional description, gate, discipline, scope, timing anchor, blocking flag, kind, confirmation flag, status, hazard, optional assignees, and — for an `automated` step — an optional automation brief and handler. The system SHALL generate the created step's identifier — the author does not choose it — in a namespace distinct from the seeded set's, carrying the step's discipline as its second segment (`mg.creative.001` is a `creative` step), so a step's origin and discipline stay legible from its identifier alone. The created step's provenance SHALL record the authoring principal and the creation date.

A step created as `active` SHALL be part of the served step set on the next read; a step created in any other status SHALL NOT be served, and SHALL be readable in the authored set. Creating a step as a `draft` SHALL require only what a draft carries, so that work can be written down before it is ready — which is the point of the status existing.

#### Scenario: A created step joins the served set

- **WHEN** a step is created as `active` with valid authorable fields
- **THEN** the next read of the playbook serves it, carrying a generated identifier whose second segment is its discipline
- **AND** its provenance records who created it and when

#### Scenario: Created identifiers never collide with the seeded namespace

- **WHEN** a step is created
- **THEN** its generated identifier is not in the seeded set's namespace and equals no existing step's identifier, retired steps included

### Requirement: A step can be updated

The system SHALL allow an existing step's authorable fields to be updated — seeded and authored steps alike. A step's identifier SHALL NOT be updatable, and neither SHALL its discipline: every identifier's second segment carries the discipline, and other capabilities compose surfaces that rely on that segment telling the truth, so changing a step's discipline is done by retiring the step and creating its successor. An update SHALL record the updating principal and date alongside the step's existing provenance, so a seeded step's reference citation survives its first edit while the edit itself is attributed. An updated step SHALL be served with its new field values on the next read, where its status has it served at all.

An update that changes a step's status SHALL be validated as the transition it is (see *Activation is a validated transition*), so the same rules apply however the status moves.

#### Scenario: An edit is served on the next read

- **WHEN** an active step's name is updated
- **THEN** the next read of the playbook serves the step with the new name under its unchanged identifier

#### Scenario: A discipline change is rejected

- **WHEN** an update attempts to change a step's discipline
- **THEN** the update is rejected and the step is unchanged

#### Scenario: An edit to a seeded step keeps its citation and gains attribution

- **WHEN** a seeded step is updated
- **THEN** its provenance still carries the reference row's source citation
- **AND** the update's principal and date are recorded
