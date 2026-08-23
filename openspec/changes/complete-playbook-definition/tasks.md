# Tasks — complete-playbook-definition

## 1. Module rename `products` → `launch` (mechanical, no behavior change)

- [ ] 1.1 `git mv src/commerce_ops/products src/commerce_ops/launch`; update every `commerce_ops.products` reference a repo-wide grep finds in `src/` — the module-internal imports (`launch/application/__init__.py`, `playbook_loader.py`, `launch_position_repository.py`) and the `_SHIPPED_PACKAGE` string constant in `playbook_loader.py`
- [ ] 1.2 `git mv tests/unit/products tests/unit/launch` and `git mv tests/integration/products tests/integration/launch`; update test imports
- [ ] 1.3 Update the import-linter contract(s) naming `products`; grep the whole repo (docs, config, alembic, pyproject) for remaining `products`-module references and fix code/wiring hits, leaving prose about product data untouched
- [ ] 1.4 Verify: `uv run pytest tests/unit tests/agents`, `uv run ruff check`, `uv run mypy`, import-linter — all green with no behavior change; commit

## 2. Shared vocabulary: `Discipline` and `MetricId`

- [ ] 2.1 Add the `Discipline` enum (twelve members) to `shared/domain` and export it through the shared public surface alongside the existing vocabulary
- [ ] 2.2 Add the `MetricId` identity VO (rejects empty and padded values; otherwise opaque, unresolved against any registry) next to the existing identity VOs
- [ ] 2.3 Verify against the shared-vocabulary delta's scenarios (tests from the test manifest); commit

## 3. `Track` → `Discipline` migration (total, one commit)

- [ ] 3.1 Replace the local `Track` enum in `launch/domain/launch_playbook.py` with the shared `Discipline`; rename `StepDefinition.track` to `discipline` and update the unrecognised-value fault message
- [ ] 3.2 Rename the loader key and the YAML shape comment from `track` to `discipline` in `playbook_loader.py` and `playbook_v1.yaml`
- [ ] 3.3 Grep for any surviving `Track`/`track` playbook reference in code, tests, and docs — the old name must not coexist with the new one; verify and commit

## 4. Gate conditions, `StepOutcome`, lesson invariant

- [ ] 4.1 Add `MetricCondition` (frozen: `MetricId`, non-empty threshold description) and `StepObligation` (frozen: step identifier); define `GateCondition` as their union type alias; give `Gate` an authored `metric_conditions` tuple defaulting to empty
- [ ] 4.2 Add `LaunchPlaybook.conditions_for_gate(gate_id)` returning one derived `StepObligation` per blocking step at the gate plus the gate's authored metric conditions
- [ ] 4.3 Extend load-time coherence: a `lesson`-binding step marked blocking is a fault naming the step; an empty metric-condition threshold description is a fault naming the gate; both reported in the aggregated all-faults error
- [ ] 4.4 Add the `StepOutcome` vocabulary (`NotStarted | InProgress | Satisfied | Blocked(reason) | Refused | NotApplicable(reason)`; reasons required non-empty) and `permissible_terminal_outcomes` answering the hazard-coupled rule (prohibited-tactic → only `Refused`; otherwise `Satisfied` yes, `Refused` no)
- [ ] 4.5 Extend `playbook_loader.py` to parse authored gate metric conditions from YAML; verify against the launch-playbook delta's scenarios; commit

## 5. Undecided-rule-policy report

- [ ] 5.1 Add the `report_undecided_rule_policies` use case in `launch/application` returning frozen rows (identifier, gate, discipline, execution mode) for steps whose rule policy is absent, loading via the existing playbook loader
- [ ] 5.2 Export it through `launch/application/__init__.py.__all__`; verify against the delta's report scenarios; commit

## 6. Author the metric-checked gates in `playbook_v1.yaml`

- [ ] 6.1 Author metric conditions on `stock-ready` ("60–80 fulfillable units, excluding Vine"), `phase-one-complete` ("~10 units/day sustained, organic share above 40%"), and `graduated` ("TACOS falling, rating stable at 4.5") with metric identifiers monitoring can later claim
- [ ] 6.2 Verify the shipped playbook loads coherently (loader test over the real YAML); commit

## 7. Documentation and closure

- [ ] 7.1 Update `docs/domain-map.md`: mark the lesson-cannot-block invariant as shipped, and record that `launch` is now the module's real name (drop "products" if the map mentions it); note the v1-mutable-until-slice-3 versioning cut-off where the map discusses versioning
- [ ] 7.2 Update the `## Purpose` of `openspec/specs/shared-vocabulary/spec.md` (edited directly, per OpenSpec convention for Purpose changes) so it covers the discipline and metric-identity vocabulary alongside product identity and lifecycle stage
- [ ] 7.3 Full verification: `uv run pytest` (all tiers), `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, import-linter; confirm every delta scenario has a passing test per the test manifest
