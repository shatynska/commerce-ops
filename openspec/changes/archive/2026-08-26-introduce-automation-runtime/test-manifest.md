# Test manifest — `introduce-automation-runtime`

Written by a test-design pass run **before** any implementation exists, from
this change's delta specs alone. No implementation source under
`src/commerce_ops/` was read while deriving these tests; the public surfaces
they call were learned from the delta specs, `design.md`, `tasks.md`, the
specifications under `openspec/specs/`, and the existing tests under
`tests/**/test_*.py`.

**This file is not part of the OpenSpec schema.** It will not appear among
`openspec instructions apply`'s context files, so whoever implements this
change must open it on purpose. `openspec/changes/introduce-automation-runtime/test-manifest.md`
is its only location.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted, disabled, or weakened. The only file written outside the
test-path glob `tests/**/test_*.py` is this manifest.

---

## Baseline

Recorded before any test here was written, from the worktree
`/home/shatynska/projects/commerce-ops-automated-step` at commit `a4cb7d3`,
a clean tree:

| Command | Result |
|---|---|
| `uv run pytest tests/unit tests/agents` | **901 passed, 0 failed** |
| `uv run pytest tests/integration` | **3 passed, 81 skipped, 0 failed** |

The integration tier skipped almost entirely: no database is configured in
this environment (`DATABASE_URL` unset; neither `.env.test` nor `.env`
carries it). Every integration-tier assertion below has therefore **never
been executed against a database at all** — its state is "not run", which is
weaker than "absent target" and is recorded as such wherever it applies.

Full-suite state **after** this pass, for attribution:

```
uv run pytest tests/unit tests/agents -q --continue-on-collection-errors
  → 22 failed, 904 passed, 4 errors
```

- **904 passed** = the 901 baseline passes, all still passing, plus 3 new
  tests that pass on their first run (each investigated below).
- **22 failed + 4 collection errors** are all new, and all belong to this
  pass.
- `--continue-on-collection-errors` is needed for that number: without it
  the four absent-target `ImportError`s abort collection and the suite runs
  nothing. **Consequence for the implementer:** the `pre-commit`
  `pytest (unit + agents)` hook will fail outright until
  `StepContext`/`StepResolution`, `automation_pass.py`,
  `automation_confirmation.py` and the advisor module exist. That is the
  expected pre-implementation state, not a defect in these tests.

`uv run ruff check` and `uv run ruff format --check` are clean over `tests/`.
`uv run mypy .` reports **8 errors, all absent-target** (`has no attribute
"StepContext"`, `"StepResolution"`, `"automation_pass"`,
`"automation_confirmation"`; `No module named
"commerce_ops.subcategory_advisor"`). Each disappears when the named target
lands; none is a type defect in a test. `tasks.md` 8.4 is where mypy becomes
clean again.

---

## Scenario accounting — the count

The delta specs carry **61** `#### Scenario:` blocks across **24**
requirements. All 61 are accounted for below: **57 covered**, **4 recorded
as uncovered with a reason**.

| Delta spec | Requirements | Scenarios | Covered | Uncovered |
|---|---|---|---|---|
| `launch-step-automation` (ADDED) | 15 | 31 | 30 | 1 |
| `subcategory-advisor` (ADDED) | 5 | 8 | 8 | 0 |
| `launch-clickup-sync` (MODIFIED) | 3 | 16 | 13 | 3 |
| `launch-playbook` (MODIFIED) | 1 | 6 | 6 | 0 |
| **Total** | **24** | **61** | **57** | **4** |

The three uncovered `launch-clickup-sync` scenarios and the one uncovered
`launch-step-automation` scenario are each covered by an **existing** test —
they are recorded as uncovered *by this pass*, with the existing test named,
rather than dropped.

---

## New test files

| File | Tier | Runner-selectable tests | First-run state |
|---|---|---|---|
| `tests/unit/launch/infrastructure/driving/test_automation_pass.py` | unit | 27 (26 fns) | absent target (`ImportError`) |
| `tests/unit/launch/infrastructure/driving/test_automation_pass_schedule.py` | unit | 4 | 3 fail (absent), 1 passes — see *First-run passes* |
| `tests/unit/launch/application/test_step_handler_contract.py` | unit | 14 (9 fns) | absent target (`ImportError`) |
| `tests/unit/launch/application/test_automated_result_decisions.py` | unit | 14 (11 fns) | all 14 fail on an absent use case |
| `tests/unit/launch/infrastructure/driving/test_automation_confirmation_delivery.py` | unit | 3 | absent target (`ImportError`) |
| `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` | agents | 10 | absent target (`ModuleNotFoundError`) |
| `tests/unit/launch/infrastructure/driven/test_clickup_automated_steps_leave_loop.py` | unit | 5 | **4 fail on a wrong value**, 1 passes |
| `tests/unit/launch/infrastructure/driving/test_clickup_webhook_automated_step.py` | unit | 2 | **1 fails on a wrong value**, 1 passes |
| `tests/integration/launch/test_automated_result_store_live.py` | integration | 2 | **not run** (no database configured) |
| `tests/integration/launch/test_registered_handlers_activate_nothing.py` | integration | 3 | **not run** (no database configured) |
| **Total** | | **84 (75 fns)** | |

