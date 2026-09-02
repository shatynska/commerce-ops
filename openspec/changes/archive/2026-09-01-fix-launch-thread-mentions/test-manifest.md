# Test Manifest: fix-launch-thread-mentions

Tests derived from this change's three delta specs, before any of its
implementation was written. Every `#### Scenario:` block in those specs is
accounted for below exactly once — covered by a named test, or recorded as
uncovered with its reason.

**This manifest is not an artifact the OpenSpec schema knows about.** It
will not appear among `openspec instructions apply`'s context files, and
must be read on purpose before implementing.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted or disabled, and no implementation was written. Tests that
this change's deltas supersede are listed under *Obsolete tests* as
candidates for human confirmation; correcting them is implementation work
that follows this pass.

---

## Baseline

Taken before any test was written, at the worktree root, clean tree, commit
`4512419`:

```
uv run pytest tests/unit tests/agents   →  1824 passed, 44 skipped, 0 failed
uv run pytest tests/integration         →     3 passed, 127 skipped, 0 failed
```

The integration tier's 127 skips are the tier's own gate: no database is
configured in this environment (`DATABASE_URL` unset, no `.env.test`, no
`.env`), and the tier skips with that reason. This is a **full** baseline
of the commit-time tiers and a **scoped-by-skip** baseline of the
integration tier.

### After this pass

```
uv run pytest tests/unit tests/agents   →  1845 passed, 51 failed, 44 skipped
uv run pytest tests/integration         →     3 passed, 132 skipped, 0 failed
```

72 tests were added (1896 − 1824 collected), 51 fail and 21 pass. **No
pre-existing test changed state**: the 1824 baseline passes are all still
passing, and every one of the 51 failures is in a file this pass created.

The 5 additional integration skips are this pass's two new integration
files. **Their assertions have never executed here**, so per
`ai-toolkit:testing` they establish nothing yet; they are written to run at
`pre-push` and in CI, where `COMMERCE_OPS_REQUIRE_DATABASE` makes an
unconfigured database a failure rather than a skip.

---

## Files written

| File | Tier | Tests | First run |
| --- | --- | --- | --- |
| `tests/unit/shared/domain/test_vocabulary_textual_form.py` | unit | 43 | 26 fail, 17 pass |
| `tests/unit/launch/application/test_mention_resolution_namespace.py` | unit | 11 | 11 fail |
| `tests/unit/launch/infrastructure/driving/test_pending_result_ask_untagged_policy.py` | unit | 9 | 9 fail |
| `tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py` | unit | 9 | 5 fail, 4 pass |
| `tests/integration/launch/test_pending_result_delivery_seam_live.py` | integration | 2 | skipped (no database here) |
| `tests/integration/launch/test_slack_entry_confirmation_last_resort.py` | integration | 3 | skipped (no database here) |

Every path is inside the dispatched test-path glob `tests/**/test_*.py`.
The only file written outside it is this manifest.

### Failure states of the first run

Per `ai-toolkit:testing`'s enumeration:

- **State 1 (the code ran and produced a wrong value)** — all 26 failures
  in `test_vocabulary_textual_form.py`, the 5 in
  `test_stuck_step_report_submitter_fallback.py`, and one in
  `test_mention_resolution_namespace.py`
  (`test_a_roster_argument_omitted_entirely_resolves_no_identity`, which
  reached its assertion and observed defect 1 directly: the resolver
  returned `'3f7c1a92-…'`, a roster identifier). These are the strongest
  state — the assertions executed and discriminated.
- **State 2 (the target does not exist yet)** — the other 10 failures in
  `test_mention_resolution_namespace.py` (no roster parameter on
  `resolve_mention_target`) and all 9 in
  `test_pending_result_ask_untagged_policy.py` (no `product_id` parameter
  on `deliver_pending_result`). These establish absence and nothing more;
  their assertions have not been exercised.
- **Passing on first run** — 21 tests, every one of them a deliberate
  regression guard on behaviour this change must *not* alter (the
  diagnostic `repr`, the composite values staying outside the textual-form
  rule, the submitter fallback for a step naming no confirmer). None is
  recorded as coverage of new behaviour, and none is the alarming
  fourth state: each is named in its own docstring as expected to pass and
  why.

Observed evidence of two of the four defects, from the first run:

```
the report rendered the identifier's object rather than its value:
  "… on ProductId(value='e0c364c5-50d3-4910-86ec-c2f4cda685df')."   ← defect 2

a confirmer resolved to '3f7c1a92-6b0e-4c7a-9d51-1e8a4b2c9f30' with no
roster reader supplied at all                                       ← defect 1
```

