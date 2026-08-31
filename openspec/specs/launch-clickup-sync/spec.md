# launch-clickup-sync Specification

## Purpose
The launch-clickup-sync capability keeps a launch's human work and ClickUp in agreement in both directions: the system projects each launch's active `human` steps into a dedicated ClickUp list — each task carrying the step's name, its description and the people responsible for it, with a due date derived from the launch schedule and Custom Field values naming the gate it belongs to and the discipline that owns it, so that a launch list can be ordered by the sequence the playbook is built on — and completion recorded in ClickUp flows back as recorded step outcomes, through webhook deliveries when they arrive and through a periodic reconciliation pass when they do not.

## Requirements

### Requirement: Each launch is projected into its own ClickUp list

The system SHALL maintain one ClickUp list per launch, created inside a configured parent folder and named with the product's name and SKU as the catalog records them (the product identifier itself is opaque and never parsed for meaning), and SHALL record the association between the launch and its list. A launch that has reached its final gate (`graduated`) SHALL NOT be projected or reconciled. When the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped.

Before a launch's projection uses a recorded list, once per pass, the system SHALL establish from ClickUp that the list still exists. A launch whose recorded list still exists SHALL NOT get a second one.

A launch whose recorded list has been deleted in ClickUp SHALL be given a new one, and its task mappings SHALL be discarded together with the recorded list they belonged to, as one indivisible act: either the launch is left recorded against its old list with its mappings intact, or it is recorded against the new list with the discard applied. The indivisibility is of the *record*; a replacement list created in ClickUp before the record is written may be left with nothing naming it, and reclaiming such a list is not undertaken here. A task mapping names a task inside a particular list, so a mapping outliving that list records something the system knows to be untrue.

**A mapping SHALL be exempt from that discard, and SHALL stand, where the playbook still defines its step and that step's recorded outcome is one that settles work** — `Satisfied`, `NotApplicable` or `Refused` — whether or not the step is one the launch is currently held to. Whether the outcome settles work SHALL be judged without reference to the step's current hazard: an outcome that settled the work when it was recorded is not unsettled by the step being re-authored afterwards, and the work does not become unfinished because the rules for finishing it changed. Such a mapping is not a stale record but a working one: it is what tells the projection that the step's work is finished, so that discarding it would re-project completed work as a fresh open task in the replacement list. The exemption reaches steps the launch is not currently held to because a step can leave the served set and return to it; its finished work must survive the round trip. A mapping whose step the playbook no longer defines at all SHALL be discarded with the rest, since nothing can re-project a step that is not defined. No sanctioned operation produces that state — a step is retired, never deleted, and a retired step is still defined — so this clause is defensive, covering mappings older than the playbook's move into Postgres and any left by an unsanctioned edit.

This exemption is stated in terms of the launch's own state — whether the playbook defines the step, and whether its work is finished — and not in terms of how the projection loop reaches it.

Replacing a list is the one thing that removes the mapping of a step the launch is no longer held to. A departed step whose work is unsettled loses its mapping here, notwithstanding the general rule that such a step leaves the completion loop with its mapping and task left standing — the task it named died with the list, so nothing stands to leave standing. Should that step return, it is projected afresh and observed afresh, so nothing that happened while it was away is replayed as a transition.

The discard is an obligation in its own right and SHALL NOT be relied upon as the means by which steps re-project; a step whose work is unfinished re-projects because its task is absent from the launch's list, whether or not its mapping was discarded first.

The deleted condition SHALL be established from what ClickUp reports about the list itself, and SHALL NOT be inferred from any failed request — neither from a failed write against the list nor from a failed read of it. A request failing with "not found" is also what a transient fault, a withdrawn permission or a mistaken identifier looks like, whereas ClickUp reporting the list as deleted is ClickUp stating the fact. Where the system cannot establish a recorded list's state, the launch SHALL fail its pass rather than be healed on the strength of the failure; a launch so failed is contained as any failing launch is.

Completions already recorded against the deleted list's tasks SHALL stand. What a deletion ends is the ability to observe *further* transitions on tasks that no longer exist; the re-projected tasks begin unobserved, exactly as newly projected tasks do.

A pass that stands down because the served playbook cannot hold a launch SHALL create nothing and write nothing, as the stand-down requirement specifies; that is a decline rather than the silent skip this requirement forbids, and it is recorded as a successful run.

#### Scenario: A launch without a list gets one

- **WHEN** the reconciliation pass runs and an active launch has no recorded ClickUp list
- **THEN** a list is created in the configured folder, named with the product's catalog name and SKU
- **AND** the association between the launch and the created list is recorded

#### Scenario: An existing list is not recreated

- **WHEN** the reconciliation pass runs, the launch already has a recorded list, and ClickUp reports that list as existing
- **THEN** no new list is created

#### Scenario: A launch whose list was deleted gets a new one

- **WHEN** the reconciliation pass runs and ClickUp reports the launch's recorded list as deleted
- **THEN** a new list is created in the configured folder, named with the product's catalog name and SKU as any launch list is
- **AND** the launch is recorded against the new list
- **AND** the launch's task mappings are discarded, except those for playbook-defined steps whose recorded outcome is terminal

#### Scenario: The replacement and the discard cannot come apart

- **WHEN** the reconciliation pass replaces a launch's deleted list and the write of that replacement does not complete
- **THEN** the launch is left recorded against its old list with its task mappings intact

#### Scenario: Steps re-project into the replacement list

- **WHEN** a launch's deleted list has been replaced and the reconciliation pass runs again
- **THEN** every projectable step whose work is unfinished has a task in the new list
- **AND** each such task begins unobserved, so its first completion is recorded as a transition

#### Scenario: Finished work is not re-projected into the replacement list

- **WHEN** a launch's deleted list is replaced and a projectable step's recorded outcome is already terminal
- **THEN** no task is created for that step in the new list

#### Scenario: Finished work of a step the launch is not held to survives the replacement

- **WHEN** a launch's deleted list is replaced, a step's recorded outcome is terminal, and the playbook defines that step but the launch is not currently held to it
- **THEN** its mapping is not discarded
- **AND** no task is created for that step should the launch later be held to it again

#### Scenario: A mapping for an undefined step is discarded

- **WHEN** a launch's deleted list is replaced and a mapping names a step the playbook no longer defines
- **THEN** that mapping is discarded with the rest

#### Scenario: Outcomes recorded before the deletion are kept

- **WHEN** a launch's deleted list is replaced and steps had outcomes recorded from tasks in that list
- **THEN** those recorded outcomes are unchanged

#### Scenario: A failed write is not read as a deletion

- **WHEN** the reconciliation pass runs and a write against the launch's list fails with "not found" while ClickUp does not report the list as deleted
- **THEN** no new list is created and no task mapping is discarded

#### Scenario: A list whose state cannot be established is not healed

- **WHEN** the reconciliation pass cannot establish the state of a launch's recorded list, because the request for it fails
- **THEN** no new list is created and no task mapping is discarded
- **AND** that launch's pass fails, rather than the failure being read as a deletion

#### Scenario: A graduated launch is left alone

- **WHEN** the reconciliation pass runs and a launch has reached `graduated`
- **THEN** no list or task is created or updated for it and no outcome is recorded from it
- **AND** its recorded list is not checked for existence

#### Scenario: Missing folder configuration fails the run

- **WHEN** the reconciliation pass runs, an active launch needs a list, and no parent folder is configured
- **THEN** the pass reports failure rather than skipping the launch silently
- **AND** this holds equally for a launch needing a list because ClickUp reports its recorded one deleted, which is not given its deleted list's identifier back

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

