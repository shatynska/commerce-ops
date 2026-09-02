# launch-gate-progression Specification

## Purpose
Moves a launch through the gate sequence: a recurring pass that advances every launch whose current gate may open, and the Slack exchange by which a gate requiring human confirmation obtains its approval. This is what makes `launch-instance`'s gate rules do something rather than merely be defined.

## Requirements

### Requirement: A recurring pass advances every launch whose gate may open

The system SHALL, on a recurring schedule, advance each launch that has not reached the final gate past its current gate where that gate may open. Where the gate opens, the system SHALL consider the resulting launch again, and SHALL continue while gates keep opening, so that a launch whose conditions have been met for several consecutive gates reaches the furthest gate its recorded state permits within one pass rather than one pass per gate.

The pass SHALL establish that a gate may open **before** commanding the advance, rather than commanding it and treating the refusal as the answer. That judgement SHALL be made from the same facts the advance itself is judged on — every condition the served playbook attaches to the gate, weighed against the launch's own recorded step outcomes and approvals — and SHALL be made by the launch, so that the pass and the advance cannot disagree about whether a gate may open. It SHALL NOT be derived from the launch report, whose awaiting-confirmation flag is false for an automatic gate whatever its conditions' state. `launch-journal` requires every refused advance to be journaled with the conditions that blocked it, and a pass that commanded an advance for every launch on every run would append that entry hundreds of times a day per launch — burying, in the record kept for members to read, the refusals that record a real attempt. A gate whose conditions the pass reads as unsatisfied SHALL therefore produce no command and no journal entry.

