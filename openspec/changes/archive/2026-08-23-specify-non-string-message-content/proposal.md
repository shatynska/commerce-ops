## Why

`omni_agent.application.use_cases.answer_question` is declared `-> str`, but its last line returns `result["messages"][-1].content`, which LangChain types as `Any`. `mypy --strict` (enabled by the `tighten-type-checking` change) correctly flags this: nothing in the code establishes that the value is a string, and LangChain's message `.content` can be a list of content blocks rather than a plain string for a multimodal or structured response.

`tighten-type-checking` deliberately did not fix this — it held the line with a scoped `# type: ignore[no-any-return]` (`src/commerce_ops/omni_agent/application/use_cases.py:30`) rather than deciding the answer, because the fix is a product decision (what the ops team sees in Slack when content is not a string), not a typing one. That change's task 5.5 names this proposal as its archive precondition; the ignore comment cites it by name. This change makes that decision and specifies it.

The defect is latent, not live: `build_production_graph` pins `ChatOpenAI(model="gpt-4o-mini")` with no multimodal input and no structured output, so `.content` is a `str` in every path exercised today. There is no user-facing incident driving this — it is closing a gap the type checker surfaced before it became one.

## What Changes

- **`omni-agent`'s existing "Answer a single question" requirement gains a scenario** covering what the agent returns when the language model's response content is not a plain string.
- **One of two resolutions is chosen and specified** (not left as an implementation choice):
  - **Raise** — treat non-string content as a failure. `slack.py:141` already catches broadly and posts the standard failure message, so this reuses the existing failure path. Tension: the model call itself succeeded: it produced content, just not in the shape `answer_question` expects. `omni-agent`'s existing "Model failure is surfaced, not masked" requirement is scoped to the language model call failing, not to the code that unpacks a successful call's result — treating this as the same kind of failure would stretch that requirement's scope rather than satisfy it.
  - **Coerce / join to string** — serialize or join the content blocks into a string so the user still gets a response. Tension: whether a serialized or lossy join counts as "a non-empty response produced by the language model" under the existing "Answer a single question" requirement is not settled by that requirement's current text, since it was written when `.content` was assumed to always be a string.
  - Both are recorded here as candidates rather than pre-decided; the design phase evaluates them against the existing `omni-agent` requirements above and records the choice with reasoning in `design.md`.
- **The scoped `# type: ignore[no-any-return]` at `use_cases.py:30` is removed** once the return type is made concrete (either the function's return path changes to make failure explicit, or the coercion makes the return genuinely `str` without help from an ignore).
- **No change to what triggers a response.** This only specifies what `answer_question` produces for a message whose content is not already a string — not how questions are submitted or how tool/state behavior work (both governed by `omni-agent`'s other, unaffected requirements).

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `omni-agent`: the "Answer a single question" requirement gains a scenario for non-string language-model response content, resolving what was previously an untested, unspecified edge case.

## Impact

- **Modified**: `openspec/specs/omni-agent/spec.md` (new scenario); `src/commerce_ops/omni_agent/application/use_cases.py` (the `answer_question` return path; removes the scoped ignore this change is named by).
- **Possibly modified**: `src/commerce_ops/omni_agent/infrastructure/driving/slack.py`, only if the chosen resolution is Raise and the existing broad `except Exception` / `_FAILURE_MESSAGE` path needs no change (it already covers any exception `answer_question` raises) — confirmed, not assumed, during design.
- **No new dependency.** No change to how or when the language model is invoked, and no change to `build_production_graph`'s configuration.
- **Unblocks archiving `tighten-type-checking`**, whose task 5.5 names this change as a precondition.