The system SHALL record, against the mapped step, a `Satisfied` outcome when its ClickUp task reaches a status of the closed type, and an `InProgress` outcome when a previously closed task is reopened — in both cases with provenance naming `clickup` as the source, the ClickUp actor where the delivery identifies one, and the task as evidence. "Previously closed" means last observed closed, per the retained observed state the reconciliation requirement defines — a reopening whose closing was never observed records nothing. A newly projected task's retained observed state starts as not closed. These recordings apply only to a step the loop still projects: the mapped task of a step that has left the projection records nothing, as the leaves-the-loop requirement below specifies. No other outcome SHALL be produced from ClickUp state. The system SHALL NOT write task status to ClickUp: completion travels one way, from ClickUp to the launch.

This recording is suspended while the served playbook cannot hold a launch: intake during a stand-down records no outcome whatever the task's status, as the stand-down requirement specifies, and what it does to the task's retained observed state depends on whether the step is served.

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

The system SHALL periodically, on a declared schedule and without any request from outside the deployment, read the ClickUp state of every active launch's mapped tasks and record any completion or reopening whose webhook delivery was missed, with the same outcome mapping, source, and evidence as webhook intake; the recorder is the reconciliation's own identity, since a read exposes no acting user. A missed completion or reopening SHALL be detected as a transition of the task's observed closed state: the system SHALL retain, per mapped task, the closed state it last observed — updated by every observation, webhook and reconciliation alike — and SHALL record an outcome only when the state read from ClickUp differs from that retained state. Recording applies only to steps the loop still projects: the mapped task of a step that has left the projection is still observed — its retained state updated — but records nothing, as the leaves-the-loop requirement below specifies. A task showing no transition SHALL NOT cause any recording, whatever outcome the step carries.

The pass does not run at all while the served playbook cannot hold a launch, as the stand-down requirement specifies; a completion missed during a stand-down is recorded by the first pass to run once the playbook is ready, from the transition its retained observed state still shows.

"Every active launch" has one exception, and it works the same way: a launch whose projection raised on this run is not reconciled on it, as the containment requirement specifies. That launch's tasks are left unread and unobserved, so a completion missed while its projection was failing is recorded by the first run that projects it successfully — again from the transition its retained observed state still shows, and again only for a step the loop still projects then, as the leaves-the-loop requirement governs.

The obligation to observe a departed step's task is deferred by the same exception, and the narrowing it causes SHALL be stated rather than left implicit. That obligation exists so a closure occurring while a step is out of the projection is consumed and never replayed as a transition after the step returns; a launch that goes unreconciled consumes nothing. So the guarantee holds from the first run that reconciles the launch onward, and a closure occurring while both the step was out of the loop **and** the launch was going unreconciled may be recorded when the step returns. This is narrower than the pass abandoning its walk, which observes nothing for any launch behind the failure, and it is accepted on that basis.

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

#### Scenario: A launch whose projection failed is left unreconciled and unobserved

- **WHEN** the reconciliation pass would reach a launch whose projection raised on the same run
- **THEN** that launch's tasks are neither read for recording nor observed, and their retained observed states are left exactly as they were

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

### Requirement: Projection and intake stand down while the playbook cannot hold a launch

The projection and reconciliation passes SHALL decline to run while the served playbook is not ready — while any gate holds no active blocking step — creating no list, writing no task, and recording no outcome. A playbook still being authored is an expected state rather than an outage, so the pass SHALL be recorded as having **succeeded**: `scheduled-jobs` records only whether a run succeeded, and recording a failure would put a working deployment into retry and overdue reporting for a condition retrying cannot resolve. The stand-down and the gates causing it SHALL be logged.

A consequence SHALL be accepted rather than worked around: because each stood-down pass refreshes the work's last success, overdue reporting does not fire while the playbook is not ready, and this capability therefore raises no signal of its own during a stand-down. The condition is reported instead by the daily briefing, which names the unheld gates on every run while they persist, so the deployment is not silent about it — see `briefing`.

Webhook intake arriving while the playbook is not ready SHALL be acknowledged and SHALL record nothing. What it does to the delivery's task depends on whether that task's step is one the playbook serves, and the two cases SHALL NOT be collapsed:

- Where the step **is served**, the delivery SHALL leave the task **unobserved**: its retained observed state SHALL NOT be advanced. This is the whole of what makes the completion recoverable. Reconciliation detects a missed completion only as a *transition* of that retained state, so advancing it during a stand-down — as an ordinary observation does — would leave the later reconciliation seeing no transition and recording nothing, losing the completion silently.
- Where the step is **not served**, the delivery SHALL observe the task exactly as it does outside a stand-down, advancing the retained observed state while recording nothing. The obligation here is the opposite one and is unchanged by the stand-down: a closure that happened while the step was out of the served set must be consumed, so it is never replayed as a transition after the step returns.

Distinguishing the two requires the playbook the stand-down declined to serve, which the refusal carries for this purpose (see `launch-playbook`). No second read is taken, and the not-ready state does not become a reason to guess.

Failing the delivery instead of acknowledging it would make ClickUp retry against a condition that retrying cannot resolve, which is why a served step's completion is recovered by reconciliation rather than by redelivery.

#### Scenario: A pass stands down rather than failing

- **WHEN** the reconciliation pass runs while a gate holds no active blocking step
- **THEN** no list is created, no task is written, and no outcome is recorded
- **AND** the run is recorded as succeeded, with the stand-down and the unheld gates logged

#### Scenario: A served step's task is not observed during a stand-down

- **WHEN** a verified webhook delivery arrives during a stand-down for a task whose step the playbook serves
- **THEN** the delivery is acknowledged, nothing is recorded, and the task's retained observed state is left exactly as it was

#### Scenario: A served step's completion arriving during a stand-down is not lost

- **WHEN** a served step's mapped task is closed in ClickUp while the playbook is not ready
- **AND** the playbook later becomes ready and the reconciliation pass runs
- **THEN** the completion is recorded then, from the transition between the task's unchanged retained state and its closed state in ClickUp

#### Scenario: A non-served step's closure during a stand-down is still consumed

- **WHEN** a verified webhook delivery arrives during a stand-down for a task whose step the playbook does not serve
- **THEN** the delivery is acknowledged, nothing is recorded, and the task's retained observed state is advanced
- **AND** when the playbook becomes ready and that step is active again, no outcome is recorded for that closure

#### Scenario: A ready playbook restores the passes

- **WHEN** every gate holds at least one active blocking step
- **THEN** the projection and reconciliation passes run exactly as they do today

### Requirement: One launch's failure does not stop the other launches being converged

The completion pass SHALL attempt every active launch on every run it makes, whatever happened while it was working on the launches before it. A failure raised while projecting or reconciling one launch SHALL be contained to that launch and SHALL NOT prevent any other active launch from being attempted on the same run. Each contained failure SHALL be reported as it happens, naming the product its launch is for and carrying what was raised — separately from, and in addition to, the run's own failure below. The aggregate is what makes the run fail; the per-launch report is what makes a fault diagnosable, and a walk that failed on three launches is required to say so three times rather than once.

This is what makes the passes' per-launch shape actually hold. Projection and reconciliation are each written as convergence over one launch, but a pass that abandons its walk on the first failure turns one launch's fault into every launch's outage — and which launches are starved is decided by nothing more principled than the order the active launches happen to come back in.

A run in which the pass stands down is not a run in which launches were skipped. Readiness is determined once, before the walk begins, and a stand-down declines the whole pass and is recorded as a successful run, exactly as the stand-down requirement specifies. A stand-down SHALL NOT be reached as a per-launch failure and SHALL NOT fail the run.

