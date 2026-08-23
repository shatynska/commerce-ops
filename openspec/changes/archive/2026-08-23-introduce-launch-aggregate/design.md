## Context

See proposal.md — Why. What exists on entry:

- `launch/domain/launch_playbook.py` (slice 2) already defines the entire definition-side vocabulary the aggregate consumes: `Gate`, `StepDefinition`, `GateCondition = StepObligation | MetricCondition`, the `StepOutcome` union, `permissible_terminal_outcomes(hazard)`, `TimingAnchor.resolve(launch_date)`, and `LaunchPlaybook.conditions_for_gate()`. Slice 3 adds no new playbook rules; it runs a product against them.
- `launch-instance` persistence is a single `launch_positions` row per product with an explicitly unvalidated `update_current_gate` path — a stopgap the spec itself flags as ending here.
- `catalog` established two precedents this change follows: an aggregate whose commands return event objects (`Product.change_stage` → `StageChanged`, no dispatch infrastructure), and a public application surface (`change_stage` use case) other modules may call.
- import-linter allows `launch.application → catalog.application` and forbids `launch.domain` from reaching any other module; `shared.domain` (including `Posture`) is open to it. (Implementation note, recorded when the wiring landed: the forbidden contracts follow *transitive* chains, so calling catalog's public surface — which internally uses its own domain — tripped `launch.application ↛ catalog.domain`. The contract now exempts catalog's internal `application → domain` edges from that chain, keeping the public surface opaque while still forbidding direct imports of `catalog.domain`. The same exemption will be needed wherever a module calls another's public surface, e.g. Omni in slice 6. `StageTransitionError` joined catalog's public exports for the same reason: `change_stage` is public, so the rejection it raises must be catchable without reaching into `catalog.domain`.)
- Constraint from the request driving this slice: the domain layer must read as the business rules themselves — showable to managers — so every invariant lives in `launch/domain`, not in use cases or the repository.

## Goals / Non-Goals

**Goals:**

