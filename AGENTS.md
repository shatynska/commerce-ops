<!-- ai-toolkit:development-workflow v1 -->
<!-- Generated. Do not edit inside this block — it is replaced on update.
     Project-specific conventions belong below the closing marker. -->

# Development workflow

These rules establish how work proceeds on this project once it has a
foundation. They apply independently of any single tool — each names an
obligation as a role to fill, and where this project uses Claude Code, names
the binding for that role beneath it.

## Spec-driven development and spec review

Use a specification-driven change process for non-trivial features, changes,
and significant architectural decisions. Do not begin implementing or
applying a non-trivial change without a corresponding change proposal
recording what is intended and why.

A change's artifacts — its proposal, its design, its specification deltas,
its task list — are the record of intended behavior and the decisions behind
it. They are read before implementation, not written after the fact to
describe what was already done.

Review is dispatched against the complete set, never against a package still
being written: a reviewer given half a package spends its round reporting
absent sections rather than defects, and a round that establishes only "this
is incomplete" is one spent, not one passed. Complete means every artifact
the change calls for exists — an artifact a change legitimately does not
have does not make its package incomplete.

Before any code is written or applied, the change must be independently
reviewed, then revised and re-reviewed until the reviewer's verdict permits
proceeding. Where a verdict permits proceeding only conditionally, the
conditions it names are applied before proceeding — a conditional pass is
not an unconditional one, and applying conditions of that kind does not
require a further review round.

The revise-and-re-review loop is bounded. Beyond an initial review and five
automatic re-reviews, do not dispatch a further round unasked: report where
the loop stands, what is still outstanding, and ask before continuing. A
loop that has not converged in six rounds is rarely one round from
converging, and an unbounded loop spends the reviewer against a change no
one has looked at since it started.

Where the reviewer judges the change's concept unsound rather than its
artifacts defective, that is not another revision round at all: stop and
raise it immediately, whatever the count stands at, because no amount of
rewriting the artifacts answers it.

An approved plan is committed before tests are derived from it. The commit
fixes the baseline those tests map to; where the specification deltas keep
moving while tests are being written against them, the mapping goes stale
with nothing reporting it. Per the commit rule below, suggest that commit
rather than making it unasked — and where it is declined, report that the
next step is blocked on it and stop there, rather than proceeding without
it.

_Claude Code binding:_ once `proposal.md`, `tasks.md`, every delta spec, and
`design.md` where one is written are complete, dispatch
`ai-toolkit:openspec-change-reviewer`. On `CHANGES REQUIRED`, revise the
artifacts and re-dispatch, up to the five automatic re-reviews the bound
above allows. On `PROCEED WITH CHANGES`, apply the `[MINOR]` fixes it lists
— that verdict is permission conditional on them — and continue without a
further review round. On `PROCEED`, continue. On `REJECT`, stop and raise
it.

## Test design before implementation

Before implementing a change with behavior that tests can be derived from,
have an author other than whoever writes the implementation derive tests
from that change's approved specification deltas — not from implementation
code. Two processes that see only the implementation share its blind spots;
a test author with no sight of the implementation does not.

Where this project's rules, or a procedure or specification they defer to,
state an exemption from test authoring for a named class of change, that
exemption applies. It applies by having been stated in advance, not by being
decided at the gate, and the reason is stated when it is used. A change that
declares it carries no specification deltas has none to derive from and owes
no new tests; what it owes is that the existing suite stays green. Deltas
that are merely unwritten are not that declaration — an absence found at the
gate is the gap this rule forbids, not an exemption.

Test authoring is dispatched only against a plan that has passed review and
been committed — never against artifacts still being written, and never
ahead of review. A test derived from a specification the review has not yet
cleared encodes whatever defect that review would have caught.

_Claude Code binding:_ dispatch `ai-toolkit:openspec-test-writer` only after
the reviewer's verdict permitted proceeding, any conditions it named were
applied, and the approved plan was committed — and strictly before applying
changes or implementing code.

## Implementation and execution

Only after the specification has passed review, and the tests it calls for
have been derived from its specification deltas, may the change be applied
and implemented in code.

