# members Specification

## Purpose
Owns the directory of membership the system knows — display names, per-service identities, admin authority and active status — as Postgres-backed data edited only through validated, attributed writes, replacing the deployed principals file.

## Requirements

### Requirement: A member is a declared identity with coherent identity data

The system SHALL represent each known member as one members entry carrying: a generated identifier (never chosen by a caller, never reused), a non-empty display name, a Slack identity that is non-empty, carries no leading or trailing whitespace and is unique across the entire membership (deactivated entries included), an optional ClickUp user id, an admin flag, and an active flag. A write producing an entry that violates any of these rules SHALL be rejected reporting every fault at once, each fault naming the offending entry.

#### Scenario: A created member carries a generated identifier

- **WHEN** a member is created with a display name and a Slack identity
- **THEN** the created entry carries an identifier the caller did not supply, and the entry is retrievable by it

#### Scenario: A duplicate Slack identity is rejected

- **WHEN** a member is created with a Slack identity an existing entry already carries — even a deactivated one
- **THEN** the write is rejected with a fault naming that Slack identity, and nothing is persisted

#### Scenario: Multiple faults are reported together

- **WHEN** a member is created with an empty display name and a whitespace-padded Slack identity
- **THEN** the write is rejected reporting both faults at once, and nothing is persisted

### Requirement: Every membership write is validated whole and attributed

The membership SHALL change only through its write use cases — create, update, deactivate, reactivate — each validating the membership the write would produce before persisting anything: a rejected write SHALL persist nothing, and a landed write SHALL record which principal made it and when. The seeding step SHALL land through this same validated, attributed path as one additional atomic write — create-or-promote in a single validated save, never composed from the enumerated verbs (whose intermediate members the last-admin floor would reject) and never written directly to the store — attributed to a reserved system principal. The fields `update` may change are exactly the display name, the ClickUp user id and the admin flag: a generated identifier and a Slack identity SHALL NOT be updatable, and active status SHALL change only through deactivate and reactivate, so those transitions always carry their own attribution. Updates SHALL apply to deactivated entries as well as active ones — correcting a deactivated member's data does not require reactivating them.

#### Scenario: A landed write is attributed

- **WHEN** a member is created by an authenticated admin principal
- **THEN** the stored entry records that principal as its creator with the time of creation

#### Scenario: A rejected write leaves the membership unchanged

- **WHEN** an update would produce an incoherent membership
- **THEN** the update is rejected with its faults and a subsequent read observes the membership exactly as it was

#### Scenario: A Slack identity cannot be updated

- **WHEN** an update names a member's Slack identity as a field to change
- **THEN** the update is refused, explaining that the identity is not updatable

#### Scenario: A deactivated entry can be corrected in place

- **WHEN** an update changes a deactivated member's display name
- **THEN** the update lands, is attributed, and the entry remains deactivated

### Requirement: The membership never loses its last active admin

A write whose outcome would leave the membership without at least one active entry carrying the admin flag SHALL be rejected whole, explaining itself — deactivating the last active admin and withdrawing the last active admin's flag alike. A write that removes admin authority or active status from an entry while another active admin remains SHALL be permitted.

#### Scenario: Deactivating the last active admin is refused

- **WHEN** the membership holds exactly one active admin and a write deactivates that member
- **THEN** the write is rejected with a fault explaining the membership would be left without an active admin, and nothing is persisted

#### Scenario: Withdrawing the last active admin's flag is refused

- **WHEN** the membership holds exactly one active admin and an update withdraws that member's admin flag
- **THEN** the write is rejected with the same explanation, and nothing is persisted

#### Scenario: An admin among admins can step down

- **WHEN** the membership holds two active admins and a write deactivates one of them
- **THEN** the write lands

### Requirement: A member is deactivated, never deleted

The membership SHALL offer no deletion. Deactivation SHALL retain the entry — identity data and attribution trail intact — while excluding it from access resolution, and SHALL record who deactivated it and when. Reactivation SHALL restore the same entry under the same identifier, recording who reactivated it and when.

#### Scenario: A deactivated member remains on the membership

- **WHEN** a member is deactivated
- **THEN** the entry is still readable with its history, records who deactivated it and when, and no longer resolves to any access

#### Scenario: Reactivation restores the same entry

- **WHEN** a deactivated member is reactivated
- **THEN** the same identifier resolves again, and the entry records who reactivated it and when

### Requirement: The first admin is seeded before the application serves

The system SHALL provide a seeding step that runs after database migrations and before the HTTP server begins serving, as a step of its own rather than as part of the serving process's own startup — so that starting the application still opens no database connection before one is first needed, and a deployment that cannot be administered fails at a named preparation step instead of crash-looping the server.