---

## Scenario accounting

**31 scenarios across the three delta specs. 31 accounted for below.**

### `launch-step-automation` (MODIFIED) — *A pending result is delivered for a decision, and delivery failure does not lose it* — 11 scenarios

#### 1. A pending result reaches Slack

**Covered by** — `test_pending_result_ask_untagged_policy.py::test_the_ask_mentions_the_slack_identity_and_never_the_roster_identifier` for the tagging clause this delta revises, together with the existing
`test_automation_confirmation_delivery.py::test_a_pending_result_reaches_slack` and
`test_automation_confirmation_to_thread_reply.py::test_pending_result_goes_to_launches_channel` / `::test_pending_result_is_thread_reply` for the clauses it does not.

- the message mentions the confirmer's Slack identity — **SPECIFIED**
- the roster's own identifier appears nowhere in the payload — **SPECIFIED** (the delta's "which satisfies no part of this requirement")
- the mention syntax is `<@…>` — **DERIVED**

#### 2. A stored pending result is delivered in the form it was stored

**Covered by** — `tests/integration/launch/test_pending_result_delivery_seam_live.py::test_a_stored_pending_result_is_delivered_in_the_form_it_was_stored`, and partly by `test_pending_result_ask_untagged_policy.py::test_delivery_is_not_refused_because_of_the_form_the_stored_row_carries`.

- the message is posted from a row read back through `undelivered()` — **SPECIFIED**
- no delivery is refused because of the identifier's stored form — **SPECIFIED**
- the row's identifier is not a `ProductId` (precondition) — **SPECIFIED**, from the requirement's own "while satisfying any test that supplies the form it wants"
- `undelivered()` is the query — **SPECIFIED** (`tasks.md` 5.4 names it)

The integration test is the one that establishes the scenario. The unit
test beside it asserts the same thing against a `uuid.UUID`-carrying row
rather than against the store, so a regression is visible at commit time
rather than only at push time; it is recorded as the weaker of the two and
does not stand in for it.

#### 3. A delivered result's controls resolve the result they were composed for

**Covered by** — `tests/integration/launch/test_pending_result_delivery_seam_live.py::test_a_delivered_results_controls_resolve_the_result_they_were_composed_for`, with the payload-shape half also at `test_pending_result_ask_untagged_policy.py::test_the_decision_controls_carry_the_identifier_the_result_was_stored_against`.

- each control names the stored product identifier and the stored step — **SPECIFIED**
- neither carries a rendering of the identifier's object — **SPECIFIED** (per `shared-vocabulary`)
- at least two controls (accept and reject) — **SPECIFIED**
- the pair reconstructed from the control resolves to the stored row — **SPECIFIED**, read **narrowly**: resolution is demonstrated through the store's own pending lookup rather than by driving `accept_automated_result` end to end. See *Deliberately untested* for why.

#### 4. A tagged confirmer is mentioned by their Slack identity

**Covered by** — `test_mention_resolution_namespace.py::test_a_resolvable_confirmer_resolves_to_their_slack_identity` and `::test_the_answer_is_never_a_roster_identifier` (resolution), and `test_pending_result_ask_untagged_policy.py::test_the_ask_mentions_the_slack_identity_and_never_the_roster_identifier` and `::test_the_ask_threads_the_step_through_to_mention_resolution` (the message).

- the mention is the person's `slack_identity` — **SPECIFIED**
- the roster identifier appears nowhere — **SPECIFIED**
- the roster was actually read on this branch — **SPECIFIED** (it is what makes the positive assertion mean something)
- the roster reader is matched on `list_people()` — **SPECIFIED** (`tasks.md` 3.1)
- the person double's field spellings — **DERIVED**, copied from `test_automated_decision_roster_shape.py`

#### 5. A confirmer the roster does not carry is not mentioned, and the gap is reported

**Covered by** — `test_mention_resolution_namespace.py::test_a_confirmer_the_roster_does_not_carry_resolves_to_nothing` and `test_pending_result_ask_untagged_policy.py::test_an_unresolvable_confirmer_leaves_the_ask_carrying_no_mention_at_all[unknown-confirmer]` and `::test_an_untagged_ask_still_names_the_product_the_step_and_the_produced_text`.

