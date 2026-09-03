## ADDED Requirements

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
