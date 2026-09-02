"""A handler's waiting does not stop the process (`launch-step-automation`).

Derived strictly from the delta spec of the change
`await-the-subcategory-advisors-graph`:
`openspec/changes/await-the-subcategory-advisors-graph/specs/launch-step-automation/spec.md`

Covers, from the ADDED requirement *A handler's waiting does not stop the
process*:

- *A handler's waiting leaves the invoking loop free* — both halves of its
  THEN, in `test_a_handlers_waiting_leaves_the_invoking_loop_free`.
- *A framework's thread offload does not stand in for a dependency's
  asynchronous entry point* — for the one handler this change ships, in
  `test_the_dependency_is_reached_on_the_invoking_thread` and
  `test_the_advisors_graph_refuses_the_synchronous_entry_point`. The
  scenario's general form is not testable here; see *What this file does
  not establish* below and `test-manifest.md` at the change root.

Two of the requirement's scenarios have no test in this file, both
recorded with their reasons in `test-manifest.md`: *A dependency offering
only a blocking call is awaited off the invoking thread* (no handler in
this repository reaches such a dependency, and `tasks.md` 3.6 forbids
adding one here), and *How a handler waits does not change what it
produces* (`design.md` Decision 5 assigns that to the seven existing
agent-tier advisor files, whose assertions `tasks.md` 2.2 pins
byte-for-byte through the migration).

## Level

The requirement is stated as an obligation on a **handler**, so its
observable is asserted at the handler — `advise_sub_category(context)`
over a monkeypatched `_graph()`, the seam
`test_subcategory_advisor_structured_recommendation.py` already
established for the two scenarios that need the real handler. The one
exception is the structural-refusal test, which is about the compiled
graph itself and so is asserted at `build_graph(model)`.

## The mechanism, and why it is this one

`design.md` Decision 2 and `tasks.md` 2.6a settle it rather than leaving
it to choice: the stub's `ainvoke` yields **once** and then answers
unconditionally; a companion task is created before the handler is
awaited and records that it ran; the assertion reads that record at the
moment the handler returned. A stub that instead awaited an
`asyncio.Event` the companion set would **deadlock** where a blocking
handler should merely fail, and a hanging suite is a worse diagnostic
than any assertion message.

There is no wall-clock timing here of any kind — no `asyncio.sleep` of a
positive duration, no "finished faster than N", no thread timing.
`await asyncio.sleep(0)` is a bare yield to the loop, not a wait, and it
is the only scheduling primitive this file uses. `AGENTS.md` requires
this tier to be deterministic and a scheduling race dressed as an
assertion would be worse than no assertion.

## What this file does not establish

Measured against `langgraph` 1.2.11 (what `uv.lock` resolves) while
writing these tests: **LangGraph's own `ainvoke` machinery yields to the
loop before it runs the node**, whether or not the node body yields. A
companion task therefore progresses across `graph.ainvoke(...)` even for
a node that never gives the loop back on its own.

That is the delta's *A framework's thread offload does not stand in ...*
scenario stated as a fact about the code under test, and it has a
consequence for the loop-free test below that must be said plainly rather
than left for someone to discover: **that test cannot fail for a blocking
call introduced inside `recommend` itself.** LangGraph will already have
yielded by the time the node body runs, so the companion's record is
populated whatever the node then does. Measured, with the post-change
node shape reconstructed over this file's own stub: a node that awaits
and a node that never yields both leave the companion recorded as having
run before the handler returned.

`design.md` Decision 2 states the opposite — that the single-yield
mechanism "keeps failing rather than hanging" for "some new blocking call
introduced directly inside `recommend`, belonging to no stub". It does
not hang, but it does not fail either. That gap is reported as a finding
against Decision 2 rather than papered over here, and the loop-free test
is kept for what it honestly is: the delta scenario's own observable,
asserted directly, with no claim to guard a revert.

What does guard that revert is `_YieldingStructuredRunnable.invoke`
raising (`tasks.md` 2.5) together with the two tests below, which assert
the thing the observable cannot: that the model was reached on the
**invoking thread** rather than on a worker thread LangGraph would have
handed synchronous code to (measured: a sync node under `ainvoke` runs on
a different `threading.get_ident()`; an async node runs on the caller's),
and that the compiled graph answers no synchronous entry point at all, so
there is no synchronous path for the framework to accommodate.

Both of those are facts about **this** handler. The scenario's general
form — any handler, any library that thread-pools synchronous work —
names a handler that must not exist, and a test constructing one in order
to assert its non-compliance would assert a property of the fixture, not
of this codebase. The requirement itself places that clause at review
("which entry point a handler reached is a fact about the source that no
runtime observation distinguishes"), and this file does not pretend
otherwise.

## What is fixed, and what is INVENTED

Fixed by the delta: that other work scheduled on the invoking loop
progresses before the handler returns, and that the handler then returns
its resolution as it otherwise would. Fixed by `design.md` Decision 2 and
`tasks.md` 2.5: the stub's synchronous `invoke` raises, in the idiom the
sibling stubs already use for `_generate`.

INVENTED, each labelled at its assertion and recorded in
`test-manifest.md`:

- `_YieldingStructuredChatModel` / `_YieldingStructuredRunnable`,
  duplicated per this directory's additive-only, separate-file
  convention rather than shared through a `conftest.py` — sharing the
  advisor's stub harness is `share-the-unit-test-harness`'s scope
  (`tasks.md` 2.3).
- Thread identity as the observable that distinguishes an awaited
  dependency from framework-thread-pooled synchronous code.
- That the refusal `TypeError` names the node, `recommend`. Measured
  against `langgraph` 1.2.11; `pyproject.toml` declares a floor rather
  than a pin, so a later resolution could reword it.

## Expected first-run state

`propose()` is synchronous as this file is written, and `recommend`
inside `build_graph` is a synchronous node, so every test here is
expected to fail before the source conversion in `tasks.md` section 3
lands. Each should fail on the stub's synchronous `invoke` — *"the
advisor reached the model through the model's synchronous `invoke(...)`
entry point"* — which is the "the sync entry point was used" shape
`tasks.md` 2.8 says a failure here should read as. A failure of any other
shape is a finding under `tasks.md` 6.2.

Baseline recorded before these tests were written, on this worktree:
`uv run pytest tests/agents tests/unit/step_handlers -q` — 114 passed,
0 failed.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from typing import Any, ClassVar, Final, cast

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatResult

import commerce_ops.step_handlers.listing.subcategory_advisor as advisor_graph
from commerce_ops.launch.application import StepContext
from commerce_ops.launch.domain.launch_playbook import Satisfied
from commerce_ops.shared.domain.identity import Asin, MarketplaceId, ProductId, Sku
from commerce_ops.shared.domain.result import Success
from commerce_ops.step_handlers.listing.subcategory_advisor import AdvisorResponse

PRODUCT_NAME: Final = "Bamboo Cutting Board with Juice Groove"
MARKETPLACE: Final = "ATVPDKIKX0DER"

NODE: Final = (
    "Home & Kitchen > Kitchen & Dining > Kitchen Utensils & Gadgets > Cutting Boards"
)
COMMENT: Final = (
    "Demands: FDA food-contact material declaration; country-of-origin "
    "marking on the product. Rejected alternative: Home & Kitchen > Home "
    "Decor > Decorative Trays."
)

#: The two things the single shared log can record, and the order between
#: them is not what is asserted — see the module docstring. What is
#: asserted is that the first is present in the log *at the moment the
#: handler returned*, which is the requirement's own wording.
_COMPANION_RAN: Final = "other work scheduled on the invoking loop ran"
_DEPENDENCY_ANSWERED: Final = "the handler's dependency answered"


@pytest.fixture(scope="module")
def anyio_backend() -> str:
    return "asyncio"


# ---------------------------------------------------------------------------
# A chat model whose structured-output seam yields once, then answers
# ---------------------------------------------------------------------------


class _YieldingStructuredRunnable:
    """What `model.with_structured_output(AdvisorResponse, include_raw=True)`
    returns: the `raw`/`parsed`/`parsing_error` shape `include_raw=True`
    produces, reachable **only** by awaiting it."""

    def __init__(self, model: _YieldingStructuredChatModel) -> None:
        self._model = model

    def _answer(self) -> dict[str, Any]:
        return {
            "raw": AIMessage(content="structured response"),
            "parsed": self._model.outcome,
            "parsing_error": None,
        }

    def invoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # `tasks.md` 2.5 / `design.md` Decision 2's model-level guard. Both
        # entry points are real on a structured-output runnable, so a
        # `recommend` body reverted to `structured.invoke(...)` inside an
        # `async def` would work, pin the loop, and pass every assertion
        # about what the advisor produces. It fails here instead, at the
        # point of the mistake.
        raise AssertionError(
            "the advisor reached the model through the model's synchronous "
            "`invoke(...)` entry point instead of awaiting `ainvoke(...)` — "
            "the enclosing coroutine then never yields, and the invoking "
            "loop is pinned for the whole of the round-trip"
        )

    async def ainvoke(self, input_: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
        # One yield, then an unconditional answer. Not a wait: `sleep(0)`
        # hands control back to the loop and reschedules immediately, so a
        # handler that blocks fails the assertion below rather than
        # hanging on a stub that is waiting to be released.
        await asyncio.sleep(0)
        self._model.answered_on_thread.append(threading.get_ident())
        self._model.observed.append(_DEPENDENCY_ANSWERED)
        return self._answer()


class _YieldingStructuredChatModel(BaseChatModel):
    """Answers one fixed `AdvisorResponse`, and only when awaited."""

    outcome: ClassVar[Any] = None
    observed: ClassVar[list[str]]
    answered_on_thread: ClassVar[list[int]]

    def __init__(self, outcome: Any, observed: list[str]) -> None:
        super().__init__()
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "observed", observed)
        object.__setattr__(self, "answered_on_thread", [])

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise AssertionError(
            "the advisor called the model directly instead of through "
            "`with_structured_output(...)`"
        )

    def with_structured_output(
        self, schema: Any, *, include_raw: bool = False, **kwargs: Any
    ) -> Any:
        return _YieldingStructuredRunnable(self)

    @property
    def _llm_type(self) -> str:
        return "yielding-structured-fake-chat-model"


# ---------------------------------------------------------------------------
# A product and a step context, as the pass resolves them
# ---------------------------------------------------------------------------


class _Product:
    def __init__(self) -> None:
        self.id = ProductId("7f3a1c22-0000-4000-8000-000000000001")
        self.sku = Sku("BCB-001")
        self.marketplace_id = MarketplaceId(MARKETPLACE)
        self.asin: Asin | None = None
        self.name = PRODUCT_NAME


class _Context:
    def __init__(self, product: Any) -> None:
        self.step = None
        self.launch = None
        self.product = product
        self.as_of = datetime.now(UTC)


def _handler_over(
    observed: list[str], monkeypatch: pytest.MonkeyPatch
) -> tuple[_YieldingStructuredChatModel, StepContext]:
    """The registered handler, over a graph whose model is the stub above.

    `_graph()` is `lru_cache`d and builds the production graph, which
    reads credentials — the monkeypatch seam is how every handler-level
    advisor test already avoids that.
    """
    model = _YieldingStructuredChatModel(
        AdvisorResponse(ok=True, value=NODE, comment=COMMENT), observed
    )
    graph = advisor_graph.build_graph(model)
    monkeypatch.setattr(advisor_graph, "_graph", lambda: graph)
    return model, cast(StepContext, _Context(_Product()))


# ---------------------------------------------------------------------------
# Scenario: A handler's waiting leaves the invoking loop free
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_a_handlers_waiting_leaves_the_invoking_loop_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A handler's waiting leaves the invoking loop free.

    WHEN a handler is invoked on a loop that also has other work
    scheduled, and the handler's dependency has not yet answered
    THEN that other work progresses before the handler returns, and the
    handler then returns its resolution as it otherwise would.
    """
    observed: list[str] = []
    model, context = _handler_over(observed, monkeypatch)

    async def companion() -> None:
        observed.append(_COMPANION_RAN)

    # Created *before* the handler is awaited, so it is already on the
    # loop's ready queue and needs only for the handler to give the loop
    # back once.
    companion_task = asyncio.create_task(companion())

    resolution = await advisor_graph.advise_sub_category(context)
    # Read at the moment the handler returned, before the companion is
    # awaited — otherwise the assertion would be satisfied by the
    # companion running *after* the handler, which is what a blocking
    # handler does.
    progressed_before_the_handler_returned = list(observed)
    await companion_task

    # SPECIFIED: "that other work progresses before the handler returns".
    assert _COMPANION_RAN in progressed_before_the_handler_returned, (
        "the handler returned without the loop ever running other work "
        "that was already scheduled on it, so waiting for its dependency "
        "pinned the loop rather than yielding it: "
        f"{progressed_before_the_handler_returned!r}"
    )
    # DERIVED: that the dependency really was reached — an assertion about
    # other work progressing would be vacuously satisfiable by a handler
    # that never called its dependency at all.
    assert _DEPENDENCY_ANSWERED in observed, (
        "the handler's dependency was never reached, so nothing was "
        "waited for and the scenario was not observed"
    )
    assert model.answered_on_thread, "the structured-output seam never answered"

    # SPECIFIED: "the handler then returns its resolution as it otherwise
    # would" — the same outcome, result text and finding the supported
    # exit produces today.
    assert resolution.outcome is Satisfied
    assert resolution.result == f"{NODE}\n\n{COMMENT}"
    assert resolution.finding == Success(value=NODE, comment=COMMENT)


