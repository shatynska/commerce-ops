# Test manifest — redesign-step-fields

Written by `ai-toolkit:openspec-test-writer` before any implementation of
this change exists. It records what was tested, what was not and why, how
each assertion traces (or does not trace) to a stated requirement, which
existing tests the change supersedes, and every project question this pass
had to answer by assumption.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and has to
be read on purpose, before implementing.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted or disabled, and no implementation was written. Everything
below in *Superseded tests* is a **candidate for human confirmation**, not
an instruction.

---

## Baseline

Full baseline, taken at the worktree root before any test was written:

```
uv run pytest
→ 729 passed, 68 skipped, 0 failed  (27.5s)
```

The 68 skips are the whole `tests/integration` tier: no database is
configured on this machine (`DATABASE_URL` unset, no `.env.test`, no
`.env`), so the tier's `database_url` gate skips. **The integration test
this pass adds has therefore never been executed against a database** —
see *Unresolved project questions*, Q11.

After this pass, with the new files present:

```
uv run pytest --continue-on-collection-errors
→ 729 passed, 68 skipped, 15 errors
```

The 15 errors are the 15 new files, each failing at import with
`ImportError: cannot import name 'StepKind' from
'commerce_ops.launch.domain.launch_playbook'`. Per `ai-toolkit:testing`
that is failure state 2 — **the target does not exist**. It establishes
absence and nothing more: no assertion in this pass has been exercised,
so none of them is yet known to be any good.

Lint and format were run over the new files and pass:
`uv run ruff check tests/unit/launch tests/integration/launch` and
`uv run ruff format --check` — clean.

**Note for whoever runs the suite next:** a collection error aborts the
whole run without `--continue-on-collection-errors`, so `uv run pytest`
currently reports `Interrupted: 15 errors during collection` and runs
nothing else. The project's `pre-commit` pytest hook runs the whole
`tests/unit` + `tests/agents` tree, so **commits are blocked until the
domain field set lands**. That is a consequence of tests-before-code in
this repository, not a defect in these tests.

---

## Files written

All within the dispatched test-path glob (`tests/**/test_*.py`), plus this
manifest.

| File | Tests | Subject |
| --- | --- | --- |
| `tests/unit/launch/domain/test_step_lifecycle_status.py` | 5 | the status field, and the served/authored split |
| `tests/unit/launch/domain/test_step_kind_and_confirmation.py` | 4 | kind and confirmation as two independent facts |
| `tests/unit/launch/domain/test_step_automation_brief_and_handler.py` | 8 | brief/handler requirements, and the load-vs-activation split |
| `tests/unit/launch/domain/test_step_assignees_are_not_a_load_rule.py` | 5 | the assignee rule the load path must **not** have |
| `tests/unit/launch/domain/test_playbook_coherence_by_status.py` | 10 | the coherence rules this change changes |
| `tests/unit/launch/domain/test_step_definition_field_set.py` | 4 | the declared attribute list, and the removed fields |
| `tests/unit/launch/application/test_step_activation.py` | 8 | activation as a validated transition; the handler registry |
| `tests/unit/launch/application/test_step_retirement_and_slots.py` | 12 | retirement as a status; slots over the active set |
| `tests/unit/launch/application/test_step_assignee_preconditions.py` | 11 | write-time preconditions, scoped to the touched steps |
| `tests/unit/launch/application/test_playbook_authoring_new_field_set.py` | 7 | create/update under the new authorable shape |
| `tests/unit/launch/application/test_report_activation_blockers.py` | 4 | the report that replaces undecided-rule-policies |
| `tests/unit/launch/infrastructure/driven/test_clickup_projection_step_fields.py` | 14 | name, body, assignees, and the projection filter |
| `tests/unit/launch/infrastructure/driven/test_clickup_non_active_steps_leave_loop.py` | 5 | leaving the loop by any of the three routes |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py` | 17 | the form, the table, the status control, reordering |
| `tests/integration/launch/test_seeded_step_fields.py` | 16 | the seeded set and the backfill, against live Postgres |

**129 test functions.** Two are parametrised (three cases each), so the
collected count will be higher.

---

## Scenario accounting

The delta specs contain **120** `#### Scenario:` blocks. Every one is
accounted for below, exactly once.

Legend for the *Covered by* column: a bare test name is in the new file
named at the head of its block; a path-qualified name is an **existing**
test that already covers the scenario (see *Existing tests that cover a
carried-forward scenario*).

### `launch-playbook` (45 scenarios)

#### Requirement: A step declares a lifecycle status, and only active steps are served

| Scenario | Covered by (`tests/unit/launch/domain/test_step_lifecycle_status.py`) |
| --- | --- |
| A draft step is authored but not served | `test_a_draft_step_is_authored_but_not_served` |
| Only active steps hold a gate | `test_only_active_steps_hold_a_gate` |
| A retired step leaves the served set without leaving the record | `test_a_retired_step_leaves_the_served_set_without_leaving_the_record` |

Also in that file, covering requirement statements no scenario states:
`test_status_has_exactly_the_four_specified_values`,
`test_a_step_whose_author_declares_no_status_is_a_draft`.

#### Requirement: A step names who does the work and whether a person accepts it

| Scenario | Covered by (`.../test_step_kind_and_confirmation.py`) |
| --- | --- |
| An automated step declares whether its result is accepted | `test_an_automated_step_declares_whether_its_result_is_accepted` |
| The playbook records no automation detail beyond the kind | `test_the_playbook_records_no_automation_detail_beyond_the_kind` |
| Kind and confirmation are independent | `test_kind_and_confirmation_are_independent` |

