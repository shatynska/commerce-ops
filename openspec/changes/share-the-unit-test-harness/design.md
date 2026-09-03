## Context

See `proposal.md` — Why, for the motivation and the measurements. This document
fixes what the proposal defers to it: where the shared package lives, what each
builder's API is, how a file is migrated, in what order, and the rule that says
when a migration has gone wrong.

Four properties of the current suite shape every decision below.

**The duplication has not yet drifted where it matters most.** All 159 copies of
`SPECIFIED_GATE_ORDER` are byte-identical; `_opening_for` has 120 copies and one
variant; `CONFIRMATION_GATES` has 128 copies and one semantic variant. The
mechanical population is mechanical *today*. It stops being mechanical the first
time someone edits one copy, and at 159 copies that is a matter of when.

**Where it has drifted, it has drifted within one body.** `_step` has 135
declarations and 77 distinct variants — but every one of them has the same body:

```python
def _step(...) -> StepDefinition:
    attributes: dict[str, Any] = { ...17 keys... }
    attributes.update(overrides)
    return StepDefinition(**attributes)
```

The variants differ only in the default values in that dict. This is not 77
designs; it is one design with 77 default sets, which is what makes Decision 4
possible and is the single most important measurement in this document.

**The signature, however, is not uniform**, and neither is `_hold`'s or
`_playbook`'s. Measured by AST rather than by eye:

| helper | declarations | signatures |
|---|---|---|
| `_step` | 135 | **121** `(**overrides)`, **14** `(identifier, **overrides)` |
| `_hold` | 104 | **89** `(gate)`, **15** `(gate, **overrides)` |
| `_playbook` | 95 | 40 `()`, 31 `(steps)`, 13 `(*steps)`, 11 one-offs |

This matters because Decision 4's migration form is a `functools.partial`, and a
partial can only preserve a call site whose local signature it can reproduce.
Decision 4 states the rule that follows from it; the counts above are what the
rule is calibrated against, and every derived table in this document is stated
over the population it was measured on rather than over the declaration total.

**`tests/` is a package, but only partly.** `tests/__init__.py`,
`tests/unit/__init__.py`, `tests/agents/__init__.py` and
`tests/integration/__init__.py` exist; 9 of roughly 70 directories carry one.
No test file imports from another test file today — there is no precedent to
follow for the import path.

**`tests/conftest.py` already forbids the escape hatch.** Its zero-skip guard
means a migration that breaks a file cannot be parked behind a skip; it fails
the commit. That is a constraint on how the work proceeds, and a good one.

## Goals / Non-Goals

**Goals:**

- One declaration of each duplicated arrangement, importable from every tier.
- Doubles complete enough that the five surviving production tolerances *could*
  be deleted — by `unify-launch-adapter-dependencies`, not here — and whose
  incompleteness would be caught by `mypy` rather than by a reader.
- A migration procedure whose failure mode is a blocked commit or a reported
  finding, never a quietly weakened assertion.
- A stopping rule that a reviewer can check mechanically rather than by reading
  202,048 lines.

**Non-Goals:**

- Deleting the production tolerances (`proposal.md` — Impact says why).
- Migrating every file. The change is complete when the populations named in
  `tasks.md` are migrated; a long tail of one-off helpers is left alone.
- A general-purpose testing framework. `tests/support/` holds what this suite
  already writes by hand, and nothing speculative.
- Reducing line count as such.
- **Repointing any test from `alembic/data/playbook_v1.yaml` to
  `alembic/data/playbook_reference.yaml`** — see the note below. It is a
  correction this change must not make in passing.

### A trap this migration walks straight into

`alembic/data/playbook_v1.yaml` is **stale**; `alembic/data/playbook_reference.yaml`
(358 steps) is the current set. `docs/deferred-work.md:835-890` records the split,
records that it has already cost one wrong analysis, and names its own trigger
conditions to close — none of which is this change.

Three tests read the stale file deliberately, as a *baseline* for asserting that
the earlier human pass was carried across unchanged:
`test_playbook_reference_set.py:298`, `test_playbook_seed.py:447`,
`test_seeded_step_fields.py:692`. Four more mention it in comments
(`tests/agents/step_handlers/strategy/test_compliance_screen_*.py`), and those
four are also among Population B's heaviest `_step` variants — eight overrides
each, the largest in the suite — so a migrator **will** be reading them.

Repointing any of them at `playbook_reference.yaml` would change what they
assert, not how they arrange it, and Decision 7 forbids exactly that. The
staleness is real, it is recorded, and it is owned elsewhere. A migrator who
notices it raises a finding and moves on.

## Decisions

### 1. `tests/support/`, imported as `tests.support.*`, with `pythonpath` pinned

The package sits at `tests/support/`, a sibling of the three tiers rather than
inside one, because all three duplicate the same arrangement — `SPECIFIED_GATE_ORDER`
appears in 140 unit, 14 integration and 5 agent files.

Imports are absolute: `from tests.support.playbook import SPECIFIED_GATE_ORDER`.
This resolves today because `tests/__init__.py` exists, so pytest's `prepend`
import mode inserts the repository root when it imports the root
`tests/conftest.py`. That is a derived consequence of a file that exists for
other reasons, and 319 files would depend on it. So
`[tool.pytest.ini_options]` gains `pythonpath = ["."]`, making the guarantee
explicit in one line.

Adding the repository root to `sys.path` shadows no installed distribution:
`commerce_ops` ships from `src/`, and the only root directory sharing a
distribution name is `alembic/`, which has no `__init__.py` and is therefore a
namespace portion the finder passes over in favour of the regular package in
site-packages.

