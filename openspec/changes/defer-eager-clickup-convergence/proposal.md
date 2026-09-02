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

---

## Exploration findings — 2026-09-02

Recorded from `/opsx:explore` against the code as it stands 66 commits after
this proposal was written (`origin/main` at `890acb4`, merged into this
branch). **No design decision was taken.** This section exists so the next
session starts from the verified picture rather than re-deriving it, and so
that the claims below which this exploration found to be *wrong* are not
carried into `design.md` unchallenged.

The code has not drifted: all four trigger sites, `converge_launch_eagerly`,
and the two-connection shape are exactly as described above.

### 1. There is no event-triggered job anywhere in this system today

`register_scheduled` (`shared/infrastructure/driven/recurring_work.py:92`)
**mandates** a cron expression and a tolerance, and applies `app.periodic`
unconditionally. All five registered jobs go through it. `grep` finds no
`defer(`, no `defer_async`, and no bare `app.task` in `src/`.

So "this is reusing the mechanism the project has, not introducing one" — as
the *What Changes* section above puts it — is only half true. The runner is
reused; the **kind of work** is new. `scheduled-jobs` today describes
recurring work in every one of its twelve requirements. Introducing a job
that fires on an event is a change to that capability's shape, not a sixth
registration, and `design.md` should carry that weight rather than the
proposal's lighter framing.

`procrastinate` 3.9 supplies what the shape needs: `configure_task` accepts
`queue`, `lock`, `queueing_lock`, `priority`, `schedule_in` and `connection`.
`queueing_lock` — at most one *pending* job per lock value — is exactly the
per-product dedup this proposal leaves open.

### 2. The HTTP process does not open the queue connector

Only `worker.py:270` calls `app.open_async()`. `main.py`'s lifespan states
outright that *"Nothing here reads the database"*, citing `database-session`'s
requirement that the serving process not open a connection before its first
request.

Deferring from three of the four sites therefore means opening
`procrastinate`'s **psycopg** pool in the serving process — a second pool,
under a second driver, alongside SQLAlchemy/asyncpg. This is *permitted*:
`docs/deferred-work.md:67` records that `database-session`'s one-pool rule
"explicitly exempts infrastructure holding its own connection or pool for
bookkeeping — which is what lets the job runner's second driver comply."

But a change whose stated purpose is relieving connection pressure must say
plainly that it adds a pool to the process it is relieving. The trade is
still favourable — one short `INSERT` against a bookkeeping pool, versus a
hold of up to ~30 s against the domain pool — and `design.md` should make
that argument rather than omit the cost.

A true transactional outbox is **not** available on this path: the
application writes through SQLAlchemy/asyncpg and `procrastinate` reads
through psycopg 3, so the defer cannot share the transaction that commits the
gate crossing. The enqueue happens after the commit, and can be lost. That is
the same window the inline call has today, and the periodic pass closes it
either way — but it is a window, not an absence of one.

### 3. The spec needs less rewriting than this proposal claims, and different rewriting

The *What Changes* bullet asserting that `launch-clickup-sync`'s eager
requirement "currently reads as though projection happens during the
triggering interaction" **does not survive reading it**
(`openspec/specs/launch-clickup-sync/spec.md:953-1015`):

- Both latency scenarios are phrased *"before the next periodic pass runs"*,
  not "during the interaction". They pass unchanged under deferral.
- *"the failure SHALL NOT be raised back to whatever triggered the run"* is
  **more** true deferred than inline, not less.
- The only wording that leans inline is the single word "immediately".

What genuinely needs new specification text is the opposite of what this
proposal anticipated. Not a weakened latency promise — a **new failure
mode**. Today "the eager run failed" is one caught exception. Deferred, it is
three distinct states:

1. the enqueue itself failed, after the state change had committed;
2. the job ran and exhausted its retries;
3. no worker was available to run it at all.

The existing sentence *"This requirement creates no new obligation to notice
or report a failed eager run"* was written about state (1)'s inline
equivalent. Whether it still holds across all three is a real question for
`design.md`, not a clause to carry across.

### 4. One of the four sites is already in the worker

`gate_progression_job` **is** a periodic job. Its convergence does not sit on
the request path and does not compete with request handling for the serving
process's pool. The pool argument that justifies deferring the other three
does not apply to it; what applies instead is that the pass currently
serialises each launch's ClickUp conversation inside its own loop.

Collapsing all four to one entry point is still right. But `design.md` should
not present one argument in four copies when it is really three-plus-one, and
should decide deliberately whether a worker job enqueueing another worker job
is worth the indirection at that fourth site.

