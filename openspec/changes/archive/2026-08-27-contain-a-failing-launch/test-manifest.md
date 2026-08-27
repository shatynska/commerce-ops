# Test manifest — `contain-a-failing-launch`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-27, from the change's
delta spec alone. `src/commerce_ops/launch/infrastructure/driving/clickup_sync_job.py`
— the module under test — was **not** read while deriving these tests; every
assertion traces to the delta, to `design.md`/`tasks.md` where marked, or to an
existing test file whose own conventions were transcribed.

**This file is not an artifact the OpenSpec schema knows about.** It will not
appear among the context files `openspec instructions apply` surfaces. Read it
on purpose, before implementing.

## Baseline

Taken before any test here was written, full-suite in both tiers:

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1114 passed, 0 failed |
| `uv run pytest tests/integration` | 93 passed, 2 skipped, 0 failed |

Both skips are pre-existing and unrelated (`test_playbook_authoring_roster_live.py`
— no active roster person; `test_registered_handlers_activate_nothing.py` — no
overlapping seeded handler).

## State after this pass

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | **9 failed**, 1117 passed |
| `uv run pytest tests/integration` | **2 failed**, 93 passed, 2 skipped |
| `uv run ruff check` / `ruff format --check` (new files) | clean |
| `uv run mypy .` | clean, 312 source files |

Nothing that passed at the baseline fails now. The eleven new failures are all in
the three files below, and every one of them fails on a **wrong value** — the
launches behind a failing one going unconverged — not on an absent target. Three
new tests pass on their first run; each is accounted for individually below.

## Files written

| File | Tier |
| --- | --- |
| `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_containment.py` | unit |
| `tests/unit/launch/infrastructure/driving/test_clickup_webhook_intake_survives_a_failing_pass.py` | unit |
| `tests/integration/launch/test_clickup_sync_job_containment_live.py` | integration |

Tier placement follows `AGENTS.md` — *Testing Strategy*: the subject is the
driving adapter `clickup_sync_job`, so the unit tests sit under
`tests/unit/launch/infrastructure/driving/`; the two scenarios needing a real
transaction sit under `tests/integration/launch/`.

## Scenario accounting

The delta carries **18** `#### Scenario:` blocks — 13 on the ADDED requirement,
5 on the MODIFIED one. All 18 are accounted for below: 14 covered by tests
written here, 4 covered by existing tests for scenarios the delta restates
verbatim.

Names are given as runner-selectable node ids. Prefix for the unit containment
file is
`tests/unit/launch/infrastructure/driving/test_clickup_sync_job_containment.py::`.

### ADDED — *One launch's failure does not stop the other launches being converged*

| # | Scenario | Test | First-run state |
| --- | --- | --- | --- |
| 1 | A launch that fails does not stop the launches after it | `…test_clickup_sync_job_containment.py::test_a_launch_that_fails_does_not_stop_the_launches_after_it` | fails, wrong value |
| 2 | Each contained failure is reported against its own launch | `…::test_each_contained_failure_is_reported_against_its_own_launch` | fails, wrong value |
| 3 | A run carrying a failed launch is reported as failed | `…::test_a_run_carrying_a_failed_launch_is_reported_as_failed` | fails, wrong value |
| 4 | A run in which every launch succeeds is reported as succeeded | `…::test_a_run_in_which_every_launch_succeeds_is_reported_as_succeeded` | **passes** — see *Tests that pass today* |
| 5 | A stand-down is not a contained failure | `…::test_a_stand_down_is_not_a_contained_failure` | **passes** — see *Tests that pass today* |
| 6 | A launch whose projection failed is not reconciled on that run | `…::test_a_launch_whose_projection_failed_is_not_reconciled_on_that_run` | fails, wrong value |
| 7 | A completion withheld by a skipped reconciliation is recorded later | `…::test_a_completion_withheld_by_a_skipped_reconciliation_is_recorded_later` | fails, wrong value |
| 8 | A webhook delivery still records for a launch whose projection is failing | `tests/unit/launch/infrastructure/driving/test_clickup_webhook_intake_survives_a_failing_pass.py::test_a_webhook_delivery_still_records_for_a_launch_whose_projection_is_failing` | **passes** — see *Tests that pass today* |
| 9 | A partially projected launch keeps what its failed attempt achieved | `tests/integration/launch/test_clickup_sync_job_containment_live.py::test_a_partially_projected_launch_keeps_what_its_failed_attempt_achieved` | fails, wrong value |
| 10 | A launch attempted after one that failed on the database is unaffected by it | `tests/integration/launch/test_clickup_sync_job_containment_live.py::test_a_launch_after_one_that_failed_on_the_database_is_unaffected_by_it` | fails, wrong value |
| 11 | A failure of the recovery between launches ends the walk | `…::test_a_failure_of_the_recovery_between_launches_ends_the_walk` | fails, wrong value |
| 12 | A cancelled pass stops rather than containing the cancellation | `…::test_a_cancelled_pass_stops_rather_than_containing_the_cancellation` | fails, wrong value |
| 13 | Missing folder configuration is not turned into a skip | `…::test_missing_folder_configuration_is_not_turned_into_a_skip` | fails, wrong value |