Three things are checkable before implementation begins: a review verdict
that permitted proceeding, a commit holding the approved plan, and the tests
derived from that plan — or, in place of those tests, the stated exemption
that excused them. Where any of the three is absent and no stated exemption
covers it, take the missing step first rather than starting implementation
and noting the gap.

## Verification before any completion claim

Implementation existing is not the same as a change being complete. Run the
verification relevant to the change — tests, type checking, linting,
formatting, a build, or whatever else the project's conventions require —
and do not report a change as complete without having run it.

## Independent review before completion

Verification establishes that a change does not fail. It does not establish
that the change is the one its specification asked for. After implementing a
change, have an independent reviewer read the diff against the change's own
specification before the change is called complete. That reviewer checks
that each requirement is implemented, that the implementation matches what
the specification describes rather than something adjacent to it, that the
tests derived from the specification deltas cover the behavior that actually
changed, that no unrelated scope was introduced, and that the project's
conventions were followed.

This review reads code; the review that gates implementation reads plans.
They are separate obligations and neither substitutes for the other — the
earlier one asks whether the plan is sound, this one asks whether the code
is that plan.

Dispatch it against a diff that already passes verification. A reviewer
handed a change whose tests fail spends its round on the failure, which
verification had already reported.

_Claude Code binding:_ run `/code-review` over the change's diff before
treating the change as done. Do not use
`ai-toolkit:openspec-change-reviewer` for this role — it reviews a change's
planning artifacts and explicitly not the code that follows them.

## Small, reviewable commits

Prefer small, focused commits that represent a complete, meaningful unit of
work, over large commits bundling unrelated concerns. After a meaningful
milestone is reached, proactively suggest creating a commit rather than
waiting to be asked.

Before committing: look at the diff being committed, run the verification
relevant to what changed, and check that no secret or unintended file is
included. Suggest the commit; do not make it without confirmation.

## Incremental development and scope control

Prefer changes small enough to review in one sitting. Where a change grows
to cover multiple independent concerns, or grows too large to review as a
unit, consider splitting it into separate changes instead.

Implement only what belongs to the change currently in progress. An
improvement noticed along the way, that is not part of that change's stated
scope, becomes a separate proposed change rather than being folded in.

## Requirements and assumptions

Do not silently invent a requirement that was not stated and cannot
reasonably be inferred. Where an important decision cannot be inferred, ask
rather than guess.

Record significant decisions in the project's own artifacts rather than
relying on them surviving only in conversation history — a decision that
exists only in a conversation is not available to whoever reads the project
next.

## The repository is the source of truth

Do not rely on earlier conversation context for information the repository
itself can supply. Prefer reading a file, a spec, or a commit over recalling
what a previous exchange said about it — the repository does not go stale
the way a remembered conversation does, and it is what the next person, or
the next session, will actually see.

<!-- /ai-toolkit:development-workflow -->

<!-- ai-toolkit:project-foundation -->

## Testing Strategy

pytest for unit/integration tests on the FastAPI layer and business logic, plus separate deterministic tests for LangGraph agent graphs using mocked/stubbed LLM responses so agent logic is tested without live model calls or nondeterminism.

Tests are split into three directory-based tiers, each mirroring the module/layer architecture above:

- `tests/unit/<module>/<layer>/` — fast, mocked unit tests.
- `tests/agents/<subject>/` — deterministic LangGraph agent-graph tests (mocked/stubbed LLM responses); treated as unit-tier since they carry no network/IO cost. One directory per subject under test, named for where that subject lives, which may be more than one segment deep: `tests/agents/omni_agent/` for the graph in `omni_agent/application/`, `tests/agents/step_handlers/listing/` for the handler in `step_handlers/listing/`. It names the subject, not its full source path — neither example reproduces one.
- `tests/integration/<module>/` — tests that touch real I/O (e.g. Postgres).

`tests/unit` and `tests/agents` run at commit-time via a `pre-commit` hook; `tests/integration` runs at `pre-push` instead, to keep individual commits fast.

