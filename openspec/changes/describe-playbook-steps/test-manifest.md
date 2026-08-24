# Test manifest — `describe-playbook-steps`

Written by the test-writing pass, from the change's delta specs alone,
before any implementation of this change exists. **This file is not an
artifact the OpenSpec schema knows about**, so it does not appear among
`openspec instructions apply`'s context files and must be read on
purpose, before implementing.

**Two passes, one record.** This manifest replaces the one the first pass
wrote, rather than merging into it: a manifest states the change as it now
stands, and the first pass's version rested on a revision of the delta
specs that no longer holds. Where a statement of the first pass has been
superseded by the current specs, that is said here explicitly rather than
silently dropped.

- **Pass 1** derived tests from the delta specs as they stood on the
  change's first review. Four test files.
- **Pass 2** (this one) derived tests for behaviour the delta specs gained
  across three subsequent review passes — behaviour pass 1 had recorded as
  *unresolved* or *deliberately untested* because no artifact settled it.
  Three further test files.

**Both passes are additive only.** Seven new test files were created. No
existing test was edited, deleted or disabled at any point, and no
implementation code was written or modified by either pass.

---

## Baselines

Per `ai-toolkit:testing`, each pass recorded what already failed before it
wrote anything.

**Pass 1 baseline:** `uv run pytest tests/unit tests/agents` —
**584 passed, 0 failed**.

**Pass 2 baseline:** `uv run pytest tests/unit tests/agents` —
**585 passed, 23 failed**. The 23 are pass 1's own tests, all failing on
the absent `description` field; none lies in pass 2's subject area, so
every pass-2 failure is separately attributable.

**Scope, and why (both passes):** `tests/unit` + `tests/agents` is the tier
`AGENTS.md` runs at commit time, and it is the tier every test written by
either pass lands in. A scoped baseline is a first-class option under
`ai-toolkit:testing`, and this is its scope. **`tests/integration` was not
run**: it needs a live Postgres, which is not available in this
environment. Two integration files
(`tests/integration/launch/test_launch_repository.py`,
`tests/integration/launch/test_launch_clickup_mapping.py`) construct
`StepDefinition` and appear in the compatibility list below; whether they
pass after the change is a claim neither pass can make.

**State after pass 2:** `uv run pytest tests/unit tests/agents` —
**586 passed, 36 failed**. The 36 failures are the two passes' new tests
(23 + 13). The two *new* tests that pass are discussed under
*Two new tests pass on their first run*.

Failure states of the 36, per `ai-toolkit:testing`:

- **34 are state 2 (absent target).** Either
  `TypeError: StepDefinition.__init__() got an unexpected keyword argument
  'description'` / `AttributeError: 'StepDefinition' object has no
  attribute 'description'`, or — for three of pass 2's ClickUp tests —
  `Failed: expected exactly one public integer task-name-limit constant in
  clickup_sync (tasks.md 1.1), found: []`. They establish only that the
  field, or the named constant, is absent. Nothing about whether their
  assertions are any good, because those assertions never executed.
- **2 are state 1 (the code ran and produced a wrong value)**, both from
  pass 1:
  `test_playbook_loader_description.py::test_a_step_omitting_the_description_is_rejected_by_name`
  and `::test_a_missing_description_is_reported_alongside_another_fault`.
  The loader loads a step carrying no `description` key and reports only
  the *other* fault, so these assertions executed and discriminated. That
  is exactly the gap `tasks.md` 2.2 describes.

`uv run mypy .` reports **14 errors, all `"StepDefinition" has no attribute
"description"`** (12 from pass 1, 2 from pass 2) — the same absent-target
fact, clearing when `tasks.md` 2.1 lands. `uv run ruff check` and
`uv run ruff format --check` pass on all seven new files.

---

## Files written

| Pass | File | Covers |
| --- | --- | --- |
| 1 | `tests/unit/launch/domain/test_step_description.py` | the declared `description` attribute and the empty / multi-line coherence rules, at playbook construction |
| 1 | `tests/unit/launch/infrastructure/test_playbook_loader_description.py` | the description key at the file boundary — the *omitted entirely* case only the loader can express |
| 1 | `tests/unit/launch/infrastructure/test_shipped_playbook_descriptions.py` | the shipped `v1` data: every step describes its work, and re-derives from its reference row |
| 1 | `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py` | the composed task name's two parts, the two never-rewrite rules, and that an over-long name is shortened with its body carried |
| 2 | `tests/unit/launch/domain/test_step_description_whitespace.py` | whitespace-only is empty — the clause that settles pass 1's unresolved question 1 |
| 2 | `tests/unit/launch/infrastructure/test_shipped_step_identifier_discipline.py` | a shipped identifier's second segment is its declared discipline — the shipped-set clause added on review |
| 2 | `tests/unit/launch/infrastructure/driven/test_clickup_task_name_composition.py` | the composed name's *exact* shape, the discipline carve-out, the fixed shortened shape and cut point, and no body when the name fits |

