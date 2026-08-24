## MODIFIED Requirements

### Requirement: A launch position can be read back by product identifier

The system SHALL retrieve a persisted launch record given the product identifier it references — the pinned playbook version, current gate, launch date, every recorded step progress with its provenance, every gate approval, and every metric attestation — and SHALL report absence rather than an error when the product has no launch record.

A read made on a caller's behalf SHALL additionally be subject to that caller's access scope: a launch whose product identifier the scope does not permit SHALL report the same absence as a product with no launch record, so that a read can never confirm the existence of a launch the caller may not see. The scope decides whether a read yields a record at all; it SHALL NOT change what a retrieved record carries, and it SHALL NOT require any particular read to carry the whole persisted record.

#### Scenario: A launch position is retrieved

- **WHEN** a launch that has recorded step outcomes, a gate approval, and a metric attestation is read using its product identifier
- **THEN** the record is returned with the pinned version, current gate, launch date, each step's outcome and provenance, each approval, and each attestation it was persisted with

#### Scenario: A product without a launch position reports absence

- **WHEN** a launch record is read for a product identifier that has none, under any scope
- **THEN** the system reports that none exists, rather than an error

#### Scenario: An out-of-scope launch reports the same absence

- **WHEN** a launch record is read on a caller's behalf for a product identifier that caller's scope does not permit
- **THEN** the system reports that none exists, exactly as it does for a product with no launch record

### Requirement: Launch positions are enumerable with their reports

The system SHALL report every persisted launch position whose referenced product identifier the caller's access scope permits, each with the same content a single-product read yields (steps with due periods and recorded progress, and the at-risk evaluation), evaluated as of a caller-supplied date; under the unrestricted scope every persisted position SHALL be reported. Enumeration SHALL NOT filter by lifecycle: the launch context does not own a product's stage, and its persisted shape deliberately does not distinguish a graduated launch from one standing at the final gate — whoever consumes the enumeration filters by the catalog's stage stamp. Scope filtering is visibility, not lifecycle: it decides whose launches the caller may see at all, never which stage of launch is worth reporting.

#### Scenario: All launch positions are reported

- **WHEN** several launch positions exist and the launches are enumerated as of a date under the unrestricted scope
- **THEN** every persisted launch position SHALL be reported, each with its steps' due periods, recorded progress, and at-risk evaluation as of that date

#### Scenario: A restricted scope enumerates only its launches

- **WHEN** several launch positions exist and the launches are enumerated under a scope permitting some of their product identifiers but not others
- **THEN** exactly the launch positions of the permitted products SHALL be reported

#### Scenario: No launches yields an empty enumeration

- **WHEN** no launch position exists and the launches are enumerated
- **THEN** the system SHALL report an empty result, not an error

#### Scenario: A scope permitting nothing enumerates nothing

- **WHEN** launch positions exist and the launches are enumerated under a scope that permits no product identifier
- **THEN** the system SHALL report an empty result, not an error
