# Test manifest — `separate-the-result-from-the-comment`

Written before any implementation, from this change's delta specs, by an
author who has not read an implementation of the behaviour under test.
It accounts for **every** `#### Scenario:` block in the three delta specs
— 28 of them — exactly once.

Not an artifact the OpenSpec schema knows about: it will not appear among
`openspec instructions apply`'s context files and must be read on
purpose, before implementing.

- **Change root**: `openspec/changes/separate-the-result-from-the-comment/`
- **Approved plan committed at**: `9d0ba21`
- **Test command**: `uv run pytest`
- **Test-path glob**: `tests/**/test_*.py`
- **Files written**: 8, all new. Nothing existing was edited, deleted or
  disabled. This pass adds tests and never subtracts.

## Baseline

Taken at this worktree root on 2026-09-03, before any test below was
written, at commit `9d0ba21`:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 2167 passed, 0 failed, 0 skipped |
| `uv run pytest tests/integration` | 137 passed, 0 failed, **0 skipped** |

The integration tier genuinely ran, against this worktree's seeded
`commerce_ops_screen_test` database — not a skipped tier reporting green
(`AGENTS.md`, *Working in a git worktree*).

**After this pass** (same commands, same worktree):

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 2185 passed, 56 failed, 12 errors |
| `uv run pytest tests/integration` | 137 passed, 11 failed, 0 skipped |
| `uv run mypy .` | Success, 485 source files |
| `uv run ruff check` / `ruff format --check` | clean |

Every failure and error is in one of the eight new files. **No
pre-existing test changed state**, verified by filtering the failure list
against the new filenames. The 18 newly-*passing* tests are the ones
whose behaviour already exists — see *First-run state*, below.

Note for whoever runs `uv run mypy .` next: a **stale `.mypy_cache` in
this worktree reported 52 spurious errors** at the baseline commit. `rm
-rf .mypy_cache` cleared them and the run is clean. Not a defect in the
change, but it will read as one.

## Files written

| File | Tier | Scenarios |
| --- | --- | --- |
| `tests/unit/launch/domain/test_recorded_finding.py` | unit / domain | launch-instance 1, 3, 4, 5, 7, 8 |
| `tests/unit/launch/application/test_launch_report_carried_finding.py` | unit / application | launch-instance 2 |
| `tests/unit/launch/infrastructure/driven/test_launch_progress_finding_rows.py` | unit / infrastructure | launch-instance 4, 5, 6, 9 |
| `tests/unit/launch/infrastructure/driving/test_automation_pass_kept_finding.py` | unit / infrastructure | automation 1, 2 (store half), 6, 7, 8, 9, 10, 11 |
| `tests/unit/launch/application/test_accepted_result_carried_finding.py` | unit / application | automation 2 (accept half), 3, 4, 5 |
| `tests/unit/launch/test_confirmable_finding_end_to_end.py` | unit / launch | automation 2, 4 (end to end) |
| `tests/unit/launch/infrastructure/driving/test_launch_detail_finding_rendering.py` | unit / infrastructure | launch-admin 1–8 |
| `tests/integration/launch/test_carried_finding_columns_live.py` | integration | launch-instance 4, 5, 6, 9; automation 2 (storage half); plus the migration itself |

97 tests collected across the eight files.

### Tier placement, and one deviation from `tasks.md`

`tasks.md` 1.5 (*An unreadable stored finding does not fail the read*) is
grouped under `tests/unit/launch/domain/`. It is written at the **row
mapping** instead — `tests/unit/launch/infrastructure/driven/`. Reason:
the domain carries no *stored* representation that can be unreadable and
no *read* that could fail, and `tasks.md` 2.8 assigns both obligations to
"Both repositories and their row mappings". Per `ai-toolkit:testing`'s
level rule, the row mapping is the smallest unit that can observe either.
Nothing was dropped; the coverage moved one directory.

`tasks.md` 1.8 is written under `tests/unit/launch/application/` rather
than the `tests/unit/launch/` the dispatch named, because that is where
the report use case's existing tests live and `tests/unit/launch/` is its
parent.

## Scenario accounting — all 28

Every test below is named in a form `uv run pytest` can select
individually: `<path>::<test>`, with `[param]` where parametrised.

### `launch-instance` — *A recording may carry the finding that produced it* (9)

Path prefix for this section: `tests/unit/launch/`.

**1. A recording carries the finding that produced it**
- `domain/test_recorded_finding.py::test_a_recording_carries_the_finding_that_produced_it`

