# product-catalog Delta

## Purpose

The one place that answers "which products exist and what lifecycle stage is each in": owns product identity (SKU, ASIN, marketplace, name) and the lifecycle-stage state machine, with human-confirmed stage changes. Every other context references products by identifier and reads the stage stamp from here.

## ADDED Requirements

### Requirement: A product is registered with its identity

The system SHALL register a product carrying: a unique product identifier, a SKU (required, unique across all products), a marketplace identifier (required), an optional ASIN, and a name. The ASIN MAY be absent at registration and supplied later, since a product has no ASIN until its listing exists. Registering a product whose SKU already belongs to an existing product SHALL be rejected without persisting anything.

#### Scenario: A product is registered with required fields only

- **WHEN** a product is registered with a SKU, a marketplace identifier, and a name, and no ASIN
- **THEN** the product is persisted with those values and its ASIN reported as absent

#### Scenario: A duplicate SKU is rejected

- **WHEN** a product is registered with a SKU that already belongs to an existing product
- **THEN** the registration is rejected and no new record is persisted

#### Scenario: An ASIN is recorded later

- **WHEN** an ASIN is recorded for a product registered without one
- **THEN** reading the product back reports that ASIN

### Requirement: A new product starts in Development

A newly registered product SHALL be in the `Development` lifecycle stage. The system SHALL NOT allow registering a product directly into any other stage. The product's stage-entry time SHALL be the registration time, and no stage-change confirmer SHALL be recorded for it — `Development` is stamped by definition, not by a human decision; a confirmer exists only once the first stage change occurs.

#### Scenario: Registration stamps Development

- **WHEN** a product is registered
- **THEN** its lifecycle stage is reported as `Development`

#### Scenario: Registration provenance

- **WHEN** a freshly registered product's stage is read
- **THEN** its stage-entry time equals the registration time
- **AND** no stage-change confirmer is reported

### Requirement: Stage changes follow the legal-transition table and are human-confirmed

A product's lifecycle stage SHALL change only along these transitions, and every change SHALL record who confirmed it and when — the system SHALL never change a stage without a named human confirmer:

- `Development` → `Launching` phase 1
- `Launching` phase n → `Launching` phase n+1
- `Launching` (any phase) → `SteadyState` with an explicitly supplied posture (graduation)
- `SteadyState` posture p → `SteadyState` posture p′ (re-posturing, including entering and leaving `InventoryOverride`)
- any stage → `Retired` (a product can be discontinued at any point)

`Retired` SHALL be terminal: no transition SHALL leave it. A transition whose target equals the product's current stage — including re-posturing to the same posture — SHALL be rejected, because a no-op change would spuriously reset the stage-entry time. Any transition not listed SHALL be rejected, leaving the stored stage unchanged.

A successful stage change SHALL yield a stage-changed notification object carrying the product identifier, the prior stage, the new stage, the confirmer, and the time of the change.

#### Scenario: A legal transition is applied and attributed

- **WHEN** a product in `Development` is moved to `Launching` phase 1 with a confirming person named
- **THEN** the product's stage is reported as `Launching` phase 1
- **AND** the change records the confirmer and the time of the change

#### Scenario: A phase is skipped

- **WHEN** a product in `Launching` phase 1 is moved to `Launching` phase 3
- **THEN** the change is rejected and the stored stage is unchanged

#### Scenario: An illegal transition is rejected

- **WHEN** a product in `Development` is moved directly to `SteadyState`
- **THEN** the change is rejected and the stored stage is unchanged

#### Scenario: Graduation requires an explicit posture

- **WHEN** a product in `Launching` is graduated to `SteadyState` without a posture supplied
- **THEN** the change is rejected — the system never chooses a posture itself

#### Scenario: A same-stage change is rejected

- **WHEN** a product in `SteadyState` with posture `Optimize` is moved to `SteadyState` with posture `Optimize`
- **THEN** the change is rejected and the stage-entry time is unchanged

#### Scenario: A successful change yields a stage-changed notification

- **WHEN** a legal, confirmed stage change is applied to a product
- **THEN** a stage-changed object is produced carrying the product identifier, the prior stage, the new stage, the confirmer, and the time of the change

#### Scenario: A retired product cannot change stage

- **WHEN** any stage change targets a product in `Retired`
- **THEN** the change is rejected

#### Scenario: An unconfirmed change is rejected

- **WHEN** a stage change is requested without a confirming person
- **THEN** the change is rejected and the stored stage is unchanged

### Requirement: A product reports when its current stage was entered

The system SHALL record the moment a product entered its current stage and report it alongside the stage, so that time-in-stage — the input to the exit-window rules later slices enforce — is always derivable.

#### Scenario: Stage entry time is reported

- **WHEN** a product's stage is read after a stage change
- **THEN** the time the current stage was entered is reported with it

### Requirement: A product can be read back by identifier or by SKU

The system SHALL retrieve a registered product — identity, name, current stage, and stage-entry time — given either its product identifier or its SKU, and SHALL report absence rather than an error when no product matches.

#### Scenario: A product is retrieved by identifier

- **WHEN** a product is read using the identifier it was registered with
- **THEN** the product is returned with every field it carries

#### Scenario: A product is retrieved by SKU

- **WHEN** a product is read using its SKU
- **THEN** the same product is returned

#### Scenario: An unknown product reports absence

- **WHEN** a product is read using an identifier or SKU no registered product has
- **THEN** the system reports that no product was found, rather than an error

### Requirement: Products can be listed with their stages

The system SHALL list registered products with, at minimum, each product's identifier, SKU, name, and current lifecycle stage, and SHALL report an empty result rather than an error when no products exist.

#### Scenario: Products are listed

- **WHEN** the product list is requested and products exist
- **THEN** every registered product is returned with its identifier, SKU, name, and current stage

#### Scenario: An empty catalog lists nothing

- **WHEN** the product list is requested and no products exist
- **THEN** an empty result is returned
