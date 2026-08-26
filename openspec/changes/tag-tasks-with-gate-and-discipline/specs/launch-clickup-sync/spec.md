## ADDED Requirements

### Requirement: A projected task carries its step's gate and discipline as tags

The system SHALL tag each projected task with the gate the step belongs to and the discipline that owns it, so that a launch list can be grouped and filtered along the two divisions the playbook is built on. The tags SHALL be named `gate:<gate identifier>` and `discipline:<discipline value>`, using the identifiers the playbook and the shared vocabulary already fix, so no second naming scheme has to be kept true to the first.

The prefixes are what the system owns. A tag carrying neither prefix belongs to whoever put it there and SHALL NOT be read, written, or removed by any pass — a person labelling a task `urgent` or `waiting-on-supplier` is doing something this projection has no opinion about.

Carrying the discipline as a tag does not reopen the task **name**, which SHALL continue to exclude it as the projection requirement specifies. That exclusion rests on name width — a single line a reader scans, where restating the discipline costs the wording the name exists to surface — and a tag spends none of it, while making the discipline filterable in a way a segment of the step identifier never was.

Before a tag can be set on a task it SHALL exist in the space the launch lists live in. The system SHALL ensure the full vocabulary — one tag per gate and one per discipline — exists in that space, and SHALL derive the space from the configured launch folder rather than requiring the space to be configured separately. Ensuring the vocabulary SHALL be repeatable without error: a tag that already exists is left as it is, including whatever colours a person has given it.

A task SHALL be created carrying both of its step's tags. On a later pass, the system SHALL add either tag to a mapped task that does not carry it, so that tasks projected before this requirement existed gain their tags rather than the behaviour reaching only launches started afterwards — the same obligation the assignee requirement already carries, and for the same reason: a projection that fixed only future work would leave every in-flight launch as it is.

The system SHALL NOT remove a tag from a task, and SHALL NOT replace one owned tag with another. Two consequences follow and are accepted rather than worked around:

- A step moved to a different gate keeps the gate tag it was projected with. Correcting it would require deciding whether a person's own retagging is preserved or overruled, which this requirement deliberately does not settle.
- A tag a person removes by hand stays removed only until the next pass, which adds it back, because the system retains nothing with which to tell "never added" from "added and then removed".

Tagging SHALL follow the projection it belongs to and never run ahead of it: a step the served playbook does not define is not tagged, a task belonging to a step that is not `active` is not tagged, and no tag is written while the passes have stood down — in each case for the reason that rule already gives, not a new one.

A tag that cannot be set SHALL NOT fail the pass or prevent the task from being created; the omission SHALL be reported as a warning-level application log record naming the step, the tag and the task. A task stating its work without its tags is a lesser fault than a launch whose work is not projected at all, and a failed run would hide the gap behind a retry.

#### Scenario: A newly projected task carries both tags

- **WHEN** a task is projected for an `active` `human` step whose gate is `listable` and whose discipline is `listing`
- **THEN** the created task carries the tags `gate:listable` and `discipline:listing`

#### Scenario: The tag vocabulary is ensured before tags are used

- **WHEN** a pass runs against a space whose tag vocabulary is incomplete
- **THEN** the missing gate and discipline tags are created in the space derived from the configured launch folder
- **AND** a tag that already exists is left exactly as it stands

#### Scenario: Ensuring the vocabulary twice is not an error

- **WHEN** a pass runs against a space that already holds the full vocabulary
- **THEN** no tag is recreated and the pass does not fail

#### Scenario: An existing untagged task gains its tags

- **WHEN** a pass runs over a mapped task that was projected before tagging existed
- **THEN** the task gains its step's `gate:` and `discipline:` tags

#### Scenario: A task already carrying its tags is left alone

- **WHEN** a pass runs over a mapped task already carrying both of its step's tags
- **THEN** no tag write is sent for that task

#### Scenario: A person's own tags are never touched

- **WHEN** a pass runs over a mapped task carrying tags outside the `gate:` and `discipline:` prefixes
- **THEN** those tags are left exactly as they stand

#### Scenario: A step moved between gates keeps its original gate tag

- **WHEN** a step whose task carries `gate:commit` is moved to the `listable` gate and a pass runs
- **THEN** the task carries `gate:listable` in addition to `gate:commit`, and no tag is removed

#### Scenario: A step that is not served is not tagged

- **WHEN** a pass runs and a mapped task's step is not defined by the served playbook, or is not `active`
- **THEN** no tag is written for that task

#### Scenario: No tag is written during a stand-down

- **WHEN** a pass stands down because the served playbook cannot hold a launch
- **THEN** no tag is created in the space and no tag is written to any task

#### Scenario: A tag that cannot be set is reported, not fatal

- **WHEN** a task is projected and one of its tags cannot be set
- **THEN** the task is still created and the pass still succeeds
- **AND** the omission is reported as a warning naming the step, the tag and the task
