## 1. Confirm the irreversible precondition

- [x] 1.1 Run `SELECT count(*) FROM launch_metric_attestations` against production and record the result in this change's notes. A non-zero count halts the drop and sends this change back to design (design.md, Decision 7)
- [x] 1.2 Transcribe the **four** metric identifiers out of `_AUTHORED_METRIC_CONDITIONS` (`launch_playbook.py:457-471`) into this change's notes **before** task 4.1 deletes it — `units-fulfillable`, `sales-velocity`, `organic-share` and `tacos`. It is their only source, and an invented identifier silently breaks the launch↔monitoring join. `review-rating` is transcribed too, as the record of what was removed without a successor, but is carried by no step (design.md, Decision 8)
- [x] 1.3 Confirm the row-to-gate-to-identifier mapping in design.md Decision 8 against `author-playbook-steps` design.md:73 before seeding, and correct the design if it disagrees — the mapping is settled there, not resolved here
- [x] 1.4 Confirm `lp.ppc.048` is seeded blocking with **no** metric identifier, and `lp.inventory.040`/`041` both with `units-fulfillable` (design.md, Decision 8)

## 2. Carry the metric identifier on a step

- [x] 2.1 Add an optional `metric_id` to `StepDefinition`, typed as the shared `MetricId`, defaulting to absent
- [x] 2.2 Add the nullable `metric_id` column to `playbook_steps` with an Alembic migration, and map it on `PlaybookStep`
- [x] 2.3 Read and write `metric_id` through the step repository, so a stored identifier survives a round trip
- [x] 2.4 Accept `metric_id` in the `playbook-authoring` create and update use cases, validated by the shared vocabulary and rejected only on its own malformedness
- [x] 2.5 Surface `metric_id` on the playbook admin step form and step page

## 3. Seed the six reference rows as blocking steps

- [x] 3.1 Add the six entries — `lp.inventory.040`, `lp.inventory.041`, `lp.strategy.025`, `lp.strategy.033`, `lp.ppc.048`, `lp.finance.036` — to `alembic/data/playbook_reference.yaml`, each `blocking: true`, `status: draft`, `kind: human`, carrying its gate and its `metric_id` — or none, for `lp.ppc.048` — from design.md Decision 8, and its description transcribed under the existing trimming rule
- [x] 3.2 Teach `seed_playbook.py` to read and insert `metric_id`, so the preparation step delivers the field as well as the rows. **No insert migration** — `launch-playbook`'s *The step set is seeded before the application serves* assigns later-added reference rows to the preparation step and states that the migration machinery cannot express them (design.md, Decision 6)
- [x] 3.3 Invert `author-playbook-steps`' task 3.1 assertion: the six identifiers are present, blocking, and each declares a metric identifier
- [x] 3.4 Confirm the vendored set moves from 352 to 358 entries and equals the reference document's ID-bearing row count

## 4. Remove metric conditions from the gate model

- [x] 4.1 Delete `MetricCondition`, `_AUTHORED_METRIC_CONDITIONS` and the `GateCondition` union from `launch_playbook.py`; `framework_gates()` stops constructing conditions
- [x] 4.2 Narrow `conditions_for_gate` to return step obligations only
- [x] 4.3 Delete the `else:` arm of `_unsatisfied_gate_conditions` (`launch_run.py:675-684`) so gate readiness weighs step obligations alone
- [x] 4.4 Delete the load-time coherence fault for an empty metric-condition threshold, and the tests covering it — the requirement it implemented is REMOVED by the `launch-playbook` delta, so implementation and specification move together

## 5. Remove attestation

- [x] 5.1 Delete `MetricAttestation` and `Launch.record_metric_attestation` from the domain, and the `attestations` accessor and constructor argument
- [x] 5.2 Delete the `record_metric_attestation` use case and its export from `launch/application/__init__.py`
- [x] 5.3 Stop persisting and rehydrating attestations in `LaunchRepository`; delete the attestation model from `models.py`
- [x] 5.4 Remove `attestation` from `PROVENANCE_SOURCES`
- [x] 5.5 Delete the `metric-attested` journal kind and the `gate_id` entry field, its only populator (`journal.py:104`)
- [x] 5.6 Delete the admin journal page's `metric-attested` branch — the gate/step exception and the condition text in the detail phrase
- [x] 5.7 Remove `attestation` from the sources a handler is documented as unable to claim (`launch-step-automation` spec:77's implementation and its test)
- [x] 5.8 Write the Alembic migration dropping `launch_metric_attestations`, with a down-migration recreating it empty — last in this group, and only after task 1.1 confirms it is empty

## 6. Reconcile the surrounding text

- [x] 6.1 Remove the metric-attestation clauses from `launch-gate-progression`'s pass — carried by that capability's delta and folded in at archive; `gate_progression_job.py` names attestations nowhere, so there was nothing to remove in code
- [x] 6.2 Remove the projection exclusion for gate metric conditions from the ClickUp sync — carried by that capability's delta and folded in at archive; `clickup_sync.py` never implemented the exclusion, projecting from the step set alone
- [x] 6.3 Update `docs/domain-map.md`'s `GateCondition` sketch and the sentence deriving the launch↔monitoring dependency from it, so the map states where the metric identifier now lives
- [x] 6.4 Amend `docs/deferred-work.md`'s "Nothing can reach the graduation gate" entry: its attestation half is closed by this change, its graduation half is not
- [x] 6.5 Record in `docs/deferred-work.md` that a migrate-only database carries the migration-era seed's 107 steps rather than the served set, so `AGENTS.md`'s "create and migrate `commerce_ops_test` once by hand" leaves a test database the preparation step must still be run against. The gap predates this change, which widens it from 245 steps to 251; recording it is in scope, closing it is a change of its own
- [x] 6.6 In the archive commit, correct the two capability *Purpose* paragraphs deltas cannot reach — `launch-instance` spec:5 ("human attestation of metric conditions") and `playbook-authoring` spec:4 ("their metric conditions") — and rewrite `launch-journal`'s inherited "this change … design.md — Decision 7" pointer to name the change that introduced the exception (design.md, *A note on one inherited cross-reference*)

## 7. Verify

- [x] 7.1 Run `uv run pytest` — the whole tree, since this change deletes types several tiers construct
- [x] 7.2 Run `ruff check`, `ruff format --check`, `mypy` and `lint-imports`
- [x] 7.3 On an **empty** database, run migrate-then-prepare and confirm: both schema migrations apply, the step set loads coherently at 358 steps, and each of the five rows that carries a metric identifier declares it, `lp.ppc.048` declaring none — the identifier, not just the row, since a null one changes no behaviour until the monitoring join is attempted and would go unnoticed (design.md, Decision 6)
- [x] 7.4 Confirm no `metric_condition`, `attestation` or `MetricCondition` reference survives in `src/`, `tests/` or `alembic/`. `openspec/specs/**` is reached only through this change's deltas and task 6.5, never by direct edit

## 8. Close out

- [ ] 8.1 Abandon the `add-metric-attestation-surface` branch, which this change supersedes
- [ ] 8.2 After deploy, confirm the three parked launches advanced past `stock-ready` — the expected visible effect (design.md, Migration Plan) — and report where each now stands
- [ ] 8.3 Decide, with the team, which of the six steps to activate and when — `lp.inventory.040`/`041` before the next launch reaches `stock-ready`, and the other four before any launch reaches `phase-one-complete` or `graduated`. Until then those three gates carry no metric obligation. Admin actions, not part of this change
