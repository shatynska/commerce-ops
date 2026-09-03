# Test manifest — `screen-a-product-for-compliance`

Written by `ai-toolkit:openspec-test-writer` against the change's approved
plan at commit `c62b48b`, before any implementation existed. Not an artifact
the OpenSpec schema defines, so `openspec instructions apply` does not
surface it — read it on purpose.

Every test below was derived from
`openspec/changes/screen-a-product-for-compliance/specs/compliance-screen/spec.md`
and, where the delta fixes a behaviour but not its shape, from `tasks.md`
and `design.md`. No implementation was read: it does not exist. The sibling
handler `src/commerce_ops/step_handlers/listing/subcategory_advisor.py` was
read for the framework contracts it uses (`StepContext`, `StepResolution`,
`register_step_handler`, the `build_graph` / `build_production_graph`
split), which are this project's conventions rather than this change's
behaviour.

**This pass adds tests and never subtracts.** No existing test file was
edited, deleted or disabled. The one place that bit is §7.

---

## Baseline

Full, not scoped. `uv run pytest tests/unit tests/agents` on the worktree at
`c62b48b`, before any test below was written:

```
2090 passed in 66.24s
```

0 failed, 0 skipped. The integration tier was not run: this change touches
no database and `tasks.md` places nothing in `tests/integration/`.

### After this pass, on the unmodified source tree

`uv run pytest tests/unit tests/agents --continue-on-collection-errors`:

```
4 failed, 2091 passed, 6 errors in 72.23s
```

Attributed in full:

| Count | What | Failure state (`ai-toolkit:testing`) |
| --- | --- | --- |
| 4 collection errors | `ModuleNotFoundError: No module named 'commerce_ops.step_handlers.strategy'` in the four files that import the screen | State 2 — the target is absent. **No assertion in those four files has run**, so nothing about their quality is yet established. |
| 2 errors | `test_compliance_screen_registration_is_cheap.py`, both raised from its module-scoped `probe` fixture, which subprocess-imports the absent module | State 2, same reason. |
| 4 failed | `test_the_screen_is_registered_in_every_process[…]`, one per root, each reporting a registry holding `listing.subcategory_advisor` alone | State 1 — the assertions executed and discriminated. This file imports no absent module. |
| 2091 passed | 2090 pre-existing, plus `test_no_root_resolves_the_screen_that_another_one_lacks` | See §6: a first-run pass, explained rather than treated as coverage. |

**Without `--continue-on-collection-errors` the run aborts on the four
collection errors and reports nothing else.** That is what the `pre-commit`
pytest hook will do until the module exists — the same state the sibling
handler's tests were committed in (their headers record it), so committing
these tests before the implementation needs `--no-verify` or the two source
files landing in the same commit.

---

## 1. Every scenario, accounted for

26 `#### Scenario:` blocks in the delta; 26 accounted for below; 0
uncovered. Test names are given in a form `uv run pytest` selects
individually.

Path prefixes, used below as `A/` and `U/`:

- `A/` = `tests/agents/step_handlers/strategy/`
- `U/` = `tests/unit/step_handlers/strategy/`

### Requirement: The screen is performed against the categories the step itself names

| Scenario | Test |
| --- | --- |
| The step's description is what the product is tested against | `A/test_compliance_screen_categories.py::test_the_steps_description_is_what_the_product_is_tested_against`<br>`A/test_compliance_screen_categories.py::test_both_halves_of_the_description_reach_the_prompt_and_the_citation` |
| The produced text cites what was screened against | `A/test_compliance_screen_categories.py::test_the_produced_text_cites_what_was_screened_against` (parametrised over all three verdicts)<br>`A/test_compliance_screen_categories.py::test_the_citation_is_rendered_even_when_the_comment_names_nothing`<br>`A/test_compliance_screen_categories.py::test_both_halves_of_the_description_reach_the_prompt_and_the_citation` |
| An edited description changes what is screened | `A/test_compliance_screen_categories.py::test_an_edited_description_changes_what_is_screened` |
| A step naming no categories is not a clear product | `A/test_compliance_screen_categories.py::test_a_step_naming_no_categories_is_not_a_clear_product` (parametrised over `None`, `""`, `"   "`, `"\n\t\n"`)<br>`A/test_compliance_screen_categories.py::test_a_step_naming_no_categories_falls_back_to_no_list_of_its_own` |

