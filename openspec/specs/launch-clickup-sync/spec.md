# launch-clickup-sync Specification

## Purpose
The launch-clickup-sync capability keeps a launch's human work and ClickUp in agreement in both directions: the system projects each launch's human-attested steps into a dedicated ClickUp list with due dates derived from the launch schedule, and completion recorded in ClickUp flows back as recorded step outcomes — through webhook deliveries when they arrive, and through a periodic reconciliation pass when they do not.

## Requirements

### Requirement: Each launch is projected into its own ClickUp list

The system SHALL maintain one ClickUp list per launch, created inside a configured parent folder and named with the product's name and SKU as the catalog records them (the product identifier itself is opaque and never parsed for meaning), and SHALL record the association between the launch and its list. A launch whose list already exists SHALL NOT get a second one. A launch that has reached its final gate (`graduated`) SHALL NOT be projected or reconciled. When the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped.

#### Scenario: A launch without a list gets one

- **WHEN** the reconciliation pass runs and an active launch has no recorded ClickUp list
- **THEN** a list is created in the configured folder, named with the product's catalog name and SKU
- **AND** the association between the launch and the created list is recorded

#### Scenario: An existing list is not recreated

- **WHEN** the reconciliation pass runs and the launch already has a recorded list
- **THEN** no new list is created

#### Scenario: A graduated launch is left alone

- **WHEN** the reconciliation pass runs and a launch has reached `graduated`
- **THEN** no list or task is created or updated for it and no outcome is recorded from it

#### Scenario: Missing folder configuration fails the run

- **WHEN** the reconciliation pass runs, an active launch needs a list, and no parent folder is configured
- **THEN** the pass reports failure rather than skipping the launch silently

### Requirement: Human-attested steps are projected as tasks
The system SHALL project, into the launch's list, one ClickUp task per step of the launch's pinned playbook version whose execution mode is `human-attested` and whose hazard is not `prohibited-tactic`, and SHALL record the association between each step and its task. Steps with `automated` or `ai-assisted` execution, steps with the `prohibited-tactic` hazard, and gate metric conditions SHALL NOT be projected. A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's description, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a description happens to say — a description whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A task's name SHALL be set when the task is created and SHALL NOT be rewritten afterwards, even when the step's description changes in a later playbook version. This is deliberately unlike the task's due date, which is a derived value the system keeps in step with the launch schedule: a name is something a person may legitimately edit, and a pass that restored the authored name would silently discard their edit.

Where the composed name would exceed the length the task system accepts, the name SHALL be shortened to fit and the step's full description SHALL be carried in the created task's body, so that no step fails to project merely because its description is long. The shortened name SHALL consist of the step's description cut at its end, then `…` marking that it was cut, then ` · ` and the step's identifier in full: shortening SHALL preserve the identifier, since that is what makes the task traceable, and SHALL be visible as shortening rather than reading as the whole description. The description SHALL be cut to the longest leading portion that leaves the whole composed name within the limit, so that shortening surrenders no more of the wording than the limit requires.

A task whose composed name is within the limit SHALL be created without a body: the body carries the description only where the name could not.

#### Scenario: A human-attested step gets a task

- **WHEN** the reconciliation pass runs and a `human-attested` step of an active launch has no recorded task
- **THEN** a task named with the step's description, then ` · `, then its identifier is created in the launch's list
- **AND** the step's discipline is not appended as a further element of that name
- **AND** the association between the step and the created task is recorded

#### Scenario: A renamed task still resolves to its step

- **WHEN** a mapped task's name has been edited in ClickUp and the reconciliation pass runs
- **THEN** the task still resolves to the step it is mapped to
- **AND** no second task is created for that step

#### Scenario: An edited task name is never restored

- **WHEN** a mapped task's name has been edited in ClickUp, the step's description has since changed, and the reconciliation pass runs
- **THEN** the task keeps the name it has in ClickUp
- **AND** no update is sent for that task's name

#### Scenario: An over-long name is shortened rather than failing

- **WHEN** a task is projected for a step whose composed name exceeds the length the task system accepts
- **THEN** the task is created with a shortened name that fits, ending in `… · ` followed by the step's identifier in full
- **AND** no more of the description is surrendered than the limit requires
- **AND** the step's full description is carried in the created task's body

#### Scenario: An existing task is not recreated

- **WHEN** the reconciliation pass runs and a step already has a recorded task
- **THEN** no new task is created for that step