### 5. A registry gap the change would open, and should close

Both registry tests — `tests/unit/shared/infrastructure/driven/test_job_runner_schedules.py:88`
and `test_recurring_work_registry.py:207` — enumerate
`app.periodic_registry.periodic_tasks`. A task registered through plain
`app.task` is invisible to them.

Two consequences. The good one: adding an event-triggered task breaks neither
test, including *"Every process holds the same registration"*. The bad one:
**no test would catch a composition root that failed to register it** — which
is precisely the silent, asymmetric failure `registrations.py`'s own docstring
exists to prevent. Extending the cross-process comparison to the runner's full
task registry (`app.tasks`, not only the periodic subset) is small, in scope,
and belongs in `tasks.md`.

### The fork that is actually open

This proposal treats "move it onto `procrastinate`" as settled.
`docs/proposed-change-order.md` does not — it lists the queue itself among the
decisions this change carries. There is a second shape, and it removes the
trigger rather than relocating it.

**A — deferred job** (this proposal): four blocks become one enqueue; the
worker performs the convergence under `queueing_lock` per product.

**B — catch-up pass**: the four trigger blocks are **deleted**. A frequent,
narrow recurring job asks which launches are behind and converges only those.

|                        | A. Deferred job                          | B. Catch-up pass                        |
|------------------------|------------------------------------------|-----------------------------------------|
| Trigger sites          | 4 blocks → 1 enqueue                     | 4 blocks → **deleted**                  |
| Mechanism              | first event-triggered job; new shape for `scheduled-jobs` | a 6th `register_scheduled` job; existing mechanism unchanged |
| HTTP process           | needs the queue connector + a 2nd pool   | untouched                               |
| Per-product dedup      | `queueing_lock`                          | inherent                                |
| Lost trigger           | same ≤12 h window as today               | impossible — there is no trigger to lose |
| Monitoring             | outside the freshness registry; needs a stated reason | cron + tolerance, monitored like everything else |
| Latency                | near-instant (LISTEN/NOTIFY)             | the pass interval (~1 min)              |
| Migration              | none                                     | **possibly none** — see below           |
| Retry/backoff          | free, via `RetryStrategy`                | **owed** — see below                    |

B rests on staleness being *derivable* rather than signalled: a launch is
behind exactly when it carries a released `active` `human` step with no row in
`launch_clickup_tasks`. Two cheap Postgres reads plus the already-loaded
playbook answer that in memory, and the pass issues **zero** ClickUp calls
when nothing is behind — which is the property that forced the twice-daily
cadence in the first place. It also matches what the eager path actually
promises (creation for newly released steps) rather than the full compare
`clickup_sync_job` performs.

**This derivability was reasoned from the schema, not verified against the
release logic and `ClickUpMappingRepository`. Verify it before B is costed.**
If it holds, B needs no migration and no marker column; if it does not, B
needs a marker written in the crossing's own transaction — which would be a
true outbox and would close the lost-trigger window that A cannot.

B's real cost, and it is not small: a launch whose task creation *fails* at
ClickUp stays "behind" and is retried every pass, against a rate-limited API.
That needs backoff. `automated_step_backoff` is the precedent, and whether its
shape transfers is an open question. A gets this free.

**Lean, not decision: B** — it deletes the coupling instead of relocating it,
keeps the serving process out of the queue entirely, and fits `scheduled-jobs`
as it stands. A is the safer change, and the backoff question is a genuine
argument against B.

A third, much smaller option was raised and not pursued: keep the call inline
and merely narrow what the session is held across. It cuts hold time with no
new machinery, but leaves the work on the request path, so it addresses the
latency half of the problem and not the pool half.

### Questions left unanswered

1. **A or B** (or spike both and settle at review).
2. **When the eager/catch-up convergence stops working entirely, is that
   reported?** Under B it is free — cron plus tolerance, like every other job.
   Under A it needs a new notion: a *backlog* check, not a *freshness* check,
   because a per-product job that fires irregularly has no "last successful
   run" in the sense `scheduled-jobs`' tolerance means. The cheap answer is
   that it is deliberately outside the registry, `clickup_sync_job` is the
   monitored safety net, and the failure mode is "projection silently degrades
   to twice-daily" — which is consistent with the current spec's "creates no
   new obligation to notice", but should be chosen rather than defaulted into.
3. **Does the latency difference matter?** ~1 minute (B) versus near-instant
   (A). That depends on what someone does immediately after a gate crosses,
   which the code cannot answer.