The two falsifying cases `tasks.md` 1.7 requires are
`test_the_citation_is_rendered_even_when_the_comment_names_nothing` (the
scripted comment names no category, so a citation the model supplied could
not produce the asserted text) and
`test_both_halves_of_the_description_reach_the_prompt_and_the_citation` (a
description carrying both a referenced list and a parenthetical of examples,
with each half asserted separately, so an extraction step that kept one and
dropped the other fails by name).

`tasks.md` 1.8's "assert the absence of the call, not only the outcome" is
established by `_install_refusing_factory`, which replaces
`build_production_graph` with one that raises. The outcome text alone would
be produced by accident by an implementation that prompted with an empty
list.

### Requirement: A verdict distinguishes clear, flagged and undetermined

| Scenario | Test |
| --- | --- |
| A verdict is read from the discriminant, not the prose | `A/test_compliance_screen_verdict_routing.py::test_a_verdict_is_read_from_the_discriminant_not_the_prose` (parametrised: a `flagged` verdict with reassuring prose, an `undetermined` verdict with clean-sounding prose) |
| A comment's content is never checked by code | `A/test_compliance_screen_verdict_routing.py::test_a_comments_content_is_never_checked_by_code` (parametrised over all three verdicts, each with a comment omitting everything the prompt asks for) |
| A verdict's comment reaches the reader | `A/test_compliance_screen_verdict_routing.py::test_a_verdicts_comment_reaches_the_reader` (parametrised over all three verdicts) |
| A verdict with an empty comment is treated as unreadable | `A/test_compliance_screen_verdict_routing.py::test_a_verdict_with_an_empty_comment_is_treated_as_unreadable` (parametrised 3 verdicts × 4 blank forms = 12 cases, the `clear` rows included deliberately) |

### Requirement: Satisfaction is proposed only for a clear verdict

| Scenario | Test |
| --- | --- |
| A clear verdict proposes satisfaction | `A/test_compliance_screen_verdict_routing.py::test_a_clear_verdict_proposes_satisfaction` |
| A flagged verdict proposes a non-terminal outcome | `A/test_compliance_screen_verdict_routing.py::test_a_flagged_verdict_proposes_a_non_terminal_outcome` |
| An undetermined verdict proposes a non-terminal outcome | `A/test_compliance_screen_verdict_routing.py::test_an_undetermined_verdict_proposes_a_non_terminal_outcome` |
| An unreadable verdict is not reported as a judgement about the product | `A/test_compliance_screen_verdict_routing.py::test_an_unreadable_verdict_is_not_a_judgement_about_the_product` |

The requirement's "the reasons SHALL be distinguishable" clause is asserted
separately, in
`A/test_compliance_screen_verdict_routing.py::test_the_three_non_terminal_reasons_are_textually_distinct`,
so that editing one reason's wording cannot silently take the distinctness
check with it.

### Requirement: A verdict its own response contradicts is not satisfaction

| Scenario | Test |
| --- | --- |
| A clear verdict carrying a stated inability is refused | `A/test_compliance_screen_verdict_routing.py::test_a_clear_verdict_carrying_a_stated_inability_is_refused` |
| A statement about a category does not withhold satisfaction | `A/test_compliance_screen_verdict_routing.py::test_a_statement_about_a_category_does_not_withhold_satisfaction` |

The negative case `tasks.md` 1.6 requires is the second row. Its fixture
uses exactly the verbs a phrase-list veto would key on ("cannot apply",
"is unable to reach") with a *category* as the subject, so a veto
implemented as a phrase list blocks the step and fails here.

### Requirement: Model failure is surfaced, not masked

| Scenario | Test |
| --- | --- |
| A failing model call surfaces as a failure | `A/test_compliance_screen_failure_and_context.py::test_a_failing_model_call_surfaces_as_a_failure` |
| Response content that is not a plain string surfaces as a failure | `A/test_compliance_screen_failure_and_context.py::test_response_content_that_is_not_a_plain_string_surfaces_as_a_failure` |

