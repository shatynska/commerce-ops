## ADDED Requirements

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

## MODIFIED Requirements

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
