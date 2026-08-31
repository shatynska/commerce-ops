# Test manifest — `write-the-advisors-finding-to-the-product`

Not an OpenSpec artifact: this file is not part of the OpenSpec schema and
will **not** appear among `openspec instructions apply`'s context files. It
must be read on purpose — by whoever implements this change next, and by
anyone re-running this test-writing pass — before implementation begins.
Also pointed to by `ai-toolkit`'s implementation-time rules fragment; this
file is the second, redundant pointer that fragment's own note says to
expect.

Written by an `openspec-test-writer` pass. No implementation code was
written. No existing test was edited, deleted, or weakened. Every test
below is new.

## Baseline

Scoped baseline taken before any test in this pass was written:

    uv run pytest tests/unit tests/agents
    1689 passed in 45.52s

Scope: `tests/unit` + `tests/agents`, per `AGENTS.md`'s stated tiers and
because every artifact this change touches lives in those two tiers
(`tests/integration` is untouched by this pass — see *Unresolved project
questions* below).

Confirmation run after writing every test in this pass (diagnostic only,
run with `--continue-on-collection-errors` since pytest otherwise aborts
the whole session on the first expected `ImportError`):

    uv run pytest tests/unit tests/agents -q --continue-on-collection-errors
    1689 passed, 4 failed, 7 errors in 44.53s

- **1689 passed** — unchanged from the baseline: nothing pre-existing was
  broken by this pass.
- **7 errors** — `ImportError`/`ModuleNotFoundError` at collection, one per
  new file importing something that does not exist yet
  (`commerce_ops.shared.domain.result`, or
  `commerce_ops.catalog.application.record_sub_category`). Expected: the
  absent-target state, per `ai-toolkit:testing`.
- **4 failed** — `tests/unit/catalog/domain/test_product_sub_category.py`,
  all `AttributeError` (`Product` has no `record_sub_category` method or
  `sub_category` attribute yet). Also the expected absent-target state —
  `Product` itself already exists, so this file fails past collection,
  on the missing method/field specifically.

No test in this pass passed on its first run. Nothing here is coverage
yet; every test establishes only that its target is absent, per
`ai-toolkit:testing`'s four failure states.

## Skills loaded

`ai-toolkit:testing` (the floor) and `python` (pytest/CPython specifics;
loaded after the bulk of this pass was already written — see *Unresolved
project questions*). No project-specific skill exists for LangGraph agent
testing beyond `langgraph` itself, which the existing `tests/agents/`
files already establish idiom for; this pass followed that established
idiom rather than reloading the skill, since every new file mirrors an
existing file's structure closely.

## Scenario accounting

38 scenarios total across the three delta specs. All 38 are accounted for
below — covered by a named test, or recorded uncovered with a reason.
None are uncovered.

### `subcategory-advisor` (23 scenarios)

New file:
`tests/agents/step_handlers/listing/test_subcategory_advisor_structured_recommendation.py`
— MODIFIED requirement *A recommendation is produced from the product's
name and marketplace* (6 scenarios):

| # | Scenario | Test |
|---|---|---|
| 1 | A recommendation names node, demands and alternative | `test_a_recommendation_names_node_demands_and_alternative` |
| 2 | A recommendation is readable as it stands | `test_a_recommendation_is_readable_as_it_stands` |
| 3 | A supported comment cannot be empty | `test_a_supported_comment_cannot_be_empty[empty-string]` / `[none]` |
| 4 | A comment's content is never checked by code | `test_a_comments_content_is_never_checked_by_code` |
| 5 | The marketplace reaching the model is the identifier | `test_the_marketplace_reaching_the_model_is_the_identifier` |
| 6 | A refusal names the marketplace as a reader would recognise it | `test_a_refusal_names_the_marketplace_as_a_reader_would_recognise_it` |

New file:
`tests/agents/step_handlers/listing/test_subcategory_advisor_structured_verdict.py`
— MODIFIED requirement *The advisor proposes satisfaction only where it
can support a node choice* (12 scenarios):

