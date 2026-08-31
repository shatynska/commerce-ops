## Why

The sub-category advisor's recommendation today only ever becomes prose `evidence` on a launch's step-outcome record — it is never written back onto the product itself. Nothing downstream (a later automated step, a person on the product's own page) can read what sub-category was chosen without re-reading a Slack message or the launch journal. Support for the model's answer is also established today by parsing a hand-written `Verdict:` line off free prose and vetoing it with a regex over that same prose — a mechanism the advisor's own spec already flags as fragile ("the recommendation's wording... nothing constrains").

Separately, `subcategory_advisor` is the first automated step handler this codebase has, built specifically to exercise how automated steps work at all (`docs/deferred-work.md`, *The sub-category advisor's supported path has never run*). More automated handlers are coming, and each will face the same two problems this one has: how to get a structured, schema-validated answer out of a model instead of parsed prose, and how to hand a finding to something later can read. Solving both here, generically enough to reuse, is cheaper now than re-deriving the same shape per handler.

## What Changes

- `subcategory_advisor`'s model call moves from free prose plus a `Verdict:` line and a regex veto (`_split_verdict`, `_ADVISOR_REFUSES`) to a schema-validated structured response: a two-field shape, a laconic recorded value and a comment carrying everything else — for this step, a supported result's comment is required (non-empty; the advisor is prompted to use it for the compliance demands and rejected alternative, though that content is not code-checked — see design.md Decision 2), and an unsupported result's error states why. The recommendation delivered to Slack and stored as evidence is rendered from this structured response rather than being the model's raw prose.
- On a supported result, the proposed sub-category node is written onto the product the step resolved for — written as soon as the handler returns, as a **provisional** value: it is not gated on a person later accepting the step's own pending result in Slack, and can disagree with the step's recorded outcome if that proposal is rejected. The write happens through a port the runtime invokes, not inside the handler itself (see design.md Decision 3 — `subcategory_advisor.py` is barred by `.importlinter`'s `step-handler-boundary` rule from calling into `catalog` directly).
- The generic step-handler contract (`StepContext` / `StepResolution` in `launch-step-automation`) gains a typed result shape — a `Success[T]` / `Failure[E]` pair — a handler may report alongside the `StepOutcome` it proposes, so a handler's finding is available as a value, not only as free text. This is the reusable half of the change: `subcategory_advisor` is its first user, not its only intended one.
- `product-catalog` gains a field on `Product` to hold the advisor's finding, and a use case to record it, following the existing `record_asin` shape (`catalog/application/use_cases.py:46`).
- **BREAKING**: none of the existing handler registration or invocation paths are removed, but `subcategory_advisor`'s produced text no longer comes from unconstrained model prose — a deployment or test relying on the old `Verdict:`-line format would need updating. There are no external consumers of that format outside this repository's own tests.

Not in scope: capturing the *main* category anywhere in commerce-ops (no automated or attestable path exists for it today — see design.md), and any change to when a step's own outcome is held for or released from Slack confirmation (`lp.listing.007` keeps needing confirmation; only the product write moves ahead of that decision).

## Capabilities

### New Capabilities
(none — every change below lands inside an existing capability)

### Modified Capabilities
- `subcategory-advisor`: the model call becomes schema-validated structured output instead of prose-plus-regex; a supported finding is made available for the runtime to write onto the product it resolved for, as a provisional value, independent of the step's own confirmation.
- `launch-step-automation`: the handler contract (`StepContext`/`StepResolution`) gains an optional typed `Success[T]`/`Failure[E]` result a handler may report alongside its proposed `StepOutcome`.
- `product-catalog`: `Product` gains a field for the advisor's finding, and a recording use case that writes it as a standalone fact, independent of stage or any launch state.

## Impact

- `src/commerce_ops/step_handlers/listing/subcategory_advisor.py` — structured output, updated prompt, the graph now reports a typed finding (no catalog access — see design.md Decision 3).
- `src/commerce_ops/launch/application/handler_contract.py`, `ports.py` — the new typed result shape on `StepResolution`, and the `SubCategoryRecorder` port.
- `src/commerce_ops/catalog/domain/product.py`, `catalog/application/use_cases.py`, `catalog/infrastructure/driven/{models.py,product_repository.py}` — new field, new use case, a new Alembic migration.
- Whatever composes the pass's dependencies today (where `SteadyStateStamper` is satisfied) gains the equivalent `SubCategoryRecorder`, and the pass invokes it when a handler reports a supported finding.
- Tests: `tests/agents/step_handlers/listing/*` (structured output replaces the verdict/veto tests), `tests/unit/catalog/*`, `tests/unit/launch/*`.
