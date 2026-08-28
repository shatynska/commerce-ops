"""Deterministic agent-graph tests for the `subcategory-advisor` capability.

Derived strictly from the delta spec:
`openspec/changes/introduce-automation-runtime/specs/subcategory-advisor/spec.md`

Covers all five ADDED requirements and all eight of their scenarios:

- *A recommendation is produced from the product's name and marketplace*
  — *A recommendation names node, demands and alternative*, *A
  recommendation is readable as it stands*.
- *The advisor proposes satisfaction only where it can support a node
  choice* — *A supported choice proposes satisfaction*, *An unsupported
  choice proposes no satisfaction*.
- *No tool invocation* — *Producing a recommendation invokes no tools*.
- *No state across invocations* — *Two invocations do not share context*.
- *Model failure is surfaced, not masked* — *Language model call fails*,
  *Response content is not a plain string*.

See `test-manifest.md` at the change root for the full accounting.

## Level, and what a stubbed model can and cannot establish

`design.md` gives the advisor `omni_agent/application/graph.py`'s shape,
"including its split between `build_graph(model)` (injectable) and
`build_production_graph()`. That split is what lets `tests/agents/` drive
it with a stubbed model, which is the project's stated LangGraph testing
strategy." So every test here runs the compiled graph over a fake chat
model: no network call, no live model, no nondeterminism.

**What that cannot establish, stated plainly:** whether the model's
answer is a *correct* Amazon browse node. Nothing in a deterministic test
can, and the spec does not ask — it asks that the advisor demand a node
path, its compliance demands and a rejected alternative, and that it not
propose satisfaction where it has no answer. With the model stubbed, the
first of those is observable only in **what the advisor asks the model
for**, which is why the scenario-1 test reads the prompt the fake model
received rather than the text it returned. That is recorded in
`test-manifest.md` as the reading it is.

## What is fixed, and what is INVENTED

Fixed by `design.md` and `tasks.md` 7.1–7.3: the `build_graph(model)` /
`build_production_graph()` split; that the advisor is a single-node
`StateGraph` over a chat model; that no structured output or tool-calling
is used ("Not chosen: structured output / tool-calling for the
recommendation"); that a model failure and a non-string response content
are both surfaced as failures.

INVENTED, each recorded in `test-manifest.md` as an unresolved project
question with its correction point:

- The module path
  `commerce_ops.step_handlers.listing.subcategory_advisor`.
  `design.md` says "the agent graph in its own module following
  `omni_agent/application/graph.py`, with its own `.importlinter`
  contract" and names the capability `subcategory-advisor`; the Python
  package spelling is assumed from that pair.
- The graph's input and output shape. `_invoke` and `_recommendation_of`
  are the two correction points: they try the structured shape a
  product-name/marketplace graph would take and fall back to the
  `MessagesState` shape `omni_agent`'s graph uses, failing loudly if
  neither answers.
- The advisor's outcome-proposing entry point — the thing that turns a
  recommendation into an outcome plus text. `_propose` probes for it.
- `_UNSUPPORTED_ANSWER`: the model response standing for "I cannot
  support a node choice". The spec fixes that the advisor must recognise
  its own inability; how it recognises it — a sentinel token, a
  structured marker, a plain-language reading — is unstated. This is the
  one correction point most likely to need adjusting.

What must survive any correction is what each test asserts: what the
advisor asks for, what it returns unaltered, which outcome it proposes in
each case, that it binds no tools, that it carries nothing between
invocations, and that neither failure is masked.

## Expected first-run state

The advisor's module does not exist (`tasks.md` 7.1), so every test here
is expected to fail on an absent target (`ImportError`). Per
`ai-toolkit:testing`, that establishes absence only — the assertions have
not been exercised.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 901 passed, 0 failed.
"""

from __future__ import annotations

import inspect
from typing import Any, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ValidationError

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    InProgress,
    NotApplicable,
    NotStarted,
    Refused,
    Satisfied,
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
OTHER_PRODUCT_NAME: Final = "Stainless Steel Insulated Water Bottle, 750 ml"
MARKETPLACE: Final = "ATVPDKIKX0DER"