- Test command: `uv run pytest` (invoked inside the uv-managed environment, not a bare `pytest` assuming manual venv activation)
- Test-path glob: `tests/**/test_*.py` (matches all three tiers)
- The integration tier finds its own database — `tests/integration/conftest.py` reads `DATABASE_URL`, else `.env.test`, else `.env` — so no `export` is needed before running it. Only that one key is read from either file; the suite sets its own Slack, OpenAI and ClickUp values. An isolated test database is optional: create one once by hand, **migrate it and then seed it** (`alembic upgrade head`, then `uv run python -m commerce_ops.seed_playbook`), and name it in `.env.test`. Where nothing resolves, tests needing a database skip and say why; where `COMMERCE_OPS_REQUIRE_DATABASE` is set — CI sets it — they fail instead, and a skipped test anywhere in the tier fails the run, so a gate cannot pass a tier, or a check, it never ran.

### The shared harness: `tests/support/`

All three tiers arrange from `tests/support/`. It is imported, never collected —
`testpaths` names the three tiers, as does every hook and CI step.

- **A new test arranges from `tests/support/`.** A new bespoke fake means a
  builder is missing, not that a thirteenth `_FakeSession` is warranted. Add the
  builder.

**The rules below govern shared doubles, and both kinds now exist.**
`tests/support/values.py` carries the value doubles and `tests/support/fakes.py`
the stateful ones. `share-the-unit-test-harness` delivered the constants, the
HTML harness, the admin session, the fixtures and the step builder;
`share-the-value-doubles` (2026-09-04) added `values.py` — `Member`,
`MemberValue`, `CatalogProduct`, `Record`, `TaskMapping`, `PendingRow`,
`FakeTask`, `CreatedTask` — replacing 166 local declarations;
`share-the-stateful-fakes` (2026-09-04) added `fakes.py` — `FakeMembers`,
`FakeMembersStore`, `FakeStepStore`, `FakeCatalogPort`, `FakeHandlers`,
`FakeHandlerRegistry`, `FakeSlackResponse`, `StubDate`, `InertBackoff` —
replacing 175 of 191 declarations across 103 files;
`share-the-playbook-builders` (2026-09-04) finished the builders — **`_hold` is
now 104 of 104 and `_playbook` 84 of 95**, across 105 files.

`share-the-aggregate-fakes` (2026-09-05) took the aggregate stores —
**115 of the 124 in-scope declarations across 83 files**, adding
`FakeProductReader`, `FakePlaybooks`/`AsyncFakePlaybooks` over a shared
`_FakePlaybooksBase`, `FakePlaybookRepository` and `FakeLaunches`. The nine it
left are recorded at each declaration, and every one is a measurement rather
than a judgement. **`src/` was untouched, checked mechanically, and the
assertion-identity multiset did not move: 6,612 / 238 / 759 / 172 over 2,192
test functions, unchanged across 89 files and 3,244 inserted lines.**

**The proof splits by what a store serves, and both instruments were needed.**
`LaunchPlaybook`, `StepDefinition` and `values.py::CatalogProduct` are frozen
dataclasses, so the equality proof reached the 42 playbook-serving and 24
product-reader declarations — 649 comparisons, no mismatches. `Launch` and
`Product` are plain aggregate roots defining no `__eq__`, so the 58
`Launch`-serving ones needed the lockstep pairing — 665 paired calls. Verify
such a split by construction, never by reading: `dataclasses.is_dataclass(T)`
and `T.__dataclass_params__` settle it in one line, and a first draft of this
paragraph asserted the strong proof for all 129 because it was written from
`_FakePlaybooks` alone.

**A shared double must not implement the filter its subject is being tested
for.** The real repository's `list_active` drops launches standing at
`graduated`, and reproducing that in `FakeLaunches` is the obvious "truer to
production" move. It is wrong:
`test_automation_pass.py::test_a_graduated_launch_is_left_alone` hands a
graduated launch to the double precisely to prove *the pass* leaves it alone, so
a filtering double removes the launch before the pass sees it and **every
assertion still passes**. Two capabilities specify that scenario
(`launch-step-automation`, `launch-clickup-sync`), so both would go unverified
against a green suite. Neither instrument can see it — values and calls are
identical either way. `tests/unit/support/test_fake_launches.py` pins the
absence of the filter so a later "improvement" fails loudly.

