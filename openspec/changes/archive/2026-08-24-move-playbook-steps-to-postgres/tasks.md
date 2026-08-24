## 1. Domain: the gate-holding coherence rule

- [x] 1.1 Add the gate-holding floor to `LaunchPlaybook` construction in `launch/domain/launch_playbook.py`: a gate with no blocking step attached is a coherence fault, reported in the same aggregated `InvalidPlaybookError` as every other, naming the gate
- [x] 1.2 Adjust existing domain/loader test fixtures that construct playbooks with unheld gates so the suite is green under the new rule (fixture repair only — new behavior gets its own tests from the test-writer)

## 2. Storage: schema and seed

- [x] 2.1 Alembic migration: playbook step tables carrying every authorable field, retirement marker (who/when), provenance (seed citation and/or authoring principal+date, update/retire/un-retire attribution), and the single optimistic step-set version
- [x] 2.2 Alembic migration: nullable retained-composition columns (last-written name, last-written body) on the ClickUp mapping table
- [x] 2.3 Seed data migration: parse `playbook_v1.yaml` through the existing loader (construction validates it, gate-holding rule included) and insert the step rows; the seed is idempotent — a populated step set is never re-seeded and authored edits are never overwritten

## 3. The Postgres `Playbooks` adapter

- [x] 3.1 Repository adapter in `launch/infrastructure/driven/` implementing the existing `Playbooks` port: serves the live step set (retired steps excluded) with code-owned gates, constructing `LaunchPlaybook` on read
- [x] 3.2 The served playbook's version identifier derives from the step-set version, so it changes with every accepted write
- [x] 3.3 Composition wiring: jobs (`worker.py`), Slack entry, and webhook read the playbook per pass through the adapter — no import-time caching of the step set

## 4. Write use cases (`playbook-authoring`)

- [x] 4.1 `create_step`: authorable fields, generated `mg.<discipline>.<seq>` identifier (collision-checked against every step, retired included), authorship provenance
- [x] 4.2 `update_step`: authorable fields minus identifier and discipline (both rejected if attempted), edit attribution recorded, seed citation preserved
- [x] 4.3 `retire_step` and `unretire_step` as distinct operations, each recording its principal and date
- [x] 4.4 Shared write path: load current set + version, apply the mutation, construct the full candidate `LaunchPlaybook` (all faults reported on rejection, nothing persisted), persist conditionally on the unchanged set-version with retry-and-revalidate on conflict
- [x] 4.5 Export the four use cases through `launch/application/__init__.py` (`__all__`) — the admin-UI change consumes only this surface

## 5. Launch instance and entry: served playbook, audit stamp

- [x] 5.1 Outcome recording and metric attestation validate step/metric identifiers against the served playbook (a retired step's identifier is rejected; its previously recorded outcomes stay readable)
- [x] 5.2 `start_launch` records the served playbook's version identifier as the launch's audit stamp; no read path branches on the stored value

## 6. ClickUp sync: healing and retirement

- [x] 6.1 Convergence heals task name and body toward the step's current composition, each field independently and only while it still carries exactly the retained last-written value; every system write updates the retained value
- [x] 6.2 Legacy mappings (no retained compositions): adopt a field's content as retained only when it exactly matches the current composition; otherwise leave it absent and the field forever unrewritten
- [x] 6.3 Retired steps leave the loop: no create/re-create/rename/re-date/close/delete for their tasks; webhook and reconciliation keep updating the retained observed state while recording no outcome; un-retired steps resume through their existing mapping, recording only later transitions

## 7. Retire the YAML path

- [x] 7.1 Remove `playbook_v1.yaml`, the YAML loading path in `playbook_loader.py`, and `shipped_playbooks.py`, updating every caller to the port — sequenced after the seed migration is deployed (the seed depends on the loader it outlives)

## 8. Verification

- [x] 8.1 Full check run: `uv run pytest` (unit + agents + integration), mypy, ruff, import-linter — all green

## 9. Record the decision and align spec prose

- [x] 9.1 Amend `AGENTS.md` and `README.md`: the repository owns the playbook framework (gates, coherence rules, vocabulary); the database owns the step content, edited through validated write use cases
- [x] 9.2 At archive time, direct spec edits declared in the proposal: amend the Purposes of `launch-playbook`, `launch-entry`, and `launch-instance` (drop "authored in the repository" / "the version the build ships" / "pinned playbook version"), and rename the requirement header "The shipped playbook carries the authored step set" to "The seeded step set carries the authored v1 definitions"
