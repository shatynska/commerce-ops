Every task below is verified the same way unless it says otherwise: `uv run
ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports`,
and `uv run pytest tests/unit tests/agents` green, **with the commit tier's
collected count excluding `tests/unit/support/` unchanged from the §1 baseline
at every commit**. A task that changes that count has changed the suite, not
migrated it.

`tests/integration` carries 2 of the 129 declarations, so its collected count is
checked with `uv run pytest tests/integration --collect-only -q` at each **phase
boundary** — tasks 3.6, 4.8, 5.8 and 7.1 — and the tier is *executed* wherever a
proof result depends on it. Saying the cadence is the point: an unstated cadence
is how a tier gets claimed without being run.

Two numbers are tracked, never one re-baselined: the pre-existing tree, which
never moves, and `tests/unit/support/`, which has its own expected count.

Every task from §3 onward also runs the AST assertion-identity check over the
files it touches, excluding `tests/support/` and `tests/unit/support/`.

**Every migration task reports two numbers, not one:** how many declarations
its phase instrument closed, and how many the **standalone proof** closed
because the instrument reported zero comparisons for them. A declaration nothing
calls is dispositioned in the phase that migrates it, before the commit that
deletes its local — never deferred, because the local is one of the two versions
being compared. §6 is the register that reports the total; it is not where the
comparison happens. Stating this once here is what stops the rule being applied
to some phases and not others.

Never `uv run pytest` bare: it fails at collection on duplicate test basenames.
Always name the tiers.

## 1. Baseline

- [x] 1.1 Record, re-taken rather than inherited: `tests/unit` outside support
      **2,246**, `tests/unit/support` **52**, `tests/agents` **236**,
      `tests/integration` **159**; commit tier **2,534** collected.

      **Done, 2026-09-05**, at the branch point `523977e`.
- [x] 1.2 Confirm `tests/integration` actually runs before any proof result is
      trusted: `docker ps` shows `commerce-ops-postgres-1`, `.env.test` names a
      `_test`-suffixed database, and the tier reports 159 passed with **zero
      skips**. A worktree without `.env.test` skips the tier entirely and
      `pre-push` reports it `Passed` (`AGENTS.md` — *Working in a git worktree*).

      **Done, 2026-09-05.** `commerce-ops-postgres-1` up on `127.0.0.1:5432`;
      `uv run pytest tests/integration` → **159 passed in 42.3 s, zero skips**.
      Re-run this in any other worktree: `.env.test` is gitignored and
      `git worktree add` carries none, so the confirmation does not travel.
- [x] 1.3 Take the assertion-identity baseline over `tests/`, excluding
      `tests/support/` and `tests/unit/support/`.

      **Done, 2026-09-05:** `assert` **6,612**, `raises` **238**, helper-assert
      **759**, `parametrize` **172**, over **2,192** test functions in **332**
      files. Taken with the reference comparator, not a re-implementation: a
      hand-written detector that omits `_assert`-prefixed helper calls reports
      648 rather than 759 and would have made every later comparison meaningless.

## 2. The proof harness

- [ ] 2.1 Stand up the **equality proof** for the 42 playbook-serving and 24
      `CatalogProduct`-serving declarations: construct local and shared side by
      side, compare each served value field-wise. Reuse
      `~/share-the-playbook-builders/verify_pb.py` and `proof_plugin.py` rather
      than rebuilding — the plugin wraps at runtime and edits no files. **If
      either is not present in this worktree, rebuild it to the contract task 2.3
      states** — per-declaration comparison counts, zero reported as zero. Those
      paths sit outside the repository, `git worktree add` carries nothing from
      them, and a pruned sibling worktree takes them with it.
