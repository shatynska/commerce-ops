## MODIFIED Requirements

### Requirement: An automated step's handler is invoked by recurring work

The system SHALL invoke registered step handlers from recurring work that runs inside the deployment, declaring its schedule and tolerance as `scheduled-jobs` requires of every piece of recurring work. Each pass SHALL consider every launch that has not graduated, and within each launch every step of its served playbook whose kind is `automated`.

A pass SHALL invoke the handler of such a step only where all of the following hold: the step's recorded outcome is not one the step's hazard permits as terminal; no pending result stands for it; it is not within the cool-off this specification places after a rejection; and it is not within the cool-off this specification places after a handler repeated a non-terminal outcome. `human` steps, steps that are not `active`, and steps already at a permitted terminal outcome SHALL NOT be invoked.

Invocation SHALL NOT be reachable from outside the deployment.

#### Scenario: An unresolved automated step is invoked

- **WHEN** a pass runs over a launch whose served playbook carries an `active` `automated` step with no recorded outcome, no pending result and no recent rejection
- **THEN** that step's named handler is invoked

#### Scenario: A human step is never invoked

- **WHEN** a pass runs over a launch whose served playbook carries an `active` `human` step
- **THEN** no handler is invoked for it, whether or not it needs confirmation

#### Scenario: A resolved step is not invoked again

- **WHEN** a pass runs over an `automated` step whose recorded outcome is one its hazard permits as terminal
- **THEN** its handler is not invoked and its recorded outcome is left unchanged

#### Scenario: A graduated launch is left alone

- **WHEN** a pass runs and a launch has reached `graduated`
- **THEN** no handler is invoked for any of its steps

### Requirement: A non-terminal outcome is recorded directly and never held for a decision

Where the outcome a handler proposes is not terminal — `NotStarted`, `InProgress` or `Blocked`, none of which `launch-playbook` permits as terminal for any step — the system SHALL record it against the launch immediately with the provenance it constructed, **whatever the step's confirmation flag says**, and SHALL NOT store it as a pending result or seek a decision on it.

Confirmation exists so a person accepts a result. A non-terminal outcome is not a result: it is a handler reporting that the step has not been resolved, and holding it would ask a person to accept "in progress" — a proposal with nothing in it to agree or disagree with, which would then suppress re-invocation until they clicked. Recording it directly keeps the reason on the launch's own record, which is what makes a stalled automated step legible rather than merely quiet.

A non-terminal outcome SHALL leave the step eligible for the next pass, **except** where it repeats the non-terminal outcome the step already carries, which the requirement *A handler that repeats itself is not asked again immediately* governs.

#### Scenario: A non-terminal outcome on a confirmable step is recorded, not held

- **WHEN** a handler proposes `Blocked` with a reason for a step whose confirmation flag is true
- **THEN** the outcome is recorded against the launch with `automated` provenance, no pending result is stored, and no decision is requested

#### Scenario: A step reporting no progress is reconsidered on the next pass

- **WHEN** a handler proposes a non-terminal outcome that differs from the one the step already carries, and a later pass runs
- **THEN** the handler is invoked again for that step

## ADDED Requirements

### Requirement: A handler that repeats itself is not asked again immediately

Where a handler proposes a non-terminal outcome that is the same as the one the step already carries, the system SHALL record that outcome as it records any other, and SHALL NOT invoke that step's handler again until a fixed cool-off has elapsed **since that repeat was noted**. Once it has, a pass SHALL invoke the handler again; where the handler repeats itself again, the step SHALL be cooled off again from that later repeat.

Two non-terminal outcomes are **the same** where they are outcomes of the same kind, disregarding any reason either carries. The reason a handler gives SHALL NOT be part of that judgement: a handler may word the same reason differently on each call — an LLM-backed handler always will — and a rule comparing reasons would find no two reports alike, engage never, and appear to work while changing nothing.

The outcome being repeated is the one the step carries, **whatever recorded it**. A `Blocked` outcome a person's rejection recorded can serve as the first of the two: the step is then cooled off on the handler's first statement rather than its second. This is intended — the rejection cool-off already governs that window, and a step a person has just rejected and a handler then declines to resolve is stuck by any reading.

A repeat SHALL be established from two recordings rather than predicted from one. A step reporting a non-terminal outcome for the first time stays eligible for the next pass, because whether the handler has more to say is not knowable without asking it. This deliberately spends one further invocation on a step that turns out to be stuck, which is what distinguishes it from a step that is progressing.

The cool-off SHALL be a fixed property of the system rather than a configured one, and SHALL be independent of the cool-off placed after a rejection: the two answer different questions, and a step that has repeated itself SHALL NOT be affected by a change to the rejection cool-off.

A cool-off SHALL cease to govern the step as soon as the step's recorded outcome is no longer an outcome **of the kind** the cool-off was noted against — including where something other than a pass recorded it. Nothing SHALL be required to actively lift it. The kind is what matters here for the same reason it is what matters above: a `Blocked` re-recorded with different wording is the same kind, and must not lift a cool-off.

