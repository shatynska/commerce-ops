## MODIFIED Requirements

### Requirement: Human-attested steps are projected as tasks
The system SHALL project, into the launch's list, one ClickUp task per step of the served playbook whose execution mode is `human-attested` and whose hazard is not `prohibited-tactic`, and SHALL record the association between each step and its task. The served playbook is live, so a step authored after the launch started is projected on the next pass like any other. Steps with `automated` or `ai-assisted` execution, steps with the `prohibited-tactic` hazard, and gate metric conditions SHALL NOT be projected. A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's description, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a description happens to say — a description whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A task's name and body SHALL be set when the task is created, and the system SHALL retain, with the mapping, the name and the body it last composed for the task. On a later pass, when the step's current composition differs from what is retained, the system SHALL rewrite each of the task's name and its body to the current composition **only while that field in ClickUp still carries exactly what the system last wrote for it** — a field still carrying the system's own words follows the step's current wording, so an authored edit to a description reaches the tasks it describes. A field that differs from its retained value has been edited by a person and SHALL NOT be rewritten by any pass, ever: a task's name, and a note a person keeps in its body, are things a person may legitimately edit, and a pass that restored the authored wording would silently discard their edit. The two fields are guarded independently — a person's body note does not freeze the name, nor a renamed task its body. Whenever the system writes a name or a body, it SHALL update that field's retained value to what it wrote.

A mapping created before compositions were retained holds no retained values. On first observing such a task, the system SHALL adopt a field's current content as its retained value when it is exactly what the system would currently compose — an unedited legacy task starts healing — and SHALL otherwise leave the retained value absent and the field forever unrewritten, treating it as person-edited: where the system cannot tell an authored change from a person's edit, it preserves the person's.

Where the composed name would exceed the length the task system accepts, the name SHALL be shortened to fit and the step's full description SHALL be carried in the task's body, so that no step fails to project merely because its description is long. The shortened name SHALL consist of the step's description cut at its end, then `…` marking that it was cut, then ` · ` and the step's identifier in full: shortening SHALL preserve the identifier, since that is what makes the task traceable, and SHALL be visible as shortening rather than reading as the whole description. The description SHALL be cut to the longest leading portion that leaves the whole composed name within the limit, so that shortening surrenders no more of the wording than the limit requires.

A task whose composed name is within the limit SHALL be created without a body: the body carries the description only where the name could not.

#### Scenario: A human-attested step gets a task

- **WHEN** the reconciliation pass runs and a `human-attested` step of an active launch has no recorded task
- **THEN** a task named with the step's description, then ` · `, then its identifier is created in the launch's list
- **AND** the step's discipline is not appended as a further element of that name
- **AND** the association between the step and the created task is recorded

#### Scenario: A step authored mid-launch is projected

- **WHEN** a `human-attested` step is added to the playbook after a launch started and the next pass runs
- **THEN** a task is created for it in the launch's list like any other step's

#### Scenario: A renamed task still resolves to its step

- **WHEN** a mapped task's name has been edited in ClickUp and the reconciliation pass runs
- **THEN** the task still resolves to the step it is mapped to
- **AND** no second task is created for that step

#### Scenario: An unedited task follows the step's current wording

- **WHEN** a step's description has been edited, the mapped task's name in ClickUp is still exactly the composition the system last wrote, and the pass runs
- **THEN** the task's name is rewritten to the step's current composition
- **AND** the retained composition is updated to what was written

#### Scenario: A person's body note survives a wording edit

- **WHEN** a person has edited a mapped task's body, the task's name still carries the system's retained composition, the step's description is edited, and the pass runs
- **THEN** the task's name is rewritten to the current composition
- **AND** the task's body is left exactly as the person wrote it

#### Scenario: An unedited legacy task starts healing

- **WHEN** a mapped task predating retained compositions is observed carrying exactly the name the system would currently compose
- **THEN** that name is adopted as the retained composition, and the task heals under the rules above thereafter

#### Scenario: An ambiguous legacy task is never rewritten

- **WHEN** a mapped task predating retained compositions is observed carrying a name that differs from the current composition
- **THEN** no retained composition is adopted and no pass ever rewrites that task's name

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

### Requirement: Completion flows from ClickUp to the launch as a recorded outcome

The system SHALL record, against the mapped step, a `Satisfied` outcome when its ClickUp task reaches a status of the closed type, and an `InProgress` outcome when a previously closed task is reopened — in both cases with provenance naming `clickup` as the source, the ClickUp actor where the delivery identifies one, and the task as evidence. "Previously closed" means last observed closed, per the retained observed state the reconciliation requirement defines — a reopening whose closing was never observed records nothing. A newly projected task's retained observed state starts as not closed. These recordings apply only to a step the served playbook defines: a retired step's mapped task records nothing, as the retired-step requirement below specifies. No other outcome SHALL be produced from ClickUp state. The system SHALL NOT write task status to ClickUp: completion travels one way, from ClickUp to the launch.

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

The system SHALL periodically, on a declared schedule and without any request from outside the deployment, read the ClickUp state of every active launch's mapped tasks and record any completion or reopening whose webhook delivery was missed, with the same outcome mapping, source, and evidence as webhook intake; the recorder is the reconciliation's own identity, since a read exposes no acting user. A missed completion or reopening SHALL be detected as a transition of the task's observed closed state: the system SHALL retain, per mapped task, the closed state it last observed — updated by every observation, webhook and reconciliation alike — and SHALL record an outcome only when the state read from ClickUp differs from that retained state. Recording applies only to steps the served playbook defines: a retired step's mapped task is still observed — its retained state updated — but records nothing, as the retired-step requirement below specifies. A task showing no transition SHALL NOT cause any recording, whatever outcome the step carries.

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

## ADDED Requirements

### Requirement: A retired step leaves the loop

A retired step SHALL leave the completion loop in both directions while its mapping and task are left standing. Outward: a retired step is absent from the served playbook, so no pass SHALL create, re-create, or update a task for it — its existing task is neither renamed, re-dated, closed, nor deleted; what a person does with the leftover task is their call, and closing it on their behalf would fabricate a completion. Inward: a state change on a retired step's mapped task SHALL NOT be recorded as an outcome — not by the reconciliation pass and not by a webhook delivery — because the step the recording would name is no longer part of the launch's obligations. Observations of the task SHALL nonetheless keep updating its retained observed state, recording nothing, so that what happened during retirement is never replayed as a transition later: a closure that occurred while the step was retired is not recorded, not even after un-retirement. An un-retired step SHALL rejoin the loop on the next pass, resuming through its existing mapping and task where they still stand, and recording only transitions observed after the un-retirement.

#### Scenario: A retired step's task is left unmanaged

- **WHEN** a step with a mapped, unfinished task is retired and the next pass runs
- **THEN** no create, rename, due-date update, close, or delete is sent for that task

#### Scenario: A retired step's closure is not recorded

- **WHEN** a retired step's mapped task changes state in ClickUp, and that change reaches the system by webhook or by the reconciliation pass
- **THEN** no outcome is recorded for the step

#### Scenario: A closure during retirement is never replayed

- **WHEN** a retired step's mapped task is closed while the step is retired, and the step is later un-retired with the task still closed
- **THEN** no outcome is recorded for that closure — before or after the un-retirement
- **AND** a reopening observed after the un-retirement records `InProgress`, per the completion requirement

#### Scenario: An un-retired step resumes through its existing task

- **WHEN** a retired step whose mapped task still exists is un-retired and the next pass runs
- **THEN** the existing mapping and task are reused — no second task is created — and the loop resumes for the step