- no identity resolves — **SPECIFIED**
- the submitter is not substituted — **SPECIFIED**
- the ask carries no mention token at all — **SPECIFIED**
- the ask still names the product, the step and the produced text — **SPECIFIED**
- the report names the step, the launch and the unresolvable confirmer — **SPECIFIED**
- "reported" means a log record at `WARNING` or above — **DERIVED** (see *Unresolved project questions*)

#### 6. A deactivated confirmer is not mentioned, and the gap is reported

**Covered by** — `test_mention_resolution_namespace.py::test_a_deactivated_confirmer_resolves_to_nothing` and `test_pending_result_ask_untagged_policy.py::test_an_unresolvable_confirmer_leaves_the_ask_carrying_no_mention_at_all[deactivated-confirmer]`.

- a deactivated person's surviving Slack identity is not used — **SPECIFIED**, and the roster double deliberately carries it, since an implementation checking only "carried, with a Slack identity" would pass every other test in the file
- the gap is reported — **SPECIFIED**

#### 7. A pending result is delivered untagged when the roster cannot be read

**Covered by** — `test_mention_resolution_namespace.py::test_a_roster_that_cannot_be_read_resolves_no_identity_and_is_reported[absent-reader|store-shaped-reader|failing-reader]`, `::test_a_roster_argument_omitted_entirely_resolves_no_identity`, and `test_pending_result_ask_untagged_policy.py::test_an_unresolvable_confirmer_leaves_the_ask_carrying_no_mention_at_all[unreadable-roster]`.

- all three failure modes resolve no identity — **SPECIFIED**
- **nothing is raised** — **SPECIFIED** (`design.md`: the opposite disposition from `_roster_or_fail`)
- the failure is reported — **SPECIFIED**
- "absent" and "explicitly `None`" are distinct cases — **DERIVED** from `tasks.md` 3.6's "absent (never injected)"

#### 8. An identifier in the message or its controls appears as its value

**Covered by** — `test_pending_result_ask_untagged_policy.py::test_the_product_identifier_fallback_appears_as_its_own_value` and `::test_the_decision_controls_carry_the_identifier_the_result_was_stored_against`.

- the identifier appears as `.value` — **SPECIFIED**
- no `ProductId`/`value=` rendering appears anywhere in the payload — **SPECIFIED**
- `product=None` is what reaches the fallback — **DERIVED**

#### 9. Undelivered is not undone — **UNCOVERED by new tests**

**Reason:** unchanged in substance by this delta, which revises who is
tagged, in what form identifiers are named, and what the delivery is handed
— not what happens when delivery fails. Remains covered by
`test_automation_pass.py::test_undelivered_is_not_undone`.

#### 10. An undelivered result is delivered again later — **UNCOVERED by new tests**

**Reason:** unchanged in substance, as above. Remains covered by
`test_automation_pass.py`. Note this scenario acquires new *significance*
from the change — `design.md` rests the backlog-release decision on it —
but its stated behaviour is untouched.

#### 11. A pending result for a launch with no thread yet establishes one — **UNCOVERED by new tests**

**Reason:** unchanged in substance. Remains covered by
`test_automation_confirmation_to_thread_reply.py::test_pending_result_with_no_thread_establishes_one` and
`test_thread_establishment_race.py`.

---

### `launch-step-automation` (MODIFIED) — *A step whose handler has stopped making progress is reported once* — 12 scenarios

#### 1. A newly cooled-off step is reported — **UNCOVERED by new tests**

**Reason:** unchanged in substance. Remains covered by
`test_stuck_step_report_to_thread_reply.py::test_stuck_step_names_handler_result_as_is`
and `test_automation_pass_repeat_backoff.py`. The message's continued
substance under this change's new fallback path *is* asserted, at
`test_stuck_step_report_submitter_fallback.py::test_the_report_still_names_the_step_and_what_the_handler_produced`.

#### 2. A stuck step naming a confirmer tags that confirmer

**Covered by** — `test_stuck_step_report_submitter_fallback.py::test_a_stuck_step_tags_the_confirmers_slack_identity_not_the_roster_identifier` and `::test_the_report_threads_the_step_through_to_mention_resolution`, with the resolution half at `test_mention_resolution_namespace.py::test_a_resolvable_confirmer_resolves_to_their_slack_identity`.

