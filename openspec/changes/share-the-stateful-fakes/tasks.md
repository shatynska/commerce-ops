# Tasks

Per-name expectations below are set from the measured body, surface and
constructor structure, not from ambition. A name landing under its expectation
is a finding to record in task 12.3, never a target to force. `design.md`
Decision 3 is the boundary; no task relaxes it.

Every task's verification is the commit tier — `uv run pytest tests/unit
tests/agents` — plus `ruff check .`, `ruff format --check .`, `uv run mypy .`
and `lint-imports`. Per-tier, never bare `uv run pytest`, which fails at
collection because two basenames repeat across tiers.

**Two names run the integration tier, and not at the same commits.** Three of
the 191 declarations live in `tests/integration/`. `FakeMembers` runs it at
**both** its commits — the lockstep proof runs inside the instrumented instance
at the first, and the local is deleted and the name rebound at the second.
`FakeSlackResponse` runs it at the **settle commit only**, because it is
proof-exempt and its instrument commit touches neither integration file
(`design.md` Decision 9). Run it with `COMMERCE_OPS_REQUIRE_DATABASE=1`, so a
skipping tier fails instead of reporting green.

**"Instrument, verify, settle, verify"** means all four every time it appears:
instrument, run the verification above, settle, run it again — **including
`assert_identity.py` between the commit before the instrument commit and the
commit after the settle commit**, never against the instrument commit itself,
which adds nodes by construction (`design.md` Decision 10).

**Instrumenting means decorating every local in the working tree and then
dropping the decorator from the ones the pairing rejects or which diverge,
before the commit is made** (`design.md` Decision 11). A rejected or diverging
declaration is a *keep*, and each name's task predicts which ones they are — 16
in all — so the step confirms a structural expectation rather than discovering
it. A seventeenth is a finding to record at 12.3, never a decorator to delete
quietly.

**The collected-count check has two halves and both run on every commit**
(`design.md` Decision 7): the three tiers *outside* `tests/unit/support/` at
2,246 / 236 / 159, and `tests/unit/support/` at exactly the number the commit's
task declares — a number the task requires its implementer to state at the
commit that adds it, and which never falls.

Counts here are AST counts. Do not re-derive one by grep.

## 1. Baseline and instruments

- [x] 1.1 Record the baseline before anything is edited: collected counts for
      `tests/unit`, `tests/agents` and `tests/integration` separately, and pass
      counts and wall time for the commit tier and the integration tier.
      Measured on this worktree at `5e5b19a`: **2,246 / 236 / 159**; commit tier
      **2,482 passed**. **Record what is measured, not what is expected** — if
      the tree disagrees, the tree is right and the disagreement is a finding.
      **Measured: 2,246 / 236 / 159, commit tier 2,482 passed in ~74 s,
      integration tier 159 passed in 32.7 s. No disagreement.**
- [x] 1.2 Confirm this worktree's `.env.test` still resolves and its database is
      migrated and seeded (`commerce_ops_harness_test`, alembic head
      `c93f1a70e5d4`). A worktree does not inherit `.env.test`; without it the
      integration tier skips in its entirety while `pre-push` reports `Passed`.
      Migrated is not seeded — a schema-only database fails four tests, each of
      which says so in its own assertion message.
- [x] 1.3 Run the integration tier once with `COMMERCE_OPS_REQUIRE_DATABASE=1`.
      Expected `159 passed`. **Measured: 159 passed in 32.7 s.**
- [x] 1.4 Take the `assert_identity.py` baseline over `tests/**/*.py` at the
      change's base commit and record it. Expected **6,623 / 238 / 759 / 172**
      over 2,192 test functions; its `REPO` constant already points at this
      worktree, and it has no whole-tree mode — call `collect()` and sum by key
      prefix. **Measured: 6,623 / 238 / 759 / 172 over 2,192 test functions, as
      expected.** Add the `tests/unit/support/` **and `tests/support/`** exclusions
      to it now, before any contract test or shared fake exists, so neither is
      written under the pressure of a failing comparison (`design.md`
      Decision 10). Both cost nothing at the baseline: `tests/support/`
      contributes zero nodes to all four kinds today, so the figures above hold
      with the exclusions or without them.
- [x] 1.5 Re-run `~/share-the-stateful-fakes/census.py` and `behaviour.py`
      against the base commit and confirm the population table in `proposal.md`:
      1,046 module-level classes in `tests/`, 803 with behaviour across 190
      names, 482 in the 27 names declared eight times or more, and the nine
      in-scope names at 43 / 38 / 37 / 16 / 15 / 13 / 12 / 9 / 8 = **191
      declarations across 103 files**. A disagreement is a finding, not a
      transcription error to smooth over. **Measured: all figures confirmed.**

## 2. The proof, before the first fake

- [x] 2.1 Write `tests/support/_paired.py`: the
      `paired(shared, *, build=None, state=None)` decorator of `design.md`
      Decision 2. It **intercepts `__init__`** to capture the local's arguments,
      build the twin — from `build(*args, **kwargs)` where `build` is given and
      from `shared(*args, **kwargs)` otherwise — and compare state once before
      any call; `__init__` is excluded from the compared-call set, not from
      interception. It wraps **every other function the local's class body
      declares**, dunders included, sync and async alike, and wraps neither
      `classmethod`, `staticmethod` nor `property`. A divergence is raised
      through `pytest.fail`, whose `Failed` derives from `BaseException`, so no
      `except Exception` in the code under test can swallow it. The two
      non-fatal observations — a silent pairing, and a shared-only attribute —
      go out as `warnings.warn`, because pytest discards a passing test's
      output. It counts paired calls per class, so a declaration that migrated
      without the pairing ever firing can be named at 12.3. **A name the local declares and the shared fake lacks is checked at decoration
      time**, over every class-body binding to a callable — **aliases included**,
      so `members = list_members` reaches the check rather than slipping past a
      `FunctionDef`-only reading. It is left unwrapped and recorded as a silent
      pairing naming the class and method, and the decorator *fails at decoration* unless that name is one of
      clause (e)'s three, **matched as `(class, name)` pairs and not by bare name** —
      `_FakeMembers.members`, `_FakeMembers.__call__` and
      `_FakeHandlerRegistry.__iter__`, so that `_Catalog.__call__` is rejected
      rather than excused. A wrapped call returns the local's value and re-raises
      the local's exception, and reports a divergence by **raising**, so a
      divergence is a test failure. `state` is a `{local_attribute: shared_attribute}`
      name map applied to the local side only — never an arbitrary callable,
      which could normalise two different values into agreement. Each wrapped
      call compares return value, raised exception (type and `str()`, with one
      side raising and the other returning a failure), and the `state` mapping:
      an attribute on the local and not the shared is a failure, one differing
      in value is a failure, one only on the shared is a note. Its docstring
      says it is temporary and names task 12.1 as the commit that deletes it.
- [x] 2.2 Prove the decorator against the spike's three cases before it meets a
      real file: a local matching the shared, a local storing less than the
      shared, and a local mutated to skip a state change. The third **must**
      fail. A proof that cannot fail is not a proof, and this is the one task
      that establishes it can. **Done, and the run found two defects in the
      decorator that the design could not have: the twin was stored on the local
      before the first state comparison and so read as an attribute the shared
      fake modelled less of; and `hasattr(SomeClass, "__call__")` is always true
      — a class is callable — so an unlicensed `__call__` was excused instead of
      rejected. Both are fixed, and the second is why `_declares()` walks the
      shared fake's own MRO rather than asking `hasattr`. Two further cases were
      added beyond the three: an unlicensed dropped name is rejected at
      decoration, and a licensed one is excused with a note.** **These three cases live in the change's
      scratchpad and are never committed** — committing them under
      `tests/unit/support/` would raise the declared count and lower it again at
      task 12.1, against "only ever rises" (`design.md` Decision 7).
- [x] 2.3 Re-take the clause (d) measurement against the base commit: an AST
      pass over the 191 declarations for a write whose target is not `self`, or
      a call to `append`, `add`, `extend`, `update`, `write`, `pop` or `insert`
      on a bare name — the same verb list `design.md` Decision 3(d) states. At
      `5e5b19a` it has **six hits, all of them `_FakeMembersStore` declarations
      already kept for a constructor reason**, so the clause excludes nothing this
      change migrates. Record the result; a seventh hit is a declaration that
      migrates on the note alone and must be named here rather than left to look
      like a proof that passed. The predicate over-reports local-variable
      assignment inside a method body, so the hits are read, not counted.
      **Measured: six hits, all `_FakeMembersStore` `_Version`-cell
      declarations, all already kept under clause (c). The clause excludes
      nothing this change migrates.**
- [x] 2.4 Check that the nine contract-test module basenames are unique across
      **all three tiers** — `tests/unit`, `tests/agents` and
      `tests/integration` — before any is committed. At `5e5b19a` all nine are
      free. **Checked across all three tiers: all nine free, and
      `test_paired.py` with them.** Duplicate basenames break collection outright under
      pytest's prepend import mode, which `docs/deferred-work.md` records as a
      live defect that no gate notices.

## 3. `FakeSlackResponse` — 13 declarations, one body, **proof-exempt**

- [x] 3.1 Add `FakeSlackResponse(dict[str, Any])` to `tests/support/fakes.py`
      with its `data` property, its protocol and `_conforms` assignment, and
      `tests/unit/support/test_fake_slack_response.py`. **Declare the number of
      tests added: **five**.** These contract tests are the *primary* check for this name,
      not a supplement: there is no instance method to intercept and the
      substance is the `dict` base class, so they must cover indexing, the
      `data` property's copy semantics and the empty payload. **Recorded while
      writing them: `data` is read by nothing — no site in `src/`, none in the
      Slack SDK or bolt, and no test. It is a fourth candidate for clause (e)'s
      treatment and is deliberately **not** dropped, because that clause names
      three cases rather than a category precisely so it cannot be widened at
      implementation time. `tests/support/fakes.py` records it for whoever owns
      the next slice.**
- [x] 3.2 Instrument, verify, settle, verify. **Record in this file that the
      lockstep proof does not run for this name** (`design.md` Decision 2) — the
      instrument commit's green is `mypy`, clause (b) and the contract tests,
      and nothing else. Two of the 13 are in `tests/integration/`
      (`test_slack_entry_confirmation_last_resort.py:214`,
      `test_slack_entry_start.py:264`), so the **settle** commit runs the
      integration tier with `COMMERCE_OPS_REQUIRE_DATABASE=1`. The instrument
      commit does not: with no decorator to add, it touches neither file
      (`design.md` Decision 9).
      **Expected: 13 of 13, all aliases. Actual: 13 of 13, all aliases.**
      Commit tier 2,487 passed (2,482 outside `tests/unit/support/`, 5 inside);
      integration tier 159 passed with `COMMERCE_OPS_REQUIRE_DATABASE=1`.

## 4. `FakeHandlers` — 8 declarations, one body

- [x] 4.1 Add `FakeHandlers` (`__contains__`, `get`, `names`, `resolve`, over
      `**handlers`), its protocol and `_conforms`, and its contract tests.
      Declare the number of tests added. The contract tests state the absent-key
      behaviour explicitly: `get` returns the default, `resolve` raises
      `KeyError`.
- [x] 4.2 Instrument, verify, settle, verify. **Expected: 8 of 8, all aliases.**
      The wrapped set includes `__contains__`, which is a dunder and is the
      surface production calls at `automation_pass:770`. **Actual: 8 of 8, all
      aliases. The pairing fired 211 times across the eight declarations --
      42/26/14/26/9/64/18/12 — with no divergence, so the green is evidence
      per declaration rather than a suite that happened not to exercise them.**
- [x] 4.3 Record the same-value check for `_registered_names`: every one of the
      8 already provides `names()`, so the probe's first branch already fires
      and the shared fake displaces nothing (`design.md` Decision 6).
      **Confirmed: all 8 declare `names()`, so both `_registered_names` sites
      take their first branch before and after. `__contains__` is kept because
      `automation_pass:770` calls `name in handlers` directly -- a call, not a
      convention -- and `get` is carried because all 8 declared it.**

## 5. `StubDate` — 15 declarations, one body, **proof-exempt**

- [x] 5.1 Add `StubDate(date)` with `_today` as a `ClassVar` and the `today`
      classmethod, **its protocol and `_conforms` assignment**, plus contract
      tests; declare the number added. The assignment takes the class-object
      form — `_conforms: type[DateShape] = StubDate` — because `date` requires
      three constructor arguments and the surface production reads is a
      classmethod (`design.md` Decision 8). Without it `mypy` compares nothing,
      and this name is one of the two whose migration is priced at exactly three
      checks. **Three tests added; `tests/unit/support/` now collects 14.
      `_today` carries no default: all 15 locals set it from a per-module
      `RENDER_DATE`, and the parent slice's rule is that a per-module constant
      does not become a shared one.** The shared
      declaration carries the `# type: ignore[override]` that all 15 locals
      carry, so no call site needs one. As with `FakeSlackResponse`, these tests
      are the primary check: they cover `today()` returning the class attribute,
      and a subclass overriding it.
