# Test manifest — `share-the-aggregate-fakes`

Written by the test-writing pass, before any of the change's implementation
tasks were performed. **Not an artifact the OpenSpec schema knows about**: it
does not appear among `openspec instructions apply`'s context files and has to
be read on purpose.

**This pass is additive only.** It added four files under `tests/unit/support/`
and this manifest. No existing test was edited, deleted or disabled, and no
implementation was written — `tests/support/fakes.py` is untouched, and nothing
under `src/` was read, written or imported.

Baseline commit: **`4b72aa5`** (`docs(openspec): propose share-the-aggregate-fakes`),
which is also `HEAD` on this branch.

## Why almost nothing was derived

`<changeRoot>/.openspec.yaml` sets `skip_specs: true` and the change carries
**no delta specs**. There are therefore **zero `#### Scenario:` blocks** to
enumerate, and zero to account for. That is the exemption `AGENTS.md` —
*Test design before implementation* — states in advance:

> A change that declares it carries no specification deltas has none to derive
> from and owes no new tests; what it owes is that the existing suite stays
> green.

`proposal.md` — *Modified Capabilities* restates it and adds the change's own
invariant: **the collected count outside `tests/unit/support/` does not move.**
So deriving a broad suite here would not be thoroughness — it would break the
invariant the change is verified by. Nothing was derived beyond the targets
`tasks.md` §3.3, §4.3 and §5.5 plan, all of which must live under
`tests/unit/support/`.

Note also that this change is exempt from delta specs but **not** from
specification: `design.md` Decision 5 turns on two *existing* capabilities
(`launch-step-automation` and `launch-clickup-sync`, both carrying *A graduated
launch is left alone*). Those were read under `specsRoot` and are cited in
`test_fake_launches.py`; nothing about them is modified by this change, so they
produced no delta to account for.

## What was written

Four files, **41 test functions**, all under `tests/unit/support/` — the
deliberate exception to the tier layout, whose subject is the harness itself.

Run all four with:

```
uv run pytest tests/unit/support/test_fake_product_reader.py \
              tests/unit/support/test_fake_playbooks.py \
              tests/unit/support/test_fake_playbook_repository.py \
              tests/unit/support/test_fake_launches.py
```

### `tests/unit/support/test_fake_product_reader.py` — 6 tests (serves §3.3)

| # | Test (runner-selectable) | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_fake_product_reader.py::test_answers_the_product_it_was_handed` | 3.1 — the reader's whole surface | fails, absent target |
| 2 | `…::test_answers_an_object_of_whatever_type_it_was_handed` | 3.1 + Decision 7 — deliberately unconstrained | fails, absent target |
| 3 | `…::test_a_fresh_reader_has_recorded_nothing` | 3.1 — both recorder spellings start empty | fails, absent target |
| 4 | `…::test_records_each_product_it_was_asked_for_in_order` | 3.1 — `reads` is a list, in call order | fails, absent target |
| 5 | `…::test_calls_is_the_same_list_object_as_reads` | 3.1 + Decision 7 — one list, two names | fails, absent target |
| 6 | `…::test_reads_is_the_stored_spelling_and_calls_cannot_be_assigned` | 3.1, 3.4 — `AGENTS.md`'s `Member.id` precedent | fails, absent target |

### `tests/unit/support/test_fake_playbooks.py` — 15 tests (serves §4.3)

