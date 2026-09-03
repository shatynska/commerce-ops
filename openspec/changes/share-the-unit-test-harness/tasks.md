Every task below is verified the same way unless it says otherwise: `uv run
ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports`,
and `uv run pytest tests/unit tests/agents` green, **with the collected test
count of the three tiers excluding `tests/unit/support/` unchanged from the 1.1
baseline at every commit**. A task that changes that count has changed the
suite, not migrated it.

The exclusion is how task 6.15 adds its fake-behaviour tests without weakening
the invariant into "unchanged unless a task says otherwise" — under an
exception, a silently dropped test nets against a newly added one and the
invariant stops catching what it exists to catch. Two numbers are tracked
instead of one re-baselined: the pre-existing tree, which never moves, and
`tests/unit/support/`, which has its own expected count. Run 6.15 last within
§6 so the two populations never mix.

Every task from §2 onward also runs the AST assertion-identity check
(`design.md` — Decision 7a) over the files it touches. For a two-commit
Population B migration, 7(a) is evaluated across the commit **pair** — the
7(b1) wrapper contains an `assert`, so 7(a) run against the intermediate commit
would fail by construction.

§6 splits by what can be proved. Tasks **6.1–6.7** migrate the 334 value-builder
declarations and run the equality proof **7(b1)** — the instrumented checking
wrapper, which adds no test function and so does not move the collected count.
Tasks **6.8–6.14** migrate the **455** fake declarations, where `==` is identity
and 7(b1) is inexpressible; they run **7(b2)** instead. Note the proportion: the
weaker substitute covers the *majority* of Population B, not a remainder.

7(b2) is weaker in named ways. It catches a fake that models less than its
protocol, and a dropped spelling — provided the search covers `src/`, since the
callers are production shape probes that fall through silently rather than
raising. It does **not** catch a fake with the same surface and different
behaviour (risk 3), and the fake that models *more* and thereby redirects a
production probe (risk 4) is guaranteed by Decision 6 rather than merely
possible — see task 6.10, which is its worst case.

**Two standing prohibitions**, both of which a migrator will be tempted by:

- Never source a spec-restating constant from production
  (`design.md` — Decision 2).
- Never repoint a test from `alembic/data/playbook_v1.yaml` to
  `playbook_reference.yaml`. The staleness is real, recorded, and owned by
  `docs/deferred-work.md:835-890` — not by this change
  (`design.md` — *A trap this migration walks straight into*).

## 1. Foundation

- [x] 1.0 **Stand up this worktree's `.env.test` first** — its own database,
      `_test`-suffixed, `alembic upgrade head` **and**
      `uv run python -m commerce_ops.seed_playbook`, per `AGENTS.md`'s worktree
      obligations. Before 1.1, not at 8.1: a baseline taken while the
      integration tier skips in its entirety is not comparable with a final
      verification while it runs, and `pre-push` reports the skipping tier as
      `Passed`. `AGENTS.md` records that this exact confusion already produced a
      merged pull request claiming a tier that had skipped.
- [x] 1.1 Record the baseline: collected test count per tier (`uv run pytest
      --collect-only -q`), and wall time — with the integration tier actually
      running. Everything after this is compared against it.

      **Recorded 2026-09-03, on `1fd93d9`, database `commerce_ops_harness_test`
      migrated and seeded (358 steps):**

      | tier | collected | result | wall |
      |---|---|---|---|
      | `tests/unit` | 2,246 | — | — |
      | `tests/agents` | 236 | — | — |
      | `tests/unit tests/agents` | **2,482** | 2,482 passed | 74.7 s |
      | `tests/integration` | **159** | 159 passed | 19.7 s |
      | total | **2,641** | green | ~95 s |

      The integration run set `COMMERCE_OPS_REQUIRE_DATABASE=1`, so a skipping
      tier would have failed rather than reported green. 159 passed, none
      skipped — the tier genuinely ran.

      **Measured per tier, not by bare `uv run pytest`, and that is a finding
      rather than a convenience.** Bare `uv run pytest` — the command `AGENTS.md`
      documents — fails at collection on `main` today: `testpaths` names all
      three tiers, and two basenames repeat across them
      (`test_product_hazard_categories.py` in `tests/unit/catalog/domain/` and
      `tests/integration/catalog/`; `test_placeholder.py` in `tests/unit/` and
      `tests/integration/`). With pytest's `prepend` import mode and no
      `__init__.py` in those directories, both import as the same top-level
      module and collection is interrupted. Every gate — `pre-commit`,
      `pre-push`, CI — invokes the tiers in *separate* commands, so none of them
      ever hits it. Pre-existing, not caused by this change, and **not fixed
      here** (see 8.4).
