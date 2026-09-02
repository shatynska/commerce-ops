# Test manifest — `restore-the-skipped-integration-tests`

Written by `ai-toolkit:openspec-test-writer` on 2026-09-02, before any of
this change's implementation existed. Not an artifact the OpenSpec schema
defines, so `openspec instructions apply` does not surface it — it is read
on purpose or not at all.

Everything below traces to `specs/deploy-pipeline/spec.md` (the change's one
delta, a `MODIFIED` requirement), to `tasks.md`, or to `design.md`. No
implementation source was read: the pre-change requirement was established
from `openspec/specs/deploy-pipeline/spec.md:7-35`, not from `ci.yml` or
from `tests/conftest.py`'s behaviour. `tests/conftest.py` *was* read — it is
test infrastructure inside the dispatched test-path glob and the subject the
new tests copy verbatim into a synthetic tree, not the implementation of any
requirement under test here.

## Baseline

**Scoped**, and the scope is the whole commit-time tier, which is where every
new test lands:

```
uv run pytest tests/unit tests/agents
→ 2064 passed in 60.55s          (0 skipped, 0 failed)
```

`tests/integration` was deliberately not run for the baseline. Nothing this
pass wrote lands there, and the tier's numbers on this machine are already
recorded in `proposal.md` — Impact from a measurement this pass did not
repeat and does not restate as its own.

After writing, the same scoped command gives **4 failed, 2072 passed** — the
baseline's 2064 plus this pass's 12, minus the 4 the change has yet to make
pass. No previously-passing test changed state.

## New test file

`tests/unit/test_integration_tier_skip_guard.py` — 12 runner-selectable
cases. Nothing else was written; `tests/conftest.py` was not touched, and
neither was `tests/unit/test_commit_time_tier_skip_guard.py`.

**Level.** Commit-time tier (`tests/unit`), not `tests/integration`, per the
level rule: the smallest unit that can observe the outcome. The subject is
what a *pytest session* does with a skipped report, which a child `pytest`
over a synthetic tree in `tmp_path` observes fully. No database is involved
in the guard's logic at any point, so raising the level to the integration
tier would buy no evidence and would put the file inside the very tier whose
guarding it exercises.

**Mechanism.** Inherited from `tests/unit/test_commit_time_tier_skip_guard.py`
— a synthetic three-tier tree, the real `tests/conftest.py` copied in
verbatim, a child `pytest` run with an environment built from scratch. The
helpers are duplicated rather than imported: `tasks.md` 5.3 sends the
implementer back into that file, and an import would let that edit break
this one. The child environment is what makes `COMMERCE_OPS_REQUIRE_DATABASE`
one dict entry, present (`"1"`) or absent.

## Scenario accounting

The delta carries **nine** `#### Scenario:` blocks. All nine are accounted
for below, exactly once each.

| # | Scenario | Status |
| --- | --- | --- |
| 1 | Pull request with a failing check is blocked | uncovered — unchanged by this delta |
| 2 | Validation requires no deploy secret | uncovered — unchanged by this delta |
| 3 | The integration tier is exercised, not skipped | uncovered — revised clause is not unit-testable |
| 4 | A gate with no database configured fails rather than passing | already covered, pre-existing test |
| 5 | A gate whose database is unreachable fails rather than passing | uncovered — unchanged by this delta |
| 6 | A test the gate's database does not satisfy fails rather than skipping | **covered, new** |
| 7 | A test skipped for an unmet precondition fails rather than passing | **covered, new** |
| 8 | An expected failure is not treated as a skip | **covered, new** |
| 9 | A developer's run is not held to the gate's rule | **covered, new** |

### 6. A test the gate's database does not satisfy fails rather than skipping

Covered by, in `tests/unit/test_integration_tier_skip_guard.py`:

- `test_an_integration_test_declining_the_gates_database_fails_the_gate`
- `test_a_whole_integration_module_skipped_at_collection_fails_the_gate`

The first is the scenario's own shape, modelled on the real one: an autouse
fixture inspecting the resolved database name and skipping during *setup*
(`tests/integration/launch/test_playbook_readiness_live.py:126`). The second
is the same decline written module-level, which produces a `CollectReport`
and no `TestReport`; `tasks.md` 2.1 requires both hooks be reused, and
`tests/conftest.py`'s own docstring records that a guard reading reports
alone is blind to it.