Plus `test_a_human_steps_confirmation_flag_is_ignored_rather_than_rejected`
for the "ignored rather than rejected" rule, which no scenario states.

#### Requirement: A step carries the brief and the handler its automation needs

| Scenario | Covered by |
| --- | --- |
| A draft automated step needs neither | `.../test_step_automation_brief_and_handler.py::test_a_draft_automated_step_needs_neither` |
| Leaving draft requires the brief | `tests/unit/launch/application/test_step_activation.py::test_leaving_draft_requires_the_brief` (write) + `.../test_step_automation_brief_and_handler.py::test_an_automated_step_beyond_draft_without_a_brief_is_rejected` (load) |
| A handler the code does not register cannot be activated | `tests/unit/launch/application/test_step_activation.py::test_a_handler_the_code_does_not_register_cannot_be_activated` |
| A human step carries no automation fields | `.../test_step_automation_brief_and_handler.py::test_a_human_step_carrying_an_automation_brief_is_rejected` and `::test_a_human_step_carrying_a_handler_is_rejected`; write half in `test_step_activation.py::test_a_human_step_written_with_automation_fields_is_refused` |

Requirement statements no scenario states, covered in the same file:
`test_a_retired_automated_step_owes_no_brief` ("beyond `draft`" excludes
`retired`), `test_an_active_automated_step_without_a_handler_is_rejected`
(presence is a load rule),
**`test_a_load_never_checks_whether_the_handler_is_registered`** (the
review point: registration is *not* a load rule),
`test_an_automated_step_with_both_is_accepted` (the permitted side), and
`test_step_activation.py::test_a_deploy_dropping_an_active_steps_handler_is_reported_at_startup`.

#### Requirement: A step names the people responsible for it

| Scenario | Covered by (`tests/unit/launch/application/test_step_assignee_preconditions.py`) |
| --- | --- |
| An active human step needs someone responsible | `test_an_active_human_step_needs_someone_responsible` |
| An unknown person is rejected | `test_an_unknown_person_is_rejected` |
| A deactivated person does not satisfy the requirement | `test_a_deactivated_person_does_not_satisfy_the_requirement` |
| Correcting a person does not touch the steps | `test_correcting_a_person_does_not_touch_the_steps` |

The requirement's load-side paragraph — the rules are write-time
preconditions and a load never re-checks them — is covered in
`tests/unit/launch/domain/test_step_assignees_are_not_a_load_rule.py`
(all five tests).

#### Requirement: An incoherent playbook is rejected against each step's status

| Scenario | Covered by | Note |
| --- | --- | --- |
| Gate sequence deviates from the specification | `tests/unit/launch/domain/test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`, `::test_gate_sequence_with_an_extra_gate_is_rejected`, `::test_gate_sequence_in_the_wrong_order_is_rejected`, `::test_gate_sequence_repeating_a_position_is_rejected` | rule unchanged; fixture migration only |
| A gate's opening mode disagrees with the specification | `.../test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected` | rule unchanged |
| Duplicate step identifier | `.../test_launch_playbook.py::test_duplicate_step_identifier_is_rejected` | rule unchanged |
| Step references an unknown gate | `.../test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected` | rule unchanged |
| A step with no name is rejected by identifier | `.../test_playbook_coherence_by_status.py::test_a_step_with_no_name_is_rejected_by_identifier` (3 params) + `::test_the_name_is_required_rather_than_defaulted` | **rule moved from description to name** |
| A name spanning several lines is rejected | `.../test_playbook_coherence_by_status.py::test_a_name_spanning_several_lines_is_rejected` | **rule moved** |
| A description spanning several lines is accepted | `.../test_playbook_coherence_by_status.py::test_a_description_spanning_several_lines_is_accepted` (+ `::test_a_description_is_optional`) | **new rule** |
| Automation past draft without a brief | `.../test_step_automation_brief_and_handler.py::test_an_automated_step_beyond_draft_without_a_brief_is_rejected` | **rule restated against status** |
| A prohibited tactic cannot block a gate | `.../test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`, `::test_prohibited_tactic_that_does_not_block_is_accepted` | rule unchanged |
| A gate with no active blocking step is rejected | `.../test_playbook_coherence_by_status.py::test_a_gate_whose_only_blocking_step_is_a_draft_is_rejected`, `::test_a_gate_whose_only_blocking_step_is_in_development_is_rejected` | **floor now counts only active steps** |
| A malformed metric condition is rejected | `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_metric_condition_with_an_empty_threshold_is_rejected` | rule unchanged |
| Multiple violations are reported together | `.../test_playbook_coherence_by_status.py::test_two_violations_of_the_new_rules_are_reported_together` | **re-established over the new rules**; the existing test of this scenario pairs two faults that cease to exist |
| A malformed step is reported alongside a coherence violation | `tests/unit/launch/infrastructure/driven/test_playbook_repository_rows.py` (both tests) | coverage was re-homed there by `move-playbook-steps-to-postgres`; unaffected by this delta |
| A coherent playbook loads | `.../test_playbook_coherence_by_status.py::test_a_coherent_playbook_loads` | **"coherent" is redefined** |

#### Requirement: What blocks a step from being activated is reported

