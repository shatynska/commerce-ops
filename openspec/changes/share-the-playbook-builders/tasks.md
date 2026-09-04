Every task below is verified the same way unless it says otherwise: `uv run
ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports`,
and `uv run pytest tests/unit tests/agents` green, **with the commit tier's
collected count excluding `tests/unit/support/` unchanged from the §1 baseline at
every commit**. A task that changes that count has changed the suite, not
migrated it.

`tests/integration` carries 17 of the 155 declarations, and running it per commit
would make every commit wait on Postgres. So its collected count is checked with
`uv run pytest tests/integration --collect-only -q` at each **phase boundary** —
tasks 3.6, 5.7 and 6.1 — and the tier is *executed* wherever a proof result
depends on it (3.6, 5.7, 6.1). The invariant is therefore per-commit for the
commit tier and per-phase for integration; saying so is the point, since an
unstated cadence is how a tier gets claimed without being run.

Two numbers are tracked, never one re-baselined: the pre-existing tree, which
never moves, and `tests/unit/support/`, which has its own expected count.

Every task from §3 onward also runs the AST assertion-identity check over the
files it touches, excluding `tests/support/` and `tests/unit/support/`. For a
two-commit migration it is evaluated across the commit **pair** — the proof
wrapper contains an `assert`, so the check run against the intermediate commit
would fail by construction.

Never `uv run pytest` bare: it fails at collection on duplicate test basenames
(`share-the-unit-test-harness` task 8.4). Always name the tiers.

## 1. Baseline

- [ ] 1.1 Record, at the branch point `132304d`: `tests/unit` outside support
      **2,246**, `tests/unit/support` **46**, `tests/agents` **236**,
      `tests/integration` **159**; commit tier **2,528** collected. Re-take
      rather than inherit these numbers.
- [x] 1.2 Confirm `tests/integration` actually runs before any proof result is
      trusted: `docker ps` shows `commerce-ops-postgres-1`, `.env.test` names a
      `_test`-suffixed database, and the tier reports 159 passed with **zero
      skips**. A worktree without `.env.test` skips the tier in its entirety and
      `pre-push` reports it `Passed` (`AGENTS.md` — *Working in a git worktree*);
      17 of this change's 155 declarations live there, so that green would make
      §3's coverage claim false.

      **Done, 2026-09-04, at the plan commit.** `commerce-ops-postgres-1` up and
      healthy; `.env.test` names `commerce_ops_harness_test`, migrated and
      seeded; `uv run pytest tests/integration` → **159 passed in 36.5 s, zero
      skips**. Re-run this in any other worktree: `.env.test` is gitignored and
      `git worktree add` carries none, so the confirmation does not travel.
- [ ] 1.3 Take the assertion-identity baseline over `tests/` at the branch point,
      with `tests/support/` and `tests/unit/support/` excluded.

## 2. The proof harness

