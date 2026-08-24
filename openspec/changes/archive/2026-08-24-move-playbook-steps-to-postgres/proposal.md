## Why

The playbook's step set is authored as repo-owned YAML, so every addition or correction requires a developer transcribing into `playbook_v1.yaml` — a workflow the ops manager cannot participate in, and one that has left `docs/reference/product-launch.md` only partially transcribed (BUILD THE LISTING is complete; the other seven gates carry a curated subset). Leadership's direction is a growing, frequently-edited step set (more transcription now, per-step automation later), and the decided editing surface is a web page — which cannot write a file in the repository. Step definitions therefore move to Postgres as the single source of truth, and the project's "repository owns the playbook definition" decision is formally amended: the repository keeps owning the *framework* (the eight gates, the coherence rules, the step vocabulary); the database owns the *step content*.

## What Changes

- Step definitions move from `playbook_v1.yaml` to Postgres tables, read through the existing `Playbooks` port by a new repository adapter. The eight gates, their opening modes, and their metric conditions stay code-owned — a manager edits steps, never the gate structure.
- `playbook_v1.yaml` becomes a one-time seed (an Alembic data migration populating the step tables), after which the YAML file and its loader are retired. **BREAKING** (internal): `load_shipped_playbook` and the YAML loading path are removed; every reader goes through the port.
- New write use cases on the launch module's public surface: create a step, update a step, retire a step, un-retire a step. A write validates by constructing the full candidate `LaunchPlaybook` — the existing all-faults-at-once coherence machinery — and rejects the write with every fault on failure. No partially valid step set can be persisted.
- The playbook becomes **live**: one current step set, edits effective immediately, no publish ceremony. A launch's pinned `playbook_version` remains as an audit stamp, not a behavior switch — every launch reads the live playbook.
- Steps are **retired, never deleted**: recorded outcomes reference step identifiers, so a retired step stops being projected and stops holding gates, but its history stays interpretable.
- Manager-created steps get generated identifiers in their own namespace (distinct from the seeded `lp.*` rows), with provenance recording who created them and when.
- ClickUp convergence extends from healing due dates to also healing task name and description — but only while a field still carries exactly what the system last wrote, so a person's edit in ClickUp is never fought; a retired step's open task drops out of projection scope — left standing, neither closed nor deleted — rather than left converging.
- `AGENTS.md` and `README.md` record the amended ownership decision.

## Capabilities

### New Capabilities

- `playbook-authoring`: creating, updating, and retiring step definitions in the stored step set — write-side validation via full-playbook construction, identifier generation and namespacing for authored steps, retire semantics, and authorship provenance.

### Modified Capabilities

- `launch-playbook`: the step set's source of truth moves from repo-authored YAML to the database ("versioned and authored in the repository" no longer holds for steps); the shipped-playbook requirements become seed requirements; version pinning becomes an audit stamp against a live playbook whose version identifier moves with the step set; load-time coherence validation now also guards every write, and gains the gate-holding floor as a coherence rule.
- `launch-clickup-sync`: projection convergence additionally drives task name and description toward what the step defines (guarded per field by the retained last-written composition), projection and recording read the served playbook rather than a pinned version, and a retired step leaves the loop in both directions.
- `launch-instance`: outcome recording and metric attestation validate step and metric identifiers against the served playbook instead of "the pinned playbook version".
- `launch-entry`: a started launch records the served playbook's version identifier as an audit stamp instead of pinning "the version the build ships".

## Impact

- New: playbook step tables (carrying an optimistic set-version that serializes writes) + Alembic migrations (schema + seed from `playbook_v1.yaml`), a migration adding retained-composition columns to the ClickUp mapping table, a Postgres `Playbooks` adapter in `launch/infrastructure/driven/`, write use cases in `launch/application/`.
- Spec Purposes brought in line at apply time: `launch-playbook`'s ("authored in the repository"), `launch-entry`'s ("the playbook version the build ships"), and `launch-instance`'s ("pinned playbook version") prose is amended directly in `openspec/specs/`, since requirement deltas do not carry Purpose edits; the stale-reading requirement header "The shipped playbook carries the authored step set" is likewise renamed there at apply time, to "The seeded step set carries the authored v1 definitions" (deltas match on header identity, so the rename cannot travel in the delta).
- Removed: `playbook_loader.py` YAML path, `shipped_playbooks.py`, `playbook_v1.yaml` (after seeding).
- Modified: `clickup_sync.py` convergence (name/description healing, retired-step handling), composition wiring for jobs and Slack entry (playbook now read per pass, not cached at import).
- Modified (domain, one rule): `launch_playbook.py` gains a single coherence rule — the gate-holding floor, promoted from a shipped-set test to a construction rule so load and write validation are one rulebook. Otherwise the domain model — gates, vocabulary, every other rule — is untouched.
- Unchanged: the `Playbooks` port signature; launch-instance's code paths (its validation already reads through the port — what changes, per its delta, is the validation target: the served playbook rather than a pinned version, which newly makes a retired step's identifier rejectable).
- Enables: the `add-playbook-admin-ui` change, whose page consumes only this change's use cases.
