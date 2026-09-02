"""The compliance screen: its graph, and its registration as a handler.

`strategy.compliance_screen`: given a product and the screening step it is
resolving, it screens that product against the prohibited and
high-compliance categories **the step itself names**, and proposes the
step's satisfying outcome only where it can support that the product is
clear of them — the work `lp.strategy.006` describes, performed before
money is spent on sourcing.

Shaped like `listing/subcategory_advisor.py`, deliberately and almost
line for line: the same `build_graph(model)` / `build_production_graph()`
split, the same async-only compiled graph, the same flat wire schema, the
same deferred graph-library imports. Where this screen differs from that
handler, it differs because the question differs — and each of those
places is called out below. Nothing here factors the common parts out:
`step_handlers/` "holds handlers and nothing else", and an abstraction
drawn from two examples across two disciplines would be a guess about the
third.

**The categories come from the step, not from this module.** There is no
list of prohibited categories in this file and there must never be one.
The authored step's `description` is the list — it is the sentence a
member opens the step to read — and `playbook-authoring` owns editing it,
recording who edited it and when. A copy here would be a second statement
of the same thing with nothing keeping the two in step, and the
divergence would be silent in the worst direction: the member reads one
list while the screen tests another. `playbook-authoring` already settles
this shape for operative content, since a gate threshold likewise lives
in the description of the step that establishes it.

The consequence is real and is accepted rather than hidden: **editing
that description edits the screen**, with no deploy and no code review.
What makes it safe is the next paragraph.

**The produced text cites the description, and this module renders that
citation itself.** Not from the model's `comment` — the comment's content
is prose this capability forbids code to inspect, so a citation carried
there is one nothing can rely on and nothing can assert. Rendering it
means a description edited to name fewer categories leaves a trace on
every launch the narrowed screen ran on.

And the citation carries the description's text **through unaltered**.
Nothing is extracted from it: no parsing into category names, no
selecting the part that looks like a list. The seeded description reads
as a sentence with a parenthetical of eight examples in it, which looks
parseable, and that instinct is wrong twice over. A parser keeps what
matches its shape and drops the rest, so a description naming both a
referenced list *and* inline examples would be cited as the examples
alone — understating the screen while every assertion written against
those eight items still passed. And a screen that parsed prose to say
what it screened against would be doing, in its own citation, exactly
what it refuses to do to the model's answer.

**Three verdicts, not two, and `undetermined` is first-class.** Most of
what decides a hazmat or high-compliance classification — a lithium
battery, a pressurised cell, an ingestible, a magnet — is not derivable
from a product's name, which is the substance of what this screen is
given. A screen forced to answer clear-or-flagged would answer one of
them by guessing, and a guessed "clear" here is not a poor answer; it is
a production run committed against a product Amazon will not let the
seller ship. So the wire schema gives an inability its own slot rather
than leaving the model to express one by contradicting itself. That is
the one structural difference from `subcategory_advisor`, whose two-state
discriminant is exactly why it needs a `Contradiction` carrier and this
does not.

**The three withheld reasons are three different sentences, and that is
load-bearing.** A flagged verdict is a finding about the product. An
undetermined one is a statement about what the screen was given. An
unreadable one is a shortfall in what the model produced. Recording any
of them under another's wording misstates on the launch's own record what
happened, and a member reading "could not screen this product" where the
truth was "this product is a supplement" takes the wrong next action.

**A model failure is not caught here, and adding a `try` would be the
defect.** `launch-step-automation` reports a raising handler naming the
launch, step and handler, records nothing against the step, and continues
the pass — the correct behaviour is obtained by doing nothing. The route
a broad `except` would land in is `_UNREADABLE_REASON`, one branch away,
which produces a perfectly well-formed non-terminal outcome; an outage
would then be recorded on every launch as this screen's judgement about a
product, and the operator-facing fault would be suppressed at the same
time. Do not "harden" the model call.

**The graph libraries are imported inside the functions that build a
graph, and that is deliberate — do not tidy them back to the top.**
Registering a step handler makes its name resolvable and must load
nothing the handler needs in order to run
(`launch-step-automation`). Registration is an import side effect, and
`registrations.py` is the one list that causes those imports in every
process consulting the registry, so a top-level `langgraph` or
`langchain_openai` here is paid by processes that will never invoke this
handler — the startup handler report among them — multiplied by every
handler the deployment answers for. `_graph()` stays `lru_cache`d for the
same reason one step later: constructing the model reads credentials.
"""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from commerce_ops.launch.application import (
    Blocked,
    Satisfied,
    StepContext,
    StepResolution,
    register_step_handler,
)

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

