## 1. Shared request path

- [ ] 1.1 Add a single internal async send helper in `clickup_client.py` that every operation routes its request through, replacing each site's direct `get_client().<verb>(...)` + `raise_for_status()` pair.
- [ ] 1.2 Implement the bounded `429` retry inside that helper: up to 3 retries (4 attempts total), honoring `Retry-After` when present (capped at 10s), falling back to exponential backoff (1s, 2s, 4s) otherwise.
- [ ] 1.3 Confirm every other status (400/404/5xx) and connection failures still propagate on the first attempt, unchanged.

## 2. Wire every operation through the shared helper

- [ ] 2.1 `create_task`
- [ ] 2.2 `update_task`
- [ ] 2.3 `create_list`
- [ ] 2.4 `list_tasks` (read a list's tasks)
- [ ] 2.5 `read_list_state`
- [ ] 2.6 `add_task_tag`
- [ ] 2.7 `folder_fields` (read a folder's Custom Fields)
- [ ] 2.8 `set_task_field`

## 3. Tests

- [ ] 3.1 Add a stateful `MockTransport` handler capable of returning `429` then a success response, for retry-then-succeeds coverage.
- [ ] 3.2 Test: a rate-limited request succeeds on retry.
- [ ] 3.3 Test: a `Retry-After` header is honored, capped at the fixed maximum wait.
- [ ] 3.4 Test: no `Retry-After` header falls back to the client's own backoff.
- [ ] 3.5 Test: an unparseable `Retry-After` header (not a plain count of seconds) falls back to the client's own backoff, without raising for the header itself.
- [ ] 3.6 Test: a request exhausts its retry budget and still fails, surfacing an error exactly as any other non-success response does.
- [ ] 3.7 Test: a non-429 failure is not retried — first-attempt propagation stays unchanged across each of the 8 functions' existing failure tests.
- [ ] 3.8 Mock or monkeypatch the retry wait (e.g. `asyncio.sleep`) in tests so the suite adds no real wall-clock delay.

## 4. Verification

- [ ] 4.1 Run `uv run pytest` and confirm the full `tests/unit` tier passes.
- [ ] 4.2 Run `ruff check` and `ruff format --check`.
- [ ] 4.3 Run `mypy`.