A run in which one or more launches failed SHALL be reported as a **failed run**, and the error that fails it SHALL name every launch that failed, by the identifier of the product each launch is for. The identifier is what the pass already holds; naming the product's catalog name instead would mean a catalog read on the failure path, which is one more thing to fail while reporting a failure. Containment governs which launches are attempted, never whether a fault is visible. `scheduled-jobs` records only whether a run succeeded, so a contained failure reported as a success would leave a launch unprojected indefinitely with nothing raising a signal at all. This is deliberately not the trade the stand-down requirement makes: a stand-down is an expected stage of a deployment being set up and its signal is carried elsewhere, by the daily briefing naming the unheld gates. A launch that cannot be converged is an outage, nothing else reports it, and the run's own outcome is the only signal there is.

Containment covers errors raised by the work itself. It SHALL NOT contain a cancellation or a shutdown of the process running the pass: a worker being stopped SHALL stop walking launches rather than recording the cancellation against a product and continuing. The cancellation is left to propagate, and nothing further is required of the run's outcome, which is `scheduled-jobs`' to decide for a process that stopped. The launches contained before it stand in their own reports.

Nor SHALL it contain a failure of the recovery the pass performs after a contained failure, before the next launch is attempted — the recovery that restores it to a state in which that launch's writes can be recorded. Where that recovery fails, the pass SHALL end the walk: continuing would mean attempting launches whose results it cannot record, writing to ClickUp and losing the record of that write, which is worse than stopping. Such a run SHALL still be reported as a failed run, and the error that fails it SHALL name the launches contained up to that point — those, rather than all that would have failed, and nothing is lost from the record by that, since each was already reported in its own right as it happened.

A launch whose projection raised SHALL NOT be reconciled on that run — neither recording an outcome from it nor observing its tasks. Projection establishes the list and the task mappings that reconciliation reads back, so a launch whose projection failed is one whose projection is in an unknown state, and reading outcomes out of it is a third condition this capability does not define.

Skipping the launch **entirely** is what makes the withheld completions recoverable rather than lost, and the two SHALL NOT be separated. Reconciliation records an outcome only on a transition of a task's retained observed state; a variant that read the launch and declined to record would advance that state and consume the transition, so the completion would never be recorded by any later run. Declining to look at all leaves the transition standing for the first run whose projection succeeds, for a step the loop still projects then — the same mechanism, with the same qualification, that the stand-down requirement relies on for a served step.

The remaining consequence SHALL be accepted rather than worked around, and it is bounded to the path it belongs to: a launch whose projection keeps failing has no completion recorded **by reconciliation** for as long as that lasts, so a completion whose webhook delivery was missed does not reach its gate until a run projects the launch successfully. Webhook intake is unaffected by any of this — it is gated on the delivery and the mapping, and on the conditions the intake requirements already impose, never on what the completion pass did — so a delivery that does arrive for such a launch is still verified, still recorded, and still opens what it opens.

A launch attempted after a failed one SHALL be converged and reconciled exactly as it would have been had the earlier launch succeeded: no state left by one launch's attempt affects another's, whatever the earlier failure was — a database fault included.

Work completed for a launch before its failure SHALL stand rather than being undone: the list already created, the tasks already created, the associations already recorded for them, and any outcome already recorded from them. Every pass is convergence over what is already there, so a later attempt resumes from the partial result: it neither repeats the ClickUp writes that succeeded nor restarts the launch's projection from nothing.

The existing obligation that an unconfigured parent folder fails the run rather than skipping a launch silently is unaffected by this requirement. That condition is reached by each launch that needs a list, so containment turns it into one failure per such launch and the run still fails; it does not become a skip.

#### Scenario: A launch that fails does not stop the launches after it

- **WHEN** the completion pass runs over several active launches and projecting or reconciling one of them raises
- **THEN** every other active launch is still converged and reconciled on that same run

#### Scenario: Each contained failure is reported against its own launch

- **WHEN** the walk contains failures for more than one launch on the same run
- **THEN** each is reported separately as it happens, naming the product its launch is for and carrying what was raised

#### Scenario: A run carrying a failed launch is reported as failed

- **WHEN** the completion pass finishes its walk and at least one launch failed
- **THEN** the run is reported to the scheduled-work machinery as a failed run
- **AND** the error that fails the run names every launch that failed, by its product identifier

#### Scenario: A run in which every launch succeeds is reported as succeeded

- **WHEN** the completion pass walks every active launch and none of them fails
- **THEN** the run is reported as succeeded

#### Scenario: A stand-down is not a contained failure

- **WHEN** the pass runs while the served playbook cannot hold a launch
- **THEN** no launch is attempted and nothing is reported as a failed launch

#### Scenario: A launch whose projection failed is not reconciled on that run

- **WHEN** projecting a launch raises during the pass
- **THEN** that launch's reconciliation is not attempted on that run: no outcome is recorded for it and none of its tasks is observed
- **AND** the walk continues to the next launch

#### Scenario: A completion withheld by a skipped reconciliation is recorded later

- **WHEN** a launch's task is closed in ClickUp and no webhook delivery for it arrives, while that launch's projection is failing on every run
- **AND** a later run projects the launch successfully and reconciles it, the task's step being one the loop still projects on that run
- **THEN** the completion is recorded then, from the transition the task's unchanged retained observed state still shows

#### Scenario: A webhook delivery still records for a launch whose projection is failing

- **WHEN** a verified webhook delivery arrives for a mapped task of a launch whose projection raised on the most recent run
- **THEN** the outcome is recorded exactly as it would be for any other launch, the completion pass's fate notwithstanding

#### Scenario: A partially projected launch keeps what its failed attempt achieved

- **WHEN** a launch's projection raises after its list and some of its tasks were created and recorded
- **THEN** the list and task associations recorded before the failure survive it
- **AND** the next run's projection continues from them rather than starting the launch again

#### Scenario: A launch attempted after one that failed on the database is unaffected by it

- **WHEN** attempting one launch fails with a database error the pass recovers from, and a later launch is then attempted
- **THEN** the later launch is projected and reconciled exactly as it would have been had the earlier launch succeeded
- **AND** the writes it makes are recorded

#### Scenario: A failure of the recovery between launches ends the walk

- **WHEN** a launch's failure is contained and the database then becomes unusable in a way the pass cannot recover from before the next launch
- **THEN** no further launch is attempted
- **AND** the run is reported as a failed run, its error naming the launches contained before that point

#### Scenario: A cancelled pass stops rather than containing the cancellation

- **WHEN** the process running the pass is cancelled or shut down partway through the walk
- **THEN** the walk stops rather than continuing to the next launch
- **AND** nothing is reported as a failed launch on account of the cancellation

#### Scenario: Missing folder configuration is not turned into a skip

- **WHEN** the completion pass runs, several active launches need lists, and no parent folder is configured
- **THEN** each such launch is attempted and fails, rather than being skipped

### Requirement: A projected task carries its step's gate and discipline as Custom Field values

The system SHALL record, on each projected task, the gate the step belongs to and the discipline that owns it, as values on two ClickUp Custom Fields, so that a launch list can be grouped, filtered and **ordered** along the two divisions the playbook is built on. Ordering is what distinguishes this from a label: the gates are a sequence, and a representation that cannot be sorted into that sequence states the gate without stating where in the launch it sits.

The two fields SHALL be identified by configured field identifiers rather than by their names, so that renaming a field in ClickUp does not detach the system from it. The configured identifier is the whole of what names the field: the system SHALL NOT search for a field by name, and SHALL NOT treat a field whose name it recognises as the configured one.

A field SHALL be **resolved** before it is written: the system reads the field's definition and matches the step's gate identifier, or its discipline value, against the field's declared options by name, writing the option the match names. The match SHALL be exact on the identifier string — the gate identifiers and discipline values are the ones the playbook and the shared vocabulary already fix, so no second naming scheme has to be kept true to the first, and a hand-typed option differing from one by case, spacing or wording is a configuration gap rather than a match.

