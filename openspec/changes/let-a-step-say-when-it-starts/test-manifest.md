# Test manifest — `let-a-step-say-when-it-starts`

Written by `openspec-test-writer` on 2026-08-29, from the change's delta
specs alone, before any implementation. **This file is not an artifact
the OpenSpec schema knows about**: it will not appear among
`openspec instructions apply`'s context files and has to be read on
purpose. `rules/` directs that it be read before implementing; this
sentence is the second, redundant pointer.

**This pass is additive only.** It adds test files and this manifest. No
existing test was edited, deleted or disabled, and no implementation was
written. Every test below fails today, and making them pass is the
implementation step's job.

---

## Baseline

Taken at the worktree root (`/home/shatynska/projects/commerce-ops`,
branch `contain-the-gap-record-fault`) on 2026-08-29, **before** any
test was written:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | **1556 passed, 0 failed** in 42.80s |
| `uv run pytest tests/integration` | **118 passed, 1 skipped** in 40.42s |

The one skip is pre-existing:
`tests/integration/launch/test_registered_handlers_activate_nothing.py:328`
("no seeded automated step names a handler this deployment registers").

Full, not scoped — the suite runs in well under two minutes and a
configured database is present, so nothing was bought by narrowing it.

**After this pass** (same commands, same machine):

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 84 failed, **1559 passed**, 7 errors |
| `uv run pytest tests/integration` | 7 failed, **119 passed**, 1 skipped |

Every failure and every error is in a file this pass added. **No
pre-existing test changed state.** The passed count rises by 3 and 1
because four of the new tests are regression guards or vacuous passes;
each is named under *First-run passes* below.

`uv run ruff check`, `uv run ruff format --check` and `uv run mypy .`
were run over the new files. Ruff is clean. Mypy reports 24 errors, all
of one kind — `"StepDefinition" has no attribute "starts_at_gate"` /
`"after_steps"` — which is the absent-target state and resolves the
moment `tasks.md` 1.1 lands. The implementation step should expect the
`pre-commit` mypy hook to be red until then.

---

## Scenario accounting

The delta specs carry **166 `#### Scenario:` blocks** across seven
capabilities. Every one is accounted for below, exactly once.

| Capability | Scenarios | New behaviour | Reproduced unchanged |
| --- | ---: | ---: | ---: |
| `launch-playbook` | 52 | 36 | 16 |
| `launch-instance` | 19 | 10 | 9 |
| `launch-clickup-sync` | 35 | 8 | 27 |
| `launch-step-automation` | 11 | 6 | 5 |
| `playbook-authoring` | 24 | 11 | 13 |
| `playbook-admin` | 18 | 5 | 13 |
| `launch-admin` | 7 | 7 | 0 |
| **Total** | **166** | **83** | **83** |

"Reproduced unchanged" means the scenario appears verbatim (or with a
wording change that adds *released* to a WHEN clause without changing
what is asserted) in the served spec under `openspec/specs/`. Those are
covered by existing tests, named per capability below. Their fixtures
declare no `starts_at_gate` and no `after_steps`, so under the new rules
every step they build is released from a launch's first gate — which is
why they keep passing and why they remain the coverage for those
scenarios.

---

## Files this pass added

| Path | Tier | Covers |
| --- | --- | --- |
| `tests/unit/launch/domain/test_step_start_release.py` | unit | the release predicate, vacuous satisfaction, the field read-back |
| `tests/unit/launch/domain/test_step_start_coherence.py` | unit | the load-time start-gate and dependency-graph rules |
| `tests/unit/launch/domain/test_launch_dates_release.py` | unit | release and the at-risk judgement |
| `tests/unit/launch/application/test_step_dependency_preconditions.py` | unit | the write-time dependency preconditions and the two new create scenarios |
| `tests/unit/launch/application/test_launch_report_release.py` | unit | what the launch report carries about an unstarted step, and overdue |
| `tests/unit/launch/infrastructure/driven/test_clickup_sync_release.py` | unit | the projection gate, and reconciliation staying ungated |
| `tests/unit/launch/infrastructure/driving/test_automation_pass_release.py` | unit | the invocation gate and the narrowed unregistered-handler report |
| `tests/unit/launch/infrastructure/driving/test_launch_admin_start_marks.py` | unit | the detail page's start mark |
| `tests/unit/launch/infrastructure/driving/test_playbook_admin_start_fields.py` | unit | the two new form controls and their fault attribution |
| `tests/unit/launch/test_playbook_reference_set_start_gates.py` | unit | the vendored file and the delivery path |
| `tests/integration/launch/test_step_start_gate_backfill.py` | integration | the backfilled stored set |

Nothing was added under `tests/agents/` — this change adds no agent
behaviour, and no scenario is stated about a graph.

Every test is named so the runner can select it individually, e.g.:

