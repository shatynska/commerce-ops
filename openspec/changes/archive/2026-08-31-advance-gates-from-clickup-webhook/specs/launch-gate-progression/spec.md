## MODIFIED Requirements

### Requirement: A recurring pass advances every launch whose gate may open

The system SHALL, on a recurring schedule, advance each launch that has not reached the final gate past its current gate where that gate may open. Where the gate opens, the system SHALL consider the resulting launch again, and SHALL continue while gates keep opening, so that a launch whose conditions have been met for several consecutive gates reaches the furthest gate its recorded state permits within one pass rather than one pass per gate.

The pass SHALL establish that a gate may open **before** commanding the advance, rather than commanding it and treating the refusal as the answer. That judgement SHALL be made from the same facts the advance itself is judged on — every condition the served playbook attaches to the gate, weighed against the launch's own recorded step outcomes, metric attestations and approvals — and SHALL be made by the launch, so that the pass and the advance cannot disagree about whether a gate may open. It SHALL NOT be derived from the launch report, which states each served step's recorded outcome but states neither a gate's authored metric conditions nor whether they have been attested, and whose awaiting-confirmation flag is false for an automatic gate whatever its conditions' state. `launch-journal` requires every refused advance to be journaled with the conditions that blocked it, and a pass that commanded an advance for every launch on every run would append that entry hundreds of times a day per launch — burying, in the record kept for people to read, the refusals that record a real attempt. A gate whose conditions the pass reads as unsatisfied SHALL therefore produce no command and no journal entry.

Advancement is a convergence pass and not a consequence of recording an outcome: the pass SHALL reach the same launch state whether the conditions became satisfied through a recorded step outcome, a recorded metric attestation, a recorded approval, or a change to the served playbook. A gate therefore opens no later than one pass interval after its last condition is met. Within this capability, advancement SHALL be caused by this pass and by a recorded decision (below), and by nothing else. In particular this capability SHALL NOT advance a launch as part of recording a step outcome, so that a launch's position is never a side effect of a completion arriving — **with one named exception**: the ClickUp webhook's own recording of a step outcome MAY also trigger the same advance-and-ask cascade for that launch, run immediately rather than waiting for the pass. This exception is narrow and procedural — it names one call site, not a new advancement rule — and does not generalize: every other path that records a step outcome (the ClickUp reconciliation pass, the automation pass, and an automated result's confirmation) remains fully bound by the SHALL NOT, exactly as before. A launch the webhook's trigger reaches is still judged, advanced and journaled by the same rules this requirement states throughout — read-before-command, one gate at a time, silent on an unsatisfied condition — the exception concerns only *when* the cascade is invoked, not *how* it decides or acts once invoked.

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

#### Scenario: Recording an outcome does not itself advance a launch

- **WHEN** a step outcome is recorded that satisfies the last outstanding condition on a launch's current gate
- **THEN** the launch's current gate is unchanged until a pass or a recorded decision advances it, unless it was recorded through the ClickUp webhook, which may also trigger the cascade immediately as the scenario below describes

#### Scenario: A ClickUp webhook delivery may trigger an advance-and-ask cascade for the launch it completes

- **WHEN** a step outcome recorded through the ClickUp webhook satisfies the last outstanding condition on a launch's current gate
- **THEN** the same advance-and-ask cascade the pass runs for that launch MAY be triggered immediately, rather than waiting for the next pass, and every rule this requirement and the requirements below state about how a gate may open, how a decision is asked for, and how often, apply to that cascade exactly as they apply to the pass's own

#### Scenario: A launch is not advanced past the final gate

- **WHEN** the pass runs while a launch stands at the final gate of the sequence
- **THEN** no advance is commanded for that launch

### Requirement: A decision records the approval and reports what it did

Pressing an approving control SHALL record an approving `GateApproval` for the launch's current gate and SHALL then attempt the advance immediately, rather than leaving it to the next pass, so that the decider is told what their decision did. Pressing a rejecting control SHALL record a rejecting approval, SHALL leave the gate closed, and SHALL NOT attempt an advance.

The reply to the decider SHALL be derived from the launch as it stands once the cascade this decision runs under the lock has finished, not from that path's own advance alone: where the pass crossed the approved gate first, the gate did open, and a reply naming a condition on some later gate would tell the decider their decision failed when it did not. The reply SHALL state whether the gate they approved opened, and where it did not, SHALL state why — including the case where the approval was recorded but a condition became unsatisfied between the ask and the decision.

A decision SHALL be acknowledged within Slack's timeout independently of whether the recording and advance it triggers have completed.

A decision arriving while the served playbook cannot hold a launch SHALL be refused and SHALL record no approval, and the decider SHALL be told why. The pass stands down in that state rather than acting on a set that is being authored, and a decision recorded against it would commit a person to a gate the system has declined to evaluate.

A decision naming the final gate of the sequence SHALL be refused and SHALL record no approval, for the reason the ask requirement gives: this capability does not obtain that gate's approval, and recording one without the posture `launch-instance` requires would be rejected in any case.

A decision naming a gate that is no longer the launch's current gate SHALL be refused and SHALL record no approval: the gate it was asked about has since moved, and recording an approval against it would attach a human decision to a commitment point the launch has already passed or not yet reached.

A launch SHALL be advanced by one path at a time. The decision path, the recurring pass, and the ClickUp webhook's own advance-and-ask trigger SHALL NOT advance the same launch concurrently, so that a single gate crossing is never attempted twice and the consequences reserved for one crossing are never produced twice.

#### Scenario: An approving decision opens the gate and says so

- **WHEN** an active person presses the approving control for a gate whose every other condition is satisfied
- **THEN** an approving approval naming that person is recorded, the gate opens, and the reply states that it opened

#### Scenario: A rejecting decision keeps the gate closed

- **WHEN** an active person presses the rejecting control
- **THEN** a rejecting approval naming that person is recorded, no advance is attempted, the gate is unchanged, and the reply states that the gate stays closed

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
