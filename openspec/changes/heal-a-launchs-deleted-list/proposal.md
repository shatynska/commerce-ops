## Why

A ClickUp list deleted in ClickUp leaves the launch that owned it permanently unprojectable. The mapping still records the dead list, `_ensure_list` hands it back unchecked, every read of it comes back empty, every step takes the re-projection branch, and every `create_task` against it returns `404`. Nothing recovers, on any pass, ever.

This happened on 2026-08-27 and is the fault that produced `contain-a-failing-launch`:

```
ClickUp completion pass starting over 5 launch(es)
  launch 2  create_task → HTTPStatusError: 404 Not Found
            .../api/v2/list/901220624358/task
```

ClickUp's own answer for that list is unambiguous — `GET /list/901220624358` returns `200` with `"deleted": true` — so the condition is observable rather than merely inferable from a failed write.

The module is written as convergence, and it already heals the neighbouring case deliberately: a *task* that has vanished from ClickUp is re-projected, on the stated ground that "deleting a task is not a sanctioned way to finish work". The same reasoning was never extended one level up. A list is likewise not a sanctioned way to end a launch's obligations, and today deleting one ends them anyway.

`contain-a-failing-launch` stops that fault from starving every other launch. It does not fix it: the launch whose list was deleted still fails on every pass, forever, and its work exists nowhere a person can do it.

## What Changes

- A launch whose recorded ClickUp list no longer exists SHALL be given a new one, and the associations that died with the old list SHALL be discarded so its steps re-project into it. This is the existing "a launch whose list already exists SHALL NOT get a second one" rule meeting the case where the recorded list is *gone* — a distinction that requirement does not currently draw.
- The condition SHALL be established from what ClickUp says about the list, not inferred from a failed write. A `404` on a write can mean a transient fault or a permissions change; `"deleted": true` on the list itself is ClickUp stating the fact.
- Every task mapping belonging to the dead list SHALL be discarded with it — task identifiers, retained compositions, retained observed states. They name tasks that no longer exist, and a retained observed state carried across to a freshly created task would describe a task nobody has seen.

Explicitly not in this change:

- **Recovering the completions recorded against the dead list's tasks.** Outcomes already recorded stand; what is lost is the ability to observe *further* transitions on tasks that no longer exist. The re-projected tasks start unobserved, exactly as newly projected tasks do.
- **Anything about the walk.** Containment, per-launch failure reporting and the run's outcome belong to `contain-a-failing-launch` and are not revisited here.
- **The orphaning residual that change accepted** — a database refusing writes while accepting rollbacks, leaving a ClickUp artifact with no association. That is the inverse fault (the artifact exists, the record does not) and needs its own answer; this change addresses a record whose artifact is gone.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: modifies "Each launch is projected into its own ClickUp list" so that the no-second-list rule holds for a list that still exists, and a launch whose recorded list has been deleted is given a new one with the dead list's task mappings discarded.

## Impact

- `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py` — `_ensure_list`, and the mapping discard that must accompany a replacement.
- `src/commerce_ops/launch/infrastructure/driven/clickup_mapping.py` — a way to discard a launch's task mappings; today the store replaces them one step at a time.
- `src/commerce_ops/shared/infrastructure/driven/clickup_client.py` — reading a list's own state, which the client does not currently do.
- Costs one ClickUp read per launch per pass, or one only where a list is recorded — a design question this change must settle.
- **Deploying this removes the production fixture** that `contain-a-failing-launch` relies on for its post-merge observations. See Sequencing.

## Sequencing

There is no code dependency between this change and `contain-a-failing-launch`: that one changes the driving adapter's loop (`clickup_sync_job.py`), this one changes the driven adapter and the client, and its tasks explicitly leave `clickup_sync.py` untouched. They can be implemented in parallel without conflict.

The dependency is in the *deployment order*, and it runs one way:

1. `contain-a-failing-launch` merges first, and its tasks.md §5 observations are made against the still-broken launch — which is the whole reason that launch was left broken.
2. This change merges after, ending the fixture and the unhealthy state it deliberately sustains.

Merging this one first would fix the deployment and destroy the evidence: every launch would converge, and containment's production verification would have nothing to observe. The unit and integration tests would still cover it, but the observation this fixture was preserved for would be gone.

Either change alone restores the deployment. Containment gets the healthy launches converging past the broken one; healing gets the broken one working. Both are needed for both.