The system SHALL NOT create either field, change its type, or add, remove, reorder or rename any of its options. The fields are configured by hand, and the system's whole relationship to their configuration is to read it and to report on it.

**Each field is configured independently.** A field's identifier is **not configured** when it is absent. An identifier that is present but **empty** SHALL NOT be treated as absent: it SHALL be reported as a configuration gap of its own, naming that field as configured with no value. Absence is how a deployment declines a field, and it is expressed by not setting the variable; an empty value is what a deployment that meant to opt in produces when its configuration is rendered wrongly, and treating that as a decline would answer a mistake with silence. This repository has already lost a deployment to exactly that shape.

Where a field's identifier is not configured, the system SHALL write no value for that field and SHALL report nothing about it — a deployment that names no field has declined that field rather than misconfigured it. The other field SHALL be unaffected: a deployment configuring the gate field alone records gates, reports on the gate field, and says nothing whatever about discipline. Silence therefore means "not asked for" and a report means "asked for and broken", for each field separately.

Carrying the discipline as a Custom Field does not reopen the task **name**, which SHALL continue to exclude it as the projection requirement specifies. That exclusion rests on name width — a single line a reader scans, where restating the discipline costs the wording the name exists to surface — and a field value spends none of it.

A task's values SHALL be set **after** the task is created, never inside the create call itself. Carrying them inside the create would save two requests per created task and would put them on the path that brings a step's work into being, where a value the task system refuses costs the step its whole task — which the guarantee below forbids save on the one path it names. The saving is two requests per created task, paid once each; the price is a failure path on the create that this requirement would then have to qualify its own guarantee around. The system SHALL set either value on a task that does not already carry it — a newly created one included, so that tasks projected before this requirement existed gain their values rather than the behaviour reaching only launches started afterwards — the same obligation the assignee requirement already carries, and for the same reason.

Where a task's value for either field differs from the one its step resolves to, the system SHALL correct it. This is deliberately unlike the name, the body and the assignees, which a person may edit and which no pass overwrites: those are things a person may legitimately mean, whereas each of these two fields is single-valued and wholly determined by the step, so a divergence is drift and there is nothing a person could mean by it that the step does not already say. Correcting it is what allows a step moved to a different gate to reach its task, which the tag representation this replaces could not do — **wherever the step's gate resolves to an option**. Where it does not, the task keeps the value it has: writing an approximation would state something the playbook does not say, and clearing the value would state nothing where something true was standing. Such a task states a gate that is no longer its step's for as long as the gap lasts, which is the predecessor's own accepted defect surviving inside the gap and no further; the gap is what is reported, and repairing it corrects the tasks on the next pass.

Recording these values SHALL follow the projection it belongs to and never run ahead of it. A task whose step has left the projection SHALL NOT be given either value, exactly as *A step that is not active leaves the loop* specifies and on every ground that requirement names — the step is not `active`, its kind is no longer `human`, or it carries the `prohibited-tactic` hazard. That requirement is referenced rather than paraphrased deliberately: it states that projection turns on three fields and that "a rule naming fewer would leave the rest undefined", so restating a subset here would reintroduce exactly the gap it was written to close. A step the served playbook does not define at all is likewise never given a value, on the projection requirement's own ground. No value is written while the passes have stood down, for the reason the stand-down requirement already gives. A launch that has reached `graduated` is not visited by any pass at all, as *Each launch is projected into its own ClickUp list* specifies, so its tasks are never given values and never backfilled.

**No value SHALL be written for a field the configuration check has found in a gap of the kinds that withhold writes** — a field whose identifier is present but empty, a field the folder does not include, a field the read could not interpret, a field of the wrong type, a field declaring no options, or a field declaring more than one option named for the same gate, or for the same discipline, as the gap definition scopes it. The last is included for the reason that definition gives: where two options share a name, "the option the match names" is not a single option, so any write picks one arbitrarily, and a pick that is not stable across passes makes every pass disagree with the task and write again — the standing write storm the representation rule exists to prevent, arriving by another door. For an absent or optionless field nothing could resolve in any case; for a wrong-typed field that nonetheless declares matching options, resolution *would* succeed, and writing anyway would send a value to a field whose write behaviour the system has just established it did not intend. The gap report is the whole of the response, and a per-task record of the same cause is exactly the once-per-task noise the check exists to replace.

No Custom Field failure SHALL fail the pass, and the guarantee carries exactly one qualification, stated in the suppression clause below: a fault in this concern SHALL cost the field values and nothing else — never the projection of a launch's work, and never the completion intake that travels on the same pass. This holds across every path this concern touches, and each is closed by its own rule rather than by assertion: nothing about these two fields reaches the call that creates a task; the sole exception is a shared store this concern could not restore, which the suppression clause below states and hands to *One launch's failure does not stop the other launches being converged*; the folder read's failure is absorbed by the reachability clause below; the read of a list's tasks is required to be total, so no field value can stop it and through it a launch; the record that suppresses repeated reports and the delivery of the report itself are each covered by their own clause below; and a per-task write failure is stepped over. A path added to this concern later joins this rule rather than sitting outside it. Where setting a value on a task fails, the pass SHALL continue, SHALL still attempt the task's other field, and SHALL report the omission as a warning-level application log record naming the step, the field and the task. Where a step's gate or discipline matches no option the field declares, the system SHALL write nothing for that field on that task rather than writing an approximation, and the gap SHALL be reported by the configuration requirement below rather than once per task.

This requirement makes no claim about the run's own outcome. Whether a run is recorded as succeeded or failed is settled by *One launch's failure does not stop the other launches being converged* and by the stand-down requirement; what is required here is only that no fault of this concern is among the things that make a run fail.

#### Scenario: A newly created task is given both values

- **WHEN** a task is projected for an `active` `human` step and both fields are configured and resolve
- **THEN** the create call carries no Custom Field value
- **AND** the task is then given the option matching the step's gate on the gate field, and the option matching its discipline on the discipline field

#### Scenario: A field fault cannot cost a step its task

- **WHEN** every write of a Custom Field value fails for a step being projected for the first time
- **THEN** the task exists and carries its name, body, assignees and due date
- **AND** nothing about the failure causes the run to be recorded as failed

#### Scenario: No value is written to a field found in a gap

- **WHEN** a pass runs and the gate field is present and declares an option for every gate but is not of the type whose values the system writes
- **THEN** no gate value is written on any task
- **AND** the gap is reported once for the pass rather than once per task

#### Scenario: A task projected before the fields existed gains its values

- **WHEN** a pass runs over a mapped task that carries neither field's value and whose step resolves both
- **THEN** the task is given both values

#### Scenario: A task already carrying its values is left alone

- **WHEN** a pass runs over a mapped task already carrying the values its step resolves to
- **THEN** no Custom Field write is sent for that task
- **AND** a task in the same launch whose values are absent is still given them

#### Scenario: A re-gated step's task is corrected

- **WHEN** a step's gate is changed by authoring and a pass runs over its mapped task, which still carries the option for the former gate
- **THEN** the task's gate field is set to the option matching the step's current gate

#### Scenario: A re-gated step whose new gate has no option keeps its former value

- **WHEN** a step's gate is changed to one the gate field declares no option for, and a pass runs over its mapped task
- **THEN** the task's gate field is left carrying what it has
- **AND** the missing option is reported as a configuration gap

#### Scenario: An option differing only in wording is not a match

- **WHEN** the gate field declares an option whose name differs from a gate identifier by case or spacing
- **THEN** no task is given that option for that gate
- **AND** the gate is reported as having no matching option

#### Scenario: A step that is not projected is given no values

- **WHEN** a pass runs and a step is not `active`, or is not `human`, or carries the `prohibited-tactic` hazard, or is not defined by the served playbook
- **THEN** no Custom Field value is written for it
- **AND** a projected step in the same launch is still given both of its values