The requirement's own prohibition — "SHALL NOT be routed to the
unreadable-verdict path, nor to any other non-terminal outcome" — is
asserted by name in
`A/test_compliance_screen_failure_and_context.py::test_a_model_failure_is_not_routed_to_the_unreadable_verdict_reason`.

### Requirement: The structured-output schema is one the model provider's adapter accepts

| Scenario | Test |
| --- | --- |
| The schema is accepted by the provider's own conversion | `U/test_compliance_screen_schema_conversion.py::test_the_schema_is_accepted_by_the_providers_own_conversion`<br>`U/test_compliance_screen_schema_conversion.py::test_the_schema_is_not_a_union_the_adapter_rejects`<br>`U/test_compliance_screen_schema_conversion.py::test_the_converted_schema_emits_no_oneof_anywhere`<br>`U/test_compliance_screen_schema_conversion.py::test_the_verdict_is_a_plain_string_carrying_the_three_values` |
| The converted schema is the one the call site passes | `U/test_compliance_screen_schema_conversion.py::test_the_guard_obtains_its_schema_from_the_call_site`<br>`U/test_compliance_screen_schema_conversion.py::test_a_diverging_call_site_is_detected_by_the_same_mechanism` |
| Every wire combination has a defined destination | The whole verdict table in `A/test_compliance_screen_verdict_routing.py`: 3 verdicts × {a real comment, `None`, `""`, whitespace} = 12 combinations, plus the no-parse route, plus the two contradiction cases. The wire schema can express nothing else — `verdict` is a closed three-value discriminant and `comment` a nullable string — so the table is exhaustive by construction rather than by sampling. |
| Wire fields state when they are to be populated | `U/test_compliance_screen_schema_conversion.py::test_wire_fields_state_when_they_are_to_be_populated` |

### Requirement: The screen reads only what it is given, and reports no finding

| Scenario | Test |
| --- | --- |
| The product is taken from the context | `A/test_compliance_screen_failure_and_context.py::test_the_product_is_taken_from_the_context` |
| A value reaching the model is the value, not its object's rendering | `A/test_compliance_screen_failure_and_context.py::test_a_value_reaching_the_model_is_the_value_not_its_rendering` |
| No finding accompanies the outcome | `A/test_compliance_screen_failure_and_context.py::test_no_finding_accompanies_the_outcome` (parametrised over all three verdicts)<br>`A/test_compliance_screen_failure_and_context.py::test_no_finding_accompanies_an_unreadable_verdict` |

### Requirement: The screen is reached only through the step it is authored onto

| Scenario | Test |
| --- | --- |
| The handler is resolvable in every process consulting the registry | `tests/unit/test_compliance_screen_registered_across_processes.py::test_the_screen_is_registered_in_every_process` (parametrised over `commerce_ops.main`, `commerce_ops.worker`, `commerce_ops.check_step_handlers`, `commerce_ops.registrations`)<br>`tests/unit/test_compliance_screen_registered_across_processes.py::test_no_root_resolves_the_screen_that_another_one_lacks` |
| The screen does not test which step invoked it | `A/test_compliance_screen_failure_and_context.py::test_the_screen_does_not_test_which_step_invoked_it` |
| Registration loads nothing the run needs | `U/test_compliance_screen_registration_is_cheap.py::test_registration_constructs_no_model_and_imports_no_graph_library`<br>`U/test_compliance_screen_registration_is_cheap.py::test_importing_the_screen_makes_its_name_resolvable` |

---

## 2. Which tests each implementation task must turn green

`tasks.md` §2, mapped to the tests that stop being red when it lands.

