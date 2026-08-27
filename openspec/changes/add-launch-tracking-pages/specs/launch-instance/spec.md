## ADDED Requirements

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

- **WHEN** a launch that is not reported at risk holds a non-blocking step whose due period has fully passed unresolved
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

### Requirement: The launch report places each step in its gate and names the gate sequence

The launch report SHALL carry, on each step entry, the gate the playbook
attaches that step to, and SHALL name the gate sequence in its order.

This is the fourth fact the report must carry for the same reason as the
other three, and the only one of them the report does not carry today. A
consumer presenting a launch shows where it stands in a sequence and
which work belongs to which gate; without both facts on the report it
must obtain the playbook and the gate framework itself, which is what
this capability's governing principle forbids and what the three
requirements above exist to avoid.

The sequence travels with the report rather than being looked up because
a consumer that had to find it would need the gate framework, not merely
the step set — a heavier dependency than the one already refused, and one
that carries the gate *order* as well as the gate names.

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

#### Scenario: The report carries an entry for a step with no recorded outcome

- **WHEN** a launch is read back and a served step has no recorded outcome
- **THEN** the report SHALL carry an entry for that step

#### Scenario: Step entries arrive in the served playbook's order

- **WHEN** a launch is read back or enumerated
- **THEN** the report's step entries SHALL be ordered by gate in the gate sequence's order, and within each gate by that gate's authored step order

#### Scenario: A step entry carries its gate

- **WHEN** a launch is read back or enumerated
- **THEN** every step entry in the report SHALL carry the gate the playbook attaches that step to

#### Scenario: The report names the gates in order

- **WHEN** a launch is read back or enumerated
- **THEN** the report SHALL name the gate sequence in its order, and the launch's current gate SHALL be one of them
