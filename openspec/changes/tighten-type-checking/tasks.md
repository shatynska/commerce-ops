## 1. Measure

- [ ] 1.1 Run `uv run mypy --strict .` and record the actual error list — proposal.md's list is a snapshot against `main` at proposal time, not the authority (design.md — Risks, first entry)
- [ ] 1.2 If the count has grown substantially beyond the recorded 10, report that before proceeding rather than absorbing it silently

## 2. Fix `src/`

- [ ] 2.1 `omni_agent/application/graph.py`: supply type arguments for `CompiledStateGraph` at lines 9 and 21, and for the bare `list` in `call_model`'s return annotation at line 10
- [ ] 2.2 `omni_agent/application/use_cases.py:12`: supply type arguments for `CompiledStateGraph`
- [ ] 2.2a Re-measure `use_cases.py:27` **after** 2.1 and 2.2 are applied. Parameterizing `CompiledStateGraph` may make `ainvoke`'s return concrete, turning `.content` into a known union and the error at line 27 from `no-any-return` into `return-value`. Task 2.3 must pin whichever code mypy actually reports
- [ ] 2.3 `omni_agent/application/use_cases.py:27`: add an error-code-scoped `# type: ignore[...]` using the code from 2.2a, with a comment stating that a non-string message content is an unresolved behavioral question, not a typing one, and citing the change named in 5.5 by name. Do **not** decide what non-string content produces, and do **not** use `cast` (design.md — "The `Any` return ... is held with a scoped ignore")
- [ ] 2.4 Verify the diff for 2.3 contains only a comment — no runtime path may change

## 3. Fix `tests/`

- [ ] 3.1 `tests/unit/shared/application/test_settings.py`: remove the four `# type: ignore[attr-defined]` comments at lines 420–423 **together with** the nine-line comment at lines 411–419 that exists solely to explain them — leaving the explanation behind would document two reasons for ignores that no longer exist
- [ ] 3.1a If step 1.1's measurement shows those four ignores are in fact still effective, task 3.1 is void: leave both the ignores and their comment in place and record that the proposal's count was wrong
- [ ] 3.2 `tests/unit/products/infrastructure/test_playbook_loader.py:219`: add `# type: ignore[comparison-overlap]` with a comment recording that the tautology is exactly what the guard exists to detect — do **not** delete or rewrite the assertion (design.md — "The `comparison-overlap` finding gets a narrow ignore")

## 4. Turn the gate on

- [ ] 4.1 Add `[tool.mypy]` to `pyproject.toml` with `strict = true`
- [ ] 4.2 Leave `.pre-commit-config.yaml` and `.github/workflows/ci.yml` unchanged — both already run `uv run mypy .`, and configuration must live in `pyproject.toml` to apply to both
- [ ] 4.3 Do **not** fill in `pyproject.toml`'s placeholder `description` while editing that file — it is unrelated to type checking and is recorded as a non-goal in design.md

## 5. Verification

- [ ] 5.1 Run `uv run mypy .` with no flags — the form the hook and CI use — and confirm it is clean and reports the same file count `--strict` did
- [ ] 5.2 Re-run the probe from proposal.md (`def f(a=[]): x: int = "s"`) in a scratch file inside the repo and confirm mypy now reports it, then delete the scratch file — the gate must be demonstrated to work, not assumed
- [ ] 5.3 Run `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports`
- [ ] 5.4 Run `openspec validate tighten-type-checking --strict`
- [ ] 5.4a Run the gate in the form the commit hook invokes it — `uv run pre-commit run mypy --all-files` — not only `uv run mypy .` directly. This change's own thesis is that a gate reported success while checking less than assumed; verifying only the direct invocation reproduces that error one level up

## 5.5 Archive precondition

- [ ] 5.5 **Before this change is archived**, propose the follow-on change `specify-non-string-message-content`: an `omni-agent` delta settling what `answer_question` produces when message content is not a string, with tests derived from that delta. It needs a product decision (join the text blocks, versus treat it as a failure) that is not this change's to make, so it is a tracked obligation rather than a task this change completes. Without it, 2.3's comment points at nothing and the deferral is untracked rather than deferred
