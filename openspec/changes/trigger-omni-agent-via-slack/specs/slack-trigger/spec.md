## Purpose

The slack-trigger capability lets the ops team invoke Omni directly from a Slack channel by mentioning the bot, and receive its generated answer back in that same channel, without going through the HTTP API.

## ADDED Requirements

### Requirement: Slack App Mention Triggers Omni
When the bot is mentioned in a Slack channel it has been invited to, the system SHALL invoke omni-agent with the text of the mention as the question, and SHALL post the resulting answer back to that same channel.

#### Scenario: Mention receives an answer in the same channel
- **WHEN** the bot is `@mentioned` in a Slack channel with a question
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
The system SHALL respond to any `app_mention` from any workspace member in a channel the bot is present in; the system SHALL NOT restrict who can trigger omni-agent via Slack in this capability.

#### Scenario: Any member in the channel can trigger Omni
- **WHEN** any member of the Slack workspace mentions the bot in a channel it is in
- **THEN** the system SHALL process that mention the same as any other, without checking the sender's identity or role
