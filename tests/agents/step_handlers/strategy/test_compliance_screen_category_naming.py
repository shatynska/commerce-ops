"""How the screen names the categories it reports (`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/compliance-screen/spec.md`

Covers, from the ADDED requirement *The categories the screen names are
the step's own wording, as an instruction to the model and not a check on
it*, all six of its scenarios:

- A repeated category is reported once
- A blank category name is dropped
- The model is instructed to use the description's wording
- A named category is carried through unaltered
- The description is not parsed to validate a name
- No category is supplied that the response did not name

`tasks.md` 1.11 and 1.12. The finding table itself, and the two
structural contradictions, are in
`test_compliance_screen_hazard_finding.py`.  See `test-manifest.md` at the
change root for the full accounting.

## Two rows that must be able to fail independently

- **The description is not parsed.** `test_a_category_the_description_does
  _not_contain_is_still_reported` names a category drawn from the
  *referenced* half of the description — the FBA-prohibited hazmat list,
  whose members the description does not enumerate — and asserts the
  screen reports it anyway. This is the row that fails an implementation
  that adds a validator, and the reason the delta gives at length for
  refusing one: "a description naming both a referenced list and inline
  examples would be checked against the examples alone".
- **Nothing is supplied that the response did not name.** The response's
  categories are deliberately *not* drawn from the description's
  parenthetical, so a screen that filled the finding from the description
  rather than from the response reports the wrong members and fails.

## Level

The registered handler over a stubbed model, the level the sibling files
use. The prompt scenario is observed from what the runnable received,
which is the only place the request the model gets is visible.

## What is fixed, and what is INVENTED

Fixed by the delta: that the request instructs the model to use the
description's wording; that a named category is carried through with
whitespace and letter case normalised and nothing else changed; that the
description is never parsed to check a name; that nothing is supplied
that the response did not name; that two names normalising to the same
value are reported once, **in the position of the first**; and that a
name normalising to nothing is dropped, a flagged verdict left naming
none then falling to the flagged-naming-nothing route.

Fixed by `design.md` Decision 4: normalisation is whitespace and case
only — `strip()` and a casefold comparison for equality, "preserving the
model's own casing in what is stored" — with deduplication preserving
first-occurrence order, and no sorting.

Fixed by `tasks.md` 4.1-4.2: the field name `categories`, and that the
prompt carries the instruction.

INVENTED, recorded in `test-manifest.md`:

- The scripting harness, duplicated per file as this project's handler
  tests are; the wire model's class is captured at the call site and
  never imported.
- **The keyword set standing in for "instructs the model to name
  categories using the wording the step's description uses".** The delta
  fixes that the instruction is present and fixes no wording, so the
  probe accepts several phrasings and its failure names every one it
  tried. DERIVED, and the correction point for a differently worded
  prompt.
- How the request the model received is read out (`_prompt_text`): every
  message the runnable was handed, flattened to text.

## Expected first-run state

`ScreenResponse` carries no `categories` field, the prompt carries no
naming instruction and the screen reports no finding (`tasks.md`
4.1-4.5), so every test here is expected to fail on an absent target.
Per `ai-toolkit:testing` that establishes absence only.

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

pytestmark = pytest.mark.anyio

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"

#: The seeded description of `lp.strategy.006`, verbatim from
#: `alembic/data/playbook_v1.yaml`.
DESCRIPTION: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)

FLAGGED_COMMENT: Final = (
    "This falls under supplements: the listing is an ingestible product, "
    "which Amazon gates behind a supplement compliance review before it may "
    "be sold."
)

#: A category the description reaches only through the list it
#: *references*, and therefore does not contain verbatim. The delta names
#: exactly this shape as what a validator would wrongly reject.
CATEGORY_FROM_THE_REFERENCED_LIST: Final = "aerosols and pressurised containers"


# ---------------------------------------------------------------------------
# Scripting the model's structured answer
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids."""


@dataclass(frozen=True)
class _Answer:
    verdict: str
    comment: str | None
    categories: list[str] = field(default_factory=list)