| # | Test | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_fake_playbooks.py::test_the_sync_store_answers_the_playbook_it_holds` | 4.1 | fails, absent target |
| 2 | `…::test_the_async_store_answers_the_playbook_it_holds` | 4.1 | fails, absent target |
| 3 | `…::test_the_sync_store_takes_the_version_its_call_sites_pass` | 4.1 — `get(version: str = "")` | fails, absent target |
| 4 | `…::test_the_async_store_takes_the_version_its_call_sites_pass` | 4.1 | fails, absent target |
| 5 | `…::test_a_store_with_no_refusal_counts_reads_and_raises_nothing` | 4.1 — `refusal` defaults inert | fails, absent target |
| 6 | `…::test_the_sync_store_raises_the_refusal_it_was_given` | 4.1 | fails, absent target |
| 7 | `…::test_the_async_store_raises_the_refusal_it_was_given` | 4.1 | fails, absent target |
| 8 | `…::test_a_refused_read_is_counted_before_it_is_refused` | 4.1 — `_answer()`'s increment-then-raise order | fails, absent target |
| 9 | `…::test_a_refused_async_read_is_counted_before_it_is_refused` | 4.1 — same, on the async sibling | fails, absent target |
| 10 | `…::test_reads_counts_every_read_rather_than_recording_them` | 4.1, Decision 2 — `reads` is an `int` | fails, absent target |
| 11 | `…::test_the_store_carries_no_calls_spelling` | 4.1, Decision 2 — the deliberate divergence from the reader | fails, absent target |
| 12 | `…::test_the_async_store_is_callable_and_reaches_get` | 4.1 — `__call__` delegates to `get` | fails, absent target |
| 13 | `…::test_calling_the_async_store_accepts_whatever_arguments_arrive` | 4.1 — `(*args, **kwargs)`, never an `attr = get` alias | fails, absent target |
| 14 | `…::test_the_sync_store_is_not_callable` | 4.1, Decision 2 — `__call__`'s placement sizes the superset | fails, absent target |
| 15 | `…::test_the_two_stores_are_siblings_rather_than_parent_and_child` | 4.1, Decision 2 — the structural fact `mypy` (not pytest) enforces | fails, absent target |

### `tests/unit/support/test_fake_playbook_repository.py` — 7 tests (serves §4.3)

| # | Test | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_fake_playbook_repository.py::test_serving_a_playbook_answers_it_from_the_built_repository` | 4.2 — the 4 inline-body declarations | fails, absent target |
| 2 | `…::test_the_constructor_discards_what_production_passes_it` | 4.2 — production constructs it with `(db)` | fails, absent target |
| 3 | `…::test_serving_a_zero_argument_callable_invokes_it_per_call` | 4.2 — the 5 `return _playbook()` declarations | fails, absent target |
| 4 | `…::test_the_source_is_read_at_call_time_not_at_subclass_creation` | **4.3's explicitly required test**; Decision 3's correctness condition | fails, absent target |
| 5 | `…::test_each_serving_call_produces_a_subclass_of_its_own` | Decision 3's rejected mutable-class-attribute alternative | fails, absent target |
| 6 | `…::test_serving_returns_a_class_rather_than_an_instance` | 4.2, 4.2a — the class-object `_conforms` form | fails, absent target |
| 7 | `…::test_get_takes_the_version_production_passes_positionally` | 4.2 — all ten locals declare `get(self, version: str)` | fails, absent target |

### `tests/unit/support/test_fake_launches.py` — 13 tests (serves §5.5)

| # | Test | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_fake_launches.py::test_lists_every_launch_it_was_handed_as_active` | 5.3 — the variadic constructor | fails, absent target |
| 2 | `…::test_list_all_answers_the_same_launches_as_list_active` | 5.3, Decision 4 — the method superset is safe only while the two agree | fails, absent target |
| 3 | `…::test_list_active_does_not_filter_a_graduated_launch` | **5.4, 5.5's explicitly required pin**; Decision 5 | fails, absent target |
| 4 | `…::test_resolves_a_launch_by_its_product_id` | 5.3 | fails, absent target |
| 5 | `…::test_answers_none_for_a_product_it_holds_no_launch_for` | 5.3 | fails, absent target |
| 6 | `…::test_a_saved_launch_is_the_one_read_back_for_its_product` | 5.3 — `save` | fails, absent target |
| 7 | `…::test_a_saved_launch_for_an_unheld_product_becomes_readable` | 5.3 — `save` (derived; see below) | fails, absent target |
| 8 | `…::test_the_two_measured_dead_spellings_are_absent` | 5.3, 5.2 — `list_launches` and `all` must not come back | fails, absent target |
| 9 | `…::test_serving_discards_what_production_passes_the_patched_class` | 5.3, Decision 4 — **not** Decision 3's `serving` | fails, absent target |
| 10 | `…::test_serving_takes_a_launch_an_iterable_or_a_callable` | 5.3 — the three source forms | fails, absent target |
| 11 | `…::test_serving_reads_its_source_at_call_time` | 5.3; the behaviour 5.5b will justify | fails, absent target |
| 12 | `…::test_each_serving_call_produces_a_subclass_of_its_own` | 5.3, Decision 4 — no shared class attribute | fails, absent target |
| 13 | `…::test_the_reads_answer_a_tuple` | derived; see *Unresolved project questions* #3 | fails, absent target |

