## MODIFIED Requirements

### Requirement: Every write is validated as the playbook it would produce

A create, update, status change, retire or un-retire SHALL be validated by evaluating the **entire step set as it would stand after the write** against the launch playbook's coherence rules, and SHALL be rejected whole when that resulting set is incoherent — nothing of a rejected write is persisted. The rejection SHALL report **every** fault found, each naming the offending step or gate, exactly as loading an incoherent playbook does. This includes rejecting a write that would leave any gate without an active blocking step.

Write-side validation SHALL apply the load-side rules **and, in addition, the preconditions a load cannot check**: that a step's assignees name people the roster carries, and that an `active` `human` step names at least one who is active. Those two are functions of the roster rather than of the step set, so a load does not evaluate them (see `launch-playbook`).

Those two preconditions SHALL be evaluated over **the steps the write creates or modifies**, and never over the whole resulting set. This is not a softening: evaluating them set-wide would mean that the migrated step set — 95 active steps deliberately left unowned — refuses every subsequent create, update, retirement and status change until all 95 are assigned, which is the backfill the migration declined to invent. Scoped to the touched steps, an author who edits a migrated step must give it an owner before it saves, and every other step is left as it is until someone gets to it. The load-side rules keep their whole-set evaluation, which is what makes the set coherent by construction. The guarantee this requirement carries is therefore one-directional and SHALL be read as such: what a write cannot persist, a load cannot see — but a set a load accepts is not necessarily one a write would accept today, because the roster may have moved underneath it.

The roster those two preconditions are evaluated against is supplied by the caller, and SHALL answer to **one** stated shape. Three cases follow, and they are distinct:

1. A roster that answers the stated shape — the preconditions are evaluated, as above.
2. **No roster supplied at all** — a permitted case, meaning "these two preconditions are not being evaluated here". This is the one sanctioned way they are not applied, and it is a decision the caller makes explicitly rather than a state a write can drift into. The load-side rules are still evaluated in full.
3. A roster supplied that does **not** answer the stated shape — a defect of *wiring*, and it SHALL be refused as one: a named **error**, identifying what was supplied and what was expected, raised before any part of the write is attempted rather than reported among the write's coherence faults. The word "fault" is reserved throughout for an entry in a rejected write's fault list; this is deliberately not one. It is not a judgement about the playbook the caller submitted, so it SHALL NOT be rendered as a rejection of that submission, and a surface that renders coherence faults SHALL NOT be able to present it as one.

Case 3 SHALL never be resolvable into case 2: a roster that cannot be read SHALL NOT cause the preconditions to be skipped, and SHALL NOT allow a write to succeed as though none had been supplied. This exists because the opposite arrangement shipped — the collaborator was accepted in whichever of several shapes it happened to arrive in, the shape production actually supplied was not among them, and the failure surfaced as an internal error raised from inside the write rather than as a refusal naming the mis-wiring.

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

#### Scenario: A collaborator of the wrong shape is refused by name

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the write is refused with a named error identifying the collaborator supplied and the shape expected
- **AND** the step set is unchanged

#### Scenario: A mis-wiring is not reported as a rejection of the submission

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the refusal is raised rather than reported among the write's coherence faults, so a surface rendering those faults cannot present the mis-wiring as a fault of what was submitted

#### Scenario: A mis-shaped collaborator never passes for an absent one

- **WHEN** a write is given a roster collaborator that cannot answer who the roster carries
- **THEN** the write is not treated as one made without a roster, and the two preconditions are not skipped

#### Scenario: No roster is still a permitted case

- **WHEN** a write is made with no roster collaborator at all
- **THEN** the write proceeds, evaluating every rule except the two the roster decides
