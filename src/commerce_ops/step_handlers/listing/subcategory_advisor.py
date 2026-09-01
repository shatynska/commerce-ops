"""The sub-category advisor: its graph, and its registration as a handler.

`subcategory-advisor`: given a product's name and its marketplace, propose
the Amazon sub-category node it belongs in and, in a comment, name the
compliance fields and certifications that node demands and the
alternative node rejected in its favour — the work `lp.listing.007`
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

**Support comes from a schema-validated discriminant, not from reading
prose.** The model's answer is constrained to `AdvisorResult` — `Supported`
or `Unsupported`, distinguished by `ok` — so a supported result is read
from that field, never searched for in text. The one place prose can still
withhold support is `Supported.comment`: it is where all of the advisor's
narrative now lives, so it is also the one place a model could still write
"actually I'm not sure" despite setting `ok: true`; `_advisor_refuses`
narrowly vetoes exactly that (`propose()`). Whether a non-empty comment
actually *contains* the compliance demands and rejected alternative it was
prompted for is never checked — only that it is non-empty. A model or
transport failure, and a response that fails schema validation against
both variants, both surface rather than being masked: a masked failure
here would not merely return a poor answer — it would reach a person as a
recommendation to accept and become the evidence for a
compliance-relevant decision.

**Which processes import this module is load-bearing.** Registration
happens where the handler is defined, through `register_step_handler` —
the `registrations.py` idiom this project keeps for scheduled work, and
for the same reason: whoever registers a handler is not necessarily
whoever decides a step is ready to hold a gate. Activation is validated
against the registry in the process serving the admin surface, while the
pass needs the same handler in the worker; a handler imported into only
one leaves them disagreeing, with `check_step_handlers` reporting it
registered while the admin's activation is refused as naming an unknown
handler. `registrations.py` — the one list every composition root imports
— is what keeps them in step.

Because the graph and the registration now sit in one module, importing it
at all is what registers the handler; previously the graph could be
imported without that happening. Nothing about that is expensive.
`_graph()` stays `lru_cache`d, so no credential read moves to import time,
and `StepHandlerRegistry.register` raises only for a *different* callable
under one name, so a repeated import is safe.

**The graph libraries are imported inside the functions that build a
graph, and that is deliberate — do not tidy them back to the top.**
Registering a step handler makes its name resolvable and must load nothing
the handler needs in order to run (`launch-step-automation`). Registration
is an import side effect, and `registrations.py` is the one list that
causes those imports in every process consulting the registry, so a
top-level `langgraph` or `langchain_openai` here is paid by processes that
will never invoke this handler — the startup handler report among them —
multiplied by every handler the deployment answers for.

This is `_graph()`'s note one step earlier. That one defers *constructing*
the model, because construction reads credentials; this defers *importing*
it, because the import costs roughly two thousand modules. Same reasoning,
one step apart.
"""

from __future__ import annotations

import functools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from commerce_ops.launch.application import (
    Blocked,
    Satisfied,
    StepContext,
    StepResolution,
    register_step_handler,
)
from commerce_ops.shared.domain.result import Success

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "HANDLER_NAME",
    "AdvisorResponse",
    "AdvisorResult",
    "AdvisorState",
    "Contradiction",
    "Proposal",
    "Supported",
    "Unsupported",
    "advise_sub_category",
    "build_graph",
    "build_production_graph",
    "propose",
]

HANDLER_NAME = "listing.subcategory_advisor"

