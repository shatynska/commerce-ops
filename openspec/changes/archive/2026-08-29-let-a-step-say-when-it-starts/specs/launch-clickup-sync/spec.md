## MODIFIED Requirements

### Requirement: Human steps are projected as tasks carrying their name, description and assignees

The system SHALL project, into the launch's list, one ClickUp task per step of the served playbook whose kind is `human`, whose status is `active`, whose hazard is not `prohibited-tactic`, and **which the launch has released** (`launch-playbook`, *A step declares when it may start*), and SHALL record the association between each step and its task. The served playbook is live, so a step activated after the launch started is projected on the next pass like any other, and so is a step the launch releases after it started. `automated` steps, steps that are not `active`, steps with the `prohibited-tactic` hazard, steps the launch has not yet released, and gate metric conditions SHALL NOT be projected.

Release is what stops a launch's list opening with the whole playbook in it on its first pass. A step the launch has not released is not yet work anybody is being asked for, and a task for it would carry a due date the launch cannot honour and accrue overdue marks against work nobody was permitted to start.

A task already created for a step SHALL NOT be withdrawn because that step is no longer released. A step can stop being released two ways — an authoring change to what it waits for, and a dependency's own outcome regressing when its task is reopened, which this capability records as `InProgress` — and neither is a reason to take away a task a person may already have begun. Release governs what is created, never what is taken away.

A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's **name**, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a step's name happens to say — a name whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A projected task's body SHALL be the step's **description** where the step carries one. Where a step carries no description the system SHALL compose no body at all, and SHALL neither write nor rewrite the task's body — leaving whatever stands there. Composing an *empty* body instead would destroy work: a task projected before this change whose name was shortened carries the step's full former text in its body, written by the system and therefore matching its retained value, so a rule that rewrote it to empty would leave that task stating its work nowhere. The body is no longer a place the name overflows into: the step's own two fields map onto the task's two, which is what having them separate is for.

A projected task SHALL be assigned to the step's assignees, each resolved to the ClickUp user the roster records for that person. Assignment SHALL be reconciled on later passes as well as at creation, so that a step whose assignees change reaches its task, and so that tasks projected before steps had assignees stop being unowned — which is the problem this field exists to solve, and solving it only for new work would leave every in-flight launch as it is. The system SHALL retain, with the mapping, the assignees it last set, exactly as it retains the name and the body it last composed. A person's own assignment change SHALL be respected the way an edited name or body is: where a task's assignees differ from what the system last set, the system SHALL NOT overwrite them. A mapping holding no retained assignees — every mapping made before this change — SHALL be treated as having last been set to nobody, so a task the system left unassigned heals to its step's assignees while one somebody has already assigned is treated as person-edited and left alone. Assignees are the one *retained* field where that reading is right: an unassigned task is the failure this projection exists to fix, so silence there is the system's own doing rather than an edit worth preserving. The Custom Field rule does not qualify it, and for the opposite reason: a Custom Field is single-valued and wholly determined by the step, so a value differing from the step's is drift rather than a person's own meaning and is corrected (see *A projected task carries its step's gate and discipline as Custom Field values*). An assignee the roster carries without a ClickUp user id SHALL be skipped for assignment — the task is still created, still carries its remaining assignees, and the omission SHALL be reported as a warning-level application log record naming the step, the person and the task rather than silently dropped — the pass itself succeeds, since a failed run would hide a data gap behind a retry, and `scheduled-jobs` records only whether a run succeeded, so the run record is not where this can be carried.

A task's name and body SHALL be set when the task is created, and the system SHALL retain, with the mapping, the name and the body it last composed for the task. On a later pass, when the step's current composition differs from what is retained, the system SHALL rewrite each of the task's name and its body to the current composition **only while that field in ClickUp still carries exactly what the system last wrote for it** — a field still carrying the system's own words follows the step's current wording, so an authored edit reaches the tasks it describes. A field that differs from its retained value has been edited by a person and SHALL NOT be rewritten by any pass, ever: a task's name, and a note a person keeps in its body, are things a person may legitimately edit, and a pass that restored the authored wording would silently discard their edit. The two fields are guarded independently — a person's body note does not freeze the name, nor a renamed task its body. Whenever the system writes a name or a body, it SHALL update that field's retained value to what it wrote.

A mapping created before compositions were retained holds no retained values. On first observing such a task, the system SHALL adopt a field's current content as its retained value when it is exactly what the system would currently compose — an unedited legacy task starts healing — and SHALL otherwise leave the retained value absent and the field forever unrewritten, treating it as person-edited: where the system cannot tell an authored change from a person's edit, it preserves the person's.

