# Test manifest — `advance-gates-from-clickup-webhook`

Written before any implementation, from the change's delta spec alone:
`openspec/changes/advance-gates-from-clickup-webhook/specs/launch-gate-progression/spec.md`,
read against the requirements it modifies in
`openspec/specs/launch-gate-progression/spec.md`.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and must be
opened on purpose by whoever implements the change next.

**This pass added tests and subtracted none.** No existing test was
edited, deleted, disabled or weakened, and no implementation source was
written or modified. Nothing outside `tests/**/test_*.py` was written
except this file.

**No implementation source was read.** What the two modules under test
already expose was established by importing them and reading `__all__` and
their module attributes, and by reading the existing tests that substitute
them — never by opening `clickup_webhook.py` or `gate_progression_job.py`.

## Baseline

Taken at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`
(worktree, branch `archive-shift-clickup-completions-to-webhook`), commit
`96303a7`, before any test below was written. A **full** baseline, not a
scoped one.

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1727 passed, 0 failed |
| `uv run pytest tests/integration` | 3 passed, 124 skipped — no `DATABASE_URL` is configured here, so that tier did not in fact run |

After this pass, with no implementation written:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1732 passed, 14 failed, 9 errors, 3 skipped |
| `uv run pytest tests/integration` | unchanged; the one new file skips for want of a database |
| `uv run ruff check` / `ruff format --check` / `mypy .` / `lint-imports` | clean on the new files |

Every one of the 23 new failures is in the two new files that probe for an
absent target, and no pre-existing test changed state. The 5 new passes are
the preserve-the-boundary guards, which are expected to pass before the
implementation and after.

## What each new file's first run establishes

Read against `ai-toolkit:testing`'s four failure states.

| File | Tests | First-run state |
| --- | --- | --- |
| `tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py` | 12 | 9 ERROR / 3 FAIL — **absent target** (`clickup_webhook` carries no trigger). Establishes absence only; no assertion in them has been exercised by the real code. |
| `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py` | 11 | 11 FAIL — **absent target** (`gate_progression_job` has no `advance_and_ask`). Same reading. |
| `tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py` | 8 | 5 PASS, 3 SKIP — a **regression guard** on behaviour the change must preserve, so passing first is the expected result and not the fourth-state alarm. The 3 skips are the alias guard, vacuous until the trigger exists. |
| `tests/integration/launch/test_webhook_advance_atomicity_live.py` | 1 | SKIP — **no baseline could be taken for this file at all**; see the disclosure below. |

### The integration file has never been executed

No `DATABASE_URL` is configured in this environment and neither `.env.test`
nor `.env` carries one, so
`tests/integration/launch/test_webhook_advance_atomicity_live.py` skipped
rather than running. It has been verified to import and collect, and
nothing more. A fixture defect in it and a satisfied requirement are
currently indistinguishable.

**Whoever implements this change must run it against a real database
before treating a green result from it as coverage.** Its helpers are
transcribed from `tests/integration/launch/test_gate_progression_atomicity_live.py`,
which does run there, so the likeliest correction points are the trigger's
name and call shape (`_TRIGGER_NAMES`, `_advance`) rather than the
transcribed harness.

## Scenario coverage

The delta contains **16** `#### Scenario:` blocks across its two MODIFIED
requirements (`grep -c '^#### Scenario:'` returns 16). All 16 are accounted
for below, exactly once each.

Thirteen of them are reproduced **verbatim** from
`openspec/specs/launch-gate-progression/spec.md` — a MODIFIED requirement
block restates its whole scenario set, changed or not. Verified
mechanically by comparing each scenario's body text between the current
spec and the delta: 13 identical, 1 changed, 2 new. The 13 are recorded
here as already covered, with the test that covers each, rather than
omitted — an unchanged scenario still has to be accounted for, and its
existing test is what this change must leave green.

### Requirement: A recurring pass advances every launch whose gate may open

