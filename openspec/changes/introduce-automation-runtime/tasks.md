## 1. The pending-result store

- [ ] 1.1 Add an `AutomatedStepResult` model to `launch/infrastructure/driven/models.py`: `product_id`, `step_id`, `handler`, `proposed_outcome`, `result_text`, `produced_at`, `delivered_at` (nullable), `state` (`pending`/`accepted`/`rejected`/`voided` — `voided` is its own state, never a flavour of `rejected`), `decided_by` (nullable), `decided_at` (nullable)
- [ ] 1.2 Write the Alembic revision creating `automated_step_results`, including the partial unique index on `(product_id, step_id) WHERE state = 'pending'` — the index is the concurrency guarantee, not an optimisation
- [ ] 1.3 Verify the revision upgrades and downgrades cleanly against a live database, and that the partial index actually refuses a second pending row
- [ ] 1.4 Add `AutomatedResultRepository` in `launch/infrastructure/driven/`, shaped like `ClickUpMappingRepository`: read the pending result for a launch and step, insert one, list undelivered, stamp delivery, settle a result with its decider, void a result, and read the most recent **rejected** result for a launch and step (the cool-off's input — a voided row is not a rejection and must not trigger it)

## 2. The handler contract

- [ ] 2.1 Define `StepContext` and `StepResolution` in `launch/application/` as frozen dataclasses, per design.md — context carries the step, a launch view, the catalog product and `as_of`; a resolution carries an outcome and the produced text
- [ ] 2.2 Type `StepHandlerRegistry`'s callables against that contract, replacing `Callable[..., object]`, so a handler with the wrong shape fails type checking rather than at run time
- [ ] 2.3 Add the resolution use case in `launch/application/`: given a launch, a step and a context, resolve the registered handler and return its resolution — constructing the `Provenance` (source `automated`, handler as recorder, `as_of`, produced text as evidence) rather than accepting one
- [ ] 2.4 Make the use case refuse a resolution that attempts to carry its own provenance
- [ ] 2.5 Branch on terminality, not on the confirmation flag alone: a non-terminal outcome is recorded directly whatever that flag says, and only a terminal proposal is eligible to be held — this is what makes "please accept: InProgress" unconstructible
- [ ] 2.6 Check a terminal proposal against the step's hazard before storing or recording, treating an impermissible one as a handler fault reported with the launch, step, handler and offending outcome

## 3. Recording and the confirmation branch

- [ ] 3.1 Where the step's `needs_confirmation` is false, record the outcome immediately through the existing `record_step_outcome`
- [ ] 3.2 Where it is true **and the proposed outcome is terminal**, store a pending result instead and record nothing
- [ ] 3.3 Implement acceptance: record the proposed outcome with source `automated`, naming the accepting person as recorder and evidence naming both the handler and the produced text; settle the pending row — recording and settlement in one transaction, so a failed recording leaves the result decidable
- [ ] 3.4 Implement rejection: record `Blocked` whose reason names the rejecter and states that an automated result was rejected, source `automated` with the rejecter as recorder, and settle the pending row as rejected
- [ ] 3.5 Refuse a second decision on an already-settled result, leaving the first decision's recorded outcome standing
- [ ] 3.6 Refuse a decision from a Slack identity the roster does not know or holds inactive, recording nothing and leaving the result pending
- [ ] 3.7 Refuse a decision whose step the served playbook no longer defines: record nothing, void the pending result rather than leaving it standing, and tell the decider why

## 4. The scheduled pass

- [ ] 4.1 Create `launch/infrastructure/driving/automation_pass.py` with `TASK_NAME`, `AUTOMATION_SCHEDULE = "*/15 * * * *"` and `AUTOMATION_TOLERANCE = 6 hours`, registered via `@register_scheduled` — carrying the comment explaining both figures, as `clickup_sync_job` does
- [ ] 4.2 Walk non-graduated launches via `list_active()`; within each, select served steps whose kind is `automated`, whose recorded outcome is not terminal for their hazard, and which have no pending result
- [ ] 4.3 Apply the post-rejection cool-off: a module constant (24h, never configuration), skipping a step whose most recent rejection falls within the window and invoking it once the window has elapsed (a voided row is not a rejection)
- [ ] 4.4 Skip and report a step whose named handler is not registered; do not fail the pass
- [ ] 4.5 Catch a handler failure per step: record nothing, report the launch, step and handler, continue to the next step and the next launch
- [ ] 4.6 Deliver undelivered pending results at the start of each pass, stamping `delivered_at` only on success
- [ ] 4.6a Record a pass that completed its walk as a successful run, whatever individual handlers or deliveries did
- [ ] 4.7 Add the module to `registrations.py`'s `JOB_MODULES` — the one list both composition roots import
- [ ] 4.8 Inject the catalog product reader in `worker.py`, reusing `_read_catalog_product`, with the comment explaining why the boundary is crossed there

## 4a. The ClickUp inward loop leaves by kind, not only by status

- [ ] 4a.1 Change `reconcile_launch`'s `defined` set (`clickup_sync.py:561`) so a step the pass no longer projects is excluded inward as well as outward — status **and** kind, reusing `is_projectable` rather than inventing a second predicate that can drift from it
- [ ] 4a.2 Apply the same exclusion on the webhook path
- [ ] 4a.3 Keep the observation running for such a step, so a closure while it was out of the projection is never replayed as a transition later
- [ ] 4a.4 Verify the case that motivated this: an `active` step flipped to `automated`, its orphaned task closed by hand, records no outcome

## 5. The Slack listener seam

- [ ] 5.1 Add a listener-contribution mechanism to `shared/infrastructure/driving/slack_app.py`: modules contribute listener-attaching callbacks under an app identity, applied by `get_slack_app` when it lazily builds that app
- [ ] 5.2 Verify nothing runs at import — the PR-validation gate imports `commerce_ops.main` and runs its lifespan with the Slack secrets absent and must still succeed
- [ ] 5.3 Convert `slack_entry.py`'s existing listener registration into a contributor, changing no behavior
- [ ] 5.4 Confirm an identity with no contributed callbacks builds exactly as before (`omni_agent`, `access`)

## 6. Confirmation delivery and decision

- [ ] 6.1 Add `launch/infrastructure/driving/automation_confirmation.py`: post a pending result to `PRODUCT_AGENT_MONITORING_CHANNEL_ID` naming the product, the step, the proposed outcome and the produced text in full, with accept and reject actions
- [ ] 6.2 Make a delivery failure report and leave `delivered_at` null, discarding nothing and recording nothing
- [ ] 6.3 Register the `block_actions` listener through the seam from task 5.1, resolving the deciding Slack identity through the roster
- [ ] 6.4 Reply in Slack on every refused decision — unknown identity, inactive person, already settled, and a step the served playbook no longer defines — so the decider learns it was refused and why

## 7. The sub-category advisor

- [ ] 7.1 Create the agent module with `build_graph(model)` / `build_production_graph()` split, mirroring `omni_agent/application/graph.py`
- [ ] 7.2 Write the prompt so a supported recommendation names the node as a full path, the compliance fields and certifications it demands, and a rejected alternative with the reason
- [ ] 7.2a Where it cannot support a node choice, propose a non-terminal outcome carrying that as its reason — never the satisfying outcome with a disclaimer in the text, which would put a compliance step one unread paragraph from being accepted
- [ ] 7.3 Surface a model failure and a non-string response content as a failure, never as a recommendation
- [ ] 7.4 Register it under a handler name via `register_step_handler`, at its definition site, and import the module from `registrations.py` so both composition roots hold it — the API process validates activation against the registry, the worker runs the pass, and a handler registered in only one leaves them disagreeing
- [ ] 7.5 Assert the two negative properties nothing else forces: no tool or marketplace call during a recommendation, and no state carried between invocations
- [ ] 7.6 Confirm `check_step_handlers` reports one registered handler and still names no unresolvable step

## 8. Verification

- [ ] 8.1 `uv run pytest tests/unit tests/agents` green
- [ ] 8.2 `uv run pytest tests/integration` green against a live database (the migration, the partial index, the repository)
- [ ] 8.3 `uv run ruff check` and `uv run ruff format --check` clean
- [ ] 8.4 `uv run mypy` clean, including the newly typed handler contract
- [ ] 8.5 `import-linter` clean, with a contract added for the advisor's new module — a module absent from the contracts is layered vacuously — and confirming `launch` still names no catalog store and that the catalog read is injected at `worker.py`
- [ ] 8.6 Both composition roots register the same job set in a fresh interpreter (the existing registry-divergence guard)
- [ ] 8.6a Both composition roots resolve the same **handler** names in a fresh interpreter, mirroring 8.6 — the failure this guards is a deploy that passes every other check and then refuses the activation the migration depends on
- [ ] 8.7 `openspec validate introduce-automation-runtime --type change --strict` passes

## 9. Post-deploy (manual, not part of the deploy)

- [ ] 9.1 Through the playbook admin surface, edit `lp.listing.007` to `kind: automated` with an automation brief, the handler name and `needs_confirmation` true, then activate it
- [ ] 9.2 Close its orphaned ClickUp task by hand — it leaves `is_projectable`, and the sync pass does not tear down a task for a step it no longer projects. Safe only once 4a is deployed: before that fix, this closure records a `clickup`-sourced `Satisfied`, terminally suppressing the automation this activation exists to enable
- [ ] 9.3 Confirm end to end: the pass produces a recommendation, it reaches Slack, accepting it records `Satisfied` against the launch with `automated` provenance naming the accepter
