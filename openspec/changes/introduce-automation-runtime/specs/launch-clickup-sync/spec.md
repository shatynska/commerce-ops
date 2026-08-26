## MODIFIED Requirements

### Requirement: A step that is not active leaves the loop

A step the loop no longer projects SHALL leave the completion loop in both directions while its mapping and task are left standing. The rule keys on the departure itself rather than on any one field, because projection turns on three of them — kind, status and hazard — and a rule naming fewer would leave the rest undefined. A step is no longer `active`, whether it became `retired` or moved back to `draft` or `in-development`; or its kind is no longer `human`, because an `automated` step resolves through `launch-step-automation` and never through a person ticking a task; or its hazard became `prohibited-tactic`, which the projection requirement already excludes.

Outward: such a step is absent from what the pass projects, so no pass SHALL create, re-create, or update a task for it — its existing task is neither renamed, re-dated, closed, nor deleted; what a person does with the leftover task is their call, and closing it on their behalf would fabricate a completion. Inward: a state change on its mapped task SHALL NOT be recorded as an outcome — not by the reconciliation pass and not by a webhook delivery — because the step the recording would name is no longer part of the launch's obligations in the form the task represents. Observations of the task SHALL nonetheless keep updating its retained observed state, recording nothing, so that what happened while the step was out of the projection is never replayed as a transition later: a closure that occurred then is not recorded, not even after the step returns to the projection. A step returning to `active` `human` work SHALL rejoin the loop on the next pass, resuming through its existing mapping and task where they still stand, and recording only transitions observed after it returned.

Retirement is the named instance of this rather than the rule itself: a rule that keyed on retirement alone — or on status alone — would leave the others undefined, which is the argument this requirement was already written on. The kind case is the one this rule most needs to state, because a step that becomes `automated` stays `active`: it is still part of the launch's obligations, so nothing about its status signals its departure from the loop, and a person closing its orphaned task would otherwise record a `clickup`-sourced completion for work a handler was about to do.

#### Scenario: A retired step's task is left unmanaged

- **WHEN** a step with a mapped, unfinished task is retired and the next pass runs
- **THEN** no create, rename, due-date update, close, or delete is sent for that task

#### Scenario: A retired step's closure is not recorded

- **WHEN** a retired step's mapped task changes state in ClickUp, and that change reaches the system by webhook or by the reconciliation pass
- **THEN** no outcome is recorded for the step

#### Scenario: A closure during retirement is never replayed

- **WHEN** a retired step's mapped task is closed while the step is retired, and the step is later un-retired and activated with the task still closed
- **THEN** no outcome is recorded for that closure — before or after the return to `active`
- **AND** a reopening observed after it returned records `InProgress`, per the completion requirement

#### Scenario: An un-retired step resumes through its existing task

- **WHEN** a retired step whose mapped task still exists is un-retired, activated, and the next pass runs
- **THEN** the existing mapping and task are reused — no second task is created — and the loop resumes for the step

#### Scenario: A de-activated step leaves the loop exactly as a retired one does

- **WHEN** an `active` step with a mapped task is moved to `in-development` and the next pass runs
- **THEN** no update is sent for its task and no state change on it is recorded

#### Scenario: A step that becomes automated leaves the loop while staying active

- **WHEN** an `active` `human` step with a mapped task is changed to kind `automated`, remains `active`, and the next pass runs
- **THEN** no update is sent for its task and no state change on it is recorded

#### Scenario: Closing the orphaned task of an automated step records nothing

- **WHEN** the mapped task of an `active` `automated` step is closed in ClickUp, and that closure reaches the system by webhook or by the reconciliation pass
- **THEN** no outcome is recorded for that step, and its retained observed state is updated so the closure is never replayed

### Requirement: Completion flows from ClickUp to the launch as a recorded outcome

The system SHALL record, against the mapped step, a `Satisfied` outcome when its ClickUp task reaches a status of the closed type, and an `InProgress` outcome when a previously closed task is reopened — in both cases with provenance naming `clickup` as the source, the ClickUp actor where the delivery identifies one, and the task as evidence. "Previously closed" means last observed closed, per the retained observed state the reconciliation requirement defines — a reopening whose closing was never observed records nothing. A newly projected task's retained observed state starts as not closed. These recordings apply only to a step the loop still projects: the mapped task of a step that has left the projection records nothing, as the leaves-the-loop requirement below specifies. No other outcome SHALL be produced from ClickUp state. The system SHALL NOT write task status to ClickUp: completion travels one way, from ClickUp to the launch.

#### Scenario: A closed task records Satisfied

- **WHEN** a mapped task's status change to a closed status is received
- **THEN** a `Satisfied` outcome is recorded for the mapped step with provenance source `clickup` and the task as evidence

#### Scenario: A reopened task records InProgress

- **WHEN** a status change to an open status is received for a mapped task whose retained observed state is closed
- **THEN** an `InProgress` outcome is recorded for the mapped step with provenance source `clickup`

#### Scenario: A reopening without an observed closing records nothing

- **WHEN** a status change to an open status is received for a mapped task that was never observed closed
- **THEN** no outcome is recorded for the mapped step

#### Scenario: A repeated delivery changes nothing

- **WHEN** the same status change for a mapped task is received more than once
- **THEN** the step's recorded outcome after the repeat is the same as after the first delivery
- **AND** the repeat is not an error

#### Scenario: The system never closes a task

- **WHEN** a mapped step's outcome is recorded through any non-ClickUp path
- **THEN** the step's ClickUp task keeps whatever status it has — the system does not write task status

### Requirement: The reconciliation pass records completions and reopenings the webhook missed

The system SHALL periodically, on a declared schedule and without any request from outside the deployment, read the ClickUp state of every active launch's mapped tasks and record any completion or reopening whose webhook delivery was missed, with the same outcome mapping, source, and evidence as webhook intake; the recorder is the reconciliation's own identity, since a read exposes no acting user. A missed completion or reopening SHALL be detected as a transition of the task's observed closed state: the system SHALL retain, per mapped task, the closed state it last observed — updated by every observation, webhook and reconciliation alike — and SHALL record an outcome only when the state read from ClickUp differs from that retained state. Recording applies only to steps the loop still projects: the mapped task of a step that has left the projection is still observed — its retained state updated — but records nothing, as the leaves-the-loop requirement below specifies. A task showing no transition SHALL NOT cause any recording, whatever outcome the step carries.

#### Scenario: A missed completion is recorded on reconciliation

- **WHEN** the reconciliation pass reads a mapped task as closed and its last observed state is not closed
- **THEN** a `Satisfied` outcome is recorded for the mapped step with provenance source `clickup` and the reconciliation's own identity as recorder
- **AND** the task's retained observed state becomes closed

#### Scenario: A missed reopening is recorded on reconciliation

- **WHEN** the reconciliation pass reads a mapped task as open and its last observed state is closed
- **THEN** an `InProgress` outcome is recorded for the mapped step with provenance source `clickup`
- **AND** the task's retained observed state becomes open

#### Scenario: No transition means no recording

- **WHEN** the reconciliation pass reads a mapped task whose state matches its last observed state
- **THEN** no outcome is recorded for that step

#### Scenario: Reconciliation never overwrites other recording paths

- **WHEN** a step's outcome was recorded through a non-ClickUp path and the step's mapped task has never been observed closed
- **THEN** the reconciliation pass records nothing for that step, leaving the recorded outcome standing
