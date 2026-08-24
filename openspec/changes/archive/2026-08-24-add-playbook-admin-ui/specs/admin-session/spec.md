## Purpose

Bridges Slack identity into a browser session for admin surfaces: a slash command mints a short-lived, single-use link for an admin-capable principal, opening the link exchanges its token for a bounded session cookie, and every other path — callers who do not resolve admin-capable, spent or expired tokens, absent or outlived sessions — is refused in a shape that does not reveal the surface exists.

## ADDED Requirements

### Requirement: An admin-capable principal can request an admin link from Slack

The system SHALL provide a Slack slash command that replies only to the calling user (ephemerally) with a browser link into the admin surface. Before minting the link, the system SHALL verify that the calling Slack user identity resolves as admin-capable in the principals directory — directory membership and visibility grants alone SHALL NOT suffice. A caller who does not resolve admin-capable — whether unknown to the directory or known without the admin declaration — SHALL receive one and the same ephemeral refusal, whose content carries no admin URL and does not confirm that an admin surface exists. The link SHALL carry a single-use token bound to the verified principal. The token SHALL expire no more than ten minutes after minting.

#### Scenario: An admin-capable principal receives a link

- **WHEN** a Slack user who resolves admin-capable invokes the command
- **THEN** they receive an ephemeral reply carrying a link with a token bound to their principal identity
- **AND** the reply is visible only to them

#### Scenario: A visibility-only principal is refused like an unknown one

- **WHEN** a Slack user the directory knows, but whose entry carries no admin declaration, invokes the command
- **THEN** they receive the same ephemeral refusal an unknown caller receives, with no admin URL

#### Scenario: An unknown caller's refusal confirms nothing

- **WHEN** a Slack user the principals directory does not know invokes the command
- **THEN** they receive an ephemeral refusal whose content contains no admin URL and does not confirm that an admin surface exists

### Requirement: A link token is single-use and short-lived

Opening a minted link SHALL exchange its token for a browser session exactly once: a successful exchange SHALL invalidate the token before the response is sent. A second use of the same token, an expired token, and a token the system never minted SHALL each be refused with the same absence-shaped response — indistinguishable from requesting a route that does not exist — so a refused caller cannot tell which of the three cases they hit.

#### Scenario: A token exchanges once

- **WHEN** a freshly minted, unexpired token is opened
- **THEN** the response establishes a browser session for the token's principal

#### Scenario: A spent token is refused like nothing

- **WHEN** the same token is opened a second time
- **THEN** the response is identical in shape to requesting a route that does not exist

#### Scenario: An expired token is refused identically

- **WHEN** a token is opened after its expiry
- **THEN** the response is identical to the spent-token refusal

### Requirement: A browser session is bounded and rides a hardened cookie

The session established by a token exchange SHALL be carried by a cookie that page script cannot read and that is not sent over plaintext transport in deployed environments. The session SHALL expire no more than twelve hours after it was established; a request bearing an expired session SHALL be refused exactly as a request bearing no session is. The system SHALL NOT establish a session by any path other than the token exchange.

#### Scenario: A session outlives its usefulness and stops working

- **WHEN** an admin route is requested with a session older than its lifetime
- **THEN** the request is refused exactly as if no session were presented

#### Scenario: The cookie is hardened

- **WHEN** the session cookie is set by the token exchange
- **THEN** it is marked unreadable to page script
- **AND** in deployed environments it is marked for secure transport only

### Requirement: Admin access fails closed and absence-shaped

Every admin route SHALL require a valid, unexpired session whose principal still resolves as admin-capable in the principals directory at the time of the request. A request failing any part of that — no session, an expired or unrecognized session, a session whose principal has since left the directory, or one whose entry no longer carries the admin declaration — SHALL be refused with the same absence-shaped response as a route that does not exist, revealing neither the surface nor the reason.

#### Scenario: No session means no surface

- **WHEN** an admin route is requested without a session
- **THEN** the response is identical in shape to requesting a route that does not exist

#### Scenario: Removal from the directory revokes access on the next request

- **WHEN** a principal's entry is removed from the principals directory while their session is still unexpired, and they then request an admin route
- **THEN** the request is refused with the absence-shaped response

#### Scenario: Withdrawing the admin declaration revokes access likewise

- **WHEN** a principal's entry loses its admin declaration while their session is still unexpired, and they then request an admin route
- **THEN** the request is refused with the absence-shaped response
