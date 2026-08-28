# Test manifest — `advance-gates-and-confirm-in-slack`

Tests derived from `specs/launch-gate-progression/spec.md`, before any
implementation code was written (`tasks.md` 1.1; `AGENTS.md` — *Test design
before implementation*).

**This file is not an artifact the OpenSpec schema defines.** It will not
appear among the context files `openspec instructions apply` surfaces, so
whoever implements this change has to read it on purpose.

Nothing outside `tests/**/test_*.py` was written except this file. No
existing test was edited, deleted or disabled. **This pass adds tests and
never subtracts.**

---

## Baseline

Taken at the worktree root `/home/shatynska/projects/commerce-ops-gate-progression`,
commit `656f1c4`, clean tree, before any test below was written:

| Run | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1472 passed, 0 failed |
| `uv run pytest tests/integration` | 3 passed, 112 skipped |

Every integration skip is the tier's own database gate: no `DATABASE_URL`
is set here and neither `.env.test` nor `.env` carries one, so **the
integration tier did not in fact run on this machine**. That is recorded
here rather than glossed: the four integration tests below have never been
executed, and their state is unverified rather than failing.

## After this pass

| Run | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 49 failed, 1473 passed |
| `uv run pytest tests/integration` | 3 passed, 116 skipped |
| `uv run ruff check .` | clean |
| `uv run ruff format --check .` | clean |
| `uv run mypy .` | clean, 364 files |

The 49 failures are all new and all in the **absent-target** state — the
second of `ai-toolkit:testing`'s four failure states. Each fails on a
loud, named probe (`gate_progression_job.py` does not exist;
`commerce_ops.launch.application` exports no cascade use case), never on a
wrong value, so **their assertions have not been exercised**. A test here
that starts passing before its target exists is a defect in that test.

The 1473rd pass is the one new test expected to pass — see *Expected first-run
state*, below. No pre-existing test changed state: 1472 → 1472 + 1.

---

## Expected first-run state, per file

| File | Tests | Expected |
| --- | --- | --- |
| `tests/unit/launch/application/test_progress_launch.py` | 9 | FAIL — absent target (`progress_launch`) |
| `tests/unit/launch/application/test_recording_does_not_advance_a_launch.py` | 1 | **PASS** — a regression guard on behaviour this change must preserve |
| `tests/unit/launch/application/test_gate_decision.py` | 15 | FAIL — absent target (the gate-decision use case) |
| `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py` | 10 | FAIL — absent target (`gate_progression_job.py`) |
| `tests/unit/launch/infrastructure/driving/test_gate_progression_containment.py` | 3 | FAIL — absent target (same) |
| `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py` | 4 | FAIL — absent target (`gate_confirmation.py`) |
| `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py` | 8 | FAIL — absent target (same) |
| `tests/integration/launch/test_gate_progression_stand_down_live.py` | 1 | SKIP here; FAIL on absent target where a database is configured |
| `tests/integration/launch/test_gate_progression_atomicity_live.py` | 3 | SKIP here; FAIL on absent target where a database is configured |

`test_recording_does_not_advance_a_launch.py` is deliberately its own
file. It must run *before* the implementation lands, and a module whose
import of `progress_launch` fails would never reach it — so a change that
folded advancement into a recording path would go uncaught for as long as
the cascade was missing.

---

## Scenario coverage

`specs/launch-gate-progression/spec.md` states **36** scenarios across
seven ADDED requirements. All 36 are accounted for below, each covered by
at least one named test. `grep -c '^#### Scenario:'` on the delta returns
36; the table has 36 rows.

### Requirement: A recurring pass advances every launch whose gate may open

