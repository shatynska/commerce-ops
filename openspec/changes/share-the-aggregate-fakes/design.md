## Context

See `proposal.md` — *Why*. The measurements it records are the input to every
decision below; none of them is a judgement made at the keyboard.

Two constraints from the tree shape everything here.

**Production does not probe these collaborators' own surfaces by shape.**
There is no `getattr` name-probe, no `hasattr` and no `except AttributeError`
anywhere in `src/commerce_ops/launch/` for a launch store, a playbook store or a
product reader. That is what separates this slice from `share-the-stateful-fakes`,
where ten `getattr` probes made every added spelling a hazard. Here a shared
double may present a superset of the *methods* a local presented, because
nothing in production can branch on their presence.

**The licence stops at the surface and does not reach what a double serves.**
`automation_pass.py:563` reads `getattr(product, "name", None) or getattr(product,
"sku", None)` — a probe over the served value, not over the reader. `AGENTS.md`'s
same-value invariant governs there, unchanged: a served object that models more
than the local's can still redirect that probe to an earlier branch.

**The proof splits by what a store serves**, so this change carries two
instruments, and every declaration's disposition names which one closed it.

## Goals / Non-Goals

**Goals:**

- Five shared types in `tests/support/fakes.py` — `FakeProductReader`,
  `FakePlaybooks`, `AsyncFakePlaybooks`, `FakePlaybookRepository`, `FakeLaunches`,
  over a shared `_FakePlaybooksBase` — taking 124 of the 129 declarations, each
  with its **own** `_conforms` protocol assignment and contract tests under
  `tests/unit/support/`. Five, not four: the sync and async playbook stores are
  siblings with different calling contracts and neither satisfies the other's
  protocol.
- A disposition per declaration naming the instrument that closed it, including
  for the 13 that execute zero calls.
- The two rules this slice establishes recorded in `AGENTS.md`, not only in this
  change.

**Non-Goals:**

- The five scope-sniffing catalog ports. See Decision 6.
- Narrowing any of the fifteen production shape probes `docs/deferred-work.md`
  records. That is `unify-launch-adapter-dependencies`' work and the standing
  rule — *do not narrow one on the strength of a green suite* — applies here
  unchanged.
- Any change under `src/`.

## Decisions

### 1. Four subjects, five types, and the fault lines are measured rather than named

`_FakeLaunches`/`_FakeLaunchStore` and `_FakePlaybooks`/`_FakePlaybookRepository`
each appear together in **zero of the 83 files**, so each pair is one subject
under two names. But `_FakePlaybooks` itself splits 25 sync `get` against 7
async, and `_FakePlaybookRepository` is 10 of 10 async — so the playbook stores
divide **on `await`, across the name boundary**, not along it.

*Alternative considered:* one type per existing name, five in all. Rejected: it
reproduces a split that is an artefact of two authors' naming habits, and it
would still not resolve the sync/async fork, which cuts through one of the
names.

### 2. The playbook store models four measured axes, not only `await`

The 32 `_FakePlaybooks` were classified per declaration, by running the census
over every body rather than reading the largest:

| variant | decls | `get` |
|---|---|---|
| plain — holds a playbook, answers with it | 19 | sync |
| no `__init__`, closes over a module constant | 6 | sync |
| aliases `__call__` to `get` | 4 | async |
| `refusal` + read counter + `__call__` alias | 2 | async |
| `refusal` only | 1 | async |

A type modelling the await alone would serve **25 of 32** — the 19 plain and the
6 constructorless, which need only a call-site argument. The 7 it would not
serve are the 4 aliasing `__call__`, the 2 that also count reads and raise a
refusal, and the 1 that only raises one. (An earlier draft said 23, by
subtracting the three variants without noticing that two of them overlap in the
same declarations.) Each axis is decided
here, so that nothing falls to the generic "keep the local" escape by default:

- **`await`** — **two siblings over a shared base, not a subclass.**
  `_FakePlaybooksBase` holds the constructor, `refusal`, `reads` and a shared
  `_answer()` that increments the counter and *then* raises the refusal — the order both locals use, so a refused read still counts — the three
  belong together because all three happen inside `get`, and without the helper
  the "one state implementation" the split promises is not achievable. The base
  defines no `get`; `FakePlaybooks` and `AsyncFakePlaybooks` each define their own.
  Subclassing and overriding `get` with a coroutine does not type-check, and
  that is mechanical rather than arguable: `uv run mypy` on the two-class form
  reports `Return type "Coroutine[Any, Any, int]" of "get" incompatible with
  return type "int" in supertype "Base"  [override]`, and this file's preamble
  requires mypy green at every commit. The sibling split keeps everything the
  subclass form wanted — one constructor, one state implementation, two calling
  contracts — and costs one class. It needs **two** protocols, sync and async,
  and therefore two `_conforms` assignments.
- **`refusal`** (3) — a constructor keyword `refusal: Exception | None = None`,
  raised from `get`. This is exactly the `FakeCatalogPort.fails` precedent the
  harness already licenses: a keyword defaulting to inert, reachable only where
  a call site sets it, and no production reader probes for the attribute.
- **read counter** (2) — `reads`, **an `int` incremented in `get`**, which is
  what both locals declare (`self.reads = 0` / `self.reads += 1` at
  `test_gate_progression_pass.py:353,356` and `test_advance_and_ask.py:360,363`)
  and what `test_gate_progression_pass.py:843` asserts against: `reads == 1`.
  **No `calls` spelling is derived here.** Decision 7's list-valued `reads` with
  a derived `calls` is measured on the *product reader*, at 6 and 4; on the
  playbook store `calls` has a measured population of **zero**, and adding it on
  a neighbouring decision's authority is the unmeasured-claim failure this
  change exists to remove. The two names are deliberately not unified: this
  suite spells the same word two ways for two different subjects, and
  `AGENTS.md`'s rule is that a double keeps the locals' spelling. **Say so at both
  types.** `AGENTS.md`'s precedent for two shared types disagreeing on a field is
  `clickup_user_id`, whose rule is that each type's docstring names the trap;
  tasks 3.1 and 4.1 carry that obligation here.
- **`__call__`** (6) — **on `AsyncFakePlaybooks`, not on the base.** That
  sizes the superset: on the async sibling it adds the spelling to the 1 async
  declaration lacking it, where on the base it would add it to all 32 playbook-store declarations — the base is shared by `FakePlaybooks` and `AsyncFakePlaybooks` only; `FakePlaybookRepository` takes `(*args, **kwargs)` and does not inherit it. Spelled
  as the six locals spell it,
  `async def __call__(self, *args: Any, **kwargs: Any) -> LaunchPlaybook`
  delegating to `get`, **not** as an `attr = method` alias: an alias to
  `get(self, version="")` narrows the signature to one positional argument,
  where all six locals accept any. Two of the six already delegate to `get` and
  four return the held playbook directly; both answer the same value.

  **This spelling is carried on the same evidence `list_launches` and `all` are
  dropped on, or it is dropped too.** No site in `src/` invokes a playbook
  collaborator as a callable, and `__call__` is exactly the kind of spelling the
  interpreter reaches implicitly — so `AGENTS.md` says to license it by
  mutation, not by search. Task **2.5a** measures it, in §2 and ahead of §4 — for the same reason task 2.5
sits ahead of §3: a superset is licensed before the phase that ships it, never a
phase after. It
  would be incoherent to demand execution-proof before removing two spellings
  and add a third on six declarations' say-so.
- **no `__init__`** (6) — these are constructed as instances
  (`_install(monkeypatch, module, "playbooks", _FakePlaybooks())`), not patched
  as classes, so the call site simply passes the module constant it was already
  closing over. No new type shape is needed; this is a call-site edit the
  migration performs anyway.

*Alternative considered:* one class whose `get` returns an already-resolved
awaitable, satisfying both call styles. Rejected: it changes the calling
contract at 25 sync sites for no gain, and `mypy` cannot express "awaitable or
not" against a protocol, so the `_conforms` assignment — the only thing that
makes a drifted double a type error — would have to be dropped. Note that this
paragraph reasoned about `mypy` at the *protocol* level and missed it at the
*inheritance* level, which is how the subclass form survived two drafts; the
mechanical check above is what settled it.

