"""A model failure surfacing, and what the screen reads and reports
(`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from three ADDED requirements, six scenarios:

*Model failure is surfaced, not masked*
- A failing model call surfaces as a failure
- Response content that is not a plain string surfaces as a failure

*The screen reads only what it is given, and reports no finding*
- The product is taken from the context
- A value reaching the model is the value, not its object's rendering
- No finding accompanies the outcome

*The screen is reached only through the step it is authored onto*
- The screen does not test which step invoked it

`tasks.md` 1.9, 1.10, 1.11 and 1.12. The remaining two scenarios of the
last requirement — *The handler is resolvable in every process consulting
the registry* and *Registration loads nothing the run needs* — are process
properties and live in the unit tier
(`tests/unit/test_compliance_screen_registered_across_processes.py` and
`tests/unit/step_handlers/strategy/test_compliance_screen_registration_is_cheap.py`).
See `test-manifest.md` at the change root for the full accounting.

## Why the failure tests assert propagation rather than a reported path

The delta is explicit that a model failure "SHALL NOT be routed to the
unreadable-verdict path, nor to any other non-terminal outcome", because
`launch-step-automation` already reports a raising handler naming the
launch, step and handler, records nothing, and continues the pass. A test
asserting only "a non-terminal outcome with some reason" would pass
exactly the broad-`except` implementation the requirement exists to
forbid, and the unreadable-verdict route is the immediately adjacent one
such an `except` would land in. So both failure tests assert that the
exception leaves the handler and that **no resolution is produced**.

## Reading "content that is not a plain string"

Two readings were available and one is foreclosed by the rest of the
capability. Reading it as "`parsed` is `None` because the response
validated against nothing" would contradict *An unreadable verdict is not
reported as a judgement about the product*, which routes exactly that
state to a non-terminal outcome. So it is read here as the reading that
leaves both requirements standing: the structured-output call yielded
something other than the `raw`/`parsed`/`parsing_error` dict
`include_raw=True` contracts to return — a response whose content the
client could not present as text at all — and the screen fails visibly on
it rather than coercing a verdict out of it. Recorded as an INVENTED
reading in `test-manifest.md`, with this reasoning.

## Level

The registered handler, invoked with a `StepContext`: every scenario here
is about what the handler reads from its context, what it hands the model,
what it reports alongside its outcome, or whether a fault escapes it.

## What is fixed, and what is INVENTED

Fixed by the delta: that a failing call and a non-plain-string response
both surface; that the screen reads the product and step from the context
and fetches nothing; that a value carried as a value object reaches the
model as its value with none of the object's rendering; that no typed
finding accompanies the outcome; and that the screen refuses nothing on
the basis of the step's identifier, discipline or gate.

INVENTED, recorded in `test-manifest.md`:

- The fakes and `_install_stub_graph`, duplicated per file.
- `_no_network` as the way "performs no lookup of its own" is established
  rather than merely inferred.
- The rendering tokens `_leaked_renderings` looks for. The delta names the
  three things that must not appear — a type name, a field name, the
  quoting around a value — and these are what those are in this codebase's
  own value objects.

## Expected first-run state

`commerce_ops.step_handlers.strategy.compliance_screen` does not exist, so
every test here is expected to fail on an absent target (`ImportError` at
collection) — failure state 2 per `ai-toolkit:testing`.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

import socket
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
    GateOpening,
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

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
OTHER_PRODUCT_NAME: Final = "Stainless Steel Insulated Water Bottle, 750 ml"

DESCRIPTION: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)

CLEAR_COMMENT: Final = (
    "Considered each named heading: nothing about this item is ingestible, "
    "pressurised or battery-powered, so none applies."
)
FLAGGED_COMMENT: Final = "This falls under one of the named headings."
UNDETERMINED_COMMENT: Final = "The name alone does not settle this."


# ---------------------------------------------------------------------------
# Scripting the model's structured answer
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids.

    A distinct type so that the failure tests below can tell a fault the
    screen surfaced from a fault in how it reached the model.
    """


