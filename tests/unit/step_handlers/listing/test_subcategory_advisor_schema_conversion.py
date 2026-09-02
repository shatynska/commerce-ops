"""The advisor's structured-output schema, at the provider adapter's own
conversion boundary (`subcategory-advisor`).

Derived strictly from the delta spec of the change
`fix-subcategory-advisor-structured-output`:
`openspec/changes/fix-subcategory-advisor-structured-output/specs/subcategory-advisor/spec.md`

Covers, from the ADDED requirement *The structured-output schema is one
the model provider's adapter accepts*, three of its five scenarios:

- The schema is accepted by the provider's own conversion
- The converted schema is the one the call site passes
- Wire fields state when they are to be populated

The requirement's other two scenarios (*Every wire combination has a
defined destination*, *The reported variants are unchanged by the wire
shape*) are behavioural rather than schema-shaped and are covered in
`tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py`.
See `test-manifest.md` at the change root for the full accounting.

## Level

The unit tier, per `tasks.md` 1.1 and `design.md`'s own placement note:
this asserts a library contract over a schema object, not graph
behaviour. It runs the advisor's graph only to reach the call site that
hands the schema over — the model itself is a fake that refuses to
generate, no socket is opened (asserted, not assumed), and no credential
is present in the environment while it runs (also asserted).

This is the check whose absence let a 100%-failure regression ship: every
existing test of this handler scripts `with_structured_output(...)`
directly, so the real conversion was never invoked by anything.

## What is fixed, and what is INVENTED

Fixed by `design.md`'s Context section and verified against the installed
libraries (`langchain_openai` 1.6.0, `langchain_core` 1.6.0): the
`json_schema` path of `ChatOpenAI.with_structured_output` converts the
schema twice, through
`langchain_openai.chat_models.base._convert_to_openai_response_format` and
through `langchain_core.utils.function_calling.convert_to_openai_tool`,
and a `X | Y` union is rejected by both. Naming the private function is a
deliberate, recorded trade (`design.md`, *The new test converts the schema
the call site passes*): it is the exact function that failed in
production, and a `langchain_openai` upgrade that renames it should break
this test loudly.

Fixed by `tasks.md` 2.1: the wire model's four field names — `ok`,
`value`, `error`, `comment`. The delta itself names no fields, so the
field-name list here traces to `tasks.md` rather than to a scenario.

INVENTED (recorded in `test-manifest.md`):

- `_CapturingChatModel` / `_CapturingRunnable` — no artifact fixes how a
  fake chat model answers the structured-output seam. Duplicated rather
  than shared with the agents tier, per this handler's existing
  separate-file convention.
- That `build_graph(model)` / `propose(product_name=, marketplace=,
  graph=)` remain the seam and its call shape — carried over from the
  four existing files, and stated by `design.md` as unchanged.
- `_no_network` / `_no_credential` as the way the scenario's "without
  opening a network connection, or supplying a credential" clause is
  *established* rather than merely asserted in prose.

## Expected first-run state

The wire schema does not exist yet (`tasks.md` 2.1-2.2), so the advisor
still hands the adapter a union and these tests are expected to fail —
the conversion raising `ValueError: Unsupported function`, which is the
production defect itself. Per `ai-toolkit:testing` that is failure state
1: the code ran and produced a wrong result.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1824 passed, 44 skipped, 0
failed.
"""

from __future__ import annotations

import json
import socket
from types import UnionType
from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult
from langchain_core.utils.function_calling import convert_to_openai_tool
from langchain_openai.chat_models.base import _convert_to_openai_response_format

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.step_handlers.listing.subcategory_advisor import (
    Supported,
    Unsupported,
)

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"

# Fixed by `tasks.md` 2.1, not by any delta scenario.
WIRE_FIELDS: Final = ("ok", "value", "error", "comment")

CREDENTIAL_VARIABLES: Final = (
    "OPENAI_API_KEY",
    "OPENAI_ORG_ID",
    "OPENAI_BASE_URL",
    "AZURE_OPENAI_API_KEY",
)


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model that records the schema its structured-output seam is given
# ---------------------------------------------------------------------------


