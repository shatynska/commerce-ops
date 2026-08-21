# internal-trigger Specification

## Purpose

Lets a driving HTTP endpoint restrict its caller to trusted internal automation (e.g. a scheduler) by requiring a shared secret, rather than relying on network placement alone to establish trust.

## Requirements

### Requirement: Trigger Secret Is Required
The system SHALL reject any request to an internal-trigger-guarded endpoint that does not present the configured trigger secret via an `Authorization` bearer header, and SHALL NOT invoke the endpoint's handler for a rejected request.

#### Scenario: Missing secret is rejected
- **WHEN** a request to an internal-trigger-guarded endpoint carries no `Authorization` header
- **THEN** the system SHALL reject the request with a 401 response and SHALL NOT invoke the endpoint's handler

#### Scenario: Incorrect secret is rejected
- **WHEN** a request carries an `Authorization` bearer value that does not match the configured trigger secret
- **THEN** the system SHALL reject the request with a 401 response and SHALL NOT invoke the endpoint's handler

### Requirement: Correct Secret Is Accepted
The system SHALL invoke the endpoint's handler when the presented secret matches the configured trigger secret.

#### Scenario: Matching secret is accepted
- **WHEN** a request carries an `Authorization` bearer value equal to the configured trigger secret
- **THEN** the system SHALL invoke the endpoint's handler

### Requirement: Secret Comparison Is Constant-Time
The system SHALL compare the presented secret to the configured trigger secret using a constant-time comparison, so that response timing does not reveal how many leading characters matched.

#### Scenario: Comparison uses constant-time equality
- **WHEN** the guard compares a presented secret to the configured secret
- **THEN** it SHALL use a constant-time comparison rather than a short-circuiting equality check

### Requirement: Guard Fails Closed When Unconfigured
The system SHALL reject every request to a guarded endpoint if the trigger secret is not configured in the running environment, rather than allowing requests through.

#### Scenario: Trigger secret is not configured
- **WHEN** the trigger secret is absent from the running environment
- **THEN** the system SHALL reject every request to a guarded endpoint
