## Why

Every prompt the sub-category advisor has ever sent has named the
marketplace wrongly. Recorded against `TestSKU13`'s launch on 2026-08-28
at 06:30 UTC, in full:

> the sub-category advisor could not support a node choice for
> 'TestProductName13' on **'MarketplaceId(value='ATVPDKIKX0DER')'**

`advise_sub_category` reads the marketplace as
`str(getattr(product, "marketplace_id", ""))`. `MarketplaceId` is a
frozen dataclass, so `str()` gives its **repr**, not the identifier. The
model is therefore asked:

```
Product: TestProductName13
Marketplace: MarketplaceId(value='ATVPDKIKX0DER')
```

The neighbouring line is correct by accident rather than by care:
`product.name` is a plain `str`, so `str()` on it is a no-op. Only the
value object leaks, and it leaks into a live model call and into the
reason recorded on the launch.

This predates the automation runtime's recent work — `28f2066` moved the
handler without introducing it — and it is invisible in the test suite,
where every fixture passes a marketplace as a bare string. Nothing that
runs in CI has ever seen the repr.

**Third instance of one mistake.** `str()` over a frozen dataclass
appeared three times in `add-product-dossier-page`'s own test helpers —
a fixture lookup that could never match, a URL builder that produced
`/admin/products/ProductId(value='…')`, and an assertion demanding the
repr appear on a rendered page. Those were caught because a test failed.
This one is in `src/`, reaches a language model, and fails silently: the
advisor answers, the answer is plausible, and nothing anywhere reports a
malformed prompt.

**What this change does not claim.** It is tempting to say the repr is
why the advisor cannot classify that product. It is not established. The
product it was asked about is named `TestProductName13`, which describes
no real product either, so a refusal is a defensible answer whatever the
marketplace said. Fixing this may well leave the advisor still refusing
on that data. The defect is worth fixing because the prompt is wrong,
not because a particular refusal is attributed to it.

## What Changes

- **The advisor is given the marketplace identifier**, not the repr of
  the value object carrying it. The handler reads through the value the
  way every other consumer of `shared.domain.identity` does.
- **A test fixture carries a real `MarketplaceId`**, so the handler is
  exercised against the object the pass actually supplies rather than
  against a bare string it never receives. This is the half that keeps
  the defect from returning: the fix is one line, and without a fixture
  holding the real type, the next edit re-opens it and CI stays green.

## Capabilities

### Modified Capabilities

- `subcategory-advisor`: the requirement that a recommendation is
  produced from the product's name and marketplace gains a clause on
  *what the marketplace is* — the identifier the catalog holds, as a
  reader of the prompt would recognise it, never a rendering of the
  object carrying it. The obligation to accept a name and a marketplace
  is unchanged; what is added is that the value reaching the model is
  the identifier itself.

`launch-step-automation` is deliberately **not** modified. Its rule that
the system resolves the product and hands it to the handler is correct
and unchanged; what is wrong is one handler's reading of what it was
handed. `product-catalog` is untouched — the catalog stores and answers
correctly, and always has.

## Impact

**Affected code**

- `step_handlers/listing/subcategory_advisor.py` — one read, in
  `advise_sub_category`.
- `tests/agents/step_handlers/listing/` — a fixture supplying the
  marketplace as the value object the pass supplies.

**Explicitly untouched**

The graph, the prompt's wording, the verdict mechanism
`separate-the-verdict-from-the-prose` introduced, the `Proposal`
contract, and every recording path. This change alters one value on its
way into an existing call.

**The standing record**

The `Blocked` outcome on `lp.listing.007` naming the repr stays as it
is. It is an accurate record of what was asked and what came back, and
rewriting history to hide a defect the system genuinely had is not this
change's business.
