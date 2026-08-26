# Test manifest — `serve-only-a-ready-playbook`

Written before any implementation of this change existed, from the change's
delta specs alone. No implementation of the behaviour under test was read;
the pre-change state of a `MODIFIED` requirement was established by comparing
the delta against `openspec/specs/<capability>/spec.md`.

This file is **not** part of the OpenSpec schema. It does not appear among
`openspec instructions apply`'s context files and must be opened on purpose.
`rules/openspec-test-manifest.md` in the ai-toolkit library directs that it be
read before implementing; this line is the second, redundant pointer.

**This pass is additive only. It adds tests and never subtracts.** No existing
test file was edited, deleted or disabled. `tasks.md` 5.0 asks for two existing
modules to be *re-pointed*; they are recorded in the obsolete list below
instead, for a human to confirm.

---

## Baseline

Full, both tiers, taken before the first test was written:

| command | result |
|---|---|
| `uv run pytest tests/unit tests/agents` | 901 passed, 0 failed |
| `uv run pytest tests/integration` | 84 passed, 0 failed |

After this pass:

| command | result |
|---|---|
| `uv run pytest tests/unit tests/agents` | 916 passed, **35 failed** — every failure in a file this pass added; all 901 pre-existing tests still pass |
| `uv run pytest tests/integration` | 84 passed, 4 skipped — the 4 skips are this pass's new module, gated on an isolated test database (see Q-6) |
| `uv run ruff check tests/` | clean |
| `uv run ruff format --check` (new files) | clean |

The integration tier resolved `DATABASE_URL` to the local **`commerce_ops`**
database — there is no `.env.test` in this checkout. See Q-6.

### Failure states of the 35

Per `ai-toolkit:testing`'s four states:

- **State 2 (absent target)** — 10 tests, all reaching a probe for
  `PlaybookNotReadyError` or the briefing-owned condition before constructing
  anything. The assertions have *not* been exercised.
- **State 1 (wrong value over a rule this change inverts)** — 25 tests. They
  fail because `LaunchPlaybook.__post_init__` currently **raises** where they
  construct an unready fixture, or because `_accept` currently **refuses** a
  write these assert lands. That is exactly the inversion tasks 1.1 and 2.1
  perform. The class under test exists; the rule does not yet.
- **State 3 (broken test)** — two were found and repaired during this pass,
  both defects of mine: the startup-check tests were written `async` against an
  entry point that drives its own `asyncio.run`, and the ready-playbook Slack
  test asserted a version identifier over a substituted collaborator. Neither
  repair touched a specified assertion.
- **State 4 (passed on first run)** — none unaccounted for. 15 new tests pass
  today, and each is a deliberately non-discriminating control or a
  survives-the-change guard, listed as such below.

---

## Files added

| file | tier |
|---|---|
| `tests/unit/launch/domain/test_playbook_readiness.py` | unit |
| `tests/unit/launch/application/test_gate_holding_ratchet.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_clickup_webhook_stand_down.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_stand_down.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_slack_entry_unready_playbook.py` | unit |
| `tests/unit/briefing/infrastructure/driving/test_unavailable_launch_source.py` | unit |
| `tests/unit/test_worker_translates_unready_playbook.py` | unit |
| `tests/unit/test_check_step_handlers_reads_the_authored_set.py` | unit |
| `tests/integration/launch/test_playbook_readiness_live.py` | integration |

Every file is inside the dispatched test-path glob `tests/**/test_*.py`. The
only write outside it is this manifest.

---

## Scenario accounting

**68 `#### Scenario:` blocks across the five delta specs. 68 accounted for.**

Counts: `launch-playbook` 27, `playbook-authoring` 12, `launch-entry` 2,
`launch-clickup-sync` 18, `briefing` 9.

Test identifiers below are runner-selectable as written:
`uv run pytest "<file>::<test>"`.

### `launch-playbook`

#### MODIFIED — Every gate is held by at least one blocking step (3)

| scenario | covered by |
|---|---|
| No gate opens for free | `tests/unit/launch/domain/test_playbook_readiness.py::test_no_gate_opens_for_free_in_a_playbook_served_to_a_launch` |
| A set that leaves a gate unheld still loads | `tests/unit/launch/domain/test_playbook_readiness.py::test_a_set_that_leaves_a_gate_unheld_still_loads`, `…::test_a_set_leaving_several_gates_unheld_still_loads` |
| A set whose steps are all drafts loads | `tests/unit/launch/domain/test_playbook_readiness.py::test_a_set_whose_steps_are_all_drafts_loads`, `…::test_a_set_of_non_active_statuses_other_than_draft_also_loads` |