#### Scenario: A deployment configuring no field writes none

- **WHEN** a pass runs in a deployment that configures neither field identifier
- **THEN** every task is projected with its name, body, assignees and due date as usual
- **AND** no Custom Field value is written and no configuration report is made

#### Scenario: A field identifier configured but empty is a gap

- **WHEN** a pass runs in a deployment where a field's identifier is present but empty
- **THEN** that field is reported as configured with no value, rather than treated as declined
- **AND** no value is written for it

#### Scenario: A deployment configuring one field records only that one

- **WHEN** a pass runs in a deployment that configures the gate field's identifier and not the discipline field's
- **THEN** every task is given its gate value
- **AND** no discipline value is written, and nothing about the discipline field is reported

#### Scenario: A stood-down pass writes no value

- **WHEN** the passes stand down because the playbook cannot hold a launch
- **THEN** no Custom Field value is written on any task of any launch

#### Scenario: A field write that fails costs only that field

- **WHEN** setting the gate value on a task fails
- **THEN** the discipline value is still attempted for that task
- **AND** the pass continues over the remaining launches
- **AND** nothing about this fault causes the run to be recorded as failed
- **AND** the omission is reported as a warning-level log record naming the step, the field and the task

### Requirement: The Custom Field configuration is checked once per pass and a gap is reported without stopping the pass

The system SHALL check the configuration of the configured fields **once per pass, before any task is written**, by a single read of the Custom Fields available to the launches' folder. Checking once rather than per task is what makes the check complete: a gap in an option is a property of the configuration, identical for every task of every launch, and discovering it only where a task happens to need it would leave a gate whose steps are all resolved — or a launch not yet reached — unchecked, so a missing option for a late gate would stay invisible until a launch arrived at it.

**An empty field identifier SHALL be reported whether or not the folder's fields could be read**, since it is established by the configuration alone and needs no network at all. Where the read did not complete, or no launch folder is configured, the empty-identifier finding SHALL still be composed and reported while every other kind is withheld. This is deliberate: an empty identifier is the shape a mis-rendered deployment takes, it is exactly what this rule exists to catch mechanically, and withholding it behind a reachability fault would make the catch depend on the very service whose configuration is in question. A stand-down remains the exception, on the ground it already gives — a stood-down pass declines entirely.

The check of the folder's fields SHALL NOT be performed in any of three states, and in the first two nothing beyond the empty-identifier finding SHALL be reported; in the third — the stand-down — nothing SHALL be reported at all, that finding included, because a stood-down pass declines entirely rather than doing a reduced amount of work. The three states: where neither field identifier is configured, on the ground the projection requirement above gives; where no launch folder is configured, leaving *Each launch is projected into its own ClickUp list* the sole authority on that condition; and on a pass that has stood down, on the ground the stand-down requirement gives — a stood-down pass declines the whole pass and SHALL reach ClickUp for nothing at all, this check included. A standing gap therefore goes unreported for the duration of a stand-down, which is accepted: a stand-down is a deployment being set up, and the configuration it would report on is part of what is still being set up.

A **configuration gap** is any of the following. The first is assessed for a field whose identifier is present at all; the rest only for a field whose identifier is present and non-empty: a field identifier that is present but **empty**, reported as that field being configured with no value and never as the field being absent — the two call for different repairs, and reporting a rendering mistake as a missing field sends someone looking in the wrong place; a configured field identifier that the folder's Custom Fields do not include; a configured field the read reports as **uninterpretable**, reported as such and never as the field declaring no options — a field the client could not make sense of may declare eight options perfectly well, and telling someone to add options to a field that has them sends them to argue with their own screen; a configured field that is not a field declaring a single value drawn from an ordered set of options; a configured field that declares no options; a gate identifier in the playbook's fixed gate sequence that no option of the gate field names exactly; a discipline of the shared vocabulary that no option of the discipline field names exactly; **or a gate field whose options naming gates do not appear in the playbook's gate-sequence order**; the gate field declaring more than one option named for the same **gate**, or the discipline field more than one named for the same **discipline** — since "the option the match names" is then not a single option, and the order clause has no single position to judge. While a duplicate stands on the gate field, no order finding SHALL be composed for that field, and neither the order kind nor the order observed SHALL enter that field's identity — otherwise shuffling options while the duplicate stands would change the identity and re-report the same unrepaired duplicate: the order cannot be judged until the duplicate is resolved, and reporting an order that may be an artefact of the duplicate would name a repair that is not yet the right one. A duplicated name the system never resolves against is **not** a gap: it makes no write ambiguous, and reporting it would disable a field over a duplicate that has nothing to do with this system's use of it.

The order clause is not decoration. Ordering is the whole of why this change prefers a field to a tag, and every other clause here can pass while the order is wrong: a field naming all eight gates in the wrong sequence produces a view that reads as meaninglessly as the tags it replaced, silently and permanently. It is also the clause a repair is most likely to break — an option added by hand lands **last** in the declared order, so the obvious response to "gate `stock-ready` has no option" fixes the reported gap and introduces this one. Checking the order is what makes that visible instead of leaving a passing configuration that does not work.

Where a field is found in a gap of the kinds that **withhold option-level findings** — its identifier empty, the field absent, uninterpretable, of the wrong type, or declaring no options — no option-level or order finding SHALL be composed for that field. This set is not identical to the kinds that withhold writes above: the duplicate-name kind withholds writes, because no write against it is unambiguous, but does not withhold option-level findings, because such a field may still be missing options a repair must address. The fault at the level of the field itself is the one to repair, and the option-level findings it would generate are its consequences rather than separate repairs: an optionless field would otherwise be reported as declaring no options *and* as missing all eight gates, which is the narrowing the absent case already states. The duplicate-name kind is the exception and is handled in its own clause above, since a field carrying duplicates may still be missing options that a repair must address.

The report SHALL name every gap found, not the first, so that one repair round closes them all. It SHALL name what the field does declare where an expected option is missing, so a hand-typed mismatch is diagnosable rather than merely reported; and where the order is wrong it SHALL name the order found, so the repair is a reordering someone can perform rather than a fault they have to reconstruct.

**A failure to read the folder's Custom Fields, or a read whose result cannot be interpreted, is not a configuration gap and SHALL NOT be reported as one.** It is a reachability fault, and `runtime-configuration` requires the two to stay distinguishable — its *Checking Configuration Performs No Network Or Database Access* exists "so that a configuration fault is distinguishable from a reachability fault". Such a read SHALL yield no finding **derived from the folder's fields** — the empty-identifier finding is derived from the configuration alone and is unaffected, as the paragraph above requires — SHALL be reported as a warning-level application log record, and SHALL cost that pass its Custom Field values and nothing else: the pass SHALL continue and project, correct and reconcile every launch as it otherwise would. Reporting an unreachable ClickUp as two absent fields would deliver a false repair instruction and then suppress the truth behind it.

A cancellation or shutdown of the process running the pass is **not** among the failures any clause of this requirement or the one above absorbs. It SHALL be left to propagate, on the ground *One launch's failure does not stop the other launches being converged* already gives for the walk: a worker being stopped must stop, rather than swallowing the cancellation and finishing its work.

A configuration gap SHALL NOT stop the pass, SHALL NOT prevent any task from being projected or corrected, and SHALL NOT be among the things that cause a run to be recorded as failed. The pass SHALL continue and write every value that does resolve. Making a run fail for it would put a working deployment into retry and overdue reporting for a condition retrying cannot resolve — the reason `scheduled-jobs` already gives for the playbook stand-down — and a gap costs the field values and nothing else, which no launch's work depends on. A gap is likewise **not** a per-launch failure and SHALL NOT be contained, reported or counted as one: it is determined once, before the walk begins, in the same phase as readiness, and *One launch's failure does not stop the other launches being converged* governs the walk rather than this check. Where launches do fail on the same run, that requirement decides the run's outcome and this one takes nothing away from it.

