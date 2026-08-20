# Test manifest — `add-omni-agent`

Not an OpenSpec-schema artifact: `openspec instructions apply` will not surface
this file among its context files. Read it on purpose before implementing —
it is also linked from this library's `rules/` fragment that directs an
implementer to read it before writing code, but that import path is
machine-local, so this file's own location is the reliable pointer:
`openspec/changes/add-omni-agent/test-manifest.md`.

Derived strictly from
`openspec/changes/add-omni-agent/specs/omni-agent/spec.md`'s ADDED
requirements. No implementation of `src/commerce_ops/omni_agent/` exists yet
(confirmed below) — nothing in these tests was shaped by reading it, and
nothing in this repository was read outside the bounds this pass is allowed:
the change's own artifacts, the spec delta, `AGENTS.md`/`CLAUDE.md`, and
files under `tests/**/test_*.py`.

## Scope note: `specs` and `MODIFIED`/`REMOVED` deltas

Every requirement in this change's delta spec is `ADDED` — `omni-agent` is a
wholly new capability, and `openspec/specs` does not exist yet in this
repository (nothing has ever been archived). There is nothing to compare
against under `specsRoot`, so no such comparison was attempted.

## New test file

`tests/agents/omni_agent/test_graph.py` (plus a scaffolding
`tests/agents/omni_agent/__init__.py`, per tasks.md 4.1).

Level chosen: the compiled graph via `.invoke()` — per the `langgraph`
skill's testing ladder, this is the smallest unit that can observe the
behavior these scenarios state (an end-to-end question-in/answer-out
contract, not an isolated node function or a routing decision — this graph
has one node and no conditional routing to isolate). All four tests build
the graph with `build_graph(model)` and a fake/stub `BaseChatModel`, never a
live model — no network call, deterministic, per the `tests/agents/<module>/`
tier convention in `AGENTS.md`.

## Scenario coverage

All 4 `#### Scenario:` blocks in the delta spec are accounted for. None
uncovered.

| # | Requirement | Scenario | Test |
|---|---|---|---|
| 1 | Answer a single question | Question receives a generated answer | `tests/agents/omni_agent/test_graph.py::test_question_receives_generated_answer` |
| 2 | No tool invocation | Processing a question invokes no tools | `tests/agents/omni_agent/test_graph.py::test_processing_question_invokes_no_tools` |
| 3 | No state across invocations | Two separate invocations do not share context | `tests/agents/omni_agent/test_graph.py::test_two_invocations_do_not_share_context` |
| 4 | Model failure is surfaced, not masked | Language model call fails | `tests/agents/omni_agent/test_graph.py::test_model_failure_is_surfaced` |

Each of these 4 is `ADDED`: a new test was written for the scenario as
stated, exactly as the contract requires (`MODIFIED` is not present in this
change, so the "also record what was superseded" half of that rule does not
apply to any of them).

## Assertion classification

**`test_question_receives_generated_answer`**
- `ai_messages` non-empty → *specified* ("the agent returns a ... response").
- `ai_messages[-1].content == scripted_answer` → *specified* ("a response
  ... produced by the language model from that question" — confirmed by
  checking it's exactly the fake model's scripted output, not something
  else).
- `ai_messages[-1].content != ""` → *specified* ("non-empty response").