**2. A carried finding reaches the launch report**
- `application/test_launch_report_carried_finding.py::test_a_carried_finding_reaches_the_launch_report`
- `application/test_launch_report_carried_finding.py::test_the_finding_reaches_the_entry_the_recording_belongs_to`
- `application/test_launch_report_carried_finding.py::test_an_unrecorded_step_entry_carries_no_finding`

**3. A recording made with no finding carries none**
- `domain/test_recorded_finding.py::test_a_recording_made_with_no_finding_carries_none`
- `domain/test_recorded_finding.py::test_the_outcome_and_provenance_match_a_recording_that_carries_one`

**4. An absent finding is distinguishable from an empty value** — the
assertion the whole change turns on, asserted at four boundaries
- `domain/test_recorded_finding.py::test_an_absent_finding_is_distinguishable_from_an_empty_value[list]`
- `…[text]` · `…[tuple]` · `…[map]`
- `domain/test_recorded_finding.py::test_a_finding_whose_value_is_null_is_not_a_present_finding`
- `domain/test_recorded_finding.py::test_a_finding_whose_value_is_absent_is_not_a_present_finding`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_a_stored_empty_value_is_not_a_null_column`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_an_empty_value_round_trips_as_a_present_finding`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_a_recording_carrying_nothing_writes_a_null_column`
- `infrastructure/driving/test_launch_detail_finding_rendering.py::test_an_empty_value_is_distinguishable_from_no_finding_at_all`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_an_empty_value_round_trips_and_is_not_null`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_a_recording_carrying_nothing_persists_null`
- `tests/unit/launch/test_confirmable_finding_end_to_end.py::test_an_empty_value_survives_the_wait_as_a_finding`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_a_pending_results_empty_value_is_not_null`
- `application/test_accepted_result_carried_finding.py::test_a_stored_empty_value_reaches_the_recording_as_a_finding[list]` · `[text]` · `[map]`

**5. A finding with no comment is carried as such**
- `domain/test_recorded_finding.py::test_a_finding_with_no_comment_is_carried_as_such`
- `domain/test_recorded_finding.py::test_an_absent_comment_is_distinct_from_an_empty_one`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_an_absent_comment_survives_the_row_as_absent`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_an_empty_comment_survives_the_row_as_empty`
- `application/test_accepted_result_carried_finding.py::test_a_stored_absent_comment_reaches_the_recording_as_absent`
- `application/test_accepted_result_carried_finding.py::test_a_stored_empty_comment_reaches_the_recording_as_empty`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_an_absent_comment_survives_postgres_as_absent`

**6. An unreadable stored finding does not fail the read**
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_an_unreadable_stored_finding_does_not_fail_the_read[bare-string]` · `[number]` · `[boolean]` · `[array]` · `[empty-object]` · `[no-field]` · `[no-value]` · `[null-value]` · `[null-field]`
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_an_unreadable_row_does_not_deny_a_readable_one`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_an_unreadable_stored_finding_does_not_fail_a_live_read`

**7. Evidence is unchanged by what is carried beside it**
- `domain/test_recorded_finding.py::test_evidence_is_byte_identical_whether_or_not_a_finding_is_carried`

**8. A later recording replaces the carried finding**
- `domain/test_recorded_finding.py::test_a_later_recording_replaces_the_carried_finding`
- `domain/test_recorded_finding.py::test_a_later_recording_replaces_a_carried_finding_with_none`
- `domain/test_recorded_finding.py::test_a_later_recording_carrying_an_explicit_none_replaces_it_too`