*Alternative considered for the three refusals:* hold them back as kept locals.
Rejected because the precedent already exists in this file and costs one
keyword; but if the completeness search at task 4.1 finds any production reader
probing for `refusal`, hold them back instead and restate §4 as 39 of 42.

### 3. The class-patched repository gets a call-time class-producing constructor

All ten `_FakePlaybookRepository` are installed as
`monkeypatch.setattr(module, "PlaybookRepository", _FakePlaybookRepository)`, so
production constructs them itself with `(db)`. They cannot be handed a playbook
as an instance, which is why all ten take `__init__(*args, **kwargs)`.

**What each serves splits three ways, measured per declaration:**

| what `get` returns | decls |
|---|---|
| `_playbook()` — the file's own builder | 5 |
| an inline `LaunchPlaybook(...)` built in the method body | 4 |
| `_SERVED[0]` — a module-level list rebound inside two tests | 1 |

`FakePlaybookRepository.serving(source)` returns a *subclass* whose `get` reads
`source` at call time: a `LaunchPlaybook` is answered directly, a zero-argument
callable is invoked per call. So the four inline bodies become
`serving(playbook(...))`, the five become `serving(_playbook)` — the file's own
builder, unfrozen — and the one becomes `serving(lambda: _SERVED[0])`.

**Reading at call time is not a refinement, it is the correctness condition.**
`test_clickup_webhook_automated_step.py` sets `_SERVED[0]` at line 359 to a
playbook with an automated step and at line 398 to one with a human step, to
prove opposite branches — the file's own comment says "only the step's kind
differs". A `serving()` that bound the value at subclass creation would serve
the import-time playbook to both, and both tests would still pass.

*Alternative considered:* a mutable class attribute the test sets
(`FakePlaybookRepository.playbook = p`). Rejected: that is session-global state
shared across every test that touches the class, which is the exact cross-test
leak the shared harness exists to remove. A per-call-site subclass holding its
own callable carries no such coupling — the rejection was about sharing, and
does not reach this form.

*Alternative considered:* bind values only, and exclude
`test_clickup_webhook_automated_step.py` as a kept local, restating §4 as 9 of
10. Rejected: five of the other nine also want their file's `_playbook` read
rather than a value frozen at import, so the call-time form is doing work at six
sites, not one.

### 4. One launch store, presenting every spelling except the two measured dead

The merged type presents `get_by_product_id`, `list_active`, `list_all` and
`save`. It **does not** present `list_launches` or `all`, which 21 of the 26
`_FakeLaunchStore` carry as delegates to `list_all`: both were wrapped at
runtime across all 2,693 tests in all three tiers and recorded **zero calls**,
neither is called from `src/`, and all 23 `tests/` mentions of `list_launches`
are its own `def`. That is the measured-dead licence, taken by execution as the
rule requires rather than by search alone.

Measured across the 58 rather than mapped onto the name split — which is the
error Decision 1 exists to prevent, and which an earlier draft of this paragraph
committed — the methods divide **17 declaring only `list_active`, 25 only
`list_all`, 9 declaring both, and 7 declaring neither** (five `_clickup_webhook*`
files and two `_slack_entry*` ones, which read only `get_by_product_id`). So the
superset reaches further than the name split suggests: 7 declarations gain both
spellings, not one.
It is licensed by the Context above: no production reader can branch on the
presence of either name, so the added spelling is unreachable except by a call
that would today raise `AttributeError` — that is, by a test that does not
exist.

**Four of the 58 cannot be handed their launches through the shared
constructor** — two of them do take `(*args, **kwargs)`, which is variadic, but
discard it — **and each is decided by a named rule rather than left to an escape
hatch:**