| Task | Tests |
| --- | --- |
| 2.1 `strategy/__init__.py` | Collection of all four files that import the screen. |
| 2.2 module + `HANDLER_NAME` | `U/…registration_is_cheap.py::test_importing_the_screen_makes_its_name_resolvable` |
| 2.3 the wire model | Everything in `U/…schema_conversion.py`. |
| 2.4 read the description; early return | `A/…categories.py::test_a_step_naming_no_categories_*` |
| 2.5 prompt from the description, carried through | `A/…categories.py::test_the_steps_description_is_what_the_product_is_tested_against`, `…::test_both_halves_of_the_description_reach_the_prompt_and_the_citation` |
| 2.6 render three parts, citation not from the comment | `A/…categories.py::test_the_produced_text_cites_what_was_screened_against`, `…::test_the_citation_is_rendered_even_when_the_comment_names_nothing`, `A/…verdict_routing.py::test_a_verdicts_comment_reaches_the_reader` |
| 2.7 graph split, async node, `include_raw=True`, deferred imports, `lru_cache` | `A/…verdict_routing.py::test_the_screen_asks_for_the_raw_response_alongside_the_parsed_one`; the `invoke`-raising guard in every agent-tier fake; `U/…registration_is_cheap.py::test_registration_constructs_no_model_and_imports_no_graph_library` |
| 2.8 no `try` around the model call | All three tests in `A/…failure_and_context.py`'s first section. |
| 2.9 verdict routing, blank comment, three distinct reasons | The verdict table in `A/…verdict_routing.py`. |
| 2.10 the contradiction veto | `A/…verdict_routing.py::test_a_clear_verdict_carrying_a_stated_inability_is_refused`, `…::test_a_statement_about_a_category_does_not_withhold_satisfaction`, `…::test_a_vetoed_verdict_does_not_borrow_another_routes_reason` |
| 2.11 registration, `finding=None`, `.value` reads, no step-identity test | `A/…failure_and_context.py::test_no_finding_accompanies_*`, `…::test_a_value_reaching_the_model_is_the_value_not_its_rendering`, `…::test_the_screen_does_not_test_which_step_invoked_it` |
| 2.12 `registrations.py` | `tests/unit/test_compliance_screen_registered_across_processes.py` (both tests), and the pre-existing `tests/unit/test_handler_registration_is_cheap.py`, which picks the new module up from `HANDLER_MODULES` automatically. |

---

## 3. Assertion classification

Per `ai-toolkit:testing`. Every test file also carries this at its own head;
what follows is the summary and the cases worth arguing about.

### Specified

Every scenario mapping in §1. In addition, these clauses of requirement
*statements* (not of a `#### Scenario:`) are asserted:

- "The reasons SHALL be distinguishable from one another" —
  `test_the_three_non_terminal_reasons_are_textually_distinct`.
- "Such a failure SHALL NOT be routed to the unreadable-verdict path" —
  `test_a_model_failure_is_not_routed_to_the_unreadable_verdict_reason`.
- "SHALL NOT fall back to any list of its own" —
  `test_a_step_naming_no_categories_falls_back_to_no_list_of_its_own`.
- "SHALL carry the description's text through unaltered … and SHALL extract
  nothing from it" —
  `test_both_halves_of_the_description_reach_the_prompt_and_the_citation`.

### Derived

Each is marked at its use site as well as here.

1. **`Blocked` as "a non-terminal outcome".** The delta says non-terminal;
   `Blocked` is the only non-terminal outcome in `launch-playbook` that can
   carry a reason, and every withheld scenario requires one. Same reading
   the sibling handler's tests already take.
2. **The keyword sets each reason is matched against.** The delta fixes what
   each reason must *state*, never its wording. Where a keyword set is used,
   the distinctness assertion is stated separately so that rewording a
   reason cannot take the real check with it.
3. **No substring ban on "flag" or "clear" in the unreadable and
   undetermined reasons.** The delta's "does not state that the product was
   flagged or that it is clear" is asserted as *distinctness from the two
   reasons that do state those things*, not as a banned substring. A
   legitimate shortfall reason may use both words while denying either —
   the sibling handler's own reads "whether a node choice could be supported
   is unknown rather than settled" — and a substring ban would fail the
   right implementation for using the right words.
4. **That the produced text states the verdict's own name.** `design.md`
   fixes the rendered text as three parts (categories, verdict, comment) and
   `tasks.md` 2.6 repeats it; the delta says "the verdict" without fixing
   how it is spelled. Asserted as the lower-cased verdict word appearing in
   the text.
5. **`include_raw=True`.** `tasks.md` 2.7, not a delta scenario. Asserted so
   that dropping it fails by name rather than as a dozen unexplained
   unreadable-verdict failures.
