## Context

See proposal.md — Why. The mechanics this design leans on already exist: `start_launch` and `record_step_outcome` read the playbook through a `Playbooks` port whose current adapter is the YAML loader; `LaunchPlaybook` enforces coherence at construction and reports **every** fault in one `InvalidPlaybookError`; the ClickUp convergence pass is self-healing (a step that appears mid-launch simply materializes as a task on the next pass). The design's job is to move step storage without disturbing any of that, and to route writes through the same validation reads already trust.

Constraints: the launch module's public surface is its `application/__init__.py` (import-linter enforced), so the new write use cases are the only doorway the future admin UI gets. The domain layer does no I/O, so nothing in `launch_playbook.py` may learn about Postgres.

## Goals / Non-Goals

**Goals:**
- Steps stored in Postgres, read through the unchanged `Playbooks` port, validated by the unchanged domain model.
- Writes that cannot corrupt: no sequence of create/update/retire calls can leave a step set that fails coherence.
- The ClickUp projection stays truthful after edits: wording changes reach existing tasks; retired steps stop being projected.

**Non-Goals:**
- No editing of gates, opening modes, or metric conditions — the framework stays code-owned.
- No playbook version management: no publish/draft workflow, no version browsing, no rollback UI.
- No admin UI — that is `add-playbook-admin-ui`, which consumes this change's use cases.
- No change to how outcomes are recorded or how gates open.

## Decisions

**1. Steps move; gates stay code-owned.**
The eight gates are structural: `Launch` validates against the gate sequence, convergence special-cases `graduated`, metric attestation hangs off gate conditions. A manager edits steps; restructuring gates would ripple into domain code regardless of where the data lived, so storing gates in the database would buy editability nobody can use. *Alternative considered:* moving the whole playbook (gates included) — rejected as editability without an editor.

**2. Live playbook; version pinning becomes an audit stamp.**
One current step set; an edit takes effect on the next read. This is coherent *because* convergence is already convergence: a new step materializes as a task on the next pass, an edited due offset heals like a moved launch date. The launch row keeps its `playbook_version` column as a record of what the launch started under, but no read path branches on it. *Alternative considered:* immutable published versions with a publish step — real rigor, but it drags a versioning UI and a draft state into an internal tool, and the self-healing loop makes instant edits safe rather than dangerous.

**3. Writes validate by constructing the whole candidate playbook.**
A create/update/retire use case loads the current step set, applies the mutation in memory, and constructs `LaunchPlaybook`. Construction failing rejects the write with the full fault list; construction succeeding is the *only* path to persistence. This reuses the entire coherence rulebook (unique identifiers, known gates, description shape, blocking rules) with zero duplication, and the all-faults-at-once contract is exactly what a form wants to render. One rule joins that rulebook in this change: the gate-holding floor ("every gate has at least one blocking step"), today a test over the shipped set, becomes a construction rule — the only edit the domain model takes — because with an editable set it must hold after every write, and putting it anywhere but the shared rulebook would make "the same rules at load and write" false. *Alternative considered:* per-field validation on the write path — rejected because it would re-implement the domain's rules and drift from them.

**4. Retire, never delete.**
Recorded outcomes and ClickUp mappings reference step identifiers; deletion orphans history. A retired step carries a retirement marker (who, when): it is excluded from the playbook the port serves (so projection, gating, and reports no longer see it) but its row and identifier persist. Un-retiring is its own fourth write operation — validated like every write, recording its own principal and date — not a field update; the retirement marker is not among the authorable fields.

**5. Identifier namespaces record origin.**
Seeded rows keep their `lp.*` identifiers and reference-row provenance untouched. Manager-created steps get generated identifiers under a distinct prefix (`mg.<discipline>.<seq>`), with provenance recording the creating principal and date. The namespace makes a step's origin legible at a glance, preserving the transcription discipline's traceability without demanding it of manager-authored steps.

