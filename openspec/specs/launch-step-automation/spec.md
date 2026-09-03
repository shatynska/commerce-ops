# launch-step-automation Specification

## Purpose
Runs the code an `automated` step names, and decides what becomes of what that code produced: recorded against the launch straight away, or held until a member accepts it. This is what makes `kind`, `handler` and `confirmer` do something rather than merely be declared.

## Requirements

### Requirement: An automated step's handler is invoked by recurring work

The system SHALL invoke registered step handlers from recurring work that runs inside the deployment, declaring its schedule and tolerance as `scheduled-jobs` requires of every piece of recurring work. Each pass SHALL consider every launch that has not graduated, and within each launch every step of its served playbook whose kind is `automated`.

A pass SHALL invoke the handler of such a step only where all of the following hold: the launch has released the step (`launch-playbook`, *A step declares when it may start*); the step's recorded outcome is not one the step's hazard permits as terminal; no pending result stands for it; it is not within the cool-off this specification places after a rejection; and it is not within the cool-off this specification places after a handler repeated a non-terminal outcome. `human` steps, steps that are not `active`, steps the launch has not released, and steps already at a permitted terminal outcome SHALL NOT be invoked.

Release is judged by the same rule the projection into a task tracker is judged by, and never by a rule private to this pass: a step's eligibility is one fact about the launch, so that what the system asks of a member and what it asks of a handler cannot drift apart.

A step that names no start gate and no dependencies is released from the launch's first pass, which is every step until an author says otherwise. Gating invocation therefore withholds nothing by itself — it gives an author a way to say that a handler must not run before the launch is ready for it, which without this rule cannot be said at all. A handler whose answer is useful early, and whose inputs are available early, is left to say nothing and keep running early.

An unreleased step SHALL be passed over silently: it is not a fault, not a stuck step, and SHALL NOT be reported as one. It has not failed to make progress — it has not been asked to.

What this means for a step naming an unregistered handler is settled by that requirement, which is narrowed to match.

Invocation SHALL NOT be reachable from outside the deployment.

#### Scenario: An unresolved automated step is invoked

- **WHEN** a pass runs over a launch whose served playbook carries a released `active` `automated` step with no recorded outcome, no pending result and no recent rejection
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

#### Scenario: A step whose start gate the launch has not reached is not invoked

- **WHEN** a pass runs over a launch standing at `commit` and the served playbook carries an `active` `automated` step whose start gate is `listable`
- **THEN** its handler is not invoked, and nothing is recorded against the step

#### Scenario: A step naming no start gate keeps running from the first pass

- **WHEN** a pass runs over a launch standing at `commit` and the served playbook carries an `active` `automated` step naming no start gate and no dependencies
- **THEN** its handler is invoked, whatever gate the step itself belongs to

#### Scenario: A step is invoked on the pass after the launch releases it

- **WHEN** a launch that stood at `commit` advances to the start gate of an unresolved `active` `automated` step, and the next pass runs
- **THEN** that step's handler is invoked

#### Scenario: An unreleased step is not reported as stuck

- **WHEN** a pass runs over a launch that has not released an `active` `automated` step
- **THEN** no stuck-step report is produced for it and no application log record names it as making no progress

#### Scenario: An unregistered handler on an unreleased step is not reported by the pass

- **WHEN** a pass runs over a launch that has not released a step whose named handler no registered use case answers to
- **THEN** the pass reports nothing for it, the startup registration report being where that fault is named

### Requirement: A handler receives the step, the launch and the product, and attributes nothing

A handler SHALL be given the step definition it is resolving, a read of the launch it is resolving against, the catalog product that launch is for, and the moment the pass is running as of. The catalog product SHALL be resolved by the system and supplied to the handler, never fetched by the handler itself — a handler is a function of the context it is given and nothing else, which is what allows it to be exercised without a database and keeps the catalog read in one place rather than one place per handler.

A handler SHALL return an outcome from the `launch-playbook` outcome vocabulary together with the result it produced, expressed as text a member can read. The produced text SHALL NOT be empty: it becomes the recorded evidence, which `launch-instance` requires of every recording. A handler MAY additionally report a typed finding alongside its outcome and result — see *A handler MAY report a typed finding alongside its outcome*. Doing so changes nothing about the outcome or the result: both continue to mean exactly what they mean for a handler that reports no finding at all.

A handler with nothing conclusive to report SHALL say so through a **non-terminal** outcome whose reason states why — never by proposing a terminal outcome it cannot support, and never by failing. Of the three non-terminal outcomes only `Blocked` can itself carry a reason; where a handler proposes one that cannot, the produced text SHALL state the reason instead, so that a stalled step is legible rather than merely quiet.

A handler SHALL NOT supply its own recording provenance. The system SHALL construct the provenance for every outcome a handler produces, with source `automated`, naming the handler as what did the work, the moment of the run, and the produced result as the evidence. A handler therefore cannot record work as having come from a member or from ClickUp.

#### Scenario: The product is supplied, not fetched

- **WHEN** a handler is invoked for a step on a launch
- **THEN** its context carries the catalog product that launch is for, resolved before the handler ran

#### Scenario: A produced outcome is attributed to the handler

- **WHEN** a handler returns a resolution and its outcome is recorded
- **THEN** the recorded provenance has source `automated`, names the handler, carries the moment of the run, and carries the produced result as its evidence

#### Scenario: A handler cannot claim another source

- **WHEN** a handler attempts to supply provenance of its own
- **THEN** the system rejects it and the provenance the system constructed stands

#### Scenario: A finding changes nothing about the outcome or the result

- **WHEN** a handler reports a typed finding alongside its outcome and result
- **THEN** the outcome is recorded, and the result is stored as evidence, exactly as they would be for a handler reporting no finding

### Requirement: A non-terminal outcome is recorded directly and never held for a decision

Where the outcome a handler proposes is not terminal — `NotStarted`, `InProgress` or `Blocked`, none of which `launch-playbook` permits as terminal for any step — the system SHALL record it against the launch immediately with the provenance it constructed, **whatever confirmer the step names**, and SHALL NOT store it as a pending result or seek a decision on it.

Confirmation exists so a named confirmer accepts a result. A non-terminal outcome is not a result: it is a handler reporting that the step has not been resolved, and holding it would ask a member to accept "in progress" — a proposal with nothing in it to agree or disagree with, which would then suppress re-invocation until they clicked. Recording it directly keeps the reason on the launch's own record, which is what makes a stalled automated step legible rather than merely quiet.

A non-terminal outcome SHALL leave the step eligible for the next pass, **except** where it repeats the non-terminal outcome the step already carries, which the requirement *A handler that repeats itself is not asked again immediately* governs.

#### Scenario: A non-terminal outcome on a confirmable step is recorded, not held

- **WHEN** a handler proposes `Blocked` with a reason for a step naming a confirmer
- **THEN** the outcome is recorded against the launch with `automated` provenance, no pending result is stored, and no decision is requested

