"""The advisor's wire→domain conversion, over the flat structured-output
schema (`subcategory-advisor`).

Derived strictly from the delta spec of the change
`fix-subcategory-advisor-structured-output`:
`openspec/changes/fix-subcategory-advisor-structured-output/specs/subcategory-advisor/spec.md`

Covers two of the ADDED requirement *The structured-output schema is one
the model provider's adapter accepts*'s scenarios:

- Every wire combination has a defined destination
- The reported variants are unchanged by the wire shape

and five scenarios of the MODIFIED requirement *The advisor proposes
satisfaction only where it can support a node choice*:

- A supported choice proposes satisfaction
- An unsupported choice proposes no satisfaction
- A supporting discriminant without its value is not support
- A withholding discriminant without its error is not a refusal
- A supporting discriminant carrying a reported error withholds satisfaction

The ADDED requirement's three schema-shaped scenarios are covered in
`tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py`.
The MODIFIED requirement's remaining scenarios are unchanged in substance
by this change and are already covered by
`test_subcategory_advisor_structured_verdict.py`; see `test-manifest.md`
at the change root for the full per-scenario accounting, including which
of those existing tests this change supersedes.

## Which requirement owns which assertion

The delta is explicit that the ADDED requirement "governs the wire
contract: that the schema is accepted, that the conversion is total, and
that the fields say when they are to be populated", and that what each
destination then proposes and records "is governed entirely by *The
advisor proposes satisfaction only where it can support a node choice*".
So: `test_every_wire_combination_has_a_defined_destination` is the ADDED
requirement's totality claim, and every routing assertion in it traces to
the MODIFIED requirement, which is why the named per-row tests below state
each route separately rather than leaving it to the grid.

## The precedence this file exists to pin

`ok: true` with a blank `value` **and** a non-blank `error` matches both
the contradiction direction and the missing-value rule, and the delta
states normatively that the contradiction takes precedence: such a
response "has told the reader *why* no node could be named", and the
shortfall route would discard that explanation. The two scenarios are
therefore tested over **disjoint** inputs — the missing-value tests pin a
*blank* error in every case, and the contradiction tests pin a non-blank
one — so neither test can pass by taking the other's route.

## Level

`propose()` — the smallest unit that observes the outcome, the recorded
reason, the rendered text and the finding together. The conversion itself
is not reachable as a plain function without naming an internal the
artifacts do not fix; observing it through `propose()` also keeps the
assertions on what a member and the launch record actually receive.

## What is fixed, and what is INVENTED

Fixed by `tasks.md` 2.1: the wire model's four fields, `ok`, `value`,
`error`, `comment`. Fixed by `design.md`'s conversion table and by the
delta's direction 1: which combination maps where, and that blank means
empty-or-whitespace rather than merely `None`.

INVENTED, each recorded in `test-manifest.md`:

- `_ScriptedWireChatModel` / `_ScriptedWireRunnable`, duplicated from the
  four existing files in this directory per this handler's separate-file
  convention.
- Obtaining the wire model **from the call site** rather than importing it
  by name: no artifact fixes what the wire model is called, and capturing
  it through `with_structured_output(...)` is the same seam the delta
  requires the schema guard to use. A test that guessed the class name
  would fail on an absent target for a reason unrelated to the behaviour.
- The reason-family word lists (`CONTRADICTION_WORDS`,
  `SHORTFALL_PHRASES`). No artifact fixes the recorded reasons' wording.
  These are the same lists `test_subcategory_advisor_structured_verdict.py`
  already uses, so an implementation satisfying that file satisfies this
  one.
- `REPORTED_ERROR` and `REFUSAL_ERROR` as realistic model-authored prose
  with no first-member subject — deliberately the shape `design.md` names
  as the one `_advisor_refuses` will *not* catch, so a pass here is
  evidence about the conversion rather than about a matcher's word list.

## Expected first-run state

The wire model does not exist yet (`tasks.md` 2.1-2.6), so the schema the
call site passes is still the domain union and no wire instance can be
constructed from it. Every test here is expected to fail on an absent
target. Per `ai-toolkit:testing` that establishes absence only — the
assertions below are unverified until the target exists.

Baseline recorded before these tests were written:
`uv run pytest tests/unit tests/agents` — 1824 passed, 44 skipped, 0
failed.
"""

