"""What the screen screens against, and what it says it screened against
(`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from the ADDED requirement *The screen is performed against the
categories the step itself names*, all four of its scenarios:

- The step's description is what the product is tested against
- The produced text cites what was screened against
- An edited description changes what is screened
- A step naming no categories is not a clear product

`tasks.md` 1.7 and 1.8. See `test-manifest.md` at the change root for the
full accounting of every scenario in the delta.

## Two assertions that must be able to fail independently

`tasks.md` 1.7 asks for two falsifying cases, and both are here because
without them the requirement is satisfiable by an implementation the delta
forbids:

1. **The citation is rendered by the screen, not taken from the model.**
   `test_the_citation_is_rendered_even_when_the_comment_names_nothing`
   scripts a comment naming no category at all and asserts the rendered
   text names them anyway. A test that only checked "the categories appear
   somewhere" passes an implementation that lets the model supply them —
   and such a citation could not be relied on, since the delta forbids code
   from inspecting the comment's content.
2. **The description's text is carried through, not parsed.**
   `test_both_halves_of_the_description_reach_the_prompt_and_the_citation`
   uses a description naming both a referenced list and a parenthetical of
   examples — the ordinary case — and asserts **both** halves reach the
   prompt and the citation. An extraction step would plausibly keep the
   parenthetical and drop the reference, understating what was screened
   while every assertion written against the parenthetical still passed.

## Level

The registered handler, invoked with a `StepContext`. Nothing below it can
observe these scenarios: the categories come from
`context.step.description`, and the fourth scenario is about the handler
declining to reach a model at all.

## What is fixed, and what is INVENTED

Fixed by the delta: that the categories are read from the step's
description as the served playbook holds it; that the produced text states
them as the screen read them; that the description's text is carried
through unaltered into both the prompt and the citation with nothing
extracted; and that an absent, empty or whitespace-only description
produces a non-terminal outcome, no satisfying outcome, and **no model
call**.

Fixed by `tasks.md` 2.2 and 2.7: `HANDLER_NAME`, `build_graph(model)`,
`build_production_graph()`.

INVENTED, recorded in `test-manifest.md`:

- The fakes and `_install_stub_graph`, duplicated per file as
  `subcategory_advisor`'s tests are.
- The wire model's class is captured at the call site rather than imported,
  so only the field names `verdict` and `comment` (`tasks.md` 2.3) are
  named here.
- `_REFUSING_FACTORY` as the way "makes no model call" is *established*
  rather than merely inferred from the outcome text.
- The re-authored description used for the third scenario.

## Expected first-run state

`commerce_ops.step_handlers.strategy.compliance_screen` does not exist, so
every test here is expected to fail on an absent target (`ImportError` at
collection) — failure state 2 per `ai-toolkit:testing`, establishing
absence only.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.strategy.compliance_screen as screen
from commerce_ops.launch.application import HANDLERS, StepContext
from commerce_ops.launch.domain.launch_playbook import (
    Blocked,
    Gate,
    Hazard,
    LaunchPlaybook,
    OffsetAnchor,
    Satisfied,
    Scope,
    StepDefinition,
    StepKind,
    StepStatus,
)
from commerce_ops.launch.domain.launch_run import Launch
from commerce_ops.shared.domain.discipline import Discipline
from commerce_ops.shared.domain.identity import MarketplaceId, ProductId, Sku
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import opening_for as _opening_for

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"

#: The seeded description of `lp.strategy.006`, verbatim from
#: `alembic/data/playbook_v1.yaml` — a *referenced list* and an inline
#: *parenthetical of examples* in one sentence, which is the ordinary case
#: the delta's carry-it-through requirement is written about.
DESCRIPTION: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)
#: The two halves an extraction step would separate. Named so that the
#: falsifying assertion reads as what it is.
REFERENCED_LIST: Final = "the FBA-prohibited hazmat list"
PARENTHETICAL_EXAMPLES: Final = (
    "(furniture, medical devices, supplements, grills, fire pits, balloons, "
    "lighters, CO detectors)"
)

#: INVENTED: a re-authored description naming a different set, for the
#: edited-description scenario. Narrower than the one above on purpose —
#: narrowing is the edit the delta's accepted consequence is about.
REAUTHORED_DESCRIPTION: Final = (
    "Screen against the aerosol and pressurised-container restrictions "
    "(spray paints, propane canisters, compressed air dusters) before "
    "sourcing"
)

CLEAR_COMMENT: Final = (
    "Considered each named heading: an untreated bamboo board carries no "
    "battery, no pressurised contents and nothing ingestible, so none "
    "applies."
)

#: DERIVED. A comment naming no category at all — the falsifying fixture
#: for a citation taken from the model's response rather than rendered by
#: the screen from what it read.
COMMENT_NAMING_NO_CATEGORIES: Final = (
    "Nothing about this item raises a concern under any of the headings considered."
)

FLAGGED_COMMENT: Final = "This falls under one of the named headings."
UNDETERMINED_COMMENT: Final = "The name alone does not settle this."


# ---------------------------------------------------------------------------
# Scripting the model's structured answer
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids."""


