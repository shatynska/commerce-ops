## ADDED Requirements

### Requirement: An Event With No Registered Handler Is Still Acknowledged
When Slack delivers an authentic event that the system has no handler registered for, the system SHALL acknowledge it with a success response rather than an error response, so that Slack does not treat the delivery as failed and retry it.

#### Scenario: An event type with no handler is acknowledged
- **WHEN** Slack delivers an authentic `event_callback` whose event type has no registered handler
- **THEN** the system SHALL respond with a success status
- **AND** SHALL NOT invoke omni-agent

#### Scenario: An unhandled event is not retried by Slack
- **WHEN** an authentic event with no registered handler has been acknowledged
- **THEN** the response SHALL be one Slack treats as successful delivery, so the same event is not redelivered

### Requirement: Handling An Event Requires No Credential Verification Call To Slack
The system SHALL NOT make any outbound call to Slack in order to establish its own identity or validate its own credentials, either at startup or while handling an inbound request. Outbound calls to Slack SHALL be made only to deliver a message the system has decided to send.

#### Scenario: Handling a mention makes no credential-verification call
- **WHEN** an authentic `app_mention` is received and handled
- **THEN** the only outbound Slack call the system makes SHALL be the one posting its answer

#### Scenario: No credential-verification call at startup
- **WHEN** the application starts and its Slack handling is initialized
- **THEN** the system SHALL make no outbound Slack call

#### Scenario: Inbound handling is unaffected by Slack being unreachable
- **WHEN** an authentic inbound request is received while Slack's API is unreachable
- **THEN** the system SHALL still verify, accept and acknowledge that request, and SHALL fail only at the point of delivering an outbound message