#: Who the refusal has to be *about* for the veto to fire. The veto reads
#: a statement that the **advisor** cannot make a choice; a recommendation
#: saying some rejected node "cannot support a food-contact claim" is a
#: statement about that node, and vetoing on it would block the step on
#: every pass for that product. Hence a subject, not a phrase list.
_REFUSING_SUBJECT = r"(?:i|we|the advisor|this advisor)"
_REFUSAL_VERB = r"(?:cannot|can not|can't|could not|couldn't|am unable to|is unable to|are unable to)"
#: What it must be refusing to do: choose a placement, not meet some
#: particular demand.
_REFUSAL_OBJECT = (
    r"(?:[^.]{0,60}?)"
    r"(?:node|sub-?category|category|placement|classification|choice|answer)"
)
_ADVISOR_REFUSES = re.compile(
    rf"\b{_REFUSING_SUBJECT}\b[^.]{{0,40}}?\b{_REFUSAL_VERB}\b{_REFUSAL_OBJECT}",
    re.IGNORECASE,
)

_PROMPT = """\
You are advising on where an Amazon product listing belongs.

Product: {product_name}
Marketplace: {marketplace}

Propose the sub-category node this product belongs in, expressed as the
full path from the top-level category down. In your comment, name the
compliance fields and certifications that node demands, then name the
alternative node a reader would most plausibly have chosen instead, and
why this one was preferred.

If the category structure gives you no confident answer for this product
and marketplace, report that you cannot support a node choice rather than
naming one.
"""

#: Shared by both fail-safe routes below (no verdict validated at all, and
#: a supported verdict whose comment was empty): a shortfall in what the
#: model produced, not a finding about the product, so both read as one
#: reason rather than two.
_NO_VERDICT_REASON = (
    "the sub-category advisor reported no verdict that could be read for "
    "'{product_name}' on '{marketplace}', so whether a node choice could "
    "be supported is unknown rather than settled"
)


def _no_verdict_reason(product_name: str, marketplace: str) -> str:
    return _NO_VERDICT_REASON.format(product_name=product_name, marketplace=marketplace)


def _contradiction_reason(
    product_name: str, marketplace: str, *, withheld_by: str
) -> str:
    """A supporting verdict its own response contradicts.

    `withheld_by` names the field that did the contradicting — `comment`
    or `error`. It is a parameter rather than fixed prose because an
    error-based contradiction may carry no comment at all, and a reason
    blaming a field the response never had would not name what was
    actually wrong.
    """
    return (
        "the sub-category advisor reported a supporting verdict that its "
        f"own {withheld_by} contradicts, so the verdict and the "
        f"{withheld_by} disagree and no node choice was accepted for "
        f"'{product_name}' on '{marketplace}'"
    )


def _unsupported_reason(error: str, product_name: str, marketplace: str) -> str:
    return (
        "the sub-category advisor could not support a node choice for "
        f"'{product_name}' on '{marketplace}': {error}"
    )


def _render_unsupported(error: str, comment: str | None) -> str:
    text = f"The sub-category advisor could not support a node choice: {error}."
    if comment:
        text = f"{text}\n\n{comment}"
    return text


def _render_supported(value: str, comment: str) -> str:
    return f"{value}\n\n{comment}"


def _render_contradiction(value: str | None, error: str, comment: str | None) -> str:
    """What a reader sees for a response that reported support and a
    refusal at once.

    The error leads, and is never omitted: this is the text delivered to
    Slack and stored as evidence, and an error-based contradiction may
    carry no comment, so rendering it the way a supported result is
    rendered would show a reader a bare node path with nothing in it to
    say support was withheld.
    """
    text = (
        "The sub-category advisor reported a node choice and, in the same "
        f"response, why it could not support one: {error}."
    )
    if value and value.strip():
        text = f"{text}\n\nThe node it named was: {value}"
    if comment:
        text = f"{text}\n\n{comment}"
    return text


class Supported(BaseModel):
    """The model's structured answer where it can support a node choice.

    `value` is the sub-category node alone — becomes `Success.value` if
    the recommendation is accepted. `comment` carries everything else: the
    compliance fields and certifications the node demands, and the
    alternative node rejected in its favour. That content is a prompting
    obligation, not something code parses out of it — only that it is
    non-empty is checked.
    """

    ok: Literal[True]
    value: str
    comment: str | None = None


