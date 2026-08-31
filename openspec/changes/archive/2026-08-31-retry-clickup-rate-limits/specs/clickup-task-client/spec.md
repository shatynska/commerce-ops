## MODIFIED Requirements

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API on any of its operations — creating or updating a task, creating a list, reading a list's tasks, reading a list's own state, adding a tag to a task, reading the Custom Fields available in a folder, or setting a Custom Field value on a task; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure. The enumeration is exhaustive of the operations this capability offers, and an operation added to it later joins this rule rather than sitting outside it.

The one carved-out case is an HTTP `429` (rate limited) response, which is retried before being treated as a failure — see *A rate-limited request is retried before it is surfaced*. Every other non-successful response, and the absence of any response, propagates to the caller on the first attempt exactly as this requirement states.

#### Scenario: ClickUp rejects a create request
- **WHEN** ClickUp responds to a create-task request with a non-success status other than `429`
- **THEN** the caller receives an error and no task identifier

#### Scenario: ClickUp rejects an update request
- **WHEN** ClickUp responds to an update-task request with a non-success status other than `429`
- **THEN** the caller receives an error and no updated task identifier

#### Scenario: ClickUp rejects a create-list request
- **WHEN** ClickUp responds to a create-list request with a non-success status other than `429`
- **THEN** the caller receives an error and no list identifier

#### Scenario: ClickUp rejects a read of a list's tasks
- **WHEN** ClickUp responds to a request for a list's tasks with a non-success status other than `429`
- **THEN** the caller receives an error and no tasks

#### Scenario: ClickUp rejects a read of a list's own state
- **WHEN** ClickUp responds to a request for a list's own state with a non-success status other than `429`
- **THEN** the caller receives an error and no state

#### Scenario: ClickUp is unreachable
- **WHEN** any of the client's requests cannot reach ClickUp at all (a connection failure or timeout, with no response received)
- **THEN** the caller receives an error and no result

#### Scenario: ClickUp rejects a tag write
- **WHEN** ClickUp responds to an add-tag request with a non-success status other than `429`
- **THEN** the caller receives an error and no result

#### Scenario: ClickUp rejects a read of a folder's Custom Fields
- **WHEN** ClickUp responds to a request for a folder's Custom Fields with a non-success status other than `429`
- **THEN** the caller receives an error and no fields

#### Scenario: ClickUp rejects a Custom Field write
- **WHEN** ClickUp responds to a set-Custom-Field-value request with a non-success status other than `429`
- **THEN** the caller receives an error and no result

## ADDED Requirements

### Requirement: A rate-limited request is retried before it is surfaced
When ClickUp responds to any of this capability's operations with HTTP `429 Too Many Requests`, the system SHALL retry the request rather than surfacing it to the caller immediately, up to a bounded number of attempts. Where the `429` response carries a `Retry-After` header, the wait before retrying SHALL honor it, up to a fixed maximum wait; where the header is absent, the system SHALL fall back to its own backoff. Every operation this capability offers is covered identically — a caller cannot tell them apart on this point.

A request still receiving `429` after its retry budget is exhausted SHALL surface as a failure exactly as *A failed ClickUp request is surfaced to the caller* states for any other non-successful response — this requirement changes when a `429` reaches the caller, never whether one eventually does.

#### Scenario: A rate-limited request succeeds on retry
- **WHEN** ClickUp responds to a request with `429` and then, on a subsequent attempt, with a success response
- **THEN** the caller receives the successful result, with no error raised for the intervening `429`

#### Scenario: A `Retry-After` header is honored
- **WHEN** ClickUp responds with `429` carrying a `Retry-After` header
- **THEN** the system waits at least that long, and no longer than the fixed maximum wait, before retrying

#### Scenario: No `Retry-After` header falls back to the client's own backoff
- **WHEN** ClickUp responds with `429` carrying no `Retry-After` header
- **THEN** the system waits according to its own backoff before retrying

#### Scenario: An unparseable `Retry-After` header falls back to the client's own backoff
- **WHEN** ClickUp responds with `429` carrying a `Retry-After` header that cannot be interpreted as a plain count of seconds
- **THEN** the system waits according to its own backoff before retrying, exactly as it does when the header is absent
- **AND** no error is raised for the unparseable header itself

#### Scenario: A request exhausts its retry budget and still fails
- **WHEN** ClickUp responds with `429` on every attempt up to the retry budget
- **THEN** the caller receives an error and no result, exactly as for any other non-successful response

#### Scenario: A non-429 failure is not retried
- **WHEN** ClickUp responds to a request with a non-success status other than `429`
- **THEN** the system does not retry, and the caller receives an error on the first attempt
