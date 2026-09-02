## MODIFIED Requirements

### Requirement: A handler receives the step, the launch and the product, and attributes nothing

A handler SHALL be given the step definition it is resolving, a read of the launch it is resolving against, the catalog product that launch is for, and the moment the pass is running as of. The catalog product SHALL be resolved by the system and supplied to the handler, never fetched by the handler itself — a handler is a function of the context it is given and nothing else, which is what allows it to be exercised without a database and keeps the catalog read in one place rather than one place per handler.

A handler SHALL return an outcome from the `launch-playbook` outcome vocabulary together with the result it produced, expressed as text a person can read. The produced text SHALL NOT be empty: it becomes the recorded evidence, which `launch-instance` requires of every recording. A handler MAY additionally report a typed finding alongside its outcome and result — see *A handler MAY report a typed finding alongside its outcome*. Doing so changes nothing about the outcome or the result: both continue to mean exactly what they mean for a handler that reports no finding at all.

A handler with nothing conclusive to report SHALL say so through a **non-terminal** outcome whose reason states why — never by proposing a terminal outcome it cannot support, and never by failing. Of the three non-terminal outcomes only `Blocked` can itself carry a reason; where a handler proposes one that cannot, the produced text SHALL state the reason instead, so that a stalled step is legible rather than merely quiet.

A handler SHALL NOT supply its own recording provenance. The system SHALL construct the provenance for every outcome a handler produces, with source `automated`, naming the handler as what did the work, the moment of the run, and the produced result as the evidence. A handler therefore cannot record work as having come from a person or from ClickUp.

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
