## MODIFIED Requirements

### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

The system SHALL deliver each pending result to Slack, as a reply within that launch's Slack thread — establishing the thread first if it does not yet exist — naming the product, the step, the outcome the handler proposed and the produced text in full, offering an accept and a reject decision, and tagging the step's named confirmer.

Delivery SHALL work from a pending result in the form the store hands it back. A delivery path that requires an identifier in a form the store does not produce delivers nothing at all, while satisfying any test that supplies the form it wants — and because an undelivered result is retried, the permanent failure is indistinguishable in the record from a transient one.

The accept and reject decisions SHALL name the launch and the step the pending result was stored against, so that a decision made on them resolves that result. Where the message or the controls name the launch or the product by an identifier, they SHALL carry that identifier's own value and never a rendering of the object holding it, per `shared-vocabulary`'s requirement on the textual form of a value.

**Tagging a person means the message carries a mention Slack resolves to them.** A step's confirmer is stored as the roster's own identifier for that person, which Slack cannot resolve; a message carrying it renders as inert literal text and notifies nobody, which satisfies no part of this requirement. The system SHALL resolve the step's confirmer through the roster to that person's Slack identity, and tag them with it.

A named confirmer SHALL be treated as **resolvable for tagging** only where the roster carries them, carries them with a Slack identity, and carries them as still active. A deactivated confirmer is not resolvable for tagging, though their Slack identity survives deactivation: *Only the step's named confirmer may decide a pending result* accepts a decision only from a confirmer who is still active, so tagging a deactivated one would summon a person whose accept and reject are certain to be refused — and the result would stay held pending regardless, as `playbook-authoring` specifies for exactly this case.

Where the named confirmer is not resolvable for tagging, the pending result SHALL still be delivered, carrying no mention, and the gap SHALL be reported naming the step, the launch and the unresolvable confirmer — the same trade the ClickUp projection makes for an assignee with no ClickUp account, and for the same reason: a failed delivery would hide a data gap behind a retry. The launch's submitter SHALL NOT be tagged in the confirmer's place. Only the named confirmer may decide a pending result, so tagging anyone else summons a person whose decision is refused; and a step naming no confirmer and a step naming one who cannot be tagged are different facts that must not read identically to a person watching the thread.

Where the roster cannot be read at all — no reader, a reader of the wrong shape, or one that fails — the pending result SHALL still be delivered, carrying no mention, and the failure SHALL be reported. The substance of the ask does not depend on the roster, and withholding it to avoid an untagged message would trade a message somebody might miss for no message at all.

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

- **WHEN** a pending result is delivered for a step naming a confirmer the roster carries, active and with a Slack identity
- **THEN** the message mentions that person by their Slack identity, and the roster's own identifier for them appears nowhere in it

#### Scenario: A confirmer the roster does not carry is not mentioned, and the gap is reported

- **WHEN** a pending result is delivered for a step naming a confirmer the roster does not carry
- **THEN** the message is still delivered naming the product, the step and the produced text, carrying no mention and not tagging the submitter, and the unresolvable confirmer is reported

#### Scenario: A deactivated confirmer is not mentioned, and the gap is reported

- **WHEN** a pending result is delivered for a step whose named confirmer has been deactivated on the roster
- **THEN** the message is still delivered, carrying no mention and not tagging the submitter, and the deactivated confirmer is reported — the decision could not be accepted from them in any case

#### Scenario: A pending result is delivered untagged when the roster cannot be read

- **WHEN** a pending result is delivered for a step naming a confirmer and the roster cannot be read at all
- **THEN** the result is still delivered, carrying no mention, and the roster failure is reported

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

### Requirement: A step whose handler has stopped making progress is reported once

Where a handler repeats a non-terminal outcome and the step is cooled off, the system SHALL report that step once — as a reply within the launch's Slack thread, establishing the thread first if it does not yet exist — naming the launch, the step, and **what the handler produced as its result**, which for a `Blocked` outcome is also the reason it carries, and tagging the step's named confirmer where the step names one, the launch's submitter otherwise, so that a person can supply what the handler is missing. A handler that cannot resolve a step is reporting work only a person can do, and a record nobody reads is not a report. The result is reported as what the handler said, never asserted as a fact about the product.