Tier placement follows `AGENTS.md`: all seven are fast mocked/data unit
tests mirroring the module/layer path of what they observe.

---

## What pass 2 added, and which pass-1 gap each closes

| Newly specified in the delta | Pass 1 recorded it as | Pass 2 test |
| --- | --- | --- |
| A whitespace-only description is empty (attribute paragraph, coherence bullet, rejection scenario) | unresolved question 1; deliberately untested | `test_step_description_whitespace.py` (all 7) |
| ` · ` is normative in the delta, not only in `design.md` | unresolved question 4; assertion labelled DERIVED | `test_clickup_task_name_composition.py::test_the_composed_name_is_exactly_description_separator_identifier` |
| The name is exactly three parts and no further element; the discipline is not *appended* | asserted as an absence of the discipline word — the wrong form (see obsolete candidate 2) | `::test_the_discipline_is_not_appended_as_a_further_element` |
| That constrains composition, not what a description says | not stated then, so not covered | `::test_a_description_naming_its_own_discipline_is_composed_unaltered` |
| The shortened shape: cut, `…`, ` · `, identifier in full | deliberately untested ("where the shortened name is cut ... the delta requires only that the name fit") | `::test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier` |
| The cut is the longest leading portion the limit allows | not assertable then | `::test_the_shortened_name_surrenders_no_more_than_the_limit_requires` |
| A task whose name fits is created without a body | deliberately untested ("a body written in every case would violate nothing") | `::test_a_task_whose_name_fits_is_created_without_a_body` |
| A shipped identifier's second segment is its declared discipline | not stated then; `design.md` carried it as an observation | `test_shipped_step_identifier_discipline.py::test_every_shipped_identifier_carries_its_discipline_as_its_second_segment` |

The measured limit (2048 characters, ClickUp rejecting rather than
truncating, applied as Python `len()` characters — `design.md` Decision 4)
did **not** become a hard-coded number in any test. Both passes read the
limit from the implementation's own named constant by shape, because
`tasks.md` 1.1 fixes the number but no artifact fixes the constant's name
(unresolved question 3, still open).

---

## Scenario accounting

**30 scenarios in the current delta specs; 30 accounted for below.** Test
names are runner-selectable node IDs (`uv run pytest <path>::<name>`).

### `launch-playbook` — Requirement: A step definition declares how it is to be resolved (MODIFIED)

| Scenario | Covered by |
| --- | --- |
| A step definition is read back with every declared attribute | **pass 1** `tests/unit/launch/domain/test_step_description.py::test_a_step_definition_reads_back_its_description`; `::test_the_description_is_not_the_identifier`; `tests/unit/launch/infrastructure/test_playbook_loader_description.py::test_a_described_playbook_file_loads_and_reads_its_descriptions_back`. The "present only if authored" half is unchanged by this delta and stays with existing `tests/unit/launch/domain/test_launch_playbook.py::test_unauthored_optional_attributes_are_absent`. |
| Steps can be selected by gate and by scope | existing `tests/unit/launch/domain/test_launch_playbook.py::test_steps_can_be_selected_by_gate_and_by_scope`. **No new test**: the delta leaves this scenario's text unchanged and adds nothing a selection query observes. |

### `launch-playbook` — Requirement: The shipped playbook carries the authored step set (MODIFIED)

| Scenario | Covered by |
| --- | --- |
| The shipped playbook loads with steps | existing `tests/unit/launch/infrastructure/test_shipped_playbook_steps.py::test_the_shipped_playbook_loads_with_a_non_empty_step_list`, `::test_every_gate_has_at_least_one_step_attached`. Unchanged text; no new test. |
| BUILD THE LISTING is fully represented | existing `test_shipped_playbook_steps.py::test_build_the_listing_is_fully_represented`. Unchanged text; no new test. |
| A step traces to its source row | first two THENs: existing `test_shipped_playbook_steps.py::test_every_step_identifier_is_a_reference_row_id`, `::test_every_step_provenance_carries_its_row_source_citation`. **The third THEN is new to this revision** ("AND the second segment of that identifier is the step's declared discipline") and is covered by **pass 2** `tests/unit/launch/infrastructure/test_shipped_step_identifier_discipline.py::test_every_shipped_identifier_carries_its_discipline_as_its_second_segment`. |
| A step states its work without the source document | **pass 1** `tests/unit/launch/infrastructure/test_shipped_playbook_descriptions.py::test_every_shipped_step_states_its_work` |
| Every description re-derives from its reference row | **pass 1** `test_shipped_playbook_descriptions.py::test_every_description_re_derives_from_its_reference_row`, with two guards: `::test_the_trimming_rule_is_actually_exercised_by_the_shipped_set`, `::test_content_terminal_characters_survive_transcription` |
| A gate-authored condition is not duplicated as a step | existing `test_shipped_playbook_steps.py::test_metric_condition_restatements_do_not_appear_as_steps`. Unchanged text; no new test. |

