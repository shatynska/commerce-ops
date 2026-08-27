# Test manifest — `record-gate-and-discipline-as-fields`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-27, from the change's
delta specs alone, before any implementation of this change exists.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among `openspec instructions apply`'s context files and must be read on
purpose, before implementing.

---

## Baseline

Taken before any test below was written, at the worktree root, on branch
`contain-a-failing-launch`:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | **1130 passed, 0 failed** |
| `uv run pytest tests/integration` | **95 passed, 2 skipped** — both skips pre-existing and unrelated (`test_playbook_authoring_roster_live.py`, `test_registered_handlers_activate_nothing.py`) |

Full-tier, not scoped. After this pass:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1131 passed, **75 failed** — every failure in the three files added here |
| `uv run ruff check` / `ruff format --check` | clean |
| `uv run mypy .` | `Success: no issues found in 315 source files` |
| `uv run pytest tests/integration` | unchanged — 95 passed, 2 skipped |

The 75 failures are all **absent target** (`ai-toolkit:testing`'s second failure
state): `folder_fields`, `set_task_field`, the resolution parameter on
`converge_launch`, the folder read in the job, the monitoring report and the
suppression record do not exist. That failure establishes absence and nothing
about whether the assertions are well-formed.

**One new test passes on its first run and that is not the fourth failure
state:**
`tests/unit/launch/infrastructure/driving/test_clickup_field_configuration_check.py::test_a_stood_down_pass_writes_no_value`
states behaviour the change must **preserve** — the stand-down already declines
the whole pass — so today's code satisfies it, and its job is to catch a Custom
Field backfill placed in the job body once one could exist. The same category
`test_clickup_sync_job_containment.py` records for two of its own tests.

**Eight tests passed vacuously on their first draft and were given controls.**
Every one asserted an absence — no report, no read, no write, no suppression —
which is unfalsifiable where nothing happens at all. Each now carries a positive
control *in the same test*: the same state under which the thing does happen.
This is `tasks.md` 7.4's own instruction applied to the check as well as to the
writes.

---

## Files written

Additive only. No existing test file was edited, deleted or disabled, and
nothing outside the dispatched test-path glob (`tests/**/test_*.py`) was written
except this manifest.

| File | Level | New tests |
| --- | --- | --- |
| `/home/shatynska/projects/commerce-ops/tests/unit/shared/infrastructure/driven/test_clickup_client_custom_fields.py` | the ClickUp adapter, over `httpx.MockTransport` | 21 (incl. parametrisations) |
| `/home/shatynska/projects/commerce-ops/tests/unit/launch/infrastructure/driven/test_clickup_sync_custom_fields.py` | `converge_launch`, over in-memory fakes | 16 (incl. parametrisations) |
| `/home/shatynska/projects/commerce-ops/tests/unit/launch/infrastructure/driving/test_clickup_field_configuration_check.py` | the job body, over the runner's periodic registry | 39 |

Each file's module docstring carries its own SPECIFIED/DERIVED/INVENTED
accounting and its correction points; this manifest is the index, not a
replacement for them.

---

## Scenario accounting

**88 scenarios in the delta specs; 88 accounted for below.**

- `launch-clickup-sync`: 64 (14 + 30 ADDED, 20 MODIFIED)
- `clickup-task-client`: 24 (6 + 3 ADDED, 7 + 8 MODIFIED)

Abbreviations for the three new files:

- **CLIENT** = `tests/unit/shared/infrastructure/driven/test_clickup_client_custom_fields.py`
- **PROJ** = `tests/unit/launch/infrastructure/driven/test_clickup_sync_custom_fields.py`
- **JOB** = `tests/unit/launch/infrastructure/driving/test_clickup_field_configuration_check.py`

### `launch-clickup-sync` — ADDED: *A projected task carries its step's gate and discipline as Custom Field values* (14)

