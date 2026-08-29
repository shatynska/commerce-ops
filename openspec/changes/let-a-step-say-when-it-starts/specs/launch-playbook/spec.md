## ADDED Requirements

### Requirement: A step declares when it may start

A step definition SHALL be able to declare when it becomes eligible for work, in two independent optional fields:

- **`starts_at_gate`** — a gate identifier the launch must have reached. Absent means the step is eligible from the launch's first gate.
- **`after_steps`** — a set of step identifiers whose steps must be resolved first. Empty means the step waits on no other step.

The two SHALL be independent, and all four combinations SHALL be representable: neither, either alone, or both at once ("once we are in `listable`, and once the photos are approved"). A step declaring neither is eligible immediately, which SHALL be the behaviour of a step whose author has said nothing.

`starts_at_gate` SHALL name a gate, not a flag, so that a step may start at a gate earlier than the one it belongs to. This is not a hypothetical: work is anchored to the launch date while gates are reached in sequence, and the two orders do not agree — the seeded set carries steps whose calendar anchor falls before their own gate can be reached.

`after_steps` SHALL be **conjunctive**: the step is eligible only once **every** step it names is resolved. It is a set rather than a single reference because a step founded on the results of several others depends on all of them, and a single reference would force that fan-in to be written as a chain — asserting an ordering among the depended-on steps that does not exist, and serialising work that could proceed in parallel. There SHALL be no disjunctive form.

**A launch SHALL be held to have released a step** when the launch's current gate is at or beyond the position of the step's `starts_at_gate`, and every step named in its `after_steps` is resolved. The gate comparison SHALL be by **position, at or beyond** — never equality: a step whose gate the launch has already passed and which is not yet resolved remains released, because work left unfinished at a gate the launch has left is exactly the work that must still be done.

Release SHALL consult no clock and perform no I/O. Its inputs are the launch's gate position, its recorded step outcomes, and the definitions of the steps it names — the last because a named step's status and hazard decide whether it counts at all. It SHALL NOT consult the current date, and a step's timing anchor SHALL take no part in it: an anchor states when work is *due*, which is a separate question from whether it may *begin*, and a rule reading the clock would make a step's eligibility differ between two passes that differ only in when they ran.

Whether the step named in `after_steps` is resolved SHALL be judged as the step's own hazard permits — the same reading of "resolved" every other consumer uses. A step classified `prohibited-tactic` SHALL NOT be depended upon at all. Its only permitted terminal outcome is `Refused` — the record that the system declined to do the thing — and sequencing other work behind a refusal is the wrong shape for a dependency, whatever a handler could in principle record. That is refused when it is authored (`playbook-authoring`, where the reasoning is stated in full), and where a step is re-classified afterwards it is satisfied vacuously on the same footing as one that is no longer `active`.

Both fields SHALL be authored facts carried on the step definition, and SHALL be read by every consumer that decides whether to **ask for** a step's work — the projection into a task tracker and the invocation of an automated step's handler — so that what the system asks of a person and what it asks of a handler cannot drift apart.

Release SHALL NOT govern what the system **accepts or evaluates**. Recording an outcome is outside it: work a person completed is work done, whenever they did it. Gate evaluation is outside it too, and this matters more: a gate's conditions are satisfied by recorded outcomes, and gating a blocking condition on release would open a gate over work that had merely not been asked for yet.

#### Scenario: A step naming neither field starts immediately

- **WHEN** a launch begins at the first gate and its served playbook carries a step declaring no `starts_at_gate` and no `after_steps`
- **THEN** the launch has released that step, whatever gate the step belongs to

#### Scenario: A step is not released before its start gate

- **WHEN** a launch stands at `commit` and a step declares `starts_at_gate` of `listable`
- **THEN** the launch has not released that step

#### Scenario: A step is released at its start gate

- **WHEN** a launch stands at `listable` and a step declares `starts_at_gate` of `listable`
- **THEN** the launch has released that step

#### Scenario: A step stays released once its gate is passed