| # | Scenario | Status | Test |
| --- | --- | --- | --- |
| 1 | An automatic gate opens once its conditions are satisfied | unchanged | `tests/unit/launch/application/test_progress_launch.py::test_an_automatic_gate_opens_once_its_conditions_are_satisfied` |
| 2 | Consecutive open gates are crossed in one pass | unchanged | `tests/unit/launch/application/test_progress_launch.py::test_consecutive_open_gates_are_crossed_in_one_pass` |
| 3 | A launch with an unsatisfied condition is left where it is, silently | unchanged | `tests/unit/launch/application/test_progress_launch.py::test_a_launch_with_an_unsatisfied_condition_is_left_where_it_is` |
| 4 | Recording an outcome does not itself advance a launch | **CHANGED** | its unchanged half: `tests/unit/launch/application/test_recording_does_not_advance_a_launch.py::test_recording_an_outcome_does_not_itself_advance_a_launch` (existing, untouched). Its new exception clause, read for what it excludes: `tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py::test_a_delivery_that_records_nothing_triggers_no_cascade` (3 params), `::test_a_graduated_launchs_delivery_triggers_no_cascade`, `::test_a_delivery_arriving_during_a_stand_down_triggers_no_cascade`, `::test_an_unverifiable_delivery_triggers_no_cascade`. Its exclusivity to one call site: every test in `tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py`. |
| 5 | A ClickUp webhook delivery may trigger an advance-and-ask cascade for the launch it completes | **NEW** | the trigger itself: `tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py::test_a_delivery_that_records_an_outcome_triggers_the_cascade_for_that_launch`, `::test_the_cascade_is_handed_the_product_identifier_and_nothing_else`, `::test_the_cascade_is_triggered_after_the_recording_transaction_has_closed`, `::test_the_route_defers_the_cascade_rather_than_awaiting_it_inline`, `::test_a_delivery_is_acknowledged_although_the_cascade_explodes`, `::test_the_trigger_is_a_named_part_of_the_modules_public_surface`. Its "every rule ... applies to that cascade exactly as they apply to the pass's own" clause: all 11 tests in `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py`. |
| 6 | A launch is not advanced past the final gate | unchanged | `tests/unit/launch/application/test_progress_launch.py::test_a_launch_is_not_advanced_past_the_final_gate`; additionally exercised for the new trigger by `tests/unit/launch/infrastructure/driving/test_advance_and_ask.py::test_the_final_gate_is_not_asked_about` |

### Requirement: A decision records the approval and reports what it did

| # | Scenario | Status | Test |
| --- | --- | --- | --- |
| 7 | An approving decision opens the gate and says so | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_an_approving_decision_records_an_approving_approval` **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_an_approving_decision_replies_that_the_gate_opened` |
| 8 | A rejecting decision keeps the gate closed | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_a_rejecting_decision_keeps_the_gate_closed` **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_rejecting_decision_replies_that_the_gate_stays_closed` |
| 9 | A decision whose gate the pass crossed first still reports it opened | unchanged | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_whose_gate_the_pass_crossed_first_still_reports_it_opened` |
| 10 | A decision arriving during a stand-down is refused | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_arriving_during_a_stand_down_is_refused` |
| 11 | A decision on a condition that has since regressed reports why | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_on_a_regressed_condition_is_recorded_and_opens_nothing` **and** `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_on_a_regressed_condition_names_what_blocks_it` |
| 12 | A decision naming the final gate is refused | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_naming_the_final_gate_is_refused` |
| 13 | A decision is acknowledged before its work completes | unchanged | `tests/unit/launch/infrastructure/driving/test_gate_decision_wiring.py::test_a_decision_is_acknowledged_before_its_work_completes` |
| 14 | A decision on a gate the launch has left is refused | unchanged | `tests/unit/launch/application/test_gate_decision.py::test_a_decision_on_a_gate_the_launch_has_left_is_refused` |
| 15 | A decision and the pass do not cross the same gate twice | unchanged | `tests/integration/launch/test_gate_progression_atomicity_live.py::test_a_decision_and_the_pass_do_not_cross_the_same_gate_twice` |
| 16 | A decision and a webhook-triggered advance do not cross the same gate twice | **NEW** | `tests/integration/launch/test_webhook_advance_atomicity_live.py::test_a_decision_and_a_webhook_triggered_advance_do_not_cross_the_same_gate_twice` — **never executed**; see the disclosure above |