Five scenarios state both a **write** clause and a **reporting** clause. A
report has no signal at the projection level, so each is covered by a pair of
tests, one at each level; the scenario is accounted for by the pair.

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | A newly created task is given both values | `PROJ::test_a_newly_created_task_is_given_both_values` |
| 2 | A field fault cannot cost a step its task | `PROJ::test_a_field_fault_cannot_cost_a_step_its_task` |
| 3 | No value is written to a field found in a gap | `PROJ::test_no_value_is_written_for_a_field_withheld_by_a_gap` + `JOB::test_a_configured_field_of_the_wrong_type_is_a_gap` (the "once for the pass rather than once per task" clause) |
| 4 | A task projected before the fields existed gains its values | `PROJ::test_a_task_projected_before_the_fields_existed_gains_its_values` |
| 5 | A task already carrying its values is left alone | `PROJ::test_a_task_already_carrying_its_values_is_left_alone` |
| 6 | A re-gated step's task is corrected | `PROJ::test_a_re_gated_steps_task_is_corrected` |
| 7 | A re-gated step whose new gate has no option keeps its former value | `PROJ::test_a_re_gated_step_whose_new_gate_has_no_option_keeps_its_value` + `JOB::test_a_missing_option_is_reported_before_any_task_is_written` |
| 8 | An option differing only in wording is not a match | `PROJ::test_an_option_differing_only_in_wording_is_not_a_match` + `JOB::test_an_option_differing_only_in_wording_is_reported_as_no_match` |
| 9 | A step that is not projected is given no values | `PROJ::test_a_step_that_is_not_projected_is_given_no_values` (3 parametrisations — not active, not human, prohibited-tactic) + `PROJ::test_a_step_the_playbook_does_not_define_is_given_no_values` (the fourth ground) |
| 10 | A deployment configuring no field writes none | `PROJ::test_a_deployment_configuring_no_field_writes_none` + `JOB::test_a_deployment_configuring_no_field_makes_no_report` |
| 11 | A field identifier configured but empty is a gap | `PROJ::test_a_field_identifier_configured_but_empty_writes_no_value` + `JOB::test_an_empty_identifier_is_reported_as_configured_with_no_value` |
| 12 | A deployment configuring one field records only that one | `PROJ::test_a_deployment_configuring_one_field_records_only_that_one` + `JOB::test_a_deployment_configuring_one_field_reports_only_that_one` |
| 13 | A stood-down pass writes no value | `JOB::test_a_stood_down_pass_writes_no_value` |
| 14 | A field write that fails costs only that field | `PROJ::test_a_field_write_that_fails_costs_only_that_field` |

### `launch-clickup-sync` — ADDED: *The Custom Field configuration is checked once per pass and a gap is reported without stopping the pass* (30)

All in **JOB**.

| # | Scenario | Covered by |
| --- | --- | --- |
| 1 | A missing option is reported before any task is written | `test_a_missing_option_is_reported_before_any_task_is_written` |
| 2 | A gap does not stop the pass | `test_a_gap_does_not_stop_the_pass` |
| 3 | Every gap is named together | `test_every_gap_is_named_together` |
| 4 | A configured field that is absent is a gap | `test_a_configured_field_that_is_absent_is_a_gap` |
| 5 | A field declaring one option name twice is a gap | `test_a_field_declaring_one_option_name_twice_is_a_gap` + `test_a_duplicate_under_a_name_that_is_no_gate_is_not_a_gap` (its third clause) |
| 6 | A field the read could not interpret is reported as such | `test_a_field_the_read_could_not_interpret_is_reported_as_such` |
| 7 | A configured field of the wrong type is a gap | `test_a_configured_field_of_the_wrong_type_is_a_gap` |
| 8 | An empty identifier is reported even when ClickUp cannot be reached | `test_an_empty_identifier_is_reported_even_when_clickup_is_unreachable` |
| 9 | An unreachable ClickUp is not reported as a gap | `test_an_unreachable_clickup_is_not_reported_as_a_gap` + `test_a_malformed_folder_read_is_not_reported_as_a_gap` (its "or a read whose result cannot be interpreted" half, per `tasks.md` 4.3) |
| 10 | An empty-identifier report on a read-less pass is suppressed like any other | `test_an_empty_identifier_report_on_a_read_less_pass_is_suppressed` |
| 11 | A pass with no active launches still checks the configuration | `test_a_pass_with_no_active_launches_still_checks_the_configuration` |
| 12 | A failure of the suppression record costs only the field values | `test_a_failure_of_the_suppression_record_costs_only_the_field_values` |
| 13 | A failed suppression read and a failed write after delivery differ | `test_a_failed_suppression_read_and_a_failed_write_after_delivery_differ` |
| 14 | A store this concern cannot restore ends the walk | `test_a_store_this_concern_cannot_restore_ends_the_walk` |
| 15 | A pass with no launch folder configured reports only the empty identifier | `test_a_pass_with_no_launch_folder_reports_only_the_empty_identifier` |
| 16 | An empty identifier is not reported during a stand-down | `test_an_empty_identifier_is_not_reported_during_a_stand_down` |
| 17 | A stood-down pass performs no check | `test_a_stood_down_pass_performs_no_check` |
| 18 | Options declared out of the playbook's order are a gap | `test_options_declared_out_of_the_playbooks_order_are_a_gap` |
| 19 | Options the playbook does not know are not an order gap | `test_options_the_playbook_does_not_know_are_not_an_order_gap` |
| 20 | Missing gates are one gap, not two | `test_missing_gates_are_one_gap_not_two` |
| 21 | A duplicate withholds the order finding | `test_a_duplicate_withholds_the_order_finding` |
| 22 | Reordering options during a duplicate does not re-report it | `test_reordering_options_during_a_duplicate_does_not_re_report_it` |
| 23 | A gap repaired into a different gap is reported again | `test_a_gap_repaired_into_a_different_gap_is_reported_again` |
| 24 | A continuing gap is reported once | `test_a_continuing_gap_is_reported_once` |
| 25 | A stand-down does not lift suppression | `test_a_stand_down_does_not_lift_suppression` |
| 26 | A continuing gap is reported once across a restart | `test_a_continuing_gap_is_reported_once_across_a_restart` |
| 27 | An undelivered report leaves the gap eligible | `test_an_undelivered_report_leaves_the_gap_eligible` |
| 28 | A repaired configuration lifts suppression | `test_a_repaired_configuration_lifts_suppression` |
| 29 | Opting out lifts suppression | `test_opting_out_lifts_suppression` |
| 30 | A changed gap is reported again | `test_a_changed_gap_is_reported_again` |