```
uv run pytest "tests/unit/launch/domain/test_step_start_release.py::test_a_step_is_not_released_before_its_start_gate"
uv run pytest "tests/unit/launch/infrastructure/driving/test_playbook_admin_start_fields.py::test_each_start_rule_is_attributed_to_its_control[a start gate naming the final gate]"
```

---

## Coverage, scenario by scenario

Test files are given by basename; the table above resolves each to its
path. `→ existing` names a test that already covers the scenario and
that this pass did not touch.

### `launch-playbook`

**ADDED — A step declares when it may start** (9) →
`test_step_start_release.py`

| Scenario | Test |
| --- | --- |
| A step naming neither field starts immediately | `test_a_step_naming_neither_field_starts_immediately` |
| A step is not released before its start gate | `test_a_step_is_not_released_before_its_start_gate` |
| A step is released at its start gate | `test_a_step_is_released_at_its_start_gate` |
| A step stays released once its gate is passed | `test_a_step_stays_released_once_its_gate_is_passed` |
| A step may start before the gate it belongs to | `test_a_step_may_start_before_the_gate_it_belongs_to` |
| Every named dependency must be resolved | `test_every_named_dependency_must_be_resolved` |
| Both fields must be satisfied | `test_both_fields_must_be_satisfied` |
| Gate opening is not gated on release | `test_gate_opening_is_not_gated_on_release` |
| Release does not consult the date | `test_release_does_not_consult_the_date` |

**ADDED — A dependency nobody is still owed is satisfied vacuously**
(4) → `test_step_start_release.py`

| Scenario | Test |
| --- | --- |
| Retiring a step releases what waited on it | `test_retiring_a_step_releases_what_waited_on_it` |
| A dependency re-classified prohibited-tactic holds nothing back | `test_a_dependency_re_classified_prohibited_tactic_holds_nothing_back` |
| An identifier naming no step holds nothing back | `test_an_identifier_naming_no_step_holds_nothing_back` |
| A mix of active and retired dependencies | `test_a_mix_of_active_and_retired_dependencies_still_holds` |

**ADDED — A step cannot start after the gate it belongs to** (6) →
`test_step_start_coherence.py`

| Scenario | Test |
| --- | --- |
| A start gate of the final gate is rejected | `test_a_start_gate_of_the_final_gate_is_rejected` |
| A final-gate step may not start at its own gate | `test_a_final_gate_step_may_not_start_at_its_own_gate` |
| A final-gate step starting earlier is accepted | `test_a_final_gate_step_starting_earlier_is_accepted` |
| A start gate later than the step's own gate is rejected | `test_a_start_gate_later_than_the_steps_own_gate_is_rejected` |
| A start gate equal to the step's own gate is accepted | `test_a_start_gate_equal_to_the_steps_own_gate_is_accepted` |
| An unknown start gate is rejected | `test_an_unknown_start_gate_is_rejected` |

**ADDED — Step dependencies form an acyclic graph that cannot deadlock a
gate** (8) → `test_step_start_coherence.py`

| Scenario | Test |
| --- | --- |
| A cycle is rejected | `test_a_cycle_is_rejected` |
| A step naming itself is rejected | `test_a_step_naming_itself_is_rejected` |
| A blocking step depending on a later-starting step is rejected | `test_a_blocking_step_depending_on_a_later_starting_step_is_rejected` |
| A blocking step may depend on a later gate's step that starts early | `test_a_blocking_step_may_depend_on_a_later_gates_step_that_starts_early` |
| A deadlock two hops away is rejected | `test_a_deadlock_two_hops_away_is_rejected` |
| The traversal does not stop at a step that is not active | `test_the_traversal_does_not_stop_at_a_step_that_is_not_active` |
| A step may depend on one starting later than the launch has reached | `test_a_step_may_depend_on_one_starting_later_than_the_launch_has_reached` |
| A non-blocking step is not held to the deadlock rule | `test_a_non_blocking_step_is_not_held_to_the_deadlock_rule` |

**ADDED — The stored step set declares when its steps start** (9)

| Scenario | Test |
| --- | --- |
| A vendored step delivered later carries a start gate | `test_playbook_reference_set_start_gates.py::test_every_vendored_step_states_a_start_gate` (with `::test_every_vendored_definition_carries_its_start_gate_through_the_loader` for the loader half) |
| A vendored step missing a start gate is a fault | `test_playbook_reference_set_start_gates.py::test_a_vendored_step_missing_a_start_gate_is_a_fault` |
| A stored step starts at its own gate | `test_step_start_gate_backfill.py::test_a_stored_step_starts_at_its_own_gate` |
| A stored step anchored before its gate starts earlier | `test_step_start_gate_backfill.py::test_a_stored_step_anchored_before_its_gate_starts_earlier` |
| A final-gate step's default spans more than one gate | `test_step_start_gate_backfill.py::test_a_final_gate_steps_default_spans_more_than_one_gate` |
| A draft step declares a start gate too | `test_step_start_gate_backfill.py::test_a_draft_step_declares_a_start_gate_too` — **see the environment caveat below** |
| An activated draft does not become eligible everywhere | `test_step_start_release.py::test_an_activated_draft_does_not_become_eligible_everywhere` |
| An author may set a step back to starting immediately | `test_step_dependency_preconditions.py::test_an_author_may_set_a_step_back_to_starting_immediately` |
| An authored value survives | `test_step_start_gate_backfill.py::test_the_stored_set_still_serves` — **partial; see *Deliberately untested*** |