from __future__ import annotations

from typing import Any, ClassVar, Final

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.domain.launch_playbook import Blocked, Satisfied
from commerce_ops.shared.domain.result import Success

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"

NODE: Final = (
    "Home & Kitchen > Kitchen & Dining > Kitchen Utensils & Gadgets > Cutting Boards"
)
COMMENT: Final = (
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product. Rejected alternative: Home & Kitchen > Home "
    "Decor > Decorative Trays — higher keyword volume, but it understates "
    "this product's compliance surface."
)

# DERIVED: an error a model would author alongside `ok: true` — deliberately
# with no first-member subject, since `design.md` records that
# `_advisor_refuses` matches on one and would not fire on this. The route
# under test must be the conversion's, not the comment veto's.
REPORTED_ERROR: Final = (
    "the browse-node tree offers no single node that covers both the "
    "food-contact and the decorative use of this item"
)

# DERIVED: the error a withholding response carries. Distinct wording from
# `REPORTED_ERROR` so the two routes cannot be confused in a failure
# message.
REFUSAL_ERROR: Final = (
    "insufficient signal to place this listing in a single browse node"
)

BLANK_VALUES: Final = (None, "", "   ")
BLANK_ERRORS: Final = (None, "", "   ")

# DERIVED: the reason wording is fixed by no artifact. These are the same
# lists `test_subcategory_advisor_structured_verdict.py` already asserts
# against, so satisfying one file satisfies the other.
CONTRADICTION_WORDS: Final = ("contradict", "conflict", "disagree", "inconsistent")
SHORTFALL_PHRASES: Final = ("no verdict", "could not be read", "unread")


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model whose `with_structured_output(...)` is scripted directly
# ---------------------------------------------------------------------------


class _ScriptedWireRunnable:
    def __init__(self, outcome: Any) -> None:
        self._outcome = outcome
        self.received: list[Any] = []

    def _answer(self) -> dict[str, Any]:
        if self._outcome is None:
            return {
                "raw": AIMessage(content="not a recognisable verdict"),
                "parsed": None,
                "parsing_error": ValueError("could not validate against the schema"),
            }
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._outcome,
            "parsing_error": None,
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


class _ScriptedWireChatModel(BaseChatModel):
    """Scripts the structured-output seam, and records the schema it is
    handed so a wire response can be built from the very type the advisor
    asked the model for."""

    outcome: ClassVar[Any] = None
    schemas: ClassVar[list[Any]]
    runnable: ClassVar[_ScriptedWireRunnable | None]

    def __init__(self, outcome: Any = None) -> None:
        super().__init__()
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "schemas", [])
        object.__setattr__(self, "runnable", None)

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
        runnable = _ScriptedWireRunnable(self.outcome)
        object.__setattr__(self, "runnable", runnable)
        return runnable

    @property
    def _llm_type(self) -> str:
        return "scripted-wire-fake-chat-model"


# ---------------------------------------------------------------------------
# The wire schema, obtained from the call site rather than by name
# ---------------------------------------------------------------------------


async def _capture_wire_schema() -> Any:
    model = _ScriptedWireChatModel(None)
    graph = advisor_graph.build_graph(model)
    if not model.schemas:
        try:
            await advisor_graph.propose(
                product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
            )
        except AssertionError:
            # Never swallowed. An `AssertionError` out of `propose()` here
            # came from this file's own fakes, so it reports that the
            # advisor reached the model by a path this file forbids. The
            # schema is recorded before the model is called, so the
            # `schemas`-empty condition below never held for one of these
            # and swallowed every guard.
            raise
        except Exception as failure:
            if not model.schemas:
                raise AssertionError(
                    "the advisor never reached its structured-output call "
                    f"site, so no wire schema could be captured: {failure!r}"
                ) from failure
    assert model.schemas, (
        "the advisor never called `with_structured_output(...)`, so there "
        "is no wire schema to build a response from"
    )
    return model.schemas[0]


