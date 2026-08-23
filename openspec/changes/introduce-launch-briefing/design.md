# Design — introduce-launch-briefing

## Context

See `proposal.md` — Why. Current state that shapes the approach:

- The daily Slack message is catalog's: `run_daily_digest` (application) + `daily_digest_job.py` (driving), registered in `registrations.py`, posting through `catalog/infrastructure/driven/slack_notifier.py` — a fully generic adapter (env-driven token and channel, no catalog imports). `worker.py` also injects that notifier into shared's `overdue_check`.
- `launch.application` exposes `read_launch(product_id, as_of) → LaunchReport` (steps with due periods and progress, plus the at-risk evaluation) but no way to enumerate active launches, and the report does not say whether the current gate awaits confirmation. `run_pending_cadence_report` is an exported no-op.
- Cross-module composition has two sanctioned patterns already in the codebase: application → another module's `application/__init__` (import-linter exempts the target's own application→domain edges), and worker-injected closed callables for anything that would otherwise need another module's infrastructure (`clickup_sync_job.read_product`, `overdue_check.notifier`).
- `scheduled-jobs` supplies schedules, retries, run history, overdue reporting and the freshness endpoint; the briefing job buys all of that by registering, not by building anything.

## Goals / Non-Goals

**Goals:**

- A `briefing` module whose domain layer is pure, deterministic, and stage-generic: raw findings in, collapsed graded `AttentionItem`s out — so slice 7 plugs monitoring findings into the same mechanism with only a different cause order.
- Silent-when-clean as a domain rule (the `Briefing` knows it is clean), not an `if` in a job.
- The delivery discipline (schedule, delivery-failure decoupling, read-failure surfacing) preserved exactly as the retired daily listing had it.

**Non-Goals:**

- Interactive Slack approvals (Block Kit buttons wired to `approve_gate`) — deferred to slice 6, when `access` can guard who may approve; here a pending confirmation gate is a briefing item only.
- Cross-briefing memory: no suppression, no persisted `Briefing`, no new tables. Digest semantics were decided at proposal time; alarm-style dedup can be layered on later without changing the assembly model.
- Monitoring-side findings, ClickUp routing of items, `Recommendation`/interpretation — later slices.
- Message formatting beyond a clear plain-text layout (Block Kit is presentation, changeable any time).

## Decisions

### 1. Briefing's domain is findings-in, items-out; launch knowledge stays in launch

`briefing/domain` defines the generic model: `AttentionItem`, `Briefing`, `CauseOrder`, and the collapse function. It never imports launch. The *derivation* of launch findings from `LaunchReport`s lives in `briefing/application` — the use case reads launch's published report shape and translates it into briefing's raw findings. Facts that require launch's own rules to compute (is the current gate awaiting confirmation?) are computed by launch and exposed on the report, never re-derived in briefing — duplicating gate logic across modules is exactly the drift the module boundary exists to prevent. Hence the two `launch-instance` deltas:

- `LaunchStore` grows enumeration and `read_launches(as_of) → tuple[LaunchReport, ...]` joins the public surface. It enumerates **all** launches, deliberately unfiltered: launch's persisted shape cannot distinguish a graduated launch from one standing at the final gate (`launch_run.py` documents this), and stage is catalog's attribute anyway. *Activeness* is briefing's filter, answered by the catalog stage stamp (steady-state or retired ⇒ not briefed) — the same `get_product_by_id` read that supplies the item's name and SKU supplies the stage, so the filter costs nothing extra. A launch whose product the catalog cannot resolve is treated as active and reported by raw id: fail toward reporting, never toward silence.
- `LaunchReport` grows `awaiting_confirmation: bool`, computed by a `Launch` domain method (current gate requires confirmation, every blocking condition satisfied, no approving approval recorded, not graduated).
- The report's step entries carry the step's owning `Discipline` (the playbook is already loaded to build the report), and the at-risk evaluation names the overdue blocking steps that produced it (`LaunchDateAtRisk.overdue_steps` already does). The report is the whole of what briefing may know — per-discipline collapse and at-risk evidence both read from it, never from the playbook.

### 2. Cause order is data, collapse is code — realized minimally

The collapse mechanism takes raw findings grouped per product and a `CauseOrder` (an ordered tuple of cause identifiers, supplied by the caller as data). Launch supplies three causes, in order: `launch-date-at-risk`, `gate-awaiting-confirmation`, `overdue-step`. Collapse rules:

- Findings that share a cause and a product collapse into one item, with the individual facts (step ids, due periods) attached as evidence.
- The at-risk finding *absorbs* the overdue blocking steps that produced it — they are its evidence, not sibling items. One struggling launch is one leading item, not one alert per step.
- Within one product's items, the higher-ranked cause precedes the lower, so the causal thing leads; ordering across products is presentation, not a domain rule.

Alternative considered: a fully general causal graph (any finding may subsume any other). Rejected — slice 5 has exactly one absorption relationship, and the map's monitoring order is also a flat ranked list; the graph can be introduced when a real second absorption case exists.

### 3. Severity: three tiers in `shared`, launch mapping fixed as data

`Severity = MONITOR | DIAGNOSE | CRITICAL` in `shared/domain/severity.py`. These are the reporting tiers of the map's `SignificanceTier` scale (its `<10%` band is "noise" — below reporting, so never an item, not a severity). Launch-side grading, recorded in the spec: at-risk launch date → `CRITICAL` (a binary event, and the map says binary events are always critical); gate awaiting confirmation → `DIAGNOSE` (a human decision is due and progression is paused on it); overdue non-blocking step → `MONITOR`. Monitoring's percentage bands grade into the same three tiers in slice 7 — one vocabulary, never a second scale to reconcile.

