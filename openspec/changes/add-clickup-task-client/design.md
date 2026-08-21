## Context

See `proposal.md` for motivation. `shared/infrastructure/driven/` currently has no adapters in it; `shared/application/` currently has no ports in it. The closest existing precedent for the shape this change takes is `products/application/ports.py`'s `ProductNameReader` Protocol, structurally satisfied by `ProductRepository` (infrastructure) — used because `products.application` may not import `products.infrastructure` directly under `.importlinter`'s `module-layers` contract. The same constraint applies here one level up: a *business module's* `application` layer may depend on `shared.application`/`shared.domain`, but not on `shared.infrastructure` — only a business module's own `infrastructure` layer may reach all three of `shared`'s layers. So a future consumer's application-layer use case (e.g. change `add-product-launch-clickup-task-group`) must depend on a Protocol defined in `shared.application`, not on this change's concrete client module directly.

ClickUp's REST API (v2) exposes `POST /api/v2/list/{list_id}/task` to create a task and `PUT /api/v2/task/{task_id}` to update one. Auth is a static personal API token sent as-is in the `Authorization` header (no `Bearer` prefix, unlike Slack's bot tokens).

## Goals / Non-Goals

**Goals:**
- A shared driven adapter that can create a task in a given list and update an existing task.
- A `shared.application` Protocol port the adapter structurally satisfies, so a consumer's application layer can depend on the capability without importing `shared.infrastructure`.
- Distinguishable failure: a caller creating a task needs to know if it failed (unlike the existing Slack notifier, which logs-and-continues because a missed notification isn't the primary outcome — a missing ClickUp task would be).

**Non-Goals:**
- No webhook / signature verification (`add-clickup-task-completed-webhook`, separate change).
- No product-agent flow or task-group/subtask orchestration (`add-product-launch-clickup-task-group`, separate change) — this change has no consumer wired up.
- No retry/backoff policy beyond what a single `httpx` call gives for free.
- No support for ClickUp fields this change has no known caller for yet (custom fields, attachments, checklists, etc.).

## Decisions

**HTTP client: `httpx`, async.** `httpx` is already present transitively (via the FastAPI/test toolchain, per `uv.lock`) but not a direct dependency — this change adds it directly. Exposed functions are `async def` using `httpx.AsyncClient`, since the only known future callers are FastAPI routes / LangGraph nodes, both async; a sync client would block the event loop. Constructed lazily and cached (mirrors `omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache` pattern for `WebClient`/`SignatureVerifier`), so importing the module never requires `CLICKUP_API_TOKEN` to be set.

**Return shape: a small typed result, not raw JSON.** Both `create_task` and `update_task` return a `ClickUpTask` dataclass (`id`, `url`) rather than ClickUp's raw response payload — gives callers (and their tests) a stable contract instead of coupling to ClickUp's response shape. Kept to two fields because no known caller needs more yet; extend when one does.

`ClickUpTask` itself lives in `shared/domain/`, not next to the adapter in `shared/infrastructure/driven/`. It is referenced by both the `ClickUpTaskWriter` Protocol (`shared.application`) and the adapter that implements it (`shared.infrastructure.driven`); placing it in `infrastructure` would force `application` to import from `infrastructure` to type the Protocol's return values — precisely the coupling the Protocol/adapter split exists to avoid, and worse than the `ProductNameReader` precedent this design cites, since that Protocol returns `Sequence[str]` and never faced this problem. A frozen dataclass carrying no behavior or invariant is a minimal, justified use of the domain layer (consistent with the project's "tactical patterns adopted only as needed" stance) and both `application` and `infrastructure` may depend on `domain` without breaking layering.

**`create_task(list_id, name, description=None)`; `update_task(task_id, fields)`.** Creation's required shape is well known (a list to create into, a name), so it gets explicit named parameters. Editing is not — ClickUp tasks carry many mutable fields (status, assignees, priority, due date, custom fields, ...) and no consumer of this change specifies which ones it needs. Rather than guess a subset now, `update_task` takes `fields: Mapping[str, object]` passed straight through as the PUT body's JSON, matching ClickUp's own update endpoint shape. Revisit if a later change needs a validated/typed subset.

**Errors surface, not swallowed.** A non-2xx ClickUp response raises (`httpx.HTTPStatusError` via `response.raise_for_status()`, uncaught) rather than being logged and absorbed the way `slack_notifier.post_monitoring_message`'s failures are in `monitoring.py`. The same applies to a request that never gets a response at all (timeout, connection failure): nothing catches it, so `httpx`'s own exception (e.g. `httpx.ConnectError`/`httpx.TimeoutException`) propagates identically. Rationale: a monitoring Slack message is best-effort; a ClickUp task a caller explicitly asked to create is not — the caller (e.g. the product-creation flow) needs to know and decide what to do (fail the request, retry, alert differently).

**Port lives in `shared.application`, adapter in `shared.infrastructure.driven`.** Mirrors the `ProductNameReader`/`ProductRepository` split. The Protocol names the two operations (`create_task`, `update_task`) structurally; the concrete adapter satisfies it without either side importing the other by name.

## Risks / Trade-offs

- [Risk] `CLICKUP_API_TOKEN` unset at call time → surfaces as `KeyError` from `os.environ[...]`, same failure mode Slack's adapters already have; not caught here, so it propagates to the caller like any other adapter failure.
- [Risk] `update_task`'s free-form `fields` mapping gives no compile-time protection against sending ClickUp a field it rejects → accepted for now (see Decisions); ClickUp's own 4xx response surfaces the problem via the raised `HTTPStatusError`.
- [Risk] No retry/backoff means a transient ClickUp outage fails the caller's request outright → acceptable for this change; a caller needing resilience can add its own retry around the port.

## Migration Plan

Purely additive — no existing behavior changes, no rollback concerns. Deploying requires `CLICKUP_API_TOKEN` to be set in each environment before any caller starts using the adapter; its absence doesn't affect anything else, since it's read lazily at call time, not at import/startup.
