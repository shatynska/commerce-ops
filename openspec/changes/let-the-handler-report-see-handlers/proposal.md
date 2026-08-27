## Why

`launch-playbook` requires that "a deployment whose registry no longer answers for an `active` step's handler SHALL... be reported at startup, where a deployment fault belongs". `check_step_handlers` is the process that owes that report, and it cannot produce it.

It imports `HANDLERS` from `commerce_ops.launch.application` and never imports `commerce_ops.registrations` (`check_step_handlers.py:45-49`). Importing a handler module is what registers it, and nothing in that process imports one — so in the container's start chain (`Dockerfile:86`) the registry it consults is **empty, unconditionally**. It cannot distinguish a deployment that registers a handler from one that does not, which is the single question it exists to answer.

The fault is latent today only because no step is both `automated` and `active`: `report_unregistered_handlers` filters to those, finds none, and returns nothing. It is latent, not harmless — the moment the first automated step is activated, the report inverts and names that step as unresolvable on every deploy while the worker resolves it perfectly well. A startup report that cries fault at a healthy deployment is worse than no report, because the next real fault reads as more of the same.

The startup clause carries **no scenario**. Two tests do cite it — `tests/unit/launch/application/test_step_activation.py:636` and `tests/unit/test_check_step_handlers_reads_the_authored_set.py:329` — but both **supply** a registry rather than reading the deployment's own, so both pass against a process that registers nothing. That is the gap this change closes: not that the clause is untested, but that nothing tests it against the registry the deployment actually has.

## What Changes

- Register handlers in the process that reports on them: `check_step_handlers` imports `commerce_ops.registrations` at module scope and calls `register_all()`, as `main.py:69` and `worker.py` do. It already sits outside `.importlinter`'s containers — its own docstring says so — which is what makes naming `registrations` there legal.
- Extend `launch-playbook`'s *A step carries the brief and the handler its automation needs* with **two normative paragraphs and four scenarios** covering the startup clause. The paragraphs say that the report must come from a process holding the deployment's own registrations, and that a report against an empty registry does not satisfy the requirement. The scenarios state the registry's *provenance* in their **WHEN** — "started the way the deployment starts it" — which is what makes them fail against the current code; a scenario that merely supplies a registry is already satisfied today.
- Extend `tests/unit/test_registrations_across_processes.py` to cover `check_step_handlers` as the third root that consults the registry, asserting its handler names **equal** the other two roots' rather than merely being non-empty.

Not changed: the report stays **advisory**, exiting zero on a fault. `check_step_handlers.py`'s own reasoning for that is untouched and correct — refusing to start would turn one unresolvable step into a full outage. This change makes the report accurate, not fatal.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-playbook`: the requirement *A step carries the brief and the handler its automation needs* gains two normative paragraphs and four scenarios pinning the startup report its existing text already demands. No existing sentence or scenario is altered — the behaviour was always specified; nothing pinned it against the deployment's own registry, and the implementation drifted from it.

## Impact

- **Depends on `keep-handler-imports-cheap`, and SHOULD land after it.** Importing `registrations` here pulls the handler modules into a start-chain process, and today that means LangGraph, `langchain_openai` and the OpenAI client: 1,988 modules and 0.89s locally, in a process that currently costs 0.31s in total. `docs/deferred-work.md:204-222` records that chain length has already broken one deploy and that the host's `Started → Healthy` figure has never been measured. `keep-handler-imports-cheap` makes a handler module cheap to import, which reduces that to the four job modules (1,110 modules, 0.42s). See design.md, Decision 2.
- `src/commerce_ops/check_step_handlers.py`: gains the `registrations` import and the `register_all()` call. No change to its read path, its exit status, or its advisory stance.
- `tests/unit/test_registrations_across_processes.py`: gains `check_step_handlers` as a third root, alongside the existing handler-registry comparison at `:292`.
- Untouched: `Dockerfile` (the start chain already runs the process at the right point), `alembic/`, every runtime variable, `deploy.yml`. No schema change and no configuration change.
- Interaction with `group-step-handlers`: both changes touch `src/commerce_ops/registrations.py` — that one repoints the handler import, this one corrects a comment about the report. The overlap is confined to that file's handler-import comment block and resolves trivially in either order.