- [ ] 2.2 Stand up the **lockstep pairing** from
      `~/share-the-stateful-fakes/_paired_spike.py` so it can drive **any of the
      five subjects**, not only the 58 `Launch`-serving ones: drive local and
      shared together, comparing return value, raised exception and instance
      state after every executed call. **If it is not present in this worktree,
      rebuild it to task 2.3's contract, for the reason task 2.1 gives.** It is needed for the 58 by
      Decision 8, and task 3.4a may route a product reader to it too, so it is
      built general here rather than re-provisioned mid-phase.
- [ ] 2.3 Make both harnesses **count comparisons per declaration** and report a
      declaration with zero as zero, never as a pass. The 13 known silent ones
      (§6) must appear in that report, and any further one it finds is
      dispositioned by the standalone proof **in the phase that migrates it**, as
      tasks 3.4b, 4.3a and 5.5c do, and recorded in §6 — never filed to §6 alone,
      which by then has no local left to compare against.
- [ ] 2.4 Resolve import aliases in every classifier, and patch
      `tests.support.X` *before* importing a test module — `from … import y as
      _z` binds at import, and a classifier keyed on the bare name reports every
      migrated declaration as unmigrated.
- [ ] 2.5 Re-take, at this commit, the probe search that licenses every
      superset in the change — **for all three collaborators, not one**: no
      `getattr` name-probe, no `hasattr`, no `except AttributeError` and — the
      construct the first three cannot see — no **`callable(...)`** test or
      `except TypeError` fallback over a launch store, a playbook store or a
      product reader anywhere in `src/`. `callable()` is not hypothetical here:
      production uses it at four sites (`clickup_sync.py:134`,
      `activation_readiness.py:154` and `:184`, `playbook_authoring.py:391`),
      all four over `members` or `names` and none over these three — which is
      the result to re-confirm, not to assume.
      It is taken here, in §2, because Decision 7's `reads`/`calls` superset
      ships in §3, two phases before §5. Every spelling-based sweep of this
      ground has come back stale; do not inherit the search made while planning.
      Note its scope: the licence covers the doubles' own method surfaces and
      **not what they serve** — `automation_pass.py:563` probes the served
      product by `name`/`sku`, where the same-value invariant still bites.
- [ ] 2.5a License `__call__` on the playbook store **here in §2, before §4
      implements it** — and measure both sides, because they are different
      questions. **Deadness** (is the spelling the 6 locals carry ever reached?):
      wrap and mutate as task 5.2 does. **Addition-safety** (is adding it to the
      declarations that lack it safe?): give those declarations a `__call__` that
      raises, run all three tiers, confirm green. A search for `getattr`/
      `hasattr` cannot answer the second — `callable()` and a `TypeError`
      fallback read `__call__` without naming it, and production uses `callable()`
      at four sites today. Carry the spelling on that evidence or drop it.
      Demanding execution-proof before dropping two spellings while adding a
      third on six declarations' say-so is not a position this change can hold.
- [ ] 2.6 Validate every expression harvested out of a file **by evaluating it**
      at build time against the call sites it will be used at. One of 179 last
      slice was not evaluable outside its own function; a one-in-179 defect is
      not one review finds.

## 3. The product reader — 24 declarations

- [ ] 3.1 Add `FakeProductReader` to `tests/support/fakes.py`: an async
      `__call__(product_id)` answering **whatever product object it is handed,
      unconstrained** — not annotated to `tests/support/values.py::CatalogProduct`,
      per design.md Decision 7, since constraining it would move the same-value
      invariant out of the visible call site and into the double. It stores
      `reads` as a **list** and derives `calls` as a read-only property over the
      same list object. Its docstring says that the playbook store spells `reads`
      as an `int` with no `calls`, and why — `AGENTS.md`'s `clickup_user_id`
      precedent is that each type names the trap.
- [ ] 3.2 Add its `_conforms: SomeProtocol = FakeProductReader(...)` assignment
      beside it — the assignment, not the protocol's existence, is what makes a
      drifted double a `mypy` error.
- [ ] 3.3 Add its contract tests under `tests/unit/support/`, and state the new
      expected count for that directory.
