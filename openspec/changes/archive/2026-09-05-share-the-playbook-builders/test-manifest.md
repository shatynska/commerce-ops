# Test manifest — `share-the-playbook-builders`

Written by the test-writing pass, before any of the change's implementation
tasks were performed. **Not an artifact the OpenSpec schema knows about**: it
does not appear among `openspec instructions apply`'s context files and has to
be read on purpose.

**This pass is additive only.** It added one file under `tests/unit/support/`
and this manifest. No existing test was edited, deleted or disabled, and no
implementation was written — `tests/support/playbook.py` is untouched.

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
So deriving a suite here would not be thoroughness, it would break the
invariant the change is verified by. Nothing was derived beyond the one target
`tasks.md` §4 plans.

## What was written

**File:** `tests/unit/support/test_playbook_fillers_first.py` — **6 test
functions**, serving `tasks.md` §4.1 (the parameter) and §4.2 (its behaviour
test, required to live in `tests/unit/support/`).

| # | Test (runner-selectable) | Serves | First run |
|---|---|---|---|
| 1 | `tests/unit/support/test_playbook_fillers_first.py::test_the_fillers_follow_the_steps_by_default` | 4.1 — `fillers_first: bool = False` preserves `(*steps, *fillers)` | **passes** |
| 2 | `…::test_fillers_first_puts_the_fillers_ahead_of_the_steps` | 4.1 — `True` produces `(*fillers, *steps)` | fails |
| 3 | `…::test_fillers_first_reorders_the_same_steps_rather_than_building_others` | 4.1 — design Decision 5's ORDER-ONLY group: same steps, different order | fails |
| 4 | `…::test_fillers_first_is_inert_where_no_gate_is_filled` | 4.1 — composition with `fill_unheld=False` | fails |
| 5 | `…::test_fillers_first_orders_a_supplied_filler_the_same_way` | 4.1 + design Decision 7 — composition with an explicit `filler` | fails |
| 6 | `…::test_supplied_step_order_is_read_back_rather_than_sorted` | design Decision 5's premise — `LaunchPlaybook.__post_init__` sorts `gates`, not `steps` | **passes** |

Run the six alone with:

```
uv run pytest tests/unit/support/test_playbook_fillers_first.py
```

### The two that pass on their first run are not the alarm state

`ai-toolkit:testing` treats a first-run pass as an alarm **where no
implementation exists**. Tests 1 and 6 are in the other situation — the target
already exists — and a pass there is the expected result:

- **Test 1** pins the order `playbook()` produces *today*, which 13
  already-migrated files assert on. It is the control the parameter must not
  disturb; it would be meaningless if it failed now.
- **Test 6** asserts an existing property of `LaunchPlaybook` (steps read back
  in supplied order). It is a regression guard on the premise Decision 5 rests
  on, not a claim about unwritten code. It is written so that both plausible
  sorts — by identifier and by gate position — would reverse the supplied pair,
  so a future `__post_init__` that started sorting steps fails it by name
  rather than surfacing as eight confusing migration failures.

Tests 2–5 fail in the **absent-target** state (`TypeError: playbook() got an
unexpected keyword argument 'fillers_first'`). Their assertions have therefore
**not yet been exercised** — that is what §4.1 makes readable.

## Assertion classification

The change carries no specification deltas, so **no assertion here is
`specified` in the delta sense.** Each one instead traces to a planning
artifact, which is recorded per assertion rather than left implicit.

| Assertion | Class | Traces to |
|---|---|---|
| Default `False` yields `(SUBJECT, *fillers)` | traceable | `tasks.md` 4.1; `playbook()` line 132 today |
| `True` yields `(*fillers, SUBJECT)` | traceable | `proposal.md` — *What Changes*; `design.md` Decision 5 |
| Both orders hold the same step **set** | derived | Not stated in any artifact. Inferred from Decision 5's label ORDER-ONLY ("same steps, fillers ahead of the subject"). Constrains the implementation to reorder rather than rebuild. |
| `fill_unheld=False` makes the parameter inert | derived | Not stated. Follows from `fillers` being `()` when nothing is filled; asserted so the two parameters cannot be entangled. |
| An explicit `filler`'s products are the ones reordered | traceable | `design.md` Decision 7 ("every migrated call passes its own filler"), which makes this the only composition the 8 will exercise in practice |
| Supplied step order is read back unsorted | traceable | `design.md` — *Context* constraint 2 and Decision 5, citing `launch_playbook.py:830-844` |