*Alternatives considered.* **A `conftest.py` exporting fixtures** — rejected:
most of the duplicated surface is constants, dataclasses and pure functions, and
routing those through fixtures makes every call site take an argument it does
not otherwise need, which is more churn in test bodies, not less. **An installed
`commerce_ops_testing` package under `src/`** — rejected: it would ship in the
wheel (`[tool.hatch.build.targets.wheel] packages = ["src/commerce_ops"]`) and
put test doubles inside the import-linter root package. **Filling in the missing
`__init__.py` files** — rejected as unnecessary scope; it changes collection
semantics for 60 directories to solve a problem `pythonpath` solves in one line.

`tests/support/` is collected by nothing: `testpaths` in `pyproject.toml` names
the three tiers, as do every pre-commit hook and CI step. It is imported, never
run.

### 2. A spec-restating literal is shared as a literal, never as an import

`SPECIFIED_GATE_ORDER` is not a convenience constant. It is an independently
written statement of the specification, and 15 files assert production's
behaviour *against* it — `test_playbook_coherence_by_status.py:472` reads
`assert [gate.identifier for gate in playbook.gates] == list(SPECIFIED_GATE_ORDER)`.

There is an obvious-looking move here that must not be made:

```python
# WRONG — makes 15 assertions vacuous
from commerce_ops.launch.domain.launch_playbook import GATE_SEQUENCE
SPECIFIED_GATE_ORDER = GATE_SEQUENCE
```

That test would then assert that production equals itself. `tests/support/` holds
the **literal**, written out, with a docstring saying it is a restatement of the
specification and must be maintained by hand against it. Declaring it once
instead of 159 times changes nothing about its independence; sourcing it from
production destroys it.

The rule extends to `CONFIRMATION_GATES`, `FINAL_GATE`, `opening_for` and
`gates`, which together form one self-contained test-side restatement of the
gate specification. `tests/support/playbook.py` carries a module-level docstring
stating it, because the next reader's instinct will be to "fix" the duplication
with an import.

**The prohibition is on values, not on the module.** `gates()` constructs
`Gate(identifier=..., position=..., opening=...)`, so it must import the `Gate`
and `GateOpening` *types* from `launch_playbook` — there is no other way to
build the subject's own type, and doing so asserts nothing. What must never be
imported is any name carrying the sequence or its openings:

```
BANNED   GATE_SEQUENCE, gate_position, _SPECIFIED_GATES,
         _SPECIFIED_GATE_IDS, _GATE_POSITION, _FINAL_GATE
ALLOWED  Gate, GateOpening          — types, not statements about the spec
```

A blanket "no import from `launch_playbook`" was the first phrasing of task 2.1
and is unsatisfiable: it forbids the type the module exists to construct. The
distinction is the whole point — a test may use production's *types* freely and
must never take production's *answer* to the question it is asking.

### 3. Two populations, two procedures

The migration is not one procedure applied 319 times. It is two, and conflating
them is how an assertion gets weakened.

```
POPULATION A — verbatim clones (1 variant, or 1 dominant variant)
  SPECIFIED_GATE_ORDER  159 | _opening_for 120 | CONFIRMATION_GATES 128
  _gates 93 | _VOID_TAGS 38 | _fake_verify 45 | _SESSION_COOKIE/_VALUE 45
  the HTML helper cluster: _TreeParser/_Node/_Text/_tree/_elements/
  _texts/_all_text/_attribute_text/_classes/_carries/_element_hidden/
  _element_disabled/_inherited/_ancestors/_nearest/_size/_flat   (37 files)

  Procedure: delete the declaration, add an aliased import.
  Judgement required: none. Diff must not touch any test body.
  Measured floor: ~6,640 lines from 27 symbols.

POPULATION B — one shape, many default sets
  _step 135 | _hold 104 | _playbook 95 | _Member 47 | _FakeMembers 43
  _FakeMembersStore 38 | _FakeStepStore 37 | _FakeLaunches 32
  _FakePlaybooks 32 | _FakeSession 12 | _RecordingSlackApi 12

  Procedure: a canonical builder (Decisions 4-6), each file keeping a
  one-line partial where its local signature allows one, and a one-line
  wrapper where it does not.
  Judgement required: per file, on the deltas.
```

### 4. `step()` — a canonical default set, and a per-file `partial` for the deltas

The 121 `**overrides`-only `_step` declarations set the same 17 keys or a subset.
Measured across those 121 — not all 135, because the other 14 *require*
`identifier` rather than defaulting it, and counting them would misreport that
key — taking each key's modal value as canonical:

| key | of the 121, set by | distinct values | canonical default |
|---|---|---|---|
| `scope` | 121 | **1** | `Scope.PRODUCT` |
| `status` | 121 | **1** | `StepStatus.ACTIVE` |
| `hazard` | 121 | **1** | `Hazard.NONE` |
| `provenance` | 121 | **1** | `None` |
| `blocking` | 121 | 2 | `False` |
| `kind` | 121 | 2 | `StepKind.HUMAN` |
| `description` | 75 | 3 | `None` |
| `assignees` | 80 | 4 | `()` |
| `timing_anchor` | 121 | 5 | `OffsetAnchor(days=-7)` |
| `handler` | 79 | 5 | `None` |
| `gate` | 121 | 7 | `"listable"` |
| `discipline` | 121 | 11 | `any_discipline()` (task 4.3a) |
| `name` | 121 | 14 | `"Work this step asks for"` |
| `identifier` | 121 | 19 | `"listing.title-conforms"` |
| `confirmer` | 27 | 4 | omitted |
| `starts_at_gate`, `after_steps` | 2 | 1 | omitted |