| # | Scenario | Test |
| --- | --- | --- |
| 1 | An automatic gate opens once its conditions are satisfied | `tests/unit/launch/application/test_progress_launch.py::test_an_automatic_gate_opens_once_its_conditions_are_satisfied` |
| 2 | Consecutive open gates are crossed in one pass | `tests/unit/launch/application/test_progress_launch.py::test_consecutive_open_gates_are_crossed_in_one_pass` |
| 3 | A launch with an unsatisfied condition is left where it is, silently | `tests/unit/launch/application/test_progress_launch.py::test_a_launch_with_an_unsatisfied_condition_is_left_where_it_is` |
| 4 | Recording an outcome does not itself advance a launch | `tests/unit/launch/application/test_recording_does_not_advance_a_launch.py::test_recording_an_outcome_does_not_itself_advance_a_launch` |
| 5 | A launch is not advanced past the final gate | `tests/unit/launch/application/test_progress_launch.py::test_a_launch_is_not_advanced_past_the_final_gate` |

The requirement's clause that readiness "SHALL NOT be derived from the
launch report" carries no scenario of its own and is covered by
`test_progress_launch.py::test_a_gate_blocked_only_by_a_metric_condition_is_left_silently`
— the case the report cannot answer, and the gate `design.md` — Risks
predicts every launch will stall at.

### Requirement: The pass stands down while the playbook cannot hold a launch

| # | Scenario | Test |
| --- | --- | --- |
| 6 | An unready playbook stands the pass down without failing it | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_an_unready_playbook_stands_the_pass_down_without_failing_it` **and** `tests/integration/launch/test_gate_progression_stand_down_live.py::test_an_unready_stored_step_set_stands_the_pass_down` |
| 7 | A ready playbook is served normally | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_ready_playbook_is_served_normally` |

Both tiers are wanted for #6, per `tasks.md` 7.9: a substituted playbook
read cannot establish that the *serving* read refuses, and the state
cannot be produced by hand on a working deployment because
`playbook-authoring`'s ratchet forbids making a ready set unready. The
integration test demotes one gate's blocking steps and restores the exact
records in a `finally`, following
`tests/integration/launch/test_playbook_readiness_live.py`, and refuses to
run against a database whose name does not end in `_test`.

### Requirement: One launch's failure does not stop the other launches being advanced

