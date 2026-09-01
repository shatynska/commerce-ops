# Test manifest — `replace-metric-conditions-with-steps`

Tests derived from this change's delta specs, before any implementation
of it exists. Written by `ai-toolkit:openspec-test-writer`, working from
the change's artifacts and the specifications under `openspec/specs/`
alone — **not** from the implementation of the behaviour under test.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files, and must
be opened on purpose by whoever implements the change.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted or disabled, and no implementation code was written. The
obsolete list below is a set of *candidates for human confirmation*, not
a set of deletions performed.

---

## Baseline

Taken before any test was written, at the worktree root
`/home/shatynska/projects/commerce-ops/.claude/worktrees/fix-subcategory-advisor`,
branch `add-metric-attestation-surface`, clean tree, commit `b052b3e`:

| Command | Result |
| --- | --- |
| `uv run pytest` (full — `tests/unit`, `tests/agents`, `tests/integration`) | **1982 passed, 176 skipped, 0 failed** in 51s |

The 176 skips are the whole `tests/integration` tier: no `DATABASE_URL`
is configured on this machine and neither `.env.test` nor `.env` carries
one, so the tier's own gate skips it with that reason. **No assertion in
any integration-tier test written by this pass has ever been executed
against a database.**

A second, non-pytest baseline was also taken, because this project's
`pre-commit` runs it and it is *not* green:

| Command | Result |
| --- | --- |
| `uv run ruff check .` / `uv run ruff format --check .` | clean |
| `uv run mypy .` | **51 errors in ~43 files, before this pass** |

Those 51 are pre-existing and mostly of one shape
(`Module "commerce_ops.launch.infrastructure.driving" has no attribute
"automation_pass"` and siblings). See *Unresolved project questions*.

### After this pass

| Command | Result |
| --- | --- |
| `uv run pytest` | 34 failed, **1986 passed**, 179 skipped |
| `uv run ruff check tests/` / `ruff format --check tests/` | clean |
| `uv run mypy .` | 61 errors — the same 51, plus 10 in the new files |

Every one of the 34 failures is in a file this pass created. **No
previously-passing test changed state.** The passed count rose by 4 and
the skipped count by 3, which are the new tests that pass on their first
run (see the state table below) and the three new integration tests that
skip for want of a database.

---

## What the failures establish

Per `ai-toolkit:testing`, a failing test is not one thing. Every new test
is classified below by the state it is currently in.

| Test file | Tests | First-run state |
| --- | --- | --- |
| `tests/unit/launch/domain/test_gate_conditions_are_steps_alone.py` | 2 of 4 | **Wrong value.** `framework_gates()` still authors metric conditions on three gates and `MetricCondition` still exists. Assertions executed and discriminated. |
| " | 2 of 4 | **Pass on first run.** The two obligation scenarios' subject is unchanged by this delta and already implemented. Not the alarm state — the alarm is a pass where nothing implements the behaviour. |
| `tests/unit/launch/domain/test_step_metric_identifier.py` | 4 of 4 | **Absent target.** `StepDefinition` takes no `metric_id` (`TypeError` / `AttributeError`). Assertions never executed. |
| `tests/unit/launch/domain/test_metric_step_gate_obligations.py` | 4 of 6 | **Absent target** (same `metric_id`). |
| " | 2 of 6 | **Wrong value.** `PROVENANCE_SOURCES` is `('clickup', 'automated', 'attestation')`; `MetricAttestation` still exists. |
| `tests/unit/launch/application/test_metric_step_journalling.py` | 3 of 4 | **Absent target** (same `metric_id`). |
| " | 1 of 4 | **Wrong value.** `record_metric_attestation` is still exported from the launch module's public surface. |
| `tests/unit/launch/application/test_progress_launch_metric_step.py` | 2 of 2 | **Absent target** (same `metric_id`). |
| `tests/unit/launch/application/test_step_metric_identifier_authoring.py` | 10 of 10 | **Absent target.** Neither `create_step` nor `update_step` accepts `metric_id`. |
| `tests/unit/launch/application/test_handler_source_claim_after_attestation.py` | 1 of 1 | **Pass on first run.** Its subject is unchanged; only the source the fixture names changes. |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_metric_identifier_field.py` | 2 of 2 | **Absent target** (same `metric_id`, raised in the fixture before the page is reached). |
| `tests/unit/launch/infrastructure/driving/test_launch_admin_journal_metric_step.py` | 1 of 1 | **Wrong value.** `launch_admin._gate_or_step` reads `entry.gate_id`, which `tasks.md` 5.5 deletes; against the specified entry shape it raises `AttributeError` **from the code under test**, not from the test. |
| `tests/unit/launch/test_playbook_reference_set_metric_steps.py` | 3 of 4 | **Wrong value.** The vendored file exists and is readable; the six rows are absent and no row carries a `metric_id`. The strongest state. |
| " | 1 of 4 | **Pass on first run**, and **not yet discriminating**: *A row merely mentioning a number is an ordinary step* asserts that no row outside the six declares a metric identifier, which currently holds because no row declares one at all. It becomes discriminating once the six are seeded. Recorded here so the pass is not mistaken for coverage established. |
| `tests/integration/launch/test_metric_steps_after_preparation.py` | 3 of 3 | **Not executed.** Skipped for want of a configured database. |

---

## Assertion provenance

Per `ai-toolkit:testing`, every assertion is **specified**, **derived**,
or **deliberately untested**. Each new test file carries the
classification inline, at the assertion, with `SPECIFIED` / `DERIVED`
comments and a `## What is fixed, and what is INVENTED` section in its
module docstring. What follows is the summary; the files are the record.

### Derived assertions (invented by this pass — review these)

| Where | Derived assertion | Why |
| --- | --- | --- |
| `test_gate_conditions_are_steps_alone.py::test_the_removed_condition_types_are_gone` | `MetricCondition`, `GateCondition`, `_AUTHORED_METRIC_CONDITIONS` and `Gate.metric_conditions` are **absent**, not merely unused | The requirement says a gate carries no condition of any other kind; a type left in place leaves the repository mapping and `framework_gates()` free to keep constructing one. Follows the precedent of `test_step_definition_field_set.py::test_the_removed_fields_are_gone_from_the_step`. |
| `test_metric_step_gate_obligations.py::test_a_satisfied_metric_step_opens_its_gate` | A satisfied metric step **does** open its gate | Paired with the holding scenario. Without it, an implementation that never satisfied a metric obligation would pass the holding scenario and reproduce, through the step, the stall this change exists to end. |
| `test_metric_step_gate_obligations.py` | Absence spelled `None` for an unauthored `metric_id`; `launch.attestations` absent | The spelling every other optional `StepDefinition` field uses. |
| `test_progress_launch_metric_step.py::test_a_resolved_metric_step_lets_the_pass_carry_the_launch_on` | The cascade carries a launch past a gate whose metric step is resolved | Same pairing reason as above, at the cascade level. |
| `test_step_metric_identifier_authoring.py::test_a_conventionally_wrong_identifier_is_still_accepted` | `stock-ready-units` and `sixty-to-eighty-units` are **accepted** by the authoring surface | Specified by the delta's own "no validation SHALL be derived from this paragraph", but stated as a positive assertion rather than as the absence of a rejection test — see *The editorial rule*, below. |
| `test_playbook_admin_metric_identifier_field.py` | "Free-typed rather than chosen from a list" read as *not a `<select>`*; "clearable" read as *not `required`, and empty where the step declares none* | HTML has one control for constraining an author to a list, and one attribute that forbids an empty submission. |
| `test_playbook_admin_metric_identifier_field.py::test_the_metric_input_carries_what_the_step_declares_and_nothing_where_none_is` | The input is populated from the step | A form that rendered the input but never populated it would satisfy "offers an input" while silently clearing the field on every submission. |
| `test_playbook_reference_set_metric_steps.py::_NUMBER_WORDS` | A small spelled-out-number list | The naming rule's own counterexample (`sixty-to-eighty-units`) carries no digit, so a digit check alone would not catch it. |
| `test_metric_steps_after_preparation.py::_seeded` | A `lp.*` count of exactly 107 is reported as a **setup gap**, not a defect | `tasks.md` 6.5: a migrate-only database carries the migration-era seed. |
| `test_handler_source_claim_after_attestation.py` | `TypeError` as the refusal signal | Python's own dataclass behaviour, named because it is what the assertion reads. |

