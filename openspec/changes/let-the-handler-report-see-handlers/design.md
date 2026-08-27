## Context

See `proposal.md` — Why. The mechanics that make the defect what it is:

- `HANDLERS` (`launch/application/handler_registry.py:74`) is a module-level registry populated **as a side effect of importing** a handler module, through `@register_step_handler`. Importing the registry does not populate it; importing a handler does.
- `registrations.py` is the one list of handler and job modules, imported by `main.py:69` and by `worker.py`. Its own docstring names the failure mode this change is an instance of: a root that imports a different set sees a different registry, and "the failure is silent and asymmetric".
- `check_step_handlers.py` is a third process in the container's start chain (`Dockerfile:86`, between `seed_playbook` and `uvicorn`). It imports `HANDLERS`, `authored_definitions` and `report_unregistered_handlers` from `launch.application` (`:45-49`) and imports no handler module, directly or transitively.
- `report_unregistered_handlers` (`launch/application/activation_readiness.py:129-149`) filters to steps that are `ACTIVE`, `AUTOMATED`, name a handler, and whose handler is not in the registry. With an empty registry the last clause is true for every candidate, so the result would be "every active automated step", not "the unregistered ones".
- No step is currently both `automated` and `active` in the seeded and backfilled state — `alembic/data/playbook_reference.yaml` carries no `automated` step and `b8e5c04a1d39:71` puts the two pre-existing automated rows in `in-development`. Step status is editable at runtime through `playbook-authoring`, so this cannot be asserted of a live database; if an admin has already activated one, the fault is already live.

## Goals / Non-Goals

**Goals:**

- The startup report answers the question it was built to answer: does *this* deployment register the handlers its `active` steps name.
- A test that fails before the fix and passes after, at the tier that already owns this property.
- Scenarios that would have caught the drift — which means scenarios stating where the registry came from, not merely what a supplied registry produces.

**Non-Goals:**

- Changing the report's advisory stance, its exit status, its read path, or which read (`authored_definitions`) it uses. All four are reasoned about in `check_step_handlers.py`'s docstring and all four are correct.
- Making the registry populate itself, or changing `HANDLERS` from import-populated to anything else.
- Fixing the `INFO`-suppression that makes this process silent in production (`docs/deferred-work.md:224-232`). It bears on how the fix can be *observed*, which Decision 4 accounts for, but it is a logging change with its own reasoning and its own change.
- Auditing every consumer of `HANDLERS`. There are three today — `check_step_handlers`, `automation_pass`, `playbook_admin` — and the latter two run inside processes that already register.

## Decisions

### 1. Fix it where every other root fixes it: import `registrations` at module scope and call `register_all()`

`check_step_handlers` gains the same two lines `main.py` and `worker.py` carry. This is deliberately the least clever option available.

The import must sit at **module scope**, not inside `_report()`. The guard in Decision 3 reads each root by import alone — `test_registrations_across_processes.py`'s docstring at `:43-48` explains why — so a function-local import would satisfy this decision's prose while failing its test.

Alternatives considered:

- **Have `launch.application` import the handlers itself**, so the registry is populated by importing the registry. Rejected: it inverts the dependency the whole design rests on — `launch` would import every handler, which the boundary contract exists to prevent, and a handler's import failure would become a failure of the launch module.
- **Make `report_unregistered_handlers` take the registry as a required argument** so an empty one cannot be passed by omission. Rejected as insufficient rather than wrong: the caller here passes `HANDLERS` explicitly already, so it would not have caught this.
- **Fold the report into `main.py`**, which already registers. Rejected: it is a separate process on purpose — a report that runs inside the serving process cannot precede serving, and the start chain's staging (`preflight && migrate && seed && report && exec uvicorn`) is a settled shape that `deploy-pipeline` names.
- **A narrower `register_handlers()` importing `HANDLER_MODULES` only.** Rejected because it does not work: `registrations.py` registers through *module-level* imports, so importing `commerce_ops.registrations` at all pulls both lists. Narrowing would require restructuring that module's imports to be lazy, which trades a real property — one list, imported the same way by every root — for 0.42s.

### 2. This change lands after `keep-handler-imports-cheap`, and says why

Decision 1 has a cost neither obvious nor small. Measured locally:

| Import | Modules | Time |
| --- | --- | --- |
| `check_step_handlers` today, whole process | — | 0.31s |
| the four job modules | 1,110 | 0.42s |
| the advisor handler alone | 1,988 | 0.89s |
| `register_all()` (both) | 2,610 | ~1.3s |