| Scenario | Covered by (`.../application/test_report_activation_blockers.py`) |
| --- | --- |
| Steps that cannot be activated are listed with their reason | `test_steps_that_cannot_be_activated_are_listed_with_their_reason` |
| A set of ready steps reports nothing | `test_a_set_of_ready_steps_reports_nothing` |

Plus `test_a_step_missing_a_registered_handler_is_reported` and
`test_a_step_whose_only_assignee_was_deactivated_is_reported` for the two
"what it is missing" cases the requirement names but no scenario exercises.

#### Requirement (MODIFIED): A step definition declares how it is to be resolved

| Scenario | Covered by (`.../domain/test_step_definition_field_set.py`) |
| --- | --- |
| A step definition is read back with every declared attribute | `test_a_step_definition_is_read_back_with_every_declared_attribute` + `test_unauthored_optional_attributes_are_absent` |
| Steps can be selected by gate and by scope | `test_steps_can_be_selected_by_gate_and_by_scope` |

Plus `test_the_removed_fields_are_gone_from_the_step` (`binding`,
`execution`, `Binding`, `ExecutionMode` are deleted, not deprecated).

#### Requirement (MODIFIED): Every gate is held by at least one blocking step

| Scenario | Covered by |
| --- | --- |
| No gate opens for free | `.../test_playbook_coherence_by_status.py::test_no_gate_opens_for_free` (unit) and `tests/integration/launch/test_seeded_step_fields.py::test_no_gate_opens_for_free_in_the_served_set` (seeded set) |

#### Requirement (MODIFIED): The authored set exercises the full step vocabulary

| Scenario | Covered by (`tests/integration/launch/test_seeded_step_fields.py`) |
| --- | --- |
| Anchor kinds are all present | `test_every_timing_anchor_kind_is_represented` |
| Every discipline appears | `test_every_discipline_is_represented` |
| Execution modes and the compliance hazard are represented | `test_kinds_confirmation_and_the_compliance_hazard_are_represented` |
| Prohibited tactics are present and never block | `test_prohibited_tactics_are_present_and_never_block` |
| Outstanding rule-policy decisions stay visible | `test_outstanding_readiness_decisions_stay_visible` |

Plus `test_every_seeded_human_step_is_active_and_the_automated_ones_are_not`
for the requirement's new status paragraph.

#### Requirement (MODIFIED): The seeded step set carries the authored v1 definitions

| Scenario | Covered by (`tests/integration/launch/test_seeded_step_fields.py`) |
| --- | --- |
| The shipped playbook loads with steps | `test_the_playbook_loads_with_steps_after_the_backfill` |
| BUILD THE LISTING is fully represented | `test_build_the_listing_is_fully_represented` |
| A step traces to its source row | `test_a_step_traces_to_its_source_row` |
| A step states its work without the source document | `test_a_step_states_its_work_without_the_source_document` |
| Every description re-derives from its reference row | `test_every_name_re_derives_from_its_reference_row` |
| A gate-authored condition is not duplicated as a step | `test_a_gate_authored_condition_is_not_duplicated_as_a_step` |
| The seed runs once | **UNCOVERED** — see below |

**Uncovered, with reason.** *The seed runs once* is uncovered for exactly
the reason the existing seed file already records: forcing the seed
revision to re-execute needs downgrade/upgrade cycling around a revision
identifier that does not exist yet, and re-running `alembic upgrade head`
at head is a no-op by construction — an assertion that cannot fail. This
change does not alter the seed's run-once machinery, so it introduces no
new reason to cover it now.

Backfill coverage owed by `tasks.md` 6.4, beyond the scenarios:
`test_no_seeded_human_step_carries_an_automation_brief`,
`test_every_seeded_automated_step_carries_its_brief`,
`test_migrated_steps_are_unowned_and_carry_no_description`.

### `playbook-authoring` (24 scenarios)

