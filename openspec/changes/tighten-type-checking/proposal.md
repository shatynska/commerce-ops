## Why

`mypy` runs on every commit and in CI, and checks far less than the project assumes.

There is no `[tool.mypy]` section in `pyproject.toml` and no `mypy.ini`, so it runs in default mode — which does not check the bodies of unannotated functions at all. Probed against this repository's own configuration:

```python
def f(a=[]):
    x: int = "s"      # mypy: Success: no issues found in 1 source file
```

Both the `pre-commit` hook and CI's `mypy` step pass on that. The gate exists, runs, and reports success while the error stands.

This matters more here than in an average project. The architecture leans on typing to carry contracts that nothing else enforces: `Protocol` ports (`ProductNameReader`, `ClickUpTaskWriter`) are structural, so a mismatch between a port and its adapter has no runtime symptom until the call fails in production. A type checker that skips unannotated bodies is exactly the wrong tool for that.

**The cost of fixing it is small, and measured rather than estimated.** Running `mypy --strict` over the tree as it stands today produces **10 errors across 4 files** — 5 in `src/`, 5 in `tests/` — and every one is mechanical. The codebase was written to a standard its configuration never asked for.

## What Changes

- **`pyproject.toml` gains a `[tool.mypy]` section enabling `strict`**, so unannotated function bodies are checked and the existing annotations are actually enforced.
- **The 10 existing errors are dispositioned — eight fixed, two suppressed with narrow, documented ignores.** In full, since the list is short enough to state:
  - `omni_agent/application/graph.py` (3) and `use_cases.py` (1) — `CompiledStateGraph` and `list` used without type arguments.
  - `omni_agent/application/use_cases.py:27` — returning `Any` from a function declared to return `str`, where the message content comes back untyped from LangChain. **This one is held, not fixed**: it is a latent behavioral defect, not a typing nit, and deciding what a non-string content should produce is a decision about what the ops team sees in Slack. It gets a narrow `# type: ignore[no-any-return]` naming the change that will resolve it, so the gate can be turned on now without a user-visible contract being settled by whoever happens to implement it. See design.md.
  - `tests/unit/shared/application/test_settings.py` (4) — `# type: ignore` comments that no longer suppress anything; `strict` turns on `warn_unused_ignores`, which is what surfaces them. Removed.
  - `tests/unit/products/infrastructure/test_playbook_loader.py:219` — a `comparison-overlap` on `GateOpening.REQUIRES_CONFIRMATION is not GateOpening.AUTOMATIC`. This one is **not** dead code: `test_the_two_opening_modes_are_distinct` is a deliberate guard against the enum collapsing to a single value, as its own docstring records. It gets a narrow `# type: ignore[comparison-overlap]` with the reason, not a deletion.
- **No behavior changes.** Every fix above is mechanical: annotations, removed dead ignore comments, and two narrow `type: ignore`s that change no runtime path. The one finding that *would* have changed observable behavior — `use_cases.py:27` — is deliberately held rather than fixed here, precisely so this remains true. `.openspec.yaml` therefore sets `skip_specs: true`, and that declaration is accurate rather than convenient.
- **A follow-on change, `specify-non-string-message-content`, is required** to resolve `use_cases.py:27` properly, with a delta on `omni-agent` specifying what a non-string message content produces, and tests derived from that delta rather than from whatever the implementer chose. It is named, and tasks.md 2.5 makes proposing it a precondition of archiving this change, so the ignore comment points at a tracked obligation rather than an idea. It is not written here because the answer is a product decision, not a typing one.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

(none — pure tooling. `skip_specs: true` is set in `.openspec.yaml`, per the rule that specs describe behavior and no behavior changes here.)

## Impact

- **Modified**: `pyproject.toml` (new `[tool.mypy]` section); `omni_agent/application/graph.py`; `omni_agent/application/use_cases.py`; `tests/unit/shared/application/test_settings.py`; `tests/unit/products/infrastructure/test_playbook_loader.py`.
- **No new dependency.** `mypy` is already a dev dependency at `>=2.3.1`.
- **No change to how the gate is invoked.** The `pre-commit` hook and CI both already run `uv run mypy .`; only what that command enforces changes.
- **Every future change is checked more strictly**, including the four others proposed alongside this one. That is the reason to land it early rather than late — each change written before it is written under the weaker gate.
- **The measurement above is a snapshot** taken against `main` at proposal time. If other changes land first, the count moves; the implementation task re-runs the measurement rather than trusting this list.
