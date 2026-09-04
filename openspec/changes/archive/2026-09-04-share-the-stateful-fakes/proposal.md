## Why

`share-the-value-doubles` (archived 2026-09-04) took the half of the double
population for which an equivalence proof is expressible — 166 of 186
declarations of eight value types, now in `tests/support/values.py` — and cut
the doubles *with behaviour* to this change. `docs/proposed-change-order.md` §3
carries the entry.

Measured against `main` at `5e5b19a` on 2026-09-04, by AST over `tests/**/*.py`
excluding `__pycache__`, that remainder is **803 declarations across 190
names** — every module-level class in `tests/` carrying a method other than
`__init__`, or an alias binding one method name to another. **482 of the 803
are the 27 names declared eight times or more**, which is the frequency floor
the parent slice used.

This change takes **191 of those 482**, across nine names and 103 files. It
does not take all 482, and the reason is stated up front rather than discovered
at the boundary: the other 291 are excluded by the composition rule below, by
divergence too wide for one shared fake, or — in the single case of
`_FakeCatalog` — because one name carries two different doubles. Forcing the
first group would repeat the parent change's `_hold` failure at one level up.

### The equality proof does not transfer — but a stronger one does

The parent slice's check was field comparison: build the local and the shared
object from the same call, assert they agree. For a stateful fake that check is
meaningless — `FakeStepStore() == FakeStepStore()` is identity — and the
archived plan therefore designed a *weaker* substitute for this population
(`share-the-unit-test-harness` `design.md` Decision 7(b2)): `_conforms` typing,
plus a per-fake surface-and-behaviour note. That substitute names four residual
risks and states plainly that **risk 3 — the shared fake keeps the whole surface
and behaves differently behind it — is caught by no check in the change**.

That gap is closable, and closing it is this change's central decision. A local
double and a shared one can be driven **in lockstep**: construct both, and on
every executed method call invoke both, comparing the return value, the raised
exception and the instance state afterwards. Where the parent slice compared two
objects, this compares two *behaviours*, over exactly the calls the suite makes.

It is not a thought experiment. A spike against two measured `_FakeStepStore`
bodies and a shared candidate passes on both, and on a third local mutated to
skip its version bump — the risk-3 shape exactly — reports:

```
LocalDivergent.save() state: {'records': ('c',), 'version': 41, ...}
                          != {'records': ('c',), 'version': 42, ...}
```

`design.md` Decision 2 states what it catches, what it does not, and the
**28 declarations it cannot reach at all** — because "stronger" on its own is
not something a reviewer can act on, and a proof that is silent for a name must
say so rather than let a green run stand in for a passed check.

### The reader-shape tolerances, three of them recorded here for the first time

`docs/deferred-work.md` records the tolerances production carries for
incomplete test doubles. The parent slice re-measured them structurally and
found **ten** attribute-spelling probes — a `getattr` over a loop variable
ranging across a tuple of string literals — and recorded **two further
tolerances its shape measurement could not find**, being loops over nothing:
`clickup_sync._members:128`, which accepts three *reader shapes*, and
`gate_progression_job._crossed:256`, which is a `getattr` with a default over a
single spelling. Those two are different kinds of thing, and only the first is
a reader shape.

Measured structurally for a reader shape — a function resolving one value from a
collaborator through more than one calling convention, whether a `getattr` for a
named method, a `callable()` test, or a bare fall-through over the collaborator
itself — `src/` holds **four**:

| site | conventions accepted | recorded before? |
|---|---|---|
| `clickup_sync._members:128` | `list_members()` · a callable · a bare iterable | yes |
| `activation_readiness._members_of:179` | `list_members()` · a callable · a bare iterable | **no** |
| `activation_readiness._registered_names:150` | `names()` · a bare iterable | **no** |
| `playbook_authoring._registered_names:389` | `names()` · a bare iterable | **no** |

**Three of the four are unrecorded**, and every one of the four sits opposite a
double in this change's population — the members readers opposite `_FakeMembers`
(43), the handler-name readers opposite `_FakeHandlerRegistry` (12) and
`_FakeHandlers` (8). `_crossed` is neither a reader shape nor this change's
business, and stays recorded as the separate live tolerance it is.

Three further sites read `list_members` through a single `getattr` and raise or
adapt otherwise (`playbook_authoring:245`, `thread_establishment:254`,
`playbook_admin:276`); they are narrow already and are listed so the next change
is not left to rediscover them.

