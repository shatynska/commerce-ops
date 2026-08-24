# Test manifest — move-playbook-steps-to-postgres

Written by the test-writer pass, before any implementation of this change
exists. Derived strictly from this change's delta specs; no implementation
source was read. **This manifest is not an artifact the OpenSpec schema
knows about**: it will not appear among `openspec instructions apply`'s
context files and must be read deliberately by whoever implements the
change.

## Baseline

Recorded before any new test was written:

- `uv run pytest tests/unit tests/agents` — **636 passed, 0 failed**
  (scoped to the commit-time tiers; scope per `AGENTS.md`).
- `tests/integration` was **not run**: it needs a live Postgres and
  `DATABASE_URL` is unset in this environment. Every claim below about
  integration tests is therefore about their expected behavior, not an
  observed run.

First-run results of the new tests (observed after writing):

- `tests/unit/launch/application/test_playbook_authoring.py` — collection
  fails with `ImportError: cannot import name 'create_step'` — the
  absent-target state; the assertions have not been exercised.
- `tests/unit/launch/domain/test_gate_holding_floor.py` — 3 failed
  (construction succeeds where the not-yet-existing floor rule must make
  it raise), 1 passed (`test_a_playbook_with_every_gate_held_constructs`,
  expected: a fully held playbook is coherent under current rules too).
- `tests/unit/launch/domain/test_outcomes_after_retirement.py` — 2 passed.
  Target-exists case, documented in the file: the aggregate already
  rejects identifiers absent from the playbook passed in; this change
  redefines what is passed. These pin that behavior.
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py`
  — 4 failed (no retained-composition machinery exists), 2 passed
  (`test_an_ambiguous_legacy_task_is_never_rewritten`,
  `test_an_edited_task_name_is_never_restored` — the current
  never-rewrite-anything behavior is a superset of the revised guarantee;
  the healing tests are the discriminating half).
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_retired_steps.py`
  — 2 failed (**discriminating**: the current reconciliation records an
  outcome for a mapped task even when the playbook no longer defines its
  step — exactly the behavior the ADDED requirement forbids), 2 passed
  (outward direction: the current pass already leaves unmapped-in-playbook
  tasks alone; pinned).
- The two integration files were not executed (no `DATABASE_URL`); both
  fail at import regardless until the adapter module exists.

`uv run ruff check` and `uv run ruff format` are clean over the seven new
files. `mypy` was not run: it fails on the deliberately absent imports,
which is the same absent-target fact pytest already reports.

## Properties the dispatcher can rely on

- **This pass is additive only**: no existing test file was edited,
  deleted, or disabled — under any delta operation. The only file written
  outside `tests/**/test_*.py` is this manifest.
- **No implementation was written**: no module, stub, or `__all__` entry
  was created to make the failing tests execute. Their failure is the
  expected, reported outcome.

## New test files

- `tests/unit/launch/domain/test_gate_holding_floor.py`
- `tests/unit/launch/domain/test_outcomes_after_retirement.py`
- `tests/unit/launch/application/test_playbook_authoring.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py`
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_retired_steps.py`
- `tests/integration/launch/test_playbook_seed.py`
- `tests/integration/launch/test_playbook_authoring_live.py`

All test names below are runner-selectable
(`uv run pytest <file>::<test_name>`).

## Scenario accounting

Every `#### Scenario:` block of the change's delta specs, each accounted
exactly once. 88 scenarios total: 31 (launch-playbook) + 12
(playbook-authoring) + 27 (launch-clickup-sync) + 15 (launch-instance)
+ 3 (launch-entry). "Existing:" names a pre-existing test that covers a
scenario this MODIFIED delta restates without behavioral change at that
test's level — those tests stay authoritative and are not duplicated.

### launch-playbook — Requirement: Playbooks are versioned (MODIFIED)

1. **The loaded playbook reports its version** — split:
   `tests/unit/launch/domain/test_launch_playbook.py::test_playbook_reports_the_version_it_was_authored_with`
   (existing, construction half) +
   `tests/integration/launch/test_playbook_seed.py::test_the_served_playbook_reports_a_version_identifier`
   (new, serving half).