**Deliberately untested**, each with its reason:

- **`fillers_first` combined with `held_must_be_active=True`.** That parameter
  changes *which* gates are filled, never where the fillers sit; the two are
  independent by construction and a test would assert the composition of two
  unrelated lines.
- **`fillers_first` combined with a custom `gates=` tuple.** `gates` is sorted
  by `__post_init__` and never reaches the steps tuple.
- **`fillers_first=True` with no steps at all.** 40 of the 82 declarations pass
  no steps (`design.md` Decision 6), but with an empty `steps` tuple both orders
  are the same value, so the test could not discriminate.
- **The 8 ORDER-ONLY declarations themselves.** They are migrations, not
  behaviour; §5.3's equality proof is what covers them, and testing them here
  would move the count outside `tests/unit/support/`.

## Obsolete tests

**Not applicable — the change carries no `MODIFIED`, `REMOVED` or `RENAMED`
delta, because it carries no delta specs at all.** No requirement is
superseded, so no existing test can be bearing on superseded behaviour.

Recorded rather than left as an empty list, and with one substantive note: task
4.1's parameter defaults to `False`, which is exactly today's behaviour, so
**no existing test's expectations change**. That is asserted by test 1 above
rather than assumed. Beyond that, no search for bearing tests was performed and
none was owed.

## Unresolved project questions

No channel exists to ask on, so each is recorded with the assumption taken and
the tests depending on it.

1. **File naming under `tests/unit/support/`.** All nine existing files are
   named for a fake class (`test_fake_step_store.py`, `test_stub_date.py`).
   This subject is a *parameter of a builder function*, which the convention
   does not cover. **Assumption:** name it for the parameter,
   `test_playbook_fillers_first.py`, rather than `test_playbook.py` — which
   would claim to cover all of `playbook()` while covering one parameter.
   **Depends on it:** all 6 tests (their path only).
2. **Whether a `tests/unit/support/` test may assert a property of a production
   aggregate.** The nine existing files exercise fakes only. Test 6 asserts
   that `LaunchPlaybook` does not sort its steps. **Assumption:** permitted,
   because it goes through the harness's own surface (`playbook()`, never
   `LaunchPlaybook(...)` directly) and states its expected order as a literal
   tuple rather than reading production's answer — which is the distinction
   `tests/support/playbook.py`'s own docstring draws. **Depends on it:** test 6.
3. **Whether `tests/unit/support/` counts toward the assertion-identity check.**
   The preamble to `tasks.md` excludes both `tests/support/` and
   `tests/unit/support/` from it. **Assumption:** this file is excluded, so its
   assertions were written for clarity rather than to a uniqueness constraint.
   **Depends on it:** tests 1, 2 and 5, whose assertions are structurally
   similar to one another.

## Baseline

Full commit-tier baseline, taken at `132304d` before any test was written:

```
uv run pytest tests/unit tests/agents  ->  2528 passed in 71.42s
```

Zero pre-existing failures, so every failure reported above is attributable to
this pass. Collected counts, before and after:

| | before | after |
|---|---|---|
| `tests/unit` outside support | 2,246 | **2,246 — unchanged** |
| `tests/unit/support` | 46 | **52** |
| `tests/agents` | 236 | **236 — unchanged** |
| commit tier total | 2,528 | 2,534 |

**§4.2's successor number for `tests/unit/support/` is 52** (46 + 6).

`tests/integration` was **not** run by this pass: it carries none of the six
tests and nothing here reaches it. Its 159 remains the §1 figure, unverified by
this pass — task 1.2 is what confirms it, and that confirmation is still owed.

Also run over the new file only: `uv run ruff check` clean, `uv run ruff format
--check` clean. `uv run mypy .` reports exactly **4 errors, all
`Unexpected keyword argument "fillers_first" for "playbook"`** at lines 63, 73,
82 and 92 of the new file — the same absent-target state as the four failing
tests, and it clears when §4.1 lands. No other file's mypy result moved.
