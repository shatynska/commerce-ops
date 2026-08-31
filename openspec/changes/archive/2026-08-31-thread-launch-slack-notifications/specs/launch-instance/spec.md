## ADDED Requirements

### Requirement: A launch record establishes and persists its Slack thread once

The system SHALL persist, against a launch record, the Slack identity of whoever submitted it and an optional Slack thread reference. The submitter SHALL be recorded once, when the launch is started, and SHALL NOT change afterward. The thread reference SHALL be absent until first needed, established by whichever per-product Slack message about that launch is delivered first, and never re-created once set — a later delivery for the same launch SHALL reuse the existing reference rather than posting a second anchor message. Two per-product messages triggered for the same launch before either has observed a thread reference SHALL still result in exactly one anchor message and a single, shared thread reference for both.

#### Scenario: The submitter is recorded at launch start

- **WHEN** a launch is started
- **THEN** the launch record persists the Slack identity of whoever submitted it

#### Scenario: The thread reference starts absent

- **WHEN** a launch is started
- **THEN** its Slack thread reference is reported as absent

#### Scenario: The first per-product Slack message establishes the thread reference

- **WHEN** the first message about a launch that has no thread reference is delivered
- **THEN** an anchor message is posted and its identifying reference is persisted on the launch record

#### Scenario: A concurrent race to establish the thread produces exactly one anchor

- **WHEN** two per-product Slack messages are triggered for the same launch at the same time, and neither has yet observed a thread reference
- **THEN** exactly one anchor message is posted, and both messages are ultimately delivered against the same, single thread reference

#### Scenario: Establishing an already-set thread reference changes nothing

- **WHEN** a per-product Slack message is delivered for a launch that already has a thread reference
- **THEN** no new anchor message is posted, and the existing thread reference is reused
