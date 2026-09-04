## Why

`share-the-unit-test-harness` shipped the shared builders and cut the shared
test doubles to a follow-up. `docs/proposed-change-order.md` §4 records that
follow-up as one change, `share-the-test-doubles`, covering **455 fake
declarations across 18 names**. Measured against the tree on 2026-09-04 the
population is larger than that — **1,199 module-level classes in `tests/`**, of
which 649 carry one of the 28 names that recur eight times or more — and, more
usefully, it is not one population. It splits on a property that decides which
verification is even expressible:

| shape | declarations | `local(...)` vs `shared(...)` |
|---|---|---|
| `@dataclass` doubles with no behaviour | 260 | field-wise comparison — **exact** |
| plain classes whose only method is `__init__` | 140 | `vars()` comparison — **exact** |
| doubles with behaviour (state, `__call__`, recording) | 799 | identity — **inexpressible** |

The parent change's stopping rule (`design.md` Decision 7(b1)) was an
equivalence proof: keep the local declaration, add the shared one, assert on
every executed call that the two build equal objects, delete only after that
passes. The parent change records that it caught **five** real defects, every one of
which left the assertions textually identical and the suite green. Its archive
substantiates two of the five directly (`tasks.md` 6.6 — a helper splatting a
dict so the call carried no keywords, and 45 files inheriting a builder default
rather than the one intended); of the rest, one is recorded at `tasks.md` 3.3 as
a `mypy` catch rather than a proof catch, and two are recorded as measurements
made while migrating. The proof is the check being carried forward here, so the
claim is stated at the strength the record supports: it caught at least two
defects that nothing else in the change would have. It was believed not to transfer to the
doubles at all — `FakeStepStore() == FakeStepStore()` is identity, so the proof
is meaningless for them.

That is true of the 799, and false of the other 400. A double with no behaviour
is a value wearing a class, and comparing two of them field-by-field is the same
proof, expressed as `dataclasses.asdict` or `vars()` rather than as `==`.
(Cross-class `==` returns `NotImplemented` even between two dataclasses, so the
comparison is on the fields, not on the operator — but the assertion it supports
is the one that found the five defects.)

**So this change takes the population the proof reaches, and takes it first.**
It is the first of two slices; `share-the-stateful-fakes` takes the 799 under
the weaker substitute the parent change designed for them (Decision 7(b2)) plus
the direct behaviour tests in `tests/unit/support/` that only it needs.

### Values first is also the answer to the composition question

The parent change migrated `_step` whole — 135 of 135 — and reached only 31 of
104 `_hold` and 13 of 95 `_playbook`, because both compose *over* `_step`: a
local helper built on a customised step is not reproducible by a shared helper
built on the canonical one, however the deltas are forwarded. Six attempts
established that; one cost 499 failing tests.

The doubles carry the same structure one level deeper. `_Member` is held by
`_FakeMembers`, which is held by `_FakeMembersStore`, which a `_FakeSession`
hands out. Sharing the store before sharing the member repeats the parent
change's failure exactly: a shared store holding *local* members is a store
whose contents differ per file, and no amount of forwarding reconciles it.

`_Member` (47) and its body-identical twin `_FakeMember` (5), `_CatalogProduct`
(40), `_Record` (30), `_TaskMapping` (19), `_PendingRow` (16), `_FakeTask` (15)
and `_CreatedTask` (14) are the leaves.
They are held by the stateful fakes and hold nothing themselves. Migrating them
first is what makes the second slice's stores reproducible — the base lands
before the composer, which is the ordering the parent change learned the
expensive way.

### The tolerances this slice actually makes deletable

`docs/deferred-work.md` records that production reads one value through several
attribute spellings so that a test's stand-in need not model the real
collaborator, and that the tolerance "closes behind `share-the-test-doubles`".
The entry was corrected on 2026-09-04 and is stale again.

It is stale for a reason worth stating, because it is the same reason each
time: every version of that table was assembled by grepping a *spelling*.
Measured instead by **shape** — a `getattr` over a loop variable ranging across
a tuple of string literals, whatever the loop variable is called — `src/` holds
**ten** such probes, and **six** of them are the member-shape probe:

| site | probe |
|---|---|
| `clickup_sync.py:140` | `("identifier", "id", "member_id")` |
| `playbook_authoring.py:272` | `("identifier", "id", "member_id")` |
| `playbook_admin.py:321` | `("identifier", "id", "member_id")` |
| `activation_readiness.py:204` | `("identifier", "id", "member_id")` |
| `roles.py:729` | `("identifier", "member_id", "id")` |
| `gate_decisions.py:105` | `("identifier", "id", "name")` |
| `gate_progression_job.py:271` | `("awaiting_gate", "gate_id", "current_gate")` |
| `automation_pass.py:209` | `("noted_kind", "outcome_kind", "outcome", "kind", "noted_outcome")` |
| `automation_pass.py:217` | `("noted_at", "when")` |
| `automation_pass.py:225` | `("reported_at", "reported", "has_been_reported")` |

Of these, `docs/deferred-work.md`'s corrected table names three; **its line
numbers are still correct**, because it anchors each on the enclosing `def`
where the table above anchors on the `for`. Seven sites it omits are recorded
here for the first time. Two of the ten — `gate_decisions.py:105` and
`roles.py:729`, both of them member-shape — iterate a loop variable named
`attribute` rather than `name`, so a sweep for the literal string `for name in (`
finds the other eight and misses exactly those two.

**Every one of the six member probes reads `identifier` first.** That is what
makes this slice's contribution safe to state precisely: the double sitting
opposite all six is a member stand-in, and 52 of them exist across the suite
(`_Member` 47, `_FakeMember` 5) — **not one of which spells the field
`identifier`.** Supplying it, with the same value, at every one of the 52 is
what leaves the second and third branches of all six probes dead and therefore
deletable.

What this change does **not** do is delete them. Deletion belongs to
`unify-launch-adapter-dependencies`, which can name a shape without naming a
type `.importlinter` forbids. This change makes deletion safe.

## What Changes

Eight shared value types are added to `tests/support/`, and the local
declarations that the equivalence proof shows they reproduce are deleted.

| local name | declarations | bodies | plain | dataclass | shared type takes |
|---|---|---|---|---|---|
| `_Member` | 47 | 14 | 37 | 10 | 37 → `Member`, 10 → `MemberValue` |
| `_FakeMember` | 5 | 1 | 5 | 0 | 5 → `Member` |
| `_CatalogProduct` | 40 | 11 | 7 | 33 *(frozen)* | 31 |
| `_Record` | 30 | 3 field sets | 30 | 0 | 29 |
| `_TaskMapping` | 19 | 2 | 0 | 19 | 19 |
| `_PendingRow` | 16 | 8 | 3 | 13 | 9 |
| `_FakeTask` | 15 | 8 | 0 | 15 | 15 |
| `_CreatedTask` | 14 | 2 | 0 | 14 *(frozen)* | 14 |

**186 declarations, of which 169 are expected to migrate** — 52 + 31 + 29 + 19
+ 9 + 15 + 14, set per name in `tasks.md` from the measured form, field and
constructor structure, not from ambition. One of the 169 is not a deletion: a
single file keeps a three-line adapter under clause (c), so the reduction is
**168 declarations deleted and 1 replaced**. The gap between "14
bodies" and the two forms is the whole opportunity: `_Member`'s fourteen bodies
differ in whether `active` is a keyword argument or hard-coded `True`, and in
whether the class is written as a `@dataclass`. They do not differ in what a
member *is*.

`_FakeMember` is in the table because it is `_Member` under another name — five
declarations, one body, byte-identical to the dominant `_Member` and spelling
the field `id` exactly as it does. A frequency threshold would exclude it and a
shape rule includes it, and it must be included: three of the five sit directly
opposite `playbook_admin.py:321`, so leaving them out would leave that probe's
`id` branch live and defeat the point of the exercise.

### The migration boundary, stated up front

The parent change reached its boundary by inference and ended at an exact
whole-body match, which is why `_playbook` took 13 of 95 against 56 distinct
bodies. An exact-body rule applied here would take 24 of 40 `_CatalogProduct`
and 12 of 19 `_TaskMapping` for no reason: those variants are *nested*, not
divergent. The rule this change uses instead has three clauses, and needs all
three:

> A local declaration is migrated when **(a)** its field set is a **subset** of
> the shared type's, and for every field it does not declare the shared type's
> default equals the value that field's absence produced at every site the file
> exercises; **(b)** the shared type's *declaration form* matches the local's —
> dataclass-ness, `frozen`, `eq`, and any `__repr__` the file relies on; and
> **(c)** the shared type's `__init__` accepts every one of the local's call
> sites unchanged, in parameter name, position and optionality. Otherwise the
> file keeps its own declaration — **except** where clause (c) alone fails,
> which is remediable by a three-line adapter subclass over the shared type.

