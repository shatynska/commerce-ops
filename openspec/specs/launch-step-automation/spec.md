# launch-step-automation Specification

## Purpose
Runs the code an `automated` step names, and decides what becomes of what that code produced: recorded against the launch straight away, or held until a person accepts it. This is what makes `kind`, `handler` and `needs_confirmation` do something rather than merely be declared.

## Requirements

### Requirement: An automated step's handler is invoked by recurring work

The system SHALL invoke registered step handlers from recurring work that runs inside the deployment, declaring its schedule and tolerance as `scheduled-jobs` requires of every piece of recurring work. Each pass SHALL consider every launch that has not graduated, and within each launch every step of its served playbook whose kind is `automated`.

A pass SHALL invoke the handler of such a step only where all of the following hold: the step's recorded outcome is not one the step's hazard permits as terminal; no pending result stands for it; and it is not within the cool-off this specification places after a rejection. `human` steps, steps that are not `active`, and steps already at a permitted terminal outcome SHALL NOT be invoked.

Invocation SHALL NOT be reachable from outside the deployment.

#### Scenario: An unresolved automated step is invoked

- **WHEN** a pass runs over a launch whose served playbook carries an `active` `automated` step with no recorded outcome, no pending result and no recent rejection
- **THEN** that step's named handler is invoked

#### Scenario: A human step is never invoked

- **WHEN** a pass runs over a launch whose served playbook carries an `active` `human` step
- **THEN** no handler is invoked for it, whether or not it needs confirmation

#### Scenario: A resolved step is not invoked again

- **WHEN** a pass runs over an `automated` step whose recorded outcome is one its hazard permits as terminal
- **THEN** its handler is not invoked and its recorded outcome is left unchanged

#### Scenario: A graduated launch is left alone

- **WHEN** a pass runs and a launch has reached `graduated`
- **THEN** no handler is invoked for any of its steps

### Requirement: A handler receives the step, the launch and the product, and attributes nothing

A handler SHALL be given the step definition it is resolving, a read of the launch it is resolving against, the catalog product that launch is for, and the moment the pass is running as of. The catalog product SHALL be resolved by the system and supplied to the handler, never fetched by the handler itself — a handler is a function of the context it is given and nothing else, which is what allows it to be exercised without a database and keeps the catalog read in one place rather than one place per handler.

A handler SHALL return an outcome from the `launch-playbook` outcome vocabulary together with the result it produced, expressed as text a person can read. The produced text SHALL NOT be empty: it becomes the recorded evidence, which `launch-instance` requires of every recording.

A handler with nothing conclusive to report SHALL say so through a **non-terminal** outcome whose reason states why — never by proposing a terminal outcome it cannot support, and never by failing. Of the three non-terminal outcomes only `Blocked` can itself carry a reason; where a handler proposes one that cannot, the produced text SHALL state the reason instead, so that a stalled step is legible rather than merely quiet.

A handler SHALL NOT supply its own recording provenance. The system SHALL construct the provenance for every outcome a handler produces, with source `automated`, naming the handler as what did the work, the moment of the run, and the produced result as the evidence. A handler therefore cannot record work as having come from a person, from ClickUp, or from an attestation.

#### Scenario: The product is supplied, not fetched

- **WHEN** a handler is invoked for a step on a launch
- **THEN** its context carries the catalog product that launch is for, resolved before the handler ran

#### Scenario: A produced outcome is attributed to the handler

- **WHEN** a handler returns a resolution and its outcome is recorded
- **THEN** the recorded provenance has source `automated`, names the handler, carries the moment of the run, and carries the produced result as its evidence

#### Scenario: A handler cannot claim another source

- **WHEN** a handler attempts to supply provenance of its own
- **THEN** the system rejects it and the provenance the system constructed stands

### Requirement: A non-terminal outcome is recorded directly and never held for a decision

Where the outcome a handler proposes is not terminal — `NotStarted`, `InProgress` or `Blocked`, none of which `launch-playbook` permits as terminal for any step — the system SHALL record it against the launch immediately with the provenance it constructed, **whatever the step's confirmation flag says**, and SHALL NOT store it as a pending result or seek a decision on it.

