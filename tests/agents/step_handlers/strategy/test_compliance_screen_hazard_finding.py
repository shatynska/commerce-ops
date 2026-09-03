"""The compliance screen's typed finding, and the two structural
contradictions the widened response admits (`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/compliance-screen/spec.md`

Covers:

*The screen reports what it established as a typed finding* (ADDED) — all
seven scenarios:
- A clear verdict establishes an empty set of categories
- A flagged verdict establishes the categories it named
- An undetermined verdict establishes nothing
- An unreadable verdict establishes nothing
- A screen given nothing to work with establishes nothing
- A prior flag survives a later screening that establishes nothing
- The outcome and the produced text are unaffected

*A flagged verdict naming no category establishes nothing* (ADDED) — both:
- A flagged verdict naming nothing is not recorded as flagged
- Its reason is its own

*A verdict its own response contradicts is not satisfaction* (MODIFIED) —
all five, written fresh for the requirement as revised:
- A clear verdict carrying a stated inability is refused
- A statement about a category does not withhold satisfaction
- A clear verdict naming categories is refused
- The structural contradiction is not reported as the prose one
- A contradicted verdict establishes nothing about the product

*Satisfaction is proposed only for a clear verdict* (MODIFIED) — all five,
likewise written fresh for the requirement as revised:
- A clear verdict proposes satisfaction
- A flagged verdict proposes a non-terminal outcome (its **WHEN** now
  narrowed to a response naming at least one category)
- An undetermined verdict proposes a non-terminal outcome
- An unreadable verdict is not reported as a judgement about the product
- A blank comment outranks a structural contradiction

`tasks.md` 1.8, 1.9, 1.10, 1.13, 1.14. The naming, normalisation and
deduplication rules are in
`test_compliance_screen_category_naming.py`; the widened wire schema at
the provider's conversion boundary is in
`tests/unit/step_handlers/strategy/test_compliance_screen_categories_field.py`.
See `test-manifest.md` at the change root for the full accounting.

## A note on the two MODIFIED requirements

Per this pass's rule for a MODIFIED requirement, its scenarios *as
revised* are written fresh here exactly as they would be for an ADDED
one, and the existing files covering the same scenarios
(`test_compliance_screen_verdict_routing.py`) are left untouched. The
duplication is deliberate and recorded rather than hidden: what is new in
each is the finding assertion beside the outcome, which is what the
existing coverage cannot see.

## Level

The registered handler over a stubbed model, invoked with a
`StepContext` — the level `test_compliance_screen_verdict_routing.py`
established, and the smallest one that can observe a finding *and* the
outcome and text beside it. The stub is reached by pointing
`build_production_graph` at a graph over it, the seam that file
documents; the graph cache is cleared around every install so one test's
stub never answers the next.

## What is fixed, and what is INVENTED

Fixed by the delta: which two routes carry a finding and what each
carries; that no route reports an empty finding to mean "nothing
established"; that reporting no finding leaves the product untouched;
that the finding names no field; that the outcome and text are unchanged
by the presence of a finding; that a `clear` verdict naming categories
and a `flagged` verdict naming none each carry their own wording; and
that a blank comment is resolved before any other property of the
response is dispatched on.

Fixed by `tasks.md` 4.1: the wire schema's third field name,
`categories`. The delta names the concept and no field, so the field name
traces to `tasks.md`.

Fixed by `tasks.md` 4.5: `finding=Success(value=[...], comment=comment)`
on the two carrying routes and `finding=None` on every other — so
"reports a finding" is read as a `Success` under
`StepResolution.finding`, and "reports none" as its absence.

INVENTED, recorded in `test-manifest.md`:

- The scripting harness (`_Answer`, `_ScriptedStructuredRunnable`,
  `_ScriptedStructuredChatModel`, `_install_stub_graph`), duplicated from
  `test_compliance_screen_verdict_routing.py` rather than imported,
  following this project's separate-file convention for handler tests.
- **The wire model is never imported by name.** Its class is captured at
  the `with_structured_output(...)` call site and instantiated there, so
  this file invents no class name — only the three field names.
- The prose of every fixture comment, and the keyword sets each reason is
  matched against. The delta fixes what a reason must *state*, never its
  wording; keyword sets are DERIVED and marked at each use. Every
  *distinctness* assertion is SPECIFIED and asserted separately, so a
  wording change cannot silently take it with it.
- `Blocked` specifically as "a non-terminal outcome", narrower than the
  delta's own word, for the reason the sibling file records.

## Expected first-run state

`ScreenResponse` carries no `categories` field and the screen reports no
finding at all (`tasks.md` 4.1-4.5), so every test here is expected to
fail on an absent target: instantiating the captured schema with a
`categories` keyword it does not declare, or reading a `finding` that is
always `None`. Per `ai-toolkit:testing` that is failure state 2 for the
former and state 1 for the latter; neither is resolved by writing the
code under test.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
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
from commerce_ops.shared.domain.result import Success
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

# ---------------------------------------------------------------------------
# Fixtures of content
# ---------------------------------------------------------------------------

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"

#: The seeded description of `lp.strategy.006`, verbatim from
#: `alembic/data/playbook_v1.yaml` — a referenced list plus an inline
#: parenthetical of examples, which is the ordinary case.
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
UNDETERMINED_COMMENT: Final = (
    "Whether this falls under the hazmat list turns on whether the unit "
    "contains a lithium battery, which the product name does not say."
)

#: DERIVED. A statement about the *screen's own* ability to screen, under
#: a `clear` verdict — the state the prose veto exists for.
SCREEN_REFUSES_IN_COMMENT: Final = (
    "On reflection I cannot screen this product properly without knowing "
    "whether the unit contains a lithium battery or a pressurised cell."
)

#: DERIVED. A statement about a *category*, under a `clear` verdict — the
#: boundary case the veto must not fire on, kept here so that a veto
#: widened while the schema was widened is caught with the finding
#: assertion beside it.
CATEGORY_CALLED_INAPPLICABLE: Final = (
    "Supplements cannot apply to this product at all, since nothing about "
    "it is ingestible; the medical-devices heading is unable to reach a "
    "cutting board either. None of the named categories applies."
)

ONE_CATEGORY: Final = ["supplements"]
SEVERAL_CATEGORIES: Final = ["supplements", "medical devices"]
NO_CATEGORIES: Final[list[str]] = []


# ---------------------------------------------------------------------------
# Scripting the model's structured answer
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids."""


