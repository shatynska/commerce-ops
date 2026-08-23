# shared-vocabulary Delta

## Purpose

Defines the domain vocabulary every module speaks — product identity value objects and the lifecycle-stage vocabulary — so that modules exchange validated, self-describing values instead of raw strings. Vocabulary only: construction-time validation, no transition rules or other cross-module behavior.

## ADDED Requirements

### Requirement: Identity value objects validate at construction

The system SHALL provide product-identity value objects — a product identifier, a SKU, an ASIN, and a marketplace identifier — each of which SHALL reject construction from an invalid value rather than carry it. A SKU, an ASIN, and a marketplace identifier SHALL each reject an empty value and a value with leading or trailing whitespace. An ASIN SHALL additionally reject a value that is not exactly ten alphanumeric characters. A product identifier SHALL reject an empty value; beyond that it is opaque — generated, never parsed for meaning.

#### Scenario: A valid SKU is constructed

- **WHEN** a SKU value object is constructed from a non-empty string with no surrounding whitespace
- **THEN** it is created and reports that string as its value

#### Scenario: An empty identity value is rejected

- **WHEN** a product identifier, SKU, ASIN, or marketplace identifier is constructed from an empty value
- **THEN** construction fails with an error naming the offending value

#### Scenario: A padded identity value is rejected

- **WHEN** a SKU, ASIN, or marketplace identifier is constructed from a string with leading or trailing whitespace
- **THEN** construction fails rather than silently trimming

#### Scenario: A malformed ASIN is rejected

- **WHEN** an ASIN is constructed from a value that is not exactly ten alphanumeric characters
- **THEN** construction fails with an error naming the value

### Requirement: Value objects are immutable and compare by value

Every vocabulary value object SHALL be immutable after construction and SHALL compare equal to another instance exactly when their values are equal, so they can serve as dictionary keys and set members across module boundaries.

#### Scenario: Two value objects with the same value are equal

- **WHEN** two SKU value objects are constructed from the same string
- **THEN** they compare equal and hash equal

#### Scenario: Mutation is not possible

- **WHEN** code attempts to assign to a field of a constructed value object
- **THEN** the attempt fails

### Requirement: Lifecycle-stage vocabulary names the stages a product can be in

The vocabulary SHALL express a product's lifecycle stage as one of: `Development`; `Launching` carrying a phase from 1 to 4; `SteadyState` carrying a posture that is one of `Scale`, `Optimize`, `Hold`, `Recover`, or `InventoryOverride`; and `Retired`. A `Launching` stage SHALL reject a phase outside 1–4. The vocabulary SHALL NOT define which transitions between stages are legal — transition rules belong to the catalog context.

#### Scenario: A launching stage carries its phase

- **WHEN** a `Launching` stage value is constructed with phase 2
- **THEN** it reports phase 2

#### Scenario: An out-of-range launch phase is rejected

- **WHEN** a `Launching` stage value is constructed with phase 0 or phase 5
- **THEN** construction fails

#### Scenario: A steady-state stage carries its posture

- **WHEN** a `SteadyState` stage value is constructed with the posture `Hold`
- **THEN** it reports the posture `Hold`

### Requirement: The vocabulary identifies which stages are temporary

The lifecycle-stage vocabulary SHALL report whether a stage value is temporary — a state a product must eventually leave. `Launching` (every phase) and `SteadyState` with the `InventoryOverride` posture SHALL report as temporary; `Development`, `Retired`, and `SteadyState` with any other posture SHALL NOT.

#### Scenario: Launching is temporary

- **WHEN** any `Launching` stage value is asked whether it is temporary
- **THEN** it reports that it is

#### Scenario: Inventory override is temporary

- **WHEN** a `SteadyState` stage value with posture `InventoryOverride` is asked whether it is temporary
- **THEN** it reports that it is

#### Scenario: Ordinary steady state is not temporary

- **WHEN** a `SteadyState` stage value with posture `Scale`, `Optimize`, `Hold`, or `Recover` is asked whether it is temporary
- **THEN** it reports that it is not
