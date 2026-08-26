## Context

See proposal.md — Why. What matters for the approach is what already exists and what shape it forces.

`HANDLERS` (`launch/application/handler_registry.py`) is a name→callable registry with `register`, `resolve`, `names` and container semantics, and it is empty. `Provenance` already admits source `automated`. `record_step_outcome` already restricts terminal outcomes by hazard. `is_projectable` already refuses to project `automated` steps to ClickUp. `check_step_handlers.py` already reports, advisorily, every `active` automated step whose handler this deployment does not register. Nothing invokes a handler.

Three existing constraints shape everything below:

- **`.importlinter`'s `products-infrastructure-boundary`** forbids `launch` importing catalog's store. The advisor needs the catalog product's name and marketplace, so that read must be injected at `worker.py`, exactly as `clickup_sync_job.read_product` and `read_people` already are.
- **`get_slack_app(identity)` is `lru_cache`d and built lazily**, never at import, because the PR-validation gate imports `commerce_ops.main` and runs its lifespan with the Slack secrets absent. Any new listener must respect that.
- **`slack_entry.py` owns the only `product_agent` route** (`/product_agent/slack/events`) and registers its listeners *inside* its own `lru_cache`d handler factory. There is currently no way for a second module to contribute a listener to that app.

## Goals / Non-Goals

**Goals:**

- One invocation path, on recurring work, reusing the `register_scheduled` idiom rather than inventing a second scheduling mechanism.
- A handler contract narrow enough that a handler cannot misattribute its own work, and pure enough that a handler needs no injection of its own.
- A pending result that survives a failed delivery, a double-click, and a restart.
- The advisor testable without a live model call, per the project's LangGraph testing strategy.

**Non-Goals:**

- A general "agent runs a step" framework. One contract, one handler, no plugin discovery.
- Any change to how outcomes are recorded. Everything lands through the existing `record_step_outcome`.
- Retrying a failed handler within a pass. The next pass is the retry.

## Decisions

### The invoker is a scheduled job module, not an event subscriber

A new `launch/infrastructure/driving/automation_pass.py` declaring `TASK_NAME`, a schedule and a tolerance through `@register_scheduled`, added to `registrations.py`'s one list.

**Why:** a handler may legitimately report that a step is not resolved yet, so something must ask again; event-driven invocation (on `StepSatisfied`, on gate advance) fires once and never revisits. It is also the shape three existing jobs already keep, and `scheduled-jobs` requires schedule and tolerance to be declared in one place.

**Values:** `*/15 * * * *`, tolerance 6 hours — matching `clickup_sync_job`'s tolerance reasoning (comfortably longer than the worker's own liveness tolerance, so an absent worker becomes visible before the work it failed to run does). Fifteen minutes rather than ten because each pass may cost a model call per unresolved automated step, where the ClickUp pass costs two cheap reads.

**Alternative rejected:** invoking on demand from an admin control. Useful later for debugging, but it makes the demo prove the button rather than the runtime, and a time-dependent handler would never fire.

### The ClickUp inward loop must exclude by kind, not only by status

**Verified in source, and it defeats the change's own migration.** `clickup_sync.py:443` guards the *outward* projection with `is_projectable`, which is kind-aware. The *inward* reconciliation at `clickup_sync.py:561` builds `defined = {step.identifier for step in playbook.served_steps}` — and `served_steps` filters on `status is ACTIVE` only. A step flipped to `automated` stays `active`, so it stays in `defined`, keeps its mapping, and a person closing its orphaned task records `Satisfied` with source `clickup`. That is terminal for hazard `none`, so the pass's invocation predicate then excludes the step permanently, on every in-flight launch. Task 9.2 — "close the orphaned task by hand" — would have been the instruction that killed the automation.

Two remedies were available:

| Remedy | Verdict |
|---|---|
| Remove the mapping during migration, before the flip | Contained, but leaves the next kind-flip to rediscover the trap |
| **Generalise `launch-clickup-sync`'s "leaves the loop" rule to cover kind** | **Chosen** |

The requirement's own closing sentence argues for the general form: *"a rule that keyed on retirement alone would leave the other two undefined."* A rule that keys on status alone leaves this one undefined in exactly the same way. The delta widens "a step that is not `active`" to "a step the loop no longer projects", keeping every existing scenario and adding two for the kind case — one per direction.

