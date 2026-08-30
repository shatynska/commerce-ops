## MODIFIED Requirements

### Requirement: A non-terminal outcome is recorded directly and never held for a decision

Where the outcome a handler proposes is not terminal — `NotStarted`, `InProgress` or `Blocked`, none of which `launch-playbook` permits as terminal for any step — the system SHALL record it against the launch immediately with the provenance it constructed, **whatever confirmer the step names**, and SHALL NOT store it as a pending result or seek a decision on it.

Confirmation exists so a named confirmer accepts a result. A non-terminal outcome is not a result: it is a handler reporting that the step has not been resolved, and holding it would ask a person to accept "in progress" — a proposal with nothing in it to agree or disagree with, which would then suppress re-invocation until they clicked. Recording it directly keeps the reason on the launch's own record, which is what makes a stalled automated step legible rather than merely quiet.

A non-terminal outcome SHALL leave the step eligible for the next pass, **except** where it repeats the non-terminal outcome the step already carries, which the requirement *A handler that repeats itself is not asked again immediately* governs.

#### Scenario: A non-terminal outcome on a confirmable step is recorded, not held

- **WHEN** a handler proposes `Blocked` with a reason for a step naming a confirmer
- **THEN** the outcome is recorded against the launch with `automated` provenance, no pending result is stored, and no decision is requested

#### Scenario: A step reporting no progress is reconsidered on the next pass

- **WHEN** a handler proposes a non-terminal outcome that differs from the one the step already carries, and a later pass runs
- **THEN** the handler is invoked again for that step

### Requirement: A result needing no confirmation is recorded at once

Where the resolved step names no confirmer, the system SHALL record the handler's outcome against the launch immediately, with the provenance it constructed. No decision is sought and nothing is held.

#### Scenario: An unconfirmed result is recorded directly

- **WHEN** a handler resolves a step that names no confirmer
- **THEN** the outcome is recorded against the launch with `automated` provenance, and no decision is requested

### Requirement: A result needing confirmation is held until a person decides

Where the resolved step names a confirmer **and the outcome the handler proposed is terminal**, the system SHALL NOT record that outcome. It SHALL store the produced result as a pending result against that launch and step — carrying the outcome the handler proposed, the produced text, the handler, and when it was produced — and SHALL seek a decision on it.

At most one pending result SHALL stand for a launch and step at any moment. A step awaiting a person is not a step awaiting more work, and a second result would leave two proposals and no way to say which was decided.

#### Scenario: A confirmable terminal result is held rather than recorded

- **WHEN** a handler proposes a terminal outcome for a step naming a confirmer
- **THEN** no outcome is recorded against the launch, and a pending result is stored carrying the proposed outcome, the produced text, the handler and the moment it was produced

#### Scenario: A pending result suppresses re-invocation

- **WHEN** a pass runs while a pending result stands for a launch and step
- **THEN** that step's handler is not invoked and the pending result is left as it is

#### Scenario: Two overlapping passes cannot both produce a pending result

- **WHEN** two passes overlap and both would store a pending result for the same launch and step
- **THEN** exactly one pending result stands, and the step is left for a later pass

### Requirement: The retained record covers results held for a decision and nothing else

Every result the system retains SHALL be one held for a decision — a terminal outcome the step's hazard permits, proposed for a step naming a confirmer, and actually stored. An outcome recorded directly SHALL NOT be retained here: neither a non-terminal outcome, which this specification records against the launch whatever confirmer the step names, nor a terminal outcome on a step naming no confirmer.

Stated as a necessary condition and not as a biconditional, because the converse is false and this specification already says why: a terminal outcome the step's hazard forbids stores nothing at all (*A terminal outcome the step's hazard forbids is a handler fault, not a recording*), and a second proposal racing an existing pending one stores nothing either (*A result needing confirmation is held until a person decides*). A consumer may rely on everything in the record being a proposal someone was asked to accept; it may not rely on the record holding every such proposal ever made.

This states no new routing policy. Which outcomes are held and which are recorded directly is settled by three requirements already in this specification — *A non-terminal outcome is recorded directly and never held for a decision*, *A result needing no confirmation is recorded at once* and *A result needing confirmation is held until a person decides* — and this requirement is their consequence, not a second statement of them. Where they change, this changes with them.

What it adds is the boundary as a fact *about the retained set*, which a consumer reads rather than derives. The retained set is the record of **what people were asked to accept**, not the record of everything handlers produced; a consumer that presented it as the latter would be wrong in a way its readers could not detect, and most wrong for exactly those products whose automated steps name no confirmer.

#### Scenario: An outcome needing no confirmation is not retained

- **WHEN** a handler resolves a step that names no confirmer, and every result retained for that product is read
- **THEN** nothing is answered for that step

#### Scenario: A non-terminal outcome is not retained

- **WHEN** a handler proposes a non-terminal outcome for a step naming a confirmer, and every result retained for that product is read
- **THEN** nothing is answered for that step

### Requirement: Accepting records the proposed outcome and names the accepter

Accepting a pending result SHALL record, against the launch, exactly the outcome the handler proposed, with source `automated`, naming the accepting person, carrying the moment of the decision, and carrying evidence that names both the handler that produced the result and the produced text itself. The pending result SHALL then be settled and SHALL no longer suppress re-invocation.

The source stays `automated` because the work was the handler's; who accepted it is what the recorder names; and the evidence names the handler so that the launch's own record answers what produced the accepted result, without depending on the pending-result store still holding the row.

The recording and the settlement SHALL both take effect, or neither: a settled result whose outcome was never recorded would be undecidable and unrecoverable.

#### Scenario: An accepted result becomes the step's outcome

