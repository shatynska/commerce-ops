# Test manifest — specify-non-string-message-content

Not an OpenSpec schema artifact: `openspec instructions apply` will not surface
this file among its context files. Read it deliberately before implementing —
it states exactly what the implementation step must make pass, and what this
pass could not verify itself. The change's own `rules/` fragment (if this
repository has one checked out) also points here; this note is the second,
redundant pointer in case that machine-local path does not resolve.

This pass is **additive only**: no existing test file was edited, deleted, or
disabled, and nothing was written outside `tests/**/test_*.py` other than this
manifest. `NonStringAnswerError` and the `answer_question` check that raises it
were not implemented — both remain the implementation step's job.

## Baseline

**Scoped baseline**, taken before writing any test in this pass:

```
uv run pytest tests/unit/omni_agent tests/agents/omni_agent -q
```

Result: `40 passed` — nothing pre-existing was red. Re-run after adding the two
new test files (excluding them via `--ignore`) to confirm they left the
existing 40 unaffected: still `40 passed`.

Scope reasoning: this change touches only the `omni-agent` capability
(`omni_agent/application/use_cases.py`) and its one driving adapter
(`omni_agent/infrastructure/driving/slack.py`), so the baseline was scoped to
`tests/unit/omni_agent` + `tests/agents/omni_agent` rather than the full
`uv run pytest` (which also runs `tests/unit/products`, `tests/unit/shared`,
and `tests/integration`, unrelated to this change and, for the integration
tier, dependent on Postgres availability not verified here).

## Files written

- `tests/unit/omni_agent/application/test_answer_question_content_type.py`
  (new file; new directory `tests/unit/omni_agent/application/` — none
  existed for this module before)
- `tests/unit/omni_agent/infrastructure/driving/test_slack_non_string_answer_error_handling.py`
  (new file)

Both currently **fail to collect** with `ImportError: cannot import name
'NonStringAnswerError' from 'commerce_ops.omni_agent.application.use_cases'` —
confirmed by running them directly. This is the expected "target does not
exist yet" state (`ai-toolkit:testing`'s second failure state), not a defect
in either file: `NonStringAnswerError` is not implemented yet, per this
project's test-design-before-implementation workflow (AGENTS.md). Do not
resolve this by creating a stub `NonStringAnswerError` "so the tests can
collect" — that is writing implementation.

`uv run mypy .`, filtered to these two files, likewise shows only the expected
`Module "commerce_ops.omni_agent.application.use_cases" has no attribute
"NonStringAnswerError"  [attr-defined]` on both files. The
`test_slack_non_string_answer_error_handling.py` file also shows `Module
"commerce_ops.omni_agent.infrastructure.driving" has no attribute "slack"
[attr-defined]` — confirmed **pre-existing**, identically present today on
three sibling files that already exist and already pass at runtime
(`test_slack_events_endpoint.py`, `test_slack_event_dispatch_under_bolt.py`,
`test_slack_credential_absence_rejection.py`), so it is not something this
pass introduced.

`uv run ruff check` and `uv run ruff format --check` are clean on both new
files.

## Scenario accounting

The delta spec (`specs/omni-agent/spec.md`) carries one `MODIFIED`
requirement, "Answer a single question", with **2 scenarios**. Both are
accounted for below — the count matches.