Confirmation exists so a person accepts a result. A non-terminal outcome is not a result: it is a handler reporting that the step has not been resolved, and holding it would ask a person to accept "in progress" — a proposal with nothing in it to agree or disagree with, which would then suppress re-invocation until they clicked. Recording it directly keeps the reason on the launch's own record, which is what makes a stalled automated step legible rather than merely quiet, and leaves the step eligible for the next pass.

#### Scenario: A non-terminal outcome on a confirmable step is recorded, not held

- **WHEN** a handler proposes `Blocked` with a reason for a step whose confirmation flag is true
- **THEN** the outcome is recorded against the launch with `automated` provenance, no pending result is stored, and no decision is requested

#### Scenario: A step reporting no progress is reconsidered on the next pass

- **WHEN** a handler proposes a non-terminal outcome for a step, and a later pass runs
- **THEN** the handler is invoked again for that step

### Requirement: A terminal outcome the step's hazard forbids is a handler fault, not a recording

Before storing or recording anything, the system SHALL check a **terminal** outcome a handler proposed against what the step's hazard permits, as `launch-playbook` defines it. A terminal outcome the hazard does not permit SHALL be treated exactly as a handler failure: nothing recorded, nothing stored, the fault reported naming the launch, the step, the handler and the offending outcome.

Checking at production time rather than at recording time is what keeps the fault visible. A `Refused` proposed for a `compliance-obligation` step, stored as a pending result and delivered, would fail only when a person pressed accept — and would then fail identically every time it was pressed, leaving a result that can never be settled.

#### Scenario: An impermissible proposal is refused before it is stored

- **WHEN** a handler proposes a terminal outcome the step's hazard does not permit
- **THEN** no outcome is recorded, no pending result is stored, and the fault is reported naming the launch, step, handler and outcome

### Requirement: An unregistered handler is reported and skipped, never fatal

Where an `active` `automated` step names a handler this deployment does not register, the pass SHALL skip that step, SHALL record no outcome for it, and SHALL report the step and the handler name it could not resolve. The pass SHALL continue with every other step and every other launch.

This is the same trade the startup handler report already settles: a step nothing can resolve is a deployment fault worth naming, never a reason to stop resolving everything else.

#### Scenario: A step naming an unregistered handler is skipped

- **WHEN** a pass reaches an `active` `automated` step whose named handler is not registered in this deployment
- **THEN** no outcome is recorded for it, the step and the handler name are reported, and the pass continues

### Requirement: A handler failure resolves nothing and does not stop the pass

Where invoking a handler fails — the handler raises, or the work it depends on is unavailable — the system SHALL record no outcome for that step, SHALL report the failure naming the launch, the step and the handler, and SHALL continue with the remaining steps and launches. A failure SHALL NOT be recorded as any outcome, `Blocked` included: a step nothing could evaluate has not been evaluated, and a crash recorded as a handler's own judgement that the step is blocked would hide the fault behind a plausible launch state.

A pass that completed its walk SHALL be recorded as a successful run whatever individual handlers or deliveries did, so that `scheduled-jobs`' retry and overdue reporting answer whether the pass is running, not whether every step within it resolved.

#### Scenario: A failing handler leaves the step untouched

- **WHEN** a handler raises while resolving a step
- **THEN** the step's recorded outcome is unchanged, the failure is reported naming the launch, step and handler, and the pass continues to the next step

#### Scenario: One failure does not abandon the remaining launches

- **WHEN** a handler fails for one launch and other launches have unresolved automated steps
- **THEN** those other launches are still walked in the same pass

#### Scenario: A completed walk is a successful run

- **WHEN** a pass walks every launch to completion while one handler failed and one delivery failed
- **THEN** the run is recorded as successful

### Requirement: A result needing no confirmation is recorded at once

Where the resolved step's confirmation flag is false, the system SHALL record the handler's outcome against the launch immediately, with the provenance it constructed. No decision is sought and nothing is held.

