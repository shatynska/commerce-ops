## 1. Within-gate step ordering

- [x] 1.1 Alembic migration: add `display_order` (integer, NOT NULL) to `playbook_steps`, backfilled per gate from the current serve order (identifier sort within gate)
- [x] 1.2 Extend `StepRecord` and the step repository with `display_order`; serve reads ordered by gate position, then `display_order`, then identifier as deterministic backstop
- [x] 1.3 Implement `reorder_step` in `launch/application/playbook_authoring.py` — atomic per-gate renumber, same whole-set validation and version serialization as the other writes, provenance recorded on the moved step; export it from `launch/application/__init__.py`
- [x] 1.4 Make `create_step`, `unretire_step`, and a gate-changing `update_step` append the step to the last slot of its (new) gate; retiring closes the gap without renumbering survivors' relative order
- [x] 1.5 Run the ordering-related tests derived from the deltas (`launch-playbook`, `playbook-authoring`) and make them pass

## 2. Admin session (access module)

- [x] 2.1 Extend the principals directory schema, loader validation, and resolution with the optional per-entry admin declaration — fail-closed, orthogonal to visibility grants, malformed values rejected at load naming the entry
- [x] 2.2 Alembic migration: `admin_link_tokens` (hashed token, principal, expiry, spent flag) and `admin_sessions` (hashed session id, principal, expiry) tables
- [x] 2.3 Implement `mint_admin_link`, `exchange_link_token`, and `verify_admin_session` use cases behind `LinkTokenStore`/`AdminSessionStore` ports in `access/application`, exported on the module's public surface; Postgres store implementations in `access/infrastructure`
- [x] 2.4 Register the Slack slash command as an access driving adapter: mint the token only for callers resolving admin-capable; unknown and visibility-only callers get one and the same no-URL ephemeral refusal
- [x] 2.5 Wire the exchange route (access driving adapter): single-use token swap for the hardened session cookie (HttpOnly, Secure in deployed environments, SameSite=Lax), with spent/expired/unknown tokens refused absence-shaped
- [x] 2.6 Run the `access-scope` and `admin-session` tests derived from the deltas and make them pass

## 3. Playbook admin page (launch driving adapter)

- [x] 3.1 Add Jinja2 dependency; vendor HTMX and the CSS kit under an app-served static directory (no CDN)
- [x] 3.2 Step table route and template: full live set grouped by gate in gate order, steps in authored order; gate and discipline filters; description search; retired steps behind an explicit control, marked as retired
- [x] 3.3 Inline edit flow through `update_step`: row swap on success; rejected writes re-render the form holding submitted values with the full fault list; stale-version conflicts state that the set changed underneath
- [x] 3.4 Create, retire, un-retire flows through their use cases, with the same full-fault rendering on rejection; identifier and discipline (and provenance) render read-only
- [x] 3.5 Reorder controls (up/down per row) posting `reorder_step`; new order rendered immediately and identical on full reload; rejected/stale moves re-render the served order and say why
- [x] 3.6 Guard every admin route with the page's FastAPI dependency (in `launch/infrastructure/driving/`, calling `verify_admin_session` through the access public surface) so unauthenticated or non-admin access is absence-shaped; HTMX error hook renders the signed-out view on a 404 swap
- [x] 3.7 Run the `playbook-admin` tests derived from the delta and make them pass

## 4. Verification and closure

- [x] 4.1 `uv run pytest` across all tiers (unit, agents, integration) green
- [x] 4.2 import-linter clean: admin routes consume only the launch and access public application surfaces
- [x] 4.3 `ruff check`, `ruff format --check`, and `mypy` clean
- [x] 4.4 `openspec validate --strict` passes for the change
- [x] 4.5 At archive time, amend the `access-scope` Purpose in `openspec/specs/access-scope/spec.md` so it also covers answering whether an identity holds the admin write capability
