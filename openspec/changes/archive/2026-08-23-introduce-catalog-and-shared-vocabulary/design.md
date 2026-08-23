# Design — introduce-catalog-and-shared-vocabulary

## Context

See `proposal.md` — Why. Current state: one flat `products` table (spec `launch-instance`) fuses identity and launch position; its only code consumer is the daily digest's `ProductNameReader` (`products/application/ports.py`), satisfied structurally by `ProductRepository`. There is no `Product` domain entity, no lifecycle stage anywhere, and `shared/domain` holds only a ClickUp VO. `.importlinter` enforces layer order per module and application-`__init__`-only cross-module imports.

## Goals / Non-Goals

**Goals**: the `catalog` bounded context with a pure-domain `Product` aggregate; shared identity/stage vocabulary; the table split with a data-preserving migration; the digest re-pointed without behavior change.

**Non-goals**: any launch-gate logic beyond what `launch-instance` already persists; exit-window *enforcement* for temporary stages (later slices — this change only records stage-entry time so the window is derivable); stage-change *history* (only the current stage's provenance is kept; a history table arrives if/when a review workflow needs it); domain-event *dispatch* infrastructure (`StageChanged` exists as a domain object the aggregate returns, with no bus behind it yet).

## Decisions

1. **Module naming — `catalog` owns identity; `listing` reserved for content.** Settled with the product owner (2026-08-23), resolving the domain map's naming-collision open question. The aggregate inside is `Product` — the module name and the aggregate name are separate concerns.

2. **`Discipline` is the ownership word, but the enum ships with the `Track` migration, not here.** The word is settled; materializing the enum now, with the rename deferred, would leave `Track` and `Discipline` coexisting and an unconsumed symbol in `shared`. The next change touching the playbook introduces the shared enum and migrates code + spec in one step. Alternative rejected: introduce the enum now — creates the very two-words problem the decision exists to end.

3. **Singular marketplace, recorded revisit trigger.** `Product` carries one `MarketplaceId` and one optional `Asin` (Amazon-first). Revisit trigger: the first real launch targeting a second marketplace for an existing product, or marketplace API access making multi-market listings actionable — at that point `Product` grows per-marketplace listings and the launch key is reconsidered as (product, marketplace). Until then `Scope.MARKET` on playbook steps stays latent shape, deliberately.

4. **Stage vocabulary in `shared`, transition rules in `catalog`.** The map's shared kernel lists `LifecycleStage` because `monitoring` will key thresholds by stage (slice 7); but "vocabulary, never behavior" means `shared` holds only the stage *shape* (sum type: `Development | Launching(phase) | SteadyState(posture) | Retired`, plus the is-temporary predicate, which is a property of a value, not a transition). The legal-transition table is `catalog` domain code. Alternative rejected: whole state machine in `shared` — puts behavior two modules could argue about into the kernel.

5. **`Retired` is reachable from any stage and terminal.** The map's transition list doesn't cover discontinuation explicitly; business reality is that products get killed in `Development` and mid-`Launching`, and forcing them through a fake graduation to retire them would corrupt the record. Recorded here as the deliberate interpretation.

6. **Temporary = `Launching` and `InventoryOverride`, per the map's explicit sentence.** `Hold`/`Recover` carry forced-decision windows too, but that is briefing-side *enforcement* over time-in-stage, not a property of the stage value; stage-entry time recorded here is the input it will need.

7. **Table split: `catalog` takes over `products`; launch fields move to a new `launch_positions` table.** The `products` table keeps its name and primary keys (stable `ProductId`s), gains `marketplace_id`, `stage` (+ phase/posture representation), `stage_entered_at`, `stage_confirmed_by` (nullable — absent until the first stage change, per the registration-provenance rule in the `product-catalog` delta), and drops `playbook_version`, `current_gate`, `launch_date` — which move to `launch_positions (product_id PK/FK, playbook_version, current_gate, launch_date)`. One-per-product is the PK. Alternative rejected: new `catalog_products` table plus data copy — churns the stable identifier column for no benefit.

8. **Migration backfill.** Existing rows (dev/test data only at this point) get `marketplace_id` backfilled with the Amazon US marketplace and `stage` backfilled to `Launching` phase 1 with a migration-named confirmer, since every existing row is a launch-in-progress record by construction. `stage_entered_at` is backfilled with the migration time. Each existing row also gets a `launch_positions` row carrying its current values.

9. **The daily digest moves into `catalog`.** (Amended during implementation, settled with the product owner 2026-08-23.) The original wording — `products.application` importing `catalog.application` — left the digest *job* (a driving adapter in `products.infrastructure`) needing to construct `catalog`'s repository, which the module-boundary contract forbids, and `catalog.application` cannot export its own adapter without violating the layer rule. Post-split, "which products exist" is catalog's question, so the digest use case, its job, and its Slack notifier relocate to `catalog` (whose own driving adapter may freely use its own repository); `worker.py` registers the job from its new home. Alternatives rejected: composition-root injection via `worker.py` (respects the rules but adds injection machinery for a job that naturally belongs to catalog); a recorded module-boundary exception (weakens the architecture rule for every future module). The `products`-module repository shrinks to the launch-position record.

10. **No driving adapters for catalog yet.** Registration and stage changes are exercised through use cases (tests, and later Slack/HTTP slices). Building an HTTP surface now would invent an interface no consumer asked for.

## Risks / Trade-offs

- [Data migration drops/moves columns — destructive if rolled back naively] → migration written as paired upgrade/downgrade with the downgrade re-fusing the columns; verified against a seeded database in the integration tier.
- [`launch-instance`'s by-SKU read disappears; some caller may depend on it] → repository search shows the only consumer is `list_names()`; the delta's REMOVED entry records the replacement path (resolve SKU in catalog).
- [Two sources could disagree on "which products exist" during the transition] → the split keeps one `products` table; `launch_positions` is strictly subordinate (FK), so no dual ownership window exists.
- [Stage backfill guesses `Launching` phase 1 for existing rows] → acceptable: only dev/test rows exist; the confirmer field names the migration so the guess is auditable.

## Migration Plan

1. Alembic migration: add catalog columns to `products` (nullable → backfill → non-null, except `stage_confirmed_by`, which stays nullable per Decision 7), create `launch_positions`, copy launch fields, drop them from `products`.
2. Deploy is a single service; no rolling-compatibility window needed.
3. Rollback: `alembic downgrade` one revision re-fuses the columns from `launch_positions`. A product with no `launch_positions` row (registered catalog-only after the upgrade) is dropped by the downgrade — the pre-split schema cannot represent a product without launch fields, and inventing them would be worse; acceptable for a dev-time rollback and asserted by the task 4.3 test.

## Open Questions

None — the deferrable unknowns (exit-window enforcement, stage history, event dispatch) are recorded as non-goals with the slice that owns each.
