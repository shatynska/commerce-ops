## MODIFIED Requirements

### Requirement: A launch record establishes and persists its Slack thread once

The system SHALL persist, against a launch record, the Slack identity of whoever submitted it and an optional Slack thread reference. The submitter SHALL be recorded once, when the launch is started, and SHALL NOT change afterward. The thread reference SHALL be absent until first needed, established by whichever per-product Slack message about that launch is delivered first, and never re-created once set — a later delivery for the same launch SHALL reuse the existing reference rather than posting a second anchor message. Two per-product messages triggered for the same launch before either has observed a thread reference SHALL still result in exactly one anchor message and a single, shared thread reference for both.

**The anchor message SHALL be composed from the launch's product as the system resolves it at establishment time, read once for that purpose**, and SHALL NOT be composed from product facts supplied by whichever delivery path happens to be establishing the thread. What the anchor names is unchanged and is stated by `launch-entry`: the product, its SKU, its marketplace, and its launch date or the absence of one. This clause governs only where those values come from, and it exists because the anchor is permanent: a delivery path that could supply less than another would make the launch's header depend on which message arrived first, with no later message able to correct it.

**Where the launch's product cannot be resolved, the thread SHALL NOT be established** — no anchor is posted, no thread reference is persisted, and the delivery that attempted it fails and is reported, to be handled by the rule that already governs that delivery — retried where that rule retries, and reported to the submitter directly where `launch-entry` requires that instead. A product that is unreadable, absent, or whose reader is not configured are one case and SHALL be treated alike: the system cannot say what the product is. An anchor posted with missing facts would be permanent and unrepairable, while a thread not yet established costs one message for which its own capability already specifies a handling — so the incomplete anchor is the outcome to refuse, and the delay is the one to accept.

**The product SHALL NOT be read for the anchor's purpose where the thread reference is already set.** Establishment for a launch that already carries one reuses it without resolving the product, so a launch with a thread is unaffected by whether the product can be resolved. This governs only the anchor's own read: a message delivered into an existing thread still reads the product for whatever its own capability requires it to name.

#### Scenario: The submitter is recorded at launch start

- **WHEN** a launch is started
- **THEN** the launch record persists the Slack identity of whoever submitted it

#### Scenario: The thread reference starts absent

- **WHEN** a launch is started
- **THEN** its Slack thread reference is reported as absent

#### Scenario: The first per-product Slack message establishes the thread reference

- **WHEN** the first message about a launch that has no thread reference is delivered
- **THEN** an anchor message is posted and its identifying reference is persisted on the launch record

#### Scenario: The anchor names the product the system resolved, not what the caller held

- **WHEN** a delivery path that holds no product facts, or partial ones, establishes a launch's thread
- **THEN** the anchor names the product, SKU and marketplace as resolved from the launch's product at establishment time

#### Scenario: A product that cannot be read refuses establishment

- **WHEN** a per-product message would establish a launch's thread and the launch's product cannot be read
- **THEN** no anchor is posted, no thread reference is persisted, and the delivery fails and is reported

#### Scenario: A product that resolves to nothing refuses establishment

- **WHEN** a per-product message would establish a launch's thread and the launch's product resolves to nothing
- **THEN** no anchor is posted, no thread reference is persisted, and the delivery fails and is reported

#### Scenario: A refused establishment leaves the next delivery free to establish

- **WHEN** establishment was refused because the product could not be resolved, and a later message for the same launch is delivered while the product can be resolved
- **THEN** that message establishes the thread and posts a complete anchor

#### Scenario: A concurrent race to establish the thread produces exactly one anchor

- **WHEN** two per-product Slack messages are triggered for the same launch at the same time, and neither has yet observed a thread reference
- **THEN** exactly one anchor message is posted, and both messages are ultimately delivered against the same, single thread reference

#### Scenario: Establishing an already-set thread reference changes nothing

- **WHEN** a per-product Slack message is delivered for a launch that already has a thread reference
- **THEN** no new anchor message is posted, and the existing thread reference is reused

#### Scenario: A launch with a thread never reads its product

- **WHEN** a per-product Slack message is delivered for a launch that already has a thread reference and whose product cannot be read
- **THEN** the existing thread reference is reused, no product is resolved for the anchor, and the message is delivered
