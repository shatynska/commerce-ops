## Context

`share-the-unit-test-harness` (archived 2026-09-04) shipped `tests/support/`
with the playbook constants, the HTML harness, the admin session, the fixture
literals and the `step()` builder. `share-the-value-doubles` (archived the same
day) added `tests/support/values.py` — `Member`, `MemberValue`,
`CatalogProduct`, `Record`, `TaskMapping`, `PendingRow`, `FakeTask`,
`CreatedTask` — replacing 166 of 186 local declarations, 163 as aliases and 3
as adapters. `tests/support/` is imported and never collected; `testpaths`
names the three tiers, as does every hook and CI step.

This change takes the doubles with *behaviour*. `proposal.md` states the
population, the scope and the rules that decide it. This document settles the
four questions the handoff from the parent slice said had to be settled before
any code: what replaces the equality proof, where the migration boundary falls,
whether `FakeMembers` drops its two extra spellings, and how
`tests/unit/support/` interacts with the count invariant.

Measurements were taken against `main` at `5e5b19a` on 2026-09-04, by AST over
`tests/**/*.py` and `src/**/*.py` excluding `__pycache__`. Counts are of
module-level class declarations unless stated otherwise.

**By AST, and not by grep, deliberately.** The parent slice recorded that
`^class _Record:` matches 31 files against 30 declarations, the 31st being
source text inside a subprocess driver script. The same discipline produced this
change's reader-shape table, where a spelling-shaped sweep finds none of the
four. Where this document states a count, it was taken structurally; where a
task re-measures one, it re-measures structurally.

## Goals / Non-Goals

**Goals.**

1. One shared declaration per stateful fake in scope, so the next test arranges
   from `tests/support/` rather than writing a forty-fourth `_FakeMembers`.
2. Every migrated file exercises exactly the behaviour it exercises today —
   verified by a proof that compares behaviour where it can run, and by a
   recorded exemption where it cannot.
3. Every double sitting opposite a reader-shape probe presents **one** reader
   shape, so `unify-launch-adapter-dependencies` inherits a narrowed population
   and a measurement of what remains, rather than the reason the probe exists.
4. `tests/unit/support/` exists, with the shared fakes' own behaviour under
   test, so the next slice inherits a place to put contract tests rather than
   an argument about whether they belong.

**Non-Goals.**

- Deleting any production tolerance. That is
  `unify-launch-adapter-dependencies`. This change narrows and measures; it does
  not touch `src/`.
- The other 291 declarations in the recurring names. `proposal.md` names them
  and why; the largest group is blocked on the same composition rule that
  ordered this change after the value doubles.
- Replacing a fake with production's real type. A real `PostgresMembers` needs
  a session; the point of the double is that it does not.
- Making the shared fakes general. A shared fake reproduces the behaviour the
  measured population had. A parameter that no measured declaration needs is not
  added because it might be wanted.

## Decisions

### 1. The local name is rebound to the shared fake, by alias or by adapter

As in the parent slice: the local declaration is deleted and the local *name*
is rebound, so nothing at or below the file's first test byte changes.

```python
from tests.support.fakes import FakeStepStore as _FakeStepStore
```

Where the shared fake can produce the exact behaviour but cannot take the call
site unchanged — a hard-coded roster, a different default, a class attribute —
the file declares an adapter subclass instead:

```python
class _FakeMembers(FakeMembers):
    def __init__(self) -> None:
        super().__init__((_Member(ALICE, ALICE_NAME),))
```

Both forms keep every call site, annotation and assertion identical. 114 of the
expected 175 migrations are the first form and 61 the second, which
`proposal.md` states up front because the ratio is far from the parent slice's
and a reviewer should not have to infer it from the tasks.

**For the seven paired names, the adapter is written at the settle commit and
specified at the instrument commit** by the pairing's `build=` argument
(Decision 2). `StubDate`'s 15 adapters are the exception and are written
directly: that name is proof-exempt, carries no `@paired` line, and its adapter
sets a `ClassVar` rather than calling a constructor, which an instance factory
cannot express. This ordering is
deliberate and it is the answer to an ambiguity worth naming: pairing a local
against a *bare* shared fake would report a divergence for every one of the 61,
because a bare `FakeMembers()` has an empty roster where the local has a fixed
one. Those 61 reports would be artefacts of the pairing rather than findings,
arriving at exactly the moment a migrator is deciding whether to keep a local —
which is where a rule gets relaxed. So **for the 61 clause (c) declarations**
the shared side is not built from the local's call: it is built by a factory the
`@paired` line carries, and that factory *is* the adapter's `__init__`, written
once and then moved. The 114 aliases have no such mismatch and take the default,
where the local's own call constructs both sides.