- **WHEN** a launch stands at `stock-ready`, and an unresolved step declares `starts_at_gate` of `listable`
- **THEN** the launch has released that step, and it does not cease to be released by the launch moving on

#### Scenario: A step may start before the gate it belongs to

- **WHEN** a launch stands at `listable` and a step belonging to gate `live` declares `starts_at_gate` of `listable`
- **THEN** the launch has released that step

#### Scenario: Every named dependency must be resolved

- **WHEN** a step names three steps in `after_steps`, and two of them are resolved
- **THEN** the launch has not released that step
- **AND** when the third is resolved, the launch has released it

#### Scenario: Both fields must be satisfied

- **WHEN** a step declares `starts_at_gate` of `listable` and an `after_steps` dependency that is resolved, and the launch stands at `commit`
- **THEN** the launch has not released that step

#### Scenario: Gate opening is not gated on release

- **WHEN** a gate's blocking step is unresolved and the launch has not released it
- **THEN** the gate's condition is unsatisfied, exactly as if the step were released and unresolved

#### Scenario: Release does not consult the date

- **WHEN** the same launch and step are evaluated on two different dates with no change to the launch's gate or recorded outcomes
- **THEN** the step's release is the same on both

### Requirement: A dependency nobody is still owed is satisfied vacuously

Where a step named in another step's `after_steps` is not `active`, names no step the set carries at all, or is classified `prohibited-tactic`, that named step SHALL be treated as satisfied for the purpose of release, and SHALL NOT hold the depending step back. These are the three cases in which a named step is not something the launch is still owed, and they are stated together because a release predicate must excuse all three or none.

This case is reachable in a stored, valid step set. Naming a non-`active` step is refused when it is authored (`playbook-authoring`), but that refusal cannot cover a step becoming non-`active` *afterwards*: retiring a step is a write against that step, not against the steps that name it. A stored set therefore legitimately carries such a reference, and this rule states which way it falls rather than leaving it to be decided by accident.

It falls this way because a step that is not `active` "is not part of the launch's obligations at all" — the reading the projection into a task tracker already takes — and an obligation nobody holds cannot be one another step waits on. The alternative would freeze every dependent step of every launch in flight as the consequence of a routine authoring action.

#### Scenario: Retiring a step releases what waited on it

- **WHEN** a step's only `after_steps` dependency is retired, and the launch has reached that step's start gate
- **THEN** the launch has released the step

#### Scenario: A dependency re-classified prohibited-tactic holds nothing back

- **WHEN** a step named in another's `after_steps` is re-authored to the `prohibited-tactic` hazard, and the launch has reached the depending step's start gate
- **THEN** the launch has released the depending step, without waiting for an outcome the classification means the system will decline to produce

#### Scenario: An identifier naming no step holds nothing back

- **WHEN** a step's `after_steps` names an identifier no step in the set carries, and the launch has reached that step's start gate
- **THEN** the launch has released the step

#### Scenario: A mix of active and retired dependencies

- **WHEN** a step names two dependencies, one retired and one `active` and unresolved
- **THEN** the launch has not released the step, the `active` one still holding it

### Requirement: A step cannot start after the gate it belongs to

A playbook SHALL be rejected where any step declares a `starts_at_gate` whose position is later than the position of the step's own `gate`. The fault SHALL name the step, its gate and its start gate.

These are **load-time coherence rules**. Each is a function of the step set and the code-owned framework gates alone — nothing outside the step set can invalidate any of them — which is the test every rule in this capability is sorted by.

For a `blocking` step this state is a permanent deadlock: the gate cannot open until the step is resolved, and the step cannot start until a gate the launch can only reach by opening that one. For a step that does not block, it is merely incoherent — the step is released only after its own gate has passed, so it is overdue from the moment it appears. Both are refused, because a state with no sensible reading is better made unrepresentable than documented.

`starts_at_gate` SHALL name one of the framework's gates; a value naming no known gate SHALL be rejected, naming the step and the unknown value.

