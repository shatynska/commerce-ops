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

- Replace the top-level union passed to `with_structured_output` with a schema `langchain_openai` accepts: a **single flat model** whose `ok` field is the discriminant and whose `value`, `error` and `comment` are independent optional fields — not two sibling models joined by `|`, and not a model wrapping a discriminated union of the two. That last shape passes every check runnable offline and still emits `oneOf`, which OpenAI's strict structured outputs do not support, so it would fail at the API exactly as the union fails at conversion (see `design.md`). The two-variant *domain* shape (`Supported` / `Unsupported`) is not what is under question here — only what crosses the model boundary — so the handler's own contract and its `Success`/`Failure` reporting stay as they are.
- Define what **every** field combination the flat schema can express converts to, including the ones a well-behaved model should never send. A flat shape can report support while carrying the error that withholds it; converting that to a supported result would drop a refusal and put `Satisfied` in front of a person on a compliance-relevant step. The conversion table is in `design.md` and each row is a scenario in the delta.
- Give each wire field a description, restoring in the schema the coupling the union carried in its shape (a supported variant could not exist without its value). Without it, the likelier failure is not a crash but a quality regression: inconsistent responses route to the specified "no verdict could be read" path, so the step stays inert while the suite is green.
- Remove the `cast(type, ...)` and the comment asserting the union is accepted. Once the schema is a single `BaseModel`, the cast has nothing to suppress, and the type checker goes back to being able to see this call.
- Add a test that exercises the **real** conversion boundary rather than a fake: assert that the schema the handler actually passes at its call site — captured through the `build_graph(model)` seam, not imported as a symbol that could drift from it — is accepted by `langchain_openai`'s own conversion, with no network call and no model invocation. This is the check whose absence let a 100%-failure regression ship. Every future handler using structured output faces the same boundary, but this change scopes the requirement to `subcategory-advisor` and makes no provision binding on another handler; generalising it is deferred, and would belong to `launch-step-automation`'s handler contract rather than here.
- Update the four existing `tests/agents/step_handlers/listing/` files, whose fakes script domain `Supported`/`Unsupported` objects as the model's parsed response — exactly the object this change re-types.

Not in scope: changing what the advisor recommends, its prompt, the finding written onto the product, or anything about how the automation pass handles a handler failure. The pass's catch-and-continue behaviour is correct and stays; a separate concern — that a handler failing 100% of the time is not reported anywhere — is noted below rather than fixed here.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `subcategory-advisor`, in three parts:
  - **ADDED** — the model-facing schema must be one the provider adapter accepts, verified against that adapter's own conversion rather than a double; where the wire shape differs from the reported shape, every combination it can express must map somewhere, and its fields must state when they are to be populated.
  - **MODIFIED** — *The advisor proposes satisfaction only where it can support a node choice*. Its rule that support is established "only by the structured verdict discriminant… and never by the value" no longer holds once the wire shape lets a discriminant arrive without its field: support now requires the discriminant **together with** the field its variant requires, and a supporting discriminant carrying a reported error withholds satisfaction as a contradiction. Left unmodified, the archived spec would assert a rule the code breaks in the dangerous direction — a reader would treat `ok: true` with no value as support.

  - **MODIFIED** — *A recommendation is produced from the product's name and marketplace*, for terminology only. It speaks of a response that "validates as supported"; once the wire schema has no supported variant, no response validates as supported, so those clauses are restated as "established as supported". No behaviour changes — the empty-comment route is untouched.

  No change to what a supported or unsupported result means to a reader, or to what is recorded from either.

## Impact

- `src/commerce_ops/step_handlers/listing/subcategory_advisor.py` — the schema passed to `with_structured_output`, the removed cast, the wire→domain conversion, a `Contradiction` carrier for a response that reports support while carrying the error withholding it, and the widening of `AdvisorState.parsed` to admit it.
- `tests/agents/step_handlers/listing/` — the four existing files' fakes are updated to script wire responses; their domain-level assertions are unchanged. `tests/unit/step_handlers/listing/` gains the conversion-boundary guard.
- No migration, no configuration, no deployment change. `lp.listing.007` starts resolving again on the next automation pass after the deploy.

## Follow-ups noted, not folded in

- **A handler failing every invocation is not reported.** The pass logs a warning per failure and continues, which is right for one bad step, but 76 consecutive failures produced no alert of any kind — it was found by reading logs on the host by hand. Whether that belongs to `report-overdue-scheduled-runs`' monitoring surface or somewhere else is a separate question.
