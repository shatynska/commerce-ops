## 1. `shared/` scaffold

- [x] 1.1 Create `src/commerce_ops/shared/__init__.py`, `shared/domain/__init__.py`, `shared/application/__init__.py`, `shared/infrastructure/__init__.py`.
- [x] 1.2 Create `shared/infrastructure/driving/__init__.py` and `shared/infrastructure/driven/__init__.py` (both stay flat inside — no further subfolders yet).

## 2. Relocate the health endpoint

- [x] 2.1 Create `shared/infrastructure/driving/health.py`: an `APIRouter` exposing `GET /health`, returning the same `200 {"status": "ok"}` contract currently inline in `main.py`, with no dependency on Postgres or any other external service.
- [x] 2.2 Update `src/commerce_ops/main.py` to be a pure composition root: construct the FastAPI `app` and `include_router` the health router; remove the inline route.
- [x] 2.3 Confirm `tests/unit/test_health.py` passes unmodified — it imports only `app` from `commerce_ops.main`, so no test change is expected; if it fails, that indicates the router wiring in 2.2 broke the contract, not that the test needs updating.

## 3. `products/` scaffold

- [x] 3.1 Create `src/commerce_ops/products/__init__.py`, `products/domain/__init__.py`, `products/application/__init__.py`, `products/infrastructure/__init__.py` — flat inside, no `driving`/`driven` split yet.

## 4. Remove speculative test scaffolding

- [x] 4.1 Remove `tests/unit/{catalog,orders_inventory,support,analytics}/` (including their nested `domain/application/infrastructure` subfolders), leaving `tests/unit/test_placeholder.py` and `tests/unit/test_health.py` at the tier root.
- [x] 4.2 Remove `tests/agents/{catalog,orders_inventory,support,analytics}/`, leaving `tests/agents/test_placeholder.py` at the tier root.
- [x] 4.3 Remove `tests/integration/{catalog,orders_inventory,support,analytics}/`, leaving `tests/integration/test_placeholder.py` at the tier root.

## 5. Documentation

- [x] 5.1 Update README.md's Architecture section: replace the specific `(catalog, orders/inventory, support, analytics)` enumeration with generic wording (domain modules, unnamed), and add a sentence noting module boundaries are established incrementally as domain work actually begins, not fixed upfront from the initial product scope. Also update the Technology section's `(named in Architecture below)` cross-reference (currently pointing at the enumeration being removed) so it doesn't promise names the Architecture section no longer lists.
- [x] 5.2 Update AGENTS.md's Architecture summary: drop the same `(catalog, orders/inventory, support, analytics)` enumeration. Do not duplicate the "established incrementally" sentence here — AGENTS.md's summary already explicitly defers "full rationale and alternatives considered" to README's Architecture section, so that explanation belongs there once, not copied in both places.

## 6. Verification

- [x] 6.1 Run `uv run pytest`, `ruff check`, `ruff format --check`, and `mypy` locally; confirm all pass with no regressions.
- [x] 6.2 Confirm README.md and AGENTS.md no longer name specific domain modules in the Architecture section/summary, and that `products/` is not held up as an example of one of the original four (it is a distinct, concretely-started module — see design.md's Open Questions).
