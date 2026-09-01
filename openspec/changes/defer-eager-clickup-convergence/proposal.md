## Why

`trigger-clickup-projection-on-launch-events` (archived 2026-08-31) added an eager, single-launch `converge_launch` call at four points — a launch starting, and a gate crossing at each of its three trigger sites. It solved a real problem: after `shift-clickup-completions-to-webhook` widened `clickup_sync_job` to twice daily, a newly started launch had no ClickUp task for up to ~12 hours.

It solved it by holding a database connection open across the whole of an external API conversation, on the request path, in four places.

### The connection is held for the duration of every ClickUp call the convergence makes

`converge_launch_eagerly` (`clickup_sync.py:752-764`):

```python
async with transaction() as lock_session:
    await hold_launch_advance_lock(lock_session, launch.product_id)
    await converge_launch(...)
```

The transaction exists only to hold the advisory lock — `launch_advisory_lock.py:34-51` argues at length, and correctly, that `converge_launch`'s own writes must **not** be bound to it. But `converge_launch` is awaited inside the block, so the connection stays checked out for as long as the convergence runs. And a convergence is not short: `_ensure_list` issues a `read_list_state`, the pass issues a `list_tasks`, and then per released step up to a `create_task`, an `update_task`, two `set_task_field` calls and a `record_composition`. `retry-clickup-rate-limits` then adds **up to ~30 s of `asyncio.sleep` per request** on a `429` (`_MAX_ATTEMPTS = 4`, `_MAX_RETRY_WAIT_SECONDS = 10.0`).

So the hold time is bounded by ClickUp's behaviour, not by ours — and ClickUp rate-limiting us is the documented reason the periodic cadence was widened in the first place. The mechanism that made the eager path necessary is the same mechanism that makes it hold connections longest.

### Two connections, not one, at the site that fires most predictably

`gate_confirmation.py:487-497` opens `session()` to build the mapping repository and then calls `converge_launch_eagerly`, which opens its own `transaction()` for the lock. Both are held simultaneously, for the same duration. `slack_entry.py:601-611` and `clickup_webhook.py:194-203` have the same shape.

### The pool is small and this was already flagged

`create_async_engine(_read_database_url())` (`database.py:52`) takes SQLAlchemy's defaults: `pool_size=5`, `max_overflow=10` — 15 connections per process. `docs/deferred-work.md` already carries *"Aggregate connections against `max_connections` are unbounded"*; this change did not create that entry, but it materially raised the hold time sitting behind it, and did so on the path that serves Slack interactions and ClickUp webhooks. A burst of webhooks during a ClickUp slowdown is exactly the correlated case: many convergences, each slow for the same reason, each holding one or two of fifteen connections.

### It also sits in front of the user, in four copies

The convergence is awaited before the handler returns. `gate_confirmation` was careful about this — its docstring notes the eager call runs *after* `respond`, so the decider is not held up — but the Slack listener task still cannot finish, and `slack_entry`'s own eager block runs after the confirmation post with the same effect on the listener.

And the trigger is written out four times: `slack_entry.py:589-620`, `gate_confirmation.py:481-506`, `gate_progression_job.py:186-224`, `clickup_webhook.py:186-212`. Each opens its own session, re-reads the playbook and the launch, wraps the call in its own `try`, and logs a near-identical warning. Four copies of "guarded independently of `converge_launch_eagerly`'s own catch" is four places to get the guard subtly different, and the reasoning is genuinely identical in all four — each docstring says so by pointing at one of the others.

## What Changes