class _ModelFailure(RuntimeError):
    """A fault raised from inside the model call, for the propagation row."""


@dataclass(frozen=True)
class _Answer:
    """A wire response to script, by field rather than by class.

    The wire model's class is deliberately not imported: the runnable
    instantiates whatever class the screen handed to
    `with_structured_output(...)`, so this file names only the three field
    names `tasks.md` 4.1 fixes.
    """

    verdict: str
    comment: str | None
    categories: list[str] = field(default_factory=list)


#: Script value meaning "the structured call completed and validated
#: against nothing".
_NO_PARSE: Final = object()
#: Script value meaning "the model call itself raised".
_RAISE: Final = object()


class _ScriptedStructuredRunnable:
    def __init__(self, script: Any, schema: Any) -> None:
        self._script = script
        self._schema = schema
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        if self._script is _RAISE:
            raise _ModelFailure("the provider refused the request")
        if self._script is _NO_PARSE:
            return {
                "raw": AIMessage(content="not a recognisable verdict"),
                "parsed": None,
                "parsing_error": ValueError("could not validate against the schema"),
            }
        assert isinstance(self._script, _Answer)
        parsed = self._schema(
            verdict=self._script.verdict,
            categories=list(self._script.categories),
            comment=self._script.comment,
        )
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": parsed,
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise _WrongSeam(
            "the screen reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)`"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
    """Answers the `with_structured_output(...)` seam and nothing else."""

    script: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]
    requested_schema: ClassVar[Any]

    def __init__(self, script: Any) -> None:
        super().__init__()
        object.__setattr__(self, "script", script)
        object.__setattr__(self, "runnable", None)
        object.__setattr__(self, "requested_schema", None)

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
        object.__setattr__(self, "requested_schema", schema)
        runnable = _ScriptedStructuredRunnable(self.script, schema)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-structured-fake-chat-model"