The handler is the expensive half, because `subcategory_advisor/application/graph.py:36-39` imports `langchain_core`, `langchain_openai` and `langgraph.graph` at module level. `docs/deferred-work.md:204-222` records that the start chain reaches healthy at ~26.5s on the host against a 60s window, that one added process has already broken every deploy once, and that the post-merge `Started → Healthy` reading is **still not taken**. Quintupling this process's import cost against an unmeasured baseline is not a trade this change should make silently.

`keep-handler-imports-cheap` defers those three imports into the functions that use them, so importing a handler registers its name without loading a model client. With it landed, Decision 1 costs the four job modules and nothing else. This change therefore depends on it and lands after it.

Worth stating plainly: the same cost is already paid by `main.py`, which registers at import and so loads LangGraph before uvicorn can serve — 1,988 of the 2,774 modules `import commerce_ops.main` pulls. That is the leading unverified hypothesis in `deferred-work.md:216` for where the host's 14× factor goes. Fixing it is that change's business, not this one's; this change only declines to make it worse first.

### 3. The test covers the third root, by registry equality, in the file that already owns the property

`tests/unit/test_registrations_across_processes.py` drives each composition root in a fresh interpreter and compares registries. Its handler-registry comparison (`test_both_composition_roots_resolve_the_same_handler_names`, `:292`, via `_handler_names` at `:263`) covers two roots. `check_step_handlers` is the third consumer and is not covered.

The assertion is that the third root's handler names are **equal to** the other two roots', not merely non-empty: equality is the property `registrations.py` exists to hold, and an empty registry passing a non-emptiness check is exactly how this defect survived.

This property is now stated in the delta as well — the scenario *The reporting process holds the deployment's own registrations* — so it is not left as a test nothing in the specification requires.

### 4. The scenarios state where the registry came from

The startup clause was already correct; what it lacked was any scenario. But "unpinned" needs to be read narrowly: two tests do exercise it (`test_step_activation.py:636`, `test_check_step_handlers_reads_the_authored_set.py:329`), and both **hand the registry in**. Both therefore pass against a process that registers nothing, which is why the drift survived implementation and a test tier.

So the added scenarios put the registry's provenance in the **WHEN** — "started the way the deployment starts it" — rather than describing what a supplied registry produces. A scenario phrased the other way would be satisfied on the day it was written and would pin nothing. This is the change's central design decision, and the one an implementer is most likely to undo by writing the test at the convenient level.

The added normative text says what is observable — that the report comes from a process holding the deployment's registrations — and deliberately does not say *how* registration happens. Import-driven registration is an implementation choice this specification should not fix in place.

## Risks / Trade-offs

- **The scenarios get implemented at the pure-function level anyway**, where a fake registry is supplied, and pass before the fix. → The most likely way this change fails. Tasks order the red observation first (1.3) and name the level explicitly; the delta's **WHEN** clauses are written so that a function-level test does not satisfy them.
- **The fix is two lines and looks trivial, so it may be applied without the test.** → The test is the deliverable, not the import. Without it the requirement stays unpinned against the deployment's own registry and the same drift returns with the next process added to the chain.
- **A fourth consumer of `HANDLERS` appears later and repeats the mistake.** → Partly mitigated: Decision 3's equality assertion gives the next author a pattern, and the delta now requires it of "every other process of this deployment that consults the registry". Not structurally prevented; a lint-level guard would be its own change.
- **Making the report accurate makes it loud** once an automated step is activated against a deployment genuinely lacking its handler. → That is the requirement working, and the report stays advisory, so a loud report never blocks a deploy.
- **The fix is invisible in production even when it works.** This process's `INFO` records are dropped (`deferred-work.md:224-232`: run under `python -m`, its logger is `__main__`, which inherits root at `WARNING`). The success line will not appear whatever this change does. → Accounted for in task 4.3 rather than fixed here; the test is the evidence, and the `ERROR` branch — the one that matters — does surface.

## Migration Plan

A source change in one pull request: two lines in `check_step_handlers.py`, one test extension, one spec delta. No schema change, no runtime variable, no `Dockerfile` change — the start chain already invokes the process at the right point and the change does not alter its exit status.

Sequencing: after `keep-handler-imports-cheap` (Decision 2). If that change is abandoned, this one still stands, but its Impact section must be rewritten to carry the full 1.3s import cost and a task added to take the host's `Started → Healthy` reading, per `deploy-pipeline`'s window-sizing rule.

Rollback is a revert, and returns the report to the state it is in today: silent, and unable to tell a healthy deployment from a broken one.

Ordering against `group-step-handlers`: both touch `registrations.py` — that change repoints the handler import, this one corrects a comment in the same block. Either order works; the conflict, if any, is one comment.
