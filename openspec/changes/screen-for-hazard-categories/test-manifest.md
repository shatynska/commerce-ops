# Test manifest — `screen-for-hazard-categories`

Written before any implementation, by an author who has not read the
implementation of the behaviour under test (`AGENTS.md`, *Test design before
implementation*). **This file is not an artifact the OpenSpec schema knows
about**, so it does not appear among `openspec instructions apply`'s context
files and must be read on purpose before implementing.

Every test named below is selectable individually with
`uv run pytest '<node id>'`.

---

## Baseline

Taken at this worktree root on 2026-09-03, **before** any test in this pass was
written:

| Command | Result |
|---|---|
| `uv run pytest tests/unit tests/agents` | **2352 passed**, 0 failed, 0 skipped |
| `uv run pytest tests/integration` | **152 passed**, 0 failed, 0 skipped |

A full baseline, not a scoped one. The integration tier is configured in this
worktree (`.env.test` present, database migrated and seeded), so its green is
evidence it ran rather than skipped.

**After this pass** (same commands, `--continue-on-collection-errors`):

| Command | Result |
|---|---|
| `uv run pytest tests/unit tests/agents` | 2411 passed, 59 failed, 1 collection error |
| `uv run pytest tests/integration` | 152 passed, 1 collection error |

2411 = 2352 baseline + 59 new tests that pass on first run. **No pre-existing
test changed state.** Every failure and both collection errors belong to the
files this pass added; each is accounted for under *First-run state*, below.

---

## Scope of this pass

**Additive only. This pass adds tests and never subtracts.** No existing test
file was edited, deleted, disabled or weakened, and no implementation was
written. Every write landed inside `tests/**/test_*.py` except this manifest.

---

## Files written

| File | Tier |
|---|---|
| `tests/unit/catalog/domain/test_product_hazard_categories.py` | unit |
| `tests/unit/catalog/application/test_record_hazard_categories.py` | unit |
| `tests/integration/catalog/test_product_hazard_categories.py` | integration |
| `tests/agents/step_handlers/strategy/test_compliance_screen_hazard_finding.py` | agents |
| `tests/agents/step_handlers/strategy/test_compliance_screen_category_naming.py` | agents |
| `tests/unit/step_handlers/strategy/test_compliance_screen_categories_field.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_launch_detail_finding_members.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_product_dossier_established_by_automation.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_automation_pass_hazard_finding.py` | unit |
| `tests/unit/launch/application/test_rejected_hazard_finding_stands.py` | unit |
| `tests/unit/test_hazard_category_sink_registration.py` | unit |

---

## Scenario accounting

**62 `#### Scenario:` blocks across the four delta files** — 27
(`compliance-screen`), 10 (`launch-admin`), 13 (`product-catalog`), 12
(`product-dossier`). All 62 are accounted for below, plus the 3 scenarios of
the REMOVED requirement.

Abbreviations for the file each test lives in:

- **HF** — `tests/agents/step_handlers/strategy/test_compliance_screen_hazard_finding.py`
- **CN** — `tests/agents/step_handlers/strategy/test_compliance_screen_category_naming.py`
- **SF** — `tests/unit/step_handlers/strategy/test_compliance_screen_categories_field.py`
- **PD** — `tests/unit/catalog/domain/test_product_hazard_categories.py`
- **PA** — `tests/unit/catalog/application/test_record_hazard_categories.py`
- **PI** — `tests/integration/catalog/test_product_hazard_categories.py`
- **RJ** — `tests/unit/launch/application/test_rejected_hazard_finding_stands.py`
- **AP** — `tests/unit/launch/infrastructure/driving/test_automation_pass_hazard_finding.py`
- **LM** — `tests/unit/launch/infrastructure/driving/test_launch_detail_finding_members.py`
- **DO** — `tests/unit/launch/infrastructure/driving/test_product_dossier_established_by_automation.py`
- **SR** — `tests/unit/test_hazard_category_sink_registration.py`

### `compliance-screen` — MODIFIED: Satisfaction is proposed only for a clear verdict