#### Scenario: A step reporting no progress is reconsidered on the next pass

- **WHEN** a handler proposes a non-terminal outcome that differs from the one the step already carries, and a later pass runs
- **THEN** the handler is invoked again for that step

### Requirement: A terminal outcome the step's hazard forbids is a handler fault, not a recording

Before storing or recording anything, the system SHALL check a **terminal** outcome a handler proposed against what the step's hazard permits, as `launch-playbook` defines it. A terminal outcome the hazard does not permit SHALL be treated exactly as a handler failure: nothing recorded, nothing stored, the fault reported naming the launch, the step, the handler and the offending outcome.

Checking at production time rather than at recording time is what keeps the fault visible. A `Refused` proposed for a `compliance-obligation` step, stored as a pending result and delivered, would fail only when a member pressed accept — and would then fail identically every time it was pressed, leaving a result that can never be settled.

#### Scenario: An impermissible proposal is refused before it is stored

- **WHEN** a handler proposes a terminal outcome the step's hazard does not permit
- **THEN** no outcome is recorded, no pending result is stored, and the fault is reported naming the launch, step, handler and outcome

### Requirement: An unregistered handler is reported and skipped, never fatal

Where an `active` `automated` step **the launch has released** names a handler this deployment does not register, the pass SHALL skip that step, SHALL record no outcome for it, and SHALL report the step and the handler name it could not resolve. The pass SHALL continue with every other step and every other launch.

A step the launch has **not** released is passed over before its handler is resolved, so the pass SHALL NOT report it. This narrowing is deliberate and is safe because the pass is not the only place the fault is found: the deployment's own handler-registration report names every step naming an unregistered handler at start, before anything serves. A step nothing will invoke for several gates is not this pass's news to break, and reporting it every pass until its gate arrives would bury the steps that are actually stuck. Once the launch releases it, the pass reports it exactly as it always did.

This is the same trade the startup handler report already settles: a step nothing can resolve is a deployment fault worth naming, never a reason to stop resolving everything else.

#### Scenario: A step naming an unregistered handler is skipped

- **WHEN** a pass reaches an `active` `automated` step whose named handler is not registered in this deployment
- **THEN** no outcome is recorded for it, the step and the handler name are reported, and the pass continues

#### Scenario: A step naming an unregistered handler is not reported before its launch releases it

- **WHEN** a pass reaches a step whose named handler is not registered and whose start gate the launch has not reached
- **THEN** nothing is reported for it, the startup registration report being where that fault is named

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

Where the resolved step names no confirmer, the system SHALL record the handler's outcome against the launch immediately, with the provenance it constructed. No decision is sought and nothing is held.

#### Scenario: An unconfirmed result is recorded directly

- **WHEN** a handler resolves a step that names no confirmer
- **THEN** the outcome is recorded against the launch with `automated` provenance, and no decision is requested

### Requirement: A result needing confirmation is held until a member decides

Where the resolved step names a confirmer **and the outcome the handler proposed is terminal**, the system SHALL NOT record that outcome. It SHALL store the produced result as a pending result against that launch and step — carrying the outcome the handler proposed, the produced text, the handler, and when it was produced — and SHALL seek a decision on it.

At most one pending result SHALL stand for a launch and step at any moment. A step awaiting a member is not a step awaiting more work, and a second result would leave two proposals and no way to say which was decided.

#### Scenario: A confirmable terminal result is held rather than recorded

- **WHEN** a handler proposes a terminal outcome for a step naming a confirmer
- **THEN** no outcome is recorded against the launch, and a pending result is stored carrying the proposed outcome, the produced text, the handler and the moment it was produced

#### Scenario: A pending result suppresses re-invocation

- **WHEN** a pass runs while a pending result stands for a launch and step
- **THEN** that step's handler is not invoked and the pending result is left as it is

#### Scenario: Two overlapping passes cannot both produce a pending result

- **WHEN** two passes overlap and both would store a pending result for the same launch and step
- **THEN** exactly one pending result stands, and the step is left for a later pass

### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

The system SHALL deliver each pending result to Slack, as a reply within that launch's Slack thread — establishing the thread first if it does not yet exist — naming the product, the step, the outcome the handler proposed and the produced text in full, offering an accept and a reject decision, and tagging the step's named confirmer.

Delivery SHALL work from a pending result in the form the store hands it back. A delivery path that requires an identifier in a form the store does not produce delivers nothing at all, while satisfying any test that supplies the form it wants — and because an undelivered result is retried, the permanent failure is indistinguishable in the record from a transient one.

The accept and reject decisions SHALL name the launch and the step the pending result was stored against, so that a decision made on them resolves that result. Where the message or the controls name the launch or the product by an identifier, they SHALL carry that identifier's own value and never a rendering of the object holding it, per `shared-vocabulary`'s requirement on the textual form of a value.

**Tagging a member means the message carries a mention Slack resolves to them.** A step's confirmer is stored as the membership's own identifier for that member, which Slack cannot resolve; a message carrying it renders as inert literal text and notifies nobody, which satisfies no part of this requirement. The system SHALL resolve the step's confirmer through the membership to that member's Slack identity, and tag them with it.

A named confirmer SHALL be treated as **resolvable for tagging** only where the membership carries them, carries them with a Slack identity, and carries them as still active. A deactivated confirmer is not resolvable for tagging, though their Slack identity survives deactivation: *Only the step's named confirmer may decide a pending result* accepts a decision only from a confirmer who is still active, so tagging a deactivated one would summon a member whose accept and reject are certain to be refused — and the result would stay held pending regardless, as `playbook-authoring` specifies for exactly this case.

Where the named confirmer is not resolvable for tagging, the pending result SHALL still be delivered, carrying no mention, and the gap SHALL be reported naming the step, the launch and the unresolvable confirmer — the same trade the ClickUp projection makes for an assignee with no ClickUp account, and for the same reason: a failed delivery would hide a data gap behind a retry. The launch's submitter SHALL NOT be tagged in the confirmer's place. Only the named confirmer may decide a pending result, so tagging anyone else summons a member whose decision is refused; and a step naming no confirmer and a step naming one who cannot be tagged are different facts that must not read identically to a member watching the thread.

Where the membership cannot be read at all — no reader, a reader of the wrong shape, or one that fails — the pending result SHALL still be delivered, carrying no mention, and the failure SHALL be reported. The substance of the ask does not depend on the membership, and withholding it to avoid an untagged message would trade a message somebody might miss for no message at all.

A failure to deliver SHALL NOT discard the pending result and SHALL NOT record an outcome. The failure SHALL be reported, and the pending result SHALL remain available to be delivered again — the same decoupling the daily briefing keeps between assembling a report and delivering it.

#### Scenario: A pending result reaches Slack

- **WHEN** a pending result is stored
- **THEN** a Slack message tagging the step's confirmer is delivered as a reply within the launch's thread, naming the product, the step, the proposed outcome and the produced text, offering an accept and a reject decision