A configuration gap SHALL be reported to the team's Slack channel, because a warning-level log record is not a place anybody looks and the entire purpose of the check is that a person acts on it. A **continuing** gap SHALL be reported once and not on every pass: the system SHALL retain that a report was delivered and SHALL NOT report the same gap again while it stands, so that a misconfiguration left in place over days produces one message rather than a wall of identical ones that trains the team to ignore the channel. Retention SHALL survive a restart of the process running the pass, for the same reason `scheduled-jobs` requires it of a continuing outage: a flood that resumes on every restart is not suppressed.

**A failure to read or write the record that suppresses repeated reports SHALL cost this pass its Custom Field values and nothing else, save on the one path this paragraph names.** It sits on the pre-walk path, ahead of every launch, so a fault there would otherwise abort a pass before any launch was projected — a fault wholly inside this concern costing the projection and the completion intake of every launch, which the guarantee above forbids. Otherwise — that is, wherever the store is left in a state in which the launches' writes can be recorded — such a failure SHALL be reported as a warning-level application log record and SHALL NOT fail the run, and the pass SHALL continue. Its effect on reporting depends on which access failed, and the two SHALL NOT be conflated. Where the **read** fails, the system cannot tell a standing gap from a new one, so it SHALL report no gap on that pass rather than risk repeating one already delivered. Where the **write** fails *after* a report has been delivered, the report has already gone out and cannot be recalled; the gap SHALL simply remain eligible to be reported again on the next pass. That is the same trade `scheduled-jobs` makes for a continuing outage — a report that could not be recorded leaves the work eligible rather than silenced — and it is preferred here for the same reason: a repeated message is a nuisance, while a gap silenced permanently is the failure this requirement exists to prevent. Where the store the record lives in is shared with the writes the pass makes for each launch, a failed access **on which a report is in flight** — the read that decides whether to report, or the write that records one delivered — SHALL oblige the pass to restore it to a state in which those writes can be recorded before the **first** launch is attempted. A failed access on the *clearing* path SHALL NOT: clearing runs on a pass that found no gap, so nothing was reported and no later launch depends on it, and obliging a restore there would let a benign fault end a walk. Where the restore is obliged, on the ground *One launch's failure does not stop the other launches being converged* already gives for recovery between launches: continuing against a store that cannot record is worse than not continuing. Where that restore itself fails, the walk SHALL end and the run SHALL be recorded as failed — on the ground *One launch's failure does not stop the other launches being converged* gives for a failed recovery **between launches**, which this requirement extends to the pre-walk restore. The extension is this requirement's own judgement rather than that one's mandate: the baseline clause is scoped to a recovery following a contained failure, and there is none before the first launch, but the consequence of continuing is identical — writing to ClickUp and losing the record of the write. This is the one path on which a fault of this concern costs more than the field values, and the guarantee above is qualified by exactly this much: the alternative is projecting launches whose writes cannot be recorded, which that requirement judges worse than stopping.

The record that suppresses further reports SHALL be written only after a report has been delivered successfully; a report that could not be delivered SHALL leave the gap eligible to be reported on the next pass, so that a transient failure of the reporting channel does not silence the gap permanently. A failure to deliver a report SHALL NOT be among the things that cause a run to be recorded as failed, and SHALL leave the pass to continue — delivery sits on the pre-walk path ahead of every launch, so a fault there must no more stop a launch being projected than a fault in the folder read does.

Suppression SHALL be lifted when the configuration is repaired, so that a gap appearing again afterwards is reported again. It SHALL likewise be lifted where the capability is **withdrawn** — on a pass performing no check because no field identifier is configured — since a deployment that has opted out has no standing gap for a report to be suppressed against, and leaving the record would let a later opt-in meet an unrepaired gap in silence.

A **stand-down** SHALL NOT lift it. A stand-down is not a withdrawal of the capability and says nothing about the configuration: lifting on one would make a deployment whose playbook moves in and out of readiness report the same unrepaired gap on every ready pass, which is the wall of identical messages this paragraph exists to forbid. The same applies to a pass that made no check because the folder read did not complete, which the reachability clause above already requires to clear nothing, and to write nothing beyond the identity of a report it did deliver, and to a pass that made none because no launch folder is configured — that state says nothing about the two fields either.

Where a report **was** delivered on such a pass — an empty-identifier finding, composed without any read — suppression SHALL be written under the identity of what was actually composed, exactly as for any other delivered report. Withholding it because the pass made no read would deliver that same message on every pass for as long as the reachability fault lasted, which is the flood this rule forbids. One consequence follows and is accepted: while reachability comes and goes with a gap standing across both fields, a pass that reads composes the whole finding and a pass that does not composes only the empty-identifier part, so the two identities differ and each transition reports once. That is bounded to one message per transition, and it is the right way round — a partial finding is genuinely different news from the whole one, and the alternative silences the whole finding behind the partial one. A gap whose **content** changes SHALL be reported again rather than suppressed as though it were the gap already reported, since it names a repair that has not been asked for yet. Content SHALL be taken over the **whole finding**, not over the missing options alone: per field, the **set** of gap kinds found — drawn from empty identifier, absent, uninterpretable, wrong type, optionless, duplicate option name, missing options, wrong order, and compared as a set, since a field may be found in more than one at once — together with the missing option names and the duplicated names — each compared as a **set**, so that two passes finding the same gap in a different enumeration order produce the same identity rather than re-reporting — and the gate-option order observed, which is compared as a sequence because its order is the finding — save while a duplicate stands on that field, where neither the order kind nor the order observed enters its identity, as the gap definition above requires. Seven of the eight gap kinds name nothing missing — only *missing options* does, so an identity taken over missing options alone would make a wrong-typed field and a wrongly-ordered one indistinguishable, and a deployment repairing the first into the second would meet silence where the whole point was a report.

#### Scenario: A missing option is reported before any task is written

- **WHEN** a pass runs and the gate field declares no option naming one of the playbook's gates
- **THEN** the gap is reported to Slack naming that gate and that field
- **AND** the report is made once for the pass, not once per task

#### Scenario: A gap does not stop the pass

- **WHEN** a pass runs with a configuration gap standing
- **THEN** every task is still projected and corrected, and every value that does resolve is still written
- **AND** nothing about the gap causes the run to be recorded as failed

#### Scenario: Every gap is named together

- **WHEN** a pass runs and two gates and one discipline have no matching option
- **THEN** the report names all three

#### Scenario: A configured field that is absent is a gap

- **WHEN** a pass runs and a configured field identifier is not among the folder's Custom Fields
- **THEN** the gap is reported as that field being absent, rather than as each of its options being missing

#### Scenario: A field declaring one option name twice is a gap

- **WHEN** a pass runs and the gate field declares two options both named for the same gate
- **THEN** the gap is reported, naming the duplicated name
- **AND** no value is written for that field on any task
- **AND** a gate field declaring two options under a name that is no gate at all is not a gap

#### Scenario: A field the read could not interpret is reported as such

- **WHEN** a pass runs and a configured field is reported by the read as uninterpretable
- **THEN** the gap names it as uninterpretable, not as declaring no options
- **AND** no value is written for that field on any task

#### Scenario: A configured field of the wrong type is a gap

- **WHEN** a pass runs and a configured field is present but is not of the type whose values the system writes
- **THEN** the gap is reported as that field being of the wrong type

#### Scenario: An empty identifier is reported even when ClickUp cannot be reached

- **WHEN** a pass runs with a field's identifier present but empty, and the read of the folder's Custom Fields does not complete
- **THEN** the empty identifier is reported
- **AND** nothing is reported about the other field's options, since they could not be read

