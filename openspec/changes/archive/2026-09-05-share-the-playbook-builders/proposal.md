## Why

`share-the-unit-test-harness` (2026-09-04) built `tests/support/steps.py::hold()`
and `tests/support/playbook.py::playbook()`, then used them in **31 of 104** and
**13 of 95** files. Task 8.3 records the reason it stopped:

> `_hold` | 73 of 104 | composes over a *customised* `_step`; `hold()` composes over the canonical one

That was true when `_step` was 135 opaque local bodies. It is not true now.
**all 135 `_step` declarations now reach the shared builder** — 121 as partials
and 14 as one-line wrappers whose signature takes `identifier` positionally — so
a file's "customised foundation" is a readable keyword set rather than an opaque
body, and reconciling it with `hold()` is forwarding that set.

The claim has been proved by execution rather than argued. Every local `_hold`
was imported and called for all eight gates, its deltas against `hold(gate)`
derived field-wise at runtime, and `hold(gate, **deltas) == local(gate)`
asserted:

| | result |
|---|---|
| `_hold` local declarations | **73** |
| reproducible exactly | **73 of 73** — 59 as a partial, 14 as a one-line wrapper |
| not reproducible | **0** |

`_playbook` was probed the same way, against the shared builder's parameter
space: **68 of 82 reproduce exactly**, 8 differ only in the order the fillers
sit in the step tuple, 5 differ in which steps they hold, 1 was unprobeable.

So the recorded blocker has dissolved for `_hold` outright and for four fifths
of `_playbook`. 155 declarations across 110 files, **1,643 lines**, are the
largest remaining duplication in the suite and the one blocking the aggregate
stores (`docs/proposed-change-order.md` — `share-the-aggregate-fakes`).

**This slice also gets the strong proof back.** `StepDefinition` and
`LaunchPlaybook` are both `@dataclass(frozen=True, slots=True)`
(`launch_playbook.py:316`, `:818`), so `==` is structural and
`share-the-value-doubles`' equality proof applies directly. The lockstep
pairing built for `share-the-stateful-fakes` was a substitute for exactly this
being inexpressible; it is strictly weaker and is not used here.

## What Changes

- **Migrate the 73 local `_hold` declarations** onto
  `tests/support/steps.py::hold` — 59 as `functools.partial(hold, **deltas)`,
  14 as a one-line wrapper. The 14 are wrappers for a measured reason, not a
  judged one: their delta value is *computed from the gate argument*
  (`handler=f"hold.{gate.replace('-','_')}"` in 11, a gate-derived `name` in 3),
  which a partial's fixed keyword cannot express.
- **Migrate the reproducible `_playbook` declarations** onto
  `tests/support/playbook.py::playbook`, each passing **its own filler**
  explicitly — never falling back on the parameter's default, per the archived
  task 6.7 and `playbook()`'s own docstring. Which callable that is was
  measured, not assumed: of the 68 that fill, 53 apply the file's own `_hold`,
  14 delegate to a local `_fill()` that itself applies it, and 1 applies
  `_step`.
- **Add one parameter to `playbook()`: `fillers_first: bool = False`**, taking
  the 8 declarations that build `(*fillers, *steps)`. `LaunchPlaybook.__post_init__`
  sorts `gates` but *not* `steps`, so that order is part of `==` and cannot be
  normalised away.
- **Record every declaration left local, with its measured reason**, in the
  final commit and in `AGENTS.md` — continuing the record `share-the-unit-test-harness`
  task 8.3 and `share-the-stateful-fakes` established.
- **Correct `docs/proposed-change-order.md`'s account of the next slice.** It
  states the aggregate stores are blocked because "a shared store would have to
  be told what to return". Measured, **26 of the 32 `_FakePlaybooks` take the
  playbook as a constructor argument** (17 `__init__(playbook)`, 6 with a
  default, 3 also taking a refusal) and the other 6 return a module constant —
  and what they hold is a `LaunchPlaybook`, so their instance state is
  structurally comparable, unlike the previous slice's. The ordering constraint
  stands; the stated reason overstates the coupling.

**No production code changes.** Nothing under `src/` is read, written or
imported differently.

## Capabilities

### New Capabilities

None. This change adds no behaviour to the system under test.

### Modified Capabilities

None. `.openspec.yaml` sets `skip_specs: true`, as
`share-the-unit-test-harness` and `share-the-stateful-fakes` both did: this
change moves duplicated test arrangement into an existing shared package and
changes no specified behaviour. Per `AGENTS.md` — *Test design before
implementation* — a change declaring no specification deltas owes no new tests
derived from deltas; **what it owes is that the existing suite stays green and
its collected count outside `tests/unit/support/` does not move.**

## Impact

- **`tests/support/steps.py`** — unchanged except its `hold()` docstring, which
  gains the migration's measured outcome.
- **`tests/support/playbook.py`** — one new parameter, `fillers_first`.
- **110 test files** across all three tiers (133 declarations under
  `tests/unit`, 17 under `tests/integration`, 5 under `tests/agents`), losing
  1,643 lines of duplicated builder bodies.
- **`AGENTS.md`** — *The shared harness* section, updated with what this slice
  took and what it left.
- **`docs/proposed-change-order.md`** — the `share-the-aggregate-fakes` entry's
  stated blocker, corrected.
- **Unblocks** `share-the-aggregate-fakes`, whose 129 declarations in five
  store names are ordered behind this one by the share-the-base-before-the-composer
  rule that has now held three times.