### Deliberately untested

| Case | Reason |
| --- | --- |
| **Which of the six rows carries which metric identifier, and which gate each holds** | `tasks.md` 1.2 transcribes the identifiers out of `_AUTHORED_METRIC_CONDITIONS` during implementation and 1.3 resolves the gates. Neither answer exists in this change's artifacts, so a test fixing them would invent the mapping rather than check it. What is asserted is that each of the six carries **an** identifier, that it obeys the stated naming rule, and that it declares **a** gate in the framework's sequence. |
| **Which reference rows qualify as threshold rows** | The delta says the selection "is made when a row is transcribed, by whoever transcribes it — it is an editorial reading, not a computation — so what a test asserts is the resulting set, not the selection". No test re-derives the criterion from the document's wording; the resulting set is asserted from both sides (the six are present with identifiers; no seventh row declares one). |
| **That a non-conforming metric identifier is rejected by the authoring surface** | Forbidden by the delta: the naming paragraph "binds the seed, not the authoring surface … no validation SHALL be derived from this paragraph". The converse is asserted instead (see the derived table). |
| **"Naming the quantity" itself** | Not machine-checkable. The three checkable clauses of the naming rule are asserted (lowercase-hyphenated form, no gate name, no threshold value). |
| **`The seed runs once`** | See *Uncovered scenarios*. |
| **The `metric-attested` journal kind's read path** | No entry of that kind was ever written (the command had no surface), so there is no legacy row to read and nothing to assert beyond the kind's absence, which is asserted. |
| **That the `launch_metric_attestations` table is empty in production** | `tasks.md` 1.1 makes this a manual check against production before the drop migration is written. It is not observable from a test. |
| **The visual half of the launch-admin journal rendering** | The delta itself says the markers are "a necessary condition, not a sufficient one" and that the rest "SHALL be confirmed by direct inspection of the rendered page". |

---

## The editorial rule, and how this pass honoured it

Two paragraphs of the `launch-playbook` delta constrain what a test may
assert, and both were followed:

1. **The selection is editorial.** No test computes which reference rows
   condition a gate. `SEEDED_METRIC_STEPS` in
   `test_playbook_reference_set_metric_steps.py` and in
   `test_metric_steps_after_preparation.py` names the six identifiers the
   REMOVED requirement's Migration paragraph names, and the tests assert
   the resulting set.
2. **The naming convention binds the seed only.** It is asserted over the
   seeded set (`test_a_metric_identifier_names_the_quantity_alone`) and
   its converse is asserted over the authoring surface
   (`test_a_conventionally_wrong_identifier_is_still_accepted`), so that
   an implementer who reads the convention and adds the validation is
   caught by a test rather than passing silently.

---

## Obsolete tests — candidates for human confirmation

Search bound: the dispatched test-path glob `tests/**/test_*.py`, and
nothing outside it. No earlier `test-manifest.md` was supplied to this
pass, so no scenario-to-test index from a previous change was available.
Every entry names the delta that supersedes it and the evidence it was
matched on.

**Every entry below is a candidate for human confirmation, not a
conclusion.** Nothing here was edited or deleted.

### Group A — subject superseded (deletion candidates)

These test a behaviour a REMOVED or MODIFIED requirement takes away. Each
would have no requirement left to trace to after the change.

