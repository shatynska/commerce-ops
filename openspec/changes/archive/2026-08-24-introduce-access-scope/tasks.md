## 1. Shared vocabulary

- [x] 1.1 Add the `AccessScope` value object to `src/commerce_ops/shared/domain/` — unrestricted / explicit frozen set of `ProductId`s, `permits(product_id)` predicate, immutable, value-equal — and export it alongside the existing vocabulary.

## 2. The access module

- [x] 2.1 Create the `access` module skeleton (`domain/`, `application/`, `infrastructure/driven/`) and add it to the `.importlinter` contract like the existing modules.
- [x] 2.2 Domain: the principals-directory model — principal entries keyed by Slack user identity, each carrying exactly one visibility declaration (all-products, or a possibly-empty SKU grant list) — with the load-time coherence rules (duplicate identity, empty/padded identity, both-or-neither declaration, malformed SKU grant) rejected with errors naming the offending entry.
- [x] 2.3 Infrastructure: the repo-owned principals YAML file and its loader (parse, validate through the domain model, never persist), validated eagerly at startup so a malformed file fails the deploy rather than any asker's resolution; the shipped default file declares an empty principals list with a commented example entry.
- [x] 2.4 Application: the `resolve_scope` use case — all-products grant → unrestricted scope; SKU grants → the resolved products' identifiers via a consumer-owned SKU-resolver port; unknown SKU grant confers nothing (logged, resolution succeeds); unknown identity → empty scope — and the module's public surface in `application/__init__.py`.

## 3. Scope-aware reads

- [x] 3.1 Catalog: `get_product_by_id`, `get_product_by_sku`, `list_products` take an `AccessScope`; out-of-scope single reads report absence exactly as nonexistence; lists filter to permitted identifiers.
- [x] 3.2 Launch: `read_launch` and `read_launches` take an `AccessScope` with the same absence and filtering semantics.
- [x] 3.3 Update every existing call site and test of the changed signatures — internal-process wiring in `worker.py` (briefing's `read_launch_reports`/`read_product`, the ClickUp sync's product reader) passes the unrestricted scope at the composition root.

## 4. Verification and record

- [x] 4.1 Run the change's derived tests plus the full commit-time tier (`uv run pytest tests/unit tests/agents`), mypy, ruff, and import-linter; run `tests/integration` before push.
- [x] 4.2 Update `docs/domain-map.md`: mark the slice-6 first half realized, recording the settled details — `AccessScope` in `shared` (visibility-only, flags deferred to the first change that checks one), principals as repo-owned YAML granting by SKU, unknown askers fail closed to the empty scope, internal processes wired with the unrestricted scope, out-of-scope reads indistinguishable from absence.