Assertions and their provenance:

| assertion | class |
| --- | --- |
| the session exits non-zero | SPECIFIED — "THEN the job SHALL fail" |
| the skipped test's nodeid appears in the output | SPECIFIED — "SHALL name that test" |
| the skip's reason appears in the output | SPECIFIED — "and the reason it declined" |
| no exception escaped the guard's hook | SPECIFIED — `tests/conftest.py`'s stated rule, carried over from `restore-the-skipped-unit-tests` 4.2a; a session that dies in the hook names neither the test nor the reason |

### 7. A test skipped for an unmet precondition fails rather than passing

Covered by
`test_an_integration_test_skipped_for_an_unmet_precondition_fails_the_gate`.

Kept a separate test from scenario 6's rather than a parametrisation of it,
deliberately: the two are mechanically identical to the guard and differ
only in the skip's *reason*, which is exactly the distinction the widening
turns on. A guard that fired only on database-flavoured reasons would pass
scenario 6 and fail here. The reason is transcribed from the real one
(`tests/integration/launch/test_registered_handlers_activate_nothing.py:345`,
"nothing here to discriminate on"), which has nothing to do with a database.

Same four assertions, same classes, all SPECIFIED by this scenario's own
THENs.

### 8. An expected failure is not treated as a skip

Covered by
`test_an_expected_failure_in_the_integration_tier_is_not_treated_as_a_skip`.

| assertion | class |
| --- | --- |
| the session exits zero with an `xfail`ed integration test present, under the marker | SPECIFIED — "the job SHALL NOT fail on account of it" |
| the session's output says `xfailed` | SPECIFIED — "SHALL report it as an expected failure" |
| the `xfail`ed test's nodeid is absent from the output | SPECIFIED — "rather than as a skip". Non-vacuous because the synthetic tree omits `-rs`: pytest names nothing itself, so a nodeid could only be the guard listing it among the skips |

### 9. A developer's run is not held to the gate's rule

Covered by three tests, one per THEN plus the real-configuration half:

- `test_a_developers_run_is_not_failed_by_a_skipped_integration_test` —
  SPECIFIED, "SHALL NOT fail on account of the skip". Carries both skip
  shapes (body and module-level), so an implementation that conditions only
  one of the two hooks on the marker fails here.
- `test_a_developers_run_still_reports_the_skipped_test_and_its_reason` —
  SPECIFIED, "the run SHALL report the skip and its reason". Runs the
  synthetic tree with `-rs` on the command line, because the tree omits it
  from `addopts` for the reason the file's docstring gives.
- `test_the_projects_own_configuration_reports_skips` — SPECIFIED, same
  clause, real subject: that `pyproject.toml` actually sets `-rs`, without
  which "the run SHALL report the skip and its reason" is false of an actual
  `uv run pytest tests/integration`. Asserted against the file's text rather
  than this session's resolved options, which any `-o` on the invocation
  could have overridden.

### 1, 2, 5 — uncovered, unchanged by this delta

Their text is identical in `openspec/specs/deploy-pipeline/spec.md:15-35` and
in the delta. Each is a property of the GitHub Actions job — that a failing
check blocks the PR, that no deploy secret is read, that an unreachable
database fails the gate — observable only by running the workflow, and none
is touched by this change. `tasks.md` lists no work against them. Writing new
tests for them here would be scope this change did not ask for.

Scenario 5 has one edge worth naming, since it is the closest of the three to
this change: the delta re-anchors the reachability carve-out into its own
paragraph. The re-anchoring changes where the sentence sits, not what it
says, and its operative half — such a test "SHALL run, and is subject to the
skip rule like any other" — is the rule scenarios 6 and 7 already assert.

### 3 — uncovered, and the revised clause is not unit-testable here

The delta revises this scenario's first THEN from "with the schema already
applied" to "with the schema **and the deployed seed** already applied". That
is a property of how `ci.yml` prepares its service container, verified by
`tasks.md` 1.3, 7.3 and 7.5 — running the real tier against a database
prepared that way and reading `137 passed, 0 skipped`. No unit-tier assertion
can establish it: a test grepping `ci.yml` for a `seed_playbook` line would
assert the workflow's text, not that the tier met a seeded step set.
`design.md` Decision 4 states the clause changes no behaviour at all — the
job has seeded since `seed-the-reference-step-set`; the specification is
catching up with the workflow.

