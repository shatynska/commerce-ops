## ADDED Requirements

### Requirement: The Custom Fields available in a folder can be read

The system SHALL retrieve the Custom Fields available to a caller-specified folder, returning for each field at least its identifier, its name, its type, and — where the field declares a set of options — those options in the order the field declares them, each with its own identifier and name. Reading at folder scope rather than list scope is what lets a caller learn the configuration without a list existing: a field configured on a folder is available to every list within it, so one read answers for all of them and for a folder holding no lists yet.

Every field the folder declares SHALL be returned, not only those in a first page, on the same ground the read of a list's tasks states it: a configured field missing from the result is indistinguishable from one that does not exist, and a caller judging a configuration would be told a field is absent when it is merely unreturned — a false repair instruction, and one that would additionally withhold every write for that field.

A field declaring no options SHALL be reported as declaring none, which is a fact about the field rather than an error — a caller that requires options is the one that decides what their absence means.

**The read SHALL be total: no field SHALL cause it to raise.** A folder holds whatever anyone has added to it, at any type this capability does not anticipate and may never anticipate — a formula, a relationship, a labels field whose options carry a shape this capability was not written against. A field the system cannot interpret SHALL be reported with the identifier, name and type it does carry, marked as **uninterpretable**, and SHALL NOT stop the other fields being reported. Where a field is uninterpretable it SHALL be reported as that **and not additionally as declaring no options**, even though it declares none: the two are not alternative descriptions of one field but a precedence, since every uninterpretable field trivially declares no options and reporting both would leave a caller unable to tell which fact to act on. Uninterpretable SHALL be distinguishable from *declaring no options*: the two call for different responses, and collapsing them would have a caller tell somebody to add options to a field that already has eight — the same reason a value the client cannot interpret is reported as it stands rather than as absent. This is the same obligation the read of a list's tasks carries and for the same reason: a caller reads a folder's fields to judge a configuration, so one unrelated field somebody added must not be able to take that judgement away permanently. A read that raised on an unanticipated field would fail on every subsequent read too, since nothing in this system can remove the field that causes it.

#### Scenario: A folder's Custom Fields are read

- **WHEN** the Custom Fields of a folder are read
- **THEN** the caller receives each field's identifier, name and type
- **AND** each option of a field that declares options, with its identifier and name, in the order the field declares them

#### Scenario: A folder's fields are read completely

- **WHEN** the task system returns a folder's fields in pages, and the Custom Fields of a folder declaring more fields than one page are read
- **THEN** every field the folder declares is returned

#### Scenario: A folder with no Custom Fields reads as empty

- **WHEN** the Custom Fields of a folder that has none are read
- **THEN** the caller receives an empty result, not an error

#### Scenario: A field the capability does not anticipate does not fail the read

- **WHEN** the Custom Fields of a folder are read and one field is of a type this capability does not anticipate, or carries a shape it was not written against
- **THEN** the read completes and reports every other field
- **AND** that field is reported with the identifier, name and type it carries, marked as **uninterpretable**

#### Scenario: An uninterpretable field is distinguishable from one declaring no options

- **WHEN** the Custom Fields of a folder are read and it holds both a field the capability cannot interpret and a field that genuinely declares no options
- **THEN** a caller can tell the two apart from what it receives
- **AND** neither is reported as the other

#### Scenario: A field declaring no options is reported as such

- **WHEN** the Custom Fields of a folder are read and one field declares no options
- **THEN** that field is reported with no options rather than omitted or reported as an error

### Requirement: A Custom Field value can be set on an existing task

The system SHALL set a value for a named Custom Field on an existing task, identified by the task's identifier and the field's identifier. Setting a value the task already holds SHALL NOT be an error.

A value drawn from a field's declared option set SHALL be named by **that option's identifier**. This is the other end of the contract *The tasks of a list can be read* states from the read side, and both ends are needed: the no-op guarantee a caller relies on — compare what a task carries against what would be written, and write only on a difference — holds only if the two speak the same representation.

The field SHALL be required to exist beforehand: unlike a tag, a Custom Field is not brought into being by being used, and this capability offers no operation that creates a field, changes its type, or adds, removes, reorders or renames an option. That is a measured property of the task system rather than an assumption — the reasoning and the measurements are recorded in this change's design.

#### Scenario: A value is set on a task

