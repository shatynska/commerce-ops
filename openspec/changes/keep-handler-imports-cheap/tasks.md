## 1. Observe the cost before changing it

- [ ] 1.1 Record the baseline in a fresh interpreter: import `commerce_ops.subcategory_advisor.application.handler`, count `sys.modules` and note whether `langgraph` and `openai` are present. Expect ~1,988 modules and both present. This figure goes in the PR description.
- [ ] 1.2 Record the same for `commerce_ops.registrations` (expect ~2,610) and for the four job modules alone (expect ~1,110, neither library present), so the handler's share is attributed rather than assumed.

## 2. Write the guard first

- [ ] 2.1 Add a test asserting that importing **`commerce_ops.registrations`** — not one handler module by name — leaves `langgraph` and `openai` out of `sys.modules`. This is the delta's third scenario, and it is the form that guards the property: the regression this rule exists to prevent arrives with the *next* handler, in a file this test does not name. Verified achievable: the four job modules reach neither library, and the deferred advisor will not either.
- [ ] 2.2 Assert the positive half in the same test: every name in `HANDLER_MODULES` is registered in `HANDLERS` afterwards. The requirement is that registration still happens *and* costs nothing; a test asserting only absence would pass against a `registrations.py` that imported nothing at all.
- [ ] 2.3 Drive both in a **subprocess**, following the pattern `tests/unit/test_registrations_across_processes.py` already uses for fresh-interpreter properties — within one interpreter another test may have imported LangGraph already, and the assertion would be meaningless (design.md, Decision 2).
- [ ] 2.4 Run it and confirm it **fails** on the unmodified tree. A guard that is green before the change guards nothing.

## 3. Defer the imports

- [ ] 3.1 In `subcategory_advisor/application/graph.py`, move `StateGraph`, `START`, `END` (`:39`) **and** `HumanMessage` (`:37`) into `build_graph`, and `ChatOpenAI` (`:38`) into `build_production_graph`. `recommend` is nested inside `build_graph` (`:107`), so the closure captures `HumanMessage` — putting it there rather than in the node body runs the import once per graph instead of once per invocation, and leaves three deferred imports across two functions rather than four across three.
- [ ] 3.2 Move `BaseChatModel` (`:36`) into a `TYPE_CHECKING` block. `from __future__ import annotations` is already in force at `:31`, so the annotation at `:106` needs no other change.
- [ ] 3.3 At each deferred import, leave a one-line comment naming the reason — registration must not load what running needs — so the next reader does not tidy it back to the top of the file.
- [ ] 3.4 Change nothing else: not the state schema, not the node's logic, not the `build_graph` / `build_production_graph` split that `tests/agents/` drives, not `__all__`.
- [ ] 3.5 Re-run 2.1 and confirm it passes.

## 4. Record the rule

- [ ] 4.1 Extend `graph.py`'s module docstring to state the rule and why the imports sit where they do, alongside its existing note that the model is constructed lazily — the two are the same reasoning one step apart.
- [ ] 4.2 Where the rule goes for a handler *author* depends on what has landed. If `group-step-handlers` is in, add it to the handler-shape conventions that change recorded in `README.md`, rather than starting a second list. If it is not, add one sentence to `README.md:61` — the paragraph that already introduces a step's `handler` field — and no more; the requirement and task 4.1's docstring are what carry the rule until there is a conventions list to join.
- [ ] 4.3 Do not invent a new README section for this. The rule is one sentence and has two existing homes competing for it; a third heading is how conventions get lost.

## 5. Verify

- [ ] 5.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports`. Watch mypy specifically: the `TYPE_CHECKING` annotation at `:106` is the one change that could break type resolution.
- [ ] 5.2 Run `uv run pytest tests/unit tests/agents`. `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` must pass **unmodified** — it imports the module and calls `build_graph(stub)`, both of which behave identically. **This step is the coverage for the delta's scenario *A handler still resolves a step*** — that scenario asks whether deferral changed what the advisor produces, and the stubbed-model cases already specify the answer. Do not write a new test duplicating them. If that file needs editing to pass, the deferral changed behaviour and something is wrong.
- [ ] 5.3 Re-run 1.1's measurement and record the after figure in the PR beside the before. This is the change's headline evidence.
- [ ] 5.4 Confirm the web process is **unchanged**: `import commerce_ops.main` still pulls `langgraph`, via the omni_agent router. That is expected and is not a failure of this change (design.md, Decision 3) — verifying it prevents a false claim in the PR description.
