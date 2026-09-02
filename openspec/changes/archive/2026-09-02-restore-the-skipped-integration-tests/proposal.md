## Why

**The validation gate has been running 132 of 137 integration tests and reporting a
pass.** Measured 2026-09-02 against CI's exact configuration — its database name, its
`COMMERCE_OPS_REQUIRE_DATABASE: "1"`, a database migrated and seeded the way
`ci.yml` prepares one:

```
132 passed, 6 skipped     ← CI's configuration. Exit 0.
137 passed, 1 skipped     ← the same code, the same data, on a database named `*_test`
```

Five tests — four in `test_playbook_readiness_live.py`, one in
`test_gate_progression_stand_down_live.py` — rewrite the stored step set, so each
module refuses to run unless the resolved database name ends in `_test`. CI's is
named `commerce_ops`. The five have therefore never run in the gate, and nothing
reports it: `pytest` exits 0 and the job is green.

`COMMERCE_OPS_REQUIRE_DATABASE` is structurally blind to this. The flag fires only
when *no* URL resolves; in CI one resolves fine. It was built for a different
absence and cannot see this one.

`deploy-pipeline` already forbids the outcome:

> A tier that does not run SHALL NOT be reported as a tier that passed. Where the
> gate runs a tier, an absent database configuration, or a failure to reach the
> database that tier is configured to run against, SHALL fail the gate rather than
> be skipped — so that a validation job cannot report success for work it never
> exercised.

Both causes it names are about a database being **absent or unreachable**. CI's is
present, reachable and correctly prepared, and merely misnamed. The requirement says
what its readers believe it says; its wording does not reach this case.

**Why now, and why this shape rather than a louder skip.** Three readers in three
weeks each supplied a false explanation for a signal the suite declined to give:
a `pre-push` hook printing `pytest (integration)... Passed` for a tier that ran
nothing; four failing tests read as "pre-existing failures" when they were an
unseeded database saying so in their own assertion messages; and an agent
concluding *"Docker isn't available in this WSL setup"* while `commerce-ops-postgres-1`
was up on `127.0.0.1:5432` the entire time. A silent skip does not present as a
misconfiguration. It presents as an environment fact, and readers rationalise it.

Making skips *louder* was already tried and is not the answer: `pyproject.toml`
sets `addopts = "-rs"` for exactly this, with a comment recording that a run
reporting "64 skipped" was read as a passing tier anyway. The project's own answer
to the identical defect one tier over is a guard that **fails the session**, written
and argued in `restore-the-skipped-unit-tests` (2026-09-01) after forty-four unit
tests were removed from the commit-time gate by a filename-matching fixture. That
guard lives in `tests/conftest.py` and excludes `tests/integration` on a premise
that is true on a bare machine and false in CI:

> `tests/integration` is deliberately excluded. It skips legitimately when no
> database resolves, and says why.

In CI there is no legitimate no-database skip — the flag already turns that one into
a failure. The exclusion protects nothing there, and hides five tests.

## What Changes

- **`deploy-pipeline`'s validation-gate requirement is widened** from "the tier did
  not run for want of a database" to "any test in the tier did not run." The gate
  fails on a skipped integration test whatever its reason, so no future skip — for
  a cause nobody has thought of — can quietly leave the gate.
- **`ci.yml` names its ephemeral database `commerce_ops_test`** (`POSTGRES_DB` and
  `DATABASE_URL`). One line each; it is what starts the five tests running. The
  database is created by the job and reachable only from it, so the rename costs
  nothing and breaks nothing.
- **`tests/conftest.py` guards `tests/integration` when `COMMERCE_OPS_REQUIRE_DATABASE`
  is set.** The existing `pytest_runtest_logreport` / `pytest_collectreport` /
  `pytest_sessionfinish` machinery is reused; only the path filter, its condition,
  and the failure report's wording are new. Where the flag is unset — a developer's machine — the tier skips
  exactly as it does today, so nothing changes for the population the original
  decision protects.
