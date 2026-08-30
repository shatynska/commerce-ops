# Test manifest — `add-step-confirmer`

Not an OpenSpec-tracked artifact. `openspec instructions apply` will not
list this file among its context files — read it on purpose before
implementing, as the imported `rules/` fragment already directs (that
fragment's own path is machine-local; this manifest, and this line in the
implementer's report, are the reachable pointers).

This pass **only added tests** (plus this manifest). No existing test
file was edited, deleted, or disabled. No implementation code was
written. Nine new test files were added, all under `tests/unit/`, no
change to `tests/integration/` or any other file.

## Baseline taken

Full baseline, taken with the nine new files already in the tree (their
own scenarios establish absence, which is the expected first-run state
for this pass — see "Expected first-run state" in each file):

```
uv run pytest tests/unit tests/agents -q
→ 38 failed, 1691 passed  (all 38 failures are the new files; nothing
  pre-existing failed)

uv run pytest tests/integration -q
→ 3 passed, 124 skipped   (no DATABASE_URL in this environment; the
  integration tier skips exactly as its own conftest documents)
```

`uv run pytest --collect-only` over the nine new files collects 40 tests
cleanly (no syntax/import errors at collection time).

## New test files (this pass)

1. `tests/unit/launch/domain/test_step_confirmer.py`
2. `tests/unit/launch/domain/test_confirmer_assignee_coherence.py`
3. `tests/unit/launch/test_playbook_reference_set_confirmer.py`
4. `tests/unit/launch/application/test_step_confirmer_preconditions.py`
5. `tests/unit/launch/application/test_playbook_authoring_confirmer_field.py`
6. `tests/unit/launch/application/test_report_activation_blockers_handler_only.py`
7. `tests/unit/launch/infrastructure/driving/test_automation_routing_confirmer_field.py`
8. `tests/unit/launch/application/test_confirmer_decision_authority.py`
9. `tests/unit/launch/infrastructure/driving/test_confirmer_mis_wiring_reply_wording.py`

Each carries its own derivation docstring naming the exact scenario(s) it
covers and why it sits at its level. This manifest indexes and
cross-references them; it does not repeat their reasoning.

Runner-selectable identifiers for what the implementation step must make
pass (`uv run pytest <path>::<name>`), grouped by file:

**`test_step_confirmer.py`**
- `test_a_step_definition_is_read_back_with_every_declared_attribute`
- `test_an_automated_step_declares_whether_its_result_is_accepted`
- `test_the_playbook_records_no_automation_detail_beyond_the_kind`
- `test_kind_and_confirmation_are_independent`
- `test_a_human_steps_confirmer_is_accepted_not_rejected`
- `test_an_automated_steps_assignees_no_longer_imply_who_confirms`

**`test_confirmer_assignee_coherence.py`**
- `test_a_sole_assignee_who_is_also_the_confirmer_fails_to_load`
- `test_the_rule_holds_regardless_of_kind`
- `test_two_or_more_assignees_including_the_confirmer_load_fine`
- `test_no_assignees_at_all_loads_fine`

**`test_playbook_reference_set_confirmer.py`**
- `test_no_seeded_step_names_a_confirmer`

**`test_step_confirmer_preconditions.py`**
- `test_an_unknown_confirmer_is_rejected`
- `test_an_active_automated_steps_confirmer_must_be_active`
- `test_a_deactivated_confirmer_may_still_be_named_on_a_step_not_yet_active`
- `test_a_sole_assignee_cannot_also_be_the_confirmer_write`
- `test_a_confirmer_among_several_assignees_is_not_rejected`
- `test_correcting_a_person_does_not_touch_the_steps_that_confirm_through_them`
- `test_a_roster_change_does_not_break_an_accepted_steps_confirmer`

**`test_playbook_authoring_confirmer_field.py`**
- `test_a_created_step_carries_the_confirmer_field_and_no_brief`
- `test_an_automated_step_is_created_naming_a_confirmer`
- `test_creating_a_draft_requires_neither_confirmer_nor_handler`
- `test_an_automated_step_activates_on_a_handler_alone_no_brief_owed`

**`test_report_activation_blockers_handler_only.py`**
- `test_a_draft_missing_only_a_handler_is_reported_by_the_handler_alone`
- `test_a_draft_naming_neither_handler_nor_confirmer_reports_only_the_handler`

**`test_automation_routing_confirmer_field.py`**
- `test_a_step_naming_no_confirmer_is_recorded_directly`
- `test_a_step_naming_a_confirmer_holds_a_terminal_result`
- `test_a_non_terminal_outcome_is_recorded_whatever_confirmer_is_named`
- `test_an_outcome_needing_no_confirmer_is_not_retained`
- `test_a_non_terminal_outcome_is_not_retained_naming_a_confirmer`

**`test_confirmer_decision_authority.py`**
- `test_the_named_confirmer_can_decide[accepting]` / `[rejecting]`
- `test_an_unknown_identity_cannot_decide[accepting]` / `[rejecting]`
- `test_someone_other_than_the_confirmer_cannot_decide[accepting]` / `[rejecting]`
- `test_a_deactivated_confirmer_cannot_decide[accepting]` / `[rejecting]`
- `test_the_named_confirmer_accepting_becomes_the_steps_outcome`
- `test_the_named_confirmer_rejecting_leaves_the_step_live`

**`test_confirmer_mis_wiring_reply_wording.py`**
- `test_a_mis_wiring_blames_neither_roster_membership_nor_confirmer_standing`
  — **passes vacuously today**: nothing in the current implementation
  mentions "confirmer" at all (the concept doesn't exist yet), so the
  negative assertion about confirmer-standing wording holds trivially.
  It becomes a meaningful regression guard only once `confirmer` exists.
  Recorded here rather than left implicit, per this pass's own
  obligation not to let a pass-before-implementation read as evidence of
  anything.

## Scenario accounting

104 `#### Scenario:` blocks appear across the four delta spec files
(`launch-playbook` 61, `launch-step-automation` 19, `playbook-authoring`
22, `product-dossier` 2 — confirmed by `grep -c` against each file).
Every one is accounted for below, either by a named test (new or
pre-existing) or as uncovered with a reason.

Where a scenario's own WHEN/THEN text is unaffected by this delta (no
mention of `confirmer`, `automation_brief`, or the authority-narrowing
rule) and a pre-existing test already demonstrates it, it is marked
**unaffected, cited** rather than duplicated — writing a fresh test
against unchanged behavior would not discharge this pass's obligation any
more than the existing one already does, and the existing test needs only
the mechanical fixture rename `tasks.md` 7.1 already tracks (not a
behavioral rewrite). Every scenario whose text *does* change, or whose
requirement's authorable/authority shape changes even where a specific
scenario's wording happens not to, has a **new** test.

Given the volume of unaffected scenarios (most of `playbook-authoring`
and roughly half of `launch-playbook`'s coherence-rule list), citations
below are given at the confidence level actually reached: where a
specific pre-existing test function was located and read, it is named;
where a scenario is unaffected but the specific covering test was not
individually re-verified in this pass (the search was bounded by time,
not by the glob), it is marked **presumed, not individually verified**.
This is a deliberate honesty distinction, not a gap glossed over: an
implementer who wants certainty for one of those should re-run the
existing suite over it, which task 7.3 already requires regardless.

### `launch-playbook` (61 scenarios)

**MODIFIED — A step definition declares how it is to be resolved** (2)
- A step definition is read back with every declared attribute → **NEW**
  `test_step_confirmer.py::test_a_step_definition_is_read_back_with_every_declared_attribute`
  (assertions: SPECIFIED)
- Steps can be selected by gate and by scope → unaffected, cited:
  `tests/unit/launch/domain/test_launch_playbook.py::test_steps_can_be_selected_by_gate_and_by_scope`

**MODIFIED — A step names who does the work and whether a person accepts it** (4)
- An automated step declares whether its result is accepted → **NEW**
  `test_step_confirmer.py::test_an_automated_step_declares_whether_its_result_is_accepted`
  (SPECIFIED)
- The playbook records no automation detail beyond the kind → **NEW**
  `test_step_confirmer.py::test_the_playbook_records_no_automation_detail_beyond_the_kind`
  (`_NO_AUTOMATION_DETAIL` probe: DERIVED; the kind/confirmer assertions: SPECIFIED)
- Kind and confirmation are independent → **NEW**
  `test_step_confirmer.py::test_kind_and_confirmation_are_independent` (SPECIFIED)
- A human step's confirmer is accepted, not rejected → **NEW**
  `test_step_confirmer.py::test_a_human_steps_confirmer_is_accepted_not_rejected`
  (SPECIFIED)

**MODIFIED — A step names the people responsible for it** (4)
- An active human step needs someone responsible → unaffected, cited:
  `test_step_assignee_preconditions.py::test_an_active_human_step_needs_someone_responsible`
- An unknown person is rejected → cited:
  `test_step_assignee_preconditions.py::test_an_unknown_person_is_rejected`
- A deactivated person does not satisfy the requirement → cited:
  `test_step_assignee_preconditions.py::test_a_deactivated_person_does_not_satisfy_the_requirement`
- Correcting a person does not touch the steps → cited:
  `test_step_assignee_preconditions.py::test_correcting_a_person_does_not_touch_the_steps`
- *(bonus, not a numbered scenario)* the requirement's own prose change
  ("naming assignees no longer says who is asked to confirm a result") →
  **NEW** `test_step_confirmer.py::test_an_automated_steps_assignees_no_longer_imply_who_confirms`
  (DERIVED from the requirement statement, no scenario states it)

**MODIFIED — The authored set exercises the full step vocabulary** (8)
- Anchor kinds are all present → unaffected, cited:
  `test_playbook_reference_set.py::test_every_anchor_kind_and_discipline_is_represented`
- Every discipline appears → cited, same test
- Execution modes and the compliance hazard are represented → **NEW**
  (confirmer half) `test_playbook_reference_set_confirmer.py::test_no_seeded_step_names_a_confirmer`
  (SPECIFIED); (human/hazard half) cited:
  `test_playbook_reference_set.py::test_every_step_is_an_unowned_human_draft`
  and `::test_both_hazards_are_present_and_prohibited_tactics_never_block`
  — **note**: the first of those two also asserts
  `step["needs_confirmation"] is False`, which is itself an obsolete
  assertion (see Obsolete tests below); its `kind == "human"` /
  `assignees == []` assertions remain accurate.
- Prohibited tactics are present and never block → cited:
  `test_playbook_reference_set.py::test_both_hazards_are_present_and_prohibited_tactics_never_block`
- Every seeded step is a draft nobody owns → cited (same caveat as
  above): `test_playbook_reference_set.py::test_every_step_is_an_unowned_human_draft`
- A seeded playbook is not ready → **uncovered by this pass** — not
  found by this search within the time available; unaffected in wording
  by this delta, so presumed covered somewhere in
  `tests/integration/launch/test_seeded_step_fields.py` or
  `tests/unit/launch/domain/test_playbook_readiness.py`, but no specific
  function was verified. Recorded as "not found by this search," not as
  "no such test exists."
- A registered runtime does not activate a seeded step → cited:
  `tests/integration/launch/test_registered_handlers_activate_nothing.py::test_a_registered_runtime_does_not_activate_a_seeded_step`
- Outstanding rule-policy decisions stay visible → cited:
  `tests/integration/launch/test_seeded_step_fields.py::test_outstanding_readiness_decisions_stay_visible`

**MODIFIED — What blocks a step from being activated is reported** (2)
- Steps that cannot be activated are listed with their reason → **NEW**
  `test_report_activation_blockers_handler_only.py::test_a_draft_missing_only_a_handler_is_reported_by_the_handler_alone`
  (SPECIFIED restatement; the "no brief wording survives" half is DERIVED)
- A set of ready steps reports nothing → unaffected, cited:
  `test_report_activation_blockers.py::test_a_set_of_ready_steps_reports_nothing`

**ADDED — An incoherent playbook is rejected against its steps' status and shape** (14)

This requirement is, by content, a rename of the REMOVED requirement
below plus one new bullet (see `design.md`'s own account of why a
MODIFIED block couldn't express dropping the old brief-scenario). 13 of
its 14 scenarios are byte-identical in wording to scenarios the
predecessor requirement already carried and the existing suite already
tests; only the sole-assignee-confirmer bullet is genuinely new. Per this
pass's own judgment call (recorded here rather than silently applied):
the 13 unaffected scenarios are cited to their existing coverage rather
than duplicated, and the one new bullet gets a fresh test.

- Gate sequence deviates from the specification → cited:
  `test_launch_playbook.py::test_gate_sequence_that_omits_a_gate_is_rejected`
  (+ its sibling tests for the other deviation shapes)
- A gate's opening mode disagrees with the specification → cited:
  `test_launch_playbook.py::test_gate_opening_mode_disagreeing_with_the_specification_is_rejected`
- Duplicate step identifier → cited:
  `test_launch_playbook.py::test_duplicate_step_identifier_is_rejected`
- Step references an unknown gate → cited:
  `test_launch_playbook.py::test_step_referencing_an_unknown_gate_is_rejected`
- A step with no name is rejected by identifier → cited:
  `test_playbook_coherence_by_status.py::test_a_step_with_no_name_is_rejected_by_identifier`
- A name spanning several lines is rejected → cited:
  `test_playbook_coherence_by_status.py::test_a_name_spanning_several_lines_is_rejected`
- A description spanning several lines is accepted → cited:
  `test_playbook_coherence_by_status.py::test_a_description_spanning_several_lines_is_accepted`
- **A sole assignee who is also the confirmer fails to load → NEW**
  `test_confirmer_assignee_coherence.py::test_a_sole_assignee_who_is_also_the_confirmer_fails_to_load`
  (SPECIFIED), plus three DERIVED-boundary tests in the same file
  (`test_the_rule_holds_regardless_of_kind`,
  `test_two_or_more_assignees_including_the_confirmer_load_fine`,
  `test_no_assignees_at_all_loads_fine`)
- A prohibited tactic cannot block a gate → cited:
  `test_launch_playbook.py::test_prohibited_tactic_marked_blocking_is_rejected`
- A gate with no active blocking step is rejected → presumed, not
  individually verified (`test_playbook_readiness.py` carries this
  family of tests; the exact function was not pinned down in this pass)
- A malformed metric condition is rejected → **not found by this
  search** within the time available (candidate location:
  `test_gate_conditions.py`, which was read and did not show a
  clearly-named match); recorded as "not found," not "does not exist"
- Multiple violations are reported together → cited:
  `test_playbook_coherence_by_status.py::test_two_violations_of_the_new_rules_are_reported_together`
  — **note**: this test's fixture pairs a human-step-with-handler fault
  with an automated-step-without-*brief* fault; the brief half is
  obsolete (see below), but the scenario itself ("two faults, one
  report") is still demonstrated and would remain true with any other
  two-fault pairing.
- A malformed step is reported alongside a coherence violation → **not
  found by this search**
- A coherent playbook loads → cited:
  `test_playbook_coherence_by_status.py::test_a_coherent_playbook_loads`
  and `test_launch_playbook.py::test_a_coherent_playbook_loads`

**ADDED — A step names who confirms an automated result** (6) — all NEW,
genuinely new field/rule:
- An automated step names its confirmer → **NEW**
  `test_step_confirmer.py::test_an_automated_step_declares_whether_its_result_is_accepted`
  (shared with the "A step names who does the work..." scenario above —
  the read-back assertion is the same fact)
- An unknown confirmer is rejected → **NEW**
  `test_step_confirmer_preconditions.py::test_an_unknown_confirmer_is_rejected`
- A deactivated confirmer does not satisfy the requirement → **NEW**
  `test_step_confirmer_preconditions.py::test_an_active_automated_steps_confirmer_must_be_active`
- A sole assignee cannot also be the confirmer → **NEW**
  `test_step_confirmer_preconditions.py::test_a_sole_assignee_cannot_also_be_the_confirmer_write`
- A confirmer among several assignees is not rejected → **NEW**
  `test_step_confirmer_preconditions.py::test_a_confirmer_among_several_assignees_is_not_rejected`
- Correcting a person does not touch the steps that confirm through them
  → **NEW**
  `test_step_confirmer_preconditions.py::test_correcting_a_person_does_not_touch_the_steps_that_confirm_through_them`

**ADDED — A step carries the handler its automation needs** (7) — this
requirement narrows an existing one (drops the brief half); its
handler-only content is unaffected in substance:
- A draft automated step needs no handler yet → **NEW** (handler-only
  restatement) `test_playbook_authoring_confirmer_field.py::test_creating_a_draft_requires_neither_confirmer_nor_handler`;
  the domain-level predecessor
  (`test_step_automation_brief_and_handler.py::test_a_draft_automated_step_needs_neither`)
  is obsolete for asserting `automation_brief is None` as part of its
  claim (see below)
- A handler the code does not register cannot be activated → unaffected,
  cited: `test_step_activation.py::test_a_handler_the_code_does_not_register_cannot_be_activated`
- The reporting process holds the deployment's own registrations →
  **not found by this search** (candidate:
  `tests/unit/test_startup_handler_report_holds_the_registry.py`, which
  was read and carries only three named tests, none matching this
  scenario by name — the guarantee may be asserted as setup inside one
  of them rather than as its own test)
- A registered handler draws no fault at startup → cited:
  `tests/unit/test_startup_handler_report_holds_the_registry.py::test_a_registered_handler_draws_no_fault_at_startup`
- An unregistered handler is named at startup → cited:
  `tests/unit/test_startup_handler_report_holds_the_registry.py::test_an_unregistered_handler_is_named_at_startup`
- The faults the report names do not stop the deployment → cited:
  `tests/unit/test_startup_handler_report_holds_the_registry.py::test_the_faults_the_report_names_do_not_stop_the_deployment`
- A human step carries no handler → cited, with a caveat:
  `test_step_activation.py::test_a_human_step_written_with_automation_fields_is_refused`
  — its name suggests it may exercise both the (now-removed) brief and
  the handler together; if so its brief half is obsolete and its handler
  half remains accurate. Flagged for confirmation rather than split
  apart, since this pass did not read that test's body.

### `launch-step-automation` (19 scenarios)

**MODIFIED — A non-terminal outcome is recorded directly and never held for a decision** (2)
- A non-terminal outcome on a confirmable step is recorded, not held →
  **NEW** `test_automation_routing_confirmer_field.py::test_a_non_terminal_outcome_is_recorded_whatever_confirmer_is_named`
  (SPECIFIED)
- A step reporting no progress is reconsidered on the next pass →
  unaffected, cited: `test_automation_pass.py::test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass`

**MODIFIED — A result needing no confirmation is recorded at once** (1)
- An unconfirmed result is recorded directly → **NEW**
  `test_automation_routing_confirmer_field.py::test_a_step_naming_no_confirmer_is_recorded_directly`
  (SPECIFIED)

**MODIFIED — A result needing confirmation is held until a person decides** (3)
- A confirmable terminal result is held rather than recorded → **NEW**
  `test_automation_routing_confirmer_field.py::test_a_step_naming_a_confirmer_holds_a_terminal_result`
  (SPECIFIED)
- A pending result suppresses re-invocation → unaffected, cited:
  `test_automation_pass.py::test_a_pending_result_suppresses_re_invocation`
- Two overlapping passes cannot both produce a pending result →
  unaffected, presumed covered in `test_automation_pass.py` (not
  individually re-verified by name in this pass)

**MODIFIED — The retained record covers results held for a decision and nothing else** (2)
- An outcome needing no confirmation is not retained → **NEW**
  `test_automation_routing_confirmer_field.py::test_an_outcome_needing_no_confirmer_is_not_retained`
  (SPECIFIED)
- A non-terminal outcome is not retained → **NEW**
  `test_automation_routing_confirmer_field.py::test_a_non_terminal_outcome_is_not_retained_naming_a_confirmer`
  (SPECIFIED)

**MODIFIED — Accepting records the proposed outcome and names the accepter** (2)
- An accepted result becomes the step's outcome → **NEW** (restated for
  named-confirmer authority)
  `test_confirmer_decision_authority.py::test_the_named_confirmer_accepting_becomes_the_steps_outcome`
  (SPECIFIED)
- A failed recording leaves the result decidable → unaffected, cited:
  `test_automated_result_decisions.py::test_a_failed_recording_leaves_the_result_decidable`
  (this mechanic — recording/settlement atomicity — does not turn on who
  may decide, only on what happens once someone validly does)

**MODIFIED — Rejecting does not terminate the step** (2)
- A rejected result leaves the step live → **NEW**
  `test_confirmer_decision_authority.py::test_the_named_confirmer_rejecting_leaves_the_step_live`
  (SPECIFIED)
- Rejection is never a refusal → unaffected, cited:
  `test_automated_result_decisions.py::test_rejection_is_never_a_refusal`

**ADDED — Only the step's named confirmer may decide a pending result** (7)
— every scenario here is written fresh, because this is the requirement
the proposal names **BREAKING**, not a rename technicality:
- The named confirmer can decide → **NEW**
  `test_confirmer_decision_authority.py::test_the_named_confirmer_can_decide`
- An unknown identity cannot decide → **NEW**
  `test_confirmer_decision_authority.py::test_an_unknown_identity_cannot_decide`
- Someone other than the confirmer cannot decide → **NEW**, the
  requirement's most discriminating scenario:
  `test_confirmer_decision_authority.py::test_someone_other_than_the_confirmer_cannot_decide`
- A deactivated confirmer cannot decide → **NEW**
  `test_confirmer_decision_authority.py::test_a_deactivated_confirmer_cannot_decide`
- A collaborator that cannot answer who the roster carries is refused by
  name → unaffected wiring mechanics (per `tasks.md` 4.3: "only the
  identity-matching rule changes, not how a broken roster collaborator
  is reported"), cited:
  `test_automated_decision_roster_shape.py::test_a_collaborator_that_cannot_answer_is_refused_by_name`
  (name presumed from the module docstring's own description; not
  individually re-verified against the file body)
- An absent collaborator is refused the same way, not silently →
  unaffected wiring mechanics, cited:
  `test_automated_decision_wiring.py::test_an_absent_collaborator_raises_the_named_wiring_error`
  and `::test_a_wiring_fault_answers_the_decider_rather_than_falling_silent`
- A mis-wiring is never reported as an unknown identity → unaffected
  half cited: `test_automated_decision_wiring.py::test_a_wiring_fault_blames_no_decider_and_is_reported_to_operators`;
  the widened half (must also not blame "standing as confirmer") is
  **NEW**: `test_confirmer_mis_wiring_reply_wording.py::test_a_mis_wiring_blames_neither_roster_membership_nor_confirmer_standing`
  (passes vacuously today — see the file list above)

**REMOVED — Only a known, active person may decide a pending result**
— carries **no scenario blocks in the delta file itself** (only
Reason/Migration text; confirmed by reading the delta spec). Nothing to
enumerate from this block under the letter of "every `#### Scenario:`
block in the delta specs." The tests that bore on the requirement's own
now-superseded authority claim are listed in Obsolete tests below.

### `playbook-authoring` (22 scenarios)

**MODIFIED — A step can be created** (4)
- A created step joins the served set → **NEW** (demonstrates the new
  authorable shape end to end)
  `test_playbook_authoring_confirmer_field.py::test_a_created_step_carries_the_confirmer_field_and_no_brief`;
  also `::test_an_automated_step_is_created_naming_a_confirmer`
  (SPECIFIED); unaffected predecessor cited:
  `test_playbook_authoring_new_field_set.py::test_a_created_step_carries_the_whole_new_authorable_shape`
- Created identifiers never collide with the seeded namespace →
  unaffected, cited: `test_playbook_authoring_new_field_set.py::test_created_identifiers_never_collide_retired_included`
- A step is created declaring when it starts → unaffected, presumed
  covered (not individually re-verified)
- A step is created declaring neither → unaffected, presumed covered
  (not individually re-verified); also incidentally exercised by
  `test_playbook_authoring_confirmer_field.py::test_creating_a_draft_requires_neither_confirmer_nor_handler`,
  though that test's primary subject is the handler/confirmer optionality,
  not the start-gate/after_steps independence this scenario is actually
  about

**MODIFIED — Activation is a validated transition** (5)
- An activation that satisfies its kind's rules lands → **NEW**
  (restated without the brief clause)
  `test_playbook_authoring_confirmer_field.py::test_an_automated_step_activates_on_a_handler_alone_no_brief_owed`
  (SPECIFIED); unaffected predecessor cited:
  `test_step_activation.py::test_an_activation_that_satisfies_its_kinds_rules_lands`
  (obsolete — see below, it still supplies a brief)
- A refused activation explains itself and persists nothing →
  unaffected, cited: `test_step_activation.py::test_a_refused_activation_explains_itself_and_persists_nothing`
- Registering a handler does not activate anything → unaffected, cited:
  `test_step_activation.py::test_registering_a_handler_does_not_activate_anything`
- Un-activating a gate's last blocking step is refused → unaffected,
  cited: `test_step_activation.py::test_un_activating_a_gates_last_blocking_step_is_refused`
- Un-activating within a set that is not ready is permitted →
  unaffected, presumed covered (not individually located by name in
  `test_step_activation.py`'s eight functions; may live in
  `test_step_retirement_and_slots.py` instead)

**MODIFIED — Every write is validated as the playbook it would produce** (13)
- A rejected write reports all faults and persists nothing → unaffected,
  cited: `test_step_assignee_preconditions.py::test_a_rejected_write_reports_all_faults_and_persists_nothing`
- Retiring a gate's last blocking step is rejected → unaffected,
  presumed covered in `test_step_retirement_and_slots.py`
- A write against a set that is not ready may leave it unready →
  unaffected, presumed covered
- An untouched unowned step does not block an unrelated write →
  unaffected, cited: `test_step_assignee_preconditions.py::test_an_untouched_unowned_step_does_not_block_an_unrelated_write`
- Editing an unowned step requires giving it an owner → unaffected,
  cited: `test_step_assignee_preconditions.py::test_editing_an_unowned_step_requires_giving_it_an_owner`
- A roster change does not break an accepted set → unaffected, cited:
  `test_step_assignee_preconditions.py::test_a_roster_change_does_not_break_an_accepted_set`
- **A roster change does not break an accepted step's confirmer → NEW**
  `test_step_confirmer_preconditions.py::test_a_roster_change_does_not_break_an_accepted_steps_confirmer`
  (SPECIFIED, load-time half only — see that test's own docstring for
  the pending-result half's placement in `launch-step-automation`'s
  files)
- A collaborator of the wrong shape is refused by name → unaffected,
  cited: `test_authoring_roster_collaborator_shape.py` (module presumed
  from its file name; not individually re-verified)
- A mis-wiring is not reported as a rejection of the submission →
  unaffected, cited: same file, presumed
- A mis-shaped collaborator never passes for an absent one →
  unaffected, cited: same file, presumed
- No roster is still a permitted case → unaffected, cited: same file,
  presumed
- What a write cannot persist, a load cannot see → unaffected, cited:
  `test_step_assignee_preconditions.py::test_what_a_write_cannot_persist_a_load_cannot_see`
- A dependency precondition is evaluated with no roster supplied →
  unaffected, presumed covered in `test_step_dependency_preconditions.py`

**MODIFIED — Authoring never touches the framework**, **A gate's steps
can be reordered**, **Every live step holds a slot in its gate's order**,
**A dependency may only be authored on an active step**, **A
`prohibited-tactic` step may not be depended upon** — not part of this
delta's changed text at all (none of these five requirements appears in
`add-step-confirmer`'s `playbook-authoring` delta); not applicable to
this accounting, and their scenarios are not among the 22 counted above.

### `product-dossier` (2 scenarios)

**MODIFIED — The produced record states what it does not cover** (2) —
both scenarios are byte-identical in wording to the requirement's
previous version (only the surrounding prose changes "confirmation flag"
to "naming a confirmer" — a terminology update the proposal itself calls
"no behavioral change"). Both already covered:
- The record is labelled for what it holds → cited:
  `test_product_dossier_page.py::test_the_record_is_labelled_for_what_it_holds`
- The qualification is present on an empty record too → cited:
  `test_product_dossier_page.py::test_the_qualification_is_present_on_an_empty_record_too`

No new test written for this capability; none needed.

## Assertion classification (per `testing`'s rule)

Applied throughout each new file's own comments (`# SPECIFIED`, `#
DERIVED`, `# DELIBERATELY UNTESTED`), following this suite's established
convention. Summarized:

- **SPECIFIED** — the great majority: field presence/absence, rejection
  vs. acceptance, who may decide, what is recorded, what is retained —
  all traced directly to a delta requirement's own SHALL/scenario text.
- **DERIVED** — probe lists for "no automation detail beyond the kind"
  (`_NO_AUTOMATION_DETAIL` in `test_step_confirmer.py`, extending the
  pre-existing probe with `needs_confirmation`/`confirmation`/
  `confirmation_flag`, which must not survive as a boolean flag beside
  `confirmer`); the boundary tests in `test_confirmer_assignee_coherence.py`
  (two-or-more-assignees, no-assignees) restating the requirement's own
  "unaffected by this rule" clause as positive-path tests; the wiring
  markers reused verbatim from the sibling wiring test files.
- **DELIBERATELY UNTESTED** — none newly introduced beyond what the
  reused patterns already carry (e.g. roster-identifier format, ordering
  of `assignees`) — those absences are already recorded in the files this
  pass's fixtures are modeled on and are not repeated here.

## Obsolete tests (candidates for human confirmation)

**Applicable** — this change carries both `MODIFIED` and `REMOVED`
deltas. Search was bounded to `tests/**/test_*.py`, using `grep -rl
"needs_confirmation\|automation_brief" --include="test_*.py" tests`
(over 100 files matched) narrowed to files/functions whose *assertions*
— not merely a fixture-helper default — turn on the removed field's
meaning or the superseded decision-authority claim. The wide set of
files matched only because their `_step()`/`_automated()` helper passes
`needs_confirmation=False`/`automation_brief=None` as an inert default is
**not** listed here: that is the mechanical rename `tasks.md` 7.1 already
tracks as separate, non-behavioral work, and listing it here would
misrepresent incidental fixture vocabulary as a behavioral finding.

Every entry below is a **candidate for human confirmation**, not a
conclusion. None was edited or deleted.

1. **`tests/unit/launch/domain/test_step_kind_and_confirmation.py`**
   (whole file, 4 tests) — superseding delta: `launch-playbook` MODIFIED
   *A step names who does the work and whether a person accepts it*.
   Evidence: every test asserts `.needs_confirmation is True/False`
   directly (lines 164, 218, 246–247) — the field this change replaces
   with `confirmer`.

2. **`tests/unit/launch/domain/test_step_automation_brief_and_handler.py`**
   (whole file) — superseding delta: `launch-playbook` REMOVED *A step
   carries the brief and the handler its automation needs* / ADDED *A
   step carries the handler its automation needs*. Evidence: asserts
   `.automation_brief` directly (lines 197, 244, 361) and specifically
   tests the removed "beyond draft without a brief is rejected" load
   rule (`test_an_automated_step_beyond_draft_without_a_brief_is_rejected`,
   `test_a_retired_automated_step_owes_no_brief`) and the removed
   "human step carrying a brief" half of the human-carries-neither rule
   (`test_a_human_step_carrying_an_automation_brief_is_rejected`). Its
   handler-only tests
   (`test_an_active_automated_step_without_a_handler_is_rejected`,
   `test_a_load_never_checks_whether_the_handler_is_registered`,
   `test_a_human_step_carrying_a_handler_is_rejected`) remain accurate
   descriptions of retained behavior.

3. **`tests/unit/launch/domain/test_playbook_coherence_by_status.py::test_two_violations_of_the_new_rules_are_reported_together`**
   — superseding delta: `launch-playbook` REMOVED/ADDED coherence-rule
   pair. Evidence: constructs `automated_without_brief =
   _step(..., automation_brief=None)` as one of its two paired faults
   (lines ~407–413); the brief-absence fault it relies on no longer
   exists. The scenario itself ("two faults reported together") is
   still true and would need only a different second fault.

4. **`tests/unit/launch/application/test_step_activation.py::test_leaving_draft_requires_the_brief`**
   — superseding delta: `launch-playbook` REMOVED *A step carries the
   brief and the handler its automation needs* (the "required to leave
   `draft`" clause is dropped outright, with no replacement). Evidence:
   function name and body (lines 536–566) assert exactly that rejection.

5. **`tests/unit/launch/application/test_step_activation.py::test_an_activation_that_satisfies_its_kinds_rules_lands`**
   — superseding delta: `playbook-authoring` MODIFIED *Activation is a
   validated transition*. Evidence: per its docstring reference ("an
   `automated` step carrying a **brief** and a registered handler"), it
   supplies `automation_brief=...` as part of what makes the activation
   land; the brief is no longer a precondition of activation at all.

6. **`tests/unit/launch/application/test_step_activation.py::test_a_human_step_written_with_automation_fields_is_refused`**
   (flagged for confirmation, not verified in full — see the
   `launch-playbook` "A step carries the handler..." accounting above)
   — superseding delta: same. Evidence: name ("automation_fields",
   plural) suggests it exercises the automation-brief half of the
   human-carries-neither rule alongside the handler half; only the
   brief half would be superseded.

7. **`tests/unit/launch/application/test_report_activation_blockers.py::test_steps_that_cannot_be_activated_are_listed_with_their_reason`**
   — superseding delta: `launch-playbook` MODIFIED *What blocks a step
   from being activated is reported*. Evidence: constructs a
   `draft_without_brief` step and asserts `"brief" in
   _row_text(row).lower()` (lines 209–239) — the report no longer names
   a missing brief because the field is gone.

8. **`tests/integration/launch/test_seeded_step_fields.py::test_no_seeded_human_step_carries_an_automation_brief`**
   and **`::test_every_seeded_automated_step_carries_its_brief`** —
   superseding delta: `launch-playbook` REMOVED requirement (field
   dropped entirely). Evidence: function names assert the field's
   presence/absence directly.

9. **`tests/integration/launch/test_seeded_step_fields.py::test_kinds_confirmation_and_the_compliance_hazard_are_represented`**
   — superseding delta: `launch-playbook` MODIFIED *The authored set
   exercises the full step vocabulary*. Evidence: function name and the
   requirement's own restated scenario ("grouped by kind and
   **confirmer**", not "kind and confirmation").

10. **`tests/unit/launch/application/test_automated_result_decisions.py`**
    (its authority-adjacent tests:
    `test_an_unknown_identity_cannot_decide`,
    `test_a_deactivated_person_cannot_decide`,
    `test_an_accepted_result_becomes_the_steps_outcome`,
    `test_a_rejected_result_leaves_the_step_live`) — superseding delta:
    `launch-step-automation` REMOVED *Only a known, active person may
    decide a pending result* / ADDED *Only the step's named confirmer
    may decide a pending result*. Evidence: `_step()`'s fixture (lines
    191–211) carries `needs_confirmation=True` and no confirmer concept
    at all; Alice decides successfully by virtue of being "known,
    active" alone, which is exactly the latitude the ADDED requirement
    removes. The file's other tests (settlement mechanics, once-only
    decision, voided-step refusal, wiring-fault handling) are unaffected
    and not part of this entry.

11. **`tests/unit/launch/infrastructure/driving/test_playbook_admin_fault_attribution.py`**
    (specific parametrized cases, not the whole file) — superseding
    delta: `launch-playbook`/`playbook-authoring` field-set change (this
    is a UI-adjacent test with no delta spec of its own, so this entry
    is offered for confirmation rather than asserted as directly
    spec-superseded). Evidence: fault-attribution pairing tuples keyed
    on the removed field name, e.g. `("kind", "status",
    "automation_brief")` (line 1779), `("kind", "automation_brief")`
    (line 1793), and brief-specific form-value assertions (lines
    1170–1174, 1321–1323, 1579).

12. **`tests/unit/launch/infrastructure/driving/test_playbook_admin_step_fields.py`**
    (one construction site, line 669: `automation_brief=typed_brief`) —
    same caveat as #11 (UI-adjacent, no delta spec of its own). Evidence:
    the line itself; not read in full, so offered as a narrower
    candidate than #11.

**Not exhaustively searched**: the remaining ~90 files matched by the
`needs_confirmation|automation_brief` grep were not individually opened
in this pass, on the judgment that their matches are fixture-default
uses (task 7.1's territory) rather than assertions bearing on the
superseded behavior itself. This is a bounded-search limitation, not a
claim that no further obsolete test exists among them — an implementer
who wants certainty should re-grep after the mechanical rename and watch
for any remaining behavioral assertion the rename alone doesn't resolve.

## Unresolved project questions

1. **No project-specific test-runner convention beyond what AGENTS.md
   states.** AGENTS.md names `uv run pytest` and the three-tier
   directory split; it says nothing about a project-specific stack skill
   for Python/pytest beyond the general `python`/`testing` skills already
   loaded. Assumption taken: the `python` skill's floor (mutable
   defaults, closures, etc.) and this suite's own established
   conventions (the `_step()`/`_FakeRoster`/`_decide()` probing patterns
   already used throughout `tests/unit/launch/`) are the operative
   standard. No test depends on a different assumption being resolved.

2. **Exact pre-existing test names for several unaffected scenarios**
   (see "presumed, not individually verified" entries above, and the
   "not found by this search" entries for *A gate with no active
   blocking step is rejected*, *A malformed metric condition is
   rejected*, *A malformed step is reported alongside a coherence
   violation*, *The reporting process holds the deployment's own
   registrations*, *A step is created declaring when it starts / neither*,
   several `playbook-authoring` write-validation scenarios). Assumption
   taken: these are unaffected in substance by this delta (their WHEN/THEN
   text names neither `confirmer` nor `automation_brief` nor the
   authority-narrowing rule) and are already covered somewhere in the
   pre-existing suite; no new test depends on resolving exactly where.

3. **Whether `test_step_activation.py::test_a_human_step_written_with_automation_fields_is_refused`
   exercises the removed brief field, the retained handler field, or
   both** (obsolete-list entry #6). Not read in full in this pass.
   Recorded rather than guessed.

## What the implementation step must make pass

Every test named under "New test files" above, run via:

```
uv run pytest \
  tests/unit/launch/domain/test_step_confirmer.py \
  tests/unit/launch/domain/test_confirmer_assignee_coherence.py \
  tests/unit/launch/test_playbook_reference_set_confirmer.py \
  tests/unit/launch/application/test_step_confirmer_preconditions.py \
  tests/unit/launch/application/test_playbook_authoring_confirmer_field.py \
  tests/unit/launch/application/test_report_activation_blockers_handler_only.py \
  tests/unit/launch/infrastructure/driving/test_automation_routing_confirmer_field.py \
  tests/unit/launch/application/test_confirmer_decision_authority.py \
  tests/unit/launch/infrastructure/driving/test_confirmer_mis_wiring_reply_wording.py
```

Plus, separately (not this pass's job, but a precondition of "implemented"
per `tasks.md` 7): the mechanical `needs_confirmation`/`automation_brief`
→ `confirmer`/(dropped) fixture rename across the wide existing-test
surface `tasks.md` 7.1 names, and resolution of the obsolete-list entries
above (by editing or retiring those specific tests, which this pass
deliberately did not do).
