"""The compliance screen's verdict table, and what routes it
(`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from four ADDED requirements, eleven scenarios:

*A verdict distinguishes clear, flagged and undetermined*
- A verdict is read from the discriminant, not the prose
- A comment's content is never checked by code
- A verdict's comment reaches the reader
- A verdict with an empty comment is treated as unreadable

*Satisfaction is proposed only for a clear verdict*
- A clear verdict proposes satisfaction
- A flagged verdict proposes a non-terminal outcome
- An undetermined verdict proposes a non-terminal outcome
- An unreadable verdict is not reported as a judgement about the product

*A verdict its own response contradicts is not satisfaction*
- A clear verdict carrying a stated inability is refused
- A statement about a category does not withhold satisfaction

*The structured-output schema is one the model provider's adapter accepts*
- Every wire combination has a defined destination (the table below is
  that requirement's behavioural half; its schema-shaped scenarios are in
  `tests/unit/step_handlers/strategy/test_compliance_screen_schema_conversion.py`)

`tasks.md` 1.3, 1.4, 1.5 and 1.6. See `test-manifest.md` at the change
root for the full accounting of every scenario in the delta.

## Level

The registered handler, invoked with a `StepContext` — the smallest unit
that can observe these scenarios, because the categories the screen tests
against are read from `context.step.description` and the citation is
rendered from the same text. A level below the handler could observe the
routing but not what it was routed against.

The stubbed model is reached by pointing `build_production_graph` at a
graph over it (`_install_stub_graph`), which is the seam `design.md`'s
*Graph, registration and imports mirror the advisor exactly* fixes:
`build_graph(model)` / `build_production_graph()`, with the production
graph `lru_cache`d. The cache is cleared around every test, so one test's
stub never answers the next.

## What is fixed, and what is INVENTED

Fixed by the delta: the three verdicts and their names; that satisfaction
is proposed only for `clear` with a non-blank comment; that a flagged, an
undetermined, an unreadable verdict and a step naming no categories each
produce a **non-terminal** outcome with a **distinguishable** reason; that
the comment is carried into the text a member reads; that the comment's
content is never inspected by code; and that the contradiction veto fires
on a statement about the *screen's* ability, not about a category.

Fixed by `tasks.md` 2.3: the wire schema's two field names, `verdict` and
`comment`, and the three literal verdict values. The delta names the three
states but no field, so the field names trace to `tasks.md`.

Fixed by `tasks.md` 2.2 and 2.7: `HANDLER_NAME`, `build_graph(model)`,
`build_production_graph()`, `with_structured_output(..., include_raw=True)`.

Fixed by `design.md`'s Context: the compiled graph is async-only, so the
fake runnable's synchronous `invoke` raises rather than answering —
a screen reverted to the synchronous entry point fails here loudly instead
of pinning the loop while passing every assertion about what it produced.

INVENTED, recorded in `test-manifest.md`:

- `_ScriptedStructuredChatModel` / `_ScriptedStructuredRunnable`, and
  `_install_stub_graph` as the way a stubbed model is put behind the
  registered handler. Duplicated per file rather than shared, following
  `subcategory_advisor`'s existing separate-file convention and because
  `step_handlers/` grows no shared layer.
- **The wire model is never imported by name.** Its class is captured at
  the `with_structured_output(...)` call site and instantiated there, so
  this file invents no class name — only the two field names above, which
  `tasks.md` fixes.
- `Blocked` specifically as "a non-terminal outcome", narrower than the
  delta's own word: it is the only non-terminal outcome that can carry a
  reason, and every withheld scenario here requires one.
- The prose of every fixture comment, and the keyword sets each reason is
  matched against. The delta fixes what a reason must *state*, never its
  wording; the keyword sets are DERIVED and are marked at each use. The
  assertion that the three reasons are *distinct* is SPECIFIED and is
  asserted separately, so a wording change does not silently take the
  distinctness check with it.

## Expected first-run state

`commerce_ops.step_handlers.strategy.compliance_screen` does not exist, so
every test here is expected to fail on an absent target (`ImportError` at
collection). Per `ai-toolkit:testing` that is failure state 2 and
establishes absence only — none of the assertions below will have run.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
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
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from tests.support.fixtures import ALICE, LAUNCH_DATE, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

# ---------------------------------------------------------------------------
# Fixtures of content
# ---------------------------------------------------------------------------

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"

#: The seeded description of `lp.strategy.006`, verbatim from
#: `alembic/data/playbook_v1.yaml`. Used rather than invented prose because
#: it is the ordinary case the delta describes — a *referenced list* and an
#: *inline parenthetical of examples* in one sentence.
DESCRIPTION: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)

CLEAR_COMMENT: Final = (
    "Considered the hazmat headings and each named category: this is an "
    "untreated bamboo board with no battery, no pressurised contents and "
    "nothing ingestible, so none of them applies."
)
FLAGGED_COMMENT: Final = (
    "This falls under supplements: the listing is an ingestible product, "
    "which Amazon gates behind a supplement compliance review before it may "
    "be sold."
)
#: A category for the flagged rows below. `screen-for-hazard-categories`
#: narrows *A flagged verdict proposes a non-terminal outcome* to a response
#: naming at least one category, so a flagged row scripting none no longer
#: reaches the flagged route at all. Every row here that means "flagged"
#: names one; the naming-nothing route has its own tests in
#: `test_compliance_screen_hazard_finding.py`.
FLAGGED_CATEGORIES: Final = ("supplements",)

UNDETERMINED_COMMENT: Final = (
    "Whether this falls under the hazmat list turns on whether the unit "
    "contains a lithium battery, which the product name does not say."
)

#: DERIVED. A `flagged` verdict whose prose reads reassuring, so that
#: routing which searched the comment instead of the discriminant would
#: propose satisfaction here. Deliberately free of any word a naive matcher
#: could key on as a flag.
REASSURING_COMMENT_UNDER_A_FLAG: Final = (
    "Nothing here looks out of the ordinary; it reads as a plain household "
    "item and I see nothing that would give a reviewer pause."
)

#: DERIVED. An `undetermined` verdict whose prose reads as a clean bill of
#: health — the same probe in the other direction.
CLEAN_SOUNDING_COMMENT_UNDER_UNDETERMINED: Final = (
    "On the face of it this is an ordinary kitchen product and none of the "
    "named categories obviously applies to it."
)

#: DERIVED. A comment that omits everything the prompt asks a clear verdict
#: to state — no categories considered, no reasoning. Routing must be
#: unaffected, since detecting the omission would mean parsing prose.
CONTENTLESS_CLEAR_COMMENT: Final = "Fine."

#: DERIVED. A flagged comment naming no category, for the same reason.
CONTENTLESS_FLAGGED_COMMENT: Final = "Not suitable."

#: DERIVED. A statement about the *screen's own* ability to screen, under a
#: `clear` verdict — the state the veto exists for. Realistic prose rather
#: than a keyword, so that passing is evidence about the requirement rather
#: than about a word list.
SCREEN_REFUSES_IN_COMMENT: Final = (
    "On reflection I cannot screen this product properly without knowing "
    "whether the unit contains a lithium battery or a pressurised cell."
)

#: DERIVED. A statement about a *category*, under a `clear` verdict — the
#: boundary case the veto must not fire on. Without it the veto can be
#: implemented as a phrase list that blocks the step on every pass for this
#: product, since the same prompt yields the same shape.
CATEGORY_CALLED_INAPPLICABLE: Final = (
    "Supplements cannot apply to this product at all, since nothing about "
    "it is ingestible; the medical-devices heading is unable to reach a "
    "cutting board either. None of the named categories applies."
)


# ---------------------------------------------------------------------------
# Scripting the model's structured answer
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids.

    A distinct type so that a test asserting "the screen raised" can tell a
    fault the screen surfaced from a fault in how it reached the model.
    """