@pytest.fixture(scope="module")
async def wire_schema() -> Any:
    """The schema the advisor's own call site hands the model.

    Captured rather than imported: the wire model's *name* is fixed by no
    artifact, and the delta requires the schema under test to be the one
    the call site passes rather than a symbol expected to match it.
    """
    return await _capture_wire_schema()


def _wire(
    schema: Any, *, ok: bool, value: str | None, error: str | None, comment: str | None
) -> Any:
    """A parsed wire response, with all four fields pinned.

    `tasks.md` 1.4 requires every case to pin both `value` and `error`, so
    that no two cases admit the same input and the contradiction/shortfall
    precedence is actually exercised rather than assumed.
    """
    try:
        return schema(ok=ok, value=value, error=error, comment=comment)
    except Exception as failure:  # noqa: BLE001 - reported as a spec failure
        pytest.fail(
            "the wire schema cannot express "
            f"ok={ok!r} value={value!r} error={error!r} comment={comment!r}, "
            "so this combination has no destination to define: "
            f"{failure!r}"
        )


async def _propose(
    schema: Any,
    *,
    ok: bool,
    value: str | None,
    error: str | None,
    comment: str | None = COMMENT,
) -> Any:
    model = _ScriptedWireChatModel(
        _wire(schema, ok=ok, value=value, error=error, comment=comment)
    )
    graph = advisor_graph.build_graph(model)
    return await advisor_graph.propose(
        product_name=PRODUCT_NAME, marketplace=MARKETPLACE, graph=graph
    )


# ---------------------------------------------------------------------------
# Reading a proposal — carried over from this directory's existing files
# ---------------------------------------------------------------------------


def _outcome_of(proposal: Any) -> Any:
    for attribute in ("outcome", "proposed_outcome"):
        carried = getattr(proposal, attribute, None)
        if carried is not None:
            return carried
    pytest.fail(f"the advisor's proposal carries no outcome: {proposal!r}")


def _text_of(proposal: Any) -> str:
    for attribute in ("result", "recommendation", "text"):
        carried = getattr(proposal, attribute, None)
        if isinstance(carried, str):
            return carried
    pytest.fail(f"the advisor's proposal carries no produced text: {proposal!r}")


_ABSENT: Final = object()


def _finding_of(proposal: Any) -> Any:
    return getattr(proposal, "finding", _ABSENT)


def _assert_withheld(proposal: Any) -> Any:
    """A non-terminal outcome, and not a satisfying one.

    DERIVED, narrower than the scenarios' word "non-terminal": `Blocked`
    specifically, the only non-terminal outcome that can carry a reason,
    and every withheld route here is required to record one. Carried over
    unchanged from `test_subcategory_advisor_structured_verdict.py`.
    """
    outcome = _outcome_of(proposal)
    assert isinstance(outcome, Blocked), (
        f"expected a non-terminal Blocked outcome, got {outcome!r}"
    )
    return outcome


def _reason_of(proposal: Any) -> str:
    outcome = _assert_withheld(proposal)
    reason = getattr(outcome, "reason", None)
    if isinstance(reason, str) and reason.strip():
        return reason
    pytest.fail(f"the advisor's proposed outcome carries no reason: {outcome!r}")


def _names_contradiction(reason: str) -> bool:
    return any(word in reason.lower() for word in CONTRADICTION_WORDS)


def _names_shortfall(reason: str) -> bool:
    return any(phrase in reason.lower() for phrase in SHORTFALL_PHRASES)


# ---------------------------------------------------------------------------
# Scenario: A supported choice proposes satisfaction
# (MODIFIED requirement — row 1 of `design.md`'s conversion table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", BLANK_ERRORS, ids=("none", "empty", "whitespace"))
@pytest.mark.anyio
async def test_a_supported_choice_proposes_satisfaction(
    wire_schema: Any, error: str | None
) -> None:
    """Scenario: A supported choice proposes satisfaction.

    WHEN the advisor can support a node choice for the given product and
    marketplace
    THEN it proposes the step's satisfying outcome together with the
    recommendation.

    SPECIFIED: support is the discriminant "together with the field that
    discriminant's variant requires" — `ok: true` and a non-blank `value`.
    The `error` is pinned blank in every case here, so this test can never
    pass by way of the contradiction route it must stay disjoint from; it
    is parametrised over all three blank forms because `design.md` fixes
    blank as empty-or-whitespace, not merely `None`.
    """
    proposal = await _propose(wire_schema, ok=True, value=NODE, error=error)

    assert _outcome_of(proposal) is Satisfied
    finding = _finding_of(proposal)
    assert isinstance(finding, Success), f"expected a Success finding, got {finding!r}"
    assert finding.value == NODE