Its second THEN — "SHALL NOT pass on a run in which that tier was skipped for
want of a database" — is unchanged and already covered by scenario 4's test
below.

### 4 — already covered, no new test

`tests/unit/test_integration_tier_database_resolution.py::test_with_the_flag_an_absent_database_fails`
covers it, and its sibling `test_without_the_flag_an_absent_database_skips`
covers the developer-machine half of the same mechanism. Neither is
superseded: the delta widens the rule *around* the absent-database case
without altering it, and both tests continue to state what the requirement
states. They are named here so their coverage is visible rather than assumed,
not as work owed.

## Assertions not traceable to a scenario

Three tests assert things the delta's *prose* or `tasks.md` requires but no
scenario states. They are listed separately so a reviewer can see they were
invented against a stated artifact rather than against the author's judgment.

| test | class | traces to |
| --- | --- | --- |
| `test_the_commit_time_tiers_stay_guarded_whatever_the_marker_says` (2 cases) | SPECIFIED | The requirement scopes the exemption to *the integration tier*; `proposal.md` — Capabilities: the widened rule "reads on **every** tier the gate runs, `tests/unit` and `tests/agents` included", and "a skip in the commit-time tiers fails a developer's run today and continues to" |
| `test_the_session_is_judged_by_the_marker_as_the_session_began` (2 cases) | SPECIFIED | `tasks.md` 2.2 — read the flag once, where the tier set is decided, "so a test that changes the environment mid-session must not change what the session is held to" |
| `test_a_clean_integration_run_under_the_marker_is_left_alone` | **DERIVED** | Nothing states it. It is the control: all three firing cases are satisfied by a guard that fails every session in which the marker is set, and this is what tells the two apart |

The first is not merely a nicety — without it, scenario 9 is satisfied by an
implementation that makes the *whole* guard conditional on the marker,
silently returning `tests/unit` and `tests/agents` to the state that lost
forty-four tests in one afternoon, while every other case in the file still
passed. Verified: that reference guard fails exactly this case and nothing
else.

## Deliberately untested

- **`COMMERCE_OPS_REQUIRE_DATABASE` set to the empty string.** See the
  unresolved question below. No assertion depends on the answer: every case
  sets the marker to `"1"` or omits the key entirely.
