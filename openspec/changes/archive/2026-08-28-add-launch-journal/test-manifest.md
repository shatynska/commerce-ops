# Test manifest — `add-launch-journal`

Written by `ai-toolkit:openspec-test-writer` before any implementation
exists, from `specs/launch-journal/spec.md` alone. This file is **not** an
artifact the OpenSpec schema knows about, so it does not appear among
`openspec instructions apply`'s context files — read it on purpose.

Every test below is expected to be **red** until the change is
implemented. This pass is additive only: it added four test files and
edited, deleted or disabled nothing.

## Baseline

Scoped, not full — the scope is recorded so a later failure is
attributable.

| Command | Result |
| --- | --- |
| `uv run pytest tests/unit/launch tests/agents` | **630 passed**, 0 failed (2026-08-28, before any file was written) |
| `uv run pytest tests/integration/launch` | **66 skipped** — no database is configured on this machine (`DATABASE_URL` unset, no `.env.test`, no `.env`) |

The unit scope covers every directory the new unit tests live beside plus
the agents tier, which the `pre-commit` hook runs together with it. The
`shared`, `catalog`, `access`, `briefing` and `omni_agent` unit
directories were not run: this change touches no code they cover.

**The integration tier has no baseline and was never executed.** Nothing
on this machine could run it, so for
`tests/integration/launch/test_launch_journal_live.py` the distinction
between "fails on the absent target" and "fails on a fixture fault" is
**unestablished**. `tasks.md` 1.3 is discharged for the three unit files
and *not* for the integration file. Run that file first, with a database,
before trusting a red result there.

## What the new tests fail on today

| File | State |
| --- | --- |
| `tests/unit/launch/application/test_launch_journal_appends.py` | 20 failed — `TypeError: ... got an unexpected keyword argument 'journal'` |
| `tests/unit/launch/application/test_launch_journal_containment.py` | 4 failed — same `TypeError` |
| `tests/unit/launch/application/test_launch_journal_read.py` | collection error — `ImportError: cannot import name 'read_launch_journal'` |
| `tests/integration/launch/test_launch_journal_live.py` | collection error — same `ImportError` (never executed against a database) |

All four are failure **state 2** in `ai-toolkit:testing`: the target does
not exist, and nothing about the assertions has been exercised by these
runs. That the assertions *do* discriminate was established separately —
see *How the assertions were checked*, below.

Because two files fail at collection, `uv run pytest tests/unit` and
`uv run pytest tests/integration` currently **abort** rather than report
per-test results, and the `pre-commit` pytest hook is therefore red until
implementation lands. That is expected for a test-first pass; it is
called out because this project's hook runs the whole unit tree on every
commit.

## Scenario accounting

34 `#### Scenario:` blocks in the delta spec; **34 accounted for, 0
uncovered.** Two are covered twice, at two levels, and are marked so.

### R1 — Every accepted launch command appends exactly one journal entry

| Scenario | Test |
| --- | --- |
| A started launch is journaled | `tests/unit/launch/application/test_launch_journal_appends.py::test_a_started_launch_is_journaled` |
| A recorded step outcome is journaled | `…test_launch_journal_appends.py::test_a_recorded_step_outcome_is_journaled` |
| A non-terminal step outcome is journaled too | `…test_launch_journal_appends.py::test_a_non_terminal_step_outcome_is_journaled_too` |
| An outcome recorded from any source is journaled alike | `…test_launch_journal_appends.py::test_an_outcome_recorded_from_any_source_is_journaled_alike` |
| A recorded approval is journaled | `…test_launch_journal_appends.py::test_a_recorded_approval_is_journaled` |
| A rejecting approval is journaled too | `…test_launch_journal_appends.py::test_a_rejecting_approval_is_journaled_too` |
| A recorded metric attestation is journaled | `…test_launch_journal_appends.py::test_a_recorded_metric_attestation_is_journaled` |
| An opened gate is journaled | `…test_launch_journal_appends.py::test_an_opened_gate_is_journaled` |
| A graduation is journaled as a graduation | `…test_launch_journal_appends.py::test_a_graduation_is_journaled_as_a_graduation` |
| A moved launch date is journaled | `…test_launch_journal_appends.py::test_a_moved_launch_date_is_journaled` |

### R2 — A refused advance is journaled with the conditions that blocked it

| Scenario | Test |
| --- | --- |
| A refused advance is journaled with its unsatisfied conditions | `…test_launch_journal_appends.py::test_a_refused_advance_is_journaled_with_its_unsatisfied_conditions` |
| A refused advance still fails | `…test_launch_journal_appends.py::test_a_refused_advance_still_fails` |
| A condition satisfied later leaves the entry standing | `…test_launch_journal_appends.py::test_a_condition_satisfied_later_leaves_the_entry_standing` |