__all__ = [
    "HANDLER_NAME",
    "ScreenResponse",
    "ScreenState",
    "Verdict",
    "build_graph",
    "build_production_graph",
    "propose",
    "screen_for_compliance",
]

HANDLER_NAME = "strategy.compliance_screen"

Verdict = Literal["clear", "flagged", "undetermined"]

#: Who the veto's refusal has to be *about* for it to fire. It reads a
#: statement that **the screen** cannot do its work; a comment saying that
#: some named category "cannot apply to this product" is a statement about
#: that category, and vetoing on it would block the step on every pass for
#: that product, since the same prompt yields the same shape. Hence a
#: subject, not a phrase list — the same construction
#: `subcategory_advisor._ADVISOR_REFUSES` uses, and deliberately a
#: separate one: the two match different sentences about different things,
#: and the only thing genuinely common between them is the technique.
_REFUSING_SUBJECT = r"(?:i|we|the screen|this screen)"
_REFUSAL_VERB = (
    r"(?:cannot|can not|can't|could not|couldn't|am unable to|is unable to|"
    r"are unable to)"
)
#: What it must be refusing to *do*, and this is the part that has to be
#: tight rather than generous.
#:
#: An earlier version allowed any 60 characters between the verb and a bare
#: object word drawn from `screen|classify|determine|…`. That is the
#: vocabulary a **clear** comment uses about the categories, so it vetoed
#: ordinary passing prose: "I cannot find anything in this product that a
#: hazmat *screen* would flag" and "I could not *determine* any hazard
#: because there is none to determine" both matched. Since the same prompt
#: yields the same shape, the step was then blocked on *every* pass for
#: that product — the failure this veto's own requirement exists to forbid.
#:
#: So the refused act must sit immediately after the verb (at most two
#: words of adverbial slack), and must take either the product or an
#: embedded question as its object. "cannot screen this product" is a
#: refusal; "could not determine any hazard" is a finding of nothing, and
#: the object is what tells them apart.
_REFUSAL_ACT = (
    r"(?:screen|classify|assess|judge)\s+(?:this|the|it)\b"
    r"|(?:determine|assess|judge|say|tell|screen)\s+(?:whether|if)\b"
)
_SCREEN_REFUSES = re.compile(
    rf"\b{_REFUSING_SUBJECT}\b[^.]{{0,40}}?\b{_REFUSAL_VERB}\b"
    rf"\s*(?:\w+\s+){{0,2}}?(?:{_REFUSAL_ACT})",
    re.IGNORECASE,
)

_PROMPT = """\
You are screening a product against a named set of prohibited and
high-compliance categories, before any money is spent on sourcing it.

Product: {product_name}

Screen it against exactly these categories, and no others:

{categories}

Answer with one of three verdicts.

- "clear" if the product falls in none of the categories above.
- "flagged" if it falls in at least one of them.
- "undetermined" if what you have been given does not settle which of the
  two it is. Most of what decides these classifications - whether the item
  contains a lithium battery, a pressurised gas, a liquid over a volume
  threshold, a magnet, something ingestible - cannot be read off a product
  name. Where that is what is missing, say so rather than guessing.

In your comment: for "clear", name the categories you considered and why
none applies; for "flagged", name which categories it falls in and what
that means for the launch; for "undetermined", state the one fact about
the product that would settle it, so the reader knows what to supply.
"""


def _blank(value: str | None) -> bool:
    """Whether a value counts as absent.

    Empty, whitespace-only or `None` — not merely `None`. Under strict
    structured output every property is required, so a model with nothing
    to put in a field emits `""` rather than omitting it; and a step's
    description is authored prose, which acquires trailing whitespace the
    way authored prose does.
    """
    return value is None or not value.strip()


def _no_product_reason() -> str:
    """A launch whose catalog product could not be resolved.

    The mirror of `_no_categories_reason`, and it exists for the same
    reason stated one guard over: a model asked to screen a product it was
    never told the name of answers anyway, plausibly `clear`, and the step
    would then be satisfied for a product the pass could not even read.
    `automation_pass` obtains the product from a read typed
    `Product | None` and hands it on without a nil check, so this is a
    state the handler is genuinely reachable in rather than a defensive
    hypothetical.
    """
    return (
        "the compliance screen was given no product to screen, so nothing "
        "was screened and whether it is clear is unasked rather than "
        "answered"
    )