class _RefusingFactory:
    """A production-graph factory that must never be called.

    Installed for the two routes the delta says reach no model at all, so
    "no model call is made" is *established* rather than inferred from the
    outcome text.
    """

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> Any:
        self.calls += 1
        raise AssertionError(
            "the screen built its production graph for a route the delta "
            "says establishes nothing without reaching a model"
        )


# ---------------------------------------------------------------------------
# Putting the stub behind the registered handler
# ---------------------------------------------------------------------------


def _clear_graph_caches() -> None:
    for value in vars(screen).values():
        clear = getattr(value, "cache_clear", None)
        if callable(clear):
            clear()


@pytest.fixture(autouse=True)
def _fresh_graph() -> Any:
    _clear_graph_caches()
    yield
    _clear_graph_caches()


def _install_stub_graph(monkeypatch: pytest.MonkeyPatch, model: BaseChatModel) -> None:
    def factory() -> Any:
        return screen.build_graph(model)

    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)


# ---------------------------------------------------------------------------
# The context the handler is invoked with
# ---------------------------------------------------------------------------

STEP_ID: Final = "lp.strategy.006"
ALICE: Final = "prs_01HQ8Z6M4A"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))


class _CatalogProduct:
    """Stands in for the catalog product the pass supplies."""

    def __init__(
        self,
        name: str = PRODUCT_NAME,
        hazard_categories: Any = None,
    ) -> None:
        self.id = PRODUCT_ID
        self.name = name
        self.sku = Sku("HZM-2027-01")
        self.marketplace_id = MarketplaceId("ATVPDKIKX0DER")
        self.sub_category: str | None = None
        self.hazard_categories = hazard_categories


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


def _context(
    product: _CatalogProduct | None = None, **step_overrides: Any
) -> StepContext:
    return StepContext(
        step=_step(**step_overrides),
        launch=_launch(),
        product=_CatalogProduct() if product is None else product,
        as_of=AS_OF,
    )


def _handler() -> Any:
    handler = HANDLERS.resolve(screen.HANDLER_NAME)
    assert handler is not None, (
        f"no step handler is registered under {screen.HANDLER_NAME!r}"
    )
    return handler


async def _screen_with(
    script: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    product: _CatalogProduct | None = None,
    **step_overrides: Any,
) -> Any:
    """Run the registered handler over a scripted model answer."""
    model = _ScriptedStructuredChatModel(script)
    _install_stub_graph(monkeypatch, model)
    return await _handler()(_context(product, **step_overrides))


# ---------------------------------------------------------------------------
# Reading a resolution
# ---------------------------------------------------------------------------

_ABSENT: Final = object()


def _text(resolution: Any) -> str:
    text = getattr(resolution, "result", None)
    assert isinstance(text, str), (
        f"the screen's resolution carries no produced text: {resolution!r}"
    )
    return text


def _withheld(resolution: Any) -> Blocked:
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


def _finding(resolution: Any) -> Any:
    """What the resolution reports as its typed finding, or `_ABSENT`.

    `_ABSENT` and `None` are deliberately not distinguished: `tasks.md`
    4.5 spells "reports none" as `finding=None`, and a resolution type
    that does not carry the attribute at all reports none just as
    plainly.
    """
    return getattr(resolution, "finding", _ABSENT)


def _reports_no_finding(resolution: Any) -> bool:
    found = _finding(resolution)
    return found is _ABSENT or found is None


def _supported_value(resolution: Any) -> Any:
    """The value of a reported finding, failing loudly where none was
    reported.

    The delta's phrase is "reports a typed finding"; `tasks.md` 4.5
    spells it `Success(value=..., comment=...)`, so a `Failure` — or
    anything carrying no `value` — is not one.
    """
    found = _finding(resolution)
    assert not _reports_no_finding(resolution), (
        "the screen reported no typed finding where the delta requires one"
    )
    assert isinstance(found, Success), (
        f"the reported finding is not a supported one: {found!r}"
    )
    return found.value


def _members(value: Any) -> list[str]:
    assert value is not None, "the finding's value is absent rather than a set"
    assert not isinstance(value, str), (
        f"the finding's value is the string {value!r}; a set of categories "
        "is not one of them"
    )
    return list(value)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


pytestmark = pytest.mark.anyio


