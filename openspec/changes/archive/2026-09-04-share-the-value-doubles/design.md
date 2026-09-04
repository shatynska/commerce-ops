## Context

`share-the-unit-test-harness` (archived 2026-09-04) shipped `tests/support/`
with the playbook constants, the HTML harness, the admin session, the fixture
literals and the `step()` builder — 200 of 319 test files now import from it —
and cut the shared test doubles to a follow-up. `tests/support/protocols.py`
ships today as 41 lines of docstring with no protocol and no importer: it is the
placeholder that change left for this one, and it already states the two rules
the first double is held to (`_conforms` typing, and the same-value invariant).

`docs/proposed-change-order.md` §4 frames the follow-up as one change over 455
declarations. `proposal.md` records why it is two, and this document settles the
four questions the parent change's implementation said had to be settled before
any code: composition, what replaces the equality proof, where the migration
boundary falls, and whether behaviour tests come first.

Measurements below were taken against `main` at `713e9da` on 2026-09-04, by AST
over `tests/**/*.py` excluding `__pycache__`. Counts are of module-level class
declarations unless stated otherwise.

**By AST, and not by grep, deliberately.** `^class _Record:` matches 31 files;
there are 30 declarations. The 31st is at
`test_startup_handler_report_holds_the_registry.py:259`, inside
`_REPORT_DRIVER_SCRIPT: Final = '''...'''` (lines 214–318) — a driver script
this test writes out and runs in a subprocess. It is source text, not a
declaration in that module, and every text-based sweep counts it. The same
discipline is what produced the ten-probe measurement in `proposal.md` where
every previous, spelling-based sweep of the same ground found between two and
five. Where this document states a count, it was taken structurally; where a
task re-measures one, it re-measures structurally.

## Goals / Non-Goals

**Goals.**

1. One shared declaration per value double, so the next test arranges from
   `tests/support/` rather than writing a forty-eighth `_Member`.
2. Every migrated file asserts exactly what it asserts today — verified, not
   asserted.
3. Every double that sits opposite production's member-identifier probe — all
   **52** of them, `_Member` 47 and `_FakeMember` 5 — exposes production's own
   spelling, so `unify-launch-adapter-dependencies` can delete the probe at all
   **six** sites rather than inheriting the reason it exists. Scoped by shape,
   not by name frequency: `_FakeMember` is five declarations and would fall
   below any frequency threshold, and three of the five sit directly opposite
   `playbook_admin.py:321`.
4. The base of the composition chain lands before the composers, so
   `share-the-stateful-fakes` inherits a foundation rather than the parent
   change's `_hold` problem.

**Non-Goals.**

- Deleting any production tolerance. That is
  `unify-launch-adapter-dependencies`. This change makes deletion safe and says
  so; it does not touch `src/`.
- The 799 doubles with behaviour. Second slice.
- The long tail. A name declared fewer than eight times is not in scope, and a
  file whose variant the shared type cannot reproduce keeps its own — recorded,
  never forced.
- Replacing a double with production's real type. Using
  `access.domain.members.Member` directly would be better than any double, but
  it is `@dataclass(frozen=True, slots=True)` with a validating `__post_init__`
  that rejects an empty `slack_identity`, and 42 of the 52 local variants never
  supply one. Adopting it would edit test bodies at every construction site,
  which Decision 3 forbids. Recorded as the right end state, owned by
  `unify-launch-adapter-dependencies`.

## Decisions

### 1. The local name is rebound to the shared class by an aliased import

The parent change replaced a local *function* (`_step`) with a shared function,
and where a file carried deltas it declared a two-line local wrapper. That
substitution is unavailable here, and the measurement is unambiguous:

| name | files declaring it | files using it in an annotation |
|---|---|---|
| `_Member` | 47 | **47** |
| `_TaskMapping` | 19 | **19** |
| `_FakeTask` | 15 | **15** |
| `_CreatedTask` | 14 | **14** |
| `_PendingRow` | 16 | 15 |
| `_Record` | 30 | 29 |
| `_CatalogProduct` | 40 | 28 |

A `functools.partial` or a wrapper function cannot stand in an annotation, so
every one of these files would fail `mypy` under the parent change's shape. What
works instead is simpler and strictly stronger:

```python
from tests.support.values import Member as _Member
```

One line. Every annotation, every `isinstance` check and every
`tuple[_Member, ...]` return type is byte-identical afterwards, and so is every
construction site **that the boundary rule admits**. The class body — five to
eleven lines — is all that is deleted.