| # | Scenario | Test |
| --- | --- | --- |
| 8 | A failing launch does not stop the others | `tests/unit/launch/infrastructure/driving/test_gate_progression_containment.py::test_a_failing_launch_does_not_stop_the_others` |
| 9 | A gate declining mid-cascade stops it without undoing what it crossed | `tests/unit/launch/application/test_progress_launch.py::test_a_gate_declining_mid_cascade_stops_it_without_undoing_the_crossing` |
| 10 | A cascade failing part-way leaves the launch where it started | `tests/unit/launch/application/test_progress_launch.py::test_a_cascade_failing_part_way_propagates_rather_than_committing` (the failure leaves the cascade rather than being committed) **and** `tests/integration/launch/test_gate_progression_atomicity_live.py::test_a_cascade_failing_part_way_leaves_the_launch_where_it_started` (the crossing is undone in Postgres) |
| 11 | A failed cascade does not discard the approval that triggered it | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_failed_cascade_does_not_discard_the_approval` |
| 12 | An unrestorable store ends the walk | `tests/unit/launch/infrastructure/driving/test_gate_progression_containment.py::test_an_unrestorable_store_ends_the_walk` |
| 13 | A shutdown stops the walk | `tests/unit/launch/infrastructure/driving/test_gate_progression_containment.py::test_a_shutdown_stops_the_walk` |

### Requirement: A gate awaiting only confirmation is asked about in Slack

| # | Scenario | Test |
| --- | --- | --- |
| 14 | A satisfied confirmation gate is asked about | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_satisfied_confirmation_gate_is_asked_about` (that one is posted) **and** `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py::test_the_ask_names_the_product_and_the_gate_and_carries_the_controls` (what it says and offers) |
| 15 | The final gate is not asked about | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_the_final_gate_is_not_asked_about` |
| 16 | A gate with unsatisfied conditions is not asked about | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_gate_with_unsatisfied_conditions_is_not_asked_about` |
| 17 | An undelivered ask is reported, retried, and does not fail the run | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_an_undelivered_ask_is_reported_retried_and_does_not_fail_the_run` (driven over two runs) **and** `tests/unit/launch/infrastructure/driving/test_gate_ask_message.py::test_a_delivery_failure_reaches_the_caller` (the adapter does not swallow the failure) |

#15 hands the pass a launch standing at the final gate deliberately,
rather than filtering it out, because the delta states the exclusion "so
that it is a property of the capability and not of a collaborator's
filtering" (`tasks.md` 5.8). #15 and #16 each carry a control launch that
*is* asked about on the same run, so neither negative is vacuous.

### Requirement: A gate is asked about at most once a day

| # | Scenario | Test |
| --- | --- | --- |
| 18 | A gate asked about is not asked about again on the next pass | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_gate_asked_about_is_not_asked_about_again_on_the_next_pass` |
| 19 | An unanswered gate is asked about again the next day | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_an_unanswered_gate_is_asked_about_again_the_next_day` |
| 20 | A rejection and its cool-off refresh land together or not at all | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_rejection_and_its_cool_off_refresh_land_together_or_not_at_all` **and** `tests/integration/launch/test_gate_progression_atomicity_live.py::test_a_rejection_and_its_cool_off_refresh_land_together_or_not_at_all` |
| 21 | A rejected gate is not re-proposed the same day | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_rejected_gate_is_not_re_proposed_the_same_day` |
| 22 | A restart does not resume asking | `tests/unit/launch/infrastructure/driving/test_gate_progression_pass.py::test_a_restart_does_not_resume_asking` |

The requirement's clause that a rejection refreshes the record is covered
by `tests/unit/launch/application/test_gate_decision.py::test_a_rejecting_decision_refreshes_the_cool_off`.
#22 models the restart by reloading the pass's module between runs, which
discards module-level state while leaving the store untouched — a pass
memoising its asks in a global passes #18 and fails #22.

### Requirement: Only a known, active person may approve a gate

| # | Scenario | Test |
| --- | --- | --- |
| 23 | An unknown identity cannot approve | `tests/unit/launch/application/test_gate_decision.py::test_an_unknown_identity_cannot_approve` (both verdicts) |
| 24 | A deactivated person cannot approve, and is told which fact refused them | `tests/unit/launch/application/test_gate_decision.py::test_a_deactivated_person_cannot_approve_and_is_told_which_fact` (both verdicts) |
| 25 | A non-administrator may approve | `tests/unit/launch/application/test_gate_decision.py::test_a_non_administrator_may_approve` |
| 26 | An absent roster collaborator is refused the same way, not silently | `tests/unit/launch/application/test_gate_decision.py::test_an_absent_roster_collaborator_is_refused_the_same_way` |
| 27 | An unreadable roster collaborator is refused by name | `tests/unit/launch/application/test_gate_decision.py::test_an_unreadable_roster_collaborator_is_refused_by_name` (the named error) **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_wiring_fault_answers_the_decider_without_blaming_them` (the decider is told, and operators see the fault) |

The requirement's clause that the wiring refusal is "raised before the
deciding identity is judged" is covered by
`tests/unit/launch/application/test_gate_decision.py::test_a_wiring_fault_does_not_displace_a_refusal_it_had_already_earned`.

### Requirement: A decision records the approval and reports what it did