### 2. The lockstep proof: how it is built, what it catches, what it cannot reach

**This is the decision the change turns on.** The parent slice's field
comparison is inexpressible here. Its designed substitute — `_conforms` typing
plus a written note — states plainly that risk 3, *the shared fake keeps the
whole surface and behaves differently behind it*, is caught by nothing.

The substitute this change uses instead is a **lockstep pairing**. During a
name's instrument commit, each local declaration is decorated:

```python
@paired(FakeStepStore)
class _FakeStepStore: ...
```

or, where the local's call cannot construct the shared side —
the clause (c) population — with the factory that will become the adapter:

```python
@paired(FakeMembers, build=lambda: FakeMembers((_Member(ALICE, ALICE_NAME),)))
class _FakeMembers: ...
```

The decorator's signature is `paired(shared, *, build=None, state=None)`:

- **`shared`** is the shared fake, used to construct the paired instance from
  the local's own call arguments when `build` is absent.
- **`build`** is a zero-or-more-argument factory receiving the local's call
  arguments and returning the shared instance. Where it is present, the local's
  arguments do not reach the shared fake directly, and the factory's **argument
  expression** is copied into the settle commit's adapter unchanged — the two
  forms differ (`lambda: FakeMembers((...))` against `super().__init__((...))`),
  and it is the expression, not the wrapper, that carries over.
- **`state`** is a **name map**, not a projection: `{local_attribute:
  shared_attribute}`, applied to the local side's keys before comparison. It is
  deliberately not an arbitrary callable, because a callable applied to both
  sides can normalise two different values into agreement, which is the one way
  a state comparison can be made to pass by writing it. The default is empty,
  and the comparison is then over `vars(obj)` on both sides.

  Each shared fake **stores under the dominant local spelling**, which is what
  `AGENTS.md`'s field-spelling rule already requires and what keeps the maps
  rare. Measured over instance attributes — which is what `vars()` reports, and
  so the only partition that decides a comparison — the 43 `_FakeMembers` split
  **14 storing `_members`, 9 storing `members_rows`, and 20 storing nothing at
  all**, the last because they hard-code the roster inside `list_members`. The
  shared fake stores `_members`, the dominant spelling; the 9 include one of the
  two kept declarations, so **8 carry `state={"members_rows": "_members"}`**,
  the 20 see `_members` as a shared-only note, and no other name needs a map —
  the stores agree on `records`/`rows`/`version`/`saves` across every migrating
  declaration. Every map used is recorded at task 12.3.

  That partition is by *stored attribute*, and it is not the constructor
  partition that decides alias against adapter: by signature the same 43 split
  20 with no `__init__`, 7 taking none, 10 taking a tuple, 5 taking varargs and
  1 taking an optional. The two are counted separately because they decide
  different things, and reading one as the other is how the figures stop adding
  up.

**The wrapped set is every function the local's class body declares except
`__init__`** — dunders included, because `__contains__` and `__iter__` *are*
the surface for two of the nine names. `classmethod`, `staticmethod` and
`property` objects are **not** wrapped; see the exemption below.

**A name the local declares and the shared fake does not is not wrapped**, and
this is the case clause (e) creates. The decorator checks for it at decoration
time rather than discovering it as an `AttributeError` mid-call: the name is
left unwrapped, and it is recorded as a **silent pairing**, naming the class and
the method. Where that name is not one of clause (e)'s three, the decorator
**fails at decoration** with that message — a shared fake missing a method the
local has is Decision 3(a)'s failure, and finding it at import time is better
than finding it on whichever call happens to run first.

Each wrapped call **returns the local's value and re-raises the local's
exception** — the local is the object production holds, and the pairing must not
change what it answers. A divergence is reported by **raising**, so it is a test failure rather than a
line in a log: a recorded-and-continue divergence would give a signal no finer
than "still green", which is the property this decision distinguishes itself
from below. **What it raises is not an `Exception`.** Production wraps
collaborator calls in `except Exception` in several places, and any of those
would swallow a divergence and leave the commit green — restoring exactly the
failure mode raising was chosen to prevent. The divergence goes through
`pytest.fail`, whose `Failed` derives from `BaseException`, so no
`except Exception` in the code under test can absorb it.