- **The reachability carve-out** (scenario 5's re-anchored paragraph). It
  states that such a test SHALL run and is subject to the skip rule like any
  other — which is the rule scenarios 6 and 7 already assert. It adds no
  behaviour distinguishable at the guard, whose only inputs are a skipped
  report and its path.
- **`ci.yml`'s database name (`tasks.md` §1) and the deleted integration test
  (§3).** Both are verified by running the real tier (7.3, 7.5). A unit test
  grepping a workflow file's text would assert the text, not the outcome.
- **The guard's wording, its exit code beyond being non-zero, and where it
  writes.** The requirement constrains that the gate names the test and the
  reason, not how it phrases the naming.

## Expected first-run state

Measured on the tree as this pass found it — `_GUARDED_TIERS` is
`("unit", "agents")` and unconditional, so the integration half does not
exist.

```
uv run pytest tests/unit/test_integration_tier_skip_guard.py
→ 4 failed, 8 passed
```

**Failing — these are what §2 must make pass:**

| test | what its failure establishes |
| --- | --- |
| `test_an_integration_test_declining_the_gates_database_fails_the_gate` | State 1 of the four `testing` names — *the code ran and produced a wrong value*. The guard exists, the child session ran to completion, and it exited 0 with a skipped integration test present. Not an absent target; the assertions executed and discriminated |
| `test_an_integration_test_skipped_for_an_unmet_precondition_fails_the_gate` | same |
| `test_a_whole_integration_module_skipped_at_collection_fails_the_gate` | same |
| `test_the_session_is_judged_by_the_marker_as_the_session_began[marker unset mid-session]` | same — it requires the guard to fire under the marker, so it fails for the same absence as the three above, not for anything about mid-session mutation |

**Passing, and two of them vacuously.** Recorded because a passing test on a
first run is otherwise an alarm:

| test | why it passes today |
| --- | --- |
| `test_a_developers_run_is_not_failed_by_a_skipped_integration_test` | Vacuous — the tier is excluded today whatever the marker says. Becomes discriminating the moment §2 lands |
| `test_a_developers_run_still_reports_the_skipped_test_and_its_reason` | Half vacuous — the guard's silence is vacuous today; the `-rs` reporting half is real now |
| `test_the_session_is_judged_by_the_marker_as_the_session_began[marker set mid-session]` | Vacuous, same reason |
| `test_an_expected_failure_in_the_integration_tier_is_not_treated_as_a_skip` | Partly real — the `xfailed` reporting is pytest's and is real; the guard's silence is vacuous until §2 |
| `test_the_projects_own_configuration_reports_skips` | Fully real — `pyproject.toml` carries `-rs` today |
| `test_the_commit_time_tiers_stay_guarded_whatever_the_marker_says` (both) | Fully real — the commit-time guard exists and fires |
| `test_a_clean_integration_run_under_the_marker_is_left_alone` | Fully real |

**That the assertions discriminate was established separately**, the way
`test_commit_time_tier_skip_guard.py` established its own: by running a copy
of the file against seven reference guards synthesized **outside this
repository**, in a scratch directory, with the copy repointed at each. None
of them is part of this repository and nothing in the committed file depends
on how any was written.

| reference guard | cases it fails |
| --- | --- |
| correct (integration added to the tier set when the marker is set, read once) | none — all 12 pass |
| integration guarded unconditionally | both developer-machine cases, and `[marker set mid-session]` |
| the *whole* tier set made conditional on the marker | `...stay_guarded_whatever_the_marker_says[on a developer's machine]`, and nothing else |
| marker re-read per report instead of once | both `...judged_by_the_marker_as_the_session_began` cases |
| collect hook left blind to the new tier | `...module_skipped_at_collection_fails_the_gate`, and nothing else |
| `wasxfail` exclusion removed | `...expected_failure...is_not_treated_as_a_skip`, and nothing else |
| fires correctly but reports a count instead of names | all six naming cases |

So the file's failing cases are failing on the change's absence, and its
passing cases are not passing because the assertions are inert.

## Obsolete tests — candidates for human confirmation

**Not deleted, not edited, not renamed by this pass.** Each entry is the
input to someone else's destructive action, so each carries its evidence.
Both were found within the dispatched test-path glob `tests/**/test_*.py`;
no earlier `test-manifest.md` was supplied to this dispatch, so the search
drew on the glob alone.

### 1. `tests/unit/test_commit_time_tier_skip_guard.py::test_the_integration_tier_may_still_skip`

- **Superseded by:** the `MODIFIED` *Pull Request Validation Gate*
  requirement — "Where the gate runs a tier, **any** test skipped in that
  tier SHALL fail the gate", read together with the exemption's scope: "Where
  the gate's own marker is absent — a developer's machine — the integration
  tier SHALL skip as it does today."
- **Evidence:** the test's own docstring states the exclusion as
  unconditional and cites `AGENTS.md` as its authority — "`tests/integration`
  skips legitimately and by specification when no database resolves
  (`AGENTS.md`)" — and its failure message says "the path filter … is what
  must exclude that tier (tasks.md 4.3)", with no condition attached. After
  this change the exclusion holds only where the marker is absent.
- **Why it is worth acting on:** it does **not** fail after the change. It
  keeps passing by accident, because `_run` does not put
  `COMMERCE_OPS_REQUIRE_DATABASE` into the child environment, so its session
  is always a developer's-machine session. A test that still passes while its
  docstring contradicts the requirement is misleading rather than broken, and
  nothing in a green suite will report it.
- **Already assigned:** `tasks.md` 5.3 gives the rewrite to whoever
  implements §2 — rename and re-document, not delete. The property it holds
  is still real; only its stated scope is wrong.
- **Adjacent, not a test:** the same file's module docstring describes the
  guard as covering the commit-time tier alone (`:1-6`, `:179-181`'s
  `UNGUARDED_TIER = "integration"`). `tasks.md` 5.4 covers it. Named here
  only so the rewrite is not left half-done.

### 2. `tests/integration/launch/test_registered_handlers_activate_nothing.py::test_no_seeded_automated_step_is_activated_by_its_handler_existing`

- **Superseded by:** the same widened clause. Under the gate this test can
  only skip, and a skip now fails the gate.
- **Evidence:** its body reads
  `resolvable = [step for step in seeded_automated if step.handler in registered]`
  and calls `pytest.skip("no seeded automated step names a handler this
  deployment registers, so there is nothing here to discriminate on …")` when
  that list is empty (`:343-347`). `design.md` Decision 3 establishes the
  list is empty on *every* run of every correctly prepared database.
- **Already assigned:** `tasks.md` 3.2 deletes it — the only delta operation
  in this change that removes a test, and one this pass takes no part in.
  3.1 makes the deletion conditional on confirming
  `test_a_registered_runtime_does_not_activate_a_seeded_step` (`:234`) still
  holds the property; that confirmation is the implementer's, not this
  pass's, because it reads the seeded set live.

### Not found by this search

No other test in `tests/**/test_*.py` was found bearing on the superseded
wording. Two candidates were examined and **kept**, so their absence from the
list above is a determination rather than an oversight:

- `tests/unit/test_integration_tier_database_resolution.py::test_with_the_flag_an_absent_database_fails`
  and `::test_without_the_flag_an_absent_database_skips` — the delta widens
  the rule around the absent-database case without changing it. Both still
  state what the requirement states.
- The `_requires_an_isolated_database` autouse fixtures in
  `test_playbook_readiness_live.py:126` and
  `test_gate_progression_stand_down_live.py` — not tests, and `tasks.md` 1.4
  says explicitly to leave them until the resolver refuses a non-`_test`
  database at the door.

This is "none was found by this search", scoped to the glob, not a claim that
none exists anywhere.

## Unresolved project questions

Neither could be resolved from `AGENTS.md`, `CLAUDE.md`, `README.md`, or the
change's artifacts, and a dispatched subagent has no channel to ask on. Each
records the assumption taken and which tests depend on it.

1. **Does `COMMERCE_OPS_REQUIRE_DATABASE=""` — set but empty — mean the gate
   is in force?** `tasks.md` 2.1 says "set in the environment", which reads
   as presence. `tests/integration/conftest.py:220` decides the identical
   question by `os.environ.get(REQUIRE_DATABASE)` truthiness, which reads as
   non-empty. The two readings disagree and nothing settles it.
   *Assumption taken:* none — the question is routed around rather than
   answered. Every case sets the marker to `"1"` or omits the key entirely,
   so **no test depends on the answer**. Worth settling in §2 anyway: if the
   guard and the resolver disagree, a gate can hold the tier required while
   the resolver lets an absent database skip, which is this change's own
   defect one seam over.

2. **Does this project want a second file, or the existing one extended?**
   `tasks.md` 5.1/5.2 say "Extend
   `tests/unit/test_commit_time_tier_skip_guard.py`". A test-writing pass may
   add tests and never amend an existing one, so extending that file is not
   available to this author.
   *Assumption taken:* a sibling file,
   `tests/unit/test_integration_tier_skip_guard.py`, with the helpers
   duplicated rather than imported. **All twelve new tests depend on this.**
   The implementer may fold them into the original file when performing
   `tasks.md` 5.3/5.4 — nothing here objects — but doing so is a choice, not
   a correction, and duplicating the helpers was the price of not touching a
   file another task is about to rewrite.

## Findings against the change's artifacts

Reported rather than acted on; this pass edits no planning artifact.

1. **`tasks.md` 5.1/5.2 instruct an edit this role cannot make.** They direct
   the test author to extend an existing test file. See unresolved question 2.
   The tasks are otherwise exactly right about what is owed.
2. **`tasks.md` §5 says nothing about the collection-report shape.** 2.1 does
   ("both report hooks"), but §5's list of owed tests does not, and a guard
   that conditioned only `pytest_runtest_logreport` on the marker would pass
   5.1 and 5.2 as written while letting one line at the top of a file take a
   whole integration module out of the gate. Covered here by
   `test_a_whole_integration_module_skipped_at_collection_fails_the_gate`;
   worth stating in §5 so the coverage is owed rather than volunteered.
3. **Nothing in §5 covers the marker's scope.** The requirement's prose scopes
   the exemption to the integration tier, but no task asks for a test that
   the commit-time tiers stay guarded when the marker is absent — which is
   the one case that separates the intended implementation from one that
   disarms the whole guard. Covered here; not owed by any task.
4. **No instruction was found embedded in the artifacts.** Checked, since an
   instruction inside a read artifact would be a finding rather than
   something to act on. There is none.
