# Test manifest — `restore-the-skipped-unit-tests`

Written by `openspec-test-writer`, 2026-09-01. **Not an artifact the OpenSpec
schema knows about**: it will not appear among `openspec instructions apply`'s
context files and must be read on purpose before implementing.

This pass **adds tests and never subtracts**. No existing test file was
edited, deleted, or disabled. One file was added:
`tests/unit/test_commit_time_tier_skip_guard.py`. Nothing else in the
repository was written.

---

## Specs status: exempt, with one carve-out

`.openspec.yaml` sets `skip_specs: true` and the change carries no delta
specs. That combination is the **specs-exempt** route: no new tests are owed
from delta scenarios, and the obligation is that the existing suite stays
green through the change.

The scenario ledger is therefore empty by construction — **0 scenarios in the
delta specs, 0 accounted for** — and this is a file read (`.openspec.yaml`),
not a judgment that tests seemed unnecessary.

The exemption was **not** taken as the whole answer, because the dispatch
named a qualification the change's own `design.md` Risks section already
concedes: section 4 adds a **new guard** — a `pytest_sessionfinish` hook in a
new `tests/conftest.py` — which is new behaviour, carries no automated test,
and is verified by `tasks.md` 4.5/4.6/4.7 only by a manual procedure
(temporarily add a skip, observe, revert). That guard is what the added file
covers. Its assertions trace to `tasks.md` section 4 and `design.md`
Decision 3, which are planning artifacts rather than delta specs; every one
is classified below on that basis.

### What was deliberately **not** written

Nothing for the forty-four restored tests. They already exist, they are not
authored by this change, and this pass never edits or authors over an
existing test. Writing new tests alongside them would duplicate coverage the
change's own premise says is already correct — `proposal.md`: "Every
requirement the restored tests cover is already specified and already
correct." The change's obligation for those forty-four is that they *run*,
which is a measurement (`tasks.md` 1.1, 5.1), not a test to be written.

---

## Baseline

**Full**, not scoped. `uv run pytest tests/unit tests/agents`, on the tree as
this pass found it (branch `restore-the-skipped-unit-tests`, working tree
clean):

```
1979 passed, 44 skipped in 48.12s
```

This matches `design.md`'s recorded baseline exactly, so the number
`tasks.md` 1.1 asks to re-measure has not moved again since `design.md` was
written.

`uv run pytest tests/integration` was **not** run: it is outside what this
pass adds to, and no test written here touches that tier.

After adding the one file, the same command reports:

```
10 failed, 1979 passed, 48.10s   (44 skipped, unchanged)
```

The passed and skipped counts are identical to the baseline. All ten
failures are the new file's, all on the absent target.

---

## What the new tests establish, and what they do not

`tests/unit/test_commit_time_tier_skip_guard.py` — 8 test functions, 10
cases after parametrisation.

**Failure state: the target does not exist.** `tests/conftest.py` has not
been written (task 4.1 is unimplemented), so every case fails in
`_guard_source` with a message saying so. Per the `testing` standard this is
the second of the four states: it establishes that the target is absent and
**nothing** about whether the assertions discriminate. Do not create
`tests/conftest.py` to make the file execute — that is task 4.1's job.

**Discrimination was established separately.** Because a target-absent
failure proves nothing about assertion quality, the file was run outside the
repository against seven reference guards — one correct, six deliberately
broken. Results:

| reference guard | outcome | caught by |
|---|---|---|
| correct | **10 passed** | — (assertions are satisfiable) |
| reads collection, not reports | 7 failed | the fixture-skip case and 6 more |
| fails every session unconditionally | 10 failed | the three silent cases |
| does not distinguish `xfail` | 1 failed | exactly the `xfail` case |
| no path filter (guards `tests/integration` too) | 1 failed | exactly the integration case |
| reports a skip but names neither test nor reason | 7 failed | the naming assertions |
| raises instead of setting `session.exitstatus` | 7 failed | `_assert_failed_cleanly` |

Those reference guards live only in this session's scratchpad, are **not**
part of the repository, and nothing in the delivered file depends on how any
of them was written. The exercise establishes that the ten cases are neither
vacuous nor unsatisfiable; it does not stand in for running them against the
real guard once task 4.1 lands.

### Case ledger

