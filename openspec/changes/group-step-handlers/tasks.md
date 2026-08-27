## 1. Establish the container

- [ ] 1.1 Create `src/commerce_ops/step_handlers/__init__.py` and `src/commerce_ops/step_handlers/listing/__init__.py`, both empty of behavior — the container holds handlers, and nothing else (design.md, Decision 2).
- [ ] 1.2 Move `subcategory_advisor/application/graph.py` and `handler.py` into a single `step_handlers/listing/subcategory_advisor.py`, dropping the `application/__init__.py` public surface with them: a handler that is one importable unit has nobody to expose a surface to (design.md, Decision 3).
- [ ] 1.2a Reconcile what the merge collides, rather than letting one side win by accident: the merged module carries **one** docstring preserving both bodies of reasoning — `graph.py:1-29` on what the advisor may propose and why a masked failure is unacceptable, and `handler.py:1-19` on why which processes import the module is load-bearing — and **one** `__all__` that is the union of `graph.py:43-50` and `handler.py:35`. The handler docstring is the one Decision 3's re-export obligation rests on; losing it is the likeliest silent damage in this change.
- [ ] 1.2b Note in that docstring that registration now runs when the module is imported at all, where previously `graph.py` could be imported without it. `_graph()` stays `lru_cache`d so no credential read moves to import time, and `StepHandlerRegistry.register` only raises for a *different* callable under one name, so a repeated import is safe.
- [ ] 1.3 Delete `src/commerce_ops/subcategory_advisor/` entirely, directory included, and confirm no `subcategory_advisor.py` is left beside any `subcategory_advisor/` — where both exist the package wins silently (design.md, Decision 3).
- [ ] 1.4 Verify `HANDLER_NAME` still reads `"listing.subcategory_advisor"` and the internal imports resolve within the new module; the registered name is the one thing the move must not touch (proposal.md, What Changes).

## 2. Rewire the composition roots

- [ ] 2.1 Repoint `registrations.py:49-51` to `from commerce_ops.step_handlers.listing import subcategory_advisor as _subcategory_advisor`, leaving `HANDLER_MODULES` otherwise unchanged, and update its comment block to name the new location.
- [ ] 2.2 Confirm both roots still register the handler: import `commerce_ops.main` in a fresh interpreter, then `commerce_ops.worker`, and assert `"listing.subcategory_advisor" in HANDLERS` in each. A handler imported into only one root is the asymmetric failure `registrations.py` exists to prevent.

## 3. Replace the boundary contract

- [ ] 3.1 In `.importlinter`, rename `subcategory-advisor-boundary` to `step-handler-boundary`, set `source_modules = commerce_ops.step_handlers`, and keep the forbidden set and the `ignore_imports` exemptions verbatim — they exempt edges `launch.application` makes on its own behalf, which this change does not touch (design.md, Decision 4).
- [ ] 3.2 Update the contract's trailing comment: it currently reasons about "the advisor" and now reasons about any handler.
- [ ] 3.3 Add no `layers` contract for `step_handlers` — deferred to the change that introduces the first handler with layers to order (design.md, Decision 4).
- [ ] 3.4 Run `uv run lint-imports` and confirm every contract is kept.

## 4. Move and extend the tests

- [ ] 4.1 Move `tests/agents/subcategory_advisor/` to `tests/agents/step_handlers/listing/`, keeping the test file's name.
- [ ] 4.2 Repoint all three places that name the advisor's import path: the docstring's invented-assumptions note (`:52`), the module import (`:98`), and the probe's candidate list (`:324-325`). Only `:98` is load-bearing — it is a plain `import`, so a stale path there fails the tier. The other two do not fail: `_propose_entry()` wraps `importlib.import_module` in `except ImportError: continue`, and its first candidate is already `advisor_graph`, which exports `propose` (`_PROPOSE_NAMES[0]`), so the probe returns before reaching `:324-325` and a stale name is inert. **A green run at 6.2 is therefore not evidence that `:52` and `:324-325` were repointed — check them by reading.**
- [ ] 4.2a Collapse the probe's candidate list while repointing it: after the merge the graph module and the handler module are the same module, so the two extra `importlib` candidates name what `advisor_graph` already is. Leaving three names for one module is what let a stale path hide.
- [ ] 4.3 Add the registration guard to `tests/unit/test_registrations_across_processes.py`, which already drives each composition root in a fresh interpreter. Strengthen `test_each_root_registers_at_least_one_handler` (`:320`) from a non-emptiness assertion to a name-specific one — that `"listing.subcategory_advisor"` is in `HANDLERS` in **both** roots — rather than adding a sibling file with its own subprocess machinery (design.md, Risks).
- [ ] 4.4 Leave untouched every test naming the *string* `"listing.subcategory_advisor"` (`tests/unit/launch/**`, `tests/integration/launch/**`). That they pass unmodified is the evidence the name did not move with the file.

## 5. Record the conventions

- [ ] 5.1 In `README.md`'s Architecture section, name `step_handlers/` as the third kind of top-level package after the bounded contexts and `shared`, and state why the "second level of nesting signals a sibling top-level module" rule does not apply to it (design.md, Decision 2).
- [ ] 5.2 In the same section, state the handler shape rule: a module until it earns a package, a package until it earns layers, and a package re-exports its registration from `__init__.py` (design.md, Decision 3).
- [ ] 5.3 In `AGENTS.md`'s Architecture summary, state only the positive facts — `step_handlers/` is the third kind of top-level package; a handler is a module until it earns a package, a package until it earns layers; a package re-exports its registration. Do **not** mirror README's carve-out there: `AGENTS.md` carries the public-surface and Shared-Kernel rules but never states the one-level-nesting rule, so an exception to it would read as a non-sequitur.
- [ ] 5.3a Amend `AGENTS.md`'s Testing Strategy, which states the agent tier as `tests/agents/<module>/`. After 4.1 that tier holds `tests/agents/step_handlers/listing/`, so the convention becomes: the tier holds one directory per subject, named for where that subject lives, which may be more than one segment deep. Check the replacement wording against `tests/agents/omni_agent/` as well as the new directory — its subject is `omni_agent/application/graph.py`, so a rule phrased as "mirrors the source path" would be violated on the day it is written. Left unamended, this change quietly violates a stated convention.
- [ ] 5.4 State that discipline grouping is a convention, not an enforced rule, so a future reader does not add a check nobody asked for (design.md, Decision 5).

## 6. Verify

- [ ] 6.1 Run `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `uv run lint-imports`.
- [ ] 6.2 Run `uv run pytest tests/unit tests/agents` — the commit-time tier, which must be green before the move is committed at all.
- [ ] 6.3 Run `uv run pytest tests/integration` if a database resolves; it touches no handler path, so it is a regression check, not a target.
- [ ] 6.4 Confirm the whole change is one commit as far as `.importlinter`, `registrations.py` and the moved files are concerned — an intermediate state fails `lint-imports` and the pre-commit tier (design.md, Migration Plan).
