# launch-step-automation Specification

## Purpose
Runs the code an `automated` step names, and decides what becomes of what that code produced: recorded against the launch straight away, or held until a person accepts it. This is what makes `kind`, `handler` and `needs_confirmation` do something rather than merely be declared.

## Requirements

### Requirement: An automated step's handler is invoked by recurring work

The system SHALL invoke registered step handlers from recurring work that runs inside the deployment, declaring its schedule and tolerance as `scheduled-jobs` requires of every piece of recurring work. Each pass SHALL consider every launch that has not graduated, and within each launch every step of its served playbook whose kind is `automated`.

A pass SHALL invoke the handler of such a step only where all of the following hold: the launch has released the step (`launch-playbook`, *A step declares when it may start*); the step's recorded outcome is not one the step's hazard permits as terminal; no pending result stands for it; it is not within the cool-off this specification places after a rejection; and it is not within the cool-off this specification places after a handler repeated a non-terminal outcome. `human` steps, steps that are not `active`, steps the launch has not released, and steps already at a permitted terminal outcome SHALL NOT be invoked.

Release is judged by the same rule the projection into a task tracker is judged by, and never by a rule private to this pass: a step's eligibility is one fact about the launch, so that what the system asks of a person and what it asks of a handler cannot drift apart.

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

Confirmation exists so a person accepts a result. A non-terminal outcome is not a result: it is a handler reporting that the step has not been resolved, and holding it would ask a person to accept "in progress" — a proposal with nothing in it to agree or disagree with, which would then suppress re-invocation until they clicked. Recording it directly keeps the reason on the launch's own record, which is what makes a stalled automated step legible rather than merely quiet.

A non-terminal outcome SHALL leave the step eligible for the next pass, **except** where it repeats the non-terminal outcome the step already carries, which the requirement *A handler that repeats itself is not asked again immediately* governs.

#### Scenario: A non-terminal outcome on a confirmable step is recorded, not held

- **WHEN** a handler proposes `Blocked` with a reason for a step whose confirmation flag is true
- **THEN** the outcome is recorded against the launch with `automated` provenance, no pending result is stored, and no decision is requested

#### Scenario: A step reporting no progress is reconsidered on the next pass

- **WHEN** a handler proposes a non-terminal outcome that differs from the one the step already carries, and a later pass runs
- **THEN** the handler is invoked again for that step

### Requirement: A terminal outcome the step's hazard forbids is a handler fault, not a recording

Before storing or recording anything, the system SHALL check a **terminal** outcome a handler proposed against what the step's hazard permits, as `launch-playbook` defines it. A terminal outcome the hazard does not permit SHALL be treated exactly as a handler failure: nothing recorded, nothing stored, the fault reported naming the launch, the step, the handler and the offending outcome.

Checking at production time rather than at recording time is what keeps the fault visible. A `Refused` proposed for a `compliance-obligation` step, stored as a pending result and delivered, would fail only when a person pressed accept — and would then fail identically every time it was pressed, leaving a result that can never be settled.

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

The roster this rule is evaluated against is supplied by the caller, and SHALL answer to **one** stated shape: it SHALL be able to answer who the roster carries, deactivated entries included, since both halves of "known **and** active" are decided here rather than by whatever supplies the roster. A collaborator that cannot answer that — including no collaborator at all — SHALL be refused as a defect of *wiring*: a named error identifying what was supplied and what was expected, raised before the deciding identity is judged. It is raised at the point the identity would be resolved, so a decision already refused for a reason that does not depend on the roster keeps that refusal.

That refusal SHALL NOT be reachable as a decision refusal. A decision refusal is a statement about the decision that was made, so an unreadable collaborator SHALL NOT be resolved into "the roster does not carry that identity", SHALL NOT be reported to the decider as a fact about their identity, and SHALL NOT leave a decider with any reason to believe their roster entry is at fault. The decider SHALL still be told their decision was not processed, and the mis-wiring SHALL be reported where operators see faults rather than only in the Slack reply.

This exists because the opposite arrangement shipped. The collaborator was accepted in whichever of several shapes it happened to arrive in; the shape production actually supplied was none of them; the read fell through to "no such person"; and every decision by every identity — active admins included — was refused as though the roster did not carry them. Unlike the same mis-wiring elsewhere in this repository, it did not fail loudly, and the message it produced pointed at correct roster data instead of at the wiring.

Consequently, the roster a decision is judged against SHALL be the same roster the roster-administration surface writes: an identity that surface holds as active SHALL be able to decide, and no arrangement of the collaborator SHALL be able to refuse every identity alike.