That qualification is load-bearing, and it was measured rather than assumed. Ten
files construct `_Member(id=ALICE, display_name=..., slack_identity=...)` — the
identifier passed as a *keyword*, not positionally — and one of them passes
`slack_identity=None`. A shared type that renamed the field would break all ten
at the call site, which this decision forbids. Those ten turn out to be
**exactly** the ten that declare `_Member` as a `@dataclass`; the two sets are
identical, verified by AST. So the keyword problem, the equality-semantics
problem and the declaration-form problem are one problem with one boundary,
which is why Decision 3 carries a form clause and Decision 5 ships two types
rather than one.

**Consequence: the parent change's strong rule applies to the whole
population.** Its Population A rule was "no line at or after the file's first
test may change at all", and it applied only to a sub-population because the
builder substitution edited call sites elsewhere. Here nothing below the
preamble changes for any of the seven names. A file where something below the
first test *would* have to change is, by that fact, not migrated.

`ruff`'s `I001` is enforced with `combine_as_imports = false`, so an aliased
import gets its own `from` line and must not be merged with a neighbour —
`ruff check --fix` splits it straight back.

### 2. The equivalence proof is expressible for this population, as field comparison

The parent change's stopping rule was an equivalence proof (`design.md` Decision
7(b1)): keep the local declaration, add the shared one, assert on every executed
call that the two build equal objects, and delete only after that passes. It
records five real defects found during that migration, **every one of which left
the assertions textually identical and the suite green**. The archive attributes
them unevenly, and the attribution matters here, because only some are evidence
for the check being carried forward:

| defect | what caught it |
|---|---|
| a helper building a dict then splatting it, so the call carried no keywords | **the proof** (parent `tasks.md` 6.6) |
| 45 files never passing a field, inheriting the builder's default rather than the intended one | **the proof** (parent `tasks.md` 6.6) |
| a constant computed in most files but pinned in five | a measurement made while migrating (parent `tasks.md` 4.3a) |
| a drift defeated by an `all(isinstance(...))` check over a dict with a `None` key | not separately recorded in the archive |
| shared leaf helpers handed local leaf instances matching nothing under `isinstance` | **`mypy`** (parent `tasks.md` 3.3), not the proof |

Two to the proof, one to `mypy`, the rest to measurement. That is a weaker
warrant than "five", and it is still sufficient: two defects that no other check
in that change would have caught is two more than a green suite reports. It is
also why Decision 7's `_conforms` typing is not an afterthought here — `mypy`
carries its own share.

The parent change concluded the proof does not transfer to doubles, because
`FakeStepStore() == FakeStepStore()` is identity. **That conclusion is correct
for doubles with behaviour and wrong for this population.** A double with no
behaviour is a value wearing a class, and the proof is the same proof written
against fields instead of against `==`.

Cross-class `==` returns `NotImplemented` even between two dataclasses, so the
operator is unavailable regardless of shape; the comparison is therefore on the
field mapping:

```python
def _fields(obj: object) -> dict[str, object]:
    if is_dataclass(obj):
        return {f.name: getattr(obj, f.name) for f in fields(obj)}
    return dict(vars(obj))
```

Shallow, deliberately. `dataclasses.asdict` recurses, and `_Record` holds a
production `StepDefinition`; recursing into it compares production against
itself, which Decision 2 of the parent change forbids in spirit and which buys
nothing — two references to the same object are equal by identity already.

**The comparison is over the intersection of the two field sets, and the
symmetric difference is recorded, not compared.** The intersection is what the
file exercises. The difference is either a field the shared type adds — which
Decision 5 governs — or a field the local carried that the shared one drops,
which is a reason not to migrate unless a search across `tests/` **and** `src/`
shows nothing reads it. Production is where the shape probes live, so scoping
that search to `tests/` would look for the caller in the wrong codebase.

**Instrument, then settle**, two commits per name:

- *Instrument.* Add the shared class. Keep the local class, and give it a
  `__post_init__` (dataclass) or a tail to `__init__` (plain class) that builds
  the shared class from the same arguments and asserts `_fields` equality over
  the intersection, failing with both mappings named. Run the full commit tier.
  Every construction the suite actually performs is now checked.
- *Settle.* Delete the local class, add the aliased import.

The instrument commit is thrown away by the settle commit; neither ships a
checker. Both run from the change's own branch, and the assertion text is
recorded in the task, not in the tree.

**What this does not catch, stated plainly.** Three things.

1. A field neither side declares cannot be compared.
2. A construction the suite never performs is never checked — a default wrong
   only on an unexercised path stays wrong and stays invisible. This is the same
   residual the parent change carried, and it is smaller here, because this
   population has no behaviour behind which a difference can hide.