# ---------------------------------------------------------------------------
# Scenario: An unsupported choice proposes no satisfaction
# (MODIFIED requirement — row 4 of `design.md`'s conversion table)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    (None, "", NODE),
    ids=("no-value", "empty-value", "value-present"),
)
@pytest.mark.anyio
async def test_an_unsupported_choice_proposes_no_satisfaction(
    wire_schema: Any, value: str | None
) -> None:
    """Scenario: An unsupported choice proposes no satisfaction.

    WHEN the advisor cannot support a confident node choice for the given
    product and marketplace
    THEN it proposes a non-terminal outcome whose reason states that it
    cannot support a choice, and does not propose a satisfying outcome.

    SPECIFIED: `ok: false` together with the error stating why. The
    `value-present` case is `design.md`'s explicit asymmetry — "`ok: false`
    with a populated `value` is deliberately *not* a contradiction",
    because the discriminant and the error already agree and the surplus
    value adds no claim the reason misstates.

    The reason is asserted by what it must **not** be — the shortfall or
    the contradiction reason — rather than by its own wording, which no
    artifact fixes; that it carries the advisor's own error is asserted
    through the rendered text, which the requirement does pin.
    """
    proposal = await _propose(wire_schema, ok=False, value=value, error=REFUSAL_ERROR)

    reason = _reason_of(proposal)
    assert _finding_of(proposal) is None
    assert not _names_shortfall(reason), (
        "a reported refusal was recorded as a shortfall, asserting no "
        f"verdict could be read where one was: {reason!r}"
    )
    assert not _names_contradiction(reason), (
        "a refusal that agrees with its own discriminant was recorded as a "
        f"contradiction: {reason!r}"
    )
    assert REFUSAL_ERROR in _text_of(proposal), (
        "the advisor's own error never reached the member reading the "
        f"recommendation: {_text_of(proposal)!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: A supporting discriminant without its value is not support
# (MODIFIED requirement — row 3, pinned disjoint from row 2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", BLANK_ERRORS, ids=("none", "empty", "whitespace"))
@pytest.mark.parametrize("value", BLANK_VALUES, ids=("none", "empty", "whitespace"))
@pytest.mark.anyio
async def test_a_supporting_discriminant_without_its_value_is_not_support(
    wire_schema: Any, value: str | None, error: str | None
) -> None:
    """Scenario: A supporting discriminant without its value is not support.

    WHEN the advisor's structured response reports support, carries no
    value or a value that is empty or blank, **and carries no error
    either**
    THEN it proposes a non-terminal outcome whose reason states that no
    verdict could be read, and does not propose a satisfying outcome.

    SPECIFIED: the error is blank in every case, per the scenario's own
    "and carries no error either" — a response carrying an error alongside
    the missing value is the contradiction below, not this route.
    """
    proposal = await _propose(wire_schema, ok=True, value=value, error=error)

    reason = _reason_of(proposal)
    assert _finding_of(proposal) is None
    assert _names_shortfall(reason), (
        f"the reason does not say no verdict could be read: {reason!r}"
    )
    # SPECIFIED: "does not assert that a node choice could not be supported
    # for the product where that is not, in fact, what happened."
    lowered = reason.lower()
    assert "could not support" not in lowered
    assert "cannot support" not in lowered


# ---------------------------------------------------------------------------
# Scenario: A withholding discriminant without its error is not a refusal
# (MODIFIED requirement — row 5)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("error", BLANK_ERRORS, ids=("none", "empty", "whitespace"))
@pytest.mark.anyio
async def test_a_withholding_discriminant_without_its_error_is_not_a_refusal(
    wire_schema: Any, error: str | None
) -> None:
    """Scenario: A withholding discriminant without its error is not a
    refusal.

    WHEN the advisor's structured response withholds support but carries
    no error, or an error that is empty or blank
    THEN it proposes a non-terminal outcome whose reason states that no
    verdict could be read, rather than one asserting that the advisor
    considered and declined a classification.
    """
    proposal = await _propose(wire_schema, ok=False, value=None, error=error)

    reason = _reason_of(proposal)
    assert _finding_of(proposal) is None
    assert _names_shortfall(reason), (
        f"the reason does not say no verdict could be read: {reason!r}"
    )
    lowered = reason.lower()
    assert "could not support" not in lowered
    assert "cannot support" not in lowered


# ---------------------------------------------------------------------------
# Scenario: A supporting discriminant carrying a reported error withholds
# satisfaction (MODIFIED requirement — row 2, and the precedence it holds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    (NODE, *BLANK_VALUES),
    ids=("value-present", "no-value", "empty-value", "whitespace-value"),
)
@pytest.mark.parametrize("comment", (COMMENT, ""), ids=("commented", "no-comment"))
@pytest.mark.anyio
async def test_a_supporting_discriminant_carrying_a_reported_error_withholds_satisfaction(
    wire_schema: Any, value: str | None, comment: str
) -> None:
    """Scenario: A supporting discriminant carrying a reported error
    withholds satisfaction.

    WHEN the advisor's structured response reports support and also
    carries a non-empty error
    THEN it proposes a non-terminal outcome naming the contradiction, does
    not propose a satisfying outcome, and its rendered text carries that
    error — the error is never discarded as surplus to a supported
    response, and never left only in the recorded reason where the member
    reading the recommendation would not see it.

    SPECIFIED, and the three blank-value cases are the **precedence** the
    delta states normatively in direction 1: this "SHALL apply whether or
    not a value accompanies the error, and SHALL take precedence over the
    missing-value rule". An implementation that tests the missing value
    first sends those three to the shortfall route, which is exactly the
    loss this direction exists to prevent.

    The `no-comment` cases are `design.md`'s own note that an error-based
    contradiction may arrive with a blank comment: such a response is never
    *established as supported*, so the served empty-comment shortfall does
    not claim it, and rendering it as a supported result would show a
    reader a bare node path with no refusal anywhere in it.
    """
    proposal = await _propose(
        wire_schema, ok=True, value=value, error=REPORTED_ERROR, comment=comment
    )

    reason = _reason_of(proposal)
    # SPECIFIED: no satisfying outcome, nothing recorded against the product.
    assert _finding_of(proposal) is None
    # SPECIFIED: the reason names the contradiction...
    assert _names_contradiction(reason), (
        f"the reason does not name the contradiction: {reason!r}"
    )
    # ...and not the shortfall, which would discard the explanation the
    # model actually gave.
    assert not _names_shortfall(reason), (
        "a supporting response carrying an error took the shortfall route, "
        f"discarding the error it reported: {reason!r}"
    )
    # SPECIFIED (`tasks.md` 1.4): the reason names the *error* as what
    # withheld support, not the comment — `_contradiction_reason`'s served
    # wording names the comment, which an error-based contradiction may not
    # even carry.
    lowered = reason.lower()
    assert "error" in lowered, (
        f"the reason does not name the error as what withheld support: {reason!r}"
    )
    assert "comment" not in lowered, (
        "the reason blames the comment for a contradiction the error "
        f"carried: {reason!r}"
    )
    # SPECIFIED: the rendered text carries the error, so the refusal is
    # visible to the member reading it.
    assert REPORTED_ERROR in _text_of(proposal), (
        "the reported error never reached the reader; a contradiction was "
        f"rendered with nothing in it to say support was withheld: "
        f"{_text_of(proposal)!r}"
    )


