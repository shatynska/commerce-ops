## ADDED Requirements

### Requirement: A principal can be declared admin-capable

The principals directory SHALL support an optional per-entry admin declaration, distinct from and orthogonal to visibility grants: grants say what a principal may *see*; the admin declaration says the principal may hold the admin surface's *write* authority. An entry without the declaration SHALL mean exactly what it means today — no existing directory file becomes invalid, and no visibility grant of any shape SHALL by itself confer admin capability. A malformed admin declaration value SHALL fail the directory load with an error naming the offending entry, like every other directory fault. Resolution SHALL be fail-closed: an identity the directory does not know, and a known identity whose entry carries no admin declaration, SHALL each resolve as not admin-capable.

#### Scenario: A declared entry resolves admin-capable

- **WHEN** admin capability is resolved for an identity whose entry carries the admin declaration
- **THEN** the identity resolves as admin-capable

#### Scenario: Visibility grants confer nothing

- **WHEN** admin capability is resolved for an identity whose entry carries the all-products grant but no admin declaration
- **THEN** the identity resolves as not admin-capable

#### Scenario: An unknown identity fails closed

- **WHEN** admin capability is resolved for an identity the directory does not know
- **THEN** the identity resolves as not admin-capable

#### Scenario: A malformed admin declaration is rejected at load

- **WHEN** the principals directory declares an entry whose admin declaration carries a malformed value
- **THEN** the load fails with an error naming that entry