| # | Scenario | Test |
|---|---|---|
| 7 | A supported choice proposes satisfaction | `test_a_supported_choice_proposes_satisfaction` |
| 8 | An unsupported choice proposes no satisfaction | `test_an_unsupported_choice_proposes_no_satisfaction` |
| 9 | A refusal is recognised however it is worded | `test_a_refusal_is_recognised_however_it_is_worded` |
| 10 | The recommendation's wording does not establish the outcome | `test_the_recommendations_wording_does_not_establish_the_outcome` |
| 11 | A verdict contradicting its own prose withholds satisfaction | `test_a_verdict_contradicting_its_own_prose_withholds_satisfaction` |
| 12 | A missing verdict is unsupported, not supported | `test_a_missing_verdict_is_unsupported_not_supported` |
| 13 | An unreadable verdict is unsupported, not supported | `test_an_unreadable_verdict_is_unsupported_not_supported` |
| 14 | A fail-safe reason names what was wrong | `test_a_fail_safe_reason_names_what_was_wrong` |
| 15 | An unrecognised verdict is not reported as an absent one | `test_an_unrecognised_verdict_reads_the_same_as_a_missing_one` (see note below — meaning flipped by this change) |
| 16 | A vetoed verdict names the contradiction | `test_a_vetoed_verdict_names_the_contradiction` |
| 17 | A response that is not text still fails visibly | `test_a_response_that_is_not_text_still_fails_visibly` |
| 18 | An unsupported recommendation still says so in prose | `test_an_unsupported_recommendation_still_says_so_in_prose` |

**Note on scenario 15**: pre-change, "a verdict reported with an
unrecognised value" and "no verdict reported" were required to carry
**distinct** reasons. Structured output collapses that distinction (a
closed two-variant schema has no third "recognised-but-wrong" state), and
the delta's own text says so: "structured output no longer distinguishes
'nothing reported' from 'something unreadable reported' as two separate
technical states." The new test asserts **sameness**, the opposite of
what a same-titled test would have asserted before this change. Flagged
here so it is not mistaken for a copy-paste error.

New file:
`tests/agents/step_handlers/listing/test_subcategory_advisor_finding_and_tools.py`
— MODIFIED requirement *No tool invocation* (2 scenarios) and ADDED
requirement *A supported recommendation's value is recorded against the
product* (3 scenarios):

| # | Scenario | Test |
|---|---|---|
| 19 | Producing a recommendation invokes no tools | `test_producing_a_recommendation_invokes_no_tools` |
| 20 | Structured output is not a tool invocation | `test_structured_output_is_not_a_tool_invocation` |
| 21 | A supported recommendation carries a recordable finding | `test_a_supported_recommendation_carries_a_recordable_finding` |
| 22 | An unsupported recommendation carries no finding | `test_an_unsupported_recommendation_carries_no_finding` |
| 23 | Only the finding's value is ever written to the product | `test_only_the_findings_value_is_ever_written_to_the_product` |

### `launch-step-automation` (11 scenarios)

New file: `tests/unit/launch/application/test_step_resolution_finding_field.py`
— construction-level (partial) coverage, and:

New file: `tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py`
— the pass-level (full) coverage every scenario below needs to be fully
observed:

| # | Scenario | Test(s) |
|---|---|---|
| 1 | The product is supplied, not fetched | `test_automation_pass_finding.py::test_the_product_is_supplied_not_fetched` |
| 2 | A produced outcome is attributed to the handler | `test_automation_pass_finding.py::test_a_produced_outcome_is_attributed_to_the_handler` |
| 3 | A handler cannot claim another source | `test_automation_pass_finding.py::test_a_handler_cannot_claim_another_source_even_with_a_finding` |
| 4 | A finding changes nothing about the outcome or the result | `test_step_resolution_finding_field.py::test_a_finding_does_not_change_the_outcome_or_the_result_carried` (contract-level half) **and** `test_automation_pass_finding.py::test_a_finding_changes_nothing_about_the_outcome_or_the_result` (full, pass-level) |
| 5 | A handler reports no finding by default | `test_step_resolution_finding_field.py::test_finding_defaults_to_none` (contract-level half) **and** `test_automation_pass_finding.py::test_a_handler_reporting_no_finding_triggers_no_recording` (full, pass-level) |
| 6 | A finding's presence does not change confirmation | `test_automation_pass_finding.py::test_a_findings_presence_does_not_change_confirmation` |
| 7 | A supported finding is recorded immediately | `test_automation_pass_finding.py::test_a_supported_finding_is_recorded_immediately` |
| 8 | No recording capability means no recording, silently | `test_automation_pass_finding.py::test_no_recording_capability_means_no_recording_silently` |
| 9 | A failure finding is never recorded this way | `test_automation_pass_finding.py::test_a_failure_finding_is_never_recorded_this_way` |
| 10 | An impermissible proposal's finding is never recorded | `test_automation_pass_finding.py::test_an_impermissible_proposals_finding_is_never_recorded` |
| 11 | A recording failure does not stop the pass | `test_automation_pass_finding.py::test_a_recording_failure_does_not_stop_the_pass` |