Every test is named so the project's runner can select it individually:
`uv run pytest '<file>::<test_name>'`, with `[accepting]` / `[rejecting]` /
`[not-started]` / `[in-progress]` / outcome-type ids on the parametrised
ones.

### The failing-state breakdown, per `ai-toolkit:testing`

- **State 2 (absent target)** — **71 tests**, of which **54 are not even
  collected** (their module's import fails) and 17 fail on a loud probe that
  found no implemented target. The assertions have *not* been exercised.
  This establishes absence and nothing more.
- **State 1 (the code ran and produced a wrong value)** — **5 tests**, all
  in the two ClickUp files. These are the highest-value tests in this pass:
  they execute against the current implementation and discriminate. Each
  fails because `reconcile_launch` / the webhook records a `clickup`-sourced
  `Satisfied` for a step the revised requirement excludes. That is exactly
  the defect `design.md` names as "it defeats the change's own migration"
  and `tasks.md` 4a.1–4a.4 exist to fix.
- **State 4 (passed on its first run)** — **3 tests**, each investigated
  below rather than recorded as coverage without comment.
- **Not run** — 5 integration tests, skipped by the tier's database gate.

71 + 5 + 3 + 5 = **84 runner-selectable tests written by this pass**, across
75 test functions (five are parametrised).

### First-run passes, investigated

1. `test_automation_pass_schedule.py::test_no_externally_reachable_route_invokes_a_handler`
   — a **prohibition** ("Invocation SHALL NOT be reachable from outside the
   deployment"). A prohibition over a surface that does not yet exist
   passes vacuously today; its value is regression protection once the pass
   and the Slack decision route land. This is the same shape as the
   existing `test_clickup_sync_job_schedule.py::test_no_externally_reachable_route_starts_the_reconciliation_pass`,
   which the project already keeps for the same reason.
2. `test_clickup_automated_steps_leave_loop.py::test_a_step_returning_to_human_work_rejoins_the_loop`
   — the **outward** half of the loop already excludes `automated` steps
   (`is_projectable` is kind-aware today), so the resume path already
   behaves as the revised requirement states. Target-exists case: it pins
   existing behaviour while `reconcile_launch` changes around it.
3. `test_clickup_webhook_automated_step.py::test_the_same_closure_on_a_human_step_still_records`
   — deliberately a discrimination check, not new coverage. It exists so
   that an implementation which broke the webhook outright (recording
   nothing for anyone) cannot make the test beside it pass for the wrong
   reason. A first-run pass is its intended state.

---

## `launch-step-automation` (ADDED, 15 requirements, 31 scenarios)

### Requirement: An automated step's handler is invoked by recurring work

| Scenario | Covering test(s) |
|---|---|
| An unresolved automated step is invoked | `test_automation_pass.py::test_an_unresolved_automated_step_is_invoked` |
| A human step is never invoked | `test_automation_pass.py::test_a_human_step_is_never_invoked` |
| A resolved step is not invoked again | `test_automation_pass.py::test_a_resolved_step_is_not_invoked_again`, `::test_a_terminal_not_applicable_also_stops_re_invocation` |
| A graduated launch is left alone | `test_automation_pass.py::test_a_graduated_launch_is_left_alone` |

Statement clauses with no scenario of their own:
`test_automation_pass_schedule.py::test_handlers_are_invoked_from_work_that_runs_on_a_declared_schedule`,
`::test_the_declared_schedule_becomes_due_every_fifteen_minutes`,
`::test_the_automation_pass_declares_a_tolerance`,
`::test_no_externally_reachable_route_invokes_a_handler`.

### Requirement: A handler receives the step, the launch and the product, and attributes nothing

| Scenario | Covering test(s) |
|---|---|
| The product is supplied, not fetched | `test_automation_pass.py::test_the_product_is_supplied_not_fetched` |
| A produced outcome is attributed to the handler | `test_automation_pass.py::test_a_produced_outcome_is_attributed_to_the_handler` |
| A handler cannot claim another source | `test_step_handler_contract.py::test_a_resolution_has_no_place_to_put_provenance` (the contract half) **and** `test_automation_pass.py::test_a_smuggled_provenance_does_not_displace_the_constructed_one` (the recording half) |

Statement clauses: `test_step_handler_contract.py::test_a_context_carries_the_step_the_launch_the_product_and_the_moment`,
`::test_a_resolution_carries_an_outcome_from_the_vocabulary_and_its_text`,
`::test_a_resolution_refuses_empty_produced_text`,
`::test_no_field_of_the_contract_is_a_provenance_in_disguise`.

### Requirement: A non-terminal outcome is recorded directly and never held for a decision

| Scenario | Covering test(s) |
|---|---|
| A non-terminal outcome on a confirmable step is recorded, not held | `test_automation_pass.py::test_a_non_terminal_outcome_on_a_confirmable_step_is_recorded_not_held` |
| A step reporting no progress is reconsidered on the next pass | `test_automation_pass.py::test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass` |

Statement clause (`NotStarted` and `InProgress`, which carry no reason):
`test_automation_pass.py::test_a_reasonless_non_terminal_outcome_is_recorded_directly_too[not-started]` / `[in-progress]`.

### Requirement: A terminal outcome the step's hazard forbids is a handler fault, not a recording

| Scenario | Covering test(s) |
|---|---|
| An impermissible proposal is refused before it is stored | `test_automation_pass.py::test_an_impermissible_proposal_is_refused_before_it_is_stored` |

Statement clause ("Before storing **or recording** anything"):
`test_automation_pass.py::test_an_impermissible_proposal_is_refused_on_an_unconfirmed_step_too`.

### Requirement: An unregistered handler is reported and skipped, never fatal

| Scenario | Covering test(s) |
|---|---|
| A step naming an unregistered handler is skipped | `test_automation_pass.py::test_a_step_naming_an_unregistered_handler_is_skipped` |

### Requirement: A handler failure resolves nothing and does not stop the pass

| Scenario | Covering test(s) |
|---|---|
| A failing handler leaves the step untouched | `test_automation_pass.py::test_a_failing_handler_leaves_the_step_untouched` |
| One failure does not abandon the remaining launches | `test_automation_pass.py::test_one_failure_does_not_abandon_the_remaining_launches` |
| A completed walk is a successful run | `test_automation_pass.py::test_a_completed_walk_is_a_successful_run` |

### Requirement: A result needing no confirmation is recorded at once

| Scenario | Covering test(s) |
|---|---|
| An unconfirmed result is recorded directly | `test_automation_pass.py::test_an_unconfirmed_result_is_recorded_directly` |

### Requirement: A result needing confirmation is held until a person decides

| Scenario | Covering test(s) |
|---|---|
| A confirmable terminal result is held rather than recorded | `test_automation_pass.py::test_a_confirmable_terminal_result_is_held_rather_than_recorded` |
| A pending result suppresses re-invocation | `test_automation_pass.py::test_a_pending_result_suppresses_re_invocation` |
| Two overlapping passes cannot both produce a pending result | `test_automated_result_store_live.py::test_two_overlapping_passes_cannot_both_produce_a_pending_result` (integration; **not run here**) |

Statement clause (the index is *partial*, so a settled row frees the pair):
`test_automated_result_store_live.py::test_settling_a_result_frees_the_launch_and_step_pair`.

### Requirement: A pending result is delivered for a decision, and delivery failure does not lose it

| Scenario | Covering test(s) |
|---|---|
| A pending result reaches Slack | `test_automation_confirmation_delivery.py::test_a_pending_result_reaches_slack` |
| Undelivered is not undone | `test_automation_pass.py::test_undelivered_is_not_undone` |
| An undelivered result is delivered again later | `test_automation_pass.py::test_an_undelivered_result_is_delivered_again_later` |

Adjacent: `test_automation_confirmation_delivery.py::test_the_message_goes_to_the_monitoring_channel`,
`::test_a_delivery_failure_reaches_the_caller`,
`test_automation_pass.py::test_an_already_delivered_result_is_not_delivered_again`.

### Requirement: Only a known, active person may decide a pending result

| Scenario | Covering test(s) |
|---|---|
| An unknown identity cannot decide | `test_automated_result_decisions.py::test_an_unknown_identity_cannot_decide[accepting]` / `[rejecting]` |
| A deactivated person cannot decide | `test_automated_result_decisions.py::test_a_deactivated_person_cannot_decide[accepting]` / `[rejecting]` |

### Requirement: Accepting records the proposed outcome and names the accepter

| Scenario | Covering test(s) |
|---|---|
| An accepted result becomes the step's outcome | `test_automated_result_decisions.py::test_an_accepted_result_becomes_the_steps_outcome` |
| A failed recording leaves the result decidable | `test_automated_result_decisions.py::test_a_failed_recording_leaves_the_result_decidable` |

Statement clause ("settled and SHALL no longer suppress re-invocation"):
`test_automated_result_decisions.py::test_an_accepted_result_is_settled_and_no_longer_suppresses`.

### Requirement: Rejecting does not terminate the step

| Scenario | Covering test(s) |
|---|---|
| A rejected result leaves the step live | `test_automated_result_decisions.py::test_a_rejected_result_leaves_the_step_live` |
| Rejection is never a refusal | `test_automated_result_decisions.py::test_rejection_is_never_a_refusal` |

Statement clause ("settle the pending result **as rejected**", which the
cool-off keys on): `test_automated_result_decisions.py::test_a_rejected_result_is_settled_as_rejected_not_voided`.

### Requirement: A rejected step is not re-proposed immediately

| Scenario | Covering test(s) |
|---|---|
| A rejected step is skipped within the cool-off | `test_automation_pass.py::test_a_rejected_step_is_skipped_within_the_cool_off` |
| A rejected step is offered to the handler again once the cool-off elapses | `test_automation_pass.py::test_a_rejected_step_is_offered_again_once_the_cool_off_elapses` |

Design rule with no scenario (`voided` is not a rejection):
`test_automation_pass.py::test_a_voided_result_is_not_a_rejection_for_the_cool_off`.

### Requirement: A pending result is decided once

| Scenario | Covering test(s) |
|---|---|
| A repeated decision changes nothing | `test_automated_result_decisions.py::test_a_repeated_decision_changes_nothing` |

### Requirement: A decision on a step the playbook no longer serves is refused

| Scenario | Covering test(s) |
|---|---|
| A decision on a de-activated step is refused and the result voided | `test_automated_result_decisions.py::test_a_decision_on_a_de_activated_step_is_refused_and_the_result_voided[accepting]` / `[rejecting]` |

Statement clause (the retirement route, which the scenario does not name):
`test_automated_result_decisions.py::test_a_decision_on_a_retired_step_is_refused_and_the_result_voided`.

---

## `subcategory-advisor` (ADDED, 5 requirements, 8 scenarios)

All eight in
`tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py`.

| Scenario | Covering test |
|---|---|
| A recommendation names node, demands and alternative | `::test_a_recommendation_names_node_demands_and_alternative` |
| A recommendation is readable as it stands | `::test_a_recommendation_is_readable_as_it_stands` |
| A supported choice proposes satisfaction | `::test_a_supported_choice_proposes_satisfaction` |
| An unsupported choice proposes no satisfaction | `::test_an_unsupported_choice_proposes_no_satisfaction` |
| Producing a recommendation invokes no tools | `::test_producing_a_recommendation_invokes_no_tools` |
| Two invocations do not share context | `::test_two_invocations_do_not_share_context` |
| Language model call fails | `::test_a_model_failure_is_surfaced` |
| Response content is not a plain string | `::test_a_non_string_response_content_is_surfaced`, `::test_a_non_string_response_is_never_returned_as_a_recommendation` |

Statement clause ("including two invocations for the same product"):
`::test_two_invocations_for_the_same_product_are_independent`.

**Read carefully — what a stubbed model can establish.** Scenario *A
recommendation names node, demands and alternative* is asserted against the
**prompt the advisor hands the model**, not against the model's answer. With
the model stubbed, the answer's content is whatever the stub says, so the
only observable form of "the recommendation contains these three parts" is
that the advisor demands them. This is a reading, and it is recorded as one.
Whether a proposed browse node is *correct* is deliberately untested — see
below.

---

## `launch-clickup-sync` (MODIFIED, 3 requirements, 16 scenarios)

### Requirement: A step that is not active leaves the loop

The requirement is generalised from "a step that is not `active`" to "a step
the loop no longer projects", keying on kind, status and hazard. Its five
existing scenarios are unchanged in wording and behaviour; two are new.

| Scenario | Covering test(s) | Who wrote it |
|---|---|---|
| A retired step's task is left unmanaged | `tests/unit/launch/infrastructure/driven/test_clickup_non_active_steps_leave_loop.py::test_a_retired_steps_task_is_left_unmanaged`; `.../test_clickup_sync_retired_steps.py::test_a_retired_steps_task_is_left_unmanaged` | **existing** — uncovered by this pass |
| A retired step's closure is not recorded | `.../test_clickup_non_active_steps_leave_loop.py::test_a_retired_steps_closure_is_not_recorded`; `.../test_clickup_sync_retired_steps.py::test_a_retired_steps_closure_is_not_recorded` | **existing** — uncovered by this pass |
| A closure during retirement is never replayed | `.../test_clickup_sync_retired_steps.py::test_a_closure_during_retirement_is_never_replayed` | **existing** — uncovered by this pass |
| An un-retired step resumes through its existing task | `.../test_clickup_non_active_steps_leave_loop.py::test_a_step_returning_to_active_resumes_through_its_existing_task` **and, for the delta's narrowing of it to "`active` `human` work"**, `test_clickup_automated_steps_leave_loop.py::test_a_step_returning_to_human_work_rejoins_the_loop` | existing + this pass |
| A de-activated step leaves the loop exactly as a retired one does | `.../test_clickup_non_active_steps_leave_loop.py::test_a_de_activated_step_leaves_the_loop_exactly_as_a_retired_one_does` | **existing** |
| **A step that becomes automated leaves the loop while staying active** | `test_clickup_automated_steps_leave_loop.py::test_a_step_that_becomes_automated_leaves_the_loop_while_staying_active` | **this pass** |
| **Closing the orphaned task of an automated step records nothing** | `test_clickup_automated_steps_leave_loop.py::test_closing_the_orphaned_task_of_an_automated_step_records_nothing` (reconciliation half) **and** `test_clickup_webhook_automated_step.py::test_closing_the_orphaned_task_of_an_automated_step_records_nothing` (webhook half) | **this pass** |

Statement clauses this pass additionally covers:
`test_clickup_automated_steps_leave_loop.py::test_a_closure_while_automated_is_not_replayed_if_the_step_returns`
(the never-replayed rule, applied to the kind route) and
`::test_a_prohibited_tactic_step_also_leaves_the_loop` (the third field the
generalised rule names, stated in no scenario).

### Requirement: Completion flows from ClickUp to the launch as a recorded outcome

**Every one of this requirement's five scenarios is textually unchanged by
the delta.** What changes is one sentence of the requirement statement:
"These recordings apply only to a step the **served playbook defines**"
becomes "only to a step the **loop still projects**". No scenario turns on
that sentence, so no new test is owed for any of them.

| Scenario | Covering test | Who wrote it |
|---|---|---|
| A closed task records Satisfied | `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py::test_a_closed_task_records_satisfied`; and, as the discrimination check for the narrowed rule, `test_clickup_webhook_automated_step.py::test_the_same_closure_on_a_human_step_still_records` | existing + this pass |
| A reopened task records InProgress | `.../test_clickup_webhook.py::test_a_reopened_task_records_in_progress` | **existing** — uncovered by this pass |
| A reopening without an observed closing records nothing | `.../test_clickup_webhook.py::test_a_reopening_without_an_observed_closing_records_nothing` | **existing** |
| A repeated delivery changes nothing | `.../test_clickup_webhook.py::test_a_repeated_delivery_changes_nothing` | **existing** |
| The system never closes a task | `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py::test_the_system_never_closes_a_task` | **existing** |

The re-scoped sentence itself is covered by the leaves-the-loop tests above:
`test_clickup_webhook_automated_step.py::test_closing_the_orphaned_task_of_an_automated_step_records_nothing` is
precisely a step the served playbook still defines and the loop no longer
projects.

### Requirement: The reconciliation pass records completions and reopenings the webhook missed

Same shape: all four scenarios textually unchanged; one sentence re-scoped.

| Scenario | Covering test | Who wrote it |
|---|---|---|
| A missed completion is recorded on reconciliation | `.../test_clickup_sync_reconciliation.py::test_a_missed_completion_is_recorded_on_reconciliation` | **existing** |
| A missed reopening is recorded on reconciliation | `.../test_clickup_sync_reconciliation.py::test_a_missed_reopening_is_recorded_on_reconciliation` | **existing** |
| No transition means no recording | `.../test_clickup_sync_reconciliation.py::test_no_transition_means_no_recording` | **existing** |
| Reconciliation never overwrites other recording paths | `.../test_clickup_sync_reconciliation.py::test_reconciliation_never_overwrites_other_recording_paths` | **existing** |

The re-scoped sentence ("still observed — its retained state updated — but
records nothing") is covered by
`test_clickup_automated_steps_leave_loop.py::test_closing_the_orphaned_task_of_an_automated_step_records_nothing`,
which asserts both halves.

---

## `launch-playbook` (MODIFIED, 1 requirement, 6 scenarios)

### Requirement: The authored set exercises the full step vocabulary

The delta changes a *justification* ("no automation runtime exists yet, so
no handler can be registered for them" expires) and adds one scenario. The
seeded statuses themselves are unchanged.

| Scenario | Covering test | Who wrote it |
|---|---|---|
| Anchor kinds are all present | `tests/integration/launch/test_seeded_step_fields.py::test_every_timing_anchor_kind_is_represented` | **existing** |
| Every discipline appears | `.../test_seeded_step_fields.py::test_every_discipline_is_represented` | **existing** |
| Execution modes and the compliance hazard are represented | `.../test_seeded_step_fields.py::test_kinds_confirmation_and_the_compliance_hazard_are_represented` | **existing** |
| Prohibited tactics are present and never block | `.../test_seeded_step_fields.py::test_prohibited_tactics_are_present_and_never_block` | **existing** |
| Outstanding rule-policy decisions stay visible | `.../test_seeded_step_fields.py::test_outstanding_readiness_decisions_stay_visible`; `tests/unit/launch/application/test_report_activation_blockers.py::test_steps_that_cannot_be_activated_are_listed_with_their_reason` | **existing** |
| **A registered runtime does not activate a seeded step** | `tests/integration/launch/test_registered_handlers_activate_nothing.py::test_a_registered_runtime_does_not_activate_a_seeded_step` | **this pass** |

Statement clauses this pass additionally covers:
`::test_every_seeded_human_step_is_still_active_after_registration` and
`::test_no_seeded_automated_step_is_activated_by_its_handler_existing`.

**Why a new file rather than an addition to `test_seeded_step_fields.py`.**
The existing file already asserts the seeded statuses, but it does so in a
process that registers no handler, so it cannot observe the scenario's
**WHEN** ("a deployment registers step handlers"). Editing that file is also
forbidden to this pass. The new file calls `register_all()` and refuses to
proceed with an empty registry, so it cannot pass vacuously.

---

## Uncovered scenarios, with reasons

Four scenarios carry **no test written by this pass**. Each is recorded here
rather than dropped, with the reason and the existing test that does cover
it. The absence of a new test is a decision, not an omission.

| Scenario | Requirement | Reason |
|---|---|---|
| A retired step's task is left unmanaged | `launch-clickup-sync` / A step that is not active leaves the loop | Textually unchanged by the delta and already covered twice (`test_clickup_non_active_steps_leave_loop.py`, `test_clickup_sync_retired_steps.py`). The generalisation widens the *rule*; this instance of it is untouched. A third copy would assert nothing new. |
| A retired step's closure is not recorded | same | As above — same two files, same reason. |
| A closure during retirement is never replayed | same | Already covered by `test_clickup_sync_retired_steps.py::test_a_closure_during_retirement_is_never_replayed`. This pass covers the *generalised* form of the same rule for the kind route (`test_a_closure_while_automated_is_not_replayed_if_the_step_returns`), which is what the delta adds. |
| A reopened task records InProgress | `launch-clickup-sync` / Completion flows from ClickUp | Textually unchanged; already covered by `test_clickup_webhook.py::test_a_reopened_task_records_in_progress`. The delta's re-scoping of the requirement's statement affects which *steps* it applies to, and that is covered by the leaves-the-loop tests. |

Two further **statement clauses** (not scenarios) are deliberately uncovered
and recorded here for the same reason:

- *"a decision SHALL be acknowledged within Slack's timeout independently of
  whether the recording it triggers has completed"* — a property of the
  Slack adapter's acknowledgement, not of the decision. It is unobservable
  at the use-case level `test_automated_result_decisions.py` works at, and
  the equivalent property is already required and tested for this app's
  other listener (`test_slack_entry_ack_and_failure_visibility.py`). Task
  6.3/6.4 should confirm it by hand.
- *"Decisions arrive on the same verified `product_agent` Slack surface
  `launch-entry` already uses"* — verification is `slack-trigger`'s
  requirement, covered by `test_slack_entry_request_verification.py`, and
  this delta adds no scenario about it.

---

## Deliberately untested, recorded rather than omitted

Each of these is a case identified and knowingly left uncovered.

1. **Whether the advisor's proposed browse node is a real or correct Amazon
   node.** No deterministic test can establish it, and the spec does not
   claim it — "The advisor is never relied on to settle the step by
   itself".
2. **`build_production_graph()`'s model constant.** `design.md`'s Open
   Questions leave the model choice open; exercising it needs a live call,
   which the `tests/agents/` tier forbids.
3. **`tasks.md` 2.2 — typing `StepHandlerRegistry`'s callables against the
   contract.** A static-analysis obligation whose point is that it fails
   before run time. `uv run mypy` (task 8.4) observes it; a runtime
   assertion over `__annotations__` would pin a spelling no scenario
   states.
4. **The Slack message's layout, ordering and wording** beyond the four
   facts its scenario names. Same reading `test_briefing_delivery.py`
   records: asserting a phrasing imposes a contract nobody agreed to.
5. **Which collaborators the scheduled job wrapper hands the pass**, and the
   pass's internal ordering between delivering and resolving. `design.md`
   fixes the ordering but no scenario turns on it, and both halves are
   observable independently.
6. **`tasks.md` 8.6a — both composition roots resolving the same handler
   names in a fresh interpreter.** It is a registry-parity property of the
   deployment, not of any scenario, and its natural home is the existing
   `tests/unit/test_registrations_across_processes.py`, which this pass may
   not edit. **The implementer must add it there.**
7. **`tasks.md` 5.1–5.4 — the Slack listener-contribution seam.** `design.md`
   states outright that "the seam has no observable behaviour of its own"
   and that `slack-trigger` therefore gets no delta. What it owes is proof
   that the existing `omni_agent` and `access` identities behave
   identically, which the existing suite already provides once the refactor
   lands — no new test is derivable from a spec that states no new
   requirement.
8. **The Alembic revision's downgrade** (`tasks.md` 1.3's second half).
   Asserting it needs a migration harness this suite does not have.
9. **Cross-process/genuinely concurrent overlap** of two passes. The
   integration test uses two independent sessions, which is what the
   partial unique index actually guards; a real race would be
   nondeterministic and would establish nothing the index check does not.

---

## Assertion provenance

Per `ai-toolkit:testing`, every assertion is **specified**, **derived**, or
**deliberately untested**. Section 7 above lists the third. Assertions marked
`# SPECIFIED:` inline trace to a stated requirement. The **derived** ones —
each labelled in its own test's docstring — are collected here so they are
reviewable rather than mistaken for stated requirements:

| Derived assertion | Where | What it rests on |
|---|---|---|
| The pass's cadence is 15 minutes | `test_automation_pass_schedule.py::test_the_declared_schedule_becomes_due_every_fifteen_minutes` | `tasks.md` 4.1's `AUTOMATION_SCHEDULE`. The spec fixes only that a schedule is declared. |
| The cool-off window is 24 hours | `test_automation_pass.py::test_a_rejected_step_is_offered_again_once_the_cool_off_elapses` (`COOL_OFF`) | `design.md`. The spec fixes only that a *fixed* cool-off exists and then expires. |
| A `voided` row is not a rejection for the cool-off | `test_automation_pass.py::test_a_voided_result_is_not_a_rejection_for_the_cool_off` | `design.md`; `tasks.md` 4.3. No scenario states it. |
| An already-delivered pending result is not re-delivered | `test_automation_pass.py::test_an_already_delivered_result_is_not_delivered_again` | `design.md`'s `delivered_at` stamping. |
| The confirmation goes to `PRODUCT_AGENT_MONITORING_CHANNEL_ID` | `test_automation_confirmation_delivery.py::test_the_message_goes_to_the_monitoring_channel` | `tasks.md` 6.1 and the proposal's "no new configuration". |
| A delivery failure reaches the caller | `test_automation_confirmation_delivery.py::test_a_delivery_failure_reaches_the_caller` | The adapter's share of the spec's "the pending result SHALL remain available to be delivered again". |
| `StepContext` and `StepResolution` are frozen | `test_step_handler_contract.py::test_a_context_is_frozen`, `::test_a_resolution_is_frozen` | `tasks.md` 2.1. |
| Whitespace-only produced text is refused | `test_step_handler_contract.py::test_a_resolution_refuses_produced_text_that_is_only_whitespace` | Extension of "SHALL NOT be empty". Reconsider *this* one, not the empty-string test, if the implementation deliberately admits it. |
| The context carries no repository/store; the resolution carries no attribution field | `test_step_handler_contract.py::test_a_context_carries_no_repository_or_store`, `::test_no_field_of_the_contract_is_a_provenance_in_disguise` | Probes, **not exhaustive**. Their name lists are judgement, not specification. |
| `ValueError` / `TypeError` / `FrozenInstanceError` as rejection signals | throughout `test_step_handler_contract.py` | Project convention (`test_step_outcome.py`) and Python's own dataclass behaviour. |
| "Reported" means a warning-level application log record | `test_automation_pass.py` (three tests use `caplog`) | The reading `test_clickup_projection_step_fields.py` already records for this module's other pass. |
| "Recorded as a successful run" means the pass body returns normally | `test_automation_pass.py::test_a_completed_walk_is_a_successful_run` | The reading `test_daily_briefing_job.py` records for the same words. |
| A prohibited-tactic step also leaves the ClickUp loop | `test_clickup_automated_steps_leave_loop.py::test_a_prohibited_tactic_step_also_leaves_the_loop` | The requirement statement names hazard as the third field; no scenario does. |
| Non-string model content raises *some* exception | `test_subcategory_advisor_graph.py::test_a_non_string_response_content_is_surfaced` | The spec fixes visibility, not a type. The `omni-agent` precedent uses a named `NonStringAnswerError`. |

---

## Unresolved project questions

Every one of these arose while deriving tests, is unanswered by `AGENTS.md`,
`CLAUDE.md`, `README.md` or this change's artifacts, and was **not resolved
silently**. Each records the assumption taken, the tests that depend on it,
and the single place to correct it. This pass runs as a dispatched subagent
with no channel to ask on, which is why they are recorded here rather than
raised in conversation.

### Naming and placement

| # | Question | Assumption taken | Depends on it | Correction point |
|---|---|---|---|---|
| 1 | The pass's entry-point name and call shape. | `automation_pass.run_automation_pass(launches=, playbook=, handlers=, results=, record_outcome=, read_product=, deliver=, now=)`, mirroring `converge_launch`. | all 26 tests in `test_automation_pass.py` | `_pass_entry()` / `_run_pass` |
| 2 | The decision use cases' names and call shape. | `accept_automated_result` / `reject_automated_result` on `launch.application`, or a single `decide_automated_result(accept=...)`. | all 14 in `test_automated_result_decisions.py` | `_decide` |
| 3 | The confirmation adapter's delivery function, and the Slack poster it reaches through. | `automation_confirmation.deliver_pending_result(result=, product=, step_name=)`, posting through a substitutable module global. | all 3 in `test_automation_confirmation_delivery.py` | `_delivery_callable()` / `_deliver` / `_install_poster` |
| 4 | The advisor's Python package path. | `commerce_ops.subcategory_advisor.application.graph`, from `design.md`'s "its own module following `omni_agent/application/graph.py`" plus the capability name. | all 10 advisor tests | the module-level import |
| 5 | The advisor's outcome-proposing entry point. | a `propose` / `recommend`-shaped callable accepting an injected `graph=` or `model=`. | `::test_a_supported_choice_proposes_satisfaction`, `::test_an_unsupported_choice_proposes_no_satisfaction` | `_propose_entry()` / `_propose` |
| 6 | The pending-result repository's module, class and method names. | `AutomatedResultRepository` under `launch/infrastructure/driven/`, with `store` / `pending_for` / `undelivered` / `mark_delivered` / `settle` / `void` / `latest_rejection`. | both store tests; the `_FakeResults` doubles in two unit files | `_repository_class()` / `_store` / `_pending_for` / `_settle_as_rejected`; `_FakeResults` |
| 7 | The step-handler registry's read-back surface. | a `names()` or an iterable on `launch.application` or its `handler_registry` module. | `test_registered_handlers_activate_nothing.py` (all 3) | `_registered_names()` |

### Contract shape

| # | Question | Assumption taken | Depends on it | Correction point |
|---|---|---|---|---|
| 8 | **Is a handler awaited?** | Yes — the module is async throughout and the one handler this change writes makes a network call. | every handler double in `test_automation_pass.py` | `_ScriptedHandler.__call__` |
| 9 | How the pass learns the moment it runs as of. | injected as `now=`. Injecting it is what makes the cool-off observable without freezing a clock. | the cool-off and provenance tests | `_run_pass` |
| 10 | The advisor graph's input and output state shape. | tries `{"product_name", "marketplace"}`, falls back to `omni_agent`'s `MessagesState` shape. | all graph-level advisor tests | `_invoke` / `_recommendation_of` |
| 11 | **How the advisor signals that it cannot support a node choice.** The spec fixes that it must; nothing fixes whether that is a sentinel token, a structured marker, or plain language. This is the single most likely correction in the advisor file. | a plain-language refusal in the model's response. | `::test_an_unsupported_choice_proposes_no_satisfaction` | `_UNSUPPORTED_ANSWER` |
| 12 | How a refused decision is *signalled* to its caller. The spec requires the decider be told; what the use case hands the Slack reply is unstated. | either a raised error or a returned value that reads as refused. | the six refusal tests in `test_automated_result_decisions.py` | `_says_refused` |
| 13 | The roster collaborator's read for resolving a Slack identity. | answered under `list_people` / `people` / `person` / `person_for_slack_identity` / `load` / a bare call. | the two authority tests | `_FakeRoster` |

**None of these questions changes what any test asserts.** Correcting one is
a fixture correction (`ai-toolkit:testing` failure state 3). What must survive
unweakened is what each test asserts: which handlers are invoked, what is
recorded, what is held, what is delivered, what is refused, and — for the
several requirements stated in the negative — what does *not* happen.

---

## Obsolete tests

**Search performed:** the dispatched test-path glob `tests/**/test_*.py`,
and nowhere else. No earlier `test-manifest.md` was supplied to this pass, so
no prior scenario-to-test mapping was available and none was sought.
Implementation source was not read.

**Requirements that could produce an obsolete entry:** the four MODIFIED
requirements. Three of them (`launch-clickup-sync`) *narrow* what the inward
ClickUp loop may record: a step that is `automated`, or non-`active`, or
hazard `prohibited-tactic`, must now record nothing on an observed task
transition. A test asserting a `clickup`-sourced recording for such a step
would be superseded. The fourth (`launch-playbook`) changes a justification
only; the seeded statuses it describes are unchanged, so nothing it says can
supersede a test.

**Result: no bearing test was found.** This is the "no such test exists"
answer rather than the "none was found by this search" answer, and here is
the evidence for that stronger claim:

1. Every ClickUp test file's `_step()` fixture defaults to `kind=HUMAN`,
   `status=ACTIVE`, `hazard=NONE` — the exact set the narrowed rule still
   projects. Verified in `test_clickup_sync_reconciliation.py:158–161`,
   `test_clickup_sync_retired_steps.py:133–136`,
   `test_clickup_sync_projection.py:174–177`,
   `test_clickup_projection_step_fields.py:178–181`,
   `test_clickup_webhook.py:164–167`.
2. The `automated` steps those files do construct are (a) `_hold(...)` gate
   fillers, which are **never mapped to a task** — grepping every
   `seed_task` / `_TaskMapping` construction for a `hold.` identifier
   returns nothing, so no inward transition can be observed for them — and
   (b) *outward*-projection subjects in
   `test_clickup_sync_projection.py::test_a_prohibited_tactic_step_is_never_projected`
   and `test_clickup_projection_step_fields.py` (around lines 1096–1122),
   which assert that automated and prohibited-tactic steps are **not**
   projected. Those agree with the revised requirement; they are not
   superseded by it.
3. Running the full `tests/unit tests/agents` tier after this pass leaves all
   901 pre-existing tests passing. That alone would not prove absence — a
   test encoding pre-change behaviour would still pass today and break only
   when task 4a.1 lands — which is why (1) and (2) are the actual evidence
   and this is only corroboration.

**Nothing in this list is to be deleted or rewritten.** There is nothing in
it. Should the implementer discover, while applying 4a.1–4a.3, that an
existing test does break, that test is a **candidate for human confirmation**
and not something to edit into agreement with the new code — report it
instead.

### One accuracy note, which is *not* an obsolete-test entry

`tests/unit/launch/infrastructure/driven/test_clickup_non_active_steps_leave_loop.py`'s
module docstring describes the requirement as keying on `status`, quoting
the pre-generalisation wording. After this change that description is stale,
though **every assertion in the file remains correct and still passes**. This
is recorded here so it is visible, deliberately **outside** the obsolete
list: the file's name and docstring are prose, no assertion is superseded,
and treating it as obsolete would invite a destructive edit that the
requirement does not call for. Whether to refresh the prose is the
implementer's call, not this pass's.

---

## What the implementation step must make pass

Running, in order:

```
uv run pytest tests/unit tests/agents
uv run pytest tests/integration            # needs a live database
uv run ruff check && uv run ruff format --check
uv run mypy .
uv run lint-imports --config .importlinter
```

- **71 tests currently failing on an absent target** (54 of them not even
  collected) become executable only once `StepContext`/`StepResolution`
  (task 2.1), `automation_pass.py` (4.1), `automation_confirmation.py`
  (6.1), the decision use cases (3.3–3.7) and
  `commerce_ops.subcategory_advisor` (7.1) exist. Until then their
  assertions have **not** been exercised — reaching import is the first
  milestone, not the last.
- **5 tests currently failing on a wrong value** are the ones to fix first,
  because they are already discriminating: tasks 4a.1–4a.4. They fail today
  against the real `reconcile_launch` and the real webhook route, and they
  are the direct executable form of the finding that drove the
  `launch-clickup-sync` delta. `tasks.md` 9.2 must not be performed on a
  deployment where these are still red.
- **5 integration tests have never run.** Configure a database before
  claiming task 8.2, or they will report as skipped and be read as green —
  the failure mode `pyproject.toml`'s own `-rs` comment records.
- **The pre-commit `pytest (unit + agents)` hook is blocked** until the four
  absent modules exist, because collection errors abort the run. Expect to
  create the modules early, not last.
- **`tasks.md` 8.6a has no test in this pass** and needs one added to
  `tests/unit/test_registrations_across_processes.py`, which this pass could
  not edit.