### R3 — An entry carries the labels the occurrence concerned

| Scenario | Test |
| --- | --- |
| An entry names the step as well as identifying it | `…test_launch_journal_appends.py::test_an_entry_names_the_step_as_well_as_identifying_it` |
| A step renamed later does not change an appended entry | `…test_launch_journal_appends.py::test_a_step_renamed_later_does_not_change_an_appended_entry` |
| A step retired later still reads by name | `…test_launch_journal_appends.py::test_a_step_retired_later_still_reads_by_name` |
| A refused advance's conditions are stored as the domain names them | `…test_launch_journal_appends.py::test_a_refused_advances_conditions_are_stored_as_the_domain_names_them` |

### R4 — An entry stores structure, never rendered prose

| Scenario | Test |
| --- | --- |
| An entry is stored as facts | `tests/unit/launch/application/test_launch_journal_read.py::test_an_entry_is_stored_as_facts` **and** `tests/integration/launch/test_launch_journal_live.py::test_an_entry_is_stored_as_facts_in_the_row` |
| Improved wording reaches entries already appended | `…test_launch_journal_read.py::test_improved_wording_reaches_entries_already_appended` **and** `tests/integration/launch/test_launch_journal_live.py::test_improved_wording_reaches_entries_already_appended` |

Covered twice on purpose. `tasks.md` 1.2 requires the assertion be made
against *what the repository wrote*: the unit pair inspects the entry the
use case hands the port (fast, runs at commit time), the integration pair
reads the row back with SQL (catches a repository that renders on the way
in even though the use case did not).

### R5 — Entries are appended, never replaced or deleted

| Scenario | Test |
| --- | --- |
| A second recording on the same step appends rather than replaces | `…test_launch_journal_appends.py::test_a_second_recording_on_the_same_step_appends_rather_than_replaces` |
| A replaced step outcome leaves the earlier entry standing | `…test_launch_journal_appends.py::test_a_replaced_step_outcome_leaves_the_earlier_entry_standing` |

### R6 — A failed append never fails the command it records

| Scenario | Test |
| --- | --- |
| A failed append leaves the command's own work standing | `tests/unit/launch/application/test_launch_journal_containment.py::test_a_failed_append_leaves_the_commands_own_work_standing` |
| A failed append does not prevent the graduation stamp | `…test_launch_journal_containment.py::test_a_failed_append_does_not_prevent_the_graduation_stamp` |
| A failed append on a refused advance leaves the refusal unchanged | `…test_launch_journal_containment.py::test_a_failed_append_on_a_refused_advance_leaves_the_refusal_unchanged` |
| A failed append is reported | `…test_launch_journal_containment.py::test_a_failed_append_is_reported` |

These take the **fake option** `tasks.md` 1.2 offers, not the real-session
one: `FakeSession` models a poisoned transaction — once a write fails,
every later use of the session raises `PendingRollbackError` until
`rollback()` is called — and the launch store, the journal and the catalog
stamp share one, as the five composing adapters share one real session. A
fake that merely raised would pass whether or not the rollback was
written, which is the trap `contain-a-failing-launch` recorded.

### R7 — One launch's journal is readable, most recent first

| Scenario | Test |
| --- | --- |
| A launch's journal is read most recent first | `tests/integration/launch/test_launch_journal_live.py::test_a_launchs_journal_is_read_most_recent_first` |
| Entries naming the same moment report the later append first | `tests/integration/launch/test_launch_journal_live.py::test_entries_naming_the_same_moment_report_the_later_append_first` |
| An entry reports what occurred, when, and what caused it | `tests/unit/launch/application/test_launch_journal_read.py::test_an_entry_reports_what_occurred_when_and_what_caused_it` |
| An occurrence naming nobody reports the command as its cause | `…test_launch_journal_read.py::test_an_occurrence_naming_nobody_reports_the_command_as_its_cause` |
| An out-of-scope launch reports an empty journal | `…test_launch_journal_read.py::test_an_out_of_scope_launch_reports_an_empty_journal` |
| A launch with nothing recorded reports an empty journal | `…test_launch_journal_read.py::test_a_launch_with_nothing_recorded_reports_an_empty_journal` |
| A product with no launch record reports an empty journal | `…test_launch_journal_read.py::test_a_product_with_no_launch_record_reports_an_empty_journal` |

