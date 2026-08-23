## 1. Implement

- [ ] 1.1 Add `NonStringAnswerError` to `use_cases.py` (design.md — "Where the exception lives")
- [ ] 1.2 In `answer_question`, replace the ignore-suppressed return with a check: if `result["messages"][-1].content` is a `str`, return it; otherwise raise `NonStringAnswerError` with a message identifying the actual type received
- [ ] 1.3 Remove the `# type: ignore[no-any-return]` and its comment at `use_cases.py:30` — the return is now genuinely `str`-typed without suppression

## 2. Verify slack.py needs no change

- [ ] 2.1 Add a test asserting `slack.py`'s `handle_app_mention` posts `_FAILURE_MESSAGE` when `answer_question` raises `NonStringAnswerError` specifically — confirming the existing broad `except Exception` covers it, not assuming it (design.md — Migration Plan, step 4)

## 3. Tests from the spec delta

- [ ] 3.1 Test: a question whose language-model response content is a plain string still returns that string (existing "Question receives a generated answer" scenario — regression coverage under the new code path)
- [ ] 3.2 Test: a question whose language-model response content is not a plain string (e.g. a list of content blocks) causes `answer_question` to raise `NonStringAnswerError` rather than returning a value (new "Language model response content is not a plain string" scenario)

## 4. Verification

- [ ] 4.1 Run `uv run mypy .` — confirm clean with no ignore at `use_cases.py`'s former line 28
- [ ] 4.2 Run `uv run pytest`
- [ ] 4.3 Run `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports`
- [ ] 4.4 Run `openspec validate specify-non-string-message-content --strict`
