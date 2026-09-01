## Context

Established by reading the installed libraries and by running their own conversion functions locally — not inferred from the traceback alone. Versions on the deployed image and in the lockfile: `langchain_openai` 1.6.0, `langchain_core` 1.6.0, `pydantic` 2.13.4.

1. **`ChatOpenAI.with_structured_output` defaults to `method="json_schema"`** (`chat_models/base.py:3723`), unlike its base class, which defaults to `"function_calling"` (`base.py:2503`). The advisor passes no `method`, so it takes the `json_schema` path.

2. **That path converts the schema twice, and a union fails both times.** It calls `_convert_to_openai_response_format(schema, strict=strict)` and, for its `ls_structured_output_format` metadata, `convert_to_openai_tool(schema)`. Confirmed by running both against the advisor's current `Supported | Unsupported`:

   | schema | `_convert_to_openai_response_format` | `convert_to_openai_tool` |
   |---|---|---|
   | `Supported \| Unsupported` (current) | `ValueError: Unsupported function` | `ValueError: Unsupported function` |
   | single `BaseModel`, flat fields | accepted | accepted |
   | `BaseModel` wrapping a discriminated union | accepted | accepted |

   So fixing only the response-format path would leave the second conversion failing.

3. **Why a single `BaseModel` is accepted at all** is the first branch of `_convert_to_openai_response_format`: `if isinstance(schema, type) and is_basemodel_subclass(schema): return schema` — it is handed to the provider untouched. A `X | Y` union is a `types.UnionType`, not a `type` in that sense, so it falls through to `convert_to_openai_function`, whose contract is a dict, a `BaseModel` subclass, or a callable.

4. **The existing tests script domain objects at the seam this change re-types.** All four files in `tests/agents/step_handlers/listing/` return `{"raw": …, "parsed": Supported(ok=True, value=…, comment=…)}` from a scripted `with_structured_output` (`test_subcategory_advisor_structured_verdict.py:165, 283, 297, 330, 346`). `parsed` is exactly what a wire shape changes, so those fakes describe a response the model will no longer produce. They must be updated with this change, not merely re-run.

## Decisions

### The wire schema is a single flat model, not a discriminated-union envelope

Two shapes pass both conversions. They are not equally safe.

A `BaseModel` wrapping `Annotated[Supported | Unsupported, Field(discriminator="ok")]` produces this for its one property:

```json
{"oneOf": [{"$ref": "#/$defs/Supported"}, {"$ref": "#/$defs/Unsupported"}],
 "discriminator": {"propertyName": "ok", "mapping": {...}}}
```

`oneOf` is the problem. OpenAI's strict structured outputs support `anyOf`, not `oneOf` — so this shape passes every check that can be run locally and is still liable to be rejected by the API itself, at which point the advisor fails exactly as it does today and the fix has bought nothing. The local `openai.lib._pydantic.to_strict_json_schema` helper accepts it, which makes this failure mode *worse*, not better: the check most obviously reached for would pass while production still failed.

A flat model — `ok: bool`, `value: str | None`, `error: str | None`, `comment: str | None` — emits a plain object with nullable string properties and no `oneOf` anywhere. It depends on nothing this codebase cannot verify offline.

Rejected for a different reason: passing a hand-written JSON-schema dict with a top-level `title`. It is accepted, and it would put the schema and the domain types in two places that must be kept in agreement by hand, with nothing checking that they agree.

### The conversion rule is exhaustive, and named here rather than left to the implementation

The flat shape's cost is that it can express states the domain forbids. That cost is only paid if the conversion states what *every* expressible combination means. The union appeared not to have this cost; it did, and merely moved the rejection into pydantic's validator, where the answer was always "neither variant".

The rule, in order:

| wire response | maps to | reason recorded |
|---|---|---|
| `ok: true`, non-blank `value`, blank `error` | `Supported` | — (subject to the existing comment veto) |
| `ok: true`, non-blank `error` | **contradiction** | names the contradiction |
| `ok: true`, blank or absent `value` | neither | no verdict could be read |
| `ok: false`, non-blank `error` | `Unsupported` | the advisor's own error |
| `ok: false`, blank or absent `error` | neither | no verdict could be read |

Blank means empty or whitespace-only, not merely `None` — a model that must emit every field under strict output will emit `""` where it means "not applicable".

