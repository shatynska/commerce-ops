# Test manifest — `fix-subcategory-advisor-structured-output`

Tests derived from this change's delta spec, before any implementation was
written. Written by `ai-toolkit:openspec-test-writer` under
`ai-toolkit:testing`, from the change's artifacts and the served specs
only — the handler's implementation source was not read.

**This file is not an artifact the OpenSpec schema knows about.** It will
not appear among `openspec instructions apply`'s context files and has to
be opened on purpose before implementing.

## Baseline

Full, not scoped, taken before any test here was written:

```
uv run pytest tests/unit tests/agents
1824 passed, 44 skipped, 0 failed
```

The integration tier was not run: nothing in this change touches it, and
no scenario here reaches I/O. The 44 skips are the served suite's own
database-dependent unit tests, skipped by `tests/unit/conftest.py`.

After the tests below were added, with no implementation written:

```
uv run pytest tests/unit tests/agents
76 failed, 1831 passed, 44 skipped
```

1831 = the 1824 baseline passes plus the 7 new tests that pass on their
first run (accounted for individually below). No previously-passing test
changed state. `uv run mypy .`, `uv run ruff check` and
`uv run ruff format --check` are clean over the new files.

## Files added

| File | Tier | Covers |
|---|---|---|
| `tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py` | unit | the ADDED requirement's three schema-shaped scenarios |
| `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py` | agents | the ADDED requirement's two behavioural scenarios, and the five MODIFIED verdict scenarios this change rewrites |
| `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_verdict.py` | agents | the MODIFIED verdict requirement's remaining nine scenarios |
| `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_recommendation.py` | agents | the MODIFIED recommendation requirement's six scenarios |

Tier placement follows `AGENTS.md`'s Testing Strategy and `tasks.md`
1.1/1.4: the conversion guard is a library contract over a schema object
(unit), the rest is graph behaviour (agents). No existing file was edited,
deleted, or disabled.

`tests/unit/step_handlers/listing/` is a new directory. It carries no
`__init__.py`, matching `tests/agents/step_handlers/listing/`; the new
file's basename is unique across the tree, which is what pytest's
rootdir-prepend import mode requires.

## Scenario coverage

26 scenarios in the delta spec; 26 accounted for. Every one is covered.

### ADDED — *The structured-output schema is one the model provider's adapter accepts*

| Scenario | Covering test |
|---|---|
| The schema is accepted by the provider's own conversion | `tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py::test_the_schema_is_accepted_by_the_providers_own_conversion`, `...::test_the_schema_is_not_the_union_the_adapter_rejects` |
| The converted schema is the one the call site passes | `...::test_the_guard_obtains_its_schema_from_the_call_site`, `...::test_a_diverging_call_site_is_detected_by_the_same_mechanism` |
| Every wire combination has a defined destination | `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py::test_every_wire_combination_has_a_defined_destination` (32 parametrised cases) |
| Wire fields state when they are to be populated | `tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py::test_wire_fields_state_when_they_are_to_be_populated` |
| The reported variants are unchanged by the wire shape | `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py::test_a_supported_wire_response_reports_what_a_supported_result_always_did`, `...::test_an_unsupported_wire_response_reports_what_a_refusal_always_did` |

### MODIFIED — *The advisor proposes satisfaction only where it can support a node choice*