**6. Convergence heals a task's name and body only while they are still the system's own words; retired steps leave the loop.**
Today the pass heals only due dates, and `launch-clickup-sync` deliberately guarantees that an edited task name is never restored — a person may legitimately rename a task, and a pass that rewrote it would silently discard their edit. An editable playbook needs wording fixes to reach existing tasks, but not at the price of that guarantee. The reconciliation is the transition pattern the loop already uses for closed-state ("keyed on the last observed state"): the mapping retains the name the system last composed, and the pass rewrites a task's name and body **only when the task still carries exactly that composition** — an unedited task follows the step's current wording; a task whose name differs has been edited by a person and is never touched again. *Alternative considered:* healing unconditionally — rejected because it reverses a deliberately argued spec guarantee; leaving names frozen — rejected because it makes every description edit a lie in ClickUp.
A step retired while its task is unfinished has that task left unmanaged: deleting it in ClickUp is not this system's call, closing it would fabricate a completion — the task simply stops being converged, and its closures stop being recorded (a retired step is no longer in the served playbook, so recording against it is impossible anyway).

**7. Writes are serialized by an optimistic step-set version.**
The step set carries a single monotonically increasing set-version. Every write reads the current set and its version, validates the mutated whole (decision 3), and persists conditionally on the version being unchanged, bumping it; a concurrent write that lost the race fails the condition and is retried against the fresh set (re-validating — the retry may now be rightly rejected, e.g. the second of two retirements that together would unhold a gate). This closes the interleaving hole in decision 3's guarantee — two overlapping retirements can no longer each validate against the pre-write set and jointly persist an incoherent one — and it serializes `mg.<discipline>.<seq>` identifier generation through the same mechanism, since both allocations cannot commit against the same version. The set-version also supplies the served playbook's version identifier (decision 2's audit stamp derives from it), so "which definition era did this launch start under" has a real answer that moves with every accepted write. *Alternatives considered:* serializable transaction isolation — equivalent power, but its failure mode (driver-level serialization errors) is harder to turn into the all-faults validation reply; a per-playbook advisory lock — simplest to reason about, but blocks instead of failing fast and gives the future admin UI nothing, whereas the set-version doubles as stale-form detection ("this page was loaded against version 41; the set is now 43").

**8. The YAML seeds once, then retires.**
An Alembic data migration parses `playbook_v1.yaml` through the existing loader (getting its validation for free) and inserts the step rows; a follow-up commit removes the YAML, `playbook_loader.py`'s YAML path, and `shipped_playbooks.py`. The seed runs through the loader precisely so the migration cannot insert what the domain would reject.

**9. The mapping retains the compositions the system last wrote, adopted for legacy rows only when unambiguous.**
Conditional healing (decision 6) needs the mapping to retain, per task, the name and the body the system last composed — two new nullable columns on the existing mapping table, written whenever the system writes the fields. Rows predating this change hold nothing there; on first observation, a field whose ClickUp content is exactly what the system would currently compose is adopted as retained (an unedited legacy task starts healing), and anything else is left unadopted and never rewritten — with no record of what was last written, an authored change cannot be told from a person's edit, and the person wins that ambiguity by design.

## Risks / Trade-offs

- [Edits take effect instantly on live launches — a bad edit propagates within one convergence pass] → the write-side full-playbook validation blocks incoherent sets entirely; for merely *unwise* edits, retire-not-delete and un-retire keep every mistake reversible, and provenance says who did what.
- [The playbook is now read from Postgres on every pass instead of a cached in-process constant] → reads are one small table per pass, on the same database the pass already queries; no caching layer until measurement says otherwise.
- [The seed migration depends on the YAML loader that a later commit deletes] → the migration vendors nothing: it runs while the loader still exists, and the deletion lands only after the seed is deployed. Rollback of the schema migration restores nothing YAML — the file stays in git history if resurrection is ever needed.
- [`mg.*` steps lack reference-document provenance] → deliberate: their provenance is authorship (who/when), which is the truthful statement of where they came from.

## Migration Plan

1. Schema migration: step tables (with the set-version) land empty; the ClickUp mapping table gains its nullable retained-composition columns.
2. Seed migration: `playbook_v1.yaml` → rows, via the existing loader.
3. Adapter swap: the `Playbooks` port binding changes to the Postgres repository; YAML path removed.
4. Rollback: revert the adapter binding (YAML loader still in git history at the previous tag); the step tables are additive, so downgrading the binding loses only post-migration edits.