Four keys are unanimous across all 121 and cost nothing to hoist. The three
partially-set keys that are canonicalised — `description`, `assignees`,
`handler` — each carry a value **identical to `StepDefinition`'s own dataclass
default** (`None`, `()`, `None`), which is what makes the next rule consistent
rather than merely convenient.
`metric_id` is absent from every default dict — it is only ever passed as an
override — and is correctly not in the canonical set.

A key the file does not set is **not** an override and is not added: the builder
omits it too, so `StepDefinition`'s own default still applies. Normalising an
omission into an explicit value changes what the test constructs.

Against this canonical set, the overrides each of the 121 would need:

```
  6 files pass 0 overrides   ██
 36 files pass 1             ████████████
 27 files pass 2             █████████
 17 files pass 3             ██████
  8 files pass 4             ███
 13 files pass 5             ████
  6 files pass 6             ██
  1 file  passes 7           ▌
  7 files pass 8             ██
                             cumulative: 69/121 need ≤2, 94/121 need ≤4
```

So the shared API is:

```python
# tests/support/steps.py
def step(**overrides: Any) -> StepDefinition: ...
```

**A `partial` where the local signature allows it; a one-line wrapper where it
does not.** This is the general rule, and it governs all three value builders:

```python
# the 121 — signature is **overrides-only, so a partial reproduces it exactly
_step = functools.partial(step, discipline=Discipline.STRATEGY, gate="commit")

# the 14 — the local signature takes `identifier` positionally, which a
# partial over `step(**overrides)` cannot accept
def _step(identifier: str, **o: Any) -> StepDefinition:
    return step(identifier=identifier, gate="commit", **o)
```

`functools.partial` gives exactly the right precedence — a keyword passed at the
call site overrides the partial's — so for the 121, **every existing `_step(...)`
call in every test body works unchanged**, and the migration is checkable by diff
shape. For the 14 the wrapper is one line and the call sites are likewise
unchanged; what is lost is only the diff-shape argument, so those 14 are read
individually. Two of them are among the largest files in the suite
(`test_launch_admin_detail.py`, `test_launch_surface_vocabulary_rules.py`).

*Alternative considered:* giving `step` an optional positional `identifier` so
one form serves both. Rejected — it makes the shared signature a compromise
between two local conventions, when Decision 4's whole argument for `**overrides`
is that it matches what 121 of the declarations already do. The compromise
belongs at the 14 call sites that need it.

*Alternative considered:* an explicit keyword-only signature naming all 17
parameters instead of `**overrides`. It would type-check the call sites, which
`**overrides: Any` does not. Rejected because matching the existing declarations
keeps the migration mechanical; a typed signature is a good follow-up once every
call site is on the shared builder, and is recorded as such rather than done
here.

### 5. `hold()` and `playbook()`, derived the same way

`_hold` is 104 declarations, each returning `_step(...)` with an override set.

**The denominator is every declaration, not the ones that pass the keyword.** A
keyword a `_hold` variant omits is not absent: the body calls `_step(...)`, so it
resolves to `step()`'s canonical value, and that value competes in the count.
Taking the modal value *among the passers* silently excludes the majority
candidate — which is exactly the error two earlier drafts of this table made, in
opposite directions, and which the corrected count reverses on five of the
fifteen keys. `step()`'s canonical set is the baseline here, the way
`StepDefinition`'s dataclass defaults are the baseline in Decision 4.

Counted over all 104, with an omission counted as the value it actually
produces:

| key | passes | inherits | effective winner | n | verdict |
|---|---|---|---|---|---|
| `blocking` | 89 | 15 | `True` | 89 | **default** |
| `identifier` | 86 | 18 | `f"hold.{gate}"` | 86 | **default** |
| `name` | 59 | 45 | `f"Blocking work holding the {gate} gate"` | 57 | **default** |
| `kind` | 75 | 29 | `StepKind.HUMAN` | 55 | inherit |
| `handler` | 74 | 30 | `None` | 51 | inherit |
| `assignees` | 37 | 67 | `()` | 79 | inherit |
| `timing_anchor` | 20 | 84 | `OffsetAnchor(days=-7)` | 87 | inherit |
| `status`, `provenance`, `hazard`, `description`, `scope` | 10–51 | 53–94 | step()'s value | **104** | inherit |
| `discipline` | 10 | 94 | `any_discipline()` | 94 | inherit |
| `confirmer` | 14 | 90 | `None` | 104 | inherit — it is `StepDefinition`'s own default, so passing it is a no-op |

So `hold()` carries **three** defaults beyond its `gate` parameter, and nothing
else:

```python
def hold(gate: str, **overrides: Any) -> StepDefinition:
    """A blocking filler step holding `gate`. Everything not named here
    inherits step()'s canonical value — see the table in design.md."""
```

with `blocking=True`, `identifier=f"hold.{gate}"` and
`name=f"Blocking work holding the {gate} gate"`.

Both `_hold` signatures — 89 `(gate)` and 15 `(gate, **overrides)` — are
reproduced by a partial, because `gate` stays positional in the shared builder.
All 104 migrate as `_hold = functools.partial(hold, **deltas)`.