- the mention is the person's Slack identity — **SPECIFIED**
- the roster identifier appears nowhere — **SPECIFIED**
- the submitter is not tagged alongside — **SPECIFIED**
- no gap is named when the confirmer resolved — **SPECIFIED** (the delta's distinguishability requirement, read in the negative)

#### 3. A stuck step naming no confirmer tags the submitter

**Covered by** — `test_stuck_step_report_submitter_fallback.py::test_a_stuck_step_naming_no_confirmer_tags_the_submitter_and_names_no_gap` and `test_mention_resolution_namespace.py::test_a_step_naming_no_confirmer_yields_the_submitter_without_reading_the_roster`.

- the submitter is tagged — **SPECIFIED**, unchanged by this delta
- **no gap is named** — **SPECIFIED** by this delta ("a reader can still tell a step that names no confirmer from one whose confirmer cannot be reached"). This is the negative half without which scenario 4's positive assertion could be satisfied by a line printed on every report.
- the roster is **not read** on this branch — **SPECIFIED** (`tasks.md` 3.4; the delta's "unaffected by whether the roster can be read")

#### 4. A stuck step whose confirmer cannot be resolved tags the submitter and names the gap

**Covered by** — `test_stuck_step_report_submitter_fallback.py::test_an_unresolvable_confirmer_tags_the_submitter_and_names_the_gap[unknown-confirmer|deactivated-confirmer|no-slack-identity]`.

- the report is still delivered — **SPECIFIED**
- it tags the launch's submitter — **SPECIFIED**, and deliberately the *opposite* postcondition to the ask's on the same input
- its text names that the confirmer could not be resolved — **SPECIFIED**
- the wording by which it does — **DERIVED**, `_NAMES_AN_UNRESOLVED_CONFIRMER` (see *Unresolved project questions*)
- the gap is reported — **SPECIFIED**, asserted at the resolver

#### 5. A stuck step is reported to the submitter when the roster cannot be read

**Covered by** — `test_stuck_step_report_submitter_fallback.py::test_an_unresolvable_confirmer_tags_the_submitter_and_names_the_gap[unreadable-roster]`, with the resolution half at `test_mention_resolution_namespace.py::test_a_roster_that_cannot_be_read_resolves_no_identity_and_is_reported`.

Same assertions and classifications as scenario 4.

#### 6. A report naming a product by identifier names it by value

**Covered by** — `test_stuck_step_report_submitter_fallback.py::test_a_stuck_step_report_names_the_product_identifier_by_value`.

- the identifier appears as `.value` — **SPECIFIED**
- no object rendering appears — **SPECIFIED**
- `product=None` is what "cannot be named any other way" means — **DERIVED**

#### 7–12. A step that stays stuck is not reported again / A step still stuck after the cool-off expires is not reported again / A step that gets stuck again after moving is reported again / A pass that cannot read the backoff record delivers no report / A report that could not be delivered is not suppressed / A failed report leaves the pass walking — **UNCOVERED by new tests (6 scenarios)**

**Reason:** all six are unchanged in substance by this delta, which revises
who a report tags and in what form it names identifiers, and touches
neither the report-once record, the backoff read, nor the pass's failure
containment. They remain covered by `test_automation_pass.py`,
`test_automation_pass_repeat_backoff.py` and
`tests/integration/launch/test_automated_step_backoff_live.py`.

---

### `launch-entry` (MODIFIED) — *A launch is started from Slack in one interaction* — 4 scenarios

#### 1. A launch is started with a date — **UNCOVERED by new tests**

**Reason:** unchanged by this delta, which adds a paragraph about what
happens when the threaded confirmation *fails*. Remains covered by
`tests/integration/launch/test_slack_entry_start.py::test_a_launch_is_started_with_a_date`.

#### 2. A launch is started without a date — **UNCOVERED by new tests**

**Reason:** as above. Remains covered by
`tests/integration/launch/test_slack_entry_start.py::test_a_launch_is_started_without_a_date`.

#### 3. A confirmation that cannot reach the thread reaches the submitter

**Covered by** — `tests/integration/launch/test_slack_entry_confirmation_last_resort.py::test_a_confirmation_that_cannot_reach_the_thread_reaches_the_submitter[anchor-fails|reply-fails]` and `::test_the_fallback_confirmation_is_not_rewritten_to_mention_the_thread`.

- the product and its launch are persisted (precondition, from the WHEN) — **SPECIFIED**
- the threaded delivery really was attempted and failed (precondition) — **SPECIFIED**
- the submitter is told directly — **SPECIFIED**
- what they are told is the launch-started confirmation — **SPECIFIED**, recognised by its ClickUp-cadence wording, which `launch-entry`'s own requirement fixes
- the failure is reported — **SPECIFIED**
- both failure points (anchor, reply) — **SPECIFIED** ("the thread cannot be established, or the reply cannot be posted")
- the fallback text is **not** rewritten to mention the missing thread — **DERIVED** from "by the same direct message a failed start already uses" plus `tasks.md` 4.3; the requirement does not state it outright. If the project decides a line about the thread is wanted, this test is what to revisit, not the requirement.
- a direct message is a `chat.postMessage` whose `channel` is the submitter's identity — **DERIVED**

#### 4. The playbook version is never user input — **UNCOVERED by new tests**

**Reason:** unchanged by this delta; it concerns the modal, which this
change does not touch. Remains covered by
`test_slack_entry_modal_contract.py` and
`tests/integration/launch/test_slack_entry_start.py`.

---

### `shared-vocabulary` (ADDED) — *A value object's textual form is its value* — 4 scenarios

#### 1. Rendering a single-valued vocabulary object yields its value

**Covered by** — `test_vocabulary_textual_form.py::test_rendering_a_single_valued_object_yields_exactly_its_value[product-id|sku|asin|marketplace-id|metric-id|discipline|severity]` and `::test_a_rendering_carries_no_type_name_field_name_or_punctuation[…same seven…]`.

- `str()`, f-string and `%s` all yield exactly the value — **SPECIFIED**; asserting only `str()` would leave the other two free to disagree, which is the split this change exists to close
- no type name, field name, or surrounding punctuation — **SPECIFIED**
- the fixture values contain none of those markers, so a match can only come from the rendering — **DERIVED** (a test-design choice, recorded because it is what makes the negative assertions non-vacuous)

#### 2. A rendered value object round-trips

**Covered by** — `test_vocabulary_textual_form.py::test_a_rendered_value_object_round_trips[product-id|sku|asin|marketplace-id|metric-id|discipline]` and `::test_a_rendered_severity_round_trips`.

- constructing the same kind from the rendering yields an equal value — **SPECIFIED**. This is what makes the first scenario checkable rather than merely stated: a rendering that dropped or reformatted the value would satisfy "no type name" and fail here.

#### 3. A value with no single value is not rendered as an object

**Covered by** — `test_vocabulary_textual_form.py::test_a_value_with_no_single_value_keeps_naming_its_type[launching|steady-state|development|retired|unrestricted-scope|set-scope]` and `::test_a_composite_stage_can_be_named_by_its_parts[launching|steady-state]`.

- a lifecycle stage and an access scope do **not** acquire a single-value textual form — **SPECIFIED**, from the requirement's last paragraph and `tasks.md` 1.3
- the mechanism asserted (the rendering still names the type) — **DERIVED**; it is the consequence of leaving these objects alone, not a format the requirement chooses
- the parts are reachable as named attributes — **DERIVED**; without it the test above would forbid one spelling while establishing nothing about whether a correct spelling exists

The requirement's **prohibition half** stated over every call site in
`src/` is recorded under *Deliberately untested*; the four sites
`design.md`'s audit found are covered as behaviour where they live.

#### 4. A debugging representation is still available

**Covered by** — `test_vocabulary_textual_form.py::test_a_debugging_representation_names_the_type_and_the_value[…seven…]` and `::test_the_debugging_representation_is_distinct_from_the_textual_form[…seven…]`.

- `repr` names the type and the value — **SPECIFIED**
- `repr` and `str` are distinct strings — **SPECIFIED**. This is the assertion that fails in both directions of the mistake: `repr` collapsed onto the value (the diagnostic lost, and `use_cases.py:342` with it) and `str` left as `repr` (the change not made).

---

## Obsolete tests

Every entry below is a **candidate for human confirmation**, not a
conclusion. Each names the test by a runner-selectable identifier, the
delta that supersedes it, and the evidence the two were matched on.

**Search bound.** The search covered the dispatched test-path glob
`tests/**/test_*.py` and nowhere else, using: the archived
`test-manifest.md` for `thread-launch-slack-notifications` as a
scenario-to-test map; a grep for `CONFIRMER_ID`,
`resolve_mention_target`, `establish_thread_and_resolve_mention`,
`product_id: ProductId` and `ProductId(value=` across that glob; and a
read of every file those turned up. No implementation source was read.

### Superseded by `launch-step-automation` — *A pending result is delivered for a decision* (MODIFIED)

1. **`tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py::test_pending_result_tags_confirmer`**
   *Evidence:* asserts `f"<@{CONFIRMER_ID}>" in poster.rendered` where
   `CONFIRMER_ID = "U0CONFIRMER"` is the value the test itself sets as
   `step.confirmer` (lines 77, 123, 258). The delta now says a step's
   confirmer "is stored as the roster's own identifier […] which Slack
   cannot resolve" and that a message carrying it "satisfies no part of
   this requirement" — so this assertion is satisfied by exactly the
   defect. Superseded by scenario *A tagged confirmer is mentioned by
   their Slack identity*.

2. **`tests/unit/launch/infrastructure/driving/test_automation_confirmation_to_thread_reply.py`** — the whole file's `_PendingRow` fixture (line 128, `product_id: ProductId = PRODUCT_ID`), and therefore all four of its tests.
   *Evidence:* the delta adds "Delivery SHALL work from a pending result in
   the form the store hands it back", and `proposal.md` names this exact
   line as the stub that "supplies the form that satisfies the check and
   quietly corrupts the button". All four tests also call
   `deliver_pending_result` without the `product_id` argument `tasks.md`
   2.1 adds.

3. **`tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py`** — its `_PendingRow` fixture (line 129, `product_id: ProductId = PRODUCT_ID`) and its three `deliver_pending_result` call sites.
   *Evidence:* the same fixture defect as entry 2, in a file the dispatch
   did not name. Same superseding clause. Its
   `::test_a_pending_result_reaches_slack` and
   `::test_the_message_goes_to_the_launches_channel_as_a_thread_reply`
   assert content and channel that this delta leaves unchanged, so the
   correction here is the fixture and the call, not the postconditions.

4. **`tests/unit/launch/infrastructure/driving/test_automation_pass.py`** — its `_PendingRow` dataclass (line 425–426, `product_id: ProductId`).
   *Evidence:* `_deliver_waiting` builds `ProductId(str(row.product_id))`
   from whatever this fake's `undelivered()` returns; with a `ProductId`
   there, that expression produces `ProductId("ProductId(value='…')")`
   today and would keep silently mis-round-tripping after the change. The
   real store returns `uuid.UUID`. Superseded by the same "in the form the
   store hands it back" clause. Its `_FakeDelivery` accepts `**kwargs`, so
   the new `product_id` argument does **not** obsolete the call sites — only
   the row's declared type.

### Superseded by `launch-step-automation` — *A step whose handler has stopped making progress is reported once* (MODIFIED)

5. **`tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_with_confirmer_tags_confirmer`**
   *Evidence:* asserts `f"<@{CONFIRMER_ID}>" in notifier.rendered` (line
   279) where `CONFIRMER_ID = "U0CONFIRMER"` is set as `step.confirmer`
   (lines 96, 130), and its `_fake_establish_thread` derives the mention
   as `getattr(step, "confirmer", None) or SUBMITTER_ID` (line 193) — i.e.
   the fake implements the defect and the assertion confirms it.
   Superseded by scenario *A stuck step naming a confirmer tags that
   confirmer* as revised.

6. **`tests/unit/launch/infrastructure/driving/test_stuck_step_report_to_thread_reply.py::test_stuck_step_without_confirmer_tags_submitter`**
   *Evidence:* same `_fake_establish_thread` (line 193). The
   postcondition — the submitter is tagged — survives this change
   unchanged; what is superseded is the fake's rule, which now stands in
   for a resolution that reads the roster. A lighter correction than entry
   5, and listed separately for that reason.

### Superseded by both requirements' shared tagging clause

7. **`tests/unit/launch/application/test_thread_establishment_race.py::test_a_step_naming_a_confirmer_resolves_to_that_confirmer`**
   *Evidence:* `_StepWithConfirmer(confirmer="U0CONFIRMER")` then
   `assert mention == "U0CONFIRMER"` (lines 296–302) — the assertion is
   literally that the resolver returns `step.confirmer` unchanged, which
   the delta now forbids ("The system SHALL resolve the step's confirmer
   through the roster to that person's Slack identity"). Its two siblings
   in that file (`::test_a_step_naming_no_confirmer_falls_back_to_the_submitter`
   and `::test_no_step_at_all_falls_back_to_the_submitter`) are **not**
   superseded — `proposal.md` puts that rule explicitly out of scope — and
   are re-covered, with the added "without reading the roster" clause, in
   `test_mention_resolution_namespace.py`.

### Not superseded, checked and recorded

- **`tests/unit/launch/infrastructure/driving/test_gate_ask_message.py`** — reads
  `establish_thread_and_resolve_mention` with `mention=SUBMITTER_ID` and
  asserts `post_gate_ask` passes **no** step
  (`::test_the_ask_calls_the_mention_resolver_with_no_step`). Both remain
  correct; `tasks.md` 5.1 and 3.3 exist to keep them so. Listed here so a
  reviewer can see it was checked rather than missed.

### A test asserting the old rendering

**No such test was found by this search**, and the distinction matters
here: `design.md` anticipates that "a test asserting the old rendering may
be asserting the defect", and this search — a grep for `ProductId(value=`
and for `repr(`-based assertions across the whole test glob — turned up
only three `repr` assertions
(`test_playbook_admin_anchor_inputs.py:1075`,
`test_step_confirmer_preconditions.py:521`,
`test_step_assignee_preconditions.py:576`), none of which asserts a
vocabulary object's rendering and all of which are about a *diagnostic*
representation that this change deliberately preserves. That is "no such
test exists" for the message case, and "none was found by this search" for
anything a grep on those two spellings would miss.

---

## Unresolved project questions

Each records the assumption taken and the tests that depend on it. None was
resolved silently; this pass is a dispatched subagent with no channel to
ask on, so they are surfaced here and in the report instead.

### 1. The name of `resolve_mention_target`'s roster parameter

**Question:** `tasks.md` 3.1 says "keyword-only `roster: RosterReader |
None`", but every other roster consumer in `launch` spells its injected
reader `read_people`. Nothing decides between them.

**Assumption:** the parameter is one of `roster`, `read_people`,
`roster_reader`, `people`, `reader`. `_resolve` reflects over the real
signature and fails by name if it is none of these, rather than passing an
argument the function silently ignores — which would let every test in the
file pass by accident on the submitter fallback.

**Depends on it:** all 11 tests in
`tests/unit/launch/application/test_mention_resolution_namespace.py`.
Correction point: `_ROSTER_PARAMETER_NAMES`.

### 2. How a gap is "reported"

**Question:** both requirements say a gap "SHALL be reported", and
`design.md` points at `_clickup_users`'s "two warnings" as the model.
Nothing fixes the mechanism.

**Assumption:** the standard library's logging, at `WARNING` or above.

**Depends on it:** `test_mention_resolution_namespace.py`'s reporting
assertions (4 tests) and
`test_slack_entry_confirmation_last_resort.py`'s. Correction points:
`_reports` in each file.

### 3. The wording naming an unresolved confirmer in the stuck-step report

**Question:** the delta requires the report's text to "name that the step's
confirmer could not be resolved". No artifact fixes the phrasing.

**Assumption:** one of `_NAMES_AN_UNRESOLVED_CONFIRMER`'s ten markers,
chosen to exclude any word a routine report already carries. It is not
asserted blind: the neighbouring no-confirmer test establishes that a
report with no gap to name matches none of them, so a marker matching
every report would fail there.

**Depends on it:**
`test_stuck_step_report_submitter_fallback.py::test_an_unresolvable_confirmer_tags_the_submitter_and_names_the_gap`
(4 params) and, in the negative,
`::test_a_stuck_step_naming_no_confirmer_tags_the_submitter_and_names_no_gap`
and `::test_a_stuck_step_tags_the_confirmers_slack_identity_not_the_roster_identifier`.

### 4. The decision control payload's internal format

**Question:** how a product identifier and a step identifier are joined
into one action `value`. `design.md` fixes that it carries
`product_id.value`, not the separator or the order.

**Assumption:** containment of each part is asserted rather than a parse,
and the resolution half is done through the store's own pending lookup
rather than by splitting the payload on a guessed separator.

**Depends on it:**
`tests/integration/launch/test_pending_result_delivery_seam_live.py::test_a_delivered_results_controls_resolve_the_result_they_were_composed_for`
and
`test_pending_result_ask_untagged_policy.py::test_the_decision_controls_carry_the_identifier_the_result_was_stored_against`.

### 5. That a direct message is a `chat.postMessage` to the submitter's own identity

**Question:** `tasks.md` 4.1 names `_post(client, submitter, …)`; nothing
fixes what that produces at the Slack API boundary.

**Assumption:** a `chat.postMessage` whose `channel` is `SUBMITTER_ID`.

**Depends on it:** all 3 tests in
`tests/integration/launch/test_slack_entry_confirmation_last_resort.py`.
Correction point: `_direct_messages`.

### 6. The mention syntax

**Assumption:** `<@USERID>`, and "carrying no mention" means the payload
contains no `<@` token at all — a stronger reading than "not the
submitter's", chosen because the requirement's wording is "carrying no
mention".

**Depends on it:** the tagging and untagged assertions in both driving
test files.

### 7. No stack skill exists for this project's test runner beyond `python`

`ai-toolkit` carries `testing` and `python`; both were loaded. No skill in
the library covers `pytest`-with-`anyio` or SQLAlchemy integration
specifics beyond `python`'s `references/testing.md`. Recorded per the
floor's obligation rather than resolved by loading a near-miss skill; the
project's own conventions in `AGENTS.md` (three tiers, `uv run pytest`,
the integration tier's own database resolution) governed every placement
decision instead.

---

## Deliberately untested, recorded rather than omitted

- **The `shared-vocabulary` prohibition half stated over every call site in
  `src/`.** A test cannot read a diff, and a source sweep asserting the
  absence of a spelling would pass for any expression whose variable is
  named otherwise. `design.md`'s audit and `tasks.md` 1.5's re-run carry it.
  The four sites that audit found are each covered as behaviour where they
  live: the two `str(product_id)` message sites in the two driving test
  files, the control payload in both of those and in the integration seam
  test, and `use_cases.py:342` by the `repr`/`str` distinctness test.
- **Driving `accept_automated_result` end to end from a delivered control
  payload.** It needs a roster collaborator and a served playbook, whose
  absence would fail the integration file for reasons unrelated to the seam
  under test; the decision rules themselves are covered in
  `tests/unit/launch/application/test_automated_result_decisions.py`. What
  the integration test establishes instead is the half those tests assume:
  the pair reaching them is the pair the result was stored against.
- **`tasks.md` 4.4's guard on the fallback itself** (where the direct
  message also fails, log and continue). Engineering it needs every
  `chat.postMessage` to fail, which makes "the submitter was told" and
  "the launch stands" indistinguishable from a run that never got that far.
  The surrounding behaviour — a delivery failure never unwinds a commit —
  is covered by
  `test_slack_entry_start.py::test_a_post_commit_delivery_failure_leaves_the_commit_standing`.
- **The one-time backlog release** (`design.md`; `tasks.md` 5.4). A
  deployment observation about rows that already exist in production, not a
  property of the code; no test over a fresh test database can observe it.
- **Static guarantees.** That `resolve_mention_target`'s return type stays
  `str | None` (`tasks.md` 3.3) and that a store-shaped injection is a
  `mypy` error at the assigning line. Both are verified by `uv run mypy`
  (`tasks.md` 7.2); a runtime assertion would have to pin an annotation's
  spelling and would fail for the wrong reason.
- **That the identifier match uses `person_identifier(person)` specifically**
  rather than reading `.id` directly (`tasks.md` 3.1). The roster double
  spells the field `id`, which both readings satisfy; distinguishing them
  would assert on the implementation's choice of helper rather than on
  behaviour. What the requirement binds — that the mention and the decision
  check never disagree about who the confirmer is — is kept observable by
  the double sharing its field spellings with
  `test_automated_decision_roster_shape.py`'s `_Person`.

---

## What the implementation step must make pass

Run these after each section of `tasks.md`:

```
# section 1 — the vocabulary's textual form
uv run pytest tests/unit/shared/domain/test_vocabulary_textual_form.py

# section 2 — the pending-result delivery seam
uv run pytest tests/unit/launch/infrastructure/driving/test_pending_result_ask_untagged_policy.py
uv run pytest tests/integration/launch/test_pending_result_delivery_seam_live.py

# section 3 — roster-backed mention resolution
uv run pytest tests/unit/launch/application/test_mention_resolution_namespace.py
uv run pytest tests/unit/launch/infrastructure/driving/test_pending_result_ask_untagged_policy.py
uv run pytest tests/unit/launch/infrastructure/driving/test_stuck_step_report_submitter_fallback.py

# section 4 — the launch confirmation's last resort
uv run pytest tests/integration/launch/test_slack_entry_confirmation_last_resort.py

# and the whole tier, against the 1824-pass baseline above
uv run pytest tests/unit tests/agents
uv run pytest tests/integration      # needs a database; see AGENTS.md
```

Two of these files must **not** all go green by the same edit, and that is
the point: `test_pending_result_ask_untagged_policy.py` requires an
untagged ask with no submitter substitution, and
`test_stuck_step_report_submitter_fallback.py` requires a submitter tag
plus a named gap — on the same input. An implementation that applies one
policy to both callers will fail one of these files whichever policy it
picks.
