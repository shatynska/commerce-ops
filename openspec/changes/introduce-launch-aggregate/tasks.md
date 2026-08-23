## 1. Domain — the `Launch` aggregate (pure, I/O-free)

- [ ] 1.1 Create `launch/domain/launch_run.py` with the value objects the aggregate speaks: `Provenance` (source `clickup | automated | attestation`, who, when, evidence), `StepProgress` (outcome + provenance), `GateApproval` (decision, named approver, timestamp, optional `Posture` — required exactly for `graduated`, rejected elsewhere), `MetricAttestation` (gate id, metric id, attester, when, evidence)
- [ ] 1.2 Define the event objects as returned domain objects (catalog's `StageChanged` precedent): `LaunchStarted`, `StepSatisfied`, `StepRefused`, `GateOpened`, `GateBlocked`, `LaunchDateMoved`, `LaunchDateAtRisk`, `LaunchGraduated`
- [ ] 1.3 Implement the `Launch` aggregate root: identity by `ProductId`, pinned `playbook_version` (commands reject a `LaunchPlaybook` whose version differs), current gate, optional launch date; `start()` creation path beginning at `commit` and returning `LaunchStarted`
- [ ] 1.4 Implement `record_step_outcome(playbook, ...)`: unknown step ids rejected, terminal outcomes restricted via `permissible_terminal_outcomes` (prohibited-tactic → only `Refused`; others never `Refused`), provenance mandatory on every outcome, re-recording replaces the stored outcome without reversing an opened gate, returns `StepSatisfied` / `StepRefused` when those outcomes are reached
- [ ] 1.5 Implement `record_metric_attestation(playbook, ...)` (rejected when the pinned playbook does not author that condition on that gate) and `approve_gate(...)` (named approver required; decision is approving or rejecting and only an approving one satisfies the gate's approval requirement; posture required for `graduated`, rejected on other gates)
- [ ] 1.6 Implement `advance_gate(playbook)`: monotonic single-step advance only (skips and backward moves rejected), evaluates `conditions_for_gate` — blocking step obligations satisfied only by `Satisfied`/`NotApplicable`, metric conditions only by attestation, `Refused` never satisfies — confirmation gates additionally require an approval; returns `GateOpened` (plus `LaunchGraduated` when opening `graduated`), raises carrying `GateBlocked` naming each unsatisfied condition
- [ ] 1.7 Implement due-period derivation (`LaunchDate + TimingAnchor` per step; absent without a launch date; recurring anchors yield none), `move_launch_date(...)` returning `LaunchDateMoved` with previous and new dates, and `date_at_risk(playbook, as_of)` returning `LaunchDateAtRisk` naming each blocking, unresolved step whose due period has fully passed

## 2. Persistence — the aggregate's repository

- [ ] 2.1 Add ORM models for `launch_step_progress`, `launch_gate_approvals`, `launch_metric_attestations`, keyed to `launch_positions.product_id` with cascade delete
- [ ] 2.2 Write the additive Alembic migration creating the three tables (no change to `launch_positions`; rollback drops only the new tables)
- [ ] 2.3 Evolve `LaunchPositionRepository` into the aggregate repository: `save(launch)` / `get_by_product_id` rehydrating the full state (position, step progress, approvals, attestations); remove `update_current_gate`; keep unknown-product and duplicate-launch rejections

## 3. Application — use cases and public surface

- [ ] 3.1 Define the launch store port and implement `start_launch` (loads and pins the current playbook version, verifies the catalog product exists, persists, reports `LaunchStarted`)
- [ ] 3.2 Implement `record_step_outcome`, `record_metric_attestation`, `approve_gate`, `advance_gate`, `move_launch_date` use cases: load aggregate, load the pinned playbook version, invoke the domain command, persist, return the produced events
- [ ] 3.3 Wire graduation: when `advance_gate` opens `graduated`, call `catalog.application.change_stage` with `SteadyState(approval.posture)` and the approver as confirmer, after the launch is persisted; surface a failed stamp as an error naming the manual catalog fix
- [ ] 3.4 Implement the launch read use case: full state plus derived due periods and at-risk evaluation as of a given date
- [ ] 3.5 Export the new use cases through `launch/application/__init__.py` and confirm `lint-imports` passes

## 4. Verification and documentation

- [ ] 4.1 Run the full commit-time verification: `uv run pytest tests/unit tests/agents`, `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, `lint-imports`
- [ ] 4.2 Run `uv run pytest tests/integration` against Postgres (repository rehydration, migration up/down)
- [ ] 4.3 Update `docs/domain-map.md`: mark slice 3 realized; record the graduation-posture decision (approval carries the approver-chosen posture) and the at-risk rule if the map's wording needs it
- [ ] 4.4 Reconcile the obsolete integration test for the removed `update_current_gate` path per the test-writer's obsolete-test manifest
