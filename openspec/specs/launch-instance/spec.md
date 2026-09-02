# launch-instance Specification

## Purpose

Runs a concrete product's launch against the `launch-playbook` definition: persists the launch record — the recorded playbook-version audit stamp, current gate, launch date, step progress, approvals — referencing the product `product-catalog` owns, and holds the rules of the run itself: gate evaluation, step-outcome recording with provenance, due-date derivation, at-risk detection, and graduation.

## Requirements

### Requirement: A launch position is persisted for a catalog product

The system SHALL persist a launch record carrying: a reference to a catalog product by its product identifier, the `launch-playbook` version identifier the launch was started under (recorded at start as an audit stamp, never changed for the life of the launch, and read through by no behavior — every read of the playbook serves the live step set), the current gate, an optional launch date, the per-step progress recorded so far, and the gate approvals recorded so far. At most one launch record SHALL exist per product. Creating a launch for a product identifier that no catalog product has SHALL be rejected. Starting a launch SHALL be reported as a `LaunchStarted` occurrence carrying the product identifier and the recorded version identifier.

#### Scenario: A launch position is created for an existing product

- **WHEN** a launch is started for a registered catalog product, with no launch date
- **THEN** the record is persisted referencing that product with the served playbook's version identifier recorded, the launch date is reported as absent, and a `LaunchStarted` occurrence is reported

#### Scenario: A launch position for an unknown product is rejected

- **WHEN** a launch is started for a product identifier no catalog product has
- **THEN** the start is rejected and nothing is persisted

#### Scenario: A second launch position for the same product is rejected

- **WHEN** a launch is started for a product that already has a launch record
- **THEN** the start is rejected and the existing record is unchanged

### Requirement: A product's current gate is restricted to the launch-playbook gate sequence

A launch record's current gate SHALL be one of the eight gate ids `launch-playbook` defines (`commit`, `order`, `listable`, `stock-ready`, `live`, `ignition`, `phase-one-complete`, `graduated`). A newly started launch SHALL begin at `commit`, the first gate in that sequence; a launch is never started at any other gate. Persisting a current gate outside the eight SHALL be rejected.

#### Scenario: A new product defaults to the first gate

- **WHEN** a launch is started
- **THEN** its current gate is reported as `commit`

#### Scenario: An unrecognized gate is rejected

- **WHEN** an attempt is made to persist a launch record whose current gate is not one of the eight `launch-playbook` gate ids
- **THEN** the operation is rejected and the stored gate is unchanged

### Requirement: A launch position can be read back by product identifier

The system SHALL retrieve a persisted launch record given the product identifier it references — the recorded version identifier, current gate, launch date, every recorded step progress with its provenance, and every gate approval — and SHALL report absence rather than an error when the product has no launch record.

A read made on a caller's behalf SHALL additionally be subject to that caller's access scope: a launch whose product identifier the scope does not permit SHALL report the same absence as a product with no launch record, so that a read can never confirm the existence of a launch the caller may not see. The scope decides whether a read yields a record at all; it SHALL NOT change what a retrieved record carries, and it SHALL NOT require any particular read to carry the whole persisted record.

#### Scenario: A launch position is retrieved

- **WHEN** a launch that has recorded step outcomes and a gate approval is read using its product identifier
- **THEN** the record is returned with the recorded version identifier, current gate, launch date, each step's outcome and provenance, and each approval it was persisted with

#### Scenario: A product without a launch position reports absence

- **WHEN** a launch record is read for a product identifier that has none, under any scope
- **THEN** the system reports that none exists, rather than an error

#### Scenario: An out-of-scope launch reports the same absence

- **WHEN** a launch record is read on a caller's behalf for a product identifier that caller's scope does not permit
- **THEN** the system reports that none exists, exactly as it does for a product with no launch record

### Requirement: A step outcome is recorded with provenance