**A `starts_at_gate` naming the final gate SHALL be rejected**, for every step including those belonging to that gate. Every consumer that acts on a step stands down once a launch reaches the final gate — the task projection and the automation pass both return without doing anything — so a step released only there is released into a state in which nothing will ever act on it. For a step that blocks the final gate this is worse than inert: the gate waits on a step nothing will project, and the launch can never graduate.

The fault SHALL name the step, and SHALL say that the final gate is not a gate at which work begins, so that an author correcting it is not left to infer the rule from a refusal.

This is why the exception rule stated for the stored set below cannot be left to derive final-gate steps' values on the anchor alone: those steps are anchored *after* their gate rather than before it, which is the opposite of the case that rule catches.

#### Scenario: A start gate of the final gate is rejected

- **WHEN** a playbook carries a step whose `starts_at_gate` is `graduated`
- **THEN** the playbook is rejected, with a fault naming the step

#### Scenario: A final-gate step may not start at its own gate

- **WHEN** a playbook carries a step whose gate is `graduated` and whose `starts_at_gate` is `graduated`
- **THEN** the playbook is rejected, notwithstanding that the start gate is not later than the step's own gate

#### Scenario: A final-gate step starting earlier is accepted

- **WHEN** a playbook carries a step whose gate is `graduated` and whose `starts_at_gate` is `phase-one-complete`
- **THEN** the playbook loads, the two-gate rule binding the default rather than the load

#### Scenario: A start gate later than the step's own gate is rejected

- **WHEN** a playbook carries a step whose gate is `listable` and whose `starts_at_gate` is `live`
- **THEN** the playbook is rejected, with a fault naming the step, its gate and its start gate

#### Scenario: A start gate equal to the step's own gate is accepted

- **WHEN** a playbook carries a step whose gate is `listable` and whose `starts_at_gate` is `listable`
- **THEN** the playbook loads

#### Scenario: An unknown start gate is rejected

- **WHEN** a playbook carries a step whose `starts_at_gate` names no gate in the framework's sequence
- **THEN** the playbook is rejected, with a fault naming the step and the unknown value

### Requirement: Step dependencies form an acyclic graph that cannot deadlock a gate

`after_steps` makes the step set a directed graph. A playbook SHALL be rejected where that graph contains a cycle, the fault naming the steps forming it. A step naming itself SHALL be rejected as the cycle it is.

A playbook SHALL further be rejected where a `blocking` step depends, **transitively**, on a step whose start gate is later than the blocking step's own gate. The fault SHALL name the blocking step, the depended-on step and the two gates.

Two things about that rule are load-bearing:

**It is stated over the depended-on step's start gate, not over its own gate.** Whether a dependency can be resolved in time is decided by when it may *start*, not by which gate it belongs to. A step belonging to a later gate but starting immediately is resolvable early and is a legitimate dependency; a step belonging to the same gate but starting later is not. A rule stated over the depended-on step's `gate` would forbid the first, which is sound authoring, while the deadlock it was meant to catch is a property of the other field.

**It is transitive, not pairwise.** A chain in which each link satisfies the rule against its immediate successor can still strand the blocking step at the head: a two-hop chain whose middle step belongs to a late gate but starts early, and whose last step starts late, passes every pairwise check and deadlocks all the same.

Both are load-time rules, being functions of the step set and the framework gates alone. Determining them SHALL require no more than one traversal of the graph, the closure walked for the deadlock rule being the closure in which a cycle would be found.

The traversal SHALL range over the authored set rather than only the served one, so that a step's declarations are validated whatever its status.

**The traversal SHALL follow an edge whatever the status of the step it names, and SHALL NOT stop at a step that is not `active`.** An edge to a non-`active` step is not a fault here — that is the write-time rule's business, and a stored set legitimately carries one — but neither is it absent. Skipping such edges would make these rules disagree with themselves across a status change: a cycle or a deadlock that a set was refused for would become loadable by retiring one step in it and reappear on un-retiring it, so whether a stored set is coherent would depend on a fact the traversal had chosen to ignore.