**Construction is intercepted**, and this is what makes the claim about initial
state mean anything: the decorator wraps `__init__` to capture the local's
arguments, build the twin, and compare state once before any call. `__init__` is
excluded from the *compared-call* set, not from interception — a fake whose
initial state differs in an attribute no executed call touches is caught there
and nowhere else.

Each wrapped call runs on both instances and compares:

- the **return value**, by `==`;
- the **raised exception**, by type and by `str()` — and one side raising while
  the other returns is a failure;
- the **instance state** afterwards, as the `state` mapping of each.

The state comparison has three cases and they are not symmetric:

| case | verdict |
|---|---|
| an attribute on the local, not on the shared | **failure** — the shared fake models less |
| an attribute on both, differing in value | **failure** — the divergence this exists to find |
| an attribute on the shared, not on the local | recorded in the note — a licensed superset, governed by `AGENTS.md`'s completeness rule |

The two non-fatal observations — a silent pairing, and a shared-only attribute —
are emitted as `warnings.warn`, not printed. Under pytest's default capture,
output from a passing test is discarded, so a note with no channel is a note
nobody reads; a warning is collected in the run's summary and survives a green
suite. Task 12.3 gathers them, which is what makes Decision 6's enumerated table
falsifiable: an addition outside it shows up as a warning against a declaration
nobody predicted.

Because `state` is the *instance* attribute mapping, a class-level alias such as
`_FakeMembers.members` is outside it. That is the intended reading: the alias is
a surface question, settled by clause (e) and its measurement, not a state one.

**Why the comparison is expressible at all**, when `==` on two fakes is
identity: both instances hold the *same argument objects*, so a returned tuple
of members compares elementwise by identity and is equal; the value doubles the
stores hold are shared types as of the parent slice, so where a fake builds a
record internally the record's own `==` is structural. That is the composition
foundation the parent slice was ordered first to supply, and it is what makes
this proof possible rather than merely desirable.

**This is not the harness the archived plan rejected.** That plan considered
"a behavioural harness running each file's tests against both fakes" and
rejected it as costing a second run of the suite for a signal no finer than
"still green". The lockstep pairing runs the suite once, and its signal is a
per-call comparison of return value, exception and state — the resolution the
rejected option lacked. The rejection's ground does not carry over; the
alternative it rejected is still rejected here.

**Verified before proposing.** A spike over two measured `_FakeStepStore`
bodies and a shared candidate passes on both, projects state where the local
stores less than the shared, and on a local mutated to skip its version bump
reports the difference. The spike is in the change's scratchpad, not committed.

**What it catches** that nothing in the parent slice's design did:

- a different mutation effect (the version bump above);
- a different return shape or ordering, on every call the suite executes;
- a different response to an absent or unknown key, where a test executes one;
- a different initial state, at construction, before any call;
- an assertion the local made and the shared does not, and the reverse.

**What it does not catch**, stated as flatly:

- **behaviour on a path the suite never executes.** The proof intercepts
  executed calls. A method no test reaches is proved by nothing, and the
  contract tests of Decision 7 exist for exactly that region.
- **a surface the shared fake adds.** The decorator wraps the methods the
  *local* declares; a method only the shared has is never invoked, so a
  production probe that starts finding it after the settle commit is outside the
  proof. This is the parent slice's risk 4, and its same-value invariant governs
  it — Decision 6.
- **a surface the shared fake drops.** Clause (e)'s three spellings are never
  executed under pairing, because the local declares them and nothing calls
  them. Their pairing is silent, and the measurement of task 11.1 — not the
  proof — is what licenses the drop.
- **it reports a false positive** — not a miss — where a fake constructs a new
  object internally that is neither a shared type nor a production dataclass:
  two separately constructed objects with identity `==` compare unequal, so the
  pairing is loud rather than silent. Like clause (d)'s residual risk, the
  failure mode is a noisy proof, and the remedy is a recorded exemption for that
  declaration rather than a weakened comparison.
- **anything about a declaration the proof cannot run on**, which is the next
  paragraph and clause (d).

**Two of the nine names are proof-exempt, and it is recorded rather than
discovered.** `StubDate` (15 declarations) constructs no instance and exposes
one `classmethod` over a `ClassVar`; `FakeSlackResponse` (13) subclasses `dict`
and exposes one `property` over the payload. There is nothing for the decorator
to intercept in either, and extending it to classmethods, properties and builtin
payload state would be real work for the two names where the base class carries
the whole substance. **28 of 191 declarations — 15% — therefore migrate on
clauses (b) and (c), `mypy`, and their contract tests, with no proof at all.**
That is stated here, and again at tasks 3.2 and 5.2, because Decision 9 spends
an integration-tier run to avoid three declarations settling with the check
silently skipped, and a silent skip fifteen times that size must not be the one
nobody wrote down.