The system SHALL record, against a launch, an outcome for a step the served playbook defines, using the `launch-playbook` outcome vocabulary (`NotStarted`, `InProgress`, `Satisfied`, `Blocked` with a reason, `Refused`, `NotApplicable` with a reason). Every recorded outcome — non-terminal ones included — SHALL carry recording provenance: a source (`clickup` or `automated`), who recorded it, when, and evidence. Completion is always recorded, never inferred. Terminal outcomes SHALL be restricted by the step's hazard as `launch-playbook` defines: a `prohibited-tactic` step can only terminate in `Refused`; any other step terminates in `Satisfied` or `NotApplicable` and can never be `Refused`. A later recording for the same step SHALL replace the stored outcome and its provenance — the hazard restrictions apply to every recording — and a re-recording SHALL NOT reverse a gate that has already opened. Recording an outcome for a step identifier the served playbook does not define — an identifier that never existed and a retired step's alike — SHALL be rejected; outcomes already recorded against a step before its retirement remain stored and readable. A step reaching `Satisfied` SHALL be reported as a `StepSatisfied` occurrence; a step reaching `Refused` SHALL be reported as a `StepRefused` occurrence.

A step establishing a metric is recorded through this same path, with the source that recorded it — there is no source naming the significance of the step rather than the channel the outcome arrived through.

#### Scenario: A satisfied step is recorded with its provenance

- **WHEN** a `Satisfied` outcome is recorded for a defined step with source `clickup`, a named recorder, a timestamp, and evidence
- **THEN** reading the launch back reports that step's outcome as `Satisfied` with exactly that provenance, and a `StepSatisfied` occurrence is reported

#### Scenario: A re-recorded outcome replaces the stored one without reopening gates

- **WHEN** a step recorded as `Satisfied` is later re-recorded as `Blocked` with a reason, after the gate it is attached to has already opened
- **THEN** the stored outcome and provenance are replaced, and the launch's current gate is unchanged

#### Scenario: A prohibited-tactic step is refused

- **WHEN** a `Refused` outcome is recorded for a step classified `prohibited-tactic`
- **THEN** the outcome is recorded and a `StepRefused` occurrence is reported

#### Scenario: Satisfying a prohibited-tactic step is rejected

- **WHEN** a `Satisfied` outcome is recorded for a step classified `prohibited-tactic`
- **THEN** the recording is rejected and the step's stored outcome is unchanged

#### Scenario: Refusing an ordinary step is rejected

- **WHEN** a `Refused` outcome is recorded for a step not classified `prohibited-tactic`
- **THEN** the recording is rejected and the step's stored outcome is unchanged

#### Scenario: An unknown step identifier is rejected

- **WHEN** an outcome is recorded for a step identifier the served playbook does not define
- **THEN** the recording is rejected

### Requirement: A gate opens only when every blocking condition attached to it is satisfied

A launch SHALL advance from its current gate only to the next gate in the `launch-playbook` sequence — gates advance monotonically, are never skipped, and never move backwards. The current gate SHALL open only when every blocking condition attached to it is satisfied: every step obligation (a blocking step attached to the gate) has reached a permitted terminal outcome (`Satisfied` or `NotApplicable`). A `Refused` outcome never satisfies any condition. Advancing SHALL be reported as a `GateOpened` occurrence; an advance attempted while any blocking condition is unsatisfied SHALL be rejected and reported as a `GateBlocked` occurrence naming each unsatisfied condition.

A gate waits on its blocking steps and on nothing else, so a threshold a gate turns on holds it as the obligation of the step that establishes it, satisfied by that step's recorded outcome.

#### Scenario: An automatic gate opens when every blocking condition is satisfied

- **WHEN** every blocking condition attached to the current automatic gate is satisfied and the launch is advanced
- **THEN** the current gate becomes the next gate in the sequence and a `GateOpened` occurrence is reported

#### Scenario: An advance with an unresolved blocking step is rejected

- **WHEN** the launch is advanced while a blocking step attached to the current gate has not reached a permitted terminal outcome
- **THEN** the advance is rejected, the current gate is unchanged, and a `GateBlocked` occurrence names that unsatisfied condition

#### Scenario: A refused prohibited-tactic step never holds a gate closed