- [x] 5.2 Instrument, verify, settle, verify. **Record that the lockstep proof
      does not run for this name** — no instance is constructed and `today` is a
      classmethod, so there is nothing to intercept (`design.md` Decision 2).
      **Expected: 15 of 15, all adapters** — each file keeps a two-line subclass
      setting its own `_today`, replacing five lines. One file additionally
      builds a subclass dynamically
      (`type("_FixedDate", (_StubDate,), {"_today": day})`); confirm it still
      resolves through the adapter. **Actual: 15 of 15, all adapters. All 15
      locals were byte-identical and all set `_today` from a per-module
      `RENDER_DATE`, so each adapter is two lines against six. The dynamic
      subclass still resolves, and is covered by a contract test.**

## 6. `InertBackoff` — 9 declarations, two bodies

- [x] 6.1 Add `InertBackoff` with all four no-op methods (`mark_reported`,
      `note`, `read`, `rollback`), its protocol and `_conforms`, and contract
      tests asserting each returns `None`; declare the number added. **Four
      tests added; `tests/unit/support/` now collects 18.**
- [x] 6.2 Instrument, verify, settle, verify. **Expected: 9 of 9, all aliases.
      Actual: 9 of 9, all aliases.** The pairing fired 95 times across the nine
      before the decorator came off, the two minimal declarations included
      (9 and 6 calls on `mark_reported`), with no divergence.