## The ordering reality, and how it was handled

**All 41 fail, and all 41 fail in the same state: the target does not exist.**
`ai-toolkit:testing`'s second failure state — the assertions never executed, so
whether they are any good is still unverified. Not one is in the first state
(code ran, wrong value), and none is in the fourth (first-run pass), which
matters here: unlike `share-the-playbook-builders`, whose parameter had a
default equal to today's behaviour, **nothing this change adds exists in any
form today**, so there is no control test that could legitimately pass now.

The failure is at **collection**, not at assertion:

```
ImportError: cannot import name 'FakeProductReader' from 'tests.support.fakes'
```

and pytest aborts the whole run — `Interrupted: 4 errors during collection`.

**Consequence for whoever implements next, stated plainly:** these four files
**cannot be committed before the types they name exist**. `tasks.md`'s preamble
records that the `pre-commit` hook runs the whole commit tier, and a collection
error takes the entire tier with it rather than failing four files. So each file
lands in the same commit as its shared type and that type's first call sites —
which is exactly the sequencing `design.md` — *Migration Plan* already
prescribes, now with a second reason.

Nothing was stubbed to make the tests execute. Creating the module, class or an
empty placeholder so collection would succeed is writing implementation, and it
is the point at which this pass would have become one.

**What was validated instead, since the assertions could not be.** Every
expression harvested out of the tree — `playbook(hold(...))`,
`playbook(fill_unheld=False)`, `CatalogProduct(name=…, sku=…)`, the
`_BespokeProduct` frozen dataclass, `Launch.start(...)` and the `_graduated()`
gate walk — was **evaluated standalone**, per `AGENTS.md`'s rule that a
harvested expression is validated by evaluating it rather than by reading it.
All evaluate; the graduation walk reaches `current_gate == "graduated"`, and two
launches built from one `product_id()` are distinct objects with equal
identifiers, which tests 6 and 7 of `test_fake_launches.py` depend on. This is
the only part of the four files whose behaviour is presently established.

## Assertion classification

The change carries no specification deltas, so **no assertion here is
`specified` in the delta sense.** Each instead traces to a planning artifact,
recorded per assertion rather than left implicit. One group is the exception and
is marked: the graduated-launch pin traces to two *existing* capability specs.

| Assertion | Class | Traces to |
|---|---|---|
| The reader answers the object it was handed, of whatever type | traceable | `tasks.md` 3.1; `design.md` Decision 7 |
| `reads` is a list, recorded in call order | traceable | `tasks.md` 3.1 |
| `calls` **is** `reads` — the same list object | traceable | `tasks.md` 3.1 ("over the same list object") |
| `reads` is assignable and `calls` is not | traceable | `tasks.md` 3.1 + 3.4; `AGENTS.md`'s `Member.id` precedent |
| Both stores answer the held playbook, sync and async | traceable | `tasks.md` 4.1 |
| `get` takes `version` absent, positional and by keyword | derived | The locals declare `get(self, version: str = "")`; no artifact states which spellings call sites use. Asserted because a shared type narrowing any of the three breaks call sites the proof would not reach. |
| `refusal` defaults inert, and raises when set | traceable | `tasks.md` 4.1; `design.md` Decision 2 |
| A refused read is counted **before** it is refused | traceable | `tasks.md` 4.1, citing `test_gate_progression_pass.py:355-358` and `test_advance_and_ask.py:362-365` |
| `reads` is an `int` and no `calls` exists on the store | traceable | `tasks.md` 4.1; `design.md` Decision 2 (measured population of `calls`: zero) |
| `__call__` is on the async sibling and not on the sync one | traceable | `tasks.md` 4.1; `design.md` Decision 2 (the placement sizes the superset) |
| `__call__` delegates to `get`, so a bare call is counted | traceable | `design.md` Decision 2 ("delegating to `get`, not an `attr = method` alias") |
| The two stores are siblings sharing one immediate base | traceable | `tasks.md` 4.1; `design.md` Decision 2 (the `mypy` override error) |
| `serving()` returns a class whose constructor discards production's arguments | traceable | `tasks.md` 4.2, 5.3; `design.md` Decisions 3 and 4 |
| `serving()` reads its source at call time | traceable | `tasks.md` 4.3 (explicitly required); `design.md` Decision 3, citing `_SERVED[0]` at lines 359 and 398 |
| Each `serving()` call yields its own subclass | derived | Not stated. Inferred from Decision 3's *rejection* of a mutable class attribute — the rejection's reason is sharing, so non-sharing is what the accepted form must provide. |
| `list_active` does **not** filter a graduated launch | **specified** (existing capabilities, not a delta) | `openspec/specs/launch-step-automation/spec.md:39` and `openspec/specs/launch-clickup-sync/spec.md:91`, both *A graduated launch is left alone*; `tasks.md` 5.4/5.5; `design.md` Decision 5 |
| `list_all` and `list_active` agree | derived | Not stated. Follows from Decision 4 merging 17 `list_active`-only and 25 `list_all`-only declarations onto one type: the superset is only safe while the two answer the same thing. |
| `get_by_product_id` resolves, and answers `None` when it cannot | traceable | `tasks.md` 5.3 |
| `save` replaces the launch held for a product | traceable | `tasks.md` 5.3; the dict-keyed locals |
| `save` **adds** a launch for a product not previously held | derived | Not stated; no artifact says whether `save` is upsert or replace-only. Asserted because the locals that key by `product_id` behave this way and a replace-only double would silently drop a saved launch. |
| `list_launches` and `all` are absent | traceable | `tasks.md` 5.3, 5.2; `design.md` Decision 4 (measured dead by execution) |
| `serving()` takes a launch, an iterable, or a zero-argument callable | traceable | `tasks.md` 5.3 |
| The reads answer a **`tuple`** | derived | Not stated by any artifact, and the locals disagree. See *Unresolved project questions* #3. |

