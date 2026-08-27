## ADDED Requirements

### Requirement: A task can be created carrying tags
The system SHALL accept a set of tag names when creating a task, and SHALL create the task carrying exactly those tags. A create with no tags supplied SHALL send no tag claim at all, rather than a claim that the task carries none.

#### Scenario: Task created with tags
- **WHEN** a task is created with a list identifier, a name, and two tag names
- **THEN** ClickUp receives a create-task request for that list containing both tag names
- **AND** the caller receives the created task's identifier and URL

#### Scenario: Task created without tags
- **WHEN** a task is created with no tags supplied
- **THEN** the create-task request carries no tags field

### Requirement: A tag can be added to an existing task
The system SHALL add a named tag to an existing task, identified by its task identifier. The tag SHALL NOT be required to exist beforehand — attaching it creates it in the task's space where it is not already there. Adding a tag the task already carries SHALL NOT be an error.

#### Scenario: A tag is added to a task
- **WHEN** a tag is added to a task by the task's identifier and the tag's name
- **THEN** ClickUp receives an add-tag request for that task and that tag
- **AND** no space-level tag request — no tag creation, and no read of a space's tags — is sent first

#### Scenario: Adding a tag twice is not an error
- **WHEN** a tag is added to a task that already carries it
- **THEN** the caller receives no error

## MODIFIED Requirements

### Requirement: The tasks of a list can be read
The system SHALL retrieve the tasks of a caller-specified list, returning for each task at least its identifier, its status, whether that status is of the closed type, its due date — absent when the task carries none — and the names of the tags it carries. When the list holds more tasks than ClickUp returns in one page, the system SHALL return them all, not only the first page. Closed tasks SHALL be included in the result.

#### Scenario: Tasks returned with status and due date
- **WHEN** the tasks of a list are read
- **THEN** the caller receives every task in the list — closed ones included — each with its identifier, its status, whether that status is of the closed type, and its due date where one is set

#### Scenario: Tasks returned with their tags
- **WHEN** the tasks of a list are read and a task carries tags
- **THEN** that task's tag names are reported with it
- **AND** a task carrying no tags is reported with an empty set of tags, not an error

#### Scenario: An empty list reads as empty
- **WHEN** the tasks of a list holding no tasks are read
- **THEN** the caller receives an empty result, not an error

#### Scenario: A multi-page list is read completely
- **WHEN** the tasks of a list holding more tasks than one ClickUp page are read
- **THEN** the caller receives all of them

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API on any of its operations — creating or updating a task, creating a list, reading a list's tasks, reading a list's own state, or adding a tag to a task; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure. The enumeration is exhaustive of the operations this capability offers, and an operation added to it later joins this rule rather than sitting outside it.

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

#### Scenario: ClickUp rejects a read of a list's own state
- **WHEN** ClickUp responds to a request for a list's own state with a non-success status
- **THEN** the caller receives an error and no state

#### Scenario: ClickUp is unreachable
- **WHEN** any of the client's requests cannot reach ClickUp at all (a connection failure or timeout, with no response received)
- **THEN** the caller receives an error and no result

#### Scenario: ClickUp rejects a tag write
- **WHEN** ClickUp responds to an add-tag request with a non-success status
- **THEN** the caller receives an error and no result