6. **`test_a_vetoed_verdict_does_not_borrow_another_routes_reason`.** The
   delta does not say which reason a vetoed contradiction carries; only that
   it must not be recorded as a finding about the product.
7. **The value-object rendering tokens.** The delta names three *kinds* of
   leak (type name, field name, quoting); which literal strings those are
   follows from `shared/domain/identity.py`'s dataclasses and from `Product`
   being a plain class rather than a dataclass.
8. **That the scripted model fault itself appears in the raised exception's
   `__cause__`/`__context__` chain.** The delta says the failure surfaces,
   not that it surfaces unwrapped.
9. **Sockets refused as the way "performs no lookup of its own" and "needs
   no network" are established.** Every fetch this deployment could make
   crosses a socket; an in-process fetch is not a state any artifact
   describes, and is recorded as untested below.

### Deliberately untested

Recorded rather than omitted; each also appears at the foot of the file it
belongs to.

- Whether a verdict is *correct* about a product — whether an item really is
  on the FBA-prohibited hazmat list. No deterministic test can establish it;
  `tasks.md` 4.5–4.6 gate it on live verification.
- Whether a comment in fact states the categories considered, the categories
  flagged, or the settling fact. The delta states these as prompting
  obligations and **forbids code from checking them**, so a test asserting
  them would assert against the requirement.
- Whether each wire-field description in fact says *when* to populate the
  field. Judging that means parsing prose for content, which the same
  requirement forbids one field over.
- Whether the provider's *API* accepts the schema both local conversions
  accept. No offline check can establish it; `design.md` records it as a
  risk and `tasks.md` §4 gates it on a live invocation after deploy.
- Whether an admin editing the description through `playbook-authoring` is
  what changes the served step. That is `playbook-authoring`'s requirement
  and its own tests; these tests establish only that the screen reads
  whatever the served step carries.
- That `launch-step-automation` reports the raising handler and records
  nothing. That capability's own requirement, already covered by its own
  tests; these establish only that the screen gives it something to report.
- Any module count or import duration in the registration probe. A count
  assertion fails on an unrelated dependency bump and says nothing about the
  property.

---

## 4. Obsolete tests

**Not applicable.** The change's delta is `ADDED`-only: it introduces the
new capability `compliance-screen` and carries no `MODIFIED`, `REMOVED` or
`RENAMED` requirement. Nothing existing is superseded, so no existing test
can bear on superseded behaviour, and no search for one was performed. This
is a statement about the delta's operations, not a search that came back
empty.

---

## 5. Unresolved project questions

Each carries the assumption taken and the tests that depend on it. None was
resolvable from `AGENTS.md`, `CLAUDE.md`, `README.md` or the change's
artifacts, and a dispatched subagent has no channel to ask on.

### 5.1 How a stubbed model is put behind the registered handler