**Deliberately untested**, each with its reason:

- **The 124 migrated declarations themselves.** They are migrations, not
  behaviour. The equality proof, the lockstep pairing and the standalone proof
  (§2, §6) are what close them, and a test per declaration would move the
  collected count outside `tests/unit/support/` — the one thing
  `proposal.md` commits will not happen.
- **The 5 kept-local scope-sniffing catalog ports.** Out of scope by
  `design.md` Decision 6, and they keep their existing local tests untouched.
- **The 2 kept-local `@dataclass` launch stores.** A declaration-form keep; they
  do not migrate, so the shared type has no contract to state about them.
- **`FakeProductReader` answering `None` for a product it does not hold.** The 4
  "build or look up" declarations of `tasks.md` 3.4 are dispositioned at
  migration, and `tasks.md` 3.1's stated surface is a *held* object rather than
  a lookup table. Asserting a `None` path would invent a surface the artifacts
  do not describe.
- **`_conforms` protocol conformance for any of the five types** (tasks 3.2,
  4.1a, 4.2a, 5.5). By design that is checked by `mypy`, not by pytest —
  `AGENTS.md` is explicit that the *assignment* is the mechanism. A pytest
  assertion mimicking it (`isinstance` against a runtime-checkable protocol)
  would check attribute presence only, and would pass for a double that had
  drifted in signature, which is the failure the assignment exists to catch.
  **Verification for these tasks is `uv run mypy .`, not a test in this file.**
- **The refusal being raised from `__call__` as well as from `get`.** It follows
  from `__call__` delegating (test 12), and asserting it separately would pin a
  composition no local exercises: no declaration both aliases `__call__` and
  refuses… except the 2 that do. Recorded as a deliberate gap rather than
  claimed: if `tasks.md` 4.5's migration of those 2 needs it, add it there.
- **Anything about `tests/support/fakes.py`'s nine existing types.** Untouched
  by this change, and already covered by the 52 tests in this directory.

## Obsolete tests

**Not applicable — the change carries no `MODIFIED`, `REMOVED` or `RENAMED`
delta, because it carries no delta specs at all.** No requirement is superseded,
so no existing test can bear on superseded behaviour, and no search for bearing
tests was performed or owed.

Recorded rather than left as an empty list, and with three substantive notes,
because "not applicable" here does **not** mean "nothing existing changes":

1. **129 local declarations across 83 files are deleted by this change**, and
   their test files are edited. Those are *fixtures*, not tests: the assertions
   in those files are unchanged, which is exactly what `tasks.md`'s
   assertion-identity check over every touched file enforces (§1.3 baseline:
   `assert` 6,612, `raises` 238, helper-assert 759, `parametrize` 172, over
   2,192 test functions in 332 files). If that check moves, an assertion was
   changed and the change stopped being a migration. **No local declaration was
   deleted by this pass** — this pass is additive only.