- **2 are class-patched** (`test_slack_entry_ack_and_failure_visibility.py:288`,
  `test_slack_entry_unready_playbook.py:279`), taking `(*args, **kwargs)` and
  answering `type(self).launch` — a mutable class attribute, the exact form
  Decision 3 rejects and task 7.2 records as a prohibition. They take `FakeLaunches.serving(source)`.

  **Decision 3's `serving` does not transfer unchanged, so it is defined here
  rather than pointed at.** `FakePlaybookRepository` has one read method and an
  `__init__` that already discards production's arguments; `FakeLaunches` has
  four read methods and a `*launches` constructor. `FakeLaunches.serving(source)`
  therefore returns a subclass whose `__init__(*args, **kwargs)` **discards**
  what production passes it — production constructs the patched class itself
  with `(db)`, and a `*launches` constructor would otherwise accept a `Session`
  and hold it as a launch — and whose four read methods resolve `source` at call
  time. `source` is a `Launch`, an iterable of them, or a zero-argument callable.

  **Call-time reading is inherited by analogy here, not measured.** What made it
  a correctness condition for the repository was `_SERVED[0]` being rebound
  mid-file; whether either of these two rebinds `type(self).launch` after
  production constructs the double is task 5.5b's to measure. It is the safe
  default either way, but the *reason* is not yet evidence.

  The mechanism keeps two declarations that would otherwise be lost to the very
  shape task 7.2 records as a prohibition.
- **2 are `@dataclass`** (`tests/unit/launch/application/test_thread_anchor_resolution.py`,
  `test_thread_establishment_race.py`). `AGENTS.md`'s declaration-form rule makes
  a dataclass/plain-class mismatch a **keep**, not an adapter: field equality
  says nothing about generated `__eq__` and `__repr__`. They stay local unless
  task 5.5a measures that nothing relies on either.

**Expected: 56 of 58 migrated, 2 kept.** Stating the figure is the point — a
phase whose population total is also its target cannot report a shortfall.

### 5. The shared launch store does not implement `list_active`'s filter

The real repository's `list_active` drops launches standing at `graduated`
(`launch_repository.py:181`), and reproducing that in the double is the obvious
"truer to production" move. It is wrong, and the measurement says why:
`list_active` returns a graduated launch in exactly two files —
`test_gate_progression_pass.py`, which walks a launch to `graduated` and asserts
the progression pass then advances it no further, and
`test_automation_pass.py`, the clearer of the two:

```python
async def test_a_graduated_launch_is_left_alone() -> None:
    launch = _graduate(_launch(playbook), playbook)
    collaborators = _Collaborators(launches=_FakeLaunches(launch), ...)
    await _run_pass(collaborators)
    assert not handler.invoked
```

A filtering double keeps every assertion in that test green while removing the
launch the pass is supposed to leave alone — the test would then prove a
property of the double, not of the pass.

**The requirement is specified, in two capabilities, not merely tested.**
`openspec/specs/launch-step-automation/spec.md:39` and
`openspec/specs/launch-clickup-sync/spec.md:91` both carry the scenario *A
graduated launch is left alone* — `THEN no handler is invoked for any of its
steps`, and `THEN no list or task is created or updated for it`. And
`clickup_sync_job.py:11` records why the guard lives in `list_active` at all:
*"Graduated launches never appear — `list_active()` filters them out, so no pass
has to remember the rule."* A filtering double would therefore leave a specified
requirement unverified in two capabilities at once, by erasing exactly the guard
those scenarios pin. **A shared double must not implement
the filter its subject is being tested for.** Neither instrument can see this:
the equality proof compares values, the pairing compares calls, and both are
identical either way. It is found by asking what each test is *for*, which is
why it is recorded as a rule and not only as a decision.

*Alternative considered:* filter, and exempt the two files. Rejected — the
exemption would have to be re-derived every time a test hands the double a
graduated launch, and nothing would report it when one does.

### 6. The five scope-sniffing catalog ports stay local, with the reason recorded