#### MODIFIED — An incoherent playbook is rejected against each step's status (14)

| scenario | covered by |
|---|---|
| Gate sequence deviates from the specification | **Uncovered here — rule unchanged.** Existing: `tests/unit/launch/domain/test_launch_playbook.py` |
| A gate's opening mode disagrees with the specification | **Uncovered here — rule unchanged.** Existing: `tests/unit/launch/domain/test_launch_playbook.py` |
| Duplicate step identifier | `tests/unit/launch/domain/test_playbook_readiness.py::test_every_other_coherence_rule_still_rejects[duplicate-identifier]` |
| Step references an unknown gate | `…::test_every_other_coherence_rule_still_rejects[unknown-gate]` |
| A step with no name is rejected by identifier | `…::test_every_other_coherence_rule_still_rejects[empty-name]` |
| A name spanning several lines is rejected | `…::test_every_other_coherence_rule_still_rejects[multi-line-name]` |
| A description spanning several lines is accepted | **Uncovered here — rule unchanged.** Existing: `tests/unit/launch/domain/test_playbook_coherence_by_status.py::test_a_description_spanning_several_lines_is_accepted` |
| Automation past draft without a brief | `…::test_every_other_coherence_rule_still_rejects[automation-past-draft-without-a-brief]` |
| A prohibited tactic cannot block a gate | `…::test_every_other_coherence_rule_still_rejects[prohibited-tactic-blocking]` |
| **A gate with no active blocking step is rejected** | Load half: `tests/unit/launch/domain/test_playbook_readiness.py::test_a_gate_with_no_active_blocking_step_is_not_rejected_at_load`. Serving-read half: `tests/integration/launch/test_playbook_readiness_live.py::test_a_launch_cannot_be_advanced_by_an_unready_playbook` |
| A malformed metric condition is rejected | **Uncovered here — rule unchanged.** Existing: `tests/unit/launch/domain/test_gate_conditions.py` |
| Multiple violations are reported together | `tests/unit/launch/domain/test_playbook_readiness.py::test_two_faults_in_a_not_ready_set_are_still_reported_together` |
| A malformed step is reported alongside a coherence violation | **Uncovered here — rule unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_playbook_repository_rows.py` |
| A coherent playbook loads | `tests/unit/launch/domain/test_playbook_readiness.py::test_a_coherent_but_unready_playbook_exposes_its_gates_and_steps` |

"Uncovered here — rule unchanged" means: this change alters neither the rule
nor the scenario body, an existing test already covers it, and re-covering it
would duplicate rather than constrain. Each named existing test is **not**
obsolete and must keep passing.

#### MODIFIED — A step declares a lifecycle status, and only active steps are served (3)

The requirement's *prose* is amended (the un-activation refusal becomes
conditional on readiness); none of its three scenarios changes.

| scenario | covered by |
|---|---|
| A draft step is authored but not served | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/domain/test_step_lifecycle_status.py` |
| Only active steps hold a gate | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/domain/test_step_lifecycle_status.py` |
| A retired step leaves the served set without leaving the record | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/domain/test_step_lifecycle_status.py`, `tests/integration/launch/test_playbook_authoring_live.py` |

The amended prose *is* covered, by the two ratchet scenarios under
`playbook-authoring` below, which state the same rule.

#### ADDED — A playbook that cannot hold a launch is not served (7)

| scenario | covered by |
|---|---|
| A launch cannot be advanced by an unready playbook | `tests/integration/launch/test_playbook_readiness_live.py::test_a_launch_cannot_be_advanced_by_an_unready_playbook` |
| Authoring reads an unready playbook freely | `tests/integration/launch/test_playbook_readiness_live.py::test_authoring_reads_an_unready_playbook_freely` |
| Readiness follows the set without ceremony | `tests/integration/launch/test_playbook_readiness_live.py::test_readiness_follows_the_set_without_ceremony` |
| A refusal carries the set it declined to serve | `tests/unit/launch/domain/test_playbook_readiness.py::test_a_refusal_carries_the_gates_and_the_set_it_declined_to_serve` |
| The carried set may be classified but not acted on | `tests/unit/launch/domain/test_playbook_readiness.py::test_the_carried_set_may_be_classified_but_not_acted_on` (first clause); second clause deliberately untested — see A-3 |
| Not ready is distinguishable from incoherent | `tests/unit/launch/domain/test_playbook_readiness.py::test_not_ready_is_distinguishable_from_incoherent`; also asserted at the read in `tests/integration/launch/test_playbook_readiness_live.py::test_a_launch_cannot_be_advanced_by_an_unready_playbook` |
| **An absent playbook is still an error** | **UNCOVERED.** See U-1 |

