"""The widened structured-output schema, at the provider adapter's own
conversion boundary (`compliance-screen`).

Derived strictly from the delta spec of the change
`screen-for-hazard-categories`:
`openspec/changes/screen-for-hazard-categories/specs/compliance-screen/spec.md`

## What this file covers, and what it does not

**No scenario in this change's delta is schema-shaped.** *The
structured-output schema is one the model provider's adapter accepts* and
*Wire fields state when they are to be populated* take no delta —
`design.md` Decision 2 is explicit that adding a field "changes nothing
about what that requirement asks, so it is not modified".

What this file does is what `tasks.md` 1.6 and 1.7 ask for: **re-exercise
those unchanged requirements over the widened schema**, so that the new
field is established to be inside the provider's accepted subset rather
than reasoned to be. `design.md` names the risk in as many words: "a
widened wire schema is a new chance to fall outside the provider's strict
subset … the risk is that someone adds the field without extending the
guard's coverage".

Every assertion here is therefore classified **DERIVED from `tasks.md`
1.6-1.7 and `design.md` Decision 2**, not SPECIFIED by a scenario in this
change — except the two that restate the unchanged requirement's own
scenarios (*The schema is accepted by the provider's own conversion*,
*Wire fields state when they are to be populated*), which are SPECIFIED by
the served `compliance-screen` spec.

A **separate file** from
`tests/unit/step_handlers/strategy/test_compliance_screen_schema_conversion.py`,
which this pass does not edit. That file asserts
`set(properties) == {"verdict", "comment"}` and is **superseded** by this
change: see the obsolete-tests section of `test-manifest.md`.

## Level

The unit tier, over a schema object obtained from the screen's own
`with_structured_output(...)` call site through the `build_graph(model)`
seam — never by importing a wire symbol, since a guard converting a
symbol the call site had stopped using would guard nothing. No model is
invoked, no socket is opened and no credential is present while the
conversion runs; each of those is established rather than asserted in
prose.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 4.1: the third field name `categories`, required,
carrying a description; and that the schema stays flat with no union
added.

Fixed by `design.md` Decision 2: that a `list[str]` "emits `{"type":
"array", "items": {"type": "string"}}`, which is inside that subset and
introduces no union at all", and that a per-verdict variant is rejected
because "pydantic emits `oneOf` for a tagged union and OpenAI's strict
structured outputs accept only `anyOf`".

INVENTED, recorded in `test-manifest.md`: the capturing harness, the
private conversion functions named directly (the same deliberate,
recorded trade the existing guard makes — they are the exact functions
that failed in production), and the no-network / no-credential fixtures.

## Expected first-run state

`ScreenResponse` carries no `categories` field (`tasks.md` 4.1), so the
field-shaped tests here are expected to fail on an absent target — the
converted schema has two properties where three are asserted. The
conversion-succeeds and no-`oneOf` tests are expected to **pass on first
run**, because the two-field schema already satisfies them; that is the
expected result for a re-exercised requirement and is recorded rather
than hidden. They become discriminating the moment the field lands.

Baseline recorded before these tests were written, at this worktree root
on 2026-09-03: `uv run pytest tests/unit tests/agents` — 2352 passed, 0
failed, 0 skipped; `uv run pytest tests/integration` — 152 passed, 0
failed, 0 skipped.
"""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime
from types import UnionType
from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai.chat_models.base import _convert_to_openai_response_format

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
from commerce_ops.shared.domain.identity import MarketplaceId, Sku
from tests.support.fixtures import ALICE, LAUNCH_DATE, product_id
from tests.support.playbook import SPECIFIED_GATE_ORDER
from tests.support.playbook import gates as _gates

#: Fixed by `tasks.md` 4.1, not by any delta scenario: the wire schema's
#: three field names after this change.
WIRE_FIELDS: Final = ("verdict", "categories", "comment")
CATEGORIES_FIELD: Final = "categories"
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
    schemas: ClassVar[list[Any]]

    def __init__(self) -> None:
        super().__init__()
        object.__setattr__(self, "schemas", [])

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
        self.schemas.append(schema)
        return _CapturingRunnable()

    @property
    def _llm_type(self) -> str:
        return "categories-schema-capturing-fake-chat-model"


# ---------------------------------------------------------------------------
# The context the screen is invoked with
# ---------------------------------------------------------------------------

STEP_ID: Final = "lp.strategy.006"
AS_OF: Final = datetime(2027, 1, 6, 9, 30, tzinfo=UTC)
PRODUCT_ID: Final = product_id()


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
# Capture from the call site, then convert
# ---------------------------------------------------------------------------


async def _the_schema_the_call_site_passes(monkeypatch: pytest.MonkeyPatch) -> Any:
    model = _CapturingChatModel()
    _clear_graph_caches()
    monkeypatch.setattr(
        screen, "build_production_graph", lambda: screen.build_graph(model)
    )
    screen.build_graph(model)
    if not model.schemas:
        handler = HANDLERS.resolve(screen.HANDLER_NAME)
        assert handler is not None, (
            f"no step handler is registered under {screen.HANDLER_NAME!r}"
        )
        try:
            await handler(_context())
        except _WrongSeam:
            raise
        except Exception as failure:
            if not model.schemas:
                raise AssertionError(
                    "the screen never reached its structured-output call "
                    f"site, so no schema could be captured: {failure!r}"
                ) from failure
    assert model.schemas, (
        "the screen never called `with_structured_output(...)`, so there is "
        "no schema to convert"
    )
    return model.schemas[0]


def _convert_the_way_the_adapter_does(schema: Any) -> dict[str, Any]:
    """Both conversions `ChatOpenAI`'s `json_schema` path performs."""
    _convert_to_openai_response_format(schema, strict=None)
    converted: dict[str, Any] = convert_to_openai_tool(schema)
    return converted


