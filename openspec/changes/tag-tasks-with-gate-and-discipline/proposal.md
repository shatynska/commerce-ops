## Why

A projected ClickUp task states its work — the step's name, its description, its due date and the people responsible for it — but says nothing about **where in the launch that work sits** or **which discipline owns it**. Both facts are already on the step (`StepDefinition.gate`, `StepDefinition.discipline`); neither reaches ClickUp, so a launch list cannot be grouped or filtered by the two divisions the playbook is actually built along.

The name deliberately does not carry them: `launch-clickup-sync` forbids appending the discipline to the task name because name width spent restating it costs the reader the wording the name exists to surface. That argument is about width, and a tag costs none — so a tag is where these facts belong.

## What Changes

- The system seeds a fixed tag vocabulary into the launch Space: `gate:<identifier>` for each of the eight gates and `discipline:<value>` for each of the twelve disciplines. The Space is derived from the already-configured launch folder, so **no new runtime configuration is introduced**.
- A newly projected task is created carrying its step's `gate:` and `discipline:` tags.
- A pass adds either tag to a mapped task that lacks it, so tasks projected before this change gain their tags rather than the change reaching only future launches.
- The system never removes a tag and never corrects one. Tags outside the two owned prefixes are never touched.
- `clickup-task-client` gains the ability to read a task's tags, to add a tag to a task, and to create a tag in a space.

### Non-goals

Deliberately excluded, and accepted as consequences rather than deferred defects:

- **A step moved to a different gate keeps its old gate tag.** Correcting it needs the removal path and the "is a person's edit corrected or preserved" rule this change declines to open. A step's discipline is not updatable at all (`playbook_authoring.update_step` refuses it — a discipline change is a retirement plus a successor step, which gets a fresh task), so that tag cannot drift by authoring.
- **A hand-removed tag comes back on the next pass.** The change retains no state with which to tell "never added" from "added and then removed", so a task missing an owned tag is indistinguishable from one that never had it. Retaining that state is exactly the machinery this change exists to avoid, so the tag is re-added. A person who wants a task untagged cannot get one — which is the price of not policing tags in the other direction.
- Tags on anything other than a projected task — the launch list itself, metric conditions, automated steps.

Both are recoverable later by a change that adds correction, and neither leaves a task worse off than the untagged one it has today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: a new requirement that a projected task carries its step's gate and discipline as tags, that the tag vocabulary is seeded into the launch Space, and that tags are added but never removed or corrected. Added rather than folded into the existing projection requirement: tagging is a new concern that changes none of the name, body, assignee or due-date behavior already specified there.
- `clickup-task-client`: the read of a list's tasks additionally reports each task's tags; two new operations — adding a tag to a task, and creating a tag in a space.

## Impact

- `src/commerce_ops/shared/domain/clickup.py` — `ClickUpTaskState` gains `tags`.
- `src/commerce_ops/shared/infrastructure/driven/clickup_client.py` — parse `tags` from the task payload; `add_task_tag`, `create_space_tag`, and a read of a folder's space identifier.
- `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py` — compose the two tags for a step, pass them on create, add missing ones on a pass.
- No database migration: the change retains no new state, so `ClickUpTaskMapping` and its table are untouched.
- No new environment variable: the Space identifier is derived from `CLICKUP_LAUNCH_FOLDER_ID`, which avoids the four-part obligation `AGENTS.md` places on every new runtime value.
- ClickUp API budget: one-time backfill of two tag calls per existing task, of the same order as the ~185-call first projection of a new launch that `clickup_sync_job.py` already accepts as a per-launch spike. The pass is convergent, so a rate-limited run resumes on the next pass rather than failing the backfill.
