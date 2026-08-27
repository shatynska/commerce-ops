## Why

Registering a step handler is an import side effect: `@register_step_handler` runs when the handler's module is imported, and `registrations.py` is what causes that import in every process that consults the registry. So **every such process pays every handler's import cost**, whether or not it will ever invoke one.

Today one handler exists and it is expensive. `subcategory_advisor/application/graph.py:36-39` imports `langchain_core`, `langchain_openai` and `langgraph.graph` at module level, so importing it costs **1,988 modules and 0.89s** locally — for a module whose registration is one dictionary entry. The model client it loads is not even used at import: `_graph()` is already `functools.lru_cache`d, so *construction* was always deferred. Only the import was not.

This is about to matter twice over. `let-the-handler-report-see-handlers` needs `check_step_handlers` — a container start-chain process that currently costs 0.31s in total — to import `registrations`, which would quintuple it. And `docs/deferred-work.md:204-222` records that the start chain reaches healthy at ~26.5s on the host against a 60s window, that one added process has already broken every deploy once, and that the host figure has **still not been measured**.

It also does not stay at one handler. The whole point of `group-step-handlers` is that many are coming; at twenty handlers, every process consulting the registry loads twenty model clients to read twenty dictionary keys.

## What Changes

- Defer the heavy imports in `subcategory_advisor/application/graph.py` into the functions that use them. All four names are used only inside function bodies except one annotation, and `from __future__ import annotations` is already in force, so the annotation moves under `TYPE_CHECKING`:

  | Name | Used at | Moves to |
  | --- | --- | --- |
  | `StateGraph`, `START`, `END` | `build_graph` body (`:126-129`) | inside `build_graph` |
  | `ChatOpenAI` | `build_production_graph` body (`:135`) | inside `build_production_graph` |
  | `HumanMessage` | the `recommend` node body (`:116`) | inside `build_graph`, captured by the nested `recommend` closure |
  | `BaseChatModel` | one annotation (`:106`) | `TYPE_CHECKING` block |

- Record the rule this establishes: **importing a handler module registers its name and loads nothing else.** A handler's dependencies are loaded when it runs, not when it is registered.
- Add a test asserting the property directly: importing `commerce_ops.registrations` — the one list, not one handler module — in a fresh interpreter leaves `langgraph` and `openai` out of `sys.modules`. The list rather than the module, because this property regresses the next time someone adds a convenient top-level import to the *next* handler, in a file no single-module test names.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: gains a requirement that registering a handler does not load what the handler needs in order to run. The capability already specifies what a handler is given, what it may return and how the pass treats it; what it never said is what registration itself is allowed to cost — and that cost is a deployment property, since every process consulting the registry pays it.

## Impact

- `src/commerce_ops/subcategory_advisor/application/graph.py`: four import statements move. No behaviour change — `build_graph`, `build_production_graph` and the node all do exactly what they did.
- New test asserting that importing `commerce_ops.registrations` — and so every handler the deployment registers — loads no model client; `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` continues to pass unmodified, since it imports the module and calls `build_graph(stub)` exactly as before.
- **Unblocks `let-the-handler-report-see-handlers`**, whose Decision 2 depends on this: with it landed, importing `registrations` into the start chain costs the four job modules (1,110 modules, 0.42s) instead of 2,610 modules and ~1.3s.
- **Overlaps `group-step-handlers`**, which moves this exact file. Either order works; if that change lands first the same four import statements move at `step_handlers/listing/subcategory_advisor.py` instead. Worth landing this one first, since it is the smaller diff of the two.
- **Does *not* speed up the web process, and this proposal claims no such thing.** `main.py` pulls LangGraph by two independent paths — the omni_agent Slack router (`main.py:34`, via `omni_agent/infrastructure/driving/slack.py`) and the advisor handler via `registrations` — so closing one leaves the other. `deferred-work.md:216` names uvicorn's LangGraph import as the leading unverified hypothesis for the host's 14× start-chain factor; testing that hypothesis means deferring `omni_agent`'s graph imports too, which is a separate change against a different module and is recorded in design.md's Open Questions rather than folded in here.
- Untouched: `Dockerfile`, `alembic/`, `pyproject.toml`, every runtime variable, and the dependency set — nothing is removed, only imported later.