#### Scenario: A stored pending result is delivered in the form it was stored

- **WHEN** a pending result that was stored is read back by a later pass and delivered
- **THEN** the message is posted, and no delivery is refused because of the form the stored result carries its identifiers in

#### Scenario: A delivered result's controls resolve the result they were composed for

- **WHEN** a decision is made on the accept or reject control of a delivered pending result
- **THEN** the launch and step the control names are the ones the pending result was stored against, and the decision resolves that pending result

#### Scenario: A tagged confirmer is mentioned by their Slack identity

- **WHEN** a pending result is delivered for a step naming a confirmer the membership carries, active and with a Slack identity
- **THEN** the message mentions that member by their Slack identity, and the membership's own identifier for them appears nowhere in it

#### Scenario: A confirmer the membership does not carry is not mentioned, and the gap is reported

- **WHEN** a pending result is delivered for a step naming a confirmer the membership does not carry
- **THEN** the message is still delivered naming the product, the step and the produced text, carrying no mention and not tagging the submitter, and the unresolvable confirmer is reported

#### Scenario: A deactivated confirmer is not mentioned, and the gap is reported

- **WHEN** a pending result is delivered for a step whose named confirmer has been deactivated on the membership
- **THEN** the message is still delivered, carrying no mention and not tagging the submitter, and the deactivated confirmer is reported — the decision could not be accepted from them in any case

#### Scenario: A pending result is delivered untagged when the membership cannot be read

- **WHEN** a pending result is delivered for a step naming a confirmer and the membership cannot be read at all
- **THEN** the result is still delivered, carrying no mention, and the membership failure is reported

#### Scenario: An identifier in the message or its controls appears as its value

- **WHEN** a delivered pending result names the product by an identifier, or its controls carry one
- **THEN** the identifier appears as its own value, not as a rendering of the object carrying it

#### Scenario: Undelivered is not undone

- **WHEN** delivering a pending result to Slack fails
- **THEN** the pending result still stands, no outcome is recorded, and the delivery failure is reported

#### Scenario: An undelivered result is delivered again later

- **WHEN** a delivery failed and a later pass runs
- **THEN** delivery of that pending result is attempted again

#### Scenario: A pending result for a launch with no thread yet establishes one

- **WHEN** a pending result is delivered for a launch that has no Slack thread reference
- **THEN** an anchor message is posted for that launch first, and the pending result is delivered as a reply within the newly established thread

### Requirement: Only the step's named confirmer may decide a pending result

A pending result exists only for a step that names a confirmer — a step naming none is recorded directly and never held (*A result needing confirmation is held until a member decides*). The system SHALL accept a decision on a pending result only from the Slack identity belonging to that step's named confirmer, and only where the confirmer is still active on the membership. A decision from any other identity — known to the membership or not, active or not — SHALL be refused, SHALL record no outcome, SHALL leave the pending result standing, and SHALL tell the decider it was refused.

Decisions arrive on the same verified `product_agent` Slack surface `launch-entry` already uses, so a decision whose authenticity cannot be established never reaches this rule; and a decision SHALL be acknowledged within Slack's timeout independently of whether the recording it triggers has completed.

The membership this rule is evaluated against is supplied by the caller, and SHALL answer to **one** stated shape: it SHALL be able to answer who the membership carries, deactivated entries included, since resolving the deciding Slack identity to a member, checking that member against the step's named confirmer, and checking that member's active status are all decided here rather than by whatever supplies the membership. A collaborator that cannot answer that — including no collaborator at all — SHALL be refused as a defect of *wiring*: a named error identifying what was supplied and what was expected, raised before the deciding identity is judged. It is raised at the point the identity would be resolved, so a decision already refused for a reason that does not depend on the membership keeps that refusal.

That refusal SHALL NOT be reachable as a decision refusal. A decision refusal is a statement about the decision that was made, so an unreadable collaborator SHALL NOT be resolved into "this identity is not the confirmer", SHALL NOT be reported to the decider as a fact about their identity, and SHALL NOT leave a decider with any reason to believe their members entry or their standing as confirmer is at fault. The decider SHALL still be told their decision was not processed, and the mis-wiring SHALL be reported where operators see faults rather than only in the Slack reply.

This carries forward a fault this system has already shipped once, on the wider rule this replaces: a members collaborator accepted in whichever shape it happened to arrive in, production supplying none of the shapes read, and every decision by every identity refused as though the membership carried nobody — silently, and pointing at correct members data instead of at the wiring.

Consequently, the membership a decision is judged against SHALL be the same membership the membership-administration surface writes and the same playbook a step's confirmer is read from: an identity the membership holds as active, and the step names as confirmer, SHALL be able to decide, and no arrangement of the collaborator SHALL be able to refuse every identity alike.

#### Scenario: The named confirmer can decide

- **WHEN** a decision arrives from the Slack identity belonging to the step's named confirmer, whom the membership holds as active
- **THEN** it is accepted, and the pending result is settled per *Accepting records the proposed outcome and names the accepter* or *Rejecting does not terminate the step*

#### Scenario: An unknown identity cannot decide

- **WHEN** a decision arrives from a Slack identity the membership does not know
- **THEN** it is refused, no outcome is recorded, the pending result still stands, and the decider is told

#### Scenario: Someone other than the confirmer cannot decide

- **WHEN** a decision arrives from a Slack identity belonging to a member the membership holds as active, who is not the step's named confirmer
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

#### Scenario: A deactivated confirmer cannot decide

- **WHEN** a decision arrives from the Slack identity belonging to the step's named confirmer, whose members entry the membership holds as inactive
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

#### Scenario: A collaborator that cannot answer who the membership carries is refused by name

- **WHEN** a decision is judged against a members collaborator that cannot answer who the membership carries
- **THEN** it is refused with a named error identifying the collaborator supplied and the shape expected, raised before the deciding identity is judged
- **AND** no outcome is recorded and the pending result still stands

#### Scenario: An absent collaborator is refused the same way, not silently

- **WHEN** a decision arrives at a deployment where no members collaborator was supplied at all
- **THEN** it is refused with the same named wiring error, the decider is told their decision was not processed, and the decision does not fail without an answer

#### Scenario: A mis-wiring is never reported as an unknown identity

- **WHEN** a decision is judged against a members collaborator that cannot answer who the membership carries
- **THEN** the decider is not told that their identity is not the confirmer, and the mis-wiring is reported where operators see faults

### Requirement: Accepting records the proposed outcome and names the accepter

Accepting a pending result SHALL record, against the launch, exactly the outcome the handler proposed, with source `automated`, naming the accepting member, carrying the moment of the decision, and carrying evidence that names both the handler that produced the result and the produced text itself. The pending result SHALL then be settled and SHALL no longer suppress re-invocation.

The source stays `automated` because the work was the handler's; who accepted it is what the recorder names; and the evidence names the handler so that the launch's own record answers what produced the accepted result, without depending on the pending-result store still holding the row.