| Scenario | Covered by |
| --- | --- |
| An activation that satisfies its kind's rules lands | `test_step_activation.py::test_an_activation_that_satisfies_its_kinds_rules_lands` |
| A refused activation explains itself and persists nothing | `test_step_activation.py::test_a_refused_activation_explains_itself_and_persists_nothing` |
| Registering a handler does not activate anything | `test_step_activation.py::test_registering_a_handler_does_not_activate_anything` |
| Un-activating a gate's last blocking step is refused | `test_step_activation.py::test_un_activating_a_gates_last_blocking_step_is_refused` |
| A retired step leaves the served set | `test_step_retirement_and_slots.py::test_retiring_sets_the_status_and_deletes_nothing` |
| A retired step's history stays readable | `test_step_retirement_and_slots.py::test_a_retired_steps_definition_survives_whole` (store half) + `tests/unit/launch/domain/test_outcomes_after_retirement.py` (aggregate half, existing) |
| An un-retired step rejoins the served set | `test_step_retirement_and_slots.py::test_an_un_retired_step_returns_to_in_development` |
| Activating a retired step from the status control still records the reversal | `test_step_retirement_and_slots.py::test_the_status_control_moving_a_step_out_of_retired_records_the_reversal` (+ `::test_the_status_control_moving_a_step_into_retired_records_the_retirement` for the unstated *into* half) |
| A rejected write reports all faults and persists nothing | `test_step_assignee_preconditions.py::test_a_rejected_write_reports_all_faults_and_persists_nothing` |
| Retiring a gate's last blocking step is rejected | `test_step_retirement_and_slots.py::test_retiring_a_gates_last_active_blocking_step_is_rejected` |
| What a write cannot persist, a load cannot see | `test_step_assignee_preconditions.py::test_what_a_write_cannot_persist_a_load_cannot_see` |
| An untouched unowned step does not block an unrelated write | `test_step_assignee_preconditions.py::test_an_untouched_unowned_step_does_not_block_an_unrelated_write` |
| Editing an unowned step requires giving it an owner | `test_step_assignee_preconditions.py::test_editing_an_unowned_step_requires_giving_it_an_owner` |
| A roster change does not break an accepted set | `test_step_assignee_preconditions.py::test_a_roster_change_does_not_break_an_accepted_set` (load half) + `test_report_activation_blockers.py::test_a_step_whose_only_assignee_was_deactivated_is_reported` (report half) |
| A created step appends to its gate | `test_step_retirement_and_slots.py::test_a_created_active_step_appends_to_its_gate` |
| An un-retired step rejoins at the end | `test_step_retirement_and_slots.py::test_a_step_entering_active_takes_the_last_slot` |
| A draft holds no slot | `test_step_retirement_and_slots.py::test_a_created_draft_holds_no_slot` |
| A gate change appends to the new gate | `test_step_retirement_and_slots.py::test_a_gate_change_appends_to_the_new_gate` |
| Retirement closes the gap | `test_step_retirement_and_slots.py::test_retirement_closes_the_gap` |
| A created step joins the served set | `test_playbook_authoring_new_field_set.py::test_a_created_step_carries_the_whole_new_authorable_shape` (+ `::test_creating_a_draft_requires_only_what_a_draft_carries` for the not-served half) |
| Created identifiers never collide with the seeded namespace | `test_playbook_authoring_new_field_set.py::test_created_identifiers_never_collide_retired_included` |
| An edit is served on the next read | `test_playbook_authoring_new_field_set.py::test_an_edit_to_the_name_is_served_on_the_next_read` |
| A discipline change is rejected | `test_playbook_authoring_new_field_set.py::test_a_discipline_change_is_rejected` |
| An edit to a seeded step keeps its citation and gains attribution | `test_playbook_authoring_new_field_set.py::test_an_edit_to_a_seeded_step_keeps_its_citation_and_is_attributed` |

Requirement statement covered beyond the scenarios:
`test_step_retirement_and_slots.py::test_a_step_leaving_active_without_being_retired_loses_its_slot`
("by retirement or by any other status change").

### `playbook-admin` (26 scenarios)

| Scenario | Covered by |
| --- | --- |
| The form offers name and description separately | `test_playbook_admin_step_fields.py::test_the_form_offers_name_and_description_separately` |
| Assignees are chosen from the roster | `::test_assignees_are_chosen_from_the_rosters_active_people` |
| A form rejected by validation shows every fault with the typed values | `::test_a_form_rejected_by_validation_shows_every_fault_with_the_typed_values` |
| Draft and in-development steps are shown and marked | `::test_draft_and_in_development_steps_are_shown_and_marked` |
| Retired steps stay behind their control | `::test_retired_steps_stay_behind_their_control` |
| Assignees are visible on the table | `::test_assignees_are_visible_on_the_table` |
| An activation lands and the step joins the served set | `::test_an_activation_from_the_page_lands_and_joins_the_served_set` |
| A refused activation explains itself | `::test_a_refused_activation_explains_itself_on_the_page` |
| The whole live set is one page | `::test_the_whole_authored_set_other_than_retired_is_one_page` |
| Filters narrow without altering | `::test_filters_narrow_without_altering` |
| Search matches description text | `::test_search_matches_the_name_and_the_description_alike` |
| Retired steps are reachable but set apart | `::test_retired_steps_are_reachable_but_set_apart` |
| A position is read against the whole gate | `::test_a_position_is_read_against_the_whole_gate` |
| Reordering is unavailable under a description search | `::test_reordering_is_unavailable_under_a_search_over_either_field` |
| A draft in the gate does not remove reordering | `::test_a_draft_in_the_gate_does_not_remove_reordering` |
| A move sticks | `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py::test_a_move_sticks` |
| A filtered move lands against the visible step it names | `tests/unit/launch/infrastructure/driving/test_playbook_admin_filtered_moves.py` |
| A filtered move upwards lands against the visible step above the one it passes | `.../test_playbook_admin_filtered_moves.py` |
| A filtered move disturbs nothing else | `.../test_playbook_admin_filtered_moves.py` |
| A move to the head of a narrowed list stops at the first visible step | `.../test_playbook_admin_filtered_moves.py` |
| A move to the end of a narrowed list stops at the last visible step | `.../test_playbook_admin_filtered_moves.py` |
| A move that changes nothing persists nothing | `.../test_playbook_admin_filtered_moves.py` |
| Reordering is unavailable while retired steps are shown | `.../test_playbook_admin_filtered_moves.py` |
| A move submitted where reordering is unavailable is refused | `.../test_playbook_admin_filtered_moves.py` |
| A move submitted from a superseded list is rejected | `tests/unit/launch/application/test_playbook_reorder_pinned_version.py` and `.../test_playbook_admin_filtered_moves.py` |
| A stale move leaves truth on the page | `tests/unit/launch/infrastructure/driving/test_playbook_admin_page.py::test_a_stale_move_leaves_truth_on_the_page` |

The eleven reorder scenarios carried by existing tests are **unchanged in
substance** by this delta; only their fixtures name removed fields. See
*Existing tests that cover a carried-forward scenario*.