**`test_processing_question_invokes_no_tools`**
- `not any(isinstance(m, ToolMessage) ...)` → *specified* ("no tool or
  function call occurs").
- `not ai_messages[-1].tool_calls` → *specified*, same requirement, second
  observable signal (a model response carrying no tool-call payload).

**`test_two_invocations_do_not_share_context`**
- `not any(m.content == first_question ...)` and `not any(m.content ==
  first_answer ...)` on the second invocation's result → *specified*
  ("generated without reference to the first question or its answer").
- `ai_messages[-1].content == second_answer` → *specified* (the second
  invocation still answers correctly on its own terms).
- Deliberately no assertion on `len(second_result["messages"])`: a stricter
  check (exactly 2 messages) was considered and rejected, since the spec
  only requires no reference to the *first* invocation, not a specific
  message count for the second — asserting an exact count would be this
  test author's invented constraint, not a stated requirement.

**`test_model_failure_is_surfaced`**
- `pytest.raises(RuntimeError, ...)` raised at all → *specified* ("the
  agent's invocation fails visibly rather than returning a response as if
  the call had succeeded").
- `match="simulated language model failure"` (the exact message) →
  *derived*: the spec only requires that failure be surfaced, not that any
  particular message text propagate unmodified. Matching on the fixture's
  own message confirms the graph doesn't catch-and-rewrap the exception into
  something generic that would obscure origin, which is a reasonable reading
  of "surfaced ... rather than masked" but is this test author's inference,
  not a literal spec requirement.

Deliberately untested: none identified beyond the scope of the four stated
scenarios. `pyproject.toml`'s API-key wiring (task 3.2, "a production graph
instance that wires a real `ChatOpenAI`") is out of scope for this
deterministic tier by the project's own testing-strategy convention — a real
model integration belongs to a different, non-`tests/agents` suite that this
project has not yet named (`AGENTS.md` does not describe one). Recorded as an
unresolved project question below rather than silently left uncovered.

## Obsolete tests

**Not applicable.** Every requirement in this change's delta spec is
`ADDED`; no `MODIFIED` or `REMOVED` delta exists to supersede any existing
test's behavior, so no obsolete-test search was performed against
`tests/**/test_*.py` for this reason. (`tests/agents/test_placeholder.py`
is addressed separately below — it is scaffolding, not a test that asserts
any of this change's behavior, so it does not belong on this list either.)

## Unresolved project questions

1. **Exact state schema for `build_graph`'s compiled graph.** Neither
   `proposal.md`, `design.md`, nor the spec delta pins down the graph's
   input/output contract beyond "a single node that calls model with the
   incoming question and returns its response." These tests assume the
   conventional LangGraph `MessagesState`-style shape —
   `invoke({"messages": [HumanMessage(...)]})` returning a state whose
   `"messages"` list ends in an `AIMessage` — because that's the standard
   shape for a single chat-model node and design.md's own named test double
   (`GenericFakeChatModel`) is built around message-list input/output.
   **Tests depending on this assumption:** all four in
   `tests/agents/omni_agent/test_graph.py`. If the implementer lands on a
   different shape (e.g. a plain `{"question": ..., "answer": ...}` state),
   these tests will fail on their first run against the real graph and
   should be reconciled with the implementer rather than silently rewritten
   to match whatever shape appeared — a mismatch here is worth surfacing,
   not absorbing.
2. **Where a real-model (non-deterministic) integration test, if any, would
   live.** `AGENTS.md`'s testing strategy names three tiers
   (`tests/unit`, `tests/agents`, `tests/integration`) but doesn't describe a
   fourth tier for a live OpenAI call, and design.md's Non-Goals don't
   mention one either. No test against a live model was written (this
   would violate the deterministic `tests/agents` tier this change's tests
   belong to), and none is proposed here as a substitute question — flagged
   only so a human decides whether one is wanted, and where.
3. **`langgraph` (project skill) is available and was loaded** for this
   pass, so this is not an absent-skill gap — recorded here only to confirm
   the "load the matching skill" obligation was discharged, not because a
   question remains open.

## Baseline

Full-suite baseline taken **before** writing any test:

```
uv run pytest -q
.....                                                                    [100%]
5 passed in 0.26s
```

After adding `tests/agents/omni_agent/test_graph.py`, a full-suite run is
**interrupted at collection**, not merely failing:

```
uv run pytest -q
ERROR tests/agents/omni_agent/test_graph.py — ModuleNotFoundError: No
module named 'commerce_ops.omni_agent'
Interrupted: 1 error during collection
```

This is the expected **target-absent** state (per the `testing` skill), not
a regression against the 5-passed baseline: confirmed via two independent
checks —

- `uv run python -c "import langchain_core"` /
  `import langgraph` / `import langchain_openai` — all
  `ModuleNotFoundError`. Task 1.1–1.3 (`langgraph` and `langchain-openai` as
  runtime dependencies, `uv sync`) have not been done yet.
- `src/commerce_ops/omni_agent/` does not exist yet. Task 2.1 and 3.1 (the
  module scaffold and `application/graph.py`) have not been done yet.

Neither absence is a defect in the tests — they are exactly the "no target
exists yet" state the `testing` skill describes, and nothing here was
resolved by creating the missing module or stub. `ruff check` and
`ruff format --check` were run against the new test file directly (they
don't require the new runtime dependencies to be installed) and both pass
clean.

## Cleanup task left to the implementer

`tasks.md` 4.5 calls for deleting `tests/agents/test_placeholder.py` now
that real agent-graph tests exist. This pass does not perform that deletion:
the additive-only bound on this pass ("never edit, delete, or disable an
existing test file — under any delta operation, for any reason") applies
unconditionally, including to a placeholder whose own docstring invites its
removal. `tests/agents/test_placeholder.py` still exists, unmodified;
deleting it is left to the implementation step.
