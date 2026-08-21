from __future__ import annotations

from langchain_core.messages import HumanMessage

from commerce_ops.omni_agent.application.graph import build_production_graph


def answer_question(question: str) -> str:
    graph = build_production_graph()
    result = graph.invoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content