class _CapturingRunnable:
    """What `with_structured_output(..., include_raw=True)` returns.

    Answers with a response that validates against nothing, so the advisor
    takes its "no verdict could be read" route and `propose()` returns
    normally. Nothing here depends on that route's behaviour — this file
    only needs the call site to have run.
    """

    def __init__(self) -> None:
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        return {
            "raw": AIMessage(content="not a recognisable verdict"),
            "parsed": None,
            "parsing_error": ValueError("could not validate against the schema"),
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # `tasks.md` 2.5 / `design.md` Decision 2's model-level guard.
        # Both entry points are real on a structured-output runnable, so a
        # `recommend` body reverted to `structured.invoke(...)` inside an
        # `async def` would work, pin the invoking loop for the whole
        # round-trip, and pass every assertion in this file about what the
        # advisor produces. It fails here instead, naming the mistake.
        raise AssertionError(
            "the advisor reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)` — "
            "the enclosing coroutine then never yields, and the invoking "
            "loop is pinned for the whole of the round-trip"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        self.received.append(input_)
        return self._answer()


class _CapturingChatModel(BaseChatModel):
    """Records every schema handed to `with_structured_output(...)`.

    `_generate` and `bind_tools` raise, so an advisor that reached the
    model any other way fails loudly rather than leaving `schemas` empty
    for an unrelated reason.
    """

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
        raise AssertionError(
            "the advisor called the model directly instead of through "
            "`with_structured_output(...)` — this fake only answers that seam"
        )

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        raise AssertionError("the advisor bound tools to its model")

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        self.schemas.append(schema)
        object.__setattr__(self, "requested_include_raw", include_raw)
        return _CapturingRunnable()

    @property
    def _llm_type(self) -> str:
        return "schema-capturing-fake-chat-model"


# ---------------------------------------------------------------------------
# The guard's own mechanism: capture from the call site, then convert
# ---------------------------------------------------------------------------


async def _schemas_the_call_site_passed() -> list[Any]:
    """Every schema the advisor's own call site handed the model.

    Obtained from the call site — never by importing a module-level
    symbol — which is what *The converted schema is the one the call site
    passes* requires. `build_graph(model)` may or may not reach the call
    site on its own; where it does not, the graph is run so the node that
    holds the call executes.
    """
    model = _CapturingChatModel()
    graph = advisor_graph.build_graph(model)
    if not model.schemas:
        try:
            await advisor_graph.propose(
                product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
            )
        except AssertionError:
            # Never swallowed, whether or not a schema was captured. An
            # `AssertionError` out of `propose()` here can only have come
            # from this file's own fakes — `_generate`, `bind_tools` and
            # the runnable's synchronous `invoke` are the three that raise
            # one — so it reports that the advisor reached the model by a
            # path this file exists to forbid.
            #
            # The distinction is load-bearing and was not obvious: the
            # schema is recorded by `with_structured_output(...)`, which
            # runs *before* the model is called, so `model.schemas` is
            # already populated by the time any of those fire. Tolerating
            # the exception on a non-empty `schemas` therefore swallowed
            # every one of them, and the sync-`invoke` guard this change
            # added was inert in this file while its own comment claimed
            # it was not.
            raise
        except Exception as failure:
            if not model.schemas:
                raise AssertionError(
                    "the advisor never reached its structured-output call "
                    f"site, so no schema could be captured: {failure!r}"
                ) from failure
    return list(model.schemas)


async def _the_schema_the_call_site_passes() -> Any:
    captured = await _schemas_the_call_site_passed()
    assert captured, (
        "the advisor never called `with_structured_output(...)`, so there "
        "is no schema to convert"
    )
    return captured[0]


def _convert_the_way_the_adapter_does(schema: Any) -> dict[str, Any]:
    """Both conversions `ChatOpenAI`'s `json_schema` path performs.

    `strict=None` is what the adapter passes when the caller supplies no
    `strict` argument, which the advisor does not (`design.md`, Context 1).
    """
    _convert_to_openai_response_format(schema, strict=None)
    return convert_to_openai_tool(schema)


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
async def test_the_schema_is_accepted_by_the_providers_own_conversion() -> None:
    """Scenario: The schema is accepted by the provider's own conversion.

    WHEN the schema the advisor passes at its structured-output call site
    is converted by the model provider's adapter
    THEN the conversion succeeds, and this is verified without invoking a
    model, opening a network connection, or supplying a credential.

    SPECIFIED: the adapter's *own* conversion, not a stand-in for it —
    both halves of it, since `design.md` Context 2 establishes the
    `json_schema` path converts twice and fixing only one would leave the
    other failing.

    The no-model / no-network / no-credential half of the THEN is
    established rather than described: the fake model's `_generate` raises,
    `socket.connect` raises, and every credential variable is removed from
    the environment for the duration of this test.
    """
    schema = await _the_schema_the_call_site_passes()

    _convert_to_openai_response_format(schema, strict=None)
    convert_to_openai_tool(schema)


@pytest.mark.usefixtures("_no_network", "_no_credential")
@pytest.mark.anyio
async def test_the_schema_is_not_the_union_the_adapter_rejects() -> None:
    """The same scenario, asserted in the direction the defect ran.

    SPECIFIED by the requirement's own rationale: "today's adapter rejects
    a top-level union of the response variants... passing one makes every
    invocation fail before the model is ever called". Stated as a separate
    test so that a regression to a union is legible by name rather than as
    a bare `ValueError` from the test above.
    """
    schema = await _the_schema_the_call_site_passes()

    assert not isinstance(schema, UnionType), (
        "the advisor still passes a top-level union at its "
        "structured-output call site, which the provider adapter rejects: "
        f"{schema!r}"
    )
    assert isinstance(schema, type), (
        "the advisor passes something that is not a single schema type, so "
        f"the adapter falls through to `convert_to_openai_function`: {schema!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: The converted schema is the one the call site passes
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_guard_obtains_its_schema_from_the_call_site() -> None:
    """Scenario: The converted schema is the one the call site passes.

    WHEN the advisor's structured-output call site passes a schema other
    than the one a guard converts
    THEN that divergence is detectable, since the guard obtains its schema
    from the call site rather than by importing a symbol independently.

    Asserted as the property the guard's mechanism has: everything it
    converts arrives through `with_structured_output(...)`, recorded by
    the fake at the moment the advisor calls it. This module imports no
    wire-model symbol at all — `Supported` and `Unsupported` are imported
    only as the *rejected* shape the probe below drives through the same
    mechanism.
    """
    captured = await _schemas_the_call_site_passed()

    assert captured, (
        "nothing was captured at the call site, so this guard would be "
        "converting a symbol rather than what the advisor passes"
    )
    assert len(captured) == 1 or all(item is captured[0] for item in captured), (
        "the advisor passed more than one distinct schema to "
        f"`with_structured_output(...)`: {captured!r}"
    )


def test_a_diverging_call_site_is_detected_by_the_same_mechanism() -> None:
    """The other half of the same scenario: the mechanism discriminates.

    A guard that captures from the call site is only worth having if a
    call site passing a schema the adapter rejects actually fails it. Run
    the guard's own capture-then-convert mechanism over a stand-in call
    site that passes the pre-change union, and it raises — so a real call
    site drifting back to that shape would be caught rather than passing
    silently.

    SPECIFIED by the scenario's THEN ("that divergence is detectable").
    The union is the concrete divergence `proposal.md` records from
    production; `tasks.md` 2.7 keeps `Supported` and `Unsupported` in
    place, so this probe stays constructible after the change.
    """
    diverging_model = _CapturingChatModel()
    diverging_model.with_structured_output(Supported | Unsupported, include_raw=True)
    captured = diverging_model.schemas[-1]

    with pytest.raises(ValueError):
        _convert_to_openai_response_format(captured, strict=None)
    with pytest.raises(ValueError):
        convert_to_openai_tool(captured)


# ---------------------------------------------------------------------------
# Scenario: Wire fields state when they are to be populated
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_wire_fields_state_when_they_are_to_be_populated() -> None:
    """Scenario: Wire fields state when they are to be populated.

    WHEN the wire schema expresses the reported variants' fields as
    individually optional
    THEN each field carries a description of what it is for and when it is
    to be populated, so the coupling the reported variants enforce
    structurally is stated rather than left to the prompt alone.

    SPECIFIED: every field carries a description, read from the schema as
    the provider's own conversion emits it — the form the model actually
    receives, not pydantic's internals.

    DELIBERATELY UNTESTED: whether each description in fact says *when* to
    populate the field. Judging that would require parsing prose for
    particular content, which the served requirement *A comment's content
    is never checked by code* forbids this capability from doing one field
    over.
    """
    schema = await _the_schema_the_call_site_passes()

    converted = _convert_the_way_the_adapter_does(schema)
    properties = converted["function"]["parameters"]["properties"]

    for field in WIRE_FIELDS:
        assert field in properties, (
            f"the wire schema has no {field!r} field: {sorted(properties)}"
        )
        description = properties[field].get("description")
        assert isinstance(description, str) and description.strip(), (
            f"the wire schema's {field!r} field carries no description, so "
            "the coupling the reported variants enforce structurally is "
            "left to the prompt alone"
        )


@pytest.mark.anyio
async def test_the_converted_schema_emits_no_oneof() -> None:
    """DERIVED — traced to `design.md`, not to a delta scenario.

    `design.md`'s first decision rejects the discriminated-union envelope
    because it emits `oneOf`, which OpenAI's strict structured outputs do
    not support: that shape passes every offline check and is still liable
    to be rejected by the API, at which point the fix has bought nothing.
    Asserted here because it is exactly the trap the change was designed
    around, and because no offline conversion check would otherwise catch
    it. Recorded as derived so it is visible as a design-level constraint
    rather than a requirement the delta states.
    """
    schema = await _the_schema_the_call_site_passes()

    converted = _convert_the_way_the_adapter_does(schema)

    assert "oneOf" not in json.dumps(converted), (
        "the converted schema emits `oneOf`, which OpenAI's strict "
        f"structured outputs do not support: {converted!r}"
    )


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the provider's *API* accepts the schema both local conversions
#   accept. No offline check can establish it; `tasks.md` section 4 gates
#   it on a live invocation after deploy, and `design.md` records it as
#   this change's first risk.
# - Whether the model fills the flat schema's independent fields
#   consistently. A quality property of the response, not of the schema;
#   `design.md`'s second risk, gated on the same live verification.
# ---------------------------------------------------------------------------
