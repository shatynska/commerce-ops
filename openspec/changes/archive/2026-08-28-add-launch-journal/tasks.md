## 1. Review and tests, before any code

- [x] 1.1 Have the change specification independently reviewed and revise until it is approved (AGENTS.md — spec-driven development and spec review).
- [x] 1.2 Derive tests from `specs/launch-journal/spec.md`'s scenarios, working from the specification rather than from `use_cases.py` (AGENTS.md — test design before implementation). Two constraints the delta spec implies but a test can silently miss:
  - **The containment scenarios need a fake that models a poisoned transaction, or a real session.** A fake journal that merely raises reproduces the exception but not the failed transaction state the rollback exists for, so a test built on one passes whether or not the rollback was written — the trap `contain-a-failing-launch` (archived 2026-08-27) recorded in its own task 1.2. Drive them either in the integration tier against a real session, or against a fake that refuses every subsequent write until `rollback()` has been called. The graduation-stamp scenario is the sharpest: it must fail if the append's failure is caught but the session is left unusable.
  - **"Improved wording reaches entries already appended" is a test about where composition happens**, not about a particular sentence. It passes only if the stored row holds no sentence — assert on what the repository wrote, and compose through the read.
- [x] 1.3 Confirm the derived tests fail against the current code before anything is implemented, and that each fails for its stated reason — no journal exists — rather than on a fixture fault.

## 2. The stored shape

- [x] 2.1 Add `LaunchJournalEntry` to `launch/infrastructure/driven/models.py` per design.md Decision 4: `sequence` bigint identity primary key, `product_id` FK to `launch_positions.product_id` with `ON DELETE CASCADE`, `occurred_at`, `kind`, nullable `actor`, `source`, `subject_id`, `subject_label`, and `details` JSONB.
- [x] 2.2 Declare the `kind` vocabulary as a module constant beside `OUTCOME_KINDS` and friends, and constrain the column with a `CheckConstraint` over it: `launch-started`, `step-outcome-recorded`, `metric-attested`, `gate-approval-recorded`, `gate-opened`, `launch-graduated`, `launch-date-moved`, `advance-refused`.
- [x] 2.3 Write the Alembic revision on top of `e4b91c73a2d5` — create the table, nothing else, no backfill (design.md — Migration Plan). Say in its docstring what a downgrade loses and why nothing else depends on it.
- [x] 2.4 Run the migration up and down against a real database and confirm the table appears and disappears cleanly.

## 3. The port and the entry

- [x] 3.1 Define the appended entry as a frozen dataclass in `launch/application/` — the facts of one occurrence, per design.md Decision 4. Typed fields, not `dict[str, Any]`; `details` is the one mapping, and it is what the composer reads by kind.
- [x] 3.2 Add the `LaunchJournal` port to `launch/application/ports.py`: `append(entry)`, `read(product_id)`, and the `rollback()` containment needs (design.md — Decision 3). Structural, like `LaunchStore` — no infrastructure import.
- [x] 3.3 Define the read model `JournalEntry(kind, what, when, cause)` and the composer that builds `what` and `cause` from a stored entry, one branch per kind (design.md — Decision 5). `cause` names the person and source where the occurrence names one, and the command that produced it where it names nobody.
- [x] 3.4 Export what belongs on the module's public surface from `launch/application/__init__.py`'s `__all__` — the port, the read, the read model. The stored-entry dataclass goes out too, since the repository must build one.

## 4. The append sites

- [x] 4.1 Add the required keyword-only `journal` argument to `start_launch`, `record_step_outcome`, `record_metric_attestation`, `approve_gate`, `advance_gate` and `move_launch_date` (design.md — Decision 1). Required, not defaulted: a defaulted journal is one an adapter can forget silently.
- [x] 4.2 Append exactly one entry per accepted command, after `launches.save(...)` and before any cross-module work (design.md — Decision 2). In `advance_gate` that means: save, append, *then* stamp the catalog.
- [x] 4.3 Capture the label at the append, from what the use case already holds: the served playbook's `name` for a step, the metric condition's `threshold` for an attestation, the gate identifier for a gate. Never re-resolved at read time (delta spec — labels captured when it happened). A `metric-attested` entry concerns two identifiers: the **metric condition** is the subject, and the gate travels in `details` (design.md — Decision 4, "The subject, per kind").
- [x] 4.4 Give the graduating advance a single `launch-graduated` entry carrying the posture and the approver — not a `gate-opened` entry as well. Exactly one entry per accepted command is the rule the delta spec states and the tests check.
- [x] 4.5 In `advance_gate`, catch `GateBlockedError`, append the `advance-refused` entry carrying the gate and `blocked.unsatisfied` as a list of strings in `details` (design.md — Decision 7), and re-raise the exception unchanged.
- [x] 4.6 Stamp `occurred_at` from the moment the occurrence names — `Provenance.when`, `GateApproval.when`, `MetricAttestation.when` — and leave the store to stamp the three commands that name none (design.md — Decision 6). The application layer gains no clock.
- [x] 4.7 Leave `launch/domain/` untouched. No new domain event, no change to `GateBlocked` (design.md — Decision 8).

