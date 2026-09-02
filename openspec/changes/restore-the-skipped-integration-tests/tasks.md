# Tasks

Ordered by dependency. Sections 1–3 must land together: section 2 alone turns the
tier's five isolation skips and its one remaining skip into CI failures, and sections
1 and 3 are what remove them.

## 1. Let the gate's database satisfy the tier

- [ ] 1.1 Rename the validation job's ephemeral database to `commerce_ops_test` in `.github/workflows/ci.yml` — `POSTGRES_DB` on the `postgres` service, and the database segment of the job-level `DATABASE_URL`. Both, or the job cannot connect.
- [ ] 1.2 Give the service's health check the database it now has: `pg_isready -U commerce_ops -d commerce_ops_test`. Without `-d` it probes `commerce_ops`, which the rename removes. `PQping` most likely still reports OK on a FATAL for an unknown database, so this is a latent adjacency rather than a live break — name it rather than leave it to be rediscovered.
- [ ] 1.3 Confirm the two isolation-guarded modules stop skipping, by running the tier against a database named as 1.1 names it, prepared exactly as `ci.yml` prepares one (`alembic upgrade head`, then `python -m commerce_ops.seed_playbook`). Expect `137 passed, 1 skipped` — the remaining skip is section 3's subject.
- [ ] 1.4 Leave `_requires_an_isolated_database()` in `test_playbook_readiness_live.py` and `test_gate_progression_stand_down_live.py` untouched. It is the only thing protecting those five tests from a step set they would rewrite until the resolver refuses a non-`_test` database at the door — see `design.md` Decision 2. Removing it belongs to the next change, not this one.

## 2. Extend the no-skip guard to the integration tier

- [ ] 2.1 In `tests/conftest.py`, make the guarded tier set include `integration` when `COMMERCE_OPS_REQUIRE_DATABASE` is set in the environment, and exclude it otherwise. Reuse `_is_guarded`, both report hooks and `pytest_unconfigure` unchanged; keep the `wasxfail` exclusion, which `design.md` Decision 6 now states in the requirement rather than leaving implicit.
- [ ] 2.2 Read the flag once, where the tier set is decided, rather than per report — the guard must judge one session by one rule, and a test that changes the environment mid-session must not change what the session is held to.
- [ ] 2.3 Update the module docstring. The paragraph beginning "`tests/integration` is deliberately excluded" states a premise this change falsifies for the gate; replace it with the two-population rule and say why the flag is the line.
- [ ] 2.4 Update `pytest_sessionfinish`'s report so it names the tiers actually guarded in that session — both the "commit-time tier" headline and the closing advice, which currently tells a reader to "move it to `tests/integration` or delete it". That escape hatch does not exist once the integration tier is guarded, and a failure message directing someone to it is worse than none.

## 3. Remove the tier's last skip

Its precondition is unsatisfiable, not occasional: every seeded automated step carries
`handler = NULL`, so `resolvable` is empty on every run and the assertion has never
executed anywhere. See `design.md` Decision 3, which also records why the two obvious
replacements are tautologies.

- [ ] 3.1 Confirm the property is not lost, before anything is removed: `test_a_registered_runtime_does_not_activate_a_seeded_step` (same file, `:234`) asserts it unconditionally over the whole seeded automated set, live, and carries its own non-vacuity guard that a handler really is registered. Its subject is a *superset* of the deleted test's — `resolvable` filters the same `automated` tuple — so the assertion over the whole set entails the assertion over the subset. Where that is not what the code says, stop: the deletion's entire warrant is that this sibling holds the line.
- [ ] 3.2 Delete `test_no_seeded_automated_step_is_activated_by_its_handler_existing` from `tests/integration/launch/test_registered_handlers_activate_nothing.py`. Delete only that function; the file's other two tests stay.
- [ ] 3.3 Record the finding in the module docstring, where the test was: the requirement's negative half — activation is "never something seeding or deploying does on an author's behalf" — has no integration-level subject, because `seed_playbook` is the only writer in the container's start chain and `compose()` carries every stored row across untouched with no status branch. Name `tests/unit/test_seed_playbook.py`'s `test_an_edited_step_is_left_exactly_as_it_stands` as where that half is held.
- [ ] 3.3b In the same docstring, remove the "Expected first-run state" paragraph. Both its claims are false once the tier runs in the gate — `HANDLERS` is no longer empty, and "these assertions have never been executed" is no longer true of `:234`, which is the sentence 3.1's warrant rests on. Leaving it would have the file state the warrant and its refutation eleven lines apart.
- [ ] 3.4 Do not add a replacement test in this change. Integration coverage of the requirement's *positive* half — that `activate_step` refuses a step naming an unregistered handler — is a real gap and a separate change; `design.md` Decision 3 records it as the strongest thing not being done here.

## 4. Specification