| Test | Superseded by | Evidence |
| --- | --- | --- |
| `tests/unit/launch/domain/test_gate_conditions.py::test_a_gates_metric_conditions_are_read_back` | `launch-playbook` REMOVED *A gate carries authored metric conditions* | Asserts `gates["stock-ready"].metric_conditions` reads back a `MetricCondition`'s `metric_id` and `threshold` (lines 190-209). |
| `tests/unit/launch/domain/test_gate_conditions.py::test_a_gate_with_no_metric_conditions_is_valid` | same | Asserts `list(gate.metric_conditions) == []` for every gate (line 224). |
| `tests/unit/launch/domain/test_gate_conditions.py::test_a_gate_may_carry_more_than_one_metric_condition` | same | Constructs two `MetricCondition`s on `phase-one-complete` and asserts the gate carries two (line 244). |
| `tests/unit/launch/domain/test_gate_conditions.py::test_authored_metric_conditions_appear_alongside_derived_obligations` | `launch-playbook` REMOVED *Gate conditions unify step obligations and metric conditions* | Its whole subject is that both kinds are returned, "each identifiable as its kind" (lines 302-330). The replacing requirement says a gate carries no condition of any other kind. |
| `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_metric_condition_with_an_empty_threshold_is_rejected` | `launch-playbook` REMOVED *An incoherent playbook is rejected against its steps' status and shape* | Docstring reads "Scenario: A malformed metric condition is rejected"; constructs `MetricCondition(MetricId("units-fulfillable"), "")`. `tasks.md` 4.4 names the deletion of both the rule and its tests. |
| `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_the_two_new_faults_are_reported_together` | same | One of "the two new faults" is the empty threshold (line 224). Its sibling scenario *Multiple violations are reported together* stays covered by four other files. |
| `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_attested_metric_condition_counts_as_satisfied` | `launch-instance` REMOVED *A metric condition is satisfied by human attestation until live evaluation exists* | Calls `launch.record_metric_attestation(playbook, _attestation())` (line 528). |
| `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_unattested_metric_condition_keeps_the_gate_closed` | same | Asserts a `GateBlocked` naming a metric condition with no recorded attestation (lines 536-556). |
| `tests/unit/launch/domain/test_launch_gate_advance.py::test_an_attestation_for_a_condition_the_gate_does_not_author_is_rejected` | same | Its whole subject is the attestation-rejection rule the requirement states (lines 558+). |
| `tests/unit/launch/application/test_launch_journal_appends.py::test_a_recorded_metric_attestation_is_journaled` | `launch-journal` REMOVED *Every accepted launch command appends exactly one journal entry*; `tasks.md` 5.5 | Calls `record_metric_attestation(...)` and asserts `entry.kind == KIND_METRIC_ATTESTED` (lines 648-672). |
| `tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_metric_attesteds_condition_is_not_a_gate_or_step` | `launch-admin` REMOVED *A launch's journal page renders its journal, newest first* | Builds `_entry(kind="metric-attested", ...)` and asserts the gate/step column excludes it (lines 822-868). `tasks.md` 5.6 deletes that branch. |
| `tests/unit/launch/application/test_progress_launch.py::test_a_gate_blocked_only_by_a_metric_condition_is_left_silently` | `launch-gate-progression` MODIFIED *A recurring pass advances every launch whose gate may open* | Function name and body turn on a gate blocked by a metric condition alone — a state no playbook can be in after the change. Replaced by `test_progress_launch_metric_step.py::test_a_gate_held_by_an_unresolved_metric_step_is_left_where_it_is`. |
| `tests/unit/launch/test_playbook_reference_set.py::test_every_reference_row_appears_except_the_restatements` | `launch-playbook` REMOVED *The seeded step set carries the authored v1 definitions* | Asserts `seeded == set(rows) - METRIC_RESTATEMENTS`, `len(seeded) == 352` and `not (seeded & METRIC_RESTATEMENTS)` (lines 106-119). `tasks.md` 3.3: "Invert … the six identifiers are present". Replaced by `test_playbook_reference_set_metric_steps.py::test_every_area_is_fully_represented_with_no_exception`. |
| `tests/unit/launch/test_playbook_reference_set.py::test_the_vendored_set_constructs_a_playbook` | same | Asserts `len(playbook.authored_steps) == 352` (line 100). Only the count is superseded; the rest of the test survives. **Partial** — a count correction, not a deletion. |
| `tests/unit/launch/test_playbook_reference_set.py::test_the_human_pass_is_carried_across_unchanged` | same | Skips `METRIC_RESTATEMENTS` when comparing against `playbook_v1.yaml` (line 268). **Partial** — the skip is what is superseded. |
| `tests/unit/test_seed_playbook.py::test_an_empty_set_receives_the_whole_vendored_set` | `launch-playbook` ADDED *The seeded step set carries every reference row*; `tasks.md` 3.4 | Asserts `added == len(vendored) == 352` (line 47). **Partial** — a count correction. |
| `tests/integration/launch/test_playbook_seed.py::test_gate_authored_conditions_are_not_duplicated_as_steps` | `launch-playbook` REMOVED *The seeded step set carries the authored v1 definitions* | Its whole subject is the exclusion this change reverses. |
| `tests/integration/launch/test_seeded_step_fields.py::test_a_gate_authored_condition_is_not_duplicated_as_a_step` | same | Same subject, at the served-set level; its module also declares the six identifiers as a `METRIC_RESTATEMENTS` constant. |
| `tests/unit/launch/domain/test_launch_run.py::test_a_satisfied_step_is_recorded_with_its_provenance` | `launch-instance` MODIFIED *A step outcome is recorded with provenance* | Its docstring quotes the scenario "with source `attestation`" and it asserts `progress.provenance.source == "attestation"` (lines 294-316). The scenario now reads `clickup`. Replaced by `test_metric_step_gate_obligations.py::test_a_satisfied_step_is_recorded_with_its_provenance`. **Partial** — a fixture-value correction, and the assertion must not be weakened while making it. |
| `tests/unit/launch/application/test_playbook_authoring.py::test_the_authoring_surface_offers_no_framework_write` | `playbook-authoring` MODIFIED *Authoring never touches the framework* | Asserts no operation takes `metric_condition` / `metric_conditions` as a parameter (lines 655-670) — a clause the delta strikes. The assertion becomes vacuous rather than wrong. **Partial** — a narrowing, not a deletion. |
| `tests/unit/launch/application/test_step_handler_contract.py::test_a_resolution_has_no_place_to_put_provenance` | `launch-step-automation` MODIFIED *A handler receives the step, the launch and the product, and attributes nothing*; `tasks.md` 5.7 | Smuggles `Provenance(source="attestation", ...)` (line 376). **Partial** — a fixture-value correction. Replaced-in-parallel by `test_handler_source_claim_after_attestation.py`. |
| `tests/unit/launch/application/test_step_handler_contract.py::test_no_field_of_the_contract_is_a_provenance_in_disguise` | same | Its docstring quotes "from a person, from ClickUp, or from an attestation" (line 398) — wording `tasks.md` 5.7 revises. **Partial** — a docstring correction only. |
| `tests/integration/launch/test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state` | `launch-instance` MODIFIED *A launch position can be read back by product identifier* | Records and reads back a `MetricAttestation` (lines 444-490); the scenario no longer says "and each attestation it was persisted with". **Partial** — the attestation half goes, the rest survives and must not be weakened. |

### Group B — fixture-only reference (**not** obsolete; migration owed)

These do **not** test superseded behaviour. Their subject survives the
change unchanged; they merely construct a type or name a source string
the change removes, so they will stop *running* rather than stop being
right. Listed separately, and explicitly, so that a reader deleting from
Group A does not reach for these.

**Whoever migrates them must correct the fixture and leave the assertion
alone.** Editing an assertion to match what the new code produces is what
`ai-toolkit:testing` forbids.

| File | What it references | Nature |
| --- | --- | --- |
| `tests/unit/launch/domain/test_gate_conditions.py` (whole module) | imports `MetricCondition`; `specified_gates(metric_conditions=…)` | Module-scope import — every test in it fails at import once the type is deleted, including `test_a_blocking_step_appears_as_a_step_obligation`, `test_a_non_blocking_step_produces_no_condition` and `test_conditions_are_scoped_to_the_asked_gate`, whose subjects survive. The first two are re-derived by `test_gate_conditions_are_steps_alone.py`; the third is not, and needs migrating. |
| `tests/unit/launch/domain/test_launch_gate_advance.py` | imports `MetricCondition` / `MetricAttestation`; `_provenance` defaults to `source="attestation"` | Module-scope imports plus a shared fixture default. |
| `tests/unit/launch/domain/test_playbook_coherence_completion.py` | imports `MetricCondition`; `specified_gates(metric_conditions=…)`; `test_a_coherent_playbook_with_the_completed_surface_loads` constructs one | Module scope. |
| `tests/unit/launch/application/test_launch_journal_appends.py`, `test_launch_journal_containment.py`, `test_progress_launch.py`, `test_scope_aware_launch_reads.py`, `test_gate_decision.py` | import `MetricCondition` / `MetricAttestation`; `_playbook()` authors one on `stock-ready`; `_satisfy_*` records an attestation | Module scope and shared walk helpers. |
| `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py`, `test_gate_progression_pass.py`, `test_gate_progression_pass_eager_convergence.py` | same shapes | Module scope. |
| `tests/integration/launch/test_gate_progression_atomicity_live.py`, `test_webhook_advance_atomicity_live.py` | `_satisfy_metrics` imports both types inside the function and records an attestation | Function-local imports — these fail at call time rather than at collection. |
| `tests/integration/launch/test_launch_repository.py` | module-scope `MetricCondition` / `MetricAttestation`; `_playbook()` authors one | Module scope. |
| ~20 files carrying `source="attestation"` in a `_provenance()` fixture default | `test_launch_run.py`, `test_launch_dates.py`, `test_launch_dates_release.py`, `test_outcomes_after_retirement.py`, `test_step_start_release.py`, `test_dependency_commitment_neutrality.py`, `test_within_gate_order_commitment_neutrality.py`, `test_launch_report_release.py`, `test_launch_report_step_facts.py`, `test_launch_reports.py`, `test_clickup_sync_projection.py`, `test_clickup_sync_reconciliation.py`, `test_clickup_sync_release.py`, `test_launch_admin_detail.py`, `test_launch_admin_list.py`, `test_launch_admin_list_presentation.py`, `test_launch_detail_navigation.py`, `test_launch_list_last_completed_column.py`, `test_launch_step_outcome_tags.py`, `test_launch_surface_vocabulary_rules.py`, `test_automation_pass.py`, `test_automation_pass_release.py`, `test_retained_results_read_live.py` | A free string today; `Provenance` validates no source. These will keep **passing** after the change unless `tasks.md` 7.4's grep catches them, which it is written to do. Flagged so they are not missed on the grounds that the suite stayed green. |

