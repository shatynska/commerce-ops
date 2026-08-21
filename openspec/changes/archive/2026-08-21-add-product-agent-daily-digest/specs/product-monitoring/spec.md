## Purpose

Posts product-status reports to Slack via the `product_agent` app on a set of independently triggerable schedules — daily, weekly, biweekly, monthly, quarterly — so the team gets proactive updates without having to ask. Only the daily cadence has real reporting content today; the rest are reserved trigger points for reporting logic planned separately.

## ADDED Requirements

### Requirement: Each Cadence Has Its Own Guarded Trigger Endpoint
The system SHALL expose an independently triggerable endpoint for each of the following cadences: daily, weekly, biweekly, monthly, quarterly. Each endpoint SHALL be guarded by the `internal-trigger` mechanism, and SHALL NOT be invocable by any request that does not satisfy that guard.

#### Scenario: A cadence endpoint rejects an unguarded request
- **WHEN** a request to any cadence's endpoint does not satisfy the internal-trigger guard
- **THEN** the system SHALL reject the request and SHALL NOT perform that cadence's reporting action

### Requirement: Daily Cadence Lists Existing Product Names
When the daily endpoint is invoked, the system SHALL post a Slack message listing the name of every product currently recorded, or a message indicating none exist if there are none.

#### Scenario: Daily trigger lists product names
- **WHEN** the daily endpoint is invoked and at least one product exists
- **THEN** the system SHALL post a Slack message listing the name of every existing product

#### Scenario: No products exist
- **WHEN** the daily endpoint is invoked and no product exists
- **THEN** the system SHALL post a message indicating no products exist, rather than posting nothing

### Requirement: Non-Daily Cadences Acknowledge Their Trigger Without Reporting
The weekly, biweekly, monthly, and quarterly endpoints SHALL accept a valid trigger and respond indicating the trigger was received, without performing any reporting action — their reporting logic is intentionally not yet implemented.

#### Scenario: A non-daily cadence is triggered
- **WHEN** the weekly, biweekly, monthly, or quarterly endpoint is invoked and satisfies the internal-trigger guard
- **THEN** the system SHALL respond indicating the trigger was received and SHALL NOT post any Slack message

### Requirement: Report Delivery Failure Is Decoupled From The Trigger
Once a cadence's report has been successfully assembled, triggering the endpoint and delivering that report to Slack SHALL be treated as separate concerns: a failure while posting the assembled report to Slack SHALL be logged, and SHALL NOT change the response the endpoint gives to the triggering caller, which reflects only that the trigger was received and processed. This requirement governs a failure to *deliver* an already-assembled report — a failure to *assemble* it (e.g. the daily cadence's database read) is governed separately, below.

#### Scenario: Slack post fails
- **WHEN** a cadence's report has been assembled and posting it to Slack fails
- **THEN** the system SHALL log the failure
- **AND** the triggering request SHALL still receive a response indicating the trigger was accepted

### Requirement: Database Read Failure Is Surfaced, Not Treated Like A Delivery Failure
When the daily endpoint cannot read products from the database, the system SHALL respond with a failing status — distinct from the response given when only report delivery fails — and SHALL attempt to post a message to the configured channel indicating the database could not be read.

#### Scenario: Database read fails
- **WHEN** the daily endpoint is invoked and reading products from the database fails
- **THEN** the system SHALL respond with a failing status
- **AND** SHALL attempt to post a message to the configured channel indicating the database could not be read
