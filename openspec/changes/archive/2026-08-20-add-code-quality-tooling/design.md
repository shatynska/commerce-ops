## Context

AGENTS.md already commits this project to `uv` (deps/env), `ruff` (lint + format), and `mypy` (types), and to `uv run pytest` as the test command against a `tests/**/test_*.py` glob. None of that is wired into git hooks yet, and there's no established test-tier or directory structure beyond the flat glob. See proposal.md for motivation.

No `pyproject.toml` or `uv.lock` exists in the repository yet — the prior `project-foundation` change established only README.md/AGENTS.md content and `.gitignore`, not a Python project. This change therefore also bootstraps the base `uv`-managed project (see Decisions below), rather than assuming one to layer hooks on top of.

## Goals / Non-Goals

**Goals:**
- Enforce ruff/mypy/gitlint/unit-tests automatically at commit time, without relying on contributors remembering to run them.
- Keep commit-time feedback fast enough that it doesn't invite `--no-verify` bypassing.
- Give tests a directory structure that scales with the project's module/layer architecture, so test-tier selection (unit vs. agents vs. integration) is a path, not a marker someone can forget.
- Avoid adding a Node.js toolchain to an otherwise pure-Python project.

**Non-Goals:**
- CI pipeline configuration (this change wires local git hooks; CI running the full suite, including integration tests, is assumed to already run tests some other way and is out of scope here).
- Changelog generation or automated version bumping (a capability tools like `commitizen` offer beyond plain commit-message linting; not needed now).
- Retroactively writing or migrating any existing tests — there are none yet in this project; this change only establishes where future tests go.

## Decisions

### Hook orchestrator: `pre-commit` framework

Chosen over hand-rolled `.git/hooks` scripts or a Husky-style bespoke runner. `pre-commit` is the Python-ecosystem's direct equivalent of husky + lint-staged combined: it manages hook installation *and* restricts hooks to staged files, in one tool, with hook definitions declared in version-controlled `.pre-commit-config.yaml` rather than living only on a contributor's machine.

### Commit-message linting: `gitlint`, not `commitlint`

`commitlint` is a Node package; pulling it in (even via `npx`, without a persistent Node dependency in `package.json`) still means every contributor needs a working Node install for a project whose stack is otherwise pure Python. `gitlint` does the equivalent job (lints commit messages against configurable rules, conventional-commits style included) as a pure-Python tool installable via `uv` alongside the rest of the dev toolchain. Rejected alternative: `commitizen` — does everything `gitlint` does plus changelog/version-bump automation, which is more than this change needs right now (non-goal above); revisit if changelog automation becomes a real need.

### Hook staging: unit tests at commit-time (strict), integration tests at pre-push

`pre-commit` supports distinct hook stages. Splitting by stage rather than running everything at both points balances two failure modes: gating nothing at commit-time lets broken code accumulate locally before it's caught; gating everything (including slower integration tests) at commit-time makes every commit slow and invites `--no-verify`. Unit tests (including the LangGraph agent-graph tests, which are deterministic and mocked per AGENTS.md's testing strategy, so they carry no real runtime cost) run on every commit. Integration tests, which are assumed to touch Postgres or otherwise carry I/O cost, are deferred to `pre-push` — still enforced before code leaves the machine, just not on every intermediate commit.

### Test directory structure: mirrors `src/<module>/<layer>`, not colocated

```
tests/
  unit/
    catalog/{domain,application,infrastructure}/test_*.py
    orders/... | support/... | analytics/...
  agents/
    catalog/test_*_graph.py   # LangGraph graph tests, unit-tier
    ...
  integration/
    catalog/test_*.py
    ...
```