- [x] 6.3 Record the same-value check for the two declarations that carry
      `mark_reported` alone: the shared fake adds three methods, each returning
      `None`. Confirm by search across `tests/` and `src/` that no site probes
      for their absence — a `getattr` fall-through or a `hasattr` guard — before
      accepting the addition (`design.md` Decision 6). **Searched: production
      calls all four by name -- `automation_pass:404` (`read`), `:531` (`note`),
      `:673` (`mark_reported`), `:713` (`rollback`) -- and no site in `src/` or
      `tests/` probes any of them with `getattr` or guards on `hasattr`. So
      nothing falls through and no branch moves; what changes for the two
      minimal declarations is only that a path which would have raised
      `AttributeError` returns `None`, and no test reaches such a path or it
      would be failing today.**

## 7. `FakeHandlerRegistry` — 12 declarations, five bodies

- [x] 7.1 Before writing the fake, re-take the clause (e) measurement for
      `__iter__`, **by execution and not only by search**, because `__iter__` is
      the interpreter's fallback for `in` and `automation_pass:770` evaluates
      `name in handlers` directly. Three parts: that all 12 declarations declare
      `__contains__`, so no membership test resolves through iteration (12 of 12
      at `5e5b19a`, as do all 8 `_FakeHandlers`); that no test iterates an
      instance; and — the execution half — that making each local `__iter__`
      raise leaves the commit tier green. If any part fails, `__iter__` stays
      and `proposal.md`'s single-reader-shape claim is narrowed to
      `FakeMembers`. **All three parts hold. 12 of 12 declare `__contains__`,
      as do all 8 `_FakeHandlers`, and none of the 8 declares `__iter__`. No
      test iterates an instance. And the execution half: mutating every one of
      the twelve `__iter__` bodies to `raise AssertionError` leaves the commit
      tier at 2,500 passed — the branch is unreachable, not merely unread.**