This is a thinner `hold()` than a preference-led design would have produced, and
it arrives at thinness by measurement: the duplication genuinely worth hoisting
is 86 files spelling `f"hold.{gate}"` and 57 spelling one filler name, not a
filler's automation or its assignees, on which the corpus does not agree the way
it appeared to.

`_playbook` is 95 declarations: 40 `()`, 31 `(steps)`, 13 `(*steps)` and 11
one-offs. The dominant body takes some steps, fills every gate not already held
with a `hold()` filler, and builds `LaunchPlaybook(version=..., gates=..., steps=...)`.

| dimension | measured | canonical default |
|---|---|---|
| `version` | `"test-v1"` in 57 of 95; 6+ others | `"test-v1"` |
| held-set predicate includes `status is ACTIVE` | **10** of 95 | `held_must_be_active=False` |
| fills unheld gates at all | **69** of 95; 26 do not | `fill_unheld=True` |
| the filler it fills with | of those 69: **36 automated**, 33 human | **no default — see below** |
| `gates` | `_gates()` in 65, a parameter in 25, `specified_gates() if gates is None else gates` in 3, `specified_gates()` in 1, an inline `tuple(Gate(...))` in 1 — 95 | `gates()` from task 2.1 |

```python
def playbook(
    *steps: StepDefinition,
    version: str = "test-v1",
    gates: tuple[Gate, ...] | None = None,
    fill_unheld: bool = True,
    filler: Callable[[str], StepDefinition] = hold,
    held_must_be_active: bool = False,
) -> LaunchPlaybook: ...
```

**`filler` is a parameter because the corpus splits almost evenly on it.** Of the
69 variants that fill, 36 fill with an *automated* filler and 33 with a human
one — and `hold()`'s own table (above) shows why: 49 of 104 `_hold` declarations
pass `kind=AUTOMATED` and 41 pass `handler="fixture.holding_check"`, so their
`_playbook` fillers are automated. A single canonical filler would be wrong for
roughly half of them. `test_launch_playbook.py:141-167` is the worked case: its
`_hold` is automated, and its own docstring records that fillers are automated
"with a decided rule, so no other rule fires" — a statement about what that file
needs, not an incidental. A file passes its own `_hold` partial as `filler`.

`held_must_be_active` is a real semantic difference, not a formatting one — 10
variants compute the held set as `step.blocking and step.status is
StepStatus.ACTIVE` and 85 as `step.blocking` alone. It is a parameter precisely
so that migrating a file cannot silently move it from one predicate to the other.
**Normalising it would change what those tests exercise**, which Decision 7
forbids.

Signature handling follows Decision 4's rule. The 40 `()` and 13 `(*steps)`
migrate as partials. The **31 `(steps)`** take a positional *tuple*, which
`playbook(*steps, …)` cannot receive through a partial — they take the one-line
wrapper. The 11 one-offs are **not migrated** in this change and are recorded
under task 8.3.

### 6. Fakes are complete, and `mypy` is what checks it

The proposal's criterion — a double "fails at the seam rather than being absorbed
by a `getattr` in production code" — is not delivered by a `Protocol` existing.
`mypy` compares a class to a protocol only where a value is assigned to a
protocol-annotated target. So each fake carries one, beside it:

```python
# tests/support/members.py
class FakeMembers:
    async def list_members(self) -> tuple[Member, ...]: ...

_conforms: MembersReader = FakeMembers()   # mypy fails here if the fake drifts
```

`uv run mypy .` already runs strict over `tests/`, so the check costs one line
per fake and nothing at runtime. **This assignment, not the protocol's
existence, is what makes an incomplete double a type error.**

What "complete" means concretely is visible in the fake being replaced. The
dominant `_FakeMembers` variant is:

```python
class _FakeMembers:
    async def list_members(self) -> tuple[_Member, ...]: ...
    members = list_members                  # second spelling
    async def __call__(self): ...           # third spelling
```

Three spellings, because `clickup_sync._members:128-136` probes for three
shapes. The fake models the tolerance, so the tolerance can never be deleted —
the dependency running backwards, exactly as `docs/deferred-work.md` records it.
`tests/support/members.py` provides **one** method, `list_members()`, matching
the `MembersReader` protocol, and that is what makes
`unify-launch-adapter-dependencies` able to delete the probe.

The `LaunchProgressed` double models `crossed`, `awaiting_confirmation`,
`awaiting_gate`, `gate_id` and `current_gate` — every attribute
`gate_progression_job.py:256-279` probes for.

Protocols live in `tests/support/protocols.py` rather than in `src/`, because
`unify-launch-adapter-dependencies` owns the production-side protocols and two
definitions of the same boundary is the disagreement this change exists to end.
Each is added by the task that adds its fake, not up front — the shape is
established by reading the variants, so authoring the protocol first would be
guessing. A module docstring records that the successor change replaces them.

**Completeness carries the same-value invariant with it.** Modelling every
attribute a probe reads is only safe if the added spellings agree with the one
they displace — otherwise completeness silently redirects the probe, which is
risk 4 in Decision 7(b2). The invariant is stated there in full; it belongs
beside the `_conforms` rule because the two are one obligation: a fake models
its subject fully **and** its added spellings carry the displaced value.

**Builders return fresh instances.** No module-level singleton, no shared mutable
default. A builder that hands two tests the same list produces order-dependent
failures, which is a worse defect than the one being fixed.

### 7. The stopping rule: AST-identical assertions, plus a per-file equivalence proof