When the membership holds no active admin entry, the step SHALL ensure the Slack identity named by a declared environment variable exists on the membership as an active admin — creating the entry when the identity is unknown (its display name seeded as the Slack identity itself, editable afterwards like any other entry's), and marking the existing entry active and admin when it is already present — a promotion recording the reserved principal in the entry's update attribution, not its reactivation attribution, so the page shows what happened (the step edited the entry) rather than implying a member reactivated it. The step SHALL also run when the membership's only active admin is a single entry whose admin status the seed itself conferred — the stored signal being that the entry's most recent admin-conferring write (the creation or promotion that made it an active admin) is attributed to the reserved system principal, unaffected by later writes that confer nothing — and the variable names a different Slack identity, so a mis-typed first seed is corrected by fixing the variable and redeploying, the wrongly seeded entry then deactivated through ordinary writes once the corrected admin exists; the step SHALL NOT itself deactivate anything. In every other case where the membership holds an active admin, the step SHALL alter nothing and the variable SHALL confer nothing.

When the membership holds no active admin and the variable is absent — or present but empty or whitespace-only, which SHALL be treated as absent rather than as an identity — the step SHALL fail, naming the variable, and the application SHALL NOT begin serving. When the members store cannot be read, the step SHALL likewise fail rather than pass silently: it runs after the migrations that just wrote to that same store, so an unreadable one is a deployment fault, not a state to tolerate.

#### Scenario: An empty membership is seeded

- **WHEN** the step runs against an empty membership with the bootstrap variable naming a Slack identity
- **THEN** the membership afterward holds that identity as an active admin entry whose display name is the Slack identity itself

#### Scenario: An existing entry is promoted rather than duplicated

- **WHEN** the step runs against a membership with no active admin, the bootstrap variable naming a Slack identity an existing deactivated entry carries
- **THEN** that entry becomes active and admin, and no second entry with that identity exists
- **AND** the entry records the reserved system principal as its most recent update, leaving its reactivation attribution untouched

#### Scenario: An enrolled admin makes the variable inert

- **WHEN** the step runs against a membership holding an active admin beyond a lone seed-attributed entry
- **THEN** the membership is not altered, whatever the bootstrap variable names

#### Scenario: A mis-seeded first admin is corrected by redeploying

- **WHEN** the step runs against a membership whose only active admin is the single seed-attributed entry, and the variable now names a different Slack identity
- **THEN** the newly named identity becomes an active admin alongside it, and nothing is deactivated by the step

#### Scenario: No admin and no variable fails the step

- **WHEN** the step runs against a membership holding no active admin with no bootstrap variable set
- **THEN** the step fails with an error naming the missing variable, and the application does not begin serving

#### Scenario: An empty variable is treated as absent

- **WHEN** the step runs against a membership holding no active admin with the bootstrap variable set to an empty or whitespace-only value
- **THEN** the step fails naming the variable, exactly as it does when the variable is unset, rather than attempting to seed an entry with no identity

#### Scenario: An unreadable store fails the step

- **WHEN** the step runs against a members store that cannot be read
- **THEN** the step fails rather than passing silently, and writes nothing

#### Scenario: Starting the server performs no seeding

- **WHEN** the serving process starts
- **THEN** it performs no seeding of its own, leaving the connection-timing guarantee `database-session` states to that specification

### Requirement: A member holding an active role's default may not be deactivated

A deactivation whose outcome would leave any `active` role without an active default holder SHALL be rejected whole, explaining itself and naming **every** active role the member is the default holder of — not the first one found. A member who deactivates while holding eight such roles should learn that in one refusal rather than in eight attempts, and the membership already rejects a write "reporting every fault at once".

This refusal is independent of the last-active-admin refusal and composes with it: a write may be refused by either, by both, or by neither. Holding a role confers no authority, so a member may be the default holder of any number of roles without being an admin, and an admin may hold none.

A member who holds active roles but is the default of none SHALL deactivate freely, as SHALL one who is the default of `draft` or `retired` roles only — neither is bound by the active-role obligation `roles` states. To deactivate a member who is an active role's default, the default is first moved to another holder or the role is retired; the system SHALL NOT do either implicitly on the member's behalf.

#### Scenario: Deactivating an active role's default holder is refused

- **WHEN** a member who is the default holder of an active role is deactivated
- **THEN** the write is rejected explaining that the role would be left without a default holder, and nothing is persisted

#### Scenario: Every blocking role is named at once

- **WHEN** a member who is the default holder of several active roles is deactivated
- **THEN** the refusal names all of those roles, not only one of them

#### Scenario: A non-default holder deactivates freely

- **WHEN** a member who holds active roles but is the default of none is deactivated
- **THEN** the write lands and the member leaves the active membership

#### Scenario: Holding only draft or retired roles does not block

- **WHEN** a member who is the default holder of draft and retired roles only is deactivated
- **THEN** the write lands

#### Scenario: Moving the default unblocks the deactivation

- **WHEN** the default of each blocking active role is moved to another holder, and the member is deactivated again
- **THEN** the write lands

#### Scenario: Both refusals report together

- **WHEN** the membership's last active admin is also the default holder of an active role and that member is deactivated
- **THEN** the write is rejected reporting both the last-admin fault and the role fault, and nothing is persisted