### 3. The migration boundary, stated before the first file

`proposal.md` carries the rule with all five clauses; this is why each is there.

**(a) Surface subset, plus behavioural equality on every executed call.** The
proof asserts it where it runs. Stating it as a rule as well matters because the
proof is silent about unexecuted paths and absent for two names, and a migrator
who has only the proof will read its silence as assent.

**(b) Declaration form, including the base class.** Neither field comparison nor
behaviour comparison can see form. `_StubDate` subclasses `date` and
`_FakeSlackResponse` subclasses `dict[str, Any]`; for both, the base class *is*
the double — a `StubDate` that does not subclass `date` fails `isinstance`
checks inside production date handling, and a `FakeSlackResponse` that is not a
`dict` cannot be indexed. For the two proof-exempt names this clause and `mypy`
carry the whole weight, which is why it is stated before them rather than after.

**(c) Constructor compatibility, else an adapter.** A behaviour set is not a
signature. `_FakeMembersStore` is declared with a default `version` of 13, 11,
7, 5, 3 and 0 across the population, and `_FakeStepStore` with 41 and with a
module constant. A file whose call site is `_FakeMembersStore()` and whose
assertions read version 7 cannot alias a shared fake defaulting to 13. The
remedy is a four-line adapter, specified at the instrument commit by `build=`
(Decision 1), not an exclusion.

**(d) Effects confined to the instance.** This is what makes the proof sound:
the pairing runs both fakes, so a local that appends to a module-level list,
writes a file, or mutates an object the test also holds would perform that
effect **twice**. Measured over all 191 declarations — an AST pass for a write
whose target is not `self`, or a call to `append`, `add`, `extend`, `update`,
`write`, `pop` or `insert` on a bare name — the clause has exactly six hits, and all six are the `_FakeMembersStore`
declarations threading an external version cell, which clause (c) already keeps.
**So the clause excludes nothing this change plans to migrate.** It stays,
recorded as measured-inert, because it is what makes the proof sound and because
the next slice's population is not measured.

**(e) A dropped spelling must be measured dead.** Clause (a) forbids the shared
fake modelling less than the local, and Decision 2's state table calls that a
failure. Three spellings are dropped anyway —`_FakeMembers.members` (32 of 43),
`_FakeMembers.__call__` (36 of 43) and `_FakeHandlerRegistry.__iter__` (12 of
12) — and without this clause the boundary would forbid the change's third
goal at its two largest names. The clause licenses a drop **only** on a
measurement taken at the commit that drops it, showing no production site and no
test reaches the spelling; Decision 5 records the measurement and task 11.1
re-takes it. Nothing else in this change is dropped, and the clause names its
three cases rather than describing a category, so it cannot be stretched at
implementation time.

The boundary is checked per declaration, not per body. The parent slice ended at
an exact whole-body match by inference and took 13 of 95 `_playbook` as a
result; here `_FakeStepStore` has eleven bodies of which seven differ only in
whether they record `saves`, which is a licensed superset rather than a
divergence.

### 4. Composition decides scope, and the scope is nine names

`proposal.md` states the rule and the excluded names. The rule is worth naming
once more as a rule, because it is the third change in a row that it has
decided: **share the base before the composer.** `_Member` before
`_FakeMembers`; `_FakeMembers` and `Record` before the stores that hold them;
`_playbook()` and `_hold()` before `_FakePlaybooks` and `_FakeLaunches`, which
is why those are not here.

The rule is *testable* rather than assumed, and this change tests it. The
handoff from the parent slice asks for exactly this: if the stores cap at a
partial hit rate, partition the outcome on whether the file's leaf migrated.
`tasks.md` 12.3 records that partition. A store whose file kept a local leaf and
which then fails clause (a) is evidence for the rule; a store that migrates
regardless is evidence the rule is over-cautious, and either finding is worth
more than the assertion.

### 5. One reader shape per double, and every drop is measured

Three spellings are dropped under clause (e). The archived plan licenses the
first two on the grounds that they exist only to satisfy a probe's branches;
this change does not take that on trust, and adds the third from its own
measurement.

- **`_FakeMembers.members` is read by nothing.** Zero production sites and zero
  test call sites, by AST over `src/` and the 43 files. The four reader probes
  read `list_members`, `names`, or the collaborator itself.
