# Complete the playbook definition

## Why

The domain map's slice 2 closes the gap between the shipped `launch-playbook` capability and the model the map records: gates today order only steps, but half the real launch gates (`stock-ready`, `phase-one-complete`, `graduated`) are threshold checks, not task checklists — the definition cannot yet express them. Two deferred decisions are also armed for "the next change that touches the playbook": the settled `Track` → `Discipline` migration (2026-08-23) and the lesson-steps-cannot-block invariant. Completing the definition now is what lets slice 3 build the `Launch` aggregate against a finished vocabulary.

## What Changes

- **`GateCondition` split**: a gate's opening conditions become explicit as `GateCondition = StepObligation(step_id) | MetricCondition(metric_id, threshold)`. `StepObligation`s are **derived** from the blocking steps attached to the gate (one source of truth, no duplication); `MetricCondition`s are **authored** on the gate. Until marketplace access lands, a `MetricCondition` is satisfied by human attestation (recorded in slice 3); the definition does not change when live data arrives.
- The v1 playbook authors the map's three metric-checked gates as data: `stock-ready`, `phase-one-complete`, `graduated` gain their `MetricCondition`s.
- **`StepOutcome` vocabulary**: the six-state outcome a step's resolution is expressed in — `NotStarted | InProgress | Satisfied | Blocked(reason) | Refused | NotApplicable(reason)` — defined next to `Hazard` so the rule "`Refused` is the only terminal state a `prohibited-tactic` can reach" lives in one place. Consumed by slice 3's `Launch` aggregate.
- **BREAKING** (internal API): **`Track` → `Discipline`** — the shared `Discipline` enum is introduced in `shared/domain` and the playbook's `Track` (code, spec, YAML shape) migrates to it in the same step, so two words for one concept never coexist. A `MetricId` identity VO joins the shared kernel alongside it, as the name `MetricCondition` speaks.
- **New coherence invariant**: a step whose binding is `lesson` cannot be marked as blocking a gate — advice that blocks a gate the same way a framework rule does is a category error.
- **Undecided-rule-policy report**: a public application use case listing the steps whose rule policy is still absent, so the outstanding decisions stay visible while the playbook is authored.
- **BREAKING** (internal API): the `products` module is renamed to **`launch`**, matching the domain map's bounded-context name — post-slice-1 the module holds only playbook and launch-position code, and no `products` context exists on the map.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-playbook`: gates carry authored `MetricCondition`s and expose derived `GateCondition`s; the step ownership attribute becomes `Discipline` (was `Track`); the `StepOutcome` vocabulary and its refusal rule are defined; a blocking `lesson` step is rejected at load; the playbook reports steps whose rule policy is undecided.
- `shared-vocabulary`: the shared kernel gains the `Discipline` enum (the twelve launch disciplines, deliberately extensible when monitoring arrives) and the `MetricId` identity VO.

## Impact

- **Code**: `src/commerce_ops/products/` renamed to `src/commerce_ops/launch/` (domain, application, infrastructure, plus `tests/unit/products/` and `tests/integration/products/` mirrors); `launch_playbook.py` gains `MetricCondition`/`StepObligation`/`StepOutcome` and loses its local `Track` enum; `shared/domain` gains `Discipline` and `MetricId`; `playbook_loader.py` and `playbook_v1.yaml` gain the gate-condition shape and the `discipline` key; import sites of `commerce_ops.products` (registrations, main, worker, tests) updated.
- **No data migration**: the v1 playbook carries zero steps, so the rename and the new invariant break no authored data; launch-position records store gate identifiers and playbook version only, both unchanged.
- **Specs**: `launch-playbook` and `shared-vocabulary` deltas; other specs mention products only as domain data, not the module, and are untouched.
- **Out of scope**: authoring the step definitions themselves (a follow-up data change), the `Launch` aggregate and attestation recording (slice 3), the metric registry (slice 7).
