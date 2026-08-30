## MODIFIED Requirements

### Requirement: The produced record states what it does not cover

The dossier SHALL present the produced record as the results that were **retained for a decision**, and SHALL NOT present it as every outcome an automated step produced for the product.

Only a terminal proposal on a step naming a confirmer is retained; a result on a step naming no confirmer, and every non-terminal outcome, is recorded against the launch and never reaches this record. A page that offered the retained set as the complete automated history would be wrong in a way a reader cannot detect from the page, and would be most wrong precisely for the products whose steps name no confirmer.

The record's container SHALL carry the literal marker `retained-for-decision`, whatever the wording it is introduced with, so that the qualification cannot be dropped by a later edit to the prose without a test noticing.

#### Scenario: The record is labelled for what it holds

- **WHEN** the dossier's produced record is rendered
- **THEN** its container carries `retained-for-decision`

#### Scenario: The qualification is present on an empty record too

- **WHEN** the dossier is rendered for a product carrying no retained results
- **THEN** the record's container still carries `retained-for-decision`