`proposal.md` states it in prose — "unchanged in what they assert and shorter in
how they arrange it." Making that enforceable takes two checks, because there are
two ways to break it.

**(a) The assertions themselves must not change.** Compared as syntax trees, not
as lines:

> For every migrated file, collect **four** node kinds and compare
> `ast.unparse` of each whole node before and after; the multiset must be
> identical, and the count of `def test_` / `async def test_` unchanged:
>
> 1. every `ast.Assert` node — **6,623**;
> 2. every `pytest.raises` `With` item — **238**;
> 3. every `ast.Expr` wrapping an `ast.Call` whose callee tail starts `assert`
>    or is `fail` — **757**;
> 4. every `@pytest.mark.parametrize` decorator — **172**.

A line-level regex was the first design and is not sufficient: **2,632 of the
6,623 `ast.Assert` nodes span more than one line**, so their expected values sit
on lines a `^\s*assert\b` pattern never reads.

**Kinds 3 and 4 are why the node set is four kinds and not one.** An earlier
draft specified only kinds 1 and 2 while claiming an AST comparison "has neither
hole" — and it does not, because a helper-style assertion (`assert_called_with`,
`_assert_unchanged`, `pytest.fail`) is an `ast.Expr` wrapping a `Call`, not an
`ast.Assert`, so all 757 of them were excluded by the very node set that was
meant to catch them. Kind 4 closes a hole neither design had noticed: a
`@parametrize` table is where a large share of expected values live, and
changing a value in one — as opposed to the number of cases — is invisible to
kinds 1–3 *and* to the collected-count check. Population A's stronger rule
covers this; Population B's per-file judgement does not, which is exactly where
it would bite.

**What this check cannot see, by construction: the *value* an assertion compares
against.** `assert x == CONFIRMATION_GATES` unparses identically whether that
name holds the file's old literal or a different shared one — and the
declaration sits *before* the first test, inside the very preamble this change
rewrites, so Population A's stronger rule does not reach it either. Decision 2's
prohibition is one instance of this class, not the whole of it.

The verbatim symbols are safe by measurement (`SPECIFIED_GATE_ORDER` 159 copies
and 1 variant; `_opening_for` 120 and 1). The exposure is the **multi-variant**
symbols the tasks permit migrating: `_gates` (6 variants, 83 dominant) and
`_TreeParser` (8 variants).

So the check is closed per *symbol*, not per file — 27 symbols rather than 300
files. The scratchpad checker evaluates each deleted local declaration and the
shared one and asserts equality. That subsumes Decision 2's grep as a special
case and closes the class instead of the instance; the grep stays anyway,
because it is one line and it fails with a clearer message.

For **Population A** the rule is stronger and simpler: no line at or after the
file's first test may change at all. Where a Population A symbol is declared
*below* the first test — so that removing it necessarily edits that region — the
file is **not** migrated under the A rule; it is recorded and left to the
Population B procedure. The A rule is never relaxed to fit a file.

**(b) The arrangement must not change either.** This is the check that matters,
and no assertion comparison can supply it: a builder default that differs from a
file's local variant in a field no assertion mentions leaves every assertion
identical, the count unchanged, and the suite green — while the test now
exercises something else. Across 121 `_step` sites over as many default sets,
this is the likely failure, not a hypothetical one.

**Population B is not one population for this purpose.** The proof works by value
equality, and **the minority of Population B has values**:

```
VALUE BUILDERS — step 135, hold 104, playbook 95     334 declarations
  StepDefinition and LaunchPlaybook are both
  @dataclass(frozen=True, slots=True), no field
  compare=False, __post_init__ normalising both
  sides alike.  `==` is structural.  Proof (b1) applies.

FAKES — Member 47, FakeMembers 43, FakeMembersStore 38,
  FakeStepStore 37, FakeLaunches 32, FakePlaybooks 32,
  FakeLaunchStore 26, FakeMapping 19, TaskMapping 19,
  FakeClickUp 15, FakeTask 15, CreatedTask 14,
  FakeSlackResponse 13, FakeSession 12,
  FakeHandlerRegistry 12, RecordingSlackApi 12,
  CatalogProduct 40, FakeCatalog 29                  455 declarations
  Plain classes.  `==` is identity, so
  `local() == shared()` is false or meaningless.
  Proof (b1) is inexpressible.  (b2) applies instead.
```

**455 against 334.** An earlier draft put the fakes at "~250" and glossed the
split as "only half of Population B has values", which reads as though the
strong proof carries the bulk. It carries the minority — 42% of Population B by
declaration, against 58% under the weaker substitute. The residual risks below
are therefore scoped to the *majority* of Population B, not a remainder.

**(b1) — the value builders.** Each file is migrated in two commits. In the
first, add the shared builder and the partial or wrapper **without deleting the
local variant**, and redefine the local name as a checking wrapper:

```python
def _step(**o: Any) -> StepDefinition:
    expected = _step_local(**o)
    actual = _step_shared(**o)
    assert expected == actual
    return actual
```

then run the file's tests. Instrumenting rather than enumerating call sites
matters three times over: every *executed* call is proved, including ones whose
kwargs come from a parametrised table or a loop that a static reading would
miss; a call arriving through a file-local second-layer helper — one that builds
its own dict and calls `_step(**attributes)`, as at
`test_metric_step_gate_obligations.py:249` — is intercepted like any other,
because the wrapper redefines the *name* rather than patching call sites; and no
test function is added, so the collected count does not move. The second commit
deletes the wrapper together with the local variant.

