## 1. Implement

- [x] 1.1 Add `NonStringAnswerError` to `use_cases.py` (design.md — "Where the exception lives")
- [x] 1.2 In `answer_question`, replace the ignore-suppressed return with a check: if `result["messages"][-1].content` is a `str`, return it; otherwise raise `NonStringAnswerError` with a message identifying the actual type received
- [x] 1.3 Remove the `# type: ignore[no-any-return]` and its comment at `use_cases.py:30` — the return is now genuinely `str`-typed without suppression

## 2. Verify slack.py needs no change

- [x] 2.1 Add a test asserting `slack.py`'s `handle_app_mention` posts `_FAILURE_MESSAGE` when `answer_question` raises `NonStringAnswerError` specifically — confirming the existing broad `except Exception` covers it, not assuming it (design.md — Migration Plan, step 4)

## 3. Tests from the spec delta

- [x] 3.1 Test: a question whose language-model response content is a plain string still returns that string (existing "Question receives a generated answer" scenario — regression coverage under the new code path)
- [x] 3.2 Test: a question whose language-model response content is not a plain string (e.g. a list of content blocks) causes `answer_question` to raise `NonStringAnswerError` rather than returning a value (new "Language model response content is not a plain string" scenario)

## 4. Verification

- [x] 4.1 Run `uv run mypy .` — confirm clean with no ignore at `use_cases.py`'s former line 28 (clean; the 20 remaining repo-wide errors are pre-existing, in unrelated in-progress job-runner files and pre-existing `slack` attr-defined findings shared by three sibling test files — none in `use_cases.py` or introduced by this change)
- [x] 4.2 Run `uv run pytest` (scoped: `tests/unit/omni_agent tests/agents/omni_agent` → 43 passed; full-tree run blocked at collection by unrelated untracked WIP files for a different in-progress change (`procrastinate` job-runner work) — not this change's concern)
- [x] 4.3 Run `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports` — all clean on this change's files; `lint-imports` clean repo-wide (8/8 contracts kept)
- [x] 4.4 Run `openspec validate specify-non-string-message-content --strict`