- [ ] 3.4 Classify the 24 against the shared type **by running each**, and
      state expected buckets before migrating: 10 answer a held product, 6
      record into `reads`, 4 into `calls`, 4 build or look up. A migration task
      whose population total is also its target cannot report a shortfall.
      Record per site whether `calls` is **assigned** or **mutated**:
      `AGENTS.md`'s `Member.id` precedent is that the assigned spelling must be
      the stored one, since a read-only property cannot receive an assignment.
      Planning measured **no site assigning either name** on a catalog reader —
      the one `.calls = []` in `tests/` is `_ReadRecorder`, a different double —
      so storing `reads` and deriving `calls` is safe; re-take it, and if any
      site assigns `calls`, store `calls` and derive `reads` instead.
- [ ] 3.4a Check the equality proof's precondition **by construction over every
      distinct type the 24 actually serve** — `dataclasses.is_dataclass(T)` and
      `T.__dataclass_params__` — rather than assuming it from the name.
      Planning measured 22 importing `tests/support/values.py::CatalogProduct`
      and 2 declaring their own `@dataclass(frozen=True)`, so all 24 serve a
      frozen dataclass; re-take it, and route any non-frozen type to the lockstep
      pairing instead. Asserting the strong proof over an unmeasured population
      is the failure `AGENTS.md` already records.
- [ ] 3.4b Migrate the 24 callable declarations against those buckets, in
      commits that land the type and its first call sites together — the
      `pre-commit` hook runs the whole tier, so neither can be committed alone.
      **19 are closed by the equality proof; the 5 that execute no calls are
      closed by the standalone proof in this phase, before the commit that
      deletes their locals** — construct both versions directly and compare while
      both are still in the tree. Deferring them to §6 would leave nothing to
      compare against. Report actual against expected, and report the 5
      separately from the 19.
- [ ] 3.5 Record the 5 scope-sniffing catalog ports as **kept local**, citing
      the disposition that already exists — `share-the-stateful-fakes` task 10.3
      and its proposal, *"four of those five apply access-scope filtering that no
      `_Catalog` declaration performs"* (design.md Decision 6). Do not attribute
      it to `FakeCatalogPort`'s docstring, whose two declarations are a different
      population; that docstring is accurate and is not to be "corrected".
- [ ] 3.6 Phase boundary: run `tests/integration` (it holds one `_FakeCatalog`)
      and confirm 159 passed, zero skips.

## 4. The playbook stores — 42 declarations

- [ ] 4.1 Add `_FakePlaybooksBase` holding the constructor, `refusal`, `reads`
      and a shared `_answer()` that **increments `reads` first and raises the
      refusal second** — the order both locals use
      (`test_gate_progression_pass.py:355-358`,
      `test_advance_and_ask.py:362-365`), so a refused read still counts — and
      defining **no** `get`, with `FakePlaybooks` (sync `get`) and
      `AsyncFakePlaybooks` (async `get`) as **siblings** over it — not
      `AsyncFakePlaybooks(FakePlaybooks)`, which `mypy` rejects as an
      incompatible override and which this file's preamble would therefore block
      at the first commit of the phase. Model the four measured axes of design.md
      Decision 2: a held playbook; a `refusal: Exception | None = None` keyword
      (3 declarations); a **`reads: int`** incremented in `get` (2) — an integer,
      not a list, and with **no derived `calls`**, because both locals spell it
      `self.reads = 0` / `self.reads += 1` and `test_gate_progression_pass.py:843`
      asserts `reads == 1`, while `calls` has a measured population of zero on
      this double; and `__call__` (6) spelled
      `async def __call__(self, *args: Any, **kwargs: Any)` delegating to `get`,
      never as an `attr = get` alias, which would narrow six locals' signature to
      one positional argument, and placed **on `AsyncFakePlaybooks`, not on the
      base** — that placement is what sizes the superset at 1 declaration rather
      than 32 (the base is shared by the two playbook stores only;
      `FakePlaybookRepository` does not inherit it), and is what task 2.5a's
      addition-safety measurement is scoped to.
      Run the completeness search each superset needs:
      if any production reader probes for `refusal` or `reads`, hold those
      declarations back and restate §4 as 39 of 42 rather than shipping the
      keyword. The type's docstring records that its `reads` is an `int` while
      the product reader's is a list with a derived `calls`, per `AGENTS.md`'s
      `clickup_user_id` precedent.