@dataclass(frozen=True)
class _Answer:
    verdict: str
    comment: str | None
    #: Added by `screen-for-hazard-categories`, which gave the wire schema a
    #: third field. Without it every `flagged` row here scripted an empty
    #: `categories` and so routed to the flagged-naming-nothing shortfall
    #: rather than to the flagged route -- silently, because both renderers
    #: cite the description and the assertion below only checks the
    #: citation. The row went on passing while covering a different route
    #: from the one it names.
    categories: tuple[str, ...] = ()


class _ScriptedStructuredRunnable:
    def __init__(self, script: _Answer, schema: Any) -> None:
        self._script = script
        self._schema = schema
        self.received: list[Any] = []

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # `design.md` Context 2's model-level guard: the compiled graph is
        # async-only, so a screen reaching the model synchronously fails
        # here rather than pinning the invoking loop while passing every
        # assertion about what it produced.
        raise _WrongSeam(
            "the screen reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)`"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._schema(
                verdict=self._script.verdict,
                comment=self._script.comment,
                categories=list(self._script.categories),
            ),
            "parsing_error": None,
        }


class _ScriptedStructuredChatModel(BaseChatModel):
    script: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]

    def __init__(self, script: _Answer) -> None:
        super().__init__()
        object.__setattr__(self, "script", script)
        object.__setattr__(self, "runnable", None)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise _WrongSeam(
            "the screen called the model directly instead of through "
            "`with_structured_output(...)`"
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise _WrongSeam("the screen bound tools to its model")

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        runnable = _ScriptedStructuredRunnable(self.script, schema)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-structured-fake-chat-model"


class _RefusingChatModel(BaseChatModel):
    """A model that answers nothing at all.

    Used with `_REFUSING_FACTORY` for the fourth scenario: between them,
    any attempt to build a graph or to reach a model raises rather than
    quietly answering.
    """

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise _WrongSeam("the screen called a model for a step naming no categories")

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        raise _WrongSeam(
            "the screen constructed a structured-output call for a step "
            "naming no categories"
        )

    @property
    def _llm_type(self) -> str:
        return "refusing-fake-chat-model"


# ---------------------------------------------------------------------------
# Putting the stub behind the registered handler
# ---------------------------------------------------------------------------


def _clear_graph_caches() -> None:
    """Drop any `lru_cache`d graph the screen holds (`tasks.md` 2.7)."""
    for value in vars(screen).values():
        clear = getattr(value, "cache_clear", None)
        if callable(clear):
            clear()


@pytest.fixture(autouse=True)
def _fresh_graph() -> Any:
    _clear_graph_caches()
    yield
    _clear_graph_caches()


def _install_stub_graph(
    monkeypatch: pytest.MonkeyPatch, model: BaseChatModel
) -> list[str]:
    built: list[str] = []

    def factory() -> Any:
        built.append("built")
        return screen.build_graph(model)

    # Cleared on every install, not only once per test: several tests below
    # invoke the screen twice, and a cached graph would let the first
    # invocation's stubbed model answer the second.
    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)
    return built


