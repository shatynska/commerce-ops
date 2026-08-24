## 1. Pre-authoring checks

- [ ] 1.1 Confirm no real launch has pinned `v1` — the deployment's `launch_positions` table (the version is pinned by its `playbook_version` column) is empty or holds only disposable test rows. Delete any disposable test rows before deploy, so the first convergence pass does not project ~92 tasks onto a stale test launch; the five child tables cascade on delete, but a ClickUp list a test launch already created does not and is archived by hand. If a real launch exists, switch this change to shipping the content as `v2` per design.md Decision 1 and adjust the tasks below accordingly.

## 2. Author the step definitions

- [x] 2.1 Author the `commit` (4) and `order` (3) steps into `playbook_v1.yaml` per the design.md table, mapping WHEN to anchors per Decision 3.
- [x] 2.2 Author the `listable` barcode/listing-creation and keyword-research/indexation groups (7 + 14 steps).
- [x] 2.3 Author the `listable` listing-content, variation-family, and creative groups (15 + 8 + 21 steps).
- [x] 2.4 Author the `stock-ready` (3), `live` (9), `ignition` (7), `phase-one-complete` (3), and `graduated` (3) steps, including the seven area-3 reassignments and the two rule-policy strings from Decision 7.
- [x] 2.5 Load the shipped playbook once (existing loader) and resolve any coherence faults the authoring introduced — the loader's aggregated fault report is the checklist.

## 3. Coverage tests

- [x] 3.1 Add unit tests asserting the shipped playbook's specified properties: loads coherently with a non-empty step list; every gate has ≥1 step and ≥1 blocking step; every BUILD THE LISTING row ID appears; every step's identifier is a reference row ID and its provenance carries that row's citation; the metric-restatement row IDs named in design.md Decision 8 do not appear as steps; all four anchor kinds, all twelve disciplines, both hazards, and all three execution modes are present; steps whose execution mode requires a rule policy carry one; no `prohibited-tactic` step blocks; the undecided-rule-policies report lists exactly the human-attested steps without a policy.

## 4. Verification and record

- [x] 4.1 Run `uv run pytest tests/unit tests/agents`, mypy, ruff, and import-linter; run `tests/integration` before push.
- [x] 4.2 Update `docs/domain-map.md`: close the "authoring the step definitions is a follow-up change" note, recording the settled details (BUILD THE LISTING complete, representative subset elsewhere, hazard-by-substance, framework-only blocking spine, metric-condition rows not duplicated, in-place `v1` edit under the recorded cut-off).