Two further **JOB** tests trace to requirement clauses rather than to a
`#### Scenario:` block, and are recorded as **derived** below:
`test_a_gap_is_not_a_per_launch_failure` and
`test_a_cancellation_during_the_check_is_not_absorbed`.

### `launch-clickup-sync` — MODIFIED: *Human steps are projected as tasks carrying their name, description and assignees* (20)

**No new test is owed and none was written.** The delta's copy of this
requirement differs from the predecessor's in exactly one paragraph, and only in
a cross-reference: the assignee paragraph's pointer to the tag rule is repointed
at the Custom Field rule. Verified by diffing the delta's requirement block
against `openspec/changes/tag-tasks-with-gate-and-discipline/specs/launch-clickup-sync/spec.md`.
All twenty scenarios are carried **verbatim**, so each stays covered by the
tests that already exist, and **none of them is superseded** — see *Obsolete
tests* for why nothing from this block enters that list.

| Scenario | Already covered by |
| --- | --- |
| A human step gets a task | `tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py::test_a_human_step_gets_a_task_named_from_its_name` |
| A step's description becomes the task's body | `…/test_clickup_projection_step_fields.py::test_a_steps_description_becomes_the_tasks_body` |
| A task is assigned to the step's people | `…/test_clickup_projection_step_fields.py::test_a_task_is_assigned_to_the_steps_people` |
| An existing unowned task gains its step's assignees | `…/test_clickup_projection_step_fields.py::test_an_existing_unowned_task_gains_its_steps_assignees` |
| A person's own assignment change is not overwritten | `…/test_clickup_projection_step_fields.py::test_a_persons_own_assignment_change_is_not_overwritten` |
| An assignee with no ClickUp account is reported, not silently dropped | `…/test_clickup_projection_step_fields.py::test_an_assignee_with_no_clickup_account_is_reported_not_dropped` |
| A step activated mid-launch is projected | `…/test_clickup_projection_step_fields.py::test_a_step_activated_mid_launch_is_projected` |
| A renamed task still resolves to its step | `…/test_clickup_task_naming.py::test_a_renamed_task_still_resolves_to_its_step` |
| An unedited task follows the step's current wording | `…/test_clickup_sync_wording_heal.py::test_an_unedited_task_follows_the_steps_current_wording` |
| A person's body note survives a wording edit | `…/test_clickup_sync_wording_heal.py::test_a_persons_body_note_survives_a_wording_edit`; also `…/test_clickup_projection_step_fields.py::test_a_persons_body_note_survives_a_wording_edit` |
| An unedited legacy task starts healing | `…/test_clickup_sync_wording_heal.py::test_an_unedited_legacy_task_starts_healing`; also `…/test_clickup_projection_step_fields.py::test_an_unedited_task_heals_to_the_new_composition` |
| An ambiguous legacy task is never rewritten | `…/test_clickup_sync_wording_heal.py::test_an_ambiguous_legacy_task_is_never_rewritten` |
| An edited task name is never restored | `…/test_clickup_task_naming.py::test_an_edited_task_name_is_never_restored`; also `…/test_clickup_sync_wording_heal.py::test_an_edited_task_name_is_never_restored` |
| An over-long name is shortened rather than failing | `…/test_clickup_task_naming.py::test_an_over_long_name_is_shortened_rather_than_failing`; `…/test_clickup_task_name_composition.py::test_a_shortened_name_ends_in_an_ellipsis_then_the_identifier`; `…/test_clickup_projection_step_fields.py::test_an_over_long_name_is_shortened_and_never_spills_into_the_body` |
| An existing task is not recreated | `…/test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated` |
| A prohibited-tactic step is never projected | `…/test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected` |
| A deleted task for unfinished work is re-projected | `…/test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected` |
| A deleted task for finished work stays gone | `…/test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone` |
| Automated steps are never projected | `…/test_clickup_projection_step_fields.py::test_automated_steps_are_never_projected` |
| A step that is not active is never projected | `…/test_clickup_projection_step_fields.py::test_a_step_that_is_not_active_is_never_projected` |

