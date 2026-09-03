"""The compliance screen's structured-output schema, at the provider
adapter's own conversion boundary (`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-a-product-for-compliance`:
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`

Covers, from the ADDED requirement *The structured-output schema is one the
model provider's adapter accepts*, three of its four scenarios:

- The schema is accepted by the provider's own conversion
- The converted schema is the one the call site passes
- Wire fields state when they are to be populated

The requirement's fourth scenario, *Every wire combination has a defined
destination*, is behavioural rather than schema-shaped and is covered by
the verdict table in
`tests/agents/step_handlers/strategy/test_compliance_screen_verdict_routing.py`.
`tasks.md` 1.1 and 1.2. See `test-manifest.md` at the change root for the
full accounting.

## Level

The unit tier, per `tasks.md` 1.1 and `design.md`'s *The conversion guard
is replicated, not shared*: this asserts a library contract over a schema
object, not graph behaviour. It runs the screen only far enough to reach
the call site that hands the schema over — the model is a fake that
refuses to generate, no socket is opened (asserted, not assumed), and no
credential is present in the environment while it runs (also asserted).

This is the check whose absence let a 100%-failure regression ship for the
sibling handler: every test of it scripted `with_structured_output(...)`
directly, so the real conversion was never invoked by anything. This
screen introduces a construct the sibling's schema does not have — a
discriminant of three named values — and `design.md` is explicit that
reasoning a construct is inside a provider's accepted subset is exactly
the reasoning that failed last time.

**Not shared with the sibling's guard, and not parameterised over both.**
The value of the test is that it converts *the schema the call site
passes*; a shared harness invited to take a schema as a parameter is one
refactor away from testing a schema no call site uses (`design.md`).

## What is fixed, and what is INVENTED

Fixed by `design.md`'s Context and verified against the installed
libraries (`langchain_openai` 1.6.0, `langchain_core` 1.6.0): the
`json_schema` path of `ChatOpenAI.with_structured_output` converts the
schema twice, through
`langchain_openai.chat_models.base._convert_to_openai_response_format` and
through `langchain_core.utils.function_calling.convert_to_openai_tool`.
Naming the private function is the same deliberate, recorded trade the
sibling's guard makes: it is the exact function that failed in production,
and an upgrade renaming it should break this test loudly.

Fixed by `tasks.md` 2.3: the wire model's two field names — `verdict` and
`comment` — and the three literal verdict values. The delta names the three
states but no field, so the field names trace to `tasks.md` rather than to
a scenario.

Fixed by `design.md`'s *One enum discriminant for three states*: pydantic
emits a plain object with a string property carrying `enum`, and **no
union appears anywhere in it, at the top level or nested** — the `oneOf`
assertion below is that claim, asserted rather than argued.

INVENTED, recorded in `test-manifest.md`:

- `_CapturingChatModel` / `_CapturingRunnable`, and `_install_stub_graph`
  as the way the call site is reached. Duplicated rather than shared, per
  this project's separate-file convention for handler tests.
- `_DivergentShape`, a local pydantic model used only to construct the
  rejected union the divergence probe drives through the same mechanism.
  It exists so this file can name **no** symbol of the screen's own wire
  schema — obtaining it from the call site is the whole point.
- `_no_network` / `_no_credential` as the way the scenario's "without
  invoking a model, opening a network connection, or supplying a
  credential" clause is *established* rather than merely asserted in prose.

## Expected first-run state

`commerce_ops.step_handlers.strategy.compliance_screen` does not exist, so
every test here is expected to fail on an absent target (`ImportError` at
collection) — failure state 2 per `ai-toolkit:testing`, establishing
absence only. Once the module exists but before `tasks.md` 2.3 lands with
the right shape, these move into failure state 1.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 2090 passed, 0 failed, 0 skipped.
"""

from __future__ import annotations

import json
import socket
import uuid
from datetime import UTC, date, datetime
from types import UnionType
from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai.chat_models.base import _convert_to_openai_response_format
from pydantic import BaseModel

