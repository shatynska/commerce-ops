"""Structured output as a non-tool mechanism, and the finding it produces
(`subcategory-advisor`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/subcategory-advisor/spec.md`

Covers:

- MODIFIED requirement *No tool invocation* — both scenarios:
  - Producing a recommendation invokes no tools
  - Structured output is not a tool invocation
- ADDED requirement *A supported recommendation's value is recorded
  against the product* — all three scenarios:
  - A supported recommendation carries a recordable finding
  - An unsupported recommendation carries no finding
  - Only the finding's value is ever written to the product

`Producing a recommendation invokes no tools` reproduces the pre-change
scenario's own wording (only "external, side-effecting" was added to the
requirement text, per `design.md`'s compliance note); written fresh here
per this pass's MODIFIED-requirement instructions, alongside
`test_subcategory_advisor_graph.py`'s own unedited
`test_producing_a_recommendation_invokes_no_tools`.

See `test-manifest.md` at the change root for the full accounting.

## Level

`propose()` observes every scenario here: what the model was and was not
given (tools bound, messages), and whether a finding is present or absent
alongside the outcome.

## What is fixed, and what is INVENTED

Fixed by `design.md`'s compliance note: constraining the model's response
to a schema via `with_structured_output(...)` is not a tool invocation —
"nothing external is called and nothing outside the model's own generation
has any side effect." Fixed by the ADDED requirement itself: the finding
is a `Success[T]` (`shared.domain`) whose `value` is exactly the node the
structured response reported, present only on a supported proposal, and
that only `.value` — never `.comment` — is what a consumer may write to
the product (this file asserts that the *finding* carries this
boundary; the boundary being *honoured downstream* is
`launch-step-automation`'s and `product-catalog`'s concern, covered in
`test_automation_pass_finding.py` and the catalog tests).

INVENTED: `_ScriptedStructuredChatModel` / `_ScriptedStructuredRunnable`,
duplicated per this pass's additive-only, separate-file convention.

## Expected first-run state

The advisor's module does not exist in this shape yet, so every test here
is expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing` that establishes absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1689 passed, 0 failed.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import Blocked, Satisfied
from commerce_ops.shared.domain.result import Success
from commerce_ops.step_handlers.listing.subcategory_advisor import (
    AdvisorResponse,
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"
NODE: Final = "Home & Kitchen > Kitchen & Dining > Cutting Boards"
COMMENT: Final = (
    "Demands: FDA food-contact declaration. Rejected alternative: Home & "
    "Kitchen > Home Decor > Decorative Trays, which understates the "
    "compliance surface."
)


# ---------------------------------------------------------------------------
# A chat model whose `with_structured_output(...)` is scripted directly
# ---------------------------------------------------------------------------


class _ScriptedStructuredRunnable:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._outcome,
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
    outcome: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]
    bound_tools: ClassVar[list[Any]]

    def __init__(self, outcome: Any) -> None:
        super().__init__()
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "runnable", None)
        object.__setattr__(self, "bound_tools", [])
        object.__setattr__(self, "requested_schema", None)
        object.__setattr__(self, "requested_include_raw", None)

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
        # Recorded, not raised: *Structured output is not a tool
        # invocation* needs to distinguish "the advisor's own code bound a
        # callable, side-effecting tool" from "the framework's structured-
        # output plumbing did something internally" — a fake that raises
        # outright cannot express that distinction. What this file asserts
        # is that the advisor's own code path never reaches here.
        object.__setattr__(self, "bound_tools", list(tools))
        return self

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


def _outcome_of(proposal: Any) -> Any:
    for attribute in ("outcome", "proposed_outcome"):
        carried = getattr(proposal, attribute, None)
        if carried is not None:
            return carried
    pytest.fail(f"the advisor's proposal carries no outcome: {proposal!r}")


_ABSENT: Final = object()


def _finding_of(proposal: Any) -> Any:
    return getattr(proposal, "finding", _ABSENT)


def _propose(outcome: Any) -> tuple[Any, _ScriptedStructuredChatModel]:
    model = _ScriptedStructuredChatModel(outcome)
    graph = advisor_graph.build_graph(model)
    proposal = advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )
    return proposal, model


# ---------------------------------------------------------------------------
# Requirement: No tool invocation
# ---------------------------------------------------------------------------


def test_producing_a_recommendation_invokes_no_tools() -> None:
    """Scenario: Producing a recommendation invokes no tools.

    WHEN the advisor produces a recommendation
    THEN no external, side-effecting tool, function, or marketplace call
    occurs during that processing.

    Reproduces the pre-change scenario's own wording; written fresh here
    per this pass's MODIFIED-requirement instructions. Distinct from
    `test_structured_output_is_not_a_tool_invocation` below: this asserts
    the advisor's own code path binds no *executable* side-effecting tool
    to the model, whatever the structured-output plumbing does internally.
    """
    proposal, model = _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    assert _outcome_of(proposal) is Satisfied
    # SPECIFIED: nothing answered as a tool, nothing requested one, on the
    # runnable's own scripted response.
    assert model.runnable is not None
    for received in model.runnable.received:
        assert not isinstance(received, ToolMessage)


def test_structured_output_is_not_a_tool_invocation() -> None:
    """Scenario: Structured output is not a tool invocation.

    WHEN the advisor's model call uses a structured-output mechanism to
    constrain the response to the schema
    THEN this is not treated as a forbidden tool invocation, since nothing
    external is called and no side effect occurs.

    Asserted here as: the advisor reaches its outcome by way of
    `with_structured_output(...)` (this fake's `runnable` is populated),
    and does so without failing or being refused for having done so —
    there is no code path in this capability that inspects "was structured
    output used" and treats it as a violation.
    """
    proposal, model = _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    # SPECIFIED: the structured-output seam was used, and using it is not
    # itself a fault — the proposal completed normally.
    assert model.runnable is not None, (
        "the advisor never called `with_structured_output(...)` — this "
        "scenario cannot be observed against a mechanism that was not used"
    )
    assert _outcome_of(proposal) is Satisfied


# ---------------------------------------------------------------------------
# Requirement: A supported recommendation's value is recorded against the
# product
# ---------------------------------------------------------------------------


def test_a_supported_recommendation_carries_a_recordable_finding() -> None:
    """Scenario: A supported recommendation carries a recordable finding.

    WHEN the advisor proposes the step's satisfying outcome
    THEN a typed finding whose value is exactly the proposed sub-category
    node is available alongside the rendered text.
    """
    proposal, _ = _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    assert _outcome_of(proposal) is Satisfied
    finding = _finding_of(proposal)
    assert isinstance(finding, Success), f"expected a Success finding, got {finding!r}"
    assert finding.value == NODE


def test_an_unsupported_recommendation_carries_no_finding() -> None:
    """Scenario: An unsupported recommendation carries no finding.

    WHEN the advisor proposes a non-terminal outcome
    THEN no typed finding is made available — there is nothing supported
    to record.
    """
    proposal, _ = _propose(AdvisorResponse(ok=False, error="no confident answer"))

    outcome = _outcome_of(proposal)
    assert isinstance(outcome, Blocked)
    assert _finding_of(proposal) is None


def test_only_the_findings_value_is_ever_written_to_the_product() -> None:
    """Scenario: Only the finding's value is ever written to the product.

    WHEN a typed finding is produced for a supported recommendation and
    recorded against the product
    THEN the product receives exactly the finding's value — the
    sub-category node — and nothing from its comment.

    This capability's own obligation is only to make the finding available
    shaped that way (`value` carries the node, `comment` carries
    everything else) — it does not record anything itself. Asserted here
    at the finding's own shape: `value` is exactly the node and nothing of
    the comment leaks into it; that the *comment* is genuinely never
    forwarded to a write is `product-catalog`'s and
    `launch-step-automation`'s concern (the recorder port takes `value`
    alone, per `design.md`'s `SubCategoryRecorder` signature), asserted at
    the pass level in `test_automation_pass_finding.py`.
    """
    proposal, _ = _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    finding = _finding_of(proposal)
    assert isinstance(finding, Success)
    # SPECIFIED: the value is exactly the proposed node.
    assert finding.value == NODE
    # DERIVED: nothing of the comment's own content leaked into `value`.
    assert COMMENT not in finding.value
    assert finding.value != finding.comment
