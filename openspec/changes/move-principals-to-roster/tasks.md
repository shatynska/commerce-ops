# Tasks — move-principals-to-roster

## 1. Domain: the roster model

- [ ] 1.1 Rewrite `access/domain/principals.py` around `Person` (generated UUID id, display name, Slack identity, optional ClickUp user id, `admin`, `active`) with per-entry coherence faults, and a roster-level validation enforcing Slack-identity uniqueness (deactivated entries included) and the last-active-admin floor, all faults reported together via `InvalidRosterError` (same shape as `InvalidPrincipalsError` / `InvalidPlaybookError`).
- [ ] 1.2 Delete the grant model: `all_products`, `skus`, `granted_skus`, and the both/neither grant rules go; `PrincipalsDirectory` is replaced by the roster with `entry_for`-equivalent lookup by Slack identity.

## 2. Application: write use cases and resolution

- [ ] 2.1 Define the roster store port (`load() -> (rows, version)` / conditional `save`) and the write use cases — `create_person`, `update_person` (Slack identity and id not updatable), `deactivate_person`, `reactivate_person` — each validating the whole resulting roster, attributing the write to its principal, and retrying lost version races the way `playbook_authoring` does.
- [ ] 2.2 Collapse `resolve_scope`: active member → `AccessScope.unrestricted()`, deactivated or unknown → `AccessScope.nothing()`; a failed store read resolves to `nothing()` (fail-closed, never an error toward the asker). Delete the `SkuResolver` port and stale-SKU handling.
- [ ] 2.3 Make `resolve_admin_capability` async against the roster: fail-closed for unknown, deactivated, and non-admin entries; update its callers (`admin_link`, admin-session dependency).
- [ ] 2.4 Export the new use cases and roster read via `access/application/__init__.py` (`__all__`), keeping import-linter's public-surface contract.

## 3. Infrastructure: persistence and bootstrap

- [ ] 3.1 Add the roster table model in `access/infrastructure/driven/models.py` and an alembic migration (additive; attribution columns for created/updated/deactivated/reactivated by/on; set-version mechanism matching the step store's).
- [ ] 3.2 Implement the Postgres roster store satisfying the port, raising the stale-version error on a lost race.
- [ ] 3.3 Delete `principals_loader.py` and `principals.yaml`; remove `load_shipped_principals` from `main.py`.
- [ ] 3.4 Declare `BOOTSTRAP_ADMIN_IDENTITY` (optional) in the runtime-configuration definition, and implement the lifespan bootstrap through the validated write path: unconfigured/unreachable store → log the deferred bootstrap and start anyway; readable store with an active admin beyond a lone seed-attributed entry → touch nothing; readable, admin-less + variable → upsert that identity as active admin (display name = the identity) attributed to `system:bootstrap`; readable with only the single seed-attributed admin + variable naming a different identity → seed the new identity, deactivating nothing; readable, admin-less, no variable → refuse startup naming the variable.
- [ ] 3.5 Rewire `main.py` and `worker.py`: everything that held the loaded `PrincipalsDirectory` (e.g. `launch_playbook_admin.directory`) now resolves through the roster-backed use cases.

## 4. Roster admin page

- [ ] 4.1 Implement `access/infrastructure/driving/roster_admin.py` + templates: the whole active roster on one page, deactivated people set apart, each entry's attribution (created by/on, most recent change by/on) readable from the page, gated by the existing admin-session dependency; mount the router in `main.py`.
- [ ] 4.2 Create and edit forms: clean writes land through the use cases; a rejected write re-presents the form with every fault and the submitted values; Slack identity renders read-only on edit.
- [ ] 4.3 Deactivate/reactivate actions, with a refused last-admin deactivation surfaced on the page with its explanation.

## 5. Tests

- [ ] 5.1 Unit tests for the domain roster rules (delta scenarios: generated id, duplicate Slack identity, faults-together, last-admin refusals, deactivate/reactivate semantics).
- [ ] 5.2 Unit tests for the write use cases (attribution, rejected-write-persists-nothing, identity-not-updatable) and resolution (active → unrestricted, deactivated/unknown → nothing, unreadable store → nothing/not-admin without an error, admin fail-closed) over a fake store.
- [ ] 5.3 Unit tests for the bootstrap (seed on empty with identity-as-name, promote-not-duplicate, inert once an admin beyond the lone seed exists, mis-seed corrected by a changed variable without deactivating anything, refuse startup when readable-admin-less-variable-less, start-and-defer when the store is unreadable).
- [ ] 5.4 Unit tests for the roster page (list whole, set-apart, fault re-presentation, blocked deactivation explains itself), following the playbook-admin test idiom.
- [ ] 5.5 Update/remove tests that exercised YAML grants, `SkuResolver`, and the sync `resolve_admin_capability`; integration-tier test for the Postgres store if the step store has one to mirror.

## 6. Documentation and verification

- [ ] 6.1 Update `AGENTS.md`'s architecture summary and any README access notes: the principals directory is Postgres-owned roster data, edited only through validated `roster` use cases; note the bootstrap variable in the deploy docs alongside `ADMIN_BASE_URL`.
- [ ] 6.2 Update the `Purpose` paragraphs of `openspec/specs/access-scope/spec.md` and `openspec/specs/admin-session/spec.md` to roster wording (a delta's Purpose is ignored for existing capabilities, so these are edited directly at implementation time).
- [ ] 6.3 Run the full verification (`uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, import-linter) and the alembic migration against a local database.