The order is load-bearing where rows 2 and 3 overlap: `ok: true` with a blank `value` **and** a non-blank `error` matches both, and row 2 wins. That precedence is stated normatively in the delta rather than left to this table's ordering, because the table is not what gets archived. The reasoning: such a response has said *why* no node could be named, and the shortfall route would discard that explanation and record only "no verdict could be read" — the same loss row 2 exists to prevent, one field over.

The second row is the one that matters, and it is the row a naive conversion gets wrong. A response reporting `ok: true` while its `error` states why no node can be named is a response contradicting itself; discarding the `error` as surplus to a supported result is how a refusal reaches a person as a `Satisfied` proposal on a compliance-relevant step. It joins the existing contradiction route — the same one the comment veto uses — so the reason names the contradiction rather than claiming the advisor declined a classification.

Note that `ok: false` with a populated `value` is deliberately *not* a contradiction, and the asymmetry with row 2 is deliberate rather than an oversight. Row 2 is caught for the accuracy of the *reason*, not merely for the outcome: its surplus field is the one that withholds support, so discarding it makes the recorded reason misstate what happened. In row 4 the discriminant and the error already agree with each other — the response withholds and says why — and the surplus value adds no claim the reason misstates. The reason may therefore name the error as a considered decline, because that is what it is. The outcome is withheld either way; only row 2 would have the reason wrong.

### The contradiction is a distinct outcome, and `AdvisorState` widens to carry it

Row 2 gives the conversion a fourth outcome — supported, unsupported, contradiction, neither — and `AdvisorState.parsed` currently admits only `Supported | Unsupported | None` (`subcategory_advisor.py:217-226`). There is nowhere to put a contradiction, and every way of forcing one through the existing shape produces a result the delta forbids:

- Returning `None` takes the "no verdict could be read" path — right outcome, wrong reason, and the reason-naming obligation exists precisely so an operator can tell those two states apart.
- Returning `Unsupported(error=…)` renders "the sub-category advisor could not support a node choice: …", asserting a classification considered and declined, which is what the requirement forbids for this case.
- Folding the error into `comment` and returning `Supported` is the dangerous one. It looks like it works, because the existing veto route reads the comment — but `_advisor_refuses` matches on a first-person subject (`_REFUSING_SUBJECT` at `subcategory_advisor.py:118`: `i|we|the advisor|this advisor`), and a model-authored error such as "the category tree gave no confident answer for this product" has none. The veto does not fire, and the response is proposed **`Satisfied`** — the exact defect row 2 was written to prevent, reached through the fix for it.

So the conversion returns a three-way result plus `None`, with a `Contradiction` carrier holding the reported value, the error and the comment, and `AdvisorState.parsed` widens to admit it. `AdvisorState` is therefore **not** on the list of types this change leaves alone.

Moving the whole conversion into `propose()` instead, so it branches four ways over the wire response directly, is a defensible alternative — but it makes `parsed` carry the wire type, which changes `AdvisorState` just the same. The amendment cannot be avoided, only relocated.

**What a reader sees.** The contradiction's rendered text SHALL carry the reported error, so the refusal is visible to the person reading it in Slack or on the product's record. This is not automatic: the existing comment-based veto renders `_render_supported(value, comment)` and is legible only because there the comment *is* the refusal. An error-based contradiction may arrive with a blank comment, and rendering it the same way would show a reader a bare node path while the record says the outcome was withheld for a contradiction — against the retained requirement that the rendered text still says so where support is withheld.

### Each wire field carries a description

The union coupled its fields structurally: a `Supported` could not exist without its `value`. Four independent nullable fields drop that coupling, and dropping it silently is what would turn a schema fix into a quality regression — the model is likelier to fill fields inconsistently, every inconsistent response routes to "no verdict could be read", and `lp.listing.007` stays unresolved while the suite is green and nothing alerts.

So each field carries a `Field(description=…)` stating what it is for and when to populate it. This is offline-verifiable, needs no prompt change, and restores in the schema what the union carried in its shape. Whether the *prompt* also needs to change is not decidable from any test that scripts the wire response — it is a question only the live verification in `tasks.md` section 4 can answer, and it is gated there rather than on a test that cannot produce that evidence.