def _install_refusing_factory(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make building a graph at all an error.

    `tasks.md` 2.4: the early return for a step naming no categories is the
    requirement, not an optimisation — "before constructing a graph or
    calling a model". A factory that raises is how that is established
    rather than inferred from the outcome text, which an implementation
    that prompted with an empty list would produce by accident.
    """
    attempts: list[str] = []

    def factory() -> Any:
        attempts.append("built")
        raise _WrongSeam(
            "the screen built its graph for a step naming no categories; "
            "the outcome is required to be reached before any graph is "
            "constructed or any model called"
        )

    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)
    return attempts


# ---------------------------------------------------------------------------
# The context the handler is invoked with
# ---------------------------------------------------------------------------

STEP_ID: Final = "lp.strategy.006"
ALICE: Final = "prs_01HQ8Z6M4A"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))


class _CatalogProduct:
    def __init__(self, name: str = PRODUCT_NAME) -> None:
        self.id = PRODUCT_ID
        self.name = name
        self.sku = Sku("HZM-2027-01")
        self.marketplace_id = MarketplaceId("ATVPDKIKX0DER")
        self.sub_category: str | None = None


def _gates() -> tuple[Gate, ...]:
    return tuple(
        Gate(identifier=identifier, position=position, opening=_opening_for(identifier))
        for position, identifier in enumerate(SPECIFIED_GATE_ORDER, start=1)
    )


def _step(**overrides: Any) -> StepDefinition:
    attributes: dict[str, Any] = {
        "identifier": STEP_ID,
        "name": "Screen for prohibited and high-compliance categories",
        "description": DESCRIPTION,
        "gate": "commit",
        "discipline": Discipline.STRATEGY,
        "scope": Scope.PRODUCT,
        "timing_anchor": OffsetAnchor(days=-90),
        "blocking": False,
        "kind": StepKind.AUTOMATED,
        "confirmer": ALICE,
        "status": StepStatus.ACTIVE,
        "hazard": Hazard.NONE,
        "assignees": (),
        "handler": "strategy.compliance_screen",
        "provenance": None,
    }
    attributes.update(overrides)
    return StepDefinition(**attributes)


def _hold(gate: str) -> StepDefinition:
    return _step(
        identifier=f"hold.{gate}",
        name=f"Blocking work holding the {gate} gate",
        description=None,
        gate=gate,
        blocking=True,
        kind=StepKind.HUMAN,
        assignees=(ALICE,),
        confirmer=None,
        handler=None,
    )


def _launch() -> Launch:
    playbook = LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=(_step(), *(_hold(gate) for gate in SPECIFIED_GATE_ORDER)),
    )
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return launch


def _context(**step_overrides: Any) -> StepContext:
    return StepContext(
        step=_step(**step_overrides),
        launch=_launch(),
        product=_CatalogProduct(),
        as_of=AS_OF,
    )


def _handler() -> Any:
    handler = HANDLERS.resolve(screen.HANDLER_NAME)
    assert handler is not None, (
        f"no step handler is registered under {screen.HANDLER_NAME!r}"
    )
    return handler


def _prompt_text(model: _ScriptedStructuredChatModel) -> str:
    """Everything the screen put in front of the model, as one string."""
    runnable = model.runnable
    assert runnable is not None and runnable.received, (
        "the screen never reached the model, so there is no prompt to read"
    )
    messages = runnable.received[-1]
    if isinstance(messages, list | tuple):
        return "\n".join(str(getattr(item, "content", item)) for item in messages)
    return str(getattr(messages, "content", messages))


async def _screen_with(
    script: _Answer,
    monkeypatch: pytest.MonkeyPatch,
    **step_overrides: Any,
) -> tuple[Any, _ScriptedStructuredChatModel]:
    model = _ScriptedStructuredChatModel(script)
    _install_stub_graph(monkeypatch, model)
    resolution = await _handler()(_context(**step_overrides))
    return resolution, model


def _text(resolution: Any) -> str:
    text = getattr(resolution, "result", None)
    assert isinstance(text, str), (
        f"the screen's resolution carries no produced text: {resolution!r}"
    )
    return text


def _reason(resolution: Any) -> str:
    outcome = getattr(resolution, "outcome", None)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    assert isinstance(outcome.reason, str) and outcome.reason.strip()
    return outcome.reason


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Scenario: The step's description is what the product is tested against
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_steps_description_is_what_the_product_is_tested_against(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The step's description is what the product is tested
    against.

    WHEN the screen resolves a step whose description names a set of
    prohibited and high-compliance categories
    THEN the judgement it produces is made against those categories.

    SPECIFIED: what the model is asked is the observable form of "the
    judgement is made against those categories" — the model is the thing
    making the judgement, and the description's text is what constrains it.
    The product's own name is asserted alongside, since a prompt carrying
    the categories but not the product would screen nothing.
    """
    _, model = await _screen_with(_Answer("clear", CLEAR_COMMENT), monkeypatch)
    prompt = _prompt_text(model)

    assert DESCRIPTION in prompt, (
        "the step's description does not reach the model, so the judgement "
        f"is not made against the categories the step names: {prompt!r}"
    )
    assert PRODUCT_NAME in prompt, (
        f"the product the screen was invoked for does not reach the model: {prompt!r}"
    )


@pytest.mark.anyio
async def test_both_halves_of_the_description_reach_the_prompt_and_the_citation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario, and *The produced text cites what was screened
    against*, asserted in the direction an extraction step would fail.

    Requirement statement: "The screen SHALL carry the description's text
    through unaltered — into what it asks the model and into what it cites
    — and SHALL extract nothing from it."

    SPECIFIED. The description names both a referenced list and an inline
    parenthetical of examples. A parser keeps what matches its shape and
    drops the rest, so an implementation extracting a category list would
    cite the parenthetical alone — understating what was screened while
    every assertion written against those eight items still passed. Both
    halves are asserted separately from the whole string so that a failure
    says which half was lost.
    """
    resolution, model = await _screen_with(_Answer("clear", CLEAR_COMMENT), monkeypatch)
    prompt = _prompt_text(model)
    text = _text(resolution)

    assert REFERENCED_LIST in prompt, (
        f"the referenced list was dropped from the prompt: {prompt!r}"
    )
    assert PARENTHETICAL_EXAMPLES in prompt, (
        f"the parenthetical examples were dropped from the prompt: {prompt!r}"
    )
    assert REFERENCED_LIST in text, (
        f"the referenced list was dropped from the citation: {text!r}"
    )
    assert PARENTHETICAL_EXAMPLES in text, (
        f"the parenthetical examples were dropped from the citation: {text!r}"
    )
    assert DESCRIPTION in prompt and DESCRIPTION in text, (
        "the description's text was not carried through unaltered into both "
        f"the prompt and the citation.\nprompt: {prompt!r}\ntext: {text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: The produced text cites what was screened against
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("verdict", "comment", "categories"),
    [
        ("clear", CLEAR_COMMENT, ()),
        ("flagged", FLAGGED_COMMENT, ("supplements",)),
        ("undetermined", UNDETERMINED_COMMENT, ()),
    ],
)
async def test_the_produced_text_cites_what_was_screened_against(
    verdict: str,
    comment: str,
    categories: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The produced text cites what was screened against.

    WHEN the screen produces text for any verdict it reaches after reading
    a step's description
    THEN that text states the categories the screen read from that
    description.

    SPECIFIED, for **any** verdict — an implementation citing on the
    satisfying route alone would pass a single-row test while leaving a
    narrowed screen untraceable on every launch it flagged or could not
    settle.
    """
    resolution, _ = await _screen_with(_Answer(verdict, comment), monkeypatch)

    assert DESCRIPTION in _text(resolution), (
        f"the text produced for a {verdict!r} verdict does not cite the "
        f"categories the screen read: {_text(resolution)!r}"
    )


@pytest.mark.anyio
async def test_the_citation_is_rendered_even_when_the_comment_names_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario's second clause: "rendered from what the screen
    read rather than taken from the model's response".

    SPECIFIED, and this is the falsifying case `tasks.md` 1.7 asks for.
    The scripted comment names no category at all, so the only place the
    rendered text can have got them is the screen's own reading of the
    description. A test that merely checked "the categories appear
    somewhere" passes an implementation that leaves the citation to the
    model — and the delta forbids code from inspecting the comment's
    content, so such a citation is one nothing can rely on and nothing can
    assert.
    """
    resolution, _ = await _screen_with(
        _Answer("clear", COMMENT_NAMING_NO_CATEGORIES), monkeypatch
    )
    text = _text(resolution)

    assert COMMENT_NAMING_NO_CATEGORIES in text, (
        f"the model's comment did not reach the reader at all: {text!r}"
    )
    assert DESCRIPTION in text, (
        "the rendered text cites no categories though the screen read a "
        "description naming them — the citation is being taken from the "
        f"model's comment rather than rendered by the screen: {text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: An edited description changes what is screened
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_an_edited_description_changes_what_is_screened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An edited description changes what is screened.

    WHEN the step's description is re-authored to name a different set of
    categories, and the screen runs again
    THEN the product is tested against the newly authored categories, and
    the text produced cites the newly authored categories, without any
    change to the screening code.

    SPECIFIED: both the prompt and the citation track the edit, and the
    superseded text is gone from both rather than merely accompanied by the
    new one — a screen holding a list of its own would keep naming it.
    "Without any change to the screening code" is what this file's two
    invocations establish: the same registered handler, the same module,
    two different descriptions.
    """
    first, first_model = await _screen_with(
        _Answer("clear", CLEAR_COMMENT), monkeypatch
    )
    second, second_model = await _screen_with(
        _Answer("clear", CLEAR_COMMENT),
        monkeypatch,
        description=REAUTHORED_DESCRIPTION,
    )

    assert DESCRIPTION in _prompt_text(first_model)
    assert DESCRIPTION in _text(first)

    second_prompt = _prompt_text(second_model)
    second_text = _text(second)
    assert REAUTHORED_DESCRIPTION in second_prompt, (
        f"the re-authored description does not reach the model: {second_prompt!r}"
    )
    assert REAUTHORED_DESCRIPTION in second_text, (
        f"the produced text does not cite the re-authored categories: {second_text!r}"
    )
    assert DESCRIPTION not in second_prompt, (
        "the superseded description still reaches the model, so the screen "
        f"is not reading the step it was given: {second_prompt!r}"
    )
    assert DESCRIPTION not in second_text, (
        f"the produced text still cites the superseded categories: {second_text!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A step naming no categories is not a clear product
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("description", [None, "", "   ", "\n\t\n"])
async def test_a_step_naming_no_categories_is_not_a_clear_product(
    description: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A step naming no categories is not a clear product.

    WHEN the screen resolves a step that carries no description, or one
    that is empty or whitespace-only
    THEN it proposes a non-terminal outcome whose reason states that the
    step names no categories to screen against, proposes no satisfying
    outcome, and makes no model call.

    SPECIFIED: all three halves. **The absence of the call is asserted, not
    only the outcome** (`tasks.md` 1.8): an implementation that prompts
    with an empty list and lets the model answer produces the same outcome
    text by accident, and that is the failure the requirement forbids —
    "a model asked to screen against nothing would answer anyway".
    Establishing it needs a graph factory that raises, since a screen with
    no description reaches no model whose call could be counted.

    DERIVED: the keyword set standing in for "states that the step names no
    categories to screen against"; no artifact fixes the wording.
    """
    attempts = _install_refusing_factory(monkeypatch)

    resolution = await _handler()(_context(description=description))

    assert attempts == [], (
        "the screen built a graph for a step naming no categories; the "
        "outcome must be reached before a graph is constructed or a model "
        "called"
    )
    assert getattr(resolution, "outcome", None) is not Satisfied, (
        "a step naming no categories proposed the step's satisfying "
        f"outcome: {resolution!r}"
    )
    reason = _reason(resolution)
    lowered = reason.lower()
    assert any(
        phrase in lowered
        for phrase in (
            "no categories",
            "no category",
            "names none",
            "nothing to screen",
        )
    ), f"the reason does not state that the step names no categories: {reason!r}"


@pytest.mark.anyio
async def test_a_step_naming_no_categories_falls_back_to_no_list_of_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario's "SHALL NOT fall back to any list of its own".

    SPECIFIED. Asserted against the produced text: a screen with a hard-
    coded list would have something to cite, and the seeded description's
    own words are the list such an implementation would most plausibly
    carry. The absence of a model call, asserted above, closes the other
    route.
    """
    _install_refusing_factory(monkeypatch)

    resolution = await _handler()(_context(description=None))
    text = _text(resolution)

    for token in ("hazmat", "supplements", "fire pits", "CO detectors"):
        assert token.lower() not in text.lower(), (
            "the screen cited a category for a step that named none, so it "
            f"is carrying a list of its own: {text!r}"
        )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That an admin editing the description through `playbook-authoring` is
#   what changes the served step. That is `playbook-authoring`'s own
#   requirement and its own tests; this file establishes only that the
#   screen reads whatever the served step carries.
# - Whether the model actually confines its judgement to the categories the
#   description names. A quality property of the response, not of the
#   screen; `tasks.md` 4.5-4.6 gate it on live verification.
# ---------------------------------------------------------------------------