- [x] 1.2 Write the two throwaway checkers to the scratchpad: the AST
      assertion-identity comparator (Decision 7a) and the instrumented
      equivalence wrapper generator (Decision 7b1). Not committed — but the
      comparator's **per-file before/after digest goes into each migration
      commit message**. Goal 3 is a rule a reviewer can check mechanically, and
      task 8.5 hands `/code-review` a ~300-file diff: a checker that leaves no
      record lets the reviewer neither re-run it nor verify by eye, only trust
      that it was run.
- [x] 1.2a The comparator collects **four** node kinds, not one: `ast.Assert`
      (6,623), `pytest.raises` `With` items (238), `ast.Expr` wrapping a `Call`
      whose callee tail starts `assert` or is `fail` (757), and
      `@pytest.mark.parametrize` decorators (172). Kinds 3 and 4 are not
      optional — an `assert_called_with` is not an `ast.Assert`, and a
      parametrize table is where expected values hide.
- [x] 1.3 Add `pythonpath = ["."]` to `[tool.pytest.ini_options]`. **Commit
      alone**, with no other change, and confirm the 1.1 baseline is unmoved
      (`design.md` — Decision 1).
- [x] 1.4 Create `tests/support/__init__.py` — empty, exporting nothing. Modules
      are imported by path, so the package cannot become one namespace
      everything pulls from.
- [x] 1.5 Create `tests/support/protocols.py` with its module docstring only,
      recording that `unify-launch-adapter-dependencies` replaces these with the
      production protocols. **Each protocol is added by the §6 task that adds its
      fake** — the shape comes from reading the variants, so authoring them up
      front would be guessing (`design.md` — Decision 6).

## 2. Phase A — the playbook framework constants

The largest single cluster: 159 files. Mechanical; no test body may change.

- [x] 2.1 Write `tests/support/playbook.py` carrying `SPECIFIED_GATE_ORDER`,
      `CONFIRMATION_GATES`, `FINAL_GATE`, `opening_for` and `gates` as
      **literals**, with the module docstring stating why they must never be
      sourced from `launch_playbook.GATE_SEQUENCE` (Decision 2). **Mechanise the
      prohibition as a name deny-list, not a module ban**: `tests/support/
      playbook.py` must import no `GATE_SEQUENCE`, `gate_position`,
      `_SPECIFIED_GATES`, `_SPECIFIED_GATE_IDS`, `_GATE_POSITION` or
      `_FINAL_GATE`. It *must* import the `Gate` and `GateOpening` types, since
      `gates()` constructs them — a blanket module ban was this task's first
      phrasing and forbids the very type the module exists to build. Decision
      2's failure mode unparses identically either way, so 7(a) cannot see it
      and task 2.6's human read is otherwise the only guard.
- [x] 2.2 Migrate the 159 files declaring `SPECIFIED_GATE_ORDER` to an aliased
      import. Verify no line at or after each file's first test changed.
- [x] 2.3 Migrate the 128 files declaring `CONFIRMATION_GATES`, including the one
      formatting variant.
- [x] 2.4 Migrate the 120 files declaring `_opening_for`.
- [x] 2.5 Migrate the 93 files declaring `_gates`. Six variants: confirm the
      83-file dominant variant is the one hoisted; record the other five as
      migrated or deliberately left.
- [ ] 2.6 Confirm the 15 files that *assert* on `SPECIFIED_GATE_ORDER` still
      assert against the literal, not against production
      (`test_playbook_coherence_by_status.py:472` is the reference case).
- [ ] 2.7 Record any file whose Population A symbol is declared **below** its
      first test. Those are not migrated here — they go to §6's procedure
      (Decision 7a). The A rule is never relaxed to fit a file.

## 3. Phase A — the HTML assertion helpers

37 files carry a hand-rolled HTML parser and its query helpers.

- [ ] 3.1 Read all 8 `_TreeParser` variants and establish whether they differ in
      behaviour or only in formatting and docstrings. Any that differs in
      behaviour is not Population A — record it and leave those files to §6.
- [ ] 3.2 Write `tests/support/html.py`: `TreeParser`, `Node`, `Text`, `tree`,
      `elements`, `texts`, `all_text`, `attribute_text`, `classes`, `carries`,
      `element_hidden`, `element_disabled`, `inherited`, `ancestors`, `nearest`,
      `size`, `flat`, plus `VOID_TAGS`, `HX_VERBS`, `HIDDEN_CLASSES`.
