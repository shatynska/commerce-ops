## Context

See `proposal.md` — Why. What follows is the evidence, because the previous
attempt at this defect recorded three hypotheses that experiment falsified,
and an explanation that cannot be checked is worth no more than those were.

### The mechanism, end to end

`commerce_ops.shared.infrastructure.driven.job_runner.app` is one
`procrastinate.App` for the whole process. Its `periodic_registry` is empty
on a bare import and holds three real jobs once `registrations.register_all()`
has run:

```
briefing.daily                       0 6 * * *
launch.clickup.completion_pass       */10 * * * *
shared.scheduled_runs.overdue_check  0 * * * *
```

with `PERIODIC_DEFAULTS = {"max_delay": float("inf")}`, so no missed
occurrence is ever dropped — deliberately, per
`replace-cron-with-job-runner`'s "A missed window runs once".

Four integration modules call `register_all()` at import
(`test_known_work_anchor.py`, `test_overdue_report_suppression_store.py`,
`test_scheduled_runs_freshness_cache.py`,
`test_scheduled_runs_freshness_unreachable.py`). pytest imports every
selected module during collection, so in any run containing one of them the
registry is armed before the first test executes.

`test_scheduled_run_history.py::_drain()` then calls
`runner_app.run_worker_async(...)`. `Worker._start_side_tasks()` always
creates a `_periodic_deferrer` task. Its behaviour depends entirely on the
registry:

```
registry EMPTY  →  periodic.py:127  "No periodic task found"  →  returns at once
registry ARMED  →  periodic.py:134  while True: defer_jobs(); wait()
```

The armed deferrer defers the three production jobs, and the test's own
worker executes them. On `_drain()` exit:

```
Worker._run_loop()          worker.py:705   finally: await self._shutdown(...)
  Worker._shutdown()        worker.py:557   await cancel_and_capture_errors(side_tasks)
    utils.py:232                            await asyncio.gather(*tasks)     ← no timeout
```

`cancel_and_capture_errors` calls `task.cancel()` **once** per side task and
then gathers them with no deadline. That is safe only if every side task
honours its cancellation. The deferrer does not, because the layer beneath it
absorbs the exception:

```python
# psycopg_pool/pool_async.py:38
CLIENT_EXCEPTIONS = (Exception, asyncio.CancelledError)

# psycopg_pool/pool_async.py:262 — _getconn_with_check_loop
while True:
    conn = await self._getconn_unchecked(deadline - monotonic())
    try:
        await self._check_connection(conn)
    except CLIENT_EXCEPTIONS:          # ← CancelledError lands here
        await self._putconn(conn, from_getconn=True)
    else:
        return conn
```

`PsycopgConnector._create_pool` passes
`check=AsyncConnectionPool.check_connection`, so every `getconn` performs a
`SELECT 1` round trip — the window in which a cancellation can be swallowed
is open on every query the deferrer makes. procrastinate's own
`wrap_exceptions` cannot re-raise it: it catches `psycopg.errors` only.

With the `CancelledError` absorbed, `defer_jobs()` returns normally, the
`while True` loop continues to `wait()`, and nothing ever cancels the task
again. `gather()` is now waiting on an immortal coroutine.

### What was captured, not reasoned

Await chain from a live stall (SIGUSR1 handler dumping `asyncio.all_tasks()`;
one signal handler, no timer and no tracing, so it cannot perturb the timing
of what it observes):

```
worker loop  [pending]
  procrastinate/worker.py:705   _run_loop
  procrastinate/worker.py:557   _shutdown
  procrastinate/utils.py:232    cancel_and_capture_errors   ← _GatheringFuture
     ▼ waiting on
deferrer     [CANCELLING]        ← cancel requested, task still alive
  procrastinate/worker.py:131   _periodic_deferrer
  procrastinate/periodic.py:137 worker
  procrastinate/periodic.py:274 wait
  asyncio/tasks.py:665          sleep                        ← a *fresh* future
```

A task cannot be in `cancelling` state and suspended on a newly created
`asyncio.sleep` future unless the delivered `CancelledError` was caught and
not re-raised.

**The stall is not frozen — it is ticking.** A wedged
`pytest tests/integration` left running for over an hour committed on exactly
the `*/10 * * * *` boundaries:

```
12:30:00.525  COMMIT
12:40:00.525  COMMIT
12:50:00.518  COMMIT
```

That is the orphaned deferrer, still deferring
`launch.clickup.completion_pass`, an hour after being cancelled. This also
explains the earlier `faulthandler` signature — the loop parked in
`selectors.select` with every Postgres connection `idle`/`ClientRead` — which
had been read as a deadlock. It is a sleep between cron ticks.

### The controlled experiment

`test_scheduled_run_history.py` alone, 15 runs per arm, 60s ceiling, the only
difference being a pytest plugin that calls `register_all()`:

| arm | stalls |
|---|---|
| with `register_all()` | **2 / 15** |
| without | **0 / 15** |

The stall lands on `test_a_retried_run_that_succeeds_is_recorded_as_succeeded`
or its sibling because those two call `_drain(passes=5)` — five worker
start/stop cycles, so five cancellations of the deferrer, against one for
every other test in the file.

