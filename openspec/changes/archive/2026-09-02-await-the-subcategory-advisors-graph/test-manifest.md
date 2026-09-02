# Test manifest — `await-the-subcategory-advisors-graph`

Written by `ai-toolkit:openspec-test-writer` from the change's delta spec,
`design.md` Decisions 2 and 5, and `tasks.md` 2.2–2.7, before any of the
source conversion in `tasks.md` section 3 was written.

This file is **not** an artifact the OpenSpec schema defines, so it does not
appear among the context files `openspec instructions apply` surfaces. It has
to be opened on purpose.

Everything below is additive. **This pass added tests and subtracted
nothing** — no existing test file was edited, deleted, disabled, or
weakened, and no source file was touched.

---

## Baseline

Taken on this worktree, before any file was written.

- Scope: `uv run pytest tests/agents tests/unit/step_handlers -q`
- Result: **114 passed, 0 failed, 0 skipped**

Scoped rather than full, per `ai-toolkit:testing` — the scope is the two
tiers this change's eight affected test files live in, which is what makes
the new tests' contribution attributable. `tests/integration` was not run;
this change touches nothing with I/O, and `tasks.md` 5.2 asks for that tier
at verification time rather than here.

After this pass: **3 failed, 114 passed**. The three failures are the three
tests added below; the 114 are unmoved.

---

## New test file

`tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py`

Placed by subject, per `AGENTS.md`'s *Testing Strategy*: the requirement
belongs to `launch-step-automation`, but the subject under test is the
handler in `step_handlers/listing/`, and that is where the tier's directory
naming points. Agent tier, not unit — it drives a LangGraph graph with a
stubbed model.

No `conftest.py` was touched. The `anyio_backend` fixture is module-scoped
in the new file, in the per-file form the five existing async advisor files
already use; sharing it is `share-the-unit-test-harness`'s scope
(`tasks.md` 2.3).

---

## Scenario accounting

The delta states **one ADDED requirement** — *A handler's waiting does not
stop the process* — with **four** `#### Scenario:` blocks. All four are
accounted for below, each exactly once.

### 1. A handler's waiting leaves the invoking loop free — **covered**

Runner-selectable:

```
tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py::test_a_handlers_waiting_leaves_the_invoking_loop_free
```

Mechanism is the one `design.md` Decision 2 and `tasks.md` 2.6a settle: the
stub's `ainvoke` yields once (`await asyncio.sleep(0)` — a bare yield, not a
wait) then answers unconditionally; the companion task is created before the
handler is awaited; the record is read **at the moment the handler
returned**, before the companion is awaited. No `asyncio.Event`, so a
blocking handler fails rather than deadlocks. No wall-clock timing of any
kind.

**Read finding F1 below before relying on this test as a guard.** It
asserts the scenario's stated observable honestly, but measurement shows it
cannot fail for a blocking call introduced inside `recommend` itself.

Assertions:

| Assertion | Class |
|---|---|
| the companion had run by the time the handler returned | **specified** — "that other work progresses before the handler returns" |
| `resolution.outcome is Satisfied` | **specified** — "the handler then returns its resolution as it otherwise would" |
| `resolution.result == f"{NODE}\n\n{COMMENT}"` | **specified** — same clause, at the result text |
| `resolution.finding == Success(value=NODE, comment=COMMENT)` | **specified** — same clause, at the finding |
| the dependency was in fact reached (`_DEPENDENCY_ANSWERED` recorded) | **derived** — guards the first assertion against being vacuously satisfied by a handler that never called its dependency |

### 2. A dependency offering only a blocking call is awaited off the invoking thread — **uncovered**

**Reason.** No handler in this repository reaches a dependency that offers
only a blocking entry point. The advisor's dependency offers `ainvoke`, and
`tasks.md` 3.6 forbids introducing an `asyncio.to_thread` here
(`design.md` Decision 3 rejects it for this handler explicitly). A test
would have to construct a handler purely to satisfy the scenario's WHEN,
and would then assert a property of `asyncio.to_thread` — the standard
library — rather than of anything this change ships.

The requirement's own text places the other half of this scenario at review
in any case: whether an offload states *why* no asynchronous entry point was
available is "a fact only its author knows", carrying "no observable of its
own".

Recorded as **deliberately untested**, to be revisited by the first change
that actually ships a handler over a blocking-only dependency.