| Scenario | Covered by |
|---|---|
| A clear verdict proposes satisfaction | `HF::test_a_clear_verdict_proposes_satisfaction` |
| A flagged verdict proposes a non-terminal outcome | `HF::test_a_flagged_verdict_naming_a_category_proposes_a_non_terminal_outcome` |
| An undetermined verdict proposes a non-terminal outcome | `HF::test_an_undetermined_verdict_proposes_a_non_terminal_outcome` |
| An unreadable verdict is not reported as a judgement about the product | `HF::test_an_unreadable_verdict_is_not_a_judgement_about_the_product` |
| A blank comment outranks a structural contradiction | `HF::test_a_blank_comment_outranks_a_structural_contradiction` (8 parametrised rows) |

### `compliance-screen` — MODIFIED: A verdict its own response contradicts is not satisfaction

| Scenario | Covered by |
|---|---|
| A clear verdict carrying a stated inability is refused | `HF::test_a_clear_verdict_carrying_a_stated_inability_is_refused` |
| A statement about a category does not withhold satisfaction | `HF::test_a_statement_about_a_category_does_not_withhold_satisfaction` |
| A clear verdict naming categories is refused | `HF::test_a_clear_verdict_naming_categories_is_refused` |
| The structural contradiction is not reported as the prose one | `HF::test_the_structural_contradiction_is_not_reported_as_the_prose_one` |
| A contradicted verdict establishes nothing about the product | `HF::test_a_contradicted_verdict_establishes_nothing_about_the_product[prose]`, `[structural]` |

### `compliance-screen` — REMOVED: The screen reads only what it is given, and reports no finding

Its 3 scenarios, accounted for by the operation:

| Scenario | Accounting |
|---|---|
| The product is taken from the context | **Not uncovered by removal** — re-stated verbatim in the ADDED requirement below, and accounted for there. |
| A value reaching the model is the value, not its object's rendering | Likewise. |
| No finding accompanies the outcome | **Uncovered, and superseded.** The behaviour it asserts is reversed by this change; the tests bearing on it are in the obsolete list. No new test is written for a removed scenario. |

### `compliance-screen` — ADDED: The screen reads only what it is given

| Scenario | Covered by |
|---|---|
| The product is taken from the context | `tests/agents/step_handlers/strategy/test_compliance_screen_failure_and_context.py::test_the_product_is_taken_from_the_context` — **existing, untouched** |
| A value reaching the model is the value, not its object's rendering | Same file, `::test_a_value_reaching_the_model_is_the_value_not_its_rendering` — **existing, untouched** |

**Why no new test.** The delta's own Migration note says this requirement is
"re-stated verbatim … with no change to its normative content or its
scenarios". The existing tests are not superseded and assert exactly the
scenarios as written. Writing duplicates would add no evidence and put two pins
on the same behaviour. **This is a judgement, recorded rather than hidden**: an
implementer who wants the ADDED requirement to have tests authored in this pass
should say so.

### `compliance-screen` — ADDED: The screen reports what it established as a typed finding

| Scenario | Covered by |
|---|---|
| A clear verdict establishes an empty set of categories | `HF::test_a_clear_verdict_establishes_an_empty_set_of_categories` |
| A flagged verdict establishes the categories it named | `HF::test_a_flagged_verdict_establishes_the_categories_it_named` |
| An undetermined verdict establishes nothing | `HF::test_an_undetermined_verdict_establishes_nothing[none|one|several]` |
| An unreadable verdict establishes nothing | `HF::test_an_unreadable_verdict_establishes_nothing`; the blank-comment route in `HF::test_a_blank_comment_establishes_nothing` (12 rows) |
| A screen given nothing to work with establishes nothing | `HF::test_a_screen_given_no_product_establishes_nothing`; `HF::test_a_step_naming_no_categories_establishes_nothing[absent|empty|blank]` |
| A prior flag survives a later screening that establishes nothing | `HF::test_a_prior_flag_survives_a_later_screening_that_establishes_nothing`; pass-side half in `AP::test_a_screening_that_establishes_nothing_invokes_no_recorder` |
| The outcome and the produced text are unaffected | `HF::test_the_outcome_and_produced_text_are_unaffected_by_the_finding` |

The requirement's clause *The finding SHALL NOT name the field it is written
to* — stated in prose rather than as a scenario — is covered by
`HF::test_the_finding_names_no_field`.