Each name below is selectable individually, e.g.
`uv run pytest "tests/unit/test_commit_time_tier_skip_guard.py::test_a_skip_in_the_unit_tier_fails_the_session"`.

| test | covers | classification |
|---|---|---|
| `test_a_skip_in_the_unit_tier_fails_the_session` | 4.1, 4.5 (`tests/unit` half) | specified |
| `test_a_skip_raised_by_an_autouse_fixture_fails_the_session` | 4.2 — reports, not collection | specified |
| `test_a_skip_in_the_agents_tier_fails_when_that_tier_runs_alone[pytest tests/agents]` | 4.1, 4.5 (`tests/agents` half), Decision 3's placement | specified |
| `test_a_skip_in_the_agents_tier_fails_when_that_tier_runs_alone[cd tests/agents && pytest .]` | Decision 3, "rootdir resolution does not depend on cwd" | specified |
| `test_every_skipped_test_is_named` | 4.1 "naming each one and its reason", plural | specified (`pytest.skip`) + derived (`skipif`) |
| `test_the_guard_reaches_a_hand_run[one file]` | Decision 3, single-file hand-run | specified |
| `test_the_guard_reaches_a_hand_run[one nodeid]` | Decision 3, bare nodeid | specified |
| `test_the_integration_tier_may_still_skip` | 4.3, 4.7 — false positive absent, forced | specified |
| `test_an_expected_failure_is_not_treated_as_a_skip` | 4.4 — `xfail` is not a skip | specified |
| `test_a_run_with_no_skips_leaves_the_session_alone` | the control | **derived** |

`_assert_failed_cleanly` runs inside every case: 4.2a, that the guard fails
by setting `session.exitstatus` rather than letting an exception escape.

### Derived assertions, stated plainly

Two, both flagged in the file's own docstring:

1. **A run with no skip at all must still exit zero.** No task states it.
   Without it, every firing case is satisfied by a guard that fails every
   session unconditionally — confirmed by reference guard C, which passes
   nothing once this case exists and would otherwise have been invisible.
2. **A `skipif` marker counts as a skip.** `tasks.md` names `pytest.skip`
   and an autouse fixture. `skipif` produces the same setup-time skipped
   report (measured), and the two conditional skips `tasks.md` 4.6
   inventories are of that kind — but no task says so.

### Deliberately untested

- **`pytest.skip(..., allow_module_level=True)`.** See *Findings* below.
  Neither asserted to fire nor asserted not to fire, on purpose.
- **`tasks.md` 4.6's `git`-absent case.** It asks what two real, existing
  tests do when `git` leaves `PATH` — a question about those tests and the
  machine, not about the guard's logic. The guard's half of it is
  `test_a_skip_in_the_unit_tier_fails_the_session`. Left to 4.6's procedure.
- **`tasks.md` 4.2a's "no work at import time".** A property of how the
  guard is written, not of what a session does; no black-box run observes it.
- **The guard's exact wording, its exit code beyond being non-zero, and
  where it writes.** A guard may phrase its report however it likes.

---

## Obsolete tests

**Not applicable.** The change carries no delta specs at all, and therefore
no `MODIFIED`, `REMOVED` or `RENAMED` delta — the operations that can
supersede an existing test. Nothing here supersedes anything.

Stated as a reason rather than as an empty list, deliberately. Note
separately that this pass added a file and edited none, so no existing test
was touched by any route.

---

## Findings against the change's artifacts

Raised, not acted on. This pass does not edit `proposal.md`, `design.md`,
`tasks.md`, or `.openspec.yaml` — revising them is
`openspec-update-change`'s job.

### Finding 1 — a whole-file skip the specified guard cannot see

`design.md` Decision 3 and `tasks.md` 4.1 state the goal as "a blanket skip
cannot silently take a file out of the commit-time tier again". `tasks.md`
4.2 then fixes the mechanism: read `TestReport`s, not collection.

Measured against pytest 9.1.1: `pytest.skip("...", allow_module_level=True)`
at the top of a test module skips **the entire file** and produces **no
`TestReport` whatsoever** — only a `CollectReport` with outcome `skipped`.
A guard reading `TestReport`s therefore cannot see it, and a file removed
from the tier that way passes the guard silently.

This does not affect the historical defect: both deleted fixtures skip
during *setup*, which does produce `TestReport`s, so the guard as specified
does catch what actually happened. The gap is between the guard's stated
*goal* and its specified *mechanism*.