### A handler receives a context object and returns a resolution; it never sees a repository

```
    StepContext:     step: StepDefinition
                     launch: <read-only view — progress, launch_date, gate>
                     product: <catalog product, resolved by the pass>
                     as_of:  datetime

    StepResolution:  outcome: StepOutcomeValue
                     result:  str          # what a person will read
```

**A handler says "not yet" with a non-terminal outcome, and terminality decides whether a result is held.** An earlier draft added a separate "declination" return value for this. Review found it did not close the hazard it was added for: nothing stopped a handler returning `InProgress` as an ordinary resolution, which on a `needs_confirmation` step would be held and delivered as "please accept: InProgress" — a proposal with nothing in it to agree with, suppressing re-invocation until someone clicked. The declination gave handlers a better door without closing the worse one.

So the rule moved to where the hazard actually is. Only a **terminal** proposal is held for a decision; a non-terminal one is recorded directly whatever the confirmation flag says, because there is nothing for a person to accept. That closes the trap, drops a concept rather than adding one, and is strictly more expressive than the declination was: a handler that has established a real blocker records `Blocked` with its reason on the launch's own record, where a declination would have left the step unresolved with the reason only in a log.

The system checks a terminal proposal against the step's hazard **before** storing or recording it, and treats an impermissible one as a handler fault. Deferring that to `record_step_outcome` would mean a pending result that fails on every press of accept, forever, with no path to settlement.

The pass — not the handler — resolves the catalog product through the injected reader and puts it in the context. **Why:** it keeps every handler free of injection, so a handler is a function of its context and nothing else, which is what makes it testable without a database. It also means the `.importlinter` boundary is crossed in exactly one place instead of once per handler.

The handler returning `result` as plain text rather than a structure is deliberate: its two consumers are a Slack message and the `evidence` column, both of which want text, and a structure would have to be rendered for each anyway.

**Why the handler cannot supply provenance:** `Provenance` requires a source from a closed set, and a handler that could name `attestation` could record its own output as a human's. The pass constructs it. This is a rule the spec states and the contract enforces by simply not accepting one.

### Pending results are their own table, keyed by launch and step

`automated_step_results`: `product_id`, `step_id`, `handler`, `proposed_outcome`, `result_text`, `produced_at`, `delivered_at` (nullable), `state` (`pending` / `accepted` / `rejected` / `voided`), `decided_by` (nullable), `decided_at` (nullable).

**`voided` is a fourth state, not a flavour of `rejected`.** A result is voided when a decision arrives for a step the served playbook no longer defines. Folding it into `rejected` would misrecord a refused decision as that person's rejection, and — because the cool-off keys on "most recent settled result was rejected" — would park the step for 24 hours after it returned to the served set. Only `rejected` counts as a rejection for the cool-off.

- **A partial unique index on `(product_id, step_id) WHERE state = 'pending'`** is what makes "one pending result per step" true under concurrency rather than only in the read-then-write path. Two overlapping passes cannot both insert.
- **Settled rows are kept, never deleted** — the same retire-never-delete discipline `playbook_steps` follows. What a manager accepted and when is the record of a compliance-adjacent decision.
- Lives in `launch/infrastructure/driven/`, with a repository shaped like `ClickUpMappingRepository`.

**Alternative rejected:** storing the pending result on the launch aggregate. It is not launch state — it is a proposal about launch state, and folding it in would put "awaiting a person's decision" inside an aggregate whose invariants have nothing to say about it.

### Delivery is retried by the next pass, not by a second job

Each pass begins by delivering every pending result whose `delivered_at` is null, then resolves handlers. A successful post stamps `delivered_at`.

**Why:** the spec requires that a failed delivery neither discards the pending result nor records an outcome, and that it remain deliverable. A nullable timestamp plus the pass already running every 15 minutes gives that for free. A dedicated delivery job would be a second schedule to reason about for no additional guarantee.

### A cool-off after rejection, to bound the cost of disagreement

A rejected step becomes invocable again, but not immediately: the pass skips a step whose most recent settled result was rejected within the cool-off. 24 hours, as a module constant.