Requirement statements covered beyond the scenarios:
`::test_the_form_offers_every_authorable_field` (the field list, stated
once and in no scenario) and
`::test_a_move_naming_a_step_that_holds_no_slot_is_refused` (the
server-side refusal `tasks.md` 5.3 names).

### `launch-clickup-sync` (25 scenarios)

| Scenario | Covered by |
| --- | --- |
| A human step gets a task | `test_clickup_projection_step_fields.py::test_a_human_step_gets_a_task_named_from_its_name` |
| A step's description becomes the task's body | `::test_a_steps_description_becomes_the_tasks_body` + **`::test_a_step_with_no_description_has_no_body_written_at_all`** + `::test_a_pre_existing_body_is_left_standing_when_the_step_has_none` |
| A task is assigned to the step's people | `::test_a_task_is_assigned_to_the_steps_people` |
| An existing unowned task gains its step's assignees | `::test_an_existing_unowned_task_gains_its_steps_assignees` |
| A person's own assignment change is not overwritten | `::test_a_persons_own_assignment_change_is_not_overwritten` |
| An assignee with no ClickUp account is reported, not silently dropped | `::test_an_assignee_with_no_clickup_account_is_reported_not_dropped` |
| A step activated mid-launch is projected | `::test_a_step_activated_mid_launch_is_projected` |
| A person's body note survives a wording edit | `::test_a_persons_body_note_survives_a_wording_edit` |
| An unedited legacy task starts healing | `::test_an_unedited_task_heals_to_the_new_composition` |
| An over-long name is shortened rather than failing | `::test_an_over_long_name_is_shortened_and_never_spills_into_the_body` |
| Automated steps are never projected | `::test_automated_steps_are_never_projected` |
| A step that is not active is never projected | `::test_a_step_that_is_not_active_is_never_projected` (3 params) |
| A renamed task still resolves to its step | `tests/unit/launch/infrastructure/driven/test_clickup_task_naming.py::test_a_renamed_task_still_resolves_to_its_step` |
| An unedited task follows the step's current wording | `.../test_clickup_sync_wording_heal.py::test_an_unedited_task_follows_the_steps_current_wording` |
| An ambiguous legacy task is never rewritten | `.../test_clickup_sync_wording_heal.py::test_an_ambiguous_legacy_task_is_never_rewritten` |
| An edited task name is never restored | `.../test_clickup_sync_wording_heal.py::test_an_edited_task_name_is_never_restored` |
| An existing task is not recreated | `.../test_clickup_sync_projection.py::test_an_existing_task_is_not_recreated` |
| A prohibited-tactic step is never projected | `.../test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected` |
| A deleted task for unfinished work is re-projected | `.../test_clickup_sync_projection.py::test_a_deleted_task_for_unfinished_work_is_re_projected` |
| A deleted task for finished work stays gone | `.../test_clickup_sync_projection.py::test_a_deleted_task_for_finished_work_stays_gone` |
| A retired step's task is left unmanaged | `test_clickup_non_active_steps_leave_loop.py::test_a_retired_steps_task_is_left_unmanaged` |
| A retired step's closure is not recorded | `test_clickup_non_active_steps_leave_loop.py::test_a_retired_steps_closure_is_not_recorded` |
| A closure during retirement is never replayed | `.../test_clickup_sync_retired_steps.py::test_a_closure_during_retirement_is_never_replayed` |
| An un-retired step resumes through its existing task | `test_clickup_non_active_steps_leave_loop.py::test_a_step_returning_to_active_resumes_through_its_existing_task` |
| A de-activated step leaves the loop exactly as a retired one does | `test_clickup_non_active_steps_leave_loop.py::test_a_de_activated_step_leaves_the_loop_exactly_as_a_retired_one_does` |

Requirement statement covered beyond the scenarios:
`test_clickup_non_active_steps_leave_loop.py::test_a_draft_step_with_a_leftover_task_is_left_alone`
(the third route out of the served set).

**Count check: 45 + 24 + 26 + 25 = 120 scenarios; 119 covered, 1 recorded
uncovered with its reason (*The seed runs once*).**

---

## Assertion provenance

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. The classification is carried **inline** in each
test's docstring and in comments beside the assertions (`SPECIFIED:` /
`DERIVED:` / `DELIBERATELY UNTESTED:`), following this repository's
existing convention. Summarised:

### Specified

Every assertion about: which write lands and which is refused; what a
refusal names (the step, the gate, the unknown identifier, the unknown
handler); that a refused write persists nothing; which steps are served;
which gate is held; what a projected task's name and body are, and whether
a body is written at all; which steps project; what the status control
records; what the seeded set contains and how each seeded name re-derives
from its reference row.

### Derived (inferred; no stated requirement covers them)

Each of these obliges an implementer to satisfy something nobody agreed to,
and each is a legitimate target for review:

- **Fault-wording substrings.** Several refusal tests assert a marker word
  (`"assign"`, `"brief"`, `"handler"`, `"name"`, `"prohibited"`) so that
  two faults in one message are distinguishable. Correcting a substring to
  the implemented wording is a fixture correction; collapsing a
  two-fault check to one is not. Precedent: the same convention in
  `test_playbook_authoring.py`.
- **The absence probes.** `_NO_AUTOMATION_DETAIL` (kind/confirmation
  file), `_NOT_ON_A_STEP` (assignees file), and
  `LaunchPlaybook`'s constructor-parameter probe. Each is a best-effort
  list of spellings a forbidden thing would take, not an exhaustive one.