#### Scenario: An unconfirmed result is recorded directly

- **WHEN** a handler resolves a step whose confirmation flag is false
- **THEN** the outcome is recorded against the launch with `automated` provenance, and no decision is requested

### Requirement: A result needing confirmation is held until a person decides

Where the resolved step's confirmation flag is true **and the outcome the handler proposed is terminal**, the system SHALL NOT record that outcome. It SHALL store the produced result as a pending result against that launch and step — carrying the outcome the handler proposed, the produced text, the handler, and when it was produced — and SHALL seek a decision on it.

At most one pending result SHALL stand for a launch and step at any moment. A step awaiting a person is not a step awaiting more work, and a second result would leave two proposals and no way to say which was decided.

#### Scenario: A confirmable terminal result is held rather than recorded

- **WHEN** a handler proposes a terminal outcome for a step whose confirmation flag is true
- **THEN** no outcome is recorded against the launch, and a pending result is stored carrying the proposed outcome, the produced text, the handler and the moment it was produced

#### Scenario: A pending result suppresses re-invocation

- **WHEN** a pass runs while a pending result stands for a launch and step
- **THEN** that step's handler is not invoked and the pending result is left as it is

#### Scenario: Two overlapping passes cannot both produce a pending result

- **WHEN** two passes overlap and both would store a pending result for the same launch and step
- **THEN** exactly one pending result stands, and the step is left for a later pass

### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

The system SHALL deliver each pending result to Slack, naming the product, the step, the outcome the handler proposed and the produced text in full, and offering an accept and a reject decision.

A failure to deliver SHALL NOT discard the pending result and SHALL NOT record an outcome. The failure SHALL be reported, and the pending result SHALL remain available to be delivered again — the same decoupling the daily briefing keeps between assembling a report and delivering it.

#### Scenario: A pending result reaches Slack

- **WHEN** a pending result is stored
- **THEN** a Slack message is delivered naming the product, the step, the proposed outcome and the produced text, offering an accept and a reject decision

#### Scenario: Undelivered is not undone

- **WHEN** delivering a pending result to Slack fails
- **THEN** the pending result still stands, no outcome is recorded, and the delivery failure is reported

#### Scenario: An undelivered result is delivered again later

- **WHEN** a delivery failed and a later pass runs
- **THEN** delivery of that pending result is attempted again

### Requirement: Only a known, active person may decide a pending result

The system SHALL accept a decision on a pending result only from a Slack identity the roster knows and that is active. A decision from an unrecognised or deactivated identity SHALL be refused, SHALL record no outcome, SHALL leave the pending result standing, and SHALL tell the decider it was refused.

Decisions arrive on the same verified `product_agent` Slack surface `launch-entry` already uses, so a decision whose authenticity cannot be established never reaches this rule; and a decision SHALL be acknowledged within Slack's timeout independently of whether the recording it triggers has completed.

#### Scenario: An unknown identity cannot decide

- **WHEN** a decision arrives from a Slack identity the roster does not know
- **THEN** it is refused, no outcome is recorded, the pending result still stands, and the decider is told

#### Scenario: A deactivated person cannot decide

- **WHEN** a decision arrives from a Slack identity belonging to a person the roster holds as inactive
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

### Requirement: Accepting records the proposed outcome and names the accepter

Accepting a pending result SHALL record, against the launch, exactly the outcome the handler proposed, with source `automated`, naming the accepting person, carrying the moment of the decision, and carrying evidence that names both the handler that produced the result and the produced text itself. The pending result SHALL then be settled and SHALL no longer suppress re-invocation.

The source stays `automated` because the work was the handler's; who accepted it is what the recorder names; and the evidence names the handler so that the launch's own record answers what produced the accepted result, without depending on the pending-result store still holding the row.

The recording and the settlement SHALL both take effect, or neither: a settled result whose outcome was never recorded would be undecidable and unrecoverable.

#### Scenario: An accepted result becomes the step's outcome

- **WHEN** a known active person accepts a pending result proposing `Satisfied`
- **THEN** `Satisfied` is recorded for that step with source `automated`, naming the accepter and the moment of the decision, with evidence naming the handler and carrying the produced text