@pytest.mark.anyio
async def test_the_three_withholding_reasons_are_distinguishable(
    wire_schema: Any,
) -> None:
    """The reason-naming obligation, asserted without depending on wording.

    SPECIFIED: "the reason recorded SHALL name what was actually wrong —
    the unsupported error where the advisor reported one, that no verdict
    could be read where the structured call produced nothing that mapped
    to a result, or the contradiction where a supporting response's own
    error or comment withheld it". An operator has to be able to tell the
    three apart, which requires them to differ at all — asserted here
    directly, so that an implementation collapsing two of them fails on
    this test rather than only on the word lists above.
    """
    shortfall = _reason_of(await _propose(wire_schema, ok=True, value=None, error=None))
    advisor_error = _reason_of(
        await _propose(wire_schema, ok=False, value=None, error=REFUSAL_ERROR)
    )
    contradiction = _reason_of(
        await _propose(wire_schema, ok=True, value=NODE, error=REPORTED_ERROR)
    )

    assert shortfall != advisor_error, (
        "a reported refusal and a response nothing could be read from "
        f"record the same reason: {shortfall!r}"
    )
    assert shortfall != contradiction, (
        "a self-contradicting response and a response nothing could be "
        f"read from record the same reason: {shortfall!r}"
    )
    assert advisor_error != contradiction, (
        "a reported refusal and a self-contradicting response record the "
        f"same reason: {advisor_error!r}"
    )