- **Enum member spellings** (`StepStatus.IN_DEVELOPMENT`,
  `StepKind.HUMAN`). The specs give wire values; the Python identifiers
  are inferred.
- **A non-active step may name a deactivated person** — the spec conditions
  the active-assignee rule on an `active` `human` step and says nothing
  about the others. `test_a_deactivated_person_may_still_be_named_on_a_step_not_yet_active`
  records the reading and the reason for it.
- **Admin page markers**: that a status is "legible" if its word appears in
  the step's rendered region; that "set apart" is observable as the step
  offering no reorder control; that the assignee chooser is a `select`.
- **`_row_text()` in the blockers report**, which reads a row via `repr`
  so only the four identifying fields are addressed by name.
- **The ClickUp payload probes** (`_body_in`, `_assignees_in`, `_as_ids`),
  which accept any plausible wire spelling rather than pinning one.
- **Position/count rendering as the digit `4`** in
  `test_a_position_is_read_against_the_whole_gate` — the spec fixes that
  the count is of the gate's active steps, not how it is rendered.

### Deliberately untested (recorded, not omitted)

- *The seed runs once* — reason above.
- Whether `assignees` preserves the order it was given: nothing makes them
  ordered, and a set-like implementation failing the one order-sensitive
  assertion is a finding for review, not a fixture to loosen unreviewed.
- The *form* of a roster identifier: `roster` generates it and no artifact
  of this change fixes it.
- Whether a `human` step's confirmation flag reads back as written or
  normalised to false: "ignored" fixes that nothing reads it, not what it
  reads back as.
- Whether the activation-blockers report ever lists a `retired` step: the
  spec does not say.
- The webhook path of *A retired step's closure is not recorded*: covered
  by the existing `test_clickup_webhook.py` and unchanged by this delta
  beyond which steps count as served.
- Concurrency between interleaved writes: not deterministically observable
  through the store seam (the same exclusion `test_playbook_authoring.py`
  already records).

---

## Superseded tests — candidates for human confirmation

**Search bound.** Only `tests/**/test_*.py` was searched, and within it
only the `launch` module plus `briefing` (which the field-name grep also
reaches). Matching was by `grep -rln 'ExecutionMode|Binding|rule_policy|
execution=|binding='` over `tests/`, plus a per-requirement read of the
existing tests named by each MODIFIED/REMOVED delta entry. No earlier
`test-manifest.md` path was supplied to this pass, so no
scenario-to-test mapping from a previous change was available; **this list
is what this bounded search found, not a claim that nothing else bears on
the change.**

**Every entry below is a candidate for human confirmation. Nothing here
was edited, deleted or disabled by this pass.**

### A. The `binding` / lesson-cannot-block rule (removed outright)

Superseding delta: `launch-playbook` — the REMOVED requirement *An
incoherent playbook is rejected at load time* and its replacement, whose
rule list drops "a step definition's binding is `lesson` and it is marked
as blocking its gate"; `proposal.md` deletes `Binding`.

| Test | Evidence |
| --- | --- |
| `tests/unit/launch/domain/test_playbook_coherence_completion.py::test_a_lesson_step_marked_blocking_is_rejected` | asserts `InvalidPlaybookError` for `Binding.LESSON` + `blocking=True` — the rule that ceases to exist |
| `.../test_playbook_coherence_completion.py::test_a_non_blocking_lesson_step_is_accepted` | the permitted side of the same rule; reads `read_back.binding is Binding.LESSON` |
| `.../test_playbook_coherence_completion.py::test_the_two_new_faults_are_reported_together` | **partially** superseded: pairs a blocking lesson with an empty metric threshold. The aggregation assertion survives; the first fault does not, so the pairing must be re-derived from a surviving rule — not deleted |
| `tests/unit/launch/domain/test_gate_holding_floor.py::test_the_floor_fault_is_reported_alongside_another_fault` | **partially** superseded, same shape: its second fault is a lesson-bound blocking step |
| `tests/unit/launch/application/test_playbook_authoring.py::test_a_rejected_write_reports_all_faults_and_persists_nothing` | named outright by `tasks.md` 6.2: its two faults are an empty description and a lesson-bound blocking step, **and neither remains a fault**. Replacement: `test_step_assignee_preconditions.py::test_a_rejected_write_reports_all_faults_and_persists_nothing` |

### B. The `ExecutionMode` vocabulary and the `rule_policy` rule

Superseding delta: `launch-playbook` — REMOVED *An undecided rule does not
prevent loading* and REMOVED *Undecided rule policies are reported*; the
kind/confirmation requirement replaces the three-value mode.

| Test | Evidence |
| --- | --- |
| `tests/unit/launch/domain/test_launch_playbook.py::test_automated_step_without_a_rule_policy_is_rejected` | asserts the rule "automated ⇒ rule policy required", now restated against status as "automated **beyond draft** ⇒ brief required" |
| `.../test_launch_playbook.py::test_ai_assisted_step_without_a_rule_policy_is_rejected` | `ExecutionMode.AI_ASSISTED` no longer exists |
| `.../test_launch_playbook.py::test_automated_step_with_a_rule_policy_is_accepted` | the permitted side of the same rule, in the removed vocabulary |
| `.../test_launch_playbook.py::test_human_attested_step_with_no_rule_policy_loads` | the sole test of the REMOVED requirement *An undecided rule does not prevent loading* |
| `tests/unit/launch/application/test_report_undecided_rule_policies.py` (**both** tests) | the whole file is the REMOVED requirement *Undecided rule policies are reported*. Replacement: `tests/unit/launch/application/test_report_activation_blockers.py` |