@dataclass(frozen=True)
class _Answer:
    """A wire response to script, by field rather than by class.

    The wire model's class name is deliberately not imported: the runnable
    instantiates whatever class the screen handed to
    `with_structured_output(...)`, so this file names only the field names
    `tasks.md` fixes -- `verdict` and `comment` from 2.3, and `categories`
    from `screen-for-hazard-categories`'s 4.1.

    `categories` defaults to none named, which is what every scenario in
    this file scripted before that field existed. Where a test needs a
    flagged verdict to route *as flagged*, it now names one: a flagged
    verdict naming no category reaches its own route, because a response
    asserting a flag while naming nothing has established no fact.
    """

    verdict: str
    comment: str | None
    categories: tuple[str, ...] = ()


#: Script value meaning "the structured call completed and validated
#: against nothing" — `parsed` is `None` and a parsing error accompanies it.
_NO_PARSE: Final = object()


class _ScriptedStructuredRunnable:
    def __init__(self, script: Any, schema: Any) -> None:
        self._script = script
        self._schema = schema
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        if self._script is _NO_PARSE:
            return {
                "raw": AIMessage(content="not a recognisable verdict"),
                "parsed": None,
                "parsing_error": ValueError("could not validate against the schema"),
            }
        assert isinstance(self._script, _Answer)
        parsed = self._schema(
            verdict=self._script.verdict,
            comment=self._script.comment,
            categories=list(self._script.categories),
        )
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": parsed,
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # `design.md`, Context 2 (`await-the-subcategory-advisors-graph`):
        # both entry points are real on a structured-output runnable, so a
        # screening node reverted to `structured.invoke(...)` inside an
        # `async def` would work, pin the invoking loop for the whole
        # round-trip, and satisfy every assertion in this file about what
        # the screen produced. It fails here instead, naming the mistake.
        raise _WrongSeam(
            "the screen reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)` — "
            "the enclosing coroutine then never yields, and the invoking "
            "loop is pinned for the whole of the round-trip"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
    """Answers the `with_structured_output(...)` seam and nothing else."""

    script: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]
    requested_schema: ClassVar[Any]
    requested_include_raw: ClassVar[Any]

    def __init__(self, script: Any) -> None:
        super().__init__()
        object.__setattr__(self, "script", script)
        object.__setattr__(self, "runnable", None)
        object.__setattr__(self, "requested_schema", None)
        object.__setattr__(self, "requested_include_raw", None)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise _WrongSeam(
            "the screen called the model directly instead of through "
            "`with_structured_output(...)` — this fake only answers that seam"
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise _WrongSeam("the screen bound tools to its model")

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        object.__setattr__(self, "requested_schema", schema)
        object.__setattr__(self, "requested_include_raw", include_raw)
        runnable = _ScriptedStructuredRunnable(self.script, schema)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-structured-fake-chat-model"


# ---------------------------------------------------------------------------
# Putting the stub behind the registered handler
# ---------------------------------------------------------------------------


def _clear_graph_caches() -> None:
    """Drop any `lru_cache`d graph the screen holds.

    `tasks.md` 2.7 caches the production graph, so without this one test's
    stubbed model would answer the next.
    """
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
    """Point the screen's production-graph factory at a graph over `model`.

    Returns the list the factory appends to, so a test can assert whether a
    graph was built at all.
    """
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


# ---------------------------------------------------------------------------
# The context the handler is invoked with
# ---------------------------------------------------------------------------

STEP_ID: Final = "lp.strategy.006"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
PRODUCT_ID: Final = product_id()


class _CatalogProduct:
    """Stands in for the catalog product the pass supplies.

    A plain class, not a dataclass: `catalog.domain.product.Product` is one
    too, so stringifying it yields `<... object at 0x...>` here exactly as
    it would in production. `sku` and `marketplace_id` are the real value
    objects, so an implementation reaching for `!r` leaks a real rendering.
    """

    def __init__(self, name: str = PRODUCT_NAME) -> None:
        self.id = PRODUCT_ID
        self.name = name
        self.sku = Sku("HZM-2027-01")
        self.marketplace_id = MarketplaceId("ATVPDKIKX0DER")
        self.sub_category: str | None = None


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
        f"no step handler is registered under {screen.HANDLER_NAME!r}; "
        "importing the module is what registers it "
        "(`@register_step_handler`, `tasks.md` 2.11)"
    )
    return handler


