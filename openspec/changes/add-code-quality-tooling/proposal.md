## Why

The project has decided on its formatting/lint/type stack (ruff, mypy, per AGENTS.md) but has no automated gate that enforces it before code is committed, and no enforcement of commit-message quality. Problems currently surface late (in review or CI) instead of at commit time, and there's no established place to put unit vs. integration vs. LangGraph-agent tests as the codebase grows.

## What Changes

- Adopt the `pre-commit` framework as the git-hook orchestrator (the Python-ecosystem equivalent of husky + lint-staged combined).
- Wire `ruff check`, `ruff format`, and `mypy` into commit-time hooks.
- Add `gitlint` as a `commit-msg` hook to enforce commit-message conventions — chosen over `commitlint` specifically to avoid introducing a Node.js dependency into an otherwise pure-Python project.
- Add a unit-test tier to commit-time hooks, run via `pytest`, kept strict (commit is blocked on failure).
- Reserve integration tests for the `pre-push` hook stage, not commit-time, to keep commits fast.
- Establish a `tests/` directory structure that mirrors the source's module/layer shape (catalog, orders/inventory, support, analytics × domain/application/infrastructure), replacing colocated-test styles from other ecosystems (e.g., NestJS's `*.spec.ts` next to source) with a structure equivalent in spirit but idiomatic for Python/pytest packaging:
  - `tests/unit/<module>/<layer>/` — fast, mocked, commit-time.
  - `tests/agents/<module>/` — LangGraph agent-graph tests (deterministic, mocked LLM responses per AGENTS.md's testing strategy); treated as unit-tier and run at commit-time since they carry no network/IO cost.
  - `tests/integration/<module>/` — pre-push tier.
- Bootstrap the `uv`-managed Python project itself (`pyproject.toml`, a pinned Python version, a dev-dependency group) — no such project scaffolding exists in the repo yet, so this change establishes it rather than assuming it as a foundation to build hooks on top of.
- Seed one trivial placeholder test per tier (`tests/unit`, `tests/agents`, `tests/integration`) so the new commit-time and pre-push pytest hooks have something to collect from day one, instead of failing on empty collection before any real test exists.

This is a tooling/process change only: it does not alter product-level behavior, so no capability specs are introduced or modified (`skip_specs: true`).

## Capabilities

### New Capabilities

None — no product-facing behavior is introduced.

### Modified Capabilities

None — no existing requirements change.

## Impact

- New file: `.pre-commit-config.yaml` (hook definitions and stages).
- New file: `.gitlint` (commit-message rule configuration).
- New file: `pyproject.toml` (created, not just edited — no Python project scaffolding exists in the repo yet), pinning Python 3.12 and declaring `pre-commit`, `gitlint`, `ruff`, `mypy`, and `pytest` as dev dependencies (managed via `uv`); pytest configuration registered for the unit/agents/integration split.
- New directory structure under `tests/`, mirroring `src/<module>/<layer>`, using `tests/unit/**/test_*.py`, `tests/agents/**/test_*.py`, and `tests/integration/**/test_*.py` — each tier seeded with a placeholder test. The existing `tests/**/test_*.py` glob named in AGENTS.md already matches these tiered paths, so this is a clarification of tier semantics, not a fix to a broken glob.
- AGENTS.md's Testing Strategy section will need its glob description clarified to name the tiers explicitly and note the commit/push hook split (tracked as a task, not a spec change, since AGENTS.md documents process, not product behavior).
- Contributor workflow: local `pre-commit install` (and hook-level `pre-commit install --hook-type pre-push` for the push-stage hooks) becomes a required one-time setup step.
