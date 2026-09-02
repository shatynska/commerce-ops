# access-scope Specification

## Purpose

Answers "which products may this caller see" — and, since `add-playbook-admin-ui`, "does this caller hold the admin write capability": resolves both, fail-closed, from the membership (`move-principals-to-roster`, which replaced the repo-owned principals directory), yielding the access scope every read use case filters by and the orthogonal per-entry admin declaration the admin surface is gated on. Product-level differentiation is deliberately absent — an active member sees every product, and what a member may see will be differentiated by information kind in a later change. It never authenticates — adapters establish who is asking; this capability only says what that identity may see and whether it may hold the admin surface.

## Requirements

### Requirement: An unknown asker resolves to the empty scope

Resolving a scope for an identity no membership entry carries SHALL yield the scope permitting nothing — the same scope type every resolution yields, never an error and never a distinct "unknown" result. Access fails closed.

#### Scenario: A stranger sees nothing

- **WHEN** the scope is resolved for a Slack user identity with no members entry
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds

### Requirement: An active member resolves to the unrestricted scope

The system SHALL resolve a Slack user identity against the membership: an identity an active membership entry carries SHALL resolve to the unrestricted scope — every product, including ones registered after the resolution. An identity carried only by a deactivated entry SHALL resolve to the scope permitting nothing, exactly as a stranger does. A resolution that cannot read the members store SHALL yield the scope permitting nothing — fail-closed, never an error toward the asker. Product-level visibility differentiation is deliberately absent: what a member may see will be differentiated by information kind in a later change, never by product.

#### Scenario: An active member sees every product

- **WHEN** the scope is resolved for a Slack user identity an active membership entry carries
- **THEN** the resolved scope permits every product identifier

#### Scenario: A deactivated member sees nothing

- **WHEN** the scope is resolved for a Slack user identity carried only by a deactivated membership entry
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds

#### Scenario: An unreachable store fails closed

- **WHEN** the scope is resolved while the members store cannot be read
- **THEN** the resolved scope permits no product identifier, and the resolution succeeds without surfacing an error to the asker

### Requirement: Admin capability resolves from the membership

A membership entry SHALL carry an admin declaration, distinct from and orthogonal to visibility: membership says what a member may *see*; the admin declaration says the member may hold the admin surface's *write* authority — no membership of any shape SHALL by itself confer it. Resolution SHALL be fail-closed: an identity the membership does not know, an identity carried only by a deactivated entry, an active entry without the admin declaration, and a resolution that cannot read the members store SHALL each resolve as not admin-capable, never as an error toward the asker.

#### Scenario: A declared entry resolves admin-capable

- **WHEN** admin capability is resolved for an identity whose active members entry carries the admin declaration
- **THEN** the identity resolves as admin-capable

#### Scenario: Membership confers nothing

- **WHEN** admin capability is resolved for an identity whose active members entry carries no admin declaration
- **THEN** the identity resolves as not admin-capable

#### Scenario: A deactivated admin fails closed

- **WHEN** admin capability is resolved for an identity whose membership entry carries the admin declaration but is deactivated
- **THEN** the identity resolves as not admin-capable

#### Scenario: An unknown identity fails closed

- **WHEN** admin capability is resolved for an identity the membership does not know
- **THEN** the identity resolves as not admin-capable

#### Scenario: An unreachable store fails closed

- **WHEN** admin capability is resolved while the members store cannot be read
- **THEN** the identity resolves as not admin-capable, and the resolution succeeds