### The domain variants stay exactly as they are

`Supported` and `Unsupported` are unchanged, and `AdvisorResult` remains their union — as a *domain* type, which is what the rest of the module, the `Proposal`, the rendered text and the typed finding are written against. What a caller receives for a supported or an unsupported result is identical to today.

The one exception is the `Contradiction` carrier above, and it is an addition rather than a change: no existing variant's fields, rendering or finding move, and nothing that reads a `Supported` or an `Unsupported` today sees anything different.

### The delta modifies the discriminant rule, and does not only add to it

An earlier draft of this change carried an ADDED-only delta, on the reasoning that the served fail-safe ("content satisfying neither variant" → unsupported) already governs an inconsistent wire response. That reasoning holds for the fail-safe and fails for a different sentence in the same requirement:

> Support SHALL be established only by the structured verdict discriminant the advisor reports, and never by the value or the comment that accompanies it — except in the one direction named below.

After this change the discriminant alone no longer establishes support: the presence of `value` participates, and a populated `error` withholds. That is a second and third exception to a sentence whose own text is exhaustive about having one. Left unmodified, the archived spec would assert a rule the code breaks, in the dangerous direction — a future implementer reading it would treat `ok: true, value: null` as support. So the requirement is MODIFIED, restating support as *the discriminant together with the field its variant requires*, and naming both withholding directions.

The scenarios keyed on "neither variant **of the schema**" are re-worded in the same delta: the wire schema has no variants, so that phrasing would describe nothing after this change.

### `cast(type, ...)` goes, and does not come back

The current call reads:

```python
structured = model.with_structured_output(cast(type, AdvisorResult), include_raw=True)
```

with a comment asserting the union "is exactly how a discriminated multi-variant response is requested" and that the stub is "narrower than what it accepts at runtime". The second half is false in the direction that matters: the stub was *right*, the runtime accepts less than the code assumed, and the cast existed solely to stop mypy saying so. A single `BaseModel` needs no cast, so the type checker gets this call back.

This is the part worth carrying forward beyond this change. A cast that silences a type error at a boundary the tests fake is a blind spot in both of the project's mechanical checks at once, and this is what one costs: a step that was inert in production for as long as it took someone to read the logs by hand.

### The new test converts the schema the call site passes, not an imported symbol

The added test calls the provider adapter's own conversion functions — no model, no network, no credential, since `_convert_to_openai_response_format` and `convert_to_openai_tool` are pure functions over a schema. It belongs in the unit tier, not the agents tier, because it tests a library contract rather than graph behaviour.

It obtains the schema by capturing the first argument to `with_structured_output` through the existing `build_graph(model)` seam, rather than importing the wire model directly. Converting an imported symbol would leave the call site free to drift away from it — the guard would keep passing while the advisor passed something else, which is the failure it exists to prevent.

Naming the private `_convert_to_openai_response_format` in a test is a deliberate, recorded trade: it is the exact function that failed in production, and asserting against `convert_to_openai_tool` alone would not have caught this defect had the failure gone the other way. A `langchain_openai` upgrade that renames it will break this test loudly, which is the correct outcome — the schema contract it guards is exactly what such an upgrade could change.

## Risks

- **The API could still reject a schema that both local conversions accept.** The flat shape is chosen to minimise this (no `oneOf`, no nested `$defs` beyond the nullable strings pydantic emits for optional fields), but no offline check can fully establish what the provider's API accepts. The verification step is a live invocation on the host after deploy, not a green test suite.
- **Response quality, not just schema acceptance, decides whether this fix works.** A flat schema the model fills inconsistently produces a *specified* outcome — "no verdict could be read" — so nothing fails and nothing alerts, and the step stays as inert as it is today. Field descriptions are the mitigation; `tasks.md` 4.2's requirement to observe an actual resolution, not merely an absent error, is the check.
- **Structured output may now return an inconsistent response where it previously raised.** Before, pydantic rejected `ok: true` with no `value` during parsing; now the advisor rejects it during conversion. The observable behaviour is specified to be identical, which is what the delta's mapping scenarios exist to pin.
- **The 76 failures a day stop, and nothing announces that they have.** Confirming the fix means looking at the host again. There is no alert on this handler's failure rate, which is recorded as a follow-up in `proposal.md` rather than fixed here.