3. **The type's own semantics.** Field comparison reads *values*; it is silent
   on `__eq__`, `__hash__`, `__repr__` and frozen-ness. Two types can agree on
   every field and disagree on whether they are equal, hashable, or render as
   `<... object at 0x...>`. Nothing in this proof would notice, and the corpus
   contains real instances of all three. That gap is closed by rule rather than
   by check — Decision 3's clause (b) — and it is stated here so the proof is
   not mistaken for covering it.

### 3. The migration boundary, stated before the first file

The parent change reached its boundary by inference and landed on an exact
whole-body match, which is why `_playbook` took 13 of 95 against 56 distinct
bodies. Applied here that rule would take 24 of 40 `_CatalogProduct` and 12 of
19 `_TaskMapping` — and it would be wrong, because those variants are *nested*,
not divergent:

```
_TaskMapping, 19 declarations, 2 bodies:
  12 ×  product_id, step_id, task_id, last_observed_closed=False,
        retained_name=None, retained_body=None, retained_assignees=None
   7 ×  product_id, step_id, task_id, last_observed_closed=False
```

The second is a strict prefix of the first. There is no whole-body match and
there is no disagreement either. So the rule is:

> **A local declaration is migrated when (a) its field set is a subset of the
> shared type's, and for every field it does not declare the shared type's
> default equals the value that field's absence produced at every site the file
> exercises; (b) the shared type's declaration form matches the local's —
> dataclass-ness, `frozen`, `eq`, and any `__repr__` the file relies on; and
> (c) the shared type's `__init__` accepts every one of the local's call sites
> unchanged, in parameter name, position and optionality.** Otherwise the file
> keeps its own declaration and the reason is recorded — **except** where
> clause (c) alone fails, which is remediable by a three-line adapter subclass
> over the shared type.

The exception is scoped to clause (c) deliberately. A clause-(a) failure is a
value difference and an adapter would only relocate it; a clause-(b) failure is
not remediable by subclassing at all, since a subclass cannot restore the plain
`__repr__` that two files document as load-bearing. Only a constructor mismatch
is a difference in how the object is *reached* rather than in what it is.

Three things follow from clause (a).

- The rule is checkable per *declaration*, not per body, so nesting costs
  nothing.
- The second clause is exactly what the Decision 2 proof asserts, so the
  boundary and the verification are one statement rather than two that can drift
  apart.
- "The value that field's absence produced" is a real value, not a hypothetical:
  for a field production reads through `getattr(x, name, default)`, absence
  produced `default`; for a field nothing reads, absence produced nothing and
  any default is admissible.

**Clause (b) exists because clause (a) cannot see it**, and the corpus makes it
concrete rather than theoretical:

| local name | plain | `@dataclass` | `frozen=True` |
|---|---|---|---|
| `_Member` | 37 | 10 | 0 |
| `_FakeMember` | 5 | 0 | 0 |
| `_CatalogProduct` | 7 | 33 | 33 |
| `_Record` | 30 | 0 | 0 |
| `_PendingRow` | 3 | 13 | 0 |
| `_TaskMapping` | 0 | 19 | 0 |
| `_FakeTask` | 0 | 15 | 0 |
| `_CreatedTask` | 0 | 14 | 14 |

Three consequences, each of which would otherwise have been a silent behaviour
change with every check green:

- **`__eq__`.** A plain local compares by identity; a `@dataclass` local
  compares by field. Migrating the 37 plain `_Member`s onto a dataclass would
  give them structural equality they never had.
- **`__hash__`.** A non-frozen dataclass sets `__hash__ = None`. Migrating a
  plain local onto one turns any set membership or dict key into a `TypeError`
  — loud, so not dangerous, but it invalidates a per-name expectation rather
  than costing a rerun.
- **`__repr__`.** `test_compliance_screen_failure_and_context.py:314` and
  `test_compliance_screen_verdict_routing.py:399` each state in the docstring
  that their `_CatalogProduct` is a plain class *because*
  `catalog.domain.product.Product` is one, so `!r` leaks
  `<... object at 0x...>` "exactly as it would in production". A shared
  dataclass renders fields instead, and the test would stop exercising what it
  says it exercises. Clause (a) alone would have excluded these two on field
  breadth — by luck, not by rule.

So each shared type declares one form, `tasks.md` states which, and locals of
the other form keep their own declaration. Where a name carries a substantial
population in both forms, it gets **two** shared types rather than one bent to
cover both; `Member` is the only such name, at 42 plain against 10 dataclass.

**Clause (c) exists because a field set is not a signature**, and the corpus
holds one declaration that proves it. `test_product_dossier_page.py:721`:

```python
class _Member:
    def __init__(self, display_name: str, *, active: bool = True) -> None:
        self.id = "prs_01HQ8Z6M4A"  # pinned, not a parameter
        self.display_name = display_name
```