`_FakeCatalog`'s 29 declarations are two subjects: 24 callable product readers
over `CatalogProduct`, and 5 ports over `Product` that sniff their arguments for
an `AccessScope` and a `ProductId`, all five in
`tests/unit/launch/…/test_product_*.py`. The five were dispositioned by `share-the-stateful-fakes`
itself — task 10.3 and its proposal, on the ground that *"four of those five
apply access-scope filtering that no `_Catalog` declaration performs. Migrating
them onto `FakeCatalogPort` would drop a scope check inside a double,
invisibly."* That is a different population from the two `FakeCatalogPort`'s own
docstring speaks of, which are `_Catalog` declarations; the docstring is
accurate and is not to be "corrected". The five are also not uniform among
themselves — three identical, one adding a `list_scopes` recorder, one sniffing
by `isinstance` across `*args`.

Taking them would widen the subject from the aggregate stores to the admin
product surfaces, for a population of five in which two need adapters. They stay
local; the reason is recorded at each, and they are a candidate for a later
slice rather than a gap.

### 7. The product reader carries both recorder spellings, on one list

**It holds whatever object it is handed, unconstrained** — not necessarily
`tests/support/values.py::CatalogProduct`. Several locals still declare their own
frozen product type (`test_briefing_delivery.py:231`), and four production sites
probe the *served* product by attribute name (`automation_pass.py:563`,
`automation_confirmation.py:115`, `product_dossier.py:326` and `:335`). A reader
that constrained the held type would move the same-value invariant from the
call site, where it is visible, into the shared double, where it is not.

Of the 24 callable readers, 6 record into `self.reads`, 4 into `self.calls` and
14 record nothing. The shared type stores `reads` and derives `calls` as a
read-only `@property` returning the same list object, so the two carry the same
value by construction — the same arrangement `Member.identifier` and
`FakeTask.custom_field_values` use, for the same reason.

Adding a recorder to the 14 that had none is a superset, licensed by the Context:
`reads` and `calls` are test-only names that no production reader touches.

### 8. Every declaration's disposition names its instrument

- **Equality proof** (`share-the-value-doubles`) for the 42 playbook-serving and
  the 24 product-reader declarations. The precondition was checked by
  construction over every distinct type the 24 actually serve, not assumed from
  the name: **22 import `tests/support/values.py::CatalogProduct` and 2 declare
  their own `@dataclass(frozen=True)`, so all 24 serve a frozen dataclass** and
  the field-wise comparison is real for every one. Task 3.4a re-takes that check
  and routes any non-frozen type it finds to the pairing — the alternative is the
  failure `AGENTS.md` already records, of asserting the strong proof over a
  population it was never measured on.
- **Lockstep pairing** (`share-the-stateful-fakes`, `_paired_spike.py`) for the
  58 `Launch`-serving ones, where `==` is identity. Its four recorded limits
  apply unchanged.

  **The ten `_FakePlaybookRepository` build their playbook rather than being
  handed it, and that is harmless here.** It looks like pairing limit 1, but
  `AGENTS.md` states that limit with its precondition attached — *a plain-class
  double's `==` is identity* — and `LaunchPlaybook` is a frozen dataclass, so the
  comparison is field-wise and the limit does not bite. They are closed by the
  equality proof, as the bullet above says; Decision 3 changes their construction
  for the `_SERVED` staleness, not for the limit.
- **Standalone proof** for the 13 declarations that execute zero calls across
  all three tiers (6 `_FakeLaunches`, 5 `_FakeCatalog`, 2 `_FakePlaybooks`).
  A declaration nothing calls reports zero, not pass; each is dispositioned by
  constructing both versions directly and comparing, and the count is stated
  rather than folded into the pass total. **That comparison happens in the phase
  that migrates the declaration** (tasks 3.4b, 4.3a, 5.5c), never in §6: the
  local is one of the two versions being compared, and its own phase's commit
  deletes it. §6 is the register that reports the 13 together.

  **The 5 silent `_FakeCatalog` are not the 5 kept-local scope-sniffing ports —
  measured, the overlap is zero.** The silent five are `clickup_*` files under
  `.../driven/`; the kept five are `test_product_*` under `.../driving/`. So all
  13 have a shared version to construct, and §3's "24 of 24" covers 5
  declarations that execute nothing and are closed standalone.

Both reviews run, not one: the equality proof passed everything last slice and
`/code-review` then found ten helpers whose override had stopped winning.

