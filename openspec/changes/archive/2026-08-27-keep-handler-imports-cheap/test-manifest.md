# Test manifest — `keep-handler-imports-cheap`

Written before any implementation of this change landed, from the change's
delta spec and its planning artifacts alone. No source under `src/` was read,
edited, or created in this pass; no existing test was edited, deleted, or
disabled. **This pass adds tests and never subtracts.**

This file is not part of the OpenSpec schema, so it does not appear among
`openspec instructions apply`'s context files. It has to be opened on purpose
before implementing.

## Baseline

Taken before writing anything, full commit-time tier:

```
uv run pytest tests/unit tests/agents -q
-> 1111 passed in 38.96s
```

Nothing was failing beforehand, so every failure recorded below is
attributable to this pass.

**Scope of the baseline:** `tests/unit` + `tests/agents` (the tier `AGENTS.md`
runs at commit time). `tests/integration` was **not** run — it needs a
Postgres database, and nothing in this change touches I/O, persistence, or any
module the integration tier drives. Recorded as a scoped baseline with its
scope, not as a full-suite one.

After this pass, same command:

```
uv run pytest tests/unit tests/agents -q
-> 2 failed, 1112 passed in 41.38s
```

The two failures are the new guards, and are the expected pre-implementation
state (tasks.md 2.4). The 1112th pass is the new positive test.

## Files added

- `tests/unit/test_handler_registration_is_cheap.py` — the only file added.

Placed in `tests/unit/` at the top level, beside
`tests/unit/test_registrations_across_processes.py` and
`tests/unit/test_startup_without_configuration.py`, because its subject is
`commerce_ops.registrations` — a composition-root concern that belongs to no
single module's layer. It is a fast, mocked-tier test in the sense
`AGENTS.md` means: no network, no database, no live model; the subprocesses it
spawns import Python modules and print JSON.

## Scenario accounting

The delta spec has **three** `#### Scenario:` blocks under one ADDED
requirement, *Registering a handler does not load what the handler needs to
run*. All three are accounted for below.

| # | Scenario | Accounted for by |
| --- | --- | --- |
| 1 | Registering a handler loads no model client | `tests/unit/test_handler_registration_is_cheap.py::test_loading_a_handler_module_alone_loads_no_model_client` (the "holds no resource" half) and `::test_every_handler_module_registers_its_name` (the "its name resolves" half) |
| 2 | A handler still resolves a step | **Covered by existing, unmodified tests** — `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` (all of it). No new test written. See below. |
| 3 | A process that never invokes a handler still pays only for the registration | `tests/unit/test_handler_registration_is_cheap.py::test_registering_every_handler_loads_no_model_client` |

Runner-selectable identifiers, in full:

```
uv run pytest "tests/unit/test_handler_registration_is_cheap.py::test_registering_every_handler_loads_no_model_client"
uv run pytest "tests/unit/test_handler_registration_is_cheap.py::test_every_handler_module_registers_its_name"
uv run pytest "tests/unit/test_handler_registration_is_cheap.py::test_loading_a_handler_module_alone_loads_no_model_client"
uv run pytest tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py
```

### Scenario 2, and why no test was written for it

tasks.md 5.2 states that the existing agent-graph tests are this scenario's
coverage and that a duplicate must not be written. That accounting holds on
inspection, and this pass agrees with it:

- The scenario asks that a handler whose resources are obtained on invocation
  produce "the outcome and the result text those tests specify, unchanged by
  when its resources were obtained". It names the deterministic agent-graph
  tests as the specification of the expected answer, so a new test could only
  restate them.
- `tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py` drives
  `build_graph(stub)` with a stubbed model over all eight scenarios of the
  `subcategory-advisor` capability. Deferring an import changes none of its
  inputs. Its passing **unmodified** is the observation the scenario asks for;
  a copy of it in a new file would assert the same thing twice and drift.
- One consequence for whoever implements: that file passing is not incidental
  verification, it is scenario 2's evidence. If it needs editing to pass, the
  deferral changed behaviour and the change is wrong — do not edit it.

### What was deliberately left uncovered