Its field set is a strict subset of the shared type's and its form is plain, so
clauses (a) and (b) both admit it — and its two call sites,
`_Member(ALICE_RENAMED)` at line 1350 and `_Member(ALICE, active=False)` at
1378, pass the *display name* in the position the shared type reads as the
identifier. Aliasing the
shared class there is a `TypeError` at collection.

**The remedy is an adapter, not an exclusion.** Goal 3 needs the `identifier`
spelling to reach the probe from *every* member double; excluding this file
would leave whichever probe its members reach still needing its `id` branch, for
the sake of three lines. So the file keeps:

```python
class _Member(Member):
    def __init__(self, display_name: str, *, active: bool = True) -> None:
        super().__init__("prs_01HQ8Z6M4A", display_name, active=active)
```

The identifier is inlined, matching the local's own hard-coded literal at line
723. **Do not reach for `tests.support.fixtures.ALICE` here**: this file
declares its own `ALICE: Final = "Alice Admin"` at line 167 — a *display name* —
while the fixture of that name is the identifier `"prs_01HQ8Z6M4A"`. The two
spellings collide, they are the two arguments of this very constructor, and
swapping them reads plausibly in the diff.

Three lines against six, every call site and annotation unchanged, `identifier`
inherited. Decision 2's proof applies to it exactly as to a plain alias, because
what it compares is the object the constructor produces. An adapter is recorded
as an adapter — it is not a clean migration and `tasks.md` counts it separately
— but it is a migration, and clause (c) is what tells a migrator to reach for
one instead of giving up on the file.

**Names that pass a shape test and are still excluded.** `_Collaborators` (28
declarations, 10 distinct surfaces) and `_Surface` (17, 8) are dataclasses and
would survive a naive filter. They are per-test *bundles* — `catalog, delivery,
handlers, launches, playbook, recorder, results` in one file, `launches,
members, playbook, recorder, results` in another — so their field sets are
genuinely divergent and a shared type would be a union no test wants. They are
excluded by judgement, recorded here so the exclusion is a decision rather than
an omission.

`_Text`, `_Node` and `_TreeParser` (17 files) are excluded on an existing
decision, not a new one: `tests/support/html.py`'s docstring and the parent
change's task 8.3 both record that 8 track `Node.order`, 4 track `Text.ordinal`
and 5 differ in `_flat` or `handle_data`, and that the shared queries model no
document order. Verified still true — 8 ORDERED, 4 ORDINAL, 5 other. Not
reopened.

**A partial hit rate is the expected outcome, not a failure.** The parent change
took 135 of 135 on one symbol and 13 of 95 on another. The per-name expectation
is set in `tasks.md` from the measured variant structure, and a name that lands
below it is a finding to record, not a target to force.

### 4. Composition: this slice has none, and that is why it is first

The parent change's cap was composition. `hold()` composes over the *canonical*
`step()`; a local `_hold` composes over its *file's* `_step`; where that file's
step carries deltas the two build on different foundations, and forwarding the
deltas does not reconcile them. Six attempts established that and one cost 499
failing tests.

The doubles carry the same structure one level deeper — `_Member` is held by
`_FakeMembers`, held by `_FakeMembersStore`, handed out by a `_FakeSession`.

**The seven types in this slice are the leaves of that chain.** They hold no
double; they are held by them. So the composition problem is not solved here, it
is *absent* here, and the slice's contribution to it is to put the base in place
before the composers arrive:

```
slice 1   Member  CatalogProduct  Record  TaskMapping  PendingRow  FakeTask  CreatedTask
             ↑ held by
slice 2   FakeMembers  FakeMembersStore  FakeStepStore  FakeLaunches  FakePlaybooks  …
```

A shared `FakeMembers` returning shared `Member`s is reproducible across files.
A shared `FakeMembers` returning each file's own `_Member` is the `_hold`
problem again, and it is what taking the stateful fakes first would have
produced. **This ordering is the change's principal design claim**, and it is falsifiable
— but only as stated carefully. "Slice 2 caps anyway, so the leaves were not the
cause" does **not** follow: files whose `_Member` stayed local are a known cause
of exactly that cap, since a store in such a file still holds a per-file member.
The claim that is falsifiable is the narrower one:

> For a file whose leaf migrated, the leaf is not what caps its store.

So slice 2 partitions its findings on whether the file's leaf migrated, and the
claim is tested against the migrated partition alone. Stating it the loose way
would build a false exoneration into the second slice's post-mortem before it
starts.

### 5. `Member` exposes production's spelling as a property, in two forms

