# access-scope Specification

## Purpose

Answers "which products may this caller see": owns the repo-owned principals directory and derives from it, fail-closed, the access scope every read use case filters by. It never authenticates — adapters establish who is asking; this capability only says what that identity may see.

## Requirements

### Requirement: A principals directory is loaded from a repo-owned definition and validated

The system SHALL read principal definitions from a repo-owned directory file mapping a Slack user identity to a visibility declaration: either an all-products grant, or a list of SKU grants (which MAY be empty). Loading SHALL reject a malformed directory rather than carry it: a duplicate principal identity, an empty or whitespace-padded identity, an entry declaring both an all-products grant and SKU grants, an entry declaring neither, and a SKU grant value that is empty or carries leading or trailing whitespace SHALL each fail the load with an error naming the offending entry. The directory SHALL be loaded and validated before the system serves any scope resolution: a malformed directory SHALL prevent the process from starting to serve, and SHALL never surface as an error on an individual asker's resolution.

#### Scenario: A well-formed directory loads

- **WHEN** the principals directory declares one identity with an all-products grant and another with a list of SKU grants
- **THEN** the directory loads and both principals are known

#### Scenario: A duplicate identity is rejected at load

- **WHEN** the principals directory declares the same identity twice
- **THEN** the load fails with an error naming that identity

#### Scenario: An entry declaring both grant forms is rejected

- **WHEN** a principal entry declares an all-products grant and also lists SKU grants
- **THEN** the load fails with an error naming that entry

#### Scenario: An entry declaring no grant form is rejected

- **WHEN** a principal entry declares neither an all-products grant nor a SKU grant list
- **THEN** the load fails with an error naming that entry

#### Scenario: A malformed SKU grant value is rejected

- **WHEN** a principal entry lists a SKU grant that is empty or padded with whitespace
- **THEN** the load fails rather than silently trimming or skipping it

#### Scenario: A malformed directory prevents serving rather than failing resolutions

- **WHEN** the process starts against a malformed principals directory
- **THEN** startup fails with the load error naming the offending entry, and no scope resolution ever observes the malformed directory

### Requirement: A known principal's scope derives from its grants

Given a loaded principals directory, the system SHALL resolve a Slack user identity to an access scope: an all-products grant SHALL yield the unrestricted scope; a list of SKU grants SHALL yield a scope permitting exactly the product identifiers of the registered products those SKUs identify; an empty grant list SHALL yield the scope permitting nothing.

#### Scenario: An all-products principal resolves to the unrestricted scope

- **WHEN** the scope is resolved for an identity whose entry carries the all-products grant
- **THEN** the resolved scope permits every product identifier

#### Scenario: SKU grants resolve to exactly those products

- **WHEN** the scope is resolved for an identity granted two SKUs, both belonging to registered products
- **THEN** the resolved scope permits exactly those two products' identifiers and no other

#### Scenario: An empty grant list resolves to the empty scope

- **WHEN** the scope is resolved for an identity whose entry carries an empty SKU grant list
- **THEN** the resolved scope permits no product identifier

### Requirement: An unknown asker resolves to the empty scope

Resolving a scope for an identity the principals directory does not declare SHALL yield the scope permitting nothing — the same scope type every resolution yields, never an error and never a distinct "unknown" result. Access fails closed.

#### Scenario: A stranger sees nothing

- **WHEN** the scope is resolved for a Slack user identity with no entry in the principals directory
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds

### Requirement: A grant naming an unregistered SKU confers nothing without failing the resolution

When a SKU grant names a SKU no registered product has, that grant SHALL confer no visibility, and the resolution SHALL still succeed with the principal's remaining grants honored — one stale grant never locks a principal out of the products they may legitimately see, and never turns into an error for the asker.

#### Scenario: A stale grant is skipped, the rest stand

- **WHEN** the scope is resolved for an identity granted one SKU belonging to a registered product and one SKU no product has
- **THEN** the resolved scope permits exactly the registered product's identifier, and the resolution succeeds
