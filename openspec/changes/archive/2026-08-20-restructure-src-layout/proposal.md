## Why

`src/commerce_ops/` currently holds one flat `main.py`. `tests/` already scaffolds a module/layer tree (`tests/unit/<module>/{domain,application,infrastructure}/` for `catalog`, `orders_inventory`, `support`, `analytics`) guessed from README's Scope section, before any domain module has actually been built. Establishing the real source layout now — before more application code lands — avoids both a mid-project restructure and carrying speculative, unverified module names in the repo. This was worked through in an explore session; this proposal captures the resulting decisions.

## What Changes

- Introduce `src/commerce_ops/shared/` for cross-cutting concerns (not owned by any single bounded context), layered immediately as `domain/`, `application/`, `infrastructure/{driving,driven}` — unlike domain modules, `shared/` is expected to fill quickly (Slack dispatch, the marketplace-adapter layer, the shared Postgres engine/session factory are all named in README as cross-cutting).
- Move the existing `GET /health` route from `src/commerce_ops/main.py` into `shared/infrastructure/driving/health.py`; `main.py` becomes the composition root only (builds the FastAPI app, mounts routers).
- Introduce `src/commerce_ops/products/`, the first real domain module, with a flat `domain/`, `application/`, `infrastructure/` (no `driving`/`driven` split yet — deferred until the module has more than one adapter per direction).
- Do **not** scaffold `catalog/`, `orders_inventory/`, `support/`, or `analytics/` — README's initial four-domain scope list is a planning artifact, not a confirmed set of code module boundaries; only `products/` is concrete work starting now.
- Remove the speculative `tests/{unit,agents,integration}/{catalog,orders_inventory,support,analytics}/` folders (including the nested `domain/application/infrastructure` subfolders under `tests/unit/`), leaving `test_placeholder.py` at each tier root (and, in `tests/unit/`, the pre-existing `test_health.py`). This change does not create a `tests/.../products/` folder either — `products/` has no internal logic yet to unit-test, and the relocated `/health` stays covered by its existing black-box `tests/unit/test_health.py`. Future test folders get added alongside whichever module first needs internal (non-black-box) tests; see design.md's Decisions for why `shared/` itself is layered now without its tests being mirrored yet.
- Adopt `driving`/`driven` (README's own hexagonal-architecture vocabulary — "driving adapters that call into the application layer" / "driven adapters the application layer calls out to") as the naming convention for splitting an `infrastructure/` layer by direction, wherever and whenever that split is actually needed — not "http"/"persistence" or similar protocol/technology-named categories, which don't hold up once Slack (not strictly "http") and the marketplace-adapter layer (not "persistence") are added.
- Generalize README's Architecture-section wording (and AGENTS.md's Architecture summary, which carries the identical domain enumeration): drop the specific `(catalog, orders/inventory, support, analytics)` enumeration in favor of describing domain modules generically, and add a sentence stating module boundaries are established incrementally as domain work actually begins. This directly resolves the `products`/`catalog` staleness risk (see Impact) rather than only flagging it.

## Capabilities

### New Capabilities
None — this is a pure structural refactor. The `health-check` capability's requirements (from `deploy-health-endpoint`, not yet archived) are unchanged: `GET /health` still returns `200` with `{"status": "ok"}` and no external dependency, only its file location and the way it's wired into the FastAPI app change.

### Modified Capabilities
None — see above. `.openspec.yaml` for this change sets `skip_specs: true` accordingly.

## Impact

- `src/commerce_ops/main.py`: becomes a pure composition root; the `/health` route moves out.
- New: `src/commerce_ops/shared/{domain,application,infrastructure/{driving,driven}}/` (mostly empty `__init__.py` scaffolding plus `shared/infrastructure/driving/health.py`).
- New: `src/commerce_ops/products/{domain,application,infrastructure}/`.
- `tests/unit/test_health.py`: no change needed — it imports only `app` from `commerce_ops.main` and drives it through `TestClient`, not the route module directly; must still pass unmodified once `main.py` mounts the relocated router.
- Removed: `tests/{unit,agents,integration}/{catalog,orders_inventory,support,analytics}/` (all nested subfolders), across all three tiers.
- No change to `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, or the CI/CD workflows from `deploy-health-endpoint` — none of them reference source paths deeply enough to be affected by this move (the ASGI entrypoint stays `commerce_ops.main:app`).
- `README.md` and `AGENTS.md`: Architecture section/summary generalized (see above) — no longer names specific domain modules, so `products/` isn't "out of sync" with either document.
- One decision deliberately left open, recorded in `design.md`'s Open Questions rather than resolved here: how to name a further split inside `driven/` once it holds more than the marketplace-adapter layer and Postgres persistence. (The other originally-open question — whether `products/` matches README's `catalog` — is addressed by generalizing README's wording rather than resolved by picking one name over the other; whether `products/` is ultimately the right name is now a standalone modeling question, no longer entangled with stale docs.)
