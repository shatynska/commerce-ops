## Why

`introduce-automation-runtime` (2026-08-26) established the step-handler registry and shipped the first handler, `subcategory_advisor`, as a **top-level package** — a sibling of the bounded contexts, with its own `.importlinter` contract and its own `application/` layer. That placement is what `module-boundary-conventions` prescribes for a second level of nesting, and for one handler it is unremarkable.

It does not survive the tenth. Automated steps are expected in quantity and most will be small scripts; one top-level entry each turns `src/commerce_ops/` from a list of bounded contexts into a list of automations, and adds one boundary contract per script. Grouping them costs one move while exactly one handler exists, and grows more expensive with every handler added before it happens.

## What Changes

- Introduce `src/commerce_ops/step_handlers/`, a single top-level package holding every step handler, grouped by discipline (`listing/`, `pricing/`, …) so the handler's import path mirrors the dotted handler **name** a step stores. This is the third kind of top-level package, after the bounded contexts and `shared` — a container of automation implementations, not a bounded context, and it never grows a `domain/`, `application/` or `infrastructure/` layer of its own.
- Move `commerce_ops.subcategory_advisor.application.{graph,handler}` to `commerce_ops.step_handlers.listing.subcategory_advisor`, collapsing the per-handler `application/` layer that a single handler does not earn.
- Fix **no** internal shape for a handler. One module (`keyword_check.py`) where a file suffices; a package where several files do; layers only where one genuinely earns them. Python resolves `foo.py` and `foo/__init__.py` behind the identical import statement, so a handler that outgrows a file changes nothing outside itself.
- State the one obligation that shape freedom carries, as a **repository code convention recorded in `README.md`** rather than as a spec requirement: registration happens at import through `@register_step_handler`, so a handler that is a package re-exports its registration from `__init__.py`. Without it the package imports cleanly and the handler is simply absent from the registry — the asymmetric failure `registrations.py` already documents for job modules, one level down. It is a convention about where code sits, not about what the system does, which is why it changes no capability and leaves `skip_specs` correct.
- Replace the `subcategory-advisor-boundary` import contract with one `step-handler-boundary` contract sourced at `commerce_ops.step_handlers`, carrying the same forbidden set and the same reasoning. It covers every handler present and future, so adding a handler never edits `.importlinter`.
- Record both decisions in `README.md`'s Architecture section and `AGENTS.md`'s Architecture summary: the new kind of top-level package, and why a handler sits outside `launch` rather than inside `launch/application`.

Deliberately **not** changed: the handler name `listing.subcategory_advisor`, the `playbook_steps.handler` column that stores it, the registry, the pass, the startup report, and the activation check. Nothing about this change is visible from Postgres, from Slack, or from the admin surface.

## Capabilities

### New Capabilities

None — a pure structural refactor. `launch-step-automation` and `subcategory-advisor` describe what a handler is given, what it may say back, and what the pass does with it; none of that depends on where the handler's source file sits, and the handler *name* is deliberately held constant so even the registry's observable contents are unchanged.

### Modified Capabilities

None — see above. `.openspec.yaml` for this change sets `skip_specs: true` accordingly, following `restructure-src-layout` (2026-08-20), the closest precedent: a layout move that changed no behavior and declared no delta.

## Impact

- **New**: `src/commerce_ops/step_handlers/{__init__.py,listing/__init__.py}` and `step_handlers/listing/subcategory_advisor.py` (or a package, per design.md).
- **Removed**: `src/commerce_ops/subcategory_advisor/` in full — its `application/__init__.py` public surface has no caller once the handler is one importable unit.
- `src/commerce_ops/registrations.py:49-51`: the handler import moves; `HANDLER_MODULES` is unchanged in shape, since a package is a `ModuleType` exactly as a module is.
- `.importlinter:270-297`: `subcategory-advisor-boundary` becomes `step-handler-boundary`, `source_modules` generalised from `commerce_ops.subcategory_advisor` to `commerce_ops.step_handlers`. Its `ignore_imports` exemptions carry over verbatim — they exempt edges `launch.application` makes on its own behalf, which the move does not touch.
- `tests/agents/subcategory_advisor/` moves to `tests/agents/step_handlers/listing/`. Three places in `test_subcategory_advisor_graph.py` name the advisor's import path and must be repointed: the docstring's invented-assumptions note (`:52`), the module import (`:98`), and the entry-point probe's candidate list (`:324-325`).
- `tests/unit/test_registrations_across_processes.py`: already holds the per-root registration assertions and is where this change's registration guard belongs.
- Untouched: every `tests/**` file that names the *string* `"listing.subcategory_advisor"` (seven of them, in `tests/unit/launch/**` and `tests/integration/launch/**`). They assert on the handler name, not on its location, which is the property this change preserves.
- Untouched: `alembic/`, `pyproject.toml` (`packages = ["src/commerce_ops"]` ships the tree wholesale), `Dockerfile`, `docker-compose.yml`, `deploy.yml`. No runtime variable is added, so `AGENTS.md`'s four-part obligation for a new setting does not apply.
- `README.md`, `AGENTS.md`: Architecture section and summary updated as described above.
