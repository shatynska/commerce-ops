## 1. Tests derived from the delta spec

- [x] 1.1 Dispatch `ai-toolkit:openspec-test-writer` over the delta. Two of the four scenarios — *A recommendation names node, demands and alternative* and *A recommendation is readable as it stands* — are reproduced unchanged from the served requirement and are already covered; exclude them. The two new ones are what this change adds: the identifier reaching the model, and the refusal reason naming it
- [x] 1.2 Place them in `tests/agents/step_handlers/listing/`, the tier `AGENTS.md` gives graph tests against stubbed models
- [x] 1.3 Record the baseline: run `uv run pytest`. Both new tests must fail **because the prompt and the reason name the repr**, not because a fixture is missing — that is the defect reproduced, and the strongest form this baseline can take

## 2. The fix

- [x] 2.1 Read the marketplace through its value in `advise_sub_category`. The whole expression, so nothing else is dropped by accident: `marketplace = getattr(product, "marketplace_id", "")` then `str(getattr(marketplace, "value", marketplace))`. The outer default and the `str()` coercion both survive — removing the default turns an absent attribute from an empty marketplace into a raised exception, which `launch-step-automation` then treats as a handler failure recording nothing at all (`design.md` — Decision 1)
- [x] 2.2 Leave `product_name` as it is. It is a plain `str`, so `str(getattr(product, "name", ""))` yields the name and the clause's general sentence is satisfied today — by the type, not by the expression. Note that this is exactly the shape the clause warns against, and that it is correct only for as long as `name` is not a value object: if it ever becomes one, the clause is what obliges this line to change too
- [x] 2.3 Change nothing else in the handler: not the prompt's wording, not the graph, not the verdict mechanism, not the `Proposal` contract

## 3. The fixture that keeps it fixed

- [x] 3.1 Give one fixture a real `MarketplaceId` rather than a bare string, so the handler is exercised against what the pass actually supplies (`design.md` — Decision 2). Without this the fix is a line no test can defend: with a bare string, correct and incorrect code produce identical prompts. Leave the module's other fixtures as they are — they are not the guard, and converting them buys nothing
- [x] 3.2 Assert on the **prompt the model receives**, not on the answer. What a model does with a malformed marketplace is unassertable; what it was asked is not
- [x] 3.2a Assert the **refusal reason** as well as the prompt. `propose()` interpolates the same `marketplace` parameter into the prompt and into all four `Blocked` reasons it composes, so the reason is handler-composed rather than model-produced and is assertable against a stubbed model. Run it against the fixture from 3.1 carrying a real `MarketplaceId`, so it fails before the fix — on a bare string the reason is identical either way and the assertion guards nothing. One read feeds both, so this asserts the same fix from the side an operator actually reads on the launch record
- [x] 3.3 Assert the negative too, covering all three exclusions the scenario names — the type name (`MarketplaceId`), the field name (`value=`) and the quoting around the value. Naming only the first would pass a prompt reading `value='ATVPDKIKX0DER'`. The positive alone passes against a prompt naming both forms

## 4. Verify

- [x] 4.1 Run `uv run pytest` and confirm the new tests pass with no previously passing test weakened, skipped or deleted
- [x] 4.2 Run `ruff check`, `ruff format --check`, `mypy` and `import-linter`
- [x] 4.3 Confirm `git diff` touches only `subcategory_advisor.py` and a test file
- [x] 4.4 Confirm no other site carries the pattern, with a grep that would have caught **this** defect — the first one written for this change matched `str(x.attr)` only, so it could not have matched `str(getattr(x, "attr", ""))`:

      grep -rnE 'str\(\s*getattr\([^,]+,\s*"(sku|asin|marketplace_id)"|str\([a-z_]+\.(sku|asin|marketplace_id)\b|\{[a-z_]+\.(sku|asin|marketplace_id)\}' --include=*.py src/

  Expect exactly one hit before the fix and none after. Two further hits on `product_id` are legitimate and out of this pattern's scope — `automation_pass.py` and `automation_confirmation.py` read an ORM column typed `uuid.UUID`, where `str()` is the correct conversion

## 5. Confirm against the deployment

- [x] 5.1 After merge and deploy, wait for a pass over a launch serving `lp.listing.007` and read the reason recorded, or the pending result produced. The marketplace named must be the identifier. **Confirmed 2026-08-28 08:00 UTC**, against a deploy that landed at 07:37: two launches serving that step recorded reasons naming `'ATVPDKIKX0DER'`, where the run at 06:30 on the previous code had named `'MarketplaceId(value='ATVPDKIKX0DER')'`
- [x] 5.1a **Did not arise** — both passes refused, so there was no supported recommendation to read. Kept as written for the next reader: if the pass instead produces a **supported** recommendation, note that it neither confirms nor refutes the fix: only a refusal reason is obliged to name the marketplace, while a recommendation need name only node, demands and alternative. Read the prompt-level assertion from 3.2 as the standing evidence in that case, and treat a supported result as the better outcome rather than a missing check
- [x] 5.2 Do **not** read an unchanged refusal as the fix having failed (`design.md` — Risks). The product on hand is named `TestProductName13`; a refusal is defensible whatever the marketplace said. What this task checks is the marketplace in the text, not the outcome. **The outcome did stay `blocked` for both launches**, and the guard held: the marketplace in the text changed, which is the whole of what this change promised