(`…` is `tests/unit/launch/infrastructure/driven`.)

### `launch-clickup-sync` — REMOVED: *A projected task carries its step's gate and discipline as tags*

**Accounted for as uncovered, with the operation itself as the reason.** Removed
behaviour is not to be tested. Its nine scenarios are not counted among the 88 —
a REMOVED block in an OpenSpec delta carries the requirement's heading, Reason
and Migration but not its scenarios, and this one is no exception. The tests
that covered it in the predecessor's pass are in *Obsolete tests* below.

### `clickup-task-client` — ADDED: *The Custom Fields available in a folder can be read* (6)

| Scenario | Covered by |
| --- | --- |
| A folder's Custom Fields are read | `CLIENT::test_a_folders_custom_fields_are_read` |
| A folder's fields are read completely | `CLIENT::test_a_folders_fields_are_read_completely` — **gated on an unmeasured premise**, see below |
| A folder with no Custom Fields reads as empty | `CLIENT::test_a_folder_with_no_custom_fields_reads_as_empty` |
| A field the capability does not anticipate does not fail the read | `CLIENT::test_a_field_the_capability_does_not_anticipate_does_not_fail_the_read` (3 parametrisations) |
| An uninterpretable field is distinguishable from one declaring no options | `CLIENT::test_an_uninterpretable_field_is_distinguishable_from_an_optionless_one` |
| A field declaring no options is reported as such | `CLIENT::test_a_field_declaring_no_options_is_reported_as_such` |

### `clickup-task-client` — ADDED: *A Custom Field value can be set on an existing task* (3)

| Scenario | Covered by |
| --- | --- |
| A value is set on a task | `CLIENT::test_a_value_is_set_on_a_task` |
| An option value is named by the option's identifier | `CLIENT::test_an_option_value_is_named_by_the_options_identifier` |
| Setting the same value twice is not an error | `CLIENT::test_setting_the_same_value_twice_is_not_an_error` |

### `clickup-task-client` — MODIFIED: *The tasks of a list can be read* (7)

Three scenarios are new; four are carried verbatim and stay covered. The
requirement is **extended**, not narrowed, so nothing existing is superseded.

| Scenario | Covered by |
| --- | --- |
| Tasks returned with status and due date | *existing* — `tests/unit/shared/infrastructure/driven/test_clickup_client_list_and_read.py::test_tasks_are_returned_with_status_closed_judgement_and_due_date` |
| Tasks returned with their tags | *existing* — `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py::test_tasks_are_returned_with_their_tag_names`, `::test_a_task_payload_without_a_tags_key_reads_without_erroring` |
| An empty list reads as empty | *existing* — `…/test_clickup_client_list_and_read.py::test_an_empty_list_reads_as_empty_rather_than_erroring` |
| A multi-page list is read completely | *existing* — `…/test_clickup_client_list_and_read.py::test_a_multi_page_list_is_read_completely` |
| Tasks returned with their Custom Field values | `CLIENT::test_tasks_are_returned_with_their_custom_field_values` |
| A value the client cannot interpret does not fail the read | `CLIENT::test_a_value_the_client_cannot_interpret_does_not_fail_the_read` (3 parametrisations) |
| An option value reads back as it would be written | `CLIENT::test_an_option_value_reads_back_as_the_option_identifier` (3 parametrisations) — **gated on an unmeasured premise**, see below |

### `clickup-task-client` — MODIFIED: *A failed ClickUp request is surfaced to the caller* (8)

The enumeration goes from five operations to seven. Six scenarios are carried
verbatim; two are new. Nothing existing is superseded.

| Scenario | Covered by |
| --- | --- |
| ClickUp rejects a create request | *existing* — `…/test_clickup_client.py::test_create_task_rejected_by_clickup_raises` |
| ClickUp rejects an update request | *existing* — `…/test_clickup_client.py::test_update_task_rejected_by_clickup_raises` |
| ClickUp rejects a create-list request | *existing* — `…/test_clickup_client_list_and_read.py::test_a_rejected_create_list_request_raises` |
| ClickUp rejects a read of a list's tasks | *existing* — `…/test_clickup_client_list_and_read.py::test_a_rejected_read_of_a_lists_tasks_raises` |
| ClickUp is unreachable | *existing* for the five earlier operations (`…/test_clickup_client.py::test_create_task_when_clickup_is_unreachable_raises`, `::test_update_task_when_clickup_is_unreachable_raises`, `…/test_clickup_client_list_and_read.py::test_create_list_when_clickup_is_unreachable_raises`, `::test_list_tasks_when_clickup_is_unreachable_raises`, `…/test_clickup_client_tags.py::test_add_task_tag_when_clickup_is_unreachable_raises`) **plus** `CLIENT::test_the_new_operations_raise_when_clickup_is_unreachable` for the two the delta adds |
| ClickUp rejects a tag write | *existing* — `…/test_clickup_client_tags.py::test_a_rejected_tag_write_raises` |
| ClickUp rejects a read of a folder's Custom Fields | `CLIENT::test_a_rejected_read_of_a_folders_custom_fields_raises` |
| ClickUp rejects a Custom Field write | `CLIENT::test_a_rejected_custom_field_write_raises` |