- **`langchain_core` and `langchain_openai` absence.** The guards assert only
  the pair `langgraph` / `openai`, which proposal.md and tasks.md 2.1 name.
  The requirement is broader ("a language model client, a graph, an HTTP
  session, or anything else"), but a wider library list risks failing for a
  reason outside this change's scope — a transitive import from an unrelated
  job module — and the guard would then be weakened rather than believed.
  Recorded so the absence of these two names is visibly a decision.
- **Module counts and import durations.** tasks.md 1.1–1.2 and 5.3 ask for
  ~2,610 -> ~1,110 measurements; those are pull-request measurements, not
  assertions. A count threshold in a test fails on an unrelated dependency
  bump while saying nothing about registration cost. The probe reports its
  count in failure messages as context only.
- **Task 5.4 — the web process is unchanged (`import commerce_ops.main` still
  pulls `langgraph`).** Deliberately untested. design.md Decision 3 says this
  is the *expected* state, not a property to preserve: the omni_agent half is
  a candidate for the same treatment in a later change, and a test asserting
  `langgraph` is present in `main` would have to be deleted the day that
  lands. It stays a PR-description check.
- **The "MAY be retained between invocations" clause** of the requirement.
  Permissive, not obligatory — nothing to fail.

## Assertion provenance

**SPECIFIED** (traces to the delta spec):

- Importing the one list and invoking no handler leaves no handler's working
  resources loaded (scenario 3).
- Loading a handler module makes its name resolve in the registry
  (scenario 1, first half).
- Loading a handler module leaves no resource it uses to resolve a step
  (scenario 1, second half).

**Specified by the change's own artifacts, not by the delta prose** — recorded
separately because the delta deliberately avoids naming Python mechanics:

- "the resources the handler uses" is read as the top-level packages
  `langgraph` and `openai` being absent from `sys.modules`. Fixed by
  proposal.md ("leaves `langgraph` and `openai` out of `sys.modules`") and
  tasks.md 2.1.
- The property is asserted at the level of `commerce_ops.registrations`, not
  one handler module. Fixed by design.md Decision 2 and tasks.md 2.1.
- A fresh interpreter per observation. Fixed by design.md Decision 2 and
  tasks.md 2.3.

**DERIVED** (inferred here; no requirement states them):

- Every entry of `HANDLER_MODULES` exposes a module-level string
  `HANDLER_NAME`, and a module exposing none **fails** rather than being
  skipped. tasks.md 2.2 asks for the loud failure; the name-per-module
  convention is established by practice, not by a requirement.
- `HANDLER_MODULES` is non-empty. Derived guard, and the reason the positive
  test exists at all: absence assertions alone would pass against a
  `registrations.py` that imported nothing.
- Per-module attribution (scenario 1 driven once per module rather than once
  over the list). Derived from how the scenario is phrased, and justified by
  what it buys at twenty handlers — naming the offender rather than the fact.

## Obsolete tests

**Not applicable.** Every delta in this change is `ADDED` — one new
requirement with three new scenarios, and no `MODIFIED`, `REMOVED`, or
`RENAMED` operation anywhere in
`specs/launch-step-automation/spec.md`. Nothing existing is superseded, so
there is nothing to nominate for deletion or rewrite.

For the avoidance of doubt: no existing test asserts the *opposite* property
either. A search of `tests/**/test_*.py` for `sys.modules`, `langgraph` and
`HANDLER_MODULES` found no test asserting that a handler's libraries are
loaded at registration, so nothing turns red by design when task 3 lands.

## Unresolved project questions

Recorded rather than resolved silently, per the testing floor — this pass runs
non-interactively and has no channel to ask on.

1. **Tier placement of a subprocess-driven guard.** `AGENTS.md` splits tests
   by cost and by module/layer; this one spawns subprocesses (~2.4s today,
   less once the imports are deferred) and belongs to no module's layer.
   *Assumption taken:* `tests/unit/` at the top level, following
   `test_registrations_across_processes.py` and
   `test_startup_without_configuration.py`, which do the same thing for the
   same reason. *Depends on it:* the whole file. If the project would rather
   such guards ran at pre-push, the file moves; no assertion changes.
2. **`HANDLER_MODULES`' name and shape.** tasks.md 2.2 fixes it as
   `tuple[ModuleType, ...]` on `commerce_ops.registrations`; this pass did not
   read `registrations.py` to confirm it. *Assumption taken:* that name and
   shape. *Depends on it:* all three tests. Verified indirectly — the probe
   ran successfully and reported one module, so the assumption held on the
   current tree. The single correction point is `_registry_probe` /
   `_REGISTRY_PROBE_SCRIPT`, and the probe's failure message says so.
3. **No stack skill for "asserting a module is absent from `sys.modules`".**
   `ai-toolkit:testing` and `ai-toolkit:python` were both loaded; neither
   carries idiom for fresh-interpreter import-cost properties, so the
   repository's own precedent
   (`tests/unit/test_registrations_across_processes.py`) was followed instead,
   as design.md's risk section directs. Recorded as an absence, not a gap that
   blocked anything.

## Expected state at hand-off

On the unmodified tree:

```
uv run pytest tests/unit/test_handler_registration_is_cheap.py -q
-> 2 failed, 1 passed in 2.34s
```

- `test_registering_every_handler_loads_no_model_client` — **fails.** A fresh
  interpreter that imported `commerce_ops.registrations` and invoked nothing
  holds 2,645 modules, `langgraph` and `openai` among them.
- `test_loading_a_handler_module_alone_loads_no_model_client` — **fails.**
  `commerce_ops.subcategory_advisor.application.handler` alone is 2,023
  modules, `langgraph` and `openai` among them.
- `test_every_handler_module_registers_its_name` — **passes**, and must keep
  passing. It is the half the deferral must not break.

Both failures are the strongest failure state: the assertions executed and
discriminated between the property holding and not holding. Neither is an
absent target, and neither is a defect in the test. **Do not weaken either to
reach green** — they go green when tasks 3.1–3.2 move the imports, and not
before.

What the implementation step must make pass, in one line:

```
uv run pytest tests/unit/test_handler_registration_is_cheap.py tests/agents/subcategory_advisor/test_subcategory_advisor_graph.py
```