class _ScriptedStructuredRunnable:
    def __init__(self, script: _Answer, schema: Any) -> None:
        self._script = script
        self._schema = schema
        self.received: list[Any] = []

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
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
                categories=list(self._script.categories),
                comment=self._script.comment,
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
        raise _WrongSeam("the screen called the model directly")

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


# ---------------------------------------------------------------------------
# The context the handler is invoked with
# ---------------------------------------------------------------------------

STEP_ID: Final = "lp.strategy.006"
ALICE: Final = "prs_01HQ8Z6M4A"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))


class _CatalogProduct:
    def __init__(self) -> None:
        self.id = PRODUCT_ID
        self.name = PRODUCT_NAME
        self.sku = Sku("HZM-2027-01")
        self.marketplace_id = MarketplaceId("ATVPDKIKX0DER")
        self.sub_category: str | None = None
        self.hazard_categories: Any = None


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


def _handler() -> Any:
    handler = HANDLERS.resolve(screen.HANDLER_NAME)
    assert handler is not None
    return handler


async def _screen_with(
    script: _Answer, monkeypatch: pytest.MonkeyPatch, **step_overrides: Any
) -> tuple[Any, _ScriptedStructuredChatModel]:
    model = _ScriptedStructuredChatModel(script)

    def factory() -> Any:
        return screen.build_graph(model)

    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)
    context = StepContext(
        step=_step(**step_overrides),
        launch=_launch(),
        product=_CatalogProduct(),
        as_of=AS_OF,
    )
    return await _handler()(context), model


# ---------------------------------------------------------------------------
# Reading a resolution, and reading the request the model got
# ---------------------------------------------------------------------------

_ABSENT: Final = object()


def _finding(resolution: Any) -> Any:
    return getattr(resolution, "finding", _ABSENT)


def _reports_no_finding(resolution: Any) -> bool:
    found = _finding(resolution)
    return found is _ABSENT or found is None


def _reported(resolution: Any) -> list[str]:
    """The categories the screen reported, as members."""
    found = _finding(resolution)
    assert not _reports_no_finding(resolution), (
        "the screen reported no typed finding, so there are no categories to read"
    )
    assert isinstance(found, Success), (
        f"the reported finding is not a supported one: {found!r}"
    )
    value = found.value
    assert not isinstance(value, str), (
        f"the finding's value is the string {value!r}; a set of categories "
        "is not one of them"
    )
    return list(value)


def _withheld(resolution: Any) -> Blocked:
    outcome = getattr(resolution, "outcome", None)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome


def _prompt_text(model: _ScriptedStructuredChatModel) -> str:
    """Everything the runnable was handed, flattened to text.

    INVENTED reading of "the request it sends the model": the state, the
    messages, or a rendered string all flatten the same way, so the probe
    survives any of those shapes.
    """
    runnable = model.runnable
    assert runnable is not None and runnable.received, (
        "the screen never reached the model, so there is no request to read"
    )
    return " ".join(str(item) for item in runnable.received)