**7(a) is evaluated across the commit *pair*, not per commit.** The wrapper
contains `assert expected == actual`, which is an `ast.Assert` — so 7(a) run
against the intermediate commit fails by construction on all 334 value-builder
migrations. The two checks contradict each other unless the boundary is stated,
and it is: for a two-commit Population B migration, 7(a) compares the commit
*before* the pair with the commit *after* it. The collected-count check still
runs on each commit individually, because the wrapper does not move it.

**(b2) — the fakes.** There is no equality to assert, so the substitute is
stated rather than computed, and it is weaker. Being precise about *where* it is
weaker is the point; "weaker" on its own is not a statement anyone can act on.

**Four** risks survive the move from a local fake to a shared one, and they are
not the same risk:

1. **The shared fake models less than its subject.** Caught by the
   `_conforms: SomeProtocol = TheFake()` assignment of Decision 6 — `mypy` fails.

2. **The shared fake drops a spelling something calls.** Caught by a
   **surface-and-behaviour note** (below) plus a search — but the search must
   cover **production, not only tests**, and the reason is specific. The
   soundness argument for this risk used to be "a caller of a removed attribute
   raises `AttributeError` rather than passing quietly." **That holds for direct
   attribute access and fails for a `getattr` shape probe**, which falls through
   to the next branch or a default and raises nothing. The worked example below
   is exactly a probe: the spellings `FakeMembers` drops exist *only* to satisfy
   `clickup_sync._members`'s three `getattr` branches, so the thing reaching for
   them is production, and it will not raise. Scoping the search to "no test
   reaches for either" would look for the caller in the wrong codebase.

3. **The shared fake keeps the whole surface and behaves differently behind it**
   — a different return ordering, a different response to an absent or unknown
   key, a different initial state. `mypy` passes, no spelling is missing, the
   AST check passes, the suite is green, and the test now exercises a different
   path. **No check in this change detects this.** Carried deliberately;
   principal across the stateful fakes — `FakeMembersStore` (38),
   `FakeStepStore` (37), `FakeLaunches` (32), `FakePlaybooks` (32),
   `FakeSession` (12).

4. **The shared fake models *more* than the local variant, and the added surface
   redirects a production shape probe.** This one is not incidental drift like
   risk 3 — **Decision 6 guarantees it**, for exactly the doubles that sit
   opposite the five tolerances, and it is the mechanism this change's whole
   thesis turns on.

   Production probes by shape at five sites. `gate_progression_job._awaiting_gate`
   is the clearest: it returns the **first** of
   `("awaiting_gate", "gate_id", "current_gate")` that is a non-empty string.
   Measured across `tests/` — file counts of `*.py`, not grep hits, which
   double through `__pycache__` — the local doubles model those attributes very
   unevenly: `current_gate` in **55** files, `gate_id` in **26**,
   `awaiting_gate` in **5**, `awaiting_confirmation` in **11**. So today almost
   every double falls through to `current_gate`. Decision 6 requires the shared
   `LaunchProgressed` double to model all five attributes, so it would match on
   `awaiting_gate` instead — **returning a different gate**. (An identifier
   count is an upper bound on "a double models it", so the affected population
   is at most 55 and in truth smaller.)

   `mypy` passes: the fake models *more*, not less. No spelling is dropped, so
   risk 2's search finds nothing. 7(a) passes. The suite may well stay green
   while those tests exercise a different branch than they did.

   ***Mitigation: make the branch indifferent, do not analyse it.*** The three
   names are three spellings of **one value**, not three data.
   `_awaiting_gate` runs only under `if not getattr(progressed,
   "awaiting_confirmation", False): return None`, and under that guard the gate
   awaited and the current gate are the same gate; `docs/deferred-work.md:1076`
   records the probe as reading those three names "for one value", and
   production's own comment agrees. So which branch fires need not be
   *established* per file — it must be made not to matter:

   > **Same-value invariant.** Where a shared double adds a spelling a
   > production probe reads *earlier* in its branch order than the spelling the
   > local variants populated, the added spelling carries the same value as the
   > one it displaces. An added attribute the probe reads as a guard or as a
   > sequence defaults to the value the fall-through produced.

   For `LaunchProgressed`: `awaiting_gate` and `gate_id` derive from the same
   argument as `current_gate` unless a test sets them apart; `crossed` defaults
   `()`, because `getattr(progressed, "crossed", None) or ()` produced `()` when
   absent; `awaiting_confirmation` defaults `False`, because `getattr(...,
   False)` did. Every branch then returns the same string and `_crossed` the
   same tuple, for all 55 files, **without reading any of them**. It generalises
   to the other four sites: `FakeMembers.list_members()` returns what
   `tuple(members)` returned for a plain-iterable local, and `Member.identifier`
   carries the string a local `id` or `member_id` carried, so
   `clickup_sync._member_identifier:139` and
   `playbook_authoring.member_identifier:266` are indifferent too.

   The invariant also closes a case per-file branch analysis would not have
   asked about: a double defaulting `awaiting_confirmation` to `True` where the
   locals omitted it flips the *guard*, taking `_awaiting_gate` from returning
   `None` in every such file to returning a gate.

   *Alternatives.* Scoping the double's completeness down to what each local
   modelled satisfies every test but forfeits the tolerance deletion, which is
   this change's stated warrant — rejected. Establishing the branch per file
   preserves the warrant but costs `src/`-reading judgement on up to 55 files in
   the one task that reads production, and misses the guard case — rejected. The
   invariant is checked once per builder, keeps Decision 6 whole, and
   *strengthens* the thesis, since "these probes read one value under several
   names" is precisely the premise `unify-launch-adapter-dependencies` needs in
   order to delete them.

   The surface-and-behaviour note still records any genuine superset, because a
   double that adds an attribute *no* probe reads is a different matter from one
   that displaces a spelling.

