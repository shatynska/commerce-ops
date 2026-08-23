## 1. Shared vocabulary

- [x] 1.1 Add `shared/domain/severity.py`: a `Severity` enum (`MONITOR`, `DIAGNOSE`, `CRITICAL`) following `discipline.py`'s pattern — immutable, value-compared, unknown values rejected by construction
- [x] 1.2 Make it importable the way the rest of the vocabulary is. *Corrected during apply*: this project's `domain/__init__.py` files are all empty and every consumer imports the module directly (`from commerce_ops.shared.domain.discipline import Discipline`). Adding an `__init__` export for `Severity` alone would invent a convention the codebase does not have, so the direct module path is the export.

## 2. Launch public surface

- [x] 2.1 Add `Launch.awaiting_confirmation(playbook) -> bool` to `launch/domain/launch_run.py`: true exactly when the current gate requires confirmation, every blocking condition attached to it is satisfied, no approving approval is recorded for it, and the launch has not graduated
- [x] 2.2 Grow the `LaunchStore` protocol (`launch/application/ports.py`) with enumeration of all persisted launches, and implement it in `launch/infrastructure/driven/launch_repository.py`. *Note during apply*: added as `list_all`, deliberately separate from the existing `list_active`, which drops launches standing at `graduated` — right for the ClickUp passes, wrong for reporting, since a launch waiting at the final gate for its graduation approval is exactly something to brief.
- [x] 2.3 Add `awaiting_confirmation: bool` to `LaunchReport`, and the step's owning `Discipline` to each `StepStatus` entry, filling both in `read_launch` (the at-risk evaluation already names its overdue blocking steps via `LaunchDateAtRisk.overdue_steps`). *Widened during apply, mandated by the delta spec's own rule that a fact a consumer needs travels on the report*: each entry also carries `blocking` and `overdue`. "Overdue" folds in "has not reached a terminal outcome its **hazard** permits" — a `prohibited-tactic` step is resolved by `Refused` — which briefing cannot evaluate without the playbook. Backed by the new domain derivation `Launch.overdue_step_ids`, which `date_at_risk` now narrows rather than duplicates.
- [x] 2.4 Add `read_launches(launches, playbooks, *, as_of) -> tuple[LaunchReport, ...]` to `launch/application/use_cases.py` — all launches, unfiltered (activeness is briefing's question), each report identical in content to `read_launch`'s (both now build through one `_report_for`, so they cannot drift)
- [x] 2.5 Export `read_launches` from `launch/application/__init__.py`; delete `launch/application/pending_cadence.py` and remove `run_pending_cadence_report` from the surface

## 3. Briefing domain

- [x] 3.1 Create `src/commerce_ops/briefing/` with `domain/`, `application/`, `infrastructure/driven/`, `infrastructure/driving/` packages
- [x] 3.2 Add `briefing/domain/attention.py`: `Evidence` (a fact naming its source — step or gate identifier — with an optional due period), `AttentionItem` (product id, discipline where applicable, `Severity`, cause identifier, evidence tuple; invariant: at least one piece of evidence), and `CauseOrder` (an ordered tuple of cause identifiers, validated unique)
- [x] 3.3 Add the collapse function (order is data, collapse is code): raw findings per product + a `CauseOrder` → items grouped so same-cause findings on one product merge (overdue steps per discipline), absorbed findings become evidence of their absorber, and items sort by cause rank within a product
- [x] 3.4 Add `briefing/domain/briefing.py`: the `Briefing` aggregate (period date, audience, items) — knows `is_clean`, and refuses to render a clean briefing for delivery
- [x] 3.5 Encode the launch-side cause order and severity grading as data in the domain: `launch-date-at-risk` (CRITICAL, absorbs overdue blocking steps) > `gate-awaiting-confirmation` (DIAGNOSE) > `overdue-step` (MONITOR)

## 4. Briefing application

- [x] 4.1 Add `briefing/application/ports.py`: a launch-reports reader, a product reader (name, SKU, lifecycle stage by product id), and a briefing notifier `Protocol` (the `MonitoringNotifier` shape)
- [x] 4.2 Add the derivation in `briefing/application/use_cases.py`: launch reports → raw findings (at-risk with its overdue blocking steps, awaiting-confirmation gate, overdue non-blocking steps), skipping launches whose product's stage is steady-state or retired; a product the catalog cannot resolve is treated as active and identified by raw id
- [x] 4.3 Add `assemble_daily_briefing(..., *, audience, as_of) -> Briefing` composing derivation + collapse into the aggregate
- [x] 4.4 Add the plain-text rendering of a non-clean briefing (product name and SKU — or raw id — per item, severity, evidence, due periods), and `run_daily_briefing(...)` which assembles, posts only when not clean, and lets a read failure propagate while only logging a delivery failure
- [x] 4.5 Export the use cases and ports from `briefing/application/__init__.py` — the module's one public surface

## 5. Briefing infrastructure and composition

- [x] 5.1 Move `slack_notifier.py` from `catalog/infrastructure/driven/` to `briefing/infrastructure/driven/` unchanged (same env vars)
- [x] 5.2 Add `briefing/infrastructure/driving/daily_briefing_job.py` on `daily_digest_job.py`'s pattern: module-level injection points (launch-reports reader, product reader, notifier), the digest's schedule slot and tolerance, run-failure semantics per the spec (assemble failure fails the run and posts one message only once retries are exhausted; delivery failure logs and succeeds)
- [x] 5.3 Delete `catalog/application/daily_digest.py`, `catalog/infrastructure/driving/daily_digest_job.py`, and `run_daily_digest` from catalog's surface. *Extended during apply*: the digest's read port went with it — `ProductNameReader` and the repository's `list_names` existed only to serve the digest, so leaving them would have left half a deletion behind as dead public surface.
- [x] 5.4 Swap the job in `registrations.py`: daily digest out, daily briefing in
- [x] 5.5 Rewire `worker.py`: point `overdue_check.notifier` at briefing's notifier; compose and inject the briefing job's closed callables from launch's and catalog's public surfaces plus their repositories (the `clickup_sync_job.read_product` pattern)
- [x] 5.6 Add `commerce_ops.briefing` to `.importlinter`: the layers contract's containers, three boundary contracts modeled on launch's (with the same application→domain `ignore_imports` exemptions for catalog and launch), and `commerce_ops.briefing` added to the other modules' forbidden lists

## 6. Tests

- [x] 6.1 Wire in the scenario tests derived from the delta specs (test-writer manifest): `tests/unit/briefing/domain/` for derivation, collapse, severity grading, clean/non-clean; `tests/unit/briefing/application/` for assembly, rendering, delivery/assembly failure semantics; `tests/unit/launch/` for enumeration and `awaiting_confirmation`; `tests/unit/shared/` for `Severity`
- [x] 6.2 Update tests that exercise the removed pieces: daily digest (catalog), `run_pending_cadence_report`, and the registration-parity test's expected job set. *Done during apply*: both digest test files removed; `test_the_schedules_due_moments_do_not_depend_on_the_hosts_timezone` **preserved** out of the digest job's file into `tests/unit/shared/infrastructure/driving/test_schedule_timezone.py`, because it derives from `scheduled-jobs` rather than from the retired `product-monitoring` requirements and deleting it with the digest would have dropped a standing obligation silently; the two `slack_notifier` import paths retargeted at briefing's copy; and `_CATCH_UP_WORK` in `test_job_runner_schedules.py` retargeted from `products.monitoring.daily` to `briefing.daily`, which otherwise silently matched nothing and left four assertions vacuous.
- [x] 6.3 Verify the briefing job's registration parity (both composition roots register it) per the existing pattern

## 7. Docs

- [x] 7.1 Update `docs/domain-map.md`: mark slice 5 realized, and record in the briefing section what this change settles — digest semantics, the three-tier `Severity` reading of `SignificanceTier`, launch cause order and grading, briefing's ownership of Slack delivery, activeness answered by the catalog stage stamp, and the deferrals (interactive approvals to slice 6, evidence staying briefing-owned until a second speaker)
- [x] 7.2 Rewrite `openspec/specs/product-monitoring/spec.md`'s Purpose (a direct edit — deltas cannot carry an existing capability's Purpose) to record that the daily listing is superseded by `briefing` and the capability returns in slice 7 as the metric registry and evaluation engine

## 8. Verification

- [x] 8.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`, `uv run lint-imports`
- [x] 8.2 Run `openspec validate --change introduce-launch-briefing --strict`