## 5. Containment

- [x] 5.1 Wrap every append in `except Exception`; roll the session back through the port, then log at `error` naming the launch's product identifier and the occurrence that went unrecorded (design.md — Decision 3).
- [x] 5.2 Catch a failing rollback too, log it, and return: the command still completes. A journal must never be why a launch command fails.
- [x] 5.3 Confirm by test that a failed append in `advance_gate` leaves the catalog steady-state stamp performed — the scenario the whole guarantee exists for.
- [x] 5.4 Confirm by test that a failed append on a refused advance changes neither the rejection nor the conditions it names.
- [x] 5.5 Add `LaunchJournal.rollback` to the dependents listed under `docs/deferred-work.md`'s "Repositories commit their own writes, so a caller cannot own a transaction". The containment rollback is safe only while `LaunchRepository.save` commits before the append is reached; whoever makes those repositories commit-neutral needs the signpost at the place they will be working (design.md — Risks).

## 6. The repository

- [x] 6.1 Write `LaunchJournalRepository` in `launch/infrastructure/driven/`, satisfying the port structurally: `append` inserts one row and commits its own write (the convention `LaunchRepository` records), stamping `occurred_at` from the database clock where the entry names no moment.
- [x] 6.2 Implement `read` ordered by `occurred_at DESC, sequence DESC` (delta spec — most recent first, later append first on a tie).
- [x] 6.3 Implement `rollback` as the session rollback containment calls.

## 7. The read

- [x] 7.1 Add `read_launch_journal(journal, *, product_id, scope)` to `use_cases.py`, returning composed `JournalEntry` values most recent first.
- [x] 7.2 Report an empty journal — not an error, and not a distinguishable refusal — for a scope that does not permit the product, for a launch with nothing recorded, and for a product with no launch record. The three must be indistinguishable, for the reason `read_launch` already reports absence the same way.

## 8. Wiring

- [x] 8.1 Build `LaunchJournalRepository(db_session)` beside the existing `LaunchRepository(db_session)` in each of the five write-composing adapters — `slack_entry.py`, `clickup_sync_job.py`, `clickup_webhook.py`, `automation_pass.py`, `automation_confirmation.py` — and pass it to the command or the `partial` each already builds. One line each; nothing else in them changes.
- [x] 8.2 Leave `worker.py` alone: its `LaunchRepository` construction serves `read_launches`, which journals nothing.
- [x] 8.3 Confirm `uv run lint-imports` (or the pre-commit `import-linter` hook) still passes — the new application module must not name infrastructure.

## 9. Verification

- [x] 9.1 `uv run pytest tests/unit tests/agents` green, the new tests included.
- [x] 9.2 `ruff check`, `ruff format --check` and `mypy` clean (the pre-commit hooks run all three).
- [x] 9.3 `uv run pytest tests/integration` green at pre-push, with the migration applied — the containment and ordering tests that need a real session are here.
- [x] 9.4 `openspec validate add-launch-journal --strict` clean.

## 10. Ship

- [x] 10.1 Commit the work in small, reviewable commits, running the relevant verification before each (AGENTS.md — small, reviewable commits).
- [x] 10.2 `openspec archive add-launch-journal --yes` as the last commit before the merge.
- [ ] 10.3 Open the pull request and merge; merging to `main` is what deploys.

## 11. Hand over to `add-launch-tracking-pages`

- [x] 11.1 Tell that change which seam name landed. It stubs this read at one of `read_journal` / `journal` / `read_launch_journal` / `journal_entries` (`test_launch_admin_detail.py::_JOURNAL_SEAM_NAMES`) — `read_launch_journal` is in that list, so its three blocked tests unblock without a rename.
- [x] 11.2 Confirm for it that an entry carries a **cause**, which its `tasks.md` 4.8 requires checking before building the section, and that the read model's `what` / `when` / `cause` match the shape it stubbed.
- [ ] 11.3 Expect its **two** `xfail(strict=True)` journal tests to start failing as soon as this merges — that is what strict is for, and the marker comes off in that change, not this one. Its third journal test, *An empty journal says so*, carries no marker and passes already: a launch with no journal renders the empty-journal statement whether the journal exists or not, which is what a launch predating the journal shows for ever (its own `test-manifest.md` records this). All three are **blocked**; only two are xfailed.
