"""The advisor's verdict, under the structured `ok` discriminant
(`subcategory-advisor`).

Derived strictly from the delta spec of the change
`write-the-advisors-finding-to-the-product`:
`openspec/changes/write-the-advisors-finding-to-the-product/specs/subcategory-advisor/spec.md`

Covers, from the MODIFIED requirement *The advisor proposes satisfaction
only where it can support a node choice*, all twelve scenarios:

- A supported choice proposes satisfaction
- An unsupported choice proposes no satisfaction
- A refusal is recognised however it is worded
- The recommendation's wording does not establish the outcome
- A verdict contradicting its own prose withholds satisfaction
- A missing verdict is unsupported, not supported
- An unreadable verdict is unsupported, not supported
- A fail-safe reason names what was wrong
- An unrecognised verdict is not reported as an absent one
- A vetoed verdict names the contradiction
- A response that is not text still fails visibly
- An unsupported recommendation still says so in prose

Written fresh for this MODIFIED requirement, superseding
`test_subcategory_advisor_verdict.py` wholesale — every scenario that file
covered is re-derived here against the `ok`-discriminated schema. That
file is unedited and is recorded in `test-manifest.md` as a superseded-test
candidate.

## A scenario whose *meaning* changed, not only its mechanism

*An unrecognised verdict is not reported as an absent one* carries the
same title as before this change, but the opposite content. Pre-change,
"a verdict reported with an unrecognised value" and "no verdict reported"
were two distinguishable technical states, and the served spec required
their reasons stay **distinct**. Structured output collapses that
distinction: the schema is a closed two-variant union, so there is no
third "recognised-but-wrong" value left to report — a response either
validates as `Supported`/`Unsupported`, or it does not validate at all.
The delta's own words say so directly: "structured output no longer
distinguishes 'nothing reported' from 'something unreadable reported' as
two separate technical states." `test_an_unrecognised_verdict_reads_the_same_as_a_missing_one`
below asserts the **new**, opposite direction — do not copy the old
file's distinctness assertion here, which would now assert the wrong
thing.

## Level

`propose()` observes eleven of the twelve scenarios; *A response that is
not text still fails visibly* needs the real compiled graph, since a
transport/content fault is a property of the model call itself, not of a
value `propose()` could be handed directly.

## What is fixed, and what is INVENTED

Fixed by `design.md` Decision 2 and `tasks.md` 5.4-5.6: `Supported`/
`Unsupported` distinguished by `ok`; `_advisor_refuses` narrowed to scan
only `comment`; the three unsupported routes in the stated order (schema
validation failed entirely; `Supported` with an empty comment; `Supported`
with a non-empty comment `_advisor_refuses` vetoes); routes 1-2 sharing
one reason, route 3 carrying a distinct one naming the contradiction.

INVENTED: `_ScriptedStructuredChatModel` / `_ScriptedStructuredRunnable`,
duplicated from `test_subcategory_advisor_structured_recommendation.py`
per this pass's own additive-only, separate-file convention. The exact
wording `_advisor_refuses` is expected to catch is not fixed by any
artifact; `REFUSAL_IN_COMMENT` below is a DERIVED fixture chosen to be
realistic prose rather than a keyword the mechanism itself might key on,
so passing against it is evidence about the requirement rather than about
a matcher's word list.

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
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Satisfied,
)
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

# DERIVED: a comment describing the *rejected alternative* as unsupportable
# — a statement about that alternative, not about the advisor's own
# ability to choose. The boundary case the veto must not fire on.
ALTERNATIVE_CALLED_UNSUPPORTABLE: Final = (
    "Demands: FDA food-contact material declaration. Rejected alternative: "
    "Home & Kitchen > Home Decor > Decorative Trays. That node cannot "
    "support a food-contact claim at all, which is why it was rejected here."
)

# DERIVED: realistic prose stating the advisor's *own* inability, despite
# `ok=True` — chosen to avoid a bare keyword a naive matcher would key on,
# so a pass here is evidence about the requirement, not about a word list.
REFUSAL_IN_COMMENT: Final = (
    "On reflection I would need more specific details about this item; "
    "without them I cannot confidently assign a sub-category node here."
)

REFUSAL_ERROR_A: Final = "the category tree gave no confident answer for this product"
REFUSAL_ERROR_B: Final = (
    "insufficient signal to place this listing in a single browse node"
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model whose `with_structured_output(...)` is scripted directly
# ---------------------------------------------------------------------------


class _ScriptedStructuredRunnable:
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
        self.received.append(input_)
        return self._answer()

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
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
        raise AssertionError("the advisor bound tools to its model")

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        runnable = _ScriptedStructuredRunnable(self.outcome)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-structured-fake-chat-model"


# ---------------------------------------------------------------------------
# `propose()` and reading a proposal
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


def _reason_of(proposal: Any) -> str:
    outcome = _outcome_of(proposal)
    reason = getattr(outcome, "reason", None)
    if isinstance(reason, str) and reason.strip():
        return reason
    pytest.fail(f"the advisor's proposed outcome carries no reason: {outcome!r}")


_ABSENT: Final = object()


def _finding_of(proposal: Any) -> Any:
    return getattr(proposal, "finding", _ABSENT)


def _propose(outcome: Any) -> Any:
    model = _ScriptedStructuredChatModel(outcome)
    graph = advisor_graph.build_graph(model)
    return advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )


def _assert_withheld(proposal: Any) -> Any:
    """A non-terminal outcome, and not a satisfying one.

    DERIVED, narrower than the scenarios' own words (which say
    "non-terminal"): `Blocked` specifically, the only non-terminal outcome
    that can carry a reason, and every withheld scenario here requires one.
    Asserted directly against `Blocked` rather than by excluding the other
    outcome types individually — `Satisfied`/`Refused`/`NotStarted`/
    `InProgress` are singleton values, not types, so excluding them by
    `isinstance` is not meaningful; a positive `isinstance(outcome, Blocked)`
    check already implies none of them.
    """
    outcome = _outcome_of(proposal)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome


# ---------------------------------------------------------------------------
# Scenario: A supported choice proposes satisfaction
# ---------------------------------------------------------------------------


def test_a_supported_choice_proposes_satisfaction() -> None:
    proposal = _propose(AdvisorResponse(ok=True, value=NODE, comment=COMMENT))

    assert _outcome_of(proposal) is Satisfied
    finding = _finding_of(proposal)
    assert isinstance(finding, Success)
    assert finding.value == NODE


# ---------------------------------------------------------------------------
# Scenario: An unsupported choice proposes no satisfaction
# ---------------------------------------------------------------------------


def test_an_unsupported_choice_proposes_no_satisfaction() -> None:
    proposal = _propose(AdvisorResponse(ok=False, error=REFUSAL_ERROR_A))

    outcome = _assert_withheld(proposal)
    reason = outcome.reason.lower()
    assert "support" in reason or "cannot" in reason or "no confident" in reason
    assert _finding_of(proposal) is None


# ---------------------------------------------------------------------------
# Scenario: A refusal is recognised however it is worded
# ---------------------------------------------------------------------------


def test_a_refusal_is_recognised_however_it_is_worded() -> None:
    """WHEN the advisor reports two unsupported responses whose error text
    shares no wording THEN both propose a non-terminal outcome, since
    support is read from the `ok` discriminant and never searched for in
    text.
    """
    a = _propose(AdvisorResponse(ok=False, error=REFUSAL_ERROR_A))
    b = _propose(AdvisorResponse(ok=False, error=REFUSAL_ERROR_B))

    _assert_withheld(a)
    _assert_withheld(b)


# ---------------------------------------------------------------------------
# Scenario: The recommendation's wording does not establish the outcome
# ---------------------------------------------------------------------------


def test_the_recommendations_wording_does_not_establish_the_outcome() -> None:
    proposal = _propose(
        AdvisorResponse(ok=True, value=NODE, comment=ALTERNATIVE_CALLED_UNSUPPORTABLE)
    )

    assert _outcome_of(proposal) is Satisfied, (
        "a rejected alternative described as unsupportable was read as the "
        "advisor refusing"
    )
    assert isinstance(_finding_of(proposal), Success)


# ---------------------------------------------------------------------------
# Scenario: A verdict contradicting its own prose withholds satisfaction
# ---------------------------------------------------------------------------


def test_a_verdict_contradicting_its_own_prose_withholds_satisfaction() -> None:
    proposal = _propose(
        AdvisorResponse(ok=True, value=NODE, comment=REFUSAL_IN_COMMENT)
    )

    _assert_withheld(proposal)
    assert _finding_of(proposal) is None


# ---------------------------------------------------------------------------
# Scenarios: schema validation failure — a missing / unreadable verdict
# ---------------------------------------------------------------------------


def test_a_missing_verdict_is_unsupported_not_supported() -> None:
    """WHEN the advisor's structured call completes but produces content
    satisfying neither the supported nor the unsupported variant THEN it
    proposes a non-terminal outcome.
    """
    proposal = _propose(None)

    _assert_withheld(proposal)
    assert _finding_of(proposal) is None


def test_an_unreadable_verdict_is_unsupported_not_supported() -> None:
    """WHEN the advisor's structured call completes and the response
    fails schema validation against both variants THEN it proposes a
    non-terminal outcome, exactly as a missing verdict does — the same
    condition, stated twice by the delta itself.
    """
    proposal = _propose(None)

    outcome = _assert_withheld(proposal)
    missing = _assert_withheld(_propose(None))
    assert outcome.reason == missing.reason, (
        "the same schema-validation-failure condition, invoked twice, "
        "produced two different reasons"
    )


# ---------------------------------------------------------------------------
# Scenario: A fail-safe reason names what was wrong
# ---------------------------------------------------------------------------


def test_a_fail_safe_reason_names_what_was_wrong() -> None:
    proposal = _propose(None)
    reason = _reason_of(proposal).lower()

    assert "verdict" in reason, (
        f"the reason does not name the missing verdict: {reason!r}"
    )
    assert any(
        phrase in reason for phrase in ("no verdict", "could not be read", "unread")
    ), f"the reason does not say no verdict could be read: {reason!r}"
    assert "could not support" not in reason
    assert "cannot support" not in reason


# ---------------------------------------------------------------------------
# Scenario: An unrecognised verdict is not reported as an absent one
#
# NOTE the flipped meaning documented at the top of this file: this now
# asserts SAMENESS, not distinctness.
# ---------------------------------------------------------------------------


def test_an_unrecognised_verdict_reads_the_same_as_a_missing_one() -> None:
    """WHEN the advisor's structured call completes but the response fails
    schema validation THEN the reason names that the response could not be
    read as a verdict — the same single reason a missing verdict produces.
    """
    unrecognised = _reason_of(_propose(None))
    missing = _reason_of(_propose(None))

    assert unrecognised == missing, (
        "structured output should no longer distinguish 'nothing "
        "reported' from 'something unreadable reported' as two separate "
        f"reasons, but got {unrecognised!r} and {missing!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A vetoed verdict names the contradiction
# ---------------------------------------------------------------------------


def test_a_vetoed_verdict_names_the_contradiction() -> None:
    proposal = _propose(
        AdvisorResponse(ok=True, value=NODE, comment=REFUSAL_IN_COMMENT)
    )
    reason = _reason_of(proposal).lower()

    assert any(
        word in reason
        for word in ("contradict", "conflict", "disagree", "inconsistent")
    ), f"the reason does not name the contradiction: {reason!r}"
    assert "could not be read" not in reason and "no verdict" not in reason, (
        f"a self-contradicting verdict was recorded with the shortfall "
        f"reason instead of naming the contradiction: {reason!r}"
    )


def test_routes_1_2_and_3_carry_distinguishable_reasons() -> None:
    """`tasks.md` 5.5-5.6: routes 1-2 share one reason; route 3 is
    distinct, "since this *is* a finding, not a shortfall."
    """
    shortfall = _reason_of(_propose(None))
    empty_comment_shortfall = _reason_of(
        _propose(AdvisorResponse(ok=True, value=NODE, comment=""))
    )
    contradiction = _reason_of(
        _propose(AdvisorResponse(ok=True, value=NODE, comment=REFUSAL_IN_COMMENT))
    )

    assert shortfall == empty_comment_shortfall, (
        "route 1 (no verdict validated) and route 2 (empty comment) should "
        f"share one reason, but got {shortfall!r} and {empty_comment_shortfall!r}"
    )
    assert contradiction != shortfall, (
        "route 3 (a vetoed contradiction) should carry a reason distinct "
        f"from the shared shortfall reason, but both read {contradiction!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A response that is not text still fails visibly
# ---------------------------------------------------------------------------


def test_a_response_that_is_not_text_still_fails_visibly() -> None:
    """WHEN the model answers with content that is not plain text at all
    THEN the failure is surfaced as a model failure, and no outcome is
    proposed for the step.

    Distinct from schema-validation failure (routes 1-2 above): this is a
    transport/client-level fault, simulated here by the structured-output
    runnable raising rather than returning a `parsed`/`parsing_error` pair.
    """
    fault = RuntimeError("simulated non-text model response")
    graph = advisor_graph.build_graph(_ScriptedStructuredChatModel(fault))

    with pytest.raises(Exception) as failure:
        advisor_graph.propose(
            product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
        )

    assert not isinstance(failure.value, AssertionError), (
        "the graph shape, not the advisor, is what failed here"
    )


# ---------------------------------------------------------------------------
# Scenario: An unsupported recommendation still says so in prose
# ---------------------------------------------------------------------------


def test_an_unsupported_recommendation_still_says_so_in_prose() -> None:
    """WHEN the advisor cannot support a node choice THEN the rendered
    text states that it cannot support one, readable without reference to
    the structured discriminant.

    Under structured output the rendered text is now built by the
    advisor's *own* code from `Failure.error` (design.md Decision 5), not
    by instructing the model's prose — so this is asserted against
    `propose()`'s rendered `result`, unlike the pre-change prompt-level
    test it supersedes.
    """
    proposal = _propose(AdvisorResponse(ok=False, error=REFUSAL_ERROR_A))
    text = _text_of(proposal)

    # SPECIFIED: the error reaches the reader.
    assert REFUSAL_ERROR_A in text
    # DERIVED: some inability-stating language accompanies it — the exact
    # wording is not fixed by any artifact.
    lowered = text.lower()
    assert any(
        phrase in lowered
        for phrase in ("cannot", "could not", "unable", "no node", "not choose")
    ), f"the rendered text does not read as a refusal on its own: {text!r}"


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a proposed browse node is a real Amazon node, or the right
#   one. No deterministic test can establish it.
# ---------------------------------------------------------------------------