SUPPORTED_RECOMMENDATION: Final = (
    "Proposed node: Home & Kitchen > Kitchen & Dining > Kitchen Utensils "
    "& Gadgets > Cutting Boards.\n"
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product.\n"
    "Rejected alternative: Home & Kitchen > Home Decor > Decorative "
    "Trays — higher keyword volume, but it carries no food-contact "
    "obligation and would understate this product's compliance surface."
)

#: What the model actually answers: the verdict line the system reads,
#: then the recommendation the person reads. The advisor stores only the
#: second (design.md Decision 1b), so a test asserting the recommendation
#: "reaches the reader whole" compares against the recommendation, never
#: against this.
SUPPORTED_ANSWER: Final = "Verdict: supported\n\n" + SUPPORTED_RECOMMENDATION

OTHER_SUPPORTED_RECOMMENDATION: Final = (
    "Proposed node: Sports & Outdoors > Outdoor Recreation > Camping & "
    "Hiking > Hydration & Filtration > Water Bottles.\n"
    "Demands: FDA food-contact declaration; Prop 65 warning for "
    "California.\n"
    "Rejected alternative: Home & Kitchen > Kitchen & Dining > Travel "
    "Mugs, which reads as a coffee product and misses the outdoor intent."
)

OTHER_SUPPORTED_ANSWER: Final = (
    "Verdict: supported\n\n" + OTHER_SUPPORTED_RECOMMENDATION
)

# The refusal, as the advisor now reports one: a verdict line the system
# reads, and prose the person reads. The prose deliberately contains none
# of the four substrings the deleted matcher searched for -- it is the
# production wording that defeated that matcher -- so this test asserts
# the requirement rather than the mechanism
# (`separate-the-verdict-from-the-prose`, tasks 4.1 and 4.2).
_UNSUPPORTED_ANSWER: Final = (
    "Verdict: unsupported\n"
    "\n"
    "To give an accurate reply I would need specific details about this "
    "item; without them I cannot confidently assign a sub-category node."
)

# `launch-playbook`'s non-terminal outcomes — the three the advisor may
# propose where it cannot support a choice.
NON_TERMINAL_TYPES: Final = (type(NotStarted), type(InProgress), Blocked)
TERMINAL_DESIGNATORS: Final = (Satisfied, Refused)


# ---------------------------------------------------------------------------
# Fake chat models
# ---------------------------------------------------------------------------


class _ScriptedChatModel(BaseChatModel):
    """A chat model that answers from a script and records what it was
    asked.

    Recording the prompt is what makes *A recommendation names node,
    demands and alternative* observable at all under a stubbed model: the
    content requirement is a property of what the advisor asks for.

    `bind_tools` raises rather than returning a bound model, so a graph
    that gives this model tools fails loudly instead of quietly passing
    the no-tools test.
    """

    answers: list[str] = []  # noqa: RUF012 -- set per instance below
    received: list[list[BaseMessage]] = []  # noqa: RUF012 -- ditto

    def __init__(self, *answers: str) -> None:
        super().__init__()
        object.__setattr__(self, "answers", list(answers))
        object.__setattr__(self, "received", [])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.received.append(list(messages))
        answer = self.answers.pop(0) if self.answers else ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=answer))]
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "the advisor bound tools to its model; the spec requires that "
            "the recommendation come solely from the model's own generation"
        )

    @property
    def _llm_type(self) -> str:
        return "scripted-fake-chat-model"

    @property
    def prompts(self) -> str:
        """Every message this model was handed, flattened."""
        return "\n".join(
            str(message.content) for batch in self.received for message in batch
        )


class _RaisingChatModel(BaseChatModel):
    """A chat model whose call always fails."""

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise RuntimeError("simulated language model failure")

    @property
    def _llm_type(self) -> str:
        return "raising-fake-chat-model"


class _NonStringContentChatModel(BaseChatModel):
    """A chat model whose response content is not a plain string.

    The shape a multimodal or content-block response actually takes — a
    list of blocks — rather than an invented sentinel.
    """

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(
                        content=[{"type": "text", "text": SUPPORTED_ANSWER}]
                    )
                )
            ]
        )

    @property
    def _llm_type(self) -> str:
        return "non-string-content-fake-chat-model"