Where the composed name would exceed the length the task system accepts, the name SHALL be shortened to fit, so that no step fails to project merely because its name is long. The shortened name SHALL consist of the step's name cut at its end, then `…` marking that it was cut, then ` · ` and the step's identifier in full: shortening SHALL preserve the identifier, since that is what makes the task traceable, and SHALL be visible as shortening rather than reading as the whole name. The name SHALL be cut to the longest leading portion that leaves the whole composed name within the limit, so that shortening surrenders no more of the wording than the limit requires. Shortening SHALL NOT move the surrendered text into the body: the body belongs to the description, and overwriting it with a fragment of the name would displace what an author wrote.

#### Scenario: A human step gets a task

- **WHEN** the reconciliation pass runs and an `active` `human` step of an active launch has no recorded task
- **THEN** a task named with the step's name, then ` · `, then its identifier is created in the launch's list
- **AND** the step's discipline is not appended as a further element of that name
- **AND** the association between the step and the created task is recorded

#### Scenario: A step's description becomes the task's body

- **WHEN** a task is projected for a step carrying a description
- **THEN** the task's body is that description
- **AND** a step carrying no description is projected with no body written at all, leaving whatever the task already holds

#### Scenario: A task is assigned to the step's people

- **WHEN** a task is projected for a step naming two assignees the roster records ClickUp user ids for
- **THEN** the created task is assigned to both of those ClickUp users

#### Scenario: An existing unowned task gains its step's assignees

- **WHEN** a pass runs over a task the system assigned to nobody and whose step now names an assignee
- **THEN** the task is assigned to that person

#### Scenario: A person's own assignment change is not overwritten

- **WHEN** a task's assignees have been changed in ClickUp from what the system last set, and a pass runs
- **THEN** the system leaves the task's assignees as they stand

#### Scenario: An assignee with no ClickUp account is reported, not silently dropped

- **WHEN** a task is projected for a step naming an assignee the roster carries without a ClickUp user id
- **THEN** the task is created and assigned to the step's remaining assignees, and the omission is reported

#### Scenario: A step activated mid-launch is projected

- **WHEN** a `human` step is activated after a launch started, the launch has released it, and the next pass runs
- **THEN** a task is created for it in the launch's list like any other step's

#### Scenario: A step activated mid-launch that the launch has not released is not projected

- **WHEN** a `human` step whose start gate the launch has not reached is activated after that launch started, and the next pass runs
- **THEN** no task is created for it

#### Scenario: A renamed task still resolves to its step

- **WHEN** a mapped task's name has been edited in ClickUp and the reconciliation pass runs
- **THEN** the task still resolves to its step through the recorded mapping

#### Scenario: An unedited task follows the step's current wording

- **WHEN** a step's name has been edited, the mapped task's name in ClickUp is still exactly the composition the system last wrote, and the pass runs
- **THEN** the task's name is rewritten to the step's current composition
- **AND** the retained composition is updated to what was written

#### Scenario: A person's body note survives a wording edit

- **WHEN** a person has edited a mapped task's body, the task's name still carries the system's retained composition, the step's name is edited, and the pass runs
- **THEN** the task's name is rewritten to the current composition
- **AND** the task's body is left exactly as the person wrote it

#### Scenario: An unedited legacy task starts healing

- **WHEN** a mapped task predating retained compositions is observed carrying exactly the name the system would currently compose
- **THEN** that name is adopted as the retained composition, and the task heals under the rules above thereafter

#### Scenario: An ambiguous legacy task is never rewritten

- **WHEN** a mapped task predating retained compositions is observed carrying a name that differs from the current composition
- **THEN** no retained composition is adopted and no pass ever rewrites that task's name

#### Scenario: An edited task name is never restored

- **WHEN** a mapped task's name has been edited in ClickUp, the step's name has since changed, and the reconciliation pass runs
- **THEN** the task keeps the name it has in ClickUp
- **AND** no update is sent for that task's name

#### Scenario: An over-long name is shortened rather than failing

- **WHEN** a task is projected for a step whose composed name exceeds the length the task system accepts
- **THEN** the task is created with a shortened name that fits, ending in `… · ` followed by the step's identifier in full
- **AND** no more of the name is surrendered than the limit requires
- **AND** the surrendered text is not written into the body

#### Scenario: An existing task is not recreated

- **WHEN** the reconciliation pass runs and a step already has a recorded task
- **THEN** no new task is created for that step

#### Scenario: A prohibited-tactic step is never projected

