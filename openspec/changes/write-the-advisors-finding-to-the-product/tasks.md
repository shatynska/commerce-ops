## 1. Shared result type

- [x] 1.1 Add `Success[T]` / `Failure[E]` (and the `Result = Success[T] | Failure[E]` alias) to a new `src/commerce_ops/shared/domain/result.py`, frozen dataclasses, no I/O. Both carry `value`/`error` respectively plus an optional `comment: str | None = None` — the universal two-field shape every automated handler's finding is expected to take, not something reintroduced per-handler.
- [x] 1.2 Export it from `shared.domain`'s public surface alongside the module's existing vocabulary types.

## 2. Handler contract

- [x] 2.1 Add an optional `finding: Result[Any, Any] | None = None` field to `StepResolution` (`launch/application/handler_contract.py`), defaulting to `None` so every existing handler is unaffected.
- [x] 2.2 Add `SubCategoryRecorder` to `launch/application/ports.py`, shaped like `SteadyStateStamper` (`record_sub_category`'s signature minus the store).
- [x] 2.3 In the pass that invokes handlers (`launch-step-automation`'s runtime), after the existing hazard-permission check on the proposed outcome passes (a proposal that fails it is a handler fault — no recorder invocation, exactly as no outcome is recorded), where the handler's resolution carries a `Success` finding and a recording capability has been supplied for that step, invoke it with the finding's value before the outcome/result routing (record-directly vs. hold-for-confirmation) runs. Where none is supplied, do nothing — not an error.
- [x] 2.4 Make a recording-capability failure report the launch, step and handler (mirroring the existing handler-failure report) without recording any step outcome and without stopping the pass.

## 3. Catalog: field, use case, migration

- [x] 3.1 Add `sub_category: str | None` to `Product` (`catalog/domain/product.py`) and a `record_sub_category(self, sub_category: str) -> None` method, mirroring `record_asin`.
- [x] 3.2 Add `record_sub_category` to `catalog/application/use_cases.py`, mirroring `record_asin`'s shape (store, product_id, value; no confirmer).
- [x] 3.3 Export `record_sub_category` from `catalog.application`'s public surface.
- [x] 3.4 Add the column to `catalog/infrastructure/driven/models.py` and `product_repository.py` (read and write paths).
- [x] 3.5 Write the Alembic migration adding the nullable column; no backfill.

## 4. Composition-root wiring

- [x] 4.1 Wherever `SteadyStateStamper` is satisfied today (partial application of `catalog.application.change_stage` over the store), add the equivalent partial application of `catalog.application.record_sub_category` satisfying `SubCategoryRecorder`.
- [x] 4.2 Wire that recorder as the recording capability supplied for `lp.listing.007` specifically — not for every step — at the same composition point that resolves handlers today.

## 5. Subcategory advisor

- [x] 5.1 Define the `Supported` / `Unsupported` structured-output schema, mirroring `Success`/`Failure`'s two-field shape exactly: `value: str` (the sub-category node) + optional `comment` on `Supported`; `error: str` + optional `comment` on `Unsupported`. No `compliance_demands` or `rejected_alternative` fields — the prompt (5.2) asks the model to put that content in `comment`, but nothing in code parses `comment` for it.
- [x] 5.2 Rewrite the prompt in `_PROMPT` for structured output: drop the `Verdict:` line instruction, since the schema itself now carries the discriminant; instruct the model to use `comment` for the compliance demands and the rejected alternative on a supported response.
- [x] 5.3 Replace `model.invoke(...)` plus `_split_verdict` with `model.with_structured_output(AdvisorResult, include_raw=True)` in the `recommend` node; remove `_split_verdict` and `_VERDICT_LINE`.
- [x] 5.4 Narrow `_ADVISOR_REFUSES` / `_advisor_refuses` to scan only `comment` (not `value`, and not a full rendered response) — `comment` is the sole free-form field left for the veto to run over.
- [x] 5.5 Rewrite `propose()` with three routes to an unsupported/non-terminal outcome, checked in this order, on top of the existing `Unsupported` branch:
  1. Schema validation failed entirely (neither variant produced) → unsupported, reason states no verdict could be read (5.6).
  2. Validates `Supported` but `comment` is empty → unsupported, same "no verdict could be read" reason as (1) — a completeness shortfall, not a finding about the product (no check of *what* the comment contains beyond emptiness).
  3. Validates `Supported`, `comment` non-empty, but `_advisor_refuses(comment)` (5.4) returns true → unsupported, reason names the contradiction between the verdict and the comment — distinct wording from (1)/(2), since this *is* a finding, not a shortfall.
  Otherwise: `Supported` — render `result` from `value` + `comment`, and set `finding=Success(value=value, comment=comment)`. On `Unsupported`, render `result` from `error` (+ `comment` if present); `finding` stays unset in every non-terminal route above.
- [x] 5.6 Implement routes 1–2 above as the fail-safe direction: both are "shortfalls" (the model answered but not usably) and share one reason. Only content that is not plain text at all (a transport/client-level fault, prior to schema validation) surfaces as a visible model failure — distinct from all three unsupported routes, which never crash.
- [x] 5.7 Update the module docstring's description of the verdict/veto mechanism, since both are gone.

## 6. Tests

- [x] 6.1 Update `tests/agents/step_handlers/listing/test_subcategory_advisor_verdict.py` (or replace it) to drive the graph with a stubbed structured-output model, covering every route in 5.5: supported with a non-empty, non-contradicting comment → `Satisfied` + `Success` finding + rendered result containing both `value` and `comment`; supported with a comment that omits the compliance demands or the alternative → still `Satisfied` (content is never checked — assert this explicitly, per the "A comment's content is never checked by code" scenario); supported with a comment describing a *rejected alternative* as unsupportable → still `Satisfied` (that is a statement about the alternative, not a contradiction — the "The recommendation's wording does not establish the outcome" scenario); supported with an *empty* comment → route 2, unsupported, no finding; supported but comment itself states the advisor cannot assign a node → route 3, unsupported, no finding, reason names the contradiction (not "no verdict could be read") — the "A verdict contradicting its own prose withholds satisfaction" / "A vetoed verdict names the contradiction" scenarios; unsupported → `Blocked` + no finding, and two differently-worded unsupported responses both propose it (`ok` alone decides, never text search — "A refusal is recognised however it is worded"); a response failing schema validation → route 1, `Blocked`, reason states no verdict could be read, no finding, no crash; content that is not plain text at all → surfaced failure, no outcome proposed.
- [x] 6.2 Update `tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py` for the new node shape.
- [x] 6.3 Confirm `tests/agents/step_handlers/listing/test_subcategory_advisor_marketplace.py` still passes unchanged (marketplace-identifier handling is untouched) or update it for the new prompt only where the prompt text itself is asserted on.
- [x] 6.4 Add unit tests for `catalog.application.record_sub_category` and `Product.record_sub_category`, mirroring the existing `record_asin` tests (mirrored recorded value, replacement on re-recording, works in `Retired`, and reports absence — not an empty string — when nothing has been recorded).
- [x] 6.5 Add unit tests for the pass's new recording-capability step: invoked on a `Success` finding when a recorder is supplied; not invoked when none is supplied; recorder failure reported without aborting the pass or recording a step outcome; never invoked for a `Failure` finding; never invoked when the proposed outcome fails the hazard-permission check, even alongside a `Success` finding (the "An impermissible proposal's finding is never recorded" scenario).
- [x] 6.6 Add a unit test asserting `StepResolution` accepts no `finding` (defaults to `None`) so every pre-existing handler's tests remain valid unchanged. Also cover: a `finding` reported alongside a terminal outcome on a step needing confirmation is still held as a pending result, not recorded directly ("A finding's presence does not change confirmation"); and a `finding`'s presence changes nothing about how the outcome is recorded or the result stored as evidence ("A finding changes nothing about the outcome or the result").

## 7. Verification

- [x] 7.1 `uv run pytest` (full `tests/unit` + `tests/agents` tier).
- [x] 7.2 `ruff check` / `ruff format --check`.
- [x] 7.3 `mypy`.
- [x] 7.4 `import-linter` (confirm `step-handler-boundary` still passes — `subcategory_advisor.py` must import nothing from `commerce_ops.catalog`).
- [x] 7.5 Run the new Alembic migration against a local database and confirm it applies and rolls back cleanly.
