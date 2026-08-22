from __future__ import annotations

import functools

from langchain_core.messages import HumanMessage
from langgraph.graph.state import CompiledStateGraph

from commerce_ops.omni_agent.application.graph import build_production_graph


@functools.lru_cache
def _get_graph() -> CompiledStateGraph:
    """Compiles the production graph once, on first use.

    Rebuilding per message also rebuilt the `ChatOpenAI` client each time.
    Reusing the compiled object carries no state between invocations: it is
    compiled without a checkpointer, so state lives in the per-invocation
    input and is discarded when `ainvoke` returns. Lazy, so importing this
    module still requires no `OPENAI_API_KEY`.
    """
    return build_production_graph()


async def answer_question(question: str) -> str:
    graph = _get_graph()
    result = await graph.ainvoke({"messages": [HumanMessage(content=question)]})
    return result["messages"][-1].content