import commerce_ops.step_handlers.strategy.compliance_screen as screen
from commerce_ops.launch.application import HANDLERS, StepContext
from commerce_ops.launch.domain.launch_playbook import (
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
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

# Fixed by `tasks.md` 2.3, not by any delta scenario. `categories` was
# added by `screen-for-hazard-categories` (`tasks.md` 4.1): the wire gained
# a third field, so the set this test compares against gained one too. The
# assertion is unchanged and is still set equality -- a fourth field
# appearing unannounced still fails it.
WIRE_FIELDS: Final = ("verdict", "categories", "comment")
DISCRIMINANT_FIELD: Final = "verdict"
VERDICT_VALUES: Final = frozenset({"clear", "flagged", "undetermined"})

CREDENTIAL_VARIABLES: Final = (
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_API_KEY",
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
DESCRIPTION: Final = (
    "Screen against the FBA-prohibited hazmat list and high-compliance "
    "categories (furniture, medical devices, supplements, grills, fire pits, "
    "balloons, lighters, CO detectors) before sourcing"
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model that records the schema its structured-output seam is given
# ---------------------------------------------------------------------------


class _WrongSeam(AssertionError):
    """The screen reached the model by a path this file forbids."""


class _CapturingRunnable:
    """What `with_structured_output(..., include_raw=True)` returns.

    Answers with a response that validates against nothing, so the screen
    takes its "no verdict could be read" route and returns normally.
    Nothing here depends on that route's behaviour — this file only needs
    the call site to have run.
    """

    def __init__(self) -> None:
        self.received: list[Any] = []

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        raise _WrongSeam(
            "the screen reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)`"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return {
            "raw": AIMessage(content="not a recognisable verdict"),
            "parsed": None,
            "parsing_error": ValueError("could not validate against the schema"),
        }


class _CapturingChatModel(BaseChatModel):
    """Records every schema handed to `with_structured_output(...)`.

    `_generate` and `bind_tools` raise, so a screen that reached the model
    any other way fails loudly rather than leaving `schemas` empty for an
    unrelated reason.
    """

    schemas: ClassVar[list[Any]]
    requested_include_raw: ClassVar[Any]

    def __init__(self) -> None:
        super().__init__()
        object.__setattr__(self, "schemas", [])
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
        self.schemas.append(schema)
        object.__setattr__(self, "requested_include_raw", include_raw)
        return _CapturingRunnable()

    @property
    def _llm_type(self) -> str:
        return "schema-capturing-fake-chat-model"


class _DivergentShape(BaseModel):
    """Only ever used to build the union the divergence probe rejects.

    Local so that this file names no symbol of the screen's own wire
    schema: obtaining that from the call site is what the second scenario
    below requires.
    """

    reason: str


# ---------------------------------------------------------------------------
# The context the screen is invoked with
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


def _context() -> StepContext:
    playbook = LaunchPlaybook(
        version="test-v1",
        gates=_gates(),
        steps=(_step(), *(_hold(gate) for gate in SPECIFIED_GATE_ORDER)),
    )
    launch, _ = Launch.start(
        product_id=PRODUCT_ID, playbook=playbook, launch_date=LAUNCH_DATE
    )
    return StepContext(
        step=_step(), launch=launch, product=_CatalogProduct(), as_of=AS_OF
    )


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
# The guard's own mechanism: capture from the call site, then convert
# ---------------------------------------------------------------------------


async def _schemas_the_call_site_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> list[Any]:
    """Every schema the screen's own call site handed the model.

    Obtained from the call site — never by importing a module-level symbol
    — which is what *The converted schema is the one the call site passes*
    requires. `build_graph(model)` may or may not reach the call site on
    its own; where it does not, the registered handler is invoked so the
    node holding the call executes.
    """
    model = _CapturingChatModel()
    _clear_graph_caches()
    monkeypatch.setattr(
        screen, "build_production_graph", lambda: screen.build_graph(model)
    )
    screen.build_graph(model)
    if not model.schemas:
        handler = HANDLERS.resolve(screen.HANDLER_NAME)
        assert handler is not None, (
            f"no step handler is registered under {screen.HANDLER_NAME!r}, so "
            "the call site cannot be reached"
        )
        try:
            await handler(_context())
        except _WrongSeam:
            # Never swallowed, whether or not a schema was captured. The
            # schema is recorded by `with_structured_output(...)`, which
            # runs *before* the model is called, so `model.schemas` is
            # already populated by the time any of this file's guards fire
            # — tolerating the exception on a non-empty `schemas` would
            # swallow every one of them and leave the sync-`invoke` guard
            # inert while its comment claimed otherwise.
            raise
        except Exception as failure:
            if not model.schemas:
                raise AssertionError(
                    "the screen never reached its structured-output call "
                    f"site, so no schema could be captured: {failure!r}"
                ) from failure
    return list(model.schemas)


async def _the_schema_the_call_site_passes(monkeypatch: pytest.MonkeyPatch) -> Any:
    captured = await _schemas_the_call_site_passed(monkeypatch)
    assert captured, (
        "the screen never called `with_structured_output(...)`, so there is "
        "no schema to convert"
    )
    return captured[0]


def _convert_the_way_the_adapter_does(schema: Any) -> dict[str, Any]:
    """Both conversions `ChatOpenAI`'s `json_schema` path performs.

    `strict=None` is what the adapter passes when the caller supplies no
    `strict` argument, which the screen does not.
    """
    _convert_to_openai_response_format(schema, strict=None)
    converted: dict[str, Any] = convert_to_openai_tool(schema)
    return converted


def _properties_of(converted: dict[str, Any]) -> dict[str, Any]:
    properties = converted["function"]["parameters"]["properties"]
    assert isinstance(properties, dict), (
        f"the converted schema exposes no properties mapping: {converted!r}"
    )
    return properties


# ---------------------------------------------------------------------------
# Establishing the scenario's "no model, no network, no credential" clause
# ---------------------------------------------------------------------------


@pytest.fixture
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "the schema-conversion guard opened a network connection; the "
            "scenario requires it to need none"
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture
def _no_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in CREDENTIAL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


# ---------------------------------------------------------------------------
# Scenario: The schema is accepted by the provider's own conversion
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_schema_is_accepted_by_the_providers_own_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The schema is accepted by the provider's own conversion.

    WHEN the schema the screen passes at its structured-output call site is
    converted by the model provider's adapter
    THEN the conversion succeeds, and this is verified without invoking a
    model, opening a network connection, or supplying a credential.

    SPECIFIED: the adapter's *own* conversion, not a stand-in — both halves
    of it, since the `json_schema` path converts twice and fixing only one
    would leave the other failing.

    The no-model / no-network / no-credential half of the THEN is
    established rather than described: the fake model's `_generate` raises,
    `socket.connect` raises, and every credential variable is removed from
    the environment for the duration of this test.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    _convert_to_openai_response_format(schema, strict=None)
    convert_to_openai_tool(schema)


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_schema_is_not_a_union_the_adapter_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same scenario, asserted in the direction the sibling's defect
    ran.

    SPECIFIED by the requirement's own rationale: a top-level union is
    rejected by the adapter before the model is ever called, which made the
    sibling handler inert at 100% of invocations. Stated as a separate test
    so that a regression to a union is legible by name rather than as a
    bare `ValueError` from the test above.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    assert not isinstance(schema, UnionType), (
        "the screen passes a top-level union at its structured-output call "
        f"site, which the provider adapter rejects: {schema!r}"
    )
    assert isinstance(schema, type), (
        "the screen passes something that is not a single schema type, so "
        f"the adapter falls through to `convert_to_openai_function`: {schema!r}"
    )


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_converted_schema_emits_no_oneof_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED by `design.md`'s *One enum discriminant for three states*,
    which this requirement's rationale invokes directly: a `BaseModel`
    wrapping a discriminated union "would have passed every offline check
    and failed at the API instead, because pydantic emits `oneOf` for a
    tagged union and OpenAI's strict structured outputs accept only
    `anyOf`".

    The whole converted document is searched, not only its top level: the
    claim `design.md` makes is that no union appears "anywhere in it, at
    the top level or nested".
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)

    assert "oneOf" not in json.dumps(converted), (
        "the converted schema emits `oneOf`, which OpenAI's strict "
        f"structured outputs do not support: {converted!r}"
    )


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_verdict_is_a_plain_string_carrying_the_three_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SPECIFIED by the requirement's rationale — "a discriminant of three
    named values rather than a boolean" — with the field name and the three
    values fixed by `tasks.md` 2.3.

    The construct is asserted as the provider's own conversion emits it,
    which is the form the model actually receives: a **plain string
    property carrying an `enum`**, not a nested union, not a `$ref` to a
    separate definition. `design.md` names exactly this as the claim that
    "read as true before `fix-subcategory-advisor-structured-output` and
    was not", so it is asserted at the boundary rather than reasoned about.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)
    properties = _properties_of(converted)

    assert DISCRIMINANT_FIELD in properties, (
        f"the wire schema has no {DISCRIMINANT_FIELD!r} field: {sorted(properties)}"
    )
    verdict = properties[DISCRIMINANT_FIELD]
    assert verdict.get("type") == "string", (
        f"the {DISCRIMINANT_FIELD!r} property is not a plain string: {verdict!r}"
    )
    assert set(verdict.get("enum", ())) == VERDICT_VALUES, (
        f"the {DISCRIMINANT_FIELD!r} property does not carry exactly the "
        f"three verdicts the delta names: {verdict!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: The converted schema is the one the call site passes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_guard_obtains_its_schema_from_the_call_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: The converted schema is the one the call site passes.

    WHEN the screen's structured-output call site passes a schema other
    than the one a guard converts
    THEN that divergence is detectable, since the guard obtains its schema
    from the call site rather than by importing a symbol independently.

    Asserted as the property the guard's mechanism has: everything it
    converts arrives through `with_structured_output(...)`, recorded by the
    fake at the moment the screen calls it. This module imports no wire
    symbol at all — a guard that converted a symbol the call site had
    stopped using would guard nothing.
    """
    captured = await _schemas_the_call_site_passed(monkeypatch)

    assert captured, (
        "nothing was captured at the call site, so this guard would be "
        "converting a symbol rather than what the screen passes"
    )
    assert len(captured) == 1 or all(item is captured[0] for item in captured), (
        "the screen passed more than one distinct schema to "
        f"`with_structured_output(...)`: {captured!r}"
    )


@pytest.mark.anyio
async def test_a_diverging_call_site_is_detected_by_the_same_mechanism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other half of the same scenario: the mechanism discriminates.

    A guard that captures from the call site is only worth having if a call
    site passing a schema the adapter rejects actually fails it. The
    guard's own capture-then-convert mechanism is run over a stand-in call
    site passing a union of the screen's real wire model and a local shape,
    and it raises — so a real call site drifting to that form would be
    caught rather than passing silently.

    SPECIFIED by the scenario's THEN ("that divergence is detectable"). The
    union is the concrete divergence `design.md` records from production.
    """
    real = await _the_schema_the_call_site_passes(monkeypatch)
    diverging_model = _CapturingChatModel()
    diverging_model.with_structured_output(real | _DivergentShape, include_raw=True)
    captured = diverging_model.schemas[-1]

    with pytest.raises(ValueError):
        _convert_to_openai_response_format(captured, strict=None)
    with pytest.raises(ValueError):
        convert_to_openai_tool(captured)


# ---------------------------------------------------------------------------
# Scenario: Wire fields state when they are to be populated
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_wire_fields_state_when_they_are_to_be_populated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: Wire fields state when they are to be populated.

    WHEN the wire schema is generated
    THEN each of its fields carries a description stating what it is for
    and when it is to be populated.

    SPECIFIED: **every** field, "the required discriminant as well as the
    optional prose" — read from the schema as the provider's own conversion
    emits it, which is the form the model actually receives rather than
    pydantic's internals.

    DELIBERATELY UNTESTED: whether each description in fact says *when* to
    populate the field. Judging that would require parsing prose for
    particular content, which this capability's own *A comment's content is
    never checked by code* forbids it doing one field over.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)
    properties = _properties_of(converted)

    assert set(properties) == set(WIRE_FIELDS), (
        "the wire schema's fields are not the two `tasks.md` 2.3 fixes: "
        f"{sorted(properties)}"
    )
    for field in WIRE_FIELDS:
        description = properties[field].get("description")
        assert isinstance(description, str) and description.strip(), (
            f"the wire schema's {field!r} field carries no description, so "
            "what it is for and when to populate it is left to the prompt "
            "alone"
        )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the provider's *API* accepts the schema both local conversions
#   accept. No offline check can establish it; `tasks.md` section 4 gates
#   it on a live invocation after deploy, and `design.md` records it as a
#   risk.
# - Whether the model fills the schema's fields consistently. A quality
#   property of the response, not of the schema.
# ---------------------------------------------------------------------------