**MODIFIED — A step definition declares how it is to be resolved** (2)

| Scenario | Test |
| --- | --- |
| A step definition is read back with every declared attribute | new clause only: `test_step_start_release.py::test_a_step_reads_back_the_gate_it_starts_at_and_the_steps_it_waits_on`; the rest → existing `test_step_definition_field_set.py::test_a_step_definition_is_read_back_with_every_declared_attribute` and `test_launch_playbook.py::test_unauthored_optional_attributes_are_absent` |
| Steps can be selected by gate and by scope | → existing `test_launch_playbook.py`, `test_step_definition_field_set.py`, `test_step_definition_discipline.py` (reproduced unchanged) |

**MODIFIED — An incoherent playbook is rejected against each step's
status** (14). All fourteen scenarios are reproduced unchanged; the
requirement gains four bullets in its rule list and no new scenario.
Covered by the existing files in `tests/unit/launch/domain/`:
`test_launch_playbook.py`, `test_playbook_coherence_by_status.py`,
`test_playbook_coherence_completion.py`, `test_playbook_readiness.py`,
`test_gate_holding_floor.py`, `test_step_automation_brief_and_handler.py`.
What is *new* is that the four start rules must join the aggregated
report (`tasks.md` 2.6), which no existing test can observe — covered by
`test_step_start_coherence.py::test_the_two_new_rules_are_reported_alongside_every_other_fault`.

### `launch-instance`

**ADDED — The launch report states whether each step has started, and
what it waits for** (4) → `test_launch_report_release.py`

| Scenario | Test |
| --- | --- |
| A released step is reported as released | `test_a_released_step_is_reported_as_released` |
| An unreleased step names the gate it starts at | `test_an_unreleased_step_names_the_gate_it_starts_at` |
| An unreleased step names its unresolved dependencies | `test_an_unreleased_step_names_its_unresolved_dependencies` |
| A step waiting on both names both | `test_a_step_waiting_on_both_names_both` |

**MODIFIED — The launch report states whether each step is overdue** (8)

| Scenario | Test |
| --- | --- |
| An overdue non-blocking step is reported overdue | → existing `test_launch_report_step_facts.py::test_an_overdue_non_blocking_step_on_a_healthy_launch_is_reported_overdue` (WHEN reworded to "a **released** non-blocking step"; the fixture declares no start gate, so it is released) |
| An overdue blocking step is reported overdue on its own entry | → existing `test_launch_report_step_facts.py::test_the_overdue_blocking_step_the_at_risk_evaluation_names_is_marked` |
| A step resolved under its own hazard is not overdue | → existing `test_launch_report_step_facts.py::test_a_step_resolved_under_its_own_hazard_is_not_overdue` |
| A step with no due period is not overdue | → existing `test_launch_report_step_facts.py::test_no_step_is_overdue_on_a_launch_with_no_date` |
| A recurring-anchor step on a dated launch is not overdue | → existing `test_launch_report_step_facts.py::test_a_recurring_anchor_step_on_a_dated_launch_is_not_overdue` |
| A step whose start gate is not reached is not overdue though its due period passed | `test_launch_report_release.py::test_a_step_whose_start_gate_is_not_reached_is_not_overdue` |
| A step held only by a dependency is still overdue | `test_launch_report_release.py::test_a_step_held_only_by_a_dependency_is_still_overdue` |
| A step becomes overdue once the launch releases it | `test_launch_report_release.py::test_a_step_becomes_overdue_once_the_launch_releases_it` |

**MODIFIED — The launch date is reported at risk…** (7)

| Scenario | Test |
| --- | --- |
| An overdue unresolved blocking step puts the date at risk | → existing `test_launch_dates.py::test_an_overdue_unresolved_blocking_step_puts_the_date_at_risk` (WHEN reworded to "a **released** blocking step") |
| An overdue non-blocking step does not put the date at risk | → existing `test_launch_dates.py::test_an_overdue_non_blocking_step_does_not_put_the_date_at_risk` |
| A resolved overdue step does not put the date at risk | → existing `test_launch_dates.py::test_a_resolved_overdue_step_does_not_put_the_date_at_risk` |
| A launch without a launch date is never at risk | → existing `test_launch_dates.py::test_a_launch_without_a_launch_date_is_never_at_risk` |
| A blocking step whose start gate is not reached does not put the date at risk | `test_launch_dates_release.py::test_a_blocking_step_whose_start_gate_is_not_reached_does_not_put_the_date_at_risk` |
| A blocking step held by a dependency puts the date at risk | `test_launch_dates_release.py::test_a_blocking_step_held_by_a_dependency_puts_the_date_at_risk` |
| The gate the launch stands at still puts the date at risk | `test_launch_dates_release.py::test_the_gate_the_launch_stands_at_still_puts_the_date_at_risk` |