- [ ] 4.1a Add the `_conforms` assignments for **both** `FakePlaybooks` and
      `AsyncFakePlaybooks` — two protocols, sync and async, since the sibling
      split means neither type satisfies the other's. Without them the two types
      serving 42 declarations lose the only mechanism that makes a drifted double
      a type error, which is the goal's "one per type", not one per pair.
- [ ] 4.2 Add `FakePlaybookRepository.serving(source)`, returning a subclass
      whose `get` reads `source` **at call time** — a `LaunchPlaybook` answered
      directly, a zero-argument callable invoked per call (design.md Decision 3).
      Binding a value at subclass creation is the defect this form exists to
      avoid, not a simpler variant of it.
- [ ] 4.2a Add the `_conforms` assignment for `FakePlaybookRepository` in its
      **class-object** form — `_conforms: type[SomeProtocol] = FakePlaybookRepository`
      — since production constructs it itself and it cannot be instantiated
      argument-free at module level (`AGENTS.md`). Without the assignment `mypy`
      stops reporting drift for the one double production builds.
- [ ] 4.3 Add contract tests for all four §4 classes under `tests/unit/support/`,
      including one that pins `serving`'s call-time read: bind a mutable source,
      change it, and assert the second `get` sees the change.
- [ ] 4.3a Disposition the 2 silent `_FakePlaybooks` by the **standalone
      proof**, in this phase and before the commit that deletes their locals:
      construct both versions directly and compare. They execute no calls, so
      the equality proof reports zero for them and zero is not a pass.
      **Both are sync** (`test_progress_launch.py`,
      `test_progress_launch_metric_step.py`), so they sit inside task 4.4's 25,
      not 4.5's 7.
- [ ] 4.4 Migrate the 19 plain sync `_FakePlaybooks` plus the 6 that declare no
      `__init__`, the latter by passing at the call site the module constant they
      closed over — they are installed as instances
      (`_install(monkeypatch, module, "playbooks", _FakePlaybooks())`), not
      patched as classes, so no new type shape is needed. **Expected: 25 of 25 —
      23 closed by the equality proof, 2 by task 4.3a**, which is the two-number
      report the preamble requires.
- [ ] 4.5 Migrate the 7 async `_FakePlaybooks` — 4 `__call__` aliases, 2
      refusal-with-counter, 1 refusal. **Expected: 7 of 7 — all 7 closed by the
      equality proof**, or 4 of 7 if 4.1's completeness search holds the refusals
      back. None of the 7 is silent.
- [ ] 4.6 Migrate the 10 `_FakePlaybookRepository` against their measured split:
      4 inline bodies to `serving(playbook(...))`, 5 `_playbook()` calls to
      `serving(_playbook)`, and `test_clickup_webhook_automated_step.py` to
      `serving(lambda: _SERVED[0])`. **Expected: 10 of 10.** These are
      closed by the **equality proof**: `LaunchPlaybook` is a frozen dataclass,
      so the built playbook compares field-wise against what the local built.
      They build rather than receive, which looks like pairing limit 1, but
      `AGENTS.md` attaches that limit to a plain-class double whose `==` is
      identity, so it does not bite here (Decision 8). For the `_SERVED` one the twin must be driven
      **past** both rebindings (lines 359 and 398), or the proof cannot see the
      staleness the call-time read exists to prevent.
