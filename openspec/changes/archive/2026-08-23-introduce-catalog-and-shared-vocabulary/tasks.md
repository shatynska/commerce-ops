# Tasks — introduce-catalog-and-shared-vocabulary

## 1. Shared vocabulary

- [x] 1.1 Add identity value objects (`ProductId`, `Sku`, `Asin`, `MarketplaceId`) to `shared/domain` with construction-time validation (non-empty, no surrounding whitespace, ASIN ten alphanumerics), immutability, and value equality
- [x] 1.2 Add the `LifecycleStage` vocabulary to `shared/domain`: `Development | Launching(phase 1–4) | SteadyState(posture) | Retired`, posture set, phase-range validation, and the is-temporary predicate
- [x] 1.3 Unit tests for the vocabulary under `tests/unit/shared/domain/`

## 2. Catalog domain

- [x] 2.1 Create `catalog/domain` with the `Product` aggregate: identity fields, name, current stage, stage-entry time, stage-change provenance (confirmer, timestamp), and the legal-transition table (including any-stage → `Retired`, terminal `Retired`, graduation requiring an explicit posture, no self-chosen posture)
- [x] 2.2 Model `StageChanged` as a domain object the aggregate returns on a successful transition (no dispatch infrastructure)
- [x] 2.3 Unit tests for the aggregate's transitions and rejections under `tests/unit/catalog/domain/`

## 3. Catalog application and infrastructure

- [x] 3.1 Create `catalog/application`: use cases (register product, record ASIN, change stage, get by id, get by SKU, list with stages), consumer-owned ports, and the module's `__init__.py` public surface
- [x] 3.2 Create `catalog/infrastructure/driven`: SQLAlchemy model for the reshaped `products` table and a repository satisfying the application ports
- [x] 3.3 Extend `.importlinter` contracts to cover the `catalog` module (layer order + public-surface rule)
- [x] 3.4 Unit tests for use cases under `tests/unit/catalog/application/`; integration tests for the repository under `tests/integration/catalog/`

## 4. Table split and launch position

- [x] 4.1 Alembic migration: add `marketplace_id`, stage columns, `stage_entered_at`, `stage_confirmed_by` to `products` (backfill per design.md Decision 8), create `launch_positions`, copy launch fields over, drop them from `products`; paired downgrade re-fuses the columns
- [x] 4.2 Reshape the `products` module's SQLAlchemy model and repository to the launch-position record (create-for-product with FK/existence rejection, one-per-product, gate restriction and default, read/update by product id)
- [x] 4.3 Unit and integration tests for the launch-position record, including migration verification against a seeded database — covering downgrade behavior when catalog-only products (rows with no `launch_positions` record) exist post-upgrade

## 5. Re-point the digest and reconcile artifacts

- [x] 5.1 Move the daily digest into `catalog` (use case + `ProductNameReader` port, scheduled job, Slack notifier — per design.md Decision 9 as amended); rewire `worker.py`'s job registration; fixture-correct the digest tests' imports; confirm digest behavior unchanged
- [x] 5.2 Update `docs/domain-map.md`: record the settled decisions (catalog=identity/listing=content, `Discipline` word, singular marketplace with revisit trigger) in the open-questions section
- [x] 5.3 Update `openspec/specs/launch-instance/spec.md`'s Purpose line to describe the launch-position record (direct edit; the delta covers requirements only)

## 6. Verification

- [x] 6.1 Run `uv run pytest` (unit + agents tiers), `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`, and `lint-imports`; all green
- [x] 6.2 Run the integration tier against a real Postgres (migration up, seeded-data split, downgrade) and confirm green