- [ ] 3.3 Migrate the 37 files to aliased imports preserving the local
      `_`-prefixed spellings. Verify no test body changed.

## 4. Phase A — the admin-session harness and fixed domain literals

- [ ] 4.1 Write `tests/support/admin.py`: `SESSION_COOKIE`, `SESSION_VALUE`,
      `fake_verify`, `signed_headers`, `signed_client`, `ADMIN_IDENTITY`.
- [ ] 4.2 Migrate the 45 files declaring `_SESSION_COOKIE` / `_SESSION_VALUE` /
      `_fake_verify`, and the 18 declaring `_signed_headers`.
- [ ] 4.3 Write `tests/support/fixtures.py` with the **fixed** literals only:
      `LAUNCH_DATE`, `PRINCIPAL`, `ALICE`, `ALICE_NAME`, `BOHDAN`, `BOHDAN_NAME`,
      `MARKETPLACE`, `PRODUCT_NAME`, `PRODUCT_SKU`, `STEP_ID`, `HANDLER_NAME`.
- [ ] 4.3a `A_DISCIPLINE` is **not** a fixed literal and does not belong in 4.3.
      Its 42 declarations are `next(iter(Discipline))` (24), `DISCIPLINES[0]`
      (13), `Discipline("listing")` (3) and `Discipline("strategy")` (2) — the
      first two computed, the last two pinned. Provide `any_discipline()`
      reproducing the computed form, since pinning a literal agrees with
      `next(iter(Discipline))` only while the enum's declaration order holds.
      The 5 pinned declarations are outliers and stay. Decide in the same task
      whether `_any_discipline` (40 files) joins Population A or stays local, and
      record which.
- [ ] 4.4 Add `product_id()` as a **factory**, not a constant. The migrated file
      keeps a module-level `PRODUCT_ID: Final = product_id()` — one identifier per
      module, exactly as today; only the construction moves. 68 files currently
      evaluate `ProductId(str(uuid.uuid4()))` at module level, and a shared
      constant would give all 68 the same value (Decision 8).
- [ ] 4.5 Migrate the files carrying the dominant variant of each 4.3/4.4 symbol.
      **Leave every outlier in place** and list them in the commit message; an
      outlier differs on purpose until shown otherwise.
- [ ] 4.6 Confirm no `uuid`, `datetime.now` or counter has been frozen into a
      module-level name anywhere in `tests/support/`.

## 5. Phase A — hoist the Slack listener-draining wrapper

- [ ] 5.1 Move `_DrainsDeferredListeners` to `tests/support/slack.py`, carrying the
      omni_agent conftest's full docstring argument (the launch conftest's own
      docstring says it is a mirror and defers to it).
- [ ] 5.2 Reduce both driving conftests to a thin `slack_asgi_app` fixture calling
      it. `tests/conftest.py` and `tests/integration/conftest.py` are not touched
      (Decision 10).
- [ ] 5.3 **Phase A checkpoint.** Full gate green, test count unchanged, line
      reduction recorded against the ~6,640-line floor. This is the last Phase A
      task, and everything through it is a coherent, independently mergeable unit
      (Decision 11).

## 6. Phase B — the builders

Designed in `design.md` Decisions 4–6. Each file is migrated in two commits:
add the builder and prove equivalence against the local variant at every call
site, then delete the local variant. A variant the builder cannot reproduce
leaves its file **unmigrated and recorded** (task 8.3) — never forced.

- [ ] 6.1 Write `tests/support/steps.py::step(**overrides)` with the canonical
      default set from Decision 4's table, derived over the **121**
      `**overrides`-only declarations. Four keys are unanimous (`scope`,
      `status`, `hazard`, `provenance`); the three canonicalised partially-set
      keys (`description`, `assignees`, `handler`) carry values identical to
      `StepDefinition`'s own dataclass defaults; `confirmer`, `starts_at_gate`,
      `after_steps` and `metric_id` are omitted, not defaulted.
- [ ] 6.2 Add `hold(gate, **overrides)` to the same module with **exactly three**
      defaults — `blocking=True`, `identifier=f"hold.{gate}"`,
      `name=f"Blocking work holding the {gate} gate"`. Everything else inherits
      `step()`'s canonical value. Derive by counting an omitted keyword as the
      value it actually produces, over all 104 declarations: counting only the
      passers reverses `kind`, `handler`, `assignees`, `timing_anchor` and
      `discipline` against the real majority, which is how two earlier drafts of
      this table got it wrong in opposite directions (Decision 5).