- **WHEN** a non-blocking `prohibited-tactic` step attached to the current gate is `Refused` and every blocking condition attached to that gate is satisfied
- **THEN** the launch advances — refusal neither satisfies nor blocks any condition

#### Scenario: An advance moves to exactly the next gate

- **WHEN** the launch advances from its current gate
- **THEN** the current gate becomes exactly the next gate in the `launch-playbook` sequence — the advance operation offers no way to target a later or an earlier gate, so gates can never be skipped and never move backwards

#### Scenario: An unresolved metric step holds its gate closed

- **WHEN** the launch is advanced while a blocking step declaring a metric identifier, attached to the current gate, has no permitted terminal outcome
- **THEN** the advance is rejected and a `GateBlocked` occurrence names that step, exactly as for any other blocking step

### Requirement: A confirmation gate additionally requires a recorded approval

For a gate whose `launch-playbook` opening mode is `requires-confirmation`, the launch SHALL advance only when, in addition to every blocking condition being satisfied, an approval for that gate has been recorded carrying the decision, a named approver, and a timestamp. An approval's decision SHALL be either approving or rejecting; only an approving decision satisfies the approval requirement — a rejecting decision is recorded but keeps the gate closed. An approval without a named approver SHALL be rejected. An approval naming a posture for any gate other than `graduated` SHALL be rejected. An automatic gate SHALL NOT require an approval.

#### Scenario: A confirmation gate with satisfied conditions but no approval stays closed

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied but no approval for it has been recorded, and the launch is advanced
- **THEN** the advance is rejected and the current gate is unchanged

#### Scenario: A confirmation gate opens once approved

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied and an approval with a named approver is recorded
- **THEN** the launch advances and a `GateOpened` occurrence is reported

#### Scenario: An approval without a named approver is rejected

- **WHEN** a gate approval is recorded without a named approver
- **THEN** the recording is rejected

#### Scenario: A rejecting decision keeps the gate closed

- **WHEN** every blocking condition attached to the current `requires-confirmation` gate is satisfied, an approval with a rejecting decision is recorded, and the launch is advanced
- **THEN** the advance is rejected and the current gate is unchanged

#### Scenario: A posture on a non-graduation approval is rejected

- **WHEN** an approval for a gate other than `graduated` names a posture
- **THEN** the recording is rejected

### Requirement: Step due dates derive from the launch date and re-resolve when it moves

When a launch has a launch date, every step's due period SHALL derive from that date and the step's `launch-playbook` timing anchor. When the launch has no launch date, due periods SHALL be reported as absent rather than invented. Moving the launch date SHALL re-resolve every step's due period at once from the new date and SHALL be reported as a `LaunchDateMoved` occurrence carrying the previous and new dates.

#### Scenario: A step's due period derives from the launch date

- **WHEN** a launch has a launch date and a step's timing anchor is an offset of -30 days
- **THEN** that step's due period is reported as the single day 30 days before the launch date

#### Scenario: Without a launch date there are no due periods

- **WHEN** a launch has no launch date
- **THEN** every step's due period is reported as absent

#### Scenario: Moving the launch date re-resolves every due period

- **WHEN** the launch date is moved to a date 14 days later
- **THEN** every step's due period is reported re-resolved from the new date, and a `LaunchDateMoved` occurrence carries the previous and new dates

### Requirement: The launch date is reported at risk when a blocking unresolved step is overdue

Evaluated as of a given date, a launch with a launch date SHALL be reported at risk — a `LaunchDateAtRisk` occurrence naming each such step — when any blocking step **whose start gate the launch has reached** has had its due period fully pass without reaching a permitted terminal outcome. A launch with no launch date, or whose overdue steps are all non-blocking or already resolved, SHALL NOT be reported at risk. A blocking step whose start gate the launch has not reached SHALL NOT put the date at risk, on the same reasoning the overdue rule above records: work nobody has been asked for is not work anyone is late with.

As with overdue, the exclusion turns on the start gate alone. A blocking step the launch has reached but which waits on an unresolved dependency SHALL put the date at risk: it is holding its gate, its due period has passed, and nothing else in the report would say so — the dependency it waits on may not itself be overdue, or may not be blocking, and in neither case would it raise the occurrence. This is the case in which the at-risk signal matters most, and an exclusion drawn any wider than the start gate would remove it.

