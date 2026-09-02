## Why

The only step handler this deployment ships blocks the event loop for the whole of an OpenAI round-trip.

`advise_sub_category` is `async def`, as `StepHandler` requires — and `handler_contract.py`'s own note explains why:

> Awaited: a handler is free to reach a model or a service, and the one this change ships does.

But the work it awaits is not awaited at all. `advise_sub_category` calls `propose()`, which is a plain `def`, and `propose()` calls:

```python
state = running.invoke({"product_name": product_name, "marketplace": marketplace})
```

`invoke` is LangGraph's **synchronous** entry point. It runs the graph's `recommend` node, which calls `model.with_structured_output(...).invoke(...)` — a blocking HTTP request to OpenAI. Declaring the enclosing function `async` does not make that non-blocking; it makes it a coroutine that never yields. For the duration of the model call — seconds, and unbounded on a slow or retrying response — the event loop running it cannot progress anything else.

Symbol names rather than line numbers throughout: this file's citations rotted once already while the change sat on a branch, and a symbol does not move.

Where that matters:

- **In the worker.** `run_automation_pass` walks every active launch and every automated step within it, awaiting each handler in turn (`_invoke` in `automation_pass.py`). Nothing else on that loop runs while a handler blocks: not `procrastinate`'s job bookkeeping, not a concurrently deferred job, not the ClickUp pass if it overlaps. `worker.py` runs `app.run_worker_async()` on one `asyncio.run` loop, so that loop is the process. A pass over N launches with an advisor step serialises N model calls with the loop pinned for each.
- **It is a property of the contract, not of this handler.** `StepHandler = Callable[[StepContext], Awaitable[StepResolution]]` invites exactly this mistake: the type is satisfied by any `async def`, whether or not what it does inside is actually awaitable. Every future handler — and `group-step-handlers`' proposal expects them "in quantity", "most … small scripts" — can reproduce it, and nothing in the repository would say so. `ruff` does not catch it either: this project selects ruff's default rules, so the `ASYNC` group is not even enabled, and `ASYNC210` would not have caught it if it were — it knows `httpx`/`requests` call sites, not a third-party graph's `.invoke`.

The fix in the handler is small — LangGraph compiles an `ainvoke` alongside `invoke`, and `langchain_openai`'s model supports it. The reason this is a change rather than a one-line commit is the second point: the obligation belongs in `launch-step-automation`, where it governs handlers that do not exist yet, rather than in one file where it will be re-broken by the next author who copies the shape.

## What Changes

- **`propose()` becomes `async` and awaits `ainvoke`; `recommend` becomes an async node awaiting the model.** `advise_sub_category` awaits `propose()`. Both frames move, because the blocking call is in the node, not in `propose()`: converting only `propose()` moves the block one frame down and buys nothing. Nothing else about the advisor's behaviour moves: the same prompt, the same `AdvisorResponse` wire schema, the same `_from_wire` conversion, the same **six** exits from `propose()` — supported, supported-with-empty-comment, supported-but-self-contradicting, contradiction, unsupported, and no-verdict-readable — the same `Proposal`, the same `StepResolution`.
- **The graph becomes async-only, and that is deliberate.** What is unchanged is the `build_graph(model)` / `build_production_graph()` split, the deferred `langgraph`/`langchain_openai` imports, and the `lru_cache` on `_graph()` that keeps credential reads out of import time — all for the reasons the module docstring gives at length. What *does* change is that a graph whose only node is a coroutine no longer answers `invoke`: LangGraph raises `TypeError: No synchronous function provided to "recommend"`. Every caller therefore moves to `await propose(...)`. This is a feature, not a cost — see `design.md` Decision 2: it is what makes the blocking path unrepresentable rather than merely discouraged.
- **`launch-step-automation` gains the obligation the contract implies.** Its normative text, its boundary (what a dependency offering only a blocking entry point is expected to do), and its observable are settled in this proposal and specified in the delta, not left to the delta writer. See *Capabilities* below.
- **The test migration spans eight files across two tiers, and the stubs are not the work.** Every stub runnable in all eight files already answers `async def ainvoke` — that part is done. The work is that the `propose()` call sites become `await`ed, the tests holding them become `async` under `@pytest.mark.anyio`, and the three files carrying no async test yet gain the per-file `anyio_backend` fixture this repository uses. One of the eight is in the commit-time `tests/unit` tier, not `tests/agents`.
- Explicitly **not** in scope: the advisor's prompt, its schema, `_advisor_refuses`'s regex veto, or any judgement it makes; the automation pass's own walk, concurrency, or ordering — this change makes one handler stop blocking, it does not make the pass run handlers in parallel, which is a separate question with its own rate-limit and ordering consequences; enabling ruff's `ASYNC` rule group, which is a repository-wide linting decision and would not have caught this defect anyway; `omni_agent`'s `call_model` node, which has the same sync-node shape and is governed by `omni-agent`, not by this capability (recorded as a finding, see *Impact*); and the `Proposal.outcome: Any` / `finding: Any` annotations, which `docs/deferred-work.md` already holds.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-step-automation`: gains **A handler's waiting does not stop the process**.

  *Normative substance.* A handler SHALL reach a model, a service or a database such that waiting for the answer yields control to whatever else the invoking process is running. Where a dependency offers an asynchronous entry point the handler SHALL use it. Where a dependency offers **only** a blocking one, the handler SHALL await it off the invoking thread and SHALL say in the handler why no asynchronous entry point was available — the thread offload is compliant, and unexplained is not, because an unexplained offload is indistinguishable from one nobody checked. How a handler waits SHALL NOT change what it produces.

  *Why it is a requirement and not a comment.* The type cannot express it — `Awaitable[StepResolution]` is satisfied by a coroutine that never yields — and no linter checks it. So the obligation is carried by the handler's own tests, which is why the requirement is stated with an observable a test can assert: while a handler's dependency has not yet answered, other work scheduled on the invoking loop progresses.

  *What it is not.* It is not a licence to run handlers concurrently. The pass's serial walk is untouched, and the requirement governs the handler's obligation, not how the pass invokes one — the pass already awaits correctly.