def _properties_of(converted: dict[str, Any]) -> dict[str, Any]:
    properties = converted["function"]["parameters"]["properties"]
    assert isinstance(properties, dict), (
        f"the converted schema exposes no properties mapping: {converted!r}"
    )
    return properties


@pytest.fixture
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _refuse(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError(
            "the schema-conversion guard opened a network connection; the "
            "requirement it re-exercises needs none"
        )

    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


@pytest.fixture
def _no_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in CREDENTIAL_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


# ---------------------------------------------------------------------------
# The widened schema is still one the adapter accepts (`tasks.md` 1.6)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_widened_schema_is_accepted_by_the_providers_own_conversion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*The structured-output schema is one the model provider's adapter
    accepts*, re-exercised over the widened schema.

    Both halves of the `json_schema` path's conversion, since fixing only
    one would leave the other failing. The no-model / no-network /
    no-credential clause is established rather than described.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    _convert_to_openai_response_format(schema, strict=None)
    convert_to_openai_tool(schema)


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_widened_schema_is_not_a_union_the_adapter_rejects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same requirement in the direction the sibling handler's defect
    ran: a top-level union is rejected before the model is ever called.

    `design.md` Decision 2 rejects a per-verdict variant for exactly this
    reason — "the obvious modelling — categories present only when flagged
    — is a tagged union, which is the construct that made `lp.listing.007`
    inert in production".
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    assert not isinstance(schema, UnionType), (
        f"the screen passes a top-level union at its call site: {schema!r}"
    )
    assert isinstance(schema, type), (
        f"the screen passes something that is not a single schema type: {schema!r}"
    )


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_widened_converted_schema_emits_no_oneof_anywhere(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 1.6: "asserting **no `oneOf` anywhere**".

    The whole converted document is searched, not only its top level: a
    `categories` field modelled as a union of shapes, or as an enum of
    variants, would nest one where the top level stays flat.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)

    assert "oneOf" not in json.dumps(converted), (
        "the converted schema emits `oneOf`, which OpenAI's strict "
        f"structured outputs do not support: {converted!r}"
    )


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_categories_field_is_an_array_of_plain_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`tasks.md` 1.6: "that `categories` is an array of plain strings".

    Asserted as the provider's own conversion emits it — the form the
    model actually receives — rather than as pydantic's internals.
    `design.md` Decision 2 fixes the emitted shape exactly: `{"type":
    "array", "items": {"type": "string"}}`.

    The `$ref` clause matters: an items schema that is a reference to a
    separate definition is what an enum or a nested model produces, and it
    is not a plain string however it reads at the pydantic level.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)
    properties = _properties_of(converted)

    assert CATEGORIES_FIELD in properties, (
        f"the wire schema has no {CATEGORIES_FIELD!r} field: {sorted(properties)}"
    )
    categories = properties[CATEGORIES_FIELD]
    assert categories.get("type") == "array", (
        f"the {CATEGORIES_FIELD!r} property is not an array: {categories!r}"
    )
    items = categories.get("items")
    assert isinstance(items, dict), (
        f"the {CATEGORIES_FIELD!r} property declares no item schema: {categories!r}"
    )
    assert items.get("type") == "string", (
        f"the {CATEGORIES_FIELD!r} property's items are not plain strings: {items!r}"
    )
    assert "$ref" not in items, (
        f"the {CATEGORIES_FIELD!r} property's items are a reference to a "
        f"separate definition rather than a plain string: {items!r}"
    )
    assert "enum" not in items, (
        f"the {CATEGORIES_FIELD!r} property's items carry an enum, which "
        "would make the vocabulary closed — the delta places the naming "
        f"obligation on the prompt and forbids a check on it: {items!r}"
    )


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_verdict_is_still_a_plain_string_carrying_the_three_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The discriminant is unchanged by the widening.

    Re-exercised beside the new field so that a schema rewritten to
    accommodate `categories` cannot quietly turn the verdict into
    something the adapter treats differently.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)
    properties = _properties_of(converted)

    verdict = properties[DISCRIMINANT_FIELD]
    assert verdict.get("type") == "string"
    assert set(verdict.get("enum", ())) == VERDICT_VALUES


# ---------------------------------------------------------------------------
# Wire fields state when they are to be populated (`tasks.md` 1.7)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_every_wire_field_the_new_one_included_carries_a_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """*Wire fields state when they are to be populated*, re-exercised over
    the widened schema.

    SPECIFIED by the served requirement (every field, "the required
    discriminant as well as the optional prose"); the *set* of three names
    is DERIVED from `tasks.md` 4.1.

    The `categories` description is load-bearing rather than decorative:
    `design.md` Decision 2 puts "the coupling to the verdict … in the
    field's own description, which the model reads", so a field added
    without one removes the only place that coupling is stated.

    DELIBERATELY UNTESTED: whether each description in fact says *when* to
    populate the field. Judging that means parsing prose for particular
    content, which this capability's own *A comment's content is never
    checked by code* forbids it doing one field over.
    """
    schema = await _the_schema_the_call_site_passes(monkeypatch)

    converted = _convert_the_way_the_adapter_does(schema)
    properties = _properties_of(converted)

    assert set(properties) == set(WIRE_FIELDS), (
        "the wire schema's fields are not the three `tasks.md` 4.1 fixes: "
        f"{sorted(properties)}"
    )
    for wire_field in WIRE_FIELDS:
        description = properties[wire_field].get("description")
        assert isinstance(description, str) and description.strip(), (
            f"the wire schema's {wire_field!r} field carries no description, "
            "so what it is for and when to populate it is left to the "
            "prompt alone"
        )