What is excluded is only the work of the gates ahead of the launch. Whatever is holding the launch up at the gate it actually stands at is still reported.

#### Scenario: An overdue unresolved blocking step puts the date at risk

- **WHEN** the launch is evaluated on a date after a released blocking step's due period has fully passed and that step has not reached a permitted terminal outcome
- **THEN** a `LaunchDateAtRisk` occurrence is reported naming that step

#### Scenario: An overdue non-blocking step does not put the date at risk

- **WHEN** the only steps whose due periods have passed unresolved are non-blocking
- **THEN** no `LaunchDateAtRisk` occurrence is reported

#### Scenario: A resolved overdue step does not put the date at risk

- **WHEN** every blocking step whose due period has passed has reached a permitted terminal outcome
- **THEN** no `LaunchDateAtRisk` occurrence is reported

#### Scenario: A launch without a launch date is never at risk

- **WHEN** a launch with no launch date is evaluated
- **THEN** no `LaunchDateAtRisk` occurrence is reported

#### Scenario: A blocking step whose start gate is not reached does not put the date at risk

- **WHEN** a launch standing at `commit` holds an unresolved blocking step that starts at `live` and whose due period has fully passed
- **THEN** no `LaunchDateAtRisk` occurrence is reported naming that step

#### Scenario: A blocking step held by a dependency puts the date at risk

- **WHEN** a launch has reached a blocking step's start gate, that step waits on an unresolved dependency which is not itself overdue, and the blocking step's due period has fully passed
- **THEN** a `LaunchDateAtRisk` occurrence is reported naming that blocking step

#### Scenario: The gate the launch stands at still puts the date at risk

- **WHEN** a launch standing at `listable` has an unresolved blocking `listable`-gate step whose due period has fully passed
- **THEN** a `LaunchDateAtRisk` occurrence is reported naming that step

### Requirement: Graduation stamps the catalog product steady-state

Opening the `graduated` gate SHALL be reported as a `LaunchGraduated` occurrence, and the system SHALL then — after the advanced launch is persisted — attempt to change the referenced catalog product's lifecycle stage, through the `product-catalog` capability, to steady state with a posture chosen by the graduation approver — the system never chooses a posture itself — recording that approver as the stage change's human confirmer. When `product-catalog`'s transition rules reject the stage change (the product is not in a stage from which steady state is reachable), the advance SHALL stand, no stage SHALL change, and the failure SHALL be reported as an error naming the manual catalog correction required. A graduation approval that does not name a posture SHALL be rejected.

#### Scenario: Graduation stamps the product with the approver's chosen posture

- **WHEN** every blocking condition on `graduated` is satisfied for a product in a launching stage and an approval naming an approver and a posture is recorded, and the launch is advanced
- **THEN** a `LaunchGraduated` occurrence is reported and the catalog product's stage becomes steady state with the chosen posture, confirmed by that approver

#### Scenario: A rejected stage stamp leaves the advance standing

- **WHEN** the `graduated` gate opens for a product whose current stage does not permit a transition to steady state
- **THEN** the launch's current gate remains `graduated`, the product's stage is unchanged, and an error is reported naming the manual catalog correction required

#### Scenario: A graduation approval without a posture is rejected

- **WHEN** an approval for the `graduated` gate is recorded without naming a posture
- **THEN** the recording is rejected

### Requirement: Launch positions are enumerable with their reports

The system SHALL report every persisted launch position whose referenced product identifier the caller's access scope permits, each with the same content a single-product read yields (steps with due periods and recorded progress, and the at-risk evaluation), evaluated as of a caller-supplied date; under the unrestricted scope every persisted position SHALL be reported. Enumeration SHALL NOT filter by lifecycle: the launch context does not own a product's stage, and its persisted shape deliberately does not distinguish a graduated launch from one standing at the final gate — whoever consumes the enumeration filters by the catalog's stage stamp. Scope filtering is visibility, not lifecycle: it decides whose launches the caller may see at all, never which stage of launch is worth reporting.