| # | Scenario | Test |
| --- | --- | --- |
| 28 | An approving decision opens the gate and says so | `tests/unit/launch/application/test_gate_decision.py::test_an_approving_decision_records_an_approving_approval` (the recording) **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_an_approving_decision_replies_that_the_gate_opened` (the opening and the reply) |
| 29 | A rejecting decision keeps the gate closed | `tests/unit/launch/application/test_gate_decision.py::test_a_rejecting_decision_keeps_the_gate_closed` **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_rejecting_decision_replies_that_the_gate_stays_closed` |
| 30 | A decision whose gate the pass crossed first still reports it opened | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_whose_gate_the_pass_crossed_first_still_reports_it_opened` |
| 31 | A decision arriving during a stand-down is refused | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_arriving_during_a_stand_down_is_refused` |
| 32 | A decision on a condition that has since regressed reports why | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_on_a_regressed_condition_is_recorded_and_opens_nothing` (the approval stands, the gate does not open) **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_on_a_regressed_condition_names_what_blocks_it` (the reply names the condition) |
| 33 | A decision naming the final gate is refused | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_naming_the_final_gate_is_refused` |
| 34 | A decision is acknowledged before its work completes | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_is_acknowledged_before_its_work_completes` |
| 35 | A decision on a gate the launch has left is refused | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_on_a_gate_the_launch_has_left_is_refused` |
| 36 | A decision and the pass do not cross the same gate twice | `tests/integration/launch/test_gate_progression_atomicity_live.py::test_a_decision_and_the_pass_do_not_cross_the_same_gate_twice` |

**#36 has no unit-tier coverage, and that is deliberate.** "One at a time"
is a claim about two callers in different processes (the worker and the
HTTP process, `tasks.md` 6.1–6.2), and the only thing in this design that
excludes them is a Postgres advisory lock, which holds nothing without
Postgres. It is therefore covered only where a database is configured —
see *Conditional coverage gaps*.

---

## Assertion classification

Every assertion in the nine files is labelled in place, beside the
assertion, as `SPECIFIED` or `DERIVED`. The derived ones, in full:

| Assertion | File | Why it is derived |
| --- | --- | --- |
| The run's aggregate error does **not** name a launch that succeeded | `test_gate_progression_containment.py::test_a_failing_launch_does_not_stop_the_others` | The delta says the error names every launch that failed; naming one that did not is not forbidden by any scenario, but would make the aggregate useless for the diagnosis it exists for |
| The cascade treats an absent launch record as a no-op | `test_progress_launch.py::test_an_absent_launch_record_is_a_no_op` | Fixed by `tasks.md` 3.2; no scenario states it |
| The cascade reports back whether the launch is awaiting confirmation, and on which gate | `test_progress_launch.py::test_a_gate_awaiting_only_confirmation_is_reported_back` | Fixed by `tasks.md` 3.5; the delta fixes *when* an ask is owed, not how the pass learns it. The same test's "no command, no journal entry" half is SPECIFIED by R1 |
| The ask's controls carry `{product_id, gate_id}` | `test_gate_ask_message.py::test_the_ask_carries_the_product_and_gate_in_its_control_value` | Fixed by `tasks.md` 5.1 and `design.md` — Decision 9; the delta states what the message names, not what its controls carry |
| The ask goes to the monitoring channel | `test_gate_ask_message.py::test_the_ask_goes_to_the_monitoring_channel` | The delta says explicitly that the channel "is configuration and not a property of this requirement". Asserted anyway because the change commits to adding no runtime variable |
| A press whose cascade failed still answers the decider | `test_gate_decision_wiring.py::test_a_failed_cascade_does_not_discard_the_approval` | `tasks.md` 5.7 states it for the *wiring* fault; no scenario states it for a failed cascade |

Everything else traces to a scenario or to a requirement's own statement,
and the statement is quoted in the test's docstring where it is not a
scenario.

### Deliberately untested, recorded rather than omitted

Each file ends with its own list. Collected:

- The schedule and tolerance the pass declares (`tasks.md` 4.1, 6.3), and
  the listeners' registration in the HTTP process rather than the worker
  (`tasks.md` 5.2, 6.2). Both are `scheduled-jobs`' and the composition
  root's obligations, with no scenario in this delta.
- That the cascade terminates without a counter. A property of the gate
  sequence, which `launch-instance` already fixes.
- That the containment catch is literally `except Exception`. Decided by
  `tasks.md` 4.5; the tests provoke a `RuntimeError` and a
  `CancelledError` between them, which is what the distinction turns on.
- Whether the store restore runs after *every* contained failure or only
  after a store fault. No scenario states it.
- The order the walk visits launches in; no requirement states one.
- Any reply's or message's wording beyond the facts a scenario names.
- That the lock is transaction-scoped rather than session-scoped
  (`design.md` — Decision 6). A mechanism choice, not a stated behaviour.
- Which of two concurrent paths wins (#36 states only that one does).
- Both windows `design.md` — Decision 11 records as **accepted rather than
  closed**: a second press recording a duplicate approval, and a recording
  path writing back a stale `current_gate`. There is no rule to assert.
- That the first pass against a real deployment asks about every ready
  launch at once (`design.md` — Risks; `tasks.md` 7.5). Accepted with no
  cap stated.

### Conditional coverage gaps

Four tests are in `tests/integration/`, which runs at `pre-push` and skips
where no database is configured. On this machine none is, so **they have
never been executed**:

- `test_gate_progression_stand_down_live.py` additionally requires an
  *isolated* database (one whose name ends `_test`), because it rewrites
  the shared step set. Without one it skips with instructions.
- `test_gate_progression_atomicity_live.py` needs only the tier's own
  database.

Scenario **#36** is covered by nothing else, so a run of this change's
verification that skips the integration tier leaves it unverified. That is
what `AGENTS.md` sets `COMMERCE_OPS_REQUIRE_DATABASE` for in CI, and it is
worth checking against `tasks.md` 7.2 before the change is called done.

---

## Obsolete tests

**Not applicable, and stated rather than left empty.** The change's delta
contains only `ADDED` requirements for a single new capability,
`launch-gate-progression`; it carries no `MODIFIED`, `REMOVED` or
`RENAMED` delta, and `proposal.md` — *Modified Capabilities* records
explicitly that it changes no requirement of `launch-instance`,
`launch-journal` or `briefing`. Nothing existing is superseded, so no
existing test can be.

An empty list would read as "the search found nothing"; this is the other
thing — there was nothing for a search to find.

---

## Unresolved project questions

Every one of these is an **invented** contract: the delta and the change's
artifacts fix the behaviour but not the spelling. Each is reached through
a single named correction point that fails **loudly** rather than
defaulting, so no test can pass against something that is not the subject.
Correcting one is a fixture correction (failure state 3 in
`ai-toolkit:testing`) — **correct the probe, never the assertion**.

| Question | Assumption taken | Correction point | Tests depending on it |
| --- | --- | --- | --- |
| The cascade's exported name | one of `progress_launch`, `progress`, `advance_launch` | `_use_case()` in `test_progress_launch.py` | all 9 in that file |
| The cascade's call shape | collaborators as keyword arguments, mirroring `advance_gate(launches=, playbooks=, stamp_steady_state=, product_id=, journal=)`; `product_id` and a playbook argument asserted present | `_progress()` in `test_progress_launch.py` | all 9 |
| What the cascade returns to say a gate awaits confirmation | any of several attribute spellings | `_awaiting()` in `test_progress_launch.py`; `_Progressed` in `test_gate_progression_pass.py` | 1 + the four ask tests |
| How a mid-cascade race is provoked | substituting the module-level `advance_gate` the cascade calls, found via `progress_launch.__module__` | `_install_advance()` / `_ScriptedAdvance` in `test_progress_launch.py`; `_cascade_module()` in the atomicity file | 2 unit + 1 integration |
| The pass's entry-point name | one of `run_gate_progression_pass`, `run_gate_progression`, `advance_launch_gates`, `progress_gates`, `run_pass` | `_entry()` in `test_gate_progression_pass.py` | 14 unit + 4 integration |
| How the pass's collaborators are reachable | as module attributes **or** as parameters; each placed under whichever spelling the module carries, and `require()` fails loudly where neither exists | the `_*_NAMES` tuples and `_Harness` in `test_gate_progression_pass.py` | same |
| The suppression store's read/write method names and the row's attributes | several spellings over one keyed dict; `(product_id, gate_id)` asserted to be named on every call | `_FakeSuppression` in `test_gate_progression_pass.py` | the five cool-off tests |
| That the store restore is observable as `rollback()` on the shared session | `tasks.md` 4.6 names `clickup_sync_job.py`'s `_restore_after_store_fault` as the shape | `_FakeSession` + the guard in `test_an_unrestorable_store_ends_the_walk` | 1 |
| The ask adapter's entry point, call shape and Slack poster | probed; the poster substituted at `raising=True` so a differently named one fails loudly rather than posting for real | `_ask_callable()`, `_post_ask()`, `_install_poster()` in `test_gate_ask_message.py` | all 4 |
| The gate-decision use case's name and call shape | an approve/reject pair, else a single decide-with-a-verdict; `roster`/`read_people` and `gate_id` asserted present | `_decide()` in `test_gate_decision.py` | all 15 |
| Which form of the roster person is written into `GateApproval.approver` | either the identifier or the display name | `_names_the_person()` in `test_gate_decision.py` | 2 |
| The wording by which a refusal blames the identity, or names inactivity | marker tuples; the unknown-identity test establishes that `_BLAMES_UNKNOWN` matches a genuine refusal, so the negative assertions cannot pass vacuously | `_BLAMES_UNKNOWN`, `_BLAMES_INACTIVE` in `test_gate_decision.py`; `_BLAMES_THE_IDENTITY` in `test_gate_decision_wiring.py` | 5 |
| The decision listener's entry point and Bolt call shape | a pool of plausible Bolt arguments filtered by the implemented signature | `_ENTRY_NAMES`, `_press()` in `test_gate_decision_wiring.py` | all 8 |
| The seam the decision adapter opens its transaction through | `transaction` or `session`, substituted with a provider that **models** a transaction (snapshot on entry, restore on a raising exit) | `_place_transaction()` in `test_gate_decision_wiring.py` | 1, decisively |
| The reply wordings for "opened", "stays closed", "not processed" | marker tuples, each paired with a positive test in the same file that establishes the set matches something | `_SAYS_OPENED`, `_SAYS_CLOSED`, `_SAYS_NOT_PROCESSED` | 6 |
| That the ask is delivered through a substitutable module-level collaborator, rather than the pass composing the message itself | assumed, following `automation_pass` + `automation_confirmation` | the `_ASK_NAMES` tuples | the ask and cool-off tests |

Two further notes, which are project questions rather than naming ones:

- **No skill in `ai-toolkit` covers this stack's testing beyond `python`.**
  `ai-toolkit:testing` and `ai-toolkit:python` were both loaded; there is
  no `pytest`- or `slack-bolt`-specific asset beyond them. The floor plus
  this repository's own strong conventions is what these tests were
  written against, and the conventions won wherever they differed.
- **The pre-commit hook runs the whole `tests/unit` + `tests/agents` tree
  and blocks a commit on any red test.** These 49 failures are the
  expected pre-implementation state, so committing them will need
  `--no-verify` or committing them together with the implementation. That
  is a workflow decision for whoever implements, not something this pass
  resolved.

---

## What the implementation must make pass, by task

| `tasks.md` | Tests that must go from failing to passing |
| --- | --- |
| 2.1–2.3 (cool-off storage) | the five cool-off tests in `test_gate_progression_pass.py`, plus `test_gate_decision.py::test_a_rejecting_decision_refreshes_the_cool_off` |
| 3.1–3.6 (the cascade) | all 9 in `test_progress_launch.py` |
| 3.7–3.11 (the decision use case) | all 15 in `test_gate_decision.py` |
| 4.1–4.9 (the scheduled pass) | all 10 in `test_gate_progression_pass.py`, all 3 in `test_gate_progression_containment.py`, and `test_gate_progression_stand_down_live.py` |
| 5.1 (the ask message) | all 4 in `test_gate_ask_message.py` |
| 5.2–5.8 (the decision adapter) | all 8 in `test_gate_decision_wiring.py` |
| 3.10 + 4.3 + 5.6 (the lock) + 5.5 (the rejecting transaction) | all 3 in `test_gate_progression_atomicity_live.py` |
| 6.1–6.4 (wiring) | no test of this change; `tasks.md` 7.1–7.3 and the existing `tests/unit/test_registrations_across_processes.py` are what hold them |

`tests/unit/launch/application/test_recording_does_not_advance_a_launch.py`
must **stay** passing throughout. It is the only guard on `design.md` —
Decision 1: advancement is a convergence pass, never a consequence of
recording.