- One `Launch` aggregate holding every launch-run invariant in one place (the map's recorded lean: one aggregate per run, per-gate splitting only as a documented escape hatch if size actually hurts).
- Deterministic, I/O-free gate evaluation over the pinned playbook; no LangGraph anywhere in the engine.
- The event vocabulary of the domain map realized as returned domain objects.

**Non-Goals:**

- No ClickUp mapping, webhook intake, or reconciliation (slice 4) — `clickup` appears only as a provenance source value.
- No Slack or HTTP driving adapters, no briefing/AttentionItems (slice 5); events are returned to callers, not routed anywhere.
- No live metric evaluation (slice 7); metric conditions are satisfied by attestation only.
- No catalog stage stamps other than graduation: `Development → Launching` and phase advances remain manual, human-confirmed catalog operations.
- No self-firing gates: nothing in this slice schedules or triggers evaluation.

## Decisions

**1. The aggregate subsumes the launch-position record.** The `launch_positions` row becomes the spine of the persisted `Launch`; step progress, approvals, and attestations become child tables keyed by the launch's product id. Alternative — a new `Launch` store alongside the old record — rejected: two owners for "current gate" is exactly the split-brain the map's state-ownership rule forbids.

**2. The playbook enters through method parameters, never through the aggregate's state.** `Launch` stores only `playbook_version`; commands that need definitions (`record_step_outcome`, `advance_gate`, due-date and at-risk evaluation) take the loaded `LaunchPlaybook` as an argument, and the application layer is responsible for loading the version the launch pinned. Alternative — embedding the playbook in the aggregate — rejected: it would drag YAML-loading concerns toward the domain and duplicate the definition per launch. A guard: the aggregate rejects a playbook whose `version` differs from its pinned one, so a caller cannot evaluate a launch against the wrong definition.

**3. Events are returned, not collected.** Each command returns the tuple of event objects it produced (e.g. recording the last blocking step of an automatic gate returns `(StepSatisfied,)` — advancing is a separate command returning `(GateOpened,)`; approving and advancing `graduated` returns `(GateOpened, LaunchGraduated)`). This extends catalog's `StageChanged` precedent instead of introducing a pending-events list plus dispatch machinery no consumer needs yet (briefing arrives in slice 5). Alternative — the classic `pending_events` collection — deferred until a real dispatcher exists.

**4. Advancing is an explicit command; "automatic" describes the approval requirement, not self-firing.** `advance_gate(playbook)` evaluates the current gate's conditions and either advances (`GateOpened`) or raises with a `GateBlocked` event naming every unsatisfied condition. An `automatic` gate needs no approval; a `requires-confirmation` gate needs a recorded `GateApproval`. Who calls `advance_gate` and when is a driving-adapter concern (slices 4–5). Alternative — auto-advancing inside `record_step_outcome` — rejected: it hides a gate transition inside an unrelated command, and confirmation gates could never behave symmetrically.

**5. Graduation posture is chosen by the approver, carried on the approval.** A `GateApproval`'s decision is binary — approving or rejecting — and only an approving decision satisfies a confirmation gate; a rejecting one is recorded but keeps the gate closed. `GateApproval` gains an optional `posture: Posture | None` (from `shared.domain`); the domain requires it exactly when the approved gate is `graduated` and rejects it as meaningless elsewhere. Rationale: catalog's rule "the system never self-stamps a posture" makes any default posture illegal — the human approving graduation is the human confirming the stage. The graduation use case in `launch.application` then calls `catalog.application.change_stage` with `SteadyState(posture)` and the approver as confirmer — a legal import per the boundary contracts. Alternative — defaulting to `Optimize` — rejected as a silent system-chosen posture.

**6. At-risk evaluation is a pure function of the aggregate as of a given date.** `date_at_risk(playbook, as_of)` reports `LaunchDateAtRisk` when any blocking step's resolved due period has fully passed without the step reaching a permitted terminal outcome. The clock never lives in the domain: `as_of` is always a parameter. Steps with recurring anchors resolve to no due period and therefore never contribute — consistent with `RecurringAnchor.resolve` returning `None`.

**7. Persistence: one repository, whole-aggregate rehydration, additive migration.** `LaunchRepository` (evolving the existing `LaunchPositionRepository`) loads and saves the full aggregate; `update_current_gate` disappears from its surface. New tables: `launch_step_progress` (one row per recorded step: outcome kind, reason, provenance source/who/when/evidence), `launch_gate_approvals`, `launch_metric_attestations` — all keyed by `launch_positions.product_id` with cascade. The migration is additive; existing rows carry over untouched. Optimistic-concurrency/versioning is deliberately left out until a second writer exists (the ClickUp webhook, slice 4).

**8. Application layer follows catalog's shape.** Plain use-case functions over ports (`start_launch`, `record_step_outcome`, `record_metric_attestation`, `approve_gate`, `advance_gate`, `move_launch_date`, plus a read model returning the launch with due periods and at-risk status), exported through `application/__init__.py` as the module's only public surface.

## Risks / Trade-offs

- [One aggregate spans ~100–150 step rows per product] → accepted by the map's recorded lean; the per-gate split remains the documented escape hatch, and whole-aggregate loads stay cheap at MVP scale (a handful of concurrent launches).
- [No optimistic locking: two concurrent commands could interleave] → single-writer reality in this slice (application use cases invoked by one operator); revisit in slice 4 when the webhook becomes a second writer — noted there rather than speculatively built here.
- [Attestation-satisfied metric conditions may later disagree with live data (slice 7)] → by design: the attestation records who claimed what with evidence; when monitoring arrives the satisfaction path changes, the model does not (the map's marketplace-deferral rule).
- [Graduation performs a cross-module write (launch → catalog) in one use case without a transaction spanning both] → ordering mitigates: advance and persist the launch first, then stamp the catalog stage; a failed stamp surfaces as an error naming the manual catalog fix, and the quarterly-review loop catches drift. A saga is deliberately out of scope pre-MVP.
- [`GateApproval.posture` is meaningful only for `graduated`] → a small modeling wart accepted to keep one approval concept; the domain rejects a posture on any other gate, so it cannot leak.

## Migration Plan

1. Alembic migration adds the three child tables; no change to `launch_positions` columns; existing rows remain valid (a launch with no recorded progress).
2. `LaunchPositionRepository`'s `update_current_gate` callers: none exist in application code today (verified — only tests exercise it), so the method is removed with its tests replaced by aggregate-driven ones.
3. Rollback: drop the three tables; `launch_positions` is untouched.

## Open Questions

None — the two decisions that could have moved the specs (at-risk rule, graduation wiring and posture) were settled with the user during exploration and are recorded above.
