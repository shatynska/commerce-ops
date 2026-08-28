# Test manifest — `separate-the-verdict-from-the-prose`

Written by a test-writing pass held separately from implementation, from
the change's delta spec and the served `subcategory-advisor` spec. No
implementation of this change exists yet; every test recorded here was
written before it.

**This file is not an OpenSpec artifact.** The schema does not know about
it, so it will not appear among `openspec instructions apply`'s context
files. Whoever implements this change has to open it on purpose.

**This pass adds tests and never subtracts.** No existing test was
edited, deleted, disabled or weakened. Exactly one file was written
inside the dispatched test-path glob, plus this manifest:

- `tests/agents/step_handlers/listing/test_subcategory_advisor_verdict.py`
  — new.
- `openspec/changes/separate-the-verdict-from-the-prose/test-manifest.md`
  — this file, the one named exception to the glob.

`tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py`
was **read and not touched**, including the supported-path stub that
`tasks.md` 4.1a will need to change and the unsupported-path stub
`tasks.md` 4.1 will need to change. Both remain the implementer's.

## Tier and level

`tests/agents/step_handlers/listing/` — the tier `AGENTS.md` gives
deterministic LangGraph agent-graph tests against stubbed models, beside
the subject's existing suite, as `tasks.md` 1.2 requires. Nothing here
touches I/O, so no unit-tier or integration-tier test is called for.

Within that tier, eleven of the twelve scenarios are observed at
`propose()` — the smallest unit that can see a verdict become an outcome
— driven over a stubbed graph that returns prepared state. One
(*A response that is not text still fails visibly*) runs the real
compiled graph over a stubbed chat model, because a non-string response
content is a property of the model call. One (*An unsupported
recommendation still says so in prose*) reads the prompt, per
`tasks.md` 1.2a.

## Baseline

**Scoped**, and the scope is stated: `uv run pytest tests/agents` →
**14 passed, 0 failed**, taken at `efa9d8a` on a clean tree before any
test was written.

Scoped rather than full because the agent tier is the only tier this
change touches (`tasks.md` 1.2) and it is where every test written here
lives, so attribution of any later failure is complete within it. The
integration tier was not run: it needs a Postgres database this
environment does not resolve, and nothing in this change reaches it.

After this pass: `uv run pytest tests/agents` → **11 failed, 16 passed**.
The 14 pre-existing tests all still pass; the 11 failures and 2 passes
are all new. Nothing that passed before fails now.

Also run clean over the new file: `uv run ruff check`,
`uv run ruff format --check`, and `uv run mypy .` (337 source files, no
issues).

## Scenario accounting

Twelve `#### Scenario:` blocks in the delta spec. Twelve accounted for.

| # | Scenario | Covering test | State on first run |
|---|---|---|---|
| 1 | A supported choice proposes satisfaction | *uncovered — see below* | — |
| 2 | An unsupported choice proposes no satisfaction | `test_an_unsupported_choice_proposes_no_satisfaction` | absent target |
| 3 | A refusal is recognised however it is worded | `test_a_refusal_is_recognised_however_it_is_worded` | absent target |
| 4 | The recommendation's wording does not establish the outcome | `test_the_recommendations_wording_does_not_establish_the_outcome` | absent target |
| 5 | A verdict contradicting its own prose withholds satisfaction | `test_a_verdict_contradicting_its_own_prose_withholds_satisfaction` | absent target |
| 6 | A missing verdict is unsupported, not supported | `test_a_missing_verdict_is_unsupported_not_supported` | **wrong value** |
| 7 | An unreadable verdict is unsupported, not supported | `test_an_unreadable_verdict_is_unsupported_not_supported` | absent target |
| 8 | A fail-safe reason names what was wrong | `test_a_fail_safe_reason_names_what_was_wrong` | **wrong value** |
| 9 | An unrecognised verdict is not reported as an absent one | `test_an_unrecognised_verdict_is_not_reported_as_an_absent_one` | absent target |
| 10 | A vetoed verdict names the contradiction | `test_a_vetoed_verdict_names_the_contradiction` | absent target |
| 11 | A response that is not text still fails visibly | `test_a_response_that_is_not_text_still_fails_visibly` | **passes** — see below |
| 12 | An unsupported recommendation still says so in prose | `test_an_unsupported_recommendation_still_says_so_in_prose` | **passes** — exempted by `tasks.md` 1.3 |

