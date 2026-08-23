# clickup-task-client Specification

## Purpose
The clickup-task-client capability lets commerce-ops create and update tasks in ClickUp on behalf of any module, through one shared adapter, without any module owning its own ClickUp credentials or HTTP integration.

## Requirements

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

### Requirement: A list can be created in a given folder
The system SHALL create a new ClickUp list in a caller-specified folder, given at least the folder's identifier and the list's name, and SHALL return the created list's identifier.

#### Scenario: List created in a folder
- **WHEN** a list is created with a folder identifier and a name
- **THEN** ClickUp receives a create-list request for that folder containing the name
- **AND** the caller receives the created list's identifier

### Requirement: The tasks of a list can be read
The system SHALL retrieve the tasks of a caller-specified list, returning for each task at least its identifier, its status, whether that status is of the closed type, and its due date — absent when the task carries none. When the list holds more tasks than ClickUp returns in one page, the system SHALL return them all, not only the first page. Closed tasks SHALL be included in the result.

#### Scenario: Tasks returned with status and due date
- **WHEN** the tasks of a list are read
- **THEN** the caller receives every task in the list — closed ones included — each with its identifier, its status, whether that status is of the closed type, and its due date where one is set

#### Scenario: An empty list reads as empty
- **WHEN** the tasks of a list holding no tasks are read
- **THEN** the caller receives an empty result, not an error

#### Scenario: A multi-page list is read completely
- **WHEN** the tasks of a list holding more tasks than one ClickUp page are read
- **THEN** the caller receives all of them

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API on any of its operations — creating or updating a task, creating a list, or reading a list's tasks; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure.

#### Scenario: ClickUp rejects a create request
- **WHEN** ClickUp responds to a create-task request with a non-success status
- **THEN** the caller receives an error and no task identifier

#### Scenario: ClickUp rejects an update request
- **WHEN** ClickUp responds to an update-task request with a non-success status
- **THEN** the caller receives an error and no updated task identifier

#### Scenario: ClickUp rejects a create-list request
- **WHEN** ClickUp responds to a create-list request with a non-success status
- **THEN** the caller receives an error and no list identifier

#### Scenario: ClickUp rejects a read of a list's tasks
- **WHEN** ClickUp responds to a request for a list's tasks with a non-success status
- **THEN** the caller receives an error and no tasks

#### Scenario: ClickUp is unreachable
- **WHEN** any of the client's requests cannot reach ClickUp at all (a connection failure or timeout, with no response received)
- **THEN** the caller receives an error and no result

### Requirement: Authentication is configured independently of any one caller
The system SHALL authenticate every request to ClickUp using a single configured credential, not one supplied per caller or per module, and SHALL NOT require that credential to be present except when a request is actually made.

#### Scenario: Credential absent until first use
- **WHEN** the client module is imported, or the application starts, and no ClickUp credential is configured
- **THEN** nothing fails as a result

#### Scenario: Credential absent at call time
- **WHEN** a task is created or updated and no ClickUp credential is configured
- **THEN** the caller receives an error, and no request is sent to ClickUp
