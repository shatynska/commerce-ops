# Move Principals to a Postgres Roster

## Why

The upcoming step-entity redesign gives playbook steps assignees — humans who receive ClickUp tasks and answer Slack confirmations — which requires a directory of people with names and per-service identities that no capability currently owns. The existing principals directory cannot grow into that role: it is a repo-owned YAML file, so onboarding a person requires a code change and a deploy (blocking whenever no developer is available, and its code-review audit rationale is hollow on a single-developer project that self-approves PRs), and its product-grant axis (`all_products`/`skus`) contradicts the settled access policy — every declared person may see every product, with future differentiation planned by *information kind* (e.g. financial data), never by product.

## What Changes

- A new Postgres-backed **roster** replaces the repo-owned principals directory: one person per row, with a generated identifier, a display name, a unique Slack identity, an optional ClickUp user id, an admin flag, an active flag, and a full attribution trail (who created/updated/deactivated/reactivated, when) — the audit that the YAML's git trail was supposed to provide, made first-class.
- The roster is edited only through validated use cases (create, update, deactivate, reactivate), with coherence guarded at every write — the same write-validation discipline `playbook-authoring` established. **The write that would leave the roster without an active admin is rejected whole** (last-admin refusal); people are deactivated, never deleted.
- **BREAKING**: product visibility grants are removed. An active roster member resolves to the unrestricted scope; an unknown or deactivated identity — and any resolution that cannot read the roster store — resolves to the scope permitting nothing. Access stays fail-closed; the `AccessScope` vocabulary and the read use cases filtering by it are untouched.
- **BREAKING**: `principals.yaml` and its loader are deleted. Admin capability resolves from the roster row's admin flag; `admin-session`'s contract (fail-closed, revocation effective on the next request) is unchanged, now reading the roster.
- **Bootstrap**: a seeding step runs between the database migration and the server — its own process, never the server's startup — making the identity a declared environment variable names the first active admin, so a fresh deployment is administrable without a permanent out-of-band authority. Keeping it out of the serving process is what preserves `runtime-configuration`'s empty-environment startup guarantee and `database-session`'s rule that the connection setting is read no earlier than the first session request. A roster with no active admin and no identity to seed — and a store the step cannot read — each fail that step, and the server does not start.
- The admin surface gains a **roster page**: list the roster whole, create and edit people, deactivate/reactivate — server-rendered like the playbook page, with a rejected write reporting its faults and re-presenting the submitted values.

Deliberately out of scope: roles / information-kind access (a later change adds a role field when there is behavior to hang on it), and step assignees themselves (the follow-up step-entity change references roster ids).

## Capabilities

### New Capabilities

- `roster`: the people directory — the person entity and its coherence rules, the validated write use cases with attribution, last-admin refusal, deactivation-not-deletion, and the pre-serving bootstrap of the first admin.
- `roster-admin`: the admin surface's roster page — listing, creating, editing, deactivating and reactivating people from the browser.

### Modified Capabilities

- `access-scope`: the principals directory's source moves from a repo-owned validated file to the roster; product-grant resolution (all-products / SKU lists / stale-SKU tolerance) is removed in favor of active-member → unrestricted, otherwise → nothing; admin capability resolves from the roster row. Fail-closed resolution is retained and extended to an unreadable store.
- `admin-session`: contract unchanged in substance; its link-minting and revocation requirements are re-stated against the roster — deactivation is the roster's form of removal, since entries are never deleted.

## Impact

- **`access` module**: `domain/principals.py` rewritten around the person/roster model; `infrastructure/driven/principals_loader.py` and `principals.yaml` deleted; new Postgres model, migration and store; new application use cases exported via `application/__init__.py`; new driving adapter for the roster page. `admin_link` keeps its contract, resolving admin capability against the roster.
- **`catalog` / `launch` read use cases**: no change — `AccessScope` remains their filter parameter; only the resolutions it can carry narrow to unrestricted/nothing.
- **`main.py` startup**: the eager YAML load-and-validate is removed and nothing replaces it — the lifespan reads no database, and directory faults can no longer exist as load faults because the store only ever holds what validated writes produced. The first admin is seeded by `commerce_ops.seed_admin`, a step of its own.
- **Deploy / configuration**: one new declared environment variable for the bootstrap admin identity; a new table and migration; and the container's start chain gains the seeding step between the migration and the server (`deploy-pipeline` delta).
- **Follow-up dependency**: the step-entity redesign (assignees, execution kinds, lifecycle) builds on roster ids and is proposed separately.