#: DERIVED. The delta fixes that the request carries the instruction and
#: fixes no wording, so several phrasings are accepted and a failure names
#: every one that was tried. Correction point for a differently worded
#: prompt.
_WORDING_INSTRUCTION_PHRASES: Final = (
    "the wording the",
    "the same wording",
    "wording used in the",
    "wording the description",
    "as the description names",
    "as they are named in the",
    "use the description's own wording",
    "name each category using the wording",
    "exactly as the step's description",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Scenario: The model is instructed to use the description's wording
# ---------------------------------------------------------------------------


async def test_the_model_is_instructed_to_use_the_descriptions_wording(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The model is instructed to use the description's wording.

    WHEN the screen builds the request it sends the model
    THEN that request instructs the model to name categories using the
    wording the step's description uses.

    SPECIFIED that the instruction is there; DERIVED which words carry it.
    The description itself must also reach the request — an instruction to
    reuse wording the model was never shown instructs nothing.
    """
    _resolution, model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, ["supplements"]), monkeypatch
    )

    request = _prompt_text(model)
    assert DESCRIPTION in request, (
        "the step's description does not reach the request, so an "
        "instruction to reuse its wording refers to nothing the model saw"
    )
    lowered = request.lower()
    assert any(phrase in lowered for phrase in _WORDING_INSTRUCTION_PHRASES), (
        "the request carries no instruction to name categories in the "
        "description's own wording — this obligation lives in the prompt "
        "because the delta forbids a check on it, so an absent instruction "
        "is the whole enforcement gone. Tried: "
        f"{list(_WORDING_INSTRUCTION_PHRASES)}"
    )


# ---------------------------------------------------------------------------
# Scenario: A named category is carried through unaltered
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("named", "reported"),
    [
        ("  supplements  ", "supplements"),
        ("\tmedical devices\n", "medical devices"),
        ("CO detectors", "CO detectors"),
        ("Fire Pits", "Fire Pits"),
        ("fire pits and grills", "fire pits and grills"),
    ],
    ids=["padded", "tabbed", "upper-inner", "title-case", "multi-word"],
)
async def test_a_named_category_is_carried_through_unaltered(
    named: str, reported: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A named category is carried through unaltered.

    WHEN the model names a category
    THEN what the screen reports is that name with surrounding whitespace
    and letter case normalised and nothing else changed.

    SPECIFIED: surrounding whitespace normalised, nothing else altered.
    `design.md` Decision 4 fixes what "letter case normalised" means for a
    *single* name: casefolding is used to compare for equality, and the
    model's own casing is preserved in what is stored — so `"Fire Pits"`
    is reported as it was named, not lowered. The two case rows are what
    fail an implementation that lowercases what it stores; the multi-word
    row is what fails one that also collapses inner whitespace or splits
    on a separator.
    """
    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, [named]), monkeypatch
    )

    assert _reported(resolution) == [reported]


# ---------------------------------------------------------------------------
# Scenario: The description is not parsed to validate a name
# ---------------------------------------------------------------------------


async def test_a_category_the_description_does_not_contain_is_still_reported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The description is not parsed to validate a name.

    WHEN the model names a category the step's description does not
    contain verbatim
    THEN the screen still reports it, having performed no extraction from
    the description to check it against.

    **This is the row that fails an implementation that adds a
    validator.** The fixture is drawn from the half of the description
    that *references* a list rather than enumerating it, which is exactly
    the correct answer the delta says a parser would reject.
    """
    assert CATEGORY_FROM_THE_REFERENCED_LIST not in DESCRIPTION  # precondition

    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, [CATEGORY_FROM_THE_REFERENCED_LIST]),
        monkeypatch,
    )

    assert _reported(resolution) == [CATEGORY_FROM_THE_REFERENCED_LIST], (
        "a category drawn from the list the description references rather "
        "than enumerates was dropped or altered; the description was "
        "parsed to check the model's answer, which this capability forbids"
    )


async def test_a_re_authored_description_does_not_filter_the_reported_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario, differentially: the description is changed and
    the reported names are not.

    Without this row a validator keyed on the *seeded* description alone
    would pass the row above by accident. Here the step names entirely
    different categories and the response names one from neither list; a
    screen filtering against the description reports nothing.
    """
    re_authored = (
        "Screen against the restricted-products policies for hoverboards, "
        "laser pointers and adult products before sourcing"
    )

    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, ["supplements"]),
        monkeypatch,
        description=re_authored,
    )

    assert _reported(resolution) == ["supplements"]


# ---------------------------------------------------------------------------
# Scenario: No category is supplied that the response did not name
# ---------------------------------------------------------------------------


