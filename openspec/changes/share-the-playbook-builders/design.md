## Context

See `proposal.md` — *Why*. The state this design starts from, measured at
`132304d`:

```
name         total   uses the shared builder   declares its own body
_step         135              135                       14
_hold         104               31                       73
_playbook      95               13                       82
```

The two columns do not partition: **all 135 `_step` declarations already reach
`tests/support/steps.py::step`**, and the 14 counted in the right-hand column
still declare a one-line body because their signature takes `identifier`
positionally, which a partial cannot deliver (archived task 6.5, `[x]`). For
`_hold` and `_playbook` the columns *do* partition — nothing in those rows is
both. The 73 and the 82 are what this change migrates.

The 73 local `_hold` split by what they compose over — 49 over a `_step` that is
itself a partial over the shared builder, 20 constructing `StepDefinition` from a
dict literal, 4 over a `_step` that is still `StepDefinition`-direct. In all
three shapes the file's own defaults are a readable keyword set, which is the
fact that dissolves task 8.3's blocker.

`tests/support/steps.py::hold` and `tests/support/playbook.py::playbook` already
exist, with their default sets derived and documented. **This change builds no
new builder.** It is a migration against builders that shipped.

Two constraints fix the shape of everything below:

1. **`StepDefinition` (`launch_playbook.py:316`) and `LaunchPlaybook` (`:818`)
   are `@dataclass(frozen=True, slots=True)`.** `==` is structural, so a
   migration can be *proved* rather than reviewed.
2. **`LaunchPlaybook.__post_init__` sorts `gates` and does not sort `steps`**
   (`:830-844`). Step order is part of equality and cannot be normalised away.

## Goals / Non-Goals

**Goals**

- Every local `_hold` and every reproducible local `_playbook` migrated, with
  the equality proof run at each one.
- Every declaration left local carries a *measured* reason, not a judged one.
- The collected count of the three tiers, excluding `tests/unit/support/`,
  unchanged at every commit.

**Non-Goals**

- The aggregate stores (`_FakePlaybooks` 32, `_FakeLaunches` 32, `_FakeCatalog`
  29, `_FakeLaunchStore` 26, `_FakePlaybookRepository` 10). They are the next
  slice and are ordered behind this one. Counted for §6.4's correction: **26 of
  the 32 `_FakePlaybooks` take the playbook as a constructor argument** (17
  `__init__(playbook)`, 6 with a default, 3 also taking a refusal) and 6 return
  a module constant with no `__init__` at all.
- The 14 positional-identifier `_step` wrappers, which
  `share-the-unit-test-harness` task 6.5 settled deliberately.
- The remaining recurring helpers the census surfaces — `_provenance` 44,
  `_start` 35, `_launch` 34, `_resolve` 29, `_approval` 24. Naming them here is
  scope control, not a promise.
- Any change to production code, or to what `hold()`'s three canonical defaults
  are. Re-deriving those would re-open a decision this change depends on.

## Decisions

### Decision 1 — Migrate `_hold` first, `_playbook` second

The share-the-base-before-the-composer rule, now held three times. **45 of the
82 files also declare a `_hold` that this change moves**; a `_playbook` migrated
over an unmigrated `_hold` is proved against a foundation that is about to move.

*Two populations wear the number 45 and they are not the same.* 71 of the 82
files declare a `_hold` **name** and 67 of the 68 filling declarations apply it
(Decision 7) — but many of those `_hold`s are already partials over the shared
builder, migrated by `share-the-unit-test-harness`. Only 45 are still local, and
only those are an ordering constraint. `proposal.md` — *Impact*'s 110 files is
`73 + 82 − 45` in that same **still-local** sense.

*Alternative considered:* migrate by file, both names at once, since 45 of the
110 files carry both. Rejected — a per-file commit proves two composed changes
in one comparison, and when it fails, which of the two failed is exactly the
information the proof was run to get. `share-the-stateful-fakes` tested this
deliberately: of 175 migrations, the single pairing that failed for a leaf
reason was the one file that kept its own `_Record`.

