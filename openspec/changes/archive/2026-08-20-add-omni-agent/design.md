## Context

See `proposal.md` - Why. Relevant constraints from the existing codebase: no LLM/agent dependency exists yet in `pyproject.toml`; the module ports-and-adapters shape (`domain/` / `application/` / `infrastructure/`) is already established by the `products` and `shared` modules; and `AGENTS.md` requires `tests/agents/<module>/` graph tests to be deterministic, with the model client mocked/stubbed rather than making live calls.

## Goals / Non-Goals

**Goals:**
- Pick the concrete libraries and the graph/testing shape so implementation has no open technical decisions left.
- Satisfy the `omni-agent` spec's "no state across invocations" and "model failure is surfaced" requirements through the LangGraph mechanics chosen here, not through hand-rolled guards.
- Satisfy "answer a single question" and "no tool invocation" structurally: a single node that calls the model directly, with no tools bound to it, needs no separate enforcement mechanism.

**Non-Goals:**
- Any configuration/settings abstraction beyond reading `OPENAI_API_KEY` from the environment — out of scope until more than one thing needs configuring.
- Anything about the Slack trigger, the sender-identity guard, or tool calling — all explicitly deferred to later changes per the proposal.

## Decisions

**LangChain's `ChatOpenAI` (`langchain-openai`) over the raw `openai` SDK.** LangGraph's node/state conventions are built around LangChain's `BaseChatModel` interface, so using it avoids hand-rolling message-format glue between the raw SDK and the graph. Alternative considered: the raw `openai` SDK directly in the node — rejected for now since it adds translation code with no present benefit; nothing stops swapping it in later since only one call site exists.

**No checkpointer — statelessness is structural, not a rule the node has to enforce.** The graph is compiled without a checkpointer/store, so LangGraph itself has nowhere to persist state between `invoke()` calls. This is what actually satisfies "no state across invocations" from the spec, rather than the node avoiding memory by convention.

**Model client is a parameter to a graph-builder function, not constructed inside the node.** E.g. `build_graph(model: BaseChatModel) -> CompiledStateGraph`. Production wiring passes a real `ChatOpenAI`; `tests/agents/omni_agent/` passes a fake chat model (e.g. LangChain's `GenericFakeChatModel`) with a scripted response. This is what makes the graph testable without patching internals or touching the network, per the deterministic agent-graph testing tier.

**State shape is LangGraph's conventional `MessagesState`.** The graph is invoked as `graph.invoke({"messages": [HumanMessage(question)]})` and returns a state whose `messages` list ends in an `AIMessage` — the standard single-turn shape for a bare chat-model node, and the shape `GenericFakeChatModel` is built to work against. Chosen over a custom `{question: str, answer: str}` state because it costs nothing extra now and avoids a throwaway schema that would need reworking the moment a second node (or multi-turn use) is added later. This is the schema the tests already written against this change assume.

**Errors propagate; no `try/except` in the node.** The "model failure is surfaced, not masked" requirement is satisfied by simply not catching exceptions from the model call — `graph.invoke()` raises, and the caller (not yet built in this change) decides how to present that. Adding a custom error-handling layer now would be speculative, since there's no caller yet to define what "surfaced" should look like at the boundary.

**API key via ambient `OPENAI_API_KEY`.** `ChatOpenAI` reads this env var by default; no settings/config object is introduced in this change. A config abstraction is deferred until a second piece of configuration exists that would actually need one (e.g. during the Slack-triggering change).

**Module scaffold mirrors `products`/`shared`.** `src/commerce_ops/omni_agent/{domain,application,infrastructure}/` are all created (matching the existing module shape), but only `application/graph.py` holds real code in this change — `domain/` and `infrastructure/` stay empty scaffolding, same as `products/` does today.

## Risks / Trade-offs

- [Risk] Coupling the model call to LangChain's `ChatOpenAI` wrapper ties the project to an abstraction layer with a history of breaking changes across versions. → Mitigation: pin a conservative version range when adding the dependency (task 1.2); only one call site exists, so migrating off it later is cheap.
- [Risk] Nothing checks that `OPENAI_API_KEY` is present until the graph is actually invoked — there's no startup check, since there's no app entry point calling this graph yet. → Mitigation: acceptable now because nothing triggers the graph in production in this change; revisit when the Slack-triggering change adds a real entry point.
- [Risk] No persistence means genuinely no cross-invocation memory, which is correct now but will need revisiting once multi-turn conversations matter. → Mitigation: intentionally deferred; recorded here so the follow-up change doesn't have to rediscover the constraint.

## Migration Plan

Purely additive — a new module and two new dependencies. No data migration. Rollback is deleting `src/commerce_ops/omni_agent/`, `tests/agents/omni_agent/`, and the two new dependency lines in `pyproject.toml`.