This makes the load rules deliberately stricter than the release predicate, which does treat a non-`active` dependency as satisfied. The asymmetry is intended: the predicate answers what a launch may do with the set it has, and must never freeze; the load rules answer whether a set is worth storing, and refusing a latent deadlock costs an author one edit while admitting one costs a launch its gate.

A step MAY therefore depend on one whose start gate the launch will not reach for some time — a non-blocking step freely, and a blocking step whose own start gate precedes its gate. Such a step is released late, and where its due period passes first it is reported overdue, and puts the date at risk if it blocks, for work that cannot yet begin.

That is accepted rather than prevented. The alternative — refusing a dependency whose start gate is later than the depending step's own *start* gate — would forbid a step that legitimately begins early as preparation and genuinely needs a later input, and it is the report, not the step set, that would be being protected. The overdue mark in this case is true on its own terms: the work is late against the date it was given, and the entry names the dependency it waits on, so the reason is legible rather than mysterious. What it signals is an authored schedule that does not hang together — which is a thing worth surfacing, not suppressing.

#### Scenario: A cycle is rejected

- **WHEN** a playbook carries step A naming B in `after_steps`, B naming C, and C naming A
- **THEN** the playbook is rejected, with a fault naming the steps forming the cycle

#### Scenario: A step naming itself is rejected

- **WHEN** a playbook carries a step naming its own identifier in `after_steps`
- **THEN** the playbook is rejected

#### Scenario: A blocking step depending on a later-starting step is rejected

- **WHEN** a `blocking` step at gate `listable` names a step whose `starts_at_gate` is `live`
- **THEN** the playbook is rejected, with a fault naming both steps and the two gates

#### Scenario: A blocking step may depend on a later gate's step that starts early

- **WHEN** a `blocking` step at gate `listable` names a step belonging to gate `live` that declares no `starts_at_gate`
- **THEN** the playbook loads, the dependency being resolvable before `listable` closes

#### Scenario: A deadlock two hops away is rejected

- **WHEN** a `blocking` step at gate `listable` names a step belonging to `graduated` that starts at `commit`, and that step names a third whose `starts_at_gate` is `live`
- **THEN** the playbook is rejected, notwithstanding that each link satisfies the rule against its immediate successor

#### Scenario: The traversal does not stop at a step that is not active

- **WHEN** a cycle among three steps includes one that is `retired`
- **THEN** the playbook is rejected, the retired step's edges being followed like any other's

#### Scenario: A step may depend on one starting later than the launch has reached

- **WHEN** a non-blocking step whose start gate the launch has reached names a dependency whose start gate the launch has not reached
- **THEN** the playbook loads, and the depending step is unreleased while its due period may pass

#### Scenario: A non-blocking step is not held to the deadlock rule

- **WHEN** a step that does not block its gate depends on a step whose start gate is later than its own gate
- **THEN** the playbook loads, no gate being held by the depending step

### Requirement: The stored step set declares when its steps start

Every step the system already stores SHALL declare a `starts_at_gate`. Left undeclared, the fields introduced here would exist while changing nothing: the stored set runs to hundreds of steps, and a per-step field nobody fills in is a field that does not do its work.

Each such step SHALL declare its own gate as its start gate, subject to two exceptions:

- **A step belonging to the final gate SHALL declare a start gate at least two gates before it.** Its own gate is refused as a start gate by the rule above, so the default is not available to it, and it is the default's one systematic failure rather than a judgement about the work. Two gates rather than one because the gate immediately before the final one is a *single* gate's window: gate progression advances a launch as far as its recorded state permits within one pass, so a launch can enter and leave that gate between two runs of the passes that act on steps, and a step released only there would never be acted on at all — the same failure the final gate itself is refused for, reached by the width of the window instead of by the value.

  Two gates is a **margin and not a guarantee**. No window width can be proved sufficient: how long a launch stands at a gate depends on the pass schedules and on what that gate is waiting for, neither of which this specification fixes. What can be said is that one gate is the width at which a single scheduling coincidence suffices, and that two requires two.

  The default SHALL be the **nearest** gate satisfying the margin, and not the earliest. Widening further is not free: releasing a step earlier than it needs to be projects it earlier, which is the whole harm this capability's release rule exists to remove. The margin buys reliability for the handful of steps whose own gate cannot serve them, and is not licence to start the plan early.