#### Scenario: A failed recording leaves the result decidable

- **WHEN** recording the outcome for an accepted pending result fails
- **THEN** the pending result is not settled and the decision can be made again

### Requirement: Rejecting does not terminate the step

Rejecting a pending result SHALL record a `Blocked` outcome against the launch, whose reason names the rejecting person and states that an automated result was rejected, with source `automated` and the rejecting person as the recorder. It SHALL settle the pending result as rejected, and SHALL leave the step available for a handler to resolve again on a later pass.

`Blocked` is chosen from among the non-terminal outcomes because it is the one that carries a reason, and a rejection whose reason was not recorded would leave the launch showing an unresolved step with nothing saying why. The source stays `automated` for the same reason acceptance does: the work being rejected was a handler's.

A rejection SHALL NOT be recorded as `Refused`. `Refused` is reserved by `launch-playbook` for a step whose hazard is `prohibited-tactic`, and means the tactic itself was recognised and declined; a person declining one produced result has said nothing about the step's permissibility. Nor SHALL it be recorded as `NotApplicable`, which is terminal and would close a step whose work still stands.

#### Scenario: A rejected result leaves the step live

- **WHEN** a known active person rejects a pending result
- **THEN** a `Blocked` outcome is recorded whose reason names the rejecter, with source `automated` and the rejecter as recorder, and the step is not at a terminal outcome

#### Scenario: Rejection is never a refusal

- **WHEN** a pending result for a step whose hazard is not `prohibited-tactic` is rejected
- **THEN** the recorded outcome is not `Refused` and is not `NotApplicable`

### Requirement: A rejected step is not re-proposed immediately

After a rejection, the system SHALL NOT invoke that step's handler again until a fixed cool-off has elapsed since the rejection. Once it has, a pass SHALL invoke the handler again.

Without a cool-off, rejecting one recommendation buys a fresh handler run on every pass thereafter, and a stream of Slack messages proposing much the same thing — so the cost of a person disagreeing would be unbounded. The cool-off is a fixed property of the system, not a configured one: it needs no per-deployment answer, and `runtime-configuration` requires a declared variable for anything that does.

#### Scenario: A rejected step is skipped within the cool-off

- **WHEN** a pass runs while a step's most recent settled result was rejected within the cool-off
- **THEN** that step's handler is not invoked

#### Scenario: A rejected step is offered to the handler again once the cool-off elapses

- **WHEN** a pass runs after the cool-off has elapsed since a step's rejection, and no pending result stands for it
- **THEN** that step's handler is invoked again

### Requirement: A pending result is decided once

The system SHALL settle a pending result on its first decision. A second decision on an already-settled result SHALL be refused, SHALL record nothing further, and SHALL leave the outcome the first decision recorded standing.

A decision arrives from Slack, where a delivery may be retried and a control may be pressed twice; a second decision that recorded a second outcome would let a rejection silently overwrite an acceptance.

#### Scenario: A repeated decision changes nothing

- **WHEN** a decision arrives for a pending result that has already been settled
- **THEN** it is refused, no further outcome is recorded, and the outcome recorded by the first decision stands

### Requirement: A decision on a step the playbook no longer serves is refused

Where a decision arrives for a pending result whose step the served playbook no longer defines — the step having been retired, or moved out of `active`, since the result was produced — the system SHALL refuse the decision, SHALL record no outcome, SHALL void the pending result rather than leaving it standing, and SHALL tell the decider why.

Recording is rejected for such a step by `launch-instance` in any case, so an unhandled decision would surface to the decider as a failure; and leaving the result pending would keep offering a decision that can never take effect. Voiding it is what lets the step, if it returns to the served set, be resolved afresh rather than settled by a proposal made about a step that has since changed.

#### Scenario: A decision on a de-activated step is refused and the result voided

- **WHEN** a decision arrives for a pending result whose step has since been moved out of `active`
- **THEN** it is refused, no outcome is recorded, the pending result is voided, and the decider is told why