The recording and the settlement SHALL both take effect, or neither: a settled result whose outcome was never recorded would be undecidable and unrecoverable.

#### Scenario: An accepted result becomes the step's outcome

- **WHEN** the step's named confirmer accepts a pending result proposing `Satisfied`
- **THEN** `Satisfied` is recorded for that step with source `automated`, naming the accepter and the moment of the decision, with evidence naming the handler and carrying the produced text

#### Scenario: A failed recording leaves the result decidable

- **WHEN** recording the outcome for an accepted pending result fails
- **THEN** the pending result is not settled and the decision can be made again

### Requirement: Rejecting does not terminate the step

Rejecting a pending result SHALL record a `Blocked` outcome against the launch, whose reason names the rejecting member and states that an automated result was rejected, with source `automated` and the rejecting member as the recorder. It SHALL settle the pending result as rejected, and SHALL leave the step available for a handler to resolve again on a later pass.

`Blocked` is chosen from among the non-terminal outcomes because it is the one that carries a reason, and a rejection whose reason was not recorded would leave the launch showing an unresolved step with nothing saying why. The source stays `automated` for the same reason acceptance does: the work being rejected was a handler's.

A rejection SHALL NOT be recorded as `Refused`. `Refused` is reserved by `launch-playbook` for a step whose hazard is `prohibited-tactic`, and means the tactic itself was recognised and declined; a member declining one produced result has said nothing about the step's permissibility. Nor SHALL it be recorded as `NotApplicable`, which is terminal and would close a step whose work still stands.

#### Scenario: A rejected result leaves the step live

- **WHEN** the step's named confirmer rejects a pending result
- **THEN** a `Blocked` outcome is recorded whose reason names the rejecter, with source `automated` and the rejecter as recorder, and the step is not at a terminal outcome

#### Scenario: Rejection is never a refusal

- **WHEN** a pending result for a step whose hazard is not `prohibited-tactic` is rejected
- **THEN** the recorded outcome is not `Refused` and is not `NotApplicable`

### Requirement: A rejected step is not re-proposed immediately

After a rejection, the system SHALL NOT invoke that step's handler again until a fixed cool-off has elapsed since the rejection. Once it has, a pass SHALL invoke the handler again.

Without a cool-off, rejecting one recommendation buys a fresh handler run on every pass thereafter, and a stream of Slack messages proposing much the same thing — so the cost of a member disagreeing would be unbounded. The cool-off is a fixed property of the system, not a configured one: it needs no per-deployment answer, and `runtime-configuration` requires a declared variable for anything that does.

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

### Requirement: Registering a handler does not load what the handler needs to run

Registering a step handler SHALL make its name resolvable and SHALL NOT, by itself, load or construct the resources the handler uses when it runs — a language model client, a graph, an HTTP session, or anything else it reaches for only while resolving a step. Those SHALL be obtained when the handler is invoked, and MAY be retained between invocations.

This is a **deployment** property, not a matter of taste. Every process that consults the registry must register every handler in order to consult it at all, so each such process pays every handler's registration cost — including processes that never invoke one, such as the process that makes the startup handler report. A registration that loads a model client makes the cost of reading a name proportional to the weight of the work behind it, multiplied by the number of handlers the deployment answers for.

Where obtaining a resource is deferred, the deferral SHALL NOT change what the handler produces: a handler resolving a step SHALL behave as it would have with the resource obtained at registration.

#### Scenario: Registering a handler loads no model client

- **WHEN** a step handler's module is loaded such that its name becomes resolvable in the registry
- **THEN** its name resolves, and the process holds no resource the handler uses to resolve a step

#### Scenario: A handler still resolves a step

- **WHEN** a registered handler whose resources are obtained on invocation is run over a step, against a model that answers as the deterministic agent-graph tests specify
- **THEN** it produces the outcome and the result text those tests specify, unchanged by when its resources were obtained

#### Scenario: A process that never invokes a handler still pays only for the registration

- **WHEN** a process registers every handler this deployment answers for in order to read the registry, and invokes none of them
- **THEN** it loads no handler's working resources

### Requirement: A retained result is kept and stays readable as the product's record

Every result stored for a decision SHALL be retained whatever state it reaches. Settling a result — as accepted or as rejected — and voiding one SHALL each keep the row, carrying the state it reached and, where a member decided it, who decided and when. Nothing in the decision flow SHALL delete a result.

This narrows three requirements already in this specification. *Accepting records the proposed outcome and names the accepter* says the pending result "SHALL then be settled"; *Rejecting does not terminate the step* says it "SHALL settle the pending result as rejected"; and *A decision on a step the playbook no longer serves is refused* says the system "SHALL void the pending result rather than leaving it standing". Read alone, each could be satisfied by deleting the row. None may be, and a later amendment to any of the three SHALL be read against this requirement.

The system SHALL be able to answer, for one product, every result retained for it: results in every state, results produced for a step the served playbook no longer defines, and results retained for a launch that has since graduated. That answer SHALL be ordered by the moment each result was produced, most recent first, and SHALL be total — results produced at the same moment SHALL be ordered by a stable tiebreak, so that the same stored data is answered in the same order every time.

Retention is already what the store does; what this requires is that it be *readable as a record*. Every read the store offers today serves the decision loop — the pending result for a step, a result by its identifier, the undelivered ones, the most recent rejection — and none of them answers "what has been produced for this product". Without such a read, "settled rows are kept, never deleted" buys storage and nothing else: the record of a compliance-adjacent decision exists and is reachable only by querying the database directly.

The read SHALL be filtered by the caller's access scope, in the shape every other product-keyed read follows: for a product the scope does not permit, it SHALL answer exactly as it does for a product with nothing retained, so that reading can never confirm the existence of a product or a result the caller may not see.

#### Scenario: A settled result is still readable

- **WHEN** every result retained for a product is read after one of them was accepted and another rejected
- **THEN** both are answered, each carrying the state it reached, the member who decided it and the moment of the decision

#### Scenario: A voided result is readable and is not a rejection

- **WHEN** every result retained for a product is read after a decision voided one of them
- **THEN** that result is answered carrying the voided state, distinct from a rejected one

#### Scenario: A voided result carries no decider

- **WHEN** every result retained for a product is read after a decision voided one of them
- **THEN** that result is answered with no decider, because voiding refuses a decision rather than recording one

#### Scenario: A result for a step no longer served is still readable

- **WHEN** every result retained for a product is read after the step one of them names has been moved out of `active`
- **THEN** that result is still answered

#### Scenario: A graduated launch's results are still readable

- **WHEN** every result retained for a product is read after that product's launch has reached `graduated`
- **THEN** every result retained for it is answered

#### Scenario: Results are answered newest first

- **WHEN** every result retained for a product is read and results were produced at different moments
- **THEN** they are answered ordered by the moment produced, most recent first

#### Scenario: Results sharing a produced moment are answered in the tiebreak's order