The requirement's prose also states that a description "occupies a single
line" as a property of the shipped set, which no scenario states on its
own: **pass 1**
`test_shipped_playbook_descriptions.py::test_every_shipped_description_occupies_a_single_line`.

### `launch-playbook` — Requirement: An incoherent playbook is rejected at load time (MODIFIED)

| Scenario | Covered by |
| --- | --- |
| Gate sequence deviates from the specification | existing `test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`, `::test_gate_sequence_with_an_extra_gate_is_rejected`, `::test_gate_sequence_in_the_wrong_order_is_rejected`, `::test_gate_sequence_repeating_a_position_is_rejected`. Unchanged rule; no new test. |
| A gate's opening mode disagrees with the specification | existing `test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected`. Unchanged rule; no new test. |
| Duplicate step identifier | existing `test_launch_playbook.py::test_duplicate_step_identifier_is_rejected`. Unchanged rule; no new test. |
| Step references an unknown gate | existing `test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected`. Unchanged rule; no new test. |
| A step with no description is rejected by name | Split by the three spellings the scenario now names. **Empty** — **pass 1** `test_step_description.py::test_a_step_with_an_empty_description_is_rejected_by_name`. **Whitespace-only** (new to this revision) — **pass 2** `test_step_description_whitespace.py::test_a_whitespace_only_description_is_rejected_by_name` (4 parametrisations: `single-space`, `several-spaces`, `tab`, `mixed-horizontal`). **Omitted entirely** — **pass 1** `test_playbook_loader_description.py::test_a_step_omitting_the_description_is_rejected_by_name`. The "same aggregated report" clause — **pass 1** `test_playbook_loader_description.py::test_a_missing_description_is_reported_alongside_another_fault`, `test_step_description.py::test_a_description_fault_is_aggregated_with_another_fault`; **pass 2** `test_step_description_whitespace.py::test_a_whitespace_only_description_fault_is_aggregated_with_another_fault`. The rule's placement (`design.md` Decision 1) — **pass 1** `test_step_description.py::test_an_empty_description_is_rejected_by_the_playbook_not_the_step`; **pass 2** `test_step_description_whitespace.py::test_a_whitespace_only_description_is_rejected_by_the_playbook_not_the_step`. The permitted side — **pass 2** `test_step_description_whitespace.py::test_a_description_that_merely_contains_whitespace_is_accepted`. |
| A description spanning several lines is rejected | **pass 1** `test_step_description.py::test_a_description_spanning_several_lines_is_rejected` (2 parametrisations: embedded `\n`, embedded `\r\n`) and `::test_a_multi_line_description_fault_is_aggregated_with_another_fault` |
| Automation without a decided rule | existing `test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected`, `::test_ai_assisted_step_without_a_rule_policy_is_rejected`, `::test_automated_step_with_a_rule_policy_is_accepted`. Unchanged rule; no new test. |
| A prohibited tactic cannot block a gate | existing `test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`, `::test_prohibited_tactic_that_does_not_block_is_accepted`. Unchanged rule; no new test. |
| A lesson cannot block a gate | existing `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_lesson_step_marked_blocking_is_rejected`, `::test_a_non_blocking_lesson_step_is_accepted`. Unchanged rule; no new test. |
| A malformed metric condition is rejected | existing `test_playbook_coherence_completion.py::test_a_metric_condition_with_an_empty_threshold_is_rejected`. Unchanged rule; no new test. |
| Multiple violations are reported together | existing `test_launch_playbook.py::test_two_distinct_violations_are_reported_together`, `test_playbook_coherence_completion.py::test_the_two_new_faults_are_reported_together`, extended over this change's faults by **pass 1** `test_step_description.py::test_a_description_fault_is_aggregated_with_another_fault`, `::test_a_multi_line_description_fault_is_aggregated_with_another_fault` and **pass 2** `test_step_description_whitespace.py::test_a_whitespace_only_description_fault_is_aggregated_with_another_fault` |
| A malformed step is reported alongside a coherence violation | existing `tests/unit/launch/infrastructure/test_playbook_loader.py::test_malformed_step_is_reported_alongside_a_coherence_violation`. Unchanged rule; no new test — but see the compatibility list: its fixture needs the new key. |
| A coherent playbook loads | existing `test_launch_playbook.py::test_a_coherent_playbook_loads`, `test_playbook_loader.py::test_a_coherent_playbook_file_loads`, `test_playbook_coherence_completion.py::test_a_coherent_playbook_with_the_completed_surface_loads`, extended over the new field by **pass 1** `test_step_description.py::test_a_single_line_description_is_accepted`, `test_playbook_loader_description.py::test_a_described_playbook_file_loads_and_reads_its_descriptions_back` and **pass 2** `test_step_description_whitespace.py::test_a_description_that_merely_contains_whitespace_is_accepted` |

