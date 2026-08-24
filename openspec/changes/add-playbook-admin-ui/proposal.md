## Why

`move-playbook-steps-to-postgres` makes the step set writable through use cases, but the only interfaces the system has — Slack commands and JSON-less internal wiring — are unfit for browsing and editing a ~100-step playbook. The ops manager (and the project owner) need a page where steps can be seen whole, filtered, and edited in place; the decided shape is a server-rendered HTMX page whose front door is a Slack-issued magic link, keeping the project pure Python with identity riding on the Slack principals the `access` module already knows.

## What Changes

- A browser entry path: a Slack slash command that verifies the caller against the principals directory, mints a short-lived single-use token, and replies ephemerally with a link; opening the link exchanges the token for a session cookie. No password store, no OAuth app, no separate user table — Slack is the identity provider.
- An admin page for the playbook's steps, server-rendered (Jinja + HTMX, CSS framework vendored — no Node toolchain, no CDN dependency at runtime):
  - a step table over the full set, filterable by gate and discipline, searchable by description text;
  - inline editing of a step's authorable fields, with a rejected write re-rendering the form carrying **every** fault from the write use case's validation;
  - creating a step (the `mg.*` namespace) and retiring/un-retiring one;
  - seeded `lp.*` fields that the framework owns render read-only where the authoring capability says they are not editable.
- The page consumes **only** the launch module's public application surface — the read port and the `playbook-authoring` use cases from `move-playbook-steps-to-postgres`; no route touches a repository or the domain directly.
- Unauthenticated or unknown-principal access to any admin route yields the same absence-shaped refusal — the admin surface does not reveal its own existence.

## Capabilities

### New Capabilities

- `admin-session`: the Slack-to-browser bridge — command entry gated by the principals directory, short-lived single-use link tokens, the cookie session they are exchanged for, session expiry, and the fail-closed behavior for unknown askers.
- `playbook-admin`: the steps management page — browsing, filtering and searching the step set; inline edit, create, retire and un-retire flows; full-fault-list rendering on rejected writes; read-only rendering of framework-owned fields.

### Modified Capabilities

<!-- none: launch-playbook and playbook-authoring behavior is consumed, not changed -->

## Impact

- New: admin routes and templates in `launch/infrastructure/driving/` (the page is a driving adapter, peer to `slack_entry.py`), the session/token machinery in the `access` module's infrastructure, one new Slack command registration.
- New dependencies: Jinja2 templating (FastAPI's standard pairing) and vendored static assets (HTMX, a CSS kit) served by the app itself.
- Depends on: `move-playbook-steps-to-postgres` (the use cases it consumes) and the existing `access-scope` principals directory.
- Unchanged: launch domain and application layers gain nothing UI-shaped; Slack notification/approval flows; the ClickUp loop.
- Not in this change: run monitoring, AI-output review, gate editing, any JSON API — the page is HTML end to end.