2. **`test_a_graduated_launch_is_left_alone`** (in
   `tests/unit/launch/infrastructure/driving/test_automation_pass.py`, and its
   counterparts in `test_clickup_sync_projection.py` and
   `test_clickup_sync_list_healing.py`) is the test most at risk from this
   change, and the risk is **silent passing**, not failing. It is not obsolete,
   must not be edited, and is protected from the outside by
   `test_fake_launches.py::test_list_active_does_not_filter_a_graduated_launch`.
3. **`test_clickup_webhook_automated_step.py`'s two branches** (`_SERVED[0]`
   rebound at lines 359 and 398) are in the same position: a `serving()` that
   bound its source at subclass creation leaves both green while proving
   nothing. Protected from the outside by
   `test_fake_playbook_repository.py::test_the_source_is_read_at_call_time_not_at_subclass_creation`.

## Where these files live

They are **not** under `tests/unit/support/` yet. Naming absent types aborts
collection of the entire commit tier, so the `pre-commit` hook would block every
commit — including this manifest's own. `mypy .` runs strict over the whole tree
with no excludes, so they must sit where **neither** tool reads them: they are
parked in `<changeRoot>/pending-tests/` with a `.py.pending` suffix, and each
phase `git mv`s its file into place, dropping the suffix, in the same commit
that adds its shared type. Tracked rather than left untracked, so 41 tests do
not ride in a worktree nobody has committed.
`tasks.md`'s preamble carries the table and the successor counts.

**Question 1 below is now settled.** `design.md` Decision 9 fixes the
constructor contract these tests were written against — `FakeProductReader(product)`,
`FakePlaybooks(playbook, *, refusal=None)`, `FakeLaunches(*launches)`,
`FakePlaybookRepository` through `serving` only — by the majority local spelling,
measured. Question 3 is settled the same way: the reads answer a `tuple`, which
46 of 60 local annotations use. The assumptions this pass recorded are now
decisions in the plan rather than facts living only in the tests.

## Unresolved project questions

No channel exists to ask on, so each is recorded with the assumption taken and
the tests depending on it.

1. **The four constructor signatures are not fixed by any artifact.**
   `tasks.md` names each type's *surface* but not how it is handed its subject.
   **Assumptions:** `FakeProductReader(product)` positional (the spelling the 10
   "answer a held product" locals use); `FakePlaybooks(playbook, refusal=…)` /
   `AsyncFakePlaybooks(playbook, refusal=…)` — positional playbook, keyword
   refusal, per Decision 2's `refusal: Exception | None = None`;
   `FakeLaunches(*launches)` variadic, per `tasks.md` 5.5a's census (35 of 58).
   **Depends on it:** all 41 tests construct through these signatures. A
   different constructor spelling makes them fail on the call rather than on the
   assertion, which is visible rather than silent — but it is a rewrite of every
   arrange line, so settle it before implementing.
2. **File naming.** The directory's convention is one file per fake class
   (`test_fake_step_store.py`). `_FakePlaybooksBase`, `FakePlaybooks` and
   `AsyncFakePlaybooks` are three classes with one shared contract.
   **Assumption:** one file for the sibling pair
   (`test_fake_playbooks.py`), a separate file for the repository
   (`test_fake_playbook_repository.py`) — because the repository is a different
   subject with a different install mechanism, and `tasks.md` 4.3 groups "all
   four §4 classes" without saying into how many files. **Depends on it:** paths
   only.
3. **The container type the launch store's reads answer.** No artifact fixes it
   and the locals disagree: `test_gate_progression_pass.py` returns a `tuple`,
   `test_automation_pass.py` a `list`. **Assumption:** `tuple`, matching
   `FakeCatalogPort.list_products()` and the majority spelling. **Depends on
   it:** exactly **one** test —
   `test_fake_launches.py::test_the_reads_answer_a_tuple`. Every other assertion
   in that file converts with `tuple(...)` before comparing, deliberately, so
   that settling this question the other way costs one test rather than eleven.