class Unsupported(BaseModel):
    """The model's structured answer where it cannot support a choice."""

    ok: Literal[False]
    error: str
    comment: str | None = None


AdvisorResult = Supported | Unsupported


@dataclass(frozen=True, slots=True)
class Contradiction:
    """A response that reported support and, in the same breath, why it
    could not support a choice.

    Not one of the two reported variants: it is neither a node choice to
    weigh nor a classification considered and declined, and recording it
    as either misstates what happened. `error` is what the model said was
    wrong, and it is what the reader must be shown — see
    `_render_contradiction`.
    """

    error: str
    value: str | None = None
    comment: str | None = None


# The shape the model is asked to answer in -- the *wire* schema.
#
# **This class's docstring is not documentation: it is sent to the model.**
# Pydantic puts it in the generated schema's `description`, so it is paid
# for on every call and read by the model as instruction. The reasoning
# below therefore lives in this comment, and the docstring says only what
# the model needs.
#
# Deliberately flat, and deliberately not `Supported | Unsupported`. A
# top-level union is not a shape `langchain_openai`'s adapter accepts: it
# hands the schema to `convert_to_openai_function`, whose contract is a
# dict, a `BaseModel` subclass or a callable, so a union raises
# `ValueError: Unsupported function` before the model is ever called --
# which is exactly what made `lp.listing.007` inert in production.
#
# A `BaseModel` wrapping a discriminated union is accepted by that
# conversion and is still the wrong answer: pydantic emits a `oneOf` for a
# tagged union, and OpenAI's strict structured outputs accept only
# `anyOf`, so it would pass every check runnable offline and fail at the
# API instead. This shape emits a plain object with nullable string
# properties and no such construct anywhere.
#
# The cost of flatness is that it can express states the reported variants
# forbid -- support with no value, support carrying an error. That cost is
# paid once, in `_from_wire`, which defines a destination for every
# combination rather than only the well-behaved ones. The field
# descriptions are the other half: the union coupled its fields
# structurally, and a flat shape has to say in the schema what the union
# said in its shape, or the model fills them inconsistently and every
# inconsistent response routes to "no verdict could be read".
class AdvisorResponse(BaseModel):
    """Where an Amazon product listing belongs, or why that cannot be said."""

    ok: bool = Field(
        description=(
            "True if you can support a sub-category node choice for this "
            "product and marketplace; False if you cannot."
        )
    )
    value: str | None = Field(
        default=None,
        description=(
            "The sub-category node you propose, as the full path from the "
            "top-level category down. Required when ok is true; leave null "
            "when ok is false."
        ),
    )
    error: str | None = Field(
        default=None,
        description=(
            "Why you cannot support a node choice. Required when ok is "
            "false; leave null when ok is true. Do not use it to qualify a "
            "node you are proposing — a response that both names a node "
            "and states why none can be named is treated as a "
            "contradiction and no node is recorded."
        ),
    )
    comment: str | None = Field(
        default=None,
        description=(
            "Everything else the reader needs: the compliance fields and "
            "certifications the proposed node demands, and the "
            "alternative node most plausibly chosen instead, with why "
            "this one was preferred. Required when ok is true."
        ),
    )


def _from_wire(
    response: AdvisorResponse,
) -> Supported | Unsupported | Contradiction | None:
    """Convert a wire response into what the advisor reports, or nothing.

    Total by construction: every combination of `ok`, `value` and `error`
    reaches exactly one destination, and `None` means "no verdict could be
    read" rather than "unhandled".

    A field counts as absent when it is `None`, empty, **or whitespace
    only** — not merely `None`. Under strict structured output every
    property is required, so a model with nothing to put in a field emits
    `""` rather than omitting it.

    The order matters. A supporting discriminant carrying an error is a
    contradiction **whether or not a value accompanies it**, and that test
    comes before the missing-value one deliberately: a response that says
    why no node could be named has told the reader more than one that
    merely omits it, and routing it to the shortfall would discard the
    explanation the model actually gave.
    """
    error = response.error
    value = response.value

    if response.ok:
        if error is not None and error.strip():
            return Contradiction(error=error, value=value, comment=response.comment)
        if value is None or not value.strip():
            return None
        return Supported(ok=True, value=value, comment=response.comment)

    if error is None or not error.strip():
        return None
    return Unsupported(ok=False, error=error, comment=response.comment)


