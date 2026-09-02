# slack-trigger Specification

## Purpose

The slack-trigger capability lets the ops team invoke Omni directly from a Slack channel by mentioning the bot, and receive its generated answer back in that same channel, without going through the HTTP API.

## Requirements

### Requirement: Slack App Mention Triggers Omni
When the bot is mentioned by a member in a Slack channel it has been invited to, the system SHALL invoke omni-agent with the text of the mention as the question, and SHALL post the resulting answer back to that same channel.

A mention authored by a bot rather than a member is outside this requirement and is governed by "Bot-Authored Events Do Not Trigger A Reply".

#### Scenario: Mention receives an answer in the same channel
- **WHEN** a member `@mentions` the bot in a Slack channel with a question
- **THEN** the system SHALL post omni-agent's generated answer as a message in that same channel

### Requirement: Slack Request Authenticity Is Verified
The system SHALL verify that each incoming Slack Events API request is authentically from Slack, using Slack's request-signing scheme, before processing it, and SHALL reject any request that fails verification.

#### Scenario: Unsigned or forged request is rejected
- **WHEN** an incoming request to the Slack events endpoint fails Slack's signature verification
- **THEN** the system SHALL reject the request and SHALL NOT invoke omni-agent

### Requirement: Endpoint Responds to Slack's URL Verification Challenge
The system SHALL respond to a Slack `url_verification` challenge request by returning the challenge value it was sent, so Slack can confirm the endpoint before enabling event delivery.

#### Scenario: Challenge request is echoed back
- **WHEN** Slack sends a `url_verification` challenge request to the events endpoint
- **THEN** the system SHALL respond with the same challenge value it received

### Requirement: Slack Events Are Acknowledged Within Slack's Timeout
The system SHALL respond to an incoming Slack event within Slack's required acknowledgement window, independent of how long generating the answer takes.

#### Scenario: Slow answer generation does not delay the acknowledgement
- **WHEN** the bot is mentioned and generating the answer takes longer than Slack's acknowledgement window
- **THEN** the system SHALL still have acknowledged the event within that window, and SHALL post the answer separately once it is ready

### Requirement: Answer Generation Failure Is Visible in Slack
If invoking omni-agent fails while processing a mention, the system SHALL post a visible failure message to the originating channel rather than leaving the mention without any response.

#### Scenario: Omni-agent invocation fails
- **WHEN** omni-agent's invocation fails while processing an `app_mention`
- **THEN** the system SHALL post a message to the originating channel indicating the request failed, rather than posting nothing

### Requirement: No Sender Identity Restriction (Deferred)
The system SHALL respond to any `app_mention` from any human workspace member in a channel the bot is present in; the system SHALL NOT restrict which workspace members can trigger omni-agent via Slack in this capability.

Suppressing bot-authored events, as "Bot-Authored Events Do Not Trigger A Reply" requires, is not a sender-identity restriction and is not deferred by this requirement: it distinguishes a message authored by a program from one authored by a member, and never distinguishes one member from another.

#### Scenario: Any member in the channel can trigger Omni
- **WHEN** any human member of the Slack workspace mentions the bot in a channel it is in
- **THEN** the system SHALL process that mention the same as any other, without checking the sender's identity or role

#### Scenario: No member is privileged over another
- **WHEN** two different workspace members each mention the bot in a channel it is in
- **THEN** the system SHALL process both mentions identically, without consulting either sender's identity, role or permissions

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
The system SHALL NOT invoke omni-agent, and SHALL NOT post a reply, for an `app_mention` that was authored by a bot rather than by a member — identified by the event carrying a `bot_id`, or a `subtype` marking it as bot-authored. Such an event SHALL still be acknowledged with a success status, so Slack does not retry it.

This exists to prevent the system answering its own posts, or entering a reply loop with another bot. It is loop prevention, not authorization: it keys on how the message was authored, never on which member authored it.

#### Scenario: A bot-authored mention receives no reply
- **WHEN** an authentic `app_mention` carrying a `bot_id`, or a bot-authored `subtype`, is delivered
- **THEN** the system SHALL acknowledge it with a success status
- **AND** SHALL NOT invoke omni-agent
- **AND** SHALL NOT post any message to the originating channel

#### Scenario: A member's mention is unaffected by the bot-authorship check
- **WHEN** an authentic `app_mention` authored by a member, carrying no `bot_id` and no bot-authored `subtype`, is delivered
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
- **WHEN** an authentic member-authored `app_mention` arrives and the token needed to post a reply is absent, or present but empty
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
