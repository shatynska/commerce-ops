"""A tick that already ran is not run again when a worker restarts.

Derived from `specs/scheduled-jobs/spec.md` in the OpenSpec change
`replace-cron-with-job-runner`:

- "A Window Missed While No Worker Was Available Is Run Once On Return"
  -- the requirement's "SHALL run that work once ... rather than skipping
  it silently", read across a worker restart rather than within one
  worker's lifetime.

and from tasks.md 5.5a, which asks for this case by name: "a tick that
has already produced a completed run produces **no second run** when a
fresh deferrer offers it again".

See `test-manifest.md` at the change root for the full accounting.

## Why this case needs a test of its own

With `max_delay` set to `float("inf")` (tasks.md 2.5), *every* worker
start offers the most recent past tick -- and this deployment restarts
the worker on every merge to `main`. A redeploy at 09:00 therefore
re-offers the 06:00 tick that already ran that morning. Nothing in the
job definition prevents a second digest; per design.md ("a third path,
which is what makes \"once\" true across restarts") the guarantee is in
the runner's own SQL: `procrastinate_defer_periodic_job_v2` first
inserts `(task_name, periodic_id, defer_timestamp)` into
`procrastinate_periodic_defers`, a table carrying
`UNIQUE (task_name, periodic_id, defer_timestamp)` with
`ON CONFLICT DO NOTHING`, and creates no job when that insert produces no
row.

`tests/unit/.../test_job_runner_schedules.py::test_a_worker_that_never_
went_away_defers_nothing_extra` covers the within-one-process half of
"once": a single deferrer's in-memory `last_defers`. That memory is gone
when the process is replaced, which is exactly the case here.

## Why this is integration tier

The deduplication is a unique constraint and an `ON CONFLICT` clause in
Postgres. It is not observable against any in-memory double: the smallest
unit that can observe it is a real database holding the row from the
first defer while a second, freshly constructed deferrer offers the same
tick. These tests assume `alembic upgrade head` has been applied to the
database `DATABASE_URL` points at, including this change's own migration
-- the same assumption `test_scheduled_run_history.py` makes.

## What is invented here

- `commerce_ops.shared.infrastructure.driven.job_runner.app` -- the
  runner application object; design.md fixes the directory, no artifact
  fixes the name. The single correction point, shared with the other
  tests this change adds.
- The tick task and its schedule below are defined for this test only.
  The daily job's *own* schedule is asserted elsewhere
  (`test_daily_digest_job.py`); what is asserted here is the runner's
  behaviour when any tick is re-offered, which is what the daily job
  inherits. Using a test-owned schedule keeps
  `test_job_runner_schedules.py`'s "exactly one piece of recurring work
  is scheduled" true -- the periodic registration below goes into a
  registry of this file's own, never into `runner_app.periodic_registry`.
"""

from __future__ import annotations

import datetime
import os
import uuid
from collections.abc import AsyncIterator

import pytest
from procrastinate import periodic
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from commerce_ops.shared.infrastructure.driven.job_runner import app as runner_app

pytestmark = pytest.mark.anyio

# The same shape of schedule the daily digest declares (tasks.md 2.4):
# once a day at 06:00, interpreted in UTC.
_CRON = "0 6 * * *"

# A worker starting at 09:00, three hours after that day's 06:00 tick.
# This is the redeploy case: `deploy.yml` restarts the worker on every
# merge to `main`, and with an unbounded `max_delay` the fresh deferrer
# offers the morning's tick again.
_FIRST_START = datetime.datetime(2026, 3, 10, 9, 0, tzinfo=datetime.UTC).timestamp()

# A second restart the same day, later still. The tick it offers is the
# same 06:00 moment -- which is the whole point.
_REDEPLOY_LATER_THE_SAME_DAY = datetime.datetime(
    2026, 3, 10, 17, 30, tzinfo=datetime.UTC
).timestamp()


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip(
            "DATABASE_URL is not set. Run the compose file's `postgres` "
            "service locally, apply `alembic upgrade head` (including this "
            "change's runner-schema migration), and point DATABASE_URL at "
            "it to run tests/integration/shared/."
        )
    return url


@pytest.fixture()
async def reader() -> AsyncIterator[AsyncEngine]:
    """A connection to the same database that is *not* the runner's own."""
    engine = create_async_engine(_database_url())
    try:
        yield engine
    finally:
        await engine.dispose()


# --------------------------------------------------------------------------
# A tick task and a schedule owned by this file.
#
# The task itself is registered on the application's own runner, so what
# runs is this application's runner against its own migrated schema. The
# *schedule* is registered in a private registry, so the application's
# scheduled work is untouched.
# --------------------------------------------------------------------------

_RAN: list[int] = []


@runner_app.task(name=f"tests.periodic_dedup.tick-{uuid.uuid4()}")
async def _tick(timestamp: int) -> None:
    """Stands in for any scheduled piece of work; records that it ran."""
    _RAN.append(timestamp)


def _schedule() -> tuple[periodic.PeriodicRegistry, str]:
    """A registry holding one schedule for `_tick`, with a fresh
    `periodic_id` so a re-run of this test file starts from a clean
    deduplication key rather than inheriting the previous run's rows.
    """
    # `PeriodicRegistry.__init__` carries no annotations upstream, which
    # `mypy`'s strict mode reads as an untyped call; nothing here depends
    # on its argument types.
    registry = periodic.PeriodicRegistry()  # type: ignore[no-untyped-call]
    periodic_id = f"dedup-{uuid.uuid4()}"
    registry.register_task(
        task=_tick,
        cron=_CRON,
        periodic_id=periodic_id,
        configure_kwargs={},
    )
    return registry, periodic_id