# ---------------------------------------------------------------------------
# Requirement: The screen reports what it established as a typed finding
# ---------------------------------------------------------------------------


async def test_a_clear_verdict_establishes_an_empty_set_of_categories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict establishes an empty set of categories.

    WHEN the screen resolves a step with a clear verdict its response does
    not contradict
    THEN it reports a typed finding whose value is an empty set of
    categories, distinct from reporting no finding at all.

    SPECIFIED: **present and empty**, and the distinctness from absent is
    asserted as its own clause. An assertion that merely tested falsiness
    would pass for `finding=None`, which is the defect this row exists to
    catch — and the one that decides whether "screened and clear" can ever
    reach a product at all.
    """
    resolution = await _screen_with(
        _Answer("clear", CLEAR_COMMENT, NO_CATEGORIES), monkeypatch
    )

    assert not _reports_no_finding(resolution), (
        "a clear verdict reported no typed finding, so a screened-and-clear "
        "product is indistinguishable from an unscreened one"
    )
    assert _members(_supported_value(resolution)) == []


async def test_a_flagged_verdict_establishes_the_categories_it_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A flagged verdict establishes the categories it named.

    WHEN the screen resolves a step with a flagged verdict naming one or
    more categories
    THEN it reports a typed finding carrying exactly those categories.

    SPECIFIED: **exactly** those — asserted over several categories, so an
    implementation carrying only the first passes neither clause.
    """
    resolution = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(SEVERAL_CATEGORIES)), monkeypatch
    )

    assert _members(_supported_value(resolution)) == list(SEVERAL_CATEGORIES)