async def _screen_with(
    script: Any,
    monkeypatch: pytest.MonkeyPatch,
    **step_overrides: Any,
) -> tuple[Any, _ScriptedStructuredChatModel]:
    """Run the registered handler over a scripted model answer."""
    model = _ScriptedStructuredChatModel(script)
    _install_stub_graph(monkeypatch, model)
    resolution = await _handler()(_context(**step_overrides))
    return resolution, model


# ---------------------------------------------------------------------------
# Reading a resolution
# ---------------------------------------------------------------------------


def _text(resolution: Any) -> str:
    text = getattr(resolution, "result", None)
    assert isinstance(text, str), (
        f"the screen's resolution carries no produced text: {resolution!r}"
    )
    return text


def _withheld(resolution: Any) -> Blocked:
    """A non-terminal outcome, and not a satisfying one.

    DERIVED, narrower than the delta's own word "non-terminal": `Blocked`
    is the only non-terminal outcome that can carry a reason, and every
    withheld scenario here requires one. A positive `isinstance` check
    already excludes `Satisfied`, which is a singleton value rather than a
    type.
    """
    outcome = getattr(resolution, "outcome", None)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome


def _reason(resolution: Any) -> str:
    reason = _withheld(resolution).reason
    assert isinstance(reason, str) and reason.strip(), (
        f"the screen's non-terminal outcome carries no reason: {resolution!r}"
    )
    return reason


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Requirement: Satisfaction is proposed only for a clear verdict
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_clear_verdict_proposes_satisfaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict proposes satisfaction.

    WHEN the screen's verdict is clear and its comment is neither empty nor
    whitespace-only
    THEN it proposes the step's satisfying outcome, carrying the cited
    categories, the verdict and the comment as the text a member reads.

    SPECIFIED: all four halves of the THEN — the outcome, and the three
    parts of the text.
    """
    resolution, _ = await _screen_with(
        _Answer(verdict="clear", comment=CLEAR_COMMENT), monkeypatch
    )

    assert getattr(resolution, "outcome", None) is Satisfied, (
        f"a clear verdict with a real comment did not propose the step's "
        f"satisfying outcome: {resolution!r}"
    )
    text = _text(resolution)
    assert DESCRIPTION in text, (
        "the text a member reads does not cite the categories the screen "
        f"screened against: {text!r}"
    )
    assert CLEAR_COMMENT in text, (
        f"the text a member reads does not carry the comment: {text!r}"
    )
    # DERIVED: the delta requires the verdict to be in the text but fixes no
    # wording for it, so the verdict's own name is what is looked for.
    assert "clear" in text.lower(), (
        f"the text a member reads does not state the verdict: {text!r}"
    )


@pytest.mark.anyio
async def test_a_flagged_verdict_proposes_a_non_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A flagged verdict proposes a non-terminal outcome.

    WHEN the screen's verdict is flagged and its response names at least
    one category
    THEN it proposes a non-terminal outcome whose reason names the product
    and states that the screen flagged it, and the text a member reads
    carries the comment.

    NARROWED by `screen-for-hazard-categories`, which modifies this
    scenario's WHEN: a flagged verdict naming *no* category now reaches its
    own route with its own reason, because a response asserting a flag
    while naming nothing has established no fact. The scenario keeps its
    name; only its condition narrowed. So this test now scripts a named
    category, and the un-named case is covered by
    `test_a_flagged_verdict_naming_nothing_is_not_recorded_as_flagged` in
    `test_compliance_screen_hazard_finding.py`. Nothing asserted below is
    weakened -- the reason keywords and the comment check are unchanged.

    SPECIFIED: that the reason **names the product** and **states the
    screen flagged it** — asserted rather than settling for "the outcome is
    non-terminal", because an implementation routing every non-clear
    verdict to one reason passes the weaker assertion while violating the
    requirement that the three reasons be distinguishable.

    DERIVED: the keyword set standing in for "states that the screen
    flagged it". No artifact fixes the wording.
    """
    resolution, _ = await _screen_with(
        _Answer(
            verdict="flagged",
            comment=FLAGGED_COMMENT,
            categories=("supplements",),
        ),
        monkeypatch,
    )

    reason = _reason(resolution)
    assert PRODUCT_NAME in reason, (
        f"the flagged reason does not name the product: {reason!r}"
    )
    assert "flag" in reason.lower(), (
        f"the flagged reason does not state that the screen flagged the "
        f"product: {reason!r}"
    )
    assert FLAGGED_COMMENT in _text(resolution), (
        f"the text a member reads does not carry the comment: {_text(resolution)!r}"
    )