### `launch-clickup-sync`

**MODIFIED — Human steps are projected as tasks…** (26). Twenty
scenarios are reproduced unchanged and are covered by the existing files
in `tests/unit/launch/infrastructure/driven/`
(`test_clickup_projection_step_fields.py`,
`test_clickup_sync_projection.py`, `test_clickup_task_naming.py`,
`test_clickup_task_name_composition.py`,
`test_clickup_sync_wording_heal.py`); *A step activated mid-launch is
projected* is among them, with "the launch has released it" added to its
WHEN and its fixture declaring no start gate. The six new ones:

| Scenario | Test (`test_clickup_sync_release.py`) |
| --- | --- |
| An unreleased step is not projected | `test_an_unreleased_step_is_not_projected` |
| A step is projected on the pass after the launch releases it | `test_a_step_is_projected_on_the_pass_after_the_launch_releases_it` |
| A step activated mid-launch that the launch has not released is not projected | `test_a_step_activated_mid_launch_that_is_not_released_is_not_projected` |
| A step waiting on another is not projected until that one is resolved | `test_a_step_waiting_on_another_is_not_projected_until_it_is_resolved` |
| A step released by its dependency being retired is projected | `test_a_step_released_by_its_dependency_being_retired_is_projected` |
| A task already created is not withdrawn | `test_a_task_already_created_is_not_withdrawn` |

**MODIFIED — A step that is not active leaves the loop** (9). Seven
reproduced unchanged → existing
`test_clickup_non_active_steps_leave_loop.py` and
`test_clickup_sync_retired_steps.py`. The two new ones:

| Scenario | Test (`test_clickup_sync_release.py`) |
| --- | --- |
| An unreleased step has not left the loop | `test_an_unreleased_step_has_not_left_the_loop` |
| Release does not suppress reconciliation | `test_release_does_not_suppress_reconciliation` |

### `launch-step-automation`

**MODIFIED — An automated step's handler is invoked by recurring work**
(9). Four reproduced unchanged → existing `test_automation_pass.py`
(*An unresolved automated step is invoked* with "released" added to its
WHEN, *A human step is never invoked*, *A resolved step is not invoked
again*, *A graduated launch is left alone*). The five new ones:

| Scenario | Test (`test_automation_pass_release.py`) |
| --- | --- |
| A step whose start gate the launch has not reached is not invoked | `test_a_step_whose_start_gate_is_not_reached_is_not_invoked` |
| A step naming no start gate keeps running from the first pass | `test_a_step_naming_no_start_gate_keeps_running_from_the_first_pass` |
| A step is invoked on the pass after the launch releases it | `test_a_step_is_invoked_on_the_pass_after_the_launch_releases_it` |
| An unreleased step is not reported as stuck | `test_an_unreleased_step_is_not_reported_as_stuck` |
| An unregistered handler on an unreleased step is not reported by the pass | `test_an_unregistered_handler_on_an_unreleased_step_is_not_reported` |

**MODIFIED — An unregistered handler is reported and skipped, never
fatal** (2)

| Scenario | Test |
| --- | --- |
| A step naming an unregistered handler is skipped | → existing `test_automation_pass.py::test_a_step_naming_an_unregistered_handler_is_skipped` |
| A step naming an unregistered handler is not reported before its launch releases it | `test_automation_pass_release.py::test_an_unregistered_handler_on_an_unreleased_step_is_not_reported` — the same observation the requirement above states, covered once by one test carrying both scenario names in its docstring |

### `playbook-authoring`

**ADDED — A dependency may only be authored on an active step** (6) →
`test_step_dependency_preconditions.py`

| Scenario | Test |
| --- | --- |
| Naming a draft step is refused | `test_naming_a_draft_step_is_refused` |
| Naming a retired step is refused | `test_naming_a_retired_step_is_refused` |
| Naming an undefined step is refused | `test_naming_an_undefined_step_is_refused` |
| Every offending dependency is reported at once | `test_every_offending_dependency_is_reported_at_once` |
| Retiring a depended-on step is not refused | `test_retiring_a_depended_on_step_is_not_refused` |
| A stored dependency on a since-retired step still loads | `test_a_stored_dependency_on_a_since_retired_step_still_loads` |

**ADDED — A `prohibited-tactic` step may not be depended upon** (2) →
`test_step_dependency_preconditions.py`