- [x] 7.2 Add `FakeHandlerRegistry(names: frozenset[str] = frozenset())` with
      `__contains__` and `names()` and **not** `__iter__`, its protocol — which
      declares what production reads, not what the real registry offers
      (`design.md` Decision 8) — `_conforms`, and contract tests; declare the
      number added. **Four tests added; `tests/unit/support/` now collects 22.
      The protocol split in two: `HandlerNamesShape` (`names`, `__contains__`)
      covers both this fake and `FakeHandlers`, and `HandlerRegistryShape`
      extends it with `resolve` for the latter. `names()` returns a `frozenset`
      here and a tuple there, as their populations did, so the shared protocol
      declares `Iterable[str]` — which is all `_registered_names` needs.**
- [x] 7.3 Instrument, verify, settle, verify. **Expected: 12 of 12 — 8 aliases
      and 4 adapters.** Three declarations carry no `__init__` and hard-code a
      single registered name; one defaults `names` to a file constant. All four
      are clause (c) mismatches, and each `@paired` line carries the `build=`
      factory that becomes its adapter at the settle commit. **Actual: 12 of 12
      — 8 aliases and 4 adapters, exactly as measured. The pairing fired 98
      times with no divergence, and emitted the 12 silent-pairing notes for
      `__iter__` that clause (e) predicts.**

