## ADDED Requirements

### Requirement: A list's own state can be read

The system SHALL retrieve the state of a caller-specified list, returning at least whether ClickUp reports that list as deleted. This is the list's own state, distinct from reading the tasks the list holds: a list ClickUp reports as deleted still answers a read of its tasks, and answers it as empty, so its tasks cannot establish whether the list exists.

The result SHALL report only what ClickUp states. Absence of an answer is not an answer: a list whose state could not be read is not thereby a list reported as deleted, and this operation SHALL offer its caller no way to confuse the two. How a failure reaches the caller is the failure requirement's to state, not this one's.

#### Scenario: A deleted list reports itself deleted

- **WHEN** the state of a list ClickUp has deleted is read
- **THEN** the caller receives a result reporting the list as deleted

#### Scenario: A live list reports itself not deleted

- **WHEN** the state of a list ClickUp still holds is read
- **THEN** the caller receives a result reporting the list as not deleted

## MODIFIED Requirements

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API on any of its operations — creating or updating a task, creating a list, reading a list's tasks, or reading a list's own state; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure.

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
