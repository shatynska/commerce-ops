"""The advisor's verdict, re-derived against the wire shape
(`subcategory-advisor`).

Derived strictly from the delta spec of the change
`fix-subcategory-advisor-structured-output`:
`openspec/changes/fix-subcategory-advisor-structured-output/specs/subcategory-advisor/spec.md`

Covers the remaining nine scenarios of the MODIFIED requirement *The
advisor proposes satisfaction only where it can support a node choice*:

- A refusal is recognised however it is worded
- The recommendation's wording does not establish the outcome
- A verdict contradicting its own prose withholds satisfaction
- A missing verdict is unsupported, not supported
- An unreadable verdict is unsupported, not supported
- A fail-safe reason names what was wrong
- An unrecognised verdict is not reported as an absent one
- A vetoed verdict names the contradiction
- A response that is not text still fails visibly

The requirement's other six scenarios are in
`test_subcategory_advisor_wire_conversion.py`, which also covers the
change's ADDED requirement. See `test-manifest.md` at the change root.

## Why these are re-derived rather than left to the served suite

The requirement is MODIFIED, so its scenarios are written afresh against
the shape this change introduces — the same reasoning the previous pass
recorded when structured output first arrived. `test_subcategory_advisor_
structured_verdict.py` covers the same nine scenarios today, but it drives
them with domain `Supported`/`Unsupported` objects scripted as the model's
parsed response, which is exactly the object this change re-types; those
tests are recorded in `test-manifest.md` as superseded candidates and are
left unedited here.

## Scenarios that pass before the implementation lands

Four of these (*A missing verdict…*, *An unreadable verdict…*, *A
fail-safe reason…*, *An unrecognised verdict…*) drive a response that
parses against nothing at all, so they never construct a wire instance and
observe behaviour this change does not alter. They are expected to pass on
their first run. Per `ai-toolkit:testing` that is the fourth failure state
and is investigated rather than recorded as new coverage: the behaviour
they assert already exists, which is what "no behaviour changes on this
route" means for a MODIFIED requirement. What they add is a guard that the
change does not disturb it. Each is marked below.

## What is INVENTED

The fakes, the reason word lists, and `REFUSAL_IN_COMMENT` /
`ALTERNATIVE_CALLED_UNSUPPORTABLE` are carried over unchanged from
`test_subcategory_advisor_structured_verdict.py`, so an implementation
satisfying that file satisfies this one; obtaining the wire schema from
the call site rather than by name is this pass's own, since no artifact
fixes the wire model's name. All recorded in `test-manifest.md`.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1824 passed, 44 skipped, 0
failed.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import Blocked, Satisfied
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

# DERIVED, carried over from `test_subcategory_advisor_structured_verdict.py`:
# a comment describing the *rejected alternative* as unsupportable — a
# statement about that alternative, not about the advisor's own ability to
# choose. The boundary case the veto must not fire on.
ALTERNATIVE_CALLED_UNSUPPORTABLE: Final = (
    "Demands: FDA food-contact material declaration. Rejected alternative: "
    "Home & Kitchen > Home Decor > Decorative Trays. That node cannot "
    "support a food-contact claim at all, which is why it was rejected here."
)

# DERIVED, carried over: realistic prose stating the advisor's *own*
# inability despite `ok: true`, chosen to avoid a bare keyword a naive
# matcher would key on.
REFUSAL_IN_COMMENT: Final = (
    "On reflection I would need more specific details about this item; "
    "without them I cannot confidently assign a sub-category node here."
)

REFUSAL_ERROR_A: Final = "the category tree gave no confident answer for this product"
REFUSAL_ERROR_B: Final = (
    "insufficient signal to place this listing in a single browse node"
)

CONTRADICTION_WORDS: Final = ("contradict", "conflict", "disagree", "inconsistent")
SHORTFALL_PHRASES: Final = ("no verdict", "could not be read", "unread")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model whose `with_structured_output(...)` is scripted directly
# ---------------------------------------------------------------------------


class _ScriptedWireRunnable:
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
        raise AssertionError("the advisor bound tools to its model")

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


# ---------------------------------------------------------------------------
# The wire schema, obtained from the call site rather than by name
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wire_schema() -> Any:
    model = _ScriptedWireChatModel(None)
    graph = advisor_graph.build_graph(model)
    if not model.schemas:
        try:
            advisor_graph.propose(
                product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
            )
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


def _propose_response(outcome: Any) -> Any:
    """`propose()` over a scripted response, wire or otherwise."""
    model = _ScriptedWireChatModel(outcome)
    graph = advisor_graph.build_graph(model)
    return advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )


def _propose(
    schema: Any,
    *,
    ok: bool,
    value: str | None,
    error: str | None,
    comment: str | None = COMMENT,
) -> Any:
    return _propose_response(
        _wire(schema, ok=ok, value=value, error=error, comment=comment)
    )


# ---------------------------------------------------------------------------
# Reading a proposal — carried over from this directory's existing files
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


def _assert_withheld(proposal: Any) -> Any:
    outcome = _outcome_of(proposal)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome


def _reason_of(proposal: Any) -> str:
    outcome = _assert_withheld(proposal)
    reason = getattr(outcome, "reason", None)
    if isinstance(reason, str) and reason.strip():
        return reason
    pytest.fail(f"the advisor's proposed outcome carries no reason: {outcome!r}")


# ---------------------------------------------------------------------------
# Scenario: A refusal is recognised however it is worded
# ---------------------------------------------------------------------------


def test_a_refusal_is_recognised_however_it_is_worded(wire_schema: Any) -> None:
    """WHEN the advisor reports two unsupported responses whose error text
    shares no wording THEN both propose a non-terminal outcome, since
    support is read from the discriminant together with its variant's
    field, and never searched for in text.

    The revised wording is what is asserted: the discriminant *together
    with its field*. Both responses carry `ok: false` and an error, and
    their error texts share no words.
    """
    a = _propose(wire_schema, ok=False, value=None, error=REFUSAL_ERROR_A)
    b = _propose(wire_schema, ok=False, value=None, error=REFUSAL_ERROR_B)

    _assert_withheld(a)
    _assert_withheld(b)
    assert _finding_of(a) is None
    assert _finding_of(b) is None


# ---------------------------------------------------------------------------
# Scenario: The recommendation's wording does not establish the outcome
# ---------------------------------------------------------------------------


def test_the_recommendations_wording_does_not_establish_the_outcome(
    wire_schema: Any,
) -> None:
    """WHEN the advisor's structured response is established as supported
    THEN it proposes the satisfying outcome whatever its value or its
    comment's compliance-demands and rejected-alternative content say —
    including a rejected alternative described as unsupportable.

    "Established as supported" is the revised phrasing: `ok: true`, a
    non-blank value, and a blank error together.
    """
    proposal = _propose(
        wire_schema,
        ok=True,
        value=NODE,
        error=None,
        comment=ALTERNATIVE_CALLED_UNSUPPORTABLE,
    )

    assert _outcome_of(proposal) is Satisfied, (
        "a rejected alternative described as unsupportable was read as the "
        "advisor refusing"
    )
    assert isinstance(_finding_of(proposal), Success)


# ---------------------------------------------------------------------------
# Scenario: A verdict contradicting its own prose withholds satisfaction
# ---------------------------------------------------------------------------


def test_a_verdict_contradicting_its_own_prose_withholds_satisfaction(
    wire_schema: Any,
) -> None:
    """WHEN the advisor's structured response is established as supported
    but its comment states that it cannot assign a node choice for this
    product and marketplace THEN it proposes a non-terminal outcome and
    does not propose a satisfying outcome.

    The error is pinned blank, so this is the comment veto and not the
    error-based contradiction direction — the two are disjoint here.
    """
    proposal = _propose(
        wire_schema, ok=True, value=NODE, error=None, comment=REFUSAL_IN_COMMENT
    )

    _assert_withheld(proposal)
    assert _finding_of(proposal) is None


# ---------------------------------------------------------------------------
# Scenario: A vetoed verdict names the contradiction
# ---------------------------------------------------------------------------


def test_a_vetoed_verdict_names_the_contradiction(wire_schema: Any) -> None:
    """WHEN the advisor proposes a non-terminal outcome because a
    supporting response's own error or comment contradicted it THEN the
    reason names that contradiction, and does not assert that the advisor
    considered and declined a classification.

    The revised scenario names **both** contradiction sources, so both are
    driven here. The reason each names is asserted per `tasks.md` 2.6: the
    field that actually withheld support, not `_contradiction_reason`'s
    served wording reused verbatim.
    """
    by_comment = _reason_of(
        _propose(
            wire_schema, ok=True, value=NODE, error=None, comment=REFUSAL_IN_COMMENT
        )
    )
    by_error = _reason_of(
        _propose(
            wire_schema,
            ok=True,
            value=NODE,
            error=REFUSAL_ERROR_A,
            comment=COMMENT,
        )
    )

    for reason in (by_comment, by_error):
        lowered = reason.lower()
        assert any(word in lowered for word in CONTRADICTION_WORDS), (
            f"the reason does not name the contradiction: {reason!r}"
        )
        assert not any(phrase in lowered for phrase in SHORTFALL_PHRASES), (
            "a self-contradicting response was recorded with the shortfall "
            f"reason instead of naming the contradiction: {reason!r}"
        )

    # SPECIFIED (`tasks.md` 2.6): each names the field that actually
    # withheld support — the served reason hardcodes "comment", which an
    # error-based contradiction may not even carry.
    assert "comment" in by_comment.lower()
    assert "error" in by_error.lower()
    assert "comment" not in by_error.lower(), (
        f"an error-based contradiction blames the comment: {by_error!r}"
    )


# ---------------------------------------------------------------------------
# Scenarios reached without a wire instance at all — the routes this
# change does not alter. Expected to pass on their first run; see the
# module docstring.
# ---------------------------------------------------------------------------


def test_a_missing_verdict_is_unsupported_not_supported() -> None:
    """WHEN the advisor's structured call completes but produces content
    the advisor's conversion maps to neither a supported nor an
    unsupported result THEN it proposes a non-terminal outcome and does
    not propose a satisfying outcome.
    """
    proposal = _propose_response(None)

    _assert_withheld(proposal)
    assert _finding_of(proposal) is None


def test_an_unreadable_verdict_is_unsupported_not_supported() -> None:
    """WHEN the advisor's structured call completes and the response fails
    validation against the wire schema entirely THEN it proposes a
    non-terminal outcome, exactly as a verdict that maps to neither result
    does.

    The delta states these as the same condition, so they are driven the
    same way and asserted to agree.
    """
    unreadable = _propose_response(None)
    maps_to_neither = _propose_response(None)

    _assert_withheld(unreadable)
    assert _reason_of(unreadable) == _reason_of(maps_to_neither)


def test_a_fail_safe_reason_names_what_was_wrong() -> None:
    """WHEN the advisor proposes a non-terminal outcome because no verdict
    could be read THEN the reason states that no verdict could be read,
    and does not assert that a node choice could not be supported for the
    product.
    """
    reason = _reason_of(_propose_response(None)).lower()

    assert "verdict" in reason, (
        f"the reason does not name the missing verdict: {reason!r}"
    )
    assert any(phrase in reason for phrase in SHORTFALL_PHRASES), (
        f"the reason does not say no verdict could be read: {reason!r}"
    )
    assert "could not support" not in reason
    assert "cannot support" not in reason


def test_an_unrecognised_verdict_reads_the_same_as_a_missing_one() -> None:
    """WHEN the advisor's structured call completes but the response fails
    validation against the wire schema THEN the reason names that the
    response could not be read as a verdict — the same single reason a
    verdict mapping to neither result produces.
    """
    unrecognised = _reason_of(_propose_response(None))
    missing = _reason_of(_propose_response(None))

    assert unrecognised == missing, (
        "structured output should no longer distinguish 'nothing reported' "
        "from 'something unreadable reported' as two separate reasons, but "
        f"got {unrecognised!r} and {missing!r}"
    )


def test_a_response_that_is_not_text_still_fails_visibly() -> None:
    """WHEN the model answers with content that is not plain text at all
    THEN the failure is surfaced as a model failure, and no outcome is
    proposed for the step.

    A transport/client-level fault, distinct from a response that fails to
    validate: simulated by the structured-output runnable raising rather
    than returning a `raw`/`parsed`/`parsing_error` triple.
    """
    fault = RuntimeError("simulated non-text model response")

    with pytest.raises(Exception) as failure:
        _propose_response(fault)

    assert not isinstance(failure.value, AssertionError), (
        "the graph shape, not the advisor, is what failed here"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a proposed browse node is a real Amazon node, or the right
#   one. No deterministic test can establish it.
# ---------------------------------------------------------------------------