- **The tier's last remaining skip is removed by deleting the test that carries it.**
  `test_no_seeded_automated_step_is_activated_by_its_handler_existing` skips when no
  seeded automated step names a handler this deployment registers. That reads as an
  occasional coincidence and is not one: every seeded automated step carries
  `handler = NULL` — the backfill migration writes none, and a handler is obliged only
  once a step is `active` — so the skip fires on **every** run of **every** correctly
  prepared database. Verified live: `lp.listing.014` and `lp.traffic.001`, both
  `in-development`, both `NULL`. **The assertion has never executed anywhere.**

  Nothing is lost. Its sibling in the same file,
  `test_a_registered_runtime_does_not_activate_a_seeded_step`, already asserts the
  property unconditionally and live over the whole seeded automated set, with its own
  guard against passing vacuously. The deleted test adds only the sharper form — *even
  for one whose handler resolves* — which needs a seeded step naming a handler, and the
  seed structurally cannot carry one. An allowlist is not available anyway:
  `tests/conftest.py` argues against one explicitly ("Zero tolerance cannot be
  satisfied by widening a list […] and there is no list here to widen"), and names
  deletion as a legitimate answer in the same breath.

  **The finding outlives the test, and is the more valuable half.** The requirement's
  negative form — activation is "never something seeding or deploying does on an
  author's behalf" — has no integration-level subject in this system: the only writer
  in the container's start chain is `seed_playbook`, and it cannot re-status by
  construction. `design.md` Decision 3 records that, and records the two replacement
  tests that were drafted and rejected for being tautologies.

- **The gate's requirement records that the tier needs the database *seeded*, not
  only migrated.** No behaviour changes — `ci.yml` has run `seed_playbook` since
  `seed-the-reference-step-set`, with a comment explaining why. The specification is
  silent on it, and that silence is the source of the same omission in `AGENTS.md`
  and `README.md`, where the recipe for a local test database says "create and
  migrate" and stops.
- **`AGENTS.md` gains rules for working in a worktree**, and `README.md`'s Local
  Postgres recipe is corrected. A worktree does not inherit `.env.test` — it is
  gitignored, so it exists only in the clone it was written into — which makes
  *creating a worktree* the trigger for an unconfigured tier, and worktrees are how
  parallel sessions run on this project. The rules name the running container as a
  fact to check rather than assume, state that migrated is not seeded, and state
  that the `_test` requirement is a **suffix**, so `commerce_ops_test_x` silently
  loses five tests where `commerce_ops_x_test` does not.

**Not in this change**, each recorded in `docs/deferred-work.md` and each its own
sentence:

- The resolver refusing a URL that names the working database (rung 3). That is a
  data-safety property, not a reporting one, and it stands alone — the deferred-work
  entry already calls it "the one worth doing whether or not the others are."
- A script that provisions a worktree's database, and `pre-push` setting the flag.
  The flag on `pre-push` is only sound once the answer to its failure is "run the
  script", and the script does not exist yet.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `deploy-pipeline`: the *Pull Request Validation Gate* requirement is widened from
  a tier that did not run to a **test** that did not run, and records that the gate
  prepares the tier's database by seeding it as well as applying the schema.

  Two consequences of that wording are deliberate and worth naming, since neither is
  visible from the summary above. The widened rule reads on **every** tier the gate
  runs, `tests/unit` and `tests/agents` included — already true in implementation
  since 2026-09-01, and now specified rather than merely built. And the exemption for
  a run outside the gate is scoped to the **integration tier only**: a skip in the
  commit-time tiers fails a developer's run today and continues to.

## Impact

**Specification** — `openspec/specs/deploy-pipeline/spec.md`, one requirement
modified, its existing scenarios preserved and four added.

**Code** — `tests/conftest.py` (path filter, its condition, and the failure report's
wording); `tests/unit/test_commit_time_tier_skip_guard.py` (a case for each
population, and one existing test re-documented);
`tests/integration/launch/test_registered_handlers_activate_nothing.py` (one test
deleted, the finding recorded in its place); `.github/workflows/ci.yml`
(`POSTGRES_DB`, `DATABASE_URL`, and the health check's `-d`).

**Documentation** — `AGENTS.md` (worktree rules); `README.md` (Local Postgres
recipe: the missing seed step, and a stale reference to `tests/integration/products/`,
a directory that no longer exists); `docs/deferred-work.md` (the entry gains what
was measured here: a byte-identical `TEMPLATE` copy of the shared `commerce_ops_test`
passes 137/1 today, 1325 retired rows included, so accumulated debris is inert and no
cleanup is owed).

**What does not change**: the resolver, its three rungs, `.env.test`, the
`pre-push` hook, and the behaviour of any developer machine where
`COMMERCE_OPS_REQUIRE_DATABASE` is unset.

**Measured before proposing**, so the change is not sized against a guess:

| observation | result |
| --- | --- |
| tier on `*_test`, migrated + seeded | 137 passed, 1 skipped |
| tier on a non-`_test` name, flag set (CI's shape) | 132 passed, **6 skipped**, exit 0 |
| tier against a `TEMPLATE` copy of the shared `commerce_ops_test`, 1325 retired rows | 137 passed, 1 skipped — **accumulated debris is inert**, so no cleanup work is owed here |
