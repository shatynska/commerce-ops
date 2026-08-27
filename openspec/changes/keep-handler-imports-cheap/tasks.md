## 1. Observe the cost before changing it

- [ ] 1.1 Record the baseline in a fresh interpreter: import `commerce_ops.subcategory_advisor.application.handler`, count `sys.modules` and note whether `langgraph` and `openai` are present. Expect ~1,988 modules and both present. This figure goes in the PR description.
- [ ] 1.2 Record the same for `commerce_ops.registrations` (expect ~2,610) and for the four job modules alone (expect ~1,110, neither library present), so the handler's share is attributed rather than assumed.

## 2. Write the guard first

- [ ] 2.1 Add a test asserting that importing the handler module leaves `langgraph` and `openai` out of `sys.modules`. Drive it in a **subprocess**, following the pattern `tests/unit/test_registrations_across_processes.py` already uses for fresh-interpreter properties — within one interpreter another test may have imported LangGraph already, and the assertion would be meaningless (design.md, Decision 2).
- [ ] 2.2 Assert the positive half in the same test: the handler's name is in `HANDLERS` after the import. The requirement is that registration still happens *and* costs nothing; a test asserting only absence would pass against a module that registers nothing at all.
- [ ] 2.3 Run it and confirm it **fails** on the unmodified tree. A guard that is green before the change guards nothing.

## 3. Defer the imports

- [ ] 3.1 In `subcategory_advisor/application/graph.py`, move `StateGraph`, `START`, `END` (`:39`) into `build_graph`; `ChatOpenAI` (`:38`) into `build_production_graph`; `HumanMessage` (`:37`) into the `recommend` node.
- [ ] 3.2 Move `BaseChatModel` (`:36`) into a `TYPE_CHECKING` block. `from __future__ import annotations` is already in force at `:31`, so the annotation at `:106` needs no other change.
- [ ] 3.3 At each deferred import, leave a one-line comment naming the reason — registration must not load what running needs — so the next reader does not tidy it back to the top of the file.
- [ ] 3.4 Change nothing else: not the state schema, not the node's logic, not the `build_graph` / `build_production_graph` split that `tests/agents/` drives, not `__all__`.
- [ ] 3.5 Re-run 2.1 and confirm it passes.

## 4. Record the rule

- [ ] 4.1 Extend `graph.py`'s module docstring to state the rule and why the imports sit where they do, alongside its existing note that the model is constructed lazily — the two are the same reasoning one step apart.
- [ ] 4.2 State the rule in `README.md`'s Architecture section beside the handler conventions: importing a handler registers its name and loads nothing else, because every process that consults the registry imports every handler.
- [ ] 4.3 If `group-step-handlers` has already landed, add the rule to the handler-shape conventions it recorded rather than starting a second list.

## 5. Verify

- [ ] 5.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `uv run lint-imports`. Watch mypy specifically: the `TYPE_CHECKING` annotation at `:106` is the one change that could break type resolution.
- [ ] 5.2 Run `uv run pytest tests/unit tests/agents`. `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` must pass **unmodified** — it imports the module and calls `build_graph(stub)`, both of which behave identically. If it needs editing, the deferral changed behaviour and something is wrong.
- [ ] 5.3 Re-run 1.1's measurement and record the after figure in the PR beside the before. This is the change's headline evidence.
- [ ] 5.4 Confirm the web process is **unchanged**: `import commerce_ops.main` still pulls `langgraph`, via the omni_agent router. That is expected and is not a failure of this change (design.md, Decision 3) — verifying it prevents a false claim in the PR description.