- **The eager convergence is deferred as a job rather than awaited inline.** The four call sites enqueue one unit of work naming a product; a worker performs the convergence. `procrastinate` is already the deployment's job runner (`scheduled-jobs`, `registrations.py`), already runs in the worker process, and already carries this application's retry and run-recording conventions — so this is reusing the mechanism the project has, not introducing one. `design.md` settles the queue, whether the job is deduplicated per product while one is pending, and what its retry policy is.
- **The connection is released before the ClickUp conversation begins.** The advisory lock still guards the convergence — the eager path and `clickup_sync_job`'s own lock-wrapped call must still not both mint a list for a launch's first convergence — but it is taken by the worker performing the work, where a long hold costs a worker slot instead of a request-path connection. `launch_advisory_lock.py`'s standing instruction not to rebind `converge_launch`'s writes to the lock transaction continues to hold and is not disturbed.
- **The four trigger blocks collapse to one.** A single "convergence is owed for this product" entry point, called from the four sites, replacing four copies of session-open / playbook-read / launch-read / try / warn. The independent guarding each site currently asserts survives as one guard in one place; the reason it exists (a caller must not depend on the callee catching its own failures) is satisfied by the enqueue call not being able to fail the caller.
- **The latency guarantee is restated in terms of what it actually promises.** `launch-clickup-sync`'s eager requirement currently reads as though projection happens during the triggering interaction. Deferred, it happens promptly and independently of it. `slack_entry.py`'s `CLICKUP_SYNC_CADENCE_DESCRIPTION` — corrected once already by the change that introduced this path — must say something true of the deferred shape.
- Explicitly **not** in scope: `clickup_sync_job`'s twice-daily cadence, its containment and stand-down behaviour, or its role as the fallback for both directions; `reconcile_launch` and the completion direction, which the webhook already serves; `converge_launch` itself — every projection, release, hazard, status and retained-composition rule is unchanged, and the deferred job calls the same function; the advisory lock's key derivation or namespace; and the pool sizing question in `docs/deferred-work.md`, which this change relieves pressure on without settling.
- Explicitly **not** a goal: making the projection faster than it is today. Deferring may add a second or two before a task appears. That is a good trade against holding a request-path connection through a rate-limited API conversation, and `design.md` should say so plainly rather than claim the change is free.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `launch-clickup-sync`: the eager single-launch projection requirement is restated as work the triggering event *causes* rather than work it *performs* — enqueued when a launch starts or a gate is crossed, carried out promptly and independently, and still in addition to (never instead of) the periodic reconciliation pass. What is projected, when it is eligible, and how a failure is contained are unchanged; a task created by the deferred path is indistinguishable from one created by the pass, because both still call `converge_launch`. The requirement that a triggering interaction is never delayed by, nor failed by, the projection becomes something the mechanism guarantees rather than something four `try` blocks assert.
- `scheduled-jobs`: gains this as a kind of work the runner carries — event-triggered and per-product, alongside the recurring passes it holds today. Whether its runs are recorded in the run history the way a recurring pass's are, and whether an overdue eager convergence is reportable at all, is a real question for `design.md`: a per-product job that fires irregularly does not have a "last successful run" in the sense the freshness check means. If the answer is that it is deliberately outside that reporting, this capability is modified only to say so.

## Impact

- `src/commerce_ops/launch/infrastructure/driven/clickup_sync.py:690-772` — `converge_launch_eagerly` becomes the job's body rather than an inline call; the module docstring's note about it being *"the one deliberate exception"* that opens a transaction is revisited, since the exception's justification changes shape.
- `src/commerce_ops/launch/infrastructure/driving/slack_entry.py:589-620`, `gate_confirmation.py:481-506`, `gate_progression_job.py:186-224`, `clickup_webhook.py:186-212` — four trigger blocks become four enqueue calls to one entry point.
- `src/commerce_ops/registrations.py` — registers the new job, so both composition roots hold it, for the reason that file already exists.
- `src/commerce_ops/main.py:254-285`, `src/commerce_ops/worker.py` — the HTTP process no longer needs `read_product`/`read_people` wired onto `slack_entry`, `gate_confirmation`, `clickup_webhook` and `gate_progression_job` for convergence's sake, since it no longer converges. That removes eight of the global assignments `unify-launch-adapter-dependencies` is about; the two changes overlap here and should be sequenced deliberately rather than merged.
- Tests: `tests/unit/launch/infrastructure/driving/test_clickup_webhook_eager_convergence.py`, `test_gate_confirmation_eager_convergence.py`, `test_gate_progression_pass_eager_convergence.py`, `test_slack_entry_eager_convergence.py`, `test_clickup_sync_job_lock_wrapping.py` and `tests/unit/launch/infrastructure/driven/test_eager_convergence_helper.py` all assert on the inline shape and are the change's real surface area. `tests/integration/launch/test_eager_convergence_atomicity_live.py` covers the lock behaviour against a real database and must keep covering it.
- No migration and no schema change of this project's own. `procrastinate`'s tables already exist.
- No new runtime variable. If `design.md` chooses a distinct queue name it is a constant, not configuration.