### C. `description` as the required, single-line field

Superseding delta: `launch-playbook` — the MODIFIED step-definition
requirement moves the emptiness and single-line rules to `name` and makes
`description` optional and multi-line.

| Test | Evidence |
| --- | --- |
| `tests/unit/launch/domain/test_step_description.py` (all 8 tests) | the file's subject is the description being required, non-empty and single-line — `test_a_step_with_an_empty_description_is_rejected_by_name`, `test_a_description_spanning_several_lines_is_rejected`, `test_a_single_line_description_is_accepted`, and their aggregation partners. `test_a_description_spanning_several_lines_is_rejected` now asserts the **opposite** of the spec |
| `tests/unit/launch/domain/test_step_description_whitespace.py` (all 4 tests) | same rule, whitespace-only case |

Replacement coverage:
`tests/unit/launch/domain/test_playbook_coherence_by_status.py` (the name
rules) and `::test_a_description_spanning_several_lines_is_accepted` /
`::test_a_description_is_optional`.

### D. The ClickUp name composed from the description

Superseding delta: `launch-clickup-sync` — REMOVED *Human-attested steps
are projected as tasks*; the name now comes from `name` and the body from
`description`.

| Test | Evidence |
| --- | --- |
| `tests/unit/launch/infrastructure/driven/test_clickup_task_name_composition.py::test_the_composed_name_is_exactly_description_separator_identifier` | asserts the name is `description · identifier` |
| `.../test_clickup_task_name_composition.py::test_a_description_naming_its_own_discipline_is_composed_unaltered` | same composition, description as source |
| `.../test_clickup_task_name_composition.py::test_a_task_whose_name_fits_is_created_without_a_body` | asserts **no body** where the name fits — under the new rule a step carrying a description always gets one |
| `.../test_clickup_task_naming.py::test_a_projected_task_is_named_description_then_identifier` | the name's title states the superseded composition |
| `.../test_clickup_sync_projection.py::test_a_human_attested_step_gets_a_task` | the projection filter it exercises (`human-attested`) no longer exists |
| `.../test_clickup_sync_projection.py::test_automated_and_ai_assisted_steps_are_never_projected` | `ai-assisted` no longer exists; replaced by `test_automated_steps_are_never_projected` |

### E. Seed tests keyed to the old fields

Superseding delta: `launch-playbook` — the seeded-set requirements
restated against `name`, kind/confirmation and status.

| Test | Evidence |
| --- | --- |
| `tests/integration/launch/test_playbook_seed.py::test_every_description_re_derives_from_its_reference_row` | compares the **description** against the reference row; the migration sets description to null and moves the text to `name` |
| `.../test_playbook_seed.py::test_every_seeded_step_states_its_work` | asserts a non-empty description |
| `.../test_playbook_seed.py::test_execution_modes_and_the_compliance_hazard_are_represented` | groups by `ExecutionMode` and asserts a rule policy per mode |
| `.../test_playbook_seed.py::test_outstanding_rule_policy_decisions_stay_visible` | calls `report_undecided_rule_policies`, which `tasks.md` 2.5 replaces |
| `.../test_playbook_seed.py::MODES_REQUIRING_A_RULE_POLICY` (module constant) | names the removed enum; the file will not import once `ExecutionMode` is deleted |

### F. Not superseded — fixture migration required (do **not** delete)

These tests assert behaviour this change leaves standing. Their fixtures
construct a `StepDefinition` with `binding=` / `execution=` /
`rule_policy=`, so they will not import or construct once the field set
lands. `tasks.md` 6.3 assigns the repair, and it says outright: **"Rewrite
from the new requirement; do not edit assertions to pass."**

`tests/unit/launch/domain/test_launch_playbook.py` (the gate-sequence,
duplicate-identifier, unknown-gate, prohibited-tactic and coherent-load
tests), `test_gate_holding_floor.py`, `test_step_definition_discipline.py`,
`test_gate_conditions.py`, `test_launch_dates.py`,
`test_launch_gate_advance.py`, `test_launch_run.py`,
`test_outcomes_after_retirement.py`,
`test_within_gate_order_commitment_neutrality.py`,
`tests/unit/launch/application/test_graduation.py`,
`test_launch_reports.py`, `test_playbook_authoring.py`,
`test_playbook_reorder.py`, `test_playbook_reorder_pinned_version.py`,
`test_scope_aware_launch_reads.py`,
`tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py`,
`test_clickup_sync_reconciliation.py`, `test_clickup_sync_retired_steps.py`,
`test_clickup_sync_wording_heal.py`, `test_clickup_task_naming.py`,
`test_clickup_task_name_composition.py`,
`tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`,
`test_playbook_admin_page.py`, `test_playbook_admin_filtered_moves.py`,
`test_slack_entry_*.py` (three files),
`tests/unit/briefing/application/test_briefing_assembly.py`,
`test_briefing_delivery.py`, and the four
`tests/integration/launch/test_*.py` files that build step definitions.

**`test_outcomes_after_retirement.py` deserves a specific look**: `design.md`
Decision 2 moves retirement from the record to the status, so whatever that
file uses to make a step retired changes mechanism even though its
assertions do not.

---

## Unresolved project questions

Each was answered by assumption because this pass has no channel to ask on.
Every one names the tests that depend on it and the single place to correct.