| Scenario | Covering test |
|---|---|
| A supported choice proposes satisfaction | `..._wire_conversion.py::test_a_supported_choice_proposes_satisfaction` |
| An unsupported choice proposes no satisfaction | `..._wire_conversion.py::test_an_unsupported_choice_proposes_no_satisfaction` |
| A refusal is recognised however it is worded | `..._wire_verdict.py::test_a_refusal_is_recognised_however_it_is_worded` |
| The recommendation's wording does not establish the outcome | `..._wire_verdict.py::test_the_recommendations_wording_does_not_establish_the_outcome` |
| A supporting discriminant without its value is not support | `..._wire_conversion.py::test_a_supporting_discriminant_without_its_value_is_not_support` (9 parametrised cases) |
| A withholding discriminant without its error is not a refusal | `..._wire_conversion.py::test_a_withholding_discriminant_without_its_error_is_not_a_refusal` |
| A supporting discriminant carrying a reported error withholds satisfaction | `..._wire_conversion.py::test_a_supporting_discriminant_carrying_a_reported_error_withholds_satisfaction` (8 parametrised cases), `..._wire_conversion.py::test_the_three_withholding_reasons_are_distinguishable` |
| A verdict contradicting its own prose withholds satisfaction | `..._wire_verdict.py::test_a_verdict_contradicting_its_own_prose_withholds_satisfaction` |
| A missing verdict is unsupported, not supported | `..._wire_verdict.py::test_a_missing_verdict_is_unsupported_not_supported` |
| An unreadable verdict is unsupported, not supported | `..._wire_verdict.py::test_an_unreadable_verdict_is_unsupported_not_supported` |
| A fail-safe reason names what was wrong | `..._wire_verdict.py::test_a_fail_safe_reason_names_what_was_wrong` |
| An unrecognised verdict is not reported as an absent one | `..._wire_verdict.py::test_an_unrecognised_verdict_reads_the_same_as_a_missing_one` |
| A vetoed verdict names the contradiction | `..._wire_verdict.py::test_a_vetoed_verdict_names_the_contradiction` |
| A response that is not text still fails visibly | `..._wire_verdict.py::test_a_response_that_is_not_text_still_fails_visibly` |
| An unsupported recommendation still says so in prose | `..._wire_conversion.py::test_an_unsupported_wire_response_reports_what_a_refusal_always_did` |

(All paths above are under `tests/agents/step_handlers/listing/`.)

### MODIFIED — *A recommendation is produced from the product's name and marketplace*

All in `tests/agents/step_handlers/listing/test_subcategory_advisor_wire_recommendation.py`.

| Scenario | Covering test |
|---|---|
| A recommendation names node, demands and alternative | `::test_a_recommendation_names_node_demands_and_alternative` |
| A recommendation is readable as it stands | `::test_a_recommendation_is_readable_as_it_stands` |
| A supported comment cannot be empty | `::test_a_supported_comment_cannot_be_empty` (2 parametrised cases) |
| A comment's content is never checked by code | `::test_a_comments_content_is_never_checked_by_code` |
| The marketplace reaching the model is the identifier | `::test_the_marketplace_reaching_the_model_is_the_identifier` |
| A refusal names the marketplace as a reader would recognise it | `::test_a_refusal_names_the_marketplace_as_a_reader_would_recognise_it` |

### Uncovered scenarios

None. Every scenario in the delta has at least one named test.

This includes the two MODIFIED requirements' scenarios that `proposal.md`
describes as unchanged or terminology-only. They are re-derived rather
than left to the served suite because the *mechanism* every one of them
runs through is the object this change re-types, and the served tests
covering them are on the obsolete list below.

## The precedence between two scenarios, and how it is kept honest

`ok: true` with a blank `value` **and** a non-blank `error` satisfies the
WHEN of both *A supporting discriminant without its value is not support*
and *A supporting discriminant carrying a reported error withholds
satisfaction*. The delta resolves it normatively in direction 1: the
contradiction takes precedence.

The two scenarios' tests therefore use **disjoint** inputs:

- the missing-value test pins a blank `error` in every one of its nine
  cases (`None`, `""`, `"   "` × the same three values);
- the contradiction test pins a non-blank `error` in every one of its
  eight cases, three of which carry a blank value — those three *are* the
  overlap, asserted to take the contradiction route.

