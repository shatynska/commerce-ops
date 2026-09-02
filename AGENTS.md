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
- The integration tier finds its own database — `tests/integration/conftest.py` reads `DATABASE_URL`, else `.env.test`, else `.env` — so no `export` is needed before running it. Only that one key is read from either file; the suite sets its own Slack, OpenAI and ClickUp values. An isolated test database is optional: create and migrate `commerce_ops_test` once by hand and name it in `.env.test`. Where nothing resolves, tests needing a database skip and say why; in CI, where `COMMERCE_OPS_REQUIRE_DATABASE` is set, they fail instead, so a gate cannot pass a tier it never ran.

## Development Tooling

- **uv** for dependency and environment management (single lockfile).
- **ruff** for linting and formatting.
- **mypy** for type checking.
- **pre-commit** orchestrates git hooks: `ruff check`, `ruff format --check`, `mypy`, and the `tests/unit`+`tests/agents` pytest tier run at commit-time; the `tests/integration` tier runs at `pre-push`.
- **gitlint** enforces conventional-commit-style commit messages via a `commit-msg` hook — chosen over `commitlint` specifically to avoid a Node.js dependency in this otherwise pure-Python project.

<!-- /ai-toolkit:project-foundation -->

## Architecture summary

**Product Launch is the MVP subdomain and the first deliverable**, driven from Slack and tracked in ClickUp; marketplace integration is deferred pending external access, so no change is sequenced as depending on a marketplace adapter until it is granted. Launch state is owned three ways — the repository owns the playbook *framework* (the gate sequence, opening modes, metric conditions and every coherence rule, in `launch_playbook.py`) while Postgres owns the *step content* as a live set edited only through validated `playbook-authoring` use cases (amended by `move-playbook-steps-to-postgres`, 2026-08). A step declares a single-line `name` and an optional multi-line `description`, its `assignees` (roster people, by identifier), its `kind` (`human` or `automated`) and, separately, whether its result `needs_confirmation`, a lifecycle `status` (`draft`, `in-development`, `active`, `retired`) and — where it is automated — an `automation_brief` and a `handler`; only `active` steps are served, hold a gate, or reach ClickUp (`redesign-step-fields`, 2026-08); Postgres also owns each product's position and per-step completion, and ClickUp owns human completion. Postgres likewise owns **who is known to the system** — the roster of people, their per-service identities, admin authority and active status — edited only through validated `roster` use cases and no longer a repo-owned file (`move-principals-to-roster`, 2026-08); adding a colleague is an admin action, not a deploy, and the first admin is seeded from `BOOTSTRAP_ADMIN_IDENTITY` by a step that runs between the migration and the server, never inside the serving process. LangGraph is scoped to interpretation, generation and conversation, not to deterministic rule evaluation. See `README.md`'s Scope, Technology and Architecture sections for the reasoning and the obligations each carries.

commerce-ops is a modular monolith: one FastAPI app organized into domain modules as DDD bounded contexts, sharing one Postgres database. Each module follows a lightweight ports-and-adapters shape — domain layer (entities/value objects, no I/O) at the center, application layer (use cases, LangGraph agent graphs) around it, infrastructure layer (FastAPI routes, its own Slack adapter, the Amazon-first marketplace-adapter layer, Postgres repositories) on the outside, each module owning its own driving adapters. Tactical DDD patterns (aggregates, domain events) are adopted per module only as needed, not mandated everywhere. Slack is a first-class two-way interface (conversational + notifications/approvals) alongside the HTTP API, not a secondary add-on.

A module's `application/__init__.py` (`__all__`-exported) is its only public surface, enforced by `import-linter`; `shared` is a Shared Kernel exception (same-or-lower matching layer, never the reverse). `step_handlers/` is the third kind of top-level package after the bounded contexts and `shared`: it holds every step handler, grouped by the discipline its registered name starts with, and reaches `launch` only through that public surface, under one `import-linter` contract covering every handler present and future. A handler is a module until it earns being a package, and a package until it earns layers; a handler that is a package re-exports its registration from `__init__.py`, since `@register_step_handler` runs only when the module holding it is imported. See `README.md`'s Architecture section for the full module-boundary contract, rationale, and alternatives considered.

## Deployment and configuration

**Every change reaches the server through a pull request.** Merging to `main` is what triggers the deploy workflow; nothing ships from a local machine, and nothing is deployed by committing to `main` directly. So all work happens on its own branch and merges through a PR — a change's OpenSpec artifacts included, not only its code. Propose a change on a branch named for it, implement there, and make the archive (`openspec archive <change> --yes`, which folds the deltas into `openspec/specs/`) the last commit before the merge, as the archived changes in this repository show. Committing a proposal straight to `main` skips the review the deploy depends on.

**Runtime configuration lives in a GitHub Environment, as secrets.** The `deploy` job declares `environment: production` and renders the host's `.env` from that environment's values. Every value it renders is an Environment **secret**, so read them with `${{ secrets.NAME }}`.

Do not reach for `${{ vars.NAME }}` for anything the application requires. This repository defines no Actions variables at all, and an unset `vars` reference renders an *empty string* rather than failing — so the application starts against a variable that is present but blank, which is a harder fault to read than a missing one. That has already cost one broken deploy: `BOOTSTRAP_ADMIN_IDENTITY` was set correctly as an Environment secret while `deploy.yml` alone among its neighbours read `vars`, so `.env` received `BOOTSTRAP_ADMIN_IDENTITY=`, the admin-seeding step refused to start a deployment nobody could administer, and the container never became healthy (2026-08). The one deliberate `vars` reference is `LOG_LEVEL`, and it is safe only because it carries a literal fallback (`${{ vars.LOG_LEVEL || 'INFO' }}`) — which is the shape to copy if a future value really should be a variable rather than a secret.

Adding a new runtime variable therefore means four things, not one: set it as an Environment secret, render it in `deploy.yml` from `secrets`, declare it on the settings model in `shared/application/settings.py`, and mirror it in the declared set `tests/unit/shared/application/test_settings.py` compares against. Read it by its literal name in the source, too — the drift check detects consumption by scanning for the name, so a read through a constant looks like a variable nobody uses.
