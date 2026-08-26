## MODIFIED Requirements

### Requirement: Every write is validated as the playbook it would produce

A create, update, status change, retire or un-retire SHALL be validated by evaluating the **entire step set as it would stand after the write** against the launch playbook's coherence rules, and SHALL be rejected whole when that resulting set is incoherent — nothing of a rejected write is persisted. The rejection SHALL report **every** fault found, each naming the offending step or gate, exactly as loading an incoherent playbook does.

Leaving a gate with no active blocking step is no longer among those coherence rules (see `launch-playbook`), and SHALL instead be governed one-directionally, against the set as it stood before the write:

- A write against a set that is **already ready** SHALL be rejected when it would leave any gate with no active blocking step. This preserves the protection a launch depends on: the playbook a running launch is being held to cannot stop serving because of a single authoring action.
- A write against a set that is **not ready** SHALL NOT be rejected for leaving gates unheld. A set being built toward readiness must be able to reach it, and rejecting every activation until all eight gates are held at once would make the first activation impossible and the set unreachable from its own starting state.

This is deliberately asymmetric, and the asymmetry is the point: it is always permitted to move a set toward being served, and never permitted to move a served set away from it in a single write.

Write-side validation SHALL apply the load-side rules **and, in addition, the preconditions a load cannot check**: that a step's assignees name people the roster carries, and that an `active` `human` step names at least one who is active. Those two are functions of the roster rather than of the step set, so a load does not evaluate them (see `launch-playbook`).

Those two preconditions SHALL be evaluated over **the steps the write creates or modifies**, and never over the whole resulting set. This is not a softening: evaluating them set-wide would mean that the migrated step set — 95 active steps deliberately left unowned — refuses every subsequent create, update, retirement and status change until all 95 are assigned, which is the backfill the migration declined to invent. Scoped to the touched steps, an author who edits a migrated step must give it an owner before it saves, and every other step is left as it is until someone gets to it. The load-side rules keep their whole-set evaluation, which is what makes the set coherent by construction. The guarantee this requirement carries is therefore one-directional and SHALL be read as such: what a write cannot persist, a load cannot see — but a set a load accepts is not necessarily one a write would accept today, because the roster may have moved underneath it.

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

#### Scenario: What a write cannot persist, a load cannot see

- **WHEN** any sequence of accepted writes has been applied
- **THEN** loading the playbook succeeds — the served set is coherent by construction

### Requirement: Activation is a validated transition

Moving a step to `active` SHALL be a write validated like any other, against the rules its kind and status carry: an `automated` step needs an automation brief and a handler the code registers; a `human` step needs at least one assignee who is active on the roster. A refused activation SHALL name the step and what it is missing, and SHALL persist nothing.

Activation SHALL be a deliberate act rather than a consequence of anything else. A handler appearing in the code does not activate the step naming it: whoever registers the handler is not necessarily whoever decides the step is ready, and a step that begins holding a gate because a deploy happened is a gate whose obligations moved without anyone choosing it.

Moving a step *out* of `active` SHALL be validated the same way, and SHALL additionally be refused where the set is currently ready and the move would leave the step's gate unheld — a status change is a write like any other, and carries the same one-directional rule. Where the set is **not** ready, no such refusal applies, so a set under construction can be rearranged freely until it first becomes servable.

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

- **WHEN** a step is moved out of `active` while it is its gate's only active blocking step, in a set where every gate is currently held
- **THEN** the write is refused, exactly as retiring it would be

#### Scenario: Un-activating within a set that is not ready is permitted

- **WHEN** a step is moved out of `active` while it is its gate's only active blocking step, in a set where some other gate is already unheld
- **THEN** the write lands, since the set was not being served in the first place