- [ ] 4.7 Where a call site cannot take the shared type unchanged, subclass and
      adapt the signature in three lines; the proof still runs over the adapter.
      Where the *values* or the declaration *form* differ, keep the local and
      record the reason. Report actual against every expected figure above; a
      §4 that completes reading "42 of 42" without them has not reported a
      shortfall, it has hidden one.
- [ ] 4.8 Phase boundary: **execute** `tests/integration` — it holds one
      `_FakePlaybookRepository`
      (`test_clickup_sync_job_containment_live.py`), so a proof result in this
      phase depends on the tier — and confirm 159 passed with zero skips.
      Collecting is not running: a worktree without `.env.test` skips the tier
      entirely while `pre-push` reports it `Passed`.

## 5. The launch store — 58 declarations

- [ ] 5.1 Confirm task 2.5's probe search still holds at this commit for the
      launch store specifically — the tree has moved by three phases since it
      was taken, and every spelling-based sweep of this ground has come back
      stale.
- [ ] 5.2 Re-take the measured-dead licence for `list_launches` and `all` **by
      execution**, not by search: wrap both across all three tiers and confirm
      zero calls, then mutate them to raise and confirm the commit tier stays
      green. Prefer the mutation wherever the interpreter can reach a spelling
      implicitly.
- [ ] 5.3 Add `FakeLaunches` to `tests/support/fakes.py` presenting
      `get_by_product_id`, `list_active`, `list_all` and `save` over launches it
      is handed — and **not** `list_launches` or `all`. Give it the same
      `serving(source)` classmethod design.md Decision 4 defines for it — **not
      Decision 3's, which does not transfer**: this one's subclass must
      `__init__(*args, **kwargs)` and *discard* what production passes it, since
      a `*launches` constructor would otherwise accept the `(db)` production
      hands the patched class and hold a `Session` as a launch. All four read
      methods resolve `source` at call time; `source` is a `Launch`, an iterable
      of them, or a zero-argument callable.
- [ ] 5.4 Give it a docstring recording, at the double itself, that
      `list_active` deliberately does not filter graduated launches, and why:
      `test_a_graduated_launch_is_left_alone` hands one in precisely to prove the
      pass leaves it alone, and a filtering double keeps that test green while
      deleting what it tests (design.md Decision 5).
- [ ] 5.5 Add its `_conforms` assignment and contract tests, including one that
      pins the non-filtering behaviour so a later "improvement" fails loudly.
- [ ] 5.5a Classify all 58 against the shared type **by running each**, and
      state expected buckets before migrating. Constructor form across the 58:
      `*launches` **35**, `launch` **15**, `tuple[Launch, ...]` **3**, `()`
      **1**, no `__init__` **2**, `(*args, **kwargs)` **2**. A variadic shared
      constructor takes the first four directly (54). The remaining four are
      each decided by a named rule, not by an escape hatch (design.md
      Decision 4):

      - the **2 `(*args, **kwargs)`** ones are class-patched and answer
        `type(self).launch`, a mutable class attribute — they take
        `FakeLaunches.serving(source)` as **Decision 4** defines it — which
        discards production's constructor arguments; Decision 3's form does not
        transfer;
      - the **2 `@dataclass`** ones are a declaration-form **keep** under
        `AGENTS.md`, unless this task measures that nothing relies on the
        generated `__eq__` or `__repr__`. **These are the same two declarations
        as the "no `__init__`" bucket** — measured, the two sets are identical
        (`test_thread_anchor_resolution.py`, `test_thread_establishment_race.py`)
        — so four declarations fall outside the variadic constructor, not six,
        and the 56-of-58 target reconciles with the census above it.

      **Expected: 56 of 58 migrated, 2 kept.** Report actual against it.