**Why:** without it, a manager rejecting one recommendation buys a fresh model call every 15 minutes, forever, and a stream of Slack messages proposing much the same thing.

**A constant, not configuration.** A configured value would owe the four obligations `AGENTS.md` places on every runtime variable — a settings declaration, a `deploy.yml` secret read, the drift-check mirror, a literal-name read — and would falsify the proposal's "no new configuration". There is no per-deployment answer to how long a person's disagreement should stand, so there is nothing to configure.

**This is a specified behaviour, not a design-only one.** An earlier draft left the cool-off in this document while a spec scenario said a rejected step is invoked again on a later pass, which the cool-off falsifies for the next pass. The rule now lives in `launch-step-automation` ("A rejected step is not re-proposed immediately"), with scenarios for both the skip and the resumption, and the invocation predicate names it.

### The Slack listener needs a contribution seam in `slack_app.py`

The confirmation buttons arrive as `block_actions` on the `product_agent` app, whose only route and whose listener registration both live inside `slack_entry.py`'s cached factory. Three ways to attach a listener:

| Option | Verdict |
|---|---|
| Register the listener inside `slack_entry`'s factory | Smallest diff, but puts `launch-step-automation`'s listener inside `launch-entry`'s adapter, where nobody will look for it |
| A second Slack app identity for confirmations | Needs a new token, a new signing secret and a new route — and the proposal commits to no new configuration |
| **A listener-contribution seam in `shared/.../slack_app.py`** | **Chosen** |

`register_slack_app` gains a companion — modules contribute listener-attaching callbacks under an app identity, and `get_slack_app` applies every contributed callback when it lazily builds that app. Laziness is preserved (nothing runs at import), each module keeps its own listeners in its own file, and `slack_entry`'s existing registration becomes one contributor rather than the owner.

**Cost, stated plainly:** this touches the shared kernel for one capability's benefit. It is justified because the alternative is a module boundary violated by convenience, and because the seam is the one `slack_app.py`'s own docstring already implies ("each module registers its own Slack app and owns its own credentials") but does not yet provide for two modules on one app.

`will_reply` already returns `True` unconditionally in `slack_entry`, so a `block_actions` request is treated as replying and the credential gate is satisfied without change.

**Why `slack-trigger` gets no delta.** The seam is additive: an identity with no contributed callbacks builds exactly as it does today, so every requirement `slack-trigger` records — the credential gate, the URL-verification challenge, acknowledgement timing, unhandled events still acknowledged — is unchanged in both statement and behaviour. Writing a delta would mean inventing a requirement to describe a refactor, which is what the artifact rules forbid. What the change owes instead is proof, and that is task 5.4: the existing `omni_agent` and `access` identities build and behave identically.

**Considered: splitting the seam into its own change.** It has an independent justification and an independent blast radius, and shipping it first with its own regression check would shrink this change by a module boundary rather than by a feature. Kept here because the seam has no observable behaviour of its own to review — its whole content is "this refactor changed nothing" — so a separate change would be a separate review of the same four tasks, gating a demo on two merges instead of one. If review disagrees, this is the piece to lift out, and lifting it out costs only re-sequencing.

### Handlers are registered from `registrations.py`, in both composition roots

`register_step_handler` registers a handler when its module is imported. Which processes import it is therefore load-bearing in a way that is easy to miss: `playbook-authoring` validates activation against the registry **in the process serving the admin surface**, while the pass needs the same handler registered **in the worker**. A handler imported only where the pass runs produces a deploy where `check_step_handlers` reports the handler registered, and the admin's activation is refused as naming an unknown handler.

So handler modules join job modules in `registrations.py` — the one list both roots already import, sitting outside `.importlinter`'s containers for exactly this reason — and a verification mirrors the existing job-registry divergence guard: both roots, in a fresh interpreter, resolve the same handler names.

**This is not hypothetical.** `registrations.py`'s own docstring records the same failure for jobs: "a root that imports a different set sees a different registry. The failure is silent and asymmetric."

### The deciding authority is roster membership, not admin authority