- [ ] 6.3 Add `playbook(*steps, version, gates, fill_unheld, filler,
      held_must_be_active)` to `tests/support/playbook.py` (Decision 5).
      `held_must_be_active` defaults `False` because 85 of 95 variants omit the
      status check; `fill_unheld` defaults `True` because 69 of 95 fill. **`filler`
      takes no canonical default** — of those 69, 36 fill with an automated filler
      and 33 with a human one, so a file passes its own `_hold` partial.
- [ ] 6.4 Migrate the **121** `**overrides`-only `_step` files as
      `_step = functools.partial(step, **deltas)`. 69 of the 121 need two
      overrides or fewer; 94 need four or fewer. Proof 7(b1) per file.
- [ ] 6.5 Migrate the **14** `_step` files whose local signature is
      `(identifier: str, **overrides)` with a one-line wrapper, not a partial —
      a partial over `step(**overrides)` cannot accept their positional argument.
      Read these individually; the diff-shape argument does not cover them, and
      two are among the largest files in the suite
      (`test_launch_admin_detail.py:321`, `test_launch_surface_vocabulary_rules.py:382`).
- [ ] 6.6 Migrate all **104** `_hold` files as
      `_hold = functools.partial(hold, **deltas)` — both signatures are
      partial-reproducible, since `gate` stays positional. Its own task rather
      than a clause of 6.4: `hold()` carries only three defaults, so most files
      will pass more deltas than the `_step` histogram would suggest, and the
      two populations should not be reported as one. Proof 7(b1) per file.
- [ ] 6.7 Migrate the `_playbook` files: the 40 `()` and 13 `(*steps)` as
      partials, the **31 `(steps)`** — which take a positional tuple a partial
      cannot deliver — as one-line wrappers. Each of the **69** that fill unheld
      gates passes its own `_hold` partial as `filler`; do not let a file fall
      back on the default, since 36 of the 69 fill with an automated step and 33
      with a human one. **The 11 one-off signatures are not migrated**; record
      them under 8.3.
- [ ] 6.8 `tests/support/members.py`: `Member`, `FakeMembers`, `FakeMembersStore`
      (47 / 43 / 38 declarations). The fake provides **one** method,
      `list_members()`, not the three spellings the current fake carries — that
      is what makes `clickup_sync._members:128` deletable by the successor
      change. Add the `MembersReader` protocol and its `_conforms` assignment.
      **Surface-and-behaviour note, licensed by Decision 7(b2):** dropped —
      `members = list_members` (present in 34 files) and `async def __call__`.
      Search **`src/` as well as `tests/`**: those two spellings exist to
      satisfy `clickup_sync._members`'s three `getattr` branches, so the caller
      is production and a probe falls through silently rather than raising
      (risk 2). Kept — `list_members()`, same shape and order as the dominant
      local variant. Added — none over the dominant variant; if the shared
      `Member` gains an attribute the local lacked, name the probe sites
      (`clickup_sync._member_identifier:139`,
      `playbook_authoring.member_identifier:266`) and the branch each takes
      before and after (risk 4).
- [ ] 6.9 `tests/support/launches.py`: `FakeLaunches`, `FakeLaunchStore`,
      `FakeSession` (32 / 26 / 12). Protocol plus `_conforms` assignment for each.
- [ ] 6.10 The `LaunchProgressed` double models `crossed`,
      `awaiting_confirmation`, `awaiting_gate`, `gate_id` and `current_gate` —
      every attribute `gate_progression_job.py:256-279` probes for (Decision 6).
      **This is risk 4's worst case.** `_awaiting_gate:267` returns the *first*
      of `("awaiting_gate", "gate_id", "current_gate")` that is a non-empty
      string, and the local doubles model them unevenly — `current_gate` in
      **55** files, `gate_id` in 26, `awaiting_gate` in **5**. A complete double
      would match on `awaiting_gate` where almost all of them fall through to
      `current_gate`, returning a different gate with `mypy`, 7(a), the search
      and the suite all passing.
      **State and verify the same-value invariant, once, rather than analysing
      55 files:** `awaiting_gate` and `gate_id` derive from the same argument as
      `current_gate` unless a caller sets them apart; `crossed` defaults `()`
      and `awaiting_confirmation` defaults `False`, matching what each
      `getattr` fall-through produced. Record the invariant in the double's
      surface-and-behaviour note. A caller that deliberately sets two spellings
      apart is the case the note exists for.
