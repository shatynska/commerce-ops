"""The sub-category advisor's graph and what it proposes.

`subcategory-advisor`: given a product's name and its marketplace, propose
the Amazon sub-category node it belongs in and name the compliance fields
and certifications that node then demands — the work `lp.listing.007`
describes.

Shaped like `omni_agent/application/graph.py`, including its
`build_graph(model)` / `build_production_graph()` split. That split is not
decoration: it is the seam that lets `tests/agents/` drive the graph with
a stubbed model, which is what "deterministic agent-graph tests without
live model calls" requires.

**The advisor proposes; it never decides.** Where it can support a node
choice it proposes the step's satisfying outcome together with the
recommendation, which a person then accepts or rejects. Where it cannot,
it proposes a **non-terminal** outcome carrying that as its reason — never
a satisfying one with a disclaimer buried in the text. The difference is
load-bearing: under `launch-step-automation` a terminal proposal is held
for someone's acceptance while a non-terminal one is recorded directly, so
proposing satisfaction alongside "I cannot tell you the category" would
leave a compliance-relevant step one unread paragraph from being recorded
`Satisfied`.

A model failure, and a response whose content is not a plain string, both
surface. A masked failure here would not merely return a poor answer — it
would reach a person as a recommendation to accept and become the evidence
for a compliance-relevant decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from commerce_ops.launch.application import Blocked, Satisfied

__all__ = [
    "AdvisorState",
    "NonStringRecommendationError",
    "Proposal",
    "build_graph",
    "build_production_graph",
    "propose",
]

# What the advisor says when it cannot support a node choice. Recognised
# by reading the model's own prose rather than by a sentinel token: the
# recommendation is written for a person either way, and a token would be
# one more thing the model could get wrong while still being right.
_UNSUPPORTED_MARKERS = (
    "cannot support",
    "can not support",
    "no confident answer",
    "unable to support",
)

_PROMPT = """\
You are advising on where an Amazon product listing belongs.

Product: {product_name}
Marketplace: {marketplace}

Name the sub-category node this product belongs in, expressed as the full
path from the top-level category down. Then name the compliance fields and
certifications that node demands. Then name the alternative node a reader
would most plausibly have chosen instead, and why this one was preferred.

If the category structure gives you no confident answer for this product
and marketplace, say plainly that you cannot support a node choice, and do
not name a node as though it were supported.
"""


class AdvisorState(TypedDict, total=False):
    """The graph's state: what it is given, and what it produced."""

    product_name: str
    marketplace: str
    recommendation: str


class NonStringRecommendationError(Exception):
    """The model answered with content that is not a plain string.

    Named rather than coerced, following `omni_agent`'s
    `NonStringAnswerError` precedent for the same words: a `str(...)` of a
    content block list is a fabricated recommendation, which is exactly
    what the requirement forbids.
    """


@dataclass(frozen=True, slots=True)
class Proposal:
    """What the advisor hands the runtime: an outcome and the text."""

    outcome: Any
    result: str


def build_graph(model: BaseChatModel) -> Any:
    """The graph over an injected model — the testable seam."""

    def recommend(state: AdvisorState) -> dict[str, str]:
        prompt = _PROMPT.format(
            product_name=state.get("product_name", ""),
            marketplace=state.get("marketplace", ""),
        )
        # No `try` around this: a model that is unavailable or errors must
        # surface, not become a recommendation.
        response = model.invoke([HumanMessage(content=prompt)])
        content = response.content
        if not isinstance(content, str):
            raise NonStringRecommendationError(
                "the language model answered with content that is not a "
                f"plain string ({type(content).__name__}); refusing to "
                "build a recommendation from it"
            )
        return {"recommendation": content}

    graph = StateGraph(AdvisorState)
    graph.add_node("recommend", recommend)
    graph.add_edge(START, "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


def build_production_graph() -> Any:
    """The graph the registered handler runs, over the configured model."""
    return build_graph(ChatOpenAI(model="gpt-4o-mini"))


def _is_unsupported(recommendation: str) -> bool:
    lowered = recommendation.lower()
    return any(marker in lowered for marker in _UNSUPPORTED_MARKERS)


def propose(
    *,
    product_name: str,
    marketplace: str,
    graph: Any | None = None,
) -> Proposal:
    """Run the advisor and say what it proposes for the step.

    The recommendation reaches the reader whole — never summarised,
    truncated or re-encoded — because it is both what a person decides on
    and what the recording keeps as evidence.
    """
    running = graph if graph is not None else build_production_graph()
    state = running.invoke({"product_name": product_name, "marketplace": marketplace})
    recommendation = state["recommendation"]

    if _is_unsupported(recommendation):
        return Proposal(
            outcome=Blocked(
                reason=(
                    "the sub-category advisor could not support a node "
                    f"choice for '{product_name}' on '{marketplace}'"
                )
            ),
            result=recommendation,
        )
    return Proposal(outcome=Satisfied, result=recommendation)