### `compliance-screen` — ADDED: A flagged verdict naming no category establishes nothing

| Scenario | Covered by |
|---|---|
| A flagged verdict naming nothing is not recorded as flagged | `HF::test_a_flagged_verdict_naming_nothing_is_not_recorded_as_flagged` |
| Its reason is its own | `HF::test_the_flagged_naming_nothing_reason_is_its_own` |

### `compliance-screen` — ADDED: The categories the screen names are the step's own wording

| Scenario | Covered by |
|---|---|
| A repeated category is reported once | `CN::test_a_repeated_category_is_reported_once[identical|case|whitespace|position-preserved]` |
| A blank category name is dropped | `CN::test_a_blank_category_name_is_dropped[empty|spaces|tab|newlines]`; the all-drop clause in `CN::test_a_flagged_verdict_whose_every_name_drops_names_no_category` |
| The model is instructed to use the description's wording | `CN::test_the_model_is_instructed_to_use_the_descriptions_wording` |
| A named category is carried through unaltered | `CN::test_a_named_category_is_carried_through_unaltered[padded|tabbed|upper-inner|title-case|multi-word]` |
| The description is not parsed to validate a name | `CN::test_a_category_the_description_does_not_contain_is_still_reported`; `CN::test_a_re_authored_description_does_not_filter_the_reported_names` |
| No category is supplied that the response did not name | `CN::test_no_category_is_supplied_that_the_response_did_not_name` |

### `launch-admin` — MODIFIED: A carried finding's result is rendered ahead of its comment

| Scenario | Covered by |
|---|---|
| A value of several members renders as those members | `LM::test_every_member_of_a_multi_member_value_appears`; `LM::test_the_members_are_separated_from_one_another`; `LM::test_the_members_carry_no_collection_notation`; `LM::test_the_result_still_leads_with_the_field_for_a_multi_member_value` |
| A textual value is not rendered as its characters | `LM::test_a_textual_value_is_rendered_as_one_value` |
| An empty value renders as readable text | `LM::test_an_empty_membered_value_renders_as_readable_text`; `LM::test_an_empty_membered_value_is_distinguishable_from_a_flagged_one` |
| The field and value lead the outcome | `test_launch_detail_finding_rendering.py::test_the_field_and_value_lead_the_outcome` — **existing, untouched** |
| The result carries no leading prose | Same file, `::test_the_result_carries_no_leading_prose` — existing |
| The field reads as an admin's words | Same file, `::test_the_field_reads_as_an_admins_words` — existing |
| A field with no supplied wording still renders | Same file, `::test_a_field_with_no_supplied_wording_still_renders` — existing |
| The distinction survives without colour | Same file, `::test_the_distinction_survives_without_colour` — existing |
| A recording with no carried finding is rendered unchanged | Same file, `::test_a_recording_with_no_carried_finding_is_rendered_unchanged` — existing |
| The evidence and provenance are still rendered | Same file, `::test_the_evidence_and_provenance_are_still_rendered` — existing |

**Why the last seven are accounted against existing tests.** Those scenarios'
text is byte-identical to the served spec; the requirement is MODIFIED only by
the three member/string/emptiness clauses. The existing file is not superseded
and covers them at the same level with a harness this pass could only duplicate.
Reproducing ~1000 lines to re-assert eight identical scenarios would add no
evidence and put two pins on the same markup. **Recorded as a judgement**, not
performed silently.

### `product-catalog` — ADDED: A hazard-category finding can be recorded against a product

| Scenario | Covered by |
|---|---|
| Hazard categories are recorded for a product with none | `PD::test_hazard_categories_are_recorded_for_a_product_with_none`; `PA::` same name; `PI::test_a_recorded_non_empty_set_round_trips_with_every_member` |
| An empty set is recorded as an empty set | `PD::test_an_empty_set_is_recorded_as_an_empty_set`; `PA::` same name; `PI::test_a_recorded_empty_set_round_trips_as_recorded_and_empty` |
| A later recording replaces the earlier one wholesale | `PD::test_a_later_recording_replaces_the_earlier_one_wholesale`; `PA::` same name; `PI::test_a_later_recording_replaces_the_stored_set_wholesale` |
| An empty set replaces a recorded set | `PD::test_an_empty_set_replaces_a_recorded_set`; `PA::` same name; `PI::test_a_stored_set_is_replaced_by_an_empty_set` |
| Recording does not require a particular stage | `PD::`, `PA::`, `PI::test_recording_does_not_require_a_particular_stage` |
| What was screened against is not recorded with the result | `PD::test_what_was_screened_against_is_not_recorded_with_the_result[flagged|empty|several]` |