- **WHEN** every result retained for a product is read and two of them share a produced moment and differ in row identifier
- **THEN** the one whose row identifier sorts higher is answered first
- **AND** it is answered first whichever order the two were stored in

#### Scenario: A product outside the caller's scope answers as an empty record

- **WHEN** every result retained for a product is read under a scope that does not permit that product's identifier
- **THEN** nothing is answered, exactly as for a product with nothing retained, and no error distinguishes the two

#### Scenario: A product with nothing retained answers emptily, not with a failure

- **WHEN** every result retained for a product that has never had a result stored is read
- **THEN** nothing is answered and the read succeeds

### Requirement: The retained record covers results held for a decision and nothing else

Every result the system retains SHALL be one held for a decision — a terminal outcome the step's hazard permits, proposed for a step naming a confirmer, and actually stored. An outcome recorded directly SHALL NOT be retained here: neither a non-terminal outcome, which this specification records against the launch whatever confirmer the step names, nor a terminal outcome on a step naming no confirmer.

Stated as a necessary condition and not as a biconditional, because the converse is false and this specification already says why: a terminal outcome the step's hazard forbids stores nothing at all (*A terminal outcome the step's hazard forbids is a handler fault, not a recording*), and a second proposal racing an existing pending one stores nothing either (*A result needing confirmation is held until a member decides*). A consumer may rely on everything in the record being a proposal someone was asked to accept; it may not rely on the record holding every such proposal ever made.

This states no new routing policy. Which outcomes are held and which are recorded directly is settled by three requirements already in this specification — *A non-terminal outcome is recorded directly and never held for a decision*, *A result needing no confirmation is recorded at once* and *A result needing confirmation is held until a member decides* — and this requirement is their consequence, not a second statement of them. Where they change, this changes with them.

What it adds is the boundary as a fact *about the retained set*, which a consumer reads rather than derives. The retained set is the record of **what members were asked to accept**, not the record of everything handlers produced; a consumer that presented it as the latter would be wrong in a way its readers could not detect, and most wrong for exactly those products whose automated steps name no confirmer.

#### Scenario: An outcome needing no confirmation is not retained

- **WHEN** a handler resolves a step that names no confirmer, and every result retained for that product is read
- **THEN** nothing is answered for that step

#### Scenario: A non-terminal outcome is not retained

- **WHEN** a handler proposes a non-terminal outcome for a step naming a confirmer, and every result retained for that product is read
- **THEN** nothing is answered for that step

### Requirement: A handler that repeats itself is not asked again immediately

Where a handler proposes a non-terminal outcome that is the same as the one the step already carries, the system SHALL record that outcome as it records any other, and SHALL NOT invoke that step's handler again until a fixed cool-off has elapsed **since that repeat was noted**. Once it has, a pass SHALL invoke the handler again; where the handler repeats itself again, the step SHALL be cooled off again from that later repeat.

Two non-terminal outcomes are **the same** where they are outcomes of the same kind, disregarding any reason either carries. The reason a handler gives SHALL NOT be part of that judgement: a handler may word the same reason differently on each call — an LLM-backed handler always will — and a rule comparing reasons would find no two reports alike, engage never, and appear to work while changing nothing.

The outcome being repeated is the one the step carries, **whatever recorded it**. A `Blocked` outcome a member's rejection recorded can serve as the first of the two: the step is then cooled off on the handler's first statement rather than its second. This is intended — the rejection cool-off already governs that window, and a step a member has just rejected and a handler then declines to resolve is stuck by any reading.

A repeat SHALL be established from two recordings rather than predicted from one. A step reporting a non-terminal outcome for the first time stays eligible for the next pass, because whether the handler has more to say is not knowable without asking it. This deliberately spends one further invocation on a step that turns out to be stuck, which is what distinguishes it from a step that is progressing.

The cool-off SHALL be a fixed property of the system rather than a configured one, and SHALL be independent of the cool-off placed after a rejection: the two answer different questions, and a step that has repeated itself SHALL NOT be affected by a change to the rejection cool-off.

A cool-off SHALL cease to govern the step as soon as the step's recorded outcome is no longer an outcome **of the kind** the cool-off was noted against — including where something other than a pass recorded it. Nothing SHALL be required to actively lift it. The kind is what matters here for the same reason it is what matters above: a `Blocked` re-recorded with different wording is the same kind, and must not lift a cool-off.

The judgement SHALL NOT be made from the launch journal. A dropped journal entry must never change what the system does: `launch-journal` keeps a record for membership, and it is safe to lose exactly because no behaviour reads it.

Where the system cannot read or write whatever it keeps this judgement in, the step SHALL be left eligible for invocation and the failure SHALL be reported — the pass SHALL behave as it did before this requirement existed rather than leave a step unresolved. The failure SHALL NOT fail the pass, and SHALL NOT prevent the remaining steps and launches from being walked or their outcomes from being recorded.

That degrade applies to invocation only. What such a failure means for reporting a stuck step is governed by *A step whose handler has stopped making progress is reported once*, which degrades the other way.

Where the shared store cannot be restored to a usable state after such a failure, the pass SHALL end and the run SHALL be recorded as failed. A pass that walked on against a store that cannot record would persist nothing while reporting success, which is worse than stopping.

#### Scenario: A cool-off is anchored to the repeat that caused it

- **WHEN** a step's handler repeats itself again after an earlier cool-off has elapsed
- **THEN** the step is cooled off again, measured from the later repeat

#### Scenario: A cool-off stops governing once the outcome differs from it

- **WHEN** a step cooled off against one non-terminal outcome has a different outcome recorded against it by something other than a pass
- **THEN** the step is eligible for invocation on the next pass

#### Scenario: A step whose backoff record cannot be read is still invoked

- **WHEN** a pass cannot read whether a step is cooled off
- **THEN** the step's handler is invoked, the failure is reported, and the pass continues

#### Scenario: A failed backoff access does not cost the pass its other work

- **WHEN** reading or writing the backoff record fails for one step
- **THEN** the remaining steps and launches are still walked and their recorded outcomes are still persisted

#### Scenario: A repeated non-terminal outcome is recorded and cools the step off

- **WHEN** a handler proposes the non-terminal outcome the step already carries
- **THEN** the outcome is recorded against the launch, and the step's handler is not invoked on the next pass

#### Scenario: A differently worded repeat still counts as a repeat

- **WHEN** a handler proposes `Blocked` with a reason worded differently from the reason recorded on the step, which is also `Blocked`
- **THEN** it is treated as a repeat, and the step's handler is not invoked on the next pass

#### Scenario: A first non-terminal outcome does not cool the step off

- **WHEN** a handler proposes a non-terminal outcome for a step carrying no recorded outcome
- **THEN** the outcome is recorded and the handler is invoked again on the next pass

#### Scenario: A changed outcome lifts the cool-off