async def test_no_category_is_supplied_that_the_response_did_not_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: No category is supplied that the response did not name.

    WHEN the screen reports the categories a flagged verdict established
    THEN every one of them was named by the response, and none was added
    from the description or from the screen's own knowledge.

    The response names one category the description's parenthetical also
    lists, so a screen that filled the finding from the description would
    report all eight of the parenthetical's members and fail on the count;
    the comment additionally names a *second* category in prose, which
    must not be reported either, since the delta forbids the comment's
    content being read at all.
    """
    comment_naming_a_second_category = (
        "This falls under supplements. I would also look closely at whether "
        "the medical devices heading could apply, though I do not think it "
        "does."
    )

    resolution, _model = await _screen_with(
        _Answer("flagged", comment_naming_a_second_category, ["supplements"]),
        monkeypatch,
    )

    assert _reported(resolution) == ["supplements"], (
        "the screen reported categories the response did not name — either "
        "supplied from the description or read out of the comment's prose"
    )


# ---------------------------------------------------------------------------
# Scenario: A repeated category is reported once
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("named", "reported"),
    [
        (["supplements", "supplements"], ["supplements"]),
        (["Supplements", "supplements"], ["Supplements"]),
        (["supplements", "  supplements  "], ["supplements"]),
        (
            ["grills", "supplements", "GRILLS", "lighters"],
            ["grills", "supplements", "lighters"],
        ),
    ],
    ids=["identical", "case", "whitespace", "position-preserved"],
)
async def test_a_repeated_category_is_reported_once(
    named: list[str], reported: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A repeated category is reported once.

    WHEN the model names two categories whose names normalise to the same
    value
    THEN the screen reports that category once, in the position the first
    of them occupied.

    SPECIFIED: both "once" and "in the position of the first". Asserting
    membership alone would pass an implementation that deduplicated
    through a set and lost the order, and asserting a sorted comparison
    would pass one that sorted — which `design.md` Decision 4 rules out
    ("sorting would be a transformation the carry-it-through rule forbids
    for no gain"). The list comparison here is what discriminates against
    both.

    The `case` row also pins which spelling survives: the *first*
    occurrence's own casing, per Decision 4's "preserving the model's own
    casing".
    """
    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, list(named)), monkeypatch
    )

    assert _reported(resolution) == reported


# ---------------------------------------------------------------------------
# Scenario: A blank category name is dropped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blank", ["", "   ", "\t", "\n  \n"], ids=["empty", "spaces", "tab", "newlines"]
)
async def test_a_blank_category_name_is_dropped(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: A blank category name is dropped.

    WHEN the model names a category whose name normalises to nothing
    THEN that name is not among the categories the screen reports.

    A real category is named alongside it so the response stays on the
    flagged-with-a-category route; the all-blank case is the next test.
    """
    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, ["supplements", blank]), monkeypatch
    )

    assert _reported(resolution) == ["supplements"], (
        f"a name normalising to nothing ({blank!r}) was reported as a category"
    )


async def test_a_flagged_verdict_whose_every_name_drops_names_no_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The clause the scenario defers: "where dropping leaves a flagged
    verdict naming no category, the requirement above governs what happens
    next."

    So the response reaches *A flagged verdict naming no category
    establishes nothing* — non-terminal, no finding — rather than
    reporting an empty finding, which would assert on the product that a
    screening found nothing. `tasks.md` 1.12's third clause, and the row
    that fails an implementation normalising after deciding the route.
    """
    resolution, _model = await _screen_with(
        _Answer("flagged", FLAGGED_COMMENT, ["   ", "\t", ""]), monkeypatch
    )

    _withheld(resolution)
    assert _reports_no_finding(resolution), (
        "a flagged verdict whose every name normalised away reported a "
        f"finding: {_finding(resolution)!r} — an empty one here would "
        "record 'screened, nothing found' for a response that asserted the "
        "opposite"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the model in fact obeys the instruction. The delta places the
#   obligation on the prompt precisely because no code checks it, so a
#   test asserting obedience would assert against the requirement.
# - Whether a recorded value stays meaningful after the description is
#   re-authored. The delta states the consequence as accepted ("recorded
#   category values are exactly as stable as the authored description")
#   and builds no reconciliation, so there is nothing to assert.
# ---------------------------------------------------------------------------