- **A step whose timing anchor falls before its own gate can be reached SHALL declare the earlier gate its anchor implies.** These SHALL be individually justified by the anchor that produces them rather than applied as a rule, since the disagreement between the calendar and the gate sequence is a property of the authored playbook and not a formula.

The second exception SHALL be applied only to steps whose anchors have actually been reviewed against their gates — today, the steps that are `active`. A step that is not yet served has never been so reviewed, and choosing a start gate for it is an authoring judgement made once, by a person, on a step somebody is about to put into play, rather than one made in bulk for hundreds of steps that may never be activated in their current form. Such a step SHALL take the default, which withholds nothing today's behaviour grants and leaves the judgement to whoever activates it. Where the same steps are delivered by a vendored file in which every step is `draft`, so that status cannot select them, the exception SHALL be applied to those same reviewed steps by identifier, so the two routes cannot disagree about which steps carry one.

The two-gate rule is a **default and not a refusal**, and the difference is deliberate. A start gate naming the final gate is *always* wrong — nothing ever acts there — so it is refused. A one-gate window is only *probably* wrong: whether a launch crosses it between two passes depends on schedules and on what its gate is waiting for, and there are step sets in which one gate is plenty. Refusing it would forbid a configuration that can be correct; so the rule binds what the system chooses on an author's behalf, and an author who names a one-gate window is taken to have meant it. An author creating a final-gate step is expected to reach at least as far back as the default does unless they have a reason not to.

**This obligation SHALL cover the authored set and not merely the served one** — steps of every status, `draft` included. Most of the stored set is `draft` awaiting activation, and activation is a single authoring action. A draft left declaring nothing becomes, on the day it is activated, a step eligible in every launch at once whatever gate it belongs to — which is the behaviour this capability's release rule exists to end, re-entering by the one route a served-set-only obligation would leave open.

A step whose `starts_at_gate` has already been authored SHALL NOT be overwritten: this obligation is on the set as it stands, not on what an author has since decided.

The obligation binds **the backfill and the delivery path**, and is not a standing invariant over the stored set. "Starts immediately" remains a value an author may choose at any time through the authoring surface, and a step carrying it afterwards is not in breach of this requirement — it is a step whose author has said when it starts. What the obligation forbids is the field being left unset because nothing ever set it.

**The obligation SHALL hold for steps delivered after it is met, and not only for those stored when it was.** A step reaches the stored set by two routes — a migration, and the vendored set the system delivers on every start, which inserts what the stored set does not yet name. A field satisfied only by the first route is satisfied only for the rows that existed at the time: every row delivered afterwards arrives at whatever value the delivery mechanism supplies by default, silently, and only for steps nobody had yet. The vendored set SHALL therefore state each step's start gate itself, and delivery SHALL reject a vendored step that does not carry one rather than substituting a default, a shape fault in a file this repository ships being reported as one.

#### Scenario: A vendored step delivered later carries a start gate

- **WHEN** the vendored set is delivered and inserts a step the stored set did not name
- **THEN** that step carries a start gate, without a further backfill being run

#### Scenario: A vendored step missing a start gate is a fault

- **WHEN** the vendored set carries a step that states no start gate
- **THEN** delivery fails, reporting the step and the missing field, and inserts nothing

#### Scenario: A stored step starts at its own gate

- **WHEN** the stored step set is read after this obligation is met
- **THEN** each step whose anchor does not precede its gate's reachability declares its own gate as its start gate

#### Scenario: A stored step anchored before its gate starts earlier

- **WHEN** a stored step's timing anchor falls before its own gate can be reached
- **THEN** it declares the earlier gate its anchor implies, and not its own gate

#### Scenario: A final-gate step's default spans more than one gate

