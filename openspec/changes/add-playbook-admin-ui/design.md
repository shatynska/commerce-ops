## Context

See `proposal.md` — Why. What already exists and constrains the approach:

- The launch module's public surface (`launch/application/__init__.py`, enforced by import-linter) already exports the read port (`Playbooks`) and the authoring writes (`create_step`, `update_step`, `retire_step`, `unretire_step`) with optimistic versioning (`StaleStepSetError`). The admin page is a driving adapter and may consume only this surface.
- The `access` module owns the principals directory (`access-scope`): repo-owned, validated at startup, resolving Slack user identities. It authenticates nothing — adapters establish who is asking.
- Steps are stored in `playbook_steps` (seeded by `d2f8b3c64e17`) and served ordered by identifier; the domain spec until now declared same-gate steps unordered, which this change amends (see the `launch-playbook` delta).
- Project constraints: pure Python, no Node toolchain, no CDN at runtime; Slack is the identity provider; the admin surface must not reveal its own existence to outsiders.

## Goals / Non-Goals

**Goals:**

- One server-rendered page (Jinja + HTMX) covering browse/filter/search, inline edit, create, retire/un-retire, and within-gate reorder — every write through the existing authoring use cases plus one new reorder use case.
- A Slack-to-browser bridge in the `access` module reusable by later admin surfaces, not owned by launch.
- Ordering that is presentation-truth only: it changes listings, never gate semantics.

**Non-Goals:**

- No JSON API, no client-side state beyond what HTMX swaps; no run monitoring or gate editing (proposal — Not in this change).
- No cross-gate ordering primitive: the gate sequence stays the only commitment order.
- No session administration UI (listing/revoking sessions); revocation is editing the principals directory.

## Decisions

**1. Order as a per-step integer slot, unique per gate by construction — not a coherence rule.**
`playbook_steps` gains a `display_order` integer. The reorder use case renumbers the whole gate's live steps in one transaction (as does create/un-retire/gate-change appending); duplicates are impossible by construction, so the load-side coherence rule list is untouched and the giant incoherence requirement needs no delta. The repository read becomes `ORDER BY gate position, display_order, identifier` (identifier as deterministic backstop only). *Alternative considered:* fractional/lexicographic ranks to avoid renumbering — rejected: a gate holds tens of steps at most, renumbering is one UPDATE per gate, and integers stay legible in the database. *Alternative considered:* promoting order-uniqueness to a coherence rule — rejected as unfalsifiable by authors: no write can produce the fault, so the rule would be dead validation.

**2. Migration backfills today's order.** One Alembic migration adds `display_order NOT NULL` backfilled from the current serve order (identifier sort within gate), satisfying the delta's "keeps the order it was being served in". Rollback drops the column; serving falls back to identifier order.

**3. Reorder use case shape.** `reorder_step(store, step_id, target_index, expected_version, principal, today)` beside the existing writes, exported from `launch/application/__init__.py`. Target index counts the gate's live steps; the moved step's provenance records the principal/date (symmetric with `update_step`). Whole-set validation and the version bump run exactly as in the other writes — same `_validate`, same `StaleStepSetError` path.

**4. Authorization predicate: an explicit admin declaration on the directory entry, not membership.**
`access-scope` deliberately supports principals with narrow or even empty visibility grants; letting mere membership confer playbook write authority would hand the most consequential write surface to identities added for read purposes. So the principals directory gains an optional per-entry admin declaration (see the `access-scope` delta): visibility grants and admin capability are orthogonal, resolution is fail-closed, and revocation stays what it already is — editing the repo-owned file. *Alternative considered:* membership-as-predicate, recorded as a deliberate decision — rejected: the empty-grant principal is a spec'd case, not a hypothetical, and one optional field in an already-validated file costs nearly nothing.