@pytest.mark.parametrize(
    "categories",
    [NO_CATEGORIES, ONE_CATEGORY, SEVERAL_CATEGORIES],
    ids=["none", "one", "several"],
)
async def test_an_undetermined_verdict_establishes_nothing(
    categories: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: An undetermined verdict establishes nothing.

    WHEN the screen resolves a step with an undetermined verdict
    THEN it reports no typed finding, and in particular does not report an
    empty one.

    SPECIFIED: both clauses. Parametrised over what the response named,
    because the widened schema lets an undetermined verdict carry
    categories and the delta gives that combination one destination —
    "an undetermined verdict, any `categories`".
    """
    resolution = await _screen_with(
        _Answer("undetermined", UNDETERMINED_COMMENT, list(categories)), monkeypatch
    )

    _withheld(resolution)
    assert _reports_no_finding(resolution), (
        "an undetermined verdict reported a finding; the finding it "
        f"reported was {_finding(resolution)!r}, and an empty one here "
        "would assert on the product that a screening found nothing"
    )


async def test_an_unreadable_verdict_establishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unreadable verdict establishes nothing.

    WHEN the screen resolves a step for a response no verdict could be
    read from
    THEN it reports no typed finding.
    """
    resolution = await _screen_with(_NO_PARSE, monkeypatch)

    _withheld(resolution)
    assert _reports_no_finding(resolution)


@pytest.mark.parametrize("verdict", ["clear", "flagged", "undetermined"])
@pytest.mark.parametrize("comment", [None, "", "   ", "\n\t "])
async def test_a_blank_comment_establishes_nothing(
    verdict: str, comment: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The requirement's own list: "a verdict that could not be read"
    includes a verdict with no comment to justify it, which *Satisfaction
    is proposed only for a clear verdict* resolves before anything else.

    The `clear` row is the one an implementation computing the finding on
    the clear branch before applying the blank-comment check gets wrong.
    """
    resolution = await _screen_with(
        _Answer(verdict, comment, list(ONE_CATEGORY)), monkeypatch
    )

    _withheld(resolution)
    assert _reports_no_finding(resolution), (
        f"a {verdict!r} verdict with comment {comment!r} reported a finding"
    )


async def test_a_screen_given_no_product_establishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A screen given nothing to work with establishes nothing —
    the no-product half.

    The pass reads the catalog through a call typed `Product | None`, so
    an unresolvable product reaches the handler as an empty name. No model
    is reached, which is *established* here rather than inferred: the
    production-graph factory raises if it is called at all.
    """
    factory = _RefusingFactory()
    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)

    resolution = await _handler()(_context(_CatalogProduct(name="")))

    _withheld(resolution)
    assert _reports_no_finding(resolution)
    assert factory.calls == 0


@pytest.mark.parametrize(
    "description", [None, "", "   "], ids=["absent", "empty", "blank"]
)
async def test_a_step_naming_no_categories_establishes_nothing(
    description: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A screen given nothing to work with establishes nothing —
    the no-categories half.

    "and for the blank description no model call is made" (`tasks.md`
    1.8), established the same way.
    """
    factory = _RefusingFactory()
    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)

    resolution = await _handler()(_context(None, description=description))

    _withheld(resolution)
    assert _reports_no_finding(resolution)
    assert factory.calls == 0


async def test_a_prior_flag_survives_a_later_screening_that_establishes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A prior flag survives a later screening that establishes
    nothing.

    WHEN a product whose hazard categories were recorded as flagged is
    screened again and the screening establishes nothing
    THEN no finding is reported, and the product's recorded categories are
    unchanged.

    Asserted at the level the screen can be held to: the screen reports no
    finding, so nothing downstream is asked to write, and the product
    object it was handed is untouched. The pass's own half — that a
    resolution reporting no finding invokes no recorder — is asserted in
    `tests/unit/launch/infrastructure/driving/test_automation_pass_hazard_finding.py`.
    """
    flagged_already = _CatalogProduct(hazard_categories=("supplements",))

    resolution = await _screen_with(
        _Answer("undetermined", UNDETERMINED_COMMENT, NO_CATEGORIES),
        monkeypatch,
        product=flagged_already,
    )

    assert _reports_no_finding(resolution), (
        "a screening that established nothing reported a finding, which "
        "would replace the flag an earlier screening recorded"
    )
    assert flagged_already.hazard_categories == ("supplements",)


async def test_the_outcome_and_produced_text_are_unaffected_by_the_finding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The outcome and the produced text are unaffected.

    WHEN the screen reports a typed finding alongside its outcome
    THEN the outcome proposed and the text a member reads are exactly what
    they would be for the same response without a finding.

    Asserted as the properties the capability's existing requirements
    already fix for those same responses, on both carrying routes: a
    clear verdict proposes satisfaction with the cited categories, the
    verdict and the comment in the text; a flagged verdict proposes a
    non-terminal outcome naming the product and stating that it was
    flagged, with the comment in the text. A regression in either lands
    here beside the finding rather than only in the existing verdict
    table.
    """
    clear = await _screen_with(
        _Answer("clear", CLEAR_COMMENT, NO_CATEGORIES), monkeypatch
    )
    flagged = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
    )

    assert getattr(clear, "outcome", None) is Satisfied
    clear_text = _text(clear)
    assert DESCRIPTION in clear_text
    assert CLEAR_COMMENT in clear_text
    assert "clear" in clear_text.lower()

    reason = _reason(flagged)
    assert PRODUCT_NAME in reason
    # DERIVED keyword: no artifact fixes the flagged reason's wording.
    assert "flag" in reason.lower()
    assert FLAGGED_COMMENT in _text(flagged)


async def test_the_finding_names_no_field(monkeypatch: pytest.MonkeyPatch) -> None:
    """The requirement's clause: "The finding SHALL NOT name the field it
    is written to."

    Where a value goes, and the wording that field reads as, are the
    registering deployment's knowledge. Asserted both structurally — the
    finding carries no field-naming attribute — and textually, since the
    resolution's own repr is what a later author would copy a field name
    into.
    """
    resolution = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
    )

    found = _finding(resolution)
    for naming in ("field", "field_name", "finding_field", "reads_as", "sink"):
        assert not hasattr(found, naming), (
            f"the reported finding carries {naming!r}, naming where its "
            "value goes — which is the registering deployment's knowledge"
        )
        assert not hasattr(resolution, naming), (
            f"the resolution carries {naming!r} beside its finding"
        )
    assert "hazard_categories" not in repr(resolution), (
        "the storage field name appears in what the handler returns"
    )


async def test_model_failure_is_surfaced_not_masked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*Model failure is surfaced, not masked*, re-exercised (`tasks.md`
    1.14).

    Unchanged by this delta, and re-exercised because the two new routes
    sit one branch away from it: a broad `except` added while widening the
    schema would land the fault in one of them, turning a provider outage
    into "the response contradicted itself" with a finding beside it.
    """
    with pytest.raises(_ModelFailure):
        await _screen_with(_RAISE, monkeypatch)


# ---------------------------------------------------------------------------
# Requirement: A flagged verdict naming no category establishes nothing
# ---------------------------------------------------------------------------


async def test_a_flagged_verdict_naming_nothing_is_not_recorded_as_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A flagged verdict naming nothing is not recorded as
    flagged.

    WHEN the screen's response reports a flagged verdict and names no
    category
    THEN it proposes a non-terminal outcome and reports no typed finding.
    """
    resolution = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, NO_CATEGORIES), monkeypatch
    )

    _withheld(resolution)
    assert _reports_no_finding(resolution), (
        "a flagged verdict naming no category reported a finding; there is "
        "no fact behind it to record"
    )


async def test_the_flagged_naming_nothing_reason_is_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Its reason is its own.

    WHEN the screen reports the shortfall for a flagged verdict naming no
    category
    THEN the wording is distinguishable from the flagged reason and from
    the undetermined reason, rather than reusing either.

    SPECIFIED, and both comparisons are made: without them an
    implementation routing this response to *either* existing reason
    passes every other row in this file. "Routing it to the flagged reason
    would put 'this product is flagged' on the launch's record with no
    category behind it, and routing it to the undetermined reason would
    say the screen could not settle the question when the response says it
    did."
    """
    naming_nothing = _reason(
        await _screen_with(
            _Answer("flagged", FLAGGED_COMMENT, NO_CATEGORIES), monkeypatch
        )
    )
    flagged = _reason(
        await _screen_with(
            _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
        )
    )
    undetermined = _reason(
        await _screen_with(
            _Answer("undetermined", UNDETERMINED_COMMENT, NO_CATEGORIES), monkeypatch
        )
    )

    assert naming_nothing != flagged, (
        "a flagged verdict naming no category was recorded under the "
        f"flagged reason: {naming_nothing!r}"
    )
    assert naming_nothing != undetermined, (
        "a flagged verdict naming no category was recorded under the "
        f"undetermined reason: {naming_nothing!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: A verdict its own response contradicts is not satisfaction
# ---------------------------------------------------------------------------


async def test_a_clear_verdict_carrying_a_stated_inability_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict carrying a stated inability is refused.

    WHEN the screen's response reports a clear verdict while also stating
    that the screen could not screen the product
    THEN it proposes a non-terminal outcome, and the text a member reads
    carries the stated inability.

    **And it reports no finding.** This row is not a re-exercise of the
    existing veto: without the finding clause an implementation that
    computes the finding on the `clear` branch *before* applying the veto
    passes every other row in this file while violating the delta —
    writing "screened, nothing found" onto a product the response says
    could not be screened.
    """
    resolution = await _screen_with(
        _Answer("clear", SCREEN_REFUSES_IN_COMMENT, NO_CATEGORIES), monkeypatch
    )

    _withheld(resolution)
    assert SCREEN_REFUSES_IN_COMMENT in _text(resolution), (
        "the text a member reads does not carry the stated inability"
    )
    assert _reports_no_finding(resolution), (
        "a clear verdict the screen's own prose withheld reported a "
        "finding; the finding was computed before the veto decided the route"
    )


async def test_a_statement_about_a_category_does_not_withhold_satisfaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A statement about a category does not withhold
    satisfaction.

    WHEN the screen's response reports a clear verdict whose comment
    states that a named category cannot apply to the product
    THEN it proposes the step's satisfying outcome.

    Extended, per `tasks.md` 1.9's last row: it **still carries the empty
    finding**. A veto widened to catch this prose would then also be
    caught by the finding assertion, so the row that stops the veto being
    reimplemented as a phrase list now guards the product's record too.
    """
    resolution = await _screen_with(
        _Answer("clear", CATEGORY_CALLED_INAPPLICABLE, NO_CATEGORIES), monkeypatch
    )

    assert getattr(resolution, "outcome", None) is Satisfied, (
        "a statement about a category that cannot apply was read as the "
        f"screen refusing to screen: {resolution!r}"
    )
    assert _members(_supported_value(resolution)) == []


async def test_a_clear_verdict_naming_categories_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict naming categories is refused.

    WHEN the screen's response reports a clear verdict and, in the same
    response, names one or more categories the product falls in
    THEN it proposes a non-terminal outcome, and the text a member reads
    carries both the clear verdict and the categories named.

    SPECIFIED: all three clauses. The text clause is the one a weaker test
    drops — "the reader must see the contradiction, not one half of it".
    """
    resolution = await _screen_with(
        _Answer("clear", CLEAR_COMMENT, list(SEVERAL_CATEGORIES)), monkeypatch
    )

    _withheld(resolution)
    text = _text(resolution)
    assert "clear" in text.lower(), (
        f"the text a member reads does not carry the clear verdict: {text!r}"
    )
    for category in SEVERAL_CATEGORIES:
        assert category in text, (
            f"the text a member reads does not carry the named category "
            f"{category!r}, so a reader sees one half of the contradiction: "
            f"{text!r}"
        )


async def test_the_structural_contradiction_is_not_reported_as_the_prose_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The structural contradiction is not reported as the prose
    one.

    WHEN the screen refuses a clear verdict because the same response
    named categories
    THEN what it reports is distinguishable from what it reports for a
    clear verdict withheld by its own comment, rather than sharing that
    route's wording.

    SPECIFIED, and asserted as textual distinctness rather than against a
    keyword set, since the delta fixes that the two read differently and
    fixes neither wording.
    """
    structural = _reason(
        await _screen_with(
            _Answer("clear", CLEAR_COMMENT, list(ONE_CATEGORY)), monkeypatch
        )
    )
    prose = _reason(
        await _screen_with(
            _Answer("clear", SCREEN_REFUSES_IN_COMMENT, NO_CATEGORIES), monkeypatch
        )
    )

    assert structural != prose, (
        "a response contradicting its verdict structurally and one "
        "withholding it in prose reported the same wording; this capability "
        f"requires different things that happened to read differently: "
        f"{structural!r}"
    )


@pytest.mark.parametrize(
    ("comment", "categories", "what"),
    [
        (SCREEN_REFUSES_IN_COMMENT, NO_CATEGORIES, "the prose contradiction"),
        (CLEAR_COMMENT, ONE_CATEGORY, "the structural contradiction"),
    ],
    ids=["prose", "structural"],
)
async def test_a_contradicted_verdict_establishes_nothing_about_the_product(
    comment: str, categories: list[str], what: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A contradicted verdict establishes nothing about the
    product.

    WHEN the screen refuses a clear verdict for either contradiction
    THEN it reports no typed finding, and nothing is recorded against the
    product on its behalf.

    "Either" is why this is parametrised rather than asserted once: an
    implementation reporting no finding on one contradiction and an empty
    one on the other satisfies a single-row test and leaves a flagged
    product reading as clear.
    """
    flagged_already = _CatalogProduct(hazard_categories=("supplements",))

    resolution = await _screen_with(
        _Answer("clear", comment, list(categories)),
        monkeypatch,
        product=flagged_already,
    )

    _withheld(resolution)
    assert _reports_no_finding(resolution), (
        f"{what} reported a finding: {_finding(resolution)!r}"
    )
    # "the product's recorded hazard categories are left exactly as they
    # were, including a flag recorded by an earlier screening".
    assert flagged_already.hazard_categories == ("supplements",)


# ---------------------------------------------------------------------------
# Requirement: Satisfaction is proposed only for a clear verdict
# ---------------------------------------------------------------------------


async def test_a_clear_verdict_proposes_satisfaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A clear verdict proposes satisfaction.

    Written fresh for the requirement as revised, per this pass's rule for
    a MODIFIED requirement. The finding beside it is what is new.
    """
    resolution = await _screen_with(
        _Answer("clear", CLEAR_COMMENT, NO_CATEGORIES), monkeypatch
    )

    assert getattr(resolution, "outcome", None) is Satisfied
    text = _text(resolution)
    assert DESCRIPTION in text
    assert CLEAR_COMMENT in text
    assert "clear" in text.lower()


async def test_a_flagged_verdict_naming_a_category_proposes_a_non_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A flagged verdict proposes a non-terminal outcome.

    The requirement's **WHEN** is narrowed by this delta to a response
    naming at least one category — the scenario keeping its name — so that
    a single flagged response is not required to carry two different
    reasons. The narrowed WHEN is what this row supplies.
    """
    resolution = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
    )

    reason = _reason(resolution)
    assert PRODUCT_NAME in reason
    # DERIVED keyword set: the delta fixes what the reason states, not its
    # wording.
    assert "flag" in reason.lower()
    assert FLAGGED_COMMENT in _text(resolution)


async def test_an_undetermined_verdict_proposes_a_non_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An undetermined verdict proposes a non-terminal outcome."""
    resolution = await _screen_with(
        _Answer("undetermined", UNDETERMINED_COMMENT, NO_CATEGORIES), monkeypatch
    )
    flagged = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
    )

    reason = _reason(resolution)
    lowered = reason.lower()
    # DERIVED keyword set.
    assert any(
        phrase in lowered
        for phrase in ("settle", "not settled", "could not determine", "undetermined")
    ), f"the undetermined reason does not say the question was not settled: {reason!r}"
    assert reason != _reason(flagged)


async def test_an_unreadable_verdict_is_not_a_judgement_about_the_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: An unreadable verdict is not reported as a judgement about
    the product.

    The second clause is asserted as distinctness from the two reasons
    that *do* state those things, not as a substring ban — the reading the
    existing suite records, and for the reason it records.
    """
    resolution = await _screen_with(_NO_PARSE, monkeypatch)
    flagged = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(ONE_CATEGORY)), monkeypatch
    )
    undetermined = await _screen_with(
        _Answer("undetermined", UNDETERMINED_COMMENT, NO_CATEGORIES), monkeypatch
    )

    reason = _reason(resolution)
    lowered = reason.lower()
    # DERIVED keyword set.
    assert any(
        phrase in lowered
        for phrase in ("no verdict", "could not be read", "unreadable", "no readable")
    ), f"the reason does not state that no verdict could be read: {reason!r}"
    assert reason != _reason(flagged)
    assert reason != _reason(undetermined)


@pytest.mark.parametrize("comment", [None, "", "   ", "\n\t "])
@pytest.mark.parametrize(
    ("verdict", "categories", "which"),
    [
        ("clear", ONE_CATEGORY, "a clear verdict naming categories"),
        ("flagged", NO_CATEGORIES, "a flagged verdict naming none"),
    ],
    ids=["clear-naming-categories", "flagged-naming-none"],
)
async def test_a_blank_comment_outranks_a_structural_contradiction(
    comment: str | None,
    verdict: str,
    categories: list[str],
    which: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A blank comment outranks a structural contradiction.

    WHEN the screen's response carries an empty or whitespace-only comment
    and would also trigger a structural contradiction
    THEN it is treated as an unreadable verdict, carrying that route's
    reason rather than either contradiction's.

    SPECIFIED, and asserted as reason **equality** with the unreadable
    route rather than as mere non-terminality: the requirement makes the
    precedence "a fact rather than a guess", and every candidate
    destination is required to carry wording distinct from the others, so
    only equality with the right one discriminates.

    These are the two combinations the widened schema newly admits into
    more than one destination.
    """
    resolution = await _screen_with(
        _Answer(verdict, comment, list(categories)), monkeypatch
    )
    unreadable = await _screen_with(_NO_PARSE, monkeypatch)

    assert getattr(resolution, "outcome", None) is not Satisfied
    assert _reason(resolution) == _reason(unreadable), (
        f"{which} with a blank comment carried its contradiction's reason "
        f"rather than the unreadable route's: {_reason(resolution)!r} vs "
        f"{_reason(unreadable)!r}"
    )
    assert _reports_no_finding(resolution)


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether a verdict is *correct* about a product. No deterministic test
#   can establish it.
# - Whether the produced text should also carry the categories a plain
#   flagged verdict named. The delta requires that for the structural
#   contradiction and says nothing about it for the ordinary flagged
#   route, so nothing here asserts either way.
# - The wording of any reason. The delta fixes what each states and that
#   each is distinct; distinctness is what is asserted.
# ---------------------------------------------------------------------------