| Scenario | Test |
| --- | --- |
| Depending on a prohibited-tactic step is refused | `test_depending_on_a_prohibited_tactic_step_is_refused` |
| A step re-authored prohibited-tactic releases its dependents | `test_a_step_re_authored_prohibited_tactic_releases_its_dependents` |

**MODIFIED — A step can be created** (4). Two reproduced unchanged →
existing `test_playbook_authoring.py`,
`test_playbook_authoring_new_field_set.py`. The two new ones:

| Scenario | Test |
| --- | --- |
| A step is created declaring when it starts | `test_a_step_is_created_declaring_when_it_starts` |
| A step is created declaring neither | `test_a_step_is_created_declaring_neither` |

**MODIFIED — Every write is validated as the playbook it would produce**
(12). Eleven reproduced unchanged → existing
`test_step_assignee_preconditions.py`,
`test_authoring_roster_collaborator_shape.py`,
`test_playbook_authoring.py`, `test_gate_holding_ratchet.py`,
`test_step_retirement_and_slots.py`. The one new scenario:

| Scenario | Test |
| --- | --- |
| A dependency precondition is evaluated with no roster supplied | `test_a_dependency_precondition_is_evaluated_with_no_roster_supplied` |

### `playbook-admin`

**MODIFIED — The step form carries every authorable field** (6). Three
reproduced unchanged → existing `test_playbook_admin_step_fields.py`.
The three new ones → `test_playbook_admin_start_fields.py`:

| Scenario | Test |
| --- | --- |
| The form offers both start fields | `test_the_form_offers_both_start_fields` |
| Starting immediately is an offered choice | `test_starting_immediately_is_an_offered_choice` |
| The dependency control is grouped and self-excluding | `test_the_dependency_control_is_grouped_and_self_excluding` |

**MODIFIED — Every rule an authoring write can provoke attributes its
fault** (2)

| Scenario | Test |
| --- | --- |
| No rule an authoring write can provoke is unattributed by accident | → existing `test_playbook_admin_fault_attribution.py::test_no_rule_an_authoring_write_can_provoke_is_unattributed_by_accident` — **see the inventory finding below** |
| Each start rule is attributed to its control | `test_playbook_admin_start_fields.py::test_each_start_rule_is_attributed_to_its_control` (six parametrised cases) |

**MODIFIED — A rejected write names the fields its faults concern** (10).
Nine reproduced unchanged → existing
`test_playbook_admin_fault_attribution.py` and
`test_playbook_admin_filtered_moves.py`. The one new scenario:

| Scenario | Test |
| --- | --- |
| A multi-step fault marks the edited step's control | `test_playbook_admin_start_fields.py::test_a_multi_step_fault_marks_the_edited_steps_control` |

The requirement's prose about a *transitive deadlock* marking all four
declarations (dependency, start gate, gate, blocking) is stated in no
scenario but is an obligation under `tasks.md` 5.6 — covered by
`test_playbook_admin_start_fields.py::test_a_transitive_deadlock_marks_every_declaration_it_turns_on`.

### `launch-admin`

**ADDED — A launch's detail page distinguishes a step that has not
started** (7) → `test_launch_admin_start_marks.py`

| Scenario | Test |
| --- | --- |
| An unreleased step is rendered, not hidden | `test_an_unreleased_step_is_rendered_not_hidden` |
| An unreleased step says what it waits for | `test_an_unreleased_step_says_what_it_waits_for` |
| Unreleased is distinguishable from unrecorded | `test_unreleased_is_distinguishable_from_unrecorded` |
| A released step carries no such mark | `test_a_released_step_carries_no_such_mark` |
| A step whose start gate is not reached is never marked overdue | `test_a_step_whose_start_gate_is_not_reached_is_never_marked_overdue` |
| A step waiting on a dependency can be both overdue and waiting | `test_a_step_waiting_on_a_dependency_can_be_both_overdue_and_waiting` |
| The page carries no third sense of blocked | `test_the_page_carries_no_third_sense_of_blocked` |

---

## Uncovered, with reasons

No scenario of this change is left without coverage. Four **clauses**
are, and each is recorded here rather than dropped.

1. **Deliberately untested — that a specific authored `starts_at_gate`
   survives the backfill migration.** *An authored value survives*
   (`launch-playbook`) is covered only as far as the stored set still
   loading and serving. Observing the clause itself means authoring a
   value, downgrading and re-upgrading, which writes to the shared
   integration database this file otherwise only reads, and leaves
   residue behind on failure. `tasks.md` 8.9 (the downgrade check) and
   10.5 (the scratch-database walk-through) are stated as manual
   verification, and that is where this belongs. **The implementation
   step should perform 8.9 and 10.5 by hand and say so.**

2. **Deliberately untested — the "at least two gates" margin as a
   *guarantee*.** The requirement is explicit that two gates is "a
   **margin and not a guarantee** … No window width can be proved
   sufficient". What is tested is the *value* the default lands on, not
   that a launch never crosses the window.

