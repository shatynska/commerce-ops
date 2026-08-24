# shared-vocabulary Specification

## Purpose

Defines the domain vocabulary every module speaks — identity value objects (product identity and the metric identifier), the lifecycle-stage vocabulary, and the discipline vocabulary naming who owns a piece of work — so that modules exchange validated, self-describing values instead of raw strings. Vocabulary only: construction-time validation, no transition rules or other cross-module behavior.

## Requirements

### Requirement: Identity value objects validate at construction

The system SHALL provide identity value objects — a product identifier, a SKU, an ASIN, a marketplace identifier, and a metric identifier — each of which SHALL reject construction from an invalid value rather than carry it. A SKU, an ASIN, a marketplace identifier, and a metric identifier SHALL each reject an empty value and a value with leading or trailing whitespace. An ASIN SHALL additionally reject a value that is not exactly ten alphanumeric characters. A product identifier SHALL reject an empty value; beyond that it is opaque — generated, never parsed for meaning. A metric identifier is likewise opaque beyond its emptiness and whitespace rules: until a metric registry exists, nothing validates that the metric it names is defined, and the identifier is a reference to be resolved later, not a checked foreign key.

#### Scenario: A valid SKU is constructed

- **WHEN** a SKU value object is constructed from a non-empty string with no surrounding whitespace
- **THEN** it is created and reports that string as its value

#### Scenario: An empty identity value is rejected

- **WHEN** a product identifier, SKU, ASIN, marketplace identifier, or metric identifier is constructed from an empty value
- **THEN** construction fails with an error naming the offending value

#### Scenario: A padded identity value is rejected

- **WHEN** a SKU, ASIN, marketplace identifier, or metric identifier is constructed from a string with leading or trailing whitespace
- **THEN** construction fails rather than silently trimming

#### Scenario: A malformed ASIN is rejected

- **WHEN** an ASIN is constructed from a value that is not exactly ten alphanumeric characters
- **THEN** construction fails with an error naming the value

#### Scenario: A metric identifier does not require a defined metric

- **WHEN** a metric identifier is constructed from a non-empty, unpadded value naming no known metric
- **THEN** it is created, because resolution against a metric registry is not this vocabulary's concern

### Requirement: Value objects are immutable and compare by value

Every vocabulary value object SHALL be immutable after construction and SHALL compare equal to another instance exactly when their values are equal, so they can serve as dictionary keys and set members across module boundaries.

#### Scenario: Two value objects with the same value are equal

- **WHEN** two SKU value objects are constructed from the same string
- **THEN** they compare equal and hash equal

#### Scenario: Mutation is not possible

- **WHEN** code attempts to assign to a field of a constructed value object
- **THEN** the attempt fails

### Requirement: Discipline vocabulary names the owning disciplines

The vocabulary SHALL express the discipline that owns a piece of launch or observation work as one of a closed set of twelve: `strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`, `price`, `ppc`, `customer`, `external`, `traffic`. Constructing a discipline from a value outside this set SHALL fail. The set is deliberately extensible — a future context adding a discipline (for example monitoring's `sales` or `health`) SHALL be able to do so by adding a member, without structural change to the vocabulary.

#### Scenario: A known discipline is constructed

- **WHEN** a discipline is constructed from the value `inventory`
- **THEN** it is created and reports `inventory` as its value

#### Scenario: An unknown discipline is rejected

- **WHEN** a discipline is constructed from a value outside the defined set
- **THEN** construction fails

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

### Requirement: Severity vocabulary names the reporting tiers

The shared vocabulary SHALL name the severities an attention item can carry: monitor, diagnose, and critical — the tiers findings are graded into for reporting. Below-threshold noise is not a severity: something not worth reporting produces no item at all. Severity values SHALL follow the vocabulary's existing construction rules: a known tier is constructible, an unknown one is rejected.

#### Scenario: A known severity is constructed

- **WHEN** a severity is constructed from the value "critical"
- **THEN** the severity is created and reports its value

#### Scenario: An unknown severity is rejected

- **WHEN** a severity is constructed from a value outside monitor, diagnose, critical
- **THEN** construction SHALL be rejected

### Requirement: Access-scope vocabulary expresses product visibility

The vocabulary SHALL express a caller's product visibility as an access scope that is either unrestricted or an explicit, possibly empty, set of product identifiers. The scope SHALL report whether it permits a given product identifier: an unrestricted scope permits every identifier; an explicit-set scope permits exactly the members of its set; the empty set is constructible and permits nothing — the fail-closed default. The unrestricted scope SHALL be a distinct construction, not a set enumerating all products, since the set of all products is unknowable to a value and changes after a scope is built. The vocabulary SHALL NOT define how a scope is derived from a person or a grant — derivation belongs to the access context, the way stage-transition rules belong to the catalog. The access scope follows the vocabulary's existing immutability and value-equality rules.

#### Scenario: The unrestricted scope permits every product

- **WHEN** an unrestricted access scope is asked whether it permits any product identifier
- **THEN** it reports that it does

#### Scenario: An explicit-set scope permits exactly its members

- **WHEN** an access scope is constructed from a set containing one product identifier and asked about that identifier and about a different one
- **THEN** it permits the member and does not permit the non-member

#### Scenario: The empty scope permits nothing

- **WHEN** an access scope is constructed from an empty set and asked whether it permits any product identifier
- **THEN** it reports that it does not