**Note on scenarios 1-3**: their wording is unchanged from the served
spec (only scenario 4 is new to this requirement). Written fresh anyway,
per this pass's own instructions for a MODIFIED requirement ("write new
tests for the requirement's scenarios as revised, exactly as you would for
ADDED"), duplicating ground `tests/unit/launch/infrastructure/driving/test_automation_pass.py`
already covers with unedited, still-valid tests
(`test_the_product_is_supplied_not_fetched`,
`test_a_produced_outcome_is_attributed_to_the_handler`,
`test_a_smuggled_provenance_does_not_displace_the_constructed_one`). This
duplication is deliberate and stated here rather than silently accepted as
"already covered", per this pass's instructions; it is not free (see
*Unresolved project questions*), and if the dispatcher considers it
unwarranted, the newly-written duplicates can be dropped without touching
any existing file.

**Note on scenario 11's reading**: the scenario's own sentence ("no step
outcome is recorded **as a result of that failure**") is ambiguous between
"the failure itself isn't entered as an outcome" and "the whole step's
outcome recording is skipped this pass because recording failed." This
pass took the **stronger** reading, because `tasks.md` 2.4 states it
unambiguously ("without recording any step outcome ... mirroring the
existing handler-failure report"). Recorded as a DERIVED interpretation of
an ambiguous scenario sentence, resolved by the task's more explicit
wording — flagged for confirmation.

### `product-catalog` (4 scenarios)

New files: `tests/unit/catalog/domain/test_product_sub_category.py`
(domain level) and `tests/unit/catalog/application/test_record_sub_category.py`
(use-case level, over a stub store):

| # | Scenario | Test(s) |
|---|---|---|
| 1 | A sub-category is recorded for a product with none | `test_product_sub_category.py::test_a_sub_category_is_recorded_for_a_product_with_none` **and** `test_record_sub_category.py::test_a_sub_category_is_recorded_for_a_product_with_none` |
| 2 | A later recording replaces the earlier one | `test_product_sub_category.py::test_a_later_recording_replaces_the_earlier_one` **and** `test_record_sub_category.py::test_a_later_recording_replaces_the_earlier_one` |
| 3 | Recording does not require a particular stage | `test_product_sub_category.py::test_recording_does_not_require_a_particular_stage` **and** `test_record_sub_category.py::test_recording_does_not_require_a_particular_stage` |
| 4 | An unrecorded sub-category reports absence | `test_product_sub_category.py::test_an_unrecorded_sub_category_reports_absence` (domain level only — deliberate; see its own file's docstring) |

## Uncovered scenarios

None. All 38 are covered above.

## Assertion classification

Every test file above labels its own assertions `SPECIFIED` or `DERIVED`
inline, per `ai-toolkit:testing`'s rule, following this project's own
established convention in its pre-existing agent-graph test files. The
DERIVED assertions worth calling out specifically, because they shape what
a later implementer or reviewer should treat as negotiable:

- **`Blocked` as the specific non-terminal outcome** for every withheld
  path in `test_subcategory_advisor_structured_verdict.py` and
  `test_subcategory_advisor_structured_recommendation.py`. The scenarios
  themselves say only "non-terminal"; `Blocked` is inferred as the only
  non-terminal outcome that can carry the reason every one of these
  scenarios requires.
- **Keyword-based reason-content checks** (e.g. asserting a reason
  contains "cannot"/"could not"/"contradict"/etc.). No artifact fixes
  exact wording; these check that *some* language consistent with the
  scenario's own words is present, not a specific string.
- **`_ScriptedStructuredRunnable`'s `{"raw": ..., "parsed": ..., "parsing_error": ...}`
  return shape**, matching `langchain`'s own documented convention for
  `with_structured_output(..., include_raw=True)`. Grounded in the
  upstream library's behaviour rather than invented outright, but still
  unconfirmed against this project's actual node implementation — see
  *Unresolved project questions*.
- **The recording-capability collaborator's keyword and shape** on the
  pass entry point (`_RECORDER_KWARG_CANDIDATES`, a mapping from step
  identifier to an async `(product_id, value)` callable) — the single
  largest INVENTED surface in this pass, since no artifact fixes it at
  all beyond "supplied for `lp.listing.007` specifically, not for every
  step" (`tasks.md` 4.2).
- **DERIVED tests not tied to a named scenario**: `tests/unit/shared/domain/test_result.py`
  (the `Success`/`Failure` shape itself — supporting infrastructure for
  `launch-step-automation`'s ADDED requirement, not a scenario of its
  own) and `test_subcategory_advisor_structured_verdict.py::test_routes_1_2_and_3_carry_distinguishable_reasons`
  (the cross-route distinctness property `tasks.md` 5.5-5.6 states but no
  single scenario names directly).

## Obsolete tests

Applicable: `subcategory-advisor` and `launch-step-automation` both carry
MODIFIED requirements. `product-catalog` carries only ADDED requirements
and contributes nothing to this list.

Search bounded to the dispatched test-path glob (`tests/**/test_*.py`)
only, and only within files this pass actually read while deriving tests
(the three pre-existing `subcategory-advisor` agent-tier files). No
broader search was performed. Every entry below is a **candidate for
human confirmation**, not a conclusion.

1. **`tests/agents/step_handlers/listing/test_subcategory_advisor_verdict.py`**
   — all 13 tests (`test_the_verdict_is_reported_as_a_value_alongside_the_recommendation`,
   `test_an_unsupported_choice_proposes_no_satisfaction`,
   `test_a_refusal_is_recognised_however_it_is_worded`,
   `test_the_recommendations_wording_does_not_establish_the_outcome`,
   `test_a_verdict_contradicting_its_own_prose_withholds_satisfaction`,
   `test_a_missing_verdict_is_unsupported_not_supported`,
   `test_an_unreadable_verdict_is_unsupported_not_supported`,
   `test_a_fail_safe_reason_names_what_was_wrong`,
   `test_an_unrecognised_verdict_is_not_reported_as_an_absent_one`,
   `test_a_vetoed_verdict_names_the_contradiction`,
   `test_each_withheld_path_records_its_own_reason`,
   `test_a_response_that_is_not_text_still_fails_visibly`,
   `test_an_unsupported_recommendation_still_says_so_in_prose`).
   Superseding delta: MODIFIED requirement *The advisor proposes
   satisfaction only where it can support a node choice*. Evidence: this
   file drives `propose()` by constructing `AdvisorState` dicts carrying a
   bare string `verdict` field (`"supported"`/`"unsupported"`/an
   unrecognised value) alongside free-prose `recommendation` text — the
   exact mechanism `tasks.md` 5.3-5.4 retires ("remove `_split_verdict`
   and `_VERDICT_LINE`"; narrow `_advisor_refuses` to the new `comment`
   field of an `ok`-discriminated schema). The state shape this file's own
   `_verdict_field()`/`_state()` helpers target has no analog once the
   `recommend` node calls `model.with_structured_output(AdvisorResult,
   include_raw=True)`.

2. **`tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py`**
   — `test_a_recommendation_names_node_demands_and_alternative`,
   `test_a_recommendation_is_readable_as_it_stands`,
   `test_a_supported_choice_proposes_satisfaction`,
   `test_an_unsupported_choice_proposes_no_satisfaction`,
   `test_producing_a_recommendation_invokes_no_tools`.
   Superseding delta: the same MODIFIED requirements as above, plus
   MODIFIED *No tool invocation*. Evidence: `_ScriptedChatModel` answers
   via `_generate` with raw prose (`SUPPORTED_ANSWER = "Verdict:
   supported\n\n" + ...`), read back through `_recommendation_of`'s
   free-text handling — a shape the new `with_structured_output(...)`
   seam does not consume.
   **Not** included: `test_two_invocations_do_not_share_context`,
   `test_two_invocations_for_the_same_product_are_independent`,
   `test_a_model_failure_is_surfaced`,
   `test_a_non_string_response_content_is_surfaced`,
   `test_a_non_string_response_is_never_returned_as_a_recommendation`.
   Their governing requirements (*No state across invocations*, *Model
   failure is surfaced, not masked*) are **not** in this change's delta
   spec at all, so they are not superseded by any delta this pass covers.
   They may still need re-verification once a real implementation lands
   (a real chat model's `with_structured_output(...)` still funnels
   through the same underlying call these tests exercise, so they are
   expected to keep passing, but that expectation is not itself a
   spec-derived claim).

3. **`tests/agents/step_handlers/listing/test_subcategory_advisor_marketplace.py`**
   — both tests (`test_the_marketplace_reaching_the_model_is_the_identifier`,
   `test_a_refusal_names_the_marketplace_as_a_reader_would_recognise_it`).
   Superseding delta: MODIFIED requirement *A recommendation is produced
   from the product's name and marketplace*. Evidence: `_CapturingChatModel`
   answers via `_generate` with prose scripts (`_SUPPORTED`/`_REFUSAL`,
   both `"Verdict: supported\n..."`/`"Verdict: unsupported\n..."` style),
   driven through `advisor.advise_sub_category(context)` with `_graph()`
   monkeypatched — the same structural mismatch with the new mechanism as
   entry 2 above.

No test outside these three files was found to bear on this change's
MODIFIED requirements, within the bounded search this pass performed.

## Unresolved project questions

Recorded with the assumption taken and the tests that depend on it, per
this pass's own instructions for discharging a convention obligation with
no channel to ask on:

1. **The recording-capability collaborator's name and shape** on the
   pass's entry point (`launch/infrastructure/driving/automation_pass.py`).
   Assumption: a keyword argument named one of `recorders`,
   `finding_recorders`, `recording_capabilities`, `sub_category_recorders`,
   or `record_finding`, carrying a mapping from step identifier to an
   async `(product_id, value) -> object` callable. Depends on this:
   every test in `test_automation_pass_finding.py` that supplies
   `recorders=...`.
2. **`with_structured_output(..., include_raw=True)`'s return shape**,
   assumed to match `langchain`'s own documented `{"raw", "parsed",
   "parsing_error"}` dict rather than some project-specific wrapper.
   Depends on this: `_ScriptedStructuredRunnable` in all four new
   `subcategory-advisor` test files.
3. **`propose()`'s continued call shape and return shape** — that it still
   accepts `product_name=`, `marketplace=`, `graph=` and returns something
   exposing `.outcome`/`.result`/`.finding` directly (carried over
   unchanged from this project's own pre-existing INVENTED assumption in
   `test_subcategory_advisor_verdict.py`, not re-litigated here). Depends
   on this: every `_propose`/`_outcome_of`/`_text_of`/`_finding_of` helper
   in the four new `subcategory-advisor` files.
4. **`Product.record_sub_category`'s store method names**, addressed
   defensively (`_SubCategoryStore` answers to `get_by_id`, `get`,
   `get_by_product_id`, and `save`) rather than resolved to one name.
   Depends on this: `test_record_sub_category.py`.
5. **Whether the new pass-level tests for scenarios 1-3 of the MODIFIED
   `launch-step-automation` handler-contract requirement are wanted at
   all**, given their wording is unchanged from the served spec and
   `test_automation_pass.py` already covers them with unedited, valid
   tests. This pass wrote them anyway per its own binding instructions
   ("exactly as you would for ADDED"); flagged in case the dispatcher
   judges the duplication unwarranted for this specific case.
6. **Whether a real-database integration test for the sub-category field**
   (mirroring `tests/integration/catalog/test_catalog_products.py`'s ASIN
   persistence scenario) is expected. `tasks.md` 6.4 asks only for unit
   tests, which is what this pass wrote; the product-catalog spec's own
   wording ("reading the product back reports...") reads structurally
   identical to the ASIN scenario, which *did* receive integration-tier
   coverage historically. Not written by this pass — flagged as a possible
   gap rather than resolved either way.
7. **No project-specific skill for LangGraph agent testing beyond
   `langgraph` itself** was found; this pass followed the existing
   `tests/agents/step_handlers/listing/*` files' own established idiom
   instead of a dedicated skill, per this pass's floor-alone fallback.

## What the implementation step must make pass

Every test named in the *Scenario accounting* tables above, across:

- `tests/unit/shared/domain/test_result.py`
- `tests/unit/launch/application/test_step_resolution_finding_field.py`
- `tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py`
- `tests/unit/catalog/domain/test_product_sub_category.py`
- `tests/unit/catalog/application/test_record_sub_category.py`
- `tests/agents/step_handlers/listing/test_subcategory_advisor_structured_recommendation.py`
- `tests/agents/step_handlers/listing/test_subcategory_advisor_structured_verdict.py`
- `tests/agents/step_handlers/listing/test_subcategory_advisor_finding_and_tools.py`

Run selectively with `uv run pytest <path>::<test_name>` (or a bare
`<path>` for a whole file), inside the uv-managed environment.

The *Obsolete tests* section above lists three pre-existing files whose
bearing tests should be reviewed for deletion or rewrite once the new
mechanism is implemented — those files were not touched by this pass and
remain green-or-red exactly as they were before it (all three currently
pass, since nothing about the pre-change implementation has moved yet).