#### Scenario: An unknown identity cannot decide

- **WHEN** a decision arrives from a Slack identity the roster does not know
- **THEN** it is refused, no outcome is recorded, the pending result still stands, and the decider is told

#### Scenario: A deactivated person cannot decide

- **WHEN** a decision arrives from a Slack identity belonging to a person the roster holds as inactive
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

#### Scenario: A collaborator that cannot answer who the roster carries is refused by name

- **WHEN** a decision is judged against a roster collaborator that cannot answer who the roster carries
- **THEN** it is refused with a named error identifying the collaborator supplied and the shape expected, raised before the deciding identity is judged
- **AND** no outcome is recorded and the pending result still stands

#### Scenario: An absent collaborator is refused the same way, not silently

- **WHEN** a decision arrives at a deployment where no roster collaborator was supplied at all
- **THEN** it is refused with the same named wiring error, the decider is told their decision was not processed, and the decision does not fail without an answer

#### Scenario: A mis-wiring is never reported as an unknown identity

- **WHEN** a decision is judged against a roster collaborator that cannot answer who the roster carries
- **THEN** the decider is not told that the roster does not know their Slack identity, and the mis-wiring is reported where operators see faults

#### Scenario: A person the roster carries can decide through the wiring production supplies

- **WHEN** a decision arrives from a Slack identity that the roster-administration surface holds as active, judged against the roster collaborator the running system supplies
- **THEN** that person is resolved and the decision is judged on its merits rather than refused as unknown

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

Every result stored for a decision SHALL be retained whatever state it reaches. Settling a result — as accepted or as rejected — and voiding one SHALL each keep the row, carrying the state it reached and, where a person decided it, who decided and when. Nothing in the decision flow SHALL delete a result.

This narrows three requirements already in this specification. *Accepting records the proposed outcome and names the accepter* says the pending result "SHALL then be settled"; *Rejecting does not terminate the step* says it "SHALL settle the pending result as rejected"; and *A decision on a step the playbook no longer serves is refused* says the system "SHALL void the pending result rather than leaving it standing". Read alone, each could be satisfied by deleting the row. None may be, and a later amendment to any of the three SHALL be read against this requirement.

The system SHALL be able to answer, for one product, every result retained for it: results in every state, results produced for a step the served playbook no longer defines, and results retained for a launch that has since graduated. That answer SHALL be ordered by the moment each result was produced, most recent first, and SHALL be total — results produced at the same moment SHALL be ordered by a stable tiebreak, so that the same stored data is answered in the same order every time.

Retention is already what the store does; what this requires is that it be *readable as a record*. Every read the store offers today serves the decision loop — the pending result for a step, a result by its identifier, the undelivered ones, the most recent rejection — and none of them answers "what has been produced for this product". Without such a read, "settled rows are kept, never deleted" buys storage and nothing else: the record of a compliance-adjacent decision exists and is reachable only by querying the database directly.

The read SHALL be filtered by the caller's access scope, in the shape every other product-keyed read follows: for a product the scope does not permit, it SHALL answer exactly as it does for a product with nothing retained, so that reading can never confirm the existence of a product or a result the caller may not see.

#### Scenario: A settled result is still readable

- **WHEN** every result retained for a product is read after one of them was accepted and another rejected
- **THEN** both are answered, each carrying the state it reached, the person who decided it and the moment of the decision

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

Every result the system retains SHALL be one held for a decision — a terminal outcome the step's hazard permits, proposed for a step whose confirmation flag is true, and actually stored. An outcome recorded directly SHALL NOT be retained here: neither a non-terminal outcome, which this specification records against the launch whatever the confirmation flag says, nor a terminal outcome on a step needing no confirmation.

Stated as a necessary condition and not as a biconditional, because the converse is false and this specification already says why: a terminal outcome the step's hazard forbids stores nothing at all (*A terminal outcome the step's hazard forbids is a handler fault, not a recording*), and a second proposal racing an existing pending one stores nothing either (*A result needing confirmation is held until a person decides*). A consumer may rely on everything in the record being a proposal someone was asked to accept; it may not rely on the record holding every such proposal ever made.

This states no new routing policy. Which outcomes are held and which are recorded directly is settled by three requirements already in this specification — *A non-terminal outcome is recorded directly and never held for a decision*, *A result needing no confirmation is recorded at once* and *A result needing confirmation is held until a person decides* — and this requirement is their consequence, not a second statement of them. Where they change, this changes with them.