### `launch-clickup-sync` — Requirement: Human-attested steps are projected as tasks (MODIFIED)

| Scenario | Covered by |
| --- | --- |
| A human-attested step gets a task | First THEN, as revised: **pass 2** `tests/unit/launch/infrastructure/driven/test_clickup_task_name_composition.py::test_the_composed_name_is_exactly_description_separator_identifier` (the whole-string equality the revised delta now fixes), with **pass 1** `test_clickup_task_naming.py::test_a_projected_task_is_named_description_then_identifier` covering the parts-and-order form and the list placement. Second THEN (the discipline is not appended): **pass 2** `::test_the_discipline_is_not_appended_as_a_further_element`, with the carve-out at `::test_a_description_naming_its_own_discipline_is_composed_unaltered`. Third THEN (the association is recorded): **pass 1** `test_clickup_task_naming.py::test_a_projected_task_is_named_description_then_identifier` and existing `test_clickup_sync_projection.py::test_a_human_attested_step_gets_a_task`. |
| A renamed task still resolves to its step | **pass 1** `test_clickup_task_naming.py::test_a_renamed_task_still_resolves_to_its_step` |
| An edited task name is never restored | **pass 1** `test_clickup_task_naming.py::test_an_edited_task_name_is_never_restored` |
| An over-long name is shortened rather than failing | First THEN (shortened, fitting, ending `… · <identifier>`): **pass 2** `test_clickup_task_name_composition.py::test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier`. Second THEN (no more surrendered than required): **pass 2** `::test_the_shortened_name_surrenders_no_more_than_the_limit_requires`. Third THEN (the full description is in the body): **pass 1** `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`. Permitted side: **pass 1** `::test_a_name_within_the_limit_is_not_shortened`, plus the body clause at **pass 2** `test_clickup_task_name_composition.py::test_a_task_whose_name_fits_is_created_without_a_body`. |
| An existing task is not recreated | existing `test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated`. Unchanged text; no new test. |
| A prohibited-tactic step is never projected | existing `test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected`. Unchanged text; no new test. |
| A deleted task for unfinished work is re-projected | existing `test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected`. Unchanged text; no new test. |
| A deleted task for finished work stays gone | existing `test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone`. Unchanged text; no new test. |
| Automated and ai-assisted steps are never projected | existing `test_clickup_sync_projection.py::test_automated_and_ai_assisted_steps_are_never_projected`. Unchanged text; no new test. |

---

## Assertion provenance

Each new test carries its classification inline, at the assertion site.
Summarised across both passes.

### Specified — traces to a SHALL or a scenario THEN of the delta specs

- the description is present on a read-back step, and non-empty
- an empty description is rejected, naming the step
- **a whitespace-only description is rejected, naming the step** (pass 2 —
  SPECIFIED as of this revision; pass 1 could not classify it at all)
- **a description that merely contains whitespace is accepted** (pass 2 —
  the permitted side of "consisting *only* of whitespace")
- an absent description key is rejected, naming the step, aggregated
- a multi-line description is rejected, naming the step
- a single-line description loads (the permitted side of both rules)
- every shipped description is non-empty and single-line
- every shipped description equals its reference row's trimmed text
  exactly, with the trimming rule applied as the delta states it
- **every shipped identifier's second segment is its declared discipline**
  (pass 2 — a new normative clause of the shipped-set requirement, and a
  new THEN on *A step traces to its source row*)
- **the composed task name equals `<description> · <identifier>` exactly**
  (pass 2 — the separator is now normative in the delta, and the name
  "SHALL consist of exactly those three parts and no further element")
- **the discipline is not appended as a further element** (pass 2 —
  asserted through that equality, deliberately not as an absence; see
  below)