**5. Session machinery lives in `access` infrastructure, stored in Postgres, no new crypto dependency.** Two small tables: `admin_link_tokens` (random 256-bit opaque value stored **hashed**, principal, expiry ≤10 min, spent flag) and `admin_sessions` (random session id stored hashed, principal, expiry ≤12 h). Single-use requires server state anyway, and a stored session gives request-time revocation for free — every admin request re-resolves the session's principal against the directory, so removal from the repo-owned file revokes on the next request with no extra machinery. *Alternative considered:* signed stateless cookies (itsdangerous) — rejected: adds a dependency, still needs a store for single-use tokens, and makes directory-removal revocation a special case instead of the default.

**6. How the session check crosses the module boundary.** The `access` module exposes three use cases on its public application surface — `mint_admin_link`, `exchange_link_token`, `verify_admin_session` — behind application-level ports (`LinkTokenStore`, `AdminSessionStore` protocols in `access/application/ports.py`), with the Postgres stores implementing them in `access/infrastructure`. The Slack command handler and the token-exchange route are `access`'s own driving adapters (`access/infrastructure/driving/`). The playbook page's FastAPI dependency lives with the page, in `launch/infrastructure/driving/`: a thin wrapper that reads the cookie and calls `verify_admin_session` through the access module's public surface — a driving adapter consuming another module's application surface, exactly the sanctioned direction, so import-linter stays clean without exceptions.

**7. Absence-shaped refusal = the app's own 404.** Every failed admin request — no session, expired, spent token, unknown token, unknown principal — returns the exact response FastAPI gives for an unregistered route, produced by one dependency so the shape cannot drift per-route. The Slack command's refusal for unknown callers is a generic ephemeral message with no URL.

**8. Page composition.** Admin routes and Jinja templates live in `launch/infrastructure/driving/` (peer to `slack_entry.py`); the sender-rights check sits in the FastAPI dependency of decision 6, not in page logic, matching how Slack entry guards are placed. HTMX drives row-level swaps (edit form in/out, reorder via up/down buttons posting the reorder write — buttons, not drag-and-drop, keep it dependency-free and keyboard-accessible). HTMX and the CSS kit are vendored under a static directory served by the app. New runtime dependency: Jinja2 only.

## Risks / Trade-offs

- [Magic link leaks (Slack logs, shoulder surfing)] → ephemeral-only reply, ≤10-minute expiry, single use, token hashed at rest so a database read does not yield a usable link.
- [Session cookie theft] → HttpOnly + Secure (deployed) + SameSite=Lax; bounded 12-hour lifetime; directory removal revokes on next request.
- [Concurrent authoring races (two admins, or admin vs. future flows)] → the step-set version already serializes writes; the page renders the stale-write case explicitly instead of retrying silently.
- [Reorder changes ClickUp projection iteration order] → projection order was never a spec'd promise of `launch-clickup-sync`; task identity is by step id, so reconciliation is unaffected. Benign, but noted so a reviewer isn't surprised.
- [Up/down buttons are clumsy for long gates] → accepted for this change; drag-and-drop is an enhancement that can ride the same reorder write later.
- [Session expires during an HTMX partial write] → the server answers with the absence-shaped 404 (no exception for fragments — the shape must not drift). The page's HTMX error hook treats any 404 on a swap as "session ended" and replaces the whole page with a neutral signed-out view, telling the admin to mint a fresh link; the in-flight form values are lost. Accepted limitation for the page's single-admin audience — the client-side hook reveals nothing a session holder didn't already know.

## Migration Plan

1. Deploy the migration (add + backfill `display_order`) — additive, no downtime; readers before the code deploy still order by identifier, which the backfill equals.
2. Deploy the code (ordered serving, reorder use case, access-session tables via the same release's migration, admin routes, Slack command registration).
3. Rollback: revert the deploy; dropping `display_order` loses authored order but nothing else — steps revert to identifier order.

## Open Questions

- Cosmetics of the page (CSS kit choice among vendorable options) — deferrable, does not affect specs or tasks.