### Where no bearing test was found

- **`launch-clickup-sync`'s removed projection exclusion** (`tasks.md`
  6.2): no test was found, within the glob, asserting that gate metric
  conditions are excluded from projection. This is "**none was found by
  this search**", not "no such test exists" — the exclusion may be
  implemented without a test of its own, or asserted somewhere the token
  search did not reach.
- **`docs/domain-map.md` and `docs/deferred-work.md`** (`tasks.md` 6.3,
  6.4, 6.5): outside the test-path glob and outside this pass's search.

---

## Uncovered scenarios

Every one of the **155** `#### Scenario:` blocks in this change's nine
delta specs is accounted for in the table below. Two are accounted for as
uncovered:

| Capability | Scenario | Reason |
| --- | --- | --- |
| `launch-playbook` | *The seed runs once* | Uncovered before this change and still uncovered. `tests/integration/launch/test_playbook_seed.py`'s own docstring records why: forcing the seed revision to re-execute needs downgrade/upgrade cycling, and re-running `alembic upgrade head` at head is a no-op by construction — an assertion that cannot fail. Unchanged by this delta; not owed by this pass. |
| `launch-playbook` | *A malformed step is reported alongside a coherence violation* | **No covering test found by this search.** `test_launch_playbook.py`'s docstring points at `tests/unit/launch/infrastructure/test_playbook_loader.py`, which no longer exists in the tree. Unchanged by this delta — its subject is not touched by the change — so it is flagged for the implementer rather than covered here. "Not found by this search", not "no such test exists". |

No scenario is uncovered *because of* a `REMOVED` or `RENAMED` delta:
this change's four REMOVED requirements carry no scenarios of their own
(their content moves to the replacing ADDED requirements), and it carries
no `RENAMED` delta.

---

## Scenario-to-test map

**How to read the third column.** For a scenario this change *writes or
rewrites*, the named test was written by this pass and is verified — it
exists, it runs, and its first-run state is in the table above. For a
scenario this delta leaves textually unchanged (117 of the 155, because a
MODIFIED requirement restates its whole block), the named test is the
**existing** coverage, located by matching the scenario's wording against
test names and docstrings across the glob. Those mappings were spot-
checked, not individually verified; two known-approximate ones are marked
inline. They are informational — this pass owed no new test for them.