---

## Assertion classification

Each file carries its own per-assertion labels at the assertion site. The
summary:

### SPECIFIED

Everything traceable to a delta requirement's own words or to a `tasks.md`
directive that fixes a name or a behaviour: the create call carrying no Custom
Field value; the option identifier as the representation on both the read and
the write; correction of a divergent value; leaving an unresolvable value
standing; the warning-level record naming step, field and task; the seven
operations in the failure enumeration; the read of the folder's fields being
total; the eight gap kinds and what each withholds; one report per pass; report
once and lift on repair or withdrawal; a stand-down declining entirely; the
run's outcome being untouched by any fault of this concern save the shared-store
path.

### DERIVED — enumerated, because each obliges the implementer to satisfy something no scenario states

1. **`ClickUp`'s response envelopes** — `{"fields": [...]}` for the folder read,
   `custom_fields` on a task, `type_config.options` carrying `{id, name,
   orderindex}`. Follows the adapter's existing `/api/v2/…` convention, which
   `test_clickup_client_list_and_read.py` already pins for the list read.
   (CLIENT, throughout.)
2. **`drop_down` as the type whose values the system writes, `labels` as a
   wrong type that nonetheless declares options.** `design.md` argues the
   distinction ("a multi-select declares options too") without naming ClickUp's
   type strings. (CLIENT, JOB.)
3. **Message wording, where a scenario is about what the report says.** Two
   forms are used, and the second is preferred wherever it is available:
   - *comparison* — the message for an empty identifier must differ from the
     message for an absent field; the message for an uninterpretable field must
     differ from the message for an optionless one. Pins no vocabulary.
     (`JOB::test_an_empty_identifier_is_reported_as_configured_with_no_value`,
     `JOB::test_a_field_the_read_could_not_interpret_is_reported_as_such`.)
   - *the delta's own word* — `uninterpretable`, `type`, and the gate/discipline
     identifiers themselves. (Same two tests, plus
     `JOB::test_a_configured_field_of_the_wrong_type_is_a_gap`,
     `JOB::test_an_empty_identifier_is_reported_even_when_clickup_is_unreachable`
     and `JOB::test_a_pass_with_no_launch_folder_reports_only_the_empty_identifier`,
     which read "gate" out of the message because an empty identifier has no
     identifier to name the field by.)
4. **"Naming the order found" is asserted as the declared options appearing in
   the message in their declared sequence.** Used positively in
   `JOB::test_options_declared_out_of_the_playbooks_order_are_a_gap` and
   negatively — as the absence of an order finding — in
   `JOB::test_missing_gates_are_one_gap_not_two` and
   `JOB::test_a_duplicate_withholds_the_order_finding`. The negative use is the
   weaker of the two and is the most likely fixture correction in this pass.
5. **`_Resolution`'s shape and the parameter it arrives under.** `tasks.md` 4.2
   fixes that a resolution is threaded into `converge_launch` as data and
   nothing more. A withheld field is encoded as its identifier being `None`.
   (PROJ, single correction point.)
6. **The suppression record's accessors.** Discovered rather than transcribed;
   see the SEAM CONTRACT in JOB.
7. **The interleaving in
   `JOB::test_options_the_playbook_does_not_know_are_not_an_order_gap`** — the
   scenario says the extra options are "additionally declared", not where. They
   are interleaved rather than appended, so an implementation judging the order
   over every option rather than over the gate options alone fails.