@dataclass(frozen=True)
class _Answer:
    verdict: str
    comment: str | None


@dataclass(frozen=True)
class _Raise:
    """Script value: the structured call itself fails."""

    failure: Exception


@dataclass(frozen=True)
class _RawPayload:
    """Script value: the structured call yields something that is not the
    `raw`/`parsed`/`parsing_error` dict `include_raw=True` contracts to."""

    payload: Any


#: Script value: the call completed and validated against nothing.
_NO_PARSE: Final = object()


class _ScriptedStructuredRunnable:
    def __init__(self, script: Any, schema: Any) -> None:
        self._script = script
        self._schema = schema
        self.received: list[Any] = []

    def _answer(self) -> Any:
        if isinstance(self._script, _Raise):
            raise self._script.failure
        if isinstance(self._script, _RawPayload):
            return self._script.payload
        if self._script is _NO_PARSE:
            return {
                "raw": AIMessage(content="not a recognisable verdict"),
                "parsed": None,
                "parsing_error": ValueError("could not validate against the schema"),
            }
        assert isinstance(self._script, _Answer)
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._schema(
                verdict=self._script.verdict, comment=self._script.comment
            ),
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> Any:
        raise _WrongSeam(
            "the screen reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)`"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> Any:
        self.received.append(input_)
        return self._answer()


class _ScriptedStructuredChatModel(BaseChatModel):
    script: ClassVar[Any] = None
    runnable: ClassVar[_ScriptedStructuredRunnable | None]

    def __init__(self, script: Any) -> None:
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

    # Cleared on every install, not only once per test: several tests below
    # invoke the screen twice, and a cached graph would let the first
    # invocation's stubbed model answer the second.
    _clear_graph_caches()
    monkeypatch.setattr(screen, "build_production_graph", factory)


@pytest.fixture
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Establish "performs no lookup of its own" rather than assume it.

    The scenario's THEN is that the screen fetches nothing — no product, no
    playbook, no category taxonomy. Every such fetch in this deployment
    crosses a socket, so refusing sockets is what turns the claim into an
    observation.
    """

    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "the screen opened a network connection; it is required to read "
            "the product and the step from the context it is given and "
            "fetch nothing of its own"
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


# ---------------------------------------------------------------------------
# The context the handler is invoked with
# ---------------------------------------------------------------------------

CONFIRMATION_GATES: Final = frozenset(
    {"commit", "order", "phase-one-complete", "graduated"}
)

STEP_ID: Final = "lp.strategy.006"
ALICE: Final = "prs_01HQ8Z6M4A"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
LAUNCH_DATE: Final = date(2027, 3, 2)
PRODUCT_ID: Final = ProductId(str(uuid.uuid4()))

SKU_VALUE: Final = "HZM-2027-01"
MARKETPLACE_VALUE: Final = "ATVPDKIKX0DER"


class _CatalogProduct:
    """Stands in for the catalog product the pass supplies.

    A plain class rather than a dataclass, because
    `catalog.domain.product.Product` is one too: stringifying it yields
    `<... object at 0x...>` here exactly as it would in production. `sku`
    and `marketplace_id` are the codebase's real value objects, so an
    implementation reaching for `!r` on one leaks a real rendering rather
    than a rendering this file invented.
    """

    def __init__(self, name: str = PRODUCT_NAME) -> None:
        self.id = PRODUCT_ID
        self.name = name
        self.sku = Sku(SKU_VALUE)
        self.marketplace_id = MarketplaceId(MARKETPLACE_VALUE)
        self.sub_category: str | None = None


def _opening_for(identifier: str) -> GateOpening:
    if identifier in CONFIRMATION_GATES:
        return GateOpening.REQUIRES_CONFIRMATION
    return GateOpening.AUTOMATIC


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


def _context(product: Any = None, **step_overrides: Any) -> StepContext:
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


def _prompt_text(model: _ScriptedStructuredChatModel) -> str:
    runnable = model.runnable
    assert runnable is not None and runnable.received, (
        "the screen never reached the model, so there is no prompt to read"
    )
    messages = runnable.received[-1]
    if isinstance(messages, list | tuple):
        return "\n".join(str(getattr(item, "content", item)) for item in messages)
    return str(getattr(messages, "content", messages))


async def _screen_with(
    script: Any,
    monkeypatch: pytest.MonkeyPatch,
    *,
    product: Any = None,
    **step_overrides: Any,
) -> tuple[Any, _ScriptedStructuredChatModel]:
    model = _ScriptedStructuredChatModel(script)
    _install_stub_graph(monkeypatch, model)
    resolution = await _handler()(_context(product=product, **step_overrides))
    return resolution, model


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# Requirement: Model failure is surfaced, not masked
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_failing_model_call_surfaces_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A failing model call surfaces as a failure.

    WHEN the configured language model is unavailable or returns an error
    while the screen is producing a verdict
    THEN the invocation fails visibly, no outcome is proposed, and the
    failure is not recorded as a verdict about the product.

    SPECIFIED: the exception leaves the handler, so no `StepResolution`
    exists to be recorded. `pytest.raises` is what establishes "no outcome
    is proposed" — a handler that caught the fault would return one and
    this test would fail with nothing raised at all.

    Asserted as **propagation**, deliberately, rather than as a
    caught-and-reported path. This is the test that stops a later broad
    `except` routing an outage into the unreadable-verdict reason, which is
    the adjacent route and the whole reason the requirement exists.
    """
    fault = RuntimeError("the model provider is unavailable")
    model = _ScriptedStructuredChatModel(_Raise(fault))
    _install_stub_graph(monkeypatch, model)

    with pytest.raises(Exception) as raised:
        await _handler()(_context())

    assert not isinstance(raised.value, _WrongSeam), (
        "the screen failed on how it reached the model, not on the fault "
        f"this test scripted: {raised.value!r}"
    )
    # DERIVED: that the scripted fault itself is what surfaced, rather than
    # some later error the screen produced while mishandling it. The delta
    # says the failure surfaces, not that it surfaces unwrapped, so the
    # chain is searched rather than the exception compared by identity.
    chain: list[BaseException] = []
    current: BaseException | None = raised.value
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    assert fault in chain, (
        "the model fault did not surface; something else was raised in its "
        f"place: {raised.value!r}"
    )


@pytest.mark.anyio
async def test_response_content_that_is_not_a_plain_string_surfaces_as_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Response content that is not a plain string surfaces as a
    failure.

    WHEN the configured language model's response content is not a plain
    string
    THEN the invocation fails visibly rather than yielding a verdict
    coerced or fabricated from that content.

    SPECIFIED, on the reading recorded in this file's header: the
    structured-output call yields something other than the
    `raw`/`parsed`/`parsing_error` dict, so there is no verdict to read and
    no text to present. It must not be coerced into one, and — since the
    requirement says such a failure "SHALL NOT be routed to the
    unreadable-verdict path" — it must not become a non-terminal outcome
    either.
    """
    model = _ScriptedStructuredChatModel(
        _RawPayload(AIMessage(content=[{"type": "text", "text": "clear"}]))
    )
    _install_stub_graph(monkeypatch, model)

    with pytest.raises(Exception) as raised:
        await _handler()(_context())

    assert not isinstance(raised.value, _WrongSeam), (
        "the screen failed on how it reached the model, not on the response "
        f"this test scripted: {raised.value!r}"
    )


@pytest.mark.anyio
async def test_a_model_failure_is_not_routed_to_the_unreadable_verdict_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Requirement statement: "Such a failure SHALL NOT be routed to the
    unreadable-verdict path, nor to any other non-terminal outcome."

    SPECIFIED, and stated as its own test so that the prohibition is
    legible by name. A broad `except` around the model call lands in the
    adjacent unreadable-verdict route, which produces a perfectly
    well-formed non-terminal outcome — the two tests above would then fail
    with "DID NOT RAISE", which says the exception escaped but not why that
    matters. This one says it: an outage entered on the launch's own record
    as the screen's judgement about a product.
    """
    unreadable, _ = await _screen_with(_NO_PARSE, monkeypatch)
    assert isinstance(getattr(unreadable, "outcome", None), Blocked), (
        "the unreadable-verdict route did not produce a non-terminal "
        f"outcome, so this test cannot establish what it is about: {unreadable!r}"
    )

    model = _ScriptedStructuredChatModel(_Raise(RuntimeError("connection reset")))
    _install_stub_graph(monkeypatch, model)

    resolution: Any = None
    try:
        resolution = await _handler()(_context())
    except Exception:  # noqa: BLE001 -- the specified behaviour, asserted below
        return

    pytest.fail(
        "a model transport fault was caught by the screen and turned into a "
        f"proposal instead of surfacing: {resolution!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: The screen reads only what it is given, and reports no
# finding
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@pytest.mark.usefixtures("_no_network")
async def test_the_product_is_taken_from_the_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The product is taken from the context.

    WHEN the screen is invoked for a step on a launch
    THEN it screens the product its context carries, and performs no lookup
    of its own.

    SPECIFIED: both halves. The first is asserted by giving two contexts
    two different products and reading what reached the model each time —
    a screen fetching a product of its own would send the same one twice.
    The second is established by refusing sockets for the duration, since
    every fetch this deployment could make crosses one.
    """
    _, first = await _screen_with(_Answer("clear", CLEAR_COMMENT), monkeypatch)
    _, second = await _screen_with(
        _Answer("clear", CLEAR_COMMENT),
        monkeypatch,
        product=_CatalogProduct(name=OTHER_PRODUCT_NAME),
    )

    assert PRODUCT_NAME in _prompt_text(first), (
        f"the context's product did not reach the model: {_prompt_text(first)!r}"
    )
    assert OTHER_PRODUCT_NAME in _prompt_text(second), (
        "the second context's product did not reach the model, so the screen "
        f"is not screening what it was given: {_prompt_text(second)!r}"
    )
    assert PRODUCT_NAME not in _prompt_text(second), (
        "the first invocation's product still reaches the model on the "
        f"second: {_prompt_text(second)!r}"
    )


@pytest.mark.anyio
async def test_a_value_reaching_the_model_is_the_value_not_its_rendering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A value reaching the model is the value, not its object's
    rendering.

    WHEN the screen passes on a value the product carries as a value object
    THEN what reaches the model is that object's value, carrying nothing of
    the object's rendering — neither its type name, nor its field name, nor
    the quoting around its value.

    SPECIFIED: the three things the THEN forbids, asserted as the three
    renderings this codebase's own value objects produce. The failure this
    guards is silent — the model answers plausibly whatever it was asked,
    so a malformed product value produces a well-formed verdict and nothing
    anywhere reports that the screen was asked about something that does
    not exist. `subcategory_advisor` paid this lesson once
    (`MarketplaceId(value='ATVPDKIKX0DER')` reached both the prompt and the
    reason recorded on the launch); this is what stops it being re-paid.

    DERIVED: the token list. The delta names the three *kinds* of leak;
    which literal strings those are here follows from `shared.domain
    .identity`'s dataclasses and from `Product` being a plain class.
    """
    _, model = await _screen_with(_Answer("clear", CLEAR_COMMENT), monkeypatch)
    prompt = _prompt_text(model)

    leaks = [
        token
        for token in (
            "MarketplaceId(",  # a type name
            "Sku(",
            "ProductId(",
            "_CatalogProduct(",
            "value=",  # a field name
            f"'{MARKETPLACE_VALUE}'",  # the quoting around a value
            f'"{MARKETPLACE_VALUE}"',
            f"'{SKU_VALUE}'",
            "object at 0x",  # the whole product, stringified
        )
        if token in prompt
    ]
    assert leaks == [], (
        f"the prompt carries a value object's rendering rather than its "
        f"value: {leaks} in {prompt!r}"
    )


# REMOVED by `screen-for-hazard-categories`: `test_no_finding_accompanies_
# the_outcome` stood here, deriving from the scenario *No finding
# accompanies the outcome* of the requirement *The screen reads only what
# it is given, and reports no finding*. That requirement is REMOVED by that
# change's delta, with its Reason and Migration recorded there: the screen
# now reports a finding on the two routes that establish something about
# the product, so the test asserted the opposite of the specification for
# its `clear` and `flagged` rows.
#
# Its `undetermined` row remains true and is covered by
# `test_an_undetermined_verdict_establishes_nothing`; the two rows that
# changed are covered by `test_a_clear_verdict_establishes_an_empty_set_of_
# categories` and `test_a_flagged_verdict_establishes_the_categories_it_
# named`, and the flagged-naming-nothing case by
# `test_a_flagged_verdict_naming_nothing_is_not_recorded_as_flagged` -- all
# four in `test_compliance_screen_hazard_finding.py`. Nothing it asserted
# is now unasserted.


@pytest.mark.anyio
async def test_no_finding_accompanies_an_unreadable_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario, on the route that reaches no verdict at all.

    SPECIFIED by the scenario's "any verdict", read to include the states
    the requirements above route to a non-terminal outcome without one.
    """
    resolution, _ = await _screen_with(_NO_PARSE, monkeypatch)

    assert getattr(resolution, "finding", None) is None, (
        f"an unreadable verdict reported a typed finding: "
        f"{getattr(resolution, 'finding', None)!r}"
    )


# ---------------------------------------------------------------------------
# Requirement: The screen is reached only through the step it is authored
# onto
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_screen_does_not_test_which_step_invoked_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The screen does not test which step invoked it.

    WHEN the screen is invoked for a step whose identifier and discipline
    are not the ones it was written for, and which names categories in its
    description
    THEN it screens against that step's categories and proposes an outcome,
    refusing nothing on the basis of the step's identifier, discipline or
    gate.

    SPECIFIED: all three properties are changed at once — identifier,
    discipline **and** gate — since a screen testing any one of them would
    refuse here, and the requirement forbids testing any of them. Which
    step the screen runs for is a property of the authored playbook and
    never of the screening code.
    """
    resolution, model = await _screen_with(
        _Answer("clear", CLEAR_COMMENT),
        monkeypatch,
        identifier="lp.finance.042",
        discipline=Discipline.FINANCE,
        gate="order",
    )

    assert getattr(resolution, "outcome", None) is Satisfied, (
        "the screen refused a step on the basis of its identifier, "
        f"discipline or gate: {resolution!r}"
    )
    assert DESCRIPTION in _prompt_text(model), (
        "the screen did not screen against the invoking step's categories: "
        f"{_prompt_text(model)!r}"
    )
    assert DESCRIPTION in str(getattr(resolution, "result", "")), (
        "the produced text does not cite the invoking step's categories: "
        f"{getattr(resolution, 'result', None)!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - That `launch-step-automation` reports the raising handler naming the
#   launch, step and handler, records nothing, and continues the pass. That
#   is that capability's own requirement, already covered by its own tests;
#   this file establishes only that the screen gives it something to
#   report.
# - Whether the screen would fetch a *playbook* or a *category taxonomy* by
#   some route that opens no socket. `_no_network` covers every fetch this
#   deployment can make; an in-process one is not a state any artifact
#   describes.
# ---------------------------------------------------------------------------