@pytest.mark.anyio
async def test_an_undetermined_verdict_proposes_a_non_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An undetermined verdict proposes a non-terminal outcome.

    WHEN the screen's verdict is undetermined
    THEN it proposes a non-terminal outcome whose reason states that the
    screen could not settle the question from what it was given, and that
    reason differs from the one a flagged verdict produces.

    SPECIFIED: both halves, including the textual difference from the
    flagged reason. DERIVED: the keyword set below.
    """
    resolution, _ = await _screen_with(
        _Answer(verdict="undetermined", comment=UNDETERMINED_COMMENT), monkeypatch
    )
    flagged, _ = await _screen_with(
        _Answer(
            verdict="flagged",
            comment=FLAGGED_COMMENT,
            categories=("supplements",),
        ),
        monkeypatch,
    )

    reason = _reason(resolution)
    lowered = reason.lower()
    assert any(
        phrase in lowered
        for phrase in ("settle", "not settled", "could not determine", "undetermined")
    ), f"the undetermined reason does not say the question was not settled: {reason!r}"
    # No substring ban on "flag" here, for the reason given in
    # `test_an_unreadable_verdict_is_not_a_judgement_about_the_product`: a
    # legitimate undetermined reason may say "whether it should be flagged
    # could not be settled", which uses the word while denying the finding.
    # Distinctness from the flagged reason is what discriminates.
    assert reason != _reason(flagged), (
        "an undetermined verdict and a flagged verdict produced the same "
        "reason; the delta requires the three non-terminal reasons to be "
        f"distinguishable: {reason!r}"
    )


@pytest.mark.anyio
async def test_an_unreadable_verdict_is_not_a_judgement_about_the_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unreadable verdict is not reported as a judgement about
    the product.

    WHEN the screen's response validates against no verdict that can be
    read
    THEN it proposes a non-terminal outcome whose reason states that no
    verdict could be read, and that reason does not state that the product
    was flagged or that it is clear.

    SPECIFIED: the outcome, and what the reason states.

    The THEN's second clause — "does not state that the product was flagged
    or that it is clear" — is asserted as **distinctness from the two
    reasons that do state those things**, not as a ban on the substrings
    "flag" and "clear". A legitimate shortfall reason may well use both
    words while denying either: the sibling handler's own reads "whether a
    node choice could be supported is unknown rather than settled", and the
    same shape here would say "whether this product is clear of them is
    unknown", which states nothing about the product while containing the
    word. A substring ban would fail that implementation for using the
    right words, which is the wrong test to leave behind — the failure this
    scenario guards is a *shared* reason, and that is what is asserted.

    DERIVED: the keyword set standing in for "no verdict could be read".
    """
    resolution, _ = await _screen_with(_NO_PARSE, monkeypatch)
    flagged, _ = await _screen_with(
        _Answer(
            verdict="flagged",
            comment=FLAGGED_COMMENT,
            categories=("supplements",),
        ),
        monkeypatch,
    )
    undetermined, _ = await _screen_with(
        _Answer(verdict="undetermined", comment=UNDETERMINED_COMMENT), monkeypatch
    )

    reason = _reason(resolution)
    lowered = reason.lower()
    assert any(
        phrase in lowered
        for phrase in ("no verdict", "could not be read", "unreadable", "no readable")
    ), f"the reason does not state that no verdict could be read: {reason!r}"
    assert reason != _reason(flagged), (
        "a shortfall in what the model produced was recorded under the "
        f"reason that states the product was flagged: {reason!r}"
    )
    assert reason != _reason(undetermined), (
        "a shortfall in what the model produced was recorded under the "
        "reason that states the screen could not settle the question: "
        f"{reason!r}"
    )