### Uncovered scenarios

None. All 16 carry at least one named test, and the 13 unchanged ones are
covered by tests that already exist and that this change must leave green.

## Assertion classification

Per `ai-toolkit:testing`, every assertion is one of three things. Recorded
per test rather than per assertion where a test's assertions share a
provenance; each test file also carries these labels inline, beside the
assertion.

### Specified — traces to a stated requirement

| Assertion | Where |
| --- | --- |
| A delivery that recorded nothing triggers no cascade (four paths: unmapped task, non-status event, reopening with no observed closing, graduated launch) | `test_clickup_webhook_triggers_the_advance_cascade.py::test_a_delivery_that_records_nothing_triggers_no_cascade`, `::test_a_graduated_launchs_delivery_triggers_no_cascade` |
| A delivery arriving during a stand-down triggers no cascade | same file, `::test_a_delivery_arriving_during_a_stand_down_triggers_no_cascade` |
| An unverifiable delivery triggers no cascade | same file, `::test_an_unverifiable_delivery_triggers_no_cascade` |
| The three other recording call sites carry no trigger, by name or by alias; the recording use case's surface carries none | all of `test_the_advance_trigger_is_the_webhooks_alone.py` |
| The cascade runs for the launch named and no other | `test_advance_and_ask.py::test_the_trigger_runs_the_cascade_for_the_launch_it_names`, `::test_the_trigger_leaves_every_other_launch_alone` |
| A gate awaiting only confirmation is asked about, and the delivery recorded | `test_advance_and_ask.py::test_a_gate_awaiting_only_confirmation_is_asked_about` |
| The 24-hour cool-off suppresses a repeat, and an expired one does not | `::test_a_gate_asked_about_within_the_cool_off_is_not_asked_about_again`, `::test_a_gate_asked_about_more_than_a_day_ago_is_asked_about_again` |
| The final gate is not asked about | `::test_the_final_gate_is_not_asked_about` |
| A gate with an unsatisfied condition is left alone, silently, without failing | `::test_a_gate_with_an_unsatisfied_condition_is_left_alone_and_silently` |
| An unready playbook stands the trigger down, logged and not raised | `::test_an_unready_playbook_stands_the_trigger_down_for_that_launch` |
| A failed ask delivery is not recorded as a delivery | `::test_a_failing_ask_delivery_never_reaches_the_caller` |
| One crossing, however two concurrent paths interleave | `test_webhook_advance_atomicity_live.py` |

### Specified by the change's own artifacts, not by a `#### Scenario:`

Marked distinctly because the delta scenario says the cascade **MAY** be
triggered, which on its own no test could falsify. `tasks.md` 2.3 and
`design.md` — Decision 2 make it definite, and these assertions rest on
that rather than on the scenario's own modal. **This is the one place to
look if the change's intent about the `MAY` is ever revisited.**

| Assertion | Where |
| --- | --- |
| A delivery that recorded an outcome *does* trigger the cascade, for that launch | `test_clickup_webhook_triggers_the_advance_cascade.py::test_a_delivery_that_records_an_outcome_triggers_the_cascade_for_that_launch` |
| No failure inside the trigger reaches its caller, and it logs a warning naming the product (`tasks.md` 1.2, `design.md` — Decision 3) | `test_advance_and_ask.py::test_a_failing_cascade_never_reaches_the_caller` |
| The acknowledgement and the recording survive a cascade that raises (`proposal.md`; `design.md` — Decision 3) | `test_clickup_webhook_triggers_the_advance_cascade.py::test_a_delivery_is_acknowledged_although_the_cascade_explodes` |

### Derived — inferred, with no stated requirement covering it

