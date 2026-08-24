## ADDED Requirements

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
