# Design — move-principals-to-roster

## Context

See `proposal.md — Why` for motivation. What shapes the approach:

- The `access` module already splits cleanly: `domain/principals.py` (coherence rules, no I/O), `application/use_cases.py` (`resolve_scope`, `resolve_admin_capability`), `infrastructure/driven/principals_loader.py` (the YAML). `AccessScope` lives in `shared` and is threaded through every `catalog`/`launch` read use case — those signatures must not churn.
- `playbook-authoring` (amended by `move-playbook-steps-to-postgres`) established the house pattern for "content edited as data": a whole-set store behind a `Protocol` port, every write validated by constructing the complete result, optimistic set-versioning with retry, attribution recorded on rows, retire-not-delete, refusals that report every fault at once.
- `main.py` currently loads and validates the YAML eagerly before serving; `runtime-configuration` forbids the configuration *check* from touching the network or database, but lifespan startup work may.
- The admin surface (`playbook-admin` + `admin-session`) is server-rendered Jinja + plain forms, gated on a session whose authority is re-checked against the directory on each request.

## Goals / Non-Goals

**Goals:**

- One Postgres-backed roster that is simultaneously the principals directory (access), the future assignee pool (step redesign), and the audit of who granted what to whom.
- Zero signature churn outside `access`: `AccessScope` and the read use cases that take it are untouched.

**Non-Goals:**

- Roles / information-kind access — no `role` column ships now; adding one later is an additive migration, and speccing a field with no behavior would invent scope.
- Data migration from `principals.yaml` — the file holds one entry (the owner-admin), which the bootstrap variable reproduces; no migration machinery for one row.
- Any change to how adapters *establish* identity — Slack signing, admin sessions, link tokens all stand.

## Decisions

### 1. Whole-set store with optimistic versioning, mirroring `playbook-authoring`

The roster port is `load() -> (rows, version)` / `save(rows, expected_version)`, and every write use case loads the whole roster, applies its mutation, validates the entire resulting roster in the domain, and saves conditionally on the version.

*Why*: the two cross-row invariants — unique Slack identity and the last-admin floor — are properties of the whole set, exactly like the gate-holding floor. Per-row repositories would need extra locking or constraints to enforce them race-safely; the whole-set pattern gets it for free, is already proven in this codebase, and a roster is small (tens of rows) so loading it whole costs nothing. *Alternative considered*: per-row repository with a DB unique constraint and a `SELECT … FOR UPDATE` admin count — more moving parts, a second validation idiom in the codebase, no benefit at this scale.

### 2. The domain entity is `Person`; `RosterDirectory` replaces `PrincipalsDirectory`

`domain/principals.py` is rewritten (kept under the same module path — the concept is still "who is declared"): `Person` (generated id, display name, Slack identity, optional ClickUp user id, `admin`, `active`) with per-entry faults, and `Roster` enforcing set-level rules (identity uniqueness, last-admin floor at write validation). `InvalidPrincipalsError`'s shape — every fault at once — is retained as `InvalidRosterError`.

