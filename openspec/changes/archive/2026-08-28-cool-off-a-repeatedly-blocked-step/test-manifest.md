# Test manifest — `cool-off-a-repeatedly-blocked-step`

Written by `ai-toolkit:openspec-test-writer` before any implementation
exists. Not an artifact the OpenSpec schema knows about, so it does **not**
appear among the context files `openspec instructions apply` surfaces —
read it on purpose.

Derived strictly from
`openspec/changes/cool-off-a-repeatedly-blocked-step/specs/launch-step-automation/spec.md`,
with `proposal.md`, `design.md` and `tasks.md` read as the reasoning behind
it and `openspec/specs/launch-step-automation/spec.md` read to establish
what the two MODIFIED requirements supersede. **No implementation source
was read**, `automation_pass.py` included; the pass's current collaborator
names were established by `inspect.signature` at runtime, which is what
the existing `test_automation_pass.py` already does.

## What was written

One file, in the unit tier, mirroring the module under test:

```
tests/unit/launch/infrastructure/driving/test_automation_pass_repeat_backoff.py
```

26 tests. **This pass added tests and subtracted none** — no existing test
file was edited, deleted or disabled, and nothing was written outside the
dispatched test-path glob (`tests/**/test_*.py`) except this manifest.

## Baseline

Taken at the worktree root, before a line of the new file was written:

| command | result |
| --- | --- |
| `uv run pytest tests/unit tests/agents` | 1427 passed, 2 xfailed, 0 failed |
| `uv run pytest tests/integration` | 108 passed, 2 skipped |

A database **is** reachable here, so the integration tier really ran; both
skips are pre-existing seed-data skips (`test_playbook_authoring_roster_live.py`,
`test_registered_handlers_activate_nothing.py`) and neither bears on this
change.

## First run of the new tests

`uv run pytest tests/unit tests/agents` → **1428 passed, 25 failed, 2
xfailed**. The 25 failures are all in the new file; no pre-existing test
changed state.

Every failure is `ai-toolkit:testing`'s **first** state — the code ran and
produced a wrong value — or the seam probe's directive. None is an absent
import: `automation_pass.run_automation_pass` already exists, so the pass
executes and fails on what it does, exactly as `tasks.md` 1.3 requires.
The failure messages observed:

- "the handler was asked again on the next pass after repeating …"
- "the handler was asked again after re-blocking in different words"
- "the second, repeating recording did not cool the step off"
- "the pass never touched the backoff record …" (the vacuous-pass guard)
- "the pass returned normally after the restore itself failed"
- "expected exactly one report for the newly cooled-off step, got []"
- "no report was attempted …"
- "the pass accepts […], none of which is the backoff record this change adds"
- "…exposes no 24-hour constant other than `COOL_OFF`"

**One test passes on its first run and is not the fourth failure state:**
`test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass_when_the_outcome_differs`
states behaviour the change must *preserve* — a progressing handler keeps
its fifteen-minute cadence. Its docstring records that.

## Scenario accounting

23 `#### Scenario:` blocks appear in the delta spec. All 23 are accounted
for below; the count is the check.

### MODIFIED — *An automated step's handler is invoked by recurring work* (4)

The requirement statement gains a fourth openness condition; **all four
scenarios are textually unchanged** by the delta, so no new test is owed
for them and none was written.

| Scenario | Covered by |
| --- | --- |
| An unresolved automated step is invoked | existing `test_automation_pass.py::test_an_unresolved_automated_step_is_invoked` |
| A human step is never invoked | existing `test_automation_pass.py::test_a_human_step_is_never_invoked` |
| A resolved step is not invoked again | existing `test_automation_pass.py::test_a_resolved_step_is_not_invoked_again` |
| A graduated launch is left alone | existing `test_automation_pass.py::test_a_graduated_launch_is_left_alone` |

The statement's new clause — the fourth condition — is what the ADDED
requirement's ten scenarios exercise, below.

### MODIFIED — *A non-terminal outcome is recorded directly and never held for a decision* (2)

