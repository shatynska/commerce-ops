## Context

See `proposal.md` — Why. What shapes the approach is what already exists:

- `launch/application/handler_registry.py` holds one process-wide `HANDLERS`, keyed by a **free string** a step stores in `playbook_steps.handler`. Registration happens at import, through `@register_step_handler`, and `registrations.py` — the one list both composition roots import — is what makes it happen in both processes.
- `.importlinter` enforces `infrastructure → application → domain` inside each of the six containers, plus one `forbidden` contract per module. `subcategory_advisor` is in none of the containers; it has only its own boundary contract.
- `README.md`'s Architecture section states that a module may nest one level, and that **a second level of nesting is a signal the concept belongs as a sibling top-level module instead**. The current placement is that rule applied.
- `StepHandler = Callable[[StepContext], Awaitable[StepResolution]]`. A handler is given the step, the launch and the product; `StepResolution` has no provenance field, so a handler structurally cannot attribute its own work.

## Goals / Non-Goals

**Goals:**

- One top-level entry for all handlers, whose count does not grow with theirs.
- One `.importlinter` contract for all handlers, likewise.
- A per-handler shape chosen by that handler's actual size, changeable later without touching anything outside it.
- The reasoning for handlers sitting outside `launch` recorded where the next reader finds it, so the question is settled rather than re-argued.

**Non-Goals:**

- Changing any handler's behavior, its registered name, or the stored value that names it.
- Enforcing that a handler's location matches its name, or that a step's discipline matches either. Both stay conventions (see Decisions 3 and 5).
- Adding a second handler, or activating the one that exists. Both remain what they are today: an admin action against a live step set.

## Decisions

### 1. Handlers live outside `launch`, not inside `launch/application`

Placing them in `launch/application/step_handlers/` was considered first, on the reading that a handler is a use case and would then share `launch/infrastructure`.

It was rejected because **that placement does not grant the access it was for, and grants a great deal it must not have**. `module-layers` (`.importlinter:5-18`) lists `commerce_ops.launch` as a container ordered `infrastructure / application / domain`, so a handler inside `launch.application` is on the side of the boundary that cannot import `launch/infrastructure` at all — the one thing the placement was chosen for.

What it would change instead is the *outgoing* boundary, and in the wrong direction. Compare the two forbidden sets:

| Reachable from a handler | Today (`subcategory-advisor-boundary`, `.importlinter:270-297`) | Inside `launch.application` (`products-application-boundary`, `.importlinter:166-188`) |
| --- | --- | --- |
| `launch.infrastructure` | forbidden | forbidden |
| `launch.domain` | **forbidden** | **reachable** |
| `catalog.application` | **forbidden** | **reachable** |
| `access.application` | **forbidden** | **reachable** |
| `shared.infrastructure` | reachable | forbidden |

So the move would buy no access to `launch/infrastructure`, cost the ability to grow a driven adapter of its own, and open `launch.domain`, `catalog.application` and `access.application` — reach the handler contract exists to deny. A handler that could reach `catalog.application` would read the catalog itself, which is exactly what `launch-step-automation`'s "The product is supplied, not fetched" forbids.

And on inspection there is nothing there to share. `launch/infrastructure/driven/` holds the launch, playbook and automated-result repositories — recording is the pass's job, and `StepResolution`'s missing provenance field is the deliberate enforcement that a handler does not record — plus the Slack notifier and the ClickUp adapters, which are projection, downstream of a recorded outcome. `launch/infrastructure/driving/` holds `automation_confirmation`, and delivery is the pass's first half. A handler reaching any of them would defeat the contract the registry exists to hold.

What a handler actually needs from outside is already provided: the **product** is injected into `StepContext` by the pass (`launch-step-automation`: "The product is supplied, not fetched"); **credentials** come from the environment or `shared/application/settings.py`, which is application-layer and importable from anywhere; an **external API client** is a library dependency, not project infrastructure. Where a handler ever needs a real project-side collaborator, the sanctioned path is the one `worker.py` uses for every collaborator it injects — module-level injection at the composition root, which is what `worker.py` does for every collaborator it injects (`:68`, `:93`, `:100`, `:119`, `:151`, `:155`) — including `automation_pass.read_product = _read_catalog_product` (`:100`), the one that feeds the pass this change's handler runs under. Not an import, and not a layer.

The ownership argument runs the same way: the registry exists so `launch` knows *that a name resolves*, never *how*. Making `launch.application` the home of every automation's implementation gives that back.

### 2. `step_handlers/` is a container, not a bounded context — and README must say so

`step_handlers/listing/subcategory_advisor` is two levels of nesting, which README's rule reads as a signal to promote to a sibling top-level module. Left unamended, the next reader applies that rule and undoes this change.

The rule is about **bounded contexts**, and `step_handlers` is not one: it has no model, no ubiquitous language and no invariants of its own. It is a container of adapters into `launch`'s automation port, and the third kind of top-level package after the bounded contexts and `shared`. README and `AGENTS.md` state that explicitly, alongside the reasoning in Decision 1.