# ---------------------------------------------------------------------------
# Scenario: Every wire combination has a defined destination
# (ADDED requirement — totality; each route traces to the MODIFIED one)
# ---------------------------------------------------------------------------

_SATISFIED: Final = "satisfied"
_CONTRADICTION: Final = "contradiction"
_SHORTFALL: Final = "shortfall"
_ADVISOR_ERROR: Final = "advisor-error"


def _blank(text: str | None) -> bool:
    return text is None or not text.strip()


def _expected_destination(*, ok: bool, value: str | None, error: str | None) -> str:
    """`design.md`'s conversion table, in the order the delta fixes.

    The contradiction test precedes the missing-value one, which is the
    load-bearing part: rows 2 and 3 overlap on `ok: true` with a blank
    value and a non-blank error, and row 2 wins.
    """
    if ok:
        if not _blank(error):
            return _CONTRADICTION
        if not _blank(value):
            return _SATISFIED
        return _SHORTFALL
    if not _blank(error):
        return _ADVISOR_ERROR
    return _SHORTFALL


_GRID: Final = [
    pytest.param(
        ok,
        value,
        error,
        id=f"ok-{str(ok).lower()}--value-{value_id}--error-{error_id}",
    )
    for ok in (True, False)
    for value, value_id in (
        (None, "none"),
        ("", "empty"),
        ("   ", "whitespace"),
        (NODE, "node"),
    )
    for error, error_id in (
        (None, "none"),
        ("", "empty"),
        ("   ", "whitespace"),
        (REFUSAL_ERROR, "reported"),
    )
]


@pytest.mark.parametrize(("ok", "value", "error"), _GRID)
@pytest.mark.anyio
async def test_every_wire_combination_has_a_defined_destination(
    wire_schema: Any, ok: bool, value: str | None, error: str | None
) -> None:
    """Scenario: Every wire combination has a defined destination.

    WHEN the provider returns any response that parses against the wire
    schema
    THEN the advisor's conversion yields exactly one of its defined
    results — a supported result, an unsupported result, a contradiction,
    or none of them — with no combination of fields left to fall through
    to an unintended route.

    Every one of the 32 combinations the flat schema can express over
    `ok`, `value` and `error` is driven here, with `comment` held
    non-blank throughout so that the served empty-comment shortfall does
    not overlap the grid — that route is the served requirement's own and
    is covered by `test_subcategory_advisor_structured_recommendation.py`.

    The destination each combination is asserted to reach is governed by
    *The advisor proposes satisfaction only where it can support a node
    choice*, per the ADDED requirement's own referral; the totality claim —
    that none of the 32 falls through — is this scenario's.
    """
    expected = _expected_destination(ok=ok, value=value, error=error)
    proposal = await _propose(wire_schema, ok=ok, value=value, error=error)

    if expected == _SATISFIED:
        assert _outcome_of(proposal) is Satisfied
        finding = _finding_of(proposal)
        assert isinstance(finding, Success)
        assert finding.value == NODE
        return

    reason = _reason_of(proposal)
    assert _finding_of(proposal) is None

    if expected == _CONTRADICTION:
        assert _names_contradiction(reason), (
            f"expected the contradiction route, got: {reason!r}"
        )
        assert not _names_shortfall(reason), (
            f"expected the contradiction route, got the shortfall: {reason!r}"
        )
        assert error is not None and error in _text_of(proposal), (
            f"the reported error never reached the reader: {_text_of(proposal)!r}"
        )
    elif expected == _SHORTFALL:
        assert _names_shortfall(reason), (
            f"expected the shortfall route, got: {reason!r}"
        )
        assert not _names_contradiction(reason), (
            f"expected the shortfall route, got a contradiction: {reason!r}"
        )
    else:
        assert not _names_shortfall(reason), (
            f"expected the advisor's own error, got the shortfall: {reason!r}"
        )
        assert not _names_contradiction(reason), (
            f"expected the advisor's own error, got a contradiction: {reason!r}"
        )
        assert error is not None and error in _text_of(proposal), (
            f"the advisor's own error never reached the reader: {_text_of(proposal)!r}"
        )


