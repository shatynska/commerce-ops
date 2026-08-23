# launch-instance Delta

## ADDED Requirements

### Requirement: A launch position is persisted for a catalog product

The system SHALL persist a launch-position record carrying: a reference to a catalog product by its product identifier, the `launch-playbook` version the launch runs under, the current gate, and an optional launch date. At most one launch-position record SHALL exist per product. Creating a launch position for a product identifier that no catalog product has SHALL be rejected.

#### Scenario: A launch position is created for an existing product

- **WHEN** a launch position is created for a registered catalog product with a playbook version and no launch date
- **THEN** the record is persisted referencing that product, with the launch date reported as absent

#### Scenario: A launch position for an unknown product is rejected

- **WHEN** a launch position is created for a product identifier no catalog product has
- **THEN** the creation is rejected and nothing is persisted

#### Scenario: A second launch position for the same product is rejected

- **WHEN** a launch position is created for a product that already has one
- **THEN** the creation is rejected and the existing record is unchanged

### Requirement: A launch position can be read back by product identifier

The system SHALL retrieve a persisted launch position given the product identifier it references, and SHALL report absence rather than an error when the product has no launch position.

#### Scenario: A launch position is retrieved

- **WHEN** a launch position is read using the product identifier it was created for
- **THEN** the record is returned with every field it was persisted with

#### Scenario: A product without a launch position reports absence

- **WHEN** a launch position is read for a product identifier that has none
- **THEN** the system reports that none exists, rather than an error

## MODIFIED Requirements

### Requirement: A product's current gate is restricted to the launch-playbook gate sequence

A launch position's current gate SHALL be one of the eight gate ids `launch-playbook` defines (`commit`, `order`, `listable`, `stock-ready`, `live`, `ignition`, `phase-one-complete`, `graduated`). A newly created launch position SHALL default to `commit`, the first gate in that sequence, when no current gate is given explicitly.

#### Scenario: A new product defaults to the first gate

- **WHEN** a launch position is created without specifying a current gate
- **THEN** its current gate is reported as `commit`

#### Scenario: An unrecognized gate is rejected

- **WHEN** a launch position is created or updated with a current gate that is not one of the eight `launch-playbook` gate ids
- **THEN** the operation is rejected and the stored gate is unchanged

### Requirement: A product's current gate can be updated

The system SHALL allow updating a persisted launch position's current gate to any of the eight `launch-playbook` gate ids. This requirement governs only that the stored value may change; it does not validate that the transition from the prior gate to the new one is one `launch-playbook` would permit.

#### Scenario: A product's current gate is updated to a valid gate

- **WHEN** an existing launch position's current gate is updated to `order`
- **THEN** reading it back reports `order` as its current gate

#### Scenario: Updating a nonexistent product is rejected

- **WHEN** a current-gate update targets a product identifier that has no launch position
- **THEN** the update is rejected

## REMOVED Requirements

### Requirement: A product is persisted with its catalog identity

**Reason**: Product identity (SKU, ASIN, name) is now owned by the `product-catalog` capability; this capability keeps only the launch-position fields, referencing the product by identifier.

**Migration**: The identity columns of the existing flat record move to the catalog's product record; `playbook_version`, `current_gate`, and `launch_date` move to the launch-position record, both preserved by a data migration.

### Requirement: A product can be read back by identifier or by SKU

**Reason**: Superseded by "A launch position can be read back by product identifier". SKU-based lookup belongs to `product-catalog`; resolving a SKU to a product identifier there and reading the launch position by that identifier replaces the removed by-SKU read.

**Migration**: Callers that read the record by SKU first resolve the SKU through `product-catalog`, then read the launch position by product identifier.