The requirement's statement clauses that name no scenario are covered too:
readiness derived and never stored →
`tests/unit/launch/domain/test_playbook_readiness.py::test_the_unheld_read_follows_the_set_without_being_stored`;
"non-empty names exactly what is missing" / "empty means ready" →
`…::test_the_unheld_read_names_exactly_the_gates_with_no_active_blocker`,
`…::test_the_unheld_read_is_empty_for_a_ready_set`.

### `playbook-authoring`

#### MODIFIED — Every write is validated as the playbook it would produce (7)

| scenario | covered by |
|---|---|
| A rejected write reports all faults and persists nothing | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_playbook_authoring.py::test_a_rejected_write_reports_all_faults_and_persists_nothing` |
| **Retiring a gate's last blocking step is rejected** (now qualified "in a set where every gate is currently held") | `tests/unit/launch/application/test_gate_holding_ratchet.py::test_retiring_a_gates_last_blocking_step_is_rejected_in_a_ready_set` |
| **A write against a set that is not ready may leave it unready** | `tests/unit/launch/application/test_gate_holding_ratchet.py::test_the_first_activation_against_an_all_draft_set_lands`, `…::test_no_fault_names_the_gates_an_accepted_unready_write_leaves_unheld` |
| An untouched unowned step does not block an unrelated write | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_step_assignee_preconditions.py` |
| Editing an unowned step requires giving it an owner | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_step_assignee_preconditions.py` |
| A roster change does not break an accepted set | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/domain/test_step_assignees_are_not_a_load_rule.py` |
| What a write cannot persist, a load cannot see | **Uncovered here — scenario unchanged.** Existing: `tests/integration/launch/test_playbook_authoring_live.py` |

Also covered from this requirement's statement, though it names no scenario:
the reachability claim → `…::test_climbing_from_all_draft_to_ready_one_activation_at_a_time`;
retiring permitted in a not-ready set → `…::test_retiring_a_gates_last_blocking_step_is_permitted_in_an_unready_set`.

#### MODIFIED — Activation is a validated transition (5)

| scenario | covered by |
|---|---|
| An activation that satisfies its kind's rules lands | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_step_activation.py::test_an_activation_that_satisfies_its_kinds_rules_lands` |
| A refused activation explains itself and persists nothing | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_step_activation.py` |
| Registering a handler does not activate anything | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/application/test_step_activation.py` |
| **Un-activating a gate's last blocking step is refused** (now qualified) | `tests/unit/launch/application/test_gate_holding_ratchet.py::test_un_activating_a_gates_last_blocking_step_is_refused_in_a_ready_set` |
| **Un-activating within a set that is not ready is permitted** | `tests/unit/launch/application/test_gate_holding_ratchet.py::test_un_activating_within_a_set_that_is_not_ready_is_permitted` |

### `launch-entry`

#### ADDED — A launch is not started against a playbook that cannot hold one (2)

| scenario | covered by |
|---|---|
| A start against an unready playbook is refused | `tests/unit/launch/infrastructure/driving/test_slack_entry_unready_playbook.py::test_a_start_against_an_unready_playbook_is_refused` |
| A start against a ready playbook is unaffected | `tests/unit/launch/infrastructure/driving/test_slack_entry_unready_playbook.py::test_a_start_against_a_ready_playbook_is_unaffected` |

The requirement's "SHALL NOT be reported as a malformed field" clause names no
scenario and is covered by
`…::test_the_refusal_is_not_reported_as_a_malformed_field`.

### `launch-clickup-sync`

#### MODIFIED — Each launch is projected into its own ClickUp list (4)

Only the requirement's *statement* gains a stand-down clause; all four
scenarios are unchanged.

| scenario | covered by |
|---|---|
| A launch without a list gets one | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py` |
| An existing list is not recreated | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py` |
| A graduated launch is left alone | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py` |
| Missing folder configuration fails the run | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py` |

