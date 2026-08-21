## Purpose

The clickup-task-client capability lets commerce-ops create and update tasks in ClickUp on behalf of any module, through one shared adapter, without any module owning its own ClickUp credentials or HTTP integration.

## ADDED Requirements

### Requirement: A task can be created in a given list
The system SHALL create a new ClickUp task in a caller-specified list, given at least the list's identifier and the task's name, and SHALL return the created task's identifier and URL.

#### Scenario: Task created with a name only
- **WHEN** a task is created with a list identifier and a name, and no description
- **THEN** ClickUp receives a create-task request for that list containing the name
- **AND** the caller receives the created task's identifier and URL

#### Scenario: Task created with a name and description
- **WHEN** a task is created with a list identifier, a name, and a description
- **THEN** ClickUp receives a create-task request for that list containing both the name and the description
- **AND** the caller receives the created task's identifier and URL

### Requirement: An existing task can be updated with caller-supplied fields
The system SHALL update an existing ClickUp task, identified by its task identifier, applying exactly the fields the caller supplies, and SHALL return the updated task's identifier and URL.

#### Scenario: Task updated with one field
- **WHEN** a task is updated by its identifier with one field
- **THEN** ClickUp receives an update request for that task containing exactly that field
- **AND** the caller receives the updated task's identifier and URL

#### Scenario: Task updated with multiple fields
- **WHEN** a task is updated by its identifier with more than one field
- **THEN** ClickUp receives an update request for that task containing exactly those fields
- **AND** the caller receives the updated task's identifier and URL

#### Scenario: Task updated with no fields
- **WHEN** a task is updated by its identifier with an empty set of fields
- **THEN** ClickUp receives an update request for that task with an empty body
- **AND** the caller receives the updated task's identifier and URL

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API when creating or updating a task; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure.

#### Scenario: ClickUp rejects a create request
- **WHEN** ClickUp responds to a create-task request with a non-success status
- **THEN** the caller receives an error and no task identifier

#### Scenario: ClickUp rejects an update request
- **WHEN** ClickUp responds to an update-task request with a non-success status
- **THEN** the caller receives an error and no updated task identifier

#### Scenario: ClickUp is unreachable
- **WHEN** a create-task or update-task request cannot reach ClickUp at all (a connection failure or timeout, with no response received)
- **THEN** the caller receives an error and no task identifier

### Requirement: Authentication is configured independently of any one caller
The system SHALL authenticate every request to ClickUp using a single configured credential, not one supplied per caller or per module, and SHALL NOT require that credential to be present except when a request is actually made.

#### Scenario: Credential absent until first use
- **WHEN** the client module is imported, or the application starts, and no ClickUp credential is configured
- **THEN** nothing fails as a result

#### Scenario: Credential absent at call time
- **WHEN** a task is created or updated and no ClickUp credential is configured
- **THEN** the caller receives an error, and no request is sent to ClickUp
