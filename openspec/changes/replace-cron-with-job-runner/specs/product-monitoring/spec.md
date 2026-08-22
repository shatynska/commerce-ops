## ADDED Requirements

### Requirement: The Daily Cadence Runs On A Schedule
The system SHALL run the daily product-monitoring cadence on a declared schedule, as a piece of recurring work governed by `scheduled-jobs`. It SHALL NOT be startable by a request from outside the deployment.

The weekly, biweekly, monthly and quarterly cadences SHALL NOT be scheduled while they have no reporting content — see the removals below.

#### Scenario: The daily cadence runs when its schedule is due
- **WHEN** the daily cadence's declared schedule becomes due
- **THEN** the system SHALL run the daily cadence

#### Scenario: The daily cadence cannot be started from outside the deployment
- **WHEN** the system's externally reachable interfaces are enumerated
- **THEN** none of them SHALL start the daily cadence

## MODIFIED Requirements

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
- **WHEN** the daily cadence's run has failed because the database could not be read, and its declared maximum number of attempts has not been reached
- **THEN** the system SHALL retry the run

## REMOVED Requirements

### Requirement: Each Cadence Has Its Own Guarded Trigger Endpoint
**Reason**: The cadences are no longer HTTP endpoints. They run as scheduled jobs inside the deployment, so there is no request to guard — and the guarded endpoints were reachable from the public internet, defended only by a static shared secret, which the move removes entirely. Replaced by `scheduled-jobs`' "Scheduled Work Is Not Reachable From Outside The Deployment" and by "The Daily Cadence Runs On A Schedule" above.

**Migration**: No caller outside the deployment invoked these endpoints — the only client was the `cron` container on the internal `app_cron` network, which is removed by the same change. `TRIGGER_SECRET` is removed from the settings model and from the deploy's `.env` render step; it may be deleted as a GitHub Actions secret once deployed.

### Requirement: Non-Daily Cadences Acknowledge Their Trigger Without Reporting
**Reason**: The weekly, biweekly, monthly and quarterly cadences have no reporting content, and their content depends on marketplace data that is deferred pending external access. Scheduling them produces four recurring no-ops that log and return; keeping them as triggerable endpoints keeps a public surface alive for work that does not exist. An unscheduled cadence states the true position — not built yet — more honestly than one that fires into a no-op.

**Migration**: `run_pending_cadence_report` and its use case are retained, unscheduled and uncalled, so that scheduling a cadence later is a matter of declaring its schedule rather than rebuilding it. Each cadence returns to the schedule in the change that gives it reporting content. `product-monitoring`'s Purpose is updated in the main spec to describe one scheduled cadence and four reserved-but-unscheduled ones.