The two ordering scenarios are in the integration tier deliberately.
Ordering is the repository's (`tasks.md` 6.2, `occurred_at DESC, sequence
DESC`) and the append sequence that breaks a tie exists only in the
database. A unit fake that sorted would test the fake; one that did not
would demand the use case re-sort, which no artifact asks of it.

### R8 — A launch's journal is retained for the life of the launch record

| Scenario | Test |
| --- | --- |
| The journal outlives the state it records | `tests/unit/launch/application/test_launch_journal_appends.py::test_the_journal_outlives_the_state_it_records` |
| Removing the launch record removes its journal | `tests/integration/launch/test_launch_journal_live.py::test_removing_the_launch_record_removes_its_journal` |

## Assertion provenance

Per `ai-toolkit:testing`, every assertion is specified, derived, or
deliberately untested. Each test file marks its own assertions inline with
`# SPECIFIED:` comments; the classes are summarised here.

**Specified** — traceable to the delta spec, or to a decision the change's
own `design.md` / `tasks.md` fixes (which the delta spec's requirements
are written over):

- how many entries a command appends, and of what `kind`
- which launch an entry is appended against
- which identifier is the entry's *subject*, per kind (`design.md`
  Decision 4)
- that a step's captured `subject_label` survives a later rename and a
  later retirement
- that a refused advance's conditions are the domain's own strings, in a
  list, identifying the step by identifier (Decision 7)
- that a refused advance's rejection, its unsatisfied conditions and the
  launch's current gate are unchanged by the journal — and unchanged again
  when the append fails
- that a failed append leaves the command's own work standing, the
  graduation stamp performed, and the failure logged at `error` naming the
  launch and the occurrence
- that no composed sentence is stored, and the wording is composed at read
- that the three empty-journal cases are indistinguishable
- ordering, and the cascade on launch-record removal

**Derived** — inferred, with no stated requirement behind them. Each is
marked in its file:

- that the port's methods are `async` (`LaunchStore`'s precedent)
- that the appended entry is a dataclass whose field set is *exactly* the
  fact columns of `design.md` Decision 4's table — the spec says "no
  composed sentence is among them"; reading that as "no field outside the
  fact set" is the derived step
- that the failure report goes through the standard library's `logging`
  (the only report the artifacts name)
- that the *whole* reported sequence is ordered, not only the three
  entries the most-recent-first scenario names
  (`test_a_launchs_journal_is_read_most_recent_first`)
- that another launch's journal survives one launch's removal
  (`test_removing_the_launch_record_removes_its_journal`) — the spec says
  entries are removed *with* their launch record, and that the cascade is
  keyed by launch rather than table-wide is the derived half
- that a rejecting decision is not *also* journaled as approving
  (`test_a_rejecting_approval_is_journaled_too`)

**Deliberately untested**, each with its reason:

- **The exact wording of `what` and `cause`.** `design.md` Decision 5 fixes
  that wording is composed at read and nothing about the sentence. Naming
  one would freeze the wording R4 exists to let improve. The tests assert
  that `what` is non-empty, draws on the entry's captured label, and is
  stored nowhere; and that `cause` names the recorder and source, or —
  where the occurrence names nobody — one of a tolerated set of ways to
  name the command (`_MOVE_COMMAND_TOKENS`).
- **The key names inside `details`.** Fixed nowhere in the artifacts. The
  tests ask whether a fact *appears* among what the entry carries
  (`_names`, comparing on alphanumerics only), rather than requiring a key
  or a spelling. `_condition_list` finds the refusal's condition list by
  its shape rather than its key.
- **Which of the eight kinds carry a `NULL` actor, as a rule.** Only the
  four an existing scenario reaches are asserted. The other four are
  `design.md` Decision 4's table, not the delta spec's.
- **The `kind` check constraint rejecting a ninth kind** (`tasks.md` 2.2).
  No delta-spec scenario states it, and it is a migration property; the
  migration's own up/down check is `tasks.md` 2.4.
- **A rollback that itself raises** (`tasks.md` 5.2). No scenario in the
  delta spec covers it — it is a design decision about the failure of the
  failure path. Worth a test if the implementer wants one; not derived
  here, so its absence is visible rather than silent.
- **The wiring of the five composing adapters** (`tasks.md` 8.1). No
  delta-spec scenario reaches an adapter, and `design.md` Decision 1's
  point is that a required argument makes an omission a type error and a
  test failure rather than something a test must hunt for. `mypy` is the
  check here.

## How the assertions were checked

An absent-target failure establishes only absence, so the assertions were
exercised separately: a throwaway `design.md`-faithful prototype was
monkeypatched onto `commerce_ops.launch.application` **in a scratch
directory outside the repository**, the three unit files were run against
it, and it was then deleted. Nothing from it was written into this
repository, and no implementation exists as a result of this pass.

- All **31** unit tests pass against a faithful prototype — so no test is
  unsatisfiable and no fixture is faulty.