Alternatives considered: `launch/step_handlers/` as a nested child module (rejected with Decision 1, and it is two levels under `launch` anyway); one top-level package per handler (the status quo the proposal exists to end); `automations/` as the name (rejected — `step_handlers` names the contract it satisfies, and matches `HANDLER_MODULES`, `register_step_handler` and `check_step_handlers`).

### 3. A handler's shape is free; a package re-exports its registration

Python resolves `foo.py` and `foo/__init__.py` behind an identical import statement, and never writes the extension. So moving a handler from a file to a package plus an internal split is a change no importer sees — not `registrations.py`, not `.importlinter` (a `forbidden` contract's `source_modules` covers a module and all its descendants), not `HANDLER_MODULES` (a package is a `ModuleType`). A handler is therefore a module until it earns being a package, and a package until it earns layers.

The obligation this carries: **a handler that is a package re-exports its registration from `__init__.py`**, because the decorator only runs if the module holding it is imported. Omitted, the package imports cleanly and the handler is absent from the registry — the same asymmetric failure `registrations.py` documents for job modules. See Risks.

One caveat worth writing down: if `foo.py` and a `foo/` directory both exist, the **package wins** silently. A shape change is a move, never a copy.

### 4. One `forbidden` contract, no layers contract

`subcategory-advisor-boundary` becomes `step-handler-boundary` with `source_modules = commerce_ops.step_handlers` and the same forbidden set and comment. Because a `forbidden` contract covers descendants, this holds for every handler ever added without an edit.

No `layers` contract accompanies it: most handlers will have no layers to order. Where one eventually adopts them, `import-linter` 2.13 takes optional layers (`layers = (infrastructure) / (application) / (domain)`) with a wildcard `containers` expression, which applies only where the directories exist. That is deferred to the change that introduces the first such handler rather than added speculatively for none.

### 5. Grouping mirrors the handler name, and stays a convention

`listing` in `step_handlers/listing/` is a real `Discipline` value (`shared/domain/discipline.py`), and the first segment of the registered name `listing.subcategory_advisor`. Grouping by discipline therefore makes the import path read as the stored name — a property worth having.

It is **not** enforced, deliberately. The registry keys on a free string; nothing validates that a handler's location, its name's first segment, and the discipline of the steps naming it agree. Enforcing that would couple a code path to a domain enum and make a file move a data migration, which is precisely the coupling Decision 3 exists to avoid. If drift ever becomes real, it is a separate change.

## Risks / Trade-offs

- **A handler package forgets to re-export its registration; it silently vanishes from `HANDLERS`.** → Two runtime mechanisms already catch it, neither added here: activation refuses a step naming a handler nothing registers, and the pass logs and skips. Both are late — they fire at an admin's next write or a launch's next pass — so this change's tasks add the earlier guard: a registration assertion in `tests/unit/test_registrations_across_processes.py`, which already drives each composition root in a fresh interpreter, naming `listing.subcategory_advisor` specifically rather than asserting non-emptiness. The current per-handler layout never needed it, because the handler *was* the package that `registrations.py` imported.

  **`check_step_handlers` is deliberately absent from that list.** It looks like the earliest guard and is not one: it imports `HANDLERS` from `launch.application` and never imports `commerce_ops.registrations` (`check_step_handlers.py:45-49`), so in the process the container starts (`Dockerfile:61`) the registry is empty unconditionally and the report cannot tell a forgotten re-export from a correct one. That is a **pre-existing defect this change does not fix** — it is latent only because no automated step is `active` today, and it belongs to its own change per `AGENTS.md`'s scope-control rule. Relying on it here would have counted a broken mitigation as a working one.
- **`step_handlers/` becomes a drawer for anything automation-adjacent.** → The boundary contract is the guard: it may reach `launch.application` and nothing else, so code that wants more cannot live there. A handler that grows a real model and invariants is a bounded context wearing a handler's clothes, and the signal to promote it — which is README's original rule, now applied to the right unit.
- **The move is invisible in behavior, so a mistake in it is invisible too.** → It is verified by the checks that already exist: `lint-imports` proves the new contract holds, the `tests/agents` tier proves the graph still loads at its new path, and `tests/unit/launch/**` — which names the handler *string*, never its location — proves the name did not move with the file.
- **Two levels of nesting sits against a stated convention.** → Accepted, and amended in README rather than left as a silent exception (Decision 2). The cost is that the convention now has a carve-out to read alongside it.

## Migration Plan

A pure source move in one pull request. No database change (`playbook_steps.handler` is `NULL` on every row today, and the name it would hold is unchanged either way), no Alembic revision, no runtime variable, no deploy-workflow change, no image change.

Deploy is the ordinary path: branch, PR, merge to `main`. Rollback is a revert — nothing outside the repository has to be undone, which is the property that makes the move cheap to attempt.

Sequencing within the PR matters in one respect only: `.importlinter` and `registrations.py` must change in the same commit as the move, or `lint-imports` and the pre-commit test tier fail on an intermediate state.