`subcategory-advisor` is **not** modified. Every requirement it states — what a recommendation carries, when satisfaction may be proposed, that the marketplace reaching the model is the identifier, that comment content is never parsed, that the converted schema is the one the call site passes — describes what the advisor answers, and this change alters none of it. Whether the model is reached by `invoke` or `ainvoke` is invisible to every one of them. Its *converted schema* scenario is nonetheless guarded by a test that must change, because that test calls `propose()` synchronously; see `tasks.md`.

## Impact

- `src/commerce_ops/step_handlers/listing/subcategory_advisor.py` — `propose()` becomes `async def` and `running.invoke(...)` becomes `await running.ainvoke(...)`; `recommend` inside `build_graph` becomes `async def` and `structured.invoke(...)` becomes `await structured.ainvoke(...)`; `advise_sub_category` awaits `propose(...)`. `StateGraph` accepts an async node without further change (verified against `langgraph 1.2.11`, which is what `uv.lock` resolves; `pyproject.toml` declares a floor, not a pin). `_graph()`'s `lru_cache` is safe across loops — a compiled graph holds no loop.
- `src/commerce_ops/launch/application/handler_contract.py` — `StepHandler`'s docstring names the obligation the new requirement states. The type itself does not change; there is no annotation that expresses "and actually yields".
- **Eight test files call `propose()` or `build_graph`, across two tiers.** Seven are the deterministic agent-tier tests `AGENTS.md` requires, in `tests/agents/step_handlers/listing/`: `test_subcategory_advisor_graph.py`, `test_subcategory_advisor_structured_verdict.py`, `test_subcategory_advisor_structured_recommendation.py`, `test_subcategory_advisor_finding_and_tools.py`, `test_subcategory_advisor_wire_conversion.py`, `test_subcategory_advisor_wire_recommendation.py`, `test_subcategory_advisor_wire_verdict.py`. The eighth is `tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py` — the **commit-time** tier, and the guard for *The converted schema is the one the call site passes*, a scenario under `subcategory-advisor`'s *The structured-output schema is one the model provider's adapter accepts*. Its `_schemas_the_call_site_passed()` helper calls `propose()` inside a `try`; once `propose` is a coroutine that call raises nothing, runs nothing, leaves `model.schemas` empty, and fails downstream with "the advisor never called `with_structured_output(...)`" — a message accusing the advisor of a fault the test caused. None of the eight carries a live model call and none gains one.
- No change to `src/commerce_ops/launch/infrastructure/driving/automation_pass.py`: `_invoke` already awaits each handler and holds no assumption about how long one takes.
- No migration, no new runtime variable, no schema change, no change to the registered handler name `listing.subcategory_advisor`.
- **Deployment note**: `docs/deferred-work.md` records that the advisor's supported path has never run against a live model. That remains true after this change, and this change does not make it truer — the first real invocation will exercise the async path and the supported path for the first time, together.
- **A finding this change does not fix**: `omni_agent/application/graph.py`'s `call_model` node is sync and calls `model.invoke`, the shape the advisor was copied from. Its caller already awaits `graph.ainvoke`, so LangGraph runs the node on a thread-pool thread and the loop is not pinned — a real difference from the advisor, which blocks the loop outright. It still holds a blocking client inside a graph, and the new requirement does not reach it: `omni_agent` is not a step handler. Recorded for `docs/deferred-work.md` rather than folded in, per `AGENTS.md`'s scope rule.