#### Scenario: All launch positions are reported

- **WHEN** several launch positions exist and the launches are enumerated as of a date under the unrestricted scope
- **THEN** every persisted launch position SHALL be reported, each with its steps' due periods, recorded progress, and at-risk evaluation as of that date

#### Scenario: A restricted scope enumerates only its launches

- **WHEN** several launch positions exist and the launches are enumerated under a scope permitting some of their product identifiers but not others
- **THEN** exactly the launch positions of the permitted products SHALL be reported

#### Scenario: No launches yields an empty enumeration

- **WHEN** no launch position exists and the launches are enumerated
- **THEN** the system SHALL report an empty result, not an error

#### Scenario: A scope permitting nothing enumerates nothing

- **WHEN** launch positions exist and the launches are enumerated under a scope that permits no product identifier
- **THEN** the system SHALL report an empty result, not an error

### Requirement: The launch report carries each step's discipline and names the steps behind an at-risk date

The launch report SHALL carry, on each step entry, the owning discipline the playbook assigns to that step, and its at-risk evaluation SHALL name the overdue blocking steps that produced it. The report is the whole of what a consumer may know about a launch: a fact a consumer needs SHALL travel on the report rather than be re-derived from the playbook outside the launch context.

#### Scenario: A step entry carries its owning discipline

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL carry the discipline the playbook assigns to that step

#### Scenario: The at-risk evaluation names its overdue blocking steps

- **WHEN** a launch's report states the launch date is at risk
- **THEN** the at-risk evaluation SHALL name each overdue blocking step that produced it

### Requirement: The launch report states whether the current gate awaits confirmation

The launch report SHALL state that the current gate awaits confirmation exactly when that gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval has been recorded for it. In every other case — an automatic gate, unsatisfied blocking conditions, an approval already recorded, or a launch that has already graduated — the report SHALL state that it does not.

#### Scenario: A satisfied confirmation gate without an approval awaits confirmation

- **WHEN** the current gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval is recorded for it
- **THEN** the launch report SHALL state the gate awaits confirmation

#### Scenario: Unsatisfied blocking conditions mean the gate is not awaiting confirmation

- **WHEN** the current gate requires confirmation and at least one blocking condition attached to it is unsatisfied
- **THEN** the launch report SHALL state the gate does not await confirmation

#### Scenario: A recorded approving approval ends the wait

- **WHEN** the current gate requires confirmation, its blocking conditions are satisfied, and an approving approval is recorded for it
- **THEN** the launch report SHALL state the gate does not await confirmation

#### Scenario: An automatic gate never awaits confirmation

- **WHEN** the current gate opens automatically
- **THEN** the launch report SHALL state the gate does not await confirmation, whatever its conditions' state

### Requirement: The launch report names each step

The launch report SHALL carry, on each step entry, the name the served
playbook gives that step, alongside the identifier it already carries.

This follows the principle the report's existing requirement already
states — "a fact a consumer needs SHALL travel on the report rather than
be re-derived from the playbook outside the launch context" — applied to
the one fact every human-facing consumer needs first. A report carrying
only `lp.listing.007` obliges each consumer to obtain the step set and
join against it, which is the arrangement that principle exists to
prevent.

The name SHALL be the served playbook's name for the step at the time the
report is produced. The report is not a historical record and does not
claim to name the step as it was called when its outcome was recorded.

#### Scenario: A step entry carries its name

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL carry the name the served playbook gives that step

#### Scenario: The name follows the served playbook

- **WHEN** a step's name is changed through the authoring writes and a launch is then read back
- **THEN** the step entry SHALL carry the changed name

### Requirement: The launch report states whether each step blocks

The launch report SHALL carry, on each step entry, whether the playbook
attaches that step to its gate as a blocking obligation.

The report already carries this in practice and no requirement demands
it, which is the gap this closes rather than a behaviour it introduces. A
consumer distinguishing work that holds a gate from work that does not —
which any presentation of a launch must — would otherwise have to consult
the playbook to learn it, and the governing principle quoted above
forbids exactly that.