- **a description whose own wording names its discipline is composed
  unaltered** (pass 2 — the delta's explicit carve-out)
- a mapped task resolves through the recorded mapping, not the name, and a
  renamed task produces no duplicate
- no name-bearing write is sent for a mapped task
- an over-long composed name is shortened to fit and keeps the identifier,
  and the full description reaches the created task's body
- **the shortened name is the cut description, then `…`, then ` · `, then
  the identifier in full** (pass 2)
- **the cut is the longest leading portion that still fits** (pass 2)
- **a task whose name fits is created without a body** (pass 2)

### Specified by a change artifact other than the delta

Named at each site, so a later artifact change supersedes them visibly.

- the rule's *placement* — playbook coherence, not `StepDefinition`
  construction (`design.md` Decision 1), asserted for both the empty and
  the whitespace-only spelling
- the description is not derived from the identifier (`design.md`
  Decision 1 rejects that fallback by name)
- the trimming rule's closed set and the content characters it must not
  eat (`design.md` Decision 3)
- the limit is applied as Python `len()` characters (`design.md`
  Decision 4), and lives in `clickup_sync.py` as a named constant
  (`tasks.md` 1.1)

**Moved out of this section by pass 2:** the separator ` · ` and "the
discipline drops out of the name" were classified here by pass 1, on
`design.md` Decision 4 and `proposal.md`. Both are now stated in the
`launch-clickup-sync` delta itself and are classified **Specified** above.

### Derived — inferred, with no stated requirement fixing them

- the field is named `description` and is passed as a keyword argument
- the YAML key is `description` (named by `tasks.md` 2.2; the document
  shape itself is inherited from `test_playbook_loader.py`, which records
  it as invented)
- the reference document's row grammar — a row's text is the markdown list
  item on the line above its `**ID:**` metadata line
- **that an identifier's segments are dot-separated** (pass 2 — the delta
  names the segments only through its example `lp.creative.008`)
- `converge_launch`'s call shape and the ClickUp/mapping port method
  names, inherited from `test_clickup_sync_projection.py`, which records
  them as invented
- the task body reaches ClickUp as `create_task`'s `description` argument
- **"without a body" is asserted as falsy rather than as `is None`** (pass
  2 — no artifact distinguishes an omitted argument from an empty one, so
  the weaker assertion is the faithful one)
- both `\n` and `\r\n` count as "spanning more than one line"

### Deliberately untested — identified and knowingly left uncovered

Recorded at the foot of each new test file as well as here.

- a description ending in a trailing newline but otherwise one line (see
  unresolved question 2)
- a description of only *vertical* whitespace (`"\n"`): it satisfies two
  rejection rules at once and the delta does not say which reports it, so
  an assertion would discriminate nothing
- whether the loader stores a padded description as authored or stripped
- Unicode whitespace outside the ASCII set
- a whitespace-only description supplied through the *file* boundary — the
  rule lives in the domain (`tasks.md` 2.1) and a loader test would
  re-observe it one layer out
- any maximum length on the description itself — the delta places the
  length concern on the composed task name
- a cut point landing on whitespace: whether the retained portion keeps or
  trims its trailing space before the `…` (see unresolved question 7)
- whether the limit is characters, bytes or UTF-16 units — `design.md`
  Decision 4 states honestly that its ladder was ASCII-only; the tests
  read the same `len()` unit and so cannot independently establish it
- that ClickUp *rejects* rather than truncates (`HTTP 400`, `INPUT_005`) —
  a fact about the live platform, measured under `tasks.md` 1.1, which a
  fake cannot re-establish
- the identifier's first and third segments
- that the identifier/discipline agreement holds for a *hand-authored*
  playbook — the requirement states it of the shipped authored set, and
  the load-time coherence rules deliberately do not include it
- the wording of any error message — only that it names the step
- the census of shipped descriptions (97) and any individual wording
- `lp.rank.003`, which `design.md` Decision 3 records as reading badly
  under any rule; the equality assertion covers it like any other row

**No longer in this section:** pass 1 listed "a whitespace-only
description", "where the shortened name is cut, and whether an ellipsis
marks it", and "whether a task body is written when the name already
fits". All three are now specified and all three are covered by pass 2.
The superseded footnotes stating them still stand in pass 1's files, which
this pass did not edit — see *Superseded annotations* below.

---

## Two new tests pass on their first run

Two of the 38 tests pass immediately. `ai-toolkit:testing`
classes a first-run pass as an alarm, so each was investigated rather than
recorded as coverage.

**Pass 1 —
`test_shipped_playbook_descriptions.py::test_the_trimming_rule_is_actually_exercised_by_the_shipped_set`.**
A **guard on the fixture**, not a scenario test: it asserts that at least
one shipped step identifier names a reference row whose text ends in a
terminal mark — a property of the reference document and the existing step
set, both of which already exist. Its purpose is to stop the re-derivation
test from holding vacuously. It asserts nothing about the `description`
field and is not counted as covering any scenario.

**Pass 2 —
`test_shipped_step_identifier_discipline.py::test_every_shipped_identifier_carries_its_discipline_as_its_second_segment`.**
This passes now, and that is the **correct** result rather than an alarm.
`ai-toolkit:testing`'s alarm covers a test written against a target that
does not exist yet; this test's target exists — the shipped
`playbook_v1.yaml` already carries all 97 identifiers and disciplines, and
`design.md` Decision 4 records the property as verified across them on
2026-08-24. In the *existing-target* situation a first-run pass is the
expected result and establishes that the code (here, the data) currently
behaves as asserted. Its value is forward-looking: this change rewrites all
97 of those rows to add descriptions, and `design.md` Decision 4's
justification for dropping the discipline from the task name rests entirely
on this property continuing to hold. `tasks.md` 3.3 asks for exactly this
assertion "rather than left as an observation".

