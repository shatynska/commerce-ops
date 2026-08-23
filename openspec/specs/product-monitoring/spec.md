# product-monitoring Specification

## Purpose

Posts product-status reports to Slack via the `product_agent` app on a recurring schedule run from inside the deployment, so the team gets proactive updates without having to ask. The daily cadence is the only one that exists: the weekly, biweekly, monthly and quarterly trigger points were removed along with the guarded endpoints that carried them, and reporting logic for further cadences is planned separately.

## Requirements

### Requirement: Daily Cadence Lists Existing Product Names
When the daily cadence runs, the system SHALL post a Slack message listing the name of every product currently recorded, or a message indicating none exist if there are none.

#### Scenario: Daily trigger lists product names
- **WHEN** the daily cadence runs and at least one product exists
- **THEN** the system SHALL post a Slack message listing the name of every existing product

#### Scenario: No products exist
- **WHEN** the daily cadence runs and no product exists
- **THEN** the system SHALL post a message indicating no products exist, rather than posting nothing

### Requirement: Report Delivery Failure Is Decoupled From The Trigger
Once a cadence's report has been successfully assembled, running the cadence and delivering that report to Slack SHALL be treated as separate concerns: a failure while posting the assembled report to Slack SHALL be logged, SHALL NOT cause the run to be recorded as failed, and SHALL NOT cause the run to be retried.

This is deliberate. A retry would re-read the database and post again, and a delivery failure does not establish that the previous delivery did not arrive — so retrying risks duplicate reports in exchange for a report that is already stale by the time it would be redelivered. This requirement governs a failure to *deliver* an already-assembled report; a failure to *assemble* it is governed separately, below.

#### Scenario: Slack post fails
- **WHEN** a cadence's report has been assembled and posting it to Slack fails
- **THEN** the system SHALL log the failure
- **AND** the run SHALL be recorded as succeeded
- **AND** the run SHALL NOT be retried

### Requirement: Database Read Failure Is Surfaced, Not Treated Like A Delivery Failure
When the daily cadence cannot read products from the database, the run SHALL be recorded as failed — distinct from the outcome recorded when only report delivery fails — so that `scheduled-jobs`' retry behavior applies to it, and, once `report-overdue-scheduled-runs` lands, its overdue reporting. The system SHALL additionally attempt to post a message to the configured channel indicating the database could not be read, and SHALL post it only once the run's retries are exhausted rather than on every attempt, so that one outage produces one message rather than one per attempt.

#### Scenario: Database read fails
- **WHEN** the daily cadence runs and reading products from the database fails on its final attempt
- **THEN** the run SHALL be recorded as failed
- **AND** the system SHALL attempt to post a message to the configured channel indicating the database could not be read

#### Scenario: An intermediate failed attempt does not post
- **WHEN** the daily cadence's database read fails on an attempt that will be retried
- **THEN** the system SHALL NOT post a message for that attempt, so that one outage produces one message rather than one per attempt

#### Scenario: A database read failure is retried
- **WHEN** an attempt of the daily cadence has failed because the database could not be read, and the run's declared maximum number of attempts has not been reached
- **THEN** the system SHALL retry the run

### Requirement: The Daily Cadence Runs On A Schedule
The system SHALL run the daily product-monitoring cadence on a declared schedule, as a piece of recurring work governed by `scheduled-jobs`. It SHALL NOT be startable by a request from outside the deployment.

The weekly, biweekly, monthly and quarterly cadences SHALL NOT be scheduled while they have no reporting content — see the removals below.

#### Scenario: The daily cadence runs when its schedule is due
- **WHEN** the daily cadence's declared schedule becomes due
- **THEN** the system SHALL run the daily cadence

#### Scenario: The daily cadence cannot be started from outside the deployment
- **WHEN** the system's externally reachable interfaces are enumerated
- **THEN** none of them SHALL start the daily cadence