class AdvisorState(TypedDict, total=False):
    """The graph's state: what it is given, and what it produced."""

    product_name: str
    marketplace: str
    #: What the model's structured answer converted to, or `None` where
    #: the call completed but its response mapped to no reported result.
    #: Absent-vs-`None` is not a distinction this state needs to preserve:
    #: a call that never ran surfaces as an exception, not as a state
    #: without this key.
    #:
    #: `Contradiction` is here because the wire schema can express a
    #: response the reported variants cannot — support carrying the error
    #: that withholds it — and it must not be forced into either of them:
    #: `None` records the wrong reason, `Unsupported` asserts a decline
    #: that never happened, and folding the error into `comment` reaches
    #: `Satisfied`, since `_advisor_refuses` needs a first-person subject
    #: a model-authored error will not have.
    parsed: Supported | Unsupported | Contradiction | None


@dataclass(frozen=True, slots=True)
class Proposal:
    """What the advisor hands the runtime: an outcome, the text, and —
    where it could support a choice — a typed finding."""

    outcome: Any
    result: str
    finding: Any = None


def build_graph(model: BaseChatModel) -> Any:
    """The graph over an injected model — the testable seam."""
    # Imported here, not at module scope: registering this handler must not
    # load what running it needs (`launch-step-automation`). `recommend` is
    # nested below, so its closure carries `HumanMessage` and the import runs
    # once per graph rather than once per invocation.
    from langchain_core.messages import HumanMessage
    from langgraph.graph import END, START, StateGraph

    def recommend(state: AdvisorState) -> dict[str, Any]:
        prompt = _PROMPT.format(
            product_name=state.get("product_name", ""),
            marketplace=state.get("marketplace", ""),
        )
        # A single `BaseModel`, so no cast is needed and the type checker
        # can see this call. The union that used to be cast to `type` here
        # was rejected at runtime by every conversion the adapter performs
        # -- the cast silenced the one check that could have said so.
        structured = model.with_structured_output(AdvisorResponse, include_raw=True)
        # No `try` around this: a model or transport fault must surface,
        # not become a recommendation.
        response = structured.invoke([HumanMessage(content=prompt)])
        # `include_raw=True` always answers a dict of `raw`/`parsed`/
        # `parsing_error` (the docstring says so; the stub's return type
        # does not encode it, since it carries no `include_raw` overload).
        assert isinstance(response, dict)
        wire = response.get("parsed")
        # A response that validated against no schema at all arrives as
        # `None` and stays `None` -- the same "no verdict could be read"
        # destination a response that parsed but mapped nowhere reaches.
        if not isinstance(wire, AdvisorResponse):
            return {"parsed": None}
        return {"parsed": _from_wire(wire)}

    graph = StateGraph(AdvisorState)
    graph.add_node("recommend", recommend)
    graph.add_edge(START, "recommend")
    graph.add_edge("recommend", END)
    return graph.compile()


def build_production_graph() -> Any:
    """The graph the registered handler runs, over the configured model."""
    # Imported here for the same reason as in `build_graph`: registration
    # loads the handler's name, and nothing it needs in order to run.
    from langchain_openai import ChatOpenAI

    return build_graph(ChatOpenAI(model="gpt-4o-mini"))