| Assertion | Basis | Where |
| --- | --- | --- |
| The trigger is handed a `ProductId` and no loaded entity or request-scoped store | `tasks.md` 2.3; `design.md` — Decision 2 | `test_clickup_webhook_triggers_the_advance_cascade.py::test_the_cascade_is_handed_the_product_identifier_and_nothing_else` |
| The trigger runs after the recording and with no request session scope open | `tasks.md` 2.3 ("after that transition is committed") | same file, `::test_the_cascade_is_triggered_after_the_recording_transaction_has_closed` |
| The handler declares a `BackgroundTasks` parameter | `tasks.md` 2.2; `design.md` — Decision 2. Structural, because the flush itself is not observable through `TestClient` | same file, `::test_the_route_defers_the_cascade_rather_than_awaiting_it_inline` |
| The trigger is named in each module's `__all__` | `tasks.md` 1.3, 2.1; `proposal.md` — Impact | same file, `::test_the_trigger_is_a_named_part_of_the_modules_public_surface`; `test_advance_and_ask.py::test_the_trigger_is_exported_from_the_jobs_public_surface` |
| "Acknowledged" reads as a 2xx, "rejected" as a 4xx | the reading `test_clickup_webhook.py` already records for the same words | `test_clickup_webhook_triggers_the_advance_cascade.py`, throughout |
| The module paths of the three still-bound call sites resolve to distinct modules | fixture guard, not a requirement | `test_the_advance_trigger_is_the_webhooks_alone.py::test_the_exempt_call_site_and_the_bound_ones_are_distinct_modules` |

### Deliberately untested — identified and knowingly left uncovered

Each is also recorded at the foot of the file it belongs to, so it survives
next to the tests rather than only here.

| Case | Reason |
| --- | --- |
| That the acknowledgement is *flushed* before the cascade begins, and that a slow cascade does not delay it | `TestClient` runs a request and its background tasks inside one blocking call, so no assertion available there distinguishes deferral from an inline await. Covered indirectly by the `BackgroundTasks` structural check and the exploding-cascade test; the flush stays a review obligation on `design.md` — Decision 2 |
| Background-task ordering relative to other requests | `design.md` names it explicitly unguaranteed and immaterial; asserting one would impose a rule nobody agreed to |
| That the periodic pass's own behaviour is unchanged (`tasks.md` 1.4) | already covered by `test_gate_progression_pass.py` and `test_gate_progression_containment.py`, which this change must leave green |
| That the trigger reads the playbook in its own session rather than being handed one | the session provider is substituted in the unit tier, so a fresh read and a shared one are indistinguishable there |
| Which gates the cascade crosses, and one-at-a-time crossing | `progress_launch`'s own requirement, covered in `tests/unit/launch/application/test_progress_launch.py`; the cascade is substituted in `test_advance_and_ask.py` precisely so its tests fail for reasons they state |
| Which of the two concurrent paths wins the lock | the requirement states only that one advances and the other acts on the result |
| The webhook trigger racing the *recurring pass*, as opposed to a decision | the delta states the three-way rule but gives a scenario only for the decision pairing; the pass-versus-decision pairing already has its own test. Adding an unstated third pairing would assert a case nobody wrote down |
| Driving each of the three still-bound passes to observe that no launch advanced | three full pass harnesses for an assertion satisfiable by a pass that reached no launch at all; the structural guard is falsifiable by exactly the edit the requirement forbids |
| A trigger reached by an import *inside a function body* in one of the three bound modules | it would evade the structural guard. Accepted because it would also break the repository's bare-global convention, which `proposal.md` — Impact reaffirms for exactly this import, so its failure mode is a convention violation review sees rather than a silent one |

## Obsolete tests

The change carries `MODIFIED` deltas, so this list is applicable and is not
empty. **One candidate, for human confirmation — not a conclusion.** Nothing
below was edited, deleted or disabled by this pass.

### Search bound