## 8. `FakeStepStore` — 37 declarations, eleven bodies

- [x] 8.1 Add `FakeStepStore(records=(), version=41)` — records `saves`, and
      **asserts `expected_version == self.version` inside `save`**
      (`design.md` Risks). Its protocol, `_conforms`, and contract tests that
      state the initial state, the `load` return shape, the version bump, the
      `saves` record and the stale-write assertion; declare the number added.
      **Six tests added; `tests/unit/support/` now collects 28.**
- [x] 8.2 Instrument, verify, settle, verify. **Expected: 36 of 37 — 34 aliases
      and 2 adapters, 1 kept.** Eight bodies differ only in whether they record
      `saves` or assert on the version, which is a licensed superset and a
      deliberate strengthening respectively; record the `AGENTS.md` completeness
      search for `saves` (`design.md` Decision 6). The two adapters are the body
      constructing records from `StepDefinition`s and the body carrying
      `supersede()`. The one kept carries a `loads` counter, which needs a
      method override rather than a constructor.
      **Actual: 36 of 37 — 34 aliases and 2 adapters, 1 kept, as expected, but
      four things the plan did not anticipate:**

      1. **The shared store is generic in its row type**, and each file's settle
         line binds the parameter its own local bound
         (`_FakeStepStore = FakeStepStore[_Record]`). All 34 annotate with the
         name, and seven read a row back through a helper declaring a concrete
         return type; a store fixed at `tuple[Any, ...]` makes those nine
         helpers return `Any` from a function declared otherwise, which
         `mypy --strict` refuses. Binding per file keeps every annotation site
         the type it had, and costs no test-body edit.
      2. **One adapter could not be paired at all.**
         `test_playbook_admin_filtered_moves.py` adds `supersede()`, a name the
         shared fake has not, so the decorator rejects it at decoration —
         correctly, since it cannot tell an adapter's addition from a keep. An
         adapter that *adds a method* is outside the proof; it migrated on
         clauses (a)–(c) and is recorded here.
      3. **One pairing was a false positive, and it is the composition
         partition's first data point.**
         `test_launch_report_step_facts.py` declares its **own** `_Record` — one
         of the twenty the parent slice left behind — so the `build=` factory
         constructs records whose `==` is identity and every comparison differs.
         Exactly the false positive `design.md` Decision 2 predicts. It migrated
         as an adapter with the proof exempt. **The one file whose leaf did not
         migrate is the one file whose store could not be paired**, which is
         evidence for the rule that ordered these two changes.
      4. **`assert_identity` reports five files changed, and all five are the
         same node**: the fake's own stale-write `assert`, textually identical,
         one per file, nothing gained, no test count moving. Those five locals
         carried the assertion in their `save`; it now lives in
         `tests/support/fakes.py`, which Decision 10 excludes — so the check
         sees the departure and not the arrival. Nothing a *test* asserts
         changed: a double's internal assertion is part of the double, and
         Decision 1's rule holds, since every one of these declarations sits
         above its file's first test. Recorded rather than suppressed, because
         the check is a belt on top of that rule and a silent exclusion is how a
         belt stops holding. It also understates the outcome — the assertion
         went from 19 files to all 34.

      Pairing totals: 34 declarations, 298 constructions, 983 calls, no
      divergence. **Two were built but never called** —
      `test_launch_admin_detail` and `test_launch_journal_page`, four
      constructions each — so those two are proved at their initial state and
      nowhere else.