3. **Deliberately untested — that the release predicate performs no
   I/O.** `tasks.md` 3.4 asks for verification "by inspection".
   `test_release_does_not_consult_the_date` asserts the no-clock half
   structurally (the predicate's signature takes no date-like
   parameter); the no-I/O half is left to `tasks.md` 10.4's
   `import-linter` run, which is the mechanism this project already has
   for "domain code must not have reached for a repository".

4. **Deliberately untested — "less legible than the surface's ordinary
   text" for the new start mark.** The `launch-admin` requirement fixes
   that the mark is *rendered* and what it may not say; anything about
   computed style is not in a response, and the existing
   `test_launch_surface_vocabulary_rules.py` records the same exclusion
   for the marks it covers.

---

## First-run passes — recorded, not counted as coverage

Four of the new tests pass on their first run. Under
`ai-toolkit:testing` a first-run pass where no implementation exists is
an alarm, so each was investigated and is recorded here.

| Test | Why it passes | Classification |
| --- | --- | --- |
| `test_automation_pass_release.py::test_a_step_naming_no_start_gate_keeps_running_from_the_first_pass` | today's pass is ungated, so it already invokes this handler | **regression guard** — the change must not take this away; the whole argument that gating withholds nothing rests on it |
| `test_playbook_reference_set_start_gates.py::test_no_vendored_start_gate_names_the_final_gate` | no vendored step declares a start gate at all, so none can name the final one | **vacuous pass** — `test_every_vendored_step_states_a_start_gate` is what stops it staying vacuous |
| `test_playbook_reference_set_start_gates.py::test_the_vendored_set_still_constructs_a_playbook` | the vendored set constructs today | **regression guard** against the new load rules and the new vendored values disagreeing |
| `test_step_start_gate_backfill.py::test_the_stored_set_still_serves` | the stored set serves today | **regression guard** — a start gate the load rules refuse would produce exactly the failure this catches |

Every other new test fails, in one of two states:

- **Absent target** — `TypeError: StepDefinition.__init__() got an
  unexpected keyword argument 'starts_at_gate'` / `'after_steps'`, or
  the loud failure of a probe (`_released`, `_read`,
  `_start_gate_field`, …) reporting that the thing it looks for is not
  there. This establishes absence and **nothing** about whether the
  assertions are any good; they have not executed.
- **Wrong value** — the vendored-file tests, which fail against a file
  that exists and states nothing.

---

## Assertion provenance

Classified per `ai-toolkit:testing`. Every test file carries the same
classification inline, beside each assertion; this is the summary.

**SPECIFIED** — traces to a stated requirement. The great majority: which
launch/step pairs are released, which playbooks are rejected and what
each fault names, which ClickUp writes happen and which do not, which
handlers a pass reaches, which report entries state overdue, which form
controls are offered and which are marked, and what the stored and
vendored sets declare.

**DERIVED** — inferred; no stated requirement covers it. Each is labelled
in the test that carries it:

| Derived assertion | Where | Why |
| --- | --- | --- |
| `after_steps` normalises to a `tuple` | `test_step_start_release.py::test_the_steps_a_step_waits_on_normalise_to_a_tuple` | `tasks.md` 1.1 asks for it; the spec does not name a type. A list on a frozen dataclass is a mutable value shared between readers |
| absence spelled `None` / `()` | `test_step_start_release.py::test_a_step_declaring_neither_reads_back_as_declaring_neither` | `design.md` and `tasks.md` 1.1 fix both spellings; the spec says only "absent" and "empty" |
| a fault "names" X ⇒ X appears in the rendered error | `test_step_start_coherence.py::_message` | no artifact fixes how a fault is carried; both the rendering and a `faults` tuple are read |
| a non-blocking step with a late start gate is refused | `test_step_start_coherence.py::test_a_non_blocking_step_with_a_late_start_gate_is_refused_too` | stated in the requirement's prose, not in a scenario |
| the naming-only-active-steps *permitted* case | `test_step_dependency_preconditions.py::test_naming_only_active_steps_is_accepted` | the rule's complement; without it an implementation refusing every `after_steps` value passes every rejection test |
| the release-predicate spelling and call shape | `_released` probes in three files | no artifact fixes the method name |
| the report's three new attribute spellings | `test_launch_report_release.py::_ATTRIBUTE_ALIASES` | no artifact fixes a field name |
| the start-gate control's field name carries "start"; the dependency control's carries "after"/"depend"/"wait" | `test_playbook_admin_start_fields.py` | no artifact fixes either |
| "starts immediately" is an empty-valued option or one whose label says so | same file, `_IMMEDIATELY_WORDS` | the spec fixes that the choice is offered, not how |
| a step's "row" and a "mark" on the detail page | `test_launch_admin_start_marks.py::_row_of`, `_added` | inherited from `test_launch_admin_detail.py`, which records the same invention |
| the overdue mark's wording | same file, `_OVERDUE_WORDS` | inherited unchanged |
| the vendored YAML key is `starts_at_gate` | `test_playbook_reference_set_start_gates.py` | matches the field name the delta fixes and the file's own key style |
| the seven anchor-exception identifiers and their gates | `test_playbook_reference_set_start_gates.py`, `test_step_start_gate_backfill.py` | transcribed from `tasks.md` 8.2-8.4 rather than recomputed from anchors, because the artifacts state them by identifier |
| dates, offsets and gate choices in every fixture | all files | chosen so each judgement is unambiguous; written as literals rather than recomputed |

