# roles Specification

## Purpose
Owns the collection of roles the company staffs — each an immutable slug, an editable title, a lifecycle status and its holders with exactly one of them the default — as Postgres-backed data edited only through validated, attributed writes, so that work can later be assigned to a position rather than to a named person.

## Requirements

### Requirement: A role is a declared position with coherent data

The system SHALL represent each role as one entry carrying: a slug that identifies it, a non-empty title, a lifecycle status of `draft`, `active` or `retired`, and a set of holders, at most one of which is marked the default.

The slug SHALL be the role's identifier — there is no second, generated one. It SHALL be non-empty, carry no leading or trailing whitespace, consist only of lowercase letters, digits and single interior hyphens, begin and end with a letter or digit, and be unique across the whole collection, retired roles included. A slug is what a step will store and what a vendored file can name, so it SHALL be chosen once and never change; this differs deliberately from a member, whose identifier is generated precisely so it can never be re-pointed at a different human.

A holder SHALL be a member of the membership, SHALL appear in a role's holders at most once, and SHALL be an active member at the moment it is added. The default holder, where one is marked, SHALL be one of that role's holders.

A write producing an entry that violates any of these rules SHALL be rejected reporting every fault at once, each fault naming the offending role.

#### Scenario: A role is identified by its slug

- **WHEN** a role is created with a slug and a title
- **THEN** the role is retrievable by that slug, and no separate generated identifier is issued for it

#### Scenario: A malformed slug is rejected

- **WHEN** a role is created with a slug carrying an uppercase letter, a leading hyphen, or surrounding whitespace
- **THEN** the write is rejected with a fault naming the slug, and nothing is persisted

#### Scenario: A duplicate slug is rejected

- **WHEN** a role is created with a slug an existing role already carries — even a retired one
- **THEN** the write is rejected with a fault naming that slug, and nothing is persisted

#### Scenario: A deactivated member cannot be added as a holder

- **WHEN** a deactivated member is added as a holder of a role
- **THEN** the write is rejected with a fault naming that member, and nothing is persisted

#### Scenario: Multiple faults are reported together

- **WHEN** a role is created with an empty title and a malformed slug
- **THEN** the write is rejected reporting both faults at once, and nothing is persisted

### Requirement: Every role write is validated whole and attributed

The role collection SHALL change only through its write use cases — create, update, add a holder, remove a holder, move the default, retire and un-retire — each validating the collection the write would produce before persisting anything: a rejected write SHALL persist nothing, and a landed write SHALL record which principal made it and when.

`create` SHALL accept the role's initial status and, where that status is `active`, its default holder in the same write. A role SHALL NOT be persisted in a state its own status forbids and then corrected: composing an active role as create-draft, add-holder, activate would satisfy the letter of these rules while recording an activation in the attribution trail that no admin performed.

The only field `update` may change is the title. A slug SHALL NOT be updatable, holders SHALL change only through the holder use cases, and status SHALL change only through the status transitions below, so each of those transitions always carries its own attribution. Renaming a role SHALL rewrite nothing else: no stored reference to a role is by title.

#### Scenario: A landed write is attributed

- **WHEN** a role is created by an authenticated admin principal
- **THEN** the stored role records that principal as its creator with the time of creation

#### Scenario: A rejected write leaves the collection unchanged

- **WHEN** a write would produce an incoherent collection
- **THEN** the write is rejected with its faults and a subsequent read observes the collection exactly as it was

#### Scenario: A slug cannot be updated

- **WHEN** an update names a role's slug as a field to change
- **THEN** the update is refused, explaining that the slug is not updatable

#### Scenario: A title is corrected freely

- **WHEN** an update changes a role's title
- **THEN** the update lands, is attributed, the role is still retrievable by the same slug, and nothing else is rewritten

### Requirement: An active role always has a default holder

An `active` role SHALL always have a default holder, and that holder SHALL be an active member. A `draft` role MAY have no holders at all — this is the whole of the difference between `draft` and `retired`, and it is what lets the collection record a position the company intends to staff but has not yet. A `retired` role SHALL retain whatever holders it had, unenforced.

Any write that would leave an `active` role without an active default holder SHALL be rejected whole, explaining itself. This obligation is not confined to role writes: deactivating a member who is the default holder of one or more active roles is refused by the same rule, and `members` states that refusal from its own side.