# ---------------------------------------------------------------------------
# Scenario: A framework's thread offload does not stand in for a
# dependency's asynchronous entry point
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_the_dependency_is_reached_on_the_invoking_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Scenario: A framework's thread offload does not stand in for a
    dependency's asynchronous entry point — asserted for the one handler
    this change ships.

    WHEN a handler hands synchronous code to a library that offers an
    asynchronous entry point and that runs such code in a thread pool on
    the handler's behalf
    THEN the handler does not satisfy this requirement, notwithstanding
    that other work on the invoking loop progresses.

    The scenario's own condition names a handler that must not exist, so
    what is asserted here is the fact that distinguishes this handler from
    one: the dependency answers on the **invoking** thread. Measured
    against `langgraph` 1.2.11 — a synchronous node reached through
    `ainvoke` runs on a worker thread with a different
    `threading.get_ident()`, while an awaited coroutine node runs on the
    caller's. The loop-free observable above cannot make this
    distinction, because LangGraph yields to the loop before running
    either kind of node.
    """
    observed: list[str] = []
    model, context = _handler_over(observed, monkeypatch)
    invoking_thread = threading.get_ident()

    resolution = await advisor_graph.advise_sub_category(context)

    # DERIVED (thread identity as the observable; the clause it serves is
    # SPECIFIED): the dependency was awaited on the loop's own thread, not
    # handed to a framework worker thread as synchronous code.
    assert model.answered_on_thread == [invoking_thread], (
        "the handler's dependency was reached on a thread other than the "
        "invoking one, which is how LangGraph accommodates a *synchronous* "
        "node — the handler relied on that accommodation instead of the "
        "dependency's own asynchronous entry point: answered on "
        f"{model.answered_on_thread!r}, invoked on {invoking_thread!r}"
    )
    assert resolution.outcome is Satisfied


def test_the_advisors_graph_refuses_the_synchronous_entry_point() -> None:
    """Scenario: A framework's thread offload does not stand in for a
    dependency's asynchronous entry point — its structural half.

    A framework can only thread-pool synchronous work a handler hands it.
    The compiled advisor graph answers no synchronous entry point at all,
    so there is nothing for LangGraph to accommodate and no way for a
    later author to reintroduce the shape without an immediate, named
    failure. `design.md` Decision 2 rests on exactly this.

    Deliberately not `@pytest.mark.anyio`: the point is what happens on a
    caller with no loop at all.
    """
    observed: list[str] = []
    model = _YieldingStructuredChatModel(
        AdvisorResponse(ok=True, value=NODE, comment=COMMENT), observed
    )
    graph = advisor_graph.build_graph(model)

    with pytest.raises(TypeError) as raised:
        graph.invoke({"product_name": PRODUCT_NAME, "marketplace": MARKETPLACE})

    # DERIVED: that the refusal names the node. Measured against
    # `langgraph` 1.2.11 as `No synchronous function provided to
    # "recommend".`; `pyproject.toml` declares a floor rather than a pin,
    # so a later resolution could reword it — matched on the node name
    # alone rather than on the sentence.
    assert "recommend" in str(raised.value), (
        "the graph refused the synchronous entry point without naming the "
        f"node responsible: {raised.value!r}"
    )
    # DERIVED: the refusal happened before anything reached the model, so
    # no synchronous path through the node exists to be thread-pooled.
    assert observed == []
    assert model.answered_on_thread == []