| Scenario | Covered by |
| --- | --- |
| A non-terminal outcome on a confirmable step is recorded, not held | unchanged; existing `test_automation_pass.py::test_a_non_terminal_outcome_on_a_confirmable_step_is_recorded_not_held` |
| A step reporting no progress is reconsidered on the next pass **(narrowed)** | `test_automation_pass_repeat_backoff.py::test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass_when_the_outcome_differs` |

### ADDED — *A handler that repeats itself is not asked again immediately* (10)

All in `test_automation_pass_repeat_backoff.py`.

| Scenario | Test |
| --- | --- |
| A cool-off is anchored to the repeat that caused it | `test_a_cool_off_is_anchored_to_the_repeat_that_caused_it` |
| A cool-off stops governing once the outcome differs from it | `test_a_cool_off_stops_governing_once_the_outcome_differs_from_it` |
| A step whose backoff record cannot be read is still invoked | `test_a_step_whose_backoff_record_cannot_be_read_is_still_invoked` |
| A failed backoff access does not cost the pass its other work | `test_a_failed_backoff_access_does_not_cost_the_pass_its_other_work` |
| A repeated non-terminal outcome is recorded and cools the step off | `test_a_repeated_non_terminal_outcome_is_recorded_and_cools_the_step_off[blocked]`, `[in-progress]`, `[not-started]` |
| A differently worded repeat still counts as a repeat | `test_a_differently_worded_repeat_still_counts_as_a_repeat` |
| A first non-terminal outcome does not cool the step off | `test_a_first_non_terminal_outcome_does_not_cool_the_step_off` |
| A changed outcome lifts the cool-off | `test_a_changed_outcome_lifts_the_cool_off` |
| A repeated step is asked again once the cool-off elapses | `test_a_repeated_step_is_asked_again_once_the_cool_off_elapses` |
| The rejection cool-off does not govern a repeat | `test_the_rejection_cool_off_does_not_govern_a_repeat` |

Three clauses of the statement carry no scenario and were tested anyway:

| Clause | Test |
| --- | --- |
| "independent of the cool-off placed after a rejection … SHALL NOT be affected by a change to the rejection cool-off" | `test_the_repeat_cool_off_is_independent_of_the_rejection_cool_off[shortened-…]`, `[lengthened-…]` |
| "a fixed property of the system rather than a configured one" (`tasks.md` 3.2: its own module constant) | `test_the_repeat_cool_off_is_a_fixed_constant_of_its_own` |
| "cannot read **or write** … the step SHALL be left eligible … the failure SHALL be reported"; "Where the shared store cannot be restored … the pass SHALL end and the run SHALL be recorded as failed" | `test_a_failed_backoff_write_leaves_the_step_eligible`, `test_a_restore_that_itself_fails_ends_the_walk_and_fails_the_run` |

### ADDED — *A step whose handler has stopped making progress is reported once* (7)

| Scenario | Test |
| --- | --- |
| A newly cooled-off step is reported | `test_a_newly_cooled_off_step_is_reported` |
| A step that stays stuck is not reported again | `test_a_step_that_stays_stuck_is_not_reported_again` |
| A step still stuck after the cool-off expires is not reported again | `test_a_step_still_stuck_after_the_cool_off_expires_is_not_reported_again` |
| A step that gets stuck again after moving is reported again | `test_a_step_that_gets_stuck_again_after_moving_is_reported_again` |
| A pass that cannot read the backoff record delivers no report | `test_a_pass_that_cannot_read_the_backoff_record_delivers_no_report` |
| A report that could not be delivered is not suppressed | `test_a_report_that_could_not_be_delivered_is_not_suppressed` |
| A failed report leaves the pass walking | `test_a_failed_report_leaves_the_pass_walking` |

One further test belongs to no scenario: `test_the_pass_accepts_a_backoff_record_and_a_report_seam` states
`tasks.md` 3.1 and 4.2's seam once, with a directive, so the other tests
fail on what they assert rather than each repeating it.

### Uncovered, recorded with the reason