- [ ] 2.1 Port the `@checked` equality-proof decorator. **It has never been in
      the repository** — `git log --all -- '*_instrument.py'` is empty, and both
      predecessors' proof harnesses were likewise session-side tools that entered
      the working tree and left with the migration. So there is no git ref to
      recover it from, and `~/share-the-playbook-builders/_instrument.py` (this
      change's measurement directory) is a convenience copy, not a source of
      truth. If that copy is absent, **reconstruct it from its specification
      rather than hunting for it**: a decorator wrapping a local builder that
      calls both the local and the shared form, compares the whole returned
      objects, raises on a difference, and counts its comparisons (2.1b).
      That specification is what this task depends on; the file is not. It compares whole
      objects, not fields an assertion reads, and reports a divergence by
      **raising**, so a divergence is a test failure rather than a log line. Do
      **not** port the lockstep pairing (`design.md` — Decision 2).
- [ ] 2.1a The harness is temporary: it enters the working tree with each
      instrument commit and leaves with that name's last settle commit. It never
      lands in `tests/support/`, for the reason both predecessors removed theirs
      (`design.md` — Decision 2). §6.1 confirms `tests/support/` carries none of
      it.
- [ ] 2.1b The harness **counts comparisons per declaration**. A declaration the
      suite never calls cannot be compared, and "zero failures" is satisfied by
      silence; a zero count is a reported result needing disposition, not a pass.
- [ ] 2.2 Write the delta-derivation pass: for a local `_hold`, call it for all
      eight gates and diff each result field-wise against `hold(gate)`.
      **Derive at runtime, never from the source** (`design.md` — Decision 3):
      a static pass over these same 73 over-reports `discipline` 26 against 13
      and `confirmer` 22 against 4, and mis-classifies one wrapper as a partial.
      **Record each local's signature beside its deltas**, not only the values:
      partial-vs-wrapper is sound only if `hold()` can accept the local's surface
      (`design.md` — Decision 3).
- [ ] 2.3 Write the filler AST check required by `design.md` — Decision 7. It
      asserts a migrated `playbook(...)` call site passes `filler=` **and that
      the argument resolves to a name bound at module level in that file** —
      a `def`, or the `_hold = functools.partial(hold, **deltas)` binding Phase A
      leaves in the majority of files — never to the `hold` imported from
      `tests.support.steps`. A rule reading "declared" as "`def`-declared" would
      reject the partial-migrated majority and pressure whoever hits it into
      weakening the one check that catches the silent fallback. Presence alone is satisfied by
      `filler=hold`, which is the exact fallback the decision forbids. Scope it
      to call sites where `fill_unheld` is not `False` — **14 of the 82 do not fill
      at all**, 8 of them inside §5.2's 66; at those no filler is ever called,
      and requiring one fails 8 correct migrations. Failing this check must fail the task, not
      warn.

## 3. Phase A — `_hold` (73 declarations, 73 files)

Ordered first: 45 of the 82 local `_playbook` compose over `_hold`
(`design.md` — Decision 1).

- [ ] 3.1 Classify all 73 by gate-independence of their delta set **and by
      parameter surface**: a local `hold()` cannot accept takes the wrapper form
      regardless of how stable its deltas are. Expected **59 PARTIAL / 14 WRAPPER
      / 0 unreproducible**, with the surface clause firing **zero times** — all
      73 are `(gate)` (63) or `(gate, **overrides)` (10), which `hold()` accepts
      unchanged. Confirm that inertness rather than assuming it; a file landing
      outside either expectation is read individually before it is migrated
      or kept.
- [ ] 3.1a Migrate the **3 zero-delta declarations** as
      `_hold = functools.partial(hold)`, not `_hold = hold`
      (`design.md` — Decision 7). An import alias is correct in substance and
      indistinguishable from the forbidden fallback to 2.3's check; the empty
      partial keeps the name file-local. They are `test_step_confirmer.py`,
      `test_automated_decision_wiring.py`, `test_automation_pass_release.py`.
- [ ] 3.2 Migrate the **59** as `_hold = functools.partial(hold, **deltas)`.
      Of the 59, **48 need three deltas or fewer and 55 need four or fewer**
      (over all 73 the figures are 58 and 69 — `design.md` — Decision 3
      tabulates both populations, and they must not be quoted across each
      other). Median local body: 13 lines. `functools.partial` gives the right precedence —
      a keyword passed at the call site wins over the partial's — so every
      existing `_hold(...)` call keeps working untouched.
- [ ] 3.3 Migrate the **14** as one-line wrappers. Their delta is computed from
      the gate argument, which a partial's fixed keyword cannot express: 11
      carry `handler=f"hold.{gate.replace('-','_')}"`, 3 a gate-derived `name`.
      The file list is not in `design.md` — re-derive it from 2.2's pass and
      confirm it comes to 14, rather than assuming the count.
- [ ] 3.4 Pass `name` back explicitly at the **16** whose local inherited
      `step()`'s `"Work this step asks for"` through their file's `_step`
      (`design.md` — Decision 4). This is the defect that took 101 proof
      failures to zero in the parent change; it is expected here, not discovered.
- [ ] 3.5 Read the **24** whose body is `attributes: dict` + `X(**attributes)`
      before migrating them. Their keywords are dict entries, not call keywords;
      2.2's runtime derivation is what makes them safe, and this task confirms
      the derivation saw them.
- [ ] 3.6 Delete the 73 local bodies (second commit of each pair) once the proof
      has settled to zero failures across **all three tiers**.

## 4. Phase B — `playbook()` gains `fillers_first`

**§4 and task 5.3 are one commit, not two phases.** 4.1 requires the parameter to
land with the declarations that need it and never speculatively; those
declarations are 5.3. So §4 describes that commit's contents and is executed when
§5.3 is reached — 4.1, 4.2 and 5.3 together, 4.2's test last within the commit.
Read as a preceding phase, the rule contradicts itself.

- [ ] 4.1 Add `fillers_first: bool = False` to
      `tests/support/playbook.py::playbook`, in the same commit as the 8
      declarations that need it — never speculatively. Document in the
      docstring *why* it cannot be normalised away:
      `LaunchPlaybook.__post_init__` sorts `gates` and not `steps`
      (`launch_playbook.py:830-844`), so step order is part of `==`.
- [ ] 4.2 Add its behaviour test to `tests/unit/support/`. This is the one task
      that moves a collected count, and it moves only `tests/unit/support`'s.
      Run it last within the §4/§5.3 commit so the two populations never mix.

      **The test is already written** — derived from the plan ahead of
      implementation, per `AGENTS.md` — *Test design before implementation*, by
      an author who does not write the implementation. It is
      `tests/unit/support/test_playbook_fillers_first.py`, **6 test functions**,
      with `test-manifest.md` beside this file recording what each serves and
      what was deliberately not tested.

      **The successor number is 52.** `tests/unit/support` 46 → **52**; the
      commit tier 2,528 → **2,534**; `tests/unit` outside support stays
      **2,246** and `tests/agents` stays **236** — verified by `--collect-only`,
      not assumed. That is the only collected-count move this change permits.

      **Four of the six fail today, and that is the expected state**, with
      `TypeError: playbook() got an unexpected keyword argument 'fillers_first'`
      — the absent-target state, so their assertions have not yet run. The other
      two pass on first run and must keep passing: they pin today's filler order
      (the control the new parameter must not disturb) and the fact that
      `LaunchPlaybook` does not sort its steps, which is what `design.md` —
      Decision 5 rests on. **Because the commit-time hook runs the whole tier,
      the test file cannot be committed before the parameter exists** — it lands
      in the §4/§5.3 commit with the implementation, which is what 4.1's "never
      speculatively" already requires.

## 5. Phase C — `_playbook` (82 declarations, 82 files)

- [ ] 5.1 Probe all 82 against the builder's parameter space. Expected **68
      REPRODUCIBLE / 8 ORDER-ONLY / 5 DIFFERENT-STEPS / 1 UNPROBEABLE**, in the
      six configurations `design.md` — Decision 5 tabulates. **Resolve the
      two-declaration disagreement Decision 7 records** between the static filler
      pass (14 non-filling, 10 of them REPRODUCIBLE) and the prover's `fill=none`
      count of 8, by reading the two rather than adopting whichever number the
      buckets prefer.
- [ ] 5.2 Migrate **66 = the REPRODUCIBLE 68 minus the 2 fill-all held back for
      call-site reading at 5.4** (those 2 need no new parameter either —
      Decision 6 forbids one — so "needs no parameter" is not what separates
      them) — 55
      `fill_unheld`, 8 `fill_unheld=False`, 3 `held_must_be_active=True`; 28 of
      them wrapping to inject a default subject when called with nothing.
      **Every one passes its own filler explicitly** (`design.md` — Decision 7).
      Which callable that is, is measured, not assumed: over the 82, 68 fill —
      **53 apply the file's own `_hold`, 14 delegate to a local `_fill()` that
      itself applies that `_hold`, and 1 applies `_step`**
      (`test_metric_step_journalling.py`, via `_metric_step`). The 14 pass the
      `_hold` their `_fill` wraps; the 1 passes its own step-shaped filler and
      is neither bent to fit `_hold` nor allowed to fall back on the default.
      Of the 82, **14 do not fill at all** — the 8 among this task's 66 pass
      `fill_unheld=False`, and the other 6 fall in 5.3–5.5's buckets.
- [ ] 5.3 Migrate the **8** ORDER-ONLY with `fillers_first=True`, against 4.1.
- [ ] 5.4 Read the **3** fill-all candidates at their real call sites
      (`design.md` — Decision 6). They are an **overlay on 5.2 and 5.3, not a
      fourth bucket**: two sit inside 5.1's REPRODUCIBLE 68 and one
      (`test_progress_launch_metric_step.py`) inside ORDER-ONLY, so the buckets
      still partition 82. The modes coincide unless a *blocking* step is
      actually passed, and `step()`'s canonical `blocking` is `False`. Migrate
      where equivalent; keep and record where not. Do **not** add a third fill
      mode.
- [ ] 5.5 Read the **5** DIFFERENT-STEPS and the **1** UNPROBEABLE individually.
      The bucket is named for its filler rule and **3 of the 5 do fill**; the
      other 2 do not, and the UNPROBEABLE one does not either.
      At least one of the five is an artefact of the probe harness feeding a
      `StepDefinition` to a single-parameter signature that means something else
      (`test_automated_decision_wiring.py`'s `confirmer`), so the bucket is a
      starting list, not a verdict.
- [ ] 5.6 Run 2.3's filler check over every file §5 touched. A green suite is
      not evidence here — a wrong filler changes which playbook a test exercises
      without changing whether it passes.
- [ ] 5.7 Delete the local bodies once the proof has settled across all three
      tiers.

## 6. Verification and record

- [ ] 6.1 Full three-tier run, all four static checks, and the assertion-identity
      check over the whole change against 1.3. Report the line delta.
- [ ] 6.1a Confirm the scope claim `proposal.md` makes — "nothing under `src/`
      is read, written or imported differently" — mechanically:
      `git diff --stat <base>..HEAD -- src/` is empty. It is the change's
      strongest guarantee and currently rests on recollection.
- [ ] 6.1b Update `tests/support/steps.py`'s `hold()` docstring with this
      migration's measured outcome (`proposal.md` — *Impact*). It currently
      describes 104 declarations, 73 of which this change removes. Leave its
      three canonical defaults and their derivation untouched — re-deriving them
      would re-open a decision this change depends on (`design.md` —
      *Non-Goals*).
- [ ] 6.2 **Record every declaration left local, with its measured reason**, in
      the final commit message — continuing the record task 8.3 established. A
      declaration kept because its variant resisted the builder is a finding,
      not a silence; a declaration kept because nobody looked is a defect.
- [ ] 6.3 Update `AGENTS.md` — *The shared harness* — with what this slice took
      and what it left, replacing the paragraph that currently reads "**291
      declarations in the recurring names are still local**, mostly the launch,
      playbook and catalog stores, which are blocked on `_playbook()` and
      `_hold()` being shared." That sentence is what this change answers.
- [ ] 6.4 Correct `docs/proposed-change-order.md`'s `share-the-aggregate-fakes`
      entry (`proposal.md` — *What Changes*, last bullet): the stores take the
      aggregate as a constructor argument and hold a `LaunchPlaybook`, so their
      instance state is structurally comparable and the *strong* proof reaches
      them. The ordering constraint stands; the stated reason overstates the
      coupling.
- [ ] 6.5 Raise as findings without acting on them: the remaining recurring
      helpers the census surfaces (`_provenance` 44, `_start` 35, `_launch` 34,
      `_resolve` 29, `_approval` 24), and the 17 unrelated `_fill` declarations
      that share a name with the 13 step-filling ones — a name collision worth
      recording before someone migrates across it.
- [ ] 6.6 Run `/code-review` over the full diff before calling the change done
      (`AGENTS.md` — *Independent review before completion*).
- [ ] 6.7 Open the pull request. Nothing reaches `main` except through one
      (`AGENTS.md` — *Deployment and configuration*); archive follows the merge
      as its own commit on its own branch.