- [x] 8.3 Where the strict assertion makes a previously-passing test fail, the
      proof reports it at the instrument commit. Record the file, keep its own
      declaration, and state the reason — do not weaken the shared fake to
      accommodate it. **None did. The strengthening is inert across all 34
      paired declarations: no test in the suite saves against a stale version,
      so eighteen files gained an assertion that never fires today and will
      fire the first time one does.**

## 9. `FakeMembersStore` — 38 declarations, fifteen bodies

- [x] 9.1 Add `FakeMembersStore(rows=(), version=13)`, recording `saves` and
      asserting on the stale write, with its protocol, `_conforms` and contract
      tests; declare the number added. Record the completeness search for
      `saves`, as at 8.2. **Six tests added; `tests/unit/support/` now collects
      35. Not generic, unlike the step store: all 38 locals annotated `rows` as
      `tuple[Any, ...]`, so there is no row type to bind. The `saves`
      completeness note fired 42 times across the tier and was the only note
      emitted -- no silent pairings, no other superset.**
- [x] 9.2 Instrument, verify, settle, verify. **Expected: 29 of 38 — 22 aliases
      and 7 adapters, 9 kept.** The nine are the six declarations threading an
      external `_Version` cell and exposing `version` as a property, the two
      whose `save` raises rather than storing, and the one carrying a `loads`
      counter. The seven adapters are default versions of 11, 7, 5, 3 and 0
      against the shared 13, one constructor without a `rows` parameter, and one
      hard-coded row set.
      **Actual: 29 of 38 — 21 aliases and 8 adapters, 9 kept.** The total is the
      one expected; one file moved from the alias column to the adapter column
      (`test_members_surface_vocabulary_rebuild`, whose constructor takes a
      version and no rows), and the hard-coded row set turned out to be one of
      the two whose `save` raises, so it is a keep rather than an adapter.

      **One migration is proof-exempt, for a limit `design.md` Decision 2 does
      not list.** `test_members_bootstrap.py:249` writes the double's state
      directly — `store.rows = remaining; store.version += 1` — rather than
      through `save()`. The pairing intercepts *calls*, not attribute writes, so
      the twin never saw it and the next `load()` diverged by two rows and a
      version. The behaviour migrates intact, since the same direct write works
      on the shared fake; it is the *proof* that cannot see it. Measured across
      every name in scope there are exactly **four** such writes in three files,
      and the other two files are keeps already, so this does not recur.

      **`assert_identity` reports six files changed, and all six are the same
      node again** — the fake's own stale-write `assert`, three in the bare
      spelling and three with the message, one per file, nothing gained and no
      test count moving. The same accounting as task 8.2's fourth point: the
      assertion moved into `tests/support/fakes.py`, which Decision 10 excludes,
      and it went from 8 files to all 29.

      Pairing totals: 28 declarations, 231 constructions, 996 calls, no
      divergence, and every one exercised — no declaration was built without
      being called. The only note emitted across the whole tier was
      `the shared fake adds ['saves']`, 42 times: the licensed superset
      Decision 6 enumerates, and nothing else.
- [x] 9.3 Record which of the nine kept declarations sit in files whose leaf
      value double migrated in `share-the-value-doubles`, for the partition
      `design.md` Decision 4 asks for. **None of the nine turns on its leaf: six
      thread an external `_Version` cell, two refuse writes outright and one
      counts loads — all constructor or behaviour reasons, none of them a row
      type. So this name contributes no evidence either way to the composition
      rule, and `FakeStepStore`'s single false positive remains the only data
      point.**

## 10. `FakeCatalogPort` — 16 declarations of `_Catalog`, seven bodies

- [x] 10.1 Add `FakeCatalogPort(*products, fails: bool = False)` with
      `get_product_by_id` and `list_products`, its protocol, `_conforms` and
      contract tests; declare the number added. `fails` is in the shared fake
      because two measured declarations need it, not because it might be wanted;
      record the completeness search establishing that no production reader
      probes it. **Six tests added; `tests/unit/support/` now collects 41.
      Searched: nothing in `src/` names `fails` or reads it by `getattr`, and
      `launch_admin` calls `list_products` and `get_product_by_id` by name. The
      eight declarations that never pass `fails` cannot tell it is there.**
