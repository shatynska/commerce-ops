## Context

See `proposal.md` — Why. The facts of the current code that shape the approach:

- Read use cases take stores and filters only: `list_products(store)`, `get_product_by_id(store, product_id)`, `get_product_by_sku(store, sku)` in `catalog`; `read_launch(...)`, `read_launches(...)` in `launch`. No caller identity reaches any of them.
- The composition root (`worker.py`) already closes over modules' public surfaces to build briefing's and the ClickUp sync job's ports — the established pattern for cross-module wiring without cross-module infrastructure imports.
- `briefing/application/ports.py` deliberately avoided importing `launch.application` "for a type alone", using a structural `Protocol`. Any design that makes `catalog` import a type from a new `access` module reintroduces exactly that objection.
- `ProductId` is opaque — generated, never parsed (shared-vocabulary spec). Humans cannot write product identifiers into a config file; SKUs are the human-meaningful unique key.
- The repo already owns one validated, repo-owned definition file: the launch playbook, loaded by `launch/infrastructure/driven/playbook_loader.py`. The principals file follows that precedent, not the Postgres one.
- The recorded guard-split decision (Omni work): "may this person call this" belongs in FastAPI `Depends()` / Slack middleware; graphs and use cases only ever receive an already-resolved scope. This change builds the resolved-scope half; guards arrive with the first user-facing read adapter (the Omni rewiring change).

## Goals / Non-Goals

**Goals:**

- Row-level visibility as a mechanism: every read use case takes an `AccessScope` and filters by it, so the Omni change threads an asker's scope through without touching read semantics.
- Fail-closed resolution: no identity, no entry in the principals file, or an empty grant list all yield a scope that sees nothing.
- Keep the domain free of authentication: nothing in any `domain/` layer knows what a Slack user is.

**Non-Goals:**

- Enforcing anything at a driving adapter — no user-facing read adapter exists yet; the guard mechanism ships with the Omni change that needs it.
- Capability flags (approve-gates, see-finance). They join `AccessScope` with the first change that checks one; adding unread fields now would be vocabulary nobody speaks.
- Scoping write use cases. Writes are a "may this person call this" question — an adapter-guard concern, deferred with the guards.
- Any Postgres persistence for principals, and any admin surface for editing them.

## Decisions

**1. `AccessScope` lives in `shared/domain`, not in `access`.**
Four modules speak it from birth: `access` derives it, `catalog` and `launch` take it as a parameter, `omni_agent` will forward it. The kernel rule — vocabulary moves up when a second module needs it, not before — is satisfied at introduction. The alternative (catalog importing `access.application` for a type alone) is exactly what briefing's structural ports were built to avoid, and a structural protocol for a filtering value with set semantics would be dishonest — equality and construction validation are the point. `AccessScope` stays vocabulary: visibility data plus a `permits(product_id)` predicate, no derivation rules (those are `access`'s), matching how `LifecycleStage` carries `is_temporary` while its transition rules live in `catalog`.

**2. `AccessScope` is visibility-only, three-valued in shape, one type in code: unrestricted, or an explicit (possibly empty) frozen set of `ProductId`s.**
The empty set is the fail-closed default and needs no special member — `permits` is simply false for everything. Unrestricted is a distinct construction, not "the set of all products", because the set of all products is unknowable to a value object and grows after the scope is built.

**3. The principals file is repo-owned YAML, validated at load, following the playbook-loader precedent.**
A small ops team's principals change at code-review cadence; a Postgres table would need registration use cases and an admin path this slice doesn't justify (recorded in the exploration and confirmed by the user, 2026-08-23). The file maps a Slack user ID to either an `all-products` grant or a list of SKU grants. Load-time validation rejects a malformed file (unknown keys, empty grant values, duplicate principal entries) the way the playbook loader rejects an incoherent playbook — but unlike the playbook, which loads lazily on first use, the principals directory is validated eagerly at startup: a lazily-discovered malformed file would turn every asker's resolution into an error, and the change's rule is that resolution never errors toward the asker. A malformed directory is a deploy-time failure, in the spirit of the existing preflight check. The shipped default file declares an empty principals list with a commented example entry — no real grant ships unreviewed; the team's actual principals are added by ordinary code review. Alternatives considered: Postgres (deferred until principals need runtime mutation), environment variables (unstructured, unreviewable).

**4. Grants are written by SKU, scopes are carried by `ProductId`; resolution translates at scope-derivation time.**
Filtering happens where only `ProductId` is available (launch reports carry no SKU), so the scope must hold product identifiers. Humans can only write SKUs. `access`'s scope-resolution use case therefore depends on a consumer-owned port (a SKU-to-product resolver), implemented at the composition root over catalog — the same closure pattern as briefing's ports. No circularity: the resolver is wired with the unrestricted scope by construction, and person scopes derive through it.

**5. A grant naming a SKU no product has confers nothing, and resolution still succeeds.**
Failing the whole resolution would let one stale line in the file lock a person out of everything they legitimately see — fail toward less access, never toward an error that blocks the rest. The unresolved grant is a config defect to surface in logs, not a refusal.

**6. Unknown askers get the empty scope, not an error and not `None`.**
One return type, uniformly fail-closed. Whether an adapter phrases a refusal ("I don't know you") is the adapter's concern in the Omni change; resolution itself only answers "what may this identity see" and the answer for a stranger is "nothing".

**7. Out-of-scope single reads report absence, indistinguishable from nonexistence.**
`get_product_by_id` outside the scope returns the same absence as an unknown identifier. Distinguishing "exists but hidden" from "does not exist" leaks the existence of products the caller may not see, and gives callers two absence cases to handle instead of one.

**8. Internal processes run under the unrestricted scope, wired at the composition root.**
The daily briefing addresses the whole team and the ClickUp sync names lists for every launch; neither impersonates a person. `worker.py` passes the unrestricted scope where it builds their ports — no port shapes change, so `briefing`'s spec and code are untouched.

## Risks / Trade-offs

- [The principals file holds Slack user IDs in the repo] → They are workspace-internal identifiers, not secrets; the file carries no tokens. Acceptable for an internal ops tool, revisit if the repo's audience widens.
- [SKU-to-ProductId resolution snapshots at scope-derivation time] → A product registered after a scope was resolved is invisible until the next resolution. Scopes are resolved per request in practice (nothing caches them in this change), so the window is one request. Recorded so the Omni change does not add caching without noticing this.
- [Every read call site changes signature at once] → Kept mechanical: one added parameter, compiler-checked by mypy; the pre-commit unit tier runs the full suite, so a missed call site cannot land.
- [Breadth: one change touches shared, access, catalog, launch, worker wiring] → Accepted deliberately — splitting the scope parameter from the module that produces scopes would ship an unusable half; the Omni rewiring is already split out as the second change.

## Open Questions

None — the deferred items (guards, flags, Omni tools, interactive approval) are scoped out, not unresolved.
