# launch-clickup-sync delta — describe-playbook-steps

## MODIFIED Requirements

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
