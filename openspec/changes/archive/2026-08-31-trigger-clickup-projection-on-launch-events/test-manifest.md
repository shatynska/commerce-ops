# Test manifest — `trigger-clickup-projection-on-launch-events`

Written by the `openspec-test-writer` pass, strictly from this change's
approved specification deltas
(`specs/launch-clickup-sync/spec.md`), before any implementation exists.
No production code has been read to derive these tests; existing **test**
files in the repository's test-path glob were read to transcribe naming,
fixture and probing conventions, and their provenance is recorded in each
new file's own module docstring.

This file is **not** an OpenSpec artifact the schema knows about — it will
not appear among `openspec instructions apply`'s context files, and must
be read on purpose before implementation begins. It is also pointed to by
this repository's `ai-toolkit` rules fragment that directs a manifest be
read before implementing, and — redundantly, since that fragment's import
path is machine-local — by this report.

Test command: `uv run pytest`. Test-path glob: `tests/**/test_*.py`.

## Baseline

Recorded before any test in this pass was written, at
`/home/shatynska/projects/commerce-ops/.claude/worktrees/clickup-webhook-explore`,
commit `cc8231e11e9e20d13738fae1fb3c474175dd240b`, clean working tree:

- `uv run pytest tests/unit tests/agents` — **1743 passed, 0 failed, 72
  skipped**.
- `uv run pytest tests/integration` — **3 passed, 0 failed, 125 skipped**
  (no `DATABASE_URL` configured in this environment; the tier did not run).

After this pass's tests were added (same commit, no implementation
written):

- `uv run pytest tests/unit tests/agents` — **1745 passed, 19 failed, 72
  skipped, 3 errors** (22 new failures/errors — all of them the expected
  absent-target/wrong-value failures enumerated below; 2 new tests pass
  already, for behavior this change must preserve rather than introduce,
  each recorded below).
- `uv run pytest tests/integration` — **3 passed, 0 failed, 127 skipped**
  (the 2 new integration tests skip, no `DATABASE_URL` configured here;
  never executed against a real database — see the warning in their own
  module docstring).
- `uv run ruff check` / `uv run ruff format --check` on every new file:
  clean.

No existing test was edited, deleted, or disabled. This pass is additive
only.

## Delta spec

`openspec/changes/trigger-clickup-projection-on-launch-events/specs/launch-clickup-sync/spec.md`
carries one ADDED requirement, *A launch is converged eagerly at start and
at a gate crossing*, with nine `#### Scenario:` blocks. All ADDED — no
MODIFIED, REMOVED or RENAMED delta in this change, so the obsolete-tests
list below is **not applicable**, per the standard's own rule for a
change carrying no such delta.

## Scenario → test accounting

Every scenario is accounted for exactly once.

### Scenario: A newly started launch's first tasks appear without waiting for the pass

- `tests/unit/launch/infrastructure/driving/test_slack_entry_eager_convergence.py::test_a_successful_submission_triggers_the_eager_helper`
- `tests/integration/launch/test_eager_convergence_atomicity_live.py` does
  not itself re-drive this scenario (see its own scope below); the
  real-ClickUp realization of "tasks exist without the pass running"
  (`tasks.md` 6.1) is recorded as **not separately covered** — see
  *Unresolved project questions*, "task 6.1/6.2 not separately driven".

### Scenario: A gate crossing's newly released steps get tasks immediately, however the gate opened

- `tests/unit/launch/infrastructure/driving/test_gate_confirmation_eager_convergence.py::test_a_decision_that_crosses_a_gate_triggers_the_eager_helper`
  (the decision path)
- `tests/unit/launch/infrastructure/driving/test_gate_progression_pass_eager_convergence.py::test_a_gate_the_pass_itself_crosses_triggers_the_eager_helper`
  (the periodic pass)