### `product-catalog` — ADDED: A product reports its hazard categories in three states, never two

| Scenario | Covered by |
|---|---|
| A never-screened product reports the question as open | `PD::test_a_never_screened_product_reports_the_question_as_open`; `PI::test_a_never_screened_product_round_trips_as_never_recorded` |
| A cleared product reports an answered question | `PD::test_a_cleared_product_reports_an_answered_question`; `PA::` same name; `PI::test_a_recorded_empty_set_round_trips_as_recorded_and_empty` |
| A flagged product reports its categories | `PD::test_a_flagged_product_reports_its_categories`; `PA::` same name |
| A product predating the field reports the question as open | `PD::test_a_product_predating_the_field_reports_the_question_as_open`; `PI::test_a_never_screened_product_round_trips_as_never_recorded` |

The requirement's "SHALL NOT collapse any two of them" is asserted pairwise, as
`tasks.md` 1.3 asks, in `PD::test_the_three_states_are_pairwise_distinguishable`
and `PI::test_the_three_states_are_pairwise_distinguishable_in_storage`.

### `product-catalog` — ADDED: A recorded hazard-category set is what a screening established

| Scenario | Covered by |
|---|---|
| A rejected proposal's recorded value stands | `RJ::test_a_rejected_proposals_recorded_value_stands` |
| A rejected clear reading is still a screening, not an open question | `RJ::test_a_rejected_clear_reading_is_still_a_screening` |
| A later screening replaces a disputed value | `RJ::test_a_later_screening_is_what_replaces_a_disputed_value`; `PD::test_a_later_screening_replaces_a_disputed_value` |

The clause "no mechanism reaches back into a value on a decision's behalf" —
prose, not a scenario — is guarded structurally by
`RJ::test_the_rejection_path_is_given_no_route_to_the_product`.

### `product-dossier` — ADDED: The dossier renders what the product's automated steps have established

| Scenario | Covered by |
|---|---|
| The region is present and marked | `DO::test_the_region_is_present_and_marked` |
| A recorded sub-category is rendered | `DO::test_a_recorded_sub_category_is_rendered` |
| The region renders for a product with nothing established | `DO::test_the_region_renders_for_a_product_with_nothing_established` |

### `product-dossier` — ADDED: An unrecorded sub-category is stated, not blank

| Scenario | Covered by |
|---|---|
| An absent sub-category carries the page's absence marker | `DO::test_an_absent_sub_category_carries_the_pages_absence_marker` |

### `product-dossier` — ADDED: The dossier renders hazard categories in three states

| Scenario | Covered by |
|---|---|
| A never-screened product says so | `DO::test_a_never_screened_product_says_so` |
| A screened-clear product is not rendered as unscreened | `DO::test_a_screened_clear_product_is_not_rendered_as_unscreened` |
| A flagged product presents its categories | `DO::test_a_flagged_product_presents_its_categories` |
| Categories are not presented in a collection's notation | `DO::test_categories_are_not_presented_in_a_collections_notation` |
| The three states render three ways | `DO::test_the_three_states_render_three_ways` |
| The field claims no ratification | `DO::test_the_field_claims_no_ratification[screened-clear|flagged]` |

### `product-dossier` — ADDED: The region offers no action and carries no page-local styling

| Scenario | Covered by |
|---|---|
| The region is read-only | `DO::test_the_region_is_read_only` |
| The new state's presentation is shared, not page-local | `DO::test_the_new_states_presentation_is_shared_not_page_local` |

### Tests written from `tasks.md` rows with no delta scenario behind them

Recorded here so they are not mistaken for spec-derived coverage. All are
classified **DERIVED**.