#### Scenario: An active role cannot be left without a default holder

- **WHEN** a write would remove the default holder of an active role
- **THEN** the write is rejected explaining that an active role must have a default holder, and nothing is persisted

#### Scenario: A draft role may hold nobody

- **WHEN** a role is created with status `draft` and no holders
- **THEN** the write lands, and the role is readable with no holders and no default

#### Scenario: A retired role keeps its holders

- **WHEN** an active role holding several members is retired
- **THEN** the role retains those holders and its default marking, and the active-role obligation is no longer enforced against it

### Requirement: Holders are managed as a set and the default is moved deliberately

The system SHALL offer adding a holder to a role, removing a holder, and moving the default from one holder to another. A member MAY hold any number of roles, and holding a role SHALL confer no authority of its own — permission remains the member's admin flag, which this collection does not touch.

Removing the default holder of an `active` role SHALL be refused whatever the rest of the holders are: where other holders remain the refusal SHALL say the default must be moved first, and where none remain it is the active-role obligation above. The default SHALL NOT be re-pointed implicitly by a removal — no holder is ever promoted to default by the system, because that would silently name a person nobody chose.

Moving the default SHALL name a member who is already a holder of that role and is active. Holders MAY be added to and removed from a `draft` or `retired` role freely, including removing its default, since neither is bound by the active-role obligation.

#### Scenario: A member holds several roles

- **WHEN** one member is added as a holder of two different roles and is the default of both
- **THEN** both writes land, and each role resolves its default to that member

#### Scenario: Removing the default of an active role is refused

- **WHEN** the default holder of an active role holding three members is removed
- **THEN** the write is rejected explaining that the default must be moved to another holder first, and no holder is promoted in their place

#### Scenario: A non-default holder leaves freely

- **WHEN** a holder who is not the default is removed from an active role
- **THEN** the write lands, is attributed, and the role's default is unchanged

#### Scenario: The default moves to another holder

- **WHEN** the default of an active role is moved to another active holder of that role
- **THEN** the write lands and that member is the role's default holder

#### Scenario: The default cannot move to a non-holder

- **WHEN** a move names a member who is not a holder of that role
- **THEN** the write is rejected explaining that the default must be one of the role's holders

#### Scenario: A draft role's default may be removed

- **WHEN** the default holder of a draft role is removed
- **THEN** the write lands and the role is left with no default

### Requirement: A role is retired, never deleted

The collection SHALL offer no deletion. A role SHALL move between statuses only along these transitions: `draft` to `active`, `draft` to `retired`, `active` to `retired`, and `retired` to `active`. No transition SHALL return a role to `draft`: once a role has been in play, `retired` is what records that it no longer is.

Entering `active` — from either `draft` or `retired` — SHALL be refused unless the role has a default holder who is an active member. A retired role retains its holders, so un-retiring one whose default has since been deactivated SHALL be refused until a holder who is active is made the default.

Retiring SHALL retain the role whole — slug, title, holders and attribution trail intact — and SHALL record who retired it and when. Un-retiring SHALL restore the same role under the same slug, recording who un-retired it and when. `draft` to `retired` is permitted so that a position sketched and then abandoned can be taken out of the working set; without it, a collection offering no deletion would accumulate abandoned drafts with no way to clear them.

#### Scenario: Activating a draft role requires a default holder

- **WHEN** a draft role holding nobody is activated
- **THEN** the write is rejected explaining that an active role must have a default holder, and the role remains `draft`

#### Scenario: A draft role with a default holder activates

- **WHEN** a draft role whose default holder is an active member is activated
- **THEN** the write lands, is attributed, and the role is `active`

#### Scenario: An abandoned draft is retired

- **WHEN** a draft role is retired
- **THEN** the write lands and the role is `retired`, retaining its slug, title and any holders

#### Scenario: Un-retiring a role whose default is deactivated is refused

- **WHEN** a retired role whose default holder has since been deactivated is un-retired
- **THEN** the write is rejected explaining that an active role's default holder must be an active member, and the role remains `retired`

#### Scenario: A retired role cannot return to draft

- **WHEN** a write names `draft` as the status a retired role should take
- **THEN** the write is refused, explaining that no role returns to `draft`