**A double installed by patching a class needs a class-producing constructor
that reads its source at call time — never a mutable class attribute.** All ten
`_FakePlaybookRepository` declarations are installed as
`monkeypatch.setattr(module, "PlaybookRepository", …)`, so production constructs
them itself and they can never be handed their subject as an instance. Two
`_FakeLaunchStore` declarations are patched the same way over `LaunchRepository`
— but both were **kept local** for a different reason (their
`get_by_product_id` ignores the identifier by design), so the launch store has
no `serving()` at all. A first draft gave it one; `/code-review` found the path
had no users outside its own contract test, and it was removed rather than left
as a shared double with a measured population of zero. `serving(source)` returns a fresh subclass per call site, and resolves
`source` on **every read**: `test_clickup_webhook_automated_step` rebinds
`_SERVED[0]` mid-file to prove opposite branches, and a value bound at subclass
creation serves the import-time playbook to both while both tests still pass. A
mutable class attribute would do the same job and is session-global state every
test touching the class shares — the cross-test leak this harness exists to
remove.

**Measure a spelling before carrying it, not only before dropping it.** The
plan modelled `__call__` on the playbook store and spent a review round on
where to put it. Wrapping the six locals that carry it recorded **0 invocations
across all three tiers**; `src/` reads a playbook store only through `.get(...)`,
so the locals' own comment claiming bare callers is stale; and injecting a
raising `__call__` on the 26 declarations lacking it left the tier green. It was
dropped on the same licence `list_launches` and `all` were — both of those taken
by mutating all 42 to raise, not by search. Demanding execution-proof before
*removing* a spelling while adding another on six declarations' say-so is not a
position a change can hold.

**The pairing's limit 2 is wider than its mismatch count suggests.** It reported
3 value mismatches over the 58 launch stores; migrating then broke **37 tests**
on attribute access it never intercepts — `.launches`, `.order`, `.stored`,
`.reads`, `.saves`. Two rules came out of that. The **stored** spelling must be
the one a test *assigns* (two files assign `store.launches = snapshot`, and a
read-only property cannot receive an assignment — the `Member.id` precedent).
And a derived property must not collide with a *method* of the same name
elsewhere in the population: `stored` answers one launch by identifier in two
files and is never read bare, so a list-valued `stored` property would have
shadowed them. The suite caught both; no proof instrument could have.

**Behaviour is proved by comparison, not by inspection — where it can be.**
A field-wise equality proof is inexpressible for a stateful fake, since
`FakeStepStore() == FakeStepStore()` is identity. What replaced it is a
**lockstep pairing**: the local and the shared fake are driven side by side,
and every executed call compares the return value, the raised exception and the
instance state afterwards. Over the migration it ran 115 declarations through
1,134 constructions and 2,687 calls. **It is worth knowing exactly what such a
proof cannot see**, because the next slice will meet all four again:

  1. **A double that builds its contents rather than being handed them.** Two
     independently built twins hold different objects, and a plain-class
     double's `==` is identity — so every comparison differs for a reason that
     is an artefact. Twenty `FakeMembers` declarations were in this position.
  2. **A test that writes the double's state directly.** The pairing intercepts
     calls, not attribute writes, so `store.rows = ...` reaches the local and
     never the twin.
  3. **A double whose surface is its base class.** `StubDate` and
     `FakeSlackResponse` expose a classmethod and a property over `date` and
     `dict`; there is no instance method to intercept, and they rest on the base
     class, `mypy` and their contract tests instead.
  4. **Anything a test never executes.** That region belongs to
     `tests/unit/support/`, which is why it exists.

- **A double keeps the locals' field spelling; production's spelling is a
  derived property.** Production probes by shape where `.importlinter` forbids
  naming a type, and every local double models the minimum, which is why the
  probe still carries branches to fall through to. `Member` stores `id` — the
  spelling all 52 locals used, and the one ten of them pass as a keyword, which
  a read-only property could not receive — and derives `identifier`, the
  spelling all six member probes read first. `FakeTask` stores `custom_fields`
  and derives `custom_field_values`. Both carry the same value by construction
  rather than by inspection, which is what lets the probe's other branches be
  deleted. A protocol declares such a name as a `@property`, never as a
  variable: `mypy` treats a protocol variable as settable, so the variable form
  makes the `_conforms` line a type error.