This is where the change earns Goal 3, and it is the one place a shared double
deliberately models *more* than every local it replaces.

Production spells the field `identifier`:

```python
# access/domain/members.py:39
@dataclass(frozen=True, slots=True)
class Member:
    identifier: str
    display_name: str
    slack_identity: str
    clickup_user_id: str | None = None
    admin: bool = False
    active: bool = True
```

**All 47 local `_Member` variants and all 5 `_FakeMember` variants spell it
`id`. Not one spells it `identifier`.** That is measured, not estimated, and it
is the whole explanation for the probe that appears at six sites:

| site | probe |
|---|---|
| `clickup_sync.py:140` | `("identifier", "id", "member_id")` |
| `playbook_authoring.py:272` | `("identifier", "id", "member_id")` |
| `playbook_admin.py:321` | `("identifier", "id", "member_id")` |
| `activation_readiness.py:204` | `("identifier", "id", "member_id")` |
| `roles.py:729` | `("identifier", "member_id", "id")` |
| `gate_decisions.py:105` | `("identifier", "id", "name")` |

`.importlinter` forbids `launch` from naming `access`'s types, so a shape is
read where a type cannot be named — that part is legitimate. The three
*spellings* are not: they exist because every stand-in models the minimum. The
double models the tolerance, which is why the tolerance can never be deleted;
`docs/deferred-work.md` records the dependency running backwards, and this is
the clearest instance of it in the tree.

**The field stays `id`; `identifier` arrives as a read-only property.**

An earlier draft of this decision had it the other way round — `identifier` as
the field, `id` as the property — on the reasoning that a double should be
shaped like the thing it stands in for. Decision 1's measurement kills that:
ten files pass the identifier as the keyword `id=`, and a read-only property
cannot receive a keyword argument. Inverting it costs nothing and breaks
nothing:

```python
class Member:  # plain: 42 declarations are plain
    def __init__(
        self,
        member_id: str,
        display_name: str,
        *,
        slack_identity: str | None = None,
        clickup_user_id: str | None = "clickup-1",
        admin: bool = False,
        active: bool = True,
    ) -> None:
        self.id = member_id
        ...

    @property
    def identifier(self) -> str:  # what all six probes read first
        return self.id
```

Every call site is untouched, because `id` is where all 52 declarations already
put it — with the single exception Decision 3's clause (c) governs, one file
whose constructor takes the display name in the first position and pins the
identifier, which keeps a three-line adapter rather than its own class. Every
one of the six probes now matches on its **first** branch and
returns the string it previously reached on its second or third — the same
string, by construction rather than by inspection, because the property *is*
the field. `_fields()` ignores properties, so Decision 2's comparison is over
`id` against the local's `id` directly, with no mapping to write down and
therefore none to get wrong.

Two shared types, not one, per Decision 3's form clause:

- **`Member`** — plain class, identity equality, hashable. Takes the 37 plain
  `_Member` declarations and all 5 `_FakeMember`.
- **`MemberValue`** — `@dataclass`, structural equality, unhashable, accepting
  `id=` as a keyword because that is how all ten of its files construct it, and
  typing `slack_identity` as `str | None` because one of them passes `None`
  deliberately. Takes the 10 dataclass `_Member` declarations.

Both expose `identifier`. That is what makes the sweep complete, and
completeness is the point: a single member double left spelling only `id` keeps
the probe's second branch live and leaves
`unify-launch-adapter-dependencies` nothing to delete. Two types is the price of
not bending one type across two equality semantics, and Decision 3 says why that
bend is not available.

Three consequences worth naming:

- The `identifier` property serves **production's probe**; `id` continues to
  serve test readers. Neither keeps the tolerance alive: the probe's second and
  third branches become dead once every double supplies `identifier`, and that
  is exactly what deleting them requires.
- **`slack_identity` defaults to `None`, and the same-value invariant is why.**
  42 of the 52 locals never declare it — exactly the 10 `@dataclass` variants
  do. It is read by shape at three sites in `src/`:

  | site | read |
  |---|---|
  | `gate_decisions.py:94` | `if getattr(member, "slack_identity", None) == slack_identity:` |
  | `automated_decisions.py:125` | the same comparison, verbatim |
  | `thread_establishment.py:224` | `slack_identity = getattr(member, "slack_identity", None)` |

  So this is a **displacement, not a genuine superset**, and
  `tests/support/protocols.py`'s standing rule applies directly: an added
  attribute a probe reads as a guard defaults to the value the fall-through
  produced, which for all 42 is `None`. A literal default would hand every one
  of them a truthy Slack identity it has never had, and the two `==`
  comparisons would begin matching where they used to fall through to "no
  member" — `mypy` passing, no spelling dropped, Decision 8's check passing and
  the suite green. Precisely the profile Decision 6 exists to prevent for
  `description`, arrived at from the other direction. It is typed `str | None`
  for the same reason, and because
  `test_mention_resolution_namespace.py:233` passes `None` deliberately.