- [x] 10.2 Instrument, verify, settle, verify. **Expected: 12 of 16 — 12
      aliases, 4 kept.** The kept are the two declarations that sniff their
      arguments for a `ProductId` rather than taking one positionally, the one
      counting list calls, and the one declaring `__call__` instead of the port
      surface. **Actual: 12 of 16 — 12 aliases, 4 kept, exactly as measured.
      The pairing fired 146 times over 112 constructions with no divergence,
      and every declaration was exercised.**
- [x] 10.3 Record explicitly that `_FakeCatalog` (29 declarations) is **not**
      migrated onto this fake, and why: it is two doubles under one name, and
      four of its five port-shaped declarations apply access-scope filtering
      that no `_Catalog` declaration performs (`proposal.md`). Migrating them
      would drop a scope check inside a double, invisibly. No file declares both
      names, so the exclusion leaves no file holding one migrated and one
      unmigrated catalog double — **confirmed, still zero.**

## 11. `FakeMembers` — 43 declarations, twenty-one bodies

- [x] 11.1 Before writing the fake, re-take the clause (e) measurements
      Decision 5 rests on, structurally: that no site in `src/` or `tests/`
      reads `members`, and that no test invokes a `_FakeMembers` instance
      directly. Record alongside them the two completeness searches Decision 6
      lists for this name and does not task elsewhere: that no probe chooses between `member(id)` and another spelling, and that
      `_members` is private and therefore outside every probe. **All four
      re-taken and all four hold: nothing in `src/` reads a reader's `members`;
      no test invokes an instance or calls `.members()`; nothing in `src/` calls
      `.member(` at all, and the one `getattr(value, "member")` — `roles.py:724`
      — reads a *record's* nested member, not a reader's query method, and would
      fall through harmlessly if it ever met one; nothing in `src/` names
      `_members`.** Both were zero at `5e5b19a`. If either is non-zero now, the drop
      does not apply to that file and it keeps its own declaration — clause (e)
      licenses a drop only on the measurement, and only for the three spellings
      it names.
- [x] 11.2 Add `FakeMembers(members: tuple[Any, ...] = ())` carrying
      `list_members()` and `member(member_id)` and **not** `members` or
      `__call__`, storing the roster as **`self._members`** — the dominant local
      spelling, and private, so the dropped `members` spelling does not return
      as instance data. The 8 declarations storing `members_rows` carry
      `state={"members_rows": "_members"}` on their `@paired` line; the 20 that
      store nothing see `_members` as a shared-only note. Add its protocol declaring
      the reader shape, `_conforms`, and contract tests covering the empty
      roster, the ordering `list_members` returns, and `member()` on a present
      and an absent identifier; declare the number added. **Five tests added;
      `tests/unit/support/` now collects 46.**
- [x] 11.3 Instrument, verify, settle, verify. **Both** commits run the
      integration tier with `COMMERCE_OPS_REQUIRE_DATABASE=1`
      (`test_seeded_step_fields.py:579`). **Expected: 41 of 43 — 8 aliases and
      33 adapters, 2 kept.** By constructor signature the 43 split 20 with no
      `__init__` at all, 7 taking none, 10 taking a tuple, 5 taking `*members`
      varargs and 1 taking an optional; **eight of the ten
      tuple-takers alias — the other two are the kept call-counter declarations,
      which are both tuple-takers** — and the remaining 33 adapt, each carrying
      its `build=` factory at the instrument commit. **The two kept are the declarations carrying a call
      counter** — `test_step_activation.py` (`calls`) and
      `test_step_assignee_preconditions.py` (`reads`) — each of which puts an
      attribute on the local that the shared fake has not, which is Decision 2's
      first failure row. They carry no `@paired` line in the committed tree.

      **Actual: 41 of 43 — 8 aliases and 33 adapters, 2 kept, exactly as
      expected. But only 17 of the 41 could be paired**, and the 24 that could
      not are the design's own fourth blind spot rather than a defect:

      - **20 build a fresh roster inside `list_members` on every call.** There
        is no stored state to seed a twin from, and `values.Member` is a plain
        class whose `==` is identity by design — so no twin, however built, can
        compare equal, and the local is not even self-consistent across two
        calls. Inexpressible, not merely unproven.
      - **4 store the roster as a `list` where the shared fake stores a
        `tuple`.** A private representation that every read normalises away, and
        the state comparison correctly reports it. The comparator was **not**
        weakened to accept it; those four migrate on clauses (a)–(c).

      **The decorator grew a second, weaker mode for the nine it could still
      reach** — `build_from`, which seeds the twin from the *constructed local*
      rather than building it independently. It is a deviation from the
      reviewed `design.md` Decision 2, taken deliberately and recorded here
      rather than smuggled: without it those nine join the exempt population,
      and with it the pairing still establishes what risk 3 is about — that
      `list_members()` returns the same tuple in the same order and `member()`
      resolves the same way. What it gives up is stated at the decorator and at
      every call site: for those nine the shared fake's *constructor* is proved
      by the adapter reproducing the roster literally, and by nothing else.

      Pairing totals: 17 declarations, 195 constructions, 379 calls, no
      divergence; one built but never called (`test_product_dossier_page`). The
      30 notes emitted were all silent pairings for the two dropped spellings,
      which is clause (e) working as written.

      The **settle** commit ran the integration tier (159 passed); the
      instrument commit did not, because the one integration declaration
      (`test_seeded_step_fields.py:579`) is among the 20 exempt and so carries
      no decorator — the same correction Decision 9 already records for
      `FakeSlackResponse`.