- [ ] 6.11 `FakeStepStore`, `FakePlaybooks`, `FakeHandlerRegistry` (37 / 32 / 12).
- [ ] 6.12 `tests/support/slack.py`: `RecordingSlackApi`, `FakeSlackResponse` — 12
      declarations, 12 variants, no two alike. Expect this to be the slowest and
      the most likely to leave files unmigrated.
- [ ] 6.13 `tests/support/clickup.py`: `FakeClickUp`, `TaskMapping`, `FakeMapping`,
      `CreatedTask`, `FakeTask`.
- [ ] 6.14 `tests/support/catalog.py`: `CatalogProduct`, `FakeCatalog` (40 / 29).
- [ ] 6.15 Add direct behaviour tests for the five stateful fakes in
      **`tests/unit/support/`** (collected; `tests/support/` is not), pinning
      return ordering, absent-key behaviour and initial state for
      `FakeMembersStore`, `FakeStepStore`, `FakeLaunches`, `FakePlaybooks` and
      `FakeSession`. These do not close risk 3 — they pin the shared fake
      without comparing it to the local one — but they make half of each
      surface-and-behaviour note executable rather than asserted, which is the
      most available where `==` is identity. **Run this last within §6.** These
      tests sit outside the preamble's count invariant by *exclusion*, not by
      exception: record `tests/unit/support/`'s own expected count, and leave
      the pre-existing tree's count untouched.
- [ ] 6.16 Every fake task in 6.8–6.14 records a **surface-and-behaviour note**
      (Decision 7b2) in three parts: what the shared fake **drops**, searched
      across `src/` **and** `tests/` because the callers are production probes
      (risk 2); what it **adds**, with the probe sites reading it and the branch
      each population takes before and after (risk 4); and for every method it
      **keeps**, return shape, absent-key behaviour and initial state, stated as
      "same as the dominant local variant" or named as a difference (risk 3).
- [ ] 6.17 Confirm every fake in `tests/support/` carries a `_conforms:
      SomeProtocol = TheFake()` assignment and that `uv run mypy .` passes — the
      assignment, not the protocol's existence, is what makes a drifted double a
      type error (Decision 6).

## 7. Record the rule

- [ ] 7.1 Add to `AGENTS.md`'s Testing Strategy section: a new test uses
      `tests/support/`; a new bespoke fake means a builder is missing, not that a
      thirteenth `_FakeSession` is warranted; a spec-restating constant is a
      literal in `tests/support/` and is never sourced from production; a fake
      carries a `_conforms` assignment against its protocol, and its added
      spellings carry the value they displace (the same-value invariant).
      **Record the directory departure in the same edit**: `tests/unit/support/`
      names no bounded context, so it fits none of the Testing Strategy's
      `tests/unit/<module>/<layer>/` rules; say that it holds the shared
      harness's own behaviour tests and why it must be collected.
- [ ] 7.2 Note in the same section that `tests/support/` exports public names and
      call sites alias them where they keep a local `_`-prefixed spelling.

## 8. Completion

- [ ] 8.1 Full verification across all three tiers. The integration tier needs
      this worktree's own `.env.test` — migrated **and** seeded
      (`uv run python -m commerce_ops.seed_playbook`), per `AGENTS.md`'s worktree
      obligations. A skipped integration test fails the run, so a green
      `pre-push` here is evidence and not a formality.
- [ ] 8.2 Compare against the 1.1 baseline: test count identical, line reduction
      measured, wall time reported (faster is a bonus, not a claim).
- [ ] 8.3 Record every file left unmigrated with its reason in the final commit
      message — the long tail is a non-goal, but a file skipped because its
      variant resisted the builder is a finding, not a silence. Expected entries:
      the 11 `_playbook` one-off signatures (6.5), any behaviourally distinct
      `_TreeParser` (3.1), any Population A symbol declared below its first
      test (2.7), and the 5 pinned `A_DISCIPLINE` outliers (4.3a).
- [ ] 8.4 Raise as findings, without acting on them: the stale-`playbook_v1.yaml`
      observation if anything new was learned while reading those tests;
      `docs/deferred-work.md:1068-1095`'s tolerance list, which this change
      established is stale in both directions
      (`proposal.md` — Why has the corrected enumeration); and **the duplicate
      test basenames that break bare `uv run pytest`** (task 1.1). The last is
      the strongest evidence against `design.md` Decision 1's rejected
      alternative of filling in the missing `__init__.py` files — it was
      rejected as unnecessary scope, and it turns out those absences already
      cost the project its documented test command. Still not this change's to
      fix: it is a module-naming defect, not arrangement duplication.
- [ ] 8.5 Run `/code-review` over the full diff before calling the change done
      (`AGENTS.md` — Independent review before completion).
