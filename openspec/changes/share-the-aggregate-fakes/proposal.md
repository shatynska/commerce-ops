## Why

`share-the-playbook-builders` (2026-09-05) was the last thing ordered ahead of
this one. It closed: **`_hold` is 104 of 104 and `_playbook` 84 of 95** on the
shared builders, so the share-the-base-before-the-composer rule that held the
aggregate stores back for three slices is discharged.

What is left is the largest remaining duplication in the suite: **129
declarations across five names in 83 files, 1,756 lines** — 127 under
`tests/unit`, 2 under `tests/integration`, none under `tests/agents`.

| name | decls | lines |
|---|---|---|
| `_FakeLaunchStore` | 26 | 593 |
| `_FakeLaunches` | 32 | 422 |
| `_FakePlaybookRepository` | 10 | 281 |
| `_FakeCatalog` | 29 | 245 |
| `_FakePlaybooks` | 32 | 215 |

**The proof splits, and this slice needs both instruments.** Checked by
construction rather than by reading — `dataclasses.is_dataclass(T)` and
`T.__dataclass_params__`:

| type | dataclass | frozen | own `__eq__` |
|---|---|---|---|
| `LaunchPlaybook`, `StepDefinition` | yes | yes | yes |
| `tests/support/values.py::CatalogProduct` | yes | yes | yes |
| `Launch`, `Product` | **no** | — | **no** |

So the 42 `LaunchPlaybook`-serving declarations and the 24 product-reader ones
get `share-the-value-doubles`' field-wise equality proof — the precondition
measured by construction over every type the readers actually serve (22 import
the shared `CatalogProduct`, 2 declare their own `@dataclass(frozen=True)`; all
24 are frozen), not assumed from the name — and the 58
`Launch`-serving ones get only `share-the-stateful-fakes`' lockstep pairing,
with its four recorded limits applying unchanged. Each declaration records
which instrument dispositioned it.

## What Changes

Five measurements taken against this tree shape the change. Each was made by
execution, per the rule the last slice recorded — reading finds candidates,
running decides.

- **The five names are four subjects.** `_FakeLaunches` and `_FakeLaunchStore`
  appear together in **zero of the 83 files**; so do `_FakePlaybooks` and
  `_FakePlaybookRepository`. They are one subject under two names, split by
  whichever convention a file's author reached for.

- **The playbook stores split on `await`, not on name.** `_FakePlaybooks` is 25
  sync `get` and 7 async; `_FakePlaybookRepository` is 10 of 10 async. The fault
  line runs *through* `_FakePlaybooks`, so it is **25 sync against 17 async**,
  not 32 against 10, and one type cannot serve both.

  **`await` is not the only axis, and the other four were measured per
  declaration rather than read off the largest body.** The 32 `_FakePlaybooks`
  are 19 plain sync, 6 sync declaring no `__init__` and closing over a module
  constant, 4 async that also alias `__call__` to `get`, 2 async that raise a
  constructor-supplied `refusal` *and* count reads *and* alias `__call__`, and 1
  async that only raises a refusal. A shared type that modelled the await alone
  would serve 25 of the 32; each remaining variant is decided in `design.md`
  rather than left to a generic escape hatch.

- **`_FakePlaybookRepository` is patched as a class, not as an instance.** All
  ten are `monkeypatch.setattr(module, "PlaybookRepository", _FakePlaybookRepository)`,
  so production constructs them with `(db)` and they cannot be handed a
  playbook. That is why all ten take `__init__(*args, **kwargs)`. **What each
  then serves splits three ways, measured per declaration rather than
  generalised from the largest body: 4 build a `LaunchPlaybook` inline, 5
  `return _playbook()` — the file's own builder — and 1 returns `_SERVED[0]`, a
  module-level list two tests rebind mid-file to serve a different playbook.**
  Their shared type needs a class-producing construction the other 42 do not,
  and one that reads its source at *call* time, since binding a value at
  subclass creation would serve the stale playbook to the two tests written to
  distinguish them.

- **`_FakeCatalog` is two subjects under one name**, and only one is in scope:
  24 callable product readers (`async __call__(product_id) -> CatalogProduct`)
  and 5 scope-sniffing catalog ports over `Product`, all five in
  `tests/unit/launch/infrastructure/driving/test_product_*.py`. The five were
  already dispositioned, by `share-the-stateful-fakes` task 10.3 and its
  proposal: *"four of those five apply access-scope filtering that no `_Catalog`
  declaration performs. Migrating them onto `FakeCatalogPort` would drop a scope
  check inside a double, invisibly."* That is a different population from the
  two `FakeCatalogPort`'s own docstring speaks of, which are `_Catalog`
  declarations. Taking the five would widen the subject from the aggregate
  stores to the admin product surfaces. **They stay local, and the recorded
  reason is the predecessor's, cited rather than restated.**