- **WHEN** the reconciliation pass runs and a step carries the `prohibited-tactic` hazard
- **THEN** no task is created for it, whatever its kind

#### Scenario: A deleted task for unfinished work is re-projected

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is not terminal
- **THEN** a new task is created for the step and the mapping is replaced with the new task

#### Scenario: A deleted task for finished work stays gone

- **WHEN** the reconciliation pass runs and a mapped task no longer exists in the launch's list while the step's recorded outcome is terminal
- **THEN** no task is recreated for that step

#### Scenario: Automated steps are never projected

- **WHEN** the reconciliation pass runs and a step's kind is `automated`
- **THEN** no task is created for it, whether or not it needs confirmation

#### Scenario: A step that is not active is never projected

- **WHEN** the reconciliation pass runs and a `human` step's status is `draft`, `in-development` or `retired`
- **THEN** no task is created for it


#### Scenario: An unreleased step is not projected

- **WHEN** the reconciliation pass runs over a launch standing at `commit` and the served playbook carries an `active` `human` step whose start gate is `listable`
- **THEN** no task is created for it, and no mapping is recorded

#### Scenario: A step is projected on the pass after the launch releases it

- **WHEN** a launch that stood at `commit` advances to `listable`, and the next reconciliation pass runs
- **THEN** a task is created for each `listable`-gate step the launch has now released

#### Scenario: A step waiting on another is not projected until that one is resolved

- **WHEN** the reconciliation pass runs over a launch that has reached a step's start gate, and that step names an `after_steps` dependency whose outcome is not yet resolved
- **THEN** no task is created for it

#### Scenario: A step released by its dependency being retired is projected

- **WHEN** a step's only `after_steps` dependency is retired, and the reconciliation pass runs over a launch that has reached that step's start gate
- **THEN** a task is created for it, the retired dependency being satisfied vacuously

#### Scenario: A task already created is not withdrawn

- **WHEN** a step's task exists and the step is subsequently authored to start at a gate the launch has not reached
- **THEN** the task is left standing in ClickUp, and its mapping is left recorded

### Requirement: A step that is not active leaves the loop

A step the loop no longer projects SHALL leave the completion loop in both directions while its mapping and task are left standing. The rule keys on the departure itself rather than on any one field, because projection turns on three of them — kind, status and hazard — and a rule naming fewer would leave the rest undefined. A step is no longer `active`, whether it became `retired` or moved back to `draft` or `in-development`; or its kind is no longer `human`, because an `automated` step resolves through `launch-step-automation` and never through a person ticking a task; or its hazard became `prohibited-tactic`, which the projection requirement already excludes.

Outward: such a step is absent from what the pass projects, so no pass SHALL create, re-create, or update a task for it — its existing task is neither renamed, re-dated, closed, nor deleted; what a person does with the leftover task is their call, and closing it on their behalf would fabricate a completion. Inward: a state change on its mapped task SHALL NOT be recorded as an outcome — not by the reconciliation pass and not by a webhook delivery — because the step the recording would name is no longer part of the launch's obligations in the form the task represents. Observations of the task SHALL nonetheless keep updating its retained observed state, recording nothing, so that what happened while the step was out of the projection is never replayed as a transition later: a closure that occurred then is not recorded, not even after the step returns to the projection. A step returning to `active` `human` work SHALL rejoin the loop on the next pass, resuming through its existing mapping and task where they still stand, and recording only transitions observed after it returned.

**Release is not one of these fields, and a step the launch has not released SHALL NOT be held to have left the loop.** Departure keys on the step ceasing to be work of the kind the projection represents — it is no longer a person's task, or no longer served at all — which is a fact about the *step*. Release is a fact about one *launch's position* against a step that is still `active`, still `human` and still the launch's obligation; the launch has simply not asked for it yet. The three departure fields say the task no longer stands for anything; release says only that the task does not exist yet.

The distinction has a consequence this requirement must state, because it is the case a reader will hit: where a task stands for a step the launch has since stopped releasing — reachable only by an authoring change, since the projection never withdraws a task — a state change on that task **SHALL** still be recorded as an outcome. Work a person completed on a task they were given is work done, and release governs what the system asks for, never what it accepts.

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

#### Scenario: An unreleased step has not left the loop

- **WHEN** a task stands for a step that is `active` and `human` but that its launch has since stopped releasing, and that task is closed in ClickUp
- **THEN** the outcome is recorded for the step, exactly as it would be for a released one

#### Scenario: Release does not suppress reconciliation

- **WHEN** the reconciliation pass observes a state change on a task whose step the launch has not released
- **THEN** the change is recorded, no rule of this requirement applying to it

