"""Deterministic agent-graph tests for the `omni-agent` capability.

Derived strictly from the ADDED requirements' scenarios in
`openspec/changes/add-omni-agent/specs/omni-agent/spec.md`:

- "Answer a single question" / Scenario: Question receives a generated answer
- "No tool invocation" / Scenario: Processing a question invokes no tools
- "No state across invocations" / Scenario: Two separate invocations do not
  share context
- "Model failure is surfaced, not masked" / Scenario: Language model call
  fails

Per `design.md`'s Decisions, `build_graph(model: BaseChatModel) ->
CompiledStateGraph` takes the chat model as a parameter specifically so a
fake/stub chat model can be substituted here -- no network call, no live
model, per this project's `tests/agents/<module>/` tier.

ASSUMPTION (recorded in test-manifest.md as an unresolved project question):
neither the spec nor design.md pins down the graph's exact state schema
beyond "a single node that calls model with the incoming question and
returns its response". These tests assume the conventional LangGraph
`MessagesState`-style contract -- `invoke({"messages": [HumanMessage(...)]})`
returning a state whose `"messages"` list ends in the model's `AIMessage`
-- since that is the standard shape for a single chat-model node, and the
design's own named test double (`GenericFakeChatModel`) is built around
message-list input/output. If the implementation lands on a different
input/output shape, these tests will fail to collect or fail on their first
run against the real graph, and should be reconciled with the implementer
rather than silently adjusted to match whatever shape appeared.
"""

from __future__ import annotations

from typing import Any

import pytest
from commerce_ops.omni_agent.application.graph import build_graph
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatResult


class _RaisingChatModel(BaseChatModel):
    """Test double whose model call always raises.

    A plain, unconditional failure -- used only to exercise the "model
    failure is surfaced" path. This is a test fixture, not an
    implementation of any part of the omni-agent capability itself.
    """

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("simulated language model failure")

    @property
    def _llm_type(self) -> str:
        return "raising-fake-chat-model"


def test_question_receives_generated_answer() -> None:
    """Scenario: Question receives a generated answer.

    WHEN a question is submitted to the agent
    THEN the agent returns a non-empty response produced by the language
    model from that question.
    """
    scripted_answer = "Paris is the capital of France."
    model = GenericFakeChatModel(messages=iter([scripted_answer]))
    graph = build_graph(model)

    result = graph.invoke(
        {"messages": [HumanMessage(content="What is the capital of France?")]}
    )

    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert ai_messages, "expected the graph to return at least one AI message"
    assert ai_messages[-1].content == scripted_answer
    assert ai_messages[-1].content != ""


def test_processing_question_invokes_no_tools() -> None:
    """Scenario: Processing a question invokes no tools.

    WHEN the agent processes a question
    THEN no tool or function call occurs during that processing.
    """
    model = GenericFakeChatModel(
        messages=iter(["No tools were needed for this answer."])
    )
    graph = build_graph(model)

    result = graph.invoke({"messages": [HumanMessage(content="What is 2 + 2?")]})

    assert not any(isinstance(m, ToolMessage) for m in result["messages"])
    ai_messages = [m for m in result["messages"] if isinstance(m, AIMessage)]
    assert ai_messages, "expected the graph to return at least one AI message"
    assert not ai_messages[-1].tool_calls


def test_two_invocations_do_not_share_context() -> None:
    """Scenario: Two separate invocations do not share context.

    WHEN the agent processes a question, and is then given a second,
    unrelated question in a separate invocation
    THEN the response to the second question is generated without
    reference to the first question or its answer.
    """
    first_question = "What is 2 + 2?"
    first_answer = "4"
    second_question = "What color is the sky?"
    second_answer = "The sky is blue."

    model = GenericFakeChatModel(messages=iter([first_answer, second_answer]))
    graph = build_graph(model)

    graph.invoke({"messages": [HumanMessage(content=first_question)]})
    second_result = graph.invoke({"messages": [HumanMessage(content=second_question)]})

    # No message from the first invocation -- neither the first question nor
    # its answer -- appears anywhere in the second invocation's state.
    assert not any(m.content == first_question for m in second_result["messages"])
    assert not any(m.content == first_answer for m in second_result["messages"])

    ai_messages = [m for m in second_result["messages"] if isinstance(m, AIMessage)]
    assert ai_messages, "expected the graph to return at least one AI message"
    assert ai_messages[-1].content == second_answer


def test_model_failure_is_surfaced() -> None:
    """Scenario: Language model call fails.

    WHEN the configured language model is unavailable or returns an error
    while the agent is processing a question
    THEN the agent's invocation fails visibly rather than returning a
    response as if the call had succeeded.
    """
    graph = build_graph(_RaisingChatModel())

    with pytest.raises(RuntimeError, match="simulated language model failure"):
        graph.invoke(
            {"messages": [HumanMessage(content="What is the capital of France?")]}
        )
