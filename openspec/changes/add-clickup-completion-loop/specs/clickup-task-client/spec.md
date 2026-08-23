# clickup-task-client Delta Specification

## ADDED Requirements

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

## MODIFIED Requirements

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
