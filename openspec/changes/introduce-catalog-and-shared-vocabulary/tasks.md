# Tasks — introduce-catalog-and-shared-vocabulary

## 1. Shared vocabulary

- [ ] 1.1 Add identity value objects (`ProductId`, `Sku`, `Asin`, `MarketplaceId`) to `shared/domain` with construction-time validation (non-empty, no surrounding whitespace, ASIN ten alphanumerics), immutability, and value equality
- [ ] 1.2 Add the `LifecycleStage` vocabulary to `shared/domain`: `Development | Launching(phase 1–4) | SteadyState(posture) | Retired`, posture set, phase-range validation, and the is-temporary predicate
- [ ] 1.3 Unit tests for the vocabulary under `tests/unit/shared/domain/`

## 2. Catalog domain

- [ ] 2.1 Create `catalog/domain` with the `Product` aggregate: identity fields, name, current stage, stage-entry time, stage-change provenance (confirmer, timestamp), and the legal-transition table (including any-stage → `Retired`, terminal `Retired`, graduation requiring an explicit posture, no self-chosen posture)
- [ ] 2.2 Model `StageChanged` as a domain object the aggregate returns on a successful transition (no dispatch infrastructure)
- [ ] 2.3 Unit tests for the aggregate's transitions and rejections under `tests/unit/catalog/domain/`

## 3. Catalog application and infrastructure

- [ ] 3.1 Create `catalog/application`: use cases (register product, record ASIN, change stage, get by id, get by SKU, list with stages), consumer-owned ports, and the module's `__init__.py` public surface
- [ ] 3.2 Create `catalog/infrastructure/driven`: SQLAlchemy model for the reshaped `products` table and a repository satisfying the application ports
- [ ] 3.3 Extend `.importlinter` contracts to cover the `catalog` module (layer order + public-surface rule)
- [ ] 3.4 Unit tests for use cases under `tests/unit/catalog/application/`; integration tests for the repository under `tests/integration/catalog/`

## 4. Table split and launch position

- [ ] 4.1 Alembic migration: add `marketplace_id`, stage columns, `stage_entered_at`, `stage_confirmed_by` to `products` (backfill per design.md Decision 8), create `launch_positions`, copy launch fields over, drop them from `products`; paired downgrade re-fuses the columns
- [ ] 4.2 Reshape the `products` module's SQLAlchemy model and repository to the launch-position record (create-for-product with FK/existence rejection, one-per-product, gate restriction and default, read/update by product id)
- [ ] 4.3 Unit and integration tests for the launch-position record, including migration verification against a seeded database — covering downgrade behavior when catalog-only products (rows with no `launch_positions` record) exist post-upgrade

## 5. Re-point the digest and reconcile artifacts

- [ ] 5.1 Rewire the daily digest's product-name read to `catalog`'s public surface; delete the now-unused `ProductNameReader` path if nothing else consumes it; confirm digest behavior unchanged
- [ ] 5.2 Update `docs/domain-map.md`: record the settled decisions (catalog=identity/listing=content, `Discipline` word, singular marketplace with revisit trigger) in the open-questions section
- [ ] 5.3 Update `openspec/specs/launch-instance/spec.md`'s Purpose line to describe the launch-position record (direct edit; the delta covers requirements only)

## 6. Verification

- [ ] 6.1 Run `uv run pytest` (unit + agents tiers), `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `lint-imports`; all green
- [ ] 6.2 Run the integration tier against a real Postgres (migration up, seeded-data split, downgrade) and confirm green
