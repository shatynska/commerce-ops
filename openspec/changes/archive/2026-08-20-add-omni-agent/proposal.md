## Why

commerce-ops names LangGraph as a core technology and describes a future general-purpose orchestrator agent ("Omni") that will eventually gate behavior on sender identity and call tools, but no agent code exists in the repository yet — no `langgraph` dependency, no agent module, no LLM wiring of any kind. Before adding Slack triggering, an identity/rights guard, or any tool-calling orchestration logic, we want to prove the smallest possible vertical slice end-to-end: a LangGraph graph that takes a question and returns an OpenAI-generated answer. Standing this up now surfaces dependency, packaging, and testing seams (mocking the model client for the deterministic `tests/agents` tier, in particular) while the cost of getting one of them wrong is negligible, rather than debugging the graph for the first time underneath Slack integration and auth all at once.

## What Changes

- Add `langgraph` and an OpenAI-backed chat model integration (e.g. `langchain-openai`) as new runtime dependencies in `pyproject.toml`.
- Scaffold a new `omni_agent` module (`src/commerce_ops/omni_agent/`) following the existing ports-and-adapters module shape. Only the application layer is populated for now: a LangGraph graph with a single node that calls an OpenAI chat model and returns its response.
- No HTTP route and no Slack integration in this change — triggering the graph is added in a follow-up change that also introduces the sender-identity guard at the driving-adapter layer (FastAPI dependency today, Slack Bolt middleware later), not inside this graph.
- No tool calling, no rights-aware branching, and no memory/state persisted across invocations — each invocation is a single, stateless question-in/answer-out call.
- Add `tests/agents/omni_agent/` tests exercising the graph deterministically, with the model client mocked/stubbed per this project's agent-graph testing tier.

## Capabilities

### New Capabilities
- `omni-agent`: the Omni graph's core contract — given a question, invoke the configured OpenAI chat model and return its answer; no tools, no sender/identity awareness, no state persisted across invocations.

### Modified Capabilities
None — no existing specs exist yet in this repository to modify.

## Impact

- `pyproject.toml`: adds `langgraph` and an OpenAI chat-model integration as new runtime dependencies.
- New module `src/commerce_ops/omni_agent/` (domain/application/infrastructure scaffold; only application populated in this change).
- New tests under `tests/agents/omni_agent/`.
- Requires an OpenAI API key available at runtime; how it's supplied (env var, `.env`, config object) is not fixed by this proposal and is left to design.
- Nothing invokes the graph in production yet — no route, no Slack listener — until the follow-up Slack-triggering change lands.
