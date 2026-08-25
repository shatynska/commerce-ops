# Tasks — move-principals-to-roster

> **Read `test-manifest.md` in this directory before starting.** The tests
> were derived from the delta specs and committed before implementation, so
> they already state the call shapes the code must satisfy. The manifest is
> not an OpenSpec artifact and is not loaded into the apply phase's context
> automatically; tasks 5.5–5.8 below depend on it.

## 1. Domain: the roster model

- [x] 1.1 Rewrite `access/domain/principals.py` around `Person` (generated UUID id, display name, Slack identity, optional ClickUp user id, `admin`, `active`) with per-entry coherence faults, and a roster-level validation enforcing Slack-identity uniqueness (deactivated entries included) and the last-active-admin floor, all faults reported together via `InvalidRosterError` (same shape as `InvalidPrincipalsError` / `InvalidPlaybookError`).
- [x] 1.2 Delete the grant model: `all_products`, `skus`, `granted_skus`, and the both/neither grant rules go; `PrincipalsDirectory` is replaced by the roster with `entry_for`-equivalent lookup by Slack identity.

## 2. Application: write use cases and resolution

- [x] 2.1 Define the roster store port (`load() -> (rows, version)` / conditional `save`) and the write use cases — `create_person`, `update_person` (Slack identity and id not updatable), `deactivate_person`, `reactivate_person` — each validating the whole resulting roster, attributing the write to its principal, and retrying lost version races the way `playbook_authoring` does.
- [x] 2.2 Collapse `resolve_scope`: active member → `AccessScope.unrestricted()`, deactivated or unknown → `AccessScope.nothing()`; a failed store read resolves to `nothing()` (fail-closed, never an error toward the asker). Delete the `SkuResolver` port and stale-SKU handling.
- [x] 2.3 Make `resolve_admin_capability` async against the roster: fail-closed for unknown, deactivated, and non-admin entries; update its callers (`admin_link`, admin-session dependency).
- [x] 2.4 Export the new use cases and roster read via `access/application/__init__.py` (`__all__`), keeping import-linter's public-surface contract.

## 3. Infrastructure: persistence and bootstrap

- [x] 3.1 Add the roster table model in `access/infrastructure/driven/models.py` and an alembic migration (additive; attribution columns for created/updated/deactivated/reactivated by/on; set-version mechanism matching the step store's).
- [x] 3.2 Implement the Postgres roster store satisfying the port, raising the stale-version error on a lost race.
- [x] 3.3 Delete `principals_loader.py` and `principals.yaml`; remove `load_shipped_principals` from `main.py`.
- [x] 3.4 Declare `BOOTSTRAP_ADMIN_IDENTITY` (optional) in the runtime-configuration definition, and implement the lifespan bootstrap through the validated write path: unconfigured/unreachable store → log the deferred bootstrap and start anyway; readable store with an active admin beyond a lone seed-attributed entry → touch nothing; readable, admin-less + variable → upsert that identity as active admin (display name = the identity) attributed to `system:bootstrap`; readable with only the single seed-attributed admin + variable naming a different identity → seed the new identity, deactivating nothing; readable, admin-less, no variable → refuse startup naming the variable.
- [x] 3.5 Rewire `main.py` and `worker.py`: everything that held the loaded `PrincipalsDirectory` (e.g. `launch_playbook_admin.directory`) now resolves through the roster-backed use cases.

## 4. Roster admin page

- [ ] 4.1 Implement `access/infrastructure/driving/roster_admin.py` + templates: the whole active roster on one page, deactivated people set apart, each entry's attribution (created by/on, most recent change by/on) readable from the page, gated by the existing admin-session dependency; mount the router in `main.py`.
- [ ] 4.2 Create and edit forms: clean writes land through the use cases; a rejected write re-presents the form with every fault and the submitted values; Slack identity renders read-only on edit.
- [ ] 4.3 Deactivate/reactivate actions, with a refused last-admin deactivation surfaced on the page with its explanation.

## 5. Tests

- [x] 5.1 Unit tests for the domain roster rules — written from the delta specs ahead of implementation (`tests/unit/access/application/test_roster_writes.py`).
- [x] 5.2 Unit tests for the write use cases and resolution (`test_roster_writes.py`, `test_roster_scope_resolution.py`, `test_roster_admin_capability.py`).
- [x] 5.3 Unit tests for the bootstrap (`test_roster_bootstrap.py`).
- [x] 5.4 Unit tests for the roster page and `admin-session` over the roster (`tests/unit/access/infrastructure/driving/test_roster_admin_page.py`, `test_admin_session_over_roster.py`).
- [x] 5.5 **Delete the four superseded test files** — their requirements are REMOVED by this change and every one of them imports the loader task 3.3 deletes, so they stop importing the moment it goes: `tests/unit/access/infrastructure/test_principals_loader.py`, `tests/unit/access/application/test_resolve_scope.py`, `tests/unit/access/application/test_admin_capability.py`, `tests/unit/test_main_principals_validation.py`. Do this in the same commit as 3.3, never before it.
- [x] 5.6 **Adapt, do not delete** the tests that only borrow the deleted loader for their fixtures — they cover `admin-session` requirements this change does *not* modify (single-use tokens, bounded sessions, the link-exchange route) and are the only coverage those requirements have: rebuild the `_directory_with_admin` helper in `tests/unit/access/application/test_admin_session_use_cases.py` on the roster and keep its four token/session tests; do the same for the `load_principals` call in `tests/unit/access/infrastructure/test_admin_link_exchange_route.py` and keep all six. The four *revocation and minting* tests in `test_admin_session_use_cases.py` are separately superseded (replacements live in `test_admin_session_over_roster.py`) and may go with 5.5.
- [ ] 5.7 Reconcile the 15 assumptions the manifest records (call shapes, row attribute spellings, page control vocabulary, the bootstrap step's name) against the implementation as it lands — each is a fixture correction with one named correction point. What a test *asserts* — what was persisted, what was not, who is recorded as having done it — must survive unweakened; only the fixture may move.
- [ ] 5.8 Integration-tier coverage the unit tier cannot observe: the Postgres roster store including the stale-version race (mirroring `tests/integration/launch/test_playbook_authoring_live.py`), and the lifespan actually calling the bootstrap step. Write these under `tests/integration/access/`.

## 6. Documentation and verification

- [ ] 6.1 Update `AGENTS.md`'s architecture summary and any README access notes: the principals directory is Postgres-owned roster data, edited only through validated `roster` use cases; note the bootstrap variable in the deploy docs alongside `ADMIN_BASE_URL`.
- [ ] 6.2 Update the `Purpose` paragraphs of `openspec/specs/access-scope/spec.md` and `openspec/specs/admin-session/spec.md` to roster wording (a delta's Purpose is ignored for existing capabilities, so these are edited directly at implementation time).
- [ ] 6.3 Run the full verification (`uv run pytest`, `ruff check`, `ruff format --check`, `mypy`, import-linter) and the alembic migration against a local database.
