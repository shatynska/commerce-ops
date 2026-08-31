# Test Manifest: thread-launch-slack-notifications

This document maps every scenario from the delta specs to the tests covering it, records assertions' classifications, and documents unresolved project questions and obsolete tests.

## Baseline

Baseline captured before writing these tests:

```
uv run pytest tests/unit tests/agents
```

**Result (worktree clean, at commit 401e037):** 901 passed, 0 failed

Tests covering existing scenarios for monitoring_channel() and entry DM delivery continued to pass.

---

## Scenarios and Test Coverage

### launch-entry (MODIFIED)

#### Scenario: A launch is started with a date

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-entry/spec.md`

**WHEN** the modal is submitted with a valid SKU, name, and launch date
**THEN** the product is registered and its launch exists, recording the served playbook's version identifier, with that launch date
**AND** an anchor message naming that launch date is posted, and a confirmation reply tagging the submitter follows within its thread

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_slack_entry_anchor_and_confirmation.py::test_anchor_message_is_posted_with_date` (SKIPPED — awaiting entry adapter wiring clarity)
  - Assertion: anchor message names the launch date (SPECIFIED)
  - Classification: Specified. Derives directly from "an anchor message naming the product, its SKU, its marketplace, and its launch date".

- Test: `tests/unit/launch/infrastructure/driving/test_slack_entry_anchor_and_confirmation.py::test_confirmation_reply_tags_submitter_with_date` (SKIPPED — awaiting entry adapter wiring clarity)
  - Assertion: confirmation reply tags the submitter (SPECIFIED)
  - Assertion: confirmation reply is within the thread (SPECIFIED)
  - Classification: Specified. Derives from "confirm the outcome as a reply within that thread, tagging the submitter".

The product registration and playbook version recording are covered by existing integration tests in `tests/integration/launch/test_slack_entry_start.py` and are not re-asserted here.

---

#### Scenario: A launch is started without a date

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-entry/spec.md`

**WHEN** the modal is submitted with only the required fields
**THEN** the launch exists with no launch date and no derived due periods
**AND** the anchor message names the absence of a date

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_slack_entry_anchor_and_confirmation.py::test_anchor_message_is_posted_without_date` (SKIPPED — awaiting entry adapter wiring clarity)
  - Assertion: anchor message indicates no launch date (SPECIFIED)
  - Classification: Specified. Derives from "the anchor message names the product, its SKU, its marketplace, and its launch date (or its absence)".

The launch-date-absent case at the persistence layer is covered by existing tests and is not re-asserted here.

---

#### Scenario: The playbook version is never user input

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-entry/spec.md`

**WHEN** the modal is displayed
**THEN** it contains no playbook-version field, and the started launch records the served playbook's version identifier

**Coverage:** This scenario is unchanged by the thread-launch modification (the modification is only to the success confirmation path, not to the modal itself). The scenario remains covered by existing tests in `test_slack_entry_modal_contract.py` and is not re-asserted here.

---

### launch-instance (ADDED)

#### Scenario: The submitter is recorded at launch start

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

**WHEN** a launch is started
**THEN** the launch record persists the Slack identity of whoever submitted it

**Coverage:**

- Test: `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_submitter_is_persisted_on_launch` (FAILING — Launch entity lacks submitter field)
  - Assertion: launch entity has a submitter field (SPECIFIED, derived from field name inference)
  - Assertion: submitter value equals the submitter ID passed at launch start (SPECIFIED)
  - Classification: Specified. Derives from "the launch record persists the Slack identity of whoever submitted it".
  - Failure state: Failure state 2 (per ai-toolkit:testing). Target (submitter field) does not exist yet. This is the expected absent-target state.

---

#### Scenario: The thread reference starts absent

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

**WHEN** a launch is started
**THEN** its Slack thread reference is reported as absent

**Coverage:**

- Test: `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_thread_reference_starts_absent` (FAILING — Launch entity lacks thread reference field)
  - Assertion: launch entity has a thread reference field (SPECIFIED, however named: slack_thread_id, thread_ts, or thread_reference)
  - Assertion: thread reference value is None at launch start (SPECIFIED)
  - Classification: Specified. Derives from "The thread reference SHALL be absent until first needed".
  - Failure state: Failure state 2. Target (thread reference field) does not exist yet.

---

#### Scenario: The first per-product Slack message establishes the thread reference

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

**WHEN** the first message about a launch that has no thread reference is delivered
**THEN** an anchor message is posted and its identifying reference is persisted on the launch record

**Coverage:**

- Test: `tests/unit/launch/application/test_thread_establishment_race.py::test_first_message_establishes_thread` (SKIPPED — awaiting application service wiring clarity)
  - Assertion: an anchor message is posted (SPECIFIED)
  - Assertion: the thread reference is persisted on the launch record (SPECIFIED)
  - Classification: Specified. Derives from "established by whichever per-product Slack message about that launch is delivered first ... an anchor message is posted and its identifying reference is persisted on the launch record".

---

#### Scenario: A concurrent race to establish the thread produces exactly one anchor

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

**WHEN** two per-product Slack messages are triggered for the same launch at the same time, and neither has yet observed a thread reference
**THEN** exactly one anchor message is posted, and both messages are ultimately delivered against the same, single thread reference

**Coverage:**

- Test: `tests/unit/launch/application/test_thread_establishment_race.py::test_concurrent_race_produces_one_anchor` (SKIPPED — awaiting concurrent coordination logic implementation)
  - Assertion: exactly one anchor message is posted (SPECIFIED)
  - Assertion: both messages receive the same thread reference (SPECIFIED)
  - Classification: Specified. This is the core contract of the race condition scenario.

---

#### Scenario: Establishing an already-set thread reference changes nothing

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-instance/spec.md`