The judgement SHALL NOT be made from the launch journal. A dropped journal entry must never change what the system does: `launch-journal` keeps a record for people, and it is safe to lose exactly because no behaviour reads it.

Where the system cannot read or write whatever it keeps this judgement in, the step SHALL be left eligible for invocation and the failure SHALL be reported — the pass SHALL behave as it did before this requirement existed rather than leave a step unresolved. The failure SHALL NOT fail the pass, and SHALL NOT prevent the remaining steps and launches from being walked or their outcomes from being recorded.

That degrade applies to invocation only. What such a failure means for reporting a stuck step is governed by *A step whose handler has stopped making progress is reported once*, which degrades the other way.

Where the shared store cannot be restored to a usable state after such a failure, the pass SHALL end and the run SHALL be recorded as failed. A pass that walked on against a store that cannot record would persist nothing while reporting success, which is worse than stopping.

#### Scenario: A cool-off is anchored to the repeat that caused it

- **WHEN** a step's handler repeats itself again after an earlier cool-off has elapsed
- **THEN** the step is cooled off again, measured from the later repeat

#### Scenario: A cool-off stops governing once the outcome differs from it

- **WHEN** a step cooled off against one non-terminal outcome has a different outcome recorded against it by something other than a pass
- **THEN** the step is eligible for invocation on the next pass

#### Scenario: A step whose backoff record cannot be read is still invoked

- **WHEN** a pass cannot read whether a step is cooled off
- **THEN** the step's handler is invoked, the failure is reported, and the pass continues

#### Scenario: A failed backoff access does not cost the pass its other work

- **WHEN** reading or writing the backoff record fails for one step
- **THEN** the remaining steps and launches are still walked and their recorded outcomes are still persisted

#### Scenario: A repeated non-terminal outcome is recorded and cools the step off

- **WHEN** a handler proposes the non-terminal outcome the step already carries
- **THEN** the outcome is recorded against the launch, and the step's handler is not invoked on the next pass

#### Scenario: A differently worded repeat still counts as a repeat

- **WHEN** a handler proposes `Blocked` with a reason worded differently from the reason recorded on the step, which is also `Blocked`
- **THEN** it is treated as a repeat, and the step's handler is not invoked on the next pass

#### Scenario: A first non-terminal outcome does not cool the step off

- **WHEN** a handler proposes a non-terminal outcome for a step carrying no recorded outcome
- **THEN** the outcome is recorded and the handler is invoked again on the next pass

#### Scenario: A changed outcome lifts the cool-off

- **WHEN** a handler that had repeated itself is invoked after the cool-off elapses and proposes a different non-terminal outcome
- **THEN** the outcome is recorded and the handler is invoked again on the next pass

#### Scenario: A repeated step is asked again once the cool-off elapses

- **WHEN** a pass runs after the cool-off has elapsed since a step's handler repeated itself
- **THEN** that step's handler is invoked again

#### Scenario: The rejection cool-off does not govern a repeat

- **WHEN** a step's handler has repeated a non-terminal outcome and no rejection stands against that step
- **THEN** the step is cooled off by the repeat alone

### Requirement: A step whose handler has stopped making progress is reported once

Where a handler repeats a non-terminal outcome and the step is cooled off, the system SHALL report that step once — naming the launch, the step, and **what the handler produced as its result**, which for a `Blocked` outcome is also the reason it carries — so that a person can supply what the handler is missing. A handler that cannot resolve a step is reporting work only a person can do, and a record nobody reads is not a report. The result is reported as what the handler said, never asserted as a fact about the product.

The report SHALL be delivered once for as long as the step stays stuck, and SHALL NOT be repeated on every pass **nor on each expiry of the cool-off**: a step stuck for a week is one message, not seven. A step whose recorded outcome later changes, or which reaches an outcome its hazard permits as terminal, SHALL become eligible to be reported again if it later gets stuck.

Two passes running over the same step at once MAY each deliver the report, since neither can see the other's delivery before it happens. A duplicate message is the accepted cost of writing the record only after a delivery succeeds.

Where the system cannot read whether a step has already been reported, it SHALL deliver no report for that step on that pass. A report that cannot be recorded as delivered cannot be delivered *once*, and attempting one anyway would turn a store outage into a report on every pass — the repetition this requirement exists to prevent. This is the opposite degrade from the one *A handler that repeats itself is not asked again immediately* places on invocation, and deliberately so: an unresolved step is the worse outcome there, and an unread channel is the worse outcome here. The access failure is itself reported, and the step is reported normally on the first pass that can read the record again.

The record that suppresses further reports SHALL be written only after a delivery has succeeded. Recording first and then failing to deliver would silence the step for as long as it stays stuck, which is precisely the period the report exists to cover.

A failure to deliver the report SHALL NOT fail the pass, SHALL NOT stop the remaining launches or steps from being walked, and SHALL NOT record any outcome.

#### Scenario: A newly cooled-off step is reported

- **WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
- **THEN** a report naming the launch, the step and what the handler produced as its result is delivered

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
