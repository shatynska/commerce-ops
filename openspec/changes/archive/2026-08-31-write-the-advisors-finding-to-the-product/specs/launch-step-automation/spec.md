## MODIFIED Requirements

### Requirement: A handler receives the step, the launch and the product, and attributes nothing

A handler SHALL be given the step definition it is resolving, a read of the launch it is resolving against, the catalog product that launch is for, and the moment the pass is running as of. The catalog product SHALL be resolved by the system and supplied to the handler, never fetched by the handler itself — a handler is a function of the context it is given and nothing else, which is what allows it to be exercised without a database and keeps the catalog read in one place rather than one place per handler.

A handler SHALL return an outcome from the `launch-playbook` outcome vocabulary together with the result it produced, expressed as text a person can read. The produced text SHALL NOT be empty: it becomes the recorded evidence, which `launch-instance` requires of every recording. A handler MAY additionally report a typed finding alongside its outcome and result — see *A handler MAY report a typed finding alongside its outcome*. Doing so changes nothing about the outcome or the result: both continue to mean exactly what they mean for a handler that reports no finding at all.

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

#### Scenario: A finding changes nothing about the outcome or the result

- **WHEN** a handler reports a typed finding alongside its outcome and result
- **THEN** the outcome is recorded, and the result is stored as evidence, exactly as they would be for a handler reporting no finding

## ADDED Requirements

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

Where a handler reports a finding that is a success, and the deployment has supplied a recording capability for that specific step, the system SHALL invoke that capability with the finding's value as soon as the handler returns and its proposed outcome has passed the hazard-permission check *A terminal outcome the step's hazard forbids is a handler fault, not a recording* — whether or not the outcome that passed is terminal, and whether or not it is held for a person's confirmation. This recording is provisional: it is not an assertion that the step is resolved, only that the handler discovered something worth making available immediately.

Where a handler's proposed outcome fails that hazard-permission check, the whole proposal is a handler fault: nothing is recorded for the step, and the recording capability SHALL NOT be invoked either, for the same reason — a finding produced alongside an outcome the system is treating as though the handler had crashed is not a finding to trust with a write of its own.

Where no recording capability has been supplied for a step, a reported success finding SHALL simply not be recorded anywhere; this is not an error; a handler reporting a finding without the deployment having wired anywhere to put it is exactly the shape every handler took before this requirement existed.

A failure to record a finding SHALL NOT be recorded as any step outcome, SHALL NOT stop the pass, and SHALL be reported naming the launch, the step and the handler — the same treatment `launch-step-automation` already gives a handler failure, because a finding that could not be recorded is a fact about the recording, not a fact about the step's own progress.

Because this recording is provisional, a step's own outcome and the last value recorded from its finding MAY disagree — most concretely, a person rejecting the step's pending result in Slack leaves the step `Blocked` while a value from the proposal that was rejected may already be recorded elsewhere. Reconciling the two is not this requirement's concern.

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