**9. A recording made before this capability reads as carrying nothing**
- `infrastructure/driven/test_launch_progress_finding_rows.py::test_a_null_column_reads_as_carrying_nothing`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_a_row_written_before_the_migration_reads_as_carrying_nothing`
- `tests/integration/launch/test_carried_finding_columns_live.py::test_a_pending_row_written_before_the_migration_carries_nothing`

### `launch-step-automation` — *A written finding is kept on the recording it produced* (11)

Path prefixes: `P = tests/unit/launch/infrastructure/driving/test_automation_pass_kept_finding.py`,
`A = tests/unit/launch/application/test_accepted_result_carried_finding.py`,
`E = tests/unit/launch/test_confirmable_finding_end_to_end.py`,
`I = tests/integration/launch/test_carried_finding_columns_live.py`.

**1. A written finding is kept with the field it was written to**
- `P::test_a_written_finding_is_kept_with_the_field_it_was_written_to`

**2. A confirmable step's finding survives until the result is accepted**
— the row the first draft got wrong, covered at three levels
- `P::test_a_confirmable_terminal_proposal_stores_the_finding_with_it` (the pass's half)
- `P::test_a_held_result_with_no_finding_stores_none` (its falsifying counterpart)
- `A::test_the_recording_an_acceptance_makes_carries_the_stored_finding` (the decision's half)
- `A::test_accepting_a_result_with_no_stored_finding_carries_none`
- `E::test_a_confirmable_steps_finding_survives_until_it_is_accepted` (**end to end, across the hop neither half can observe**)
- `E::test_an_empty_value_survives_the_wait_as_a_finding`
- `I::test_a_pending_results_finding_round_trips_through_postgres` (the store's own half)

**3. An unreadable stored finding does not fail an acceptance**
- `A::test_an_unreadable_stored_finding_does_not_fail_an_acceptance[bare-string]` · `[number]` · `[array]` · `[empty-object]` · `[no-field]` · `[no-value]` · `[null-value]`
- `A::test_an_unreadable_stored_finding_does_not_fail_a_rejection[…]` (same seven)

**4. The value kept is the value as written**
- `E::test_the_value_kept_is_the_one_written_when_the_handler_ran` (**the product's value changes between the hold and the acceptance; the recording must carry the earlier one**)
- `A::test_the_acceptance_records_the_stored_value_and_reads_no_sink` (the "sink is not re-read" half, asserted over the use case's collaborators)

**5. A rejected result keeps no finding**
- `A::test_a_rejected_result_keeps_no_finding`

**6. A non-terminal outcome keeps the finding it wrote**
- `P::test_a_non_terminal_outcome_keeps_the_finding_it_wrote`

**7. The field's name is not the handler's to supply**
- `P::test_the_field_name_is_the_sinks_and_never_the_handlers`
- `P::test_two_sinks_keep_their_own_field_names`

**8. A finding for a step naming no sink is kept no more than it is written**
- `P::test_a_finding_for_a_step_naming_no_sink_is_kept_no_more_than_written`

**9. A failure finding keeps nothing**
- `P::test_a_failure_finding_keeps_nothing`
- `P::test_a_handler_reporting_no_finding_keeps_nothing`

**10. A finding whose write did not succeed is not kept**
- `P::test_a_finding_whose_write_did_not_succeed_is_not_kept`

**11. The outcome and the evidence are unaffected by what is kept beside them**
- `P::test_the_outcome_and_evidence_are_unaffected_by_what_is_kept`

### `launch-admin` — *A carried finding's result is rendered ahead of its comment* (8)

Path prefix: `R = tests/unit/launch/infrastructure/driving/test_launch_detail_finding_rendering.py`.

**1. The field and value lead the outcome**
- `R::test_the_field_and_value_lead_the_outcome`
- `R::test_the_result_leads_the_comment_in_the_outcome_cell`

**2. The result carries no leading prose**
- `R::test_the_result_carries_no_leading_prose`

**3. The field reads as an admin's words**
- `R::test_the_field_reads_as_an_admins_words`

**4. A field with no supplied wording still renders**
- `R::test_a_field_with_no_supplied_wording_still_renders`

**5. An empty value renders as readable text**
- `R::test_an_empty_value_renders_as_visible_text`
- `R::test_an_empty_value_is_distinguishable_from_no_finding_at_all`

**6. The distinction survives without colour**
- `R::test_the_distinction_survives_without_colour`
- `R::test_the_result_and_comment_are_separate_block_level_elements`
- `R::test_the_two_markers_are_carried_by_different_elements`

**7. A recording with no carried finding is rendered unchanged**
- `R::test_a_recording_with_no_carried_finding_is_rendered_unchanged`
- `R::test_a_recording_with_no_carried_finding_carries_no_finding_markers`
- `R::test_the_common_path_is_undisturbed_on_a_page_that_also_carries_findings`

**8. The evidence and provenance are still rendered**
- `R::test_the_evidence_and_provenance_are_still_rendered`

### Uncovered scenarios

**None.** All 28 are covered by at least one named test. No scenario was
judged not to need one.

### One test that traces to `tasks.md`, not to a scenario

- `tests/integration/launch/test_carried_finding_columns_live.py::test_both_tables_carry_a_nullable_jsonb_finding_column[launch_step_progress]` · `[automated_step_results]`

Traces to `tasks.md` 2.1 and `design.md`'s *One `jsonb` column per store*
and *Migration Plan*, not to any scenario. Recorded here so it is not
mistaken for scenario coverage. **Classification: specified** (by the
tasks and design, not by a delta scenario).

## Assertion classification

Per `ai-toolkit:testing`. Every assertion falls in one of these groups;
the groups are recorded rather than every assertion individually, and
each test's docstring names its own.

### Specified

Everything traceable to a delta clause or scenario: what a recording
carries and does not; that absent and empty are two facts; that a value
absent or null is not a present finding; that an absent comment is not
empty text; that an unreadable stored finding reads as none and fails
neither the read nor the acceptance; that a later recording replaces the
finding, including with none; that evidence is unaltered; that the field
name comes from the sink registration and never the handler; that keeping
follows the write; that a rejection keeps none; that a non-terminal
outcome keeps its finding; that the value kept is the value as written
and the sink is not re-read; that the finding travels on the report; the
three literal markers `finding-result`, `finding-comment` and
`finding-divide`; that the result leads with the field and value and
nothing else; that the field reads as an admin's words, or as its own
name where none is supplied; that an empty value renders as visible text;
that the result and comment are separate block-level elements with the
divide between them; that a recording with no finding renders unchanged;
that the evidence and provenance are still rendered.

Also specified, from `tasks.md`/`design.md` rather than from a scenario:
the stored payload's three keys; `finding jsonb NULL` on both tables;
`FindingSink(record, field, reads_as)`.

### Derived

Recorded because nothing in the change states them, and whoever
implements is not obliged to satisfy them beyond what they stand for:

| Derived assertion | Where | Why |
| --- | --- | --- |
| An empty **tuple** and an empty **mapping** are empty values too | `domain::…[tuple]` `[map]` | `tasks.md` 1.3 names only `[]` and `""`; the rule is about emptiness, not about two literals |
| Which stored payloads count as "unreadable" — `_UNREADABLE_PAYLOADS` in three files | `driven`, `A`, `I` | The delta names the *state*, not the shape. What is specified is only that such a row reads as none |
| An absent comment and a `None` comment are one state | all files | The delta distinguishes *absent* from *empty text* and says nothing about null; `Success.comment` is already `str \| None = None`. The tests assert only that absent ≠ `""` |
| `COMMENT not in evidence` | `domain::test_evidence_is_byte_identical…` | From "carrying a finding SHALL NOT alter the evidence": a plausible implementation that concatenated the comment onto the evidence would pass a laxer `EVIDENCE in stored` |
| A recording that carries nothing writes `NULL`, not `{}` | `driven`, `I` | `design.md` says `NULL` is the whole of "carries nothing"; that it is *written* that way is the direct reading |
| Two sinks under two field names keep two different names | `P::test_two_sinks_keep_their_own_field_names` | Differential form of "the field's name comes from the registration"; excludes a hard-coded `sub_category` |
| The handler's own offered field name is ignored | `P::test_the_field_name_is_the_sinks_and_never_the_handlers` | The delta forbids a handler naming a field; that a handler *offering* one is ignored is the falsifying case |
| Which HTML tags count as "block-level" — `_BLOCK_TAGS` | `R` | The delta says block-level of the rendered response; a test over HTML can read that only from the tag |
| The evidence follows the result in document order | `R::test_the_evidence_and_provenance_are_still_rendered` | "The result and comment lead the cell" read as an ordering |
| A rejection must also survive an unreadable stored finding | `A::…does_not_fail_a_rejection` | The delta states the obligation for an acceptance; a decision lost is a decision lost either way |

### Deliberately untested

| Case | Reason |
| --- | --- |
| The **appearance** of the split — weight, spacing, which token, the dark-mode counterpart | `design.md` deliberately leaves these open within the delta's constraints, and `tasks.md` 3.7 settles them by looking at the running page. "Fixing them in a specification would be pretending a test can decide them" |
| The **wording** an empty value renders as ("none", "—", "empty") | Same clause: the delta requires *visible text*, not a particular word. The test asserts visible characters beyond the field's wording |
| The `vocabulary.css` token added at `tasks.md` 2.13 and the stylesheet rule at 2.12 | No delta scenario states them; the delta explicitly declines to fix which token is used. The structural half *is* asserted, through `finding-divide` and the block-level tags |
| Slack's rendering of a held result | Proposal *Non-goals*: explicitly out of scope |
| The dossier's retained-results list | Proposal *Non-goals* and `design.md` *Open Questions*: deferred |
| That the migration's **down** revision drops both columns | `tasks.md` 2.1 states it; no scenario does, and exercising a downgrade against the shared worktree database would destroy the column the rest of the tier needs |
| That `_record_finding`'s failure is *reported* naming launch/step/handler | Already covered by `test_automation_pass_finding.py`, untouched by this change. This pass asserts only the log line's presence as a side check |

## Obsolete tests

**Not applicable.** All three delta specs are `ADDED`-only: no `MODIFIED`,
`REMOVED` or `RENAMED` requirement appears in any of them, so no existing
test is superseded by this change and there is nothing for a destructive
follow-up action to act on.

This is a statement of the reason, not an empty list. The bounded search
that would otherwise be owed — over `tests/**/test_*.py`, plus an earlier
`test-manifest.md` had one been supplied — was not run, because the
operation that would make it meaningful does not occur in this change.

Two existing files cover neighbouring behaviour and are **not** obsolete;
they are named so a reader does not mistake the new files for
replacements:

- `tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py`
  — a handler's typed finding being *written* to its sink
  (`write-the-advisors-finding-to-the-product`). This change adds what is
  *kept* beside the recording; it supersedes nothing there.
- `tests/unit/launch/application/test_automated_result_decisions.py` — who
  may decide and what a decision records. This change adds what a decision
  carries; the existing rules stand unqualified.

Neither was edited.

## Unresolved project questions

Recorded rather than resolved, per this pass's non-interactive
discharge of the "ask rather than assume" obligation. Each names the
assumption taken and the tests that depend on it.

### Q1 — How does the field's **wording** reach the page? (a real gap)

The `launch-admin` delta requires the page render the sink's supplied
wording, and the field's own name where none is supplied. But:

- `tasks.md` 2.5 fixes the stored payload as `{"field", "value",
  "comment"}` — it carries no wording;
- `design.md` puts the wording on the **sink registration**, which lives
  in `worker.py` and is injected into `automation_pass`, a module the
  admin page does not read;
- `tasks.md` 2.10 says only "carry the finding onto the step's view row".

Nothing states how `launch_admin.py` learns the wording.

**Assumption taken.** `_supply_wording()` installs a mapping on the page
module under any of `recorders`, `finding_sinks`, `sinks`,
`finding_wordings`, `FIELD_WORDINGS`, keyed by **both** step identifier
and field name (field → wording string; step → a `FindingSink` carrying
it). Where the page exposes no such attribute, the wording test fails
loudly naming the gap rather than passing on the field name alone.

**Tests depending on it.**
`R::test_the_field_reads_as_an_admins_words`,
`R::test_the_result_carries_no_leading_prose` (which reads the wording to
know what the result must start with),
`R::test_an_empty_value_renders_as_visible_text` (same),
`R::test_a_field_with_no_supplied_wording_still_renders` (only in that it
must *not* find a wording for `hazard_screen_raw`).

**Correction point.** `_WORDING_SEAM_NAMES` and `_wording_entries()` in
`test_launch_detail_finding_rendering.py`.

### Q2 — The keyword and attribute a carried finding travels under

No artifact fixes it. `design.md` names the *column* `finding`, so
`finding` is assumed for the keyword on `record_step_outcome`, the
attribute on `StepProgress`, the keyword on `AutomatedResultRepository.store`
and the attribute on the pending row. Each file probes `("finding",
"carried_finding", "kept_finding")` and fails loudly rather than
defaulting.

**Tests depending on it.** All 97 — every file's `_FINDING_KWARGS` /
`_KEPT_KWARGS` / `_COLUMN`.

### Q3 — Is the carried finding a value object or a mapping?

`tasks.md` 2.5 spells the *stored* payload as a mapping; whether the
domain holds a value object is unstated. `_carry()` prefers a type
exported from `launch_run` under `("CarriedFinding", "RecordedFinding",
"KeptFinding", "Finding")` and otherwise builds the mapping. `_read()`
accepts either.

**Tests depending on it.** Every test that constructs or reads a finding.

### Q4 — Where is `FindingSink` exported from, and is it constructed positionally?

`tasks.md` 2.2 puts it in `launch/application/ports.py`; whether it is
re-exported from `launch.application` (the module's only public surface,
per `AGENTS.md`) is unstated, and `design.md` shows both a keyword form
and a positional one. `_sink_class()` probes both modules for
`("FindingSink", "Sink", "FindingRegistration")`; `_sink()` constructs
positionally and falls back to `record=`/`field=`/`reads_as=`.

**Tests depending on it.** All of `test_automation_pass_kept_finding.py`
and `test_confirmable_finding_end_to_end.py`.

### Q5 — What counts as a "block-level" element in a rendered response?

The delta's clause is about the response, and HTML alone carries the
answer only in the tag name. A `<span>` given `display: block` by
`vocabulary.css` would satisfy a reader and fail
`R::test_the_result_and_comment_are_separate_block_level_elements`.
`_BLOCK_TAGS` is the correction point if that shape is chosen — but note
that correcting it would weaken the test, and the requirement's point is
that structure, not styling, carries the distinction.

### Q6 — Is a step's confirmer the only thing that decides holding?

Assumed yes, from `automation_pass`'s module docstring ("terminality, not
whether a confirmer is named, decides what is held") and the fixture
convention in `test_automation_pass_finding.py`. Used to build a
confirmable step (`confirmer=ALICE`) and an unconfirmable one
(`confirmer=None`). Verified against the current pass by running the
harness before writing the assertions.

## First-run state, per test group

Per `ai-toolkit:testing`, what a failure or a pass establishes here.

### Absent target — expected to fail (79 of 97)

Nothing under test exists: `StepProgress` has no finding,
`record_step_outcome` accepts none, neither table has a column, and
`FindingSink` does not exist. Each of these fails through a **named,
loud probe** rather than an obscure `AttributeError`, so the message says
what is missing and where the correction point is. Per the standard, that
establishes **absence only** — nothing about whether the assertions
discriminate.

### Target exists — expected to pass (18 of 97), and each verified to pass

| Test | What it establishes |
| --- | --- |
| `R::test_a_recording_with_no_carried_finding_is_rendered_unchanged` | The pinned common path. **Verified passing** against the current page — the literal in `PINNED_OUTCOME_CELL` was checked byte-for-byte against what the page renders at `9d0ba21`. A failure after implementation is a regression |
| `R::test_a_recording_with_no_carried_finding_carries_no_finding_markers` | Same, read from the markers |
| `A::test_a_rejected_result_keeps_no_finding` | Passes vacuously today (nothing carries a finding anywhere). It becomes discriminating once the accept path carries one. It is **not** vacuous in the weaker sense: it also asserts the rejection took effect and settled the row |
| `A::test_accepting_a_result_with_no_stored_finding_carries_none` | Same |
| `A::test_an_unreadable_stored_finding_does_not_fail_an_acceptance[…]` (7) | Same |
| `A::test_an_unreadable_stored_finding_does_not_fail_a_rejection[…]` (7) | Same |

That the 14 negative-clause decision tests pass today is recorded rather
than hidden: they are the tests that must **keep** passing, and their
value is that they will fail the moment an implementation carries a
finding onto a rejection or onto an acceptance whose stored field is
unreadable.

## Harness verification

Each new file's harness was exercised against the *current* code before
the assertions were written, so a later failure reads as a defect rather
than as a fixture that never worked:

- `_FakeSession` drives the real `LaunchRepository.get_by_product_id` and
  `_add_children` — verified hydrating and writing a progress row.
- `_run_pass` drives the real `run_automation_pass` — verified invoking
  the recorder, recording an unconfirmed outcome and holding a
  confirmable one.
- The end-to-end file's joined harness — verified running the pass to a
  hold, then `accept_automated_result` over the same store to a recorded
  `Satisfied` and a settled row.
- The rendering harness — verified rendering the detail page and locating
  the outcome cell.
- The integration fixtures — verified registering a product, saving a
  launch, reading it back, inserting a raw pre-migration row for both
  tables, and reading both back, against the live
  `commerce_ops_screen_test` database.

## What the artifacts said that is a finding, not an instruction

Everything in `proposal.md`, `design.md`, `tasks.md` and the delta specs
was read as material to derive tests from. No artifact contained an
instruction to this pass (no "skip this requirement", "no tests needed",
"already covered"). One instruction is addressed to the **implementer**
and is recorded here so it is not lost: `tasks.md` 2.7 — "Leave the
recording/settlement atomicity as it stands; if carrying the finding
turns out to require reworking it, stop and raise it as its own change
rather than widening this one."