- **`_FakeMembers.__call__` is unreachable while `list_members` exists.** Both
  members probes reach `callable(...)` only after the `list_members` branch
  misses, and all 43 declare `list_members`. Zero tests invoke an instance.
- **`_FakeHandlerRegistry.__iter__` is unreachable, and needs one measurement
  the other two do not.** Both `_registered_names` sites iterate the
  collaborator only when `names` is not callable, and all 12 declare `names()`;
  zero tests iterate an instance. But `__iter__` is also the interpreter's
  fallback for `in`, and `automation_pass:770` evaluates `name in handlers`
  directly — so a static search for iteration cannot see the path that would
  exercise it. Measured per declaration: **all 12 declare `__contains__`**, and
  so do all 8 `_FakeHandlers` (none of which declares `__iter__` at all). No
  membership test in the suite resolves through iteration, so the drop removes
  no live mechanism. Task 7.1 additionally re-takes this **by execution** —
  making the local `__iter__` raise and running the commit tier — because a
  spelling the interpreter can reach implicitly is exactly the case
  `docs/deferred-work.md`'s standing rule says not to settle on a static
  reading.

`_FakeMembers.member(id)` is *kept*: a genuine second query, six files use it,
and no probe chooses between it and anything else. `FakeHandlerRegistry` and
`FakeHandlers` keep `__contains__`, because `automation_pass:770` evaluates
`name in handlers` directly rather than through a probe — a call, not a
convention, and clause (e) does not reach it.

**The claim this licenses is narrower than "the tolerance closes",** and
`proposal.md` states it at that width. What closes is that no double in these
three populations — other than the two `_FakeMembers` the boundary does not
reach, which keep their own declarations and their own spellings — presents more
than one shape. What remains open is the rest of
the reader population — `_StoreShapedMembers`, `_ReaderMembers`, `_Members` and
a module-level `_members()` at 17 call sites, and whatever bare iterables are
passed as handlers — which this change measures and hands on.

### 6. Completeness carries the same-value invariant with it

`AGENTS.md` records the invariant and the parent slice's reasoning: where a
shared double adds a spelling a production probe reads *earlier* than the one
the local variants populated, the added spelling carries the same value as the
one it displaces, and an added attribute a probe reads as a guard defaults to
the value the fall-through produced.

**Every addition in this change is enumerated here**, because an addition that
is governed by the rule and not listed is indistinguishable from one nobody
considered:

| addition | over how many locals | why it displaces nothing |
|---|---|---|
| `InertBackoff.note`, `.read`, `.rollback` | 2 | each returns `None`, which is what absence produced at the one guarded call site; task 6.3 searches `src/` and `tests/` for a `getattr` or `hasattr` on them before it is accepted |
| `FakeStepStore.saves` | ~11 | an attribute no production reader probes; task 8.2 records the search |
| `FakeStepStore`'s stale-write assertion | ~19 | a strengthening, not a spelling; Risks and task 8.3 |
| `FakeMembersStore.saves` | ~2 | as above; task 9.1 records the search |
| `FakeCatalogPort.fails` | 14 | a constructor flag defaulting `False`, reachable only when a call site sets it — 2 of the 16 `_Catalog` declarations carry it and 14 do not, which is the column's convention throughout this table; task 10.1 records the search |
| `FakeMembers.member` | 37 | a method no probe chooses between; production calls it by name where it calls it at all, and task 11.2 records the search establishing it |
| `FakeMembers._members` | 29 | the roster attribute, stored under the dominant local spelling (14 of the 43) and **private**, so no probe reads it; it appears in the state comparison, not on the surface, and the 29 locals that store it under another spelling or not at all see the difference there, not on the surface. Task 11.2 records that a private attribute is outside every probe |

Two cases that look like risk 4 and are not, recorded because the resemblance is
the trap: `FakeHandlerRegistry` and `FakeHandlers` both already provide
`names()` in every declaration, so `_registered_names`' first branch already
fires and the shared fake displaces nothing.

### 7. `tests/unit/support/`, contract tests, and the count invariant

`tests/unit/support/` arrives with this change, as `AGENTS.md` says it will. It
names no bounded context because its subject is the harness itself, and it sits
under `tests/unit/` so the shared fakes' behaviour is collected and run at
commit time by the existing hook and CI step — no configuration changes, and
`deploy-pipeline`'s requirement, which names the tiers by path, stays satisfied.

