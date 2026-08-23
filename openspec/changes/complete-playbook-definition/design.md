# Design — complete-playbook-definition

## Context

See `proposal.md` — Why. Current state that shapes the approach:

- The playbook domain model lives in `src/commerce_ops/products/domain/launch_playbook.py` and is already rich: gates with opening modes, the full `StepDefinition` attribute set, all four timing-anchor forms, and all-faults load-time coherence. Slice 2 completes it rather than rebuilding it.
- `products` is the leftover name from before slice 1 split `catalog` out; the module now holds only playbook and launch-position code plus the pending-cadence no-op. The domain map has no `products` context — this module *is* `launch`.
- `playbook_v1.yaml` carries the eight gates and **zero steps** (step authoring is a deliberate follow-up), so no authored data migrates: the `track` → `discipline` key rename and the lesson-cannot-block invariant break nothing.
- `shared/domain` has identity VOs and `LifecycleStage`, but no `Discipline` — the settled naming decision (2026-08-23) requires the shared enum and the rename to land in one step.

## Goals / Non-Goals

**Goals:**

- Finish the playbook *definition* so slice 3 can build the `Launch` aggregate against a stable vocabulary: gate conditions, step outcomes, one discipline name.
- Keep the marketplace deferral clean: a `MetricCondition` is the same authored object whether satisfied by attestation (now) or observation (slice 7).
- Land the module rename while the module's import surface is small: the `commerce_ops.products` references are module-internal (`application/__init__.py`, `playbook_loader.py`, `launch_position_repository.py`) plus the `_SHIPPED_PACKAGE` string constant in `playbook_loader.py` — the app-level wiring files reference the module only through those imports' re-exports.

**Non-Goals:**

- No `Launch` aggregate, no attestation or approval recording, no outcome persistence (slice 3).
- No metric registry and no validation of a `MetricId` against one (slice 7); no `Cadence`/`Severity`/`Verdict` move into `shared` — those migrate when monitoring needs them.
- No authoring of the ~100+ step definitions (a follow-up data change).
- No HTTP/Slack delivery of the undecided-rule-policy report — it ships as a public application use case; a driving adapter or Omni wires it up when a consumer exists.

## Decisions

**1. `StepObligation` is derived, `MetricCondition` is authored.**
Steps already declare their gate and a `blocking` flag; authoring obligation lists on gates as well would state one fact in two places that can disagree. So `Gate` gains only `metric_conditions: tuple[MetricCondition, ...]`, and `LaunchPlaybook.conditions_for_gate(gate_id)` returns the union: one `StepObligation(step_id)` per blocking step at that gate plus the gate's authored metric conditions. `GateCondition = StepObligation | MetricCondition` is a union type alias, mirroring `TimingAnchor`. *Alternative rejected*: authored obligation lists with a coherence check that they match the blocking steps — more machinery to enforce what derivation gives for free.

**2. `MetricCondition = (MetricId, threshold description)` — the threshold is prose for now.**
No registry exists to type thresholds against, and until slice 7 a human attests the condition, so a human-readable description ("60–80 fulfillable units, excluding Vine") is the entire contract. `MetricId` becomes a shared identity VO (opaque, unresolved) so launch and monitoring speak the same reference type from day one. When the registry arrives, the condition's satisfaction *source* changes, not its shape. *Alternative rejected*: a structured threshold (operator, value, unit) — invents a schema slice 7 owns, before its owner exists.

**3. `Discipline` lives in `shared/domain` with exactly today's twelve members.**
The map's shared-kernel sketch lists `Discipline`; monitoring's extra disciplines (`sales`, `health`) are added as members when slice 7 needs them — the enum's closure is deliberately weak ("a thirteenth discipline costs one member"). The launch-playbook spec stops restating the value set and defers to the shared vocabulary. The rename is total in one commit: enum name, `StepDefinition.discipline` field, loader key `discipline:`, YAML comment shape, spec language — `Track` does not survive anywhere. *Alternative rejected*: a 14-member union enum now — invents monitoring's vocabulary before monitoring exists.