Person id is a UUID generated at creation. *Why not the Slack identity as key*: a person must be able to exist (and later receive ClickUp tasks) before or independently of any credential, and step assignees will store these ids — they must never change. The Slack identity is a unique attribute, not the identity of the row, and is immutable through `update` (like a step's identifier) so an id can never be quietly re-pointed at a different human; correcting a wrong one is deactivate-and-recreate.

### 3. Resolution reads the store per request; `resolve_admin_capability` becomes async

`resolve_scope(identity)` becomes: active member → `AccessScope.unrestricted()`, else `AccessScope.nothing()`. `resolve_admin_capability` must now read the store, so it turns async; its callers (`admin_link`, the admin-session dependency) are already in async request paths. *Why not cache the roster in process*: revocation-on-next-request is an existing `admin-session` guarantee; a cache would need invalidation across two processes (web + worker) to keep it. At tens of rows, a read per resolution is the simple correct thing; caching is a later optimization if it ever shows up in profiles.

### 4. Bootstrap is a lifespan startup task, seed-once, deferred when the store is unreadable

In `main.py`'s lifespan (not in `preflight.py` — the configuration check must stay I/O-free): attempt one roster read. If the store is unconfigured or unreachable, log the deferred bootstrap as a fault and continue startup — this preserves `runtime-configuration`'s "importing and starting require no configuration" and `database-session`'s "no connection before first need" guarantees unamended, and the seed simply runs on the next start against a readable store. If the read succeeds and an active admin exists beyond a lone seed-attributed entry, do nothing. If it succeeds and none exists, upsert the entry named by `BOOTSTRAP_ADMIN_IDENTITY` (declared per `runtime-configuration` as optional; display name seeded as the identity itself) as active admin, attributed to a reserved principal string (e.g. `system:bootstrap`) and landing through the same validated write path as every other write; if the variable is absent, refuse to start — refusal fires only on a *readable*, admin-less, variable-less roster, never on an unreachable one. One bounded re-assertion exists: while the roster's only active admin is the single seed-attributed entry (its most recent admin-conferring write attributed to the reserved principal) and the variable names a different identity, the seed runs again for the new identity (deactivating nothing). The seed is one atomic create-or-promote write — composing reactivate-then-update would deadlock on the last-admin floor, every intermediate roster still holding zero active admins. *Why the bound*: without it, a mis-typed first seed is unrecoverable — the typo'd row is the active admin that makes the variable inert, nobody can mint an admin link as it, and the last-admin floor protects it — so the realistic first-boot failure would end in manual database surgery, which this change's whole philosophy disclaims. The bound expires the moment any admin beyond the lone seed exists, so the variable never becomes the standing overlay this decision rejects, and every seed remains visible on the roster page with its attribution. *Why seed-once over a permanent env overlay*: an overlay is standing authority invisible to the roster page; seed-once means that after first boot the roster is the single truth, and the last-admin refusal makes a return to zero admins impossible except by starting from an empty database — exactly the case the seed covers. *Trades acknowledged*: the YAML's "malformed directory stops the process before serving" guarantee is replaced, not lost — invalid rosters are unreachable because only validated writes produce them; and a deploy whose database is misconfigured starts serving an unseeded roster, degrading fail-closed (no one gets in) with the fault logged and the config check reporting the database variable.

### 5. The roster page lives in `access/infrastructure/driving/`, reusing the admin surface's session gate

Same Jinja/plain-form/HTMX-free-fallback shape as `playbook_admin`, mounted alongside it, gated by the same admin-session dependency. Stale-write races on the roster page are surfaced the same way the playbook page surfaces them (the set-version makes this free), but the page spec does not promise it — contention on a tens-of-rows roster edited by admins is negligible, and promising it would couple the page spec to the store pattern.

## Risks / Trade-offs

- **[Lockout by identity typo: the seeded or edited Slack identity is wrong, so no one can request an admin link]** → A typo in the variable is fixed by correcting the variable and redeploying: the seed's bounded re-assertion (decision 4) runs whenever the only active admin is the lone seed-attributed entry, so the corrected identity is seeded alongside the wrong one, logs in, and deactivates it through an ordinary write — the floor permits it, two admins existing at that moment. A typo in a created person is fixed by any other admin — and the last-admin floor guarantees one exists.
- **[Access checks now depend on the database being reachable]** → Fail-closed is preserved (a failed read must resolve as `nothing()` / not-admin, never as an exception reaching the asker — matching `resolve_scope`'s existing "never an error toward the asker" contract); an outage degrades to "no one gets in", never "everyone gets in".
- **[Deleting the YAML removes the last code-reviewed access record]** → Replaced by strictly better attribution: every grant, withdrawal and deactivation carries who/when on the row, visible on the roster page.
- **[`system:bootstrap` attribution string is a convention, not an enforced principal]** → Kept greppable and documented in the module docstring; it never collides with Slack ids (different alphabet).

## Migration Plan

1. Land schema migration (roster table) — additive, deploy-safe.
2. Deploy code with `BOOTSTRAP_ADMIN_IDENTITY` set to the owner's Slack id (the YAML's sole current entry); first boot seeds it.
3. `principals.yaml`, its loader, and the grant fields die in the same change — there is no window where both directories exist.
4. Rollback: redeploy the previous image — the YAML is still in git history, the roster table is ignored by old code and left in place.

## Open Questions

None — the deferred items (roles, assignees) are scoped out by the proposal, not left ambiguous.