- **Declaration form is part of the contract.** A local migrates onto a shared
  double only where the two agree on dataclass-ness, `frozen`, `eq` and any
  `__repr__` the file relies on — field equality says nothing about those, and
  this suite disagrees on all three for real reasons. Where a name carries a
  substantial population in both forms it gets **two** shared types rather than
  one bent across two equality semantics; `Member` and `MemberValue` are that
  case, at 42 plain against 10 `@dataclass`. **Where two such types also
  disagree on a default, say so at both of them**: choosing between them then
  changes a value as well as an equality semantics, which is the one way this
  arrangement can break the same-value invariant. `clickup_user_id` is that
  field, and each type's docstring names the trap.
- **A constructor mismatch is remediable by a three-line adapter; a form or
  value mismatch is not.** Where the shared type can produce the exact object
  but cannot take the call site unchanged, the file subclasses it and adapts the
  signature — the proof still runs over the adapter. Where the values or the
  form differ, the file keeps its own declaration and the reason is recorded.
- **A builder's delta is derived by *running* the local, never by reading it.**
  `share-the-playbook-builders` measured the same 73 `_hold` declarations both
  ways: the static pass over-reported `discipline` at 26 against 13 and
  `confirmer` at 22 against 4, because it cannot see that
  `next(iter(Discipline))` and `any_discipline()` evaluate equal, and it
  mis-classified one file as reproducible by a fixed partial when its value is
  computed from the gate. Reading is for finding candidates; running is for
  deciding.
- **An expression harvested out of a file must be validated by evaluating it.**
  `test_launch_report_carried_finding` spells `name` as
  `f"Work {identifier} asks for"`, where `identifier` is a parameter of that
  file's `_step` and not a module-level name. Harvested and trusted, it fails at
  the call site; harvested and validated against all eight gates, it is caught
  at build time and synthesised from the values instead. Exactly one of 179
  expressions needed this, which is the point — a one-in-179 defect is the kind
  a review does not find.
- **A comprehension over `SPECIFIED_GATE_ORDER` is not necessarily building
  fillers.** Three files use one to *reorder* steps by gate. A migration that
  read the two as the same thing silently deleted five real steps, and the
  equality proof — not the suite, and not review — is what reported it.
- **A signature-preserving body rewrite must inline the bindings it deletes.**
  Replacing a `_playbook` body while keeping its signature removes the
  `steps = (...)` and `gates = (...)` its `return` referred to; 28 files needed
  those inlined.

- **A spec-restating constant is a literal there, and is never sourced from
  production.** `SPECIFIED_GATE_ORDER`, `CONFIRMATION_GATES`, `FINAL_GATE`,
  `opening_for` and `gates` state what the specification says the gates are, and
  fifteen files assert production *against* them. Importing
  `launch_playbook.GATE_SEQUENCE` instead would make those assertions say that
  production equals itself. The types (`Gate`, `GateOpening`) are imported
  freely; only the values are banned. The distinction is the point: a test may
  use production's types and must never take production's answer to the question
  it is asking.
- **A generated value is a factory, never a shared constant.** `product_id()`
  exists because 68 modules each evaluated `ProductId(str(uuid.uuid4()))` at
  module level and got 68 distinct identifiers; one shared constant would give
  them all the same one. A file keeps `PRODUCT_ID: Final = product_id()`.
- **A fake carries `_conforms: SomeProtocol = TheFake()` beside it.** `mypy`
  compares a class to a protocol only where a value is assigned to a
  protocol-annotated target, so that assignment — not the protocol's existence —
  is what makes a double which has stopped matching its subject a type error.
- **Completeness carries the same-value invariant with it.** Production reads
  several collaborators by probing attribute names in order, so a double that
  models *more* than the local one can silently redirect the probe to an earlier
  branch. Where a fake adds a spelling a probe reads before the one the local
  populated, the added spelling carries the same value as the one it displaces.
- **The package exports public names**; a call site that keeps a local
  `_`-prefixed spelling aliases them (`from tests.support.html import tree as
  _tree`). A module-private name imported across modules is a contradiction.
- **A dropped spelling must be measured dead, and the measurement is named.**
  A shared fake may carry less than the locals it replaces only where nothing in
  `src/` **or** `tests/` reaches the dropped name — searched at the commit that
  drops it, not once and then assumed. Three were dropped this way:
  `FakeMembers.members`, `FakeMembers.__call__` and
  `FakeHandlerRegistry.__iter__`. The last needed more than a search, and shows
  why: `in` falls back to `__iter__` when `__contains__` is absent, and
  `automation_pass:770` evaluates `name in handlers`, so the licence was taken
  **by execution** — mutating every local `__iter__` to raise left the commit
  tier green. Prefer that method wherever the interpreter can reach a spelling
  implicitly.