- **Two spellings on the launch store are dead, measured by execution.** 21 of
  26 `_FakeLaunchStore` carry `list_launches` and `all` as delegates to
  `list_all` — counted against the 26 declarations, not against the 23 `def`s
  in `tests/`, two of which sit on doubles outside this slice. Across all 2,693 tests in all three tiers, wrapped at runtime:
  **`list_launches` 0 calls, `all` 0 calls.** Neither is called anywhere in
  `src/`, and all 23 `tests/` mentions of `list_launches` are its own `def`. The
  shared launch store drops both, per the measured-dead rule.

So the change puts **124 declarations in scope, onto five shared types** — the
sync and async playbook stores are two types, not one row's worth, since they
differ in calling contract and each needs its own protocol:

| shared type | takes | decls |
|---|---|---|
| `FakePlaybooks` — sync | `_FakePlaybooks` (sync `get`) | 25 |
| `AsyncFakePlaybooks` | `_FakePlaybooks` (async `get`) | 7 |
| `FakePlaybookRepository` | `_FakePlaybookRepository` | 10 |
| `FakeLaunches` | `_FakeLaunches` 32, `_FakeLaunchStore` 26 | 58 |
| `FakeProductReader` | `_FakeCatalog` (callable) | 24 |

The async playbook store and the repository are separate rows because they are
separate types: the first is handed a playbook as an instance, the second is
installed by patching a *class* production then constructs itself, so they differ
in constructor, install mechanism and the form their `_conforms` assignment takes.
Merging them by declaration count is what hid the fact that two of the five had no
`_conforms` task at all.

**Expected migrated: 122 of the 124**, stated per phase so a shortfall has
something to report against — 24 of 24 product readers, 42 of 42 playbook stores
(or 39, if the completeness search holds the three refusals back), and **56 of
58** launch stores, the two `@dataclass` declarations being a declaration-form
keep under `AGENTS.md` rather than a failure. A phase whose population total is
also its target cannot report a shortfall, which is why none of these is left
implicit.

Two further things this change does, both carried from measurement:

- **The shared launch store does not implement production's `list_active`
  filter, and the reason is recorded at it.** The real repository's
  `list_active` drops launches standing at `graduated`
  (`launch_repository.py:181`), and it is tempting to reproduce that. Measured:
  `list_active` returns a graduated launch in two files, and one of them is
  `test_automation_pass.py::test_a_graduated_launch_is_left_alone`, which hands
  a graduated launch to the double precisely to prove *the pass* leaves it
  alone. A filtering double keeps every assertion in that test green while
  deleting the thing under test. **A shared double must not implement the filter
  its subject is being tested for** — the equality proof cannot see this,
  because the assertions are identical either way.

- **Thirteen of the 129 declarations execute zero calls** across all three
  tiers and must be dispositioned against the standalone proof rather than
  counted green — 6 `_FakeLaunches`, 5 `_FakeCatalog`, 2 `_FakePlaybooks`. A
  declaration nothing calls reports zero, not pass.

**No production code changes.** Nothing under `src/` is read, written or
imported differently.

## Capabilities

### New Capabilities

None. This change adds no behaviour to the system under test.

### Modified Capabilities

None. `.openspec.yaml` sets `skip_specs: true`, as `share-the-unit-test-harness`,
`share-the-value-doubles`, `share-the-stateful-fakes` and
`share-the-playbook-builders` all did: this change moves duplicated test
arrangement into an existing shared package and changes no specified behaviour.
Per `AGENTS.md` — *Test design before implementation* — a change declaring no
specification deltas owes no new tests derived from deltas; **what it owes is
that the existing suite stays green and its collected count outside
`tests/unit/support/` does not move.**

Baselines re-taken on this tree, not inherited: `tests/unit` outside support
**2,246**, `tests/agents` **236**, `tests/integration` **159** (run here with a
configured `.env.test`, 159 passed and zero skipped), `tests/unit/support`
**52** and the only number allowed to move.

## Impact

- **`tests/support/fakes.py`** — five new shared types (six classes, counting
  the base the sync and async playbook stores share) beside the nine
  `share-the-stateful-fakes` added, each with its **own** `_conforms` protocol
  assignment — five of them, since the sync and async playbook stores are
  siblings and neither satisfies the other's protocol.
- **`tests/unit/support/`** — contract tests for all six classes, added to its 52.
- **Up to 83 test files** (129 declarations — 127 under `tests/unit`, 2 under
  `tests/integration` — of which **7 stay local**: the 5 scope-sniffing catalog
  ports and the 2 declaration-form keeps of Decision 4), losing the reproducible part of
  1,756 lines. A file whose only declaration is a kept-local port is not
  modified, so 83 is the population, not the touched count.
- **`AGENTS.md`** — *The shared harness* section, updated with what this slice
  took and what it left, including the two rules it establishes: that a shared
  double must not implement the filter its subject is tested for, and that a
  double patched as a class needs a class-producing construction.
- **`docs/proposed-change-order.md`** — entry 3 deleted on archive, per that
  file's own rule.
- **Conflict-prone**, like all four predecessors: it reaches up to 83 test files, so
  it does not run concurrently with anything else editing `tests/` broadly.