# ---------------------------------------------------------------------------
# Scenario: The reported variants are unchanged by the wire shape
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_supported_wire_response_reports_what_a_supported_result_always_did(
    wire_schema: Any,
) -> None:
    """Scenario: The reported variants are unchanged by the wire shape.

    WHEN the advisor reports a supported result
    THEN that result carries the same fields, and produces the same
    rendered text and the same typed finding, as it would have had the
    wire shape and the reported shape been identical.

    "The same" is established by re-making, against a **wire** instance,
    the very assertions the served suite makes against a domain `Supported`
    (`test_subcategory_advisor_structured_recommendation.py`'s *A
    recommendation is readable as it stands* and
    `test_subcategory_advisor_finding_and_tools.py`'s *A supported
    recommendation carries a recordable finding*). Comparing against the
    domain-scripted path at runtime is not available: `tasks.md` 1.6
    forbids the conversion from accepting a domain variant, so there is no
    second path left to compare with.

    DELIBERATELY UNTESTED: whether the finding also carries the comment.
    The served requirement makes that a MAY ("The finding MAY also carry
    the comment"), so pinning it would invent a constraint.
    """
    proposal = await _propose(wire_schema, ok=True, value=NODE, error=None)

    assert _outcome_of(proposal) is Satisfied
    # SPECIFIED: the same typed finding — `Success`, whose value is exactly
    # the proposed node.
    finding = _finding_of(proposal)
    assert isinstance(finding, Success)
    assert finding.value == NODE
    # SPECIFIED: the same rendered text — the value and the comment
    # together, whole and unsummarised.
    text = _text_of(proposal)
    assert NODE in text
    for line in COMMENT.splitlines():
        assert line.strip() in text


@pytest.mark.anyio
async def test_an_unsupported_wire_response_reports_what_a_refusal_always_did(
    wire_schema: Any,
) -> None:
    """Scenario: The reported variants are unchanged by the wire shape,
    for the unsupported variant.

    Re-makes, against a wire instance, the assertions
    `test_subcategory_advisor_structured_verdict.py`'s *An unsupported
    recommendation still says so in prose* makes against a domain
    `Unsupported`.
    """
    proposal = await _propose(wire_schema, ok=False, value=None, error=REFUSAL_ERROR)

    _assert_withheld(proposal)
    assert _finding_of(proposal) is None
    text = _text_of(proposal)
    # SPECIFIED: the error reaches the reader.
    assert REFUSAL_ERROR in text
    # DERIVED: some inability-stating language accompanies it — the exact
    # wording is fixed by no artifact. Carried over unchanged from the
    # served file's own assertion.
    lowered = text.lower()
    assert any(
        phrase in lowered
        for phrase in ("cannot", "could not", "unable", "no node", "not choose")
    ), f"the rendered text does not read as a refusal on its own: {text!r}"


# ---------------------------------------------------------------------------
# DELIBERATELY UNTESTED, recorded rather than omitted
#
# - Whether the wire schema's `comment` field participates in any routing
#   beyond the two routes the served spec already fixes (the empty-comment
#   shortfall and the comment veto). Both are served scenarios covered by
#   the existing files in this directory; this change does not restate
#   them, so re-deriving them here would duplicate coverage rather than
#   add it.
# - Whether the model fills the flat schema's fields consistently in
#   production. Not observable from any test that scripts the wire
#   response — `tasks.md` section 4 gates it on the host.
# ---------------------------------------------------------------------------
