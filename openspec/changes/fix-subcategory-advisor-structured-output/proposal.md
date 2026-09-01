## Why

`lp.listing.007` has resolved nothing since `write-the-advisors-finding-to-the-product` deployed. Every invocation of the `listing.subcategory_advisor` handler raises before it reaches the model:

```
ValueError: Unsupported function
commerce_ops.step_handlers.listing.subcategory_advisor.Supported | ...Unsupported

Functions must be passed in as Dict, pydantic.BaseModel, or Callable. If they're a
dict they must either be in OpenAI function format or valid JSON schema with
top-level 'title' key.
```

Observed on the prod host, not inferred: **76 failures in 24 hours, out of 76 invocations** — a 100% failure rate. The automation pass catches it, logs `handler 'listing.subcategory_advisor' failed resolving step 'lp.listing.007'; nothing is recorded for it and the pass continues`, and moves on. Nothing else reports it, so the step has simply been silently inert since the deploy.

The cause is at `subcategory_advisor.py:257`:

```python
AdvisorResult = Supported | Unsupported                                  # line 214
structured = model.with_structured_output(cast(type, AdvisorResult), include_raw=True)
```

`langchain_openai`'s `_convert_to_openai_response_format` hands the schema to `convert_to_openai_function`, which accepts a dict, a single `pydantic.BaseModel` subclass, or a callable — and rejects a `X | Y` union. The comment above that call asserts the opposite ("a union of Pydantic models is exactly how a discriminated multi-variant response is requested"), and the `cast(type, ...)` exists solely to stop mypy objecting to the union. So the one static check that could have caught this was deliberately silenced at the exact line that fails at runtime.

**Why no test caught it.** All four `tests/agents/step_handlers/listing/` files supply a fake chat model whose `with_structured_output(...)` is scripted directly. The real conversion is never invoked, so no test in the suite ever passes `AdvisorResult` to `langchain_openai` at all. That change's own `test-manifest.md` recorded the load-bearing assumption ("a real chat model's `with_structured_output(...)` still funnels through the same underlying call these tests exercise... that expectation is not itself a spec-derived claim") — the assumption was wrong, and nothing was positioned to find out.

## What Changes

- Replace the top-level union passed to `with_structured_output` with a schema `langchain_openai` accepts: a single Pydantic model carrying a discriminator, rather than two sibling models joined by `|`. The two-variant *domain* shape (`Supported` / `Unsupported`) is not what is under question here — only what crosses the model boundary — so the handler's own contract and its `Success`/`Failure` reporting stay as they are.
- Remove the `cast(type, ...)` and the comment asserting the union is accepted. Once the schema is a single `BaseModel`, the cast has nothing to suppress, and the type checker goes back to being able to see this call.
- Add a test that exercises the **real** conversion boundary rather than a fake: assert that whatever schema the handler passes is accepted by `langchain_openai`'s own conversion, with no network call and no model invocation. This is the check whose absence let a 100%-failure regression ship, and it is the reusable half — every future handler using structured output faces the same boundary.

Not in scope: changing what the advisor recommends, its prompt, the finding written onto the product, or anything about how the automation pass handles a handler failure. The pass's catch-and-continue behaviour is correct and stays; a separate concern — that a handler failing 100% of the time is not reported anywhere — is noted below rather than fixed here.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `subcategory-advisor`: the model-facing schema becomes a single discriminated model rather than a union of two, so a recommendation can actually be requested. No change to what a supported or unsupported result means, or to what is recorded from either.

## Impact

- `src/commerce_ops/step_handlers/listing/subcategory_advisor.py` — the schema passed to `with_structured_output`, the removed cast, and whatever unwrapping the `recommend` node does with the parsed result.
- `tests/agents/step_handlers/listing/` — the four existing files' fakes keep working against the handler's seam; one new test covers the real conversion boundary.
- No migration, no configuration, no deployment change. `lp.listing.007` starts resolving again on the next automation pass after the deploy.

## Follow-ups noted, not folded in

- **A handler failing every invocation is not reported.** The pass logs a warning per failure and continues, which is right for one bad step, but 76 consecutive failures produced no alert of any kind — it was found by reading logs on the host by hand. Whether that belongs to `report-overdue-scheduled-runs`' monitoring surface or somewhere else is a separate question.
