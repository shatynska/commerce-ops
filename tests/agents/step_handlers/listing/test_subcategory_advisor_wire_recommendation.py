"""The advisor's recommendation, re-derived against the wire shape
(`subcategory-advisor`).

Derived strictly from the delta spec of the change
`fix-subcategory-advisor-structured-output`:
`openspec/changes/fix-subcategory-advisor-structured-output/specs/subcategory-advisor/spec.md`

Covers all six scenarios of the MODIFIED requirement *A recommendation is
produced from the product's name and marketplace*:

- A recommendation names node, demands and alternative
- A recommendation is readable as it stands
- A supported comment cannot be empty
- A comment's content is never checked by code
- The marketplace reaching the model is the identifier
- A refusal names the marketplace as a reader would recognise it

See `test-manifest.md` at the change root for the full accounting.

## Why these are re-derived when the requirement changed for terminology
## only

`proposal.md` records this requirement as MODIFIED "for terminology only"
— "validates as supported" becomes "established as supported", and no
behaviour changes. The scenarios are nevertheless re-derived here, because
the *mechanism* every one of them runs through does change: each is
observed by scripting the model's parsed response, and that response is
the object this change re-types. The served file covering these six
(`test_subcategory_advisor_structured_recommendation.py`) scripts domain
variants and is recorded in `test-manifest.md` as a superseded candidate;
it is left unedited.

The re-derived assertions are deliberately identical in substance to that
file's, so an implementation satisfying one satisfies the other. What
differs is the input: a wire instance built from the schema the call site
actually passes.

## What is INVENTED

The fakes, `_Product`/`_Context`, the `_graph()` monkeypatch seam and the
`RENDERING_FRAGMENTS`/`REASON_FRAGMENTS` lists are carried over unchanged
from `test_subcategory_advisor_structured_recommendation.py`. Obtaining
the wire schema from the call site rather than by name is this pass's
own — no artifact fixes the wire model's name. All recorded in
`test-manifest.md`.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1824 passed, 44 skipped, 0
failed.
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
REFUSAL_ERROR: Final = "the category tree gave no confident answer for this product"

RENDERING_FRAGMENTS: Final = ("MarketplaceId", "value=", f"'{MARKETPLACE}'")
REASON_FRAGMENTS: Final = ("MarketplaceId", "value=")


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


class _ScriptedWireRunnable:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
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


class _ScriptedWireChatModel(BaseChatModel):
    outcome: ClassVar[Any] = None
    schemas: ClassVar[list[Any]]
    runnable: ClassVar[_ScriptedWireRunnable | None]

    def __init__(self, outcome: Any = None) -> None:
        super().__init__()
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "schemas", [])
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
        self.schemas.append(schema)
        runnable = _ScriptedWireRunnable(self.outcome)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-wire-fake-chat-model"

    @property
    def prompt(self) -> str:
        if self.runnable is None or not self.runnable.received:
            return ""
        return _flatten_text(self.runnable.received[-1])


# ---------------------------------------------------------------------------
# The wire schema, obtained from the call site rather than by name
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def wire_schema() -> Any:
    model = _ScriptedWireChatModel(None)
    graph = advisor_graph.build_graph(model)
    if not model.schemas:
        try:
            await advisor_graph.propose(
                product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
            )
        except AssertionError:
            # Never swallowed. An `AssertionError` out of `propose()` here
            # came from this file's own fakes, so it reports that the
            # advisor reached the model by a path this file forbids. The
            # schema is recorded before the model is called, so the
            # `schemas`-empty condition below never held for one of these
            # and swallowed every guard.
            raise
        except Exception as failure:
            if not model.schemas:
                raise AssertionError(
                    "the advisor never reached its structured-output call "
                    f"site, so no wire schema could be captured: {failure!r}"
                ) from failure
    assert model.schemas, "the advisor never called `with_structured_output(...)`"
    return model.schemas[0]


def _wire(
    schema: Any, *, ok: bool, value: str | None, error: str | None, comment: str | None
) -> Any:
    try:
        return schema(ok=ok, value=value, error=error, comment=comment)
    except Exception as failure:  # noqa: BLE001 - reported as a spec failure
        pytest.fail(
            "the wire schema cannot express "
            f"ok={ok!r} value={value!r} error={error!r} comment={comment!r}: "
            f"{failure!r}"
        )


async def _propose(
    schema: Any,
    *,
    ok: bool,
    value: str | None,
    error: str | None,
    comment: str | None = COMMENT,
) -> tuple[Any, _ScriptedWireChatModel]:
    model = _ScriptedWireChatModel(
        _wire(schema, ok=ok, value=value, error=error, comment=comment)
    )
    graph = advisor_graph.build_graph(model)
    proposal = await advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )
    return proposal, model


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


# ---------------------------------------------------------------------------
# Scenario: A recommendation names node, demands and alternative
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_recommendation_names_node_demands_and_alternative(
    wire_schema: Any,
) -> None:
    """WHEN the advisor is given a product name and a marketplace
    identifier it can support a node choice for THEN it returns a
    structured recommendation whose value is the proposed node as a full
    path, and whose comment states the compliance fields and
    certifications that node demands and a rejected alternative node with
    the reason it was rejected.

    Under a scripted model the *content* of the answer is whatever the
    script says; what this establishes is that the advisor still asks for
    all three parts, and that a supported response's rendered text carries
    the node and the comment whole.
    """
    proposal, model = await _propose(wire_schema, ok=True, value=NODE, error=None)

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
async def test_a_recommendation_is_readable_as_it_stands(wire_schema: Any) -> None:
    """WHEN a recommendation is returned THEN the rendered text is
    readable by a person without further processing.
    """
    proposal, _ = await _propose(wire_schema, ok=True, value=NODE, error=None)

    text = _text_of(proposal)
    assert isinstance(text, str)
    assert text.strip()
    # SPECIFIED: the value and comment reach the reader whole, not
    # summarised or re-encoded.
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
async def test_a_supported_comment_cannot_be_empty(
    wire_schema: Any, comment: str | None
) -> None:
    """WHEN the advisor's structured response is established as supported
    but its comment is empty THEN the advisor proposes a non-terminal
    outcome instead, exactly as it would for an unreadable verdict.

    "Established as supported" is the revised phrasing, and it is what
    this case pins: `ok: true`, a non-blank value and a **blank error**
    together. With a non-blank error the response would never be
    established as supported at all, and would take the contradiction
    route — a different scenario, covered in
    `test_subcategory_advisor_wire_conversion.py`.
    """
    proposal, _ = await _propose(
        wire_schema, ok=True, value=NODE, error=None, comment=comment
    )

    outcome = _outcome_of(proposal)
    assert outcome is not Satisfied
    # DERIVED: `Blocked` specifically — the only non-terminal outcome that
    # can carry the reason this route must record.
    assert isinstance(outcome, Blocked), f"expected Blocked, got {outcome!r}"
    # SPECIFIED: no finding — "there is nothing supported to record".
    assert _finding_of(proposal) is None


# ---------------------------------------------------------------------------
# Scenario: A comment's content is never checked by code
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_comments_content_is_never_checked_by_code(wire_schema: Any) -> None:
    """WHEN the advisor's structured response is established as supported
    with a non-empty comment THEN the advisor proposes the satisfying
    outcome whatever the comment's content is — including a comment that
    omits the compliance demands or the rejected alternative the prompt
    asked for.
    """
    bare_comment = "ok, ship it"
    proposal, _ = await _propose(
        wire_schema, ok=True, value=NODE, error=None, comment=bare_comment
    )

    assert _outcome_of(proposal) is Satisfied
    finding = _finding_of(proposal)
    assert isinstance(finding, Success)
    assert finding.value == NODE
    assert bare_comment in _text_of(proposal)


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


async def _resolve(outcome: Any, monkeypatch: pytest.MonkeyPatch) -> tuple[Any, str]:
    model = _ScriptedWireChatModel(outcome)
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
    wire_schema: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN the advisor resolves a step for a product whose marketplace is
    carried as a value object THEN the marketplace the model is asked
    about is that object's identifier, and carries nothing else of the
    object's rendering.
    """
    _, prompt = await _resolve(
        _wire(wire_schema, ok=True, value=NODE, error=None, comment=COMMENT),
        monkeypatch,
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
    wire_schema: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHEN the advisor cannot support a node choice and states the
    marketplace in its reason THEN that reason names the identifier, not a
    rendering of the object carrying it.
    """
    resolution, _ = await _resolve(
        _wire(wire_schema, ok=False, value=None, error=REFUSAL_ERROR, comment=None),
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
# - Whether the finding also carries the comment. The served requirement
#   makes that a MAY, so pinning it would invent a constraint.
# ---------------------------------------------------------------------------