---

## Obsolete tests

The change carries `MODIFIED` deltas, so this list is applicable. Every
entry is a **candidate for human confirmation, not a conclusion**, and
nothing here was edited, deleted or disabled by either pass.

**Search bound:** `tests/**/test_*.py` — the dispatched glob — and nothing
else. No earlier `test-manifest.md` from an archived change was supplied to
either pass, so no external scenario-to-test index was available; the
search matched on assertion text, test and fixture names, and referenced
behaviour. Pass 2 additionally treated pass 1's four files as ordinary
existing tests, which is where candidates 2–4 come from.

### Candidate 1 — a pre-existing test whose recorded provenance is superseded

- **Test:** `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_human_attested_step_gets_a_task`
- **Superseded by:** `launch-clickup-sync` delta, Requirement *Human-attested
  steps are projected as tasks* — "a task named for the step" becomes "a
  task named with the step's description, then ` · `, then the step's
  identifier".
- **Evidence:** the test asserts `"listing.title-conforms" in
  created[0]["name"]` under the comment *"SPECIFIED: named for the step.
  DERIVED: 'named for the step' is read as the step's identifier being
  recoverable from the name; no artifact fixes a title format"*. The delta
  now fixes the format, so the recorded derivation is superseded.
- **Important:** the **assertion itself is not contradicted** — the
  identifier is still in the composed name, and the test should still pass
  after the change. What is obsolete is its stated provenance, not its
  expectation. Deleting it would lose the list-placement and association
  coverage it also carries. The recommended action is to update the
  comment, not the assertion — the confirming human's call, not this
  pass's.

### Candidate 2 — a pass-1 test whose assertion *form* the revised delta forecloses

- **Test:** `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_the_discipline_does_not_appear_in_the_task_name`
- **Superseded by:** `launch-clickup-sync` delta, Requirement *Human-attested
  steps are projected as tasks* — "Before any shortening under the rule
  below, the name SHALL consist of exactly those three parts and no further
  element: the step's discipline SHALL NOT be appended as a further element
  of the name. ... **This constrains what the system composes, not what a
  description happens to say — a description whose own wording mentions its
  discipline is unaffected.**"
- **Evidence:** the test's operative assertion is
  `assert "ppc" not in created[0]["name"].lower()` — an assertion that the
  discipline *word* is absent from the name string. The delta's carve-out
  says exactly this is not the rule: a conformant name may contain the
  discipline word, because the description may. The test was written before
  that sentence existed, when `proposal.md`'s "the discipline drops out of
  the task name" was all there was.
- **Why it still passes today's fixture:** its step's description and
  identifier happen to contain no "ppc", so the absence follows from
  correct composition. It is the *form* that is superseded, not the
  observed value — the test would reject a conformant implementation for a
  step whose wording mentions its own discipline.
- **Replacement already written, additively:**
  `test_clickup_task_name_composition.py::test_the_discipline_is_not_appended_as_a_further_element`
  asserts the same clause as a whole-string equality, and
  `::test_a_description_naming_its_own_discipline_is_composed_unaltered`
  covers the carve-out. **Candidate for human confirmation:** the
  recommended action is to remove the superseded absence assertion now that
  the compositional one exists — a destructive edit this pass did not and
  will not make.

### Candidate 3 — a pass-1 test whose provenance label is superseded

- **Test:** `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_the_composed_name_uses_the_authored_separator`
- **Superseded by:** the same requirement — ` · ` is now stated in the delta
  ("then ` · ` (a space, a middle dot, a space)"), not only in `design.md`
  Decision 4.
- **Evidence:** the test's docstring reads "DERIVED from `design.md`
  Decision 4 ... this is the one assertion in the file that a change of
  separator would legitimately supersede". Its assertion —
  `created[0]["name"] == f"{STEP_DESCRIPTION}{SEPARATOR}{STEP_ID}"` — is
  **unchanged and now SPECIFIED**.
- **Recommended action:** update the docstring's classification only. The
  assertion is correct and is duplicated deliberately by pass 2's
  `test_the_composed_name_is_exactly_description_separator_identifier`,
  which carries the specified label.

### Candidate 4 — a pass-1 test whose docstring cites a superseded measurement

- **Test:** `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`
- **Superseded by:** `design.md` Decision 4 as revised — the limit is
  **measured** at 2048 characters with ClickUp rejecting rather than
  truncating, where the earlier text said "believed to be 255 ... the rule
  holds whatever the number turns out to be".
- **Evidence:** the docstring quotes that earlier wording verbatim.
- **The assertions are not contradicted** — the test reads the limit from
  the implementation's constant rather than hard-coding it, which is
  exactly why it survives the measurement. **Recommended action:** update
  the quotation. Its "DELIBERATELY UNTESTED" footnote is separately
  superseded — see below.

