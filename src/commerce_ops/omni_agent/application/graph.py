from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph


def build_graph(model: BaseChatModel) -> CompiledStateGraph[MessagesState]:
    def call_model(state: MessagesState) -> dict[str, list[BaseMessage]]:
        response = model.invoke(state["messages"])
        return {"messages": [response]}

    graph = StateGraph(MessagesState)
    graph.add_node("call_model", call_model)
    graph.add_edge(START, "call_model")
    graph.add_edge("call_model", END)
    return graph.compile()


def build_production_graph() -> CompiledStateGraph[MessagesState]:
    return build_graph(ChatOpenAI(model="gpt-4o-mini"))
