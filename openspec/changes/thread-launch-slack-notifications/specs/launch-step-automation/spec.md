## MODIFIED Requirements

### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

The system SHALL deliver each pending result to Slack, as a reply within that launch's Slack thread — establishing the thread first if it does not yet exist — naming the product, the step, the outcome the handler proposed and the produced text in full, offering an accept and a reject decision, and tagging the step's named confirmer.

A failure to deliver SHALL NOT discard the pending result and SHALL NOT record an outcome. The failure SHALL be reported, and the pending result SHALL remain available to be delivered again — the same decoupling the daily briefing keeps between assembling a report and delivering it.

#### Scenario: A pending result reaches Slack

- **WHEN** a pending result is stored
- **THEN** a Slack message tagging the step's confirmer is delivered as a reply within the launch's thread, naming the product, the step, the proposed outcome and the produced text, offering an accept and a reject decision

#### Scenario: Undelivered is not undone

- **WHEN** delivering a pending result to Slack fails
- **THEN** the pending result still stands, no outcome is recorded, and the delivery failure is reported

#### Scenario: An undelivered result is delivered again later

- **WHEN** a delivery failed and a later pass runs
- **THEN** delivery of that pending result is attempted again

#### Scenario: A pending result for a launch with no thread yet establishes one

- **WHEN** a pending result is delivered for a launch that has no Slack thread reference
- **THEN** an anchor message is posted for that launch first, and the pending result is delivered as a reply within the newly established thread

### Requirement: A step whose handler has stopped making progress is reported once

Where a handler repeats a non-terminal outcome and the step is cooled off, the system SHALL report that step once — as a reply within the launch's Slack thread, establishing the thread first if it does not yet exist — naming the launch, the step, and **what the handler produced as its result**, which for a `Blocked` outcome is also the reason it carries, and tagging the step's named confirmer where the step names one, the launch's submitter otherwise, so that a person can supply what the handler is missing. A handler that cannot resolve a step is reporting work only a person can do, and a record nobody reads is not a report. The result is reported as what the handler said, never asserted as a fact about the product.

The report SHALL be delivered once for as long as the step stays stuck, and SHALL NOT be repeated on every pass **nor on each expiry of the cool-off**: a step stuck for a week is one message, not seven. A step whose recorded outcome later changes, or which reaches an outcome its hazard permits as terminal, SHALL become eligible to be reported again if it later gets stuck.

Two passes running over the same step at once MAY each deliver the report, since neither can see the other's delivery before it happens. A duplicate message is the accepted cost of writing the record only after a delivery succeeds.

Where the system cannot read whether a step has already been reported, it SHALL deliver no report for that step on that pass. A report that cannot be recorded as delivered cannot be delivered *once*, and attempting one anyway would turn a store outage into a report on every pass — the repetition this requirement exists to prevent. This is the opposite degrade from the one *A handler that repeats itself is not asked again immediately* places on invocation, and deliberately so: an unresolved step is the worse outcome there, and an unread channel is the worse outcome here. The access failure is itself reported, and the step is reported normally on the first pass that can read the record again.

The record that suppresses further reports SHALL be written only after a delivery has succeeded. Recording first and then failing to deliver would silence the step for as long as it stays stuck, which is precisely the period the report exists to cover.

A failure to deliver the report SHALL NOT fail the pass, SHALL NOT stop the remaining launches or steps from being walked, and SHALL NOT record any outcome.

#### Scenario: A newly cooled-off step is reported

- **WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
- **THEN** a report naming the launch, the step and what the handler produced as its result is delivered as a reply within the launch's Slack thread

#### Scenario: A stuck step naming a confirmer tags that confirmer

- **WHEN** a report is delivered for a stuck step that names a confirmer
- **THEN** the message tags that confirmer

#### Scenario: A stuck step naming no confirmer tags the submitter

- **WHEN** a report is delivered for a stuck step that names no confirmer
- **THEN** the message tags the launch's submitter instead

#### Scenario: A step that stays stuck is not reported again

- **WHEN** a later pass runs while the same step is still cooled off with an unchanged outcome
- **THEN** no further report is delivered for it

#### Scenario: A step still stuck after the cool-off expires is not reported again

- **WHEN** the cool-off elapses, the handler is invoked again, and it repeats the same non-terminal outcome
- **THEN** the step is cooled off again and no further report is delivered for it

#### Scenario: A step that gets stuck again after moving is reported again

- **WHEN** a step that was reported later records a different outcome, and later still repeats a non-terminal outcome again
- **THEN** a report is delivered for it again

#### Scenario: A pass that cannot read the backoff record delivers no report

- **WHEN** a pass cannot read whether a step has already been reported
- **THEN** the step's handler is invoked, no report is delivered for it, and the access failure is reported

#### Scenario: A report that could not be delivered is not suppressed

- **WHEN** delivery of the report fails
- **THEN** nothing is recorded as reported, and the next pass attempts the report again

#### Scenario: A failed report leaves the pass walking

- **WHEN** delivery of the report fails for one launch's step
- **THEN** the pass continues with the remaining steps and launches, and the pass is still recorded as a successful run