**4. `StepOutcome` is definition-side vocabulary, shipped now without a runtime consumer.**
It lives next to `Hazard` because its one rule is hazard-coupled: `permissible_terminal_outcomes(hazard)` answers "for a `prohibited-tactic`, only `Refused`; otherwise `Satisfied` yes, `Refused` no". Slice 3 consumes the vocabulary and enforces transitions; putting it there instead would let the `Launch` aggregate define what a playbook concept means. `Blocked`/`NotApplicable` are small frozen dataclasses carrying a required non-empty reason; the reasonless states are singletons — a union type, matching how `LifecycleStage` and `TimingAnchor` are already modeled.

**5. The undecided-rule-policy report is a pure query, exposed on `application/__init__`.**
`report_undecided_rule_policies()` loads the playbook via the existing loader and returns frozen rows (identifier, gate, discipline, execution mode). No delivery channel in this change — the v1 playbook has zero steps, so the report is empty until step authoring begins, which is exactly when its consumer (the authoring workflow) appears. Public-surface placement follows the Omni rule: if Omni later answers "which steps are undecided?", this use case is its tool.

**6. Module rename `products` → `launch` as a mechanical first commit.**
`git mv src/commerce_ops/products src/commerce_ops/launch` (and the `tests/unit/products`, `tests/integration/products` mirrors), then update every `commerce_ops.products` reference a repo-wide grep finds — the module-internal imports, the `_SHIPPED_PACKAGE` string constant in `playbook_loader.py`, test imports, and any import-linter contract naming `products`. Done *before* the behavioral work so every later diff reads against the final module name, and history stays followable via rename detection. `v1` YAML stays in place under the renamed module; `playbook_v1.yaml` is updated in place (new `discipline` shape, three gates' metric conditions) rather than versioned to v2 — no real launch has been started against v1, and versioning discipline gets teeth in slice 3 when a `Launch` records the version it runs under.

**7. Metric conditions for the three gates are authored data, not spec.**
The spec fixes the *mechanism* (gates may author metric conditions); which gate carries which condition is playbook data, like every other authored attribute. `stock-ready`, `phase-one-complete`, and `graduated` get their map-named conditions in `playbook_v1.yaml`.

## Risks / Trade-offs

- [Rename churn: stale `commerce_ops.products` references in strings, docs, alembic, or config] → grep the whole repo (not just imports) for `products` after the move; the pre-commit suite plus import-linter catch the code paths, a repo-wide search catches prose and wiring.
- [`StepOutcome` ships unused and could drift from slice 3's needs] → its shape is copied from the domain map verbatim and the map is the steering document; slice 3 revises it through a spec delta if reality disagrees, which is cheaper than slice 3 inventing it under aggregate pressure.
- [Prose thresholds invite untestable conditions] → acceptable by construction: until slice 7 the judge is a human attester, and the load-time non-empty check is the only enforceable rule; the registry later gives thresholds structure where data exists.
- [Editing v1 in place weakens versioning discipline] → bounded: no launch-position record can yet name a playbook version it started under (that field arrives with slice 3's aggregate work); recorded here as the explicit cut-off — from slice 3 on, definition changes version.

## Migration Plan

Single branch, reviewable commits in this order: (1) module rename, mechanical; (2) `shared` vocabulary additions; (3) `Track`→`Discipline` migration; (4) gate conditions + `StepOutcome` + lesson invariant; (5) undecided-rule-policy use case; (6) YAML authoring of the three gates' metric conditions. No data migration and no deploy steps beyond the normal pipeline; rollback is reverting the branch.

## Open Questions

None — the deferred items (step authoring, delivery channel for the report, monitoring's disciplines, structured thresholds) are sequenced to later slices by the domain map, not left ambiguous here.