@pytest.mark.anyio
async def test_the_three_non_terminal_reasons_are_textually_distinct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "The reasons SHALL be distinguishable from
    one another."

    SPECIFIED, and asserted separately from the three tests above so that
    editing a reason's wording cannot silently take the distinctness check
    with it. A flagged verdict is a finding about the product, an
    undetermined one a statement about what the screen was given, an
    unreadable one a shortfall in what the model produced — recording any
    under another's reason misstates what happened on the launch's own
    record.
    """
    flagged = _reason(
        (await _screen_with(_Answer("flagged", FLAGGED_COMMENT), monkeypatch))[0]
    )
    undetermined = _reason(
        (
            await _screen_with(
                _Answer("undetermined", UNDETERMINED_COMMENT), monkeypatch
            )
        )[0]
    )
    unreadable = _reason((await _screen_with(_NO_PARSE, monkeypatch))[0])

    reasons = {
        "flagged": flagged,
        "undetermined": undetermined,
        "unreadable": unreadable,
    }
    assert len(set(reasons.values())) == 3, (
        "the three non-terminal reasons are not distinguishable from one "
        f"another: {reasons!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: A verdict distinguishes clear, flagged and undetermined
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.parametrize("verdict", ["clear", "flagged", "undetermined"])
@pytest.mark.parametrize("comment", [None, "", "   ", "\n\t "])
async def test_a_verdict_with_an_empty_comment_is_treated_as_unreadable(
    verdict: str, comment: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A verdict with an empty comment is treated as unreadable.

    WHEN the screen's structured response carries a verdict but its comment
    is empty or whitespace-only
    THEN the screen proposes a non-terminal outcome, exactly as it would
    for an unreadable verdict.

    SPECIFIED: "exactly as" is read as the same reason, not merely as
    another non-terminal outcome — the requirement says such a response is
    "treated exactly as an unreadable verdict is treated".

    The `clear` row is the one an implementation checking the verdict
    before the comment gets wrong, which is why every verdict is covered
    rather than only the interesting-looking one. Whitespace-only is
    covered alongside `None` and `""` because under strict structured
    output every property is required, so a model with nothing to say emits
    a blank string rather than omitting the field.
    """
    resolution, _ = await _screen_with(_Answer(verdict, comment), monkeypatch)
    unreadable, _ = await _screen_with(_NO_PARSE, monkeypatch)

    assert getattr(resolution, "outcome", None) is not Satisfied, (
        f"a {verdict!r} verdict with a blank comment proposed satisfaction: "
        f"{resolution!r}"
    )
    assert _reason(resolution) == _reason(unreadable), (
        f"a {verdict!r} verdict with comment {comment!r} did not read as an "
        f"unreadable verdict: {_reason(resolution)!r} vs "
        f"{_reason(unreadable)!r}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("verdict", "comment"),
    [
        ("flagged", REASSURING_COMMENT_UNDER_A_FLAG),
        ("undetermined", CLEAN_SOUNDING_COMMENT_UNDER_UNDETERMINED),
    ],
)
async def test_a_verdict_is_read_from_the_discriminant_not_the_prose(
    verdict: str, comment: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A verdict is read from the discriminant, not the prose.

    WHEN the screen's structured response carries a verdict whose
    accompanying comment reads as though it says something else
    THEN the verdict acted on is the one the structured response carries,
    and the comment is never parsed to establish it.

    SPECIFIED. Both rows read as a clean bill of health in prose while
    carrying a non-clear discriminant, which is the direction that would
    cost a production run: an implementation searching the comment would
    propose satisfaction for either.
    """
    resolution, _ = await _screen_with(_Answer(verdict, comment), monkeypatch)

    assert getattr(resolution, "outcome", None) is not Satisfied, (
        f"a {verdict!r} verdict whose comment reads as reassuring was routed "
        f"on its prose rather than on its discriminant: {resolution!r}"
    )
    _withheld(resolution)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("verdict", "comment", "categories", "satisfies"),
    [
        ("clear", CONTENTLESS_CLEAR_COMMENT, (), True),
        ("flagged", CONTENTLESS_FLAGGED_COMMENT, FLAGGED_CATEGORIES, False),
        ("undetermined", CONTENTLESS_FLAGGED_COMMENT, (), False),
    ],
)
async def test_a_comments_content_is_never_checked_by_code(
    verdict: str,
    comment: str,
    categories: tuple[str, ...],
    satisfies: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A comment's content is never checked by code.

    WHEN the screen's structured response carries a verdict with a comment
    that is neither empty nor whitespace-only
    THEN the screen routes that verdict as the requirement states, whatever
    the comment's content is — including a comment that omits the
    categories considered, the categories flagged, or the settling fact the
    prompt asked for.

    SPECIFIED: each comment here omits everything the prompt obliges it to
    state, and routing must be unchanged. Detecting the omission would
    require parsing prose content, which this capability does not do.
    """
    resolution, _ = await _screen_with(
        _Answer(verdict, comment, categories), monkeypatch
    )

    if satisfies:
        assert getattr(resolution, "outcome", None) is Satisfied, (
            "a clear verdict was withheld because its comment omitted the "
            f"content the prompt asked for: {resolution!r}"
        )
    else:
        _withheld(resolution)
    assert comment in _text(resolution), (
        f"the text a member reads does not carry the comment: {_text(resolution)!r}"
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("verdict", "comment", "categories"),
    [
        ("clear", CLEAR_COMMENT, ()),
        ("flagged", FLAGGED_COMMENT, FLAGGED_CATEGORIES),
        ("undetermined", UNDETERMINED_COMMENT, ()),
        # A flagged verdict naming no category still *reaches a verdict*,
        # so this requirement binds on it exactly as on the three above:
        # `compliance-screen`'s *A verdict distinguishes clear, flagged and
        # undetermined* says every verdict's comment is carried into the
        # text a member reads, and `screen-for-hazard-categories` does not
        # modify that requirement. The route it takes is new, and code
        # review found it dropping the comment; without this row the suite
        # covered the requirement for every route but the one that got it
        # wrong. It matters most here, where the comment is the only
        # surviving account of a flag whose category the model failed to
        # name.
        ("flagged", FLAGGED_COMMENT, ()),
    ],
    ids=["clear", "flagged", "undetermined", "flagged-naming-nothing"],
)
async def test_a_verdicts_comment_reaches_the_reader(
    verdict: str,
    comment: str,
    categories: tuple[str, ...],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A verdict's comment reaches the reader.

    WHEN the screen reaches any verdict with a comment
    THEN that comment is carried into the text a member reads, alongside
    the verdict and the cited categories.

    SPECIFIED: all three parts, for every one of the three verdicts —
    the scenario says "any verdict", and an implementation carrying the
    comment on the satisfying route alone would pass a single-row test.
    """
    resolution, _ = await _screen_with(
        _Answer(verdict, comment, categories), monkeypatch
    )
    text = _text(resolution)

    assert comment in text, f"the comment does not reach the reader: {text!r}"
    assert DESCRIPTION in text, (
        f"the cited categories do not accompany the comment: {text!r}"
    )
    if categories or verdict != "flagged":
        # The naming-nothing route's text states what happened in a
        # sentence rather than echoing the bare verdict word, so this
        # clause is asserted for the rows it was written for. The comment
        # and citation clauses above are asserted for every row, which is
        # what this scenario is about.
        assert verdict in text.lower(), (
            f"the verdict does not accompany the comment: {text!r}"
        )


@pytest.mark.anyio
async def test_the_screen_asks_for_the_raw_response_alongside_the_parsed_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from `tasks.md` 2.7, not from a delta scenario.

    `with_structured_output(..., include_raw=True)` is what makes the
    "validated against nothing" state reachable as `parsed is None` rather
    than as a raised validation error, which is the state the
    unreadable-verdict route above is written against. Asserted here so
    that a screen dropping the flag fails by name rather than by every
    unreadable-verdict test failing for an unexplained reason.
    """
    _, model = await _screen_with(_Answer("clear", CLEAR_COMMENT), monkeypatch)

    assert model.requested_include_raw is True, (
        "the screen did not ask for the raw response alongside the parsed "
        f"one: include_raw={model.requested_include_raw!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: A verdict its own response contradicts is not satisfaction
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_clear_verdict_carrying_a_stated_inability_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict carrying a stated inability is refused.

    WHEN the screen's response reports a clear verdict while also stating
    that the screen could not screen the product
    THEN it proposes a non-terminal outcome, and the text a member reads
    carries the stated inability.

    SPECIFIED: both halves. The second is the one a weaker test drops — a
    rendering showing a bare "clear" would show the reader a judgement the
    response itself withheld.
    """
    resolution, _ = await _screen_with(
        _Answer("clear", SCREEN_REFUSES_IN_COMMENT), monkeypatch
    )

    _withheld(resolution)
    assert SCREEN_REFUSES_IN_COMMENT in _text(resolution), (
        "the text a member reads does not carry the stated inability, so a "
        f"reader sees a bare verdict the response withheld: {_text(resolution)!r}"
    )


@pytest.mark.anyio
async def test_a_statement_about_a_category_does_not_withhold_satisfaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A statement about a category does not withhold
    satisfaction.

    WHEN the screen's response reports a clear verdict whose comment states
    that a named category cannot apply to the product
    THEN it proposes the step's satisfying outcome, that being a statement
    about the category rather than about the screen's own ability to
    screen.

    SPECIFIED. Without this case the veto can be implemented as a phrase
    list ("cannot", "unable to") that blocks the step on every pass for
    this product, since the same prompt yields the same shape — which is
    why the fixture uses exactly those verbs about a category.
    """
    resolution, _ = await _screen_with(
        _Answer("clear", CATEGORY_CALLED_INAPPLICABLE), monkeypatch
    )

    assert getattr(resolution, "outcome", None) is Satisfied, (
        "a statement about a category that cannot apply was read as the "
        f"screen refusing to screen: {resolution!r}"
    )


@pytest.mark.anyio
async def test_a_vetoed_verdict_does_not_borrow_another_routes_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DERIVED from the requirement's own reasoning, not a `#### Scenario:`.

    *Satisfaction is proposed only for a clear verdict* requires each
    non-terminal reason to state which of the four things occurred.
    A vetoed contradiction is a fifth state; the delta does not say which
    reason it carries, so this asserts only that it is not silently
    recorded under the flagged reason — which would put "this product is a
    supplement" on the record where the truth was "the response
    contradicted itself".
    """
    vetoed = _reason(
        (await _screen_with(_Answer("clear", SCREEN_REFUSES_IN_COMMENT), monkeypatch))[
            0
        ]
    )
    flagged = _reason(
        (await _screen_with(_Answer("flagged", FLAGGED_COMMENT), monkeypatch))[0]
    )

    assert vetoed != flagged, (
        "a self-contradicting clear verdict was recorded under the flagged "
        f"reason, stating a finding about the product: {vetoed!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a verdict is *correct* about a product — whether a given item
#   really is on the FBA-prohibited hazmat list. No deterministic test can
#   establish it; `tasks.md` 4.5-4.6 gate it on live verification.
# - Whether the comment in fact states the categories considered, the
#   categories flagged, or the settling fact. The delta states these as
#   prompting obligations and forbids code from checking them, so a test
#   asserting them would assert against the requirement.
# ---------------------------------------------------------------------------