| Capability | Op | Scenario | Covered by |
| --- | --- | --- | --- |
| `launch-admin` | ADDED | An entry names when it occurred | tests/unit/launch/infrastructure/driving/test_launch_journal_page.py::test_a_journal_entry_names_what_occurred_when_and_what_caused_it |
| `launch-admin` | ADDED | An entry's row shows its subject, source and who recorded it as separate facts | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_an_entry_names_when_it_occurred_and_shows_subject_source_who |
| `launch-admin` | ADDED | A kind's facts are composed into the row's detail phrase | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_a_kinds_facts_are_composed_into_the_row_detail_phrase |
| `launch-admin` | ADDED | A detail phrase does not restate the subject | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_a_detail_phrase_does_not_restate_the_subject |
| `launch-admin` | ADDED | A metric step reads as a step | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_metric_step.py::test_a_metric_step_reads_as_a_step |
| `launch-admin` | ADDED | A sourceless entry's source column says system | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_a_sourceless_entrys_source_column_says_system |
| `launch-admin` | ADDED | A known actor resolves to their name by roster identifier | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_an_entrys_who_column_resolves_a_known_actor_to_their_name |
| `launch-admin` | ADDED | A known actor resolves to their name by ClickUp user id | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_an_entrys_who_column_resolves_a_known_actor_by_clickup_user_id |
| `launch-admin` | ADDED | An unresolvable actor renders as its raw value | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_an_entry_names_when_it_occurred_and_shows_subject_source_who |
| `launch-admin` | ADDED | An entry's row shows its label as a coloured kind tag and carries its category marker | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_an_entrys_label_renders_as_a_kind_tag |
| `launch-admin` | ADDED | A source renders as a plain, uncoloured tag | tests/unit/launch/infrastructure/driving/test_launch_admin_journal_table.py::test_a_source_renders_as_a_plain_uncoloured_tag |
| `launch-admin` | ADDED | Entries render newest first | tests/unit/launch/infrastructure/driving/test_launch_journal_page.py::test_journal_entries_render_newest_first |
| `launch-admin` | ADDED | An empty journal says so | tests/unit/launch/infrastructure/driving/test_launch_journal_page.py::test_an_empty_journal_says_so |
| `launch-clickup-sync` | MODIFIED | A human step gets a task | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_human_step_gets_a_task_named_from_its_name |
| `launch-clickup-sync` | MODIFIED | A step's description becomes the task's body | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_steps_description_becomes_the_tasks_body |
| `launch-clickup-sync` | MODIFIED | A task is assigned to the step's people | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_task_is_assigned_to_the_steps_people |
| `launch-clickup-sync` | MODIFIED | An existing unowned task gains its step's assignees | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_an_existing_unowned_task_gains_its_steps_assignees |
| `launch-clickup-sync` | MODIFIED | A person's own assignment change is not overwritten | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_persons_own_assignment_change_is_not_overwritten |
| `launch-clickup-sync` | MODIFIED | An assignee with no ClickUp account is reported, not silently dropped | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_an_assignee_with_no_clickup_account_is_reported_not_dropped |
| `launch-clickup-sync` | MODIFIED | A step activated mid-launch is projected | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_step_activated_mid_launch_is_projected |
| `launch-clickup-sync` | MODIFIED | A step activated mid-launch that the launch has not released is not projected | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_a_step_activated_mid_launch_that_is_not_released_is_not_projected |
| `launch-clickup-sync` | MODIFIED | A renamed task still resolves to its step | tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_a_renamed_task_still_resolves_to_its_step |
| `launch-clickup-sync` | MODIFIED | An unedited task follows the step's current wording | tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py::test_an_unedited_task_follows_the_steps_current_wording |
| `launch-clickup-sync` | MODIFIED | A person's body note survives a wording edit | tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py::test_a_persons_body_note_survives_a_wording_edit |
| `launch-clickup-sync` | MODIFIED | An unedited legacy task starts healing | tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py::test_an_unedited_legacy_task_starts_healing |
| `launch-clickup-sync` | MODIFIED | An ambiguous legacy task is never rewritten | tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py::test_an_ambiguous_legacy_task_is_never_rewritten |
| `launch-clickup-sync` | MODIFIED | An edited task name is never restored | tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_an_edited_task_name_is_never_restored |
| `launch-clickup-sync` | MODIFIED | An over-long name is shortened rather than failing | tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing |
| `launch-clickup-sync` | MODIFIED | An existing task is not recreated | tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated |
| `launch-clickup-sync` | MODIFIED | A prohibited-tactic step is never projected | tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected |
| `launch-clickup-sync` | MODIFIED | A deleted task for unfinished work is re-projected | tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected |
| `launch-clickup-sync` | MODIFIED | A deleted task for finished work stays gone | tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone |
| `launch-clickup-sync` | MODIFIED | Automated steps are never projected | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_automated_steps_are_never_projected |
| `launch-clickup-sync` | MODIFIED | A step that is not active is never projected | tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_step_that_is_not_active_is_never_projected |
| `launch-clickup-sync` | MODIFIED | An unreleased step is not projected | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_an_unreleased_step_is_not_projected |
| `launch-clickup-sync` | MODIFIED | A step is projected on the pass after the launch releases it | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_a_step_is_projected_on_the_pass_after_the_launch_releases_it |
| `launch-clickup-sync` | MODIFIED | A step waiting on another is not projected until that one is resolved | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_a_step_waiting_on_another_is_not_projected_until_it_is_resolved |
| `launch-clickup-sync` | MODIFIED | A step released by its dependency being retired is projected | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_a_step_released_by_its_dependency_being_retired_is_projected |
| `launch-clickup-sync` | MODIFIED | A task already created is not withdrawn | tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py::test_a_task_already_created_is_not_withdrawn |
| `launch-gate-progression` | MODIFIED | An automatic gate opens once its conditions are satisfied | tests/unit/launch/application/test_progress_launch.py::test_an_automatic_gate_opens_once_its_conditions_are_satisfied |
| `launch-gate-progression` | MODIFIED | Consecutive open gates are crossed in one pass | tests/unit/launch/application/test_progress_launch.py::test_consecutive_open_gates_are_crossed_in_one_pass |
| `launch-gate-progression` | MODIFIED | A launch with an unsatisfied condition is left where it is, silently | tests/unit/launch/infrastructure/driving/test_advance_and_ask.py::test_a_gate_with_an_unsatisfied_condition_is_left_alone_and_silently |
| `launch-gate-progression` | MODIFIED | A gate held by an unresolved metric step is left where it is | tests/unit/launch/application/test_progress_launch_metric_step.py::test_a_gate_held_by_an_unresolved_metric_step_is_left_where_it_is |
| `launch-gate-progression` | MODIFIED | Recording an outcome does not itself advance a launch | tests/unit/launch/application/test_recording_does_not_advance_a_launch.py::test_recording_an_outcome_does_not_itself_advance_a_launch |
| `launch-gate-progression` | MODIFIED | A ClickUp webhook delivery may trigger an advance-and-ask cascade for the launch it completes | tests/unit/launch/infrastructure/driving/test_advance_and_ask.py::test_the_trigger_runs_the_cascade_for_the_launch_it_names |
| `launch-gate-progression` | MODIFIED | A launch is not advanced past the final gate | tests/unit/launch/infrastructure/driving/test_advance_and_ask.py::test_the_final_gate_is_not_asked_about |
| `launch-instance` | MODIFIED | A launch position is created for an existing product | tests/unit/launch/domain/test_launch_run.py::test_starting_reports_a_launch_started_occurrence |
| `launch-instance` | MODIFIED | A launch position for an unknown product is rejected | tests/integration/launch/test_launch_repository.py::test_a_launch_for_an_unknown_product_is_rejected |
| `launch-instance` | MODIFIED | A second launch position for the same product is rejected | tests/integration/launch/test_launch_repository.py::test_a_second_launch_for_the_same_product_is_rejected |
| `launch-instance` | MODIFIED | A launch position is retrieved | tests/unit/launch/domain/test_metric_step_gate_obligations.py::test_a_launch_carries_no_attestations_to_persist_or_read_back (dropped half); tests/integration/launch/test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state (surviving half, fixture migration owed) |
| `launch-instance` | MODIFIED | A product without a launch position reports absence | tests/unit/launch/application/test_scope_aware_launch_reads.py::test_a_product_without_a_launch_position_reports_absence |
| `launch-instance` | MODIFIED | An out-of-scope launch reports the same absence | tests/unit/launch/application/test_scope_aware_launch_reads.py::test_an_out_of_scope_launch_reports_the_same_absence |
| `launch-instance` | MODIFIED | A satisfied step is recorded with its provenance | tests/unit/launch/domain/test_metric_step_gate_obligations.py::test_a_satisfied_step_is_recorded_with_its_provenance; ::test_the_declared_source_set_is_clickup_and_automated_alone |
| `launch-instance` | MODIFIED | A re-recorded outcome replaces the stored one without reopening gates | tests/unit/launch/domain/test_launch_run.py::test_a_re_recorded_outcome_replaces_the_stored_one_without_reopening_gates |
| `launch-instance` | MODIFIED | A prohibited-tactic step is refused | tests/unit/launch/domain/test_launch_run.py::test_a_prohibited_tactic_step_is_refused |
| `launch-instance` | MODIFIED | Satisfying a prohibited-tactic step is rejected | tests/unit/launch/domain/test_launch_run.py::test_satisfying_a_prohibited_tactic_step_is_rejected |
| `launch-instance` | MODIFIED | Refusing an ordinary step is rejected | tests/unit/launch/domain/test_launch_run.py::test_refusing_an_ordinary_step_is_rejected |
| `launch-instance` | MODIFIED | An unknown step identifier is rejected | tests/unit/launch/domain/test_outcomes_after_retirement.py::test_recording_for_a_step_absent_from_the_served_playbook_is_rejected |
| `launch-instance` | MODIFIED | An automatic gate opens when every blocking condition is satisfied | tests/unit/launch/domain/test_launch_gate_advance.py::test_an_automatic_gate_opens_when_every_blocking_condition_is_satisfied |
| `launch-instance` | MODIFIED | An advance with an unresolved blocking step is rejected | tests/unit/launch/domain/test_launch_gate_advance.py::test_an_advance_with_an_unresolved_blocking_step_is_rejected |
| `launch-instance` | MODIFIED | A refused prohibited-tactic step never holds a gate closed | tests/unit/launch/domain/test_launch_gate_advance.py::test_a_refused_prohibited_tactic_step_never_holds_a_gate_closed |
| `launch-instance` | MODIFIED | An advance moves to exactly the next gate | tests/unit/launch/domain/test_launch_gate_advance.py::test_an_advance_moves_to_exactly_the_next_gate |
| `launch-instance` | MODIFIED | An unresolved metric step holds its gate closed | tests/unit/launch/domain/test_metric_step_gate_obligations.py::test_an_unresolved_metric_step_holds_its_gate_closed |
| `launch-journal` | ADDED | A started launch is journaled | tests/unit/launch/application/test_launch_journal_appends.py::test_a_started_launch_is_journaled |
| `launch-journal` | ADDED | A recorded step outcome is journaled | tests/unit/launch/application/test_launch_journal_appends.py::test_a_recorded_step_outcome_is_journaled |
| `launch-journal` | ADDED | A non-terminal step outcome is journaled too | tests/unit/launch/application/test_launch_journal_appends.py::test_a_non_terminal_step_outcome_is_journaled_too |
| `launch-journal` | ADDED | An outcome recorded from any source is journaled alike | tests/unit/launch/application/test_launch_journal_appends.py::test_an_outcome_recorded_from_any_source_is_journaled_alike |
| `launch-journal` | ADDED | A recorded approval is journaled | tests/unit/launch/application/test_launch_journal_appends.py::test_a_recorded_approval_is_journaled |
| `launch-journal` | ADDED | A rejecting approval is journaled too | tests/unit/launch/application/test_launch_journal_appends.py::test_a_rejecting_approval_is_journaled_too |
| `launch-journal` | ADDED | A metric step's outcome is journaled as a step outcome | tests/unit/launch/application/test_metric_step_journalling.py::test_a_metric_steps_outcome_is_journaled_as_a_step_outcome |
| `launch-journal` | ADDED | An opened gate is journaled | tests/unit/launch/application/test_launch_journal_appends.py::test_an_opened_gate_is_journaled |
| `launch-journal` | ADDED | A graduation is journaled as a graduation | tests/unit/launch/application/test_launch_journal_appends.py::test_a_graduation_is_journaled_as_a_graduation |
| `launch-journal` | ADDED | A moved launch date is journaled | tests/unit/launch/application/test_launch_journal_appends.py::test_a_moved_launch_date_is_journaled |
| `launch-journal` | MODIFIED | An entry names the step as well as identifying it | tests/unit/launch/application/test_launch_journal_appends.py::test_an_entry_names_the_step_as_well_as_identifying_it |
| `launch-journal` | MODIFIED | A step renamed later does not change an appended entry | tests/unit/launch/application/test_launch_journal_appends.py::test_a_step_renamed_later_does_not_change_an_appended_entry |
| `launch-journal` | MODIFIED | A step retired later still reads by name | tests/unit/launch/application/test_launch_journal_appends.py::test_a_step_retired_later_still_reads_by_name |
| `launch-journal` | MODIFIED | A refused advance's conditions are stored as the domain names them | tests/unit/launch/application/test_launch_journal_appends.py::test_a_refused_advances_conditions_are_stored_as_the_domain_names_them |
| `launch-journal` | MODIFIED | A metric step is labelled by its name | tests/unit/launch/application/test_metric_step_journalling.py::test_a_metric_step_is_labelled_by_its_name |
| `launch-journal` | MODIFIED | A launch's journal is read most recent first | tests/integration/launch/test_launch_journal_live.py::test_a_launchs_journal_is_read_most_recent_first |
| `launch-journal` | MODIFIED | Entries naming the same moment report the later append first | tests/integration/launch/test_launch_journal_live.py::test_entries_naming_the_same_moment_report_the_later_append_first |
| `launch-journal` | MODIFIED | An entry reports its distinguishing facts as their own fields | tests/unit/launch/application/test_launch_journal_read.py::test_an_entry_reports_its_distinguishing_facts_as_their_own_fields |
| `launch-journal` | MODIFIED | A kind's distinguishing facts are absent from an entry of another kind | tests/unit/launch/application/test_metric_step_journalling.py::test_gate_id_leaves_the_entry_shape_with_its_only_populator |
| `launch-journal` | MODIFIED | An entry reports a label naming its kind | tests/unit/launch/application/test_launch_journal_categorization.py::test_an_entry_reports_a_label_naming_its_kind |
| `launch-journal` | MODIFIED | An entry reports its subject, source and actor as raw facts | `tests/unit/launch/application/test_launch_journal_read.py::test_an_entry_is_stored_as_facts` |
| `launch-journal` | MODIFIED | An occurrence naming no subject, source or actor reports each as absent | `tests/unit/launch/application/test_launch_journal_read.py::test_a_kinds_distinguishing_facts_are_absent_from_an_entry_of_another_kind` |
| `launch-journal` | MODIFIED | An entry reports a category | tests/unit/launch/application/test_launch_journal_categorization.py::test_an_entry_reports_a_category |
| `launch-journal` | MODIFIED | A rejecting approval categorizes as blocked | tests/unit/launch/application/test_launch_journal_categorization.py::test_a_rejecting_approval_categorizes_as_blocked |
| `launch-journal` | MODIFIED | An approving approval categorizes as judgment | tests/unit/launch/application/test_launch_journal_categorization.py::test_an_approving_approval_categorizes_as_judgment |
| `launch-journal` | MODIFIED | A blocked or refused step outcome categorizes as blocked | tests/unit/launch/application/test_launch_journal_categorization.py::test_a_blocked_or_refused_step_outcome_categorizes_as_blocked |
| `launch-journal` | MODIFIED | Every other step outcome categorizes as progression | tests/unit/launch/application/test_launch_journal_categorization.py::test_every_other_step_outcome_categorizes_as_progression |
| `launch-journal` | MODIFIED | An out-of-scope launch reports an empty journal | tests/unit/launch/application/test_launch_journal_read.py::test_an_out_of_scope_launch_reports_an_empty_journal |
| `launch-journal` | MODIFIED | A launch with nothing recorded reports an empty journal | tests/unit/launch/application/test_launch_journal_read.py::test_a_launch_with_nothing_recorded_reports_an_empty_journal |
| `launch-journal` | MODIFIED | A product with no launch record reports an empty journal | tests/unit/launch/application/test_launch_journal_read.py::test_a_product_with_no_launch_record_reports_an_empty_journal |
| `launch-playbook` | ADDED | A blocking step appears as a step obligation | tests/unit/launch/domain/test_gate_conditions_are_steps_alone.py::test_a_blocking_step_appears_as_a_step_obligation |
| `launch-playbook` | ADDED | A non-blocking step produces no condition | tests/unit/launch/domain/test_gate_conditions_are_steps_alone.py::test_a_non_blocking_step_produces_no_condition |
| `launch-playbook` | ADDED | A gate waits on nothing but its steps | tests/unit/launch/domain/test_gate_conditions_are_steps_alone.py::test_a_gate_carries_no_condition_of_any_other_kind |
| `launch-playbook` | ADDED | The shipped playbook loads with steps | tests/integration/launch/test_seeded_step_fields.py::test_the_playbook_loads_with_steps_after_the_backfill |
| `launch-playbook` | ADDED | BUILD THE LISTING is fully represented | tests/integration/launch/test_seeded_step_fields.py::test_build_the_listing_is_fully_represented |
| `launch-playbook` | ADDED | Every area is fully represented | tests/unit/launch/test_playbook_reference_set_metric_steps.py::test_every_area_is_fully_represented_with_no_exception |
| `launch-playbook` | ADDED | A step traces to its source row | tests/integration/launch/test_seeded_step_fields.py::test_a_step_traces_to_its_source_row |
| `launch-playbook` | ADDED | A step states its work without the source document | tests/integration/launch/test_seeded_step_fields.py::test_a_step_states_its_work_without_the_source_document |
| `launch-playbook` | ADDED | Every description re-derives from its reference row | `tests/unit/launch/test_playbook_reference_set.py::test_every_description_re_derives_from_its_row`; `tests/unit/launch/test_playbook_reference_set.py::test_no_other_character_is_stripped` |
| `launch-playbook` | ADDED | A name is short enough to title a task | tests/unit/launch/test_playbook_reference_set.py::test_every_name_is_a_single_short_line |
| `launch-playbook` | ADDED | A row's leading marker survives into its name | tests/unit/launch/test_playbook_reference_set.py::test_a_rows_leading_marker_survives_into_its_name |
| `launch-playbook` | ADDED | A threshold row is seeded as a blocking metric step | tests/unit/launch/test_playbook_reference_set_metric_steps.py::test_a_threshold_row_is_seeded_as_a_blocking_metric_step; tests/integration/launch/test_metric_steps_after_preparation.py::test_each_of_the_six_carries_its_metric_identifier |
| `launch-playbook` | ADDED | A row merely mentioning a number is an ordinary step | tests/unit/launch/test_playbook_reference_set_metric_steps.py::test_a_row_merely_mentioning_a_number_is_an_ordinary_step; tests/integration/launch/test_metric_steps_after_preparation.py::test_no_other_prepared_step_gained_a_metric_identifier |
| `launch-playbook` | ADDED | A metric identifier names the quantity alone | tests/unit/launch/test_playbook_reference_set_metric_steps.py::test_a_metric_identifier_names_the_quantity_alone |
| `launch-playbook` | ADDED | The seed runs once | **UNCOVERED** — see *Uncovered scenarios* |
| `launch-playbook` | ADDED | Gate sequence deviates from the specification | tests/unit/launch/domain/test_launch_playbook.py::test_gate_sequence_with_an_extra_gate_is_rejected |
| `launch-playbook` | ADDED | A gate's opening mode disagrees with the specification | tests/unit/launch/domain/test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected |
| `launch-playbook` | ADDED | Duplicate step identifier | tests/unit/launch/domain/test_launch_playbook.py::test_duplicate_step_identifier_is_rejected |
| `launch-playbook` | ADDED | Step references an unknown gate | tests/unit/launch/domain/test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected |
| `launch-playbook` | ADDED | A step with no name is rejected by identifier | tests/unit/launch/domain/test_playbook_coherence_by_status.py::test_the_name_is_required_rather_than_defaulted |
| `launch-playbook` | ADDED | A name spanning several lines is rejected | tests/unit/launch/domain/test_playbook_coherence_by_status.py::test_a_name_spanning_several_lines_is_rejected |
| `launch-playbook` | ADDED | A description spanning several lines is accepted | tests/unit/launch/domain/test_playbook_coherence_by_status.py::test_a_description_spanning_several_lines_is_accepted |
| `launch-playbook` | ADDED | A sole assignee who is also the confirmer fails to load | tests/unit/launch/domain/test_confirmer_assignee_coherence.py::test_a_sole_assignee_who_is_also_the_confirmer_fails_to_load |
| `launch-playbook` | ADDED | A prohibited tactic cannot block a gate | `tests/unit/launch/domain/test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected` |
| `launch-playbook` | ADDED | A gate with no active blocking step is rejected | `tests/unit/launch/domain/test_playbook_readiness.py::test_a_gate_with_no_active_blocking_step_is_not_rejected_at_load` (the load half); `::test_no_gate_opens_for_free_in_a_playbook_served_to_a_launch` (the serve half) |
| `launch-playbook` | ADDED | Multiple violations are reported together | tests/unit/launch/domain/test_playbook_readiness.py::test_two_faults_in_a_not_ready_set_are_still_reported_together |
| `launch-playbook` | ADDED | A malformed step is reported alongside a coherence violation | **NOT FOUND by this search** — see *Uncovered scenarios* |
| `launch-playbook` | ADDED | A coherent playbook loads | tests/unit/launch/domain/test_playbook_readiness.py::test_a_coherent_but_unready_playbook_exposes_its_gates_and_steps |
| `launch-playbook` | MODIFIED | A step definition is read back with every declared attribute | tests/unit/launch/domain/test_step_metric_identifier.py::test_an_authored_metric_identifier_is_read_back; ::test_an_unauthored_metric_identifier_reads_back_as_absent |
| `launch-playbook` | MODIFIED | Steps can be selected by gate and by scope | tests/unit/launch/domain/test_step_definition_field_set.py::test_steps_can_be_selected_by_gate_and_by_scope |
| `launch-playbook` | MODIFIED | A metric identifier names no defined metric | tests/unit/launch/domain/test_step_metric_identifier.py::test_a_metric_identifier_naming_no_defined_metric_still_loads |
| `launch-playbook` | MODIFIED | A metric identifier does not change how a step resolves | tests/unit/launch/domain/test_step_metric_identifier.py::test_a_metric_identifier_does_not_change_how_a_step_resolves |
| `launch-step-automation` | MODIFIED | The product is supplied, not fetched | tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py::test_the_product_is_supplied_not_fetched |
| `launch-step-automation` | MODIFIED | A produced outcome is attributed to the handler | tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py::test_a_produced_outcome_is_attributed_to_the_handler |
| `launch-step-automation` | MODIFIED | A handler cannot claim another source | tests/unit/launch/application/test_handler_source_claim_after_attestation.py::test_a_handler_cannot_claim_a_surviving_source (new); tests/unit/launch/application/test_step_handler_contract.py::test_a_resolution_has_no_place_to_put_provenance (existing, fixture migration owed) |
| `launch-step-automation` | MODIFIED | A finding changes nothing about the outcome or the result | tests/unit/launch/infrastructure/driving/test_automation_pass_finding.py::test_a_finding_changes_nothing_about_the_outcome_or_the_result |
| `playbook-admin` | MODIFIED | The form offers name and description separately | tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py::test_the_form_offers_name_and_description_separately |
| `playbook-admin` | MODIFIED | Assignees are chosen from the roster | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_assignees_are_chosen_from_the_rosters_active_people |
| `playbook-admin` | MODIFIED | A form rejected by validation shows every fault with the typed values | tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py::test_a_form_rejected_by_validation_shows_every_fault_with_the_typed_values |
| `playbook-admin` | MODIFIED | The form offers both start fields | tests/unit/launch/infrastructure/driving/test_playbook_admin_start_fields.py::test_the_form_offers_both_start_fields |
| `playbook-admin` | MODIFIED | Starting immediately is an offered choice | tests/unit/launch/infrastructure/driving/test_playbook_admin_start_fields.py::test_starting_immediately_is_an_offered_choice |
| `playbook-admin` | MODIFIED | The dependency control is grouped and self-excluding | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_the_dependency_control_is_grouped_and_self_excluding |
| `playbook-admin` | MODIFIED | A multi-valued control clears without a modifier key | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_each_multi_valued_control_renders_a_control_per_value |
| `playbook-admin` | MODIFIED | What is chosen is rendered apart from the options and names its field | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_what_is_chosen_is_rendered_apart_from_the_options_and_names_its_field |
| `playbook-admin` | MODIFIED | Every value has its own control among the options | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_every_value_has_its_own_control_among_the_options |
| `playbook-admin` | MODIFIED | An empty set says so | `tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py` — **mapping not individually verified**, see the caveat below |
| `playbook-admin` | MODIFIED | An emptied control still submits its key | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_an_emptied_control_still_submits_its_key |
| `playbook-admin` | MODIFIED | A cleared control stays cleared when the write is rejected | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_a_cleared_control_stays_cleared_when_the_write_is_rejected |
| `playbook-admin` | MODIFIED | A submission omitting the key means the empty set | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_a_submission_omitting_the_key_means_the_empty_set |
| `playbook-admin` | MODIFIED | A fault mark cannot be hidden by what the author did to the options | tests/unit/launch/infrastructure/driving/test_playbook_admin_multi_value_controls.py::test_a_fault_mark_renders_outside_what_the_options_are_scrolled_within |
| `playbook-admin` | MODIFIED | The form offers the metric identifier | tests/unit/launch/infrastructure/driving/test_playbook_admin_metric_identifier_field.py::test_the_form_offers_the_metric_identifier; ::test_the_metric_input_carries_what_the_step_declares_and_nothing_where_none_is |
| `playbook-authoring` | MODIFIED | A created step joins the served set | tests/unit/launch/application/test_playbook_authoring_new_field_set.py::test_creating_a_draft_requires_only_what_a_draft_carries |
| `playbook-authoring` | MODIFIED | Created identifiers never collide with the seeded namespace | tests/unit/launch/application/test_playbook_authoring_new_field_set.py::test_created_identifiers_never_collide_retired_included |
| `playbook-authoring` | MODIFIED | A step is created declaring when it starts | tests/unit/launch/application/test_step_dependency_preconditions.py::test_a_step_is_created_declaring_when_it_starts |
| `playbook-authoring` | MODIFIED | A step is created declaring neither | tests/unit/launch/application/test_step_dependency_preconditions.py::test_a_step_is_created_declaring_neither |
| `playbook-authoring` | MODIFIED | The framework is not writable | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_the_framework_is_not_writable |
| `playbook-authoring` | MODIFIED | A threshold is editable as the step that states it | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_a_threshold_is_editable_as_the_step_that_states_it |
| `playbook-authoring` | ADDED | A step is created declaring a metric identifier | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_a_step_is_created_declaring_a_metric_identifier |
| `playbook-authoring` | ADDED | A step's metric identifier is changed | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_a_steps_metric_identifier_is_changed |
| `playbook-authoring` | ADDED | A step is created declaring no metric identifier | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_a_step_is_created_declaring_no_metric_identifier |
| `playbook-authoring` | ADDED | An invalid metric identifier is rejected | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_an_invalid_metric_identifier_is_rejected |
| `playbook-authoring` | ADDED | An identifier naming no defined metric is accepted | tests/unit/launch/application/test_step_metric_identifier_authoring.py::test_an_identifier_naming_no_defined_metric_is_accepted |