- **`tests/unit/support/` is a deliberate exception to the tier layout above.**
  It names no bounded context because its subject is the harness itself, and it
  sits under `tests/unit/` so the shared fakes' own behaviour is collected and
  run at commit time — 46 tests as of `share-the-stateful-fakes`.
  `tests/support/` itself is imported, never collected, and is excluded from the
  assertion-identity check for that reason: a double's internal assertion is
  part of the double, not a test's.
- **A protocol beside a fake is checked only by its `_conforms` assignment**,
  and two spellings of that assignment are traps rather than style. A name a
  probe *reads* is declared `@property`, never as a variable — `mypy` treats a
  protocol variable as settable and a read-only property does not satisfy one.
  And where the double cannot be constructed without arguments, or its surface
  is a classmethod, the assignment takes the **class-object** form:
  `_conforms: type[DateShape] = StubDate`, because `date` requires three
  constructor arguments and `DateShape = StubDate()` cannot be written.

### Working in a git worktree

Parallel sessions run as worktrees under `.claude/worktrees/`, and a worktree
starts out unable to run the integration tier. These are obligations, not tips.

1. **The Postgres container runs continuously.** Check it — `docker ps` — before
   concluding a database, or Docker, is unavailable. A session has already
   reported "Docker isn't available in this WSL setup" while
   `commerce-ops-postgres-1` was up and serving on `127.0.0.1:5432`.
2. **A worktree does not inherit `.env.test`.** It is gitignored (`.env.*`), so
   it exists only in the clone it was written into, and `git worktree add`
   carries none. Configure one before relying on the tier. Until you do, the
   tier skips in its entirety and `pre-push` reports it as `Passed` — that
   green is not evidence anything ran, and a merged pull request has already
   claimed a tier that had skipped.
3. **Migrated is not seeded.** `alembic upgrade head` writes the migrated rows;
   the other steps come from `uv run python -m commerce_ops.seed_playbook`,
   which every container runs on start and no migration performs. A database
   with only the schema applied fails four tests.
4. **Read a failing test's assertion message before concluding the failure is
   pre-existing.** The four above say what is wrong with the database in their
   own messages. "Pre-existing failures" has been the wrong answer every time it
   has been given here.
5. **Put `_test` last in a test database's name.** The check is a suffix check,
   so `commerce_ops_x_test` is a test database and `commerce_ops_test_x` is not.
   Give each worktree its own; the tier writes freely and issues at least one
   unscoped `DELETE`, so two sessions sharing a database produce failures that
   read as defects and are not.

## Development Tooling

- **uv** for dependency and environment management (single lockfile).
- **ruff** for linting and formatting.
- **mypy** for type checking.
- **pre-commit** orchestrates git hooks: `ruff check`, `ruff format --check`, `mypy`, and the `tests/unit`+`tests/agents` pytest tier run at commit-time; the `tests/integration` tier runs at `pre-push`.
- **gitlint** enforces conventional-commit-style commit messages via a `commit-msg` hook — chosen over `commitlint` specifically to avoid a Node.js dependency in this otherwise pure-Python project.

<!-- /ai-toolkit:project-foundation -->

## Architecture summary