Two tests were written that are not a scenario's coverage and are
recorded here so they are not mistaken for one:

| Test | What it is |
|---|---|
| `test_the_verdict_is_reported_as_a_value_alongside_the_recommendation` | The requirement's own sentence, "Support SHALL be established only by a verdict the advisor reports as a **value alongside** the recommendation" — the structural precondition every scenario reads through, asserted once so a run says so plainly instead of eleven times through a helper. |
| `test_each_withheld_path_records_its_own_reason` | The property scenarios 8, 9 and 10 add up to and none can see alone: four withheld paths, four distinct reasons. The requirement's own clause. A single shared fail-safe wording would satisfy parts of each of those three while defeating it. |

All tests are selectable individually:

```
uv run pytest "tests/agents/step_handlers/listing/test_subcategory_advisor_verdict.py::<test name>"
```

and the whole file with:

```
uv run pytest tests/agents/step_handlers/listing/test_subcategory_advisor_verdict.py
```

### Uncovered, with reasons

**Scenario 1 — *A supported choice proposes satisfaction*.** Reproduced
verbatim from the served requirement and genuinely covered by
`test_a_supported_choice_proposes_satisfaction` in
`test_subcategory_advisor_graph.py`. Not re-derived, per `tasks.md` 1.1.

That test's **stub** nevertheless needs changing: it reports no verdict,
which the fail-safe at `tasks.md` 3.2 resolves to unsupported, so it goes
red the moment the fail-safe lands (`tasks.md` 4.1a). That is an
implementation task and this pass did not perform it — coverage and
correctness-under-the-new-mechanism are different questions, and the
additive-only rule binds here regardless.

**Scenario 2 is *not* recorded as covered by its existing test**, though
it is also reproduced verbatim. Its existing test passes only because the
stub recites `cannot support` — one of the four literal markers the
change deletes — so it establishes the mechanism, not the requirement.
The new test refuses in the production wording, which contains none of
the four.

### Two tests that pass on their first run

Per `ai-toolkit:testing` a first-run pass before any implementation exists
is normally an alarm. Both of these are examined and neither is one; both
are **regression guards on behaviour this change must not break**, not
coverage of behaviour it introduces.

- **Scenario 12** asserts the *prompt* instructs the prose refusal. The
  pre-change prompt already carries that instruction and `tasks.md` 2.2
  requires it be kept. `tasks.md` 1.3 names this exemption from the
  absent-target baseline explicitly, for the reason the test can only be
  written this way at all: against a stubbed model the recommendation is
  whatever the stub was told to say, so reading it back would pass
  against any implementation, including one that dropped the instruction.
- **Scenario 11** asserts a non-text response still raises rather than
  resolving to a proposal. Today it raises because
  `NonStringRecommendationError` already exists; the scenario's content
  is that the *new* fail-safe must not extend to it. There is no
  pre-implementation state in which this could fail, and its value is
  that it fails if the fail-safe swallows the fault — which is only
  reachable once the fail-safe is written.

## Assertion classification

**Specified** — traces to a stated requirement in the delta or the served
spec:

- Which outcome each verdict reaches: supported → `Satisfied`;
  unsupported, absent, unrecognised, or vetoed → non-terminal and not
  satisfying.
- That two refusals differing only in wording reach the **same** outcome,
  not merely two independently non-terminal ones.
- That a rejected alternative described as unsupportable still reaches
  `Satisfied` — the delta's carve-out, stated in scenario 4's own THEN.
- That the four withheld reasons are pairwise distinct, and each negative
  clause: the missing-verdict reason does not assert a node choice could
  not be supported; the unrecognised-verdict reason does not say no
  verdict was reported; the vetoed reason does not assert the advisor
  considered and declined a classification.
- That the recommendation reaches the proposal whole, unaltered.
- That a non-text response fails and proposes no outcome.
- That the prompt instructs the prose refusal.
- That the verdict is a value alongside the recommendation rather than
  read back out of it.

**Derived** — inferred; no stated requirement fixes it. Each is visible
in the test file at the assertion it governs:

- **The verdict field's name.** Nothing fixes it. `_verdict_field()`
  reads `AdvisorState`'s own declared fields — a known candidate name if
  declared, otherwise the single field declared beyond the three that
  exist today — and fails loudly naming what it saw rather than
  defaulting. Correction point: `_VERDICT_FIELD_CANDIDATES`.
- **The verdict's values**, `"supported"` / `"unsupported"`, taken from
  the delta's own phrase "a value that is neither supported nor
  unsupported". Correction points: `SUPPORTED_VERDICT`,
  `UNSUPPORTED_VERDICT`, `UNRECOGNISED_VERDICT`.
- **`Blocked` specifically**, where the scenarios say "non-terminal".
  `permissible_terminal_outcomes` makes `Satisfied`, `NotApplicable` and
  `Refused` terminal; of the three non-terminal outcomes, `Blocked` is
  the only one carrying a reason, and every one of these scenarios
  requires a reason. Narrower than the scenarios' words, so recorded as
  derived. In `_assert_withheld`.
- **Every keyword list used to read a reason** — `"verdict"`,
  `"contradict"`/`"conflict"`, `"unrecognis"`, and so on. The delta fixes
  what each reason must say and must not say; no wording is specified.
  The wording-independent half of the same obligation is
  `test_each_withheld_path_records_its_own_reason`, which asserts
  distinctness without depending on any keyword.
- **That the unrecognised-verdict reason names the offending value
  itself.** Read out of "name what was actually wrong"; the delta does
  not say the value must be quoted.
- **The prompt test's verb and refusal-phrase vocabularies.**
- **The 5-letter threshold** for "share no wording" in scenario 3. The
  scenario gives no measure; the two fixtures were checked to share no
  word of five letters or more, and the check is an assertion in the test
  rather than a comment, so an edit that breaks it fails.

**Deliberately untested**, recorded rather than omitted (also listed at
the foot of the test file):

- That `_is_unsupported` and `_UNSUPPORTED_MARKERS` are gone rather than
  relocated. `tasks.md` 5.4 discharges it by grep, and asserting the
  absence of a private symbol would assert the mechanism rather than the
  requirement — the defect this change is about.
- How the graph node parses a verdict out of the model's answer. No
  artifact fixes an answer format, so a test of it would assert an
  invented wire format. Reached indirectly: every test reads the verdict
  from state, and the state field's existence is asserted separately.
- The served requirement that a satisfying outcome comes with a
  recommendation naming node, demands and alternative. `design.md`'s
  *Non-Goals* park it explicitly: "Nothing checks that today and nothing
  checks it after this change."
- Whether a proposed browse node is a real Amazon node, or the right one.
  No deterministic test can establish it and the delta does not claim it.

## Obsolete tests

The delta is one `MODIFIED` requirement, so this list applies. Searched
**within the dispatched test-path glob only** (`tests/**/test_*.py`),
comparing the served requirement under `openspec/specs/` with the delta.
No earlier `test-manifest.md` was supplied to this pass, so no
scenario-to-test mapping was available beyond the existing test file's own
docstring, which names its scenarios.

Every entry below is a **candidate for human confirmation, not a
conclusion**, and this pass performed none of the edits they imply.

| Test | Superseding delta clause | Evidence | Recommended action |
|---|---|---|---|
| `tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py::test_an_unsupported_choice_proposes_no_satisfaction` | "Support SHALL be established only by a verdict … and never by the recommendation's wording"; "Two refusals that mean the same thing SHALL therefore reach the same outcome, whatever words each uses." | Its stub `_UNSUPPORTED_ANSWER` is the string `"I cannot support a node choice for this product and marketplace: …"` — it recites `cannot support`, one of the four literal markers the change deletes, so the test passes by the mechanism being removed rather than by the requirement. `proposal.md` and `design.md`'s Decision 4 indict it by name. | **Its stub is superseded; its assertions are not.** `tasks.md` 4.1 and 4.3: change the stub's wording, keep every assertion. Not a deletion. Scenario 2's coverage is additionally re-derived in the new file, so deleting this test is not necessary to remove the marker recitation — but weakening or deleting it is forbidden regardless. |
| `tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py::test_a_supported_choice_proposes_satisfaction` | "A verdict the advisor did not report … SHALL be treated as **unsupported**." | Its stub `_ScriptedChatModel(SUPPORTED_ANSWER)` predates the verdict field and reports no verdict, so under the new fail-safe the state it produces resolves to unsupported and the test's `assert _outcome_of(proposal) is Satisfied` goes red. The assertion is still correct; the stub no longer expresses a supported choice. | **Its stub is superseded; its assertion is not.** `tasks.md` 4.1a: give the stub a supporting verdict. `tasks.md` 5.1's "no previously passing test weakened" cannot be discharged otherwise. Do not relax the assertion. |

