# launch-instance Specification

## Purpose

Persists a concrete product's position in the `launch-playbook` gate sequence — playbook version, current gate, launch date — as a launch-position record referencing the product `product-catalog` owns, so work on the launch process has a real record to run against instead of only the abstract playbook definition.

## Requirements

### Requirement: A product is persisted with its catalog identity

The system SHALL persist a product record carrying: a unique identifier, a SKU, an optional ASIN, a name, the `launch-playbook` version it runs under, an optional launch date, and its current gate. SKU SHALL be required and unique across all products.

#### Scenario: A product is created with only the required fields

- **WHEN** a product is created with a SKU, a name, and a playbook version, and no ASIN or launch date
- **THEN** the product is persisted with those fields set and ASIN and launch date reported as absent

#### Scenario: A product is created with every field

- **WHEN** a product is created with a SKU, a name, a playbook version, an ASIN, and a launch date
- **THEN** the product is persisted with all five values present

#### Scenario: A duplicate SKU is rejected

- **WHEN** a product is created with a SKU that already belongs to an existing product
- **THEN** the creation is rejected and no new record is persisted

### Requirement: A product's current gate is restricted to the launch-playbook gate sequence

A product's current gate SHALL be one of the eight gate ids `launch-playbook` defines (`commit`, `order`, `listable`, `stock-ready`, `live`, `ignition`, `phase-one-complete`, `graduated`). A newly created product SHALL default to `commit`, the first gate in that sequence, when no current gate is given explicitly.

#### Scenario: A new product defaults to the first gate

- **WHEN** a product is created without specifying a current gate
- **THEN** its current gate is reported as `commit`

#### Scenario: An unrecognized gate is rejected

- **WHEN** a product is created or updated with a current gate that is not one of the eight `launch-playbook` gate ids
- **THEN** the operation is rejected and the product's stored gate is unchanged

### Requirement: A product can be read back by identifier or by SKU

The system SHALL retrieve a persisted product given either its identifier or its SKU, and SHALL report that no product exists when queried by an identifier or SKU that does not belong to any persisted product.

#### Scenario: A product is retrieved by its identifier

- **WHEN** a product is read using the identifier it was persisted with
- **THEN** the same product is returned with every field it was persisted with

#### Scenario: A product is retrieved by its SKU

- **WHEN** a product is read using the SKU it was persisted with
- **THEN** the same product is returned

#### Scenario: Reading an unknown product reports absence

- **WHEN** a product is read using an identifier or a SKU that no persisted product has
- **THEN** the system reports that no product was found, rather than an error

### Requirement: A product's current gate can be updated

The system SHALL allow updating a persisted product's current gate to any of the eight `launch-playbook` gate ids. This requirement governs only that the stored value may change; it does not validate that the transition from the product's prior gate to the new one is one `launch-playbook` would permit.

#### Scenario: A product's current gate is updated to a valid gate

- **WHEN** an existing product's current gate is updated to `order`
- **THEN** reading the product back reports `order` as its current gate

#### Scenario: Updating a nonexistent product is rejected

- **WHEN** a current-gate update targets an identifier that no persisted product has
- **THEN** the update is rejected