The **surface-and-behaviour note** is what stands in for (b1) here. Per fake, in
the task's own notes, the migrator records:

- every attribute or method the local variants offered that the shared one does
  not, with a search **across `tests/` and `src/`** confirming nothing calls it
  — production is where the probes live (risk 2);
- every attribute the shared fake **adds** over the dominant local variant, with
  the production probe sites that read it and the branch each population takes
  before and after (risk 4);
- for every method the shared fake *keeps*: its return shape, its error
  behaviour on an absent or unknown key, and its initial state — each stated as
  "same as the dominant local variant" or named as a difference (risk 3).

That is judgement rather than proof, but it is judgement that leaves a trace a
reviewer can read, which is what Goal 3 asks for. A behavioural harness running
each file's tests against both fakes was considered and rejected: it costs
roughly a second run of the suite for a signal no finer than "still green".

`FakeMembers` is the worked example, and it is a **licensed** arrangement change
rather than an exception smuggled past the rule. The local fake carries
`list_members()`, `members = list_members` (in 34 files) and `async def
__call__`; the shared one carries `list_members()` alone. That is deliberate —
the three spellings exist only to satisfy `clickup_sync._members`'s three
branches, and reproducing them would preserve the very tolerance this change
exists to make deletable. Its note therefore records both halves: the two
dropped spellings, *and* that `list_members()` itself returns the same shape in
the same order as the dominant local variant.

Where a variant cannot be reproduced by the builder, the file is **left
unmigrated and recorded** (task 8.3) — never forced, and never migrated with the
applicable proof skipped.

Both checks run from a throwaway script in the scratchpad, not a committed tool:
they have no life after the change lands, and shipping them would be scope this
change does not own.

### 8. A per-module constant does not become a shared constant

There is a third population, and it is the one most likely to be migrated
wrongly. These have a dominant variant and a few deliberate outliers:

| symbol | copies | variants | dominant form |
|---|---|---|---|
| `PRODUCT_ID` | 76 | 7 | `Final = ProductId(str(uuid.uuid4()))` |
| `LAUNCH_DATE` | 95 | 11 | `Final = date(2027, 3, 2)` |
| `PRINCIPAL` | 72 | 3 | `Final = "helen"` |
| `ALICE` | 56 | 2 | `Final = "prs_01HQ8Z6M4A"` |
| `MARKETPLACE` | 45 | 3 | `Final = MarketplaceId("ATVPDKIKX0DER")` |
| `PRODUCT_NAME` | 47 | 3 | `Final = "Bamboo Cutting Board"` |

`LAUNCH_DATE`, `PRINCIPAL`, `ALICE`, `MARKETPLACE` and `PRODUCT_NAME` are fixed
literals: 47 files spelling `"Bamboo Cutting Board"` is 47 copies of one value,
and hoisting it changes nothing.

**`PRODUCT_ID` is not.** `ProductId(str(uuid.uuid4()))` evaluated at module level
in 68 files produces **68 distinct identifiers**. Hoisting it to one module-level
constant in `tests/support/` produces **one**, shared by every test in the
session — and any test that writes a product to a shared store would then collide
with every other, or worse, pass because a fixture it never set up was left
behind by a neighbour. It migrates as a **factory**, and only the construction
moves:

```python
# tests/support/fixtures.py
def product_id() -> ProductId: ...

# in the migrated file — module-level, one per module, exactly as today
PRODUCT_ID: Final = product_id()
```

The reviewer of each batch checks that no `uuid`, `datetime.now` or counter has
been frozen into a module-level name in `tests/support/`.

The outliers stay where they are. A file whose `LAUNCH_DATE` differs from the
dominant one differs on purpose until shown otherwise; it keeps its local
declaration and is recorded, not normalised.

### 9. Population A migrations preserve test bodies exactly, via aliased imports

A Population A file loses its declaration and gains:

```python
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.html import tree as _tree, elements as _elements
```

The shared modules export public names (`tree`, not `_tree`), because a
module-private name imported across modules is a contradiction; the alias at the
call site preserves the existing local spelling so no test body changes.

Ruff's isort rules are not configured in this repository — no `select` is set —
so the ~300 new first-party imports cannot trigger the `I001` classification
churn `docs/deferred-work.md` records as having cost a commit two attempts.

*Alternative considered:* renaming call sites to the public name. Rejected for
Population A — it converts a mechanically checkable diff into a reviewed one, at
159-file scale, for a cosmetic gain. New tests use the public names.

### 10. `_DrainsDeferredListeners` is hoisted to `tests/support/slack.py`

`tests/unit/launch/infrastructure/driving/conftest.py` opens by declaring itself
a mirror of `tests/unit/omni_agent/infrastructure/driving/conftest.py` "exactly,
for the same reason recorded there," and defers the full argument to the other
file's docstring. Two conftests, one wrapper, one explanation living in one of
them. The wrapper moves to `tests/support/slack.py` with the omni_agent
docstring's argument; both conftests keep a thin `slack_asgi_app` fixture that
calls it.

`tests/conftest.py` and `tests/integration/conftest.py` are untouched — the
first is the zero-skip guard, the second is database resolution. Neither is
arrangement.

