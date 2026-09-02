## MODIFIED Requirements

### Requirement: A launch is started from Slack in one interaction

The system SHALL provide a Slack slash command on the `product_agent` app that opens a modal collecting a new product's SKU and name (required), its ASIN and launch date (optional), and a marketplace selection (required, preselected to the single offered option). Submitting the modal SHALL register the product in the catalog and start its launch against the served playbook, recording the served playbook's version identifier on the launch as its audit stamp. On success, the system SHALL post the launch's anchor message — naming the product, its SKU, its marketplace, and its launch date (or its absence) — establishing the launch's Slack thread, and SHALL confirm the outcome as a reply within that thread, tagging the submitter and naming that tracked work appears in ClickUp on the sync cadence.

**A started launch SHALL NOT be left unreported.** Where the threaded confirmation cannot be delivered — the thread cannot be established, or the reply cannot be posted — the system SHALL tell the submitter directly that the launch started, by the same direct message a failed start already uses, and SHALL report the delivery failure. The threaded reply remains the specified delivery; this is what happens when it fails, not an alternative to it.

The confirmation is owed because the product and the launch are persisted either way: a submitter told nothing cannot tell a silent success from a silent failure, and a failed start is already reported to them directly, so a successful one must not be the only outcome that goes unremarked.

#### Scenario: A launch is started with a date

- **WHEN** the modal is submitted with a valid SKU, name, and launch date
- **THEN** the product is registered and its launch exists, recording the served playbook's version identifier, with that launch date
- **AND** an anchor message naming that launch date is posted, and a confirmation reply tagging the submitter follows within its thread

#### Scenario: A launch is started without a date

- **WHEN** the modal is submitted with only the required fields
- **THEN** the launch exists with no launch date and no derived due periods
- **AND** the anchor message names the absence of a date

#### Scenario: A confirmation that cannot reach the thread reaches the submitter

- **WHEN** the modal is submitted, the product and its launch are persisted, and establishing the launch's thread or posting the confirmation reply within it fails
- **THEN** the submitter is told directly that the launch started, and the failure to deliver the threaded confirmation is reported

#### Scenario: The playbook version is never user input

- **WHEN** the modal is displayed
- **THEN** it contains no playbook-version field, and the started launch records the served playbook's version identifier