8. **Two whole tests, each traceable to a requirement clause but to no
   `#### Scenario:` block**, written because `tasks.md` asks for them by name:
   - `JOB::test_a_gap_is_not_a_per_launch_failure` — `tasks.md` 4.3b ("Add
     tests asserting a gap leaves the run's outcome untouched while an
     unrelated launch failure still fails it").
   - `JOB::test_a_cancellation_during_the_check_is_not_absorbed` — `tasks.md`
     5.5a and the requirement's cancellation clause.
9. **`PROJ::test_a_re_gated_steps_task_is_corrected` additionally asserts that
   the *discipline* field, which did not change, is not rewritten.** The
   scenario states only the gate correction; the no-op guarantee is stated over
   fields generally, and this reads it per field.

### DELIBERATELY UNTESTED — recorded with the reason

Each file's closing block states these at its own level. Collected:

| Not tested | Reason |
| --- | --- |
| `Authentication is configured independently of any one caller` over `folder_fields` / `set_task_field` | An existing, unmodified requirement of `clickup-task-client`; the delta does not restate its two scenarios over the new operations, exactly as `test_clickup_client_list_and_read.py` records for `create_list`/`list_tasks`. |
| What `folder_fields` returns as a concrete type; what the field-definition value object is called; what `set_task_field` returns | The delta states only what each field carries and that a rejection reaches the caller as an error. |
| A `graduated` launch being visited at all, and the graduation backfill exclusion | Owned by *Each launch is projected into its own ClickUp list*, which already has its own coverage; nothing about Custom Fields changes it. |
| The order of the two field writes relative to each other | Fixed only that both follow the create. |
| Which Slack channel the report reaches | `MonitoringNotifier`'s own concern; `test_monitoring_notifier_port.py` covers the wiring. Asserting a channel here would test `product-monitoring` through `launch-clickup-sync`. |
| The `when` half of the suppression row | No scenario turns on the timestamp; report-once is decided by the identity alone. |
| The Alembic migration creating the suppression table (`tasks.md` 5.1) | Schema, driven in the integration tier by `tasks.md` 7.6. A unit test over a substituted store establishes nothing about it, and inventing the table and repository names wholesale would be guesswork presented as coverage. **No integration test was written by this pass** — see *What this pass did not cover*. |
| `import-linter` passing with the pass reaching `MonitoringNotifier` (`tasks.md` 7.8) | A structural gate the project runs directly, not a scenario. |
| The `deploy.yml` conditional render and the process environment (`tasks.md` 1.3/1.3a) | No delta scenario states it; `runtime-configuration` carries no delta in this change, and 1.3a is explicitly a manual verification against a rendered `.env` and a running container. |
| Adding the two variables to the declared set in `tests/unit/shared/application/test_settings.py` (`tasks.md` 1.2) | That is an **edit to an existing test**, which this pass is forbidden to make. The drift test will fail once the settings model declares the two variables and before 1.2 lands; that is the implementer's step, not an obsolete test. |

---

## Unresolved project questions

Recorded here because a dispatched subagent has no channel to ask on. Each names
the assumption taken and the tests that depend on it.

1. **Does `GET /api/v2/folder/{folder_id}/field` page?** `tasks.md` 2.3b gates
   this behind a measurement taken *before* the tests are derived — which had
   not been taken when this pass ran.
   *Assumption:* it pages in the same idiom the list read uses (successive
   responses, the first marked `last_page: False`), so the requirement's
   completeness obligation is assertable.
   *Depends on it:* `CLIENT::test_a_folders_fields_are_read_completely`.
   *If the measurement says otherwise:* the scenario's own WHEN ("WHEN the task
   system returns a folder's fields in pages") is never satisfied and this test
   fixes a wire contract nobody measured. Take it to `tasks.md` rather than
   weakening the test; the change owns the decision, and this pass does not edit
   its planning artifacts.

2. **What wire form does ClickUp report a drop-down value in?** `tasks.md` 2.4a
   gates this the same way, and `design.md` records the premise as deliberately
   unmeasured.
   *Assumption:* the value is normalisable from what the task payload itself
   carries, and the plausible forms are the option's own identifier and the
   option's `orderindex` (mapped through the `type_config.options` the same
   payload carries). The test is written against the **obligation**, parametrised
   over those forms rather than pinning one.
   *Depends on it:* `CLIENT::test_an_option_value_reads_back_as_the_option_identifier`.
   *If the measurement finds a third form:* add a parametrisation. If it finds a
   form that carries **neither** the option identifier nor the field's options,
   `design.md`'s own Risks entry says the answer is to reopen the decision, not
   to let the caller absorb the difference.

3. **Is a well-formed field of a type that declares no options (`formula`,
   `relationship`) *uninterpretable*, or does it *declare no options*?** The
   delta requires the two to be distinguishable and names "a formula, a
   relationship" among the types the capability does not anticipate, while also
   requiring "a field declaring no options SHALL be reported as declaring none".
   *Assumption:* a `formula` field is uninterpretable; a `drop_down` with an
   empty options list declares none.
   *Depends on it:* the first parametrisation of
   `CLIENT::test_a_field_the_capability_does_not_anticipate_does_not_fail_the_read`.
   The other two parametrisations are malformed shapes and are unambiguous under
   either reading. If the implementer reads a formula the other way, that test
   fails and the ambiguity is surfaced rather than fossilised — which is the
   point.