| Not covered | Reason |
| --- | --- |
| Statement clause: "The judgement SHALL NOT be made from the launch journal." | Observable only negatively, and observed everywhere: the new file supplies the pass no journal collaborator at all, and every cool-off above engages without one. A positive test would have to pin a collaborator the requirement says must not exist. |
| Statement clause: "Two passes running over the same step at once MAY each deliver the report." | A permission, not an obligation; nothing is owed for a MAY, and the concurrency it describes has no signal at the pass level. |
| `tasks.md` 3.1's store-side obligation — noting a repeat against a different outcome kind clears the reported stamp. | Deliberately **not** modelled by the fake, so the pass's own lazy lift carries *A step that gets stuck again after moving is reported again* (see below). The accessor's own behaviour is an integration question against a table that does not exist yet. |
| `tasks.md` 2.3 / 2.4 — the Alembic revision, up and down. | A migration, not a stated scenario. `tests/integration/launch/` has no precedent for asserting one; the task is the verification. |
| Any integration-tier test at all. | Every scenario in this delta is stated over *a pass* and is observable at the unit tier with in-memory doubles, which is the level `test_automation_pass.py` already establishes for this same function. The one thing that would want the real database — the store accessors — has an entirely invented shape at this point, so an integration test would pin a fixture rather than a behaviour. A database **was** reachable, so this is a judgement, not a limitation. |

## Assertion provenance

**Specified** (traces to a delta-spec scenario or statement clause) — the
default throughout: which handler is invoked and how many times, whether
an outcome is recorded, how many reports are delivered, what a report
names, whether a failure is reported, whether the pass returns or raises,
and whether the remaining work is persisted after a fault. Each is marked
`SPECIFIED` at its site.

**Derived** (inferred; no requirement states it), each labelled at its
site and listed here so it is reviewable:

| Derived assertion | Where | Correction point |
| --- | --- | --- |
| The cool-off is **24 hours**. The spec fixes only that it is fixed and separate. | `REPEAT_COOL_OFF` | that constant |
| The repeat rule covers `NotStarted` and `InProgress`, not only `Blocked`. Read off the statement ("a non-terminal outcome … of the same kind"), which no scenario exercises for the two reasonless outcomes. | `test_a_repeated_non_terminal_outcome_is_recorded_and_cools_the_step_off[in-progress]`, `[not-started]` | the parametrisation |
| The pass runs every fifteen minutes, so "the next pass" is `NOW + 15m`. | `PASS_INTERVAL` | that constant |
| A *fault* is "reported" through a WARNING-or-above log record **or** a monitoring message. | `_reported_text` | that helper — it reads both, so no test pins the channel |
| "The run is recorded as failed" means the pass body raises; "a successful run" means it returns normally. | `test_a_restore_that_itself_fails…`, `test_a_failed_report_leaves_the_pass_walking` | the reading `test_clickup_sync_job_containment.py` and `test_clickup_field_configuration_check.py` already record for the same words |
| "Naming the launch" is satisfied by the product's name, its SKU **or** its identifier. | `_names_the_launch` | that helper |
| "Naming the step" is satisfied by the step's identifier **or** its name. | `_names_the_step` | that helper |

**Deliberately untested** — the five rows of the *Uncovered* table above,
plus the block of the same name at the foot of the test file.

## Where a naive test would have passed vacuously — and what stops it

`tasks.md` 1.2 names four traps. Each is closed, and the closure is
itself load-bearing:

1. **The differently-worded repeat.** `test_a_differently_worded_repeat_still_counts_as_a_repeat`
   drives the two wordings `proposal.md` quotes from the deployment's own
   journal, and opens with `assert Blocked(A) != Blocked(B)` so the
   premise is on the record: `Blocked` is a frozen dataclass whose
   equality includes `reason`, and a bare `==` would silently never
   match.
2. **The first non-terminal outcome.** `test_a_first_non_terminal_outcome_does_not_cool_the_step_off`
   asserts the **second** invocation happens, and then runs a **third**
   pass as a positive control in the same test — so the second assertion
   cannot be green merely because nothing ever backs off.
3. **The undelivered report.** `test_a_report_that_could_not_be_delivered_is_not_suppressed`
   drives a **failing** notifier, asserts nothing was stamped as
   reported, then repairs it and asserts the next pass attempts again.
