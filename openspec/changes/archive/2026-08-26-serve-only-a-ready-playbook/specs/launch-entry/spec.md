## ADDED Requirements

### Requirement: A launch is not started against a playbook that cannot hold one

Starting a launch SHALL require a playbook that is ready to be served — one in which every gate has at least one active blocking step. When it is not, the submission SHALL be rejected with nothing persisted, and the user SHALL be told which gates hold no active blocking step, so the message identifies the work needed rather than reporting an internal failure.

This rejection SHALL be surfaced the way other domain rejections established at persistence time are: to the submitting user, naming the reason, with nothing persisted. It SHALL NOT be reported as a malformed field, because no field the user filled in caused it.

#### Scenario: A start against an unready playbook is refused

- **WHEN** the modal is submitted while one or more gates hold no active blocking step
- **THEN** the user is told the playbook cannot yet hold a launch, and the message names those gates
- **AND** neither the product nor a launch is persisted

#### Scenario: A start against a ready playbook is unaffected

- **WHEN** the modal is submitted while every gate holds at least one active blocking step
- **THEN** the launch starts exactly as it does today, recording the served playbook's version identifier