| Test | Traces to |
|---|---|
| `SF::test_the_widened_schema_is_accepted_by_the_providers_own_conversion` | `tasks.md` 1.6; re-exercises the unchanged served requirement |
| `SF::test_the_widened_schema_is_not_a_union_the_adapter_rejects` | `tasks.md` 1.6, `design.md` Decision 2 |
| `SF::test_the_widened_converted_schema_emits_no_oneof_anywhere` | `tasks.md` 1.6 |
| `SF::test_the_categories_field_is_an_array_of_plain_strings` | `tasks.md` 1.6, `design.md` Decision 2 |
| `SF::test_the_verdict_is_still_a_plain_string_carrying_the_three_values` | `tasks.md` 1.6 |
| `SF::test_every_wire_field_the_new_one_included_carries_a_description` | `tasks.md` 1.7 + `tasks.md` 4.1's field set |
| `HF::test_model_failure_is_surfaced_not_masked` | `tasks.md` 1.14; unchanged requirement, re-exercised |
| `AP::test_an_empty_sequence_finding_reaches_the_recorder_as_an_empty_sequence` | `tasks.md` 1.15 |
| `AP::test_a_flagged_finding_reaches_the_recorder_with_every_member` | `tasks.md` 1.15 |
| `AP::test_an_empty_sequence_finding_is_kept_as_present_and_empty` | `tasks.md` 1.16 |
| `AP::test_a_kept_empty_finding_is_distinguishable_from_no_finding_at_all` | `tasks.md` 1.16 |
| `AP::test_a_confirmable_screening_stores_its_empty_finding_with_the_result` | `tasks.md` 1.15 |
| `SR::test_the_worker_registers_a_sink_for_the_compliance_screen` | `tasks.md` 1.19, 5.3 |
| `SR::test_the_screens_sink_names_the_field_and_its_wording` | `tasks.md` 5.3 |
| `SR::test_the_existing_sink_is_still_registered_beside_it` | `tasks.md` 5.3 |
| `PD::test_a_caller_cannot_mutate_what_the_aggregate_holds` | `tasks.md` 3.1's immutability clause |
| `PA::test_the_recording_is_saved_and_not_only_held_in_memory` | `tasks.md` 3.2 |
| `CN::test_a_re_authored_description_does_not_filter_the_reported_names` | differential companion to the no-parsing scenario |
| `CN::test_a_flagged_verdict_whose_every_name_drops_names_no_category` | the naming requirement's deferral clause + `tasks.md` 1.12 |
| `LM::test_an_empty_membered_value_is_distinguishable_from_a_flagged_one` | the requirement's two-clause structure |

---

## Deliberately untested, recorded rather than omitted

- **Whether a verdict is correct about a product.** No deterministic test can
  establish it; live verification is `tasks.md` 8.7's job.
- **Whether the model obeys the naming instruction.** The delta places the
  obligation on the prompt *precisely because* no code checks it, so a test
  asserting obedience would assert against the requirement.
- **Whether each wire-field description in fact says *when* to populate the
  field.** Judging that means parsing prose for content, which this
  capability's *A comment's content is never checked by code* forbids.
- **The wording of any reason, and the wording behind `screened-clear`.**
  `design.md`'s Open Questions defers the latter to the running page and
  records that it "changes no test derived from" the specified parts. Only
  distinctness and markers are asserted.
- **How members are separated from one another**, on either surface. Both
  requirements decline to fix it; the tests assert *that* something separates
  them, never what.
- **Whether the produced text should also carry the categories a plain
  `flagged` verdict named.** Required for the structural contradiction, silent
  for the ordinary flagged route; nothing asserts either way.
- **Whether the provider's API accepts the schema both local conversions
  accept.** No offline check can establish it.

---

## Obsolete tests — candidates for human confirmation

**Bounded search.** The dispatched test-path glob `tests/**/test_*.py` and
nowhere else. No earlier `test-manifest.md` was supplied, so the search drew on
the glob alone: grep over the served spec's superseded assertions
(`no finding`, `finding is None`, `WIRE_FIELDS`, `not-recorded`) plus reading
the four test files bearing on the compliance screen, the launch detail
finding rendering and the dossier.