- [ ] 4.1 Apply the `deploy-pipeline` delta in `specs/deploy-pipeline/spec.md`: the *Pull Request Validation Gate* requirement widened from a tier that did not run to a **test** that did not run, the expected-failure clause, the gate's database described as schema **and** seed, the reachability carve-out re-anchored, the developer-machine exclusion, and the four added scenarios.
- [ ] 4.2 Run `openspec validate restore-the-skipped-integration-tests --strict` and resolve anything it reports.

## 5. Durable verification of the guard itself

The change's central behaviour is a guard firing. A guard nobody has a standing test
for is the thing this change exists to prevent.

**These are tests derived from this change's delta scenarios**, so `AGENTS.md`'s
test-design rule applies: they are owed to an author other than whoever implements
§2, dispatched through `ai-toolkit:openspec-test-writer` after this plan is committed
and strictly before §2 is written. Listing them here says what is owed, not who writes
it.

- [ ] 5.1 Extend `tests/unit/test_commit_time_tier_skip_guard.py` with a case that sets `COMMERCE_OPS_REQUIRE_DATABASE` in the child environment and asserts the session fails, naming the skipped integration test and its reason. `_run` already builds that environment explicitly (`env={"PATH": ...}`), so this is one dict entry.
- [ ] 5.2 Add the paired case with the flag unset, asserting the session stays silent — the developer-machine exemption, held by a test rather than by a manual procedure.
- [ ] 5.3 Rewrite `test_the_integration_tier_may_still_skip`. Its docstring asserts the exclusion is unconditional and cites `AGENTS.md` as specifying it; after this change the exclusion holds only without the marker. It keeps passing by accident — the flag is not inherited into the child — so it must be renamed and re-documented rather than left to mislead.
- [ ] 5.4 Update that file's module docstring, which describes the guard as covering the commit-time tier alone.

## 6. Documentation

- [ ] 6.1 Add worktree rules to `AGENTS.md` — the five in `design.md` Decision 5's table, verbatim as to substance. Place them where the project's other working obligations live, phrased as obligations rather than as tips. Keep each rule's instruction separable from its consequence clause: change B updates rule 5's enforcement point and change C updates rule 2's, and neither should have to rewrite a rule to do it.
- [ ] 6.2 Correct `AGENTS.md`'s own Testing Strategy sentence, which tells a reader to "create and migrate `commerce_ops_test`" and stops. It is the recipe that produces the state 6.1's third rule warns about; leaving both would have the file state the rule and the violation.
- [ ] 6.3 Correct `README.md`'s Local Postgres section: add `python -m commerce_ops.seed_playbook` to the test-database recipe, say that the `_test` requirement is a suffix rather than a literal name, and fix the stale reference to `tests/integration/products/`, a directory that no longer exists.
- [ ] 6.4 Update `docs/deferred-work.md`'s entry *The integration tier's local setup is per-clone, and fails open*: mark the first of its three gaps — `pre-push` reporting a tier that never ran — as closed **for the gate** by this change and still open for `pre-push`, and record that accumulated debris was measured inert (a `TEMPLATE` copy of the shared `commerce_ops_test` passes 137/1 with 1325 retired rows), so no cleanup is owed by any of the three.
- [ ] 6.5 Record a new `docs/deferred-work.md` line, noticed during review and deliberately not fixed here: `openspec/specs/launch-playbook/spec.md:344` states the seeded set "is entirely `human` drafts", while `test_registered_handlers_activate_nothing.py:264` asserts the opposite and passes — the two backfilled `lp.*` automated rows predate `seed-the-reference-step-set`. The tension belongs to `launch-playbook`, not to this change, and its failure mode is a loud assertion rather than a silent vacuum. Record it; do not fix it.
- [ ] 6.6 Refresh the entry's clone survey, or leave it and update its "Surveyed on" date. Two of its five rows are gone and two worktrees not in it exist.

## 7. Verification

- [ ] 7.1 `uv run pytest tests/unit tests/agents` — green, and no new skip reported.
- [ ] 7.2 `uv run pytest tests/integration` with no flag set, against a prepared `*_test` database: green, and the run must **not** fail on a skip. This is the developer-machine population the requirement exempts.
- [ ] 7.3 `COMMERCE_OPS_REQUIRE_DATABASE=1 uv run pytest tests/integration` against the same database: green, `0 skipped`. Where any test skips, the session must fail and name it — that is the change working, not the change broken.
- [ ] 7.4 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy .`, `uv run lint-imports --config .importlinter`.
- [ ] 7.5 Confirm on the pull request that the validation job reports the integration tier as `137 passed, 0 skipped`. The arithmetic: 132 passed today, plus the five the rename releases; section 3 deletes a test rather than fixing one, so the collected total falls from 138 to 137 and the skip count reaches zero. `uv run pytest tests/integration` prints no passing test names and `-rs` reports only skips, so the count and the zero are what is observable — do not write a check that depends on seeing the five named unless `-v` is added to that step.

## 8. Review

- [ ] 8.1 Run `/code-review` over the change's diff before treating it as done, per `AGENTS.md`.
