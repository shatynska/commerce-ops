## MODIFIED Requirements

### Requirement: A launch is started from Slack in one interaction

The system SHALL provide a Slack slash command on the `product_agent` app that opens a modal collecting a new product's SKU and name (required), its ASIN and launch date (optional), and a marketplace selection (required, preselected to the single offered option). Submitting the modal SHALL register the product in the catalog and start its launch against the served playbook, recording the served playbook's version identifier on the launch as its audit stamp, and SHALL confirm the outcome with a message naming the product, its launch date (or its absence), and that tracked work appears in ClickUp on the sync cadence.

#### Scenario: A launch is started with a date

- **WHEN** the modal is submitted with a valid SKU, name, and launch date
- **THEN** the product is registered and its launch exists, recording the served playbook's version identifier, with that launch date
- **AND** a confirmation message is posted

#### Scenario: A launch is started without a date

- **WHEN** the modal is submitted with only the required fields
- **THEN** the launch exists with no launch date and no derived due periods
- **AND** the confirmation names the absence of a date

#### Scenario: The playbook version is never user input

- **WHEN** the modal is displayed
- **THEN** it contains no playbook-version field, and the started launch records the served playbook's version identifier