Searched `tests/**/test_*.py` and nowhere else, by scenario title, by the
superseded clause's own wording ("does not itself advance", "advance",
"progress_launch", "gate_progression"), and via the archived manifest
`openspec/changes/archive/2026-08-28-advance-gates-and-confirm-in-slack/test-manifest.md`,
whose scenario-to-test table maps the requirements this delta modifies.
That manifest was reached because the archived change is the one this delta
amends and its path is recorded in the delta's own provenance; no other
archived manifest was consulted.

### Candidate

| Test | Superseded by | Evidence | Confidence |
| --- | --- | --- | --- |
| `tests/unit/launch/application/test_recording_does_not_advance_a_launch.py::test_recording_an_outcome_does_not_itself_advance_a_launch` | the MODIFIED scenario *Recording an outcome does not itself advance a launch* | The file transcribes the **pre-amendment** THEN verbatim in its module docstring and in the test's own docstring ("the launch's current gate is unchanged until a pass or a recorded decision advances it"), with no "unless it was recorded through the ClickUp webhook" clause. Its `DELIBERATELY UNTESTED` block additionally states that the other call sites "are covered by their own files, and none of them can advance a gate that the use case they all share does not advance" — which the amendment makes false for `clickup_webhook`, since the webhook now advances *beside* the use case rather than through it. | **Candidate for human confirmation.** Its **assertion is not superseded** and should not be deleted: the amendment exempts a call site, not the use case, so `record_step_outcome` still advances nothing and the test still guards that. What is superseded is the file's transcribed scenario text and one sentence of its untested-cases note. The likely correct action is a documentation-only update to those two passages, not a change to the assertion — and, per this pass's own rule, this pass made neither. |

No other test bearing on either MODIFIED requirement's superseded text was
found within the bound above. That is *"none was found by this search"*,
not *"no such test exists"*: the search was by scenario wording and by the
archived manifest's mapping, and a test that constrained the old behaviour
without naming it either way would not have surfaced.

## Unresolved project questions

Discharged per this agent's contract: `AGENTS.md` and `CLAUDE.md` were
read, and each question below is one they do not answer. Each is recorded
with the assumption taken and the tests that depend on it.

| Question | Assumption taken | Tests depending on it | Correction point |
| --- | --- | --- | --- |
| What is the trigger called on `gate_progression_job`? | `advance_and_ask`, per `tasks.md` 1.1 — probed across four spellings, failing loudly where none is found rather than running against an unsubstituted real one | all of `test_advance_and_ask.py`; `test_webhook_advance_atomicity_live.py` | `_ENTRY_NAMES` / `_TRIGGER_NAMES` in each file |
| What is it called once imported into `clickup_webhook`? | the same name | all of `test_clickup_webhook_triggers_the_advance_cascade.py` | `_TRIGGER_NAMES` there |
| Is it invoked positionally or by keyword, and does it take `now`? | read off the implemented signature at call time rather than assumed | `test_advance_and_ask.py`, `test_webhook_advance_atomicity_live.py` | `_Harness.run` / `_advance` |
| What does the cascade hand back to say a gate awaits confirmation? | `_Progressed`, transcribed from `test_gate_progression_pass.py`, which records the provenance | `test_advance_and_ask.py` | that file, and its original |
| The cool-off window's length | read off the module (`ASK_COOL_OFF`), falling back to 24 hours | `test_advance_and_ask.py`'s two cool-off tests | `_cool_off()` |
| Is a structural assertion (a `BackgroundTasks` parameter; a name in `__all__`) acceptable in this project's tests, or does it prefer behaviour only? | Accepted — `test_clickup_webhook.py`'s mounting guard and `test_main_monitoring_wiring.py` set the precedent for structural wiring guards, and `AGENTS.md` records no rule either way. Each such assertion states its limit inline | `::test_the_route_defers_the_cascade_rather_than_awaiting_it_inline`, the two `__all__` guards, all of `test_the_advance_trigger_is_the_webhooks_alone.py` | the tests named |
| No stack skill covers FastAPI/Starlette specifically | `ai-toolkit:testing` plus `ai-toolkit:python` were loaded; no near-miss skill was substituted. The FastAPI idiom was taken from this repository's existing tests instead | all four files | — |

