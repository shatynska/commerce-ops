## Why

The only step handler this deployment ships blocks the event loop for the whole of an OpenAI round-trip.

`advise_sub_category` is `async def` (`step_handlers/listing/subcategory_advisor.py:366`), as `StepHandler` requires — and `handler_contract.py`'s own note explains why:

> Awaited: a handler is free to reach a model or a service, and the one this change ships does.

But the work it awaits is not awaited at all. `advise_sub_category` calls `propose()`, which is a plain `def` (`:299`), and `propose()` calls:

```python
state = running.invoke({"product_name": product_name, "marketplace": marketplace})
```

`invoke` is LangGraph's **synchronous** entry point. It runs `model.with_structured_output(...).invoke(...)` underneath, which issues a blocking HTTP request to OpenAI. Declaring the enclosing function `async` does not make that non-blocking; it makes it a coroutine that never yields. For the duration of the model call — seconds, and unbounded on a slow or retrying response — the event loop running it cannot progress anything else.

Where that matters:

- **In the worker.** `run_automation_pass` walks every active launch and every automated step within it, awaiting each handler in turn (`automation_pass.py:750`). Nothing else on that loop runs while a handler blocks: not `procrastinate`'s job heartbeat, not a concurrently deferred job, not the ClickUp pass if it overlaps. A pass over N launches with an advisor step serialises N model calls with the loop pinned for each.
- **It is a property of the contract, not of this handler.** `StepHandler = Callable[[StepContext], Awaitable[StepResolution]]` invites exactly this mistake: the type is satisfied by any `async def`, whether or not what it does inside is actually awaitable. Every future handler — and the architecture summary expects them "in quantity", "most … small scripts" (`group-step-handlers`) — can reproduce it, and nothing in the repository would say so. `ruff`'s `ASYNC` rules do not catch it: `ASYNC210` knows `httpx`/`requests` calls, not a third-party graph's `.invoke`.

The fix in the handler is small — LangGraph compiles an `ainvoke` alongside `invoke`, and `langchain_openai`'s model supports it. The reason this is a change rather than a one-line commit is the second point: the obligation belongs in `launch-step-automation`, where it governs handlers that do not exist yet, rather than in one file where it will be re-broken by the next author who copies the shape.

## What Changes

- **`propose()` becomes `async` and awaits `ainvoke`.** `advise_sub_category` awaits it. Nothing else about the advisor's behaviour moves: the same prompt, the same `AdvisorResult` union, the same four routes out of `propose()` (supported, supported-with-empty-comment, supported-but-self-contradicting, unsupported, unreadable), the same `Proposal`, the same `StepResolution`.
- **`build_graph`/`build_production_graph` and the `_graph()` cache are unchanged.** The compiled graph already answers both `invoke` and `ainvoke`; the deferred `langgraph`/`langchain_openai` imports and the `lru_cache` that keeps credential reads out of import time stay exactly as they are, for the reasons the module docstring gives at length.
- **`launch-step-automation` gains the obligation the contract implies:** a handler's model, network and database work is awaited, never performed by a blocking call inside a coroutine, so that one handler's latency costs the pass its own time and not the process's ability to do anything else. Stated as a requirement because the type signature cannot express it and the linter does not check it.
- **The agent-tier tests drive the graph through the async path.** `tests/agents/step_handlers/listing/` currently stubs a model and calls `propose()` synchronously; the stubs must answer `ainvoke`. `design.md` decides whether the tier additionally asserts that no blocking call is made, and how — a test that only checks the answer would pass against a handler that reverted to `invoke`.
- Explicitly **not** in scope: the advisor's prompt, its schema, `_advisor_refuses`'s regex veto, or any judgement it makes; the automation pass's own walk, concurrency, or ordering — this change makes one handler stop blocking, it does not make the pass run handlers in parallel, which is a separate question with its own rate-limit and ordering consequences; and the `Proposal.outcome: Any` / `finding: Any` annotations, which are worth tightening and are not this.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: gains a requirement that a handler performs its external work asynchronously — the pass awaits a handler precisely so that the handler's own waiting does not stop the process, and a handler that blocks defeats that while satisfying the handler type exactly. The requirement is about the handler's obligation, not about how the pass invokes one; the pass already awaits correctly.

`subcategory-advisor` is **not** modified. Every requirement it states — what a recommendation carries, when satisfaction may be proposed, that the marketplace reaching the model is the identifier, that comment content is never parsed — describes what the advisor answers, and this change alters none of it. Whether the model is reached by `invoke` or `ainvoke` is invisible to every one of them.

## Impact

- `src/commerce_ops/step_handlers/listing/subcategory_advisor.py:299-389` — `propose()` becomes `async def`, `running.invoke(...)` becomes `await running.ainvoke(...)`, `advise_sub_category` awaits `propose(...)`. `recommend` inside `build_graph` (`:248-267`) becomes an async node so the model call inside it is awaited too; `StateGraph` accepts async nodes without further change.
- `tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py`, `test_subcategory_advisor_structured_verdict.py`, `test_subcategory_advisor_structured_recommendation.py`, `test_subcategory_advisor_finding_and_tools.py` — the stubbed models answer `ainvoke`, and the tests await `propose`. These are the deterministic agent-tier tests `AGENTS.md` requires; they carry no live model call and gain none.
- `src/commerce_ops/launch/application/handler_contract.py` — `StepHandler`'s docstring names the obligation the new requirement states. The type itself does not change; there is no annotation that expresses "and actually awaits".
- No change to `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`: it already awaits each handler and holds no assumption about how long one takes.
- No migration, no new runtime variable, no schema change, no change to the registered handler name `listing.subcategory_advisor`.
- **Deployment note**: `docs/deferred-work.md` records that the advisor's supported path has never run against a live model. That remains true after this change, and this change does not make it truer — the first real invocation will exercise the async path for the first time.
