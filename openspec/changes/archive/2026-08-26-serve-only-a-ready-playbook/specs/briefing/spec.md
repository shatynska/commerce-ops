## MODIFIED Requirements

### Requirement: A failure to assemble is surfaced, not treated like a delivery failure

When the briefing cannot be assembled because the data it derives from cannot be read, the run SHALL be recorded as failed — so `scheduled-jobs`' retry and overdue reporting apply to it. The system SHALL additionally attempt to post one message to the configured channel indicating the briefing could not be assembled, and SHALL post it only once the run's retries are exhausted, so one outage produces one message.

This SHALL NOT cover the case where the launch source reports that it cannot supply reports at all. That is not a failure to read data but a source that is not yet able to answer, and it carries its own outcome — see *A launch source that cannot supply reports is reported, not treated as a clean day*. Retrying cannot resolve it, which is the whole reason it is separated: a failed run would put the work into retry and overdue reporting for a condition no retry reaches.

#### Scenario: A read failure on the final attempt fails the run and says so

- **WHEN** assembling the daily briefing fails on the run's final attempt because its source data cannot be read
- **THEN** the run SHALL be recorded as failed
- **AND** the system SHALL attempt to post a message indicating the briefing could not be assembled

#### Scenario: An intermediate failed attempt does not post

- **WHEN** assembling the daily briefing fails on an attempt that will be retried
- **THEN** the system SHALL NOT post a message for that attempt

#### Scenario: An assembly failure is retried

- **WHEN** an attempt of the daily briefing has failed because its source data could not be read, and the declared maximum number of attempts has not been reached
- **THEN** the system SHALL retry the run

#### Scenario: A source that cannot supply reports is not a read failure

- **WHEN** the launch source reports that it cannot supply reports at all
- **THEN** this requirement does not apply, and the run is not recorded as failed

## ADDED Requirements

### Requirement: A launch source that cannot supply reports is reported, not treated as a clean day

The source the briefing reads its launch items from SHALL be able to report a distinct condition — **it cannot supply reports at all** — separately from supplying none, and SHALL carry with it the identifiers describing why. Supplying no reports and being unable to supply any SHALL lead to different outcomes, so the briefing SHALL NOT collapse them.

Whatever satisfies that source is responsible for translating its own module's condition into this one; the briefing SHALL treat the carried identifiers as opaque. Today the only such condition is a launch playbook that cannot hold a launch, and the identifiers are the gates that hold no active blocking step — neither of which the briefing needs to understand in order to report them.

When the port reports it, the briefing SHALL NOT be assembled, and SHALL NOT be treated as a briefing with no attention items. The run SHALL be recorded as **succeeded**, because a source that is still being set up is an expected state and not a failure to read data: recording it as failed would put the work into retry and overdue reporting for a condition retrying cannot resolve, which is what the assembly-failure requirement is for and what this is not.

The system SHALL post one message to the configured channel naming the carried identifiers, on **every** run while the condition persists. This is deliberately not suppressed to one message per outage: the existing suppression hook is retry exhaustion, which a run recorded as succeeded never reaches, and no other state is kept to distinguish a continuing condition from a new one. A message on each run naming what is still missing is a true and actionable statement about a deployment being set up, not an alarm about a fault — and it is what stops the condition reading as a clean day, which the rule that a clean briefing is not sent would otherwise produce.

A failure to deliver that message SHALL be logged and SHALL NOT fail or retry the run. The decoupling this capability already draws between assembly and delivery is scoped to a briefing that was assembled, so it does not reach a message posted when nothing was; without this, a Slack outage during a stand-down would fail a run this requirement has just said succeeds.

#### Scenario: A failure to post the message does not fail the run

- **WHEN** the message naming the carried identifiers cannot be delivered
- **THEN** the failure is logged, the run is still recorded as succeeded, and it is not retried

#### Scenario: An unavailable launch source posts a message rather than nothing

- **WHEN** the daily briefing runs and its launch-report source reports it cannot supply reports, carrying two gate identifiers
- **THEN** one message is posted naming those gates
- **AND** the run is recorded as succeeded

#### Scenario: An unavailable launch source is not a clean day

- **WHEN** the daily briefing runs and its launch-report source reports it cannot supply reports
- **THEN** no briefing is assembled, and the message posted states the source could not supply reports rather than reporting an absence of attention items

#### Scenario: An unavailable launch source is not an assembly failure

- **WHEN** the daily briefing runs and its launch-report source reports it cannot supply reports
- **THEN** the run is not recorded as failed, is not retried, and does not produce the message an assembly failure produces

#### Scenario: The condition is reported on each run while it persists

- **WHEN** the daily briefing runs on consecutive days and its launch-report source reports the same condition each time
- **THEN** a message is posted on each of those runs