#### Scenario: A step entry states whether it blocks

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL state whether that step blocks its gate

### Requirement: The launch report states whether each step is overdue

The launch report SHALL carry, on each step entry, whether that step is
overdue as of the date the report is evaluated for — its due period
having fully passed without the step reaching a terminal outcome its
hazard permits — for blocking and non-blocking steps alike, and whether
or not the launch's date is reported at risk.

**A step whose start gate the launch has not reached SHALL NOT be reported overdue**, whatever its due period says. Its due period is derived from the launch date and may well have passed; reporting it overdue states a failure that has not occurred and attributes it to whoever the step names. Nobody has been asked for the work, so there is nothing anyone has failed to do, and a launch delayed at an early gate would otherwise accumulate overdue marks against the whole of the plan ahead of it.

**The exclusion SHALL turn on the start gate alone, and not on the step's dependencies.** A step whose start gate the launch has reached is work whose gate the launch has arrived at — it is inside the plan the launch is currently working, even though the system is not yet asking anyone for it. That a step it waits on is unresolved is a delay *within* work already in scope, which is what an overdue mark is for.

The reason to keep it in is that nothing else would report it. The dependency holding it may not itself be overdue, and may not be blocking, so neither the overdue rule nor the at-risk rule would raise anything for it — and the launch would sit unable to open its gate while every surface said it was healthy. Excluding it would mean the later a dependency ran, the quieter the report became. Such a step SHALL be reported overdue on its own entry, alongside the dependency its entry already names.

This is settled here, and never on a surface. Overdue is derived in the launch context and carried on the report precisely so that no consumer recomputes it; a surface suppressing the mark on its own would leave this report, the daily briefing and that surface stating different things about one step. The suppression is part of what overdue *means*, not part of how it is shown.

This is the third fact the report carries in practice with no requirement
behind it, and the one whose absence bites hardest. The existing at-risk
requirement names overdue steps **only** where they are blocking **and**
only when the launch is at risk, so an overdue non-blocking step on a
healthy launch is nowhere in the specified report — while `briefing`
already derives a monitor item from exactly that step, and any
presentation of a launch must show it.

It cannot be re-derived outside the launch context. Which terminal
outcomes resolve a step depends on the step's hazard — a
`prohibited-tactic` step is resolved by `Refused` — so a consumer
computing overdue from the due period and the recorded outcome alone
would mark such a step overdue forever. That is precisely what this
capability's governing principle forbids: a fact a consumer needs travels
on the report rather than being re-derived from the playbook.

#### Scenario: An overdue non-blocking step is reported overdue

- **WHEN** a launch that is not reported at risk holds a released non-blocking step whose due period has fully passed unresolved
- **THEN** that step's entry SHALL state that it is overdue

#### Scenario: An overdue blocking step is reported overdue on its own entry

- **WHEN** a launch is reported at risk, its at-risk evaluation naming an overdue blocking step
- **THEN** the entry for the step the at-risk evaluation names SHALL state that it is overdue

#### Scenario: A step resolved under its own hazard is not overdue

- **WHEN** a step whose hazard permits only `Refused` has reached `Refused` and its due period has fully passed
- **THEN** that step's entry SHALL NOT state that it is overdue

#### Scenario: A step with no due period is not overdue

- **WHEN** a launch has no launch date, so no step's due period resolves
- **THEN** no step entry SHALL state that it is overdue

#### Scenario: A recurring-anchor step on a dated launch is not overdue

- **WHEN** a launch has a launch date and holds a step whose timing anchor is recurring, so it resolves to no due period
- **THEN** that step's entry SHALL NOT state that it is overdue

#### Scenario: A step whose start gate is not reached is not overdue though its due period passed

- **WHEN** a launch standing at `commit` holds an unresolved step that starts at `listable` and whose due period has fully passed
- **THEN** that step's entry SHALL NOT state that it is overdue

#### Scenario: A step held only by a dependency is still overdue