**Three entries. Each is a CANDIDATE FOR HUMAN CONFIRMATION, never a
conclusion. This pass edited none of them.**

### 1. `test_no_finding_accompanies_the_outcome` — two of its three rows

- **Node ids** (parametrised; ids embed the fixture comments):
  - `tests/agents/step_handlers/strategy/test_compliance_screen_failure_and_context.py::test_no_finding_accompanies_the_outcome[clear-Considered each named heading: nothing about this item is ingestible, pressurised or battery-powered, so none applies.]`
  - `tests/agents/step_handlers/strategy/test_compliance_screen_failure_and_context.py::test_no_finding_accompanies_the_outcome[flagged-This falls under one of the named headings.]`
- **Superseded by**: `compliance-screen` REMOVED *The screen reads only what it
  is given, and reports no finding* → ADDED *The screen reports what it
  established as a typed finding*.
- **Evidence**: the test's own body asserts
  `getattr(resolution, "finding", None) is None` for every verdict, and its
  docstring names the scenario verbatim — *"Scenario: No finding accompanies
  the outcome"* — and gives as its reason "reporting a finding no sink accepts
  would record nothing", which this change makes false by registering the sink.
  The new requirement requires a finding on exactly the `clear` and
  `flagged`-naming-a-category routes, so those two rows now assert the opposite
  of the spec.
- **The `undetermined` row and `test_no_finding_accompanies_an_unreadable_verdict`
  are NOT obsolete**: the new requirement still reports no finding on both, so
  they remain correct. Deleting the whole test would remove live coverage.

### 2. `test_wire_fields_state_when_they_are_to_be_populated`

- **Node id**:
  `tests/unit/step_handlers/strategy/test_compliance_screen_schema_conversion.py::test_wire_fields_state_when_they_are_to_be_populated`
- **Superseded by**: `tasks.md` 4.1 (`ScreenResponse` gains `categories`),
  under `design.md` Decision 2.
- **Evidence**: the test asserts `set(properties) == set(WIRE_FIELDS)` against
  the module constant `WIRE_FIELDS: Final = ("verdict", "comment")`. A third
  wire field makes that equality false by construction. The rest of that
  file's tests are unaffected and are re-exercised, not replaced, by
  `tests/unit/step_handlers/strategy/test_compliance_screen_categories_field.py`.

### 3. `test_a_products_identity_is_rendered_whole` — its closing assertion

- **Node id**:
  `tests/unit/launch/infrastructure/driving/test_product_dossier_page.py::test_a_products_identity_is_rendered_whole`
- **Superseded by**: `product-dossier` ADDED *An unrecorded sub-category is
  stated, not blank* and *The dossier renders hazard categories in three
  states*.
- **Evidence**: its last assertion is
  `assert not _page_carries(page, NOT_RECORDED)` — commented "SPECIFIED,
  negatively: nothing is `not-recorded` on a product whose fields are all
  populated". Its subject `_fully_populated()` populates ASIN, stage and
  confirmer, and records **no** sub-category and **no** hazard categories. The
  new region requires `not-recorded` on both of those fields, so the page will
  carry the marker and this assertion will fail. Everything else in the test
  (SKU, name, marketplace, ASIN, stage, moment, confirmer) remains correct.

**Nothing else was found by this search.** That is stated as what it is — *none
was found by this search*, not *no such test exists*. In particular the search
was not able to rule out a bearing test outside the four files read in full.

---

## An implementation collision this pass could not resolve

Not an obsolete-test entry, because these tests assert nothing superseded — but
they will **break** on the implementation as `tasks.md` 4.1 describes it, and
that is worth knowing before the diff is written rather than after.

Three existing agent test files script the wire model by instantiating the
class captured at the `with_structured_output(...)` call site with **two**
keywords only:

```python
self._schema(verdict=self._script.verdict, comment=self._script.comment)
```

- `tests/agents/step_handlers/strategy/test_compliance_screen_verdict_routing.py:256`
- `tests/agents/step_handlers/strategy/test_compliance_screen_categories.py:194`
- `tests/agents/step_handlers/strategy/test_compliance_screen_failure_and_context.py:199`