Evidence stays a briefing-owned value (`AttentionItem.evidence`: the facts the item summarizes, each naming its source — step id, gate id, due period). `EvidenceRef` is *not* promoted to `shared` yet: only briefing speaks it today, and the kernel rule is that vocabulary moves to `shared` when a second module needs it, not before.

### 4. Digest semantics ⇒ the `Briefing` aggregate is assembled, not persisted

Each run assembles a fresh `Briefing` (period, audience, items) and either delivers it or — when clean — deliberately does not. Invariants live on the aggregate: a clean briefing cannot be rendered for delivery; every item carries product, severity, and at least one piece of evidence. No repository, no table. If routing/audit later wants history (the map's open question on `Recommendation` and ClickUp routing), persistence is added then; nothing here forecloses it.

The assembly use case takes the audience as a parameter even though slice 5 only ever passes the one monitoring channel — the day-one shape the map's scope-awareness constraint asks for, enforced for real in slice 6.

### 5. Composition: worker-injected closed callables, the `clickup_sync_job` pattern

`briefing/infrastructure/driving/daily_briefing_job.py` declares module-level injection points — a launch-reports reader, a product-name reader, and the notifier — and `worker.py` (outside the import-linter containers, where naming both sides is legal) composes them from launch's and catalog's public surfaces plus their repositories. Briefing's infrastructure cannot import `launch.infrastructure` or `catalog.infrastructure`, so the callables must arrive closed over their sessions and stores, exactly as `clickup_sync_job.read_product` does today.

Product names: item rendering shows name and SKU, read through catalog's existing `get_product_by_id`; a product the catalog cannot resolve is rendered by its raw id rather than dropped — a briefing must not lose an item to a naming failure.

### 6. The Slack notifier moves to briefing; the daily digest is deleted whole

`slack_notifier.py` moves from `catalog/infrastructure/driven/` to `briefing/infrastructure/driven/` — the map makes briefing the owner of delivery discipline, and with the digest gone catalog has no Slack concern left. `worker.py` re-points the `overdue_check.notifier` injection at briefing's copy. Deleted: `catalog/application/daily_digest.py`, `catalog/infrastructure/driving/daily_digest_job.py`, `run_daily_digest` from catalog's surface, `launch/application/pending_cadence.py` and its export. The briefing job takes the digest's place in `registrations.py` and inherits its schedule slot and tolerance (same daily cron, tolerance per `scheduled-jobs`' rule that it exceed the longest scheduling gap).

Alternative considered: notifier to `shared/infrastructure` (it imports nothing business-side). Rejected for now — `overdue_check`'s port-injection design was chosen deliberately and documented; relocating the adapter into `shared` would invite collapsing that seam as a "simplification" in some later cleanup. One mover, one new injection target, no seam changes.

### 7. Failure semantics carry over verbatim, re-anchored on the briefing

From the retired `product-monitoring` requirements, unchanged in substance: a failure to *assemble* (launch or catalog reads fail) fails the run — `scheduled-jobs` retries it, and one message is attempted only once retries are exhausted; a failure to *deliver* an assembled briefing is logged, the run succeeds, no retry (a stale briefing redelivered risks a duplicate for no freshness gain). A clean day is a successful run that posts nothing — the job's own liveness stays visible through `scheduled-jobs`' freshness endpoint and overdue reporting, which is what makes silence trustworthy.

### 8. Import-linter: briefing joins as a first-class container

`commerce_ops.briefing` joins the layers contract and gets the three boundary contracts every module has, modeled on launch's: domain reaches nowhere outside its layer; application may touch only other modules' `application` surfaces (with the same catalog/launch application→domain `ignore_imports` exemptions); infrastructure likewise. Existing modules' forbidden lists grow `commerce_ops.briefing` where they enumerate siblings.

## Risks / Trade-offs

- [Silent-when-clean hides breakage — no message could mean "all clear" or "job dead"] → the job registers with `scheduled-jobs`, so a dead job surfaces through the freshness endpoint and the hourly overdue report; the clean outcome is logged.
- [Removing the daily listing removes the only unconditional daily signal] → accepted at proposal time; Omni answers "what products exist" on demand, and a launch in trouble is exactly what the briefing does report.
- [Digest repeats a long-standing item daily — potential alert fatigue] → accepted as the deliberate semantics (a briefing is a digest, not an alarm); if fatigue materializes, alarm-style suppression is an additive later change (see Non-Goals).
- [Worker-injected callables put real composition in `worker.py`, which no import contract watches] → the pattern is already established twice; the registration-parity test pattern covers the job being registered, and the injected callables are exercised by the job's tests.
- [`awaiting_confirmation` on the report widens launch's public surface for one consumer] → it is launch's own concept (gate opening mode + approval state), belongs there regardless of who reads it, and slice 6's approval flow will need the same fact.

## Migration Plan

No data migration (no new tables, none removed). One deploy of app + worker together: the digest job's registration disappears as the briefing job's appears, and `scheduled-jobs`' first-known anchoring treats the new job identifier as fresh work (no false overdue on day one). Environment variables are unchanged — the moved notifier reads the same `PRODUCT_AGENT_SLACK_BOT_TOKEN` / `PRODUCT_AGENT_MONITORING_CHANNEL_ID`. Rollback is a redeploy of the previous image; the digest job re-registers under its old identifier and its run history is still there.

## Open Questions

- Slack formatting: plain text now; whether the briefing later renders as Block Kit sections per product is presentation-only and can change without touching specs.
- Whether `Briefing` gains persistence when items start routing into ClickUp tasks — tracked on the map as an open question; nothing in this slice forecloses either answer.