- [ ] 11.4 Record the resulting reader-shape population: how many members
      readers in `tests/` now present `list_members` alone, and what remains —
      `_StoreShapedMembers`, `_ReaderMembers`, `_Members`, and the module-level
      `_members()` at 17 call sites. This is what
      `unify-launch-adapter-dependencies` inherits, and it is a measurement, not
      a claim that the branches are dead.

## 12. Close out

- [ ] 12.1 Delete `tests/support/_paired.py` in the last settle commit. A proof
      that outlives its migration is a permanent dependency on a temporary
      arrangement. The declared `tests/unit/support/` count does not move: the
      decorator's own cases were never committed (task 2.2).
- [ ] 12.2 Run the full verification once more, both tiers, plus
      `assert_identity.py` across the whole change: base commit against head,
      **excluding `tests/unit/support/` and `tests/support/` from all four
      multisets and from the test-function count** — the latter because
      `fakes.py` carries the stale-write assertions of tasks 8.1 and 9.1 and
      persists at head. This is the run that catches drift accumulated
      across pairs on the 52 files that more than one name touches.
- [ ] 12.3 Record the outcome per name — expected against actual, with the
      reason for every shortfall — and the three findings this change was asked
      to produce: the composition partition of Decision 4, the reader-shape
      population of task 11.4, and the list of declarations that migrated with
      the proof exempt or silent (tasks 2.3, 3.2, 5.2) — together with every
      `state` name map used, so a state comparison that passed under a rename is
      visible rather than inferred; every warning the decorator emitted — silent
      pairings and shared-only attributes, the latter being how an addition
      outside Decision 6's table surfaces; and **any declaration that migrated
      with a paired-call count of zero**, which is proved by nothing and must not
      read as proved.
- [ ] 12.4 Update `AGENTS.md`'s "shared harness" section **and both
      `tests/support/` docstrings** (`__init__.py` and `protocols.py`), and
      record the class-object `_conforms` form beside the existing `@property`
      rule, so the next slice does not re-derive the `date`-constructor trap
      (`design.md` Decision 8): the
      stateful fakes are no longer deferred; their population is 803
      declarations across 190 names, not the "~355" `__init__.py` currently
      records; the equality proof's inexpressibility is superseded by the
      lockstep proof, with what it does, does not and cannot reach stated; and
      `tests/unit/support/` exists, with the count invariant's exact form.
- [ ] 12.5 Add the **three** newly measured reader-shape probes to
      `docs/deferred-work.md`'s tolerance record — `activation_readiness`'s two
      and `playbook_authoring._registered_names` — with the measurement *method*
      beside them: a reader shape is invisible to a spelling-shaped sweep, which
      is why they were missed. `clickup_sync._members` is already recorded and
      `gate_progression_job._crossed` stays where it is, as the separate live
      tolerance of a different kind that it is.
- [ ] 12.6 Update `docs/proposed-change-order.md`: correct §4's caution to say
      what this change actually hands `unify-launch-adapter-dependencies`, and
      record the 291 declarations that remain, with the composition rule that
      blocks the largest group of them. The §3 entry is deleted on archive, not
      here.
- [ ] 12.7 Open the pull request. Per `AGENTS.md`, the archive is a separate
      commit on its own branch in a last pull request of its own, after this one
      merges.
