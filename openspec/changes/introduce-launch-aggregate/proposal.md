## Why

The playbook definition is complete (slice 2, `complete-playbook-definition`), but nothing can run a launch against it: the runtime side is a bare launch-position record whose own spec admits its current gate "does not validate that the transition from the prior gate to the new one is one `launch-playbook` would permit", and no step outcome, attestation, or approval can be recorded at all. Slice 3 of `docs/domain-map.md` — the heart of the MVP — closes that gap with the `Launch` aggregate: the one place where gate evaluation, step outcomes, attestations, approvals, due dates, and launch events live as explicit, deterministic domain rules readable outside the codebase.

## What Changes

- Introduce the `Launch` aggregate root in `launch/domain`: product reference, pinned playbook version, movable launch date, current gate position, and per-step progress (`StepOutcome` plus completion provenance: source, who, when, evidence).
- Gate evaluation as domain behavior: gates advance monotonically and are never skipped; a gate opens only when every blocking condition (`StepObligation` and `MetricCondition`) is satisfied; a `requires-confirmation` gate additionally requires a recorded `GateApproval`; a `Refused` outcome never satisfies anything.
- Record `MetricAttestation`s — a human's evidenced satisfaction of a gate's `MetricCondition` — as the interim path until `monitoring` (slice 7) evaluates live data.
- Due dates derived from `LaunchDate + TimingAnchor`; moving the launch date re-resolves every anchor at once (`LaunchDateMoved`); a blocking, unresolved step past its due window puts the launch date at risk (`LaunchDateAtRisk`).
- Domain events returned by aggregate commands (following `catalog`'s `StageChanged` precedent — returned domain objects, no dispatch infrastructure): `LaunchStarted`, `StepSatisfied`, `StepRefused`, `GateOpened`, `GateBlocked`, `LaunchDateMoved`, `LaunchDateAtRisk`, `LaunchGraduated`.
- Application use cases as the slice's only driving surface: start a launch, record a step outcome, record a metric attestation, approve a gate, move the launch date. No new HTTP or Slack adapters (those arrive with slices 4–5).
- Graduation wiring: approving the `graduated` gate stamps the catalog product `SteadyState` through `catalog`'s existing public application surface, with the gate approver as the human confirmer.
- **BREAKING** (internal): the launch-position record is subsumed by the aggregate. Free-form current-gate updates are retired — the stored gate changes only through aggregate behavior. Persistence grows step progress, attestations, and approvals (schema migration).

## Capabilities

### New Capabilities

None — this change grows the existing `launch-instance` capability; no new spec directory is introduced.

### Modified Capabilities

- `launch-instance`: reshaped from "persist a position record" to "run a launch". The unvalidated current-gate-update requirement is replaced by gate-advance rules; new requirements cover step-outcome recording with provenance, metric attestations, gate approvals, due-date derivation and launch-date movement, at-risk detection, emitted events, and graduation stamping the catalog stage.

## Impact

- `src/commerce_ops/launch/domain/` — new `Launch` aggregate module (pure, I/O-free; consumes `LaunchPlaybook`, `GateCondition`, `StepOutcome`, `TimingAnchor`, `permissible_terminal_outcomes` already defined in `launch_playbook.py`).
- `src/commerce_ops/launch/application/` — new use cases; `application/__init__.py` public surface grows accordingly (import-linter contract unchanged in shape).
- `src/commerce_ops/launch/infrastructure/driven/` — `LaunchPositionRepository` becomes the aggregate's repository (rehydrate/persist whole `Launch`); new tables for step progress, attestations, approvals via an Alembic migration.
- `src/commerce_ops/catalog/application/` — consumed (not modified): graduation calls the existing stage-change use case.
- `docs/domain-map.md` — slice 3 marked realized; any divergence discovered during the change is folded back into the map per its living-document rule.
- Tests: new unit tiers under `tests/unit/launch/domain` and `tests/unit/launch/application`; integration tests for the reshaped repository under `tests/integration/launch`.