**What goes in it.** One module per shared fake, asserting the contract the
migration relies on and the proof cannot reach: the initial state before any
call, the return shape of each method, the response to an absent or unknown key,
the effect of each mutation, and — where the fake has one — the assertion it
makes about its own arguments. These are the statements the surface-and-behaviour
note would otherwise make in prose, written as tests, which is the improvement
available here that was not available to the parent slice. For the two
proof-exempt names they are not an improvement but the *primary* check, and
`tasks.md` says so at 3.1 and 5.1.

**The count invariant.** The parent slice held all three tiers exactly with no
exclusion, and warned that weakening it to "unchanged unless a task says
otherwise" would let a silently dropped test net against a newly added one. That
warning is honoured here by making the exclusion exact rather than open. Per
commit:

> `tests/unit` collected outside `tests/unit/support/` is 2,246; `tests/agents`
> is 236; `tests/integration` is 159. `tests/unit/support/` collects exactly the
> number of tests the commit's task declares, and that number only ever rises.

Both halves are checked on every commit, so a dropped test cannot be masked by
an added contract test — the two live in disjoint sets and are counted
separately. **Every task that adds a contract-test module requires its implementer to
declare that number in the task, at the commit that adds it** — the numbers are
not fixed in `tasks.md`, because they follow from the contract each fake turns
out to need. What is fixed is that a number is declared and that it never falls,
which is what keeps the second half from degenerating into the open form this
decision exists to avoid.

The decorator's own three proof-cases (task 2.2) live in the change's
scratchpad and are **never committed**. Committing them under
`tests/unit/support/` would raise the declared count and then lower it again
when task 12.1 deletes `_paired.py`, against "only ever rises"; and their
subject is a temporary instrument, not the harness.

The three baselines were measured on this worktree at `5e5b19a`, not inherited.

### 8. `_conforms` typing, and protocols that are meant to be deleted

Per `tests/support/protocols.py`'s standing rule: a `Protocol` declared beside a
double checks nothing on its own, because `mypy` compares a class to a protocol
only where a value is assigned to a protocol-annotated target. So each shared
fake carries, beside it:

```python
_conforms: MembersReaderShape = FakeMembers()
```

A protocol declares a name a probe reads as a **`@property`, never as a
variable** — `mypy` treats a protocol variable as settable, so the variable form
makes the `_conforms` line a type error. For this population the members are
mostly methods rather than attributes, so the trap bites less often than it did
in the parent slice; the rule is restated because the next slice's fakes will
have attributes.

Each protocol is written against **what production reads**, not against what
the real collaborator offers. That is why `FakeHandlerRegistryShape` declares
`names()` and `__contains__` and not `__iter__`, even though the real
`handler_registry` documents itself as iterable: the protocol's job is to fail
when the double stops matching the calls production makes of it.

**`StubDate` needs the class-object form, and that is a second `mypy` trap worth
recording beside the `@property` one.** `date` requires three constructor
arguments, so `_conforms: DateShape = StubDate()` cannot be written; and the
surface production reads is a classmethod, not an instance attribute. Its
assignment is therefore `_conforms: type[DateShape] = StubDate`, which asks
`mypy` whether instances of the class satisfy the protocol without constructing
one. All nine fakes carry a protocol and a `_conforms` line; this is the only
one that carries it in that form, and task 5.1 states it.

Each protocol is added by the task that adds its fake, never up front: the shape
comes from reading the variants being replaced. They live in
`tests/support/protocols.py`, whose docstring already says they are temporary
and that `unify-launch-adapter-dependencies` owns the production-side ones.

### 9. Two names run the integration tier at both of their commits

Every task's default verification is the commit tier, because that is what
`pre-commit` runs and it is where 188 of the 191 declarations live. Three are
not:

| declaration | file |
|---|---|
| `_FakeMembers` | `tests/integration/launch/test_seeded_step_fields.py:579` |
| `_FakeSlackResponse` | `tests/integration/launch/test_slack_entry_confirmation_last_resort.py:214` |
| `_FakeSlackResponse` | `tests/integration/launch/test_slack_entry_start.py:264` |

Two things happen in those files that the commit tier cannot see, and they
happen at *different* commits. At the instrument commit the lockstep proof runs
inside the instrumented instance, so it executes only when the suite that drives
that instance runs. At the settle commit the local is deleted and the name
rebound, so a broken import or a mistaken adapter lives there and nowhere else.
Verifying only the first would leave the second claimed green by a tier that
never imports the file, which is the failure mode `AGENTS.md`'s worktree section
already records.

So `FakeMembers` runs the integration tier at **both** its commits, with
`COMMERCE_OPS_REQUIRE_DATABASE=1` so a skipping tier fails rather than reporting
green.

