## Context

See proposal.md — Why, for the defect and why it was split out of `tighten-type-checking`. Relevant constraints:

- `answer_question` (`src/commerce_ops/omni_agent/application/use_cases.py`) is the only caller of the graph's result; its sole consumer is `slack.py`'s `handle_app_mention`, which already wraps the call in `try`/`except Exception: ... post _FAILURE_MESSAGE` (`slack.py:139-141`), with a `noqa: BLE001` comment stating "any omni-agent failure must surface in Slack."
- `omni_agent/domain/` is currently empty — the module has no entities or aggregates. Tactical DDD patterns are adopted per module only as needed (AGENTS.md), and this defect does not warrant introducing a domain layer on its own.
- The defect is latent: `build_production_graph` pins `ChatOpenAI(model="gpt-4o-mini")` with no multimodal input and no structured output, so `.content` is a `str` on every path exercised today. No existing test currently exercises a non-string `.content`.

## Goals / Non-Goals

**Goals:**

- `answer_question` never returns a non-`str` value silently coerced or passed through as if it were a valid answer.
- The scoped `# type: ignore[no-any-return]` at `use_cases.py:28` is removed, with the return path made genuinely type-correct rather than re-suppressed.
- The failure path this relies on is the existing one — no new Slack-facing message or handling code.

**Non-Goals:**

- **Changing what triggers a response, or omni-agent's other requirements** (tool invocation, cross-invocation state). Untouched.
- **Handling non-string content by interpreting or transforming it into a meaningful answer.** Rejected in favor of Raise — see Decisions.
- **Adding multimodal or structured-output support to `build_production_graph`.** This change only specifies what happens if content already arrives in a shape `answer_question` doesn't expect; it does not change what shapes the graph can produce.

## Decisions

### Non-string content raises, rather than being coerced into a string

Two candidates were carried into this change from `tighten-type-checking`'s design.md: raise, or coerce/join into a string. **Raise is chosen.**

Coercion has no well-defined algorithm to specify: LangChain content blocks can carry text, images, or other structured data, and there is no existing rule in this codebase for which blocks to include or how to render them as text. Specifying a join now would mean inventing that rule from nothing, and a lossy or partial join risks presenting the ops team with something that reads as a real answer but isn't — a silently-degraded response in substance, even though the code path that produces it is not the language-model call itself.

Raising keeps the existing, already-correct failure path: `slack.py:139-141` already catches any exception from `answer_question` and posts `_FAILURE_MESSAGE`. No Slack-facing code changes. This is also the conservative choice given the defect is latent rather than live — it costs nothing on any path exercised today, and does not lock in a serialization format that a future coercion approach would need to have gotten right on the first try.

**On the tension with "Model failure is surfaced, not masked":** that requirement's scenario is scoped to the language model call itself failing or being unavailable. Here, the model call succeeds — the response just isn't a string. Raising for this case does not satisfy that requirement (it isn't the same failure), but it does not contradict it either. `omni-agent`'s new scenario (see specs delta) names this as its own failure condition — the agent failing to produce a valid answer — rather than being folded into the existing model-failure scenario's wording.

**Alternative considered — coerce via `str()` on whatever the content is.** Rejected: Python's `str()` of a list of content-block dicts produces a debug-style repr (e.g. `[{'type': 'text', 'text': '...'}]`), not a genuinely more useful response than a clear failure message. It would technically satisfy "returns a `str`" but not "a non-empty response produced by the language model" in the spirit that requirement was written.

### Where the exception lives

A new exception, `NonStringAnswerError`, is raised in `use_cases.py` at the point the non-`str` content is detected, and left uncaught by `answer_question` itself — `slack.py`'s existing broad catch is the intended handler. It is defined in `use_cases.py` (application layer, alongside its only raiser and only caller's module boundary) rather than introducing `omni_agent/domain/` for a single exception class; the module's `application/__init__.py` public surface is unaffected, since callers only ever observe it as an exception propagating out of `answer_question`, not as an imported symbol.

**Alternative considered — reuse a bare `TypeError`.** Rejected: it would be indistinguishable from a genuine programming error elsewhere in the call chain, and gives a future reader of `slack.py` or a test no way to assert specifically that this is the "non-string content" case rather than some other failure.

## Risks / Trade-offs

- **A future LangChain/LangGraph release could make non-string content routine rather than latent** (e.g. if `build_production_graph` gains multimodal input). → At that point, every affected question would surface as a Slack failure instead of an answer. This is a deliberate trade for correctness now; revisiting the decision (likely toward a real coercion/rendering strategy) becomes appropriate at that point, not before.
- **`slack.py`'s catch is broad (`except Exception`), so this failure is indistinguishable from any other `answer_question` failure in the message the user sees.** → Acceptable: `_FAILURE_MESSAGE` was already generic, and no existing requirement asks for failure-cause-specific user-facing messages. `NonStringAnswerError` still makes the cause distinguishable in logs/tests, which is what this change needs.

## Migration Plan

1. Add `NonStringAnswerError` to `use_cases.py`.
2. Replace the `# type: ignore[no-any-return]`-suppressed return with a check: if `.content` is a `str`, return it; otherwise raise `NonStringAnswerError`.
3. Update the `omni-agent` spec with the new scenario (see specs delta).
4. Confirm `slack.py` needs no change — its existing `except Exception` already covers the new exception; add a test asserting this rather than assuming it.
5. Run the full verification suite (`pytest`, `mypy`, `ruff`, `lint-imports`) — no runtime path outside the one described above changes.

Rollback is reverting the commit. No schema, external contract, or dependency is involved.