`tasks.md` 4.1 says `categories: list[str]`, **required**. A pydantic field with
no default is required at construction, so every one of those instantiations
raises `ValidationError` and those three files fail wholesale — roughly 60
existing tests. (The reverse direction is already confirmed safe: this pass's
new harnesses pass `categories=` to the current two-field model and pydantic's
default `extra='ignore'` drops it, which is why they collect today.)

Two ways out, and **choosing between them is the implementer's call, not this
pass's**:

- give the field a pydantic default (`Field(default_factory=list, description=…)`),
  which keeps the existing harnesses working but takes the property out of the
  generated schema's `required` list — check that against `design.md` Decision
  2's "required rather than optional, because under strict structured output
  every property is required anyway"; or
- keep it required and accept that the three files must be updated, which is a
  **destructive edit this pass is forbidden to make and must not be made
  silently.**

`tests/unit/step_handlers/strategy/test_compliance_screen_categories_field.py`
does **not** assert the field is in `required`, deliberately: fixing that would
pre-empt the decision.

---

## Unresolved project questions

Each is an assumption taken, with the tests that depend on it. None was
resolved silently; none has a channel to ask on, so each is recorded here and
surfaced in the report (`AGENTS.md` and `CLAUDE.md` were read; neither answers
any of these).

1. **The sentinel for "never recorded".** The delta fixes only that the state
   is distinguishable. Assumed `None`, following `asin` and `sub_category` on
   the same aggregate and `design.md` Decision 1's `NULL`. **Every
   three-state assertion is written pairwise first** (comparing two products'
   readings), so a different sentinel is a fixture correction and the
   distinction is not. Depends on it: `PD::test_a_never_screened_product_…`,
   `PD::test_a_product_predating_the_field_…`, `PI::test_a_never_screened_…`.
2. **The call convention of `record_hazard_categories`.** Assumed positional
   `(store, product_id, categories)`, matching `record_asin` and
   `record_sub_category`'s existing call sites. Depends on it: all of `PA`,
   all of `PI`.
3. **The read-back attribute name `product.hazard_categories`.** Fixed by
   `tasks.md` 3.1 as a field; that it is readable under that name is assumed,
   mirroring `sub_category`. Depends on it: `PD`, `PA`, `PI`, `RJ`, `DO`.
4. **How the wording instruction is phrased in the prompt.** The delta fixes
   that the instruction exists and fixes no wording. `_WORDING_INSTRUCTION_PHRASES`
   in `CN` accepts nine phrasings and names all nine on failure. Depends on it:
   `CN::test_the_model_is_instructed_to_use_the_descriptions_wording`.
5. **Whether `tasks.md` 1.19's "both composition roots hold the second sink"
   is achievable as written.** Finding sinks are read only by the automation
   pass, which runs in the worker; the existing cross-process file checks
   *handlers* and *recurring work*, both of which really are registered in
   every process, and the existing `lp.listing.007` sink is not. `SR` asserts
   the **worker** root only. Depends on it: all of `SR`. **Raised, not
   resolved.**
6. **Which element the dossier's hazard and sub-category fields are.** The
   delta fixes the region's marker and each field's markers, not the markup.
   `DO::_field_in_region` locates a field as the smallest element inside the
   region naming it. Depends on it: every `DO` test but
   `test_the_region_is_present_and_marked`,
   `test_the_region_is_read_only` and
   `test_the_new_states_presentation_is_shared_not_page_local`.
7. **How a field's wording reaches the launch detail page.** Inherited
   unresolved from `separate-the-result-from-the-comment`'s own manifest;
   `LM::_supply_wording` installs whichever of two routes the page exposes.
   Depends on it: `LM::test_the_result_still_leads_with_the_field_…`,
   `LM::test_an_empty_membered_value_renders_as_readable_text`.
8. **What "each readable and separated" excludes.** Asserted as "the two
   members do not appear run together with nothing between them", after
   stripping whitespace — so a separator made only of whitespace fails.
   `AGENTS.md` records no convention. Depends on it:
   `LM::test_the_members_are_separated_from_one_another`,
   `DO::test_a_flagged_product_presents_its_categories`.
