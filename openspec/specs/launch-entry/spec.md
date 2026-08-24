# launch-entry Specification

## Purpose
The launch-entry capability is how a new product enters the system: one Slack interaction registers the product in the catalog and starts its launch against the served live playbook, recording its version identifier as the launch's audit stamp. It owns the modal's contract, the atomicity of the register-and-start pair, where each kind of rejection is surfaced, the verification every request passes before anything is acted on, and the boundary that entry never projects work into ClickUp.

## Requirements

### Requirement: A launch is started from Slack in one interaction

The system SHALL provide a Slack slash command on the `product_agent` app that opens a modal collecting a new product's SKU and name (required), its ASIN and launch date (optional), and a marketplace selection (required, preselected to the single offered option). Submitting the modal SHALL register the product in the catalog and start its launch against the served playbook, recording the served playbook's version identifier on the launch as its audit stamp, and SHALL confirm the outcome with a message naming the product, its launch date (or its absence), and that tracked work appears in ClickUp on the sync cadence.

#### Scenario: A launch is started with a date

- **WHEN** the modal is submitted with a valid SKU, name, and launch date
- **THEN** the product is registered and its launch exists, recording the served playbook's version identifier, with that launch date
- **AND** a confirmation message is posted

#### Scenario: A launch is started without a date

- **WHEN** the modal is submitted with only the required fields
- **THEN** the launch exists with no launch date and no derived due periods
- **AND** the confirmation names the absence of a date

#### Scenario: The playbook version is never user input

- **WHEN** the modal is displayed
- **THEN** it contains no playbook-version field, and the started launch records the served playbook's version identifier

### Requirement: Registration and start are atomic

A submission SHALL either persist both the catalog product and its launch, or persist nothing. A rejection anywhere in the pair SHALL leave no partial state behind.

#### Scenario: A rejected start leaves no product behind

- **WHEN** a submission's product registration succeeds but its launch start is rejected
- **THEN** neither the product nor a launch is persisted
- **AND** resubmitting the same SKU is not rejected as a duplicate

### Requirement: Rejections are surfaced where the user is

A missing or malformed field SHALL be rejected inline in the open modal, attached to the offending field. A domain rejection established only at persistence time (a duplicate SKU, an already-launched product) SHALL be reported to the submitting user as an error message naming the rejection, with nothing persisted.

#### Scenario: A missing required field keeps the modal open

- **WHEN** the modal is submitted without a SKU or without a name
- **THEN** the modal stays open showing the error on that field, and nothing is persisted

#### Scenario: A duplicate SKU is rejected with nothing persisted

- **WHEN** the modal is submitted with a SKU that already identifies a catalog product
- **THEN** the user is told the SKU is already registered
- **AND** no second product and no launch is persisted

### Requirement: Acknowledgement is independent of persistence, and a post-acknowledgement failure is visible

A modal submission SHALL be acknowledged within Slack's acknowledgement window regardless of how long its persistence takes. A failure of the persistence occurring after acknowledgement — a domain rejection or an infrastructure failure alike — SHALL be reported to the submitting user as a message naming the failure, with nothing persisted; it SHALL NOT pass silently. A failure to deliver a message after a successful commit leaves the commit standing — delivery failure is not grounds to unwind persisted state.

#### Scenario: A slow transaction does not miss the acknowledgement window

- **WHEN** a valid submission's persistence outlasts Slack's acknowledgement window
- **THEN** the submission was already acknowledged within the window, and the outcome is delivered afterwards as a message

#### Scenario: A post-acknowledgement failure reaches the user

- **WHEN** persistence fails after the submission was acknowledged and the modal closed
- **THEN** the submitting user receives an error message naming the failure
- **AND** nothing is persisted

### Requirement: Requests are verified before anything is acted on

Slack requests to this surface SHALL be verified against the `product_agent` app's signing secret before any collaborator is touched. An unverifiable request SHALL be rejected; an absent signing secret SHALL reject every request rather than treating "nothing to check" as passing. A request whose handling would require the bot's reply credential SHALL be rejected when that credential is absent or empty, rather than acknowledged.

#### Scenario: An unverifiable request is rejected

- **WHEN** a request arrives whose signature does not verify
- **THEN** it is rejected and nothing is persisted

#### Scenario: No configured secret rejects everything

- **WHEN** the signing secret is absent from the environment and any request arrives
- **THEN** the request is rejected

#### Scenario: An absent reply credential rejects rather than strands

- **WHEN** a request whose handling would need the bot's reply credential arrives and no bot token is configured
- **THEN** the request is rejected rather than acknowledged and left undeliverable

### Requirement: Entry never projects work

Starting a launch through this surface SHALL NOT create, update, or delete anything in ClickUp. Projection of the launch's work is owned by the ClickUp completion loop, whose next convergence pass picks the new launch up.

#### Scenario: A started launch touches no external tracker

- **WHEN** a submission succeeds
- **THEN** no ClickUp call was made by the entry surface
- **AND** the launch is picked up by the completion loop's next pass with no involvement from this surface
