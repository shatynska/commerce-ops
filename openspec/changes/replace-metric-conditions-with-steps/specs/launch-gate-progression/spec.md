## MODIFIED Requirements

### Requirement: A recurring pass advances every launch whose gate may open

The system SHALL, on a recurring schedule, advance each launch that has not reached the final gate past its current gate where that gate may open. Where the gate opens, the system SHALL consider the resulting launch again, and SHALL continue while gates keep opening, so that a launch whose conditions have been met for several consecutive gates reaches the furthest gate its recorded state permits within one pass rather than one pass per gate.

The pass SHALL establish that a gate may open **before** commanding the advance, rather than commanding it and treating the refusal as the answer. That judgement SHALL be made from the same facts the advance itself is judged on — every condition the served playbook attaches to the gate, weighed against the launch's own recorded step outcomes and approvals — and SHALL be made by the launch, so that the pass and the advance cannot disagree about whether a gate may open. It SHALL NOT be derived from the launch report, whose awaiting-confirmation flag is false for an automatic gate whatever its conditions' state. `launch-journal` requires every refused advance to be journaled with the conditions that blocked it, and a pass that commanded an advance for every launch on every run would append that entry hundreds of times a day per launch — burying, in the record kept for people to read, the refusals that record a real attempt. A gate whose conditions the pass reads as unsatisfied SHALL therefore produce no command and no journal entry.

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