| # | Question | Assumption taken | Depends on it | Correction point |
| --- | --- | --- | --- | --- |
| Q1 | How does a `launch` use case receive the roster reader? | a `roster=` keyword argument on each write use case and on `converge_launch`, answering `list_people()` (also callable, also `person(id)`) | every application-tier and ClickUp test | `_create`/`_update`/`_converge` helpers; `_FakeRoster` |
| Q2 | What shape is the handler registry, and how does a use case receive it? | a `handlers=` keyword argument satisfied by a container answering `__contains__` / `__iter__` / `names()` | `test_step_activation.py`, `test_report_activation_blockers.py` | `_FakeHandlerRegistry` |
| Q3 | Is a status change a dedicated use case or `update_step(status=...)`? | either — `_set_status()` prefers `change_step_status` / `set_step_status` if exported, else falls back to `update_step(status=...)` | activation, retirement and assignee files | `_set_status` |
| Q4 | What is the activation-blockers report called, and what does it take? | one of four candidate names, taking `steps=`, `roster=`, `handlers=`; rows expose `identifier`, `gate`, `discipline`, `status` | `test_report_activation_blockers.py`, `test_seeded_step_fields.py` | `_REPORT_NAMES`, `_blockers` |
| Q5 | What is the startup unregistered-handler report called? | one of four candidate names, taking `steps=` and `handlers=`, sync or async | `test_step_activation.py` (2 tests) | `_STARTUP_REPORTS`, `_startup_report` |
| Q6 | How is the **authored** set (every status) read back? | an accessor on the playbook (`authored_steps` / `all_steps` / `steps`) or on the repository | lifecycle, brief/handler and seed files | `_authored` / `_authored_steps` |
| Q7 | How does the admin page reach the roster? | a module attribute named one of `roster` / `read_roster` / `people` / `roster_reader`, substituted with `monkeypatch.setattr`; **fails loudly if none exists** | every admin-page test | `_install_roster`, `_ROSTER_ATTRIBUTES` |
| Q8 | What does the page's status control look like, and how is a status made "legible"? | a form or control whose URL/fields mention the step and `status`; legibility = the status word appears in the step's rendered region | `test_playbook_admin_step_fields.py` (status/table tests) | `_status_control`, `_row_marks_status` |
| Q9 | How do assignees reach ClickUp, and how are the last-set ones retained? | any create/update field whose key contains "assign", as a list or `{"add": [...]}`; retained via `record_composition(assignees=)` **or** `record_assignees(...)` | `test_clickup_projection_step_fields.py` | `_assignees_in`, `_as_ids`, `_FakeMapping` |
| Q10 | Python spellings of the new enum members | `StepKind.HUMAN`/`AUTOMATED`, `StepStatus.DRAFT`/`IN_DEVELOPMENT`/`ACTIVE`/`RETIRED` | every file | the imports |
| Q11 | The integration tier has never run here | the new integration file has **never been executed**: no database is configured on this machine, and the tier skips through its `database_url` gate. `tasks.md` 6.4's coverage exists but is unverified until someone runs it against Postgres | `tests/integration/launch/test_seeded_step_fields.py` | run it with `DATABASE_URL` set, after both migrations |
| Q12 | Must a non-`active` step's assignees be active? | no — the spec conditions the rule on an `active` `human` step | `test_a_deactivated_person_may_still_be_named_on_a_step_not_yet_active` | that test |
| Q13 | Does the readiness report list `retired` steps? | unanswered; nothing asserts either way | — | recorded as deliberately untested |
| Q14 | The suite cannot run at all while these tests are red | `uv run pytest` aborts on collection errors, and the `pre-commit` hook runs the whole unit tree, so **commits are blocked until the domain field set exists**. This pass did not work around it | the whole suite | implement `StepKind`/`StepStatus` first, or run with `--continue-on-collection-errors` |

---

## What the implementation step must make pass

In rough dependency order:

1. `StepKind`, `StepStatus`, and the restated `StepDefinition` in
   `launch/domain/launch_playbook.py`, with `Binding` and `ExecutionMode`
   deleted. **Until this lands, `uv run pytest` collects nothing.**
2. The coherence rules against status, and the served/authored split on
   `LaunchPlaybook`, including the authored read (Q6).
3. The write use cases' new collaborators (Q1, Q2), the validated status
   transition (Q3), the retire/un-retire semantics, and the slot rules over
   the active set.
4. The two reports (Q4, Q5).
5. The ClickUp projection's name/body/assignee mapping and its filter.
6. The admin page's form, table, status control and reorder rules (Q7, Q8).
7. The schema migration and the backfill, then a run of
   `tests/integration/launch/test_seeded_step_fields.py` against a live
   database (Q11).

Four rules were called out as hard-won in review and each has a test whose
only job is to catch the backwards implementation:

- assignee rules are **write-time only, over the touched steps** —
  `test_step_assignees_are_not_a_load_rule.py` and
  `test_an_untouched_unowned_step_does_not_block_an_unrelated_write`;
- handler **presence** is a load rule, **registration** is not —
  `test_a_load_never_checks_whether_the_handler_is_registered`;
- a step with no description composes **no body at all** —
  `test_a_step_with_no_description_has_no_body_written_at_all` and
  `test_a_pre_existing_body_is_left_standing_when_the_step_has_none`;
- a move into or out of `retired` **is** the retire / un-retire write, and
  arrives at `in-development` on the way out —
  `test_the_status_control_moving_a_step_out_of_retired_records_the_reversal`
  and its `into` counterpart.