Neither test can pass by taking the other's route. `tasks.md` 2.3's
warning ("test this branch before the missing-value one, or the overlap
case takes the wrong route") is what those three cases catch.

## Assertion classification

### Specified — traced to a delta scenario or to a served requirement the delta retains

- The schema the call site passes is accepted by both conversions the
  `json_schema` path performs, and is not a top-level union.
- Every wire field carries a non-empty description in the converted
  schema.
- The guard's schema comes from the call site; the same mechanism rejects
  a call site that passes the pre-change union.
- Each of the 32 `ok`/`value`/`error` combinations reaches exactly the
  destination `design.md`'s table and the delta's direction 1 fix.
- Support = discriminant **and** its variant's field; a supported
  response yields `Satisfied` and a `Success` finding whose value is the
  node exactly.
- A contradiction yields a non-terminal outcome, no finding, a reason
  naming the contradiction, and rendered text carrying the reported
  error.
- A contradiction's reason names the field that withheld support — the
  error where the error withheld it, the comment where the comment did
  (`tasks.md` 2.6, and the delta's reason-naming obligation).
- The shortfall reason says no verdict could be read and does not assert
  that a node choice could not be supported.
- The three withholding reasons differ from one another.
- Supported and unsupported results carry the same rendered text and the
  same typed finding as before the wire shape.
- The prompt carries the product name and the marketplace identifier, and
  nothing of the value object's rendering; the same of a refusal's reason.

### Derived — inferred, no stated requirement fixes them

Each is labelled in place in the test files as well.

- **`Blocked` specifically for "non-terminal".** The scenarios say
  non-terminal; `Blocked` is the only non-terminal outcome that can carry
  a reason, and every withheld route here must record one. Carried over
  unchanged from the served suite.
- **The reason word lists** — `CONTRADICTION_WORDS` (`contradict`,
  `conflict`, `disagree`, `inconsistent`) and `SHORTFALL_PHRASES`
  (`no verdict`, `could not be read`, `unread`). No artifact fixes the
  recorded reasons' wording. These are the same lists
  `test_subcategory_advisor_structured_verdict.py` already asserts
  against, so an implementation satisfying that file satisfies these.
- **The four wire field names** `ok`, `value`, `error`, `comment` — fixed
  by `tasks.md` 2.1, not by any delta scenario.
- **`REPORTED_ERROR` / `REFUSAL_ERROR` / `REFUSAL_IN_COMMENT` /
  `ALTERNATIVE_CALLED_UNSUPPORTABLE`** — prose fixtures. The error
  fixtures deliberately carry no first-person subject, since `design.md`
  records `_advisor_refuses` as matching on one; a pass therefore
  evidences the conversion route rather than the comment veto.
- **`test_the_converted_schema_emits_no_oneof`** — traced to `design.md`'s
  first decision (a `oneOf`-emitting shape passes every offline check and
  is still liable to be rejected by the API), not to any delta scenario.
  Recorded here so it is visible as a design-level constraint rather than
  a requirement.
- **The refusal-prose word list** (`cannot`, `could not`, `unable`,
  `no node`, `not choose`) — carried over unchanged from the served
  verdict file.
- **The fakes** (`_ScriptedWireChatModel`, `_CapturingChatModel`, their
  runnables, `_Product`/`_Context`, the `_graph()` monkeypatch seam).
  Duplicated per file rather than shared, per this handler's existing
  separate-file convention.
- **Obtaining the wire model from the call site rather than by name.** No
  artifact fixes what the wire model is called, so importing it by a
  guessed name would fail for a reason unrelated to the behaviour. This
  also means the behavioural tests inherit the ADDED requirement's own
  call-site-provenance property for free.
- **`build_graph(model)` / `propose(product_name=, marketplace=, graph=)`
  survive unchanged**, as does `advise_sub_category(context)`. Stated by
  `design.md` as unchanged and carried over from the served suite.

### Deliberately untested — identified and knowingly left uncovered

- **Whether each field description actually says *when* to populate the
  field.** Judging that means parsing prose for particular content, which
  the served requirement *A comment's content is never checked by code*
  forbids this capability from doing one field over. Only non-emptiness
  is asserted.
- **Whether the provider's API accepts a schema both local conversions
  accept.** No offline check can establish it; `design.md`'s first risk,
  gated on `tasks.md` section 4's live verification.
- **Whether the model fills the flat schema's independent fields
  consistently.** A response-quality property, not a schema property —
  `design.md`'s second risk. This is why `tasks.md` 4.2 requires
  observing an actual resolution rather than an absent error.
- **Whether the finding also carries the comment.** The served
  requirement makes it a MAY, so pinning it would invent a constraint.
- **Whether a proposed browse node is a real Amazon node, or the right
  one.** No deterministic test can establish it.
- **`ok: false` with a populated value being deliberately not a
  contradiction** is asserted (it is in `design.md`), but *why* the
  asymmetry with row 2 holds is a reasoning claim, not a testable one.

## Tests that pass on their first run

Seven, each investigated rather than recorded as new coverage — per
`ai-toolkit:testing`, a first-run pass before any implementation exists is
an alarm, and each of these resolves to "the behaviour already exists"
rather than "the test asserts nothing".

| Test | Why it passes already |
|---|---|
| `..._schema_conversion.py::test_the_guard_obtains_its_schema_from_the_call_site` | Asserts a property of the guard's own mechanism (its input arrives through `with_structured_output(...)`), which holds before and after the change. It is what makes the *other* schema tests trustworthy, and is expected to keep passing. |
| `..._schema_conversion.py::test_a_diverging_call_site_is_detected_by_the_same_mechanism` | Drives a stand-in call site passing the pre-change union and asserts the mechanism rejects it. The rejection is the production defect, so it is already true; the test exists to establish that the guard discriminates rather than accepting anything. |
| `..._wire_verdict.py::test_a_missing_verdict_is_unsupported_not_supported` | Drives `parsed=None`, which constructs no wire instance. This route is unchanged by the change. |
| `..._wire_verdict.py::test_an_unreadable_verdict_is_unsupported_not_supported` | Same. |
| `..._wire_verdict.py::test_a_fail_safe_reason_names_what_was_wrong` | Same. |
| `..._wire_verdict.py::test_an_unrecognised_verdict_reads_the_same_as_a_missing_one` | Same. |
| `..._wire_verdict.py::test_a_response_that_is_not_text_still_fails_visibly` | Drives a raising runnable — a transport-level fault, prior to any schema. Unchanged by the change. |

The other 76 new test cases fail. Their failure states:

- **Failure state 1 (the code ran and produced a wrong result)** — the
  four failing tests in `..._schema_conversion.py`. The conversion runs
  and raises `ValueError: Unsupported function` on
  `Supported | Unsupported`, which is the production defect reproduced
  offline for the first time.
- **Failure state 2 (absent target)** — every failing test in the three
  agents-tier files. The wire schema does not exist, so the schema
  captured from the call site is still the domain union and no wire
  instance can be constructed from it (`'types.UnionType' object is not
  callable`). Their assertions have therefore **not** been exercised;
  absence is all these establish so far.

## Obsolete tests — candidates for human confirmation

Search bound: the dispatched test-path glob `tests/**/test_*.py`, and
nothing else. No earlier `test-manifest.md` path was supplied to this
pass, so no scenario-to-test mapping from the superseded change was
available; the entries below were found by reading the four files in
`tests/agents/step_handlers/listing/` that `proposal.md`, `design.md`
Context 4 and `tasks.md` 1.6 name.

**Every entry is a candidate for human confirmation, not a conclusion.
None was edited, deleted, or disabled by this pass.** `tasks.md` 1.6
already tasks the implementer with updating them, and explicitly forbids
making them pass by adding an `isinstance` passthrough for domain variants
in the conversion — that would shape production code to a test double.

Common evidence for every entry: each scripts a domain `Supported(...)` or
`Unsupported(...)` object as the model's `parsed` response, and the
superseding delta re-types exactly that object. After the change the
conversion is defined over the wire schema, so these fakes describe a
response the model can no longer produce. Superseding delta for all of
them: the ADDED requirement *The structured-output schema is one the model
provider's adapter accepts* ("The shape crossing the model boundary MAY
differ from the shape the advisor reports to its own callers"), together
with `tasks.md` 1.6.

| Test (runner-selectable) | Evidence |
|---|---|
| `tests/agents/step_handlers/listing/test_subcategory_advisor_structured_verdict.py::test_a_supported_choice_proposes_satisfaction` | `Supported(ok=True, value=NODE, comment=COMMENT)` at line 283 |
| `...test_subcategory_advisor_structured_verdict.py::test_an_unsupported_choice_proposes_no_satisfaction` | `Unsupported(...)` at line 297 |
| `...test_subcategory_advisor_structured_verdict.py::test_a_refusal_is_recognised_however_it_is_worded` | `Unsupported(...)` at lines 316-317 |
| `...test_subcategory_advisor_structured_verdict.py::test_the_recommendations_wording_does_not_establish_the_outcome` | `Supported(...)` at line 330 |
| `...test_subcategory_advisor_structured_verdict.py::test_a_verdict_contradicting_its_own_prose_withholds_satisfaction` | `Supported(...)` at line 346 |
| `...test_subcategory_advisor_structured_verdict.py::test_a_vetoed_verdict_names_the_contradiction` | `Supported(...)` at line 432 |
| `...test_subcategory_advisor_structured_verdict.py::test_routes_1_2_and_3_carry_distinguishable_reasons` | `Supported(...)` at lines 451, 454. **Additionally superseded on substance**, not only mechanism: it asserts three routes where the change defines four, and its "route 3" reason is now one of two contradiction reasons (`tasks.md` 2.6). `..._wire_conversion.py::test_the_three_withholding_reasons_are_distinguishable` is its wire-shape successor. |
| `...test_subcategory_advisor_structured_verdict.py::test_an_unsupported_recommendation_still_says_so_in_prose` | `Unsupported(...)` at line 510 |
| `...test_subcategory_advisor_structured_recommendation.py::test_a_recommendation_names_node_demands_and_alternative` | `Supported(...)` at line 270 |
| `...test_subcategory_advisor_structured_recommendation.py::test_a_recommendation_is_readable_as_it_stands` | `Supported(...)` at line 304 |
| `...test_subcategory_advisor_structured_recommendation.py::test_a_supported_comment_cannot_be_empty` (both params) | `Supported(...)` at line 333 |
| `...test_subcategory_advisor_structured_recommendation.py::test_a_comments_content_is_never_checked_by_code` | `Supported(...)` at line 363 |
| `...test_subcategory_advisor_structured_recommendation.py::test_the_marketplace_reaching_the_model_is_the_identifier` | `Supported(...)` at line 434 |
| `...test_subcategory_advisor_structured_recommendation.py::test_a_refusal_names_the_marketplace_as_a_reader_would_recognise_it` | `Unsupported(...)` at line 459 |
| `...test_subcategory_advisor_finding_and_tools.py::test_producing_a_recommendation_invokes_no_tools` | `Supported(...)` at line 206 |
| `...test_subcategory_advisor_finding_and_tools.py::test_structured_output_is_not_a_tool_invocation` | `Supported(...)` at line 230 |
| `...test_subcategory_advisor_finding_and_tools.py::test_a_supported_recommendation_carries_a_recordable_finding` | `Supported(...)` at line 254 |
| `...test_subcategory_advisor_finding_and_tools.py::test_an_unsupported_recommendation_carries_no_finding` | `Unsupported(...)` at line 269 |
| `...test_subcategory_advisor_finding_and_tools.py::test_only_the_findings_value_is_ever_written_to_the_product` | `Supported(...)` at line 294 |
| `...test_subcategory_advisor_graph.py::test_two_invocations_do_not_share_context` | `Supported(...)` at lines 148-149 |
| `...test_subcategory_advisor_graph.py::test_two_invocations_for_the_same_product_are_independent` | `Supported(...)` at lines 177-178 |

**Not superseded, and not to be touched:** the four files' remaining tests
that drive `parsed=None` or a raising runnable
(`test_a_missing_verdict_is_unsupported_not_supported`,
`test_an_unreadable_verdict_is_unsupported_not_supported`,
`test_a_fail_safe_reason_names_what_was_wrong`,
`test_an_unrecognised_verdict_reads_the_same_as_a_missing_one`,
`test_a_response_that_is_not_text_still_fails_visibly`). They construct no
domain variant and are unaffected by the re-typing.

Eight of the twenty-one entries above — those covering the *finding*, the
*no-tools* and the *no-state* requirements, which this change does not
touch at all — have **no successor test in this pass**, because their
requirements carry no scenarios in this delta. Updating their fakes to
wire instances (`tasks.md` 1.6) is therefore the only route by which those
requirements stay covered; deleting any of them would silently drop
coverage this change never proposed to drop.

## Unresolved project questions

Recorded rather than resolved: this pass had no channel on which to ask.

1. **No `langgraph`-specific testing idiom is recorded for this project.**
   `ai-toolkit:testing` directs loading the stack-matching skill; the
   `langgraph` skill carries LangGraph practice but this repository's
   `AGENTS.md` fixes the convention that matters here — deterministic
   agent-graph tests with stubbed model responses, in `tests/agents/`.
   Assumption taken: the served four files' fake-at-the-
   `with_structured_output`-seam pattern is this project's idiom, and it
   is reproduced rather than replaced. Depends on it: every test in the
   three agents-tier files.
2. **The wire model's name is fixed by no artifact.** `tasks.md` 2.1 fixes
   its fields but not its class name. Assumption taken: the tests obtain
   the schema from the call site instead of importing it, so no name is
   assumed at all. Depends on it: every test in all four new files. This
   also means the implementer is free to name it anything.
3. **The recorded reasons' wording is fixed by no artifact.** Assumption
   taken: the served verdict file's word lists are the project's de-facto
   contract, and are reused verbatim. Depends on it: every reason-family
   assertion. If the implementer's wording differs, the correct response
   is to reconcile the wording across both files — not to weaken either
   test.
4. **The contradiction reason must name `error` and not `comment`.**
   `tasks.md` 2.6 permits either generalising `_contradiction_reason` or
   adding a second reason. Assumption taken: whichever route is chosen,
   the reason names the field that actually withheld support, since that
   is the obligation 2.6 states. Depends on it:
   `..._wire_conversion.py::test_a_supporting_discriminant_carrying_a_reported_error_withholds_satisfaction`
   and `..._wire_verdict.py::test_a_vetoed_verdict_names_the_contradiction`.
5. **An error-based contradiction with a blank comment does not take the
   empty-comment shortfall route.** The delta says such a response "has
   not established support", and the empty-comment rule applies only to a
   response *established as supported* — so the contradiction claims it
   first. Assumption taken: that reading. Depends on it: the `no-comment`
   parametrisations of the contradiction test.
6. **No `rules/` fragment directing that this manifest be read is
   imported by this project's `AGENTS.md` or `CLAUDE.md`.** The library's
   fragment resolves through a machine-local path this repository does not
   reference, so the pointer in the test-writer's report is currently the
   only reachable one. Nothing was added to `AGENTS.md` by this pass —
   editing a project's conventions is not this pass's to do.

## Property this pass guarantees

**It adds tests and never subtracts.** No existing test file was edited,
deleted, or disabled. No implementation, stub, module, or type was
created to make a test execute. Nothing was written outside the dispatched
test-path glob except this manifest.
