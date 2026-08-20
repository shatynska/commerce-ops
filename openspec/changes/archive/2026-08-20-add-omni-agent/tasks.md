## 1. Dependencies

- [x] 1.1 Add `langgraph` to `pyproject.toml` runtime dependencies, pinned to a conservative version range
- [x] 1.2 Add `langchain-openai` to `pyproject.toml` runtime dependencies, pinned to a conservative version range
- [x] 1.3 Run `uv sync` to update the lockfile and environment

## 2. Module scaffold

- [x] 2.1 Create `src/commerce_ops/omni_agent/` with empty `domain/`, `application/`, `infrastructure/` subpackages (`__init__.py` each), matching the existing `products` module shape

## 3. Graph implementation

- [x] 3.1 Implement `application/graph.py`: a `build_graph(model: BaseChatModel) -> CompiledStateGraph` function with a single node that calls `model` with the incoming question and returns its response; compile without a checkpointer
- [x] 3.2 In `application/graph.py`, add a production graph instance that wires a real `ChatOpenAI` (reading `OPENAI_API_KEY` from the environment) into `build_graph`

## 4. Tests

- [x] 4.1 Create `tests/agents/omni_agent/__init__.py`
- [x] 4.2 Test: a question submitted to the graph returns the scripted answer from a fake chat model (e.g. `GenericFakeChatModel`) — covers the "Answer a single question" and "No tool invocation" requirements
- [x] 4.3 Test: two separate `invoke()` calls on the same compiled graph produce independent results, with the second call showing no trace of the first question/answer — covers "No state across invocations"
- [x] 4.4 Test: when the (fake) chat model raises, `invoke()` raises rather than returning a response — covers "Model failure is surfaced, not masked"
- [x] 4.5 Delete `tests/agents/test_placeholder.py`, now that real agent-graph tests exist (per its own docstring)

## 5. Verification

- [x] 5.1 Run `uv run pytest` and confirm the new `tests/agents/omni_agent` tests, and the existing suite, pass
- [x] 5.2 Run `ruff check` and `ruff format --check`
- [x] 5.3 Run `mypy`