- `clickup_user_id` is where the defaults genuinely disagree — the plain locals
  hard-code `'clickup-1'`, the dataclass ones default to `None`, which is
  production's own default. The split falls along the same line as the form
  split, so each shared type takes its own population's default and neither has
  to compromise. This is the second thing the two-type shape buys.

### 6. `FakeTask.description` defaults to `None`, and the measurement says why

The same-value invariant's second instance, and the sharper one, because here a
plausible shared type would have broken ten files silently.

`clickup_sync.py:517` reads `task_body = getattr(task, "description", None)`.
Across the 15 local `_FakeTask` declarations:

```
neither body nor description   5
body only                      5
description only               4
both                           1
```

So **10 of 15 files exercise `task_body = None` today.** A shared `FakeTask`
carrying both spellings with `description` populated from `body` — which is what
"model the whole surface" naively suggests — would hand those ten files a body
where they had none, changing which branch of the retention comparison at
`clickup_sync.py:514-517` fires. `mypy` passes, no spelling is dropped, the AST
check passes, and the suite may well stay green.

The invariant settles it without per-file analysis: `description` defaults to
`None`, because `None` is what the fall-through produced. `body` is carried as a
separate field with its own default because nothing in `src/` reads it — it is
test-local, and `retained_body` on the *mapping* is the thing production
compares against.

### 7. `_conforms` typing, and protocols that are meant to be deleted

Per `tests/support/protocols.py`'s standing rule and the parent change's
Decision 6: a `Protocol` declared beside a double checks nothing on its own,
because `mypy` compares a class to a protocol only where a value is assigned to
a protocol-annotated target. So each shared type carries, beside it:

```python
_conforms: MemberShape = Member("m-1", "Ada")
```

where `MemberShape` declares `identifier` **as a property, not as a variable**:

```python
class MemberShape(Protocol):
    @property
    def identifier(self) -> str: ...
```

`mypy` treats a protocol *variable* as settable, and a read-only property does
not satisfy one — so `identifier: str` in the protocol would make the
`_conforms` line a type error, on the one line the decision exists to justify.
The property form is also the truthful one: the protocol is written against what
production *reads*, and no production site assigns to it.

That assignment, not the protocol's existence, is what makes a double which has
stopped matching its subject a type error. `uv run mypy .` already runs strict
over `tests/`, so it costs one line per type and nothing at runtime. It is also
the check that caught defect 5 in the parent change, where tests could not.

Each protocol is added by the task that adds its type, never up front: the shape
comes from reading the variants being replaced, so authoring it first would be
guessing. They live in `tests/support/protocols.py` rather than in `src/`
because `unify-launch-adapter-dependencies` owns the production-side protocols
and two definitions of one boundary is the disagreement this work exists to end.
The module docstring already says they are temporary; this change adds instances
and does not change that sentence.

### 8. Assertion identity, checked as syntax trees

Decision 1 makes the region below the first test byte-identical for every
migrated file, so this check is a belt on top of a rule rather than the rule
itself. It is kept because the parent change's experience is that the rule is
the thing people are tempted to relax.

For every migrated file, collect four node kinds and compare `ast.unparse` of
each whole node before and after; the multiset must be identical, and the count
of `def test_` / `async def test_` unchanged:

1. every `ast.Assert`;
2. every `pytest.raises` `With` item;
3. every `ast.Expr` wrapping an `ast.Call` whose callee tail starts `assert` or
   is `fail` — an `assert_called_with` is not an `ast.Assert`, and there are 757
   of these;
4. every `@pytest.mark.parametrize` decorator — a changed value in a table is
   invisible to kinds 1–3 and to the collected count.

A line-level regex is insufficient: 2,632 of the 6,623 `ast.Assert` nodes span
more than one line. `~/share-the-test-doubles/assert_identity.py` implements all
four kinds; its `ROOT` points at the parent change's worktree and must be
repointed before use.

**The check is run across the commit pair, never within it.** Decision 2's
instrument commit deliberately *adds* an assertion, so running the check against
it reports a difference by construction — the parent change had to state the
same boundary (archived `tasks.md:17-20`) after hitting it. The comparison is
therefore between the commit before a name's instrument commit and the commit
after its settle commit. Here the ordering happens to make that natural; it is
written down anyway, because a migrator who runs it at the wrong point reads a
failure that means nothing and may relax something real in response.