- **WHEN** a handler that had repeated itself is invoked after the cool-off elapses and proposes a different non-terminal outcome
- **THEN** the outcome is recorded and the handler is invoked again on the next pass

#### Scenario: A repeated step is asked again once the cool-off elapses

- **WHEN** a pass runs after the cool-off has elapsed since a step's handler repeated itself
- **THEN** that step's handler is invoked again

#### Scenario: The rejection cool-off does not govern a repeat

- **WHEN** a step's handler has repeated a non-terminal outcome and no rejection stands against that step
- **THEN** the step is cooled off by the repeat alone

### Requirement: A step whose handler has stopped making progress is reported once

Where a handler repeats a non-terminal outcome and the step is cooled off, the system SHALL report that step once — as a reply within the launch's Slack thread, establishing the thread first if it does not yet exist — naming the launch, the step, and **what the handler produced as its result**, which for a `Blocked` outcome is also the reason it carries, and tagging the step's named confirmer where the step names one, the launch's submitter otherwise, so that a member can supply what the handler is missing. A handler that cannot resolve a step is reporting work only a member can do, and a record nobody reads is not a report. The result is reported as what the handler said, never asserted as a fact about the product.

**Tagging a member means the message carries a mention Slack resolves to them**, on the same terms this capability's delivery requirement states: the step's confirmer is stored as the membership's own identifier and SHALL be resolved through the membership to that member's Slack identity, and is resolvable for tagging only where the membership carries them, with a Slack identity, and still active. The launch's submitter is already a Slack identity and needs no resolution, which is why a step naming no confirmer is unaffected by whether the membership can be read.

Where the named confirmer is not resolvable for tagging, or the membership cannot be read at all, the report SHALL still be delivered, SHALL tag the launch's submitter, and SHALL name in its text that the step's confirmer could not be resolved. The gap SHALL also be reported.

**This report falls back to the submitter where the pending-result ask does not, and the difference is deliberate.** No authorization rule governs who may act on a stuck step: the report exists so that *a member* can supply what the handler is missing, so reaching somebody is the whole of its purpose, and an untagged report reaching nobody would defeat it. The ask is the opposite — only the named confirmer may decide it, so a fallback tag there summons a member whose decision is refused. Naming the unresolved confirmer in the text is what keeps the two facts distinct here without withholding the mention: a reader can still tell a step that names no confirmer from one whose confirmer cannot be reached.

Where the report names the launch or the product by an identifier, it SHALL carry that identifier's value and not a rendering of the object holding it, per `shared-vocabulary`.

The report SHALL be delivered once for as long as the step stays stuck, and SHALL NOT be repeated on every pass **nor on each expiry of the cool-off**: a step stuck for a week is one message, not seven. A step whose recorded outcome later changes, or which reaches an outcome its hazard permits as terminal, SHALL become eligible to be reported again if it later gets stuck.

Two passes running over the same step at once MAY each deliver the report, since neither can see the other's delivery before it happens. A duplicate message is the accepted cost of writing the record only after a delivery succeeds.

Where the system cannot read whether a step has already been reported, it SHALL deliver no report for that step on that pass. A report that cannot be recorded as delivered cannot be delivered *once*, and attempting one anyway would turn a store outage into a report on every pass — the repetition this requirement exists to prevent. This is the opposite degrade from the one *A handler that repeats itself is not asked again immediately* places on invocation, and deliberately so: an unresolved step is the worse outcome there, and an unread channel is the worse outcome here. The access failure is itself reported, and the step is reported normally on the first pass that can read the record again.

An unreadable *members* degrades differently again, and only the mention: the report is delivered, tagged to the submitter, and the failure reported — because the substance of the report does not depend on the membership, and because the membership is not what decides whether this message may be sent.

The record that suppresses further reports SHALL be written only after a delivery has succeeded. Recording first and then failing to deliver would silence the step for as long as it stays stuck, which is precisely the period the report exists to cover.

A failure to deliver the report SHALL NOT fail the pass, SHALL NOT stop the remaining launches or steps from being walked, and SHALL NOT record any outcome.

#### Scenario: A newly cooled-off step is reported

- **WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
- **THEN** a report naming the launch, the step and what the handler produced as its result is delivered as a reply within the launch's Slack thread

#### Scenario: A stuck step naming a confirmer tags that confirmer

- **WHEN** a report is delivered for a stuck step naming a confirmer the membership carries, active and with a Slack identity
- **THEN** the message mentions that member by their Slack identity, and the membership's own identifier for them appears nowhere in it

#### Scenario: A stuck step naming no confirmer tags the submitter

- **WHEN** a report is delivered for a stuck step that names no confirmer
- **THEN** the message tags the launch's submitter instead

#### Scenario: A stuck step whose confirmer cannot be resolved tags the submitter and names the gap

- **WHEN** a report is delivered for a stuck step naming a confirmer the membership does not carry, or carries without a Slack identity, or carries as deactivated
- **THEN** the report is delivered tagging the launch's submitter, its text names that the step's confirmer could not be resolved, and the gap is reported

#### Scenario: A stuck step is reported to the submitter when the membership cannot be read

- **WHEN** a report is delivered for a stuck step naming a confirmer and the membership cannot be read at all
- **THEN** the report is delivered tagging the submitter, naming that the confirmer could not be resolved, and the membership failure is reported

#### Scenario: A report naming a product by identifier names it by value

- **WHEN** a report is delivered for a stuck step whose product cannot be named any other way
- **THEN** the identifier appears as its own value, not as a rendering of the object carrying it

#### Scenario: A step that stays stuck is not reported again

- **WHEN** a later pass runs while the same step is still cooled off with an unchanged outcome
- **THEN** no further report is delivered for it

#### Scenario: A step still stuck after the cool-off expires is not reported again

- **WHEN** the cool-off elapses, the handler is invoked again, and it repeats the same non-terminal outcome
- **THEN** the step is cooled off again and no further report is delivered for it

#### Scenario: A step that gets stuck again after moving is reported again

- **WHEN** a step that was reported later records a different outcome, and later still repeats a non-terminal outcome again
- **THEN** a report is delivered for it again

#### Scenario: A pass that cannot read the backoff record delivers no report

- **WHEN** a pass cannot read whether a step has already been reported
- **THEN** the step's handler is invoked, no report is delivered for it, and the access failure is reported

#### Scenario: A report that could not be delivered is not suppressed

- **WHEN** delivery of the report fails
- **THEN** nothing is recorded as reported, and the next pass attempts the report again

#### Scenario: A failed report leaves the pass walking

- **WHEN** delivery of the report fails for one launch's step
- **THEN** the pass continues with the remaining steps and launches, and the pass is still recorded as a successful run

### Requirement: A handler MAY report a typed finding alongside its outcome

A handler's resolution MAY carry, in addition to its outcome and its result text, a typed finding expressed as either a success carrying a value or a failure carrying an error, either of which MAY carry an additional comment — the same generic shape regardless of which handler produced it. A handler that has nothing for another part of the system to consume beyond its outcome and result text SHALL simply not report one; this is the case for every handler that predates this requirement, and is expected to remain the common case.

