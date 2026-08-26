## Why

A projected ClickUp task states its work — the step's name, its description, its due date and the people responsible for it — but says nothing about **where in the launch that work sits** or **which discipline owns it**. Both facts are already on the step (`StepDefinition.gate`, `StepDefinition.discipline`); neither reaches ClickUp, so a launch list cannot be grouped or filtered by the two divisions the playbook is actually built along.

The name deliberately does not carry them: `launch-clickup-sync` forbids appending the discipline to the task name because name width spent restating it costs the reader the wording the name exists to surface. That argument is about width, and a tag costs none — so a tag is where these facts belong.

## What Changes

- A newly projected task is created carrying its step's `gate:` and `discipline:` tags. No tag has to exist first — ClickUp creates one in the task's space on first use — so the change **seeds nothing, reaches no space, and introduces no new runtime configuration**.
- A pass adds either tag to a mapped task that lacks it, so tasks of every launch the pass still visits gain their tags rather than the change reaching only future launches. A `graduated` launch is not among them — it is excluded from projection and reconciliation entirely, so its tasks never backfill.
- The system never removes a tag and never corrects one. Tags outside the two owned prefixes are never touched.
- `clickup-task-client` gains two things: tags on task creation, and adding a tag to an existing task. The read of a list's tasks additionally reports each task's tags.

### Non-goals

Deliberately excluded, and accepted as consequences rather than deferred defects:

- **A step moved to a different gate keeps its old gate tag.** Correcting it needs the removal path and the "is a person's edit corrected or preserved" rule this change declines to open. A step's discipline is not updatable at all (`playbook_authoring.update_step` refuses it — a discipline change is a retirement plus a successor step, which gets a fresh task), so that tag cannot drift by authoring.
- **A hand-removed tag comes back on the next pass.** The change retains no state with which to tell "never added" from "added and then removed", so a task missing an owned tag is indistinguishable from one that never had it. A person who wants a task untagged cannot get one — which is the price of not policing tags in the other direction.

  The honest form of that trade: the mapping **already** retains a name, a body, an assignee set and an observed closed state, so the alternative is not new machinery — it is one more column and one migration, and it would buy removal-respecting and correction as well. It is declined here for scope, not for cost: adding it means settling whether a person's own retagging is preserved or overruled, which is a separate decision with its own argument, and this change is meant to be the small one that makes gate and discipline visible.
- **A tagging fault costs tags and nothing else.** A tag write that fails is logged and stepped over; the pass continues and still succeeds. A backfill can therefore stall behind runs recorded as succeeded, visible in the log rather than the run record.
- Tags on anything other than a projected task — the launch list itself, metric conditions, automated steps.

The two accepted consequences above — the stale gate tag and the returning tag — are both recoverable later by a change that adds correction, and neither leaves a task worse off than the untagged one it has today.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: a new requirement that a projected task carries its step's gate and discipline as tags, that no tag vocabulary is maintained, seeded or verified — a tag needs no prior existence — and that tags are added but never removed or corrected. Added rather than folded into the existing projection requirement: tagging is a new concern that changes none of the name, body, assignee or due-date behavior already specified there. The projection requirement is nonetheless **modified** in one clause, to narrow its "assignees are the one field" claim now that the tag rule reaches the same reading by another route.
- `clickup-task-client`: **two added requirements** — tags on task creation, and adding a tag to an existing task. **Two modified** — the read of a list's tasks additionally reports each task's tags, and the failure-surfacing enumeration is extended to cover the new operation.

## Impact

- `src/commerce_ops/shared/domain/clickup.py` — `ClickUpTaskState` gains `tags`.
- `src/commerce_ops/shared/infrastructure/driven/clickup_client.py` — parse `tags` from the task payload; `tags` on `create_task`; `add_task_tag`.
- `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py` — compose the two tags for a step, pass them on create, add missing ones on a pass, and let a per-task tag failure warn and continue.
- No database migration: the change retains no new state, so `ClickUpTaskMapping` and its table are untouched.
- No new environment variable, and no space-level access at all: the change touches only tasks.
- ClickUp API budget: one-time backfill of up to two tag calls per existing task, of the same order as the ~185-call first projection of a new launch that `clickup_sync_job.py` already accepts as a per-launch spike. The pass is convergent, so a rate-limited run resumes on the next pass rather than failing the backfill.