4. **The poisoned session.** `_FakeSession` is transcribed from
   `tests/unit/launch/application/test_launch_journal_containment.py`: a
   failed access poisons it and every later use raises
   `PendingRollbackError` until it is rolled back. The launches read, the
   outcome recorder and the backoff store share one. A store that merely
   raised would pass whether or not the restoration was written.
   `test_a_failed_backoff_access_does_not_cost_the_pass_its_other_work`
   asserts the **remaining** steps' and launches' outcomes are still
   persisted.

Two further guards, not in `tasks.md`:

- **The split degrade is two tests, never one.**
  `test_a_step_whose_backoff_record_cannot_be_read_is_still_invoked`
  (degrades toward running) and
  `test_a_pass_that_cannot_read_the_backoff_record_delivers_no_report`
  (degrades toward silence). A single test asserting one half passes
  against an implementation that applied one default to both — the
  mistake the third review round caught.
- **`_require_backoff_reached`.** Several assertions ("the handler is
  invoked") are satisfied by the pass as it ships today. Those tests fail
  with a directive where the pass never consulted the record at all, so a
  green-because-absent result is never mistaken for coverage.

**One deliberate asymmetry, worth reviewing.** `_BackoffStore.note` is
*naive on purpose*: it writes the kind and the moment and leaves
`reported_at` exactly as it found it. `tasks.md` 3.1 puts the
stamp-clearing obligation inside the driven accessor, and a fake that
implemented it would do the implementation's work — *A step that gets
stuck again after moving is reported again* would then pass whether or not
anything in the pass had been written. As written, that scenario turns on
the pass's own **lazy lift** (`design.md` Decision 4: a row whose noted
outcome is not the step's currently recorded one governs neither the
cool-off nor the report suppression), which the delta requires
independently. An implementation that lazily lifts passes whether or not
its store also clears the stamp; one that relies on the store alone does
not.

## Obsolete tests

**One candidate. Not deleted, not edited — that judgement is the
implementer's.**

### Candidate 1 — for human confirmation

- **Test:** `tests/unit/launch/infrastructure/driving/test_automation_pass.py::test_a_step_reporting_no_progress_is_reconsidered_on_the_next_pass`
- **Superseded by:** the MODIFIED requirement *A non-terminal outcome is
  recorded directly and never held for a decision*, whose scenario *A
  step reporting no progress is reconsidered on the next pass* is narrowed
  from "a handler proposes a non-terminal outcome for a step" to "a
  handler proposes a non-terminal outcome **that differs from the one the
  step already carries**".