# ---------------------------------------------------------------------------
# Driving the graph — the two correction points
# ---------------------------------------------------------------------------


def _invoke(graph: Any, *, product_name: str, marketplace: str = MARKETPLACE) -> Any:
    """INVENTED input shape — correction point one.

    Tries the structured shape a product-name/marketplace graph would
    take, then the `MessagesState` shape `omni_agent`'s graph uses.

    CORRECTED during implementation (question 10's named correction
    point): the fallback catches only the errors a graph raises for an
    input *shape* it does not accept. It used to catch every exception,
    which meant a graph that accepted the structured input and then
    failed for a real reason — an unavailable model, a non-string
    response — was retried against the other shape and finally reported
    as a shape mismatch. That turned the three failure-path scenarios'
    specified exceptions into this probe's own `pytest.fail`, which is
    the one thing those tests assert did not happen. No assertion was
    changed.
    """
    structured = {"product_name": product_name, "marketplace": marketplace}
    shape_rejections = (KeyError, TypeError, ValidationError)
    try:
        return graph.invoke(structured)
    except shape_rejections as structured_error:
        prompt = f"Product: {product_name}\nMarketplace: {marketplace}"
        try:
            return graph.invoke({"messages": [HumanMessage(content=prompt)]})
        except shape_rejections as messages_error:
            pytest.fail(
                "the advisor graph accepted neither the structured input "
                f"{sorted(structured)} ({structured_error!r}) nor a "
                f"`messages` input ({messages_error!r}) — correct `_invoke` "
                "to the implemented state schema"
            )


def _recommendation_of(result: Any) -> str:
    """INVENTED output shape — correction point two."""
    if isinstance(result, str):
        return result
    for key in ("recommendation", "result", "text", "answer"):
        carried = result.get(key) if hasattr(result, "get") else None
        if isinstance(carried, str):
            return carried
    messages = result.get("messages") if hasattr(result, "get") else None
    if messages:
        ai_messages = [
            message for message in messages if isinstance(message, AIMessage)
        ]
        if ai_messages:
            return str(ai_messages[-1].content)
    pytest.fail(
        f"no recommendation text found on the graph's result {result!r} — "
        "correct `_recommendation_of` to the implemented state schema"
    )


_PROPOSE_NAMES: Final = (
    "propose",
    "propose_resolution",
    "recommend",
    "advise",
    "resolve",
)


def _propose_entry() -> Any:
    """The advisor's outcome-proposing entry point, failing loudly rather
    than defaulting.

    Probed on one module only. `group-step-handlers` merged the graph and
    the handler into a single module, so the two extra `importlib`
    candidates this once carried named what `advisor_graph` already is —
    and three names for one module is what let a stale path sit here
    unnoticed, since a candidate that fails to import is skipped silently.
    """
    for name in _PROPOSE_NAMES:
        found = getattr(advisor_graph, name, None)
        if callable(found):
            return found
    pytest.fail(
        "no outcome-proposing entry point found for the advisor under any "
        f"of {_PROPOSE_NAMES} — correct this file's probe to the "
        "implemented name"
    )


def _propose(model: BaseChatModel, *, product_name: str = PRODUCT_NAME) -> Any:
    """INVENTED call shape — the single correction point for scenarios
    *A supported choice proposes satisfaction* and *An unsupported choice
    proposes no satisfaction*.

    The model (or a graph built from it) is injected, so no live call is
    made — the same seam `build_graph(model)` exists for.
    """
    entry = _propose_entry()
    accepted = set(inspect.signature(entry).parameters)
    supplied: dict[str, Any] = {
        "product_name": product_name,
        "marketplace": MARKETPLACE,
    }
    if "graph" in accepted:
        supplied["graph"] = advisor_graph.build_graph(model)
    elif "model" in accepted:
        supplied["model"] = model
    else:
        pytest.fail(
            "the advisor's proposing entry point takes neither a `graph` "
            "nor a `model`, so it cannot be exercised without a live model "
            "call — correct `_propose`, or the seam"
        )
    unknown = sorted(set(supplied) - accepted)
    assert not unknown, (
        f"the advisor's proposing entry point does not accept {unknown}; "
        "correct `_propose` to the implemented parameter names"
    )
    return entry(**supplied)


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