- `tests/unit/launch/infrastructure/driving/test_clickup_webhook_eager_convergence.py::test_a_delivery_whose_cascade_crosses_a_gate_triggers_the_eager_helper`
  (the webhook's advance-and-ask trigger)

### Scenario: The eager run applies the same eligibility rules as the pass

- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_the_helper_delegates_to_the_real_converge_launch_not_a_copy`

  Covered as a delegation guard rather than by re-asserting every
  eligibility rule: the requirement's own reasoning is "because it is the
  same convergence, run early, not a second rule", and every eligibility
  rule `converge_launch` itself applies is already covered by the
  untouched driven-tier suite (`test_clickup_sync_projection.py` and its
  siblings). Re-testing each rule here would duplicate rather than add,
  and is recorded as such in that file's own DELIBERATELY UNTESTED
  section.

### Scenario: The eager run does not record completions

- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_the_eager_run_reaches_no_completion_recording_collaborator`

### Scenario: The eager run and the pass do not duplicate each other's work

- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_the_lock_is_acquired_around_the_convergence_call`
- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_converge_launchs_collaborators_are_not_rebound_to_the_lock_transaction`
- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_a_failure_partway_through_convergence_leaves_prior_writes_standing_for_a_later_attempt`
- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_lock_wrapping.py::test_the_lock_is_acquired_for_each_launchs_convergence_call`
  (the pass's own side of the race)
- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_lock_wrapping.py::test_converge_launchs_collaborators_are_reused_across_launches_not_rebuilt`
- `tests/integration/launch/test_eager_convergence_atomicity_live.py::test_two_concurrent_eager_calls_for_a_brand_new_launch_produce_one_list`
  (the real-Postgres, real-lock realization)
- `tests/integration/launch/test_eager_convergence_atomicity_live.py::test_a_failure_partway_through_the_eager_run_leaves_real_prior_writes_standing`
  (the real-Postgres realization of `tasks.md` 1.2's partial-write-survival
  claim — this is the test the dispatch specifically asked to assert prior
  writes are **not rolled back**, not merely that no exception escapes)

### Scenario: A failed eager run does not fail the action that triggered it

- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_a_failing_convergence_is_logged_not_raised`
  (the helper's own containment, asserted once)
- `tests/unit/launch/infrastructure/driving/test_slack_entry_eager_convergence.py::test_a_failing_eager_run_does_not_fail_the_submission`
- `tests/unit/launch/infrastructure/driving/test_gate_confirmation_eager_convergence.py::test_a_failing_eager_run_does_not_affect_the_deciders_reply`
- `tests/unit/launch/infrastructure/driving/test_gate_progression_pass_eager_convergence.py::test_a_failing_eager_run_does_not_fail_the_passs_own_run`
- `tests/unit/launch/infrastructure/driving/test_clickup_webhook_eager_convergence.py::test_a_failing_eager_run_does_not_affect_the_webhooks_acknowledgement`

### Scenario: A failed eager run is caught up by the next periodic pass

- `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py::test_a_failure_partway_through_convergence_leaves_prior_writes_standing_for_a_later_attempt`
  (driven together with the "do not duplicate" scenario — see that test's
  own docstring for why the two are inseparable at this level: what makes
  a later attempt converge cleanly is precisely that nothing the failed
  one wrote was undone)

### Scenario: The eager run stands down exactly as the pass does

- `tests/unit/launch/infrastructure/driving/test_slack_entry_eager_convergence.py::test_a_stood_down_start_never_reaches_the_eager_helper`
- `tests/unit/launch/infrastructure/driving/test_gate_progression_pass_eager_convergence.py::test_a_stood_down_pass_never_reaches_the_eager_helper`
- The decision path's and the webhook's own stand-down are recorded as
  **not separately driven** — see *Uncovered / not separately driven*
  below.

## Uncovered / not separately driven, with reasons

Per the standard, a case judged not to need its own test is recorded here
rather than silently dropped:

- **The decision path's stand-down** (`gate_confirmation.py`, part of *The
  eager run stands down exactly as the pass does*). Not driven as its own
  test. Reason: `design.md` states stand-down is "inherited... not
  re-implemented" at every call site — the eager helper is only ever
  reached once its caller has already cleared `PlaybookNotReadyError`. The
  decision path's own existing stand-down behavior (refusing before any
  advance is attempted) is unaffected by this change and already covered
  by `test_gate_decision_wiring.py`'s sibling suite; a dedicated eager-
  specific stand-down test here would need to duplicate that fixture set
  to prove a property (`helper.calls == []`) that follows trivially once
  "the helper is only reached after a successful advance" already holds
  (asserted positively by this file's own crossing test). Two of the four
  call sites (`slack_entry`, `gate_progression_job`) carry a dedicated
  stand-down test as a representative sample of the pattern; the other two
  are recorded here rather than reproduced.
- **The webhook's stand-down**, same reasoning, same recorded omission.
  `test_clickup_webhook_eager_convergence.py`'s own DELIBERATELY UNTESTED
  section notes that a delivery which records nothing (including one
  arriving during a stand-down) already implies no crossing and therefore
  no eager call, per that file's own positive test's premise.
- **`tasks.md` 6.1/6.2's own integration-tier realizations** — that
  starting a launch, and each of the three gate-crossing paths, results in
  ClickUp tasks existing without `clickup_sync_job`'s pass having run, as
  full end-to-end integration tests through the real HTTP/Slack routes.
  Not driven. Reason: every call site's own unit-tier wiring test already
  establishes "the eager helper is triggered, handed this launch" at the
  route/listener level (this is what a route/listener test *can* observe,
  per this repository's own level convention — see e.g.
  `test_clickup_webhook_triggers_the_advance_cascade.py`'s docstring
  drawing the identical line for `advance_and_ask`), and
  `test_eager_convergence_helper.py` establishes what the helper then does
  with a real `converge_launch`. A full end-to-end integration test
  through all four real routes would mostly re-exercise both halves
  through more machinery (Slack signature verification, FastAPI wiring,
  `main.py`'s composition) without adding a claim neither already makes.
  This is a **deliberate scope reduction from `tasks.md`'s own task list**,
  not from the delta spec's scenarios — every scenario is still accounted
  for above — and is called out explicitly so it can be revisited if the
  implementer judges the wiring-level tests insufficient assurance.

## Specified / derived / deliberately-untested accounting

Each new file's own module docstring and inline `SPECIFIED` / `DERIVED` /
`SPECIFIED-BY-TASKS` / `SPECIFIED-BY-DESIGN` markers carry this
classification at the assertion level, per this repository's own
established convention (visible throughout the existing suite, e.g.
`test_advance_and_ask.py`, `test_gate_decision_wiring.py`). Summarized
here by file:

- **`test_eager_convergence_helper.py`** — every assertion traces to the
  delta spec's own requirement text or to `tasks.md` 1.1/1.2/`design.md`'s
  stated mechanism (SPECIFIED / SPECIFIED-BY-TASKS / SPECIFIED-BY-DESIGN).
  No assertion in this file is DERIVED beyond the ordinary premise/guard
  assertions ("the failing convergence was really reached") every file in
  this suite already carries.
- **`test_slack_entry_eager_convergence.py`,
  `test_gate_confirmation_eager_convergence.py`,
  `test_gate_progression_pass_eager_convergence.py`,
  `test_clickup_webhook_eager_convergence.py`** — each call site's
  trigger-and-containment assertions are SPECIFIED or SPECIFIED-BY-TASKS.
  One DERIVED assertion per file, each recorded inline: that a decision
  which crosses no gate does not trigger the helper
  (`test_a_rejecting_decision_never_triggers_the_eager_helper`); that a
  launch left unchanged by the pass does not trigger it
  (`tasks.md` 2.3, so actually SPECIFIED-BY-TASKS there, not DERIVED); the
  ordering guard that the decider's reply precedes the helper
  (`test_the_eager_helper_runs_after_the_decider_has_already_been_answered`,
  SPECIFIED-BY-DESIGN).
- **`test_clickup_sync_job_lock_wrapping.py`** — SPECIFIED-BY-DESIGN
  throughout; the collaborator-identity and containment-regression tests
  are explicitly framed as regression guards, not new requirements, in
  the file's own docstring.
- **`test_slack_entry_cadence_wording.py`** — the no-stale-minute-count
  assertion is SPECIFIED-BY-TASKS (`tasks.md` 5.1); the "reads as
  near-immediate" assertion is DERIVED, explicitly labelled as such in
  its own docstring, because no artifact fixes an exact replacement
  phrase.
- **`test_eager_convergence_atomicity_live.py`** — both tests are
  SPECIFIED-BY-TASKS/SPECIFIED-BY-DESIGN, realizing claims already
  classified at the unit tier against a real database.

## Obsolete tests

**Not applicable.** This change's delta spec carries only an ADDED
requirement — no MODIFIED, REMOVED or RENAMED delta — so there is no
superseded behavior to search for, per the standard's own rule for this
case.

## Unresolved project questions

Recorded here because no channel exists to ask them interactively; each
carries the assumption taken and the tests that depend on it.

1. **Where the shared eager-convergence helper lives.** `tasks.md` 1.1
   names two candidate homes (`clickup_sync.py` or a thin
   `gate_progression_job.py` function). Assumption: neither is assumed;
   `_MODULE_CANDIDATES` in `test_eager_convergence_helper.py` and
   `test_eager_convergence_atomicity_live.py` probes both at collection
   time and fails loudly, naming both candidates, if neither carries a
   plausible entry point. Depends on this: every test in those two files.
2. **The helper's own name.** `_HELPER_NAMES` (five candidate spellings)
   is the correction point, kept identical and cross-referenced across
   every new file that reaches the helper (`test_eager_convergence_helper.py`
   is the canonical list; every call-site file's own copy is commented
   "kept in step with" it). Depends on this: every test that installs or
   locates the helper.
3. **The helper's call shape** — whether it takes a bare `ProductId`, a
   loaded `Launch`, both, or `converge_launch`'s own collaborators
   directly as keyword arguments. Assumption: a pool of plausible names is
   supplied and filtered by the implemented signature (`_invoke`), mirroring
   `test_advance_and_ask.py`'s and `test_gate_progression_pass.py`'s own
   established convention for an invented entry-point signature. Depends
   on this: every test that calls the helper directly (not through a
   driving-adapter route/listener, which instead substitutes the helper
   wholesale and does not need to know its signature).
4. **Whether `clickup_webhook.py` dispatches the eager helper via its own
   `background_tasks.add_task` call, or from inside `advance_and_ask`
   itself once it crosses a gate.** `tasks.md` 3.5 permits either.
   Assumption: `test_clickup_webhook_eager_convergence.py`'s assertions
   are written to hold under either shape (see its own module docstring,
   "What 'alongside, or from within' leaves open"). Depends on this: both
   tests in that file.
5. **`gate_progression_job.py`'s own worker-process wiring**
   (`read_product`/`read_people` module globals injected by `worker.py`,
   `tasks.md` 2.1) is a composition-root detail outside this change's
   delta spec scenarios. Assumption: not independently tested; the
   in-memory harness substitutes the helper wholesale, so this file's
   tests would pass regardless of whether that wiring is correct. Depends
   on this: nothing in this pass; flagged so the implementer knows a wiring
   defect there would not be caught by any test in this manifest and needs
   its own verification (e.g. a manual run, or `tasks.md` 7.3's own
   deployment check).
6. **The exact replacement wording for `CLICKUP_SYNC_CADENCE_DESCRIPTION`.**
   No artifact fixes a phrase. Assumption: the replacement must not carry
   a stale fixed-minute claim and must read as describing near-immediate
   appearance under a small set of plausible markers (`_NEAR_IMMEDIATE_MARKERS`
   in `test_slack_entry_cadence_wording.py`). Depends on this: one test in
   that file, explicitly labelled DERIVED.
7. **`tasks.md` 6.1/6.2's full end-to-end integration realization** is
   deliberately not separately driven — see *Uncovered / not separately
   driven* above for the reasoning, which is a scope decision rather than
   an unresolved factual question, recorded here for visibility alongside
   the others.

## What the implementation step must make pass

Every test enumerated under *Scenario → test accounting* above, plus the
regression guards in `test_clickup_sync_job_lock_wrapping.py` (2 of which
already pass and must **continue** to pass — they exist to catch a
restructuring that reaches further than `tasks.md` 4.1 intends) and the
existing, untouched suites this change must not regress
(`test_gate_progression_pass.py`, `test_gate_progression_containment.py`,
`test_gate_decision_wiring.py`, `test_advance_and_ask.py`,
`test_clickup_webhook.py`, `test_clickup_webhook_triggers_the_advance_cascade.py`,
`test_clickup_sync_job_containment.py`,
`test_clickup_sync_job_containment_live.py`, and every driven-tier
`converge_launch` eligibility test). None of these existing files were
edited by this pass.

Run `uv run pytest tests/unit tests/agents` for the fast tiers and
`uv run pytest tests/integration` against a real, migrated database for
the two new atomicity tests — neither has ever been executed against one;
see their own module docstring's explicit warning not to trust a green
result from a run that never happened.
