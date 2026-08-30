## ADDED Requirements

### Requirement: A sub-category finding can be recorded against a product

The system SHALL record a sub-category node against a registered product, given its product identifier and the node — a full path from the top-level category down. Recording SHALL be independent of the product's lifecycle stage: it is not a stage transition, requires no confirmer, and MAY be recorded for a product in any stage, including `Retired`. A later recording for the same product SHALL replace the previously recorded node.

This mirrors how an ASIN is recorded (`product-catalog`, *A product is registered with its identity*): a standalone fact about the product, not part of the stage machine, that starts absent and may be supplied — or replaced — at any point after registration.

#### Scenario: A sub-category is recorded for a product with none

- **WHEN** a sub-category node is recorded for a product that has none recorded yet
- **THEN** reading the product back reports that node

#### Scenario: A later recording replaces the earlier one

- **WHEN** a sub-category node is recorded for a product that already has one recorded
- **THEN** reading the product back reports the later node, not the earlier one

#### Scenario: Recording does not require a particular stage

- **WHEN** a sub-category node is recorded for a product in `Retired`
- **THEN** the recording succeeds exactly as it would for a product in any other stage

### Requirement: A product reports its recorded sub-category, or its absence

Reading a product back SHALL report its recorded sub-category node where one has been recorded, and SHALL report it as absent — never as an empty or default value — for a product nothing has been recorded for.

#### Scenario: An unrecorded sub-category reports absence

- **WHEN** a registered product that has never had a sub-category recorded is read back
- **THEN** its sub-category is reported as absent, not as an empty string
