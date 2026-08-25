## Purpose

Owns the directory of people the system knows — display names, per-service identities, admin authority and active status — as Postgres-backed data edited only through validated, attributed writes, replacing the deployed principals file.

## ADDED Requirements

### Requirement: A person is a declared identity with coherent identity data

The system SHALL represent each known person as one roster entry carrying: a generated identifier (never chosen by a caller, never reused), a non-empty display name, a Slack identity that is non-empty, carries no leading or trailing whitespace and is unique across the entire roster (deactivated entries included), an optional ClickUp user id, an admin flag, and an active flag. A write producing an entry that violates any of these rules SHALL be rejected reporting every fault at once, each fault naming the offending entry.

#### Scenario: A created person carries a generated identifier

- **WHEN** a person is created with a display name and a Slack identity
- **THEN** the created entry carries an identifier the caller did not supply, and the entry is retrievable by it

#### Scenario: A duplicate Slack identity is rejected

- **WHEN** a person is created with a Slack identity an existing entry already carries — even a deactivated one
- **THEN** the write is rejected with a fault naming that Slack identity, and nothing is persisted

#### Scenario: Multiple faults are reported together

- **WHEN** a person is created with an empty display name and a whitespace-padded Slack identity
- **THEN** the write is rejected reporting both faults at once, and nothing is persisted

### Requirement: Every roster write is validated whole and attributed

The roster SHALL change only through its write use cases — create, update, deactivate, reactivate — each validating the roster the write would produce before persisting anything: a rejected write SHALL persist nothing, and a landed write SHALL record which principal made it and when. The startup seed SHALL land through this same validated, attributed path as one additional atomic write — create-or-promote in a single validated save, never composed from the enumerated verbs (whose intermediate rosters the last-admin floor would reject) and never written directly to the store — attributed to a reserved system principal. The fields `update` may change are exactly the display name, the ClickUp user id and the admin flag: a generated identifier and a Slack identity SHALL NOT be updatable, and active status SHALL change only through deactivate and reactivate, so those transitions always carry their own attribution. Updates SHALL apply to deactivated entries as well as active ones — correcting a deactivated person's data does not require reactivating them.

#### Scenario: A landed write is attributed

- **WHEN** a person is created by an authenticated admin principal
- **THEN** the stored entry records that principal as its creator with the time of creation

#### Scenario: A rejected write leaves the roster unchanged

- **WHEN** an update would produce an incoherent roster
- **THEN** the update is rejected with its faults and a subsequent read observes the roster exactly as it was

#### Scenario: A Slack identity cannot be updated

- **WHEN** an update names a person's Slack identity as a field to change
- **THEN** the update is refused, explaining that the identity is not updatable

#### Scenario: A deactivated entry can be corrected in place

- **WHEN** an update changes a deactivated person's display name
- **THEN** the update lands, is attributed, and the entry remains deactivated

### Requirement: The roster never loses its last active admin

A write whose outcome would leave the roster without at least one active entry carrying the admin flag SHALL be rejected whole, explaining itself — deactivating the last active admin and withdrawing the last active admin's flag alike. A write that removes admin authority or active status from an entry while another active admin remains SHALL be permitted.

#### Scenario: Deactivating the last active admin is refused

- **WHEN** the roster holds exactly one active admin and a write deactivates that person
- **THEN** the write is rejected with a fault explaining the roster would be left without an active admin, and nothing is persisted

#### Scenario: Withdrawing the last active admin's flag is refused

- **WHEN** the roster holds exactly one active admin and an update withdraws that person's admin flag
- **THEN** the write is rejected with the same explanation, and nothing is persisted

#### Scenario: An admin among admins can step down

- **WHEN** the roster holds two active admins and a write deactivates one of them
- **THEN** the write lands

### Requirement: A person is deactivated, never deleted

The roster SHALL offer no deletion. Deactivation SHALL retain the entry — identity data and attribution trail intact — while excluding it from access resolution, and SHALL record who deactivated it and when. Reactivation SHALL restore the same entry under the same identifier, recording who reactivated it and when.

#### Scenario: A deactivated person remains on the roster

- **WHEN** a person is deactivated
- **THEN** the entry is still readable with its history, records who deactivated it and when, and no longer resolves to any access

#### Scenario: Reactivation restores the same entry

- **WHEN** a deactivated person is reactivated
- **THEN** the same identifier resolves again, and the entry records who reactivated it and when

### Requirement: The first admin is seeded from declared configuration

At startup, when the roster store is readable and holds no active admin entry, the system SHALL ensure the Slack identity named by a declared environment variable exists on the roster as an active admin — creating the entry when the identity is unknown (its display name seeded as the Slack identity itself, editable afterwards like any other entry's), and marking the existing entry active and admin when it is already present. The seed SHALL also run when the readable roster's only active admin is a single entry whose admin status the seed itself conferred — the stored signal being that the entry's most recent admin-conferring write (the creation or promotion that made it an active admin) is attributed to the reserved system principal, unaffected by later writes that confer nothing — and the variable names a different Slack identity — so a mis-typed first seed is corrected by fixing the variable and redeploying, the wrongly seeded entry then deactivated through ordinary writes once the corrected admin exists; the seed SHALL NOT itself deactivate anything. In every other case where the readable roster holds an active admin, startup SHALL NOT alter the roster and the variable SHALL confer nothing. When the roster store is readable, holds no active admin, and the variable is absent, startup SHALL fail with an error naming the variable rather than serve a roster no one can administer. When the roster store is unconfigured or unreachable, startup SHALL succeed without altering or requiring anything — preserving the guarantees that starting requires no configuration and that no database connection is made before it is first needed — reporting the deferred bootstrap as a logged fault, so the seed runs on the next start against a readable store.

#### Scenario: An empty roster is seeded

- **WHEN** the process starts with a readable, empty roster and the bootstrap variable naming a Slack identity
- **THEN** the roster afterward holds that identity as an active admin entry whose display name is the Slack identity itself

#### Scenario: An existing entry is promoted rather than duplicated

- **WHEN** the process starts with no active admin on the readable roster and the bootstrap variable naming a Slack identity an existing deactivated entry carries
- **THEN** that entry becomes active and admin, and no second entry with that identity exists

#### Scenario: A rostered admin makes the variable inert

- **WHEN** the process starts with the readable roster holding an active admin beyond a lone seed-attributed entry
- **THEN** the roster is not altered, whatever the bootstrap variable names

#### Scenario: A mis-seeded first admin is corrected by redeploying

- **WHEN** the process starts with the readable roster's only active admin being the single seed-attributed entry, and the variable now names a different Slack identity
- **THEN** the newly named identity becomes an active admin alongside it, and nothing is deactivated by the seed

#### Scenario: No admin and no variable stops startup

- **WHEN** the process starts with a readable roster holding no active admin and no bootstrap variable
- **THEN** startup fails with an error naming the missing variable

#### Scenario: An unconfigured or unreachable store defers the bootstrap

- **WHEN** the process starts with the roster store unconfigured or unreachable
- **THEN** startup succeeds without touching the roster, and the deferred bootstrap is reported as a logged fault