- [ ] 5.5b Measure whether either class-patched declaration rebinds
      `type(self).launch` after production constructs the double. Call-time
      reading was proved a correctness condition for the *repository*
      (`_SERVED[0]`, rebound mid-file); for these two it is currently inherited
      by analogy. It is the safe default either way — but record which of the two
      it is, rather than letting an unmeasured claim stand as a measured one.
- [ ] 5.5c Disposition the 6 silent `_FakeLaunches` by the **standalone proof**,
      in this phase and before the commits that delete their locals: construct
      both versions directly and compare. The pairing reports zero comparisons
      for them, and zero is not a pass.
- [ ] 5.6 Migrate the 32 `_FakeLaunches` — 26 closed by the lockstep pairing with
      its four recorded limits stated where they bite, 6 by task 5.5c.
- [ ] 5.7 Migrate the `_FakeLaunchStore` declarations: **24 of 26 migrated, 2
      kept**. The 2 kept are the `@dataclass` pair — measured, both carry this
      name — `tests/unit/launch/application/test_thread_anchor_resolution.py` and
      `test_thread_establishment_race.py`, a declaration-form keep under
      `AGENTS.md` (task 5.5a). With 5.6's 32 that is **56 of 58**, reconciling
      with 5.5a and Decision 4. **All 24 are closed by the lockstep pairing, 0 by
      the standalone proof** — none of the 26 is silent; the 6 silent launch
      stores are all `_FakeLaunches` and are closed by task 5.5c.
- [ ] 5.8 Phase boundary: `tests/integration` collected count unchanged, tier
      executed, 159 passed and zero skips.

## 6. The thirteen silent declarations — rollup

**Each is dispositioned in the phase that migrates it** (tasks 3.4b, 4.3a,
5.5c), not here. §6 is the register, not the action: by the time it runs, the
locals the standalone proof compares against have been deleted by their own
phase's commits, so a §6 that still tried to construct them would have nothing
to construct — and would degrade into inspecting the shared version alone, which
is exactly the "reports zero, not pass" failure Decision 8 names.

- [ ] 6.1 Roll up the 13 — 6 `_FakeLaunches`, 5 `_FakeCatalog`, 2
      `_FakePlaybooks` — recording for each the phase that closed it and the
      commit its local was constructed from. Report the count **separately**;
      never fold it into any phase's pass total.
- [ ] 6.2 For each, record *why* it is silent — never called by its file, or
      built at import before the harness can wrap it — since the two have
      different consequences for the next slice.

## 7. Record and review

- [ ] 7.1 Full verification: `ruff check`, `ruff format --check`, `mypy`,
      `lint-imports`, all three tiers green, all four collected counts at their
      §1 values except `tests/unit/support/`, and the assertion-identity check
      against the §1.3 baseline over every file touched.
- [ ] 7.1a Confirm the proposal's *"no production code changes"* claim
      mechanically rather than from recollection:
      `git diff --stat <branch-point>..HEAD -- src/` is empty. The predecessor
      added this task for exactly this reason.
- [ ] 7.2 Update `AGENTS.md`'s *The shared harness* section with what this slice
      took and what it left, including the two rules it establishes: **a shared
      double must not implement the filter its subject is being tested for**,
      and **a double installed by patching a class needs a class-producing
      constructor, never a mutable class attribute**.
- [ ] 7.3 Record every declaration left local with its measured reason —
      continuing the record the three predecessors established.
- [ ] 7.4 Run `/code-review` over the diff. Both reviews run, not one: the
      equality proof passed everything last slice and `/code-review` then found
      ten helpers whose override had stopped winning — values identical, calling
      contract broken, suite green.
- [ ] 7.5 Act on the review's findings.

## 8. Ship

- [ ] 8.1 Open the pull request for `share-the-aggregate-fakes` and merge it.
- [ ] 8.2 Archive on its own branch in a later pull request
      (`openspec archive share-the-aggregate-fakes --yes`), deleting entry 3
      from `docs/proposed-change-order.md` per that file's own rule.