def _no_categories_reason(product_name: str) -> str:
    """A step that named nothing to screen against.

    Deliberately says nothing about any category — a screen carrying a
    list of its own would have something to name here, and naming one
    would be the tell.
    """
    return (
        "the step names no categories to screen against, so nothing was "
        f"screened for '{product_name}' and whether it is clear is unasked "
        "rather than answered"
    )


def _unreadable_reason(product_name: str) -> str:
    """A shortfall in what the model produced — not a finding about the
    product, and worded so an operator can tell the difference."""
    return (
        "the compliance screen reported no verdict that could be read for "
        f"'{product_name}', so whether it is clear of the categories the "
        "step names is unknown rather than established"
    )


def _flagged_reason(product_name: str) -> str:
    """A finding about the product: the screen did its work and the answer
    was unwelcome."""
    return (
        f"the compliance screen flagged '{product_name}' against the "
        "categories the step names, so it is not clear of them"
    )


def _undetermined_reason(product_name: str) -> str:
    """A statement about what the screen was given, not about the
    product."""
    return (
        "the compliance screen could not settle whether "
        f"'{product_name}' falls in any category the step names from what "
        "it was given"
    )


def _contradiction_reason(product_name: str) -> str:
    """A clear verdict its own comment withholds.

    Its own reason rather than the flagged one: recording a
    self-contradicting response as flagged would put "this product is a
    supplement" on the record where the truth was "the response
    contradicted itself".
    """
    return (
        "the compliance screen reported a clear verdict that its own "
        f"comment contradicts, so no clear verdict was accepted for "
        f"'{product_name}'"
    )


def _render(categories: str, verdict: str, comment: str) -> str:
    """The text a member reads: three parts, in this order.

    The citation leads because it is the part no other participant can
    supply — the model never sees it come back, and a reader checking
    whether the screen was narrowed looks for it first.
    """
    return (
        f"Screened against, as the step names them:\n{categories}\n\n"
        f"Verdict: {verdict}\n\n{comment}"
    )


def _render_shortfall(categories: str, reason: str) -> str:
    """What a reader sees where no verdict was reached at all.

    The citation still leads. On these routes the description *was* read
    and the model *was* called against it, so a narrowed screen ran — and
    the whole point of citing is that it leaves a trace on every launch it
    ran on. Rendering only the reason here would lose exactly the launches
    where the screen produced least.
    """
    return f"Screened against, as the step names them:\n{categories}\n\n{reason}"


def _render_contradiction(categories: str, comment: str) -> str:
    """What a reader sees for a clear verdict whose comment withholds it.

    The withholding leads, and the comment is never dropped: this is the
    text delivered to Slack and stored as evidence, and rendering it the
    way a clear verdict is rendered would show a reader a bare "clear"
    with nothing in it to say the response took it back.
    """
    return (
        f"Screened against, as the step names them:\n{categories}\n\n"
        "The compliance screen reported a clear verdict and, in the same "
        f"response, why it could not screen the product:\n\n{comment}"
    )


# The shape the model is asked to answer in -- the *wire* schema.
#
# **This class's docstring is not documentation: it is sent to the model.**
# Pydantic puts it in the generated schema's `description`, so it is paid
# for on every call and read by the model as instruction. The reasoning
# therefore lives in this comment, and the docstring says only what the
# model needs.
#
# Deliberately flat, and deliberately not a union of the three verdicts.
# `langchain_openai`'s adapter hands the schema to
# `convert_to_openai_function`, whose contract is a dict, a `BaseModel`
# subclass or a callable, so a top-level union raises before the model is
# ever called -- which is what made `lp.listing.007` inert in production. A
# `BaseModel` wrapping a discriminated union is accepted by that conversion
# and still wrong: pydantic emits `oneOf` for a tagged union, and OpenAI's
# strict structured outputs accept only `anyOf`.
#
# One `Literal` discriminant rather than two booleans. Two booleans can
# express `determinable=False, clear=True`, which means nothing, and every
# such combination would need a defined destination. A three-valued
# `Literal` cannot express them at all, and emits a plain string property
# carrying `enum` -- inside the strict subset, and no `oneOf` anywhere.
#
# There is no `error` field. That is `subcategory_advisor`'s shape, and it
# is what created that handler's `Contradiction` case: `ok=true` carrying
# an error is a state the reported variants forbid but the wire permits.
# Here `undetermined` *is* the structured home for an inability, so a model
# with nothing to assert has a slot for it and no reason to reach for a
# contradicting one.
class ScreenResponse(BaseModel):
    """Whether a product falls in any of the named categories."""

    verdict: Verdict = Field(
        description=(
            "'clear' if the product falls in none of the named categories; "
            "'flagged' if it falls in at least one; 'undetermined' if what "
            "you were given does not settle which. Always populated."
        )
    )
    comment: str | None = Field(
        default=None,
        description=(
            "Why you reached that verdict, in prose: for 'clear', the "
            "categories considered and why none applies; for 'flagged', "
            "which categories and what that means; for 'undetermined', the "
            "one fact about the product that would settle it. Always "
            "populate this - a verdict with no comment is discarded."
        ),
    )