4. **What attribute names do the new value objects carry?** `tasks.md` 2.1
   fixes the *facts* ("identifier, name, type, and options in declared order,
   each with identifier and name") and no artifact fixes the spellings.
   *Assumption:* read through tolerant probes rather than pinned —
   `_field_id`/`_field_name`/`_field_type`/`_field_options`/`_uninterpretable`/
   `_option_id`/`_option_name`/`_custom_field_values` in CLIENT, and
   `_FieldDefinition`/`_FieldOption` exposing both spellings in JOB.
   *Depends on it:* all of CLIENT's folder-read tests and JOB's folder fixtures.

5. **How does the resolution reach `converge_launch`, and what does it look
   like?** `tasks.md` 4.2 fixes only that it is threaded as data.
   *Assumption:* a keyword parameter named one of `custom_fields`,
   `custom_field_resolution`, `field_resolution`, `fields`, `resolution`,
   `field_values`, carrying an object that is both attribute-readable
   (`gate_field_id`, `gate_options`, …) and a `Mapping` from field identifier to
   `{vocabulary name: option identifier}`.
   *Depends on it:* every test in PROJ (all 16 fail on this probe today, with a
   directive naming the correction point).

6. **How does the job reach the folder read, the notifier and the suppression
   record?** `tasks.md` 5.2 says the notifier is the one `worker.py` already
   injects; nothing fixes the other two.
   *Assumption:* the collaborator pattern `test_overdue_check.py` records —
   imported by name into the job module's namespace, referenced as bare globals.
   The folder read is installed under `_FOLDER_READ_NAMES` on the job module
   *and* on `clickup_client`; the notifier under `notifier` /
   `monitoring_notifier`; the suppression record by discovering any job-module
   global whose name mentions a gap.
   *Depends on it:* every test in JOB. The suppression seam is isolated behind
   `_require_store_used`, so a wrong guess there fails the eleven
   suppression-specific tests with a directive rather than all thirty-nine.

7. **Which exception type does a Custom Field write failure raise?** No artifact
   names one; `clickup-task-client` requires only that the failure propagates.
   *Assumption:* the pass is required only to *survive* it, so PROJ raises its
   own `_FieldWriteRefused` and CLIENT asserts `pytest.raises(Exception)`, the
   convention `test_clickup_client.py` already records.

Convention files read for this pass: `/home/shatynska/projects/commerce-ops/AGENTS.md`
(the authority; `CLAUDE.md` only includes it) and
`/home/shatynska/projects/commerce-ops/README.md`. `AGENTS.md` fixes the runner
(`uv run pytest`), the three tiers, the test-path glob and the naming convention
for `tests/agents/<subject>/`; no test here belongs in that tier, since none
drives a LangGraph graph.

---

## Obsolete tests — **candidates for human confirmation, not conclusions**

Every entry below is superseded by the REMOVED delta *A projected task carries
its step's gate and discipline as tags*, whose Reason states that the Custom
Field requirement "takes over the same subject". `tasks.md` 6.1 names their
removal in as many words ("plus their tests").

**Nothing in this list was edited, deleted or disabled by this pass.** This pass
adds tests and never subtracts.

### The baseline these were matched against is not `specsRoot`

The predecessor `tag-tasks-with-gate-and-discipline` is merged into `main` in
code but **not archived**, so `openspec/specs/launch-clickup-sync/spec.md`
records no tag requirement at all — the REMOVED delta has no target in today's
baseline (confirmed: the baseline's nine requirement headings do not include
it). The effective baseline used here is `specsRoot` **plus**
`openspec/changes/tag-tasks-with-gate-and-discipline/specs/launch-clickup-sync/spec.md`,
as the dispatch directed. Every entry below is matched against the predecessor's
delta file and against the tests' own docstrings, which name the change and the
scenarios they were derived from.

This matters for one thing in particular: had the search been run against
`specsRoot` alone, the REMOVED delta would have appeared to remove nothing and
this list would have been empty — which reads as "no such test exists" while
meaning "the baseline had not caught up".

### Search bound

`tests/**/test_*.py` — the dispatched glob — and nowhere else. Matched on the
literals `"gate:"` / `"discipline:"` and on the private helper names `tasks.md`
6.1 names (`_step_tags`, `_missing_tags`, `_ensure_tags`, `GATE_TAG_PREFIX`,
`DISCIPLINE_TAG_PREFIX`, `_OWNED_TAG_PREFIXES`). No earlier `test-manifest.md`
was supplied to this pass, and none was sought.

### Entries

| Test (runner-selectable) | Superseding delta | Evidence |
| --- | --- | --- |
| `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py::test_a_newly_projected_task_carries_both_tags` | REMOVED *A projected task carries its step's gate and discipline as tags* | The file's module docstring states it "Covers every scenario of the ADDED requirement *A projected task carries its step's gate and discipline as tags*", naming the predecessor's delta path. This test's docstring names *A newly projected task carries both tags*, one of that requirement's nine scenarios. |
| `…::test_an_existing_untagged_task_gains_its_tags` | same | Same module docstring; scenario *An existing untagged task gains its tags*. |
| `…::test_a_task_already_carrying_its_tags_is_left_alone` | same | Scenario *A task already carrying its tags is left alone*. |
| `…::test_a_persons_own_tags_are_never_touched` | same | Scenario *A person's own tags are never touched*. |
| `…::test_a_step_moved_between_gates_keeps_its_original_gate_tag` | same | Scenario *A step moved between gates keeps its original gate tag*. Additionally: the REMOVED delta's Reason names this exact behaviour as a **defect the successor retires** ("a step moved to a different gate has its task corrected rather than keeping a stale value"), so this test asserts the opposite of what the change ships. |
| `…::test_a_hand_removed_tag_is_added_back` | same | Scenario *A hand-removed tag is added back*. |
| `…::test_a_step_that_has_left_the_projection_is_not_tagged` | same | Scenario *A step that has left the projection is not tagged*. Parametrised; every parametrisation is superseded. |
| `…::test_a_tag_that_cannot_be_set_is_reported_and_not_fatal` | same | Scenario *A tag that cannot be set on a task is reported, not fatal*. |
| `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_tag_stand_down.py::test_no_tag_is_written_during_a_stand_down` | same | The file's module docstring: "Covers exactly one scenario of the ADDED requirement *A projected task carries its step's gate and discipline as tags*: *No tag is written during a stand-down*." Its spy is installed strictly over `clickup_client.add_task_tag`, which the projection will no longer call. |

`…` is `tests/unit/launch/infrastructure/driven/test_clickup_sync_tags.py`.

Both files become empty of live tests once these entries are actioned, so the
files themselves are candidates for deletion rather than pruning — the successor
coverage is in PROJ and JOB. That is a judgement for whoever actions the list,
not a conclusion of this pass.

### Found by the search and **not** obsolete

Recorded so the distinction is visible rather than inferred:

- `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py` — all of
  it. It uses `"gate:listable"` and `"discipline:listing"` as **sample tag
  strings** while testing `create_task`'s `tags` argument, `add_task_tag` and
  `ClickUpTaskState.tags`. The REMOVED delta's Migration says in as many words
  that "the client's tag operations are untouched and remain available", and
  `tasks.md` 6.3 repeats it. Renaming the sample strings would be cosmetic; no
  assertion here is superseded.
- Everything else the literal search reached — `"gate": …` as a dict key in
  playbook fixtures across roughly sixty files. Not tag literals.

### Where the search found nothing

No test outside the two files above asserts anything about the launch-side tag
composition. That is **"none was found by this search"** within the bound stated
above, not a proof that none exists: this pass has never seen
`clickup_sync.py`'s implementation and holds no requirement-to-test index, and
`tasks.md` 6.2 exists precisely because a scripted removal on the predecessor
"reported success, did not persist, and the suite stayed green across two runs".
Run that grep over `src/` and `tests/` as 6.2 directs; do not read a green suite
as the check.

---

## What this pass did not cover

- **No integration-tier test was written.** `tasks.md` 5.1 adds a table and a
  migration and 7.6 makes `uv run pytest tests/integration` load-bearing, but no
  `#### Scenario:` block states anything about the schema, and the table and
  repository names are unfixed by any artifact. A live-store test belongs with
  the implementation of 5.1, in the shape
  `tests/integration/shared/test_overdue_report_suppression_store.py` already
  sets.
- **No test asserts the end-to-end convergence `tasks.md` 7.10a demands.** It
  says so itself: "a mocked test cannot establish it." The unit-level half — a
  task already carrying its values receives no write — is
  `PROJ::test_a_task_already_carrying_its_values_is_left_alone`.
- **No test drives `deploy.yml`.** See the DELIBERATELY UNTESTED table.

## What the implementation step must make pass

Run each file individually while working:

```
uv run pytest tests/unit/shared/infrastructure/driven/test_clickup_client_custom_fields.py
uv run pytest tests/unit/launch/infrastructure/driven/test_clickup_sync_custom_fields.py
uv run pytest tests/unit/launch/infrastructure/driving/test_clickup_field_configuration_check.py
```

Then the tier: `uv run pytest tests/unit tests/agents` must return to green with
**1131 + 75 = 1206 passing** — 1130 from the baseline, plus the 76 written here
(75 failing, 1 already passing).

`tasks.md` 7.4's mutation check applies to these tests and not only to the ones
it was written against: with field writing removed entirely, every test that
claims to cover it must fail. Every absence-asserting test here already carries
its control, so that check should find no unfalsifiable assertion — but run it,
because the predecessor's 3.1c found four.
