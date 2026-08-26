## MODIFIED Requirements

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

### Requirement: Completion flows from ClickUp to the launch as a recorded outcome

The system SHALL record, against the mapped step, a `Satisfied` outcome when its ClickUp task reaches a status of the closed type, and an `InProgress` outcome when a previously closed task is reopened — in both cases with provenance naming `clickup` as the source, the ClickUp actor where the delivery identifies one, and the task as evidence. "Previously closed" means last observed closed, per the retained observed state the reconciliation requirement defines — a reopening whose closing was never observed records nothing. A newly projected task's retained observed state starts as not closed. These recordings apply only to a step the served playbook defines: a retired step's mapped task records nothing, as the retired-step requirement below specifies. No other outcome SHALL be produced from ClickUp state. The system SHALL NOT write task status to ClickUp: completion travels one way, from ClickUp to the launch.

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

### Requirement: The reconciliation pass records completions and reopenings the webhook missed

The system SHALL periodically, on a declared schedule and without any request from outside the deployment, read the ClickUp state of every active launch's mapped tasks and record any completion or reopening whose webhook delivery was missed, with the same outcome mapping, source, and evidence as webhook intake; the recorder is the reconciliation's own identity, since a read exposes no acting user. A missed completion or reopening SHALL be detected as a transition of the task's observed closed state: the system SHALL retain, per mapped task, the closed state it last observed — updated by every observation, webhook and reconciliation alike — and SHALL record an outcome only when the state read from ClickUp differs from that retained state. Recording applies only to steps the served playbook defines: a retired step's mapped task is still observed — its retained state updated — but records nothing, as the retired-step requirement below specifies. A task showing no transition SHALL NOT cause any recording, whatever outcome the step carries.

The pass does not run at all while the served playbook cannot hold a launch, as the stand-down requirement specifies; a completion missed during a stand-down is recorded by the first pass to run once the playbook is ready, from the transition its retained observed state still shows.

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
