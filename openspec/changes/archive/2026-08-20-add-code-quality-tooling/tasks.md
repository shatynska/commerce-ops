## 1. Project bootstrap

- [x] 1.1 Initialize the uv-managed Python project (`pyproject.toml`), pinning Python 3.12.
- [x] 1.2 Configure a dev-dependency group in `pyproject.toml`.

## 2. Dependencies

- [x] 2.1 Add `pre-commit` and `gitlint` as dev dependencies via `uv`.
- [x] 2.2 Add `ruff` and `mypy` as dev dependencies via `uv` (per AGENTS.md's chosen tooling).
- [x] 2.3 Add `pytest` as a dev dependency via `uv` (required by tasks 4.2, 4.3, and 7.3, which invoke `uv run pytest`).

## 3. Test directory structure

- [x] 3.1 Create `tests/unit/<module>/<layer>/` directories for AGENTS.md's named modules (catalog, orders/inventory, support, analytics × domain/application/infrastructure).
- [x] 3.2 Create `tests/agents/<module>/` directories for LangGraph agent-graph tests.
- [x] 3.3 Create `tests/integration/<module>/` directories.
- [x] 3.4 Seed one trivial placeholder passing test per tier (`tests/unit`, `tests/agents`, `tests/integration`) so hooks have something to collect from day one; delete each placeholder once real tests land in that tier.
- [x] 3.5 Configure `pytest` discovery in `pyproject.toml` so `uv run pytest` covers `tests/unit`, `tests/agents`, and `tests/integration` by default, with a way to select unit+agents only (e.g. `uv run pytest tests/unit tests/agents`) for the commit-time hook.

## 4. Pre-commit hook configuration

- [x] 4.1 Create `.pre-commit-config.yaml` with commit-stage hooks: `ruff check`, `ruff format --check`, `mypy`.
- [x] 4.2 Add a commit-stage local hook that runs `uv run pytest tests/unit tests/agents`.
- [x] 4.3 Add a pre-push-stage local hook that runs `uv run pytest tests/integration`.
- [x] 4.4 Verify hook stages are correctly scoped (commit hooks don't run integration tests; push hook doesn't re-run unit tests) by inspecting `pre-commit run --all-files` and `pre-commit run --hook-stage pre-push --all-files` output separately.

## 5. Commit-message linting

- [x] 5.1 Add `.gitlint` config file with the project's commit-message rules (conventional-commit-style types at minimum).
- [x] 5.2 Add `gitlint` as a `commit-msg`-stage hook in `.pre-commit-config.yaml`.
- [x] 5.3 Verify a malformed commit message is rejected and a well-formed one passes.

## 6. Documentation

- [x] 6.1 Update AGENTS.md's Testing Strategy section: name the tiered `tests/unit/`, `tests/agents/`, `tests/integration/` structure explicitly and note the commit-time vs. pre-push split.
- [x] 6.2 Add an onboarding step documenting both required install commands (`pre-commit install` and `pre-commit install --hook-type pre-push`); create a new "Setup" section in README.md or AGENTS.md if neither currently has one.

## 7. Verification

- [x] 7.1 Run `pre-commit run --all-files` on the repo in its current state and confirm it passes cleanly (no existing code violates the new hooks).
- [x] 7.2 Make a throwaway commit with an intentionally malformed message and confirm `gitlint` blocks it; make one with a real ruff/mypy violation and confirm the corresponding hook blocks it; then revert the throwaway commit.
- [x] 7.3 Confirm `uv run pytest` (full suite) and the commit-time subset (`tests/unit` + `tests/agents`) both collect and pass the seeded placeholder tests.