## Method note: how the fixtures were verified without writing implementation

The unit fixtures were exercised against a **throwaway probe kept entirely
outside the repository**, in this session's scratchpad, loaded as a pytest
plugin by `PYTHONPATH` for a handful of runs and then deleted. Its purpose
was to tell a broken fixture (`ai-toolkit:testing`'s third failure state)
from an absent target (its second) — without it, a fixture defect would
have been indistinguishable from the expected pre-implementation failure.

Nothing from it was written into `src/`, and the repository's own runs still
fail on the absent target, as the table at the top of this file records. Two
of the eleven `test_advance_and_ask.py` assertions were additionally checked
against a *mutated* probe — one with its cool-off check and its final-gate
check removed — and both failed, so those two tests discriminate rather than
merely pass.

## What the implementation step must make pass

Run these, and expect them green when sections 1 and 2 of `tasks.md` are
done:

```
uv run pytest tests/unit/launch/infrastructure/driving/test_clickup_webhook_triggers_the_advance_cascade.py
uv run pytest tests/unit/launch/infrastructure/driving/test_advance_and_ask.py
uv run pytest tests/unit/launch/infrastructure/driving/test_the_advance_trigger_is_the_webhooks_alone.py
uv run pytest tests/integration/launch/test_webhook_advance_atomicity_live.py   # needs a database
```

Task-by-task:

| `tasks.md` | Tests that hold it |
| --- | --- |
| 1.1 `advance_and_ask` on `gate_progression_job` | all of `test_advance_and_ask.py` |
| 1.2 broad catch, logged warning naming the product | `test_advance_and_ask.py::test_a_failing_cascade_never_reaches_the_caller`, `::test_a_failing_ask_delivery_never_reaches_the_caller` |
| 1.3 exported from `__all__` | `test_advance_and_ask.py::test_the_trigger_is_exported_from_the_jobs_public_surface` |
| 1.4 the periodic pass unchanged | no test of this change; the existing `test_gate_progression_pass.py` and `test_gate_progression_containment.py` are what hold it, and must stay green |
| 2.1 bare global + `__all__` on `clickup_webhook` | `test_clickup_webhook_triggers_the_advance_cascade.py::test_the_trigger_is_a_named_part_of_the_modules_public_surface`, and every substitution in that file |
| 2.2 `BackgroundTasks` parameter | `::test_the_route_defers_the_cascade_rather_than_awaiting_it_inline` |
| 2.3 dispatched after the recording, with the `ProductId` alone | `::test_a_delivery_that_records_an_outcome_triggers_the_cascade_for_that_launch`, `::test_the_cascade_is_triggered_after_the_recording_transaction_has_closed`, `::test_the_cascade_is_handed_the_product_identifier_and_nothing_else` |
| 2.4 no other early-return path schedules it | `::test_a_delivery_that_records_nothing_triggers_no_cascade` (3 params), `::test_a_graduated_launchs_delivery_triggers_no_cascade`, `::test_a_delivery_arriving_during_a_stand_down_triggers_no_cascade`, `::test_an_unverifiable_delivery_triggers_no_cascade` |
| 3.1, 3.2 | this manifest and the four files above |

### One thing to watch that no test here can flag

`clickup_webhook.py`'s existing test files substitute its collaborators with
`monkeypatch.setattr` at its default `raising=True`, but **none of them
substitutes the new trigger** — they were written before it existed. Once
the route dispatches it, those files' deliveries will schedule the *real*
`advance_and_ask` as a background task against their fake stores. It should
degrade quietly, because `tasks.md` 1.2's broad catch swallows and logs
whatever it hits, but it is real work running inside tests that did not ask
for it. If any of those files turns flaky or slow after section 2 lands,
that is the reason — and adding the substitution to them is an edit to
existing tests, which is deliberately not this pass's to make.