def _advisor_refuses(comment: str) -> bool:
    """Whether the comment says *the advisor* cannot make a choice.

    Deliberately narrower than a substring list. That would also match a
    rejected alternative described as unable to support some particular
    demand -- a statement about that node, not about the advisor -- and
    vetoing on it would block the step on every pass for the product,
    since the same prompt yields the same shape. So the subject is what is
    matched, not the phrase. Runs only over `comment`: `value` carries no
    prose to misread at all.
    """
    return _ADVISOR_REFUSES.search(comment) is not None


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
    parsed = state.get("parsed")

    if isinstance(parsed, Supported):
        comment = parsed.comment
        # Route 2: validated as supported, but the comment is empty — a
        # shortfall in what the model produced, not evidence to be trusted
        # with satisfaction. Shares its reason with route 1 below.
        if not comment:
            reason = _no_verdict_reason(product_name, marketplace)
            return Proposal(outcome=Blocked(reason=reason), result=reason)
        # Route 3: the one direction prose may still act in. A verdict
        # claiming support while its own comment refuses is the state the
        # served prohibition on "a satisfying one accompanied by text
        # admitting there is no answer" exists to forbid.
        if _advisor_refuses(comment):
            reason = _contradiction_reason(
                product_name, marketplace, withheld_by="comment"
            )
            return Proposal(
                outcome=Blocked(reason=reason),
                result=_render_supported(parsed.value, comment),
            )
        return Proposal(
            outcome=Satisfied,
            result=_render_supported(parsed.value, comment),
            finding=Success(value=parsed.value, comment=comment),
        )

    if isinstance(parsed, Contradiction):
        # Route 4: the response reported support and, in the same breath,
        # why it could not support a choice. Neither a node choice to
        # weigh nor a classification considered and declined -- and the
        # error is carried into the rendered text, not left only in the
        # reason, so the person reading the recommendation sees the
        # refusal rather than a node path that looks accepted.
        reason = _contradiction_reason(product_name, marketplace, withheld_by="error")
        return Proposal(
            outcome=Blocked(reason=reason),
            result=_render_contradiction(parsed.value, parsed.error, parsed.comment),
        )

    if isinstance(parsed, Unsupported):
        # A classification considered and declined -- a finding about the
        # product, unlike the two shortfall routes above and below.
        return Proposal(
            outcome=Blocked(
                reason=_unsupported_reason(parsed.error, product_name, marketplace)
            ),
            result=_render_unsupported(parsed.error, parsed.comment),
        )

    # Route 1: the structured call completed but validated against neither
    # variant -- the same condition a value fitting neither `supported` nor
    # `unsupported` described before structured output existed. Saying
    # "could not support a node choice" here would record a model omission
    # on the launch as the advisor's own judgement about the product.
    reason = _no_verdict_reason(product_name, marketplace)
    return Proposal(outcome=Blocked(reason=reason), result=reason)


@functools.lru_cache
def _graph() -> object:
    """Built on first use, never at import: constructing the model reads
    credentials, and importing this module must not require them."""
    return build_production_graph()


@register_step_handler(HANDLER_NAME)
async def advise_sub_category(context: StepContext) -> StepResolution:
    """Propose the sub-category node, or say it cannot support a choice.

    Reads only what the context carries — the product the pass resolved,
    never a catalog of its own. A model failure propagates, and the pass
    records nothing for a step it could not evaluate.
    """
    product = context.product
    # Read through the value, not over the object carrying it. `str()` on a
    # `MarketplaceId` yields its repr, so the model was being asked about a
    # marketplace named `MarketplaceId(value='ATVPDKIKX0DER')` -- and the
    # refusal reason recorded on the launch named it too, since `propose`
    # interpolates this one value into both. `name` needs no unwrapping: it
    # is a plain `str`, which is why the line below it was correct while
    # this one was not.
    marketplace = getattr(product, "marketplace_id", "")
    proposal = propose(
        product_name=str(getattr(product, "name", "")),
        marketplace=str(getattr(marketplace, "value", marketplace)),
        graph=_graph(),
    )
    return StepResolution(
        outcome=proposal.outcome, result=proposal.result, finding=proposal.finding
    )