Not written as a test in either direction: asserting the guard catches it
would contradict a stated task and impose a requirement nobody agreed to;
asserting it does not would freeze the gap into the suite.

### Finding 2 — `tasks.md` 4.2a's stated symptom is wrong for this pytest

4.2a says an exception raised inside `pytest_sessionfinish` "surfaces as
`INTERNALERROR`, not as the clean failing session naming each skipped test
that 4.5 asserts."

Against pytest 9.1.1 it does not. A raise there produces a raw `Traceback`
on stderr through `pluggy`, naming the hook, with **no `INTERNALERROR`
banner anywhere**, and exit code 1.

This mattered concretely: the first version of `_assert_failed_cleanly`
keyed on the literal string `INTERNALERROR` and **passed** against a
reference guard that raised — the exact mistake 4.2a warns about. The
assertion now looks for either shape. 4.2a's *advice* is unaffected and
correct; only its stated symptom is wrong.

### Finding 3 — `pytester` is not available, which constrains 4.5's automation

`pytest --fixtures` lists no `pytester`: the plugin is not registered by
default and the project neither enables nor uses it anywhere. Enabling it
would mean `pytest_plugins = "pytester"` in a conftest — for this file, that
means `tests/conftest.py`, which is the file under test — and would register
the plugin suite-wide. Recorded so that a future reader does not assume the
obvious tool was overlooked. The subprocess-plus-synthetic-tree approach
used instead follows
`tests/unit/test_handler_registration_is_cheap.py`,
`tests/unit/test_registrations_across_processes.py` and
`tests/unit/test_integration_tier_database_resolution.py`.

---

## Unresolved project questions

Recorded rather than resolved silently; this pass had no channel to ask on.

1. **Does an automated test of the guard belong in the change's scope at
   all?** `design.md` argues the `openspec-test-writer` binding does not fit
   this change, and the reviewer accepted that across three rounds while
   raising the section-4 qualification this file answers. `tasks.md` has no
   task for "write a test for the guard", so the added file has no task to
   tick. *Assumption taken:* it is wanted, per the dispatch. *Depends on it:*
   the whole of `tests/unit/test_commit_time_tier_skip_guard.py`. If the
   answer is no, delete the file — nothing else in this pass depends on it.

2. **Is a ~4s subprocess cost acceptable in the commit-time tier?**
   `AGENTS.md` defines `tests/unit` as "fast, mocked" with "no network/IO
   cost"; ten subprocess pytest runs cost roughly 4s measured, against a
   48s tier the change already accepts growing by ~13s. Two existing files
   in the same tier already spawn subprocesses, so the precedent is
   established, but no convention states a budget. *Assumption taken:* 4s is
   acceptable given that precedent. *Depends on it:* every case in the file.
   If not, the parametrised cases are the cheapest to drop.

3. **Where does a repo-level test of test infrastructure belong?**
   `AGENTS.md` prescribes `tests/unit/<module>/<layer>/`, and the guard is
   neither a module nor a layer. *Assumption taken:* the top level of
   `tests/unit/`, following `test_integration_tier_database_resolution.py`,
   `test_dockerfile_runtime_sync.py` and their neighbours. *Depends on it:*
   the file's path only, and with it the `parents[1]` that locates
   `tests/conftest.py`. Moving the file means correcting that constant.

---

## What the implementation step must make pass

1. `tests/unit/test_commit_time_tier_skip_guard.py` — all 10 cases, once
   task 4.1's `tests/conftest.py` exists. They currently fail on the absent
   target and are the executable form of `tasks.md` 4.5 and 4.7.
2. Everything already green: **1979 passed** must not fall, and by 5.1 must
   become 2023 as the 44 skips are restored.
3. **0 skipped** under `tests/unit` and `tests/agents` — which the guard
   itself then enforces.

Two cases are worth singling out, because a guard can be written to satisfy
the rest while failing them and still look correct:

- `test_a_skip_raised_by_an_autouse_fixture_fails_the_session` — fails if
  the guard is written against `pytest_collection_modifyitems`, which is the
  vacuous implementation `tasks.md` 4.2 exists to forbid.
- `test_a_skip_in_the_agents_tier_fails_when_that_tier_runs_alone` — fails
  if the guard is placed in `tests/unit/conftest.py`, which is the placement
  `design.md` Decision 3 rejected.