**No test was found that should be deleted.** That is a finding, not an
empty list: the search covered the glob and found two tests bearing on
superseded behaviour, both of which are superseded in their **stubs**
rather than in what they assert, and `tasks.md` 4.3 says so independently.

**Not searched, and therefore not claimed:** anything outside
`tests/**/test_*.py`. Also worth stating plainly — this pass holds no
requirement-to-test index and has not read the implementation, so "no
other bearing test was found by this search" is the claim, not "no other
bearing test exists". Two candidates in one file is what the search
returned; the file is the subject's only test file in the tier.

## Unresolved project questions

Each was reached from the dispatched convention files (`AGENTS.md`,
`CLAUDE.md`, `README.md`) and the change's artifacts, and none is answered
there. The assumption taken and the tests depending on it are named. None
was resolved silently.

1. **How the verdict is spelled on `AdvisorState`** — field name and
   value vocabulary. *Assumption:* a field named `verdict` (or one of the
   candidates `_VERDICT_FIELD_CANDIDATES` lists, or the only field
   declared beyond today's three), carrying `"supported"` /
   `"unsupported"` strings. *Depends on it:* every test in the new file
   except `test_a_missing_verdict_is_unsupported_not_supported`,
   `test_a_fail_safe_reason_names_what_was_wrong`,
   `test_a_response_that_is_not_text_still_fails_visibly` and
   `test_an_unsupported_recommendation_still_says_so_in_prose`.
   *Correction:* three module-level constants and one helper, all named
   under *Correction points* in the test file's docstring.

2. **How the model conveys the verdict in its answer**, and therefore
   what a chat-model stub's answer should look like. `design.md` rules
   out a sentinel token in the prose and the earlier change ruled out
   structured output, leaving the wire format unstated. *Assumption:*
   none taken — the tests avoid the question by injecting state rather
   than a model answer, and this is recorded above as deliberately
   untested. *Consequence:* no test establishes that the graph node
   actually populates the verdict from a real answer. That gap is worth
   closing by the implementer once the format exists.

3. **Whether the reason is read off the outcome or off the produced
   text.** `launch-step-automation` permits a handler's reason to reach
   the record either way, and the existing unsupported-path test searches
   both. *Assumption:* the four reason assertions read **only**
   `outcome.reason`, since the delta speaks of "the reason recorded" and
   `Blocked` requires a non-empty reason. *Depends on it:* the four
   reason tests and `test_each_withheld_path_records_its_own_reason`.

4. **Whether this manifest is reachable from the project's own
   conventions.** It is not: no `rules/` fragment directing that a
   test manifest be read before implementing is imported by this
   repository's `AGENTS.md` or `CLAUDE.md`, and no such fragment is
   installed on this machine. *Consequence:* the only pointer to this
   file is the dispatching agent's report. If the implementation step is
   run by someone who did not read that report, this file will be missed.

## A bound this pass did not hold

Recorded rather than left implicit. This pass is meant not to read the
implementation of the behaviour under test, so that its assertions cannot
be shaped to match code. Its dispatch named
`src/commerce_ops/step_handlers/listing/subcategory_advisor.py` under
*Existing code the tests target*, together with the symbols it carries,
and it was read.

What that does and does not affect:

- Every assertion above traces to the delta or the served spec, not to
  the source. The behaviour read is the **pre-change** implementation,
  which this change deletes and which the delta explicitly rejects, so
  matching it was never the risk direction here.
- Two facts used in this manifest do come from that read and would
  otherwise have come from the artifacts anyway: that the four marker
  strings are what `_is_unsupported` searches for (also quoted in
  `proposal.md` and in the delta's scenario 3), and that the pre-change
  prompt already instructs the prose refusal (also required by
  `tasks.md` 2.2).
- `propose()`'s `graph=` seam, which the new tests inject through, was
  taken from the dispatch and from the existing test file's own use of
  it, both of which are within this pass's reading bounds.