# ---------------------------------------------------------------------------
# Requirement: A recommendation is produced from the product's name and
# marketplace
# ---------------------------------------------------------------------------


def test_a_recommendation_names_node_demands_and_alternative() -> None:
    """Scenario: A recommendation names node, demands and alternative.

    WHEN the advisor is given a product name and a marketplace identifier
    it can support a node choice for
    THEN it returns a recommendation naming the proposed node as a full
    path, the compliance fields and certifications that node demands, and
    a rejected alternative node with the reason it was rejected.

    Under a stubbed model the *content* of the answer is whatever the
    stub says, so what this can and does establish is the other half:
    that the advisor is given both inputs the requirement names, and that
    it asks the model for all three parts. An advisor whose prompt asks
    only for a node — the requirement's own named failure, "a
    recommendation that names no rejected alternative gives its reader
    nothing to disagree with" — fails here.
    """
    model = _ScriptedChatModel(SUPPORTED_ANSWER)
    graph = advisor_graph.build_graph(model)

    result = _invoke(graph, product_name=PRODUCT_NAME)

    # SPECIFIED: the advisor works from the product's name and the
    # marketplace identifier, so both must reach the model.
    asked = model.prompts
    assert asked, "the advisor invoked no model"
    assert PRODUCT_NAME in asked
    assert MARKETPLACE in asked

    lowered = asked.lower()
    # SPECIFIED: the node, expressed as the full path from the top-level
    # category down.
    assert "path" in lowered or "full path" in lowered
    # SPECIFIED: the compliance fields and certifications that node
    # demands.
    assert "complian" in lowered
    assert "certificat" in lowered
    # SPECIFIED: the alternative a reader would most plausibly have
    # chosen instead, with why this one was preferred.
    assert "alternative" in lowered

    # And the recommendation itself came back.
    assert _recommendation_of(result)


def test_a_recommendation_is_readable_as_it_stands() -> None:
    """Scenario: A recommendation is readable as it stands.

    WHEN a recommendation is returned
    THEN it is text a person can read without further processing, since
    it is delivered to a person for a decision and stored as the evidence
    of what was decided.
    """
    model = _ScriptedChatModel(SUPPORTED_ANSWER)
    graph = advisor_graph.build_graph(model)

    recommendation = _recommendation_of(_invoke(graph, product_name=PRODUCT_NAME))

    # SPECIFIED: text, not a structure needing rendering.
    assert isinstance(recommendation, str)
    assert recommendation.strip()
    # SPECIFIED: readable *as it stands* — the model's own prose reaches
    # the reader whole, not summarised, truncated or re-encoded.
    for line in SUPPORTED_RECOMMENDATION.splitlines():
        assert line.strip() in recommendation


# ---------------------------------------------------------------------------
# Requirement: The advisor proposes satisfaction only where it can support
# a node choice
# ---------------------------------------------------------------------------


def test_a_supported_choice_proposes_satisfaction() -> None:
    """Scenario: A supported choice proposes satisfaction.

    WHEN the advisor can support a node choice for the given product and
    marketplace
    THEN it proposes the step's satisfying outcome together with the
    recommendation.
    """
    proposal = _propose(_ScriptedChatModel(SUPPORTED_ANSWER))

    # SPECIFIED: the satisfying outcome.
    assert _outcome_of(proposal) is Satisfied
    # SPECIFIED: *together with* the recommendation — the outcome alone
    # would leave the person with nothing to weigh.
    text = _text_of(proposal)
    assert text.strip()
    for line in SUPPORTED_RECOMMENDATION.splitlines():
        assert line.strip() in text