### 3. A framework's thread offload does not stand in for a dependency's asynchronous entry point — **covered for this change's handler; general form uncovered**

Runner-selectable:

```
tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py::test_the_dependency_is_reached_on_the_invoking_thread
tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py::test_the_advisors_graph_refuses_the_synchronous_entry_point
```

The dispatch asked explicitly whether this scenario can be given an honest
test at this level. **Partly, and the part that cannot is named rather than
faked.**

*What is honestly covered.* The scenario's discriminating fact — did the
handler use the dependency's asynchronous entry point, or hand synchronous
code to a library that thread-pools it — **is** runtime-observable for this
handler, by two independent routes, both measured against `langgraph`
1.2.11 (what `uv.lock` resolves) while writing these tests:

- A synchronous node reached through `ainvoke` runs on a worker thread with
  a different `threading.get_ident()`; an async node runs on the caller's.
  So asserting the model answered on the invoking thread distinguishes the
  two shapes directly.
- A compiled graph whose only node is a coroutine raises
  `TypeError: No synchronous function provided to "recommend"` from
  `.invoke(...)`. So there is no synchronous path through the node at all
  for a framework to accommodate.

*What is not covered, and why no test was written for it.* The scenario's
general form — **any** handler handing synchronous code to **any**
thread-pooling library — names a handler that must not exist. A test
constructing one in order to assert its non-compliance would assert a
property of its own fixture. The requirement itself assigns this clause to
review ("which entry point a handler reached is a fact about the source that
no runtime observation distinguishes"). Recorded as **deliberately
untested** at the general level.

Assertions:

| Assertion | Class |
|---|---|
| the clause "a framework's thread offload does not satisfy this requirement" holds of the shipped handler | **specified** |
| thread identity (`model.answered_on_thread == [invoking_thread]`) as the observable serving that clause | **derived** — the delta names no mechanism; measured against langgraph 1.2.11 |
| `graph.invoke(...)` raises `TypeError` | **derived** — from `design.md` Decision 2's structural guard, not from any scenario |
| the `TypeError` message contains `recommend` | **derived** — measured against langgraph 1.2.11; `pyproject.toml` declares a floor, not a pin, so a later resolution could reword it. Matched on the node name alone rather than the sentence, to keep the brittleness as small as the claim allows |
| nothing reached the model before the refusal | **derived** — establishes the refusal precedes the node, so no synchronous path exists to thread-pool |
| `resolution.outcome is Satisfied` in the thread test | **derived** — keeps the thread assertion from passing on a run that produced nothing |

### 4. How a handler waits does not change what it produces — **covered by existing tests, none of them written or touched by this pass**

`design.md` Decision 5 settles this deliberately: behaviour preservation is
asserted by the tests that already exist, **not** by new equivalence tests.
All six exits from `propose()` are already covered across the seven
agent-tier advisor files, over both the structured and the wire stub
families, and `tasks.md` 2.2 pins every one of their assertions and
assertion messages byte-for-byte through the migration.

Writing a second set of expected outcome/result/finding values here would
create a competing source of truth for the same six exits — exactly what
Decision 5 excludes. So none was written.

Runner-selectable, the files carrying this scenario's coverage:

```
tests/agents/step_handlers/listing/test_subcategory_advisor_structured_verdict.py
tests/agents/step_handlers/listing/test_subcategory_advisor_structured_recommendation.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_recommendation.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_verdict.py
tests/agents/step_handlers/listing/test_subcategory_advisor_finding_and_tools.py
tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py
tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py
```

**Two caveats, both of which the implementer must hold.**

1. That coverage is contingent on the `tasks.md` 2.2–2.7 migration, which
   **this pass did not perform** — see finding F2. Until it lands, those
   files call `propose()` synchronously and will not exercise the converted
   handler at all.
2. The equivalence this scenario states — "the same outcome, the same
   result text and the same finding **as it did before the change**" — is
   not something a test can assert on its own, because the before-values and
   the after-values live in the same assertions. What makes it real is the
   `tasks.md` 2.2 rule that a moved assertion is a finding and not an edit.
   That is a **review** obligation, and it is the load-bearing half here.

Partial independent corroboration exists: the loop-free test in scenario 1
asserts the supported exit's outcome, result text and finding against values
derived from the current source, in a file written before the conversion.
That is one exit of six, and it is recorded as corroboration rather than as
this scenario's coverage.

---

## Obsolete tests

**Not applicable, and stated with the reason rather than left empty.**

The change's delta carries exactly one operation — `ADDED` — and no
`MODIFIED`, `REMOVED` or `RENAMED` requirement. Nothing in the served specs
is superseded, so no existing test asserts superseded behaviour, and there
is nothing for an implementer to consider deleting or rewriting.

`proposal.md` says the same from the other direction: `subcategory-advisor`
is explicitly **not** modified, and every requirement it states is invisible
to whether the model is reached by `invoke` or `ainvoke`.

**This is not the same as saying no existing test must change.** Eight files
must change — mechanically, at their call sites — and that is finding F2
below, not an obsolescence. An obsolete-test entry invites a destructive
action; these entries invite a migration whose whole rule is that nothing
about them may be destroyed.

No earlier `test-manifest.md` path was supplied for this change, so the
search above was over the dispatched test-path glob (`tests/**/test_*.py`)
alone, matched on `propose(`, `build_graph(` and `advise_sub_category(`
call sites.

---

## Findings

### F1 — `design.md` Decision 2's single-yield guard does not fail for the shape it names

**Decision 2 claims:** the single-yield mechanism "keeps failing rather than
hanging" for "some new blocking call introduced directly inside `recommend`,
belonging to no stub", because "a blocked handler then leaves the
companion's record empty and the assertion fails on an empty record".

**Measured, langgraph 1.2.11:** LangGraph's own `ainvoke` machinery yields
to the loop *before* it runs the node. The companion's record is therefore
populated whatever the node body then does. Reconstructing the post-change
node shape over the new file's own stub, a node that awaits and a node that
never yields **both** leave the companion recorded as having run before the
handler returned.

So the mechanism does not hang — Decision 2 is right about that, and the
rejection of the `asyncio.Event` alternative stands — but it does not fail
either. It is not a guard against that third revert shape.

**What this does not change.** The loop-free test is still the delta
scenario's own observable asserted directly, and it stays. The two guards
that do bite are the stub's raising synchronous `invoke` (`tasks.md` 2.5)
and the thread-identity assertion in scenario 3.

**What it might change.** Whether `design.md` Decision 2's third bullet
should be reworded, and whether `tasks.md` 2.6a's rationale should be, is a
planning-artifact question. This pass does not edit planning artifacts;
`ai-toolkit:openspec-update-change` owns that. The measurement is recorded
here and in the new test file's docstring so the claim is not re-derived
from scratch by whoever reads it next.

### F2 — the `tasks.md` 2.2–2.7 migration of the eight existing files was not performed

`tasks.md` 2.1 dispatches the test writer for section 2's files, and 2.2–2.7
describe a migration of eight **existing** test files: awaiting every
`propose()` call site, making the enclosing tests `async` under
`@pytest.mark.anyio`, adding the per-file `anyio_backend` fixture to three of
them, making the stubs' synchronous `invoke` raise, correcting the
`graph.invoke()` prose in `test_subcategory_advisor_graph.py`, and making
`_schemas_the_call_site_passed()` and its callers async.

`openspec-test-writer` is bound to be **additive only**: it never edits,
deletes, or disables an existing test file, under any delta operation, for
any reason. That bound does not yield to a project convention or to a task
list. So none of those eight files was touched, and the migration remains
open for the implementation step.

The eight files, all still calling `propose()` synchronously:

```
tests/agents/step_handlers/listing/test_subcategory_advisor_graph.py
tests/agents/step_handlers/listing/test_subcategory_advisor_structured_verdict.py
tests/agents/step_handlers/listing/test_subcategory_advisor_structured_recommendation.py
tests/agents/step_handlers/listing/test_subcategory_advisor_finding_and_tools.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_conversion.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_recommendation.py
tests/agents/step_handlers/listing/test_subcategory_advisor_wire_verdict.py
tests/unit/step_handlers/listing/test_subcategory_advisor_schema_conversion.py
```

Confirmed against the tree, so the implementer need not re-derive it: all
eight stub runnables already define `async def ainvoke` (`tasks.md` 2.4 —
do not add one). Five carry a module-scoped `anyio_backend` fixture; the
three that do not are `test_subcategory_advisor_graph.py`,
`test_subcategory_advisor_finding_and_tools.py`, and the unit-tier
`test_subcategory_advisor_schema_conversion.py` (`tasks.md` 2.3).

`tasks.md` 2.2's rule governs that migration whoever performs it: an
assertion or an assertion message that has to change is a **finding**, not
an edit.

### F3 — no instruction inside the change's artifacts was acted on as an instruction

The artifacts were read as material to derive tests from. Nothing in them
was treated as directing this pass — `tasks.md` 2.1's dispatch instruction
included, which is why F2 is reported rather than obeyed.

---

## Unresolved project questions

Recorded rather than resolved silently: a dispatched subagent has no channel
to ask on.

### Q1 — `anyio` is used by the suite but declared nowhere

`@pytest.mark.anyio` and the `anyio_backend` fixture are the repository's
established idiom for async tests (five existing advisor files, plus others),
but `anyio` appears in neither `[project] dependencies` nor
`[dependency-groups] dev` in `pyproject.toml`. It currently resolves
transitively (through the langchain/httpx/starlette chain), and the marker
works — the baseline run confirms it.

**Assumption taken:** the idiom is the project's convention and stays
resolvable, so the new file uses it unchanged rather than introducing a
different async-test mechanism.

**Tests depending on it:** both `@pytest.mark.anyio` tests in the new file,
and every existing `@pytest.mark.anyio` test in the repository. A future
dependency resolution that drops `anyio` would un-run them rather than fail
them, which is the same class of invisibility `tests/conftest.py`'s
no-skip guard was written against.

### Q2 — where a test for a `launch-step-automation` requirement lives when its subject is a handler

`AGENTS.md` names `tests/agents/<subject>/` "one directory per subject under
test, named for where that subject lives". The requirement is
`launch-step-automation`'s; the subject exercising it is
`step_handlers/listing/subcategory_advisor.py`.

**Assumption taken:** subject wins over capability, so the new file sits
beside the other advisor agent-tier files in
`tests/agents/step_handlers/listing/`.

**Tests depending on it:** all three new tests — placement only; a move
would not change an assertion.

### Q3 — whether the migration in F2 is the test writer's work or the implementer's

`tasks.md` 2.1 reads as though the writer produces section 2's files;
`openspec-test-writer`'s additive-only bound forbids it. The two cannot both
hold.

**Assumption taken:** the bound wins, and the migration is reported rather
than performed (F2).

**Tests depending on it:** none of the new tests. But scenario 4's coverage
claim above depends on the migration being done by someone, so this question
is load-bearing for the coverage count, not just for process.

---

## What the implementation step must make pass

Three tests, currently failing, all in
`tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py`:

```
uv run pytest tests/agents/step_handlers/listing/test_subcategory_advisor_yields_the_loop.py -q
```

- `test_a_handlers_waiting_leaves_the_invoking_loop_free`
- `test_the_dependency_is_reached_on_the_invoking_thread`
- `test_the_advisors_graph_refuses_the_synchronous_entry_point`

All three fail today with one message, which is the shape `tasks.md` 2.8
says a failure here should read as:

> `AssertionError: the advisor reached the model through the model's
> synchronous `invoke(...)` entry point instead of awaiting `ainvoke(...)`
> — the enclosing coroutine then never yields, and the invoking loop is
> pinned for the whole of the round-trip`

Per `ai-toolkit:testing` that is the **target-absent** failure state: the
async path does not exist yet, so the assertions in these tests have not
been exercised and their quality is not yet established by a run. What has
been established, by an isolated probe over the new file's own stub rather
than by editing the source, is that the mechanism itself is sound — the
companion records, the thread identity matches, and the graph refuses
`.invoke` in the post-change node shape.

Making them pass is `tasks.md` section 3, and nothing else:

- 3.1 `recommend` becomes `async def`, awaiting `structured.ainvoke(...)`
- 3.2 `propose` becomes `async def`, awaiting `running.ainvoke(...)`
- 3.3 `advise_sub_category` awaits `propose(...)`

No stub, no empty module, no `asyncio.to_thread`, and no edit to an
assertion in these three tests.

Alongside them, and not made passing by section 3 alone: the F2 migration.
`tasks.md` 5.1's count is the 1.1 baseline **plus** the three tests above,
with nothing subtracted.