**`FakeSlackResponse` runs it at the settle commit only**, and the asymmetry is
the point of stating this per name rather than per tier. That name is
proof-exempt (Decision 2), so its instrument commit adds a shared fake, a
protocol and a contract-test module and **touches neither integration file** —
there is no decorator to add, so there is nothing in those files for the tier to
verify. Its settle commit deletes both locals and rebinds the name, which is
where a broken import lives. Running the tier at its instrument commit would
cost a database round for a commit that cannot break those files; an earlier
draft of this decision claimed otherwise and was wrong.

The other seven names run it at neither, and paying that cost three times rather
than eighteen is why this is stated per name.

### 10. Assertion identity, checked as syntax trees, across the commit pair

Decision 1 makes the region below the first test byte-identical for every
migrated file, so this is a belt on top of a rule. It is kept because the parent
slice's experience is that the rule is the thing people are tempted to relax.

For every migrated file, collect four node kinds and compare `ast.unparse` of
each whole node before and after; the multiset must be identical, and the count
of `def test_` / `async def test_` unchanged: every `ast.Assert`; every
`pytest.raises` `With` item; every `ast.Expr` wrapping a call whose callee tail
starts `assert` or is `fail`; and every `@pytest.mark.parametrize` decorator.

Baseline on this worktree at `5e5b19a`: **6,623 / 238 / 759 / 172**, over 2,192
test functions. `~/share-the-stateful-fakes/assert_identity.py` implements all
four kinds; its `REPO` constant already points here.

**`tests/unit/support/` and `tests/support/` are both excluded, from all four
multisets and from the test-function count.** The contract tests are new
assertions by construction, so a whole-tree comparison at head would differ from
the baseline in every kind — and a check that fails by construction is a check
someone relaxes. `tests/support/` is excluded for the same reason and one
better: `FakeStepStore` and `FakeMembersStore` carry a stale-write `assert` in
their bodies (Decision 6), so `tests/support/fakes.py` adds `ast.Assert` nodes
that persist at head, and the files there are imported rather than collected —
they are not tests, and their assertions are not the assertions this check is
about.

**The exclusion costs nothing at the baseline**: measured at `5e5b19a`,
`tests/support/` contributes **zero** nodes to all four kinds and zero test
functions, so 6,623 / 238 / 759 / 172 over 2,192 is the figure with the
exclusion or without it. It is needed for what this change *adds* there, not for
what is there now.

**The check runs across the commit pair, never within it.** The instrument
commit adds a decorator whose module contains assertions, so running the check
against the intermediate commit reports a difference by construction. The
comparison is between the commit before a name's instrument commit and the
commit after its settle commit; task 12.2 additionally runs it base-to-head,
which is what catches drift accumulated across pairs on the 52 files that more
than one name touches.

### 11. One name, two commits

Instrument then settle, per name: the instrument commit adds the shared fake,
its protocol, its contract tests and the `@paired` decorator over the local
declarations **that are expected to migrate**, leaving the locals in place; the settle commit deletes the locals,
rebinds the names, and — for the seven paired names — writes the adapter
subclasses from the `build=` factories the instrument commit carried.
`StubDate`'s 15 adapters have no factory to come from and are written directly
(Decision 1). Nine names, eighteen commits, each green under
the verification its task names — which for `FakeMembers` and
`FakeSlackResponse` includes the integration tier at both commits.

**A declaration the pairing rejects or which diverges carries no `@paired` line
in the committed tree**, and this is the one place the procedure differs from
the parent slice's. Undecorated is **not** the same as kept: there are three
states, not two. A declaration may be *migrated and proved*; *kept*, because the
shared fake cannot reproduce it; or **migrated with the proof exempt** —
undecorated because the pairing reported a false positive of the kind Decision 2
names, and migrated anyway on clauses (a) to (c), `mypy` and the contract tests,
with the reason recorded at task 12.3. Without that third state a spurious
divergence silently converts into a lost migration, and the 175 under-delivers
for a reason that reads as structural. Sixteen declarations are predicted keeps, and a keep is
exactly a local the shared fake cannot reproduce: `_FakeStepStore`'s `loads`
counter and `_FakeMembers`' two put an attribute on the local that is not on the
shared, which Decision 2 calls a failure, and the `_Catalog` declaring only
`__call__` names a method `FakeCatalogPort` does not have, which the decorator
rejects at decoration. Decorating them would make four of the nine instrument
commits red or uncollectable by construction — at the moment Decision 1 names as
where a rule gets relaxed.

