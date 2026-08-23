# Introduce the catalog context and the shared vocabulary

## Why

The domain map's target shape (slice 1 of its path) has no code yet: product identity, lifecycle stage, and launch position are fused into one flat `products` row owned by the launch side, there is no `Product` domain entity at all, and the shared kernel holds no domain vocabulary. Every later slice — the `Launch` aggregate, briefing, monitoring's stage-keyed thresholds — needs a `catalog` context to read the stage stamp from and a shared vocabulary to speak; this change builds that foundation while the surface area is still small (one table, one consumer).

This change also settles three open questions the domain map gates slice 1 on, as decided with the product owner:

- **Naming**: `catalog` = product identity & lifecycle (this module); the future listing-*content* context will be named `listing`. The ownership tag is **`Discipline`** (today's `Track` migrates when a change next touches the playbook).
- **Multi-marketplace**: `Product` carries a singular `MarketplaceId` and optional `Asin` for now (Amazon-first); the revisit trigger is recorded in `design.md`.

## What Changes

- A new `shared` domain vocabulary: identity value objects (`ProductId`, `Sku`, `Asin`, `MarketplaceId`) and the `LifecycleStage` vocabulary (stage names, launch phases, postures) — vocabulary only, no transition rules.
- A new `catalog` module (domain, application, infrastructure) owning the `Product` aggregate: identity, name, and the lifecycle-stage state machine (`Development → Launching(phase 1..4) → SteadyState(posture) → Retired`, postures `Scale/Optimize/Hold/Recover/InventoryOverride`), with legal-transition enforcement, human-confirmed stage changes, and a `StageChanged` domain event.
- **BREAKING**: the flat `products` table splits. Catalog owns product identity + stage; the launch-position fields (`playbook_version`, `current_gate`, `launch_date`) move to a launch-owned record referencing the product by `ProductId`. Alembic migration included.
- The daily digest's product-name read is re-pointed at `catalog`'s public surface.
- `.importlinter` contracts extended to cover the new `catalog` module; `docs/domain-map.md`'s open questions updated with the settled decisions.

Out of scope: the `Launch` aggregate and gate evaluation (slice 3); the `Track` → `Discipline` migration together with the shared `Discipline` enum itself (they land in one change the next time the playbook is touched, so two words for one concept never coexist); vocabulary with no consumer yet (`Severity`, `Verdict`, `EvidenceRef`, `MetricId` arrive with briefing/monitoring); and any HTTP/Slack driving surface for catalog beyond what the digest already needs.

## Capabilities

### New Capabilities

- `shared-vocabulary`: the domain terms every module speaks — identity value objects and their validation rules, and the `LifecycleStage` vocabulary shape. No behavior beyond construction-time validation.
- `product-catalog`: the `Product` aggregate — identity and lifecycle stage, legal stage transitions (including temporary-state semantics), human-confirmed stage changes, persistence and read-back by id or SKU.

### Modified Capabilities

- `launch-instance`: the persisted record no longer owns product identity (SKU, ASIN, name move to `product-catalog`); it becomes a launch-position record (playbook version, current gate, launch date) referencing a catalog product. Gate-value restrictions and read/update behavior carry over unchanged.

## Impact

- **Code**: new `src/commerce_ops/catalog/` module; `src/commerce_ops/shared/domain/` gains vocabulary modules; `products` module's repository/model shrink to the launch-position record; `products/application/ports.py`'s name-reader consumer rewired to catalog's public surface.
- **Database**: one Alembic migration splitting the `products` table (data-preserving for existing rows).
- **Specs**: two new capability specs; `launch-instance` delta.
- **Tooling**: `.importlinter` module list; no dependency changes.
- **Docs**: `docs/domain-map.md` open-questions section records the three settled decisions.