### 9. The constructor contract, fixed here rather than left to the implementer

**Five review rounds checked instrument assignment, populations, arithmetic and
cross-references, and none of them asked how a double is *handed its subject*.**
The test-writing pass found the gap: `tasks.md` named each type's surface and
never its constructor, so all 41 contract tests were written against assumed
signatures. An assumption that lives only in the tests is the thing this
project's rules exist to prevent, so it is settled here — by the majority local
spelling, measured rather than chosen.

| type | constructor | measured basis |
|---|---|---|
| `FakeProductReader` | `(product)` positional | 12 of 24 spell `__init__(product)`; 7 take none and answer a module constant, which the call site now passes |
| `FakePlaybooks` / `AsyncFakePlaybooks` | `(playbook, *, refusal=None)` | 17 spell `__init__(playbook)`, 6 default it to a module constant, 3 also take a refusal — positional subject, keyword refusal, per Decision 2 |
| `FakePlaybookRepository` | none — `serving(source)` only | all 10 take `(*args, **kwargs)` and are constructed by production (Decision 3) |
| `FakeLaunches` | `(*launches)` variadic | 35 of 58; `serving(source)` for the 2 class-patched ones (Decision 4) |

Two consequences worth stating, because both are call-site work the migration
performs and neither is a shared-type feature:

- The **7 readers and 6 playbook stores that take no constructor argument** and
  close over a module constant pass that constant explicitly. A shared type
  cannot carry a per-file default, and `AGENTS.md` already forbids a builder
  falling back on a parameter's default where the file has its own.
- The **2 readers taking `products: dict[ProductId, CatalogProduct]`** are a
  different subject shape. They are an adapter under the three-line rule, or a
  keep with the reason recorded — task 3.4 decides by running them.

**The reads answer a `tuple`.** The locals disagree — 46 annotate
`tuple[Launch, ...]`, 13 `list[Launch]`, 1 `Sequence[Launch]` — and `tuple`
is both the majority and the spelling `FakeCatalogPort.list_products()` already
uses. Production's own ports annotate `Sequence`, which a tuple satisfies.

**`_FakePlaybooksBase` is not imported by any test.** `AGENTS.md` states that a
module-private name imported across modules is a contradiction, and the base is
private deliberately: it is an implementation detail of the sibling split, not a
double any test arranges from. The sibling relationship is asserted without
naming it — neither sibling is a subclass of the other, and both share one base.

## Risks / Trade-offs

- **A harvested expression that is not evaluable outside its own function** →
  Validate every expression by evaluating it against all its call sites at build
  time. One of 179 needed this last slice; a one-in-179 defect is not one review
  finds.
- **A classifier keyed on the bare name reporting everything as unmigrated** →
  Resolve import aliases before classifying, and patch `tests.support.X` before
  importing a test module, since `from … import y as _z` binds at import.
- **The superset argument resting on a stale probe search** → It rests on
  `src/commerce_ops/launch/` containing no `getattr` shape probe, no `hasattr`
  and no `except AttributeError` for these three collaborators. Re-take that
  search at the commit that lands the change, not once and then assume — every
  spelling-based sweep of this ground has come back stale.
- **A declaration whose double is built at import, before a plugin can wrap it**
  → It reports zero calls and falls to the standalone proof by Decision 8, which
  is what the 13 are for. It is never counted green on the pairing's silence.
- **83 files touched, concurrently with another `tests/`-wide change** → Do not
  run it concurrently with one. The three predecessors carried the same caution.

## Migration Plan

One branch, `share-the-aggregate-fakes`, merged through its own pull request,
archived in a later one — per `AGENTS.md`. Within it, one subject per commit,
each commit leaving all four baselines intact: `tests/unit` outside support
**2,246**, `tests/agents` **236**, `tests/integration` **159**,
`tests/unit/support` **52** and rising.

The shared type and its contract tests land in the same commit as the first call
sites that use it: the `pre-commit` hook runs the whole commit tier, so a type
with no callers and a call site with no type cannot be committed apart.

Rollback is per-commit and needs nothing beyond `git revert` — no production
code, no schema, no configuration.