**Product Launch is the MVP subdomain and the first deliverable**, driven from Slack and tracked in ClickUp; marketplace integration is deferred pending external access, so no change is sequenced as depending on a marketplace adapter until it is granted. Launch state is owned three ways — the repository owns the playbook *framework* (the gate sequence, opening modes, metric conditions and every coherence rule, in `launch_playbook.py`) while Postgres owns the *step content* as a live set edited only through validated `playbook-authoring` use cases (amended by `move-playbook-steps-to-postgres`, 2026-08). A step declares a single-line `name` and an optional multi-line `description`, its `assignees` (members, by identifier), its `kind` (`human` or `automated`) and, separately, whether its result `needs_confirmation`, a lifecycle `status` (`draft`, `in-development`, `active`, `retired`) and — where it is automated — an `automation_brief` and a `handler`; only `active` steps are served, hold a gate, or reach ClickUp (`redesign-step-fields`, 2026-08); Postgres also owns each product's position and per-step completion, and ClickUp owns human completion. Postgres likewise owns **who is known to the system** — the membership, their per-service identities, admin authority and active status — edited only through validated `members` use cases and no longer a repo-owned file (`move-principals-to-roster`, 2026-08); adding a colleague is an admin action, not a deploy, and the first admin is seeded from `BOOTSTRAP_ADMIN_IDENTITY` by a step that runs between the migration and the server, never inside the serving process. LangGraph is scoped to interpretation, generation and conversation, not to deterministic rule evaluation. See `README.md`'s Scope, Technology and Architecture sections for the reasoning and the obligations each carries.

commerce-ops is a modular monolith: one FastAPI app organized into domain modules as DDD bounded contexts, sharing one Postgres database. Each module follows a lightweight ports-and-adapters shape — domain layer (entities/value objects, no I/O) at the center, application layer (use cases, LangGraph agent graphs) around it, infrastructure layer (FastAPI routes, its own Slack adapter, the Amazon-first marketplace-adapter layer, Postgres repositories) on the outside, each module owning its own driving adapters. Tactical DDD patterns (aggregates, domain events) are adopted per module only as needed, not mandated everywhere. Slack is a first-class two-way interface (conversational + notifications/approvals) alongside the HTTP API, not a secondary add-on.

A module's `application/__init__.py` (`__all__`-exported) is its only public surface, enforced by `import-linter`; `shared` is a Shared Kernel exception (same-or-lower matching layer, never the reverse). `step_handlers/` is the third kind of top-level package after the bounded contexts and `shared`: it holds every step handler, grouped by the discipline its registered name starts with, and reaches `launch` only through that public surface, under one `import-linter` contract covering every handler present and future. A handler is a module until it earns being a package, and a package until it earns layers; a handler that is a package re-exports its registration from `__init__.py`, since `@register_step_handler` runs only when the module holding it is imported. See `README.md`'s Architecture section for the full module-boundary contract, rationale, and alternatives considered.

## Deployment and configuration

**Every change reaches the server through a pull request.** Merging to `main` is what triggers the deploy workflow; nothing ships from a local machine, and nothing is deployed by committing to `main` directly. So all work happens on its own branch and merges through a PR — a change's OpenSpec artifacts included, not only its code. Propose a change on a branch named for it, implement there, and merge that through its own PR. Only then archive it (`openspec archive <change> --yes`, which folds the deltas into `openspec/specs/`) — the last commit, on its own branch, in a last PR of its own. The archive records that a change shipped, so it follows the merge rather than riding along with it. Committing a proposal straight to `main` skips the review the deploy depends on.

**Runtime configuration lives in a GitHub Environment, as secrets.** The `deploy` job declares `environment: production` and renders the host's `.env` from that environment's values. Every value it renders is an Environment **secret**, so read them with `${{ secrets.NAME }}`.

Do not reach for `${{ vars.NAME }}` for anything the application requires. This repository defines no Actions variables at all, and an unset `vars` reference renders an *empty string* rather than failing — so the application starts against a variable that is present but blank, which is a harder fault to read than a missing one. That has already cost one broken deploy: `BOOTSTRAP_ADMIN_IDENTITY` was set correctly as an Environment secret while `deploy.yml` alone among its neighbours read `vars`, so `.env` received `BOOTSTRAP_ADMIN_IDENTITY=`, the admin-seeding step refused to start a deployment nobody could administer, and the container never became healthy (2026-08). The one deliberate `vars` reference is `LOG_LEVEL`, and it is safe only because it carries a literal fallback (`${{ vars.LOG_LEVEL || 'INFO' }}`) — which is the shape to copy if a future value really should be a variable rather than a secret.

Adding a new runtime variable therefore means four things, not one: set it as an Environment secret, render it in `deploy.yml` from `secrets`, declare it on the settings model in `shared/application/settings.py`, and mirror it in the declared set `tests/unit/shared/application/test_settings.py` compares against. Read it by its literal name in the source, too — the drift check detects consumption by scanning for the name, so a read through a constant looks like a variable nobody uses.