### 9. No `tests/unit/support/` in this slice

The archived plan gives the shared doubles direct behaviour tests in
`tests/unit/support/` — a deliberate exception to the tier layout, collected at
commit time, whose subject is the harness itself. `AGENTS.md` already describes
it as arriving with the fakes.

**It arrives with the second slice, not this one.** These seven types have no
behaviour to test: no state, no ordering, no absent-key response — the three
things risk 3 in the parent change's Decision 7(b2) is about. A behaviour test
over a frozen field bag asserts that a dataclass stores what it was given.
Decision 2's proof is the check here, and it is stronger than such a test would
be, because it compares against the thing actually being replaced.

This has a verification consequence worth stating: **this slice holds the
collected count of all three tiers exactly, with no exclusion.** The parent
change needed the count held "excluding `tests/unit/support/`" and warned that
weakening it to "unchanged unless a task says otherwise" would let a silently
dropped test net against a newly added one. Here the strong form is available,
so it is used, and the second slice inherits the exclusion alone.

### 10. Four names need the integration tier at their instrument commit

Every task's default verification is the commit tier, because that is what the
`pre-commit` hook runs and it is where 181 of the 186 declarations live. Five
are not there:

| declaration | file |
|---|---|
| `_Member` | `tests/integration/launch/test_seeded_step_fields.py:578` |
| `_CatalogProduct` | `tests/integration/launch/test_pending_result_delivery_seam_live.py:267` |
| `_CatalogProduct` | `tests/integration/launch/test_eager_convergence_atomicity_live.py:225` |
| `_FakeTask` | the same file, `:271` |
| `_CreatedTask` | the same file, `:282` |

Decision 2's proof runs *inside* the instrumented constructor, so it executes
only when the suite that constructs the object runs. The commit tier never
imports these modules, so instrumenting them and running only the commit tier
would settle five declarations with the change's central check silently
skipped — four of them constructed, so four whose proof the tier is what runs,
and a fifth covered below — a green that means nothing, which is the failure mode `AGENTS.md`'s
worktree section already records for this tier. So `Member`, `CatalogProduct`,
`FakeTask` and `CreatedTask` run the integration tier at their instrument
commit, with `COMMERCE_OPS_REQUIRE_DATABASE=1`. The other three names do not,
and paying that cost four times rather than seven is the whole reason to state
this per name instead of globally.

**One of the five is worse than untested: it is untestable.**
`test_seeded_step_fields.py`'s `_Member` is **never constructed** — the file's
`_FakeMembers.list_members` returns `()` and the class appears only in
annotations. No instrumented constructor ever runs, on any tier, so the proof is
not merely skipped but inapplicable. It migrates on clauses (a)–(c) and on
`mypy` alone, and that is recorded against it rather than left to look like a
proof that passed.

## Risks / Trade-offs

1. **A default wrong only on an unexercised path.** Decision 2 checks every
   construction the suite performs and nothing else. Mitigation: none available
   at proportionate cost; the residual is smaller than the parent change's
   because there is no behaviour to hide in. Accepted and recorded.
2. **This slice found no genuine superset, and that is the finding.** Every
   field a shared type here adds over the locals it replaces turns out to be
   read somewhere in `src/` by shape, so every one is a *displacement* under the
   same-value invariant rather than an unread addition: `identifier` at six
   probe sites, `slack_identity` at three, `description` at one,
   `display_order` at four, `assignees` at one. An earlier draft of this
   document listed `slack_identity` here as the example of an unread superset;
   it is read at `gate_decisions.py:94`, `automated_decisions.py:125` and
   `thread_establishment.py:224`, and Decision 5 now says so. The residual risk
   is therefore not "a superset was mishandled" but "a *sixth* read was not
   found": the searches are per field and recorded per type, and a field added
   without one is the defect this entry names.
3. **A probe this change did not enumerate.** The measurement is by *shape* — a
   `getattr` over a loop variable ranging across a tuple of string literals —
   and it finds ten sites where every previous, spelling-based sweep found
   between two and five. It would still miss a probe written as a chain of
   `if hasattr(...)`, or one reading a name held in a module constant.
   Mitigation: `tasks.md` 10.1 re-runs the shape measurement rather than copying
   this document's table, and records the *method* beside the result, so the
   next correction starts from a method rather than from a list. This is the
   difference between correcting a stale table and stopping it going stale.
4. **A conflict-prone diff.** ~150 test files, and
   `unify-launch-adapter-dependencies` touches `src/` in the same area.
   Mitigation: order, not technique — this change does not run concurrently
   with anything else that edits `tests/` broadly, and the queue records that.
