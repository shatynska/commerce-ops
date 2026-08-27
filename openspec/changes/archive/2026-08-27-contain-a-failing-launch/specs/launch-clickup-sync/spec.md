## ADDED Requirements

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

## MODIFIED Requirements

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