- **WHEN** a launch has reached a step's start gate, the step is held only by an unresolved `after_steps` dependency, and its due period has fully passed
- **THEN** that step's entry SHALL state that it is overdue, and SHALL still name the dependency it waits on

#### Scenario: A step becomes overdue once the launch releases it

- **WHEN** a launch advances to the start gate of an unresolved step whose due period has already fully passed
- **THEN** that step's entry SHALL state that it is overdue from that point

### Requirement: The launch report places each step in its gate and names the gate sequence

The launch report SHALL carry, on each step entry, the gate the playbook
attaches that step to, and SHALL name the gate sequence in its order.

A consumer presenting a launch shows where it stands in a sequence and
which work belongs to which gate; without both facts on the report it
must obtain the playbook and the gate framework itself, which is what
this capability's governing principle forbids and what the requirements
above exist to avoid.

The sequence travels with the report rather than being looked up because
a consumer that had to find it would need the gate framework, not merely
the step set — a heavier dependency than the one already refused, and one
that carries the gate *order* as well as the gate names.

#### Scenario: A step entry carries its gate

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL carry the gate the playbook attaches that step to

#### Scenario: The report names the gates in order

- **WHEN** a launch is read back or enumerated
- **THEN** the report SHALL name the gate sequence in its order, and the launch's current gate SHALL be one of them

### Requirement: The launch report carries one entry per served step, in the served order

The report SHALL carry one entry per served step, whether or not an
outcome has been recorded for it, and those entries SHALL arrive in the
served playbook's own order: gate sequence order, and within a gate the
authored order that gate's steps carry.

Both are relied on and neither is stated today. `launch-playbook` gives
each gate's steps a total authored order "followed by every consumer that
lists a gate's steps" — a consumer reading the report has no other way to
follow it, since the order is a property of the served set and no entry
carries a position. And a report holding only the recorded steps could
not distinguish a step nobody has touched from one recorded as not
started, which is a distinction the recording provenance exists to make.

Stated apart from the gate requirement above because neither obligation
is about gates, and a later change touching one should not have to
reproduce the other.

#### Scenario: The report carries an entry for a step with no recorded outcome

- **WHEN** a launch is read back and a served step has no recorded outcome
- **THEN** the report SHALL carry an entry for that step

#### Scenario: Step entries arrive in the served playbook's order

- **WHEN** a launch is read back or enumerated
- **THEN** the report's step entries SHALL be ordered by gate in the gate sequence's order, and within each gate by that gate's authored step order

### Requirement: The launch report states whether each step has started, and what it waits for

The launch report SHALL carry, on each step entry, whether the launch has released that step (`launch-playbook`, *A step declares when it may start*), and where it has not, what the step is waiting for: the gate it starts at where the launch has not reached it, and the identifiers of the steps named in its `after_steps` that are not yet resolved.

It travels on the report for the reason every other derived fact here does: it cannot be re-derived by a consumer. Release depends on the gate sequence's *positions* and on which terminal outcomes each named step's hazard permits, and a surface that read the playbook to work that out would be the one place the arrangement this capability keeps — that a fact a consumer needs travels on the report rather than being recomputed from the playbook — was broken.

The unresolved dependencies SHALL be named by identifier, so that a consumer can state what a step waits for without a second read.

#### Scenario: A released step is reported as released

- **WHEN** a launch's report is produced and the launch has released a step
- **THEN** that step's entry states that it has started, and names nothing it waits for

#### Scenario: An unreleased step names the gate it starts at

- **WHEN** a launch standing at `commit` holds a step whose start gate is `listable`
- **THEN** that step's entry states that it has not started, and names `listable` as the gate it starts at

#### Scenario: An unreleased step names its unresolved dependencies

- **WHEN** a step the launch has reached the start gate of names two `after_steps` dependencies, one resolved and one not
- **THEN** that step's entry names only the unresolved one

#### Scenario: A step waiting on both names both

- **WHEN** a step is held back by its start gate and by an unresolved dependency
- **THEN** its entry names the gate and the dependency

### Requirement: A launch record establishes and persists its Slack thread once

