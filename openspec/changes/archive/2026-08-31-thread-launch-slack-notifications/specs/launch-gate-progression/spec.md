## MODIFIED Requirements

### Requirement: A gate awaiting only confirmation is asked about in Slack

Where a launch's current gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval has been recorded for it, the system SHALL ask for that approval as a message delivered to Slack, as a reply within that launch's Slack thread — establishing the thread first if it does not yet exist. The message SHALL name the product and the gate, SHALL carry the controls by which the decision is made, and SHALL tag the launch's submitter: a gate carries no confirmer of its own.

The ask SHALL be made only for a gate that is awaiting confirmation in exactly the sense `launch-instance` defines: a gate with an unsatisfied blocking condition SHALL NOT be asked about, because the decision it would request cannot yet be acted on.

**The final gate of the sequence SHALL NOT be asked about**, although it requires confirmation. Its approval must name a steady-state posture and its opening stamps the catalog, and this capability obtains neither; a launch standing there is left for the change that adds them. The exclusion is stated here rather than left to which launches the pass happens to walk, so that it is a property of the capability and not of a collaborator's filtering.

A delivery that fails SHALL be reported and SHALL leave the gate eligible to be asked about again, SHALL NOT be recorded as though the ask had been delivered, and SHALL NOT fail the run. A Slack outage is not a fault of the advancing this pass exists to do, and failing the run for it would put the deployment into retry and overdue reporting for every pass the outage lasts.

#### Scenario: A satisfied confirmation gate is asked about

- **WHEN** the pass runs against a launch whose current gate requires confirmation, has every blocking condition satisfied, and has no approving approval recorded
- **THEN** a message naming the product and the gate, tagging the launch's submitter, is posted as a reply within the launch's Slack thread, carrying the decision controls

#### Scenario: The final gate is not asked about

- **WHEN** the pass runs against a launch standing at the final gate of the sequence with every blocking condition satisfied and no approval recorded
- **THEN** no ask is posted, although that gate requires confirmation

#### Scenario: A gate with unsatisfied conditions is not asked about

- **WHEN** the pass runs against a launch whose current gate requires confirmation but has an unsatisfied blocking condition
- **THEN** no ask is posted for that gate

#### Scenario: An undelivered ask is reported, retried, and does not fail the run

- **WHEN** posting the ask fails
- **THEN** the failure is reported, no delivery is recorded, the run is not failed by it, and the ask is attempted again on the next pass while the gate is still awaiting confirmation

#### Scenario: An ask for a launch with no thread yet establishes one

- **WHEN** the pass asks about a gate for a launch that has no Slack thread reference
- **THEN** an anchor message is posted for that launch before the ask, and the ask is delivered as a reply within the newly established thread