#### Scenario: Retirement is attributed and reversible

- **WHEN** an active role is retired and later un-retired
- **THEN** the same slug resolves throughout, and the role records who retired it and when, and who un-retired it and when

### Requirement: The roles are seeded before the application serves

The step that seeds the first admin SHALL also seed the roles, after the admin exists and before the HTTP server begins serving — the roles' default holders are members, so the membership must be usable first, and a later step seeds the playbook that will come to reference these slugs.

The step SHALL seed eleven roles, adding only those whose slug is not already present and altering no role that is: a slug already in the collection SHALL be left exactly as it is, whatever its title, status or holders, so that an operator's edits survive every subsequent deployment. Seeded roles SHALL be attributed to the same reserved system principal the admin seeding uses.

The member the active roles are seeded to hold is **the seeding administrator**, resolved in this order: the member the admin seeding established on this run, where it created or promoted one; otherwise the earliest-created active admin on the membership, ties and absent creation times broken by identifier so that the choice is deterministic.

The second branch always resolves. `members` has the admin seeding alter nothing only in the case where the membership already holds an active admin, so one exists to be chosen; and where the membership holds no active admin, that step has already failed and this one does not run. The seeding administrator is therefore an active member by construction on both branches, which is what the active-role obligation requires. This resolution is stated because a seed that named "the bootstrap admin" would have no referent on the branch every already-administered deployment takes — which is the branch the first deployment of this change takes.

Naming the seeding administrator SHALL confer no authority on them and SHALL alter no membership entry; it reads who administers the system in order to choose a starting holder, and holding a role confers nothing. Like the seeded titles and statuses, it is a starting arrangement to be corrected in the admin, not a claim about who owns the position.

Eight roles SHALL be seeded `active` with the seeding administrator as their sole holder and default: `supply-chain` (*Supply Chain Manager*), `ppc` (*PPC Manager*), `brand` (*Brand Manager*), `catalog` (*Catalog Manager*), `controller` (*Financial Controller*), `creative` (*Creative Manager*), `customer-service` (*Customer Service Manager*) and `marketing` (*Marketing Manager*). These are the roles a later change assigns the seeded step set to, so they must be assignable from the first boot.

Three roles SHALL be seeded `draft` holding nobody: `operations` (*Operations Manager*), `managing-director` (*Managing Director*) and `it` (*IT Manager*). None owns a step, so seeding them active would both assert that a position is filled when it is not and pin the seeding administrator as a default holder who cannot then be deactivated.

Where the step cannot read or write the role collection it SHALL fail rather than pass silently, and the application SHALL NOT begin serving — it runs after the migrations that just wrote to that same store, so an unusable one is a deployment fault, not a state to tolerate.

#### Scenario: An empty collection is seeded with eleven roles

- **WHEN** the step runs against a collection holding no roles
- **THEN** the collection afterward holds the eleven roles, the eight `active` with the seeding administrator as their sole holder and default, and the three `draft` holding nobody

#### Scenario: A seeded role that was edited is not reset

- **WHEN** the step runs against a collection in which a seeded slug has since been renamed, retired, or given different holders
- **THEN** that role is left exactly as it stands, and no second role with that slug is created

#### Scenario: Roles missing from an edited collection are added

- **WHEN** the step runs against a collection holding some of the eleven slugs but not others
- **THEN** only the absent ones are added, and the present ones are untouched

#### Scenario: The newly seeded admin holds the eight active roles

- **WHEN** the step runs against an empty membership, the admin seeding having just created the first admin
- **THEN** each of the eight active roles resolves its default holder to that member

#### Scenario: An already-administered membership resolves a seeding administrator

- **WHEN** the step runs against a membership that already holds an active admin, so the admin seeding altered nothing
- **THEN** the eight active roles are seeded holding the earliest-created active admin, and no membership entry is altered

#### Scenario: The choice is deterministic

- **WHEN** the seeding administrator is resolved twice against a membership holding several active admins and no role the seed established
- **THEN** both resolutions name the same member

#### Scenario: An unusable store fails the step

- **WHEN** the step runs against a role store that cannot be read or written
- **THEN** the step fails rather than passing silently, and the application does not begin serving