Considered and rejected: colocating test files next to the source file they cover (the NestJS `*.spec.ts`-next-to-`*.service.ts` convention the user is used to). Rejected because:
- Python packaging: a colocated test file inside `src/<module>/...` ships inside the built package unless explicitly excluded; a separate `tests/` tree is excluded by default.
- Import resolution: pytest's classic import mode can collide on same-named `test_*.py` files scattered across colocated directories without careful `__init__.py`/import-mode handling; a single `tests/` tree sidesteps this.
- Architectural fit: this project's domain layer is defined (AGENTS.md) as having no I/O or framework dependencies; colocating pytest-dependent test files inside that layer's directory cuts against that boundary.

The mirrored structure still gives "test location tells you what it covers" — the property the user wanted from colocation — without those costs, and it directly reflects this project's existing module × layer architecture (catalog/orders/support/analytics × domain/application/infrastructure).

Considered and rejected: marker-based tiering (`@pytest.mark.unit` / `@pytest.mark.integration` inside a flat `tests/` tree, selected via `pytest -m unit`). Rejected because nothing stops a slow or I/O-bound test from being mismarked or left unmarked; a directory boundary is enforced by where the file physically lives, not by a contributor remembering a decorator.

### Scope: fold Python project bootstrap into this change, not a separate prerequisite

No `pyproject.toml` exists yet, so the tooling this change adds (pre-commit, gitlint, ruff, mypy, and pytest as dev dependencies, plus pytest's tier configuration) has nothing to attach to. Splitting bootstrap into its own prerequisite change was considered and rejected: the only content such a change would have is "create `pyproject.toml`, pin a Python version" — a single trivial decision with no independent rationale of its own, and AGENTS.md's incremental-scope guidance is about avoiding *unrelated* concerns sharing a change, not about a dependency's dependency needing its own change. Bootstrap is folded into task group 1 here instead, decided explicitly (Python 3.12 pinned — current stable, well-supported by FastAPI and LangGraph, no other constraint driving the choice — plus a dev-dependency group) rather than left to whatever `uv add`'s implicit auto-init would otherwise choose silently.

### Day-one hook failure: seed placeholder tests, not exit-code tolerance or deferred activation

The commit-time and pre-push pytest hooks have nothing to collect until a real test exists; vanilla pytest exits non-zero (code 5, "no tests collected") on empty collection, which `pre-commit` treats as hook failure. Two alternatives were considered and rejected in favor of seeding one trivial placeholder test per tier:
- **Tolerate empty collection** (wrap the hook to treat exit code 5 as success): masks the same failure mode later — a tier that *should* have tests but silently has none again exits 5 and passes, defeating the strictness goal.
- **Defer hook activation** (land pre-commit/gitlint now, wire the pytest hook stage in later): means the hook ships disabled at the moment this change lands, which is the outcome the whole change exists to avoid.

A placeholder test per tier is deleted once real tests land there, and keeps the hook meaningfully enforcing "the suite passes" from day one rather than "the suite exists," which the tolerate-empty-collection approach would silently downgrade to.

## Risks / Trade-offs

- [Commit-time unit-test tier grows slow as the suite grows, eroding the fast-feedback goal] → Revisit the unit/integration boundary if commit-time `pytest` exceeds a few seconds; moving a slow "unit" test to `integration/` is a file move, not a rewrite, because the boundary is directory-based.
- [`gitlint`'s rule set is less widely known than `commitlint`'s, so contributors coming from a JS background may need a moment to learn its config format] → `.gitlint` config and its rule names are documented inline in the config file itself as part of implementation.
- [Two-stage hook install (`pre-commit install` and `pre-commit install --hook-type pre-push`) is an extra manual step new contributors can forget] → Document both commands together in the same onboarding step (tracked as a task); a missing pre-push hook fails safe (commit-time checks still ran) rather than silently skipping all checks.
- [Day-one hook lockout: the commit-time pytest hook would fail on every commit before any real test exists, since this project currently has zero tests] → Mitigated by seeding one placeholder test per tier as part of this change's own task list (task group 3); each placeholder is deleted once real tests land in that tier.