The new clause ("a stand-down creates nothing and writes nothing, and is
recorded as a successful run") is covered by
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_stand_down.py::test_a_pass_stands_down_rather_than_failing`.

#### MODIFIED — Completion flows from ClickUp to the launch as a recorded outcome (5)

| scenario | covered by |
|---|---|
| A closed task records Satisfied | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py`. Re-established outside a stand-down as a control by `…test_clickup_webhook_stand_down.py::test_a_ready_playbook_leaves_intake_recording_exactly_as_before` |
| A reopened task records InProgress | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py` |
| A reopening without an observed closing records nothing | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py` |
| A repeated delivery changes nothing | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driving/test_clickup_webhook.py` |
| The system never closes a task | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py` |

The new clause ("intake during a stand-down records no outcome whatever the
task's status") is covered by the two stand-down tests below.

#### MODIFIED — The reconciliation pass records completions and reopenings the webhook missed (4)

| scenario | covered by |
|---|---|
| A missed completion is recorded on reconciliation | **Uncovered here — scenario unchanged.** Existing: `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py::test_a_missed_completion_is_recorded_on_reconciliation` |
| A missed reopening is recorded on reconciliation | **Uncovered here — scenario unchanged.** Existing: same file |
| No transition means no recording | **Uncovered here — scenario unchanged.** Existing: same file |
| Reconciliation never overwrites other recording paths | **Uncovered here — scenario unchanged.** Existing: same file |

The new clause ("a completion missed during a stand-down is recorded by the
first pass to run once the playbook is ready") is the second half of
`…test_clickup_webhook_stand_down.py::test_a_served_steps_completion_arriving_during_a_stand_down_is_not_lost`.

#### ADDED — Projection and intake stand down while the playbook cannot hold a launch (5)

| scenario | covered by |
|---|---|
| A pass stands down rather than failing | `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_stand_down.py::test_a_pass_stands_down_rather_than_failing` |
| A served step's task is not observed during a stand-down | `tests/unit/launch/infrastructure/driving/test_clickup_webhook_stand_down.py::test_a_served_steps_task_is_not_observed_during_a_stand_down` |
| A served step's completion arriving during a stand-down is not lost | `tests/unit/launch/infrastructure/driving/test_clickup_webhook_stand_down.py::test_a_served_steps_completion_arriving_during_a_stand_down_is_not_lost` — **one test, spanning the whole sequence**, as the scenario's `WHEN … AND … THEN` requires |
| A non-served step's closure during a stand-down is still consumed | `tests/unit/launch/infrastructure/driving/test_clickup_webhook_stand_down.py::test_a_non_served_steps_closure_during_a_stand_down_is_still_consumed` — including the scenario's second `AND`, by reconciling after the step returns to the served set |
| A ready playbook restores the passes | `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_stand_down.py::test_a_ready_playbook_restores_the_passes` (pass half) and `…test_clickup_webhook_stand_down.py::test_a_ready_playbook_leaves_intake_recording_exactly_as_before` (intake half) |

The served/non-served pair is written over the **same delivery shape and the
same stand-down**, differing only in which step the carried playbook serves, so
an implementation applying one treatment to both fails exactly one of them.
The requirement says in as many words that the two "SHALL NOT be collapsed".

### `briefing`

#### MODIFIED — A failure to assemble is surfaced, not treated like a delivery failure (4)

| scenario | covered by |
|---|---|
| A read failure on the final attempt fails the run and says so | **Uncovered here — scenario unchanged.** Existing: `tests/unit/briefing/infrastructure/driving/test_daily_briefing_job.py::test_a_read_failure_on_the_final_attempt_fails_the_run_and_says_so` |
| An intermediate failed attempt does not post | **Uncovered here — scenario unchanged.** Existing: same file |
| An assembly failure is retried | **Uncovered here — scenario unchanged.** Existing: same file |
| **A source that cannot supply reports is not a read failure** | `tests/unit/briefing/infrastructure/driving/test_unavailable_launch_source.py::test_an_unavailable_launch_source_is_not_an_assembly_failure` |

#### ADDED — A launch source that cannot supply reports is reported, not treated as a clean day (5)

| scenario | covered by |
|---|---|
| A failure to post the message does not fail the run | `tests/unit/briefing/infrastructure/driving/test_unavailable_launch_source.py::test_a_failure_to_post_the_message_does_not_fail_the_run` |
| An unavailable launch source posts a message rather than nothing | `…::test_an_unavailable_launch_source_posts_a_message_rather_than_nothing` |
| An unavailable launch source is not a clean day | `…::test_an_unavailable_launch_source_is_not_a_clean_day` |
| An unavailable launch source is not an assembly failure | `…::test_an_unavailable_launch_source_is_not_an_assembly_failure` |
| The condition is reported on each run while it persists | `…::test_the_condition_is_reported_on_each_run_while_it_persists` |

The requirement's statement clause — "Whatever satisfies that source is
responsible for translating its own module's condition into this one" — names
no scenario and is covered in
`tests/unit/test_worker_translates_unready_playbook.py`, which is the only
place the translation is observable (`tasks.md` 5.13).

---

## Uncovered scenarios

**U-1 — `launch-playbook` / *An absent playbook is still an error*.**
Uncovered, deliberately. Producing "no step set exists at all" requires
destroying the live seeded step set, and no isolated test database is
configured in this checkout (Q-6) — a test that deleted it would be a real
hazard to the developer's working database, not a test. The change makes no
edit to that path: `tasks.md` 3.2 states it as a *confirmation* ("confirm the
absent-playbook failure is unchanged"), not a change. The negative half of the
scenario — that the absent-playbook failure is **not** `PlaybookNotReadyError`
— is covered by
`tests/unit/launch/domain/test_playbook_readiness.py::test_not_ready_is_distinguishable_from_incoherent`
plus the `isinstance` assertion in
`tests/integration/launch/test_playbook_readiness_live.py::test_a_launch_cannot_be_advanced_by_an_unready_playbook`.
**Once `commerce_ops_test` exists, this becomes cheaply coverable** — drop the
`playbook_step_set` row in a test transaction and assert the absence error —
and it should be added then.

No other scenario is uncovered. Every "Uncovered here — rule unchanged" row
above names an existing test that covers it and must keep passing; those are
accounted for, not omitted.

---

## Assertion provenance

Every assertion in the new files is annotated in place as SPECIFIED, DERIVED
or DELIBERATELY UNTESTED. The DERIVED and DELIBERATELY UNTESTED ones, gathered:

### DERIVED (inferred; no `#### Scenario:` states them)

| id | assertion | source it was derived from | test |
|---|---|---|---|
| D-1 | The unheld-gate read answers in **gate-sequence order** | `tasks.md` 1.2 | `test_playbook_readiness.py::test_the_unheld_read_is_in_gate_sequence_order` |
| D-2 | The gate-holding fault keeps the substring `has no active blocking step attached` | `tasks.md` 2.1 (`playbook_admin._CROSSINGS` matches it) | `test_gate_holding_ratchet.py::test_retiring_a_gates_last_blocking_step_is_rejected_in_a_ready_set` |
| D-3 | An all-draft set can be climbed to ready one activation at a time, and the ratchet then closes behind it | the requirement's reason clause + `design.md`'s three-line table | `test_gate_holding_ratchet.py::test_climbing_from_all_draft_to_ready_one_activation_at_a_time` |
| D-4 | A **reorder** of an unowned `active` `human` step still lands | `tasks.md` 2.2 / 5.5 | `test_gate_holding_ratchet.py::test_a_reorder_of_an_unowned_active_human_step_still_lands` |
| D-5 | A delivery for a step absent from the **authored** set still advances the retained state | `tasks.md` 4.3 / 5.11 — a guard on the membership check's position | `test_clickup_webhook_stand_down.py::test_a_delivery_for_a_step_outside_the_authored_set_still_advances_the_row` |
| D-6 | "Acknowledged" reads as a 2xx | the reading `test_clickup_webhook.py` already recorded | every stand-down webhook test |
| D-7 | "Recorded as succeeded / failed" reads as the job body returning / raising | the reading `test_daily_briefing_job.py` already recorded | the sync-job and briefing-job tests |
| D-8 | The briefing job posts nothing on an ordinary run | control against a job that always posts | `test_unavailable_launch_source.py::test_a_successful_run_still_leaves_the_condition_path_unreached` |
| D-9 | The startup handler check takes `load()` and **not** `get()` | `tasks.md` 4.7 / `design.md`'s "leaves the serving-read caller set at four" | `test_check_step_handlers_reads_the_authored_set.py::test_the_startup_check_takes_the_authoring_read_not_the_serving_one` |
| D-10 | The condition `briefing` receives is not a `launch.domain` type even by subclassing | `design.md`'s boundary claim | `test_worker_translates_unready_playbook.py::test_the_launch_domain_exception_does_not_escape` |
| D-11 | "Nothing is persisted" at the Slack route reads as *the persisting collaborators were never called* | the division `test_slack_entry_ack_and_failure_visibility.py` records | `test_slack_entry_unready_playbook.py::test_a_start_against_an_unready_playbook_is_refused` |

Each is stated as its own test or its own assertion with the label beside it,
so a deliberate change to any one of them fails visibly rather than inside a
specified assertion.

### DELIBERATELY UNTESTED

| id | case | reason |
|---|---|---|
| A-1 | The wording of the briefing's unavailable-source message, beyond that it names the carried identifiers | No artifact pins a phrasing; asserting one would impose a contract nobody agreed to. Same reading `test_daily_briefing_job.py` recorded for the assembly-failure message. |
| A-2 | The wording of the Slack refusal message, beyond that it names the unheld gates | Same reason. |
| A-3 | *The carried set may be classified but not acted on* — the **second** clause ("may not use it to advance, project or report on a launch") | It is an obligation on each consumer, not a capability the aggregate withholds: the spec is explicit that the set is coherent and there is nothing unsafe about returning it. Established per consumer instead — the webhook records nothing while holding it (`test_a_served_steps_task_is_not_observed_during_a_stand_down`) — and by review of the four call sites `design.md` enumerates. |
| A-4 | The Slack route recording the served playbook's **version identifier** | `start_launch`'s own doing, over a collaborator this file substitutes; asserting it here would assert the double. Covered against real persistence in `tests/integration/launch/test_slack_entry_start.py`, which reads `playbook_step_set.version` back. |
| A-5 | That `briefing` names nothing from `launch` at all | A source-structure property, not a behaviour. `design.md` says so explicitly and assigns it to `lint-imports` (for the two forbidden edges) plus review (for the convention the linter does not encode). `tasks.md` 6.4. |
| A-6 | The sync job's schedule and tolerance | Unchanged by this change; already covered in `test_clickup_sync_job_schedule.py`. |

---

## Unresolved project questions

Raised while deriving these tests; **none is silently resolved**. Each records
the assumption taken and which tests depend on it. There is no channel to ask
on from a dispatched subagent, so they are recorded here and surfaced in the
report instead.

**Q-1 — What is `PlaybookNotReadyError`'s constructor signature, and under
what attribute names does it carry the gates and the playbook?**
`tasks.md` 1.3 fixes *that* it carries both, not *how*.
*Assumption taken:* four candidate signatures are probed in order —
`(playbook=, gates=)`, `(playbook=, unheld_gates=)`, `(gates, playbook)`,
`(playbook, gates)` — and the first that constructs is used; a probe that
exhausts them fails loudly with a message naming the correction point.
Carried gates are read from `gates` / `unheld_gates` / `unheld` /
`identifiers`; the playbook by `isinstance`.
*Depends on it:* every test in `test_playbook_readiness.py`,
`test_clickup_webhook_stand_down.py`, `test_clickup_sync_job_stand_down.py`,
`test_slack_entry_unready_playbook.py`,
`test_worker_translates_unready_playbook.py`,
`test_check_step_handlers_reads_the_authored_set.py`,
`test_playbook_readiness_live.py`.
*Correction point:* `_build_not_ready` / `_carried_gates` / `_carried_playbook`
in each file.

**Q-2 — What is the unheld-gate read called on `LaunchPlaybook`, and is there
a separate readiness predicate?**
`tasks.md` 1.2 fixes the obligation, not the spelling.
*Assumption taken:* `_UNHELD_READS` probes `unheld_gates`,
`gates_without_active_blocking_step`, `unheld_gate_identifiers`,
`gates_holding_no_active_blocking_step`; `_READINESS_READS` probes `is_ready`,
`ready`, `is_servable`, `servable`. Where no predicate exists, readiness falls
back to the emptiness of the unheld read — which is what the requirement
defines readiness *as*, so this is not a weakening.
*Depends on it:* `test_playbook_readiness.py`, all readiness assertions.
*Correction point:* `_UNHELD_READS` / `_READINESS_READS`.

**Q-3 — What is the briefing-owned condition called?**
`tasks.md` 4.4 fixes what it means and where it lives, not its spelling.
*Assumption taken:* `_CONDITION_NAMES` probes five plausible names on
`commerce_ops.briefing.application`, and its constructor is probed over
`identifiers=`, `reasons=`, a positional sequence, and a positional string.
*Depends on it:* every test in `test_unavailable_launch_source.py` and
`test_worker_translates_unready_playbook.py`.
*Correction point:* `_CONDITION_NAMES` / `_condition` in both files.

**Q-4 — What is `worker`'s launch-reports reader called, and what does its
signature take?**
`design.md` names `_read_launch_reports` at `worker.py:129`; the tests probe
`_read_launch_reports`, `read_launch_reports`, `_launch_reports`, and supply
whatever required parameters the resolved signature declares (`None`, or a date
/ `AccessScope.unrestricted()` for parameters named as such).
*Depends on it:* `test_worker_translates_unready_playbook.py`.
*Correction point:* `_READER_NAMES` / `_call_reader`.

**Q-5 — How does `clickup_sync_job` reach the launches it runs the pass
over?** No artifact fixes the collaborator's name.
*Assumption taken:* the double is installed over `LaunchRepository` with
`raising=False`, so where the job reaches them another way the double is
simply not installed — and the **ready-playbook** test is what surfaces it,
failing with a message that names the reason rather than passing vacuously.
*Depends on it:* `test_clickup_sync_job_stand_down.py::test_a_ready_playbook_restores_the_passes`
(which passes today, so the seam resolved on this run).
*Correction point:* `_FakeLaunches` and the `launches` fixture.

**Q-6 — No isolated test database is configured in this checkout, so the
integration tier writes into `commerce_ops`.**
`AGENTS.md` says an isolated database is optional; `tasks.md` 6.2 says the
change's own verification must use one. Reaching a *stored* set that leaves a
gate unheld requires writing the step set directly — the ratchet forbids
producing it through any accepted write — so
`tests/integration/launch/test_playbook_readiness_live.py` mutates and restores
the stored set.
*Assumption taken:* that module **skips**, loudly and with instructions, unless
`DATABASE_URL` names a database whose name ends `_test`. It skipped on this run
(4 skips). Its three scenarios are therefore **not covered on this machine as
configured** — a conditional coverage gap, recorded as such and not as
coverage.
*Depends on it:* all three ADDED-requirement read scenarios of
`launch-playbook` (see the accounting table), plus U-1.
*Action for the implementer:* create `commerce_ops_test`, run
`alembic upgrade head` against it, and name it as `DATABASE_URL` in
`.env.test` **before** running the integration tier for this change.

**Q-7 — Whether the retained-observed-state scenarios belong at the
integration tier.**
The dispatch suggested they might. The project's own tier rule
(`AGENTS.md`: `tests/integration` is "tests that touch real I/O") and
`ai-toolkit:testing`'s level rule both put them at unit tier: the behaviour
under test is the webhook route's **ordering** of the readiness check relative
to `mapping.observe(...)`, which is fully observable over the in-memory
mapping double that `test_clickup_webhook.py` already uses, and the repository's
own commit is covered separately in
`tests/integration/launch/test_launch_clickup_mapping.py`.
*Assumption taken:* unit tier, with the assertion made on the mapping **row**
(not on the response) as `tasks.md` 5.7 requires, and additionally on whether
`observe` was called at all — so an implementation that observes and then
restores still fails.
*Depends on it:* the three stand-down webhook tests.

---

## Obsolete tests

Every entry below is a **candidate for human confirmation**, never a
conclusion. Nothing here was edited, deleted or disabled by this pass.

The search was bounded to the dispatched test-path glob `tests/**/test_*.py`.
No earlier `test-manifest.md` was supplied for this change, so no
scenario-to-test mapping was available beyond the glob and the existing test
modules' own docstrings. Method: grep for the fault wording
(`no active blocking step`), for the gate-holding scenario titles, and for the
write-path phrases (`last blocking`, `only active blocking`, `left unheld`),
then read each hit in full.

### O-1 — `tests/unit/launch/domain/test_gate_holding_floor.py` (3 of its 4 tests)

**Superseded by:** `launch-playbook` MODIFIED *Every gate is held by at least
one blocking step* ("This floor is a property of the **served** set, not a
coherence rule. A step set that leaves a gate unheld SHALL load") and MODIFIED
*An incoherent playbook is rejected against each step's status* (scenario *A
gate with no active blocking step is rejected*, whose body now reads "the
rejection happens when that playbook is asked for in order to hold a launch …
and not when it is loaded").

**Evidence:** the module's own docstring states its subject as "The
gate-holding floor as a **construction rule** of `LaunchPlaybook`", and each of
the three tests asserts `pytest.raises(InvalidPlaybookError)` around a
constructor call:

| test | evidence |
|---|---|
| `test_a_gate_with_no_step_at_all_is_rejected_naming_the_gate` | `with pytest.raises(InvalidPlaybookError): _playbook(steps)` over a set leaving `ignition` unheld — the exact state the delta says "SHALL load" |
| `test_a_gate_with_only_non_blocking_steps_is_rejected` | same shape, over `live` |
| `test_the_floor_fault_is_reported_alongside_another_fault` | asserts the floor fault appears in the aggregated `InvalidPlaybookError`; after this change there is no floor fault at construction to aggregate |

**Not obsolete, in the same file:**
`test_a_playbook_with_every_gate_held_constructs` — it constructs a fully held
set and asserts the grouping, which the revised *No gate opens for free* still
requires. It must keep passing.

**Replaced by:** `tests/unit/launch/domain/test_playbook_readiness.py::test_a_gate_with_no_active_blocking_step_is_not_rejected_at_load`
(the load half) and
`tests/integration/launch/test_playbook_readiness_live.py::test_a_launch_cannot_be_advanced_by_an_unready_playbook`
(the serving-read half), plus
`…test_playbook_readiness.py::test_two_faults_in_a_not_ready_set_are_still_reported_together`
for the aggregation the third test was really about.

### O-2 — `tests/unit/launch/domain/test_playbook_coherence_by_status.py` (2 of its tests)

**Superseded by:** the same two MODIFIED requirements as O-1.

**Evidence:**

| test | evidence |
|---|---|
| `test_a_gate_whose_only_blocking_step_is_a_draft_is_rejected` | docstring names *Scenario: A gate with no active blocking step is rejected* and asserts `pytest.raises(InvalidPlaybookError)` over `_raw(steps)`. Its stated reason — "the floor exists to make that state **unreachable**" — is exactly what the delta reverses: the state is now reachable and merely unservable. |
| `test_a_gate_whose_only_blocking_step_is_in_development_is_rejected` | same shape, over `live` with an `in-development` blocker |

**Not obsolete, in the same file:** everything else, including
`test_no_gate_opens_for_free` — which uses the `_playbook(...)` helper that
back-fills every unheld gate, so it constructs a **ready** set and asserts the
grouping the revised scenario still states. The name rules, the aggregation
test and the coherent-load test are all untouched by this change.

**Caution for whoever confirms this entry:** the file's `_playbook(...)` helper
fills unheld gates precisely so the pre-change constructor would accept its
fixtures. After task 1.1 that back-filling is no longer *needed*, but removing
it would change what several unrelated tests in the file construct. Leave it.

**Replaced by:** the same two tests as O-1.

### No other bearing test was found

Searched, and **no such test exists** (as distinct from "none was found"):

- **The write-path gate-holding tests** —
  `test_playbook_authoring.py::test_retiring_a_gates_last_blocking_step_is_rejected`,
  `test_step_retirement_and_slots.py`'s retirement test, and
  `test_step_activation.py::test_un_activating_a_gates_last_blocking_step_is_refused`.
  Each builds its store from one `active` blocking step **per gate**, so every
  one of them starts from a **ready** set — which is precisely the half of the
  rule the ratchet preserves. They are not superseded and must keep passing.
- **`test_playbook_admin_fault_attribution.py`** (`_Provocation("a gate left
  with no active blocking step", …)`). It asserts the fault is attributed at
  page level rather than to a field. `tasks.md` 2.1 requires the fault's
  wording be kept for exactly this reason, and the provocation is an *edit*
  against the live (ready) set, so the ratchet still refuses it. Not
  superseded.
- **`test_seeded_step_fields.py:318`** (`assert holding, f"gate {gate} has no
  active blocking step"`). A statement about the **seeded** set, which
  `design.md`'s migration plan confirms stays ready. Not superseded.
- **The three `launch-clickup-sync` MODIFIED requirements' existing tests.**
  Each gains a clause conditioned on a stand-down; every existing test is
  stated outside one, so none asserts superseded behaviour.
- **The `briefing` assembly-failure tests.** The requirement gains a carve-out
  for a condition none of them exercises. Not superseded.
- **`test_daily_briefing_job.py::test_one_outage_produces_exactly_one_message`.**
  Worth flagging to the implementer even though it is **not** obsolete: the new
  requirement is its deliberate inverse for a *different* condition ("on
  **every** run while it persists"). Reusing the retry-exhaustion suppression
  hook for the new path would break
  `test_the_condition_is_reported_on_each_run_while_it_persists`; reusing the
  new path's non-suppression for assembly failures would break this one. Both
  must pass.