---

## Unresolved project questions

Recorded here rather than asked, because a dispatched subagent has no
channel to ask on. Each names the assumption taken and the tests that
depend on it.

1. **`uv run mypy .` is not green in this worktree (51 pre-existing
   errors), yet `pre-commit` runs it on every commit.** Either the hook
   is being bypassed or the errors are tolerated; nothing in `AGENTS.md`
   says which. **Assumption taken:** mypy cleanliness is not a gate this
   pass must meet, so the new tests were held to the same standard as
   their neighbours — `ruff check` and `ruff format` clean, mypy
   consistent with the surrounding files. **Depends on it:** all ten new
   mypy errors from this pass, every one of which is an absent-target
   error (`"StepDefinition" has no attribute "metric_id"`,
   `Unexpected keyword argument "metric_id"`,
   `Item "MetricCondition" … has no attribute "step_id"`) and resolves
   when the implementation lands, plus one
   `Module … has no attribute "playbook_admin"` that matches a shape
   already present in ~8 sibling files.

2. **`AGENTS.md`'s integration-tier instruction ("create and migrate
   `commerce_ops_test` once by hand") leaves a database the preparation
   step has not been run against**, which `tasks.md` 6.5 records as a
   pre-existing gap this change widens from 245 steps to 251.
   **Assumption taken:** the tier's database is expected to be *migrated
   **and** prepared*, and a test finding a migrate-only one should say so
   rather than fail obscurely. **Depends on it:** all three tests in
   `tests/integration/launch/test_metric_steps_after_preparation.py`,
   through `_seeded()`'s 107-step guard.

