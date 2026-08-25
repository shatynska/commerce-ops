## MODIFIED Requirements

### Requirement: An admin-capable principal can request an admin link from Slack

The system SHALL provide a Slack slash command that replies only to the calling user (ephemerally) with a browser link into the admin surface. Before minting the link, the system SHALL verify that the calling Slack user identity resolves as admin-capable against the roster — active roster membership alone SHALL NOT suffice. A caller who does not resolve admin-capable — whether unknown to the roster, deactivated, or an active member without the admin declaration — SHALL receive one and the same ephemeral refusal, whose content carries no admin URL and does not confirm that an admin surface exists. The link SHALL carry a single-use token bound to the verified principal. The token SHALL expire no more than ten minutes after minting.

#### Scenario: An admin-capable principal receives a link

- **WHEN** a Slack user who resolves admin-capable invokes the command
- **THEN** they receive an ephemeral reply carrying a link with a token bound to their principal identity
- **AND** the reply is visible only to them

#### Scenario: A visibility-only principal is refused like an unknown one

- **WHEN** a Slack user the roster knows as an active member, but whose entry carries no admin declaration, invokes the command
- **THEN** they receive the same ephemeral refusal an unknown caller receives, with no admin URL

#### Scenario: An unknown caller's refusal confirms nothing

- **WHEN** a Slack user the roster does not know invokes the command
- **THEN** they receive an ephemeral refusal whose content contains no admin URL and does not confirm that an admin surface exists

### Requirement: Admin access fails closed and absence-shaped

Every admin route SHALL require a valid, unexpired session whose principal still resolves as admin-capable against the roster at the time of the request. A request failing any part of that — no session, an expired or unrecognized session, a session whose principal's roster entry has since been deactivated, or one whose entry no longer carries the admin declaration — SHALL be refused with the same absence-shaped response as a route that does not exist, revealing neither the surface nor the reason.

#### Scenario: No session means no surface

- **WHEN** an admin route is requested without a session
- **THEN** the response is identical in shape to requesting a route that does not exist

#### Scenario: Removal from the directory revokes access on the next request

- **WHEN** a principal's roster entry is deactivated — the roster's form of removal, since entries are never deleted — while their session is still unexpired, and they then request an admin route
- **THEN** the request is refused with the absence-shaped response

#### Scenario: Withdrawing the admin declaration revokes access likewise

- **WHEN** a principal's roster entry loses its admin declaration while their session is still unexpired, and they then request an admin route
- **THEN** the request is refused with the absence-shaped response