class ScreenState(TypedDict, total=False):
    """The graph's state: what it is given, and what it produced."""

    product_name: str
    categories: str
    #: The model's structured answer, or `None` where the call completed
    #: but its response validated against no schema at all.
    parsed: ScreenResponse | None


def build_graph(model: BaseChatModel) -> Any:
    """The graph over an injected model — the testable seam.

    **The compiled graph is async-only, and that is load-bearing.** Its
    one node is a coroutine, so `compiled.invoke(...)` raises rather than
    running anything. Callers reach it through `ainvoke`, and `propose()`
    is the only caller that should.

    That refusal is the enforcement for the graph half of
    `launch-step-automation`'s *A handler's waiting does not stop the
    process*. A later author who reverts the node to the synchronous entry
    point does not get a handler that quietly pins the event loop for the
    length of a model call — they get one that fails on its first
    invocation, naming the node. Do not "restore" a synchronous path to
    make some caller work; fix the caller.
    """
    # Imported here, not at module scope: registering this handler must not
    # load what running it needs (`launch-step-automation`). `screen` is
    # nested below, so its closure carries `HumanMessage` and the import
    # runs once per graph rather than once per invocation.
    from langchain_core.messages import HumanMessage
    from langgraph.graph import END, START, StateGraph

    async def screen(state: ScreenState) -> dict[str, Any]:
        prompt = _PROMPT.format(
            product_name=state.get("product_name", ""),
            categories=state.get("categories", ""),
        )
        structured = model.with_structured_output(ScreenResponse, include_raw=True)
        # No `try` around this, deliberately -- see the module docstring.
        # A model or transport fault must surface, not become a verdict.
        #
        # Awaited, not called: `invoke` issues a blocking HTTP request, and
        # a coroutine that never yields pins the loop it was invoked on for
        # the whole round-trip.
        response = await structured.ainvoke([HumanMessage(content=prompt)])
        # `include_raw=True` always answers a dict of `raw`/`parsed`/
        # `parsing_error`. A response that is not that dict is a
        # transport- or client-level fault prior to any verdict existing,
        # and this assertion is what surfaces it rather than letting it be
        # coerced into one.
        assert isinstance(response, dict)
        wire = response.get("parsed")
        # A response that validated against no schema arrives as `None` and
        # stays `None` -- the "no verdict could be read" destination, which
        # is a shortfall in what the model produced and not a fault.
        if not isinstance(wire, ScreenResponse):
            return {"parsed": None}
        return {"parsed": wire}

    graph = StateGraph(ScreenState)
    graph.add_node("screen", screen)
    graph.add_edge(START, "screen")
    graph.add_edge("screen", END)
    return graph.compile()


def build_production_graph() -> Any:
    """The graph the registered handler runs, over the configured model."""
    # Imported here for the same reason as in `build_graph`: registration
    # loads the handler's name, and nothing it needs in order to run.
    from langchain_openai import ChatOpenAI

    return build_graph(ChatOpenAI(model="gpt-4o-mini"))


def _screen_refuses(comment: str) -> bool:
    """Whether the comment says *the screen* could not do its work.

    Deliberately narrower than a substring list. "cannot" and "unable to"
    appear in perfectly good comments about categories that cannot apply
    to a product, and vetoing on those would block the step on every pass
    for that product. So the subject is what is matched, not the verb.
    """
    return _SCREEN_REFUSES.search(comment) is not None


