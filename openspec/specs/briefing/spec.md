# briefing Specification

## Purpose

The convergence point where launch outcomes (and, in later slices, monitoring findings) become one daily Slack report: attention items graded by severity, collapsed by cause so one struggling product is one item, delivered only when there is something to say.

## Requirements

### Requirement: Attention items are derived from every active launch

When the daily briefing is assembled, the system SHALL derive attention items from every active launch, evaluated as of the assembly date. A launch is active when its catalog product's lifecycle stage is neither steady-state nor retired — the stage stamp is the catalog's answer, so a launch drops out of the briefing the moment graduation stamps its product steady-state. A launch whose product the catalog cannot resolve SHALL be treated as active — the filter fails toward reporting, never toward silence. Three conditions SHALL each yield an item: a launch date at risk, a current gate awaiting confirmation, and an overdue step that is not blocking and has not reached a permitted terminal outcome. Every item SHALL carry the product it concerns, a severity from the shared vocabulary, and evidence naming the launch facts it summarizes (the step or gate identifiers and, where applicable, their due periods). A launch none of whose conditions hold SHALL contribute no items.

#### Scenario: An at-risk launch date yields a critical item

- **WHEN** the briefing is assembled and an active launch's date is at risk
- **THEN** the briefing SHALL contain an item for that product with severity critical
- **AND** the item's evidence SHALL name the overdue blocking steps that put the date at risk

#### Scenario: A gate awaiting confirmation yields a diagnose item

- **WHEN** the briefing is assembled and an active launch's current gate awaits confirmation
- **THEN** the briefing SHALL contain an item for that product with severity diagnose, naming the gate awaiting approval

#### Scenario: An overdue non-blocking step yields a monitor item

- **WHEN** the briefing is assembled and an active launch has an overdue step that is not blocking and has not reached a permitted terminal outcome
- **THEN** the briefing SHALL contain an item for that product with severity monitor, whose evidence names the step and its due period

#### Scenario: A healthy launch contributes nothing

- **WHEN** the briefing is assembled and an active launch has no at-risk date, no gate awaiting confirmation, and no overdue steps
- **THEN** the briefing SHALL contain no item for that product

#### Scenario: A graduated product's launch is not briefed

- **WHEN** the briefing is assembled and a launch's catalog product is in a steady-state stage
- **THEN** the briefing SHALL contain no item derived from that launch, whatever its recorded step outcomes

#### Scenario: An unresolvable product's launch is still derived from

- **WHEN** the briefing is assembled and a launch's product cannot be resolved by the catalog
- **THEN** that launch SHALL be treated as active and its conditions SHALL yield items as for any other launch

### Requirement: Findings collapse by cause and the causal item leads

The launch-side cause order SHALL rank an at-risk launch date first, then a gate awaiting confirmation, then overdue non-blocking steps. Findings SHALL collapse rather than repeat: the overdue blocking steps that produce an at-risk date SHALL appear only as that item's evidence, never as items of their own, and overdue non-blocking steps on one product SHALL collapse into one item per discipline with each step as evidence. Within one product's items, the higher-ranked cause SHALL precede the lower.

#### Scenario: Overdue blocking steps are absorbed by the at-risk item

- **WHEN** a launch's date is at risk because two blocking steps are overdue
- **THEN** the briefing SHALL contain exactly one at-risk item for that product carrying both steps as evidence
- **AND** no separate item SHALL exist for either blocking step

#### Scenario: Overdue non-blocking steps in one discipline collapse into one item

- **WHEN** two non-blocking steps of the same discipline on one launch are overdue
- **THEN** the briefing SHALL contain exactly one monitor item for that product and discipline, with both steps as evidence

#### Scenario: The causal item precedes the rest

- **WHEN** one product has both an at-risk date and an overdue non-blocking step
- **THEN** that product's at-risk item SHALL precede its monitor item in the briefing

### Requirement: A clean briefing is not sent

A briefing that contains no attention items SHALL NOT be delivered: the run completes successfully and no Slack message is posted. A briefing with at least one item SHALL be delivered as one Slack message reporting every item.

#### Scenario: A clean day posts nothing

- **WHEN** the daily briefing is assembled and no attention item exists
- **THEN** no Slack message SHALL be posted
- **AND** the run SHALL be recorded as succeeded

#### Scenario: A briefing with items is delivered

- **WHEN** the daily briefing is assembled and at least one attention item exists
- **THEN** the system SHALL post one Slack message reporting every item, its severity, and its evidence

### Requirement: Items identify products by name and SKU, and never drop an item over naming

The delivered briefing SHALL identify each item's product by its catalog name and SKU. A product the catalog cannot resolve SHALL be identified by its raw product identifier instead; the item SHALL still be reported.

#### Scenario: A resolvable product is named

- **WHEN** a briefing item concerns a product the catalog resolves
- **THEN** the delivered item SHALL show that product's name and SKU

#### Scenario: An unresolvable product does not lose its item

- **WHEN** a briefing item concerns a product the catalog cannot resolve
- **THEN** the item SHALL be delivered identifying the product by its raw identifier

### Requirement: The daily briefing runs on a schedule

The system SHALL assemble and deliver the daily briefing on a declared schedule, as recurring work governed by `scheduled-jobs`. It SHALL NOT be startable by a request from outside the deployment.

#### Scenario: The briefing runs when its schedule is due

- **WHEN** the daily briefing's declared schedule becomes due
- **THEN** the system SHALL run the daily briefing

#### Scenario: The briefing cannot be started from outside the deployment

- **WHEN** the system's externally reachable interfaces are enumerated
- **THEN** none of them SHALL start the daily briefing

### Requirement: Delivery failure is decoupled from the run

Once a briefing has been assembled, a failure while posting it to Slack SHALL be logged, SHALL NOT cause the run to be recorded as failed, and SHALL NOT cause the run to be retried — a redelivered briefing would be stale, and the delivery failure does not establish the message did not arrive.

#### Scenario: A failed Slack post does not fail the run

- **WHEN** an assembled briefing's Slack post fails
- **THEN** the system SHALL log the failure
- **AND** the run SHALL be recorded as succeeded
- **AND** the run SHALL NOT be retried

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