Clause (a) is checkable per declaration rather than per body, and it is exactly
what the equivalence proof asserts, so that rule and that proof are one
statement.

Clause (b) is there because the proof cannot see it. Field comparison reads
values; it says nothing about `__eq__`, `__hash__` or `__repr__`, and those
differ across this corpus for real reasons. Two files document their
`_CatalogProduct` as a plain class *because* `catalog.domain.product.Product`
is one, so `!r` leaks `<... object at 0x...>` "exactly as it would in
production" — a shared dataclass would render fields instead, with every check
green. Non-frozen dataclasses are unhashable where the plain classes they sit
beside are not. So form is part of the boundary, and it is what splits `_Member`
into two shared types rather than one.

Clause (c) is there because a field set is not a signature.
`test_product_dossier_page.py:721` declares
`def __init__(self, display_name: str, *, active: bool = True)` and hard-codes
`self.id` — a strict field subset in the plain form, so clauses (a) and (b) both
admit it, while its two call sites pass the *display name* where the shared type
expects the identifier. Aliasing the shared class there is a `TypeError` at
collection. The remedy is not exclusion: the file keeps a three-line adapter
subclass over the shared type, which preserves its call sites, its annotations
and — the point of the exercise — the `identifier` spelling the probes read. A
constructor mismatch costs three lines; it does not cost the goal.

### Two names that look like candidates and are not

`_Collaborators` (28 declarations, 10 surfaces) and `_Surface` (17, 8) are
dataclasses and would pass a shape test. They are excluded: both are per-test
*bundles* of whatever collaborators that test happens to need, so their field
sets are genuinely divergent rather than nested, and a shared bundle would be a
union nobody wants. `_Text`, `_Node` and `_TreeParser` (17 files) are excluded
too, and that exclusion is already recorded and reasoned in
`tests/support/html.py`'s docstring and in the parent change's task 8.3 — 8
track `Node.order`, 4 track `Text.ordinal`, 5 differ in `_flat` or
`handle_data`, and the shared queries model no document order. This change does
not reopen it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/`, `AGENTS.md` and
`docs/proposed-change-order.md`, and corrects one table in
`docs/deferred-work.md`. Every requirement the suite covers is unchanged and
every test must still assert exactly what it asserts today — that is the
acceptance criterion, not an aside.

No recorded specification names any of these types; they exist only in `tests/`.
`deploy-pipeline`'s validation-job requirement names the three tiers by path,
and `tests/support/` is not a tier and is collected by nothing, so it stays
satisfied. `.openspec.yaml` therefore sets `skip_specs: true`, following
`share-the-unit-test-harness` (2026-09-04) and
`isolate-tests-from-the-shared-runner` (2026-08-25).

Per `AGENTS.md`, a change declaring no specification deltas has none to derive
tests from and owes no new tests; what it owes is that the existing suite stays
green, with the collected count held exactly. The exemption is stated here, in
advance, and its reason is that this change adds no behaviour — it deletes
duplicate declarations of behaviour that is already covered.

## Impact

- **Added**: `tests/support/values.py`, and one protocol per *shape* in
  `tests/support/protocols.py` — seven for the eight types, `Member` and
  `MemberValue` sharing `MemberShape` — which ships today with 41 lines of docstring,
  no protocol and no importer, as the placeholder this change fills.
- **Reduced**: 168 of 186 declarations deleted outright and 1 replaced by a
  three-line adapter, across roughly 150 files. `_Member` and
  `_FakeMember` together are 52 declarations of one six-field class.
- **Corrected**: `docs/deferred-work.md`'s tolerance table, `AGENTS.md`'s
  "shared harness" rules — which are written as binding on whoever writes the
  first shared double, there being no instance to copy yet — and the two
  `tests/support/` docstrings that say the shared doubles have not landed.
- **Unchanged, and verified so**: the collected count of all three tiers —
  `tests/unit` 2,246, `tests/agents` 236, `tests/integration` 159, measured
  against `main` at `713e9da` rather than inherited. This slice
  adds no test of its own, so the count is held with no exclusion. (The
  behaviour tests under `tests/unit/support/` belong to the second slice, which
  will need the exclusion this one does not.)

### Ordering against the other proposed changes

**Order-independent, and conflict-prone** — it touches ~150 test files, so it
should not run concurrently with anything else that does.
`unify-launch-adapter-dependencies` is the change that deletes the tolerances
this one makes safe, and must follow it. `share-the-stateful-fakes` must follow
it too, for the composition reason above.
