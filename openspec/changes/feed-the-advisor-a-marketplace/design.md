## Context

See `proposal.md` — *Why*. Only what shapes the approach follows.

`advise_sub_category` reads its two inputs off the resolved product:

```python
product_name=str(getattr(product, "name", "")),
marketplace=str(getattr(product, "marketplace_id", "")),
```

`name` is a plain `str`, so the first line is a no-op and correct by accident. `marketplace_id` is a `MarketplaceId` — `@dataclass(frozen=True, slots=True)` with a single `value: str` and no `__str__` — so the second yields `MarketplaceId(value='ATVPDKIKX0DER')`.

The same shape occurs safely elsewhere. `product_dossier.py` reads `getattr(product.sku, "value", product.sku)`, which unwraps the object where there is one and passes a bare string through unchanged. That is the idiom this repository already has; the advisor simply does not use it.

**The same variable feeds the prompt and the reason.** `propose()` takes `marketplace` as a parameter, interpolates it into the prompt, and interpolates the same parameter into all four `Blocked` reasons it composes. The refusal reason is handler-composed, not model-produced — so the one read at the top fixes both, and the delta's scenario about the reason is assertable against a stubbed model rather than being a claim about model output.

**One site, on a grep that can see it.** The first grep written for this change matched `str(x.attr)` and so could not have matched `str(getattr(x, "attr", ""))` — the defect's own shape. A broad sweep covering the `getattr` form and including `product_id` finds three hits: this one, and two on ORM rows whose `product_id` is a `uuid.UUID` column (`automation_pass.py`, `automation_confirmation.py`), where `str()` is the correct conversion. Task 4.4 carries the narrowed pattern — the three identity value objects, without `product_id` — and therefore expects exactly one hit before the fix and none after. So the claim stands, but it now rests on a grep that would have found the live defect rather than on one that demonstrably would not.

## Goals / Non-Goals

**Goals:**

- The model is asked about the marketplace the catalog holds.
- A test exercises the handler against the object the pass actually supplies, so the defect cannot return green.

**Non-Goals:**

- Changing the prompt's wording, the graph, the verdict mechanism, or the `Proposal` contract.
- Making the advisor classify `TestProductName13`. See *Risks*.
- Rewriting the `Blocked` outcome already recorded naming the repr.

## Decisions

### Decision 1 — Unwrap with the idiom already in the repository

`getattr(value, "value", value)`, as `product_dossier.py` uses, rather than `product.marketplace_id.value`.

The direct attribute access is shorter and, on today's types, equivalent. The `getattr` form is chosen because it keeps working against a product double that supplies a bare string — which is what every existing fixture does, and what a handler test would naturally construct. A handler that only accepts the real value object would force every test to build one, which is a cost with no safety in it: the *handler* does not care whether it was handed an object or a string, only that what it forwards is the identifier.

**What this does not do is make bare-string tolerance a promise.** The production path always supplies a value object — the system resolves the product and hands it over, and a marketplace identifier is required at registration — so the tolerance exists for test doubles and for nothing else. It is deliberately *not* stated in the delta: a served capability spec obliging every future implementation to accept an input that cannot arise would be a test convenience written into public behaviour, and would foreclose the `.value` refactor below on the record. That refactor stays available.

**The cost, named rather than glossed.** `getattr` with a default returns `Any`, so the fixed expression is outside `mypy`'s reach — as the broken one was. `product.marketplace_id.value` would be typed `str` and would fail type-checking if the product's marketplace type ever changed. That is real static protection given up, and it is given up knowingly: the *Risks* note that "`mypy` cannot help" is true of the defect but would be misleading about the remedy if left unqualified. The trade is tolerance for doubles over a type check, and it is only defensible because Decision 2 supplies a test that does what the type check would have.

That reasoning cuts the other way for the fixture — see Decision 2.

### Decision 2 — One fixture holds the real value object, deliberately

The fix is a single expression, and a single expression is exactly what a later edit reverts without noticing. What keeps it fixed is a test that fails when it is reverted, and no such test can exist while every fixture passes a bare string: with a string, correct and incorrect code produce identical prompts.

So one fixture supplies a real `MarketplaceId`, and two tests run against it: one asserting the prompt names the identifier and carries nothing else of the object's rendering, one asserting the same of the refusal reason the launch keeps. That is this change's whole test surface, and it is the half that matters — the other half is a line anyone could have written.

Asserting on the prompt rather than on the model's answer is deliberate: what the model *does* with a malformed marketplace is unknowable and unassertable, and the requirement is about what it was asked.

### Decision 3 — The recorded `Blocked` outcome stays

`lp.listing.007` on `TestSKU13` carries a reason naming `MarketplaceId(value='ATVPDKIKX0DER')`. It is an accurate record of what the system asked and what came back, and the launch record is not a place to hide a defect the system genuinely had. It will age out when the step is resolved.

## Risks / Trade-offs

**Fixing this may not change what the advisor answers** → The product it refused is named `TestProductName13`, which describes no real product, so a refusal is defensible whatever the marketplace said. Do not read an unchanged answer as the fix having failed. Confirming the supported path needs a product with a name a model can classify — which is `separate-the-verdict-from-the-prose`'s task 6.1, unobservable for the same reason.

**No test can prove the live prompt is right** → The assertion is on what the handler forwards, against a stubbed model. That is the standing arrangement for every agent graph here, and this change does not alter it. What it does close is the specific hole that made the defect invisible: a fixture type that could not distinguish correct code from incorrect.

**One site today, no guard against the next** → This is the third instance of `str()` over a frozen dataclass in this repository, and nothing mechanical prevents a fourth. `mypy` cannot help: `str(anything)` is well-typed, and so is `getattr(x, "value", x)`, so neither the defect nor the remedy is statically visible (see Decision 1). A lint rule is conceivable but would need to know which attributes are value objects. Left unaddressed deliberately rather than solved badly — the pattern is worth naming in review, not automating on this evidence. What *is* mechanical is task 4.4's grep, and it is only worth having in a form that would have caught this one.

## Migration Plan

None. No schema, no stored shape, no configuration, no recorded outcome revisited. Rollback is reverting the merge.

## Open Questions

None. The defect, its cause and its blast radius are all established.
