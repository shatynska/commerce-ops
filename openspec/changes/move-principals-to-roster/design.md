# Design — move-principals-to-roster

## Context

See `proposal.md — Why` for motivation. What shapes the approach:

- The `access` module already splits cleanly: `domain/principals.py` (coherence rules, no I/O), `application/use_cases.py` (`resolve_scope`, `resolve_admin_capability`), `infrastructure/driven/principals_loader.py` (the YAML). `AccessScope` lives in `shared` and is threaded through every `catalog`/`launch` read use case — those signatures must not churn.
- `playbook-authoring` (amended by `move-playbook-steps-to-postgres`) established the house pattern for "content edited as data": a whole-set store behind a `Protocol` port, every write validated by constructing the complete result, optimistic set-versioning with retry, attribution recorded on rows, retire-not-delete, refusals that report every fault at once.
- `main.py` currently loads and validates the YAML eagerly before serving. `runtime-configuration` forbids the configuration *check* from touching the network or database; this change first assumed lifespan startup work therefore could, and Decision 4 records how verification falsified that — `database-session` binds the serving process's first read of the connection setting regardless of which hook does the reading.
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

### 4. The seed is a pre-serving step, not a lifespan task

The container's start chain becomes `preflight && alembic upgrade head && seed-admin && exec uvicorn`. The seed runs in its own process, after the migrations that create the roster tables and before the server starts: with a readable roster holding no active admin it upserts the identity `BOOTSTRAP_ADMIN_IDENTITY` names (display name seeded as the identity itself) through the same validated write path as every other write, attributed to a reserved principal (`system:bootstrap`); with an admin already present beyond a lone seeded entry it does nothing; with no admin and no variable it exits non-zero, and the chain stops before the server starts.

*Why not the lifespan* — which is where this change first put it. Reading the roster at startup made the serving process open a database connection before its first request, which `database-session` requires not to happen, and this change wrote no delta for that spec. It was not a paper cut: it broke two `scheduled-runs` freshness tests, which simulate an unreachable database by repointing `DATABASE_URL` and can only do so while no engine built from a working one is cached — the lifespan seed cached one first. Disabling the seed made both pass and restoring it failed them again, so the causation is established rather than assumed. Moving the step out of the serving process removes the violation at its source instead of amending the guarantee or editing the test that detected it.

The relocation also improves how the failure *reads*, though it is worth being exact about how far that goes. The step lives in the container's start command, not in the deploy job, so a failing seed fails the container much as a failing `preflight` or `alembic upgrade head` does — the previous container has already been recreated by then, and the restart policy governs what follows. What changes is legibility: the failure is a named step with its own message, distinguishable from a server that crashed, sitting next to the migration step an operator already reads. Putting it in the GitHub Actions job instead would genuinely fail the deployment once, but the runner has no route to a Postgres service private to the compose network, so in-container is the placement available.

*Why seed-once with a bounded re-assertion*, unchanged: an environment variable that permanently overrides the roster is standing authority invisible to the roster page. Seeding once means the roster is the single truth afterwards, and the bound — the seed re-runs only while the sole active admin is one it created itself and the variable now names someone else — is what keeps a mis-typed first identity recoverable, since the typo'd row is otherwise an active admin nobody can log in as. The bound expires the moment any other admin exists. The seed is one atomic create-or-promote write: composing reactivate-then-update would deadlock on the last-admin floor, every intermediate roster still holding zero active admins.

*Trade acknowledged*: a developer running `uvicorn` directly gets no seed, so a fresh local database has no admin until they run the step by hand. That is the same shape as needing `alembic upgrade head` locally, and the README says so.

### 5. The roster page lives in `access/infrastructure/driving/`, reusing the admin surface's session gate

Same Jinja/plain-form/HTMX-free-fallback shape as `playbook_admin`, mounted alongside it, gated by the same admin-session dependency. Stale-write races on the roster page are surfaced the same way the playbook page surfaces them (the set-version makes this free), but the page spec does not promise it — contention on a tens-of-rows roster edited by admins is negligible, and promising it would couple the page spec to the store pattern.

## Risks / Trade-offs

- **[Lockout by identity typo: the seeded or edited Slack identity is wrong, so no one can request an admin link]** → A typo in the variable is fixed by correcting the variable and redeploying: the seed's bounded re-assertion (decision 4) runs whenever the only active admin is the lone seed-attributed entry, so the corrected identity is seeded alongside the wrong one, logs in, and deactivates it through an ordinary write — the floor permits it, two admins existing at that moment. A typo in a created person is fixed by any other admin — and the last-admin floor guarantees one exists.
- **[A seed-time store fault now blocks serving where it previously degraded]** → Before the relocation an unreadable roster let the server start and fail closed; now it stops the container. Mitigated by `deploy-pipeline` already gating `app` on Postgres reporting healthy, and bounded by the last-admin floor: a roster with no active admin cannot arise from ordinary use, only from a fresh database, so the branch that demands the variable is a first-deploy concern rather than a recurring one.
- **[The seed does not run for a developer starting uvicorn directly]** → The roster simply has no admin until `python -m commerce_ops.seed_admin` is run, exactly as tables do not exist until `alembic upgrade head` is; both are in the README's Setup section.
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
