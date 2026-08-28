"""What marketplace the advisor is actually given
(`subcategory-advisor`).

Derived strictly from the delta spec
`openspec/changes/feed-the-advisor-a-marketplace/specs/subcategory-advisor/spec.md`
— the two scenarios that requirement adds:

- *The marketplace reaching the model is the identifier*
- *A refusal names the marketplace as a reader would recognise it*

The two reproduced scenarios (*A recommendation names node, demands and
alternative*, *A recommendation is readable as it stands*) are covered by
`test_subcategory_advisor_graph.py` and excluded here, per `tasks.md` 1.1.

**Why this file exists at all.** Every fixture in the neighbouring files
supplies the marketplace as a bare string, and with a bare string the
broken and the fixed reads produce identical prompts — so no existing
test could distinguish them, and the defect lived in production with a
green suite. These tests run the handler over a product whose marketplace
is a real `MarketplaceId`, which is what the pass supplies.

Baseline before the fix: both tests fail, naming the repr the prompt and
the reason carried.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar, Final, cast

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor
from commerce_ops.launch.application import StepContext
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku

MARKETPLACE_VALUE: Final = "ATVPDKIKX0DER"
PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


#: Everything the value object's rendering carries beyond the identifier:
#: its type name, its field name, and the quoting the repr puts around the
#: value. The delta names all three, and asserting only the first would
#: pass a prompt reading `value='ATVPDKIKX0DER'`.
RENDERING_FRAGMENTS: Final = ("MarketplaceId", "value=", "'ATVPDKIKX0DER'")

#: The reason interpolates its own values inside single quotes -- `on
#: '{marketplace}'` -- so quoting there is the reason's, not the object's,
#: and asserting its absence would fail a correctly-rendered reason. The
#: object's quoting never appears without `value=` in front of it, so the
#: first two fragments are what discriminate.
REASON_FRAGMENTS: Final = ("MarketplaceId", "value=")

_SUPPORTED: Final = (
    "Verdict: supported\n"
    "\n"
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative Trays."
)

_REFUSAL: Final = (
    "Verdict: unsupported\n"
    "\n"
    "To give an accurate reply I would need specific details about this "
    "item; without them I cannot confidently assign a sub-category node."
)


class _CapturingChatModel(BaseChatModel):
    """Answers a fixed script and keeps every prompt it was sent."""

    answer: str = ""
    # `ClassVar` so pydantic leaves it alone and ruff does not read it as a
    # shared mutable default; each instance rebinds it in `__init__`.
    asked: ClassVar[list[str]]

    def __init__(self, answer: str) -> None:
        super().__init__()
        object.__setattr__(self, "answer", answer)
        object.__setattr__(self, "asked", [])

    @property
    def _llm_type(self) -> str:
        return "capturing"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        for message in messages:
            self.asked.append(str(message.content))
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.answer))]
        )


class _Product:
    """A catalog product as the pass resolves one: identity carried by the
    value objects `shared.domain.identity` defines, not by bare strings."""

    def __init__(self) -> None:
        self.id = ProductId("7f3a1c22-0000-4000-8000-000000000001")
        self.sku = Sku("BCB-001")
        self.marketplace_id = MarketplaceId(MARKETPLACE_VALUE)
        self.asin: Asin | None = None
        self.name = PRODUCT_NAME


class _Context:
    """`StepContext` is frozen and typed; the handler reads only
    `product`, so a stand-in carrying that is what the scenarios need."""

    def __init__(self, product: Any) -> None:
        self.step = None
        self.launch = None
        self.product = product
        self.as_of = datetime.now(UTC)


async def _resolve(
    answer: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, list[str]]:
    """Run the handler over a product carrying a real `MarketplaceId`."""
    model = _CapturingChatModel(answer)
    graph = advisor.build_graph(model)
    monkeypatch.setattr(advisor, "_graph", lambda: graph)
    # Cast rather than built: `StepContext` also carries a `StepDefinition`
    # and a `Launch`, and the handler reads neither — it reads `product`
    # and nothing else, which is the property `launch-step-automation`
    # states as "a function of the context it is given".
    context = cast(StepContext, _Context(_Product()))
    resolution = await advisor.advise_sub_category(context)
    return resolution, model.asked


def _reason_of(outcome: Any) -> str:
    reason = getattr(outcome, "reason", None)
    assert isinstance(reason, str) and reason, (
        f"the outcome carries no reason to read: {outcome!r}"
    )
    return reason


@pytest.mark.anyio
async def test_the_marketplace_reaching_the_model_is_the_identifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The marketplace reaching the model is the identifier.

    WHEN the advisor resolves a step for a product whose marketplace is
    carried as a value object
    THEN the marketplace the model is asked about is that object's
    identifier, and carries nothing else of the object's rendering —
    neither its type name, nor its field name, nor the quoting around its
    value.
    """
    _, asked = await _resolve(_SUPPORTED, monkeypatch)

    assert asked, "the model was never asked anything"
    prompt = asked[0]

    # SPECIFIED: the identifier reaches the model.
    assert MARKETPLACE_VALUE in prompt, (
        f"the prompt names no marketplace identifier: {prompt!r}"
    )
    # SPECIFIED: and nothing else of the object's rendering. All three
    # fragments, because naming only the type would pass a prompt reading
    # `value='ATVPDKIKX0DER'`.
    for fragment in RENDERING_FRAGMENTS:
        assert fragment not in prompt, (
            f"the prompt carries {fragment!r} from the value object's "
            f"rendering rather than its identifier alone: {prompt!r}"
        )


@pytest.mark.anyio
async def test_a_refusal_names_the_marketplace_as_a_reader_would_recognise_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A refusal names the marketplace as a reader would
    recognise it.

    WHEN the advisor cannot support a node choice and states the
    marketplace in its reason
    THEN that reason names the identifier, not a rendering of the object
    carrying it.

    This is the side an operator reads: the reason is what
    `launch-step-automation` records against the launch when a
    non-terminal outcome is proposed, and it is where the defect was
    first seen.
    """
    resolution, _ = await _resolve(_REFUSAL, monkeypatch)
    reason = _reason_of(resolution.outcome)

    # SPECIFIED: the reason names the identifier.
    assert MARKETPLACE_VALUE in reason, (
        f"the recorded reason names no marketplace identifier: {reason!r}"
    )
    # SPECIFIED: not a rendering of the object carrying it.
    for fragment in REASON_FRAGMENTS:
        assert fragment not in reason, (
            f"the recorded reason carries {fragment!r} from the value "
            f"object's rendering: {reason!r}"
        )