3. **`tasks.md` 1.2 says "the six metric identifiers"; `proposal.md`'s
   Impact enumerates five** (`units-fulfillable`, `sales-velocity`,
   `organic-share`, `tacos`, `review-rating`) across three gates, for six
   rows. Whether two rows share an identifier, or whether a sixth exists
   that the Impact paragraph omits, is not settled by the artifacts.
   **This is reported as a possible defect in the change's planning
   artifacts, not acted on** — revising them belongs to
   `openspec-update-change`. **Assumption taken:** no test asserts the
   row-to-identifier mapping at all (see *Deliberately untested*), so no
   test depends on the answer. Whichever way it resolves, the tests as
   written stay correct.

4. **How the six rows' metric identifiers reach the database is
   `tasks.md` 3.2's "teach `seed_playbook.py` to read and insert
   `metric_id`".** No artifact fixes the YAML key or the column name.
   **Assumption taken:** `metric_id` for both, which is what `tasks.md`
   2.1 / 2.2 / 3.2 spell. **Depends on it:**
   `test_playbook_reference_set_metric_steps.py` (the YAML key) and
   `test_metric_steps_after_preparation.py` (the read-back attribute).

5. **The project records no convention for where a test's assertion
   provenance is written down.** **Assumption taken:** inline
   `SPECIFIED` / `DERIVED` comments plus a module docstring section,
   which is the established practice in every recent test file in this
   tree. **Depends on it:** the readability of the provenance record, not
   any assertion.

---

## Also read

The library's `rules/` fragment directs this file be read before
implementing. Its import path is machine-local, so this manifest's
location is stated a second time, deliberately:

    openspec/changes/replace-metric-conditions-with-steps/test-manifest.md