So the working procedure is: **decorate every local in the working tree, run,
then drop the decorator from the rejects before committing**, recording each at
task 12.3 with its reason. The predicted sixteen are named per name in
`tasks.md`, so the flow confirms a structural expectation rather than
discovering it; a seventeenth is a finding, and task 8.3 is what it is for. The
committed instrument commit is therefore green under its own verification, and
this decision's "each green" holds as written.

`tests/support/_paired.py` is the decorator's home and it is **deleted by the
last settle commit**, like the parent slice's `_instrument.py`. A proof that
outlives the migration is a permanent dependency on a temporary arrangement.

## Risks / Trade-offs

**Two names carry no proof, and that is a deliberate trade.** 28 of 191
declarations — `StubDate` and `FakeSlackResponse` — rest on clause (b), `mypy`
and their contract tests. All three must actually be there: `mypy` checks a
double against a protocol only where a `_conforms` assignment exists, so both
names carry one, `StubDate` in the class-object form Decision 8 records. The alternative is extending the decorator to
classmethods, properties and builtin payload state for two names whose whole
substance is a base class and one constant. The exemption is recorded in
Decision 2 and in both tasks, so that a green instrument commit for those names
is never read as a proof that passed.

**The proof doubles execution, and clause (d) is how that is contained.** Every
paired call runs twice. For a fake that is pure state this is invisible; for one
with an external effect it is a defect the proof itself introduces. Measured,
the clause excludes nothing this change migrates. The residual risk is a
declaration whose external effect is not visible in its own body — one that
mutates an object it was handed. The state comparison would report that as a
difference, because both instances hold the same object and the second call
would see the first's mutation, so the failure mode is a noisy proof rather than
a silent one.

**The strict-save decision may break tests that pass today.** Half the store
population asserts `expected_version == self.version` inside `save`, and half
does not. The shared fakes take the *stricter* behaviour, because a fake that
silently accepts a stale write is a fake that hides an optimistic-concurrency
defect. A file whose test saves with a stale version deliberately will fail
under the shared fake — and will fail *loudly, at the instrument commit*, where
the proof compares the local's silence against the shared's assertion. Such a
file keeps its own declaration and the reason is recorded. This is a deliberate
trade of a possible per-file exclusion against a real improvement in what the
shared fake checks.

**Sixty-one adapters is a smaller win than 114 aliases.** Recorded rather than
smoothed over. The gain is that the surface becomes uniform even where the
contents do not, which is what the reader-shape work needs, and that a future
change to the fake's behaviour lands in one place.

**Nine names leaves 291 declarations.** This change does not finish the fakes,
and says so in `proposal.md` rather than implying completeness by silence. The
alternative — one change over 482 declarations — is the change
`docs/proposed-change-order.md` §4 originally proposed at 455, and it is the one
the parent slice split precisely because a single reviewer cannot hold it.

**The contract tests could drift from the fakes' real use.** A contract test
asserts what the shared fake does, not what any caller needs. That is the same
risk every unit test of a library carries; the mitigation is that the contract
tests are written *from the measured population's behaviour*, at the same commit
that measures it, rather than from the shared fake's implementation.

## Migration Plan

Nine names, instrument-then-settle, in ascending order of difficulty so the
machinery is proven on the simple population before it meets `_FakeMembers`:
`FakeSlackResponse` (13), `FakeHandlers` (8), `StubDate` (15), `InertBackoff`
(9), `FakeHandlerRegistry` (12), `FakeStepStore` (37), `FakeMembersStore` (38),
`FakeCatalogPort` (16), `FakeMembers` (43).

Each name is independently revertible: its two commits touch only its own
declarations, its own shared fake and its own contract-test module. Fifty-two of
the 103 files are touched by more than one name — up to five — so a revert of
one name's pair is clean while a revert of a file's history is not; task 12.2's
base-to-head run is what covers the accumulation.

## Open Questions

None blocking. Three are settled here that the handoff left open, and are
recorded so a reader does not reopen them: `FakeMembers` **does** drop `members`
and `__call__` (Decision 5, on measurement rather than on the archived licence);
`FakeHandlerRegistry` **does** drop `__iter__`, on the same measurement, which
the handoff did not anticipate; and `tests/unit/support/` interacts with the
count invariant by **exact declaration rather than exclusion** (Decision 7).

One is deferred by design: whether the shared fakes should eventually be
replaced by production's real types behind an in-memory adapter. That is the end
state `unify-launch-adapter-dependencies` gestures at, and it is not decidable
until the production-side protocols exist.