- **Rollback omitted** (the exception caught, the session left poisoned):
  `test_a_failed_append_leaves_the_commands_own_work_standing` and
  `test_a_failed_append_does_not_prevent_the_graduation_stamp` both go
  red. This is the trap `tasks.md` 1.2 names, and the sharpest scenario
  behaves as it must.
- **A composed sentence stored in `details` and read straight back**: both
  R4 tests go red.
- **The graduating advance appending a `gate-opened` entry as well**:
  `test_a_graduation_is_journaled_as_a_graduation` goes red.
- **The step label not captured at append**: all three R3 label tests, plus
  the two R4 tests and the R7 what/when/cause test, go red.

The integration file was **not** part of this check — no database.

## Obsolete tests

**Not applicable.** Every delta in `specs/launch-journal/spec.md` is
`ADDED`, under a new capability that supersedes no existing requirement.
The change's own `proposal.md` records that `launch-instance` keeps every
requirement unchanged. No existing test is superseded, and none was
searched for, edited, deleted or disabled.

## Unresolved project questions

Each carries the assumption taken and the tests that depend on it.

1. **Are the `LaunchJournal` port's methods async?** `tasks.md` 3.2 names
   `append`, `read` and `rollback` without saying. *Assumed:* async, on
   `LaunchStore`'s precedent and because the repository holds an
   `AsyncSession`. *Depends on it:* every test in all four files (the
   fakes' `async def`). *Correction point:* the fake classes.
2. **What is the appended-entry dataclass called, and where does it live?**
   `tasks.md` 3.1 fixes neither; `LaunchJournalEntry` is taken by the ORM
   model (`tasks.md` 2.1). *Assumed:* nothing — no test imports it. They
   assert on the object's attributes, so any name works. *Depends on it:*
   nothing.
3. **What are the keys inside `details`?** Unfixed. *Assumed:* nothing —
   `_names` / `_condition_list` match on shape and content. *Depends on
   it:* every "names X" assertion. *Correction point:* `_facts` /
   `_names`.
4. **What is the journal repository's module and class name?**
   `tasks.md` 6.1 fixes the directory only. *Assumed:*
   `commerce_ops.launch.infrastructure.driven.launch_journal_repository`
   exporting `LaunchJournalRepository(session)`, on `LaunchRepository`'s
   precedent. *Depends on it:* the whole integration file.
5. **Is `read_launch_journal` exported from
   `commerce_ops.launch.application`?** `tasks.md` 3.4 puts the read on the
   public surface without naming the import. *Assumed:* yes, alongside the
   other use cases. *Depends on it:* the read and integration files.
6. **What words name "the command that produced it" as a cause?**
   Deliberately unfixed. *Assumed:* any of `launch-date-moved`, `launch
   date`, `move`. *Depends on it:*
   `test_an_occurrence_naming_nobody_reports_the_command_as_its_cause`.
   *Correction point:* `_MOVE_COMMAND_TOKENS`.
7. **Does an entry naming no moment reach the port with
   `occurred_at=None`?** `design.md` Decision 6 says the store stamps it;
   whether the application layer passes `None` or omits the field is not
   said. *Assumed:* the field is present and `None`, and the store stamps
   it — `FakeJournal` in the read file models the stamp for that reason.
   *Depends on it:*
   `test_an_occurrence_naming_nobody_reports_the_command_as_its_cause`.
8. **`ruff`'s import sorting for a module that does not exist yet.** The
   integration file's `launch_journal_repository` import currently sorts
   into the third-party block, because `ruff` cannot see a first-party
   module that has not been written. `ruff check` and `ruff format --check`
   pass as the file stands; once the module exists `ruff` will want the
   import moved into the first-party block. Run `ruff check --fix` on that
   file after `tasks.md` 6.1 and expect a one-hunk diff. Not a defect in
   the test.

No project-specific question about *runner, tiers or paths* went
unanswered: `AGENTS.md` fixes the test command (`uv run pytest`), the
three tiers, and where each tier's tests live, and this pass followed it.
`CLAUDE.md` is an `@AGENTS.md` include and adds nothing. The
`ai-toolkit:python` skill was loaded alongside `ai-toolkit:testing` for
the pytest idiom.

## Verification run on the new files

- `uv run ruff check` — clean on all four files.
- `uv run ruff format --check` — clean on all four files.
- `uv run mypy .` — the only errors touching these files are the absent
  target itself (`Unexpected keyword argument "journal"`, `has no
  attribute "read_launch_journal"`, and the missing
  `launch_journal_repository` module). Every other finding was fixed. Those
  errors disappear as the change is implemented; if any survives
  implementation, it is a real signature mismatch, not noise.
