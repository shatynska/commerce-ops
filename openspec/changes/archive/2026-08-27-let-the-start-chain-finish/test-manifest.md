# Test manifest — `let-the-start-chain-finish`

Written by `ai-toolkit:openspec-test-writer` on 2026-08-27, from the
change's delta spec alone, before any of the change was implemented. The
`Dockerfile` this change edits was deliberately **not read** by this
pass; the guards below read it at run time, which is what they are for.

**This file is not part of the OpenSpec schema.** It does not appear
among `openspec instructions apply`'s context files, so whoever
implements this change has to open it on purpose. Nothing in
`AGENTS.md`'s managed block points at it either — recorded below as an
unresolved project question.

**Fulfils `tasks.md` 2.1, 2.2 and 2.3.** No other task was touched, and
no task checkbox was ticked by this pass.

---

## Baseline

`uv run pytest tests/unit tests/agents` — the commit-time tier — at the
worktree root, branch `let-the-start-chain-finish`, commit `ae43d72`,
tree clean apart from this change's own untracked artifacts, immediately
before any test here was written:

```
1109 passed in 38.44s
```

0 failed, 0 skipped.

**This is a scoped baseline, and the scope is stated rather than
implied.** `tests/integration` was not run: it needs a live Postgres,
which is not available to this pass, and nothing in this change touches
the integration tier — the change edits one literal in the `Dockerfile`
and adds one unit-tier file. A later claim about failure below is
therefore attributable within `tests/unit` + `tests/agents` and makes no
claim about the integration tier either way.

**State after this pass** (same command, same commit, one test file
added, nothing else changed):

```
1 failed, 1110 passed in 37.67s
```

The 1 failure and 1 of the passes are both in the file this pass
created. No pre-existing test changed outcome.

`uv run ruff check`, `uv run ruff format --check` and `uv run mypy` are
clean on the added file.

---

## Files added

| File | Covers |
| --- | --- |
| `tests/unit/test_dockerfile_health_probe.py` | `deploy-pipeline` ADDED *The Container's Health Probe Allows Its Start Chain to Finish* — the 2 of its 6 scenarios that any test in this repository can observe |

No existing test file was edited, deleted or disabled. No file outside
the project's declared test-path glob (`tests/**/test_*.py`) was written,
apart from this manifest. **This pass adds tests and never subtracts.**

Placed at the top level of `tests/unit/` rather than under a
`<module>/<layer>/` path, following the two existing repository-artifact
guards it sits beside — `tests/unit/test_dockerfile_runtime_sync.py` and
`tests/unit/test_compose_worker_service.py`. A `Dockerfile` belongs to no
domain module, so the tiering in `AGENTS.md` — Testing Strategy has no
layer for it; the precedent does.

---

## The failure state of each added test

Per `ai-toolkit:testing`, a failing test is not one thing, and neither is
a passing one. Both readings below are recorded because the two tests are
in **different situations**, which is easy to misread as one of them
being wrong.

| Test | State now | What that establishes |
| --- | --- | --- |
| `test_the_start_period_is_at_least_sixty_seconds` | **FAILS** — the code ran and produced a wrong value (state 1) | The strongest state. The `Dockerfile` parsed, the flag was found, and a **specified** assertion did not match: `--start-period=5s` against a stated floor of 60s. Per the provenance rule, a specified assertion that does not match means the target is wrong, not the test. This is the expected pre-implementation state and is what `tasks.md` 1.1 must make pass. |
| `test_the_steady_state_liveness_signal_is_unchanged` | **PASSES** on its first run | Not the fourth-state alarm, because this is the *target-already-exists* situation: the `HEALTHCHECK` exists, and the delta **fixes values that must remain** (`--interval=10s`, `--retries=3`) rather than introducing new ones. A pass therefore establishes that the declared values currently match what the delta fixes, and the test's job is to stay green — it is a regression guard against `tasks.md` 1.1 being implemented the way `design.md` rejects. |

**The passing test was checked for vacuity rather than assumed
non-vacuous**, since a first-run pass has to earn its reading. Its
parsing helpers were driven directly against fabricated `HEALTHCHECK`
text and confirmed to discriminate: `--interval=30s` reads as 30.0 and
fails; `--retries=9` fails; an absent `--start-period` or `--interval`
fails with the absent-flag message rather than passing by default; a
`--retries=9` fragment **inside the probe command string** is correctly
not read as a probe option (flag parsing stops at the first non-`--`
token); and `1m` / `0m10s` read as 60.0 / 10.0, so the guard is tolerant
of duration spelling as intended.

---

## Scenario accounting

The delta spec carries **6** `#### Scenario:` blocks, all under the one
ADDED requirement. All 6 are accounted for below, each exactly once:
**2 covered, 4 uncovered with reasons.**

### Covered

#### 1. *The declared window meets its floor* — COVERED

`tests/unit/test_dockerfile_health_probe.py::test_the_start_period_is_at_least_sixty_seconds`

Assertion classification, as recorded in the test's own docstring:

- **SPECIFIED** — the declared start-up grace window is at least 60
  seconds. Traces to the scenario's THEN and to the Sizing paragraph's
  "SHALL NOT be less than 60 seconds".
- **SPECIFIED** — an absent `--start-period` is a violation, not a
  missing precondition. Docker's default is 0s, which is below the
  stated floor, so the absent-flag case is the very state the delta
  forbids.
- **DERIVED** — the value is read as a *duration* rather than matched as
  the literal `60s`, so `1m` and `90s` satisfy it too. The delta states a
  floor in seconds; pinning one spelling would fail a harmless edit.
- **DERIVED** — where an image declared more than one `HEALTHCHECK`, the
  last is taken as the effective one (Docker's documented semantics). No
  scenario states this; today there is one probe and the two readings
  coincide.
- **DERIVED** — `HEALTHCHECK NONE` and an absent `HEALTHCHECK` fail with
  their own messages, so neither test can pass vacuously by the probe
  having been deleted. Follows the same guard in
  `test_dockerfile_runtime_sync.py`.
- **DELIBERATELY UNTESTED** — that the window is *exactly* 60 seconds.
  Sizing makes 60s a floor, not a target, and obliges the window to grow
  when the deploy's start-to-healthy figure rises (`tasks.md` 4.4). A
  test demanding exactly 60 would fail the very edit the delta requires.
- **DELIBERATELY UNTESTED** — `--timeout`, `--start-interval` and the
  probe command. The delta fixes none of them. `design.md` — "Leave
  `--start-interval` unset" is a decision resting on a Docker version
  floor this repository does not establish, so a test either way would
  assert a preference no scenario states.

#### 5. *Start-up tolerance is not taken from the steady-state signal* — COVERED, first clause only

`tests/unit/test_dockerfile_health_probe.py::test_the_steady_state_liveness_signal_is_unchanged`

- **SPECIFIED** — the probe's interval is 10 seconds and its
  consecutive-failure count is 3. Traces to the scenario's THEN and to
  the requirement's Scope paragraph ("those SHALL remain a 10-second
  interval and 3 consecutive failures").
- **SPECIFIED** — both are asserted as *equalities*, not lower or upper
  bounds. The delta fixes them, so a narrowing (`--retries=1`) is as
  much an unauthorised change to the steady-state signal as the
  widening `design.md` rejects (`--retries=9`).
- **SPECIFIED** — an absent `--interval` is a violation: Docker's
  default is 30s, not the required 10s.
- **DERIVED** — an absent `--retries` is a violation too, rather than
  accepted because Docker's default happens to be 3. The reasoning: the
  delta requires the count to be *stated at this probe*, and an engine
  default is a value a future Docker release could move without anyone
  in this repository noticing. If that reading is unwanted, this
  assertion is the one to change — deliberately, and with a reason.
- **NOT OBSERVABLE, and the test says so in its own docstring** — the
  scenario's second clause, "the start-up grace window SHALL NOT have
  been obtained by widening either of them". That is a statement about
  *how the window came about*, and no reading of the file's present text
  can observe a counterfactual. What the test does instead is make the
  outcome that clause forbids impossible to reach quietly: an edit
  buying start-up tolerance out of the interval or the retry count turns
  this test red.

### Uncovered

Four scenarios have **no test in this repository, and cannot have one.**

> **No pytest tier here has a built Docker image.** `tests/unit` and
> `tests/agents` run at commit time with no Docker involved at all;
> `tests/integration` runs at `pre-push` against Postgres and has no
> built image either. `design.md` — "Guard the value with a text-level
> test, and say what it does not prove" records the rejection of an
> integration test that builds an image and starts a container: every
> push would pay for it.

Each is recorded with what *does* verify it, so the absence of a test is
distinguishable from the absence of the thought.

#### 2. *A chain slower than the probe's failure budget still deploys* — UNCOVERED

Requires observing a real container's start chain and a real Docker
health monitor. **Verified by the deploy itself** — `docker compose pull
&& up -d --wait` on the host — and by Docker's documented start-period
semantics (`design.md` — Context: a failing probe inside the start
period leaves the container `starting` and does not increment the
consecutive-failure count; a succeeding probe marks it healthy
immediately, start period or not). The first verification is the deploy
that carries this change, per `design.md` — Migration Plan.

#### 3. *The declared window clears the measured interval* — UNCOVERED

Its WHEN is an action taken by a person on a future change ("a change
adds a step to the start chain and reads the start-to-healthy interval
its own deploy reports"), and its input is the `Started` → `Healthy`
figure from the three most recent successful GitHub Actions deploy runs.
Nothing in this repository holds those figures in a form a test could
read, and no scenario requires them to be recorded in one. **Verified by
`tasks.md` 4.4**, which reads the figure out of the deploy log after
merge and records it in `docs/deferred-work.md`; the rule's threshold is
40s, above which the window must grow and a follow-up change is owed.

A test that read a number out of `docs/deferred-work.md` was considered
and rejected: it would invent a machine-readable-record requirement the
delta does not state, and it would assert the transcription rather than
the measurement.

#### 4. *A start that never completes still fails the deploy* — UNCOVERED

Requires a container whose start chain genuinely fails. **Verified by
Docker's semantics** — the start period delays the unhealthy verdict, it
does not remove it, since the container is only ever marked healthy by a
*succeeding* probe — and by `deploy-pipeline`'s existing *A
startup-critical fault leaves the deploy failed*, which the `--wait` in
the host's fixed `app-deploy` mechanism enforces.

Worth reading together with `design.md` — Risks: the time to that
verdict grows from 26.5s to roughly 87s, and if `app-deploy`'s own wait
timeout sits between the two, a broken container fails the deploy by
wait-timeout rather than by `container ... is unhealthy`. The gate fails
closed either way; the message differs.

#### 6. *A restarted container is granted the window again* — UNCOVERED

Requires a container that becomes healthy, exits, and is restarted by
`restart: unless-stopped`. **Verified by Docker's semantics** — the start
period is measured from the container's `StartedAt` and health status
resets to `starting` on every start. This scenario states a **cost** the
change accepts (~87s per crash-loop cycle to reach `unhealthy`, against
26.5s today) rather than a behaviour to be secured, so there is nothing
here a guard could protect even if a built image were available.

---

## Obsolete tests

**Not applicable — and the reason is recorded rather than left as an
empty list.** The change carries a single `## ADDED Requirements` delta
and no `MODIFIED`, `REMOVED` or `RENAMED` operation, so nothing existing
is superseded and no test can have been written against superseded
behaviour.

For completeness, the search that would have produced the list was run
anyway, bounded to the project's declared test-path glob
(`tests/**/test_*.py`). Two existing tests mention the health probe:

- `tests/unit/test_dockerfile_runtime_sync.py::test_the_healthcheck_does_not_launch_through_uv_run`
- `tests/unit/test_compose_worker_service.py::test_the_workers_inherited_http_healthcheck_is_disabled`

**Neither is obsolete.** The first asserts the probe's *launcher*, the
second that the worker service disables its inherited probe; this change
alters neither, and both still passed after this pass. No test in the
repository asserts the probe's timing at all — which is why
`test_the_steady_state_liveness_signal_is_unchanged` passing on its
first run is a new guard over an existing value rather than a duplicate.

---

## Unresolved project questions

Recorded, not resolved, per the standard: each names the assumption
taken and which tests depend on it.

1. **Nothing in `AGENTS.md`'s managed block directs a reader to this
   manifest.** The workflow block names the test-writer dispatch but not
   the artifact it produces, and `test-manifest.md` is not an OpenSpec
   schema file, so `openspec instructions apply` will not surface it.
   *Assumption taken:* the implementer is told the path out of band.
   *Depends on it:* nothing mechanical — but if this file is not read,
   the four uncovered scenarios above look uncovered by oversight rather
   than by necessity. Editing `AGENTS.md` is outside this pass's
   additive test-only bound, so it is reported rather than done.

2. **Whether an absent `--retries` should read as a violation or as
   accepted-by-Docker's-default.** No scenario says. *Assumption taken:*
   a violation, because the delta fixes the count at this probe and an
   engine default can move.
   *Depends on it:* one assertion in
   `test_the_steady_state_liveness_signal_is_unchanged`. It is inert
   while the flag is declared, which it is today.

3. **The host's Docker engine version is not established by this
   repository**, and "two probe intervals" in the Sizing rule means 10s
   on an engine before 25.0 and 5s on 25.0+, where a default
   `--start-interval` applies inside the window (`design.md` — Context).
   *Assumption taken:* none was needed.
   *Depends on it:* no test written here. The one scenario that turns on
   the figure (*The declared window clears the measured interval*) is
   uncovered for independent reasons, and `tasks.md` 4.4 already names
   both expected readings as correct results.

4. **`ai-toolkit` carries no Docker or `Dockerfile` skill**, so this pass
   ran on the general testing floor plus `python` alone. *Assumption
   taken:* Docker's `HEALTHCHECK` flag syntax is `--name=value`, its
   durations are Go duration strings, and the last `HEALTHCHECK` in an
   image wins.
   *Depends on it:* the `_healthcheck_options` and `_duration_seconds`
   helpers, hence both tests. Each was written to fail loudly with the
   raw text when it cannot parse a value, rather than to return a
   default — so a wrong assumption here surfaces as a stated parsing
   defect, not as a false verdict about the requirement.

---

## What the implementation must make pass

```
uv run pytest tests/unit/test_dockerfile_health_probe.py
```

- `test_the_start_period_is_at_least_sixty_seconds` — currently red.
  `tasks.md` 1.1 turns it green.
- `test_the_steady_state_liveness_signal_is_unchanged` — currently
  green, and `tasks.md` 1.1 must leave it that way. It is the guard on
  "leaving `--interval=10s`, `--timeout=3s`, `--retries=3` and the probe
  command exactly as they are".

Neither test observes a running container. Turning the first one green
is necessary for this change and is not sufficient evidence that the
requirement holds; the deploy is.
