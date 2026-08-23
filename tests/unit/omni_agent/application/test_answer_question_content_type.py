"""Unit tests for `answer_question`'s handling of the language model
response's content type.

Derived strictly from the MODIFIED "Answer a single question" requirement's
scenarios in
`openspec/changes/specify-non-string-message-content/specs/omni-agent/spec.md`:

- Scenario: Question receives a generated answer (regression coverage for
  the plain-string path, exercised under the new code path -- tasks.md 3.1)
- Scenario: Language model response content is not a plain string
  (tasks.md 3.2)

`NonStringAnswerError` does not exist yet -- design.md's "Where the exception
lives" names it as new, to be added to `use_cases.py` alongside its only
raiser. Importing it here is expected to fail collection until that
implementation lands; per this project's test-design-before-implementation
workflow (AGENTS.md), that is the intended, reportable state for this file,
not a defect in it.

Seam: design.md's Context states `answer_question` is the sole caller of the
compiled production graph, and that `build_production_graph` pins
`ChatOpenAI(model="gpt-4o-mini")`. Rather than guess how `answer_question`
obtains or caches that graph internally -- which would mean reading
`use_cases.py`, out of bounds for this pass -- these tests patch
`ChatOpenAI._generate`/`._agenerate` directly (`langchain_openai`), the
network-calling boundary the graph's model node ultimately calls through,
per this project's own "mock at the boundary the code under test actually
calls through" convention. This is the same override point
`tests/agents/omni_agent/test_graph.py`'s test doubles use one layer up (on
`BaseChatModel._generate` directly, via a fake `BaseChatModel` subclass) --
here applied to the real `ChatOpenAI` class itself, since design.md's
Context states that class as a fact about the production wiring, not
something read from `use_cases.py`. Both the sync and async generation
methods are patched because whether the compiled graph's model node calls
`.invoke()` or `.ainvoke()` internally is not pinned anywhere either.

ASSUMPTION (recorded in test-manifest.md as an unresolved project question):
`answer_question(question: str) -> str` is a coroutine (an already-existing
fact about this codebase, evidenced by
`tests/unit/omni_agent/infrastructure/driving/test_slack_event_dispatch_under_bolt.py`'s
own `_RecordingAnswerQuestion` docstring: "A coroutine after this change
(tasks.md 4.1), so `__call__` is async def" -- substituted directly for
`omni_agent.application.answer_question` there), and that it invokes its
graph with a single `HumanMessage` and reads `result["messages"][-1]`,
mirroring `tests/agents/omni_agent/test_graph.py`'s own invocation contract
and proposal.md's quoted line, `result["messages"][-1].content`. If
`answer_question` does not route through a `ChatOpenAI` instance's
`_generate`/`_agenerate` at all, these tests will fail to collect or fail on
their first run rather than exercise the intended path, and should be
reconciled with the implementer rather than silently adjusted to match
whatever shape appeared.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_openai import ChatOpenAI

from commerce_ops.omni_agent.application.use_cases import (
    NonStringAnswerError,
    answer_question,
)

pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    # Pinned to asyncio -- consistent with this project's other async test
    # modules (e.g. tests/unit/products/application/test_daily_digest.py):
    # no trio dependency is installed, so leaving this at anyio's own
    # ["asyncio", "trio"] default would fail collection on the trio branch.
    return "asyncio"


@pytest.fixture(autouse=True)
def _openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A dummy key so constructing `ChatOpenAI(...)` never fails for its
    absence. No real call is ever made: `_generate`/`_agenerate` are patched
    in every test in this file, so this value is never sent anywhere.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")


@contextlib.contextmanager
def _scripted_chat_openai(content: Any) -> Iterator[None]:
    """Makes every `ChatOpenAI` instance respond with `content` as its
    single `AIMessage`'s `.content`, synchronously or asynchronously,
    without any real OpenAI call being made.
    """
    result = ChatResult(
        generations=[ChatGeneration(message=AIMessage(content=content))]
    )

    def _generate(
        self: ChatOpenAI,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return result

    async def _agenerate(
        self: ChatOpenAI,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return result

    with (
        patch.object(ChatOpenAI, "_generate", _generate),
        patch.object(ChatOpenAI, "_agenerate", _agenerate),
    ):
        yield


async def test_plain_string_answer_is_returned_unchanged() -> None:
    """Scenario: Question receives a generated answer (regression coverage
    under the new code path -- tasks.md 3.1).

    WHEN a question is submitted to the agent, and the language model's
    response content is a plain string
    THEN the agent returns a non-empty response produced by the language
    model from that question, unaltered by the new non-string check.
    """
    scripted_answer = "Paris is the capital of France."

    with _scripted_chat_openai(scripted_answer):
        result = await answer_question("What is the capital of France?")

    # Specified: the response is the one the language model produced.
    assert result == scripted_answer
    # Specified: the response is non-empty.
    assert result != ""


async def test_non_string_content_raises_non_string_answer_error() -> None:
    """Scenario: Language model response content is not a plain string.

    WHEN a question is submitted to the agent, and the configured language
    model's response content is not a plain string
    THEN the agent's invocation fails visibly -- raising
    `NonStringAnswerError` (design.md, "Where the exception lives") --
    rather than returning a fabricated, coerced, or partial string derived
    from that content.
    """
    content_blocks = [{"type": "text", "text": "Paris is the capital of France."}]

    with _scripted_chat_openai(content_blocks), pytest.raises(NonStringAnswerError):
        await answer_question("What is the capital of France?")
