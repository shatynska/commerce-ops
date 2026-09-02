"""The advisor's recommendation, as structured output
(`subcategory-advisor`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/subcategory-advisor/spec.md`

Covers, from the MODIFIED requirement *A recommendation is produced from
the product's name and marketplace*, all six scenarios:

- A recommendation names node, demands and alternative
- A recommendation is readable as it stands
- A supported comment cannot be empty
- A comment's content is never checked by code
- The marketplace reaching the model is the identifier
- A refusal names the marketplace as a reader would recognise it

Written fresh for this MODIFIED requirement, including the two scenarios
whose *wording* carries over from the served spec (the first two) —
because the *mechanism* underneath every one of them changed (structured
output, not prose), and this pass's own instructions say to cover a
MODIFIED requirement's scenarios "as revised, exactly as you would for
ADDED". `test_subcategory_advisor_graph.py` and
`test_subcategory_advisor_marketplace.py` are unedited and are recorded
in `test-manifest.md` as candidates for superseded-test confirmation,
since both drive the advisor with a plain-string-answering fake model that
the new `model.with_structured_output(...)` seam cannot parse.

See `test-manifest.md` at the change root for the full accounting.

## Level

`propose()` is the smallest unit that can observe the outcome/finding/
rendered-text scenarios; the two marketplace scenarios need the real
handler (`advise_sub_category`) over a product carrying a real
`MarketplaceId`, mirroring `test_subcategory_advisor_marketplace.py`'s own
reasoning for the same two scenarios pre-change.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 2 / `tasks.md` 5.1: the class names
`Supported`/`Unsupported` on `commerce_ops.step_handlers.listing.subcategory_advisor`,
each carrying `value`/`comment` or `error`/`comment` respectively, and the
node calling `model.with_structured_output(AdvisorResult, include_raw=True)`.

INVENTED, each recorded in `test-manifest.md`:

- `_ScriptedStructuredChatModel` scripts the `with_structured_output(...)`
  seam directly rather than `_generate`, since no artifact fixes *how* a
  chat model is expected to answer that call for a fake. It records
  whatever it is invoked with, so prompt-content assertions still work.
- That `propose()`'s call shape (`product_name=`, `marketplace=`,
  `graph=`) survives unchanged — `design.md`'s own stated reason for
  keeping the `build_graph(model)` seam.
- `advise_sub_category(context)` and the `_graph()` monkeypatch seam,
  carried over from `test_subcategory_advisor_marketplace.py` unchanged.

## Expected first-run state

The advisor's module does not exist in this shape yet (`tasks.md` 5.1-5.6),
so every test here is expected to fail on an absent target (`ImportError`).
Per `ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar, Final, cast

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.application import StepContext
from commerce_ops.launch.domain.launch_playbook import Blocked, Satisfied
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.result import Success
from commerce_ops.step_handlers.listing.subcategory_advisor import (
    AdvisorResponse,
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"

NODE: Final = (
    "Home & Kitchen > Kitchen & Dining > Kitchen Utensils & Gadgets > Cutting Boards"
)
COMMENT: Final = (
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product. Rejected alternative: Home & Kitchen > Home "
    "Decor > Decorative Trays — higher keyword volume, but it understates "
    "this product's compliance surface."
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model whose `with_structured_output(...)` is scripted directly
# ---------------------------------------------------------------------------


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, BaseMessage):
        return str(value.content)
    if isinstance(value, dict):
        return "\n".join(_flatten_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return "\n".join(_flatten_text(item) for item in value)
    return str(value)


class _ScriptedStructuredRunnable:
    """What `model.with_structured_output(AdvisorResult, include_raw=True)`
    returns — a runnable answering with the `raw`/`parsed`/`parsing_error`
    shape `include_raw=True` produces, scripted rather than derived from a
    real model call."""

    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        if self._outcome is None:
            return {
                "raw": AIMessage(content="not a recognisable verdict"),
                "parsed": None,
                "parsing_error": ValueError("could not validate against the schema"),
            }
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._outcome,
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # `tasks.md` 2.5 / `design.md` Decision 2's model-level guard.
        # Both entry points are real on a structured-output runnable, so a
        # `recommend` body reverted to `structured.invoke(...)` inside an
        # `async def` would work, pin the invoking loop for the whole
        # round-trip, and pass every assertion in this file about what the
        # advisor produces. It fails here instead, naming the mistake.
        raise AssertionError(
            "the advisor reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)` — "
            "the enclosing coroutine then never yields, and the invoking "
            "loop is pinned for the whole of the round-trip"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
    """A chat model whose structured-output seam is scripted directly.

    `_generate` raises rather than answering, so a node that bypasses
    `with_structured_output(...)` and reads the model's plain response
    fails loudly instead of silently passing against the old mechanism.
    `bind_tools` raises too, mirroring the existing no-tools guard.
    """

    outcome: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]

    def __init__(self, outcome: Any) -> None:
        super().__init__()
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "runnable", None)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError(
            "the advisor called the model directly instead of through "
            "`with_structured_output(...)` — this fake only answers that seam"
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "the advisor bound tools to its model; the spec requires no "
            "external, side-effecting tool invocation"
        )

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        object.__setattr__(self, "requested_schema", schema)
        object.__setattr__(self, "requested_include_raw", include_raw)
        runnable = _ScriptedStructuredRunnable(self.outcome)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-structured-fake-chat-model"

    @property
    def prompt(self) -> str:
        if self.runnable is None or not self.runnable.received:
            return ""
        return _flatten_text(self.runnable.received[-1])


# ---------------------------------------------------------------------------
# `propose()` — the level for the outcome/finding/rendered-text scenarios
# ---------------------------------------------------------------------------


def _outcome_of(proposal: Any) -> Any:
    for attribute in ("outcome", "proposed_outcome"):
        carried = getattr(proposal, attribute, None)
        if carried is not None:
            return carried
    pytest.fail(f"the advisor's proposal carries no outcome: {proposal!r}")


def _text_of(proposal: Any) -> str:
    for attribute in ("result", "recommendation", "text"):
        carried = getattr(proposal, attribute, None)
        if isinstance(carried, str):
            return carried
    pytest.fail(f"the advisor's proposal carries no produced text: {proposal!r}")


_ABSENT: Final = object()


def _finding_of(proposal: Any) -> Any:
    return getattr(proposal, "finding", _ABSENT)


async def _propose(outcome: Any, *, product_name: str = PRODUCT_NAME) -> Any:
    model = _ScriptedStructuredChatModel(outcome)
    graph = advisor_graph.build_graph(model)
    return await advisor_graph.propose(
        product_name=product_name, marketplace=MARKETPLACE, graph=graph
    ), model


# ---------------------------------------------------------------------------
# Scenario: A recommendation names node, demands and alternative
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_recommendation_names_node_demands_and_alternative() -> None:
    """Scenario: A recommendation names node, demands and alternative.

    WHEN the advisor is given a product name and a marketplace identifier
    it can support a node choice for
    THEN it returns a structured recommendation whose value is the
    proposed node as a full path, and whose comment states the compliance
    fields and certifications that node demands and a rejected alternative
    node with the reason it was rejected.

    Under a scripted model the *content* of the answer is whatever the
    script says; what this establishes is that the advisor still asks for
    all three parts, and that a supported response's rendered text carries
    the node and the comment whole.
    """
    proposal, model = await _propose(
        AdvisorResponse(ok=True, value=NODE, comment=COMMENT)
    )

    # SPECIFIED: both inputs reach the model.
    assert model.prompt, "the advisor invoked no model"
    assert PRODUCT_NAME in model.prompt
    assert MARKETPLACE in model.prompt
    lowered = model.prompt.lower()
    assert "path" in lowered or "full path" in lowered
    assert "complian" in lowered
    assert "certificat" in lowered
    assert "alternative" in lowered

    # SPECIFIED: the satisfying outcome, together with the recommendation —
    # a rendering of the value and the comment together.
    assert _outcome_of(proposal) is Satisfied
    text = _text_of(proposal)
    assert NODE in text
    for line in COMMENT.splitlines():
        assert line.strip() in text


# ---------------------------------------------------------------------------
# Scenario: A recommendation is readable as it stands
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_recommendation_is_readable_as_it_stands() -> None:
    """Scenario: A recommendation is readable as it stands.

    WHEN a recommendation is returned
    THEN the rendered text is readable by a person without further
    processing, since it is delivered to a person for a decision and
    stored as the evidence of what was decided.
    """
    proposal, _ = await _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    text = _text_of(proposal)
    assert isinstance(text, str)
    assert text.strip()
    # SPECIFIED: readable as it stands — the value and comment reach the
    # reader whole, not summarised or re-encoded.
    assert NODE in text
    for line in COMMENT.splitlines():
        assert line.strip() in text


# ---------------------------------------------------------------------------
# Scenario: A supported comment cannot be empty
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "comment", [pytest.param("", id="empty-string"), pytest.param(None, id="none")]
)
@pytest.mark.anyio
async def test_a_supported_comment_cannot_be_empty(comment: str | None) -> None:
    """Scenario: A supported comment cannot be empty.

    WHEN the advisor's structured response validates as supported but its
    comment is empty
    THEN the advisor proposes a non-terminal outcome instead, exactly as
    it would for an unreadable verdict — a supported result with no
    comment is not a valid recommendation for this step.
    """
    proposal, _ = await _propose(AdvisorResponse(ok=True, value=NODE, comment=comment))

    # SPECIFIED: a non-terminal outcome, not the satisfying one.
    outcome = _outcome_of(proposal)
    assert outcome is not Satisfied
    # DERIVED: `Blocked` specifically — the only non-terminal outcome that
    # can carry the reason every withheld path here must carry
    # (`tasks.md` 5.5-5.6 groups this with "no verdict could be read").
    assert isinstance(outcome, Blocked), f"expected Blocked, got {outcome!r}"
    # SPECIFIED: no finding — "there is nothing supported to record".
    assert _finding_of(proposal) is None


# ---------------------------------------------------------------------------
# Scenario: A comment's content is never checked by code
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_comments_content_is_never_checked_by_code() -> None:
    """Scenario: A comment's content is never checked by code.

    WHEN the advisor's structured response validates as supported with a
    non-empty comment
    THEN the advisor proposes the satisfying outcome whatever the
    comment's content is — including a comment that, in fact, omits the
    compliance demands or the rejected alternative the prompt asked for,
    since detecting that omission would require parsing prose content,
    which this capability does not do.
    """
    bare_comment = "ok, ship it"
    proposal, _ = await _propose(
        AdvisorResponse(ok=True, value=NODE, comment=bare_comment)
    )

    # SPECIFIED: the satisfying outcome, whatever the comment says.
    assert _outcome_of(proposal) is Satisfied
    finding = _finding_of(proposal)
    assert isinstance(finding, Success)
    assert finding.value == NODE
    text = _text_of(proposal)
    assert bare_comment in text


# ---------------------------------------------------------------------------
# Scenarios: the marketplace reaching the model, and the reason recorded
# ---------------------------------------------------------------------------


class _Product:
    """A catalog product as the pass resolves one: identity carried by the
    value objects `shared.domain.identity` defines, not by bare strings."""

    def __init__(self) -> None:
        self.id = ProductId("7f3a1c22-0000-4000-8000-000000000001")
        self.sku = Sku("BCB-001")
        self.marketplace_id = MarketplaceId(MARKETPLACE)
        self.asin: Asin | None = None
        self.name = PRODUCT_NAME


class _Context:
    def __init__(self, product: Any) -> None:
        self.step = None
        self.launch = None
        self.product = product
        self.as_of = datetime.now(UTC)


RENDERING_FRAGMENTS: Final = ("MarketplaceId", "value=", f"'{MARKETPLACE}'")
REASON_FRAGMENTS: Final = ("MarketplaceId", "value=")


async def _resolve(outcome: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    model = _ScriptedStructuredChatModel(outcome)
    graph = advisor_graph.build_graph(model)
    monkeypatch.setattr(advisor_graph, "_graph", lambda: graph)
    context = cast(StepContext, _Context(_Product()))
    resolution = await advisor_graph.advise_sub_category(context)
    return resolution, model.prompt


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
    _, prompt = await _resolve(
        AdvisorResponse(ok=True, value=NODE, comment=COMMENT), monkeypatch
    )

    assert prompt, "the model was never asked anything"
    assert MARKETPLACE in prompt
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
    """
    resolution, _ = await _resolve(
        AdvisorResponse(ok=False, error="the category tree gave no confident answer"),
        monkeypatch,
    )
    reason = _reason_of(resolution.outcome)

    assert MARKETPLACE in reason, (
        f"the recorded reason names no marketplace identifier: {reason!r}"
    )
    for fragment in REASON_FRAGMENTS:
        assert fragment not in reason, (
            f"the recorded reason carries {fragment!r} from the value "
            f"object's rendering: {reason!r}"
        )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a proposed browse node is a real Amazon node, or the right
#   one. No deterministic test can establish it, and the spec does not
#   claim it.
# ---------------------------------------------------------------------------