5. **Two shared member types is a smell, and is accepted deliberately.**
   `Member` and `MemberValue` differ in equality semantics, hashability and one
   default, and in nothing else. A reader will reasonably ask why the suite
   needs both. The answer is that the suite already has both — 42 declarations
   of one and 10 of the other — and this change's job is to stop re-declaring
   them, not to decide which is right. Collapsing them means choosing an
   equality semantics for files that did not choose one, which Decision 3's
   clause (b) exists to prevent. `unify-launch-adapter-dependencies` is where
   the two collapse into production's own type; `tasks.md` 10.4 records the pair
   as a known follow-up rather than leaving it to be rediscovered.
6. **`docs/deferred-work.md`'s tolerance table has now been stale three times.**
   This change corrects it again and adds seven sites. Correcting a table that
   has gone stale twice within one week is weak mitigation for whatever keeps
   making it stale; risk 3's method-not-list remedy is the real one, and the
   durable fix is deleting the probes, which is
   `unify-launch-adapter-dependencies`.

## Migration Plan

Per name, in descending order of declarations, each name its own pair of
commits: instrument, verify, settle, verify. `Member` first — it is the largest,
it carries Goal 3, and if the `id`/`identifier` decision is wrong it is better
to learn that on the first name than the last.

No production file is edited. No test body is edited. Rollback for any name is
the revert of its two commits, which touch no other name.

## Open Questions

1. **Whether `Record`'s field values defeat Decision 2's shallow comparison.**
   It holds a production `StepDefinition`, so it is the one type whose field
   values are production objects — if the shallow choice is uncomfortable
   anywhere, it is here. Two references to the same `StepDefinition` compare
   equal by identity, so it should be fine; `tasks.md` 5.3 confirms it rather
   than assuming it, and stops if it does not hold.

   **Its `display_order` default is settled here rather than left open**, since
   the measurement that would have answered it has already been made. Its
   variant structure is **three field sets**, not the
   near-uniform one an earlier draft of this document claimed on the strength of
   a surface measure that read only method names:

   | declarations | fields |
   |---|---|
   | 28 | `definition`, `display_order`, and eight provenance fields (`created_by`/`_on`, `updated_by`/`_on`, `retired_by`/`_on`, `unretired_by`/`_on`) |
   | 1 | the same, without `display_order` — `test_launch_report_step_facts.py` |
   | 1 | `definition` and `display_order` only — `test_check_step_handlers_reads_the_authored_set.py` |

   Both minorities are strict subsets, so clause (a) admits them **if** the
   shared defaults equal what absence produced — and for `display_order` the two
   impose **opposing** constraints, which is why this is a decision and not a
   formality:

   The constructor signatures decide it, and there are three of them across the
   30 — a measurement an earlier draft of this document got wrong in a way worth
   recording, because it inverted the answer:

   | declarations | `__init__` | what a call that omits `display_order` yields |
   |---|---|---|
   | 16 | `(self, definition, display_order: int = 10)` | **`10`** |
   | 13 | `(self, definition, display_order: int)` | n/a — always passed |
   | 1 | `(self, definition)` | the field does not exist |

   Production reads it at four sites as `getattr(row, "display_order", 0)` —
   `playbook_authoring.py:180` and `:428`, `playbook_admin.py:911`,
   `playbook_repository.py:154` — so for the single declaration that carries no
   such field, absence produced **`0`**.

   **The shared default is `10`.** It is what 16 locals produce, inside the
   compared intersection, so anything else fails their proof loudly and
   pointlessly. The 13 that require the argument are indifferent. The one
   declaration with no such field — `test_launch_report_step_facts.py`, which
   drives `update_step` into `_as_record` — would receive `10` where its absence
   yielded `0`, and that difference sits *outside* the intersection, so it is
   silent. It therefore **keeps its own declaration**, and `Record` lands at
   **29 of 30**.

   An earlier draft chose `0` on the belief that only one local defaulted to
   `10`, reasoning that a loud failure beats a silent one. The reasoning was
   right and the measurement was wrong: `0` would have broken 16 declarations to
   protect one, where `10` excludes the one and protects the 16. The principle
   is unchanged — the file whose exercised production read would silently move
   is the file that stays local.
2. **Whether the 37 plain `_Member` declarations depend on identity
   inequality.** They do not get structural equality under Decision 5 — the
   shared `Member` is a plain class precisely so they do not — so this question
   does not gate the migration. It is recorded because it is the question that
   would have to be answered before the two member types could ever be
   collapsed into one, and answering it while the corpus is being read is
   cheaper than answering it later from cold. `tasks.md` 3.2 measures it and
   records the answer for `unify-launch-adapter-dependencies` to use.