### 11. One change, two phases, Phase A independently mergeable

Population A alone removes a measured ~6,640 lines with no judgement calls. It is
kept in this change rather than split out because the scarce resource is the
conflict window (`proposal.md` — Ordering), and because Decision 4's measurement
turned Phase B from eleven undesigned APIs into three designed ones plus a set of
fakes whose shape is dictated by protocols — a much smaller planning surface than
it appeared before the variants were read.

The phases are kept as separate commits so that if Phase B stalls, Phase A is
already a coherent, independently mergeable unit and the change can be cut there
rather than abandoned. `tasks.md` groups accordingly, with the checkpoint after
the last Phase A task.

*Alternative considered:* two OpenSpec changes, Phase B proposed separately once
Phase A merges. It buys a dedicated plan review for the builder APIs; carrying
those designs here (Decisions 4–6) buys the same thing for one review round
instead of a change cycle, which is the trade taken. It remains the fallback if
Phase B's migrations turn into their own loop.

## Risks / Trade-offs

**A migration weakens a test and the suite still passes** → Decision 7's two
checks. (a) catches a changed assertion, (b) catches an unchanged assertion over
changed arrangement, which is the failure that would make this change
net-negative and which (a) alone cannot see.

**Conflict with work started while this is in flight** → the whole reason the
change was queued last. Mitigated by working it now, while nothing else is
started (`proposal.md` — Ordering), and by ordering Population A first so the
highest-conflict, lowest-judgement edits land soonest. Not eliminated: anything
that starts mid-flight will conflict, and rebasing 300 files is unpleasant.

**A shared builder grows into a god-object** → one module per subject
(`playbook.py`, `steps.py`, `launches.py`, `members.py`, `clickup.py`,
`slack.py`, `html.py`, `catalog.py`, `fixtures.py`), and a builder needing more
than the measured override count is a signal the cluster was drawn wrong.
Reviewed per builder, not at the end.

**`**overrides: Any` type-checks nothing at the call site** → accepted for this
change (Decision 4), because it is what 121 of the existing declarations already do
and matching them is what keeps the migration mechanical. Recorded as a
follow-up, not silently carried.

**`pythonpath = ["."]` changes import resolution for the whole suite** → it adds
a root that `prepend` mode already inserts today. Task 1.3 commits it alone, with
the baseline re-measured, so any effect is observed in isolation rather than
blamed on a migration.

**Population B does not converge** → Phase A is the floor and is independently
mergeable (Decision 11). The stopping rule for B is per-file: a file whose
variant the builder cannot reproduce is left alone and recorded.

**The change lands and new tests keep writing bespoke fakes** → the `AGENTS.md`
rule is part of this change, not a follow-up. It is the only durable part; the
deduplication is a one-time payment and the rule is what stops it accruing again.

## Migration Plan

Not a deployment. Nothing reaches the server: no `src/`, no schema, no CI
configuration. The rollback for any commit is `git revert`, and the verification
is the existing gate — `ruff check`, `ruff format --check`, `mypy`,
`lint-imports`, and the `tests/unit` + `tests/agents` tier at commit time,
`tests/integration` at pre-push — all green *before and after* every migration
commit, with the collected test count unchanged.

`openspec/specs/deploy-pipeline/spec.md:8` requires the validation job to run
those checks over the three tiers. `tests/support/` is a fourth directory under
`tests/` that is not a tier and is collected by nothing, so that requirement
stays satisfied; it is named here because it is the only recorded specification
that mentions anything this change touches.

Per `AGENTS.md`, this plan is committed before tests are derived from it — and
this change derives none: it declares no specification deltas
(`skip_specs: true`), so the stated exemption applies, and what it owes instead
is that the existing suite stays green with an unchanged test count and unchanged
assertions. That is the acceptance criterion, and Decision 7 is how it is
checked.

## Open Questions

- **Whether `tests/support/` should carry its own tests — settled, not
  deferred, and the answer differs by half.**

  For `step`, `hold` and `playbook` it is moot: 7(b1) exercises each against the
  variant it replaces at every executed call site, which is stronger coverage
  than a hand-written builder test would give.

  For the **fakes** it is not moot, and an earlier draft deferred it wrongly.
  They are the *majority* of Population B (455 declarations against 334), they
  get no equivalence coverage at all, and risks 3 and 4 are both precisely
  builder bugs. So the five stateful fakes — `FakeMembersStore` (38),
  `FakeStepStore` (37), `FakeLaunches` (32), `FakePlaybooks` (32) and
  `FakeSession` (12) — carry direct behaviour tests pinning return ordering,
  absent-key behaviour and initial state (task 6.15).

  These do not close risk 3: they pin the shared fake's behaviour without
  comparing it to the local variant. What they do is make half of the
  surface-and-behaviour note **executable** rather than merely asserted, which
  is the most that is available where `==` is identity.

  They live in **`tests/unit/support/`**, which is collected, not in
  `tests/support/`, which is not. That directory names no bounded context and so
  fits none of `AGENTS.md`'s `tests/unit/<module>/<layer>/` rules; task 7.1
  records the departure in the same edit that adds the other rules, so the next
  reader does not find a tier directory answering to nothing.

  **Writing these does not conflict with the specs-exempt routing.** `AGENTS.md`
  says a change carrying no deltas *owes* no new tests — not that it may not
  write any. These derive from the fakes' own behaviour rather than from
  specification deltas, so no independent test author is owed for them either;
  the exemption is about what the change is held to, and it is unchanged.