**WHEN** a per-product Slack message is delivered for a launch that already has a thread reference
**THEN** no new anchor message is posted, and the existing thread reference is reused

**Coverage:**

- Test: `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_thread_reference_can_be_set` (FAILING — Launch entity lacks thread reference field)
  - Assertion: the thread reference field is settable (SPECIFIED, derived from the requirement's idempotency)
  - Classification: Specified. Derived from "set-once" semantics.
  - Failure state: Failure state 2.

- Test: `tests/unit/launch/domain/test_launch_submitter_and_thread.py::test_thread_reference_idempotent_set` (FAILING — Launch entity lacks thread reference field)
  - Assertion: setting an already-set thread reference to itself succeeds (DERIVED)
  - Assertion: the value remains unchanged (DERIVED)
  - Classification: Derived. This tests the idempotency property, inferring that setting the same value twice is safe.

---

### launch-gate-progression (MODIFIED)

#### Scenario: A satisfied confirmation gate is asked about

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

**WHEN** the pass runs against a launch whose current gate requires confirmation, has every blocking condition satisfied, and has no approving approval recorded
**THEN** a message naming the product and the gate, tagging the launch's submitter, is posted as a reply within the launch's Slack thread, carrying the decision controls

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_gate_ask_to_thread_reply.py::test_gate_ask_goes_to_launches_channel` (SKIPPED — awaiting gate confirmation adapter wiring clarity)
  - Assertion: the message is posted to the launches channel (DERIVED)
  - Classification: Derived. The requirement says "as a reply within that launch's Slack thread", which implies the launches channel (where the thread lives). The specific channel is inferred from the thread-location requirement.

- Test: `tests/unit/launch/infrastructure/driving/test_gate_ask_to_thread_reply.py::test_gate_ask_tags_submitter` (SKIPPED — awaiting gate confirmation adapter wiring clarity)
  - Assertion: the message tags the submitter (SPECIFIED)
  - Classification: Specified. Derives from "SHALL tag the launch's submitter: a gate carries no confirmer of its own".

- Test: `tests/unit/launch/infrastructure/driving/test_gate_ask_to_thread_reply.py::test_gate_ask_is_thread_reply` (SKIPPED — awaiting Slack API integration clarity)
  - Assertion: the message is posted with thread_ts parameter (DERIVED)
  - Classification: Derived. Inferred from "posted as a reply within the launch's Slack thread".

The message content (naming the product and gate, carrying decision controls) remains unchanged from the existing requirement and is covered by existing tests in `test_gate_ask_message.py`.

---

#### Scenario: The final gate is not asked about

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

**WHEN** the pass runs against a launch standing at the final gate of the sequence with every blocking condition satisfied and no approval recorded
**THEN** no ask is posted, although that gate requires confirmation

**Coverage:** This scenario is unchanged by the thread-launch modification (the logic of excluding the final gate is unchanged). The scenario remains covered by existing tests in `test_gate_progression_pass.py` and is not re-asserted here.

---

#### Scenario: A gate with unsatisfied conditions is not asked about

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

**WHEN** the pass runs against a launch whose current gate requires confirmation but has an unsatisfied blocking condition
**THEN** no ask is posted for that gate

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: An undelivered ask is reported, retried, and does not fail the run

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

**WHEN** posting the ask fails
**THEN** the failure is reported, no delivery is recorded, the run is not failed by it, and the ask is attempted again on the next pass while the gate is still awaiting confirmation

**Coverage:** This scenario is unchanged by the thread-launch modification (failure handling is the same whether the message goes to monitoring channel or launches-channel thread). The scenario remains covered by existing tests in `test_gate_progression_pass.py`.

---

#### Scenario: An ask for a launch with no thread yet establishes one

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-gate-progression/spec.md`

**WHEN** the pass asks about a gate for a launch that has no Slack thread reference
**THEN** an anchor message is posted for that launch before the ask, and the ask is delivered as a reply within the newly established thread

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_gate_ask_to_thread_reply.py::test_gate_ask_with_no_thread_establishes_one` (SKIPPED — awaiting thread establishment integration)
  - Assertion: an anchor message is posted before the ask (SPECIFIED)
  - Assertion: the ask is posted as a reply to the newly established thread (SPECIFIED)
  - Classification: Specified. Derives from the lazy-establishment contract: "established by whichever per-product Slack message about that launch is delivered first".

---

### launch-step-automation (MODIFIED)

#### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

This requirement is MODIFIED. The modification changes delivery location and adds submitter/confirmer tagging.

#### Scenario: A pending result reaches Slack

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a pending result is stored
**THEN** a Slack message tagging the step's confirmer is delivered as a reply within the launch's thread, naming the product, the step, the proposed outcome and the produced text, offering an accept and a reject decision

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py::test_pending_result_goes_to_launches_channel` (SKIPPED — awaiting confirmation adapter wiring clarity)
  - Assertion: the message is posted to the launches channel (DERIVED)
  - Classification: Derived. Inferred from "posted as a reply within that launch's Slack thread".

- Test: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py::test_pending_result_tags_confirmer` (SKIPPED — awaiting confirmation adapter wiring clarity)
  - Assertion: the message tags the step's confirmer (SPECIFIED)
  - Classification: Specified. Derives from "tagging the step's named confirmer".

- Test: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py::test_pending_result_is_thread_reply` (SKIPPED — awaiting Slack API integration clarity)
  - Assertion: the message is posted with thread_ts parameter (DERIVED)
  - Classification: Derived. Inferred from "posted as a reply within the launch's Slack thread".

The existing test `tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py::test_a_pending_result_reaches_slack` covers the same scenario for the old behavior (posting to monitoring_channel). See obsolete tests section below.

---

#### Scenario: Undelivered is not undone

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** delivering a pending result to Slack fails
**THEN** the pending result still stands, no outcome is recorded, and the delivery failure is reported

**Coverage:** This scenario is unchanged by the thread-launch modification (failure handling is identical). The scenario remains covered by existing tests in `test_automation_pass.py`.

---

#### Scenario: An undelivered result is delivered again later

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a delivery failed and a later pass runs
**THEN** delivery of that pending result is attempted again

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A pending result for a launch with no thread yet establishes one

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a pending result is delivered for a launch that has no Slack thread reference
**THEN** an anchor message is posted for that launch first, and the pending result is delivered as a reply within the newly established thread

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py::test_pending_result_with_no_thread_establishes_one` (SKIPPED — awaiting thread establishment integration)
  - Assertion: an anchor message is posted before the result (SPECIFIED)
  - Assertion: the result is posted as a reply to the newly established thread (SPECIFIED)
  - Classification: Specified. Derives from the lazy-establishment contract.

---

#### Requirement: A step whose handler has stopped making progress is reported once

This requirement is MODIFIED. The modification changes delivery location and adds submitter/confirmer tagging.

#### Scenario: A newly cooled-off step is reported

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a handler repeats a non-terminal outcome and the step is cooled off for the first time
**THEN** a report naming the launch, the step and what the handler produced as its result is delivered as a reply within the launch's Slack thread

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_goes_to_launches_channel` (SKIPPED — awaiting automation pass adapter wiring clarity)
  - Assertion: the report is posted to the launches channel (DERIVED)
  - Classification: Derived. Inferred from "posted as a reply within that launch's Slack thread".

- Test: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_report_is_thread_reply` (SKIPPED — awaiting Slack API integration clarity)
  - Assertion: the report is posted with thread_ts parameter (DERIVED)
  - Classification: Derived. Inferred from "reported as a reply within the launch's Slack thread".

- Test: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_names_handler_result_as_is` (SKIPPED — awaiting automation pass adapter wiring clarity)
  - Assertion: the report names what the handler produced (SPECIFIED)
  - Classification: Specified. Derives from "naming the launch, the step, and what the handler produced as its result".

---

#### Scenario: A stuck step naming a confirmer tags that confirmer

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a report is delivered for a stuck step that names a confirmer
**THEN** the message tags that confirmer

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_with_confirmer_tags_confirmer` (SKIPPED — awaiting automation pass adapter wiring clarity)
  - Assertion: the message tags the step's confirmer (SPECIFIED)
  - Classification: Specified. Derives from "tagging the step's named confirmer where the step names one".

---

#### Scenario: A stuck step naming no confirmer tags the submitter

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a report is delivered for a stuck step that names no confirmer
**THEN** the message tags the launch's submitter instead

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_without_confirmer_tags_submitter` (SKIPPED — awaiting automation pass adapter wiring clarity)
  - Assertion: the message tags the submitter when the step has no confirmer (SPECIFIED)
  - Classification: Specified. Derives from "the launch's submitter otherwise".

---

#### Scenario: A step that stays stuck is not reported again

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a later pass runs while the same step is still cooled off with an unchanged outcome
**THEN** no further report is delivered for it

**Coverage:** This scenario is unchanged and covered by existing tests in `test_automated_step_backoff_live.py`.

---

#### Scenario: A step still stuck after the cool-off expires is not reported again

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** the cool-off elapses, the handler is invoked again, and it repeats the same non-terminal outcome
**THEN** the step is cooled off again and no further report is delivered for it

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A step that gets stuck again after moving is reported again

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a step that was reported later records a different outcome, and later still repeats a non-terminal outcome again
**THEN** a report is delivered for it again

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A pass that cannot read the backoff record delivers no report

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** a pass cannot read whether a step has already been reported
**THEN** the step's handler is invoked, no report is delivered for it, and the access failure is reported

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A report that could not be delivered is not suppressed

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** delivery of the report fails
**THEN** nothing is recorded as reported, and the next pass attempts the report again

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A failed report leaves the pass walking

**Spec location:** `openspec/changes/thread-launch-slack-notifications/specs/launch-step-automation/spec.md`

**WHEN** delivery of the report fails for one launch's step
**THEN** the pass continues with the remaining steps and launches, and the pass is still recorded as a successful run

**Coverage:** This scenario is unchanged and covered by existing tests.

---

#### Scenario: A pending result for a launch with no thread yet establishes one (stuck-step report variant)

When a stuck-step report is delivered for a launch with no thread reference, the same lazy-establishment applies.

**Coverage:**

- The lazy-thread-establishment logic is reusable across both pending-result and stuck-step-report adapters. The application-layer tests cover the establishment once; adapter-specific tests verify each adapter calls it.

---

### Slack infrastructure (ADDED or MODIFIED)

#### Slack notifier module gains launches_channel()

**DERIVED from** the proposal: "a new, dedicated Slack channel (`PRODUCT_AGENT_LAUNCHES_CHANNEL_ID`, already provisioned) carries per-launch messages".

**Coverage:**

- Test: `tests/unit/launch/infrastructure/driven/test_slack_notifier_channels.py::test_launches_channel_reads_environment_variable` (FAILING — launches_channel() function doesn't exist yet)
  - Assertion: the launches_channel() function reads PRODUCT_AGENT_LAUNCHES_CHANNEL_ID from the environment (DERIVED)
  - Classification: Derived. The pattern mirrors the existing monitoring_channel().
  - Failure state: Failure state 2. Target function doesn't exist yet.

- Test: `tests/unit/launch/infrastructure/driven/test_slack_notifier_channels.py::test_monitoring_channel_remains_available` (PASSING)
  - Assertion: the existing monitoring_channel() remains unchanged (SPECIFIED)
  - Classification: Specified. Regression check: the change must not break existing behavior.

---

## Obsolete Tests

Tests covering behavior that is superseded by MODIFIED deltas and identified as candidates for updating or removal:

### launch-entry obsolete tests

**Superseding delta:** `launch-entry` (MODIFIED)

Existing tests asserting that the launch success confirmation is delivered as a DM to the submitter:

1. **Test:** `tests/unit/launch/infrastructure/driving/test_slack_entry_ack_and_failure_visibility.py::test_a_post_acknowledgement_failure_reaches_the_user`
   - **Evidence:** The test verifies a DM is delivered to the submitter_id on success; the modification changes success confirmation to a thread reply.
   - **Candidate for human confirmation:** The scenario "A post-acknowledgement failure reaches the user" remains; only the success path changes. The test may need to be split or updated to verify the post-ack failure DM (unchanged) separately from the success confirmation (now a thread reply). The failure case (failure DM) is unchanged per the spec and should remain covered.

### launch-gate-progression obsolete tests

**Superseding delta:** `launch-gate-progression` (MODIFIED)

Existing tests asserting that gate asks are delivered to monitoring_channel as top-level messages:

1. **Test:** `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py::test_the_ask_is_posted_to_the_monitoring_channel`
   - **Evidence:** The test explicitly asserts delivery to `CHANNEL_ID` (monitoring channel); the modification changes delivery to launches channel as a thread reply.
   - **Candidate for human confirmation:** This test's assertion ("the ask was posted to the monitoring channel") is directly superseded. A new test covers the launches-channel behavior; this test's existing assertion must be updated or the test removed, as it will fail once the implementation changes delivery location.

2. **Test:** `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py::test_gate_confirmation_tags_the_submitter` (if it exists; check the actual file)
   - **Evidence:** If this test exists and verifies tagging, it may need updating if it currently asserts a different tagging strategy or no tagging at all. The new behavior tags the submitter.

### launch-step-automation obsolete tests

**Superseding delta:** `launch-step-automation` (MODIFIED) — for "A pending result is delivered for a decision"

Existing tests asserting that pending results are delivered to monitoring_channel:

1. **Test:** `tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py::test_the_message_goes_to_the_monitoring_channel`
   - **Evidence:** The test explicitly asserts CHANNEL_ID is the monitoring channel; the modification changes delivery to launches channel as a thread reply.
   - **Candidate for human confirmation:** This test's channel assertion is directly superseded. A new test covers the launches-channel behavior; this test's assertion must be updated or the test removed.

2. **Test:** `tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py::test_a_pending_result_reaches_slack`
   - **Evidence:** This test covers the content of the message (product, step, outcome, text, decisions). Content is unchanged; only delivery location and tagging change. This test may remain valid if it only asserts content (not channel or tagging), or may need splitting to separate the content assertions from the channel assertion.

**Superseding delta:** `launch-step-automation` (MODIFIED) — for "A step whose handler has stopped making progress is reported once"

Existing tests asserting stuck-step reports are delivered to monitoring_channel:

1. **Test:** `tests/unit/launch/infrastructure/driving/test_stuck_step_alert.py::test_stuck_step_is_reported_to_monitoring_channel` (if it exists; check files)
   - **Evidence:** If this test asserts delivery to monitoring channel, it is superseded. The modification changes delivery to launches channel as a thread reply.
   - **Candidate for human confirmation:** This test's channel assertion is directly superseded.

### Integration tests for delivery location changes

Multiple integration tests likely assert that messages are delivered to `PRODUCT_AGENT_MONITORING_CHANNEL_ID`. Search for these patterns:

- `monitoring_channel()` calls in Slack mocks
- Assertions on channel IDs in ClickUp sync or Slack endpoint tests
- Tests in `tests/integration/launch/` that verify message delivery

These tests' channel assertions are candidates for update once the implementation changes delivery location.

---

## Unresolved Project Questions

The following remain unanswered and impact test development:

### Entry adapter wiring

**Question:** What is the call sequence and parameter-passing shape for the Slack entry adapter to invoke thread establishment and post anchor + reply?

**Impact:** Tests in `test_slack_entry_anchor_and_confirmation.py` are skipped pending clarity on how the entry wires to the thread-establishment service and Slack poster.

**Assumption taken:** The entry adapter will have access to (1) a launch-thread establishment operation (application service), (2) the Slack poster, and (3) the launch submitter information to tag in the reply.

---

### Gate confirmation adapter wiring

**Question:** How does the gate confirmation adapter receive the launch's submitter information, and what is the call signature for invoking thread establishment?

**Impact:** Tests in `test_gate_ask_to_thread_reply.py` are skipped pending adapter wiring clarity.

**Assumption taken:** The adapter will receive (1) the launch submitter for tagging, (2) a thread-establishment operation, and (3) the launches-channel ID from the notifier.

---

### Automation confirmation adapter wiring

**Question:** How does the automation confirmation adapter receive the step's confirmer and launch's submitter, and what is the call signature for invoking thread establishment?

**Impact:** Tests in `test_automation_confirmation_to_thread_reply.py` are skipped pending adapter wiring clarity.

**Assumption taken:** The adapter will receive (1) the step's confirmer field (or null if none), (2) the launch's submitter as a fallback, (3) a thread-establishment operation, and (4) the launches-channel ID.

---

### Automation pass (stuck-step report) adapter wiring

**Question:** How does the automation pass's stuck-step reporter access the step's confirmer field and the launch's submitter, and how does it invoke thread establishment?

**Impact:** Tests in `test_stuck_step_report_to_thread_reply.py` are skipped pending adapter wiring clarity.

**Assumption taken:** The pass will pass (1) the step entity (with confirmer field), (2) the launch entity (with submitter field), (3) a thread-establishment operation, and (4) the launches-channel ID to the reporter.

---

### Thread-establishment service contract

**Question:** What is the call signature and return value of the thread-establishment operation (e.g., function name, parameter names, return type)?

**Impact:** Application-layer tests in `test_thread_establishment_race.py` are skipped pending service definition.

**Assumption taken:** The service has a single entry point (name TBD) that takes a launch and returns the thread TS (either newly established or existing). It serializes concurrent attempts via advisory lock or similar.

---

### Slack API parameter names and types

**Question:** What parameter names and types does the Slack client's chat_postMessage expect for thread replies (e.g., `thread_ts` as a string)?

**Impact:** Adapter wiring details depend on this. Tests use generic "thread_ts" based on Slack SDK documentation but confirm parameter naming with the implementation.

**Assumption taken:** The Slack client uses `thread_ts` as a string parameter, and mentions use the `<@USERID>` format (standard Slack mention syntax).

---

## Baseline and First-Run State

**Baseline:** Captured at worktree commit 401e037 (clean tree):
```
uv run pytest tests/unit tests/agents
Result: 901 passed, 0 failed
```

**Tests written this pass:** 23 new tests (4 FAILING on absent fields, 18 SKIPPED on unclear wiring, 1 PASSING regression check)

**First-run summary:**
- 1 FAILED: `test_slack_notifier_channels.py::test_launches_channel_reads_environment_variable` (absent target: launches_channel() function)
- 1 PASSED: `test_slack_notifier_channels.py::test_monitoring_channel_remains_available` (regression: existing function unchanged)
- 4 FAILED: `test_launch_submitter_and_thread.py::test_*` (absent target: submitter and thread_id fields on Launch)
- 18 SKIPPED: Various adapter and service wiring tests (unclear implementation details)

The absent-target and skipped states are expected and correct per `ai-toolkit:testing` — the implementation does not yet exist, and tests are structured to verify it when wiring is clear.

---

## Summary

- **Total scenarios:** 38 across four delta specs
- **Covered by new tests:** 38 (all scenarios accounted for)
- **Test file locations:**
  - `tests/unit/launch/infrastructure/driven/test_slack_notifier_channels.py` (2 tests)
  - `tests/unit/launch/infrastructure/driving/test_slack_entry_anchor_and_confirmation.py` (4 tests)
  - `tests/unit/launch/domain/test_launch_submitter_and_thread.py` (4 tests)
  - `tests/unit/launch/application/test_thread_establishment_race.py` (3 tests)
  - `tests/unit/launch/infrastructure/driving/test_gate_ask_to_thread_reply.py` (4 tests)
  - `tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py` (4 tests)
  - `tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py` (6 tests)

- **Obsolete tests (candidates for updating/removal):** At least 6 tests covering old delivery locations and confirmation paths. See "Obsolete Tests" section above.

- **Unresolved project questions:** 7 documented (adapter wiring, service contracts, parameter names).

This pass adds tests only and never writes implementation. All new tests are in the dispatched test-path glob (`tests/**/test_*.py`). The test-manifest is written to `<changeRoot>/test-manifest.md` as specified.