2. **A launch records the version it started under** — split: existing
   `tests/unit/launch/domain/test_launch_run.py::test_starting_reports_a_launch_started_occurrence`
   (the recording mechanics: the stamp is the passed playbook's version)
   + the no-read-branches half by
   `tests/integration/launch/test_playbook_authoring_live.py::test_a_stale_version_stamp_does_not_freeze_the_read`.
   The universal negative "no subsequent read of the playbook branches on
   it" is not exhaustively testable; the stale-stamp read is its
   strongest observable instance. Remainder: deliberately untested,
   recorded here.
3. **An authored change changes the served version identifier** —
   `tests/integration/launch/test_playbook_authoring_live.py::test_an_authored_change_changes_the_served_version_identifier`
   (new); the write-side mechanism (conditional persistence on the loaded
   set-version) by
   `tests/unit/launch/application/test_playbook_authoring.py::test_an_accepted_write_persists_conditionally_on_the_loaded_version`.
4. **An authored change reaches a launch already in flight** —
   `tests/integration/launch/test_playbook_authoring_live.py::test_a_stale_version_stamp_does_not_freeze_the_read`
   (new).

### launch-playbook — Requirement: An incoherent playbook is rejected at load time (MODIFIED)

5. **Gate sequence deviates from the specification** — existing:
   `test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`
   / `..._with_an_extra_gate_...` / `..._in_the_wrong_order_...` /
   `..._repeating_a_position_...` (unchanged rule).
6. **A gate's opening mode disagrees with the specification** — existing:
   `test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected`.
7. **Duplicate step identifier** — existing:
   `test_launch_playbook.py::test_duplicate_step_identifier_is_rejected`.
8. **Step references an unknown gate** — existing:
   `test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected`.
9. **A step with no description is rejected by name** — existing:
   `tests/unit/launch/domain/test_step_description.py::test_a_step_with_an_empty_description_is_rejected_by_name`
   and `test_step_description_whitespace.py::test_a_whitespace_only_description_is_rejected_by_name`.
10. **A description spanning several lines is rejected** — existing:
    `test_step_description.py::test_a_description_spanning_several_lines_is_rejected`.
11. **Automation without a decided rule** — existing:
    `test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected`
    / `..._ai_assisted_...`.
12. **A prohibited tactic cannot block a gate** — existing:
    `test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`.
13. **A lesson cannot block a gate** — existing:
    `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_lesson_step_marked_blocking_is_rejected`.
14. **A gate with no blocking step is rejected** (new rule) —
    `tests/unit/launch/domain/test_gate_holding_floor.py::test_a_gate_with_no_step_at_all_is_rejected_naming_the_gate`
    and `::test_a_gate_with_only_non_blocking_steps_is_rejected` (new);
    aggregation with other faults by
    `::test_the_floor_fault_is_reported_alongside_another_fault`.
15. **A malformed metric condition is rejected** — existing:
    `test_playbook_coherence_completion.py::test_a_metric_condition_with_an_empty_threshold_is_rejected`.
16. **Multiple violations are reported together** — existing:
    `test_launch_playbook.py::test_two_distinct_violations_are_reported_together`;
    extended to the new rule by
    `test_gate_holding_floor.py::test_the_floor_fault_is_reported_alongside_another_fault`.
17. **A malformed step is reported alongside a coherence violation** —
    currently covered by
    `tests/unit/launch/infrastructure/test_playbook_loader.py` (the file
    boundary), which is an **obsolete-test candidate** below. ⚠ When the
    YAML loader is removed, this scenario's coverage must be re-homed to
    wherever malformed stored rows surface (the Postgres adapter's read,
    or write validation). Recorded as **uncovered at the post-change
    level, with this reason** — flagged for the implementation step.
18. **A coherent playbook loads** (as revised: coherent now includes the
    floor) —
    `test_gate_holding_floor.py::test_a_playbook_with_every_gate_held_constructs`
    (new). The pre-floor half remains in existing
    `test_launch_playbook.py::test_a_coherent_playbook_loads`, whose
    fixture the floor invalidates — see *Impacted fixtures*.

### launch-playbook — Requirement: The shipped playbook carries the authored step set (MODIFIED → seed requirement)

All in `tests/integration/launch/test_playbook_seed.py` (new), reading
the served playbook from the seeded database and filtering to the `lp.*`
namespace:

19. **The shipped playbook loads with steps** —
    `::test_the_playbook_loads_with_steps_after_seeding`.
20. **BUILD THE LISTING is fully represented** —
    `::test_build_the_listing_is_fully_represented`.
21. **A step traces to its source row** —
    `::test_every_seeded_step_traces_to_its_source_row`.
22. **A step states its work without the source document** —
    `::test_every_seeded_step_states_its_work`.
23. **Every description re-derives from its reference row** —
    `::test_every_description_re_derives_from_its_reference_row`.
24. **A gate-authored condition is not duplicated as a step** —
    `::test_gate_authored_conditions_are_not_duplicated_as_steps`.
25. **The seed runs once** — **uncovered, with reason**: forcing the seed
    revision to re-execute requires downgrade/upgrade cycling around an
    Alembic revision identifier that does not exist yet, and re-running
    `alembic upgrade head` while already at head is a no-op by
    construction — an assertion that cannot fail establishes nothing.
    Recommended once `tasks.md` 2.3 lands: an integration test that
    stamps the database below the seed revision (leaving the populated
    tables in place) and upgrades again, asserting no re-seed and no
    overwrite of an authored edit.

### launch-playbook — Requirement: Every gate is held by at least one blocking step (MODIFIED)

26. **No gate opens for free** — three-part coverage matching "at seed,
    and after every authored change":
    `test_gate_holding_floor.py::test_a_playbook_with_every_gate_held_constructs`
    (construction invariant),
    `test_playbook_authoring.py::test_retiring_a_gates_last_blocking_step_is_rejected`
    (after every write),
    `test_playbook_seed.py::test_no_gate_opens_for_free_in_the_served_set`
    (at seed, served).

### launch-playbook — Requirement: The authored set exercises the full step vocabulary (MODIFIED — seed-only)

All in `tests/integration/launch/test_playbook_seed.py` (new):

27. **Anchor kinds are all present** —
    `::test_every_timing_anchor_kind_is_represented`.
28. **Every discipline appears** — `::test_every_discipline_is_represented`.
29. **Execution modes and the compliance hazard are represented** —
    `::test_execution_modes_and_the_compliance_hazard_are_represented`.
30. **Prohibited tactics are present and never block** —
    `::test_prohibited_tactics_are_present_and_never_block`.
31. **Outstanding rule-policy decisions stay visible** (now "over the
    served playbook") —
    `::test_outstanding_rule_policy_decisions_stay_visible`.

### playbook-authoring (ADDED)

32. **A created step joins the served set** — split:
    `test_playbook_authoring.py::test_a_created_step_is_persisted_with_identifier_and_authorship`
    (identifier, namespace, authorship provenance) +
    `test_playbook_authoring_live.py::test_a_created_step_joins_the_served_set`
    (served on next read).
33. **Created identifiers never collide with the seeded namespace** —
    `test_playbook_authoring.py::test_created_identifiers_never_collide_retired_included`.
34. **An edit is served on the next read** — split:
    `test_playbook_authoring.py::test_an_update_replaces_fields_under_the_unchanged_identifier`
    + `test_playbook_authoring_live.py::test_an_edit_is_served_on_the_next_read`.
35. **A discipline change is rejected** —
    `test_playbook_authoring.py::test_a_discipline_change_is_rejected`.
36. **An edit to a seeded step keeps its citation and gains attribution** —
    `test_playbook_authoring.py::test_an_edit_to_a_seeded_step_keeps_its_citation_and_is_attributed`.
37. **A retired step leaves the served set** — split:
    `test_playbook_authoring.py::test_retiring_marks_the_step_and_deletes_nothing`
    + `test_playbook_authoring_live.py::test_a_retired_step_leaves_and_rejoins_the_served_set`.
38. **A retired step's history stays readable** —
    `test_outcomes_after_retirement.py::test_outcomes_recorded_before_retirement_stay_readable`
    (aggregate half); the stored-rows half is general rehydration,
    existing:
    `tests/integration/launch/test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state`.
39. **An un-retired step rejoins the served set** — split:
    `test_playbook_authoring.py::test_unretiring_restores_the_step_and_is_attributed`
    + `test_playbook_authoring_live.py::test_a_retired_step_leaves_and_rejoins_the_served_set`.
40. **A rejected write reports all faults and persists nothing** —
    `test_playbook_authoring.py::test_a_rejected_write_reports_all_faults_and_persists_nothing`.
41. **Retiring a gate's last blocking step is rejected** —
    `test_playbook_authoring.py::test_retiring_a_gates_last_blocking_step_is_rejected`.
42. **What a write cannot persist, a load cannot see** —
    `test_playbook_authoring.py::test_the_set_after_accepted_writes_loads_coherently`;
    every read in `test_playbook_authoring_live.py` exercises it against
    the real store. The *concurrent*-writes half (`design.md` Decision
    7's race) is **deliberately untested**: not deterministically
    observable through these seams; the conditional-persistence unit
    assertion is its proxy.
43. **The framework is not writable** —
    `test_playbook_authoring.py::test_the_authoring_surface_offers_no_framework_write`
    (surface enumeration + signature check; partially DERIVED — see
    classifications).

### launch-clickup-sync — Requirement: Human-attested steps are projected as tasks (MODIFIED)

44. **A human-attested step gets a task** — existing:
    `test_clickup_sync_projection.py::test_a_human_attested_step_gets_a_task`
    and `test_clickup_task_naming.py::test_a_projected_task_is_named_description_then_identifier`.
45. **A step authored mid-launch is projected** (new) —
    `test_clickup_sync_wording_heal.py::test_a_step_authored_mid_launch_is_projected`.
46. **A renamed task still resolves to its step** — existing:
    `test_clickup_task_naming.py::test_a_renamed_task_still_resolves_to_its_step`.
47. **An unedited task follows the step's current wording** (new) —
    `test_clickup_sync_wording_heal.py::test_an_unedited_task_follows_the_steps_current_wording`.
48. **A person's body note survives a wording edit** (new) —
    `test_clickup_sync_wording_heal.py::test_a_persons_body_note_survives_a_wording_edit`.
49. **An unedited legacy task starts healing** (new) —
    `test_clickup_sync_wording_heal.py::test_an_unedited_legacy_task_starts_healing`.
50. **An ambiguous legacy task is never rewritten** (new) —
    `test_clickup_sync_wording_heal.py::test_an_ambiguous_legacy_task_is_never_rewritten`.
51. **An edited task name is never restored** (revised) —
    `test_clickup_sync_wording_heal.py::test_an_edited_task_name_is_never_restored`
    (restated over the retained-composition machinery); the pre-change
    formulation stays covered by existing
    `test_clickup_task_naming.py::test_an_edited_task_name_is_never_restored`,
    which remains valid under the revision (see obsolete list, entry O-9).
52. **An over-long name is shortened rather than failing** — existing:
    `test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`.
53. **An existing task is not recreated** — existing:
    `test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated`.
54. **A prohibited-tactic step is never projected** — existing:
    `test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected`.
55. **A deleted task for unfinished work is re-projected** — existing:
    `test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected`.
56. **A deleted task for finished work stays gone** — existing:
    `test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone`.
57. **Automated and ai-assisted steps are never projected** — existing:
    `test_clickup_sync_projection.py::test_automated_and_ai_assisted_steps_are_never_projected`.

### launch-clickup-sync — Requirement: Completion flows from ClickUp… (MODIFIED)

The delta's change to this requirement is one sentence (recordings apply
only to steps the served playbook defines — the retired-step routing),
covered under scenarios 67–70. The five restated scenarios are unchanged:

58. **A closed task records Satisfied** — existing:
    `test_clickup_webhook.py::test_a_closed_task_records_satisfied`.
59. **A reopened task records InProgress** — existing:
    `test_clickup_webhook.py::test_a_reopened_task_records_in_progress`.
60. **A reopening without an observed closing records nothing** — existing:
    `test_clickup_webhook.py::test_a_reopening_without_an_observed_closing_records_nothing`.
61. **A repeated delivery changes nothing** — existing:
    `test_clickup_webhook.py::test_a_repeated_delivery_changes_nothing`.
62. **The system never closes a task** — existing:
    `test_clickup_sync_reconciliation.py::test_the_system_never_closes_a_task`.

### launch-clickup-sync — Requirement: The reconciliation pass records… (MODIFIED)

Same single-sentence change; the four restated scenarios are unchanged:

63. **A missed completion is recorded on reconciliation** — existing:
    `test_clickup_sync_reconciliation.py::test_a_missed_completion_is_recorded_on_reconciliation`.
64. **A missed reopening is recorded on reconciliation** — existing:
    `test_clickup_sync_reconciliation.py::test_a_missed_reopening_is_recorded_on_reconciliation`.
65. **No transition means no recording** — existing:
    `test_clickup_sync_reconciliation.py::test_no_transition_means_no_recording`.
66. **Reconciliation never overwrites other recording paths** — existing:
    `test_clickup_sync_reconciliation.py::test_reconciliation_never_overwrites_other_recording_paths`.

### launch-clickup-sync — Requirement: A retired step leaves the loop (ADDED)

All in
`tests/unit/launch/infrastructure/driven/test_clickup_sync_retired_steps.py`
(new):

67. **A retired step's task is left unmanaged** —
    `::test_a_retired_steps_task_is_left_unmanaged`.
68. **A retired step's closure is not recorded** —
    `::test_a_retired_steps_closure_is_not_recorded` (reconciliation
    path). Webhook path: jointly covered by
    `test_outcomes_after_retirement.py::test_recording_for_a_step_absent_from_the_served_playbook_is_rejected`
    (recording against a retired identifier is impossible); how the
    webhook *surfaces* that rejection (quiet skip vs. error response) is
    unspecified by the delta — unresolved project question Q8.
69. **A closure during retirement is never replayed** —
    `::test_a_closure_during_retirement_is_never_replayed`.
70. **An un-retired step resumes through its existing task** —
    `::test_an_unretired_step_resumes_through_its_existing_task`.

### launch-instance (MODIFIED — pinned → served; mechanics unchanged at these tests' level)

The delta replaces "the pinned playbook version" with "the served
playbook" as the validation and stamping referent. At the aggregate and
repository level the mechanics are the playbook object passed in; what
changes is composition (which playbook is served), covered under
scenarios 3, 4, and the new retired-identifier nuance in scenario 82.

71. **A launch position is created for an existing product** — existing:
    `test_launch_repository.py::test_a_started_launch_is_persisted_for_an_existing_product`
    (+ `test_launch_run.py::test_starting_reports_a_launch_started_occurrence`).
72. **A launch position for an unknown product is rejected** — existing:
    `test_launch_repository.py::test_a_launch_for_an_unknown_product_is_rejected`.
73. **A second launch position for the same product is rejected** —
    existing: `test_launch_repository.py::test_a_second_launch_for_the_same_product_is_rejected`.
74. **A launch position is retrieved** — existing:
    `test_launch_repository.py::test_a_launch_is_retrieved_with_its_full_recorded_state`.
75. **A product without a launch position reports absence** — existing:
    `test_launch_repository.py::test_a_product_without_a_launch_reports_absence`,
    `test_scope_aware_launch_reads.py::test_a_product_without_a_launch_position_reports_absence`.
76. **An out-of-scope launch reports the same absence** — existing:
    `test_scope_aware_launch_reads.py::test_an_out_of_scope_launch_reports_the_same_absence`.
77. **A satisfied step is recorded with its provenance** — existing:
    `test_launch_run.py::test_a_satisfied_step_is_recorded_with_its_provenance`.
78. **A re-recorded outcome replaces the stored one without reopening
    gates** — existing:
    `test_launch_run.py::test_a_re_recorded_outcome_replaces_the_stored_one_without_reopening_gates`.
79. **A prohibited-tactic step is refused** — existing:
    `test_launch_run.py::test_a_prohibited_tactic_step_is_refused`.
80. **Satisfying a prohibited-tactic step is rejected** — existing:
    `test_launch_run.py::test_satisfying_a_prohibited_tactic_step_is_rejected`.
81. **Refusing an ordinary step is rejected** — existing:
    `test_launch_run.py::test_refusing_an_ordinary_step_is_rejected`.
82. **An unknown step identifier is rejected** (revised: "an identifier
    that never existed and a retired step's alike") — existing
    `test_launch_run.py::test_an_unknown_step_identifier_is_rejected`
    (never-existed half) + new
    `test_outcomes_after_retirement.py::test_recording_for_a_step_absent_from_the_served_playbook_is_rejected`
    (retired half, with pre-retirement outcomes staying readable).
83. **An attested metric condition counts as satisfied** — existing:
    `test_launch_gate_advance.py::test_an_attested_metric_condition_counts_as_satisfied`.
84. **An unattested metric condition keeps the gate closed** — existing:
    `test_launch_gate_advance.py::test_an_unattested_metric_condition_keeps_the_gate_closed`.
85. **An attestation for a condition the gate does not author is
    rejected** — existing:
    `test_launch_gate_advance.py::test_an_attestation_for_a_condition_the_gate_does_not_author_is_rejected`.
    Like 82, "the served playbook does not author" is a composition
    change; a *retired-analogue* does not arise (metric conditions are
    code-owned and not retirable).

### launch-entry (MODIFIED — records the served version instead of "the version the build ships")

The behavioral content at these tests' level (register + start + confirm,
version never user input) is unchanged; the stamp's referent becomes the
served playbook, covered by scenarios 2–4 above. The integration fixture
`test_slack_entry_start.py` currently supplies the playbook via
`load_shipped_playbook` and is an impacted fixture (see below).

86. **A launch is started with a date** — existing:
    `tests/integration/launch/test_slack_entry_start.py::test_a_launch_is_started_with_a_date`.
87. **A launch is started without a date** — existing:
    `tests/integration/launch/test_slack_entry_start.py::test_a_launch_is_started_without_a_date`.
88. **The playbook version is never user input** — existing:
    `tests/unit/launch/infrastructure/driving/test_slack_entry_modal_contract.py::test_the_modal_contains_no_playbook_version_field`.

## Assertion classifications

Per `ai-toolkit:testing`, marked inline in each test (`SPECIFIED:` /
`DERIVED:` comments); the derived and deliberately-untested items in one
place:

**Derived (inferred, no stated requirement fixes them):**

- `test_playbook_authoring.py` — the two-fault wording check in
  `test_a_rejected_write_reports_all_faults_and_persists_nothing`
  (substrings "description" and "lesson"/"block"); the enumeration
  pattern and signature check in
  `test_the_authoring_surface_offers_no_framework_write`; the `REJECTED`
  exception tuple for the discipline-change rejection.
- `test_clickup_sync_wording_heal.py` — in
  `test_an_edited_task_name_is_never_restored`, that the retained
  composition is not replaced by a person's edit (inferred from
  "whenever the system writes … it SHALL update that field's retained
  value" — only system writes move it).
- Both integration files — the reference-document row grammar (parser),
  inherited from the existing shipped-set tests.

**Deliberately untested (recorded, not omitted):**

- Concurrent interleaved writes racing the set-version (scenario 42's
  concurrency half; `design.md` Decision 7) — not deterministically
  observable through the invented seams.
- The exhaustive form of "no read path branches on the stamp" (scenario
  2) — universal negative; its strongest observable instance is tested.
- Scenario 25 (*The seed runs once*) and scenario 17's post-change
  re-homing — see their entries above.
- The retire/un-retire *return values* of the use cases — no scenario
  states them; tests observe stores and served playbooks instead.

## Obsolete-test candidates

Input to a **destructive** action this pass will not take. Every entry is
a **candidate for human confirmation**, never a conclusion. Search scope:
`tests/**/test_*.py` (the dispatched glob), matched on imports and
asserted behavior; no earlier `test-manifest.md` was supplied with this
dispatch, so no scenario-to-test map from a prior pass was available.
Superseding deltas are cited per entry.

The YAML-path entries (O-1…O-8) are superseded by the proposal's
**BREAKING** removal (`load_shipped_playbook`, the YAML loading path,
`shipped_playbooks.py`, `playbook_v1.yaml` — `tasks.md` 7.1) and by the
MODIFIED requirement *The shipped playbook carries the authored step set*
becoming a seed requirement. Replacement coverage for the data
guarantees: `tests/integration/launch/test_playbook_seed.py`.

- **O-1** `tests/unit/launch/infrastructure/test_playbook_loader.py` —
  evidence: imports `load_playbook`/`load_shipped_playbook` from
  `playbook_loader`; tests the YAML file boundary. ⚠ Carries scenario
  17's only coverage — re-home before deleting (see scenario 17).
- **O-2** `tests/unit/launch/infrastructure/test_playbook_loader_completion.py`
  — evidence: imports `load_shipped_playbook`; YAML loading path.
- **O-3** `tests/unit/launch/infrastructure/test_playbook_loader_description.py`
  — evidence: imports `load_playbook`; YAML description parsing.
- **O-4** `tests/unit/launch/infrastructure/test_shipped_playbook_steps.py`
  — evidence: imports `load_shipped_playbook`; asserts the YAML step
  census (BUILD THE LISTING, provenance, vocabulary). Superseded by the
  seed requirement; replaced by `test_playbook_seed.py`.
- **O-5** `tests/unit/launch/infrastructure/test_shipped_playbook_descriptions.py`
  — evidence: imports `load_shipped_playbook`; asserts YAML descriptions
  re-derive from the reference document. Replaced by
  `test_playbook_seed.py::test_every_description_re_derives_from_its_reference_row`.
  ⚠ Its two guard tests (trimming actually exercised; content terminals
  survive) were **not** ported — worth porting with the seed test if the
  guards are still wanted; recorded so the loss is a decision, not an
  accident.
- **O-6** `tests/unit/launch/infrastructure/test_shipped_step_identifier_discipline.py`
  — evidence: imports `load_shipped_playbook`. Replaced by
  `test_playbook_seed.py::test_every_seeded_step_traces_to_its_source_row`
  (discipline-segment assertion included).
- **O-7** `tests/unit/launch/application/test_shipped_playbook_undecided_policies.py`
  — evidence: imports `load_shipped_playbook`; the revised scenario runs
  the report "over the served playbook". Replaced by
  `test_playbook_seed.py::test_outstanding_rule_policy_decisions_stay_visible`.
  (`test_report_undecided_rule_policies.py` — the use case against
  constructed playbooks — is *not* obsolete in substance, but its
  fixtures load via `load_playbook`: impacted fixture I-3.)
- **O-8** `tests/integration/launch/test_slack_entry_start.py` — evidence:
  its `_ShippedPlaybooks` substitute imports `load_shipped_playbook`.
  The *asserted behavior* (scenarios 86–87) survives; only the fixture's
  playbook source is superseded. Likely an impacted fixture rather than
  a deletion — listed here because the superseding delta (`launch-entry`
  MODIFIED) changes what the recorded version means.
- **O-9** `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_an_edited_task_name_is_never_restored`
  — superseded-in-formulation by the revised *An edited task name is
  never restored* (the guarantee now rides retained compositions).
  Evidence: its setup predates retained values, which under the new
  rules is the ambiguous-legacy case — the same non-rewrite outcome, so
  the test should keep passing. Candidate for *retitling to the legacy
  case or leaving as-is*, not deletion; replacement for the revised
  formulation: `test_clickup_sync_wording_heal.py::test_an_edited_task_name_is_never_restored`.

No test was found asserting the *removed* sentence "a task's name …
SHALL NOT be rewritten afterwards" in its universal form (i.e. asserting
no rewrite of an *unedited* task after a wording change) — stated
explicitly: none was found by this search, which is not proof none
exists.

## Impacted fixtures (repair, not deletion — distinct from obsolete)

The gate-holding floor (`tasks.md` 1.1) makes **every existing fixture
that constructs `LaunchPlaybook` with unheld gates** raise
`InvalidPlaybookError` once implemented — most fixtures in
`test_launch_playbook.py`, `test_launch_run.py`,
`test_launch_gate_advance.py`, `test_gate_conditions.py`,
`test_launch_dates.py`, the clickup-sync unit files,
`test_scope_aware_launch_reads.py`, `test_graduation.py`,
`test_launch_reports.py`, and others construct small step sets
(representative evidence:
`test_launch_playbook.py::test_a_coherent_playbook_loads` builds a
playbook whose eight gates have no blocking step and asserts it loads).
`tasks.md` 1.2 assigns this repair to the implementation step. Per
`ai-toolkit:testing` this is failure state 3 — broken fixture — and is
repaired by satisfying the floor in the fixture (as the new files do
with eight automated blocking fillers), **never** by weakening what
those tests assert.

- **I-1** the fixture class above (floor).
- **I-2** `test_slack_entry_start.py` (`load_shipped_playbook` → the
  served-playbook source; see O-8).
- **I-3** `test_report_undecided_rule_policies.py` (loads its constructed
  playbooks via the YAML `load_playbook`; the use case itself is
  untouched by this change).

## Invented interfaces / unresolved project questions

Each taken because no artifact or recorded convention answers it; the
tests depending on each are named. The correction point for every entry
is a single helper or fake, documented in the owning file's docstring.

- **Q1 — step-store seam and protocol** (`steps=` parameter;
  `load() -> (records, version)`, `save(records, expected_version=)`).
  Depends: all of `test_playbook_authoring.py`.
- **Q2 — stored-record attribute spellings** (`definition`,
  `created_by/on`, `updated_by/on`, `retired_by/on`, `unretired_by/on`;
  un-retire clears the retirement marker and records its own
  attribution). Depends: `test_playbook_authoring.py`'s accessors.
- **Q3 — rejection surface of non-coherence rejections** (discipline
  change): the `REJECTED` tuple. Depends:
  `test_a_discipline_change_is_rejected`.
- **Q4 — Postgres adapter module/class/read**
  (`playbook_repository.PlaybookRepository(session).get(version)`, sync
  or async tolerated). Depends: both integration files.
- **Q5 — the real write store's constructor** (`PlaybookStepStore` or
  the repository class doubling as it). Depends:
  `test_playbook_authoring_live.py::_store`.