#### Scenario: An unreachable ClickUp is not reported as a gap

- **WHEN** a pass runs with both identifiers configured and non-empty, and the read of the folder's Custom Fields does not complete
- **THEN** no configuration gap is reported to Slack
- **AND** no suppression is written or cleared
- **AND** the pass still projects, corrects and reconciles every launch, writing no Custom Field values

#### Scenario: An empty-identifier report on a read-less pass is suppressed like any other

- **WHEN** an empty identifier is reported on a pass whose folder read did not complete, and the next pass finds the same state
- **THEN** no second report is made

#### Scenario: A pass with no active launches still checks the configuration

- **WHEN** a pass runs, the playbook is ready, and no launch is active
- **THEN** the folder's Custom Fields are still read and a standing gap is still reported
- **AND** the check does not depend on any launch existing

#### Scenario: A failure of the suppression record costs only the field values

- **WHEN** the record that suppresses repeated reports cannot be read or written, and the store it lives in is left in a state where the launches' writes can still be recorded
- **THEN** every launch is still projected, corrected and reconciled
- **AND** nothing about the failure causes the run to be recorded as failed

#### Scenario: A failed suppression read and a failed write after delivery differ

- **WHEN** the suppression record cannot be **read** on a pass
- **THEN** no gap is reported on that pass, since a standing gap cannot be told from a new one
- **AND WHEN** on a later pass a gap is reported and the suppression record cannot then be **written**
- **THEN** the gap remains eligible and is reported again on the pass after

#### Scenario: A store this concern cannot restore ends the walk

- **WHEN** an access of the suppression record fails on a store shared with the launches' writes, and the restore of that store before the first launch itself fails
- **THEN** no launch is attempted
- **AND** the run is recorded as failed

#### Scenario: A pass with no launch folder configured reports only the empty identifier

- **WHEN** a pass runs with no launch folder configured and a field's identifier present but empty
- **THEN** no read of the folder's Custom Fields is made
- **AND** the empty identifier is reported and nothing else is
- **AND** no suppression is cleared

#### Scenario: An empty identifier is not reported during a stand-down

- **WHEN** the passes stand down because the playbook cannot hold a launch, and a field's identifier is present but empty
- **THEN** nothing is reported, the empty identifier included

#### Scenario: A stood-down pass performs no check

- **WHEN** the passes stand down because the playbook cannot hold a launch
- **THEN** no read of the folder's Custom Fields is made and no gap is reported

#### Scenario: Options declared out of the playbook's order are a gap

- **WHEN** a pass runs and the gate field declares an option naming every gate, but not in the playbook's gate-sequence order
- **THEN** the gap is reported, naming the order found
- **AND** it is reported even though no gate is missing an option

#### Scenario: Options the playbook does not know are not an order gap

- **WHEN** the gate field declares an option for every gate in playbook order, and additionally declares options naming no gate at all
- **THEN** no gap is reported
- **AND** the extra options are neither reported nor written to any task

#### Scenario: Missing gates are one gap, not two

- **WHEN** the gate field declares options for only some gates, and those it does declare are in playbook order relative to one another
- **THEN** the missing gates are reported
- **AND** no order gap is reported alongside them

#### Scenario: A duplicate withholds the order finding

- **WHEN** a pass runs and the gate field declares two options named for the same gate, and its gate options are also out of playbook order
- **THEN** the duplicate is reported
- **AND** no order gap is reported alongside it, since the order cannot be judged until the duplicate is resolved

#### Scenario: Reordering options during a duplicate does not re-report it

- **WHEN** a duplicate on the gate field is reported, and a later pass finds the same duplicate with that field's options reordered
- **THEN** no second report is made, since neither the order kind nor the order observed entered that field's identity

#### Scenario: A gap repaired into a different gap is reported again

- **WHEN** a wrong-typed gate field is reported, then replaced by a drop-down whose gate options are out of playbook order
- **THEN** the order gap is reported, rather than suppressed as the gap already reported

#### Scenario: A continuing gap is reported once

- **WHEN** a gap is reported on one pass and the same gap still stands on the next
- **THEN** no second report is made

#### Scenario: A stand-down does not lift suppression

- **WHEN** a gap is reported, a later pass stands down because the playbook cannot hold a launch, and a pass afterwards finds the same gap standing
- **THEN** no second report is made

#### Scenario: A continuing gap is reported once across a restart

- **WHEN** a gap is reported, the process running the pass restarts, and the same gap still stands
- **THEN** no second report is made

#### Scenario: An undelivered report leaves the gap eligible

- **WHEN** a gap is found and the report cannot be delivered to Slack
- **THEN** no suppression is retained and the gap is reported again on the next pass
- **AND** nothing about the failed delivery causes the run to be recorded as failed

#### Scenario: A repaired configuration lifts suppression

- **WHEN** a reported gap is repaired, a pass finds no gap, and a gap appears again afterwards
- **THEN** the later gap is reported

#### Scenario: Opting out lifts suppression

- **WHEN** a gap is reported, both field identifiers are then unconfigured, and a later deployment configures them again with the same gap standing
- **THEN** the gap is reported again

#### Scenario: A changed gap is reported again

- **WHEN** a gap is reported, and a later pass finds a gap naming a different set of missing options
- **THEN** the later gap is reported rather than suppressed

### Requirement: The webhook subscription is registered as an idempotent, non-blocking deploy step

The system SHALL provide a step that ensures a ClickUp webhook subscription exists for this deployment's completion endpoint, run after database migrations and before the HTTP server begins serving, as a step of its own rather than as part of the serving process's own startup — the same positioning `roster`'s admin-seeding step takes, and for the analogous reason: the step's one piece of work is a call to an external system (ClickUp), and an external call that can fail or hang must not gate the first request the server would otherwise serve.

Before creating anything, the step SHALL check whether a subscription already targets both this deployment's endpoint and the configured launch folder, and SHALL NOT create a second one where it finds such a match — an idempotent check-then-create, not an unconditional create run on every deploy. Matching on the endpoint alone would not do: a subscription found only because it shares the endpoint could belong to a since-changed folder configuration, and treating it as sufficient would silently leave the *current* folder unregistered. A created or matched subscription SHALL be scoped to the configured launch folder and to task status change events, not to the whole ClickUp workspace, since nothing outside that folder is ever mapped to a launch — which the endpoint-and-folder match keeps true of a matched subscription as well as a created one.

Where the configured launch folder has changed since a subscription was last registered, the check finds no match against the new folder and the step creates a fresh one scoped to it, exactly as it would with no prior subscription at all. The old subscription is not deleted — it is simply no longer this deployment's concern, having become, from the moment the folder configuration changed, a subscription for a folder nothing here maps to any more.

Where the configured credentials resolve to no ClickUp workspace or to more than one, the step SHALL take no action beyond logging the ambiguity — it SHALL NOT guess which workspace to register against. Where this deployment's own public endpoint is not configured, the step SHALL likewise take no action beyond logging the gap, rather than registering a subscription pointed at an unreachable or malformed address.

Unlike `roster`'s admin-seeding step, a failure here — an unresolvable workspace, an unreachable endpoint, a failed ClickUp API call, or any other fault — SHALL be logged as a warning naming the reason and SHALL NOT fail the step, block the deployment, or prevent the server from serving. The two steps share a shape and differ in this one respect deliberately: an unadministrable roster breaks a feature the moment the release starts serving, while completion delivery already has a fallback this capability provides independently of the webhook — the reconciliation pass — so a registration failure degrades to that fallback rather than to a broken deployment.

Each time the step creates a subscription — whether none existed before, or one that existed has since been removed from ClickUp by any means — ClickUp generates that subscription's signing secret itself and returns it in the creation response; the system never supplies its own. The step SHALL log that secret at warning level, naming explicitly that the deployment's configured signing secret must be set or updated to match it before any delivery will verify, and that a subscription recreated without that update leaves every delivery silently rejected by signature verification — indistinguishable, from ClickUp's side, from a healthy subscription.