### Decision 2 — The equality proof, not the lockstep pairing

Because both subjects are frozen dataclasses, the proof is the direct one:

```python
def _hold(gate, **o):
    expected = _hold_local(gate, **o)
    actual = hold(gate, **{**FILE_DELTAS, **o})
    assert expected == actual
    return actual
```

Instrument every migrating declaration, run all three tiers, settle to zero
failures, then delete the local and the wrapper in a second commit.

**The proof harness is temporary and leaves with the migration.** The decorator
is added to the working tree by each instrument commit and removed by that
name's last settle commit; it never lands in `tests/support/`. A proof that
outlives its migration is a permanent dependency on a temporary arrangement,
and both predecessors removed theirs for that reason (`share-the-value-doubles`
§1.6; `share-the-stateful-fakes`' `_paired.py`).

*Alternative considered:* the lockstep pairing from `share-the-stateful-fakes`.
Rejected explicitly. It exists because `FakeStepStore() == FakeStepStore()` is
identity, and `AGENTS.md` records four things it cannot see. None of the four
applies to a frozen dataclass compared by value, and the pairing is strictly
weaker than what is available here.

### Decision 3 — Partial or wrapper is decided by gate-independence, measured

For each local `_hold`, derive the deltas **at runtime by field difference**
against `hold(gate)`, for all eight gates. If the delta set is identical across
gates, the file takes `functools.partial(hold, **deltas)`. If any delta *value*
varies with the gate, a partial cannot express it and the file takes a one-line
wrapper.

Run over all 73:

```
  verdict            files
  PARTIAL              59
  WRAPPER              14      11 handler=f"hold.{gate.replace('-','_')}"
                                3 a gate-derived name
  not reproducible      0

  deltas per declaration, all 73:  0│▏3  1│████▏16  2│████▊18  3│█████▍21
                                   4│██▉11  5│█▏4        ≤3 = 58 · ≤4 = 69
       of which the 59 PARTIAL:    0│3  1│16  2│12  3│17  4│7  5│4
                                                     ≤3 = 48 · ≤4 = 55
       and the 14 WRAPPER:         2│6  3│4  4│4

  against a median local body of 13 lines.

  delta keys, over all 73: handler 43 · kind 43 · timing_anchor 35
              assignees 25 · name 16 · discipline 13 · confirmer 4
              (179 occurrences, reconciling with the histogram's weighted sum)
```

**Parameter surface is checked separately from delta values, and is
measured-inert here.** Gate-independence decides partial-vs-wrapper only for a
local whose *surface* `hold(gate, **overrides)` can already accept. A local
taking a second positional, or a keyword `hold()` does not have, cannot become a
partial however stable its deltas are — and dropping such a spelling would fall
under `AGENTS.md`'s "a dropped spelling must be measured dead". Measured over all
73: **63 are `(gate)` and 10 are `(gate, **overrides)`, and nothing else.** Every
one is accepted by `hold()` unchanged, so no file is routed to the wrapper form
for a surface reason. The clause is kept because it is what makes the
classification sound, and recorded as measured-inert rather than left looking
like a live exclusion.

**Deriving deltas at runtime rather than from the source is itself a decision.**
A static pass over the same 73 over-reported `discipline` at 26 (it cannot see
that `next(iter(Discipline))` and `any_discipline()` evaluate equal),
over-reported `confirmer` at 22, and mis-classified one wrapper as a partial.
The archive records the same lesson from the other direction: a local `_hold`
that builds a dict and calls `_step(**attributes)` carries no call keywords, so
reading `call.keywords` silently drops `kind`, `status` and `handler` — and **24
of these 73 are exactly that shape.**

### Decision 4 — `name` is passed back explicitly wherever the local inherited it

`hold()` defaults `name` to `f"Blocking work holding the {gate} gate"`; a local
`_hold` that never passes `name` inherits `step()`'s `"Work this step asks for"`
through its file's `_step`. Those two differ, silently, in a field no assertion
usually reads. **16 of the 73 are in this position** and take `name` as an
explicit delta. The archive records this as the defect that took 101 proof
failures to zero, so it is planned for rather than discovered.

### Decision 5 — `playbook()` gains exactly one parameter: `fillers_first`

Probing all 82 local `_playbook` against the builder's parameter space:

```
  68  REPRODUCIBLE exactly
        32  fill=unheld  held_must_be_active=False  injects no subject
        23  fill=unheld  held_must_be_active=False  injects a default subject
         5  fill=none    injects a default subject
         3  fill=none    injects no subject
         3  fill=unheld  held_must_be_active=True
         2  fill=all     (see Decision 6)
   8  ORDER-ONLY       same steps, fillers ahead of the subject
   5  DIFFERENT-STEPS  a genuinely different filler rule
   1  UNPROBEABLE      required positional arguments the probe cannot supply
```

Only the 8 ORDER-ONLY group needs the builder to grow, and it needs one
boolean. `steps=(*fillers, *steps)` cannot be reached from
`steps=(*steps, *fillers)` by any existing parameter, because `__post_init__`
does not sort steps.

*Alternatives considered:* (a) let those 8 keep a local body — rejected, 8 is
the second-largest configuration group and the parameter is one line; (b)
normalise step order inside `playbook()` — rejected outright, it would change
what 13 already-migrated files produce and silently rewrite a tuple the suite
asserts on.

### Decision 6 — No fill-all mode; the 3 candidates are settled at their call sites

A static read says 32 declarations "fill every gate unconditionally" and so need
a third fill mode. The proof says otherwise: **40 of the 82 take no steps at
all**, and with no steps the held set is empty, so filling all and filling
unheld are the same function. Only 3 declarations both accept steps *and* fill
unconditionally — and they are not a fourth disjoint bucket. **Two sit in
Decision 5's REPRODUCIBLE 68** (the `fill=all` row); the third,
`test_progress_launch_metric_step.py`, sits in **ORDER-ONLY**, where fill-all is
the mode under which its steps match as a multiset. So §5's buckets partition 82,
and fill-all is an overlay across two of them, not a fifth.

For those 3 the modes still coincide unless a *blocking* step is actually
passed — and `step()`'s canonical `blocking` is `False`. Whether they diverge is
therefore a fact about their real call sites, not about the file. So the
implementation reads those three call sites and migrates them where the fill is
equivalent; where it is not, the file keeps its body and is recorded.

*Alternative considered:* make `fill_unheld: bool` three-valued
(`"none" | "unheld" | "all"`). Rejected — it degrades the primary parameter's
type for at most three files, and `playbook()` is already load-bearing for 13
migrated ones.

### Decision 7 — Every migrated call passes **its own filler**, explicitly, always

`playbook()`'s `filler` has no trustworthy default: of the local variants that
fill, 36 fill with an automated step and 33 with a human one. A file that falls
back on the built-in `hold` gets a human filler where its own was automated —
**and the suite can stay green while those tests exercise a different
playbook.** This is the one place the migration goes quietly wrong, which is
why it is a decision rather than a task note.

**The rule is "its own filler", not "its own `_hold`."** Measured over the 82,
by the callable each applies per gate:

```
  68 fill · 14 do not
       53  apply the file's own _hold directly
       14  delegate to a local _fill(), which itself applies the file's _hold
        1  applies _step  (test_metric_step_journalling.py, via _metric_step)
```

So 67 of the 68 resolve to the file's `_hold` and exactly one does not.

The **14 that do not fill** split across Decision 5's buckets as 10
REPRODUCIBLE, 2 DIFFERENT-STEPS, 1 ORDER-ONLY, 1 UNPROBEABLE. Two things follow
that the implementer needs stated rather than inferred. First, **DIFFERENT-STEPS
is not a bucket of non-fillers**: 3 of its 5 do fill, with a filler rule that is
genuinely different, which is what the label means. Second, **this split
disagrees with Decision 5's `fill=none` count of 8 by two declarations** — the
static filler pass scores a declaration non-filling when it never iterates
`SPECIFIED_GATE_ORDER`, while the prover scores by reproduced output. The
disagreement is real and small; task 5.1 resolves it by reading the two, and it
is recorded here rather than reconciled by picking the more convenient number. That one
passes its own step-shaped filler; it is not made to fit `_hold`, and it is not
allowed to fall back on the default either. Naming the rule after `_hold` would
have left it undefined for that file and would have invited the implementer to
invent a rule at the gate.

**Mechanised, and by identity rather than by presence.** The AST check asserts
that a migrated `playbook(...)` call site passes `filler=` **and that its
argument resolves to a name bound at module level in that file** — a `def`, or
(after Phase A, for the majority) a `_hold = functools.partial(hold, **deltas)`
binding — never to the `hold` imported from `tests.support.steps`.

*The binding form matters for three files.* Decision 3's histogram records **3
declarations needing zero deltas**, whose shortest migration is `_hold = hold`.
That is a plain import alias: correct under this decision, since it *is* the
file's own filler, but indistinguishable from the forbidden fallback to any
check reading the call site. Those three bind
`_hold = functools.partial(hold)` instead — no deltas, one wrapper, and the name
stays file-local and checkable. They are
`test_step_confirmer.py`, `test_automated_decision_wiring.py` and
`test_automation_pass_release.py`. A check for the keyword alone is satisfied
by `filler=hold`, which is the exact fallback this decision forbids. The check
is scoped to call sites where `fill_unheld` is not `False`. **14 of the 82 do
not fill at all**, 8 of them inside the 66 that §5.2 migrates; at those no filler
is ever called, and requiring one would fail 8 correct migrations.

## Risks / Trade-offs

- **A migrated `_playbook` silently falls back on the default filler** →
  Decision 7's AST check, run over every touched file, at every commit.
- **`name` diverges unnoticed because no assertion reads it** → Decision 4; and
  the proof compares whole objects, not the fields a test happens to assert.
- **The proof passes vacuously for a declaration the suite never executes** →
  a declaration nothing calls cannot be compared, and "zero failures" is
  satisfied by silence. So the harness *counts* comparisons per declaration, and
  a zero count is a reported result requiring disposition, not a pass. The proof
  otherwise runs at every real call site during a full three-tier run. `tests/integration` carries 17 of the
  155 declarations and **skips in its entirety without a configured
  `.env.test`** (`AGENTS.md` — *Working in a git worktree*), which would make
  that reporting a lie. The tier is confirmed running before any proof result is
  believed.
- **The collected count moves** → checked at every commit against the 1.1
  baseline, tracked as two numbers (the pre-existing tree, which never moves,
  and `tests/unit/support/`, which has its own).
- **A file is edited by both the `_hold` and the `_playbook` pass** — 45 of 110
  are → the whole-change assertion-identity run is what catches drift
  accumulated across passes on one file, as it was in the previous slice.
- **`fillers_first` is added and then used by one file** → it is added in the
  same commit as the 8 that need it, never speculatively.

## Migration Plan

Per name, then per file, two commits each as in the previous three slices:
instrument and prove, then delete the local. Baselines re-taken at `132304d`:
**2,528** collected in the commit tier (2,246 `tests/unit` outside support + 46
`tests/unit/support` + 236 `tests/agents`), **159** `tests/integration`. This
worktree's `.env.test` points at `commerce_ops_harness_test`, migrated and
seeded; `commerce-ops-postgres-1` is up.

Rollback is per commit — no production code is touched, and no schema, config
or deployment artifact changes.

## Open Questions

None. The two questions this change opened — whether `playbook()` needs a
fill-all mode, and whether the ORDER-ONLY group can be normalised — were both
answered by the proof before this document was written (Decisions 5 and 6).