**Assumption.** The handler reaches its graph through
`build_production_graph()` — `design.md`'s *Graph, registration and imports
mirror the advisor exactly*, with `tasks.md` 2.7's `lru_cache` in front of
it. Each test therefore monkeypatches `screen.build_production_graph` with a
factory returning `screen.build_graph(stub_model)`, and clears every
`cache_clear`-bearing module attribute before each install (several tests
invoke the screen twice, and a cached graph would let the first
invocation's stub answer the second).

**Why not the sibling's seam.** `subcategory_advisor` is driven through
`propose(product_name=…, marketplace=…, graph=…)`. This screen's equivalent
would have to take the description too, and inventing that signature would
have been this pass designing the implementation's API. Driving the
registered handler instead names only `HANDLER_NAME`, `build_graph`,
`build_production_graph` and the registry — all fixed by `tasks.md` — and it
is also the only level at which the description-reading scenarios are
observable at all.

**Depends on it.** Every test in the three agent-tier files and in
`U/test_compliance_screen_schema_conversion.py`. If the implementation
reaches its graph some other way, `_install_stub_graph` (and
`_install_refusing_factory`) in each file is the single correction point;
nothing else in any file names the graph.

### 5.2 The wire model's class name

**Assumption: none taken.** No artifact names the class. Rather than guess
one, the fakes capture whatever class the screen hands to
`with_structured_output(...)` and instantiate *that*, so the only names this
pass commits to are the two field names `tasks.md` 2.3 fixes (`verdict`,
`comment`) and the three literal values.

**Depends on it.** Every scripted response in the agent tier. If the field
names differ, construction raises at the fake and the failure names them.

### 5.3 What "content that is not a plain string" means

**Assumption.** The structured-output call yields something other than the
`raw`/`parsed`/`parsing_error` dict `include_raw=True` contracts to return,
and the screen fails visibly on it.

**Why the other reading is foreclosed.** Reading it as "`parsed` is `None`
because the response validated against nothing" would contradict *An
unreadable verdict is not reported as a judgement about the product*, which
routes exactly that state to a non-terminal outcome. Only the reading above
leaves both requirements standing. It also matches the sibling handler's
own shape, whose `assert isinstance(response, dict)` is what surfaces it.

**Depends on it.**
`A/…failure_and_context.py::test_response_content_that_is_not_a_plain_string_surfaces_as_a_failure`.

### 5.4 Whether the `launch` a `StepContext` carries may be a stand-in

**Assumption.** No. A real `Launch` is built in every context, from a real
`LaunchPlaybook` with the eight specified gates and one blocking step each,
following `tests/unit/launch/application/test_step_handler_contract.py`.
A sentinel would have been a stronger assertion that the screen ignores the
launch, but the delta neither requires nor forbids reading it, so a sentinel
would have invented a constraint.

**Depends on it.** Nothing asserts anything about the launch; this only
affects how the context is constructed.

### 5.5 Whether `tests/agents/step_handlers/strategy/` needs an `__init__.py`

**Assumption.** No — `tests/agents/step_handlers/listing/` and
`tests/unit/step_handlers/listing/` carry none, and every new file's
basename is unique across the tree. `AGENTS.md` records the directory
layout but not this.

### 5.6 Ruff will want these imports reordered once the module exists

**Not a question about the change; a tooling fact worth stating so it is not
mistaken for something needing thought.** Ruff's isort classifies
`commerce_ops.step_handlers.strategy.compliance_screen` as *third-party*
today, because no such path exists under `src/` — verified by probe. The
four files importing it are therefore currently formatted with that import
in the third-party block, and `ruff check` / `ruff format --check` are clean
as committed. The moment `src/commerce_ops/step_handlers/strategy/` exists,
ruff reclassifies it as first-party and reports `I001` on those four files.
`uv run ruff check --fix` resolves it; the move is an import reorder and
touches no assertion.

---

## 6. A test that passes on the unmodified tree, and why

`tests/unit/test_compliance_screen_registered_across_processes.py::test_no_root_resolves_the_screen_that_another_one_lacks`
**passes today.** Per `ai-toolkit:testing` a first-run pass is normally an
alarm, so it is explained here rather than left to be discovered.

It asserts that the four roots *agree* about whether this deployment answers
for `strategy.compliance_screen`. Four roots that all lack it agree, so it
holds vacuously. Its subject is the asymmetry a half-finished
`registrations.py` edit produces — a handler in the worker and not the API,
or the reverse — and no such asymmetry can exist before the edit is begun.

It therefore carries **no evidence about the absence**, and must not be read
as covering the scenario. `test_the_screen_is_registered_in_every_process`
is what covers it, and that one fails on all four roots today.

Strengthening the guard into an absence check would duplicate the other test
and lose the asymmetry check entirely, so it is left as it is.

---

## 7. Where this pass departed from `tasks.md`

One place, and only one.

**`tasks.md` 1.14** asks that
`tests/unit/test_registrations_across_processes.py` be *extended* so both
composition roots hold the new handler. This pass is additive only and does
not edit existing test files under any circumstances, so the scenario is
covered by a new file instead —
`tests/unit/test_compliance_screen_registered_across_processes.py` — using
the same fresh-interpreter mechanism that file establishes, and asserting
the half it does not: that the resolved set *contains* this handler. The
existing file's own assertion is that the roots resolve the *same* set,
which holds whether or not this screen is in it.

`tests/unit/test_registrations_across_processes.py` is unedited. Whoever
implements the change may fold the new file's assertion into it and delete
the new file, or leave both; the scenario is covered either way. Nothing
else in this pass touched, weakened or disabled an existing test.