**What this change contributes is precise, and smaller than "the tolerance
closes".** It gives **41 of the 43** `_FakeMembers` and **all 20** handler
registries a single reader shape — measured dead spellings dropped, not merely
deduplicated. The two `_FakeMembers` the boundary does not reach — each carrying
a call counter the shared fake has no attribute for — keep their own
declarations and their own spellings, so the members population is narrowed
rather than made uniform. It does *not* empty any fall-through branch, because
both populations are broader than the names in scope: the suite also passes
`_StoreShapedMembers`, `_ReaderMembers`, `_Members` and a module-level
`_members()` function at 17 call sites. Establishing those branches dead is
`unify-launch-adapter-dependencies`' work, by the mutation method the parent
slice used for the member-identifier probes — and `docs/deferred-work.md`'s
standing rule applies until it does: **do not narrow a probe on the strength of
a green suite.**

### The composition rule, applied one level up

The parent slice was ordered first because `_Member` is held by `_FakeMembers`,
which is held by `_FakeMembersStore`: a shared store holding each file's own
members is a store whose contents differ per file, which is the `_hold` problem
that cost that change 499 failing tests in one attempt.

The same rule now decides *which* fakes are in scope. A fake is reproducible
when everything it holds or returns is already shared — a primitive, a
production type, or one of the eight value doubles — and is not when it returns
the output of a per-file builder. `_FakeStepStore` holds `Record`s, which
migrated; `_FakeMembersStore` holds rows the call site passes. `_FakePlaybooks`
(32) and `_FakePlaybookRepository` (10) return `_playbook()`, of which the
parent slice reproduced 13 of 95 — so a shared repository would have to be told
which playbook to serve, at call sites this change may not edit.

## What Changes

Nine shared fakes are added to `tests/support/fakes.py`, with a protocol each in
`tests/support/protocols.py`, and the local declarations the lockstep proof
shows they reproduce are deleted. `tests/unit/support/` arrives with them,
carrying the contract tests that state each shared fake's behaviour directly.

| local name | decls | files | bodies | surfaces | shared type |
|---|---|---|---|---|---|
| `_FakeMembers` | 43 | 43 | 21 | 7 | `FakeMembers` |
| `_FakeMembersStore` | 38 | 38 | 15 | 2 | `FakeMembersStore` |
| `_FakeStepStore` | 37 | 37 | 11 | 2 | `FakeStepStore` |
| `_Catalog` | 16 | 16 | 7 | 2 | `FakeCatalogPort` |
| `_StubDate` | 15 | 15 | 1 | 1 | `StubDate` |
| `_FakeSlackResponse` | 13 | 13 | 1 | 1 | `FakeSlackResponse` |
| `_FakeHandlerRegistry` | 12 | 12 | 5 | 2 | `FakeHandlerRegistry` |
| `_InertBackoff` | 9 | 9 | 2 | 2 | `InertBackoff` |
| `_FakeHandlers` | 8 | 8 | 1 | 1 | `FakeHandlers` |

**191 declarations, of which 175 are expected to migrate** — the per-name
expectations are set in `tasks.md` from the measured body, surface and
constructor structure, not from ambition, and a name landing under its
expectation is a finding to record rather than a target to force. Three of the
191 live in `tests/integration/`, in two names, which decides where the
integration tier is run (`design.md` Decision 9).

**The migration profile differs from the parent slice's, and the difference is
worth seeing before the tasks are read.** There, 163 of 166 migrations were an
aliased import and 3 were adapter subclasses. Here **114 are aliases and 61 are
small adapter subclasses**, because a stateful fake far more often hard-codes
its contents in the body rather than taking them through a constructor: of the
43 `_FakeMembers`, 20 declare no `__init__` at all and return a fixed roster and
7 more take no arguments, and all 15 `_StubDate` carry their day as a class
attribute. An adapter is a
smaller win than an alias — four lines against eight, rather than nothing
against eight — and it is still the win this change is for, because it is what
makes the *surface* uniform. The counts are split per name in `tasks.md` so that
a slice landing a third of its migrations as adapters is visible rather than
averaged away.

### The migration boundary, stated up front

The parent slice's boundary had three clauses and grew a fourth during
implementation. Behaviour needs a fifth from the start, because a field set no
longer describes a fake:

