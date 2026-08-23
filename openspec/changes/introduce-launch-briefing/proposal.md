# Introduce the launch briefing

## Why

Slice 5 of `docs/domain-map.md`: the launch engine now records outcomes, due dates, at-risk judgements and gate approvals (slices 3–4), but nobody hears about them unless they ask — the daily Slack message still just lists product names, and `run_pending_cadence_report` is an intentional no-op. The `briefing` bounded context is the convergence point both the TASK side (launch) and the CHECK side (monitoring, slice 7) deliver through; building it stage-generically now, with the launch-side cause order, is what makes slice 7 "mostly data plus one engine" instead of a second reporting system.

## What Changes

- A new `briefing` module (domain + application + infrastructure) — the third bounded context with a domain layer:
  - `AttentionItem` (VO): product · discipline · severity · evidence · due, derived from launch state — at-risk launch dates, overdue steps, and confirmation gates awaiting approval (surfaced as briefing items; interactive Slack approval is deferred to slice 6, when `access` can guard it).
  - `Briefing` (aggregate root): one assembly per period and audience; knows whether it is clean, and **a clean briefing is not sent** (silent-when-clean).
  - **Cause-order collapse — the order is data, the collapse is code**: one collapse mechanism, fed the launch-side order (blocking cause first); one launch in trouble is one item with its symptoms attached, not five alerts.
  - **Digest semantics** (decided at proposal time): each daily briefing reports every attention item currently open, and a clean day sends nothing. No cross-briefing memory, no suppression state, no new tables.
- A daily scheduled briefing job (briefing's driving adapter, governed by `scheduled-jobs`) that assembles from launch's public surface and delivers through the existing Slack notifier port. It **replaces** the daily product-name listing.
- `Severity` joins the shared vocabulary (the tier scale the domain map's `SignificanceTier` grades into); briefing and, later, monitoring both speak it.
- `launch`'s public surface grows the two read affordances briefing needs: enumerating active launches, and a launch report that says when its current gate awaits confirmation. The no-op `run_pending_cadence_report` is retired. **BREAKING** only at the module-API level (an exported no-op is removed); no shipped behavior is lost.
- **BREAKING**: the daily product-name listing is removed — `product-monitoring`'s requirements are superseded by the briefing (its daily-cadence, delivery-failure and read-failure obligations are re-expressed on the briefing report), emptying that spec until slice 7 rebuilds monitoring as the metric registry and evaluation engine.
- `docs/domain-map.md` is updated in this change with what slice 5 settles (living-document rule).

## Capabilities

### New Capabilities

- `briefing`: the convergence-point context — deriving launch-side attention items, cause-order collapse, severity grading, silent-when-clean assembly, and the daily Slack delivery discipline (schedule, delivery-failure decoupling, read-failure surfacing) it inherits from the retired daily listing.

### Modified Capabilities

- `shared-vocabulary`: adds the `Severity` vocabulary (immutable, value-compared, like the existing enums).
- `launch-instance`: active launches become enumerable through the public surface; the launch report additionally states whether the current gate is a confirmation gate whose blocking conditions are satisfied but which lacks an approval.
- `product-monitoring`: all four requirements are removed — the daily cadence and its failure-handling obligations move to `briefing`, re-expressed over the briefing report instead of the product-name listing.

## Impact

- **New code**: `src/commerce_ops/briefing/` (domain, application, infrastructure/driving for the scheduled job).
- **Modified code**: `launch/application` (new read use case, report field, stub removal), `launch/application/pending_cadence.py` deleted, the worker's job registration and notifier wiring, `.importlinter` (briefing may import `launch.application` and `catalog.application` — same pattern as `omni_agent`).
- **Removed behavior**: the daily product-name Slack message (its schedule slot is taken by the briefing job).
- **No new persistence**: digest semantics need no tables; run history and retries come from `scheduled-jobs` as-is.
- **Docs**: `docs/domain-map.md` slice-5 row and briefing section updated.
- **Tests**: `tests/unit/briefing/`, plus updates where `pending_cadence` and the daily listing are exercised today.
