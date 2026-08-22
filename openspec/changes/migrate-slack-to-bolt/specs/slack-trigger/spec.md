## ADDED Requirements

### Requirement: An Event With No Registered Handler Is Still Acknowledged
When Slack delivers an authentic event that the system has no handler registered for, the system SHALL acknowledge it with a success response rather than an error response, so that Slack does not treat the delivery as failed and retry it.

#### Scenario: An event type with no handler is acknowledged
- **WHEN** Slack delivers an authentic `event_callback` whose event type has no registered handler
- **THEN** the system SHALL respond with a success status
- **AND** SHALL NOT invoke omni-agent

#### Scenario: A handled event type still reaches its handler
- **WHEN** Slack delivers an authentic `app_mention`, for which a handler is registered
- **THEN** that handler SHALL run, rather than the event being absorbed by the acknowledgement of unhandled events

### Requirement: Handling An Event Requires No Credential Verification Call To Slack
The system SHALL make no outbound Slack call for the purpose of establishing its own identity or validating its own credentials, either at startup or while handling an inbound request.

This constrains identity and credential-verification calls only. It does not restrict outbound calls a capability makes to do its work.

#### Scenario: Handling a mention makes no credential-verification call
- **WHEN** an authentic `app_mention` is received and handled
- **THEN** the system SHALL make no outbound Slack call to establish or validate its own identity or credentials
- **AND** the call posting its answer SHALL NOT be preceded by any such call

#### Scenario: No credential-verification call at startup
- **WHEN** the application starts and its Slack handling is initialized
- **THEN** the system SHALL make no outbound Slack call to establish or validate its own identity or credentials

#### Scenario: Inbound handling is unaffected by Slack being unreachable
- **WHEN** an authentic inbound request is received while Slack's API is unreachable
- **THEN** the system SHALL still verify, accept and acknowledge that request, and SHALL fail only at the point of delivering an outbound message

### Requirement: Bot-Authored Events Do Not Trigger A Reply
The system SHALL NOT invoke omni-agent, and SHALL NOT post a reply, for an `app_mention` that was authored by a bot rather than by a person — identified by the event carrying a `bot_id`, or a `subtype` marking it as bot-authored. Such an event SHALL still be acknowledged with a success status, so Slack does not retry it.

This exists to prevent the system answering its own posts, or entering a reply loop with another bot. It is loop prevention, not authorization: it keys on how the message was authored, never on which person authored it.

#### Scenario: A bot-authored mention receives no reply
- **WHEN** an authentic `app_mention` carrying a `bot_id`, or a bot-authored `subtype`, is delivered
- **THEN** the system SHALL acknowledge it with a success status
- **AND** SHALL NOT invoke omni-agent
- **AND** SHALL NOT post any message to the originating channel

#### Scenario: A person's mention is unaffected by the bot-authorship check
- **WHEN** an authentic `app_mention` authored by a person, carrying no `bot_id` and no bot-authored `subtype`, is delivered
- **THEN** the system SHALL process it normally and post omni-agent's answer to the originating channel

### Requirement: A Request That Cannot Be Handled With Available Credentials Is Rejected
When an inbound Slack request arrives and a credential that request needs is absent, or present but empty, the system SHALL reject that request with an unauthorized response rather than acknowledging it or returning a server-error response.

A credential is evaluated only for requests that need it. A request the system can answer without a given credential SHALL NOT be rejected on account of that credential's absence.

This requirement covers absence and emptiness — conditions observable from the configuration alone. A credential that is present and non-empty but rejected by Slack SHALL surface when a message is delivered, not before: establishing otherwise would require an outbound identity call, which "Handling An Event Requires No Credential Verification Call To Slack" forbids.

#### Scenario: The signing secret is absent or empty
- **WHEN** an inbound request arrives and the signing secret needed to verify it is absent or empty
- **THEN** the system SHALL respond as unauthorized
- **AND** SHALL NOT invoke omni-agent

#### Scenario: The credential needed to reply is absent or empty
- **WHEN** an authentic person-authored `app_mention` arrives and the token needed to post a reply is absent, or present but empty
- **THEN** the system SHALL respond as unauthorized rather than acknowledging an event it cannot answer

#### Scenario: A request needing no reply credential is unaffected
- **WHEN** a `url_verification` challenge arrives while the token needed to post a reply is absent
- **THEN** the system SHALL answer the challenge normally, since answering it requires no such token

#### Scenario: An event that is only acknowledged is unaffected
- **WHEN** an authentic `event_callback` whose event type has no registered handler arrives while the token needed to post a reply is absent
- **THEN** the system SHALL acknowledge it with a success status, as "An Event With No Registered Handler Is Still Acknowledged" requires
- **AND** SHALL NOT reject it, since acknowledging it requires no such token

#### Scenario: An event that is deliberately not answered is unaffected
- **WHEN** an authentic bot-authored `app_mention` arrives while the token needed to post a reply is absent
- **THEN** the system SHALL acknowledge it with a success status, as "Bot-Authored Events Do Not Trigger A Reply" requires
- **AND** SHALL NOT reject it, since the system was never going to reply to it

## MODIFIED Requirements

### Requirement: Slack App Mention Triggers Omni
When the bot is mentioned by a person in a Slack channel it has been invited to, the system SHALL invoke omni-agent with the text of the mention as the question, and SHALL post the resulting answer back to that same channel.

A mention authored by a bot rather than a person is outside this requirement and is governed by "Bot-Authored Events Do Not Trigger A Reply".

#### Scenario: Mention receives an answer in the same channel
- **WHEN** a person `@mentions` the bot in a Slack channel with a question
- **THEN** the system SHALL post omni-agent's generated answer as a message in that same channel

### Requirement: No Sender Identity Restriction (Deferred)
The system SHALL respond to any `app_mention` from any human workspace member in a channel the bot is present in; the system SHALL NOT restrict which workspace members can trigger omni-agent via Slack in this capability.

Suppressing bot-authored events, as "Bot-Authored Events Do Not Trigger A Reply" requires, is not a sender-identity restriction and is not deferred by this requirement: it distinguishes a message authored by a program from one authored by a person, and never distinguishes one person from another.

#### Scenario: Any member in the channel can trigger Omni
- **WHEN** any human member of the Slack workspace mentions the bot in a channel it is in
- **THEN** the system SHALL process that mention the same as any other, without checking the sender's identity or role

#### Scenario: No member is privileged over another
- **WHEN** two different workspace members each mention the bot in a channel it is in
- **THEN** the system SHALL process both mentions identically, without consulting either sender's identity, role or permissions