A finding is not a second copy of the outcome. The outcome answers what becomes of the *step*; a finding, where reported, answers what the handler *discovered* that something outside the launch itself — a product, a later automated step — might need to read. The two SHALL be reported independently: a handler MAY resolve a step `Satisfied` while reporting no finding, and nothing about a reported finding's presence or content SHALL influence which outcome is treated as terminal or how it is held for confirmation.

#### Scenario: A handler reports no finding by default

- **WHEN** a handler that does not report a finding resolves a step
- **THEN** no finding is recorded anywhere on its behalf, and nothing about the step's resolution is affected by its absence

#### Scenario: A finding's presence does not change confirmation

- **WHEN** a handler reports a finding alongside a terminal outcome for a step whose confirmation flag is true
- **THEN** the outcome is still held as a pending result exactly as it would be without a finding

### Requirement: A handler's supported finding is recorded independently of the step's own confirmation

Where a handler reports a finding that is a success, and the deployment has supplied a recording capability for that specific step, the system SHALL invoke that capability with the finding's value as soon as the handler returns and its proposed outcome has passed the hazard-permission check *A terminal outcome the step's hazard forbids is a handler fault, not a recording* — whether or not the outcome that passed is terminal, and whether or not it is held for a member's confirmation. This recording is provisional: it is not an assertion that the step is resolved, only that the handler discovered something worth making available immediately.

Where a handler's proposed outcome fails that hazard-permission check, the whole proposal is a handler fault: nothing is recorded for the step, and the recording capability SHALL NOT be invoked either, for the same reason — a finding produced alongside an outcome the system is treating as though the handler had crashed is not a finding to trust with a write of its own.

Where no recording capability has been supplied for a step, a reported success finding SHALL simply not be recorded anywhere; this is not an error; a handler reporting a finding without the deployment having wired anywhere to put it is exactly the shape every handler took before this requirement existed.

A failure to record a finding SHALL NOT be recorded as any step outcome, SHALL NOT stop the pass, and SHALL be reported naming the launch, the step and the handler — the same treatment `launch-step-automation` already gives a handler failure, because a finding that could not be recorded is a fact about the recording, not a fact about the step's own progress.

Because this recording is provisional, a step's own outcome and the last value recorded from its finding MAY disagree — most concretely, a member rejecting the step's pending result in Slack leaves the step `Blocked` while a value from the proposal that was rejected may already be recorded elsewhere. Reconciling the two is not this requirement's concern.

#### Scenario: A supported finding is recorded immediately

- **WHEN** a handler reports a success finding for a step whose confirmation flag is true, and a recording capability is supplied for that step
- **THEN** the finding's value is recorded before any Slack decision is sought, and independent of what that decision later is

#### Scenario: No recording capability means no recording, silently

- **WHEN** a handler reports a success finding for a step no recording capability has been supplied for
- **THEN** nothing is recorded on the finding's behalf, and this is not reported as a fault

#### Scenario: A failure finding is never recorded this way

- **WHEN** a handler reports a finding that is a failure
- **THEN** no recording capability is invoked — a failure finding carries nothing to record

#### Scenario: An impermissible proposal's finding is never recorded

- **WHEN** a handler proposes a terminal outcome the step's hazard does not permit, alongside a success finding
- **THEN** the recording capability is not invoked, exactly as no step outcome is recorded for that proposal

#### Scenario: A recording failure does not stop the pass

- **WHEN** invoking a step's recording capability fails
- **THEN** no step outcome is recorded as a result of that failure, the failure is reported naming the launch, the step and the handler, and the pass continues

### Requirement: A handler's waiting does not stop the process

A handler SHALL reach a model, a service or a database such that **waiting for the answer yields control to whatever else the invoking process is running**. While a handler's dependency has not yet answered, other work scheduled on the loop the handler was invoked on SHALL continue to progress.

Where a dependency offers an asynchronous entry point, the handler SHALL use it. Where a dependency offers **only** a blocking entry point, the handler SHALL await that call off the invoking thread.

**A framework moving a handler's synchronous code onto a thread on its behalf does not satisfy the first of those.** Where a library accepts synchronous work and runs it in a thread pool when reached asynchronously, a handler that hands it blocking code has not used the dependency's asynchronous entry point — it has relied on an accommodation the library makes for code that could not. Other work on the loop does progress, so such a handler passes the observable above while being the shape this requirement exists to end: the choice is invisible at the call site, it costs a thread per invocation for work that is only waiting, and removing the accommodation later reintroduces the block silently. Where an asynchronous entry point exists, using it is the obligation, and the observable is not the whole of the test.

A thread offload for a dependency that genuinely offers no asynchronous entry point is not an evasion but the correct accommodation, and satisfies this requirement fully. It SHOULD state at the call site why no asynchronous entry point was available — a review obligation rather than one carrying an observable of its own, because nothing at runtime can distinguish an offload chosen deliberately from one nobody examined, and the reason is what a reviewer needs in order to tell the difference.

How a handler waits SHALL NOT change what it produces. A handler converted from a blocking call to an awaited one SHALL produce the same outcome, the same result text and the same finding for the same answers from its dependency.

**This is not a property the handler type can carry.** A handler is registered as returning an awaitable, and a coroutine that never yields satisfies that exactly — `async def` describes what a function returns, not whether the work inside it ever gives the loop back. Nor is it a property a linter checks: a rule that knows a particular HTTP client's blocking call site does not know a third-party library's synchronous entry point. The obligation is therefore stated here rather than delegated to a tool.

Most of it is carried by each handler's own tests, which is why the first clause is expressed as an observable rather than as a prohibition on a syntax. Two clauses are not, and are named as such rather than left to look like clauses nobody bothered to test: which entry point a handler reached is a fact about the source that no runtime observation distinguishes, and why an offload was chosen is a fact only its author knows. Those are held at review. A requirement whose parts are checked in different places is more useful than one narrowed to the part a test can reach.

**Why it matters is a property of the deployment, not a preference.** The recurring work that invokes handlers runs on one loop inside a process that is also doing other things — its own job bookkeeping, any concurrently deferred job, any overlapping pass. The pass invokes handlers one at a time and awaits each, which is what makes one handler's latency cost the pass its own time. A handler that blocks instead makes that latency cost the whole process, for as long as its dependency takes to answer, which for a model call is unbounded.

**This is not a licence to run handlers concurrently.** The pass's serial walk over launches and steps is unchanged, and this requirement governs what a handler owes the process that invokes it, not how the pass invokes one — the pass already awaits each handler correctly.

#### Scenario: A handler's waiting leaves the invoking loop free

- **WHEN** a handler is invoked on a loop that also has other work scheduled, and the handler's dependency has not yet answered
- **THEN** that other work progresses before the handler returns, and the handler then returns its resolution as it otherwise would

