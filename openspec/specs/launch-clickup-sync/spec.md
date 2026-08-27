# launch-clickup-sync Specification

## Purpose
The launch-clickup-sync capability keeps a launch's human work and ClickUp in agreement in both directions: the system projects each launch's active `human` steps into a dedicated ClickUp list — each task carrying the step's name, its description and the people responsible for it, with a due date derived from the launch schedule — and completion recorded in ClickUp flows back as recorded step outcomes, through webhook deliveries when they arrive and through a periodic reconciliation pass when they do not.

## Requirements

### Requirement: Each launch is projected into its own ClickUp list

The system SHALL maintain one ClickUp list per launch, created inside a configured parent folder and named with the product's name and SKU as the catalog records them (the product identifier itself is opaque and never parsed for meaning), and SHALL record the association between the launch and its list. A launch whose list already exists SHALL NOT get a second one. A launch that has reached its final gate (`graduated`) SHALL NOT be projected or reconciled. When the parent folder is not configured, projection SHALL fail in a way the scheduled-work machinery observes as a failed run, rather than being silently skipped.

A pass that stands down because the served playbook cannot hold a launch SHALL create nothing and write nothing, as the stand-down requirement specifies; that is a decline rather than the silent skip this requirement forbids, and it is recorded as a successful run.

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

The system SHALL project, into the launch's list, one ClickUp task per step of the served playbook whose kind is `human`, whose status is `active`, and whose hazard is not `prohibited-tactic`, and SHALL record the association between each step and its task. The served playbook is live, so a step activated after the launch started is projected on the next pass like any other. `automated` steps, steps that are not `active`, steps with the `prohibited-tactic` hazard, and gate metric conditions SHALL NOT be projected. A step whose task already exists SHALL NOT get a second one. A step whose mapped task no longer exists in ClickUp SHALL be re-projected — a new task created and the mapping replaced — unless the step's recorded outcome is already terminal (`Satisfied`, `Refused`, or `NotApplicable`), in which case the vanished task SHALL be left unrecreated.

A projected task SHALL be named with the step's **name**, then ` · ` (a space, a middle dot, a space), then the step's identifier, so that the list states the work while each task remains traceable to the step it stands for. Before any shortening under the rule below, the name SHALL consist of exactly those three parts and no further element: the step's discipline SHALL NOT be appended as a further element of the name. The identifier's own second segment already carries it, and name width spent restating it costs the reader the wording this name exists to surface. This constrains what the system composes, not what a step's name happens to say — a name whose own wording mentions its discipline is unaffected. The name SHALL NOT be the sole record of that association: a task renamed or edited in ClickUp SHALL still resolve to its step, because the association is the recorded mapping and never the name.

A projected task's body SHALL be the step's **description** where the step carries one. Where a step carries no description the system SHALL compose no body at all, and SHALL neither write nor rewrite the task's body — leaving whatever stands there. Composing an *empty* body instead would destroy work: a task projected before this change whose name was shortened carries the step's full former text in its body, written by the system and therefore matching its retained value, so a rule that rewrote it to empty would leave that task stating its work nowhere. The body is no longer a place the name overflows into: the step's own two fields map onto the task's two, which is what having them separate is for.

A projected task SHALL be assigned to the step's assignees, each resolved to the ClickUp user the roster records for that person. Assignment SHALL be reconciled on later passes as well as at creation, so that a step whose assignees change reaches its task, and so that tasks projected before steps had assignees stop being unowned — which is the problem this field exists to solve, and solving it only for new work would leave every in-flight launch as it is. The system SHALL retain, with the mapping, the assignees it last set, exactly as it retains the name and the body it last composed. A person's own assignment change SHALL be respected the way an edited name or body is: where a task's assignees differ from what the system last set, the system SHALL NOT overwrite them. A mapping holding no retained assignees — every mapping made before this change — SHALL be treated as having last been set to nobody, so a task the system left unassigned heals to its step's assignees while one somebody has already assigned is treated as person-edited and left alone. Assignees are the one field where that reading is right: an unassigned task is the failure this projection exists to fix, so silence there is the system's own doing rather than an edit worth preserving. An assignee the roster carries without a ClickUp user id SHALL be skipped for assignment — the task is still created, still carries its remaining assignees, and the omission SHALL be reported as a warning-level application log record naming the step, the person and the task rather than silently dropped — the pass itself succeeds, since a failed run would hide a data gap behind a retry, and `scheduled-jobs` records only whether a run succeeded, so the run record is not where this can be carried.

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

- **WHEN** a `human` step is activated after a launch started and the next pass runs
- **THEN** a task is created for it in the launch's list like any other step's

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
