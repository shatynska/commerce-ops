## ADDED Requirements

### Requirement: Discipline vocabulary names the owning disciplines

The vocabulary SHALL express the discipline that owns a piece of launch or observation work as one of a closed set of twelve: `strategy`, `finance`, `setup`, `inventory`, `creative`, `listing`, `rank`, `price`, `ppc`, `customer`, `external`, `traffic`. Constructing a discipline from a value outside this set SHALL fail. The set is deliberately extensible — a future context adding a discipline (for example monitoring's `sales` or `health`) SHALL be able to do so by adding a member, without structural change to the vocabulary.

#### Scenario: A known discipline is constructed

- **WHEN** a discipline is constructed from the value `inventory`
- **THEN** it is created and reports `inventory` as its value

#### Scenario: An unknown discipline is rejected

- **WHEN** a discipline is constructed from a value outside the defined set
- **THEN** construction fails

## MODIFIED Requirements

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
