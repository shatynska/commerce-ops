## 1. ClickUp client: tags on the shared adapter

- [x] 1.1 Add `tags: tuple[str, ...] = ()` to `ClickUpTaskState` in `shared/domain/clickup.py`, defaulting empty so existing constructions stay valid (the same treatment `name`, `description` and `assignees` were given).
- [x] 1.2 Parse `tags` in `clickup_client._task_state`, taking each tag's `name` and tolerating a tag object without one.
- [x] 1.3 Add `tags` to `clickup_client.create_task`, sent only when non-empty — omitted rather than sent as `[]`, matching how `assignees` is already handled.
- [x] 1.4 Add `add_task_tag(task_id, tag_name)` over `POST /api/v2/task/{task_id}/tag/{tag_name}`.
- [x] 1.5 Add `create_space_tag(space_id, name)` over `POST /api/v2/space/{space_id}/tag`.
- [x] 1.6 Add `space_tags(space_id)` over `GET /api/v2/space/{space_id}/tag`, returning the tag names.
- [x] 1.7 Add `space_id_for_folder(folder_id)` over `GET /api/v2/folder/{folder_id}`, returning `space.id`.
- [x] 1.8 Leave the failure behaviour of all five new calls uncaught, as `clickup-task-client`'s "A failed ClickUp request is surfaced to the caller" already requires of every operation.

## 2. Launch projection: compose and apply the tags

- [x] 2.1 Add the tag composition to `launch/infrastructure/driven/clickup_sync.py`: `gate:<step.gate>` and `discipline:<step.discipline.value>`, plus the owned-prefix predicate the add-if-missing rule tests against.
- [x] 2.2 Add vocabulary seeding to the pass: resolve the space from the configured folder, read the space's tags once, create only the missing members of `GATE_SEQUENCE` and `Discipline`. Resolve and read once per pass, not once per launch.
- [x] 2.3 Pass the composed tags to `create_task` when a task is created.
- [x] 2.4 On a mapped task, add each owned tag the task does not already carry, reading its current tags from the `list_tasks` result the pass already fetches — no extra read.
- [x] 2.5 Send nothing for a task already carrying both tags, and never send a tag removal.
- [x] 2.6 Wrap each tag write so a failure logs a warning naming the step, the tag and the task, and lets the pass continue — mirroring `_clickup_users`' treatment of an assignee with no ClickUp account.
- [x] 2.7 Confirm no change is needed for the not-active-step and stand-down paths: both already return before any task write, so tagging inherits their behaviour rather than restating it. Add a test rather than code if that holds.

## 3. Verification

- [x] 3.1 Write the tests the delta specs call for, and make them pass. **Deviation from `AGENTS.md`, recorded rather than hidden:** the spec review (`openspec-change-reviewer`) and spec-derived test authoring (`openspec-test-writer`) gates were both skipped at the user's explicit direction on 2026-08-26, so these tests were written by the implementer against the delta specs rather than by an independent author. That is exactly the shared-blind-spot risk the two gates exist to prevent; the mitigation applied was a mutation check (see below), which is weaker than independent authorship. Files: `tests/unit/launch/infrastructure/driven/test_clickup_tag_projection.py`, `tests/unit/shared/infrastructure/driven/test_clickup_client_tags.py`.
- [x] 3.1a Confirm the new tests discriminate, by mutating the implementation and checking they fail: `_ensure_tags` made a no-op → 4 tests fail (backfill included); the already-correct short-circuit removed → caught by `test_a_task_already_carrying_its_tags_is_left_alone`.
- [x] 3.2 `uv run pytest tests/unit tests/agents`.
- [x] 3.3 `uv run pytest tests/integration` (needs a database per `AGENTS.md`'s testing section).
- [x] 3.4 `uv run ruff check`, `uv run ruff format --check`, `uv run mypy`.
- [x] 3.5 Confirm `import-linter` still passes — the projection reaches `Discipline` through `shared.domain`, which the Shared Kernel exception permits, and reaches nothing new across a module boundary.
- [x] 3.6 Check the settings drift test still passes unchanged, confirming no new runtime variable was introduced.
