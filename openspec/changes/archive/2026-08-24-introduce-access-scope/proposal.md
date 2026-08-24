## Why

Slice 6 of `docs/domain-map.md` requires that before Omni answers arbitrary askers in Slack, the system can say which products a caller may see — and the map's standing constraint is that every read model is scope-aware from day one, not retrofitted. Today no access concept exists anywhere: `list_products`, `read_launches` and their siblings answer with everything, for anyone who can reach them. This change builds the `access` module and threads a visibility scope through every read use case, so that the follow-up change (Omni rewired over the modules' public surfaces) can pass an asker's scope down without touching read semantics again. It is deliberately the first half of slice 6: Omni's rewiring, adapter guards, capability flags, and interactive gate approval are all out of scope here.

## What Changes

- A new `AccessScope` value object joins the shared vocabulary: a product-visibility scope that is either unrestricted or an explicit set of product identifiers, with an empty scope as the fail-closed default. It moves into `shared` at birth because four modules speak it at once (`access` derives it, `catalog` and `launch` filter by it, `omni_agent` will forward it) — the kernel rule's "a second module needs it" is satisfied on day one.
- A new `access` module (supporting, thin) owns principals and scope resolution: a repo-owned principals file maps Slack user identities to visibility grants expressed by SKU (human-writable, unlike opaque product identifiers); resolving a scope translates grants to product identifiers; an unknown asker resolves to the empty scope — fail closed, never an error.
- **BREAKING** (internal API): every read use case on `product-catalog` and `launch-instance` takes an `AccessScope` parameter and filters by it. A single-product read outside the scope reports absence — indistinguishable from a product that does not exist. List reads return only in-scope rows.
- Internal system processes (the daily briefing job, the ClickUp sync job) are not principals; the composition root wires them with the unrestricted scope. Briefing's own behavior is unchanged.

## Capabilities

### New Capabilities

- `access-scope`: the principals directory (repo-owned, validated at load) and scope resolution — known principal to derived scope, unknown asker to the empty scope, a grant naming an unregistered SKU conferring nothing.

### Modified Capabilities

- `shared-vocabulary`: gains the `AccessScope` value object — unrestricted / explicit-set / empty visibility, construction validation, and the `permits` predicate — under the vocabulary's existing immutability and value-equality rules.
- `product-catalog`: the read requirements ("read back by identifier or by SKU", "products can be listed") become scope-aware — reads take a scope, out-of-scope products report absence, lists filter.
- `launch-instance`: the read requirements ("a launch position can be read back", "launch positions are enumerable") become scope-aware in the same way.

## Impact

- New code: `src/commerce_ops/access/` (domain, application, principals-file loader in infrastructure), `AccessScope` in `src/commerce_ops/shared/domain/`.
- Signature changes: `catalog/application/use_cases.py` (`get_product_by_id`, `get_product_by_sku`, `list_products`), `launch/application/use_cases.py` (`read_launch`, `read_launches`), and their callers — `worker.py` composition wiring for the briefing and ClickUp sync jobs supplies the unrestricted scope. Write use cases are untouched.
- No new database tables, no new external dependencies, no marketplace access. `.importlinter` gains the `access` module under the existing contract.
- Not in this change: Omni's tool rewiring, adapter guards (`Depends()` / Slack middleware), capability flags such as approve-gates, interactive gate approval in Slack. Each of these consumes what this change builds.
