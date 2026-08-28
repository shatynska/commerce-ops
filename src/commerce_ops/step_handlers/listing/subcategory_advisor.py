"""The sub-category advisor: its graph, and its registration as a handler.

`subcategory-advisor`: given a product's name and its marketplace, propose
the Amazon sub-category node it belongs in and name the compliance fields
and certifications that node then demands — the work `lp.listing.007`
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

A model failure, and a response whose content is not a plain string, both
surface. A masked failure here would not merely return a poor answer — it
would reach a person as a recommendation to accept and become the evidence
for a compliance-relevant decision.

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
from typing import TYPE_CHECKING, Any, TypedDict

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
    "AdvisorState",
    "NonStringRecommendationError",
    "Proposal",
    "advise_sub_category",
    "build_graph",
    "build_production_graph",
    "propose",
]

HANDLER_NAME = "listing.subcategory_advisor"

#: The two values the verdict may carry. Anything else — including a
#: verdict the model never reported — is not support, which is the
#: fail-safe direction: a supported result wrongly withheld costs a pass,
#: while an unsupported one wrongly accepted puts a false terminal
#: outcome in front of a person.
SUPPORTED = "supported"
UNSUPPORTED = "unsupported"

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

Name the sub-category node this product belongs in, expressed as the full
path from the top-level category down. Then name the compliance fields and
certifications that node demands. Then name the alternative node a reader
would most plausibly have chosen instead, and why this one was preferred.

If the category structure gives you no confident answer for this product
and marketplace, say plainly that you cannot support a node choice, and do
not name a node as though it were supported.

Begin your answer with a single line reading exactly `Verdict: supported`
or `Verdict: unsupported`, then a blank line, then the answer itself. The
verdict line is read by the system; everything after it is read by a
person, so state a refusal there in your own words as well.
"""

#: Reads the verdict line the prompt asks for and takes it off the front
#: of the recommendation, so the prose a person reads carries no machine
#: scaffolding. A missing line yields `None` -- not a default -- because
#: "never reported" and "reported as something unrecognised" are
#: different facts the caller has to be able to tell apart.
_VERDICT_LINE = re.compile(
    r"^[ \t]*verdict[ \t]*:[ \t]*(?P<value>[^\r\n]*)", re.IGNORECASE
)


def _split_verdict(content: str) -> tuple[str | None, str]:
    """The verdict the model reported, and the recommendation without it."""
    match = _VERDICT_LINE.match(content)
    if match is None:
        return None, content
    verdict = match.group("value").strip()
    prose = content[match.end() :].lstrip("\r\n")
    # A `Verdict:` line with nothing after it reported no verdict at all.
    return (verdict or None), prose


class AdvisorState(TypedDict, total=False):
    """The graph's state: what it is given, and what it produced."""

    product_name: str
    marketplace: str
    recommendation: str
    #: Whether the advisor could support a node choice, as its own value
    #: rather than something read back out of `recommendation`. Absent is
    #: a state the fail-safe answers, which is why this is not defaulted.
    verdict: str


class NonStringRecommendationError(Exception):
    """The model answered with content that is not a plain string.

    Named rather than coerced, following `omni_agent`'s
    `NonStringAnswerError` precedent for the same words: a `str(...)` of a
    content block list is a fabricated recommendation, which is exactly
    what the requirement forbids.
    """


@dataclass(frozen=True, slots=True)
class Proposal:
    """What the advisor hands the runtime: an outcome and the text."""

    outcome: Any
    result: str


def build_graph(model: BaseChatModel) -> Any:
    """The graph over an injected model — the testable seam."""
    # Imported here, not at module scope: registering this handler must not
    # load what running it needs (`launch-step-automation`). `recommend` is
    # nested below, so its closure carries `HumanMessage` and the import runs
    # once per graph rather than once per invocation.
    from langchain_core.messages import HumanMessage
    from langgraph.graph import END, START, StateGraph

    def recommend(state: AdvisorState) -> dict[str, str]:
        prompt = _PROMPT.format(
            product_name=state.get("product_name", ""),
            marketplace=state.get("marketplace", ""),
        )
        # No `try` around this: a model that is unavailable or errors must
        # surface, not become a recommendation.
        response = model.invoke([HumanMessage(content=prompt)])
        content = response.content
        if not isinstance(content, str):
            raise NonStringRecommendationError(
                "the language model answered with content that is not a "
                f"plain string ({type(content).__name__}); refusing to "
                "build a recommendation from it"
            )
        verdict, prose = _split_verdict(content)
        # The verdict is omitted from the returned state when the model did
        # not give one, rather than defaulted: `propose` has to be able to
        # tell "not reported" from "reported as something unrecognised",
        # and a default would erase that distinction here.
        produced: dict[str, str] = {"recommendation": prose}
        if verdict is not None:
            produced["verdict"] = verdict
        return produced

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


def _advisor_refuses(recommendation: str) -> bool:
    """Whether the recommendation says *the advisor* cannot make a choice.

    Deliberately narrower than the substring list this change deletes.
    That list would also match a rejected alternative described as unable
    to support some particular demand -- a statement about that node, not
    about the advisor -- and vetoing on it would block the step on every
    pass for the product, since the same prompt yields the same shape.
    So the subject is what is matched, not the phrase.
    """
    return _ADVISOR_REFUSES.search(recommendation) is not None


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
    recommendation = state["recommendation"]

    # Read, never inferred. The verdict is the only thing that can
    # *establish* support; the prose below can only withhold it.
    reported = state.get("verdict")
    verdict = reported.strip().lower() if isinstance(reported, str) else None

    if verdict == SUPPORTED:
        # The one direction prose may act in. A verdict claiming support
        # while the recommendation refuses is the state the served
        # prohibition on "a satisfying one accompanied by text admitting
        # there is no answer" exists to forbid, and without this check
        # nothing would enforce it once the old matcher is gone.
        if _advisor_refuses(recommendation):
            return Proposal(
                outcome=Blocked(
                    reason=(
                        "the sub-category advisor reported a supporting "
                        "verdict that its own recommendation contradicts, so "
                        "the verdict and the prose disagree and no node "
                        f"choice was accepted for '{product_name}' on "
                        f"'{marketplace}'"
                    )
                ),
                result=recommendation,
            )
        return Proposal(outcome=Satisfied, result=recommendation)

    if verdict == UNSUPPORTED:
        # A classification considered and declined -- the only one of the
        # four withheld paths that is a finding about the product, and the
        # only one keeping this wording.
        return Proposal(
            outcome=Blocked(
                reason=(
                    "the sub-category advisor could not support a node "
                    f"choice for '{product_name}' on '{marketplace}'"
                )
            ),
            result=recommendation,
        )

    if reported is None:
        # A shortfall, not a finding. Saying "could not support a node
        # choice" here would record a model omission on the launch as the
        # advisor's judgement about the product.
        return Proposal(
            outcome=Blocked(
                reason=(
                    "the sub-category advisor reported no verdict for "
                    f"'{product_name}' on '{marketplace}', so whether a node "
                    "choice could be supported is unknown rather than settled"
                )
            ),
            result=recommendation,
        )

    # Reported, but as neither value. Distinct from absence, and the
    # offending value is named: an operator cannot act on "unreadable".
    return Proposal(
        outcome=Blocked(
            reason=(
                "the sub-category advisor reported the unrecognised verdict "
                f"'{reported}' for '{product_name}' on '{marketplace}', which "
                "is neither supported nor unsupported"
            )
        ),
        result=recommendation,
    )


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
    return StepResolution(outcome=proposal.outcome, result=proposal.result)