def test_an_unsupported_choice_proposes_no_satisfaction() -> None:
    """Scenario: An unsupported choice proposes no satisfaction.

    WHEN the advisor cannot support a confident node choice for the given
    product and marketplace
    THEN it proposes a non-terminal outcome whose reason states that it
    cannot support a choice, and does not propose a satisfying outcome.

    The requirement's own reasoning names what this prevents: proposing
    satisfaction alongside "I cannot tell you the category" "would put a
    compliance-relevant step one unread paragraph away from being
    recorded `Satisfied`".
    """
    proposal = _propose(_ScriptedChatModel(_UNSUPPORTED_ANSWER))
    outcome = _outcome_of(proposal)

    # SPECIFIED: it does not propose a satisfying outcome.
    assert outcome is not Satisfied
    # SPECIFIED: nor any other terminal one — `NotApplicable` would close
    # the step just as firmly.
    assert outcome not in TERMINAL_DESIGNATORS
    assert not isinstance(outcome, NotApplicable)
    # SPECIFIED: a non-terminal outcome.
    assert isinstance(outcome, NON_TERMINAL_TYPES), (
        f"expected a non-terminal outcome, got {outcome!r}"
    )
    # SPECIFIED: whose reason states that it cannot support a choice.
    # `launch-step-automation` allows the reason to live in the produced
    # text where the outcome cannot carry one, so both are searched.
    reason = f"{getattr(outcome, 'reason', '')}\n{_text_of(proposal)}".lower()
    assert "cannot" in reason or "no confident" in reason
    assert "choice" in reason or "node" in reason or "categor" in reason


# ---------------------------------------------------------------------------
# Requirement: No tool invocation
# ---------------------------------------------------------------------------


def test_producing_a_recommendation_invokes_no_tools() -> None:
    """Scenario: Producing a recommendation invokes no tools.

    WHEN the advisor produces a recommendation
    THEN no tool, function, or marketplace call occurs during that
    processing.

    Three checks, because each catches a different way tools could enter:
    the model is never given any (`bind_tools` raises on this fake), the
    answer requests none, and nothing answered as a tool.
    """
    model = _ScriptedChatModel(SUPPORTED_ANSWER)
    graph = advisor_graph.build_graph(model)

    result = _invoke(graph, product_name=PRODUCT_NAME)

    messages = result.get("messages", []) if hasattr(result, "get") else []
    # SPECIFIED: nothing answered as a tool.
    assert not any(isinstance(message, ToolMessage) for message in messages)
    # SPECIFIED: nothing requested a tool.
    for message in messages:
        assert not getattr(message, "tool_calls", None)
    # SPECIFIED: the recommendation came solely from the model's own
    # generation over the two inputs.
    assert _recommendation_of(result)


# ---------------------------------------------------------------------------
# Requirement: No state across invocations
# ---------------------------------------------------------------------------


def test_two_invocations_do_not_share_context() -> None:
    """Scenario: Two invocations do not share context.

    WHEN the advisor produces a recommendation, and is then invoked again
    for a different product
    THEN the second recommendation is produced without reference to the
    first product or its recommendation.
    """
    model = _ScriptedChatModel(SUPPORTED_ANSWER, OTHER_SUPPORTED_ANSWER)
    graph = advisor_graph.build_graph(model)

    first = _recommendation_of(_invoke(graph, product_name=PRODUCT_NAME))
    second_result = _invoke(graph, product_name=OTHER_PRODUCT_NAME)
    second = _recommendation_of(second_result)

    # SPECIFIED: the second invocation carries nothing from the first —
    # neither the first product nor the recommendation made for it.
    second_prompt = "\n".join(str(message.content) for message in model.received[-1])
    assert PRODUCT_NAME not in second_prompt
    assert first not in second_prompt

    second_messages = (
        second_result.get("messages", []) if hasattr(second_result, "get") else []
    )
    for message in second_messages:
        assert PRODUCT_NAME not in str(message.content)
        assert first not in str(message.content)

    assert (
        second == OTHER_SUPPORTED_RECOMMENDATION
        or OTHER_SUPPORTED_RECOMMENDATION in second
    )