#### Scenario: A dependency offering only a blocking call is awaited off the invoking thread

- **WHEN** a handler's only way to reach a dependency is a blocking call, and the handler awaits it off the invoking thread
- **THEN** other work scheduled on the invoking loop still progresses while the handler waits, and the handler satisfies this requirement

#### Scenario: A framework's thread offload does not stand in for a dependency's asynchronous entry point

- **WHEN** a handler hands synchronous code to a library that offers an asynchronous entry point and that runs such code in a thread pool on the handler's behalf
- **THEN** the handler does not satisfy this requirement, notwithstanding that other work on the invoking loop progresses

#### Scenario: How a handler waits does not change what it produces

- **WHEN** a handler that reached its dependency by a blocking call is changed to await the same dependency, and the dependency answers exactly as before
- **THEN** the handler produces the same outcome, the same result text and the same finding as it did before the change

### Requirement: A written finding is kept on the recording it produced

Where a handler reports a supported finding and the step names a sink for it, the system SHALL keep on that step's recording the name of the field the sink writes, the wording that sink gives it, the value written, and the finding's comment — as `launch-instance` provides for.

*"Kept" here is deliberately not "retained".* This capability already uses **retained** for a result held awaiting a member's decision (*A retained result is kept and stays readable as the product's record*), and that is a different record from the one this requirement adds to. The two are related below, and must not be read as one.

**A finding is kept on the recording the value's write belongs to — and for a confirmable step, that recording is made when the result is accepted, not when the handler ran.** This capability already separates the two: a supported finding is written to its sink at the moment the handler runs, *independently of the step's own confirmation*, while a terminal outcome on a step naming a confirmer is held as a pending result and recorded only when a member accepts it. A finding kept only on a recording the pass makes would therefore never reach a confirmable step at all.

So the finding SHALL travel with the pending result: stored alongside the proposed outcome and produced text when the result is held — extending what *A result needing confirmation is held until a member decides* stores — and kept on the recording that acceptance makes, extending what *Accepting a pending result records the proposed outcome* records. A step recording its outcome directly — because it names no confirmer, or because the proposed outcome is non-terminal — SHALL have the finding kept on that recording instead.

**A finding stored with a pending result SHALL follow the same rules `launch-instance` states for one kept on a recording**: one spelling of an empty value, an absent comment carried as absent, and a stored finding that cannot be read reported as none. **A finding that cannot be read at acceptance SHALL NOT fail the acceptance.** The recording and the settlement must both take effect or neither, so a decision a member has made must not be lost to an unreadable field beside it — the outcome the member accepted is what matters, and the finding is what accompanies it.

**The value kept is the value as it was written when the handler ran, and acceptance SHALL NOT re-read the sink.** A pending result suppresses re-invocation of its step, so the handler cannot overwrite it meanwhile; but a direct write elsewhere can, and re-reading at acceptance would silently substitute a later value for the one the member was shown and decided on. What the recording asserts is what the handler established, which is also what the produced text a member read describes.

**A rejected result SHALL keep no finding.** The value written to the product before the proposal was made stands or falls by `product-catalog`'s own rules and is not this requirement's business; but a member rejecting the proposal has declined the fact it asserted, and a `Blocked` recorded from that rejection SHALL NOT carry a finding asserting it anyway.

**Keeping follows the write.** Only a finding actually written to its sink is kept. A finding for a step naming no sink is not written today and SHALL NOT be kept either; where a write did not succeed, no finding SHALL be kept.

**A non-terminal outcome carrying a finding SHALL keep it.** Where a handler writes a finding and proposes a non-terminal outcome, that outcome is recorded directly, and the finding is kept on it. Nothing about keeping a finding is conditional on the outcome being a satisfying one — a fact established about a product is established whether or not the step it came from is resolved.

**The field's name and its wording SHALL both come from the sink's registration and never from the handler.** They are kept together on the recording, so that the surface rendering them needs no registry of its own — see `launch-instance`, which states why. A handler reports a value and a comment; where that value goes is the composition root's knowledge, registered alongside the sink itself. A handler SHALL NOT name a field, and SHALL NOT be given a way to. This is the rule `subcategory-advisor` states as "nothing outside this capability ever needs to know this step in particular has a sub-category field", read in the other direction: the capability does not get to know either.

**Keeping a finding changes nothing about the outcome or the result.** The existing requirement that a reported finding leaves both exactly as they would be for a handler reporting none continues to hold in full. This requirement adds what is kept *beside* them; it does not qualify that one. A handler's produced text is still stored as evidence, unchanged and unabridged.

A handler reporting a `Failure` finding, and a handler reporting none, SHALL cause nothing to be kept.

#### Scenario: A written finding is kept with the field it was written to

- **WHEN** a handler reports a supported finding for a step naming a sink and no confirmer, and the value is written
- **THEN** the recording the pass makes carries that sink's field name and wording, the value written, and the finding's comment

#### Scenario: A confirmable step's finding survives until the result is accepted

- **WHEN** a handler reports a supported finding with a terminal outcome for a step naming a confirmer, and the value is written
- **THEN** the finding is stored with the pending result, and the recording made when a member accepts carries the field name, the value and the comment

#### Scenario: An unreadable stored finding does not fail an acceptance

- **WHEN** a member accepts a pending result whose stored finding cannot be read
- **THEN** the acceptance takes effect, the outcome is recorded, and that recording carries no finding

#### Scenario: The value kept is the value as written

- **WHEN** a pending result's finding is kept on the recording an acceptance makes
- **THEN** the value kept is the one written when the handler ran, and the sink is not re-read at acceptance

#### Scenario: A rejected result keeps no finding

- **WHEN** a member rejects a pending result whose finding was written
- **THEN** the outcome recorded from that rejection carries no finding

#### Scenario: A non-terminal outcome keeps the finding it wrote

- **WHEN** a handler writes a finding and proposes a non-terminal outcome
- **THEN** that outcome is recorded directly and carries the field name, the value and the comment

#### Scenario: The field's name is not the handler's to supply

- **WHEN** a handler reports a supported finding
- **THEN** the field name kept is the one the sink's registration names, and no part of it is taken from the handler

#### Scenario: A finding for a step naming no sink is kept no more than it is written

- **WHEN** a handler reports a supported finding for a step that names no sink
- **THEN** nothing is written and nothing is kept, and the outcome and evidence are recorded as they are for any handler reporting no finding

#### Scenario: A failure finding keeps nothing

- **WHEN** a handler reports a `Failure` finding
- **THEN** nothing is kept, exactly as nothing is written

#### Scenario: A finding whose write did not succeed is not kept

- **WHEN** a handler reports a supported finding and writing it to its sink does not succeed
- **THEN** no finding is kept

#### Scenario: The outcome and the evidence are unaffected by what is kept beside them

- **WHEN** a handler reports a supported finding that is written and kept
- **THEN** the outcome recorded and the evidence stored are exactly what they would have been had the handler reported no finding at all