- **WHEN** the stored step set is read after this obligation is met
- **THEN** each step belonging to the final gate declares a start gate at least two gates before it

#### Scenario: A draft step declares a start gate too

- **WHEN** the stored step set is read after this obligation is met
- **THEN** a step whose status is `draft` declares a start gate on the same rule as an `active` one

#### Scenario: An activated draft does not become eligible everywhere

- **WHEN** a `draft` step carrying a start gate is activated while launches stand at earlier gates
- **THEN** those launches have not released it

#### Scenario: An author may set a step back to starting immediately

- **WHEN** an author sets a backfilled step's start gate to "starts immediately"
- **THEN** the write is accepted, this obligation binding the backfill and the delivery path rather than every later write

#### Scenario: An authored value survives

- **WHEN** a step's `starts_at_gate` has been authored before this obligation is met
- **THEN** the authored value stands

## MODIFIED Requirements

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

Gates SHALL remain the only primitive ordering the launch's **commitments** — the points at which money, stock or exposure becomes irreversible — and the only thing determining when a gate opens. A step definition MAY additionally declare steps it waits on (*A step declares when it may start*), which orders **when work is asked for** and never when a commitment is reached: a gate opens exactly when its own blocking steps are resolved and its conditions are met, whatever any step waited on before starting. That ordering is authored, acyclic, and validated so it can never leave a gate unopenable.

The distinction is the whole of it. `after_steps` cannot move a step to another gate, cannot add or remove a gate's obligations, and cannot make a gate open earlier or later given the same recorded outcomes. What it can do is stop the system asking for a step's work until the work it builds on is done — which is a statement about sequencing effort, not about the irreversibility ladder this sequence exists to express.

Step definitions attached to the same gate SHALL additionally carry an authored order relative to one another — a total order within the gate, exposed by the served step set and followed by every consumer that lists a gate's steps. This within-gate order SHALL carry no commitment semantics: it SHALL never affect when a gate opens, which steps block it, or how step completion is evaluated — reordering a gate's steps changes how they are listed, and nothing else.

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

#### Scenario: A dependency does not change when a gate opens

- **WHEN** a gate's blocking steps are all resolved, and some step at that gate declares steps it waits on
- **THEN** the gate opens exactly as it would with no such declaration, the declaration having governed only when the work was asked for

#### Scenario: A dependency does not move a step's obligations

- **WHEN** a step declaring steps it waits on is read from the served playbook
- **THEN** it belongs to the gate it declares, and that gate's conditions name it exactly as they would without the declaration


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
- the gate it starts at: absent means it may start from the launch's first gate
- the steps it waits on: empty means it waits on none
- an automation brief and a handler, where its kind is `automated`
- a provenance reference into the source material it derives from

The name is required and SHALL NOT be empty, and a name consisting only of whitespace SHALL be treated as empty. A step whose work cannot be read from the step itself is indistinguishable, to whoever is asked to do it, from a step that was never written down; the identifier names the step and the provenance says where it came from, but neither states the work. The coherence rules below reject a playbook that declares a step with an empty, whitespace-only, or absent name; that rejection is stated once, with the other load-time rules, rather than twice.

The name and the description are two fields because they answer to two audiences: the name is what a person scans in a list of work, and the description is what they read once they have decided to do it. Carrying one field for both forces every description to be short enough to be a name, which is why the single-line rule belongs to the name and not to the description.

#### Scenario: A step definition is read back with every declared attribute

- **WHEN** a step definition is read from a loaded playbook
- **THEN** its identifier, name, gate, discipline, scope, timing anchor, blocking flag, kind, confirmation flag, status, and hazard classification are all present
- **AND** its description, assignees, automation brief, handler and provenance reference are present only if authored
- **AND** the gate it starts at and the steps it waits on are read back as declared

#### Scenario: Steps can be selected by gate and by scope

- **WHEN** the playbook is queried for the steps attached to a given gate
- **THEN** exactly the step definitions declaring that gate are returned
- **AND** the same holds when querying by scope

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