9. **A minor artifact disagreement, reported not acted on.** `proposal.md`'s
   *What Changes* says "the wire schema gains the categories, and gains two
   structural contradictions with them", reading as though the schema
   requirement is modified; `design.md` Decision 2 says the opposite — "it is
   not modified" — and the delta has no MODIFIED entry for it. Tests were
   derived from the delta and `design.md`. Nothing was changed in the
   artifacts.

---

## First-run state, per file

`ai-toolkit:testing`'s four failure states. A pass in the *target-absent*
situation would be an alarm; a pass in the *target-exists* situation is the
expected result. Both occur here and are separated.

| File | State |
|---|---|
| `PD` | **All 15 fail on an absent target** (`AttributeError: 'Product' object has no attribute 'record_hazard_categories'`). State 2 — establishes absence only. |
| `PA` | **Collection error on an absent target** (`ImportError: cannot import name 'record_hazard_categories'`). State 2. |
| `PI` | **Collection error on an absent target**, same import. State 2. |
| `HF` | 7 fail, 16 pass. The failures are state 1 or 2 (the finding is always `None`, and the structural routes do not exist). **The passes are non-discriminating today** — see below. |
| `CN` | 16 fail, 0 pass. State 1/2. |
| `SF` | 2 fail (the `categories` property, and the three-field set), 4 pass. The 4 passes are the unchanged requirement holding over the two-field schema; they become discriminating when the field lands. |
| `LM` | **All 7 pass on first run.** Target-exists situation. `design.md` Decision 8 and `tasks.md` 6.0 say the renderer already behaves this way and that the expected diff to `launch_admin.py` is empty. **Do not edit the renderer to make these look earned.** |
| `DO` | **All 12 fail** — 4 on an absent target (`record_hazard_categories`), 8 on an absent region (`established-by-automation`). |
| `AP` | **All 6 pass on first run.** Target-exists: this change adds no mechanism to the pass. Regression guards on the generic path for a value type it has never carried. |
| `RJ` | 3 fail on an absent target; `test_the_rejection_path_is_given_no_route_to_the_product` passes — target-exists, and it is the guard on an absence. |
| `SR` | 2 fail (no sink for `lp.strategy.006`); `test_the_existing_sink_is_still_registered_beside_it` passes. |

### The passes in `HF` that are non-discriminating today

Recorded honestly rather than counted as coverage. Each asserts that **no**
finding is reported, and today no finding is ever reported, so each passes
vacuously. Each becomes discriminating the moment `tasks.md` 4.5 lands, which
is what they are for:

- `test_an_undetermined_verdict_establishes_nothing` (3 rows)
- `test_an_unreadable_verdict_establishes_nothing`
- `test_a_blank_comment_establishes_nothing` (12 rows)
- `test_a_screen_given_no_product_establishes_nothing`
- `test_a_step_naming_no_categories_establishes_nothing` (3 rows)
- `test_a_prior_flag_survives_a_later_screening_that_establishes_nothing`
- `test_the_finding_names_no_field`
- `test_a_flagged_verdict_naming_nothing_is_not_recorded_as_flagged` — and note
  it passes **for the wrong reason**: today that response routes to the flagged
  reason, which the delta forbids. Its companion
  `test_the_flagged_naming_nothing_reason_is_its_own` fails, and that is the
  row that discriminates.
- `test_a_blank_comment_outranks_a_structural_contradiction` (8 rows) — passes
  because no structural contradiction exists yet to outrank.

### The collection errors, and `pre-commit`

`PA` and `PI` fail at **collection**, which aborts a plain `uv run pytest` run
of the whole tier. That matches how every earlier pass in this repository left
its target-absent tests (see `test_record_sub_category.py`'s own docstring), and
it is why `tasks.md` 1 says these land in the same commit as the implementation.
Until then, use `--continue-on-collection-errors` to read the rest of the tier.

---

## Verification of this pass itself

- `uv run ruff check tests/` → **All checks passed**
- `uv run ruff format --check tests/` → **332 files already formatted**
- `mypy` was **not** run over the new files. Several read
  `product.hazard_categories` and call `Product.record_hazard_categories`,
  neither of which exists yet, so `mypy` reports `attr-defined` until
  `tasks.md` 3.1 lands. That is the same absent-target state the tests are in
  and is not resolved by writing the code under test.
