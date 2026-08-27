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

### What containment established, and what it left

`contain-a-failing-launch` merged and deployed on 2026-08-27 at 10:24Z. The first pass under it, at 10:30Z, is the measurement this change is proposed on:

```
10:29:34Z  lists: TestProductName=89
10:30:21Z  lists: TestProductName=89 | TestProductName5=9 | asdfsdf=0
10:31:08Z  lists: TestProductName=89 | TestProductName5=9 | asdfsdf=9 | TestProductName6=9
           launch.clickup.completion_pass last_success=07:20:00Z — unchanged
```

Three launches that had been starved behind the broken one were projected within seventy seconds: a list each, nine tasks each, nine being the count of active human steps the served playbook then carried. Four of the deployment's five active launches now have live lists.

The fifth does not, and this is what remains. `TestProductName0`'s recorded list is `901220624358`, which ClickUp reports as `"deleted": true`, and the pass has failed on it on every run since. That is why `last_success` is still `07:20:00Z` — deliberately, since containment must not report a launch it could not converge as a success, and the observation above is the evidence that it does not.

Two consequences follow, and they are this change's actual urgency rather than a general argument about robustness:

- **The launch is inert.** Its steps exist in no list a person can open, and no completion can be recorded for it, so its gates cannot open on ClickUp's evidence.
- **The deployment is knowingly unhealthy until this lands.** The completion work's six-hour tolerance runs from `07:20Z`, so it becomes overdue at about `13:20Z` on 2026-08-27 and `scheduled-jobs` reports the outage to Slack once. Nothing further is reported while it persists, so a *second*, unrelated failure of this pass would arrive into an already-red signal.

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
- A launch healed here is given a **new** list, whose name is composed the way every launch list's is. That composition currently renders the SKU value object rather than its value, so the four live lists read `TestProductName5 (Sku(value='TestSKU5'))`. Healing will reproduce it in the fifth. Fixing it is not this change's business — it is a one-line defect in `_list_name` with its own test blind spot, and it needs its own change — but it should be fixed before this one mints another name, not after.

## Sequencing

There is no code dependency between this change and `contain-a-failing-launch`: that one changed the driving adapter's loop (`clickup_sync_job.py`), this one changes the driven adapter and the client, and containment's tasks explicitly left `clickup_sync.py` untouched.

**The ordering constraint is already discharged.** Containment merged and deployed first, and its post-merge observations were made against the still-broken launch — which is the whole reason that launch was left broken. Nothing now depends on the fixture, so this change is free to land whenever it is ready, and the sooner it does the shorter the deliberate outage above.

Recorded because the reasoning is no longer visible from the artifacts: had this change merged first, it would have fixed the deployment and destroyed the evidence. Every launch would have converged, and containment's production verification would have had nothing left to observe.

Either change alone would have restored the deployment for a *new* product — containment by walking past the broken launch, healing by fixing it. Only healing restores the broken launch itself, which is why containment shipping is not a reason to defer this.