Advancement is a convergence pass and not a consequence of recording an outcome: the pass SHALL reach the same launch state whether the conditions became satisfied through a recorded step outcome, a recorded approval, or a change to the served playbook. A gate therefore opens no later than one pass interval after its last condition is met. Within this capability, advancement SHALL be caused by this pass and by a recorded decision (below), and by nothing else. In particular this capability SHALL NOT advance a launch as part of recording a step outcome, so that a launch's position is never a side effect of a completion arriving — **with one named exception**: the ClickUp webhook's own recording of a step outcome MAY also trigger the same advance-and-ask cascade for that launch, run immediately rather than waiting for the pass. This exception is narrow and procedural — it names one call site, not a new advancement rule — and does not generalize: every other path that records a step outcome (the ClickUp reconciliation pass, the automation pass, and an automated result's confirmation) remains fully bound by the SHALL NOT, exactly as before. A launch the webhook's trigger reaches is still judged, advanced and journaled by the same rules this requirement states throughout — read-before-command, one gate at a time, silent on an unsatisfied condition — the exception concerns only *when* the cascade is invoked, not *how* it decides or acts once invoked.

A launch left where it is because a condition is unsatisfied is the ordinary case, not a fault, and SHALL NOT be reported as a failure of the pass.

#### Scenario: An automatic gate opens once its conditions are satisfied

- **WHEN** the pass runs against a launch whose current gate opens automatically and every blocking condition attached to it is satisfied
- **THEN** the gate opens and the launch's current gate becomes the next gate in the sequence

#### Scenario: Consecutive open gates are crossed in one pass

- **WHEN** the pass runs against a launch for which the conditions of its current gate and of the gate after it are both satisfied and neither requires confirmation
- **THEN** both gates open on that pass and the launch's current gate becomes the gate after them

#### Scenario: A launch with an unsatisfied condition is left where it is, silently

- **WHEN** the pass runs against a launch whose current gate has an unsatisfied blocking condition
- **THEN** the launch's current gate is unchanged, no advance is commanded, no refused-advance entry is journaled, and the pass is not failed by it

#### Scenario: A gate held by an unresolved metric step is left where it is

- **WHEN** the pass runs against a launch whose current gate carries a blocking step declaring a metric identifier, and that step has no satisfying outcome recorded
- **THEN** the launch's current gate is unchanged, exactly as for any other unresolved blocking step

#### Scenario: Recording an outcome does not itself advance a launch

- **WHEN** a step outcome is recorded that satisfies the last outstanding condition on a launch's current gate
- **THEN** the launch's current gate is unchanged until a pass or a recorded decision advances it, unless it was recorded through the ClickUp webhook, which may also trigger the cascade immediately as the scenario below describes

#### Scenario: A ClickUp webhook delivery may trigger an advance-and-ask cascade for the launch it completes

- **WHEN** a step outcome recorded through the ClickUp webhook satisfies the last outstanding condition on a launch's current gate
- **THEN** the same advance-and-ask cascade the pass runs for that launch MAY be triggered immediately, rather than waiting for the next pass, and every rule this requirement and the requirements below state about how a gate may open, how a decision is asked for, and how often, apply to that cascade exactly as they apply to the pass's own

#### Scenario: A launch is not advanced past the final gate

- **WHEN** the pass runs while a launch stands at the final gate of the sequence
- **THEN** no advance is commanded for that launch

### Requirement: The pass stands down while the playbook cannot hold a launch

Readiness SHALL be determined once, before the walk begins, rather than per launch. The pass SHALL decline to run while the served playbook is not ready — while any gate holds no active blocking step — advancing no launch, commanding nothing, and posting no ask. A playbook still being authored is an expected stage of a deployment being set up rather than an outage, so the pass SHALL be recorded as having **succeeded**: `scheduled-jobs` records only whether a run succeeded, and recording a failure would put a working deployment into retry and overdue reporting for a condition retrying cannot resolve. The stand-down and the gates causing it SHALL be logged.

This is the treatment `launch-clickup-sync` gives the same condition, and it carries the same accepted consequence for the same reason: because each stood-down pass refreshes the work's last success, overdue reporting does not fire during a stand-down, and this capability raises no signal of its own. The condition is reported instead by the daily briefing, which names the unheld gates on every run while they persist.

#### Scenario: An unready playbook stands the pass down without failing it

- **WHEN** the pass runs while a gate holds no active blocking step
- **THEN** no launch is advanced and no ask is posted
- **AND** the run is recorded as succeeded, with the stand-down and the unheld gates logged

#### Scenario: A ready playbook is served normally

- **WHEN** the pass runs while every gate holds at least one active blocking step
- **THEN** launches are advanced as the requirements above describe

### Requirement: One launch's failure does not stop the other launches being advanced

The pass SHALL attempt every launch it walks on every run it makes, whatever happened while it was working on the launches before it. A failure raised while advancing one launch SHALL be contained to that launch and SHALL NOT prevent any other launch from being attempted on the same run. Each contained failure SHALL be reported as it happens, naming the product its launch is for and carrying what was raised.

Because the pass writes as it walks, a contained failure SHALL be followed by restoring the shared store to a state the next launch can be attempted against. Where it cannot be restored, the walk SHALL end rather than continue against a store that would persist nothing while appearing to succeed.

A run in which one or more launches failed SHALL be reported as a failed run, and the error that fails it SHALL name every launch that failed, by the identifier of the product each launch is for. A failed **ask delivery** is the one stated exception among failures and SHALL NOT fail the run — see the ask requirement below, which gives the reason. A gate declining to open is not a failure at all, and is treated below.

A gate declining to open SHALL end the cascade as a **stop**, never as a failure. The advance the launch refuses is the cascade reaching its stopping condition by a different route than the pass's read predicted — the race the read-before-command rule knowingly leaves open — so the crossings already made SHALL stand, the refusal SHALL be journaled as `launch-journal` requires, and the run SHALL NOT be failed by it. Undoing the crossings would discard work that was valid, and would discard with it the one record that a condition ever blocked an advance, which no later pass can reconstruct once that condition is satisfied.

A cascade that fails part-way — for any reason other than a gate declining to open — SHALL leave the launch at the gate it stood at when the pass reached it — every crossing made during that cascade is undone, not only the one that failed. This is deliberately unlike `launch-clickup-sync`'s rule that work completed for a launch before its failure stands, and the difference is what the work costs to redo: that pass's unit is a launch's whole projection, many calls against a rate budget, where discarding completed work is expensive and externally visible; a crossing here is a cheap local write with no external effect, which the next pass redoes. An atomic unit is worth more than a partially-advanced launch nobody chose.

A recorded approval SHALL NOT be undone by the failure of the cascade it triggered. A decision is a fact about what a member did; discarding it would leave that member believing they had approved, while the record that suppresses repeated asks — written before the decision and outside its work — would keep the gate from being asked about again.

Containment covers errors raised by the work itself. It SHALL NOT contain a cancellation or a shutdown of the process running the pass.

#### Scenario: A failing launch does not stop the others

- **WHEN** advancing one launch raises an error and other launches remain to be walked
- **THEN** the remaining launches are still attempted, the failure is reported naming that launch's product, and the run is reported as failed

#### Scenario: A gate declining mid-cascade stops it without undoing what it crossed

- **WHEN** a launch crosses one gate and the next declines to open, a condition having stopped being satisfied since the pass read it
- **THEN** the crossing already made stands, the refusal is journaled with the conditions that blocked it, and the run is not failed

#### Scenario: A cascade failing part-way leaves the launch where it started

- **WHEN** a launch crosses one gate and the attempt at the next raises
- **THEN** the launch stands at the gate it was at when the pass reached it, the crossing already made having been undone

#### Scenario: A failed cascade does not discard the approval that triggered it

- **WHEN** an approving decision is recorded and the cascade it triggers then fails
- **THEN** the approval stands, and the gate it approves is crossed by a later pass rather than being asked about again

#### Scenario: An unrestorable store ends the walk

- **WHEN** a contained failure leaves the shared store in a state that cannot be restored
- **THEN** the walk ends rather than continuing against it, the run is reported as failed, and the error names the launches contained up to that point

#### Scenario: A shutdown stops the walk

- **WHEN** the process running the pass is cancelled part-way through the walk
- **THEN** the walk stops rather than recording the cancellation against a product and continuing

### Requirement: A gate awaiting only confirmation is asked about in Slack

Where a launch's current gate requires confirmation, every blocking condition attached to it is satisfied, and no approving approval has been recorded for it, the system SHALL ask for that approval as a message delivered to Slack, as a reply within that launch's Slack thread — establishing the thread first if it does not yet exist. The message SHALL name the product and the gate, SHALL carry the controls by which the decision is made, and SHALL tag the launch's submitter: a gate carries no confirmer of its own.

The ask SHALL be made only for a gate that is awaiting confirmation in exactly the sense `launch-instance` defines: a gate with an unsatisfied blocking condition SHALL NOT be asked about, because the decision it would request cannot yet be acted on.

**The final gate of the sequence SHALL NOT be asked about**, although it requires confirmation. Its approval must name a steady-state posture and its opening stamps the catalog, and this capability obtains neither; a launch standing there is left for the change that adds them. The exclusion is stated here rather than left to which launches the pass happens to walk, so that it is a property of the capability and not of a collaborator's filtering.

A delivery that fails SHALL be reported and SHALL leave the gate eligible to be asked about again, SHALL NOT be recorded as though the ask had been delivered, and SHALL NOT fail the run. A Slack outage is not a fault of the advancing this pass exists to do, and failing the run for it would put the deployment into retry and overdue reporting for every pass the outage lasts.

#### Scenario: A satisfied confirmation gate is asked about

- **WHEN** the pass runs against a launch whose current gate requires confirmation, has every blocking condition satisfied, and has no approving approval recorded
- **THEN** a message naming the product and the gate, tagging the launch's submitter, is posted as a reply within the launch's Slack thread, carrying the decision controls

#### Scenario: The final gate is not asked about

- **WHEN** the pass runs against a launch standing at the final gate of the sequence with every blocking condition satisfied and no approval recorded
- **THEN** no ask is posted, although that gate requires confirmation

#### Scenario: A gate with unsatisfied conditions is not asked about

- **WHEN** the pass runs against a launch whose current gate requires confirmation but has an unsatisfied blocking condition
- **THEN** no ask is posted for that gate

#### Scenario: An undelivered ask is reported, retried, and does not fail the run

- **WHEN** posting the ask fails
- **THEN** the failure is reported, no delivery is recorded, the run is not failed by it, and the ask is attempted again on the next pass while the gate is still awaiting confirmation

#### Scenario: An ask for a launch with no thread yet establishes one

- **WHEN** the pass asks about a gate for a launch that has no Slack thread reference
- **THEN** an anchor message is posted for that launch before the ask, and the ask is delivered as a reply within the newly established thread

### Requirement: A gate is asked about at most once a day

The system SHALL record, for a launch and a gate, when it was last asked about or last decided against. A record of a **delivery** SHALL be written only after that delivery succeeds; a rejecting decision writes its own, having delivered nothing. An ask SHALL be made only where no such record younger than twenty-four hours exists for that launch and gate.

One rule SHALL cover three cases, which differ only in what happened after the previous ask: a gate is asked about once rather than on every pass; a gate whose ask nobody answered is asked about again the following day; and a gate whose approval was **rejected** is not proposed again until a day has passed. The last mirrors the cool-off `launch-step-automation` applies to a rejected automated result, and exists for the reason that requirement gives — without it one rejection buys a fresh Slack message on every pass, forever.

Recording a rejecting decision SHALL refresh the record, so the day is counted from the decision rather than from the ask that prompted it. The rejecting approval and that refresh SHALL land together: unlike a delivery, where a lost write costs one duplicate message, a lost refresh here re-proposes a gate a member has just declined, which is the case this rule exists to prevent.

The record SHALL be held in storage rather than in the memory of the process running the pass, so that restarting the process does not resume the flood the record exists to prevent.

#### Scenario: A gate asked about is not asked about again on the next pass

- **WHEN** an ask for a gate was delivered and the pass runs again within twenty-four hours while the gate is still awaiting confirmation
- **THEN** no second ask is posted

#### Scenario: An unanswered gate is asked about again the next day

- **WHEN** an ask for a gate was delivered more than twenty-four hours ago and the gate is still awaiting confirmation
- **THEN** the ask is posted again

#### Scenario: A rejection and its cool-off refresh land together or not at all

- **WHEN** a rejecting decision is recorded and the cool-off refresh fails
- **THEN** neither the rejecting approval nor the refresh stands, and the decider is told the decision was not recorded

#### Scenario: A rejected gate is not re-proposed the same day

- **WHEN** a rejecting decision is recorded for a gate and the pass runs again within twenty-four hours
- **THEN** no ask is posted for that gate

#### Scenario: A restart does not resume asking

- **WHEN** the process running the pass restarts and runs a pass while a delivered ask is less than twenty-four hours old
- **THEN** no second ask is posted

### Requirement: Only a known, active member may approve a gate

The system SHALL accept a gate decision only from a Slack identity the membership knows and that is active. A decision from an unrecognised or deactivated identity SHALL be refused, SHALL record no approval, SHALL leave the gate as it stands, and SHALL tell the decider it was refused.

The member the membership resolves SHALL be recorded as the approval's named approver, so that every recorded approval names a real member on the membership and no approver is ever supplied by the system itself.

Decisions arrive on the same verified `product_agent` Slack surface `launch-entry` already uses, so a decision whose authenticity cannot be established never reaches this rule.

Administrative authority on the membership SHALL NOT be required. Members `admin` marks who may administer the system — the membership and the playbook — and a launch commitment is not an act of system administration; requiring it would make the two authorities the same concept, which no requirement in this repository states them to be.

The membership this rule is evaluated against is supplied by the caller, and SHALL answer to **one** stated shape: it SHALL be able to answer who the membership carries, **deactivated entries included**, since both halves of "known and active" are decided here rather than by whatever supplies the membership. A collaborator that cannot answer that — including no collaborator at all — SHALL be refused as a defect of *wiring*: a named error identifying what was supplied and what was expected, raised before the deciding identity is judged. That refusal SHALL NOT be reachable as a decision refusal, SHALL NOT be resolved into "the membership does not carry that identity", SHALL NOT be reported to the decider as a fact about their identity, and SHALL be reported where operators see faults. The decider SHALL still be told their decision was not processed.

#### Scenario: An unknown identity cannot approve

- **WHEN** a gate decision arrives from a Slack identity the membership does not know
- **THEN** it is refused, no approval is recorded, the gate is unchanged, and the decider is told

#### Scenario: A deactivated member cannot approve, and is told which fact refused them

- **WHEN** a gate decision arrives from a Slack identity belonging to a member the membership holds as inactive
- **THEN** it is refused as inactive rather than as unknown, no approval is recorded, and the gate is unchanged

#### Scenario: A non-administrator may approve

- **WHEN** a gate decision arrives from a Slack identity belonging to an active member the membership does not mark as an administrator
- **THEN** the approval is recorded naming that member

#### Scenario: An absent members collaborator is refused the same way, not silently

- **WHEN** a gate decision is judged with no members collaborator supplied at all
- **THEN** it is refused as the same wiring fault, by a named error, and not reported to the decider as a fact about their identity

#### Scenario: An unreadable members collaborator is refused by name

- **WHEN** a gate decision is judged against a members collaborator that cannot answer who the membership carries
- **THEN** it is refused with a named error identifying the collaborator supplied and the shape expected, no approval is recorded, and the decider is told their decision was not processed without being told anything about their own members entry

### Requirement: A decision records the approval and reports what it did

Pressing an approving control SHALL record an approving `GateApproval` for the launch's current gate and SHALL then attempt the advance immediately, rather than leaving it to the next pass, so that the decider is told what their decision did. Pressing a rejecting control SHALL record a rejecting approval, SHALL leave the gate closed, and SHALL NOT attempt an advance.

The reply to the decider SHALL be derived from the launch as it stands once the cascade this decision runs under the lock has finished, not from that path's own advance alone: where the pass crossed the approved gate first, the gate did open, and a reply naming a condition on some later gate would tell the decider their decision failed when it did not. The reply SHALL state whether the gate they approved opened, and where it did not, SHALL state why — including the case where the approval was recorded but a condition became unsatisfied between the ask and the decision.

A decision SHALL be acknowledged within Slack's timeout independently of whether the recording and advance it triggers have completed.

A decision arriving while the served playbook cannot hold a launch SHALL be refused and SHALL record no approval, and the decider SHALL be told why. The pass stands down in that state rather than acting on a set that is being authored, and a decision recorded against it would commit a member to a gate the system has declined to evaluate.

A decision naming the final gate of the sequence SHALL be refused and SHALL record no approval, for the reason the ask requirement gives: this capability does not obtain that gate's approval, and recording one without the posture `launch-instance` requires would be rejected in any case.

A decision naming a gate that is no longer the launch's current gate SHALL be refused and SHALL record no approval: the gate it was asked about has since moved, and recording an approval against it would attach a human decision to a commitment point the launch has already passed or not yet reached.

A launch SHALL be advanced by one path at a time. The decision path, the recurring pass, and the ClickUp webhook's own advance-and-ask trigger SHALL NOT advance the same launch concurrently, so that a single gate crossing is never attempted twice and the consequences reserved for one crossing are never produced twice.

#### Scenario: An approving decision opens the gate and says so

- **WHEN** an active member presses the approving control for a gate whose every other condition is satisfied
- **THEN** an approving approval naming that member is recorded, the gate opens, and the reply states that it opened

#### Scenario: A rejecting decision keeps the gate closed

- **WHEN** an active member presses the rejecting control
- **THEN** a rejecting approval naming that member is recorded, no advance is attempted, the gate is unchanged, and the reply states that the gate stays closed

#### Scenario: A decision whose gate the pass crossed first still reports it opened

- **WHEN** an approving decision is recorded and the recurring pass crosses that gate before the decision path acquires the lock
- **THEN** the reply states that the gate opened, rather than reporting the decision's own advance as having opened nothing

#### Scenario: A decision arriving during a stand-down is refused

- **WHEN** a decision arrives while the served playbook cannot hold a launch
- **THEN** it is refused, no approval is recorded, and the decider is told why

#### Scenario: A decision on a condition that has since regressed reports why

- **WHEN** an approving decision arrives after a blocking condition on that gate has stopped being satisfied
- **THEN** the approval is recorded, the gate does not open, and the reply names the condition that now blocks it

#### Scenario: A decision naming the final gate is refused

- **WHEN** a decision arrives naming the final gate of the sequence
- **THEN** it is refused, no approval is recorded, and the decider is told

#### Scenario: A decision is acknowledged before its work completes

- **WHEN** a decision arrives and the recording and advance it triggers have not yet completed
- **THEN** it is acknowledged within Slack's timeout, and the reply reporting what it did follows separately

#### Scenario: A decision on a gate the launch has left is refused

- **WHEN** a decision arrives naming a gate that is not the launch's current gate
- **THEN** it is refused, no approval is recorded, and the decider is told

#### Scenario: A decision and the pass do not cross the same gate twice

- **WHEN** a decision's advance and a scheduled pass would act on the same launch at the same time
- **THEN** one of them advances the launch and the other acts on the launch as that advance left it

#### Scenario: A decision and a webhook-triggered advance do not cross the same gate twice

- **WHEN** a decision's advance and the ClickUp webhook's advance-and-ask trigger would act on the same launch at the same time
- **THEN** one of them advances the launch and the other acts on the launch as that advance left it
