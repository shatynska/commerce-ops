## ADDED Requirements

### Requirement: An active roster member resolves to the unrestricted scope

The system SHALL resolve a Slack user identity against the roster: an identity an active roster entry carries SHALL resolve to the unrestricted scope — every product, including ones registered after the resolution. An identity carried only by a deactivated entry SHALL resolve to the scope permitting nothing, exactly as a stranger does. A resolution that cannot read the roster store SHALL yield the scope permitting nothing — fail-closed, never an error toward the asker. Product-level visibility differentiation is deliberately absent: what a person may see will be differentiated by information kind in a later change, never by product.

#### Scenario: An active member sees every product

- **WHEN** the scope is resolved for a Slack user identity an active roster entry carries
- **THEN** the resolved scope permits every product identifier

#### Scenario: A deactivated member sees nothing

- **WHEN** the scope is resolved for a Slack user identity carried only by a deactivated roster entry
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds

#### Scenario: An unreachable store fails closed

- **WHEN** the scope is resolved while the roster store cannot be read
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds without surfacing an error to the asker

### Requirement: Admin capability resolves from the roster

A roster entry SHALL carry an admin declaration, distinct from and orthogonal to visibility: membership says what a person may *see*; the admin declaration says the person may hold the admin surface's *write* authority — no membership of any shape SHALL by itself confer it. Resolution SHALL be fail-closed: an identity the roster does not know, an identity carried only by a deactivated entry, an active entry without the admin declaration, and a resolution that cannot read the roster store SHALL each resolve as not admin-capable, never as an error toward the asker.

#### Scenario: A declared entry resolves admin-capable

- **WHEN** admin capability is resolved for an identity whose active roster entry carries the admin declaration
- **THEN** the identity resolves as admin-capable

#### Scenario: Membership confers nothing

- **WHEN** admin capability is resolved for an identity whose active roster entry carries no admin declaration
- **THEN** the identity resolves as not admin-capable

#### Scenario: A deactivated admin fails closed

- **WHEN** admin capability is resolved for an identity whose roster entry carries the admin declaration but is deactivated
- **THEN** the identity resolves as not admin-capable

#### Scenario: An unknown identity fails closed

- **WHEN** admin capability is resolved for an identity the roster does not know
- **THEN** the identity resolves as not admin-capable

#### Scenario: An unreachable store fails closed

- **WHEN** admin capability is resolved while the roster store cannot be read
- **THEN** the identity resolves as not admin-capable, and the resolution succeeds

## MODIFIED Requirements

### Requirement: An unknown asker resolves to the empty scope

Resolving a scope for an identity no roster entry carries SHALL yield the scope permitting nothing — the same scope type every resolution yields, never an error and never a distinct "unknown" result. Access fails closed.

#### Scenario: A stranger sees nothing

- **WHEN** the scope is resolved for a Slack user identity with no roster entry
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds

## REMOVED Requirements

### Requirement: A principals directory is loaded from a repo-owned definition and validated

**Reason**: The directory's source moves from a repo-owned YAML file to the Postgres-backed roster (`roster` capability). Load-time validation of a deployed file no longer has a file to validate: the store only ever holds what the roster's validated writes produced, so directory faults are refused at write time rather than caught at startup.
**Migration**: Delete `principals.yaml` and its loader; declare people through the roster instead. The first admin is seeded from declared configuration (`roster` capability's bootstrap requirement).

### Requirement: A known principal's scope derives from its grants

**Reason**: The product-grant axis (`all_products` / SKU lists) is removed: every known person may see every product, and future access differentiation is by information kind, not by product.
**Migration**: Active roster membership resolves to the unrestricted scope (see the ADDED requirement); no per-product grants exist to carry over.

### Requirement: A grant naming an unregistered SKU confers nothing without failing the resolution

**Reason**: With SKU grants removed there is no stale grant to tolerate.
**Migration**: None — the situation can no longer arise.

### Requirement: A principal can be declared admin-capable

**Reason**: The requirement is re-stated against the roster (see the ADDED requirement "Admin capability resolves from the roster"): the declaration now lives on a roster entry rather than a directory-file entry, deactivation joins the fail-closed cases, and the malformed-value-at-load scenario has no load to attach to — a malformed declaration is refused at write time by the `roster` capability's validation.
**Migration**: Existing admin declarations are reproduced by the roster bootstrap (the YAML's sole admin entry becomes the seeded bootstrap admin); admin capability afterwards is granted and withdrawn through roster writes.