Correcting a derived spelling or a call shape is a **fixture
correction**, and each file names its single correction point. Editing a
**specified** assertion to match what the code produced is not available
under any label: a specified assertion that does not match means the code
is wrong.

---

## Obsolete tests — candidates for human confirmation

The change carries nine `MODIFIED` requirements and no `REMOVED` or
`RENAMED` one, so this list is applicable.

**Search bound.** `tests/**/test_*.py`, and nowhere else. No earlier
`test-manifest.md` was supplied to this pass, so no scenario-to-test
index was available; the search matched on scenario text, on the field
names the change introduces, and on the assertions each MODIFIED
requirement's *superseded* text would have produced.

**One entry. Marked as a candidate for human confirmation, not a
conclusion.**

### 1. `tests/unit/launch/domain/test_launch_playbook.py::test_steps_at_the_same_gate_carry_no_ordering`

- **Runner-selectable identifier**
  `uv run pytest "tests/unit/launch/domain/test_launch_playbook.py::test_steps_at_the_same_gate_carry_no_ordering"`
- **Superseding delta** — `launch-playbook`, MODIFIED *A step definition
  declares how it is to be resolved*, which adds "the steps it waits on:
  empty means it waits on none" to what a step definition may declare.
- **Evidence** — the test's final assertion loop and its stated basis:

  ```python
  ORDERING_ATTRIBUTE_NAMES: Final = (
      "position", "order", "sequence", "index", "rank", "priority",
      "depends_on", "dependencies", "after", "before",
      "predecessor", "successor",
  )
  ...
      for name in ORDERING_ATTRIBUTE_NAMES:
          assert not hasattr(first, name), (
              f"StepDefinition exposes {name!r}: the authored within-gate "
              f"order is serving-layer truth, and gates are meant to remain "
              f"the only commitment ordering primitive in the playbook"
          )
  ```

  with the comment above it: *"SPECIFIED (design boundary): a step
  *definition* carries no ordering relative to another … and if it ever
  reached `StepDefinition` the domain would be handed an ordering its
  evaluations must never see."*

- **What is superseded, precisely** — the **premise**, not the assertion.
  A step definition now does carry an ordering relative to another, and
  the domain does evaluate it. The test will nonetheless keep **passing**:
  the field is named `after_steps`, and `hasattr(step, "after")` stays
  `False`. So nothing goes red, and the stale rationale survives
  invisibly.
- **Recommended action, for a human to confirm** — leave the assertion
  in place (it still guards the *within-gate presentation* order, which
  this change does not touch) and revise the comment and the docstring so
  they no longer claim a step definition carries no ordering at all. Do
  **not** add `after_steps` to `ORDERING_ATTRIBUTE_NAMES`.
- This pass did not edit the file.

### No other bearing test was found — and the two readings differ

For the remaining eight MODIFIED requirements, **no such test exists**
rather than "none was found": the reason is structural and checkable.
Every existing fixture builds its steps without `starts_at_gate` and
without `after_steps`, so under the new rules every step those tests
build is released from a launch's first gate, and every assertion they
make is about released steps. The four `MODIFIED` requirements whose text
adds *released* to a WHEN clause (`launch-instance` ×2,
`launch-clickup-sync` ×1, `launch-step-automation` ×1) therefore describe
exactly what those tests already exercise. This was confirmed
empirically: the post-pass runs above show **no pre-existing test
changing state**.

---

## Other findings the implementation step needs

These are not obsolete-test entries — nothing is superseded and nothing
should be deleted — but each is something a run will not tell you.

1. **The fault-attribution inventory is now incomplete.**
   `tests/unit/launch/infrastructure/driving/test_playbook_admin_fault_attribution.py`
   carries `_PROVOCATIONS`, a hand-maintained inventory of every rule an
   authoring write can provoke, parametrising the sweep that covers *No
   rule an authoring write can provoke is unattributed by accident*. That
   file's own docstring records the limit: *"this sweep catches a rule
   **reworded**, not a rule **added**"*. This change adds six provokable
   rules, and none of them is in `_PROVOCATIONS` — so the sweep will stay
   green while covering less than the requirement it is named for. This
   pass covers the six separately, in
   `test_playbook_admin_start_fields.py::test_each_start_rule_is_attributed_to_its_control`,
   and **did not edit the existing file**. Whether to fold them into
   `_PROVOCATIONS` instead is a judgement for whoever implements; it is a
   change to an existing test and is out of this pass's bounds.

