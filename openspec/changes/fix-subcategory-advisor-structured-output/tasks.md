## 1. Tests derived from the delta spec

Written before the implementation, from the delta's scenarios rather than from the code.

- [x] 1.1 `tests/unit/step_handlers/listing/` — the schema the advisor passes is accepted by `langchain_openai`'s `_convert_to_openai_response_format` **and** by `langchain_core`'s `convert_to_openai_tool`, with no model call, no network and no credential. Covers *The schema is accepted by the provider's own conversion*.
- [x] 1.2 That test obtains the schema by capturing the first argument to `with_structured_output` through the `build_graph(model)` seam — not by importing the wire model — so a call site that drifts from the symbol is detected. Covers *The converted schema is the one the call site passes*.
- [x] 1.3 Each wire field carries a non-empty `description` in the generated JSON schema. Covers *Wire fields state when they are to be populated*.
- [x] 1.4 `tests/agents/step_handlers/listing/` — the conversion table, one case per row, covering *Every wire combination has a defined destination* and the five MODIFIED scenarios below. Pin **both** of `value` and `error` in every case, so no two cases admit the same input — rows 2 and 3 overlap on `ok: true` with a blank value and a non-blank error, where row 2 takes precedence:
  - `ok: true` + non-blank `value` + blank `error` → satisfying outcome (*A supported choice proposes satisfaction*)
  - `ok: true` + non-blank `error` → non-terminal, reason names the contradiction, **and the rendered text carries the reported error**, with the reason naming the *error* as what withheld support rather than the comment — assert the wording, not merely that the outcome is non-terminal, since the dangerous implementations of this row differ from the correct one only in what they record and show (*A supporting discriminant carrying a reported error withholds satisfaction*)
  - `ok: true` + `value` absent, `""`, or whitespace + **blank `error`** → non-terminal, reason states no verdict could be read (*A supporting discriminant without its value is not support*)
  - `ok: true` + blank `value` + **non-blank `error`** → the contradiction route, not the shortfall one: reason names the contradiction and the rendered text carries the error. This is the overlap case, and it is where an implementation that checks the missing value first goes wrong.
  - `ok: false` + non-blank `error` → non-terminal, reason is the advisor's own error (*An unsupported choice proposes no satisfaction*)
  - `ok: false` + `error` absent, `""`, or whitespace → non-terminal, reason states no verdict could be read (*A withholding discriminant without its error is not a refusal*)
- [x] 1.5 A supported wire response produces the same rendered text and the same typed finding as the current supported path, and an unsupported one the same refusal text, using real wire instances rather than domain ones. Covers *The reported variants are unchanged by the wire shape*.
- [x] 1.6 Update the four existing files in `tests/agents/step_handlers/listing/` so their fakes script **wire** responses; their domain-level assertions stay unchanged. They currently script `{"parsed": Supported(...)}` (`test_subcategory_advisor_structured_verdict.py:283, 297, 330, 346`), which is exactly the object this change re-types — so they describe a response the model can no longer produce. Do **not** make them pass by adding an `isinstance` passthrough for domain variants in the conversion: that would shape production code to a test double.

## 2. Implementation

- [x] 2.1 Add the wire model to `subcategory_advisor.py`: a single `BaseModel` with `ok: bool`, `value: str | None`, `error: str | None`, `comment: str | None`, each carrying a `Field(description=…)` stating what it is for and when to populate it.
- [x] 2.2 Pass it to `with_structured_output(..., include_raw=True)` in the `recommend` node, replacing `cast(type, AdvisorResult)`. Remove the `cast` and the comment asserting a union is accepted.
- [x] 2.3 Implement the conversion exactly as `design.md`'s table states, treating blank as empty-or-whitespace, not merely `None`:
      supported requires `ok is True` **and** non-blank `value` **and** blank `error`;
      `ok is True` with a non-blank `error` joins the contradiction route **whether or not a value accompanies it** — test this branch before the missing-value one, or the overlap case takes the wrong route;
      `ok is False` with a non-blank `error` is unsupported;
      every other combination yields `None` and joins the existing "no verdict could be read" path.
- [x] 2.4 Add a `Contradiction` carrier holding the reported value, error and comment, and widen `AdvisorState.parsed` to admit it alongside `Supported | Unsupported | None`. Do **not** attempt to carry a contradiction as one of the existing variants: returning `None` records the wrong reason, returning `Unsupported` asserts a decline that did not happen, and folding the error into `comment` proposes `Satisfied` — `_advisor_refuses` requires a first-person subject (`subcategory_advisor.py:118`) that a model-authored error will not have. See `design.md`.
- [x] 2.5 Render a contradiction so the reported **error** is visible to the reader, not only recorded as the outcome's reason. An error-based contradiction may arrive with a blank comment, so rendering it the way the existing comment veto does (`_render_supported(value, comment)`) would show a bare node path with no refusal in it.
- [x] 2.6 Make the recorded reason name the field that actually withheld support. `_contradiction_reason` (`subcategory_advisor.py:163-169`) hardcodes "a supporting verdict that its **own comment** contradicts" — reused verbatim for an error-based contradiction, which may carry no comment at all, it names the wrong field, against the requirement that the reason name what was actually wrong. Generalise it, or add a second reason for the error-based case.
- [x] 2.7 Leave `Supported`, `Unsupported`, `AdvisorResult`, `Proposal`, `_render_supported` and `_render_unsupported` unchanged. `AdvisorState` and `_contradiction_reason` are deliberately absent from this list — 2.4 widens the first, 2.6 generalises the second.
- [x] 2.8 Leave the prompt alone. Whether it needs to name the wire fields is not answerable by any test that scripts the wire response; the field descriptions in 2.1 are this change's answer, and section 4's live verification is what would reopen it.

## 3. Verification

- [x] 3.1 `uv run pytest tests/unit tests/agents` green.
- [x] 3.2 `uv run mypy .` green **without** any `cast` or `type: ignore` at the structured-output call — if one is needed to pass, the schema shape is wrong, not the type checker.
- [x] 3.3 `uv run ruff check` and `uv run ruff format --check` clean.
- [x] 3.4 `uv run lint-imports --config .importlinter` green (the handler's boundary is untouched, so this is a regression check).

## 4. Live verification after deploy

A green suite cannot establish this fix, since a green suite is what shipped the defect. The check is on the host.

- [ ] 4.1 Confirm an automation pass actually ran after the deploy, from the run record rather than from a log grep: `curl -sS https://fuperia.shatynska.com/health/scheduled-runs` and check that `launch.automation.resolution_pass`'s `last_success` is later than the deploy. A log grep cannot serve as this gate — the pass emits no line on success, only warnings on failure (`automation_pass.py` logs at `warning` and nothing else), so the token would match only the failures the fix removes, and a zero count would be indistinguishable from a pass that never ran.
- [ ] 4.2 With a pass confirmed to have run, check `docker compose logs --since <deploy> worker | grep -c "Unsupported function"` is `0`, **and** that `lp.listing.007` actually resolved on a product. A pass that logs no failure but records nothing has not been verified — that is the shape the "no verdict could be read" path produces, and it is the outcome a schema the model fills inconsistently would give.
- [ ] 4.3 If the API rejects the schema despite both local conversions accepting it (`design.md`'s first risk), the error will name the schema rather than the union; that is a new finding for this change, not a separate one.

## 5. Archive

- [x] 5.1 `openspec validate fix-subcategory-advisor-structured-output --strict` passes.
- [ ] 5.2 `openspec archive fix-subcategory-advisor-structured-output --yes` as the last commit before the merge, per `AGENTS.md`.