- **WHEN** the step's named confirmer accepts a pending result proposing `Satisfied`
- **THEN** `Satisfied` is recorded for that step with source `automated`, naming the accepter and the moment of the decision, with evidence naming the handler and carrying the produced text

#### Scenario: A failed recording leaves the result decidable

- **WHEN** recording the outcome for an accepted pending result fails
- **THEN** the pending result is not settled and the decision can be made again

### Requirement: Rejecting does not terminate the step

Rejecting a pending result SHALL record a `Blocked` outcome against the launch, whose reason names the rejecting person and states that an automated result was rejected, with source `automated` and the rejecting person as the recorder. It SHALL settle the pending result as rejected, and SHALL leave the step available for a handler to resolve again on a later pass.

`Blocked` is chosen from among the non-terminal outcomes because it is the one that carries a reason, and a rejection whose reason was not recorded would leave the launch showing an unresolved step with nothing saying why. The source stays `automated` for the same reason acceptance does: the work being rejected was a handler's.

A rejection SHALL NOT be recorded as `Refused`. `Refused` is reserved by `launch-playbook` for a step whose hazard is `prohibited-tactic`, and means the tactic itself was recognised and declined; a person declining one produced result has said nothing about the step's permissibility. Nor SHALL it be recorded as `NotApplicable`, which is terminal and would close a step whose work still stands.

#### Scenario: A rejected result leaves the step live

- **WHEN** the step's named confirmer rejects a pending result
- **THEN** a `Blocked` outcome is recorded whose reason names the rejecter, with source `automated` and the rejecter as recorder, and the step is not at a terminal outcome

#### Scenario: Rejection is never a refusal

- **WHEN** a pending result for a step whose hazard is not `prohibited-tactic` is rejected
- **THEN** the recorded outcome is not `Refused` and is not `NotApplicable`

## ADDED Requirements

### Requirement: Only the step's named confirmer may decide a pending result

A pending result exists only for a step that names a confirmer — a step naming none is recorded directly and never held (*A result needing confirmation is held until a person decides*). The system SHALL accept a decision on a pending result only from the Slack identity belonging to that step's named confirmer, and only where the confirmer is still active on the roster. A decision from any other identity — known to the roster or not, active or not — SHALL be refused, SHALL record no outcome, SHALL leave the pending result standing, and SHALL tell the decider it was refused.

Decisions arrive on the same verified `product_agent` Slack surface `launch-entry` already uses, so a decision whose authenticity cannot be established never reaches this rule; and a decision SHALL be acknowledged within Slack's timeout independently of whether the recording it triggers has completed.

The roster this rule is evaluated against is supplied by the caller, and SHALL answer to **one** stated shape: it SHALL be able to answer who the roster carries, deactivated entries included, since resolving the deciding Slack identity to a roster person, checking that person against the step's named confirmer, and checking that person's active status are all decided here rather than by whatever supplies the roster. A collaborator that cannot answer that — including no collaborator at all — SHALL be refused as a defect of *wiring*: a named error identifying what was supplied and what was expected, raised before the deciding identity is judged. It is raised at the point the identity would be resolved, so a decision already refused for a reason that does not depend on the roster keeps that refusal.

That refusal SHALL NOT be reachable as a decision refusal. A decision refusal is a statement about the decision that was made, so an unreadable collaborator SHALL NOT be resolved into "this identity is not the confirmer", SHALL NOT be reported to the decider as a fact about their identity, and SHALL NOT leave a decider with any reason to believe their roster entry or their standing as confirmer is at fault. The decider SHALL still be told their decision was not processed, and the mis-wiring SHALL be reported where operators see faults rather than only in the Slack reply.

This carries forward a fault this system has already shipped once, on the wider rule this replaces: a roster collaborator accepted in whichever shape it happened to arrive in, production supplying none of the shapes read, and every decision by every identity refused as though the roster carried nobody — silently, and pointing at correct roster data instead of at the wiring.

Consequently, the roster a decision is judged against SHALL be the same roster the roster-administration surface writes and the same playbook a step's confirmer is read from: an identity the roster holds as active, and the step names as confirmer, SHALL be able to decide, and no arrangement of the collaborator SHALL be able to refuse every identity alike.

#### Scenario: The named confirmer can decide

- **WHEN** a decision arrives from the Slack identity belonging to the step's named confirmer, whom the roster holds as active
- **THEN** it is accepted, and the pending result is settled per *Accepting records the proposed outcome and names the accepter* or *Rejecting does not terminate the step*

#### Scenario: An unknown identity cannot decide

- **WHEN** a decision arrives from a Slack identity the roster does not know
- **THEN** it is refused, no outcome is recorded, the pending result still stands, and the decider is told

#### Scenario: Someone other than the confirmer cannot decide

- **WHEN** a decision arrives from a Slack identity belonging to a person the roster holds as active, who is not the step's named confirmer
- **THEN** it is refused, no outcome is recorded, and the pending result still stands

#### Scenario: A deactivated confirmer cannot decide

- **WHEN** a decision arrives from the Slack identity belonging to the step's named confirmer, whose roster entry the roster holds as inactive
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
- **THEN** the decider is not told that their identity is not the confirmer, and the mis-wiring is reported where operators see faults

## REMOVED Requirements

### Requirement: Only a known, active person may decide a pending result

**Reason**: Decision authority on a pending result narrows from any known, active roster person to the one person the step names as its `confirmer` — `add-step-confirmer` replaces the `needs_confirmation` flag with a named confirmer specifically so that responsibility for a decision is unambiguous. Superseded by *Only the step's named confirmer may decide a pending result*.

**Migration**: No stored data changes. Deployed behavior changes: a Slack identity that could previously decide by virtue of being active on the roster can no longer decide unless the roster also names them as the step's confirmer.