The system SHALL persist, against a launch record, the Slack identity of whoever submitted it and an optional Slack thread reference. The submitter SHALL be recorded once, when the launch is started, and SHALL NOT change afterward. The thread reference SHALL be absent until first needed, established by whichever per-product Slack message about that launch is delivered first, and never re-created once set — a later delivery for the same launch SHALL reuse the existing reference rather than posting a second anchor message. Two per-product messages triggered for the same launch before either has observed a thread reference SHALL still result in exactly one anchor message and a single, shared thread reference for both.

**The anchor message SHALL be composed from the launch's product as the system resolves it at establishment time, read once for that purpose**, and SHALL NOT be composed from product facts supplied by whichever delivery path happens to be establishing the thread. What the anchor names is unchanged and is stated by `launch-entry`: the product, its SKU, its marketplace, and its launch date or the absence of one. This clause governs only where those values come from, and it exists because the anchor is permanent: a delivery path that could supply less than another would make the launch's header depend on which message arrived first, with no later message able to correct it.

**Where the launch's product cannot be resolved, the thread SHALL NOT be established** — no anchor is posted, no thread reference is persisted, and the delivery that attempted it fails and is reported, to be handled by the rule that already governs that delivery — retried where that rule retries, and reported to the submitter directly where `launch-entry` requires that instead. A product that is unreadable, absent, or whose reader is not configured are one case and SHALL be treated alike: the system cannot say what the product is. An anchor posted with missing facts would be permanent and unrepairable, while a thread not yet established costs one message for which its own capability already specifies a handling — so the incomplete anchor is the outcome to refuse, and the delay is the one to accept.

**The product SHALL NOT be read for the anchor's purpose where the thread reference is already set.** Establishment for a launch that already carries one reuses it without resolving the product, so a launch with a thread is unaffected by whether the product can be resolved. This governs only the anchor's own read: a message delivered into an existing thread still reads the product for whatever its own capability requires it to name.

#### Scenario: The submitter is recorded at launch start

- **WHEN** a launch is started
- **THEN** the launch record persists the Slack identity of whoever submitted it

#### Scenario: The thread reference starts absent

- **WHEN** a launch is started
- **THEN** its Slack thread reference is reported as absent

#### Scenario: The first per-product Slack message establishes the thread reference

- **WHEN** the first message about a launch that has no thread reference is delivered
- **THEN** an anchor message is posted and its identifying reference is persisted on the launch record

#### Scenario: The anchor names the product the system resolved, not what the caller held

- **WHEN** a delivery path that holds no product facts, or partial ones, establishes a launch's thread
- **THEN** the anchor names the product, SKU and marketplace as resolved from the launch's product at establishment time

#### Scenario: A product that cannot be read refuses establishment

- **WHEN** a per-product message would establish a launch's thread and the launch's product cannot be read
- **THEN** no anchor is posted, no thread reference is persisted, and the delivery fails and is reported

#### Scenario: A product that resolves to nothing refuses establishment

- **WHEN** a per-product message would establish a launch's thread and the launch's product resolves to nothing
- **THEN** no anchor is posted, no thread reference is persisted, and the delivery fails and is reported

#### Scenario: A refused establishment leaves the next delivery free to establish

- **WHEN** establishment was refused because the product could not be resolved, and a later message for the same launch is delivered while the product can be resolved
- **THEN** that message establishes the thread and posts a complete anchor

#### Scenario: A concurrent race to establish the thread produces exactly one anchor

- **WHEN** two per-product Slack messages are triggered for the same launch at the same time, and neither has yet observed a thread reference
- **THEN** exactly one anchor message is posted, and both messages are ultimately delivered against the same, single thread reference

#### Scenario: Establishing an already-set thread reference changes nothing

- **WHEN** a per-product Slack message is delivered for a launch that already has a thread reference
- **THEN** no new anchor message is posted, and the existing thread reference is reused

#### Scenario: A launch with a thread never reads its product

- **WHEN** a per-product Slack message is delivered for a launch that already has a thread reference and whose product cannot be read
- **THEN** the existing thread reference is reused, no product is resolved for the anchor, and the message is delivered
