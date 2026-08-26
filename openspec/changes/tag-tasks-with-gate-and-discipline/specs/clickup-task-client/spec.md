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
The system SHALL add a named tag to an existing task, identified by its task identifier. Adding a tag the task already carries SHALL NOT be an error.

#### Scenario: A tag is added to a task
- **WHEN** a tag is added to a task by the task's identifier and the tag's name
- **THEN** ClickUp receives an add-tag request for that task and that tag

#### Scenario: Adding a tag twice is not an error
- **WHEN** a tag is added to a task that already carries it
- **THEN** the caller receives no error

### Requirement: A tag can be created in a space
The system SHALL create a named tag in a caller-specified space. Creating a tag the space already holds SHALL NOT be an error and SHALL NOT alter the existing tag.

#### Scenario: A tag is created in a space
- **WHEN** a tag is created with a space identifier and a name
- **THEN** ClickUp receives a create-tag request for that space containing the name

#### Scenario: Creating an existing tag leaves it as it stands
- **WHEN** a tag is created in a space that already holds a tag of that name
- **THEN** the caller receives no error and the existing tag is unaltered

### Requirement: The tags of a space can be read
The system SHALL retrieve the tag names a caller-specified space holds, so that a caller can tell which of the tags it needs are missing before creating any.

#### Scenario: A space's tags are read
- **WHEN** the tags of a space are read
- **THEN** the caller receives the name of every tag the space holds

#### Scenario: A space with no tags reads as empty
- **WHEN** the tags of a space holding no tags are read
- **THEN** the caller receives an empty result, not an error

### Requirement: The space containing a folder can be resolved
The system SHALL report the identifier of the space a caller-specified folder belongs to, so that a caller configured with a folder need not also be configured with its space.

#### Scenario: A folder resolves to its space
- **WHEN** the space of a folder is resolved by the folder's identifier
- **THEN** the caller receives the identifier of the space that folder belongs to

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