#### Scenario: A first registration creates a subscription and surfaces its secret

- **WHEN** the step runs and no subscription targets this deployment's endpoint
- **THEN** a subscription is created, scoped to the configured launch folder and to task status change events
- **AND** the secret ClickUp returns for it is logged at warning level, naming that the deployment's signing secret must be set to match

#### Scenario: An existing matching subscription is not recreated

- **WHEN** the step runs and a subscription already targets both this deployment's endpoint and the configured launch folder
- **THEN** no new subscription is created

#### Scenario: A recreated subscription surfaces its secret exactly as a first registration does

- **WHEN** the step runs, no subscription currently targets both this deployment's endpoint and the configured launch folder, and one matching both previously did before being removed
- **THEN** a subscription is created and its ClickUp-generated secret is logged at warning level, exactly as on a first registration — the step does not distinguish the two, since it has no record of a subscription ever having existed before

#### Scenario: A changed launch folder gets its own fresh subscription

- **WHEN** the step runs, the configured launch folder differs from the one a prior subscription was scoped to, and that prior subscription still exists in ClickUp
- **THEN** a new subscription is created scoped to the currently configured folder, and its secret is logged exactly as on a first registration
- **AND** the prior subscription is left as it is — the step neither deletes it nor treats it as satisfying the check

#### Scenario: An ambiguous workspace takes no action

- **WHEN** the step runs and the configured credentials resolve to no ClickUp workspace or to more than one
- **THEN** no subscription is created or checked for
- **AND** the ambiguity is logged

#### Scenario: A missing public endpoint takes no action

- **WHEN** the step runs and this deployment's own public endpoint is not configured
- **THEN** no subscription is created
- **AND** the gap is logged

#### Scenario: A registration failure does not block the deployment

- **WHEN** the step runs and the call to ClickUp fails for any reason
- **THEN** the failure is logged as a warning naming the reason
- **AND** the deployment proceeds and the server begins serving, exactly as if the step had succeeded

#### Scenario: Starting the server performs no registration

- **WHEN** the serving process starts
- **THEN** it performs no webhook registration of its own, leaving that entirely to the step that already ran before it

### Requirement: A launch is converged eagerly at start and at a gate crossing

In addition to the periodic reconciliation pass, the system SHALL run the creation/update half of projection — the same convergence *Each launch is projected into its own ClickUp list*, *Task due dates derive from the launch schedule*, *Human steps are projected as tasks carrying their name, description and assignees* and *A projected task carries its step's gate and discipline as Custom Field values* already define — for one launch immediately when that launch starts, and again immediately whenever that launch's gate crosses, so that a launch's first released steps and a gate's newly released steps get their ClickUp tasks without waiting for the pass's next run.

The eager run SHALL apply every projection and eligibility rule exactly as the pass applies them — release, kind, status, hazard, and retained-composition healing included — because it is the same convergence, run early, not a second rule. Nothing about a task's eligibility, its name, or its body SHALL differ depending on whether the pass or the eager trigger created or last touched it.

The eager run is exempted from one part of that convergence: resolving and correcting a task's Custom Field values (`A projected task carries its step's gate and discipline as Custom Field values`) requires reading ClickUp's field definitions and, on a gap, reporting it — work whose cost and reporting cadence that requirement scopes to a pass run, not to an event. The eager run SHALL write no Custom Field value and SHALL report no configuration gap; a task it creates or corrects is left exactly as if the periodic pass had not yet reached it for that concern, and the next periodic pass resolves and corrects its Custom Field values as it would for any task carrying none — the existing healing rule for "a task projected before the fields existed," reached here by a different route.

The eager run SHALL cover only the creation/update half. It SHALL NOT read back ClickUp state or record any outcome — that remains exactly as *Completion flows from ClickUp to the launch as a recorded outcome*, the webhook, and the pass's own reconciliation half already provide for, untouched by this requirement.

A gate crossing SHALL trigger the eager run regardless of which path crossed it — a recorded decision, the periodic gate-progression pass, or the ClickUp webhook's own advance-and-ask trigger — so that the latency this requirement closes does not silently reopen for whichever of the three happens to be least common.

Because the eager run and the periodic pass perform the same idempotent convergence, either running before, after, or concurrently with the other for the same launch SHALL produce the same converged state as either running alone: neither SHALL create a second list or a second task for work the other has already projected, and a launch's convergence SHALL NOT depend on which of the two reaches it first.

A launch for which the eager run fails SHALL be left exactly as if the eager run had not been attempted: the failure SHALL NOT be raised back to whatever triggered the run — launch start, a recorded decision, the gate-progression pass's own advance, or the webhook's acknowledgement — and SHALL NOT stand in the way of that action's own outcome being reported. The next periodic pass SHALL still attempt to converge that launch on its own schedule, exactly as it would for a launch the eager run never ran for. This requirement creates no new obligation to notice or report a failed eager run beyond what the pass already reports when it, in turn, fails to converge the same launch.

The eager run SHALL be suppressed under exactly the condition *Projection and intake stand down while the playbook cannot hold a launch* already suppresses the pass: while the served playbook cannot hold a launch, neither the pass nor the eager run SHALL create a list or write a task.

#### Scenario: A newly started launch's first tasks appear without waiting for the pass

- **WHEN** `start_launch` succeeds for a product
- **THEN** the launch's released `active` `human` steps have tasks created in its ClickUp list before the next periodic pass runs

#### Scenario: A gate crossing's newly released steps get tasks immediately, however the gate opened

- **WHEN** a launch's gate crosses, whether through a recorded decision, the periodic gate-progression pass, or the ClickUp webhook's advance-and-ask trigger
- **THEN** every `active` `human` step the launch newly releases at that gate has a task created in its ClickUp list before the next periodic reconciliation pass runs

#### Scenario: The eager run applies the same eligibility rules as the pass

- **WHEN** the eager run is triggered for a launch carrying a step that is not `active`, is not `human`, carries the `prohibited-tactic` hazard, or is not yet released
- **THEN** no task is created for that step, exactly as the periodic pass would not create one for it

#### Scenario: Custom Field values on an eagerly created task are left to the next pass

- **WHEN** the eager run creates a task for a step
- **THEN** no Custom Field value is written for that task and no configuration gap is reported by the eager run
- **AND** the next periodic pass gives the task its gate and discipline values, exactly as it would for a task carrying none

#### Scenario: The eager run does not record completions

- **WHEN** the eager run is triggered for a launch
- **THEN** no ClickUp state is read back and no step outcome is recorded as a consequence of the eager run itself

#### Scenario: The eager run and the pass do not duplicate each other's work

- **WHEN** the eager run converges a launch and the periodic pass converges the same launch afterward, with nothing about the launch having changed in between
- **THEN** no new list or task is created by the pass for that launch

#### Scenario: A failed eager run does not fail the action that triggered it

- **WHEN** the eager run raises while converging a launch just started or just crossed a gate
- **THEN** the launch start, the recorded decision, the gate-progression pass's advance, or the webhook's acknowledgement completes and is reported exactly as it would have been had the eager run succeeded

#### Scenario: A failed eager run is caught up by the next periodic pass

- **WHEN** the eager run fails to converge a launch and the next periodic pass reaches that launch
- **THEN** the pass converges it exactly as it would a launch for which no eager run was ever attempted

#### Scenario: The eager run stands down exactly as the pass does

- **WHEN** a launch starts or crosses a gate while the served playbook cannot hold a launch
- **THEN** the eager run creates no list and writes no task for that launch, exactly as the periodic pass would decline to on the same condition
