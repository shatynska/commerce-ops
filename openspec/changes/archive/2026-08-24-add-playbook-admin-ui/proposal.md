## Why

`move-playbook-steps-to-postgres` makes the step set writable through use cases, but the only interfaces the system has — Slack commands and JSON-less internal wiring — are unfit for browsing and editing a ~100-step playbook. The ops manager (and the project owner) need a page where steps can be seen whole, filtered, and edited in place; the decided shape is a server-rendered HTMX page whose front door is a Slack-issued magic link, keeping the project pure Python with identity riding on the Slack principals the `access` module already knows.

## What Changes

- A browser entry path: a Slack slash command that verifies the caller against the principals directory — specifically against a new, explicit admin declaration on the entry, because visibility grants alone must not confer write authority — mints a short-lived single-use token, and replies ephemerally with a link; opening the link exchanges the token for a session cookie. No password store, no OAuth app, no separate user table — Slack is the identity provider.
- An admin page for the playbook's steps, server-rendered (Jinja + HTMX, CSS framework vendored — no Node toolchain, no CDN dependency at runtime):
  - a step table over the full set, filterable by gate and discipline, searchable by description text;
  - inline editing of a step's authorable fields, with a rejected write re-rendering the form carrying **every** fault from the write use case's validation;
  - creating a step (the `mg.*` namespace) and retiring/un-retiring one;
  - reordering steps within their gate — moving a step to a new slot among its gate's steps, so whoever works a gate sees its steps in the order the ops manager intends;
  - seeded `lp.*` fields that the framework owns render read-only where the authoring capability says they are not editable.
- The page consumes **only** the launch module's public application surface — the read port and the `playbook-authoring` use cases from `move-playbook-steps-to-postgres`; no route touches a repository or the domain directly.
- Unauthenticated or non-admin-capable access to any admin route yields the same absence-shaped refusal — the admin surface does not reveal its own existence.

## Capabilities

### New Capabilities

- `admin-session`: the Slack-to-browser bridge — command entry gated by the principals directory, short-lived single-use link tokens, the cookie session they are exchanged for, session expiry, and the fail-closed behavior for unknown askers.
- `playbook-admin`: the steps management page — browsing, filtering and searching the step set; inline edit, create, retire and un-retire flows; full-fault-list rendering on rejected writes; read-only rendering of framework-owned fields.

### Modified Capabilities

- `launch-playbook`: the "steps at the same gate are unordered" rule gives way — steps at the same gate now carry an authored order that the served step set exposes and every consumer follows when listing them. Gates remain the only *commitment* ordering primitive: a step's order says nothing about when a gate opens or what blocks it.
- `playbook-authoring`: a reorder write joins create/update/retire/un-retire — validated whole-set like every other write; a created or un-retired step takes the last slot of its gate.
- `access-scope`: the principals directory gains an optional per-entry admin declaration, orthogonal to visibility grants — a principal added to see products does not thereby gain the admin surface; resolution of the declaration is fail-closed like everything else in the directory.

## Impact

- New: admin routes and templates in `launch/infrastructure/driving/` (the page is a driving adapter, peer to `slack_entry.py`), the session/token machinery in the `access` module's infrastructure, one new Slack command registration.
- New: a reorder use case beside the existing `playbook-authoring` writes, an order column on the step table (one Alembic migration, backfilled from today's serve order), and ordered serving in the step repository.
- New dependencies: Jinja2 templating (FastAPI's standard pairing) and vendored static assets (HTMX, a CSS kit) served by the app itself.
- Depends on: `move-playbook-steps-to-postgres` (the use cases it consumes) and the existing `access-scope` principals directory.
- Unchanged: launch domain and application layers gain nothing UI-shaped; Slack notification/approval flows; the ClickUp loop.
- Not in this change: run monitoring, AI-output review, gate editing, any JSON API — the page is HTML end to end.