Accepting a compliance-adjacent recommendation requires a person the roster knows and holds active — not an admin. `access-scope` maintains a real distinction between membership and write authority, so this is a choice rather than a default, and it goes this way because the decision is launch work: the people who do a launch's steps are the people who should judge a proposal about one. Admin authority governs who edits the playbook and the roster, which is a different question from who accepts a result within a launch.

If this proves wrong, the change to make is narrow — the decision path already resolves the identity through the roster, so tightening it to admins is one predicate.

### The advisor is a LangGraph graph shaped like `omni_agent`'s

A single-node `StateGraph` over `ChatOpenAI`, matching `omni_agent/application/graph.py` — including its split between `build_graph(model)` (injectable) and `build_production_graph()`. That split is what lets `tests/agents/` drive it with a stubbed model, which is the project's stated LangGraph testing strategy.

The advisor is registered under a handler name via `register_step_handler`, so registration happens where it is defined, and `check_step_handlers` reports it at startup like any other.

**Not chosen:** structured output / tool-calling for the recommendation. The spec requires no tool invocation, the result is consumed as text by both consumers, and a schema would add a failure mode (malformed structured output) between the model and a person who is going to read the text anyway.

## Risks / Trade-offs

- **A hallucinated browse node reaching a launch as fact** → `needs_confirmation` is true, so nothing is recorded without a person; the advisor spec additionally requires it to say when it cannot support a choice rather than name one anyway.
- **Model cost growing with active launches** → a pending result suppresses re-invocation, and a rejection triggers the cool-off; the only steps costing a call every pass are automated steps with no pending result and no recent rejection. **That set is not bounded**: a product whose category the advisor can never support proposes a non-terminal outcome every pass, forever, at roughly ninety-six calls a day. Accepted rather than mitigated — a re-ask may legitimately succeed on a later run given model nondeterminism, the design already treats a call per unresolved step per pass as the norm, and inventing a second cool-off shape for a handler that keeps saying "not yet" is a feature this change did not propose. What is not accepted is a risk register claiming a bound it does not have, which is why this sentence is here.
- **Flipping `lp.listing.007` to `automated` orphans its existing ClickUp task** → the step leaves `is_projectable`, and the sync pass does not tear down a task for a step it no longer projects, so someone closes it by hand. That hand-closure is safe only because of the inward-loop fix above; without it, it would have recorded a completion.
- **Touching `slack_app.py` affects `omni_agent`'s app too** → the seam is additive; an identity with no contributed callbacks builds exactly as it does today, which is what the existing `omni_agent` and `access` apps will exercise.
- **A settled result whose recorded outcome failed to persist** → delivery and recording are separate writes. The decision handler records the outcome and settles the pending row in one transaction, so a failure leaves the result pending and re-decidable rather than settled-but-unrecorded.
- **Two passes overlapping under a slow model call** → the partial unique index makes a duplicate pending row impossible; the losing insert is caught and that step is left for the next pass.

## Migration Plan

1. One Alembic revision creating `automated_step_results` with its partial unique index. No data migration; no existing row is rewritten.
2. Deploy — including the inward-loop fix, which must be live **before** any step is flipped to `automated`. `check_step_handlers` now reports one registered handler instead of zero, and no step changes status: the seeded automated steps stay `in-development`, which the modified `launch-playbook` requirement pins with its own scenario.
3. **Activation is a separate, manual, post-deploy act**: an admin edits `lp.listing.007` through the playbook admin surface — `kind` to `automated`, an `automation_brief`, the handler name, `needs_confirmation` true — and only then activates it. Nothing in the deploy does this.
4. **Rollback**: revert the revision, which drops the table and with it any *undecided* pending results. Recorded outcomes are unaffected — they live on the launch, not here. An activated `lp.listing.007` would then name an unregistered handler, which `check_step_handlers` reports advisorily and the pass skips, so a rollback degrades to "that step stops resolving" rather than to an outage.

## Open Questions

- Which model the advisor should use. `omni_agent` uses `gpt-4o-mini`; a sub-category recommendation may want more capability. Answerable after seeing real output, and it changes a constant rather than the specs, the approach, or the task breakdown.
- Whether the cool-off should be per-step-configurable rather than one default. Deferred until there is a second handler to disagree about it.