def test_two_invocations_for_the_same_product_are_independent() -> None:
    """Requirement statement: "each invocation SHALL be independent of
    every other, **including two invocations for the same product**".

    Stated in the requirement rather than in its scenario, and it is the
    harder half: a graph carrying state keyed by product would pass the
    different-product scenario and fail here. It is also the case the
    runtime actually produces — a rejected recommendation is re-asked for
    the same product once the cool-off elapses.
    """
    model = _ScriptedChatModel(SUPPORTED_ANSWER, OTHER_SUPPORTED_ANSWER)
    graph = advisor_graph.build_graph(model)

    _invoke(graph, product_name=PRODUCT_NAME)
    _invoke(graph, product_name=PRODUCT_NAME)

    second_prompt = "\n".join(str(message.content) for message in model.received[-1])
    assert SUPPORTED_ANSWER not in second_prompt, (
        "the second invocation for the same product carried the first "
        "invocation's answer into its prompt"
    )
    assert len(model.received[-1]) == len(model.received[0]), (
        "the second invocation's prompt grew, so the graph is accumulating "
        "state across invocations"
    )


# ---------------------------------------------------------------------------
# Requirement: Model failure is surfaced, not masked
# ---------------------------------------------------------------------------


def test_a_model_failure_is_surfaced() -> None:
    """Scenario: Language model call fails.

    WHEN the configured language model is unavailable or returns an error
    while the advisor is producing a recommendation
    THEN the invocation fails visibly rather than returning a
    recommendation as if the call had succeeded.
    """
    graph = advisor_graph.build_graph(_RaisingChatModel())

    with pytest.raises(RuntimeError, match="simulated language model failure"):
        _invoke(graph, product_name=PRODUCT_NAME)


def test_a_non_string_response_content_is_surfaced() -> None:
    """Scenario: Response content is not a plain string.

    WHEN the configured language model's response content is not a plain
    string
    THEN the invocation fails visibly rather than returning a
    recommendation coerced or fabricated from that content.

    SPECIFIED: it fails. DERIVED: nothing fixes the exception type; the
    `omni-agent` precedent for the same words is a named error
    (`NonStringAnswerError`), so a specific type is likely — but the
    requirement is visibility, which any raised failure satisfies and a
    coerced `str(...)` does not.
    """
    graph = advisor_graph.build_graph(_NonStringContentChatModel())

    with pytest.raises(Exception) as failure:  # any visible failure will do
        _invoke(graph, product_name=PRODUCT_NAME)

    # Not a `pytest.fail` from this file's own probes: those would mean
    # the shape is wrong, not that the advisor surfaced anything.
    assert not isinstance(failure.value, AssertionError), (
        "the graph shape, not the advisor, is what failed here"
    )


def test_a_non_string_response_is_never_returned_as_a_recommendation() -> None:
    """Requirement statement: "rather than returning a fabricated, empty,
    or silently degraded recommendation".

    The negative half, asserted separately because "it raised" and "it
    did not return a degraded answer" are different claims and an
    implementation could satisfy the first for an unrelated reason. A
    masked failure here "would reach a person as a recommendation to
    accept, and be recorded as the evidence for a compliance-relevant
    decision".
    """
    graph = advisor_graph.build_graph(_NonStringContentChatModel())

    try:
        result = _invoke(graph, product_name=PRODUCT_NAME)
    except Exception:  # noqa: BLE001 -- the specified path; asserted above
        return

    pytest.fail(
        "the advisor returned a recommendation built from non-string "
        f"response content instead of surfacing the failure: {result!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a proposed browse node is a real Amazon node, or the right
#   one. No deterministic test can establish it, and the spec does not
#   claim it: "The advisor is never relied on to settle the step by
#   itself", which is why the step it is written for requires
#   confirmation.
# - `build_production_graph()`'s own wiring — which model constant it
#   pins. `design.md`'s Open Questions leave the model choice open
#   ("Answerable after seeing real output"), and exercising it would mean
#   a live call, which this tier forbids.
# - That the advisor is registered under a handler name in both
#   composition roots (`tasks.md` 7.4, 8.6a). That is a registry-parity
#   property of the deployment, not of the graph, and belongs with the
#   existing registration-divergence guard in
#   `tests/unit/test_registrations_across_processes.py`, which this pass
#   does not edit.
# ---------------------------------------------------------------------------