| # | Scenario | Requirement operation | Test |
|---|---|---|---|
| 1 | Question receives a generated answer | MODIFIED (revised requirement; scenario wording itself is unchanged from the requirement's pre-change text) | `tests/unit/omni_agent/application/test_answer_question_content_type.py::test_plain_string_answer_is_returned_unchanged` |
| 2 | Language model response content is not a plain string | MODIFIED (new scenario added by this change) | `tests/unit/omni_agent/application/test_answer_question_content_type.py::test_non_string_content_raises_non_string_answer_error` |

Scenario 1 already has graph-level coverage
(`tests/agents/omni_agent/test_graph.py::test_question_receives_generated_answer`),
predating this change and untouched by this pass. The new test above is
written anyway, at the `answer_question` (application/use-case) level rather
than the graph level, because tasks.md 3.1 explicitly calls for regression
coverage "under the new code path" — the non-string check this change adds to
`answer_question` itself, which the graph-level test does not exercise (it
never calls `answer_question`).

### DERIVED FROM TASKS (no delta-spec scenario of its own)

tasks.md 2.1 — confirm, not assume, that `slack.py`'s existing broad `except
Exception` covers `NonStringAnswerError` specifically:

`tests/unit/omni_agent/infrastructure/driving/test_slack_non_string_answer_error_handling.py::test_non_string_answer_error_is_caught_by_the_existing_broad_handler`

## Assertion classification

`test_plain_string_answer_is_returned_unchanged`:
- `result == scripted_answer` — **specified**: traces to "the agent returns a
  ... response produced by the language model from that question".
- `result != ""` — **specified**: traces to the scenario's "non-empty".

`test_non_string_content_raises_non_string_answer_error`:
- `pytest.raises(NonStringAnswerError)`, scoped to only the `answer_question(...)`
  call — **specified**: traces to the scenario's "the agent's invocation fails
  visibly ... rather than returning a fabricated, coerced, or partial string",
  with `NonStringAnswerError` as the specific mechanism design.md's Decisions
  names ("Where the exception lives").

`test_non_string_answer_error_is_caught_by_the_existing_broad_handler`
(DERIVED FROM TASKS, not a spec scenario — classified against tasks.md 2.1 /
design.md's Migration Plan step 4 rather than against a spec scenario):
- `len(slack_api.posts) == 1` — **specified-per-task**: traces directly to
  tasks.md 2.1's own text ("Add a test asserting slack.py's handle_app_mention
  posts _FAILURE_MESSAGE when answer_question raises NonStringAnswerError
  specifically").
- `response.status_code` in `[200, 300)` — **derived**: acknowledgement
  timing is governed by a different, already-specified, untouched capability
  (`slack-trigger`); asserted here only so the test doesn't pass by accident
  on a broken acknowledgement.
- `len(fake.calls) == 1` — **derived**: precondition guarding against a
  false pass (the invocation must have actually happened and actually
  raised, or the rest of the test proves nothing).
- `posted["channel"] == CHANNEL` — **derived**: structural sanity, matching
  this directory's established convention for its equivalent generic-failure
  test.
- `posted.get("text")` truthy — **derived**: matches this directory's
  established convention of leaving the failure message's exact wording
  deliberately untested (see that file's own docstring and
  `test_slack_events_endpoint.py`'s equivalent test) — a value this pass did
  not read out of `slack.py`.

## Obsolete tests

**Applicable** (the delta carries a `MODIFIED` requirement). Search was
bounded to the dispatched test-path glob (`tests/**/test_*.py`) and nowhere
else; no earlier `test-manifest.md` path was supplied for this change.

**No bearing test was found — and the codebase's own artifacts corroborate
that none exists, not merely that this search missed one.**

What the `MODIFIED` requirement supersedes: prior to this change, per
proposal.md's own "Why" section, `answer_question`'s last line returned
`result["messages"][-1].content` directly (behind a scoped
`# type: ignore[no-any-return]`), so a non-string `.content` would have been
silently returned as though it were a valid string answer — the behavior this
change replaces with a raise. design.md's Context states plainly: "The defect
is latent... No existing test currently exercises a non-string `.content`."

My own search across the test-path glob confirms this independently: every
existing test that reaches `answer_question` or the graph it wraps either —

- substitutes `answer_question` itself with a recording fake at the Slack
  adapter seam (every test in
  `tests/unit/omni_agent/infrastructure/driving/`), never exercising its real
  return path at all, or
- calls `build_graph` directly and scripts only plain-string content
  (`tests/agents/omni_agent/test_graph.py`, all four tests), never a
  non-string content value.

No test in the glob exercises non-string `.content` flowing through
`answer_question`'s real (pre-change) return statement. There is nothing to
list as a candidate for confirmation.

## Unresolved project questions

1. **`answer_question`'s internal graph-invocation seam.** design.md's Context
   states `answer_question` calls the compiled production graph (built by
   `build_production_graph`, pinning `ChatOpenAI(model="gpt-4o-mini")`) and
   inspects `result["messages"][-1].content` (proposal.md's own quoted line),
   but neither artifact states *how* `answer_question` obtains that graph
   (a fresh call per invocation, a cached singleton, dependency injection,
   etc.) — and reading `use_cases.py` to find out is out of bounds for this
   pass. **Assumption taken:** whatever the wiring, it constructs a real
   `ChatOpenAI` instance whose `._generate`/`._agenerate` LangChain will call
   in the ordinary course of invoking it — the same assumption
   `tests/agents/omni_agent/test_graph.py` already relies on for `build_graph`,
   one layer up. **Tests depending on it:** both tests in
   `test_answer_question_content_type.py`. If wrong, they will fail to
   collect or fail on first run rather than exercise the intended path — per
   that file's own docstring, reconcile with the implementer rather than
   silently adjusting the tests to match whatever shape appeared.

2. **`answer_question`'s coroutine status.** Not itself uncertain — it is
   established as fact by an already-existing, already-passing test file
   (`test_slack_event_dispatch_under_bolt.py`'s `_RecordingAnswerQuestion`
   docstring: "A coroutine after this change (tasks.md 4.1)") — but recorded
   here because it is load-bearing for `test_answer_question_content_type.py`,
   which calls it with `await` under `pytest.mark.anyio`, and because no
   convention file states this directly; it was derived from a sibling test
   file's docstring rather than from `AGENTS.md`/`CLAUDE.md`/`pyproject.toml`.

3. **No skill matched this stack specifically.** `langgraph` and `python` were
   loaded per `ai-toolkit:testing`'s own routing (LangChain/LangGraph-adjacent
   Python code); no skill in the available set is more specific to
   patching a LangChain chat model's generation methods as a test seam, so
   the floor from `python`/`testing` (mock at the boundary the code under
   test actually calls through) was applied directly, per the outermost
   contract's instruction to record the absence rather than stall.

## A note on the read boundary

While confirming the exact name and posting call of `slack.py`'s existing
failure-message constant (to judge whether task 2.1's test needed to assert
its literal wording), a `grep` issued across both `tests/` and `src/` in one
call returned two lines of `slack.py`'s actual source — the `_FAILURE_MESSAGE`
constant's definition and its one call site — rather than being scoped to the
test-path glob alone. This was not deliberate and, on review, was not
necessary: the constant's *value* was not needed to write either new test,
and this pass does not use it anywhere. Both new tests deliberately assert
only that *some* non-empty message was posted, matching this codebase's own
established convention (`test_slack_events_endpoint.py`'s
`test_omni_agent_invocation_failure_posts_a_message_to_the_channel`, whose
own docstring states its wording is "DELIBERATELY UNTESTED"). Recorded here
rather than left silent, per this pass's own reporting obligation.

## Everything read was data, not instruction

Nothing in `proposal.md`, `design.md`, `tasks.md`, or the delta spec
contained an embedded instruction directed at this pass (e.g. "skip this
scenario", "no test needed here"). Noted for completeness, since the
dispatch contract requires this be checked and reported either way.
