<!-- ai-toolkit:development-workflow v1 -->
<!-- Generated. Do not edit inside this block — it is replaced on update.
     Project-specific conventions belong below the closing marker. -->

# Development workflow

These rules establish how work proceeds on this project once it has a foundation. They apply independently of any single tool — each names an obligation as a role to fill, and where this project uses Claude Code, names the binding for that role beneath it.

## Spec-driven development and spec review

Use a specification-driven change process for non-trivial features, changes, and significant architectural decisions. Do not begin implementing or applying a change without a corresponding change proposal recording what is intended and why.

A change's artifacts — its proposal, its design, its specification deltas — are the record of intended behavior. Before any code is written or applied, the proposed change specification must be independently reviewed and verified.

_Claude Code binding:_ dispatch `ai-toolkit:openspec-change-reviewer` to review the change proposal and specification deltas before applying changes or moving to implementation. If revisions to the spec are necessary, make them and re-dispatch `ai-toolkit:openspec-change-reviewer` until the change spec is approved.

## Test design before implementation

Before implementing a change or applying code modifications, derive tests directly from the approved specification deltas — not from implementation code. The test author operates strictly from the specification deltas to prevent shared implementation blind spots.

_Claude Code binding:_ dispatch `ai-toolkit:openspec-test-writer` after the change specification is reviewed and approved, but strictly before applying changes or implementing code.

## Implementation and execution

Only after the specification has passed review and tests have been derived from its specification deltas may the change be applied and implemented in code.

## Verification before any completion claim

Implementation existing is not the same as a change being complete. Run the verification relevant to the change — tests, type checking, linting, formatting, a build, or whatever else the project's conventions require — and do not report a change as complete without having run it.

## Small, reviewable commits

Prefer small, focused commits that represent a complete, meaningful unit of work, over large commits bundling unrelated concerns. After a meaningful milestone is reached, proactively suggest creating a commit rather than waiting to be asked.

Before committing: look at the diff being committed, run the verification relevant to what changed, and check that no secret or unintended file is included. Suggest the commit; do not make it without confirmation.

## Incremental development and scope control

Prefer changes small enough to review in one sitting. Where a change grows to cover multiple independent concerns, or grows too large to review as a unit, consider splitting it into separate changes instead.

Implement only what belongs to the change currently in progress. An improvement noticed along the way, that is not part of that change's stated scope, becomes a separate proposed change rather than being folded in.

## Requirements and assumptions

Do not silently invent a requirement that was not stated and cannot reasonably be inferred. Where an important decision cannot be inferred, ask rather than guess.

Record significant decisions in the project's own artifacts rather than relying on them surviving only in conversation history — a decision that exists only in a conversation is not available to whoever reads the project next.

## The repository is the source of truth

Do not rely on earlier conversation context for information the repository itself can supply. Prefer reading a file, a spec, or a commit over recalling what a previous exchange said about it — the repository does not go stale the way a remembered conversation does, and it is what the next person, or the next session, will actually see.

<!-- /ai-toolkit:development-workflow -->

<!-- ai-toolkit:project-foundation -->

## Testing Strategy

pytest for unit/integration tests on the FastAPI layer and business logic, plus separate deterministic tests for LangGraph agent graphs using mocked/stubbed LLM responses so agent logic is tested without live model calls or nondeterminism.

Tests are split into three directory-based tiers, each mirroring the module/layer architecture above:

- `tests/unit/<module>/<layer>/` — fast, mocked unit tests.
- `tests/agents/<module>/` — deterministic LangGraph agent-graph tests (mocked/stubbed LLM responses); treated as unit-tier since they carry no network/IO cost.
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

**Product Launch is the MVP subdomain and the first deliverable**, driven from Slack and tracked in ClickUp; marketplace integration is deferred pending external access, so no change is sequenced as depending on a marketplace adapter until it is granted. Launch state is owned three ways — the repository owns the playbook *framework* (the gate sequence, opening modes, metric conditions and every coherence rule, in `launch_playbook.py`) while Postgres owns the *step content* as a live set edited only through validated `playbook-authoring` use cases (amended by `move-playbook-steps-to-postgres`, 2026-08); Postgres also owns each product's position and per-step completion, and ClickUp owns human completion. LangGraph is scoped to interpretation, generation and conversation, not to deterministic rule evaluation. See `README.md`'s Scope, Technology and Architecture sections for the reasoning and the obligations each carries.

commerce-ops is a modular monolith: one FastAPI app organized into domain modules as DDD bounded contexts, sharing one Postgres database. Each module follows a lightweight ports-and-adapters shape — domain layer (entities/value objects, no I/O) at the center, application layer (use cases, LangGraph agent graphs) around it, infrastructure layer (FastAPI routes, its own Slack adapter, the Amazon-first marketplace-adapter layer, Postgres repositories) on the outside, each module owning its own driving adapters. Tactical DDD patterns (aggregates, domain events) are adopted per module only as needed, not mandated everywhere. Slack is a first-class two-way interface (conversational + notifications/approvals) alongside the HTTP API, not a secondary add-on.

A module's `application/__init__.py` (`__all__`-exported) is its only public surface, enforced by `import-linter`; `shared` is a Shared Kernel exception (same-or-lower matching layer, never the reverse). See `README.md`'s Architecture section for the full module-boundary contract, rationale, and alternatives considered.