### Superseded annotations, not tests

These are comments and footnotes, not runner-selectable tests, so they are
not obsolete *tests* — but they now state the opposite of the specs and
would mislead the next reader. Listed for the same confirming human.

- `tests/unit/launch/domain/test_step_description.py`, foot of file: "A
  whitespace-only description ... whether whitespace-only counts as empty
  is not stated anywhere in the change's artifacts". The delta now states
  it, three times, and `test_step_description_whitespace.py` covers it.
- `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py`,
  foot of file: "*Where* the shortened name is cut, and whether an ellipsis
  marks it. The delta requires only that the name fit and keep the
  identifier" — the delta now fixes both. And "Whether the task body is set
  for a step whose name already fits ... a body written in every case would
  violate nothing" — the delta now forbids it.
- The same file's module docstring says "`design.md` Decision 4 leaves the
  number itself to be confirmed" — it no longer does.

### No further candidate found — stated explicitly

No other existing test was found asserting behaviour the three `MODIFIED`
`launch-playbook` requirements or the `MODIFIED` `launch-clickup-sync`
requirement supersede. Specifically:

- No existing test asserts that a step **without** a description is valid,
  or that a playbook lacking descriptions loads *because* they are absent.
  Existing playbooks load without descriptions only because the field does
  not exist yet — an absence of coverage, not an assertion.
- No existing test asserts anything about the shipped set's descriptions.
- No existing test asserts that a shipped identifier's second segment is
  *unconstrained*, or contradicts the discipline clause pass 2 covers.

**This is "none was found by this search", not "no such test exists."** The
bound above is real: with no requirement-to-test index and no
implementation read, a test asserting superseded behaviour under a name
mentioning neither descriptions nor task names would not have surfaced.

### Not obsolete, but incompatible — the implementer's own list

These existing tests are **not** superseded: they assert behaviour this
change leaves standing. They will nonetheless stop constructing a valid
`StepDefinition` once `description` becomes required, and `tasks.md` 2.3
already names the work. Listed so the implementer does not mistake a
compatibility failure for a superseded assertion, and so no assertion is
weakened while making them build again. **Neither pass touched any of
them** — the additive-only rule binds regardless of how mechanical the edit
is.

Sixteen files carrying a `_step(**overrides)` factory or a direct
`StepDefinition(...)` construction:

- `tests/unit/launch/domain/test_launch_playbook.py`
- `tests/unit/launch/domain/test_playbook_coherence_completion.py`
- `tests/unit/launch/domain/test_step_definition_discipline.py`
- `tests/unit/launch/domain/test_gate_conditions.py`
- `tests/unit/launch/domain/test_launch_dates.py`
- `tests/unit/launch/domain/test_launch_gate_advance.py`
- `tests/unit/launch/domain/test_launch_run.py`
- `tests/unit/launch/application/test_launch_reports.py`
- `tests/unit/launch/application/test_scope_aware_launch_reads.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py`
- `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`
- `tests/unit/briefing/application/test_briefing_assembly.py`
- `tests/unit/briefing/application/test_briefing_delivery.py`
- `tests/integration/launch/test_launch_repository.py`
- `tests/integration/launch/test_launch_clickup_mapping.py`

Two raw-YAML fixtures supplying a step as a mapping rather than through the
dataclass (both named by `tasks.md` 2.3):

- `_TWO_FAULTY_STEPS_YAML` in
  `tests/unit/launch/infrastructure/test_playbook_loader.py` — after the
  change its two steps each gain a *third* fault (no description); its
  assertions name both existing faults and would still hold, but the
  fixture no longer isolates what it was built to isolate.
- the raw playbook text in
  `tests/unit/launch/application/test_report_undecided_rule_policies.py`
  (two documents, four steps).

---

## Unresolved project questions

Recorded rather than assumed, per this project's conventions
(`AGENTS.md`: "Do not silently invent a requirement that was not stated";
"where an important decision cannot be inferred, ask rather than guess").
Both passes ran non-interactively with no channel to ask on, so each is
recorded with the assumption taken and the tests depending on it.

**Settled since pass 1 — kept for the record, no longer open:**

1. ~~Does a whitespace-only description count as empty?~~ **Settled by the
   delta**: "a description consisting only of whitespace SHALL be treated
   as empty", stated in the attribute paragraph, the coherence bullet and
   the rejection scenario. Pass 2 covers it in
   `tests/unit/launch/domain/test_step_description_whitespace.py`.
4. ~~Is the composed separator ` · `?~~ **Settled by the delta**: "then
   ` · ` (a space, a middle dot, a space)". Now SPECIFIED rather than
   derived from `design.md`.

**Still open:**