What it adds is the boundary as a fact *about the retained set*, which a consumer reads rather than derives. The retained set is the record of **what people were asked to accept**, not the record of everything handlers produced; a consumer that presented it as the latter would be wrong in a way its readers could not detect, and most wrong for exactly those products whose automated steps need no confirmation.

#### Scenario: An outcome needing no confirmation is not retained

- **WHEN** a handler resolves a step whose confirmation flag is false, and every result retained for that product is read
- **THEN** nothing is answered for that step

#### Scenario: A non-terminal outcome is not retained

- **WHEN** a handler proposes a non-terminal outcome for a step whose confirmation flag is true, and every result retained for that product is read
- **THEN** nothing is answered for that step

### Requirement: A handler that repeats itself is not asked again immediately

Where a handler proposes a non-terminal outcome that is the same as the one the step already carries, the system SHALL record that outcome as it records any other, and SHALL NOT invoke that step's handler again until a fixed cool-off has elapsed **since that repeat was noted**. Once it has, a pass SHALL invoke the handler again; where the handler repeats itself again, the step SHALL be cooled off again from that later repeat.

Two non-terminal outcomes are **the same** where they are outcomes of the same kind, disregarding any reason either carries. The reason a handler gives SHALL NOT be part of that judgement: a handler may word the same reason differently on each call — an LLM-backed handler always will — and a rule comparing reasons would find no two reports alike, engage never, and appear to work while changing nothing.

The outcome being repeated is the one the step carries, **whatever recorded it**. A `Blocked` outcome a person's rejection recorded can serve as the first of the two: the step is then cooled off on the handler's first statement rather than its second. This is intended — the rejection cool-off already governs that window, and a step a person has just rejected and a handler then declines to resolve is stuck by any reading.

A repeat SHALL be established from two recordings rather than predicted from one. A step reporting a non-terminal outcome for the first time stays eligible for the next pass, because whether the handler has more to say is not knowable without asking it. This deliberately spends one further invocation on a step that turns out to be stuck, which is what distinguishes it from a step that is progressing.

The cool-off SHALL be a fixed property of the system rather than a configured one, and SHALL be independent of the cool-off placed after a rejection: the two answer different questions, and a step that has repeated itself SHALL NOT be affected by a change to the rejection cool-off.

A cool-off SHALL cease to govern the step as soon as the step's recorded outcome is no longer an outcome **of the kind** the cool-off was noted against — including where something other than a pass recorded it. Nothing SHALL be required to actively lift it. The kind is what matters here for the same reason it is what matters above: a `Blocked` re-recorded with different wording is the same kind, and must not lift a cool-off.

The judgement SHALL NOT be made from the launch journal. A dropped journal entry must never change what the system does: `launch-journal` keeps a record for people, and it is safe to lose exactly because no behaviour reads it.

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

Where a handler repeats a non-terminal outcome and the step is cooled off, the system SHALL report that step once — naming the launch, the step, and **what the handler produced as its result**, which for a `Blocked` outcome is also the reason it carries — so that a person can supply what the handler is missing. A handler that cannot resolve a step is reporting work only a person can do, and a record nobody reads is not a report. The result is reported as what the handler said, never asserted as a fact about the product.

The report SHALL be delivered once for as long as the step stays stuck, and SHALL NOT be repeated on every pass **nor on each expiry of the cool-off**: a step stuck for a week is one message, not seven. A step whose recorded outcome later changes, or which reaches an outcome its hazard permits as terminal, SHALL become eligible to be reported again if it later gets stuck.

Two passes running over the same step at once MAY each deliver the report, since neither can see the other's delivery before it happens. A duplicate message is the accepted cost of writing the record only after a delivery succeeds.

Where the system cannot read whether a step has already been reported, it SHALL deliver no report for that step on that pass. A report that cannot be recorded as delivered cannot be delivered *once*, and attempting one anyway would turn a store outage into a report on every pass — the repetition this requirement exists to prevent. This is the opposite degrade from the one *A handler that repeats itself is not asked again immediately* places on invocation, and deliberately so: an unresolved step is the worse outcome there, and an unread channel is the worse outcome here. The access failure is itself reported, and the step is reported normally on the first pass that can read the record again.

The record that suppresses further reports SHALL be written only after a delivery has succeeded. Recording first and then failing to deliver would silence the step for as long as it stays stuck, which is precisely the period the report exists to cover.

A failure to deliver the report SHALL NOT fail the pass, SHALL NOT stop the remaining launches or steps from being walked, and SHALL NOT record any outcome.

#### Scenario: A newly cooled-off step is reported

- **WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
- **THEN** a report naming the launch, the step and what the handler produced as its result is delivered

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