- **Evidence:** the test's docstring transcribes the served spec's WHEN
  verbatim ("WHEN a handler proposes a non-terminal outcome for a step,
  and a later pass runs"), which the delta replaces. Its body scripts one
  handler returning `Blocked("no confident node")` and runs two passes,
  asserting `len(handler.contexts) == 2` — i.e. it drives the *same*
  outcome twice, which under the delta is the repeat case, not the
  changed-outcome case its name now claims.
- **What it is not:** it is **not expected to go red**. Its recorder
  (`_RecordingOutcomes` in that file) collects keywords and never writes
  to the launch, so the step carries no outcome on either pass and both
  are the "first non-terminal outcome" case — which the ADDED scenario *A
  first non-terminal outcome does not cool the step off* still requires to
  re-invoke. What is superseded is its **attribution**, not its assertion.
- **Suggested handling, for the implementer to accept or reject:**
  re-attribute it (its name and docstring) to the ADDED scenario it now
  demonstrates, or narrow it to the revised WHEN by giving it a launch
  that already carries a different outcome. Deleting it would drop a live
  assertion. The same file's module docstring says it covers *A
  non-terminal outcome is recorded directly and never held for a
  decision* — "both scenarios"; that line drifts with this change too.

**Nothing else was found.** The search was bounded, as the dispatch
requires, to the test-path glob `tests/**/test_*.py`, by `grep` for
`reconsidered`, `next pass`, `invoked again`, `cool`, `COOL_OFF` and
`run_automation_pass`. No earlier `test-manifest.md` was supplied, so no
scenario-to-test index was available to widen it. **Read this as "none was
found by this search", not as "no such test exists"** — in particular, a
test bearing on the superseded openness rule that names neither the pass
entry point nor any of those words would not have been reached.

## Not obsolete, but it will break: two existing harnesses

Flagged because it is foreseeable and because the additive-only rule bars
me from acting on it.

`tests/unit/launch/infrastructure/driving/test_automation_pass.py` and
`tests/unit/launch/infrastructure/driving/test_retained_record_boundary.py`
each call `run_automation_pass` with a fixed keyword set that will not
include the two collaborators this change adds. If those parameters are
made **required**, both files fail with `TypeError` on every test.

Two routes, and the choice is the implementer's:

- Give the new parameters defaults. Cheapest, but a mis-wire then
  silently disables the whole feature in production rather than failing
  loudly — which is the class of fault `AGENTS.md` records
  `BOOTSTRAP_ADMIN_IDENTITY` costing a deploy over.
- Add the new collaborator to those two files' `_run_pass` helpers. That
  is a **fixture correction** (`ai-toolkit:testing`'s third failure
  state), not a weakening: no assertion changes. It is the route this
  manifest suggests.

Either way, no assertion in those files may be edited, relaxed or removed
to reach green.

## Unresolved project questions

Recorded rather than resolved: this pass ran non-interactively, with no
channel to ask on. `AGENTS.md` and `README.md` were read and answer none
of these.

1. **What the two new collaborators are called on `run_automation_pass`.**
   `tasks.md` 3.1 and 4.2 fix that they are *arguments*; no artifact names
   them. *Assumption taken:* the harness probes the entry point's
   signature for the first accepted name out of
   `_BACKOFF_ARGUMENT_NAMES` / `_REPORT_ARGUMENT_NAMES`, and supplies
   nothing where none matches, so the pass still runs. *Depends on it:*
   every test in the file. *Correction point:* those two tuples.
2. **The backoff store's accessor spellings and its row's attribute
   names.** *Assumption taken:* `read` / `note` / `mark_reported`, each
   absorbing `*args, **kwargs` with `_identify` recovering the launch,
   step, kind and moment; the row answers to several attribute spellings
   and its kind compares equal to a class, an instance or a name string
   alike. *Depends on it:* every test that seeds or inspects a row.
   *Correction point:* `_BackoffStore`, `_identify`, `_BackoffRow`,
   `_Kind`.
3. **How the shared store is restored after a fault.** `design.md`
   Decision 5 names the behaviour, not the mechanism. *Assumption taken:*
   modelled two ways at once — the store's own `rollback()` and
   `automation_pass.session` replaced by a provider yielding the same
   `_FakeSession`. *Depends on it:*
   `test_a_failed_backoff_access_does_not_cost_the_pass_its_other_work`,
   `test_a_restore_that_itself_fails_ends_the_walk_and_fails_the_run`.
4. **Which channel a backoff *access failure* is reported through.** The
   delta says "reported"; `design.md` says "to operators". *Assumption
   taken:* either a WARNING-or-above log record or a monitoring message
   satisfies it (`_reported_text` reads both). The *stuck-step report* is
   not assumed — `tasks.md` 4.2 fixes the monitoring notifier.
5. **Whether this repository wants the `ai-toolkit` `rules/test-manifest.md`
   fragment imported.** It is not referenced from `AGENTS.md` or
   `CLAUDE.md`, so nothing in the repository currently tells the next
   reader that this file exists. *Assumption taken:* none — the pointer
   is carried in the dispatch report instead. Worth deciding separately;
   it is not part of this change's scope.

No stack-specific testing skill beyond `python` was needed and none was
missing: `ai-toolkit:testing` and `ai-toolkit:python` both loaded.

## Instructions found inside the change's artifacts

None. Nothing in `proposal.md`, `design.md`, `tasks.md` or the delta specs
addressed the test author with a directive to skip, assume coverage, or
leave a requirement alone. `tasks.md` 1.2's four constraints are
*requirements on the tests*, which is what they were treated as.