async def propose(
    *,
    product_name: str,
    categories: str | None,
    graph: Any | None = None,
) -> StepResolution:
    """Screen the product and say what it proposes for the step.

    `categories` is the step's description, carried through unaltered. A
    blank one is answered before a graph is built or a model is called: a
    screen with nothing to screen against has not found the product clear,
    it has not screened, and a model asked to screen against nothing would
    answer anyway.

    Awaited, because the graph it runs is async-only.
    """
    if _blank(product_name):
        reason = _no_product_reason()
        return StepResolution(outcome=Blocked(reason=reason), result=reason)

    if _blank(categories):
        reason = _no_categories_reason(product_name)
        return StepResolution(outcome=Blocked(reason=reason), result=reason)
    # Narrowed for the type checker by `_blank`, which `mypy` cannot see
    # through; the branch above is the only path where it is `None`.
    assert categories is not None

    # Annotated rather than inferred: `_graph()` answers `object`, so the
    # union of it with the injected graph has no `ainvoke` for the type
    # checker to see. A local annotation says what a compiled graph is
    # without reaching for a `cast` or an ignore at the call itself.
    running: Any = graph if graph is not None else _graph()
    state = await running.ainvoke(
        {"product_name": product_name, "categories": categories}
    )
    parsed = state.get("parsed")

    # Route 1: the structured call completed but validated against nothing.
    # Saying "flagged" or "clear" here would record a model omission on the
    # launch as the screen's own judgement about the product.
    if not isinstance(parsed, ScreenResponse):
        reason = _unreadable_reason(product_name)
        return StepResolution(
            outcome=Blocked(reason=reason),
            result=_render_shortfall(categories, reason),
        )

    comment = parsed.comment
    # Route 2: a verdict arrived, but with no comment to justify it. The
    # requirement says such a response is treated *exactly* as an
    # unreadable verdict, so it shares that route's reason rather than
    # getting a fourth of its own -- both are shortfalls in what the model
    # produced, and an operator reading the record should see one thing.
    #
    # Checked before the verdict is dispatched on: an implementation that
    # tested `clear` first would propose satisfaction on a bare verdict.
    if _blank(comment):
        reason = _unreadable_reason(product_name)
        return StepResolution(
            outcome=Blocked(reason=reason),
            result=_render_shortfall(categories, reason),
        )
    assert comment is not None

    if parsed.verdict == "clear":
        # Route 3: the one direction in which prose may still act. A clear
        # verdict whose own comment says the screen could not do its work
        # is the state the prohibition on "a satisfying outcome
        # accompanied by text admitting the question was not settled"
        # exists to forbid.
        if _screen_refuses(comment):
            return StepResolution(
                outcome=Blocked(reason=_contradiction_reason(product_name)),
                result=_render_contradiction(categories, comment),
            )
        return StepResolution(
            outcome=Satisfied,
            result=_render(categories, parsed.verdict, comment),
        )

    # Routes 4 and 5: flagged is a finding about the product, undetermined
    # a statement about what the screen was given. Two reasons, because
    # they are two different things that happened.
    reason = (
        _flagged_reason(product_name)
        if parsed.verdict == "flagged"
        else _undetermined_reason(product_name)
    )
    return StepResolution(
        outcome=Blocked(reason=reason),
        result=_render(categories, parsed.verdict, comment),
    )


@functools.lru_cache
def _graph() -> object:
    """Built on first use, never at import: constructing the model reads
    credentials, and importing this module must not require them."""
    return build_production_graph()


@register_step_handler(HANDLER_NAME)
async def screen_for_compliance(context: StepContext) -> StepResolution:
    """Screen the product, or say why no verdict was reached.

    Reads only what the context carries — the product the pass resolved
    and the step it is resolving, never a catalog or a playbook of its
    own. A model failure propagates, and the pass records nothing for a
    step it could not evaluate.

    **Nothing here tests which step invoked it.** Which step this screen
    runs for is a property of the authored playbook, not of this code, so
    the identifier, discipline and gate it was given are all read past.
    The step's `description` is the one thing inspected, and only because
    it is the input.
    """
    product = context.product
    # Read through the value, not over the object carrying it. `str()` on a
    # value object yields its repr, so a screen doing that would ask the
    # model about a product named `Sku(value='HZM-2027-01')` -- and would
    # record that non-existent product in the reason the launch keeps. The
    # failure is silent: the model answers plausibly whatever it was asked.
    # `name` is a plain `str` and needs no unwrapping, which is why it is
    # the only value passed on.
    name = getattr(product, "name", "")
    return await propose(
        product_name=str(getattr(name, "value", name)),
        categories=context.step.description,
    )