2. **The local integration database carries no `draft` step, so
   `tasks.md` 8.8 cannot be observed on it.** Read directly from the
   configured database on 2026-08-29: `playbook_steps` holds **95 `lp.`
   active, 2 `lp.` in-development, 680 `mg.` retired, and zero drafts** —
   777 rows, against the 352 (95 active / 2 in-development / 255 draft)
   `design.md` describes. The 255 drafts come from `seed_playbook`, which
   runs on **container start** rather than as a migration, and has never
   run against this database; the 680 `mg.` rows are residue from the
   authoring tests and are correctly excluded by the `lp.` filter.
   Consequence: `test_step_start_gate_backfill.py::test_a_draft_step_declares_a_start_gate_too`
   fails here with a guard message saying exactly this, and will keep
   failing until the preparation step is run against that database. The
   test was **not** weakened to accommodate it. The active-step gate
   distribution does match `design.md`'s table exactly (listable 64,
   live 9, ignition 7, commit 4, graduated 3, order 3, stock-ready 3,
   phase-one-complete 2), which is what `tasks.md` 8.7's re-derivation
   needs.

3. **Two existing stylesheet tests constrain how `tasks.md` 7.4 may be
   done.** `tests/unit/launch/infrastructure/driving/test_launch_surface_vocabulary_rules.py`
   carries `test_no_selector_this_change_adds_reaches_another_surface`
   and `test_a_reused_class_name_is_never_selected_unqualified`. The new
   start mark's styling must therefore use a **qualified** selector that
   matches nothing the step list, roster page, product index or product
   dossier renders. Nothing here is superseded; this is a constraint that
   will surface as a red existing test if missed.

4. **`mypy` will be red until `tasks.md` 1.1 lands.** 24 errors, all
   `"StepDefinition" has no attribute "starts_at_gate"` / `"after_steps"`,
   across three of the new files. Adding the two fields to
   `StepDefinition` clears every one. The `pre-commit` mypy hook runs
   `uv run mypy .` and will block a commit until then, which is worth
   knowing before the first commit of the implementation.

---

## Unresolved project questions

`AGENTS.md` and `CLAUDE.md` were read (`CLAUDE.md` is a one-line include
of `AGENTS.md`). They settle the runner (`uv run pytest`), the three
tiers and their directory layout, the test-path glob, and how the
integration tier finds its database. They do not settle the following.
Each was answered by assumption, the assumption is recorded, and the
tests depending on it are named — none was resolved silently.

| Question | Assumption taken | Tests depending on it |
| --- | --- | --- |
| What is the release predicate called, and what does it take? | a method on `Launch`, found by probing `has_released` / `released` / `is_released` / `releases` / `has_started` / `step_released`, called `(playbook, step)` with four fallback shapes | every test in `test_step_start_release.py`; `test_step_start_coherence.py::test_a_step_may_depend_on_one_starting_later_than_the_launch_has_reached`; `test_step_dependency_preconditions.py::test_a_step_re_authored_prohibited_tactic_releases_its_dependents` and `::test_a_step_is_created_declaring_neither` |
| How does the launch report spell "released", "the gate it starts at" and "the unresolved dependencies"? | `_ATTRIBUTE_ALIASES` in `test_launch_report_release.py`, four to five candidates each, failing loudly when none is present | all seven tests in `test_launch_report_release.py` |
| What are the two new form fields called? | the start-gate field's name contains `start`; the dependency field's contains one of `after` / `depend` / `wait` | all five tests in `test_playbook_admin_start_fields.py` |
| How does the page mark an unreleased step? | differentially — the text an unreleased step's row carries that an otherwise-identical released step's row does not | all seven tests in `test_launch_admin_start_marks.py` |
| Which module attribute names the vendored YAML file? | probed across a candidate list and then across every `Path` attribute of `commerce_ops.seed_playbook`, failing loudly | `test_playbook_reference_set_start_gates.py::test_a_vendored_step_missing_a_start_gate_is_a_fault` |
| Does the vendored loader raise a domain error, a `ValueError`, a `KeyError` or a `TypeError` on a missing field? | any of the four; the delta fixes that delivery *fails*, not how | same test |
| Is the backfill's stored-set assertion allowed to write? | no — this file reads only, and the authored-value-survives clause is left to manual verification | `test_step_start_gate_backfill.py::test_the_stored_set_still_serves` |

Where an assumption is wrong, the file's named correction point is the
one place to change. **Correcting a probe is a fixture correction.
Editing what a test asserts, to match what the code produced, is not.**
