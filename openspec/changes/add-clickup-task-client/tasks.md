## 1. Dependency

- [ ] 1.1 Add `httpx` as a direct dependency in `pyproject.toml` (already present transitively per `uv.lock`)

## 2. Domain

- [ ] 2.1 Add `shared/domain/clickup.py` with a frozen `ClickUpTask` dataclass (`id`, `url`) — no behavior, no I/O

## 3. Port

- [ ] 3.1 Add `shared/application/ports.py` with a `ClickUpTaskWriter` Protocol declaring `create_task` and `update_task`, typed against `shared.domain.clickup.ClickUpTask`
- [ ] 3.2 Export it from `shared/application/__init__.py`

## 4. Adapter

- [ ] 4.1 Add `shared/infrastructure/driven/clickup_client.py`: lazily-cached `httpx.AsyncClient` construction (mirrors `omni_agent/infrastructure/driving/slack.py`'s `functools.lru_cache` pattern), reading `CLICKUP_API_TOKEN` at call time; imports `ClickUpTask` from `shared.domain.clickup`
- [ ] 4.2 Implement `create_task(list_id, name, description=None) -> ClickUpTask` (`POST /api/v2/list/{list_id}/task`)
- [ ] 4.3 Implement `update_task(task_id, fields) -> ClickUpTask` (`PUT /api/v2/task/{task_id}`)
- [ ] 4.4 Let a non-2xx ClickUp response propagate via `response.raise_for_status()`, and a transport-level failure (timeout/connection error) propagate unmodified — no catching either way

## 5. Tests

- [ ] 5.1 Unit tests for `create_task` (name only, name+description) using `httpx.MockTransport` to fake ClickUp's response — assert the outgoing request body/URL and the returned `ClickUpTask`
- [ ] 5.2 Unit tests for `update_task` (one field, multiple fields, empty fields) — same approach
- [ ] 5.3 Unit tests for a non-success ClickUp response on create and on update — assert the error propagates
- [ ] 5.4 Unit test for a transport-level failure (e.g. `httpx.ConnectError`/timeout via `MockTransport`) on create or update — assert it propagates
- [ ] 5.5 Unit tests for `CLICKUP_API_TOKEN` absent: importing the module succeeds; calling `create_task`/`update_task` raises without sending a request
- [ ] 5.6 Verify `ClickUpTaskWriter` structurally accepts the concrete adapter (a `mypy`-checked assignment or a test asserting `isinstance`-style structural compatibility, matching how `ProductRepository`/`ProductNameReader` is verified)

## 6. Verification

- [ ] 6.1 Run `uv run pytest`, `uv run mypy`, `uv run ruff check`, `uv run ruff format --check`
- [ ] 6.2 Run `openspec validate --change add-clickup-task-client --strict`