- **Q6 — the mapping-port write for retained compositions**
  (`record_composition(product_id, step_id, name=, body=)`) and body
  updates travelling as a `description` field on `update_task`. Depends:
  `test_clickup_sync_wording_heal.py`, `test_clickup_sync_retired_steps.py`.
- **Q7 — principal representation** (a plain string). Depends: every
  authoring test.
- **Q8 — webhook behavior on a retired step's delivery** (quiet skip vs.
  error response): the delta fixes only "no outcome is recorded".
  Depends: the accounting of scenario 68; no test asserts the response
  shape.
- **Q9 — no stack skill for FastAPI/SQLAlchemy/Alembic exists in the
  library** beyond `python` (loaded) — recorded as required by the
  test-writer contract; the pass proceeded on `ai-toolkit:testing` +
  `python`.

## What the implementation step must make pass

In dependency order:

1. `tests/unit/launch/domain/test_gate_holding_floor.py` — `tasks.md`
   1.1 (then 1.2 for the fixture ripple across the existing suite).
2. `tests/unit/launch/application/test_playbook_authoring.py` —
   `tasks.md` 4.1–4.5.
3. `tests/unit/launch/infrastructure/driven/test_clickup_sync_wording_heal.py`
   and `test_clickup_sync_retired_steps.py` — `tasks.md` 2.2, 6.1–6.3.
4. `tests/integration/launch/test_playbook_seed.py` and
   `test_playbook_authoring_live.py` — `tasks.md` 2.1–2.3, 3.1–3.3
   (require a live Postgres with `alembic upgrade head` applied).
5. Keep passing: `tests/unit/launch/domain/test_outcomes_after_retirement.py`
   and the currently-green halves noted in the baseline section.

The commit-time tiers must return to green only after the obsolete
candidates above are dispositioned by a human and the impacted fixtures
repaired (`tasks.md` 1.2, 7.1, 8.1).