async def _a_worker_starts_at(
    registry: periodic.PeriodicRegistry, moment: float
) -> list[int]:
    """What a *freshly started* worker does at `moment`: build a deferrer
    with no memory of any previous defer -- as a replaced process has --
    and offer whatever ticks it finds already past.

    Returns the tick timestamps it offered, so that a test can establish
    the second start really did re-offer the same tick rather than
    silently offering nothing.
    """
    deferrer = periodic.PeriodicDeferrer(
        registry=registry, **runner_app.periodic_defaults
    )
    offered = list(deferrer.get_previous_tasks(at=moment))
    await deferrer.defer_jobs(jobs_to_defer=offered)
    return [timestamp for _, timestamp in offered]


async def _drain() -> None:
    """Runs the worker until the queue is empty."""
    await runner_app.run_worker_async(
        wait=False,
        install_signal_handlers=False,
        listen_notify=False,
        delete_jobs="never",
    )


async def _runs_of(engine: AsyncEngine, task_name: str) -> list[dict[str, object]]:
    async with engine.connect() as connection:
        result = await connection.execute(
            text(
                "SELECT id, status, args FROM procrastinate_jobs "
                "WHERE task_name = :task_name ORDER BY id"
            ),
            {"task_name": task_name},
        )
        return [dict(row) for row in result.mappings().all()]


# --------------------------------------------------------------------------
# Requirement: A Window Missed While No Worker Was Available Is Run Once On
# Return
# --------------------------------------------------------------------------


async def test_a_tick_that_already_ran_is_not_run_again_after_a_restart(
    reader: AsyncEngine,
) -> None:
    """Scenario: A single missed window is run on return -- read across a
    process restart, per tasks.md 5.5a.

    WHEN a due moment has already produced a completed run, and a
    replacement process starts and offers that same due moment again
    THEN no second run SHALL be produced.

    SPECIFIED: "the system SHALL run that work once" -- once, not once per
    process that starts afterwards. The requirement's other half (that a
    missed window is not skipped) is covered by the unit-tier
    missed-window tests; this asserts the half those cannot see, because
    it lives in the database rather than in the deferrer's memory.
    """
    registry, _ = _schedule()

    async with runner_app.open_async():
        first_offer = await _a_worker_starts_at(registry, _FIRST_START)
        await _drain()

        after_first = await _runs_of(reader, _tick.name)

        second_offer = await _a_worker_starts_at(registry, _REDEPLOY_LATER_THE_SAME_DAY)
        await _drain()

        after_redeploy = await _runs_of(reader, _tick.name)

    # Precondition, not the assertion under test: the first start really
    # did run the missed tick, and the restart really did re-offer the
    # *same* tick. Without both, "no second run" would hold vacuously.
    assert len(after_first) == 1, (
        "a freshly started worker did not produce exactly one run for the "
        f"missed tick; runs recorded: {after_first}"
    )
    assert after_first[0]["status"] == "succeeded", (
        f"the first run did not complete: {after_first[0]}"
    )
    assert first_offer and second_offer == first_offer, (
        "the restarted worker did not re-offer the same tick, so this test "
        f"establishes nothing: first offered {first_offer}, then {second_offer}"
    )

    # SPECIFIED: no second run.
    assert len(after_redeploy) == 1, (
        "a tick that had already produced a completed run produced "
        f"{len(after_redeploy)} runs after the worker was restarted and "
        f"offered it again; runs recorded: {after_redeploy}"
    )
    assert [job["id"] for job in after_redeploy] == [
        job["id"] for job in after_first
    ], (
        "the run recorded after the restart is not the same run as before "
        f"it: {after_first} then {after_redeploy}"
    )
    assert _RAN.count(first_offer[0]) == 1, (
        f"the work itself ran {_RAN.count(first_offer[0])} times for one "
        "tick, so a redeploy would post a second digest"
    )


async def test_the_deduplication_key_is_the_tick_itself(reader: AsyncEngine) -> None:
    """DERIVED, from design.md's "a third path, which is what makes
    \"once\" true across restarts", and from tasks.md 5.5a's stated reason
    for wanting a test at all -- "a test is what keeps a future schema
    change from removing it silently".

    The test above observes the behaviour; this one names the mechanism
    the behaviour rests on, so that a schema change which drops the
    constraint fails with the reason rather than only with a second
    digest. No `#### Scenario:` block asks for this.
    """
    async with reader.connect() as connection:
        result = await connection.execute(
            text(
                """
                SELECT array_agg(attname ORDER BY attname) AS columns
                FROM pg_constraint
                JOIN pg_class ON pg_class.oid = pg_constraint.conrelid
                JOIN pg_attribute
                  ON pg_attribute.attrelid = pg_constraint.conrelid
                 AND pg_attribute.attnum = ANY (pg_constraint.conkey)
                WHERE pg_class.relname = 'procrastinate_periodic_defers'
                  AND pg_constraint.contype IN ('u', 'p')
                GROUP BY pg_constraint.oid
                """
            )
        )
        keys = [set(row["columns"]) for row in result.mappings().all()]

    assert {"task_name", "periodic_id", "defer_timestamp"} in keys, (
        "the run history no longer carries a uniqueness key over "
        "(task_name, periodic_id, defer_timestamp), which is what stops a "
        "restarted worker from re-running a tick that already ran; keys "
        f"found: {keys}"
    )