This also retires the two-file framing in `docs/deferred-work.md`. The pair
is minimal, not special: any of the four arming modules plus this one will
do, and two of them sort *before* it, which is why the full tier hangs too.

### The second defect, same root

The tests do not merely arm a deferrer; they run the jobs. The development
database currently holds, deferred by `pytest` rather than by a worker:

```
briefing.daily                        failed      3
launch.clickup.completion_pass        failed     28
shared.scheduled_runs.overdue_check   succeeded  16
products.monitoring.daily             succeeded   1   ← a task name no longer registered
```

They fail fast today only because no `CLICKUP_*`, Slack or OpenAI variable is
set in a test process. `docs/deferred-work.md` records that the owner has
asked for the ClickUp variables to be **required**; on the day a tier runs
with them present, these tests begin making real outbound calls and writing
to a real ClickUp folder. The hang is the loud half of this defect; this is
the quiet half.

## Goals / Non-Goals

**Goals:**

- The runner tests drive a periodic registry they own, so no sibling module's
  import can change what they execute.
- No test can defer or run a production job.
- A future wedge inside `run_worker_async` fails a test rather than hanging
  the session.

**Non-Goals:**

- Changing `register_all()`, the four modules that call it, or anything in
  `src/`. Each of those calls is correct for its own file.
- Fixing procrastinate or psycopg_pool. Both behaviours are arguably upstream
  bugs and worth reporting, but this project should not be waiting on either
  to have a suite that terminates.
- Making the tier hermetic with respect to the *database*. It is an
  integration tier; a real Postgres is the point.
- Retention or pruning of `procrastinate_jobs` in general — that is its own
  deferred item. Only the rows this defect produced are in scope.

## Decisions

### Decision 1 — Isolate the registry rather than emptying it

The registry is a mutable module-level dict on a shared `App`. Two shapes
were considered.

**Chosen: give the runner tests their own `procrastinate.App`,** built the
same way `job_runner.py` builds the shared one, with the test tasks
registered on it. Nothing the tests do can then reach production
registrations, and nothing a future sibling module imports can reach the
tests.

**Rejected: a fixture that saves, empties and restores
`runner_app.periodic_registry`.** Smaller, and it would work. It is rejected
because it leaves the coupling in place and depends on every future runner
test remembering to request the fixture — the same "one shared global, many
uncoordinated users" shape that produced the defect. It also keeps the tests
mutating an object the application owns.

The cost of the chosen shape is real and should be stated: these tests then
exercise *a* procrastinate App rather than *this application's* App, which
`test_scheduled_run_history.py`'s own docstring gives as a reason for using
the shared one ("what is exercised is this application's runner, its schema
migration and its accessor"). That reason survives: the schema migration and
`last_successful_run` are unchanged, and both are what those tests actually
assert. What is lost is only the shared *registry*, which those tests never
meant to exercise.

### Decision 2 — Bound `_drain()`, and keep the bound after the fix

`asyncio.wait_for` around `run_worker_async`, with a ceiling generous enough
that it can only be reached by a wedge, never by slow I/O.

Kept rather than removed once Decision 1 lands, on the same reasoning
`verify-the-integration-tier` used for `timeout-minutes`: this defect was
invisible for as long as it was, partly because nothing in the tier could
fail fast. A ceiling converts the next wedge — in a library version bump, or
in a shape nobody has thought of — into a named failing test.

### Decision 3 — Delete the rows this defect wrote

`briefing.daily`, `launch.clickup.completion_pass`,
`shared.scheduled_runs.overdue_check` and `products.monitoring.daily` rows in
the development database's `procrastinate_jobs` were written by test runs.
They are not evidence of anything and they distort
`last_successful_run`, which the overdue reporter reads.

Scoped to the developer database named by `.env` / `.env.test`. **Not** the
deployment: production rows there are genuine runs and must not be touched.
`products.monitoring.daily` is a task name no longer registered anywhere, so
it is dead by a second route.

## Risks / Trade-offs

- **A private App means the runner tests no longer exercise the shared one.**
  → `test_job_runner_schedules.py` and `test_known_work_anchor.py` already
  assert what the shared registry contains, and they keep doing so. The
  division becomes explicit: those files own "what is registered", these
  files own "how the runner behaves".
- **A ceiling on `_drain()` can be reached by a genuinely slow machine, turning
  a wedge-detector into a flaky test.** → Choose it against a measured
  baseline (the file runs in ~1–2s locally, ~7s behind an arming sibling) and
  set it an order of magnitude above, as `BOUNDED_SECONDS` in
  `test_scheduled_runs_freshness_unreachable.py` already does for a
  comparable judgement.
- **Deleting rows in a database this project does not own the state of.** →
  Development database only, named explicitly, and every affected task name
  listed before anything is deleted.
- **The upstream behaviours remain.** → Any future code that cancels a task
  which touches psycopg_pool inherits the same trap. `src/` has no such
  caller today. Worth recording in `docs/deferred-work.md` as a known
  property of the dependency rather than treating it as closed.

## Migration Plan

None. Tests and documentation only; no schema change, no deployed behaviour,
revertible as a code change alone.

## Open Questions

- Whether to report the two upstream behaviours (`cancel_and_capture_errors`
  gathering without a deadline; `psycopg_pool` classifying `CancelledError` as
  a retryable client error). Deferrable: it changes nothing here either way.