#### Scenario: A prohibited-tactic step is never projected

- **WHEN** the reconciliation pass runs and a step carries the `prohibited-tactic` hazard
- **THEN** no task is created for it, whatever its execution mode

#### Scenario: A deleted task for unfinished work is re-projected

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is not terminal
- **THEN** a new task is created for the step and the mapping is replaced with the new task

#### Scenario: A deleted task for finished work stays gone

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is terminal
- **THEN** no task is recreated for that step

#### Scenario: Automated and ai-assisted steps are never projected

- **WHEN** the reconciliation pass runs and a step's execution mode is `automated` or `ai-assisted`
- **THEN** no task is created for it

### Requirement: Task due dates derive from the launch schedule

The system SHALL set each projected task's due date to the end of the step's due period, as resolved from the launch date and the step's timing anchor, and SHALL update a task whose due date in ClickUp no longer matches the resolved value — so a moved launch date cascades into every already-created task. A step whose due period cannot be resolved (no launch date set) or has no end (an open-ended or recurring anchor) SHALL leave the task without a due date.

#### Scenario: Tasks carry due dates resolved from the launch date

- **WHEN** a task is projected for a step with a bounded due period and the launch has a launch date
- **THEN** the task's due date is the resolved due period's end

#### Scenario: A moved launch date updates existing tasks

- **WHEN** the launch date has moved since a step's task was created and the reconciliation pass runs
- **THEN** that task's due date is updated to the newly resolved due period's end

#### Scenario: An unresolvable due period means no due date

- **WHEN** a task is projected for a step of a launch with no launch date, or for a step whose anchor is open-ended or recurring
- **THEN** the task carries no due date

### Requirement: Completion flows from ClickUp to the launch as a recorded outcome

The system SHALL record, against the mapped step, a `Satisfied` outcome when its ClickUp task reaches a status of the closed type, and an `InProgress` outcome when a previously closed task is reopened — in both cases with provenance naming `clickup` as the source, the ClickUp actor where the delivery identifies one, and the task as evidence. "Previously closed" means last observed closed, per the retained observed state the reconciliation requirement defines — a reopening whose closing was never observed records nothing. A newly projected task's retained observed state starts as not closed. No other outcome SHALL be produced from ClickUp state. The system SHALL NOT write task status to ClickUp: completion travels one way, from ClickUp to the launch.

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

### Requirement: Webhook deliveries are verified before anything is recorded

The system SHALL expose an endpoint for ClickUp webhook deliveries and SHALL verify each delivery's signature against a configured secret before acting on it. A delivery with a missing or invalid signature, or arriving while no secret is configured, SHALL be rejected without recording anything. A verified delivery concerning a task with no recorded mapping, a task mapped to a launch that has reached `graduated`, or an event other than a task status change, SHALL be acknowledged without recording anything.

#### Scenario: A validly signed delivery is processed

- **WHEN** a delivery arrives whose signature matches the configured secret
- **THEN** it is acknowledged and its status change is processed against the mapping

#### Scenario: An invalid signature is rejected

- **WHEN** a delivery arrives whose signature does not match the configured secret, or carries no signature
- **THEN** it is rejected and no outcome is recorded

#### Scenario: No configured secret rejects all deliveries

- **WHEN** a delivery arrives while no webhook secret is configured
- **THEN** it is rejected and no outcome is recorded

#### Scenario: An unmapped task is acknowledged and ignored

- **WHEN** a verified delivery concerns a task no mapping records
- **THEN** it is acknowledged and no outcome is recorded

#### Scenario: A graduated launch's task is acknowledged and ignored

- **WHEN** a verified delivery concerns a task mapped to a launch that has reached `graduated`
- **THEN** it is acknowledged and no outcome is recorded

### Requirement: The reconciliation pass records completions and reopenings the webhook missed

The system SHALL periodically, on a declared schedule and without any request from outside the deployment, read the ClickUp state of every active launch's mapped tasks and record any completion or reopening whose webhook delivery was missed, with the same outcome mapping, source, and evidence as webhook intake; the recorder is the reconciliation's own identity, since a read exposes no acting user. A missed completion or reopening SHALL be detected as a transition of the task's observed closed state: the system SHALL retain, per mapped task, the closed state it last observed — updated by every observation, webhook and reconciliation alike — and SHALL record an outcome only when the state read from ClickUp differs from that retained state. A task showing no transition SHALL NOT cause any recording, whatever outcome the step carries.

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