> A local declaration is migrated when **(a)** its surface is a subset of the
> shared fake's, and the shared fake's initial state, return shape, absent-key
> response and mutation effect match the local's on every call the file
> executes; **(b)** the shared fake's declaration form matches the local's,
> including its base class, which for `_StubDate` (`date`) and
> `_FakeSlackResponse` (`dict`) is the whole substance of the double; **(c)**
> the shared fake's `__init__` accepts every one of the local's call sites
> unchanged, in parameter name, position and optionality; and **(d)** the
> local's effects are confined to its own instance, because the proof runs both
> fakes and an effect on anything else would happen twice. Otherwise the file
> keeps its own declaration — **except** where clause (c) alone fails, which is
> remediable by a small adapter subclass; **except** where the only difference
> is a surface the shared fake *adds*, which clause (a) permits and `AGENTS.md`'s
> completeness rule governs; and **except** where the only difference is a
> spelling the shared fake *drops* that has been **measured dead across both
> `src/` and `tests/`**, which is clause (e).

**Clause (e) is what makes the reader-shape work expressible at all**, and it is
narrow on purpose. It licenses dropping a spelling only on a measurement, taken
at the commit that drops it, showing that no production site and no test reaches
for it. Three spellings qualify and they are named in advance:
`_FakeMembers.members`, `_FakeMembers.__call__` and `_FakeHandlerRegistry`'s
`__iter__`. Without it, clause (a) forbids the drop and the change's third goal
is unreachable; with it stated loosely, the boundary would license dropping
anything nobody happened to grep for.

Clause (d) is what makes the lockstep proof *sound*. A double that appends to a
module-level list, writes a file or increments a counter shared with the test
would record twice under pairing, and the proof would report a difference that
is an artefact of the proof. Measured over all 191 declarations, **clause (d)
excludes none of the ones this change plans to migrate**: its only six hits are
the `_FakeMembersStore` declarations threading an external version cell, which
are already kept for a constructor reason. The clause stays because it is what
makes the proof sound and because the next slice's population is not measured;
it is recorded as measured-inert rather than left looking like a live exclusion.

### `FakeMembers` drops two spellings, and the measurement says it costs nothing

The archived plan calls this a **licensed** arrangement change: the local fake
carries `list_members()`, `members = list_members` and `async def __call__`, and
the shared one carries `list_members()` alone, because the three spellings exist
only to satisfy a probe's three branches and reproducing them would preserve the
tolerance this work exists to make deletable.

Measured rather than assumed, on `main` at `5e5b19a`:

- **`members` is read by nothing.** No production site probes it — the four
  reader probes read `list_members`, `names`, or the collaborator itself — and
  no test calls it. Zero uses across `tests/` and `src/`.
- **`__call__` is unreachable while `list_members` exists.** Both members
  probes test `callable(...)` only after the `list_members` branch has missed,
  and every one of the 43 declares `list_members`. No test invokes an instance
  directly either: zero call sites, by AST over the 43 files.
- **`_FakeHandlerRegistry.__iter__` is the same case, and one measurement
  further.** Both `_registered_names` sites iterate the collaborator only when
  `names` is not callable, and all 12 declare `names()`; no test iterates an
  instance. The mechanism that could still reach it is the `in` operator, which
  falls back to `__iter__` when `__contains__` is absent — and
  `automation_pass:770` evaluates `name in handlers` directly. Measured: **all
  12 declare `__contains__`**, as do all 8 `_FakeHandlers`, so no membership
  test in the suite resolves through iteration today. `__contains__` is
  therefore **kept** — it is a call, not a convention — and `__iter__` goes.

Six of the 43 additionally carry `member(member_id)`. That is a genuine second
query, not a second spelling of the first, so the shared fake keeps it.

### Names that look like candidates and are not

- **`_FakePlaybooks` (32), `_FakeLaunches` (32), `_FakeLaunchStore` (26),
  `_FakePlaybookRepository` (10)** — each returns a per-file aggregate built by
  a local `_playbook()` or `_hold()` helper, of which the parent slice
  reproduced 13 of 95 and 31 of 104. A shared fake would have to be told what to
  serve, at call sites that pass nothing. This is the composition rule above.
- **`_FakeCatalog` (29)** is excluded for a third reason, and it is the one
  exclusion neither rule covers: it is **two doubles under one name**, and
  neither is `_Catalog` under another name — which is what `_FakeMember` was to
  `_Member`, and why that one was included on shape rather than frequency.
  Twenty-four declarations are a callable product reader; the other five are
  catalog-port shaped, and **four of those five apply access-scope filtering
  that no `_Catalog` declaration performs**. Migrating them onto
  `FakeCatalogPort` would drop a scope check inside a double, invisibly. No file
  declares both names, so the exclusion leaves no file holding one migrated and
  one unmigrated catalog double.