4. **Whether `_FakePlaybooksBase` may be imported by a test.** `AGENTS.md` says
   the package exports public names and that a module-private name imported
   across modules is a contradiction; `tasks.md` 4.1 nonetheless names the base
   `_FakePlaybooksBase`. **Assumption:** it is not imported.
   `test_the_two_stores_are_siblings_rather_than_parent_and_child` therefore
   states the same fact without naming the base — neither sibling is a subclass
   of the other, and `FakePlaybooks.__mro__[1] is AsyncFakePlaybooks.__mro__[1]`.
   **Depends on it:** that one test.
5. **Whether a `tests/unit/support/` test may construct a production aggregate.**
   The predecessor recorded the same question for `LaunchPlaybook` and assumed
   yes, via the harness's own surface. `test_fake_launches.py` goes one step
   further: it calls `Launch.start(...)` and walks the launch with
   `approve_gate` / `advance_gate` directly, because no harness builder produces
   a graduated launch. **Assumption:** permitted, and unavoidable — the pin
   Decision 5 requires cannot be expressed without a genuinely graduated launch,
   and asserting one into place would make the pin a statement about the test's
   own fixture. The gate list is still read from `tests/support/playbook`'s
   spec-restating constants, never from `launch_playbook.GATE_SEQUENCE`.
   **Depends on it:** `test_fake_launches.py`'s `_launch()` and `_graduated()`
   helpers, so 13 of the 41 tests.
6. **`# type: ignore` on a refused attribute assignment.** `reader.calls = []`
   is a `mypy` error once the property lands and an *unused ignore* until then,
   so neither spelling type-checks in both states. **Assumption:** route the
   refused assignment through `setattr` with the attribute name in a variable,
   which type-checks in both. **Depends on it:**
   `test_reads_is_the_stored_spelling_and_calls_cannot_be_assigned`.

## Baseline

**Full commit-tier baseline**, taken at `4b72aa5` before any test was written:

```
uv run pytest tests/unit tests/agents  ->  2534 passed in 71.55s
```

Zero pre-existing failures, so every failure reported above is attributable to
this pass. Collected counts, before and after:

| | before | after (these 41 landed) | now, with the target absent |
|---|---|---|---|
| `tests/unit` outside support | 2,246 | **2,246 — unchanged** | 2,246 |
| `tests/unit/support` | 52 | **93** | collection error |
| `tests/agents` | 236 | **236 — unchanged** | 236 |
| commit tier total | 2,534 | 2,575 | **cannot be collected** |

**The successor number for `tests/unit/support/` is 93** (52 + 41). Tasks 3.3,
4.3 and 5.5 each ask for "the new expected count"; the per-phase split is 58
after §3 (52 + 6), 80 after §4 (58 + 15 + 7), 93 after §5 (80 + 13).

Re-confirming the tier is green with the four new files set aside — the
attributability check `ai-toolkit:testing` requires:

```
uv run pytest tests/unit tests/agents \
  --ignore=tests/unit/support/test_fake_product_reader.py \
  --ignore=tests/unit/support/test_fake_playbooks.py \
  --ignore=tests/unit/support/test_fake_playbook_repository.py \
  --ignore=tests/unit/support/test_fake_launches.py
  ->  2534 passed in 69.50s
```

**`tests/integration` was not run by this pass.** It carries none of the 41
tests and nothing here reaches it; its 159 remains the §1.2 figure. Noted for
the phase-boundary tasks (3.6, 4.8, 5.8), which do have to run it: this worktree
**does** carry a `.env.test` and `commerce-ops-postgres-1` is up, so the
`AGENTS.md` worktree trap does not currently apply here — but that is a fact
about this worktree at this moment, not one that travels.

Other verification over the four new files:

- `uv run ruff check` — **clean**.
- `uv run ruff format --check` — **clean**.
- `uv run mypy .` — exactly **5 errors, all `Module "tests.support.fakes" has
  no attribute "…"`**, one per shared type named
  (`FakeProductReader`, `FakePlaybooks`, `AsyncFakePlaybooks`,
  `FakePlaybookRepository`, `FakeLaunches`). The same absent-target state as the
  41 failing tests; it clears when §3–§5 land. **No other file's `mypy` result
  moved** (535 source files checked).
- `uv run lint-imports` — not run: these files add no `src/` import that
  `.importlinter` governs, and they import only from `tests.support` and
  `commerce_ops.*.domain`, as the neighbouring files in this directory already
  do.