- **WHEN** a Custom Field value is set on a task by the task's identifier and the field's identifier
- **THEN** ClickUp receives a set-value request for that task and that field carrying that value

#### Scenario: An option value is named by the option's identifier

- **WHEN** a value drawn from a field's declared option set is set on a task
- **THEN** the request names that value by the option's identifier, the same representation the read of a list's tasks reports it in

#### Scenario: Setting the same value twice is not an error

- **WHEN** a Custom Field value is set on a task that already holds it
- **THEN** the caller receives no error

## MODIFIED Requirements

### Requirement: The tasks of a list can be read
The system SHALL retrieve the tasks of a caller-specified list, returning for each task at least its identifier, its status, whether that status is of the closed type, its due date — absent when the task carries none — the names of the tags it carries, and the value it currently holds for each Custom Field that carries one, each identified by that field's identifier. When the list holds more tasks than ClickUp returns in one page, the system SHALL return them all, not only the first page. Closed tasks SHALL be included in the result.

A value drawn from a field's declared option set SHALL be reported as **that option's identifier** — the same representation a write of that value sends. A caller compares what a task carries against what it intends to write, and a comparison across two representations of the same value is not a comparison at all: it reports every task as differing, on every pass, producing a write that succeeds and changes nothing. Where the task system reports such a value in some other form, the system SHALL normalise it to the option identifier rather than passing the difference to the caller.

The normalisation SHALL be performed from what the task payload itself carries. This operation SHALL NOT require a separately obtained field definition, and SHALL NOT make a second request to obtain one — a read of a list's tasks answers about tasks, and requiring it to first learn every field's options would make one read into two and put a second failure on the path. A definition the task payload itself carries is part of the payload and may be used.

**The read SHALL be total: no Custom Field value SHALL cause it to raise.** A value the system cannot interpret as a single option identifier — one naming no option the field currently declares, one carrying several values where an option identifier was expected, or one of any shape this capability does not anticipate — SHALL be reported as the payload carries it, unnormalised, and SHALL NOT be reported as absent. The reason is not the cost of a redundant write, which reporting absence would not in fact incur: it is that this read gates a launch's projection and its completion intake, so a value the client cannot make sense of must not be able to stop either. One hand edit in the task system's own interface — deleting and recreating an option, or changing a field's type under values already written — would otherwise stop convergence for everything. Reporting the value as it stands preserves what is there for a caller that can judge it; reporting absence would discard information the caller may need to tell "nothing set" from "something the client did not recognise".

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

#### Scenario: Tasks returned with their Custom Field values

- **WHEN** the tasks of a list are read and a task holds a value for a Custom Field
- **THEN** that value is reported with the task, identified by that field's identifier
- **AND** a task holding no Custom Field value is reported with none, not an error

#### Scenario: A value the client cannot interpret does not fail the read

- **WHEN** the tasks of a list are read and a task holds a Custom Field value that names no declared option, or carries several values, or is of a shape this capability does not anticipate
- **THEN** the read completes and returns every task
- **AND** that value is reported as the payload carries it, neither raising nor being reported as absent

#### Scenario: An option value reads back as it would be written

- **WHEN** a value is set on a task from a field's declared option set, and the tasks of that list are then read
- **THEN** the value reported for that task and that field is the same option identifier that was written
- **AND** a caller comparing the two finds them equal

### Requirement: A failed ClickUp request is surfaced to the caller
The system SHALL NOT catch or suppress a failure from ClickUp's API on any of its operations — creating or updating a task, creating a list, reading a list's tasks, adding a tag to a task, reading the Custom Fields available in a folder, or setting a Custom Field value on a task; a non-successful response, or the absence of any response, SHALL propagate to the caller as an error identifying the failure. The enumeration is exhaustive of the operations this capability offers, and an operation added to it later joins this rule rather than sitting outside it.

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

#### Scenario: ClickUp rejects a tag write
- **WHEN** ClickUp responds to an add-tag request with a non-success status
- **THEN** the caller receives an error and no result

#### Scenario: ClickUp rejects a read of a folder's Custom Fields

- **WHEN** ClickUp responds to a request for a folder's Custom Fields with a non-success status
- **THEN** the caller receives an error and no fields

#### Scenario: ClickUp rejects a Custom Field write

- **WHEN** ClickUp responds to a set-Custom-Field-value request with a non-success status
- **THEN** the caller receives an error and no result