**Tagging a person means the message carries a mention Slack resolves to them**, on the same terms this capability's delivery requirement states: the step's confirmer is stored as the roster's own identifier and SHALL be resolved through the roster to that person's Slack identity, and is resolvable for tagging only where the roster carries them, with a Slack identity, and still active. The launch's submitter is already a Slack identity and needs no resolution, which is why a step naming no confirmer is unaffected by whether the roster can be read.

Where the named confirmer is not resolvable for tagging, or the roster cannot be read at all, the report SHALL still be delivered, SHALL tag the launch's submitter, and SHALL name in its text that the step's confirmer could not be resolved. The gap SHALL also be reported.

**This report falls back to the submitter where the pending-result ask does not, and the difference is deliberate.** No authorization rule governs who may act on a stuck step: the report exists so that *a person* can supply what the handler is missing, so reaching somebody is the whole of its purpose, and an untagged report reaching nobody would defeat it. The ask is the opposite — only the named confirmer may decide it, so a fallback tag there summons a person whose decision is refused. Naming the unresolved confirmer in the text is what keeps the two facts distinct here without withholding the mention: a reader can still tell a step that names no confirmer from one whose confirmer cannot be reached.

Where the report names the launch or the product by an identifier, it SHALL carry that identifier's value and not a rendering of the object holding it, per `shared-vocabulary`.

The report SHALL be delivered once for as long as the step stays stuck, and SHALL NOT be repeated on every pass **nor on each expiry of the cool-off**: a step stuck for a week is one message, not seven. A step whose recorded outcome later changes, or which reaches an outcome its hazard permits as terminal, SHALL become eligible to be reported again if it later gets stuck.

Two passes running over the same step at once MAY each deliver the report, since neither can see the other's delivery before it happens. A duplicate message is the accepted cost of writing the record only after a delivery succeeds.

Where the system cannot read whether a step has already been reported, it SHALL deliver no report for that step on that pass. A report that cannot be recorded as delivered cannot be delivered *once*, and attempting one anyway would turn a store outage into a report on every pass — the repetition this requirement exists to prevent. This is the opposite degrade from the one *A handler that repeats itself is not asked again immediately* places on invocation, and deliberately so: an unresolved step is the worse outcome there, and an unread channel is the worse outcome here. The access failure is itself reported, and the step is reported normally on the first pass that can read the record again.

An unreadable *roster* degrades differently again, and only the mention: the report is delivered, tagged to the submitter, and the failure reported — because the substance of the report does not depend on the roster, and because the roster is not what decides whether this message may be sent.

The record that suppresses further reports SHALL be written only after a delivery has succeeded. Recording first and then failing to deliver would silence the step for as long as it stays stuck, which is precisely the period the report exists to cover.

A failure to deliver the report SHALL NOT fail the pass, SHALL NOT stop the remaining launches or steps from being walked, and SHALL NOT record any outcome.

#### Scenario: A newly cooled-off step is reported

- **WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
- **THEN** a report naming the launch, the step and what the handler produced as its result is delivered as a reply within the launch's Slack thread

#### Scenario: A stuck step naming a confirmer tags that confirmer

- **WHEN** a report is delivered for a stuck step naming a confirmer the roster carries, active and with a Slack identity
- **THEN** the message mentions that person by their Slack identity, and the roster's own identifier for them appears nowhere in it

#### Scenario: A stuck step naming no confirmer tags the submitter

- **WHEN** a report is delivered for a stuck step that names no confirmer
- **THEN** the message tags the launch's submitter instead

#### Scenario: A stuck step whose confirmer cannot be resolved tags the submitter and names the gap

- **WHEN** a report is delivered for a stuck step naming a confirmer the roster does not carry, or carries without a Slack identity, or carries as deactivated
- **THEN** the report is delivered tagging the launch's submitter, its text names that the step's confirmer could not be resolved, and the gap is reported

#### Scenario: A stuck step is reported to the submitter when the roster cannot be read

- **WHEN** a report is delivered for a stuck step naming a confirmer and the roster cannot be read at all
- **THEN** the report is delivered tagging the submitter, naming that the confirmer could not be resolved, and the roster failure is reported

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