- **`_RecordingSlackApi` (12), `_FakeMapping` (19), `_FakeClickUp` (15),
  `_FakeResults` (15), `_FakeSession` (12)** — 12 distinct bodies in 12
  declarations, 14 in 19, 14 in 15, 10 in 15, 10 in 12. A shared fake over a
  population that agrees on nothing is a union, which is what
  `docs/proposed-change-order.md` already rejected for `_Collaborators` and
  `_Surface`.
- **`_TreeParser` (17)** is excluded by a decision already recorded in
  `tests/support/html.py`'s docstring and in `share-the-unit-test-harness`'s
  task 3.1a — 12 track a document order the shared queries do not model, and 5
  differ in `_flat` or `handle_data`. This change does not reopen it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. This change edits `tests/`, `AGENTS.md` and
`docs/proposed-change-order.md`, and adds three rows to
`docs/deferred-work.md`'s tolerance record for the reader-shape probes it
measured for the first time. Every requirement the suite covers is unchanged and
every existing test must still assert exactly what it asserts today — that is
the acceptance criterion, not an aside.

No recorded specification names any of these types; they exist only in
`tests/`. `deploy-pipeline`'s validation-job requirement names the three tiers
by path, and `tests/unit/support/` is *inside* `tests/unit`, so it is collected
by the existing hook and CI step with no configuration change and that
requirement stays satisfied. `.openspec.yaml` therefore sets `skip_specs: true`,
following `share-the-value-doubles` and `share-the-unit-test-harness`
(both 2026-09-04).

Per `AGENTS.md`, a change declaring no specification deltas has none to derive
tests from and owes no new tests; the exemption is stated here, in advance, and
its reason is that this change adds no behaviour to the system — it deletes
duplicate declarations of test-side behaviour. The contract tests under
`tests/unit/support/` are part of the implementation, not the derived tests that
exemption covers: they are written against the shared fakes' stated contract,
which this change authors, and nothing derives them from a specification because
there is none to derive them from.

## Impact

- **Added**: `tests/support/fakes.py` with nine shared fakes; nine protocols in
  `tests/support/protocols.py`, each with the `_conforms` assignment that makes
  `mypy` check it; and `tests/unit/support/` — a deliberate exception to the
  tier layout, whose subject is the harness itself, which `AGENTS.md` already
  describes as arriving with the fakes.
- **Reduced**: 175 of 191 declarations expected to go, across 103 files. Nine
  names become nine shared declarations, 61 adapter subclasses and 16 kept
  locals — not nine declarations outright, and the difference is the point of
  the alias/adapter split above.
- **Corrected**: `AGENTS.md`'s "shared harness" section and both
  `tests/support/` docstrings, which say the stateful fakes are deferred, put
  their population at "~355 declarations" against a measured 803, and say the
  equality proof is inexpressible for them — true of the *comparison*, and this
  change supersedes it with a proof that compares behaviour instead;
  `docs/proposed-change-order.md`, whose §3 entry is deleted on archive and
  whose §4 caution about the probe surface is updated with the three
  reader-shape sites; and `docs/deferred-work.md`'s tolerance record, which
  gains them.
- **Unchanged, and verified so**: the collected count of all three tiers
  *outside* `tests/unit/support/` — `tests/unit` 2,246, `tests/agents` 236,
  `tests/integration` 159, measured against `main` at `5e5b19a` rather than
  inherited — together with the exact number of tests added under
  `tests/unit/support/`, declared by every task that adds one. The parent slice
  held the strong form with no exclusion and warned that weakening it to
  "unchanged unless a task says otherwise" would let a silently dropped test net
  against a newly added one. That warning is honoured by making the exclusion
  *exact* rather than open: the number inside is declared per commit, and it
  only ever rises.

### Ordering against the other proposed changes

**Conflict-prone**, like both predecessors: it touches 103 test files — 52 of
them by more than one name's commit pair — so it does not run concurrently with
anything else that edits `tests/` broadly.

**`unify-launch-adapter-dependencies` must follow it**, which
`docs/proposed-change-order.md` §4 already records — with the correction that
what this change hands it is a narrowed reader population and three newly
measured probe sites, not four dead branches.

**A third slice remains.** 291 of the 482 declarations in the 27 recurring
names are untouched here, and the largest group of them — the launch, playbook
and catalog stores — is blocked on the same composition rule that ordered this
one: they become reproducible when `_playbook()` and `_hold()` are shared, which
is work no proposed change currently owns. That is recorded in
`docs/proposed-change-order.md` on archive, not left implicit in a count.
