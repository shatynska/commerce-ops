"""State isolation across the advisor's graph invocations
(`subcategory-advisor`).

This file predates the change `write-the-advisors-finding-to-the-product`
and originally covered every ADDED requirement of `introduce-automation-
runtime`'s delta spec. That change's requirements now read differently
(structured output, not prose) and are re-derived, fresh, in
`test_subcategory_advisor_structured_recommendation.py`,
`test_subcategory_advisor_structured_verdict.py` and
`test_subcategory_advisor_finding_and_tools.py` — see those files' own
headers and `test-manifest.md` for the accounting.

What survives here is *No state across invocations* — a requirement this
change's delta spec does not touch, and one the served spec still states
in full: "each invocation SHALL be independent of every other, including
two invocations for the same product." Its old fixture (a fake model
answering `model.invoke(...)` with a `.content` string) no longer matches
how `recommend` calls the model (`model.with_structured_output(...)`), so
the two scenarios below are ported onto a structured-output-scripting
fake, following `test_subcategory_advisor_structured_recommendation.py`'s
own fake shape, extended to answer a *sequence* of outcomes across
successive `graph.invoke()` calls rather than one fixed outcome.

## Level

`propose()` — the level `test_subcategory_advisor_structured_recommendation.py`
already established for the rest of this capability's scenarios.

## What is fixed, and what is INVENTED

Fixed by the served spec: two invocations, whether for different products
or the same one, share no state.

INVENTED: `_SequencedStructuredChatModel`, answering one `AdvisorResult`
per `graph.invoke()` call in order given, tracking every prompt it
received — the minimum needed to observe what one invocation carried into
the next.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.step_handlers.listing.subcategory_advisor import Supported

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
OTHER_PRODUCT_NAME: Final = "Stainless Steel Insulated Water Bottle, 750 ml"
MARKETPLACE: Final = "ATVPDKIKX0DER"

NODE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = (
    "Demands: FDA food-contact declaration. Rejected alternative: Home & "
    "Kitchen > Home Decor > Decorative Trays."
)
OTHER_NODE: Final = "Sports & Outdoors > Camping & Hiking > Hydration"
OTHER_COMMENT: Final = (
    "Demands: BPA-free material declaration. Rejected alternative: "
    "Kitchen & Dining > Water Bottles."
)


class _SequencedStructuredRunnable:
    def __init__(self, model: _SequencedStructuredChatModel) -> None:
        self._model = model

    def _answer(self) -> dict[str, Any]:
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._model._next_outcome(),
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._model.received.append(input_)
        return self._answer()

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self._model.received.append(input_)
        return self._answer()


class _SequencedStructuredChatModel(BaseChatModel):
    """Answers one `AdvisorResult` per `graph.invoke()` call, in the order
    given — the last is repeated if invoked more times than scripted."""

    outcomes: ClassVar[tuple[Any, ...]] = ()
    index: ClassVar[int]
    received: ClassVar[list[Any]]

    def __init__(self, *outcomes: Any) -> None:
        super().__init__()
        object.__setattr__(self, "outcomes", outcomes)
        object.__setattr__(self, "index", 0)
        object.__setattr__(self, "received", [])

    def _next_outcome(self) -> Any:
        outcome = self.outcomes[min(self.index, len(self.outcomes) - 1)]
        object.__setattr__(self, "index", self.index + 1)
        return outcome

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError(
            "the advisor called the model directly instead of through "
            "`with_structured_output(...)`"
        )

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        return _SequencedStructuredRunnable(self)

    @property
    def _llm_type(self) -> str:
        return "sequenced-structured-fake-chat-model"


def _prompt_text(messages: list[BaseMessage]) -> str:
    return "\n".join(str(message.content) for message in messages)


# ---------------------------------------------------------------------------
# Requirement: No state across invocations (served spec, untouched by this
# change's delta)
# ---------------------------------------------------------------------------


def test_two_invocations_do_not_share_context() -> None:
    """Scenario: Two invocations do not share context.

    WHEN the advisor produces a recommendation, and is then invoked again
    for a different product
    THEN the second recommendation is produced without reference to the
    first product or its recommendation.
    """
    model = _SequencedStructuredChatModel(
        Supported(ok=True, value=NODE, comment=COMMENT),
        Supported(ok=True, value=OTHER_NODE, comment=OTHER_COMMENT),
    )
    graph = advisor_graph.build_graph(model)

    first = advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )
    second = advisor_graph.propose(
        product_name=OTHER_PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )

    second_prompt = _prompt_text(model.received[-1])
    # SPECIFIED: the second invocation carries nothing from the first —
    # neither the first product nor the recommendation made for it.
    assert PRODUCT_NAME not in second_prompt
    assert first.result not in second_prompt
    assert OTHER_NODE in second.result


def test_two_invocations_for_the_same_product_are_independent() -> None:
    """Requirement statement: "each invocation SHALL be independent of
    every other, **including two invocations for the same product**".

    Stated in the requirement rather than in its scenario, and it is the
    harder half: a graph carrying state keyed by product would pass the
    different-product scenario and fail here.
    """
    model = _SequencedStructuredChatModel(
        Supported(ok=True, value=NODE, comment=COMMENT),
        Supported(ok=True, value=NODE, comment=COMMENT),
    )
    graph = advisor_graph.build_graph(model)

    advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )
    advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )

    assert len(model.received) == 2
    first_prompt = _prompt_text(model.received[0])
    second_prompt = _prompt_text(model.received[-1])
    assert first_prompt == second_prompt, (
        "the second invocation's prompt differs though the inputs are "
        "identical, so state is leaking across invocations"
    )