### MODIFIED — *The reconciliation pass records completions and reopenings the webhook missed*

The delta restates four of this requirement's five scenarios **verbatim** from
`openspec/specs/launch-clickup-sync/spec.md` (compared line by line). Their
existing tests are unaffected and are not rewritten.

| # | Scenario | Test | First-run state |
| --- | --- | --- | --- |
| 14 | A missed completion is recorded on reconciliation | `tests/unit/launch/infrastructure/driven/test_clickup_sync_reconciliation.py::test_a_missed_completion_is_recorded_on_reconciliation` (existing, unchanged) | passes, unchanged |
| 15 | A missed reopening is recorded on reconciliation | `…test_clickup_sync_reconciliation.py::test_a_missed_reopening_is_recorded_on_reconciliation` (existing, unchanged) | passes, unchanged |
| 16 | No transition means no recording | `…test_clickup_sync_reconciliation.py::test_no_transition_means_no_recording` (existing, unchanged) | passes, unchanged |
| 17 | Reconciliation never overwrites other recording paths | `…test_clickup_sync_reconciliation.py::test_reconciliation_never_overwrites_other_recording_paths` (existing, unchanged) | passes, unchanged |
| 18 | A launch whose projection failed is left unreconciled and unobserved | `…test_clickup_sync_job_containment.py::test_a_launch_whose_projection_failed_is_left_unreconciled_and_unobserved` | fails, wrong value |

**Uncovered scenarios: none.** Every one of the 18 has at least one named test.

## Tests that pass on their first run

`ai-toolkit:testing` treats a first-run pass as an alarm for a test written
ahead of its implementation. Three passed here, each was investigated, and each
is recorded rather than reported as coverage of new behaviour:

- **#4, a run in which every launch succeeds is reported as succeeded** — states
  what containment must **preserve**. The pass already returns normally when
  nothing fails. The test's job is to catch containment that swallowed the run's
  outcome, which is the exact failure `design.md` warns of.
- **#5, a stand-down is not a contained failure** — readiness already sits above
  the loop (`design.md` — Context; `tasks.md` 2.5). The test's job is to catch an
  implementation that moved the serving read inside the loop and turned a
  stand-down into one contained failure per launch. It asserts more than the
  existing `test_clickup_sync_job_stand_down.py` does: that nothing is reported
  as a *failed launch* during a stand-down.
- **#8, a webhook delivery still records** — the delta says intake "is unaffected
  by any of this". The test's job is to catch a containment implementation that
  reached into the intake path.

Two further tests — #7 and #18 — **passed on their first draft for a reason
their scenario does not state**: a pass that abandons its walk also withholds
the launch's reconciliation, so their assertions held against the very behaviour
this change removes. Each was strengthened to assert the premise its scenario is
stated over (that the failure was *contained* and the walk went on), and both
now fail on that assertion. Recorded here because the first draft was squarely
the fourth failure state.

## Assertion classification

### Specified

Every assertion carrying a `# SPECIFIED` comment in the three files. In summary:
which launches are converged and which are reconciled on a run; that each
contained failure is logged separately, naming its product identifier, carrying
what was raised, and doing so before the next launch is attempted; that the job
raises for a run carrying a failed launch and returns normally otherwise; that
the raised error names every failed launch by product identifier; that a
stand-down attempts nothing and reports nothing as a failed launch; that a
skipped reconciliation leaves the retained observed state untouched and the
withheld completion is recorded by a later successful run; that a raising
rollback ends the walk and names only the launches contained up to that point;
that a cancellation propagates and is not attributed to a product; that the
unconfigured-folder condition produces one failure per launch rather than a
skip; that committed associations survive a contained failure and are found by
the next run; and that a launch after a database fault records its writes.

Two readings are transcribed rather than invented, from
`test_clickup_sync_job_stand_down.py` and the briefing job's tests: **"reported
as a failed run" = the job body raises**, **"reported as succeeded" = it returns
normally**. A job body has no other outcome signal.

### Derived

Three, each marked `# DERIVED` at its assertion site:

1. **The aggregate error does not name a launch that did not fail**
   (`test_a_run_carrying_a_failed_launch_is_reported_as_failed`). Derived from
   the requirement's "the per-launch report is what makes a fault diagnosable";
   no scenario states it.
2. **The aggregate error carries the rollback failure in its cause chain**
   (`test_a_failure_of_the_recovery_between_launches_ends_the_walk`). Derived
   from `design.md` — *A contained failure rolls the session back* ("raise the
   aggregate below chained to it") and `tasks.md` 2.3. The delta states only
   that the error names the contained launches.
3. **A 2xx is what "acknowledged" means for the webhook delivery**
   (webhook-intake file). The same reading `test_clickup_webhook.py` already
   records for the intake requirements.

### Deliberately untested

Recorded in a closing block in each file, and summarised here:

- That the catch is literally `except Exception` rather than a curated list of
  error types. `design.md` decides it; no scenario states it. The tests provoke
  `ClickUpSyncError`, a bare `RuntimeError` and a real `SQLAlchemyError` between
  them, which is what a curated list would miss.
- That the recovery is a `rollback()` specifically, rather than any other means
  of restoring the session. The scenarios state the *effect*.
- That the rollback runs after every contained failure rather than only after a
  database one. `design.md` chooses unconditional; no scenario states it.
- What `scheduled-jobs` records for a run whose process was cancelled — the
  requirement explicitly declines to constrain it.
- The order the walk visits launches in. `design.md` — *The walk's order is left
  as it is* — leaves it unspecified; the fixtures pin an order only so that
  "before" and "after" are sayable.
- A database that accepts rollbacks while refusing writes (read-only failover,
  full disk). `design.md` — Risks — names it accepted unmitigated, so there is no
  stated behaviour to assert.
- Recovery from a fault raised by `reconcile_launch` rather than
  `converge_launch` **in the integration tier**. The requirement contains both
  halves as one unit; the unit tier drives the reconciliation half.
- Every intake condition other than the one scenario #8 states — signature
  verification, unmapped task, graduated launch, repeated delivery. Those
  requirements are unmodified and their tests stand in
  `test_clickup_webhook.py`.
- Whether a delivery arriving *during* a run is recorded. No scenario states an
  ordering, and the change introduces no shared state between the two paths.

## Why two scenarios are in the integration tier

`tasks.md` 1.2 required a decision here and it is recorded rather than left
implicit. **Both scenarios #9 and #10 are driven against a real Postgres session,
not against a fake that refuses writes until `rollback()` is called.**

The alternative `tasks.md` 1.2 offers would establish that the implementation
calls a method named `rollback` — a fact about the code's shape. A real session
establishes that *the next launch's write lands*, which is what the scenario
states, and it costs nothing extra here because the tier already has a database
and a real mapping store to write through. Concretely:

- **#9** needs the associations recorded before the failure to be readable **in
  a fresh session** after the walk's session is rolled back and closed. An
  in-memory store keeps its dictionary entries through any exception, so it
  cannot tell a committed write from a pending one — and "nothing is pending
  when the rollback runs" is the property `design.md` says makes the
  unconditional rollback safe.
- **#10** provokes a genuine failed transaction: the first launch's projection
  runs `SELECT 1 / 0`, which Postgres rejects and which leaves the shared
  `AsyncSession` in the state every later write raises against until it is
  rolled back. The second launch's write then lands only if the pass recovered.
  A fake that merely raises would be green with no rollback at all.

Both files were verified to fail today for the stated reason — the second launch
never attempted — and, in #9, only *after* the committed-work assertions passed,
which independently confirms `design.md`'s "every write in the walk is already
committed when it is made".

## Obsolete tests

**None found.** Stated as a determination rather than as an empty list:

The search covered the dispatched test-path glob `tests/**/test_*.py` and nothing
outside it. No earlier `test-manifest.md` was supplied for this change, so no
scenario-to-test mapping was available to draw on. Within the glob, every test
file referencing the job module (`clickup_sync_job`, `reconcile_clickup_completions`)
or either pass function (`converge_launch`, `reconcile_launch`) was enumerated
and read for bearing:

- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_schedule.py` —
  asserts only that the pass is scheduled and unreachable from outside. It quotes
  the MODIFIED requirement's "every active launch's mapped tasks" in its docstring
  but asserts nothing about which launches are walked. **Not obsolete.**
- `tests/unit/launch/infrastructure/driving/test_clickup_sync_job_stand_down.py`
  and `…test_clickup_sync_job_tag_stand_down.py` — one active launch each, and
  they assert whether the passes ran, never what happens when one fails.
  **Not obsolete.**
- The seven driven-tier `test_clickup_sync_*.py` / `test_clickup_*_leave_loop.py`
  files — each drives one launch directly through `converge_launch` or
  `reconcile_launch`. The delta explicitly leaves both passes' own behaviour
  unchanged (`tasks.md` 2.6). **Not obsolete.**
- `tests/unit/launch/infrastructure/driven/test_clickup_sync_projection.py::test_missing_folder_configuration_fails_the_run`
  — the delta states the unconfigured-folder obligation is *unaffected*.
  **Not obsolete.**
- `tests/unit/launch/infrastructure/driving/test_clickup_webhook*.py` — intake is
  explicitly unaffected. **Not obsolete.**
- `tests/integration/launch/test_launch_clickup_mapping.py` — the mapping store
  and the active-launch enumeration, neither changed here. **Not obsolete.**

So the finding is the stronger one — **no such test exists**, rather than merely
"none was found" — bounded to the glob searched. No existing test was edited,
deleted or disabled by this pass.

## Unresolved project questions

Each was assumed rather than asked, because a dispatched subagent has no channel
to ask on. Each names the assumption taken and the tests that depend on it. All
are **fixture** assumptions: correcting one is a fixture correction (failure
state 3), and what must survive unweakened is what each test asserts.

1. **How the job hands a launch to the two passes.** No artifact fixes a call
   shape. Assumed: the `Launch` aggregate appears somewhere in the call's
   arguments. `_product_of` in each file scans for it and `pytest.fail`s loudly
   rather than guessing. Depends on: every test in all three files.
2. **The collaborator names substituted on the job module** — `converge_launch`,
   `reconcile_launch`, `LaunchRepository`, `PlaybookRepository`, `session`.
   Probed on the module; each substitution fails loudly if the name is absent, so
   no test can go green against an unpatched real collaborator. Depends on: every
   test in all three files.
3. **The session provider's name and shape.** Assumed `session` is a zero-or-more
   argument async context manager yielding the shared `AsyncSession`, as
   `test_clickup_sync_job_stand_down.py` already assumes. `transaction` is
   patched too where present. Depends on: the rollback tests (#11) and both
   integration tests.
4. **How a contained failure is reported.** Assumed: the standard library's
   `logging`, which is the only report `design.md` names. The assertion accepts
   either the exception quoted in the message or attached as `exc_info`. Depends
   on: #2, #5, #12.
5. **The type of the aggregate error the run fails with.** No artifact names one.
   The tests assert only that *some* `Exception` is raised and what its `str()`
   names, so a purpose-built error class or a plain `RuntimeError` both satisfy
   them. Depends on: #3, #10, #11, #13.
6. **How a product identifier is rendered in a message.** `ProductId` is a frozen
   dataclass, so `repr` and `.value` differ. The assertions match on the bare
   `.value`, which is a substring of both. Depends on: #2, #3, #11, #12, #13, #10.
7. **`PlaybookNotReadyError`'s constructor signature** — probed the same four
   ways `test_clickup_sync_job_stand_down.py` probes it. Depends on: #5.
8. **`ClickUpMappingRepository`'s method names** — `record_list` / `list_id_for`
   / `record_task` / `task_for`, transcribed from
   `tests/integration/launch/test_launch_clickup_mapping.py`, which records them
   as invented there. Depends on: #9, #10.
9. **The project does not install the toolkit's `rules/test-manifest.md`
   fragment.** `AGENTS.md` carries the `ai-toolkit:development-workflow` and
   `ai-toolkit:project-foundation` managed blocks but no standing constraint
   directing that this manifest be read before implementing. Editing `AGENTS.md`
   is outside this pass's additive-only bound, so it was **not** done; the gap is
   raised here and in the completion report instead.

## What the implementation must make pass

`tasks.md` 2.1–2.5, mapped to the tests each must turn green:

| Task | Tests it must satisfy |
| --- | --- |
| 2.1 contain the pair, skip reconciliation where projection raised, continue the walk | #1, #6, #7, #13, #18, and both integration tests |
| 2.2 log each contained failure against its launch, with traceback | #2 |
| 2.3 roll the session back between launches; a raising rollback ends the walk and chains | #11, and integration #10 |
| 2.4 collect and raise one error naming every failed launch; raise nothing when none failed | #3, #4, #11, #13, integration #10 |
| 2.5 keep readiness and its stand-down above the loop | #5 |
| 2.6 leave the passes, the mapping store and the client untouched | #8, and the 17 unchanged existing `converge_launch`/`reconcile_launch` tests staying green |

This pass **adds tests and never subtracts**: no existing test was edited,
deleted or disabled, no implementation code was written, and nothing was written
outside the dispatched test-path glob except this manifest.