2. **Does a trailing newline make a description span more than one line?**
   No artifact says. *Assumption taken:* none — only an *embedded* break is
   tested. *Tests depending on it:* none.
3. **What is the task-name limit constant called?** The *number* is settled
   (`tasks.md` 1.1, `design.md` Decision 4: 2048 characters, applied as
   Python `len()`), but no artifact fixes the constant's **name**.
   *Assumption taken:* `clickup_sync` exposes exactly one public,
   module-level, non-boolean integer constant whose name contains "NAME",
   and `_task_name_limit()` reads it. *Tests depending on it:*
   `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`,
   `::test_a_name_within_the_limit_is_not_shortened`;
   `test_clickup_task_name_composition.py::test_a_task_whose_name_fits_is_created_without_a_body`,
   `::test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier`,
   `::test_the_shortened_name_surrenders_no_more_than_the_limit_requires`.
   All fail today with a message naming `tasks.md` 1.1 rather than a wrong
   number; **none hard-codes 2048**.
5. **How does the full description reach the task body?**
   `create_task(list_id, name, description=None)` is the shape
   `tests/unit/shared/infrastructure/driven/test_clickup_client.py`
   records. *Assumption taken:* the body is that `description` argument.
   *Tests depending on it:*
   `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`;
   `test_clickup_task_name_composition.py::test_a_task_whose_name_fits_is_created_without_a_body`.
6. **`converge_launch`'s call shape and the port method names.** Inherited
   unchanged from `test_clickup_sync_projection.py`, which records them as
   invented. *Tests depending on it:* every test in
   `test_clickup_task_naming.py` and
   `test_clickup_task_name_composition.py`; `_converge()` is the single
   correction point in each file.
7. **Does a cut landing on whitespace keep or trim the trailing space
   before the `…`?** (New in pass 2.) The delta fixes the cut as "the
   longest leading portion that leaves the whole composed name within the
   limit" but says nothing about a boundary falling on a space.
   *Assumption taken:* none — `_long_description()` is built so the cut
   point falls mid-word, so no test asserts an answer either way. *Tests
   depending on it:* none; the fixture avoids the case deliberately.

Correcting any of (3), (5) or (6) to match what is implemented is a
**fixture correction** (failure state 3 in `ai-toolkit:testing`). Changing
what these tests assert about the resulting name, body or rejection would
be **weakening them**, and is not a correction.

---

## What the implementation must make pass

```
uv run pytest \
  tests/unit/launch/domain/test_step_description.py \
  tests/unit/launch/domain/test_step_description_whitespace.py \
  tests/unit/launch/infrastructure/test_playbook_loader_description.py \
  tests/unit/launch/infrastructure/test_shipped_playbook_descriptions.py \
  tests/unit/launch/infrastructure/test_shipped_step_identifier_discipline.py \
  tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py \
  tests/unit/launch/infrastructure/driven/test_clickup_task_name_composition.py
```

**38 tests, of which 36 fail today.** The two that pass are the two
first-run passes discussed above — pass 1's trimming-rule fixture guard and
pass 2's shipped identifier/discipline test. Both must still pass after all
97 rows are rewritten.

Mapped to `tasks.md`:

- **1.1** → `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`
  and every limit-reading test in `test_clickup_task_name_composition.py`
  (the named constant is what `_task_name_limit()` locates)
- **2.1** → `test_step_description.py` (all) and
  `test_step_description_whitespace.py` (all). The whitespace file is what
  makes the task's own warning enforceable: "a bare `if not description` is
  not enough".
- **2.2** → `test_playbook_loader_description.py` (all)
- **2.3** → no test of either pass; it is the compatibility list above
- **3.1–3.2** → `test_shipped_playbook_descriptions.py` (all)
- **3.3** → `test_shipped_step_identifier_discipline.py::test_every_shipped_identifier_carries_its_discipline_as_its_second_segment`
  is the assertion this task asks for; the coherence half of the task is
  covered by `test_shipped_playbook_descriptions.py`
- **4.1** → `test_clickup_task_name_composition.py::test_the_composed_name_is_exactly_description_separator_identifier`,
  `::test_the_discipline_is_not_appended_as_a_further_element`,
  `::test_a_description_naming_its_own_discipline_is_composed_unaltered`;
  `test_clickup_task_naming.py::test_a_projected_task_is_named_description_then_identifier`,
  `::test_the_composed_name_uses_the_authored_separator`
- **4.2** → `test_clickup_task_name_composition.py::test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier`,
  `::test_the_shortened_name_surrenders_no_more_than_the_limit_requires`,
  `::test_a_task_whose_name_fits_is_created_without_a_body`;
  `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`,
  `::test_a_name_within_the_limit_is_not_shortened`,
  `::test_an_edited_task_name_is_never_restored`,
  `::test_a_renamed_task_still_resolves_to_its_step`
- **5.1** → satisfied by both passes' files taken together
