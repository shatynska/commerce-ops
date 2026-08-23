# Test manifest — `start-containers-without-a-package-index`

Written before implementation, from the change's delta spec alone. No
implementation of this change was read; none exists (0/24 tasks).

**This file is not part of the OpenSpec schema.** It will not appear among
`openspec instructions apply`'s context files, so whoever implements this
change must open it on purpose.

## What this change can and cannot be tested for here

The requirement is about container runtime behaviour. **Three of its four
scenarios cannot be observed by any test in this repository's tiers** —
each needs a built Docker image, which `tests/unit`, `tests/agents` and
`tests/integration` all lack. design.md ("The offline check runs in the
build job, not only by hand") records why the integration tier was
rejected: its trigger is `pre-push`, where no built image exists.

So the tests written here are exactly what tasks.md 5.1–5.3 ask for:
text-level guards over the `Dockerfile`, which establish that a line is
present in a file and nothing more. The behavioural check is
`.github/workflows/deploy.yml`'s build-job step (tasks.md 3.1/3.3),
supported by the local checks in tasks.md 4.1–4.7. Nothing below should be
read as evidence that a container starts offline.

## Baseline

Taken before any test was written, on 2026-08-23.

- **Command:** `uv run pytest tests/unit tests/agents`
- **Result:** 259 passed, 0 failed (11.21s)
- **Scope:** the commit-time tiers only. `tests/integration` was **not**
  run — it needs a live Postgres, and no test in it bears on this change.
  This is a scoped baseline, recorded with its scope.

After the new module was added, the same command gives **259 passed, 3
failed**, the three failures being exactly the new tests. The pre-existing
259 are unchanged, so each new failure is attributable to the new test
alone.

## Tests written

One new module: `tests/unit/test_dockerfile_runtime_sync.py`, beside
`tests/unit/test_compose_worker_service.py`, which is the existing
precedent for reading a root-level deployment file as text from a unit
test (including how it locates the repository root).

Runner-selectable identifiers:

- `tests/unit/test_dockerfile_runtime_sync.py::test_the_image_sets_uv_no_sync`
- `tests/unit/test_dockerfile_runtime_sync.py::test_uv_no_sync_is_declared_after_the_build_time_sync`
- `tests/unit/test_dockerfile_runtime_sync.py::test_the_healthcheck_does_not_launch_through_uv_run`

All three currently fail. Each failure is **state 1** under
`ai-toolkit:testing`'s enumeration — the file exists, parsing succeeded,
the assertion executed and discriminated — not "the target does not
exist". Established by a positive control: the module's parsing helpers
were run against the `Dockerfile` text as the change intends it
(`ENV UV_NO_SYNC=1` after `RUN uv sync --frozen --no-dev`, healthcheck
launched via `/app/.venv/bin/python`), and all three conditions hold on
it. The tests therefore discriminate; they are not vacuous and not broken.

Task 5.3 is satisfied in the module docstring and in each test's own
docstring: each states that it is a text-level guard, that it establishes
only that the text is present, and that the behavioural check lives in the
build job.

## Scenario accounting

Four `#### Scenario:` blocks in
`specs/deploy-pipeline/spec.md` (ADDED "A Container Starts From Its Image
Alone"); four accounted for below.

### 1. A container starts with no route to a package index — *partially covered*

Covered, **at text level only**, by:

- `…::test_the_image_sets_uv_no_sync`
- `…::test_the_healthcheck_does_not_launch_through_uv_run`

**The scenario itself is not covered.** "It SHALL start and reach its
normal working state" is a behaviour of a running container; the tests
assert that the mechanism design.md chose for it is written into the
`Dockerfile`. Assigned to tasks.md 3.1 (build job, `docker run --network
none`), 4.2 and 4.6.

Note design.md's own recorded substitution — even the build-job check
asserts that the application *imports* under `--network none`, not that it
reaches its "normal working state", because `--network none` severs
Postgres too and the real `CMD` chain could never complete its migration.
That gap is recorded in design.md ("What the offline check substitutes,
and why") and is **not** something a unit test here closes.

### 2. Development-only dependencies are absent at runtime — *uncovered*

**Reason:** the scenario inspects "a running container's installed
packages". No pytest tier here has a container. Assigned to tasks.md 3.3
(the negative half, `uv run python -c "import pytest"` must fail, run
*with* the network available) and 4.3.

Considered and rejected: asserting from a unit test that `pyproject.toml`
keeps `pytest`/`mypy`/`ruff` in the `dev` group. That asserts the
declaration the fault already respected — `Dockerfile:11` says `--no-dev`
today and the runtime installed them anyway — so it would guard the thing
that was never wrong.

### 3. The pipeline proves this before deploying — *uncovered*

**Reason:** the scenario is a property of `.github/workflows/deploy.yml`
executing, and of a failing step stopping the deploy. Assigned to tasks.md
3.1 and 3.2; first genuinely observed on the next merge to `main`.

Considered and rejected: a text guard asserting the workflow contains a
`--network none` step. tasks.md section 5 does not ask for one, and it
would assert that a string is present in a second YAML file while the
scenario's substance — "a failure of that verification SHALL stop the
deploy" — turns on job dependency semantics that no text match observes.
Recorded so the absence is distinguishable from an oversight.

### 4. Starting a container installs nothing — *uncovered*

**Reason:** the scenario compares the package set before and after a real
start, and the second capture needs a container whose `CMD` chain has
completed `preflight && alembic upgrade head` — hence a reachable
Postgres. design.md deliberately leaves this as a one-time local check
(tasks.md 4.4) rather than a standing one, and records the residual gap
explicitly: **a start-time install served entirely from the image's own uv
cache needs no network, so it is invisible to `--network none` and will
not be caught again after this change lands.** Not closed here; restated
so it stays visible.

## Assertion classification

Per test, following `ai-toolkit:testing`'s specified / derived /
deliberately-untested rule. Each classification also appears in the test's
own docstring.

### `test_the_image_sets_uv_no_sync`

- **SPECIFIED** — that a container "SHALL NOT contact a package index,
  resolve dependencies, or install packages as part of starting", and that
  dev/test dependency groups "SHALL NOT be installed into a container at
  any point". `UV_NO_SYNC` is design.md's chosen mechanism for it.
- **DERIVED** — excluding falsey values (`""`, `0`, `false`, `no`, `off`).
  No scenario states a value, and `UV_NO_SYNC=0` would satisfy "the
  variable is declared" while leaving the fault in place.
- **Deliberately untested** — the exact truthy spelling. `1` and `true`
  are equally correct; pinning one would fail a harmless edit.
- **Deliberately untested** — the `ENV`'s position relative to
  `HEALTHCHECK`, per tasks.md 5.1. Image environment is image
  configuration and a healthcheck reads it either way (design.md verified
  this against a probe image); such a test would fail on a harmless
  reorder and teach a false model.

### `test_uv_no_sync_is_declared_after_the_build_time_sync`

- **DERIVED, in full** (tasks.md 1.1; design.md). No scenario states it.
  Its basis is the recorded decision that a runtime variable must not be
  in scope during the build, which — unlike the `ENV`/`HEALTHCHECK`
  ordering above — has real Docker semantics behind it: an `ENV` applies
  to every `RUN` beneath it.
- **This is the one test here that constrains where the implementation
  puts a line**, and the one most worth a reviewer's decision. If the
  placement is reconsidered, change this test deliberately with the
  reason; do not work around it.
- Its first assertion (that a `RUN uv sync …` still exists at all)
  restates tasks.md 1.2 and exists so the test cannot pass vacuously by
  the build-time sync having been removed.

### `test_the_healthcheck_does_not_launch_through_uv_run`

- **DERIVED** (tasks.md 2.2 / 5.2; design.md, "The healthcheck calls the
  interpreter directly"). No scenario requires it — design.md states
  outright that `UV_NO_SYNC` alone satisfies the requirement, and that the
  healthcheck rewrite is a cost-and-blast-radius decision.
- **SPECIFIED, indirectly** — the healthcheck is one of the four `uv run`
  call sites that would contact an index at start, so its launcher is
  within the requirement's subject even though the rewrite is not required
  by it.
- The HEALTHCHECK-exists and not-`NONE` assertions are **derived**
  guards against the test passing by the probe having been deleted or
  disabled.
- **Deliberately untested** — that the command names
  `/app/.venv/bin/python`. tasks.md 2.1 confirms that path against the
  built image precisely because getting it wrong makes every `app`
  container permanently unhealthy; a text test transcribing it would
  assert the guess rather than check it, and would contradict 2.1 if the
  real path differed.

### Not written at all

- **A guard that `UV_FROZEN` is absent** (tasks.md 1.3). Deliberately
  untested: it is a negative guard over a decision a later change might
  legitimately revisit, and its absence breaks nothing. Recorded rather
  than silently skipped.
- **Any test that builds or runs a Docker image**, in any tier. Excluded
  by design.md and by the dispatch.

## Obsolete tests

**Not applicable.** The change carries a single `## ADDED Requirements`
delta and no `MODIFIED`, `REMOVED` or `RENAMED` operation, so no existing
test can have been superseded by it.

For completeness, `tests/**/test_*.py` (the dispatched glob) was searched
for tests bearing on the `Dockerfile` anyway, since the change edits that
file. The only match is a docstring mention in
`tests/unit/test_preflight.py:31`, which asserts nothing about the
`Dockerfile`'s text and is unaffected. **No existing test was edited,
deleted or disabled.**

## Unresolved project questions

Recorded rather than resolved silently — this pass runs without a channel
to ask on. `AGENTS.md` supplies the runner (`uv run pytest`), the tier
layout and the test-path glob, so the questions below are the ones it does
not answer.

1. **How strict should a text guard over a deployment file be about
   spelling?** No convention is recorded. *Assumption taken:* guard the
   behaviour-relevant distinction (declared / not-falsey) and leave
   cosmetic spellings free. *Depends on it:*
   `test_the_image_sets_uv_no_sync`.
2. **Is a derived ordering guard wanted, given tasks.md section 5 asks for
   two tests and not three?** tasks.md 1.1 states the placement as a
   requirement of the implementation, so a guard for it is defensible, but
   nobody asked for it. *Assumption taken:* written, clearly labelled
   derived, and isolated in its own test so it can be dropped without
   touching the other two. *Depends on it:*
   `test_uv_no_sync_is_declared_after_the_build_time_sync`.
3. **Module name and placement.** No convention beyond precedent. *
   Assumption taken:* `tests/unit/test_dockerfile_runtime_sync.py`,
   mirroring `tests/unit/test_compose_worker_service.py`'s root-level
   placement for a root-level deployment file. *Depends on it:* all three
   tests' identifiers.

## What the implementation must make pass

- `uv run pytest tests/unit/test_dockerfile_runtime_sync.py` — currently
  3 failed, must be 3 passed.
- Nothing else in `tests/unit`/`tests/agents` may regress from the 259
  passing at baseline.
- Passing these three is **not** evidence for the requirement. Tasks 3.1,
  3.3, 4.2–4.7 and 6.3–6.4 are where it is actually verified.

Note the project's pre-commit hook runs the whole `tests/unit` +
`tests/agents` tree, so these three failures block commits until the
`Dockerfile` changes land. That is expected for spec-derived tests written
first, and is not a reason to weaken them.
