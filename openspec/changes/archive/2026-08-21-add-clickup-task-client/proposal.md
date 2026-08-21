## Why

commerce-ops has no way to create or update work in ClickUp, which the ops team uses to track product-related work. Two upcoming flows both need this: a product-agent Slack command that should create a ClickUp task group when a new product is added, and a ClickUp webhook that reacts to a task being completed. Both depend on being able to talk to the ClickUp API — this change adds that foundational capability on its own, before either consumer exists.

## What Changes

- New shared driven adapter that can create a ClickUp task and edit (update) an existing one.
- The target list is supplied by the caller as a parameter (`list_id`) — the adapter is not bound to one list or space, so any module's application layer can use it for a different list.
- Authenticates outbound calls with a `CLICKUP_API_TOKEN` env var. Unlike Slack (where each module owns a distinct Slack app/bot and its own token), ClickUp is authenticated with one workspace-level token, so the credential and the client live in `shared` rather than being duplicated per module.
- No consumer is wired up yet. This capability is standalone; the product-agent task-group flow and the task-completed webhook (separate, later changes) will each call into it.

## Capabilities

### New Capabilities
- `clickup-task-client`: creating and editing ClickUp tasks via the ClickUp REST API, as a reusable shared driven adapter.

### Modified Capabilities
(none)

## Impact

- New code under `src/commerce_ops/shared/infrastructure/driven/` (a ClickUp client module), `src/commerce_ops/shared/application/` (a port/protocol other modules' application layers can depend on, per the existing `ProductNameReader`-style pattern in `products/application/ports.py`), and `src/commerce_ops/shared/domain/` (a plain `ClickUpTask` value object shared by the port and the adapter).
- New dependency: an HTTP client library (`httpx`) for calling ClickUp's REST API — not currently a direct project dependency.
- New env var: `CLICKUP_API_TOKEN`.
- No FastAPI routes, no `main.py` wiring — this change has no driving adapter, only the driven client.
